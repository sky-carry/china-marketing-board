# -*- coding: utf-8 -*-
"""投放数据平台 后端 (FastAPI)。
运行: uvicorn app:app --host 0.0.0.0 --port 8000
提供: 账号管理 / 数据查询(看板) / 任务&运行 / 登录刷新 API，并托管前端静态文件。"""
import os, datetime, hashlib, hmac, base64, json, time, secrets, psycopg2, psycopg2.extras
from fastapi import FastAPI, HTTPException, Body, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from starlette.requests import Request

HERE=os.path.dirname(os.path.abspath(__file__))
DSN=os.environ.get("DATABASE_URL","postgresql://postgres:postgres@localhost:5432/ad_data")
def db():
    c=psycopg2.connect(DSN); c.cursor_factory=psycopg2.extras.RealDictCursor; return c

# 统一时间格式化：一律转上海时区(UTC+8)，输出「年-月-日 时:分:秒」
_SH=datetime.timezone(datetime.timedelta(hours=8))
def fmt_dt(v):
    if not v: return None
    try:
        if getattr(v,"tzinfo",None) is None:      # 无时区信息按 UTC 处理
            v=v.replace(tzinfo=datetime.timezone.utc)
        return v.astimezone(_SH).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(v)

app=FastAPI(title="投放数据平台")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ============================ 登录鉴权(单账户共享) ============================
# 密码哈希(pbkdf2)存 DB；登录发 HMAC 签名 token（无状态，服务重启也不失效）。
_SECRET_FILE=os.path.join(HERE,"auth_secret.txt")
def _auth_secret():
    try: return open(_SECRET_FILE,"rb").read().strip()
    except Exception:
        s=secrets.token_hex(32).encode()
        try: open(_SECRET_FILE,"wb").write(s)
        except Exception: pass
        return s
_SECRET=_auth_secret()
def _hash_pw(pw, salt):
    return base64.b64encode(hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 100000)).decode()
