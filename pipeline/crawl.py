# -*- coding: utf-8 -*-
"""滚动抓取：重抓最近 window_days 天并 UPSERT 覆盖。供定时任务与手动触发调用。
token 过期时通过 auth_autologin 子进程自动重登（沸点/微橙/麦斯纯密码；小飞机靠 profile 续期）。"""
import datetime, traceback, subprocess, sys, os, time, ssl, socket, urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
import fetchers as F
import db as DB

HERE = os.path.dirname(os.path.abspath(__file__))
PW_PLATFORMS = ("沸点", "微橙", "麦斯")  # 可纯密码自动重登
MAX_WORKERS = 8                          # 并发抓取线程数（同时在飞的请求数）
RETRIES = 2                              # 瞬时网络错误重试次数
RETRY_WAIT = 1.0                         # 重试间隔（秒）

def _auth_err(e):
    s=repr(e).lower()
    return any(x in s for x in ("401","403","token","unauth","expired","login","sign"))

def _transient(e):
    """瞬时网络错误（可重试）：连接/SSL/超时/重置等；auth 与业务错误不重试。"""
    if _auth_err(e):
        return False
    if isinstance(e, urllib.error.HTTPError):
        return e.code in (429, 500, 502, 503, 504)  # 限流/服务端抖动才重试
    return isinstance(e, (urllib.error.URLError, ssl.SSLError, socket.timeout, TimeoutError, ConnectionError))

def _fetch_retry(lg, level, day):
    """带重试的抓取：瞬时网络错误重试 RETRIES 次（间隔 RETRY_WAIT）；auth/业务错误立即抛出。"""
    for attempt in range(RETRIES + 1):
        try:
            return F.fetch(lg, level, day)
        except Exception as e:
            if attempt < RETRIES and _transient(e):
                time.sleep(RETRY_WAIT)
                continue
            raise

def refresh_login(account_id, timeout=200):
    """子进程跑 auth_autologin.py 刷新某账号凭证。返回 (returncode, tail_output)。"""
    try:
        r=subprocess.run([sys.executable, os.path.join(HERE,"auth_autologin.py"), str(account_id)],
                         capture_output=True, text=True, encoding="utf-8", timeout=timeout, cwd=HERE)
        out=((r.stdout or "")+(r.stderr or "")).strip()
        return r.returncode, out[-300:]
    except Exception as e:
        return -1, repr(e)[:200]

def keep_tokens_fresh(max_age_hours=6, only_expired=False):
    """定时保活：刷新过期或超过 max_age 的登录凭证（跳过已知需人工登录的小飞机 need_login）。"""
    conn=DB.connect(); cur=conn.cursor()
    cur.execute("SELECT id,platform,tag,token_status,token_updated_at FROM accounts WHERE enabled AND NOT COALESCE(is_historical,false)")
    rows=cur.fetchall(); conn.close()
    now=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
    done=[]
    for aid,plat,tag,st,upd in rows:
        if st=="need_login":            # 小飞机会话彻底失效，需人工短信登录，不自动重试
            continue
        age_h=(now-upd).total_seconds()/3600 if upd else 1e9
        stale = st in ("expired","error") or age_h>=max_age_hours
        if only_expired: stale = st in ("expired","error")
        if not stale:
            continue
        code,out=refresh_login(aid)
        done.append({"tag":tag,"code":code,"msg":out.splitlines()[-1] if out else ""})
    return done

def _crawl_unit(lg, level, days):
    """抓取单个 (登录, 层级) 的全部天，内部按天串行。每个单元独立 DB 连接，可安全并发。
    返回 {tag, rows, errs:[...], auth_fail:bool}。"""
    p=lg["platform"]; tag=lg["tag"]
    conn=DB.connect(); total=0; errs=[]; auth_fail=False
    try:
        for day in days:
            try:
                rows=_fetch_retry(lg,level,day)
                DB.upsert(conn,rows)
                DB.mark_progress(conn,p,tag,level,day,len(rows))
                total+=len(rows)
            except Exception as e:
                errs.append(f"{p}/{tag}/{level}/{day}: {repr(e)[:50]}")
                if _auth_err(e): auth_fail=True
                break  # 该(login,level)本天失败，跳过剩余天，避免刷屏
    finally:
        conn.close()
    return {"tag":tag,"rows":total,"errs":errs,"auth_fail":auth_fail}

def crawl_window(window_days=15, platform=None, mark_expired=True, auto_relogin=True, max_workers=MAX_WORKERS):
    logins=F.load_logins()
    if platform: logins=[l for l in logins if l["platform"]==platform]
    end=datetime.date.today(); start=end-datetime.timedelta(days=window_days-1)
    days=[start+datetime.timedelta(days=i) for i in range((end-start).days+1)]
    tag2id={l["tag"]:l.get("id") for l in logins}
    # 工作单元：每个 (登录, 层级) 一个任务，线程池并发；单元内部仍按天串行（保留 auth 失败跳过剩余天的逻辑）
    units=[]; attempted=set()
    for lg in logins:
        if not lg.get("auth"):   # 未登录(空凭证)：跳过，不触碰状态
            continue
        attempted.add(lg["tag"])
        for lv in F.LEVELS.get(lg["platform"], []):   # 未知平台(代码未加载)跳过，不崩溃
            units.append((lg,lv))
    total=0; errs=[]; bad_logins=set()
    if units:
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futs=[ex.submit(_crawl_unit, lg, lv, days) for lg,lv in units]
            for f in as_completed(futs):
                r=f.result()
                total+=r["rows"]; errs+=r["errs"]
                if r["auth_fail"]: bad_logins.add(r["tag"])
    # 平台迁移去重：删除迁走平台残留的重复账户行(小飞机→沸点等，见 docs/业务说明.md)
    deduped=0
    try:
        conn=DB.connect(); deduped=DB.dedupe_migrated_accounts(conn); conn.close()
    except Exception as e:
        errs.append(f"dedupe: {repr(e)[:60]}")
    # 标记登录态
    if mark_expired:
        conn=DB.connect()
        with conn.cursor() as cur:
            for tag in attempted:   # 只更新真正尝试过的
                st="expired" if tag in bad_logins else "ok"
                cur.execute("UPDATE accounts SET token_status=%s WHERE tag=%s",(st,tag))
        conn.commit(); conn.close()
    # 自动重登：对本轮失败的登录尝试重新登录，下一轮即可恢复
    relogin=[]
    if auto_relogin and bad_logins:
        for tag in bad_logins:
            aid=tag2id.get(tag)
            if aid:
                code,out=refresh_login(aid)
                relogin.append({"tag":tag,"code":code,"msg":out.splitlines()[-1] if out else ""})
    return {"rows":total,"errors":len(errs),"bad_logins":list(bad_logins),
            "relogin":relogin,"sample":errs[:5],"deduped":deduped}
