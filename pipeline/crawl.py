# -*- coding: utf-8 -*-
"""滚动抓取：重抓最近 window_days 天并 UPSERT 覆盖。供定时任务与手动触发调用。"""
import datetime, traceback
import fetchers as F
import db as DB

def _auth_err(e):
    s=repr(e).lower()
    return any(x in s for x in ("401","403","token","unauth","expired","login","sign"))

def crawl_window(window_days=15, platform=None, mark_expired=True):
    logins=F.load_logins()
    if platform: logins=[l for l in logins if l["platform"]==platform]
    end=datetime.date.today(); start=end-datetime.timedelta(days=window_days-1)
    days=[start+datetime.timedelta(days=i) for i in range((end-start).days+1)]
    conn=DB.connect(); total=0; errs=[]; bad_logins=set(); attempted=set()
    for lg in logins:
        p=lg["platform"]; tag=lg["tag"]
        if not lg.get("auth"):   # 未登录(空凭证)：跳过，不触碰状态
            continue
        attempted.add(tag)
        for lv in F.LEVELS[p]:
            for day in days:
                try:
                    rows=F.fetch(lg,lv,day)
                    DB.upsert(conn,rows)
                    DB.mark_progress(conn,p,tag,lv,day,len(rows))
                    total+=len(rows)
                except Exception as e:
                    errs.append(f"{p}/{tag}/{lv}/{day}: {repr(e)[:50]}")
                    if _auth_err(e): bad_logins.add(tag)
                    break  # 该流本天失败，跳过该(login,level)剩余天，避免刷屏
    # 标记登录态
    if mark_expired:
        with conn.cursor() as cur:
            for lg in logins:
                if lg["tag"] not in attempted: continue  # 只更新真正尝试过的
                st="expired" if lg["tag"] in bad_logins else "ok"
                cur.execute("UPDATE accounts SET token_status=%s WHERE tag=%s",(st,lg["tag"]))
        conn.commit()
    conn.close()
    return {"rows":total,"errors":len(errs),"bad_logins":list(bad_logins),"sample":errs[:5]}
