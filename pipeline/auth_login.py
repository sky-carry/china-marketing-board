# -*- coding: utf-8 -*-
"""登录/刷新 token：为某个 account 打开浏览器(服务器机器上)，用户登录后抓取凭证并写回 DB。
用法(子进程): python auth_login.py <account_id>
"""
import os
import sys, os, io, time, json, urllib.parse
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
import psycopg2, psycopg2.extras
from playwright.sync_api import sync_playwright

HERE=os.path.dirname(os.path.abspath(__file__))
DSN=os.environ.get("DATABASE_URL","postgresql://postgres:postgres@localhost:5432/ad_data")
PROFILES=os.path.join(HERE,"profiles")
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
CLICK="""(name)=>{let e=[...document.querySelectorAll('*')].filter(x=>x.children.length===0&&(x.textContent||'').trim()===name);e.sort((a,b)=>a.textContent.length-b.textContent.length);if(e.length){e[0].click();return true}return false}"""

def profile_dir(tag):
    safe="".join(c if c.isalnum() or c in "-_" else "_" for c in tag)
    d=os.path.join(PROFILES,safe); os.makedirs(d,exist_ok=True); return d

def grab(platform, tag):
    g={}
    with sync_playwright() as p:
        ctx=p.chromium.launch_persistent_context(profile_dir(tag), headless=False, args=["--start-maximized"], no_viewport=True)
        pg=ctx.pages[0] if ctx.pages else ctx.new_page()
        def on_req(req):
            u=req.url; h=req.headers
            if platform=="小飞机" and "/v1/" in u and req.method=="POST":
                if h.get("authorization","").startswith("Bearer "):
                    g["token"]=h["authorization"][7:]; g["op_uid"]=h.get("td-op-uid","")
                    ck=h.get("cookie","")
                    for part in ck.split("; "):
                        if part.startswith("td.sid="): g["sid"]=part[7:]
            elif platform=="沸点" and "api.fifay.cn" in u:
                if h.get("token"): g["token"]=h["token"]; g["did"]=h.get("did","")
            elif platform=="微橙" and "taotik.douyongtuan.com/business/" in u and req.post_data:
                q=urllib.parse.parse_qs(req.post_data)
                if "session_id" in q: g["session_id"]=q["session_id"][0]; g["customer_id"]=q.get("customer_id",[""])[0]
            elif platform=="麦斯" and "preapi.maxengine.cn/admin/" in u:
                if h.get("x-token"): g["x_token"]=h["x-token"]; g["signip"]=h.get("signip","") or g.get("signip","")
        pg.on("request", on_req)
        entry={"小飞机":"https://td.smallfighter.com/#serving","沸点":"https://admin.fifay.cn/admin/index.html",
               "微橙":"https://business.douyongtuan.com/#/tiktok","麦斯":"https://ad.maxengine.cn/media_data/xhs"}[platform]
        try: pg.goto(entry, timeout=60000)
        except Exception: pass
        print(">>> 请在浏览器登录 %s / %s（最多等 6 分钟）..."%(platform,tag), flush=True)
        need=("token","sid","op_uid") if platform=="小飞机" else \
             ("token","did") if platform=="沸点" else \
             ("session_id",) if platform=="微橙" else ("x_token",)
        for i in range(180):
            if all(k in g for k in need): break
            try:
                if platform=="麦斯":
                    pg.evaluate(CLICK,"广告平台"); pg.wait_for_timeout(700); pg.evaluate(CLICK,"聚光平台")
                elif platform=="微橙":
                    pg.evaluate(CLICK,"数据统计"); pg.wait_for_timeout(500); pg.evaluate(CLICK,"巨量引擎")
                elif platform=="小飞机" and "token" not in g:
                    for ck in ctx.cookies():
                        if ck["name"]=="td.token": g["token"]=ck["value"]
                        elif ck["name"]=="td-op-uid": g["op_uid"]=ck["value"]
                        elif ck["name"]=="td.sid": g["sid"]=ck["value"]   # 保持浏览器原编码(s%3A...)，勿再 quote
            except Exception: pass
            if platform=="麦斯" and "signip" not in g:
                try: g["signip"]=pg.evaluate("()=>localStorage.getItem('signip')||''") or ""
                except Exception: pass
            time.sleep(2)
        ctx.close()
    return g if all(k in g for k in need) else None

def main():
    aid=int(sys.argv[1])
    c=psycopg2.connect(DSN); c.autocommit=True; cur=c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT platform,tag,auth FROM accounts WHERE id=%s",(aid,)); row=cur.fetchone()
    if not row: print("account not found"); sys.exit(1)
    auth=grab(row["platform"], row["tag"])
    if not auth:
        print("FAIL 未取到凭证"); sys.exit(2)
    merged={**dict(row.get("auth") or {}), **auth}   # 合并：保留 op_uids 等字段，不覆盖
    cur.execute("UPDATE accounts SET auth=%s, token_status='ok', token_updated_at=now() WHERE id=%s",
        (psycopg2.extras.Json(merged), aid))
    print("OK 已更新凭证:", list(auth.keys())); c.close()

if __name__=="__main__":
    main()