def _make_token(username, days=7):
    exp=int(time.time())+days*86400
    payload=base64.urlsafe_b64encode(json.dumps({"u":username,"exp":exp}).encode()).decode().rstrip("=")
    sig=hmac.new(_SECRET, payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"
def _verify_token(token):
    try:
        payload,sig=token.split(".")
        if not hmac.compare_digest(sig, hmac.new(_SECRET, payload.encode(), hashlib.sha256).hexdigest()): return None
        data=json.loads(base64.urlsafe_b64decode(payload+"="*(-len(payload)%4)))
        return data.get("u") if data.get("exp",0)>=time.time() else None
    except Exception:
        return None

_PUBLIC_API={"/api/login","/api/health"}
@app.middleware("http")
async def _auth_mw(request:Request, call_next):
    path=request.url.path
    if request.method!="OPTIONS" and path.startswith("/api/") and path not in _PUBLIC_API:
        auth=request.headers.get("authorization","")
        token=auth[7:] if auth.startswith("Bearer ") else request.cookies.get("token","")
        if not _verify_token(token):
            return JSONResponse({"detail":"未登录或登录已过期"}, status_code=401)
    return await call_next(request)

@app.post("/api/login")
def login(body:dict=Body(...)):
    u=(body.get("username") or "").strip(); pw=body.get("password") or ""
    c=db(); cur=c.cursor()
    cur.execute("SELECT username,salt,pw_hash FROM auth_users WHERE username=%s",(u,))
    row=cur.fetchone(); c.close()
    if not row or not hmac.compare_digest(_hash_pw(pw,row["salt"]), row["pw_hash"]):
        raise HTTPException(401,"账号或密码错误")
    return {"ok":True,"token":_make_token(u),"username":u}

@app.get("/api/me")
def me():  # 能进到这里说明中间件已放行(token 有效)
    return {"ok":True}

@app.post("/api/change_password")
def change_password(body:dict=Body(...)):
    u=(body.get("username") or "").strip(); old=body.get("old") or ""; new=body.get("new") or ""
    if len(new)<6: raise HTTPException(400,"新密码至少 6 位")
    c=db(); c.autocommit=True; cur=c.cursor()
    cur.execute("SELECT salt,pw_hash FROM auth_users WHERE username=%s",(u,)); row=cur.fetchone()
    if not row or not hmac.compare_digest(_hash_pw(old,row["salt"]), row["pw_hash"]):
        c.close(); raise HTTPException(401,"原密码错误")
    salt=secrets.token_hex(16)
    cur.execute("UPDATE auth_users SET salt=%s,pw_hash=%s,updated_at=now() WHERE username=%s",(salt,_hash_pw(new,salt),u))
    c.close(); return {"ok":True}

# ============================ 指标定义(SQL 聚合，比率按明细重算) ============================
METRICS={
 "cost":("消费(元)","SUM(cost)"),
 "real_pay_amount":("真实付款(元)","SUM(real_pay_amount)"),
 "pay_amount":("付款金额(元)","SUM(pay_amount)"),
 "real_roi":("真实ROI","SUM(real_pay_amount)/NULLIF(SUM(cost),0)"),
 "roi":("ROI","SUM(pay_amount)/NULLIF(SUM(cost),0)"),
 "impressions":("展示量","SUM(impressions)"),
 "clicks":("点击量","SUM(clicks)"),
 "ctr":("点击率(%)","SUM(clicks)*100.0/NULLIF(SUM(impressions),0)"),
 "cpm":("CPM(元)","SUM(cost)*1000.0/NULLIF(SUM(impressions),0)"),
 "cpc":("CPC(元)","SUM(cost)/NULLIF(SUM(clicks),0)"),
 "conversions":("转化数","SUM(conversions)"),
 "conversion_cost":("转化成本(元)","SUM(cost)/NULLIF(SUM(conversions),0)"),
 "orders":("订单数","SUM(orders)"),
 "real_orders":("真实订单数","SUM(real_orders)"),
 "refund_rate":("退款率(%)","SUM(refund_rate*cost)/NULLIF(SUM(cost),0)"),
 "direct_pay_amount":("直投下单金额(元)","SUM(direct_pay_amount)"),
 "direct_real_pay_amount":("直投成交金额(元)","SUM(direct_real_pay_amount)"),
 "direct_orders":("直投下单量","SUM(direct_orders)"),
 "direct_real_orders":("直投成交量","SUM(direct_real_orders)"),
 "direct_roi":("直投下单ROI","SUM(direct_pay_amount)/NULLIF(SUM(cost),0)"),
 "direct_real_roi":("直投成交ROI","SUM(direct_real_pay_amount)/NULLIF(SUM(cost),0)"),
}
def _bucket(gran):
    if gran=="month": return "to_char(date,'YYYY-MM')"
    if gran=="week":  return "to_char(date_trunc('week',date),'YYYY-MM-DD')"
    return "to_char(date,'YYYY-MM-DD')"
def _where(platforms, levels, start, end, extra=None):
    cond=["cost IS NOT NULL"]; args=[]
    if platforms:
        cond.append("platform = ANY(%s)"); args.append(platforms)
    if levels:
        lst=levels if isinstance(levels,list) else [x for x in levels.split(",") if x]
        if lst: cond.append("level = ANY(%s)"); args.append(lst)
    if start: cond.append("date>=%s"); args.append(start)
    if end:   cond.append("date<=%s"); args.append(end)
    if extra:
        for k,v in extra.items():
            cond.append(f"{k}=%s"); args.append(v)
    return " AND ".join(cond), args

# ============================ 数据查询 API ============================
@app.get("/api/meta")
def meta():
    c=db(); cur=c.cursor()
    cur.execute("SELECT DISTINCT platform FROM ad_daily ORDER BY platform")
    plats=[r["platform"] for r in cur.fetchall()]
    cur.execute("SELECT DISTINCT platform,level FROM ad_daily ORDER BY platform,level")
    levels={}
    for r in cur.fetchall(): levels.setdefault(r["platform"],[]).append(r["level"])
    cur.execute("SELECT min(date) mn, max(date) mx FROM ad_daily")
    rng=cur.fetchone()
    cur.execute("SELECT platform,tag FROM accounts ORDER BY platform,tag")
    logins={}
    for r in cur.fetchall(): logins.setdefault(r["platform"],[]).append(r["tag"])
    c.close()
    return {"platforms":plats,"levels":levels,"logins":logins,
            "metrics":[{"key":k,"label":v[0]} for k,v in METRICS.items()],
            "date_min":str(rng["mn"]) if rng["mn"] else None,"date_max":str(rng["mx"]) if rng["mx"] else None}

# ============================ 明细表(实体聚合 + 总计) ============================
_DETAIL_METRICS = {  # 列key -> SQL 聚合表达式
 "cost":"SUM(cost)","impressions":"SUM(impressions)","clicks":"SUM(clicks)",
 "ctr":"SUM(clicks)*100.0/NULLIF(SUM(impressions),0)",
 "cpm":"SUM(cost)*1000.0/NULLIF(SUM(impressions),0)","cpc":"SUM(cost)/NULLIF(SUM(clicks),0)",
 "conversions":"SUM(conversions)","conversion_cost":"SUM(cost)/NULLIF(SUM(conversions),0)",
 "orders":"SUM(orders)","pay_amount":"SUM(pay_amount)","roi":"SUM(pay_amount)/NULLIF(SUM(cost),0)",
 "real_pay_amount":"SUM(real_pay_amount)","real_orders":"SUM(real_orders)",
 "real_roi":"SUM(real_pay_amount)/NULLIF(SUM(cost),0)",
 "refund_rate":"SUM(refund_rate*cost)/NULLIF(SUM(cost),0)",
 # 直投归因（小飞机=直推/沸点=直接/微橙=单品/麦斯=主投品）：下单(gross)+成交(net)，ROI 相对消费重算
 "direct_orders":"SUM(direct_orders)","direct_pay_amount":"SUM(direct_pay_amount)",
 "direct_roi":"SUM(direct_pay_amount)/NULLIF(SUM(cost),0)",
 "direct_real_orders":"SUM(direct_real_orders)","direct_real_pay_amount":"SUM(direct_real_pay_amount)",
 "direct_real_roi":"SUM(direct_real_pay_amount)/NULLIF(SUM(cost),0)"}
_METRIC_SQL = ",".join(f"{e} {k}" for k,e in _DETAIL_METRICS.items())
# 汇总行专用聚合：退款率 = (Σ付款 − Σ真实付款)/Σ付款，其余同 _DETAIL_METRICS
_TOTALS_OVERRIDE = {"refund_rate": "(SUM(pay_amount)-SUM(real_pay_amount))*100.0/NULLIF(SUM(pay_amount),0)"}
_TOTALS_SQL = ",".join(f"{_TOTALS_OVERRIDE.get(k, e)} {k}" for k,e in _DETAIL_METRICS.items())

@app.get("/api/detail")
def detail(platform:str, level:str, login:str=None, start:str=None, end:str=None,
           search:str=None, sort:str="cost", limit:int=50, offset:int=0):
    cond=["platform=%s","level=%s","cost IS NOT NULL"]; args=[platform, level]
    if login: cond.append("login_account=%s"); args.append(login)
    if start: cond.append("date>=%s"); args.append(start)
    if end: cond.append("date<=%s"); args.append(end)
    if search: cond.append("(entity_name ILIKE %s OR entity_id ILIKE %s)"); args += [f"%{search}%", f"%{search}%"]
    w=" AND ".join(cond)
    if sort not in _DETAIL_METRICS: sort="cost"
    c=db(); cur=c.cursor()
    cur.execute(f"SELECT count(DISTINCT entity_id) n FROM ad_daily WHERE {w}", args); total=cur.fetchone()["n"]
    cur.execute(f"""SELECT entity_id, max(entity_name) entity_name, max(account_name) account_name,
        max(parent_name) parent_name, max(channel) channel, {_METRIC_SQL}
        FROM ad_daily WHERE {w} GROUP BY entity_id
        ORDER BY {_DETAIL_METRICS[sort]} DESC NULLS LAST LIMIT %s OFFSET %s""", args+[limit,offset])
    rows=[{k:(float(v) if isinstance(v,(int,float)) and k not in ('entity_id',) else v) for k,v in dict(r).items()} for r in cur.fetchall()]
    cur.execute(f"SELECT {_METRIC_SQL} FROM ad_daily WHERE {w}", args)
    totals=dict(cur.fetchone())
    c.close()
    def rnd(d):
        for k in _DETAIL_METRICS:
            if d.get(k) is not None: d[k]=round(float(d[k]),2)
        return d
    return {"total":total, "rows":[rnd(r) for r in rows], "totals":rnd(totals)}

@app.get("/api/summary")
def summary(platforms:str=None, levels:str="", start:str=None, end:str=None):
    pl=platforms.split(",") if platforms else None
    w,args=_where(pl, levels or None, start, end)
    c=db(); cur=c.cursor()
    cur.execute(f"""SELECT SUM(cost) cost, SUM(real_pay_amount) rpay,
        SUM(real_pay_amount)/NULLIF(SUM(cost),0) rroi, SUM(real_orders) rord,
        SUM(refund_rate*cost)/NULLIF(SUM(cost),0) refund FROM ad_daily WHERE {w}""",args)
    r=cur.fetchone(); c.close()
    f=lambda x: float(x) if x is not None else 0
    return {"cost":f(r["cost"]),"real_pay_amount":f(r["rpay"]),"real_roi":round(f(r["rroi"]),2),
            "real_orders":int(r["rord"] or 0),"refund_rate":round(f(r["refund"]),2)}

@app.get("/api/trend")
def trend(metric:str="cost", gran:str="day", group:str="platform",
          platforms:str=None, levels:str=None, start:str=None, end:str=None, topn:int=10):
    if metric not in METRICS: raise HTTPException(400,"unknown metric")
    pl=platforms.split(",") if platforms else None
    w,args=_where(pl, levels or None, start, end)
    bkt=_bucket(gran); expr=METRICS[metric][1]
    c=db(); cur=c.cursor()
    cur.execute(f"SELECT DISTINCT {bkt} t FROM ad_daily WHERE {w} ORDER BY t",args)
    times=[r["t"] for r in cur.fetchall()]
    series=[]
    if group=="total":
        cur.execute(f"SELECT {bkt} t, {expr} v FROM ad_daily WHERE {w} GROUP BY t ORDER BY t",args)
        m={r["t"]:r["v"] for r in cur.fetchall()}
        series=[{"name":"总计","data":[round(float(m[t]),2) if m.get(t) is not None else None for t in times]}]
    else:
        gcol={"platform":"platform","account":"account_name","login":"login_account"}.get(group,"platform")
        # 取该分组的 topN(按消费)
        cur.execute(f"SELECT {gcol} g, SUM(cost) c FROM ad_daily WHERE {w} GROUP BY g ORDER BY c DESC NULLS LAST LIMIT %s",args+[topn])
        groups=[r["g"] for r in cur.fetchall() if r["g"] is not None]
        for g in groups:
            w2=w+f" AND {gcol}=%s"
            cur.execute(f"SELECT {bkt} t, {expr} v FROM ad_daily WHERE {w2} GROUP BY t ORDER BY t",args+[g])
            m={r["t"]:r["v"] for r in cur.fetchall()}
            series.append({"name":g,"data":[round(float(m[t]),2) if m.get(t) is not None else None for t in times]})
    c.close()
    return {"times":times,"series":series,"metric":metric,"label":METRICS[metric][0]}

@app.get("/api/table")
def table(platforms:str=None, levels:str=None, start:str=None, end:str=None, limit:int=500, offset:int=0):
    pl=platforms.split(",") if platforms else None
    w,args=_where(pl, levels, start, end)
    c=db(); cur=c.cursor()
    cur.execute(f"SELECT count(*) n FROM ad_daily WHERE {w}",args); total=cur.fetchone()["n"]
    cur.execute(f"""SELECT platform,login_account,level,date,entity_name,account_name,parent_name,channel,
        cost,impressions,clicks,ctr,cpm,cpc,conversions,conversion_cost,orders,pay_amount,roi,real_pay_amount,real_orders,real_roi,refund_rate,
        direct_orders,direct_pay_amount,direct_roi,direct_real_orders,direct_real_pay_amount,direct_real_roi
        FROM ad_daily WHERE {w} ORDER BY date DESC, cost DESC LIMIT %s OFFSET %s""",args+[limit,offset])
    rows=[dict(r) for r in cur.fetchall()]
    for r in rows: r["date"]=str(r["date"])
    c.close()
    return {"total":total,"rows":rows}

# ============================ 账号管理 API ============================
@app.get("/api/accounts")
def list_accounts():
    c=db(); cur=c.cursor()
    cur.execute("""SELECT a.id,a.platform,a.tag,a.enabled,a.token_status,a.token_updated_at,a.note,
        a.username, COALESCE(a.is_historical,false) AS is_historical,
        (a.password IS NOT NULL AND a.password<>'') AS has_pw,
        (SELECT min(date) FROM ad_daily d WHERE d.login_account=a.tag) first_date,
        (SELECT max(date) FROM ad_daily d WHERE d.login_account=a.tag) last_date,
        (SELECT count(*) FROM ad_daily d WHERE d.login_account=a.tag) rows
        FROM accounts a ORDER BY COALESCE(a.is_historical,false), a.platform, a.tag""")
    rows=[dict(r) for r in cur.fetchall()]
    for r in rows:
        r["token_updated_at"]=fmt_dt(r["token_updated_at"])
        r["first_date"]=str(r["first_date"]) if r["first_date"] else None
        r["last_date"]=str(r["last_date"]) if r["last_date"] else None
    c.close(); return rows

@app.post("/api/accounts")
def add_account(body:dict=Body(...)):
    c=db(); c.autocommit=True; cur=c.cursor()
    cur.execute("INSERT INTO accounts (platform,tag,auth,note) VALUES (%s,%s,%s,%s) RETURNING id",
        (body["platform"],body["tag"],psycopg2.extras.Json(body.get("auth",{})),body.get("note")))
    i=cur.fetchone()["id"]; c.close(); return {"id":i}

def _rename_login_data(cur, old_tag, new_tag):
    """登录标识改名时，把历史数据一起迁移到新名下（去重不丢行）。"""
    if not old_tag or not new_tag or old_tag==new_tag: return
    for tbl,keys in (("ad_daily","level,entity_id,date"),("crawl_progress","level,date")):
        conds=" AND ".join(f"b.{k.strip()}=a.{k.strip()}" for k in keys.split(","))
        cur.execute(f"""UPDATE {tbl} a SET login_account=%s
            WHERE login_account=%s AND NOT EXISTS (
              SELECT 1 FROM {tbl} b WHERE b.platform=a.platform AND b.login_account=%s AND {conds})""",
            (new_tag, old_tag, new_tag))
        cur.execute(f"DELETE FROM {tbl} WHERE login_account=%s",(old_tag,))

@app.put("/api/accounts/{aid}")
def update_account(aid:int, body:dict=Body(...)):
    c=db(); c.autocommit=True; cur=c.cursor()
    old_tag=None
    if "tag" in body:
        cur.execute("SELECT tag FROM accounts WHERE id=%s",(aid,)); r=cur.fetchone()
        old_tag=r["tag"] if r else None
    if body.get("is_historical") is True and "enabled" not in body:
        body["enabled"]=False   # 历史账号强制不启用
    sets=[]; args=[]
    for k in ("platform","tag","enabled","note","username","password","is_historical"):
        if k in body: sets.append(f"{k}=%s"); args.append(body[k])
    if "auth" in body: sets.append("auth=%s"); args.append(psycopg2.extras.Json(body["auth"]))
    if sets:
        args.append(aid); cur.execute(f"UPDATE accounts SET {','.join(sets)} WHERE id=%s",args)
    # 标识改名 -> 级联迁移历史数据，避免"已入库行数变0"
    if "tag" in body and old_tag and body["tag"]!=old_tag:
        _rename_login_data(cur, old_tag, body["tag"])
    c.close(); return {"ok":True}

@app.delete("/api/accounts/{aid}")
def del_account(aid:int):
    c=db(); c.autocommit=True; cur=c.cursor()
    cur.execute("DELETE FROM accounts WHERE id=%s",(aid,)); c.close(); return {"ok":True}

# ============================ 任务 & 运行 API ============================
@app.get("/api/tasks")
def list_tasks():
    c=db(); cur=c.cursor(); cur.execute("SELECT * FROM tasks ORDER BY id")
    rows=[dict(r) for r in cur.fetchall()]
    for r in rows: r["last_run_at"]=fmt_dt(r["last_run_at"]); r["created_at"]=fmt_dt(r["created_at"])
    c.close(); return rows

@app.get("/api/runs")
def list_runs(limit:int=50):
    c=db(); cur=c.cursor(); cur.execute("SELECT * FROM runs ORDER BY id DESC LIMIT %s",(limit,))
    rows=[dict(r) for r in cur.fetchall()]
    for r in rows:
        r["started_at"]=fmt_dt(r["started_at"]); r["finished_at"]=fmt_dt(r["finished_at"])
    c.close(); return rows

@app.put("/api/tasks/{tid}")
def update_task(tid:int, body:dict=Body(...)):
    c=db(); c.autocommit=True; cur=c.cursor()
    sets=[]; args=[]
    for k in ("name","enabled","window_days","interval_minutes","platform","daily_time"):
        if k in body: sets.append(f"{k}=%s"); args.append(body[k])
    if sets: args.append(tid); cur.execute(f"UPDATE tasks SET {','.join(sets)} WHERE id=%s",args)
    c.close(); return {"ok":True}

def _run_task(tid):
    """在后台线程执行滚动抓取并记录 runs。"""
    import crawl
    c=db(); c.autocommit=True; cur=c.cursor()
    cur.execute("SELECT * FROM tasks WHERE id=%s",(tid,)); t=cur.fetchone()
    if not t: c.close(); return
    cur.execute("INSERT INTO runs (task_id,kind,status) VALUES (%s,%s,'running') RETURNING id",(tid,t["kind"]))
    rid=cur.fetchone()["id"]; c.close()
    try:
        wd=t["window_days"] or 15
        res=crawl.crawl_window(window_days=wd, platform=t["platform"])
        st="ok" if res["errors"]==0 else "error"
        detail=f"写入{res['rows']}行" + (f"，失败{res['errors']}(登录失效:{res['bad_logins']})" if res["errors"] else "")
        if res["errors"] and res.get("sample"):
            detail += "；样例: " + " | ".join(res["sample"])[:600]
        rows=res["rows"]
        # 订单同窗口滚动抓取（和广告数据同一节奏：当日1天/近15天）
        try:
            import order_fetchers as OF
            ores=OF.crawl_orders_window(window_days=wd, platform=t["platform"])
            detail += f"；订单{ores['orders']}单" + (f"(失效:{ores['bad_logins']})" if ores["errors"] else "")
            if ores["errors"]: st="error"
        except Exception as oe:
            detail += f"；订单抓取异常:{repr(oe)[:80]}"; st="error"
    except Exception as e:
        st="error"; detail=repr(e)[:200]; rows=0
    c=db(); c.autocommit=True; cur=c.cursor()
    cur.execute("UPDATE runs SET finished_at=now(),status=%s,rows_written=%s,detail=%s WHERE id=%s",(st,rows,detail,rid))
    cur.execute("UPDATE tasks SET last_run_at=now(),last_status=%s WHERE id=%s",(st,tid))
    c.close()

@app.post("/api/tasks/{tid}/run")
def run_task(tid:int):
    import threading
    threading.Thread(target=_run_task,args=(tid,),daemon=True).start()
    return {"ok":True,"msg":"已触发"}

@app.post("/api/accounts/{aid}/login")
def account_login(aid:int):
    import subprocess, sys
    r=subprocess.run([sys.executable, os.path.join(HERE,"auth_login.py"), str(aid)],
                     cwd=HERE, capture_output=True, text=True, timeout=420, encoding="utf-8", errors="replace")
    if r.returncode!=0:
        raise HTTPException(400, (r.stdout or "")[-300:] + (r.stderr or "")[-300:])
    return {"ok":True,"detail":(r.stdout or "")[-200:]}

@app.post("/api/accounts/{aid}/autologin")
def account_autologin(aid:int):
    """用已存的账号密码自动重登(沸点/微橙/麦斯)，或用 profile 续期(小飞机)。无需人工。"""
    import subprocess, sys
    r=subprocess.run([sys.executable, os.path.join(HERE,"auth_autologin.py"), str(aid)],
                     cwd=HERE, capture_output=True, text=True, timeout=240, encoding="utf-8", errors="replace")
    out=((r.stdout or "")+(r.stderr or "")).strip()
    tail=out.splitlines()[-1] if out else ""
    if r.returncode==0:
        return {"ok":True,"detail":tail}
    if r.returncode==3:   # 小飞机会话失效，需人工短信登录
        return {"ok":False,"need_login":True,"detail":tail or "小飞机会话失效，请点『扫码/手动登录』用短信验证码登一次"}
    raise HTTPException(400, tail or out[-300:] or "自动登录失败")

@app.post("/api/keep_tokens")
def keep_tokens(only_expired:bool=False):
    """立即触发一次 token 保活刷新（后台线程），返回已触发。"""
    import threading, crawl
    threading.Thread(target=lambda: crawl.keep_tokens_fresh(only_expired=only_expired), daemon=True).start()
    return {"ok":True,"msg":"已触发后台保活刷新"}

# ============================ 账户看板(全平台所有账户 + 标签) ============================
ACCOUNT_LEVELS=['推广账号','账户维度','账户']

@app.get("/api/account_board")
def account_board(start:str=None, end:str=None, platform:str=None, search:str=None,
                  sort:str="cost", desc:bool=True, limit:int=100, offset:int=0, mode:str="summary"):
    cond=["level = ANY(%s)","cost IS NOT NULL"]; args=[ACCOUNT_LEVELS]
    if platform: cond.append("platform=%s"); args.append(platform)
    if start: cond.append("date>=%s"); args.append(start)
    if end: cond.append("date<=%s"); args.append(end)
    if search: cond.append("(entity_name ILIKE %s OR entity_id ILIKE %s)"); args+=[f"%{search}%",f"%{search}%"]
    w=" AND ".join(cond)
    if sort not in _DETAIL_METRICS: sort="cost"
    daily = (mode=="daily")                                  # 分日：多按 date 分组，每账户每天一行
    grp = "platform,login_account,entity_id" + (",date" if daily else "")
    datesel = "date::text AS date, " if daily else ""
    order = ("date DESC, " if daily else "") + f"{_DETAIL_METRICS[sort]} {'DESC' if desc else 'ASC'} NULLS LAST"
    c=db(); cur=c.cursor()
    cur.execute(f"SELECT count(*) n FROM (SELECT 1 FROM ad_daily WHERE {w} GROUP BY {grp}) x", args)
    total=cur.fetchone()["n"]
    cur.execute(f"""SELECT platform, login_account, entity_id, {datesel} max(entity_name) entity_name, max(channel) channel, {_METRIC_SQL}
        FROM ad_daily WHERE {w} GROUP BY {grp}
        ORDER BY {order} LIMIT %s OFFSET %s""", args+[limit,offset])
    rows=[dict(r) for r in cur.fetchall()]
    cur.execute("SELECT platform,entity_id,tags FROM account_tags")
    tagmap={(r["platform"],r["entity_id"]):r["tags"] for r in cur.fetchall()}
    cur.execute("SELECT * FROM account_meta")
    metamap={r["entity_id"]:dict(r) for r in cur.fetchall()}
    # 汇总行：对当前筛选(全部账户/全部分页)整体聚合；比率列由合计重算，退款率=(Σ付款-Σ真实付款)/Σ付款
    cur.execute(f"SELECT {_TOTALS_SQL} FROM ad_daily WHERE {w}", args)
    totals=dict(cur.fetchone())
    c.close()
    def rnd_metrics(d):
        for k in _DETAIL_METRICS:
            if d.get(k) is not None: d[k]=round(float(d[k]),2)
        return d
    def rnd(d):
        rnd_metrics(d)
        d["tags"]=tagmap.get((d["platform"],d["entity_id"]),[])
        m=metamap.get(d["entity_id"]) or {}
        for f in META_FIELDS: d[f]=m.get(f)
        return d
    return {"total":total,"rows":[rnd(r) for r in rows],"totals":rnd_metrics(totals)}

@app.post("/api/account_tags")
def set_account_tags(body:dict=Body(...)):
    c=db(); c.autocommit=True; cur=c.cursor()
    cur.execute("""INSERT INTO account_tags(platform,entity_id,tags) VALUES(%s,%s,%s)
        ON CONFLICT(platform,entity_id) DO UPDATE SET tags=EXCLUDED.tags, updated_at=now()""",
        (body["platform"], body["entity_id"], psycopg2.extras.Json(body.get("tags",[]))))
    c.close(); return {"ok":True}

# ============================ 投放账户管理(账户自定义属性) ============================
# 6 个业务属性：类目/投放产品/电商平台/投放渠道/店铺/代理商，按 账户ID 存，供账户看板自定义列展示
META_FIELDS=["category","product","ecom_platform","ad_channel","store","agency"]
META_LABELS={"category":"类目","product":"投放产品","ecom_platform":"电商平台",
             "ad_channel":"投放渠道","store":"店铺","agency":"代理商"}

@app.get("/api/adv_accounts")
def adv_accounts(search:str=None):
    """投放账户列表(账户级去重 by entity_id) + 已填的自定义属性 + 各属性已有取值(供下拉候选)。"""
    cond=["level = ANY(%s)","cost IS NOT NULL"]; args=[ACCOUNT_LEVELS]
    if search: cond.append("(entity_name ILIKE %s OR entity_id ILIKE %s)"); args+=[f"%{search}%",f"%{search}%"]
    w=" AND ".join(cond)
    c=db(); cur=c.cursor()
    cur.execute(f"""SELECT entity_id, max(entity_name) entity_name,
        array_agg(DISTINCT platform) platforms, max(date) last_date, sum(cost) cost
        FROM ad_daily WHERE {w} GROUP BY entity_id ORDER BY sum(cost) DESC NULLS LAST""", args)
    rows=[dict(r) for r in cur.fetchall()]
    cur.execute("SELECT * FROM account_meta")
    meta={r["entity_id"]:dict(r) for r in cur.fetchall()}
    for r in rows:
        m=meta.get(r["entity_id"]) or {}
        filled=sum(1 for f in META_FIELDS if m.get(f))
        for f in META_FIELDS: r[f]=m.get(f)
        r["filled"]=filled
        r["complete"]=(filled==len(META_FIELDS))   # 六个全填才算完整
        r["last_date"]=str(r["last_date"]) if r["last_date"] else None
        r["cost"]=round(float(r["cost"]),2) if r["cost"] else 0
    # 未填/不完整的排最前面(complete=False 在前)，其次按消耗降序
    rows.sort(key=lambda r:(r["complete"], -r["cost"]))
    # 每个字段已有的去重取值，前端做下拉候选
    options={}
    for f in META_FIELDS:
        cur.execute(f"SELECT DISTINCT {f} v FROM account_meta WHERE {f} IS NOT NULL AND {f}<>'' ORDER BY v")
        options[f]=[r["v"] for r in cur.fetchall()]
    c.close()
    return {"rows":rows,"options":options,"fields":[{"key":k,"label":META_LABELS[k]} for k in META_FIELDS]}

@app.post("/api/account_meta")
def set_account_meta(body:dict=Body(...)):
    """保存单个账户的自定义属性(只更新传入的字段)。"""
    eid=body.get("entity_id")
    if not eid: raise HTTPException(400,"entity_id required")
    cols=[f for f in META_FIELDS if f in body]
    c=db(); c.autocommit=True; cur=c.cursor()
    if cols:
        vals=[ (body[f] or None) for f in cols ]
        setc=",".join(f"{f}=EXCLUDED.{f}" for f in cols)
        cur.execute(f"""INSERT INTO account_meta(entity_id,{','.join(cols)}) VALUES(%s,{','.join(['%s']*len(cols))})
            ON CONFLICT(entity_id) DO UPDATE SET {setc}, updated_at=now()""", [eid]+vals)
    c.close(); return {"ok":True}

# 导出/导入 Excel（下发给用户离线填写 6 个属性，再导回）
_EXPORT_COLS=[("entity_id","账户ID"),("entity_name","账户名称"),("platforms","平台")]+[(f,META_LABELS[f]) for f in META_FIELDS]

@app.get("/api/adv_accounts/export")
def adv_accounts_export():
    import io, openpyxl
    from urllib.parse import quote
    from fastapi.responses import StreamingResponse
    c=db(); cur=c.cursor()
    cur.execute("""SELECT entity_id, max(entity_name) entity_name, array_agg(DISTINCT platform) platforms, sum(cost) cost
        FROM ad_daily WHERE level = ANY(%s) AND cost IS NOT NULL GROUP BY entity_id
        ORDER BY sum(cost) DESC NULLS LAST""",(ACCOUNT_LEVELS,))
    rows=[dict(r) for r in cur.fetchall()]
    cur.execute("SELECT * FROM account_meta"); meta={r["entity_id"]:dict(r) for r in cur.fetchall()}
    c.close()
    # 未填的排前面，方便用户优先填
    for r in rows:
        m=meta.get(r["entity_id"]) or {}
        r["_filled"]=sum(1 for f in META_FIELDS if m.get(f))
        r["_meta"]=m
    rows.sort(key=lambda r:(r["_filled"]==len(META_FIELDS), -(r["cost"] or 0)))
    wb=openpyxl.Workbook(); ws=wb.active; ws.title="投放账户"
    ws.append([lbl for _,lbl in _EXPORT_COLS])
    for r in rows:
        line=[]
        for key,_ in _EXPORT_COLS:
            if key=="platforms": line.append("/".join(r["platforms"] or []))
            elif key in META_FIELDS: line.append(r["_meta"].get(key) or "")
            else: line.append(str(r.get(key) or ""))
        ws.append(line)
    ws.column_dimensions["A"].width=20; ws.column_dimensions["B"].width=34
    for row in ws.iter_rows(min_row=2,min_col=1,max_col=1):   # 账户ID 列设文本，防长数字被 Excel 变科学计数
        for cell in row: cell.number_format="@"
    buf=io.BytesIO(); wb.save(buf); buf.seek(0)
    fn=quote("投放账户属性表.xlsx")
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{fn}"})

@app.post("/api/adv_accounts/import")
async def adv_accounts_import(request: Request):
    import io, openpyxl
    data=await request.body()   # 前端直接把 .xlsx 二进制作为请求体发来(避免依赖 python-multipart)
    if not data: raise HTTPException(400,"未收到文件")
    try:
        wb=openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as e:
        raise HTTPException(400, "无法解析文件，请上传导出的 .xlsx："+repr(e)[:80])
    ws=wb.active; allrows=list(ws.iter_rows(values_only=True))
    if not allrows: return {"updated":0,"detail":"空文件"}
    header=[str(h).strip() if h is not None else "" for h in allrows[0]]
    lbl2f={META_LABELS[f]:f for f in META_FIELDS}
    idx_id=next((i for i,h in enumerate(header) if h in ("账户ID","账户id","entity_id")), None)
    field_idx={lbl2f[h]:i for i,h in enumerate(header) if h in lbl2f}
    if idx_id is None: raise HTTPException(400,"未找到「账户ID」列，请用导出的模板填写")
    if not field_idx: raise HTTPException(400,"未找到可导入的属性列(类目/投放产品/…)")
    def _eid(v):
        if isinstance(v,float) and v.is_integer(): return str(int(v))   # Excel 把长数字读成 float 的兜底
        return str(v).strip()
    c=db(); c.autocommit=True; cur=c.cursor(); updated=0
    cols=list(field_idx.keys()); setc=",".join(f"{f}=EXCLUDED.{f}" for f in cols)
    for r in allrows[1:]:
        if idx_id>=len(r) or r[idx_id] in (None,""): continue
        eid=_eid(r[idx_id])
        vals=[ (str(r[i]).strip() if i<len(r) and r[i] not in (None,"") else None) for i in (field_idx[f] for f in cols) ]
        if not any(vals): continue   # 整行属性都空的账户跳过，不创建空记录
        cur.execute(f"""INSERT INTO account_meta(entity_id,{','.join(cols)}) VALUES(%s,{','.join(['%s']*len(cols))})
            ON CONFLICT(entity_id) DO UPDATE SET {setc}, updated_at=now()""", [eid]+vals)
        updated+=1
    c.close(); return {"updated":updated}

@app.get("/api/health")
def health(): return {"ok":True,"ts":str(datetime.datetime.now())}

# ============================ 订单明细 API ============================
_ORDER_SORTS={"pay_time","order_date","pay_amount","click_time","refund_time","product_price"}
@app.get("/api/order_meta")
def order_meta():
    c=db(); cur=c.cursor()
    cur.execute("SELECT DISTINCT platform FROM orders ORDER BY platform"); plats=[r["platform"] for r in cur.fetchall()]
    cur.execute("SELECT DISTINCT platform,order_type FROM orders ORDER BY 1,2")
    types={}
    for r in cur.fetchall(): types.setdefault(r["platform"],[]).append(r["order_type"])
    cur.execute("SELECT DISTINCT platform,login_account FROM orders ORDER BY 1,2")
    logins={}
    for r in cur.fetchall(): logins.setdefault(r["platform"],[]).append(r["login_account"])
    cur.execute("SELECT min(order_date) mn, max(order_date) mx FROM orders"); rng=cur.fetchone()
    c.close()
    return {"platforms":plats,"types":types,"logins":logins,
            "date_min":str(rng["mn"]) if rng["mn"] else None,"date_max":str(rng["mx"]) if rng["mx"] else None}

@app.get("/api/orders")
def orders(platform:str=None, login:str=None, order_type:str=None, start:str=None, end:str=None,
           search:str=None, sort:str="pay_time", limit:int=50, offset:int=0):
    cond=[]; args=[]
    if platform: cond.append("platform=%s"); args.append(platform)
    if login: cond.append("login_account=%s"); args.append(login)
    if order_type: cond.append("order_type=%s"); args.append(order_type)
    if start: cond.append("order_date>=%s"); args.append(start)
    if end: cond.append("order_date<=%s"); args.append(end)
    if search:
        cond.append("(order_no ILIKE %s OR main_order_no ILIKE %s OR ad_account_name ILIKE %s OR product_info ILIKE %s)")
        args += [f"%{search}%"]*4
    w=" AND ".join(cond) or "true"
    sort_col=sort if sort in _ORDER_SORTS else "pay_time"
    c=db(); cur=c.cursor()
    cur.execute(f"SELECT count(*) n, COALESCE(sum(pay_amount),0) amt FROM orders WHERE {w}", args)
    agg=cur.fetchone()
    cur.execute(f"SELECT * FROM orders WHERE {w} ORDER BY {sort_col} DESC NULLS LAST LIMIT %s OFFSET %s", args+[limit,offset])
    rows=[dict(r) for r in cur.fetchall()]
    for r in rows:
        for k in ("click_time","pay_time","refund_time"): r[k]=str(r[k]) if r[k] else None
        r["order_date"]=str(r["order_date"]) if r["order_date"] else None
        r["fetched_at"]=fmt_dt(r.get("fetched_at"))
        for k in ("product_price","pay_amount"): r[k]=float(r[k]) if r[k] is not None else None
    c.close()
    return {"total":agg["n"], "sum_pay":float(agg["amt"] or 0), "rows":rows}

# ============================ 定时调度 ============================
_sched_lock_conn=None   # 持有建议锁的专用连接（锁随连接存活；进程退出即释放）
def _acquire_scheduler_lock():
    """尝试获取 Postgres 会话级建议锁：抢到返回 True，说明本进程负责调度；
    抢不到返回 False，说明已有别的实例在调度，本进程不重复启动定时任务。"""
    global _sched_lock_conn
    try:
        conn=psycopg2.connect(DSN); conn.autocommit=True
        cur=conn.cursor()
        cur.execute("SELECT pg_try_advisory_lock(918273645)")   # 固定 key，全项目唯一
        if cur.fetchone()[0]:
            _sched_lock_conn=conn                               # 全局持有，防止连接被回收而释放锁
            return True
        conn.close(); return False
    except Exception as e:
        print("advisory lock 获取失败，回退为直接调度:", repr(e)[:120])
        return True   # 数据库异常时不因锁机制而完全停摆

def _ensure_tables():
    c=db(); c.autocommit=True; cur=c.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS account_tags (
        platform text, entity_id text, tags jsonb DEFAULT '[]',
        updated_at timestamptz DEFAULT now(), PRIMARY KEY(platform,entity_id))""")
    # 投放账户自定义属性(按 账户ID/entity_id 存，跨平台共享；供账户看板自定义列展示)
    cur.execute("""CREATE TABLE IF NOT EXISTS account_meta (
        entity_id text PRIMARY KEY,
        category text, product text, ecom_platform text, ad_channel text, store text, agency text,
        updated_at timestamptz DEFAULT now())""")
    cur.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS daily_time text")  # 每日定时(HH:MM)，空则用 interval_minutes
    cur.execute("ALTER TABLE accounts ADD COLUMN IF NOT EXISTS is_historical boolean DEFAULT false")  # 历史账号：不再抓取、列表置底
    # 登录账户表：默认种子账户 skg
    cur.execute("""CREATE TABLE IF NOT EXISTS auth_users (
        username text PRIMARY KEY, salt text, pw_hash text, updated_at timestamptz DEFAULT now())""")
    cur.execute("SELECT count(*) n FROM auth_users")
    if cur.fetchone()["n"]==0:
        salt=secrets.token_hex(16)
        cur.execute("INSERT INTO auth_users(username,salt,pw_hash) VALUES(%s,%s,%s)",
            ("skg", salt, _hash_pw("skg@A168", salt)))
    c.close()

def _seed_and_schedule():
    c=db(); c.autocommit=True; cur=c.cursor()
    # 任务拆分：当日实时(每5分钟·1天) + 近15天补数(每日08:30·15天)
    # 迁移旧的"全平台滚动(近15天,每5分钟)"单一任务为"当日实时"任务
    cur.execute("""UPDATE tasks SET name='当日实时同步(每5分钟)', window_days=1, interval_minutes=5, daily_time=NULL
                   WHERE kind='rolling' AND window_days=15 AND interval_minutes=5 AND daily_time IS NULL""")
    # 确保存在"当日实时"任务(interval)
    cur.execute("SELECT count(*) n FROM tasks WHERE kind='rolling' AND daily_time IS NULL")
    if cur.fetchone()["n"]==0:
        cur.execute("""INSERT INTO tasks (name,kind,platform,window_days,interval_minutes,enabled)
            VALUES ('当日实时同步(每5分钟)','rolling',NULL,1,5,true)""")
    # 确保存在"近15天补数"任务(每日08:30)
    cur.execute("SELECT count(*) n FROM tasks WHERE kind='rolling' AND daily_time IS NOT NULL")
    if cur.fetchone()["n"]==0:
        cur.execute("""INSERT INTO tasks (name,kind,platform,window_days,interval_minutes,daily_time,enabled)
            VALUES ('近15天补数(每日08:30)','rolling',NULL,15,NULL,'08:30',true)""")
    cur.execute("SELECT * FROM tasks WHERE kind='rolling'"); tasks=cur.fetchall(); c.close()
    # 多实例保护：只有抢到 Postgres 建议锁的进程才启动调度器，避免两个后端进程重复跑同一任务
    if not _acquire_scheduler_lock():
        print(">>> 已有其它后端实例持有调度锁，本实例只提供 API/页面，不启动定时任务")
        return None
    from apscheduler.schedulers.background import BackgroundScheduler
    sch=BackgroundScheduler(timezone="Asia/Shanghai")
    for t in tasks:
        if not t["enabled"]: continue
        if t.get("daily_time"):                       # 每日定时(cron)
            try: hh,mm=[int(x) for x in str(t["daily_time"]).split(":")]
            except Exception: hh,mm=8,30
            sch.add_job(_run_task, "cron", hour=hh, minute=mm,
                        args=[t["id"]], id=f"task{t['id']}", max_instances=1, coalesce=True)
        else:                                         # 间隔(interval)
            sch.add_job(_run_task, "interval", minutes=t["interval_minutes"] or 5,
                        args=[t["id"]], id=f"task{t['id']}", max_instances=1, coalesce=True)
    # token 保活：每 3 小时刷新到期/超龄的登录凭证（沸点/微橙/麦斯密码自动重登；小飞机 profile 续期）
    def _keepalive():
        import crawl
        try: crawl.keep_tokens_fresh(max_age_hours=6)
        except Exception as e: print("keepalive failed:", repr(e)[:120])
    sch.add_job(_keepalive, "interval", hours=3, id="keepalive", max_instances=1, coalesce=True)
    sch.start()
    return sch

_scheduler=None
@app.on_event("startup")
def _startup():
    global _scheduler
    try: _ensure_tables()
    except Exception as e: print("ensure tables failed:", e)
    try: _scheduler=_seed_and_schedule()
    except Exception as e: print("scheduler start failed:", e)

# ============================ 前端静态托管 ============================
# 整个 dist 挂到根路径：favicon.svg / icons.svg / assets/* / index.html 全部由后端托管。
# 本段在文件末尾注册，所有 /api/* 路由已先注册、优先匹配，SPA 静态资源只兜底其余路径。
WEB=os.path.join(HERE,"web","dist")
if os.path.isdir(WEB):
    app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
