# -*- coding: utf-8 -*-
"""同时为所有 token_status='need_login' 的账号弹出浏览器窗口(平铺)，用户逐个登录，
每登好一个即抓 token 写库并关闭该窗口。最多等 10 分钟。"""
import os, io, sys, time, json, urllib.parse
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
import psycopg2, psycopg2.extras
from playwright.sync_api import sync_playwright

HERE=os.path.dirname(os.path.abspath(__file__))
DSN=os.environ.get("DATABASE_URL","postgresql://postgres:postgres@localhost:5432/ad_data")
PROFILES=os.path.join(HERE,"profiles")
CLICK="""(name)=>{let e=[...document.querySelectorAll('*')].filter(x=>x.children.length===0&&(x.textContent||'').trim()===name);e.sort((a,b)=>a.textContent.length-b.textContent.length);if(e.length){e[0].click();return true}return false}"""
ENTRY={"小飞机":"https://td.smallfighter.com/#serving","沸点":"https://admin.fifay.cn/admin/index.html",
       "微橙":"https://business.douyongtuan.com/#/tiktok","麦斯":"https://ad.maxengine.cn/media_data/xhs"}
NEED={"小飞机":("token","sid","op_uid"),"沸点":("token","did"),"微橙":("session_id",),"麦斯":("x_token",)}

def profile_dir(tag):
    safe="".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in tag)
    d=os.path.join(PROFILES,safe); os.makedirs(d,exist_ok=True); return d

def make_handler(platform, got):
    def on_req(req):
        u=req.url; h=req.headers
        if platform=="小飞机" and "/v1/" in u and req.method=="POST":
            if h.get("authorization","").startswith("Bearer "):
                got["token"]=h["authorization"][7:]; got["op_uid"]=h.get("td-op-uid","")
                for part in h.get("cookie","").split("; "):
                    if part.startswith("td.sid="): got["sid"]=part[7:]
        elif platform=="沸点" and "api.fifay.cn" in u:
            if h.get("token"): got["token"]=h["token"]; got["did"]=h.get("did","")
        elif platform=="微橙" and "taotik.douyongtuan.com/business/" in u and req.post_data:
            q=urllib.parse.parse_qs(req.post_data)
            if "session_id" in q: got["session_id"]=q["session_id"][0]; got["customer_id"]=q.get("customer_id",[""])[0]
        elif platform=="麦斯" and "preapi.maxengine.cn/admin/" in u:
            if h.get("x-token"): got["x_token"]=h["x-token"]; got["signip"]=h.get("signip","") or got.get("signip","")
    return on_req

def main():
    c=psycopg2.connect(DSN); c.autocommit=True
    cur=c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT id,platform,tag FROM accounts WHERE token_status='need_login' ORDER BY id")
    accts=cur.fetchall()
    if not accts:
        print("没有待登录账号"); return
    print(f">>> 弹出 {len(accts)} 个窗口，请在每个窗口登录对应账号：")
    for a in accts: print(f"    - {a['platform']} / {a['tag']}")
    tiles=[(0,0),(770,0),(0,440),(770,440),(380,220)]
    with sync_playwright() as p:
        st={}
        for i,a in enumerate(accts):
            x,y=tiles[i%len(tiles)]
            ctx=p.chromium.launch_persistent_context(profile_dir(a["tag"]), headless=False,
                 args=[f"--window-position={x},{y}",f"--window-size=760,430"], no_viewport=True)
            pg=ctx.pages[0] if ctx.pages else ctx.new_page()
            got={}
            pg.on("request", make_handler(a["platform"], got))
            try: pg.goto(ENTRY[a["platform"]], timeout=60000)
            except Exception: pass
            st[a["id"]]={"a":a,"ctx":ctx,"pg":pg,"got":got,"done":False}
        # banner 标注每个窗口
        for s in st.values():
            try: s["pg"].evaluate("""(t)=>{let d=document.createElement('div');d.textContent='登录: '+t;d.style.cssText='position:fixed;top:0;left:0;z-index:2147483647;background:#409EFF;color:#fff;padding:4px 10px;font:14px sans-serif';document.body.appendChild(d);}""", s["a"]["tag"])
            except Exception: pass
        for _ in range(260):
            alldone=True
            for aid,s in st.items():
                if s["done"]: continue
                plat=s["a"]["platform"]
                try:
                    if plat=="麦斯": s["pg"].evaluate(CLICK,"广告平台"); s["pg"].wait_for_timeout(400); s["pg"].evaluate(CLICK,"聚光平台")
                    elif plat=="微橙": s["pg"].evaluate(CLICK,"数据统计"); s["pg"].wait_for_timeout(300); s["pg"].evaluate(CLICK,"巨量引擎")
                    elif plat=="小飞机" and "token" not in s["got"]:
                        for ck in s["ctx"].cookies():
                            if ck["name"]=="td.token": s["got"]["token"]=ck["value"]
                            elif ck["name"]=="td-op-uid": s["got"]["op_uid"]=ck["value"]
                            elif ck["name"]=="td.sid": s["got"]["sid"]=urllib.parse.quote(ck["value"],safe="")
                    if plat=="麦斯" and "signip" not in s["got"]:
                        s["got"]["signip"]=s["pg"].evaluate("()=>localStorage.getItem('signip')||''") or ""
                except Exception: pass
                if all(k in s["got"] for k in NEED[plat]):
                    cur.execute("UPDATE accounts SET auth=%s,token_status='ok',token_updated_at=now() WHERE id=%s",
                                (psycopg2.extras.Json(s["got"]), aid))
                    print(f">>> ✔ 已登录并入库: {plat}/{s['a']['tag']}", flush=True)
                    try: s["ctx"].close()
                    except Exception: pass
                    s["done"]=True
                else:
                    alldone=False
            if alldone: break
            time.sleep(2)
        for s in st.values():
            if not s["done"]:
                print(f">>> ✘ 超时未登录: {s['a']['platform']}/{s['a']['tag']}")
                try: s["ctx"].close()
                except Exception: pass
    c.close()
    print(">>> 完成")

if __name__=="__main__":
    main()
