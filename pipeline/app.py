# -*- coding: utf-8 -*-
"""投放数据平台 后端 (FastAPI)。
运行: uvicorn app:app --host 0.0.0.0 --port 8000
提供: 账号管理 / 数据查询(看板) / 任务&运行 / 登录刷新 API，并托管前端静态文件。"""
import os, datetime, psycopg2, psycopg2.extras
from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

HERE=os.path.dirname(os.path.abspath(__file__))
DSN="postgresql://postgres:postgres@localhost:5432/ad_data"
def db():
    c=psycopg2.connect(DSN); c.cursor_factory=psycopg2.extras.RealDictCursor; return c

app=FastAPI(title="投放数据平台")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

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
    c.close()
    return {"platforms":plats,"levels":levels,
            "metrics":[{"key":k,"label":v[0]} for k,v in METRICS.items()],
            "date_min":str(rng["mn"]) if rng["mn"] else None,"date_max":str(rng["mx"]) if rng["mx"] else None}

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
        gcol="platform" if group=="platform" else "account_name"
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
        cost,impressions,clicks,ctr,cpm,cpc,conversions,orders,pay_amount,roi,real_pay_amount,real_orders,real_roi,refund_rate
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
        (SELECT min(date) FROM ad_daily d WHERE d.login_account=a.tag) first_date,
        (SELECT max(date) FROM ad_daily d WHERE d.login_account=a.tag) last_date,
        (SELECT count(*) FROM ad_daily d WHERE d.login_account=a.tag) rows
        FROM accounts a ORDER BY a.platform,a.tag""")
    rows=[dict(r) for r in cur.fetchall()]
    for r in rows:
        r["token_updated_at"]=str(r["token_updated_at"]) if r["token_updated_at"] else None
        r["first_date"]=str(r["first_date"]) if r["first_date"] else None
        r["last_date"]=str(r["last_date"]) if r["last_date"] else None
    c.close(); return rows

@app.post("/api/accounts")
def add_account(body:dict=Body(...)):
    c=db(); c.autocommit=True; cur=c.cursor()
    cur.execute("INSERT INTO accounts (platform,tag,auth,note) VALUES (%s,%s,%s,%s) RETURNING id",
        (body["platform"],body["tag"],psycopg2.extras.Json(body.get("auth",{})),body.get("note")))
    i=cur.fetchone()["id"]; c.close(); return {"id":i}

@app.put("/api/accounts/{aid}")
def update_account(aid:int, body:dict=Body(...)):
    c=db(); c.autocommit=True; cur=c.cursor()
    sets=[]; args=[]
    for k in ("platform","tag","enabled","note"):
        if k in body: sets.append(f"{k}=%s"); args.append(body[k])
    if "auth" in body: sets.append("auth=%s"); args.append(psycopg2.extras.Json(body["auth"]))
    if sets:
        args.append(aid); cur.execute(f"UPDATE accounts SET {','.join(sets)} WHERE id=%s",args)
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
    for r in rows: r["last_run_at"]=str(r["last_run_at"]) if r["last_run_at"] else None; r["created_at"]=str(r["created_at"])
    c.close(); return rows

@app.get("/api/runs")
def list_runs(limit:int=50):
    c=db(); cur=c.cursor(); cur.execute("SELECT * FROM runs ORDER BY id DESC LIMIT %s",(limit,))
    rows=[dict(r) for r in cur.fetchall()]
    for r in rows:
        r["started_at"]=str(r["started_at"]); r["finished_at"]=str(r["finished_at"]) if r["finished_at"] else None
    c.close(); return rows

@app.put("/api/tasks/{tid}")
def update_task(tid:int, body:dict=Body(...)):
    c=db(); c.autocommit=True; cur=c.cursor()
    sets=[]; args=[]
    for k in ("name","enabled","window_days","interval_minutes","platform"):
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
        res=crawl.crawl_window(window_days=t["window_days"] or 15, platform=t["platform"])
        st="ok" if res["errors"]==0 else "error"
        detail=f"写入{res['rows']}行" + (f"，失败{res['errors']}(登录失效:{res['bad_logins']})" if res["errors"] else "")
        rows=res["rows"]
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

@app.get("/api/health")
def health(): return {"ok":True,"ts":str(datetime.datetime.now())}

# ============================ 定时调度 ============================
def _seed_and_schedule():
    c=db(); c.autocommit=True; cur=c.cursor()
    cur.execute("SELECT count(*) n FROM tasks")
    if cur.fetchone()["n"]==0:
        cur.execute("""INSERT INTO tasks (name,kind,platform,window_days,interval_minutes,enabled)
            VALUES ('全平台滚动(近15天)','rolling',NULL,15,5,true)""")
    cur.execute("SELECT * FROM tasks WHERE kind='rolling'"); tasks=cur.fetchall(); c.close()
    from apscheduler.schedulers.background import BackgroundScheduler
    sch=BackgroundScheduler(timezone="Asia/Shanghai")
    for t in tasks:
        if t["enabled"]:
            sch.add_job(_run_task, "interval", minutes=t["interval_minutes"] or 5,
                        args=[t["id"]], id=f"task{t['id']}", max_instances=1, coalesce=True)
    sch.start()
    return sch

_scheduler=None
@app.on_event("startup")
def _startup():
    global _scheduler
    try: _scheduler=_seed_and_schedule()
    except Exception as e: print("scheduler start failed:", e)

# ============================ 前端静态托管 ============================
WEB=os.path.join(HERE,"web","dist")
if os.path.isdir(WEB):
    app.mount("/assets", StaticFiles(directory=os.path.join(WEB,"assets")), name="assets")
    @app.get("/")
    def index(): return FileResponse(os.path.join(WEB,"index.html"))
