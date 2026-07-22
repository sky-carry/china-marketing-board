# -*- coding: utf-8 -*-
"""投放数据平台 后端 (FastAPI)。
运行: uvicorn app:app --host 0.0.0.0 --port 8000
提供: 账号管理 / 数据查询(看板) / 任务&运行 / 登录刷新 API，并托管前端静态文件。"""
import os, datetime, hashlib, hmac, base64, json, time, secrets, threading, urllib.request, urllib.parse, psycopg2, psycopg2.extras
from fastapi import FastAPI, HTTPException, Body, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
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
def _week_start_ts():
    """本周一 0:00(上海) 的 epoch 秒。只有本周一0点之后签发的 token 才有效 —— 实现「每周一强制重新登录」。"""
    now=datetime.datetime.now(_SH)
    monday0=(now - datetime.timedelta(days=now.weekday())).replace(hour=0,minute=0,second=0,microsecond=0)
    return int(monday0.timestamp())
def _make_token(username, role="user", days=7):
    now=int(time.time()); exp=now+days*86400
    payload=base64.urlsafe_b64encode(json.dumps({"u":username,"r":role,"exp":exp,"iat":now}).encode()).decode().rstrip("=")
    sig=hmac.new(_SECRET, payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"
def _token_data(token):
    """校验签名+有效期，返回 payload dict({u,r,exp,iat}) 或 None。
    另：本周一0点前签发的 token 一律失效（每周一强制重登一次）。"""
    try:
        payload,sig=token.split(".")
        if not hmac.compare_digest(sig, hmac.new(_SECRET, payload.encode(), hashlib.sha256).hexdigest()): return None
        data=json.loads(base64.urlsafe_b64decode(payload+"="*(-len(payload)%4)))
        if data.get("exp",0)<time.time(): return None            # 常规 7 天过期
        if data.get("iat",0)<_week_start_ts(): return None        # 本周一0点前签发 -> 失效，需重登
        return data
    except Exception:
        return None

_PUBLIC_API={"/api/login","/api/health","/api/auth_config","/api/feishu/login_url","/api/feishu/callback","/api/dev_login"}
# 管理员专属接口(账号管理/用户管理/定时任务页)——仅密码登录(skg)或 is_admin 用户可访问
_ADMIN_PREFIXES=("/api/accounts","/api/adv_accounts","/api/account_meta","/api/account_tags","/api/users","/api/tasks","/api/runs","/api/keep_tokens",
                 "/api/auth_accounts","/api/scope_options")
def _is_admin_path(p):
    return any(p==x or p.startswith(x+"/") for x in _ADMIN_PREFIXES)
@app.middleware("http")
async def _auth_mw(request:Request, call_next):
    path=request.url.path
    if request.method!="OPTIONS" and path.startswith("/api/") and path not in _PUBLIC_API:
        auth=request.headers.get("authorization","")
        token=auth[7:] if auth.startswith("Bearer ") else request.cookies.get("token","")
        data=_token_data(token)
        if not data:
            return JSONResponse({"detail":"未登录或登录已过期"}, status_code=401)
        if _is_admin_path(path) and data.get("r")!="admin":
            return JSONResponse({"detail":"无权限：该功能仅管理员可用"}, status_code=403)
    return await call_next(request)

# ============================ 数据可见范围(账号密码普通用户按 代理商/账户 隔离) ============================
def _req_token(request:Request):
    auth=request.headers.get("authorization",""); tok=auth[7:] if auth.startswith("Bearer ") else request.cookies.get("token","")
    return _token_data(tok)

def _scope_ids(request:Request):
    """当前用户可见的账户 entity_id 列表；返回 None=不限制(管理员/飞书用户)。
    仅「密码普通账号」(auth_users 里 is_admin=false)受限。范围规则：
      属性过滤 = 代理商、店铺 各自过滤，两者都选=交集(AND)，只选其一=仅按该维度；
      最终 = 显式选中账户 ∪ 属性过滤命中的账户。
    已授权但范围为空 -> 返回 []（看不到任何数据）。"""
    d=_req_token(request)
    if not d or d.get("r")=="admin": return None
    u=d.get("u")
    if not u: return None
    c=db(); cur=c.cursor()
    cur.execute("SELECT is_admin, scope_agencies, scope_stores, scope_accounts FROM auth_users WHERE username=%s",(u,))
    row=cur.fetchone()
    if not row or row["is_admin"]:      # 不在密码表(飞书用户) 或 管理员 -> 不限制
        c.close(); return None
    agencies=list(row["scope_agencies"] or []); stores=list(row["scope_stores"] or [])
    ids=set(str(x) for x in (row["scope_accounts"] or []))
    if agencies or stores:              # 代理商∩店铺(都选=交集，仅一者=按该维度)
        mc=[]; ma=[]
        if agencies: mc.append("agency = ANY(%s)"); ma.append(agencies)
        if stores:   mc.append("store = ANY(%s)"); ma.append(stores)
        cur.execute("SELECT entity_id FROM account_meta WHERE "+" AND ".join(mc), ma)
        ids |= {r["entity_id"] for r in cur.fetchall()}
    c.close(); return list(ids)

def _scope_cond(request:Request, col="entity_id"):
    """返回 (sql条件 or None, 参数值 or None)。None=不加过滤；'false'=空结果(无授权范围)。"""
    ids=_scope_ids(request)
    if ids is None: return None, None
    if not ids: return "false", None
    return f"{col} = ANY(%s)", ids

def _apply_scope(w, args, request:Request, col="entity_id"):
    """把当前用户的数据范围条件并入已有 WHERE(w,args)。管理员/飞书用户不变。"""
    cond,val=_scope_cond(request, col)
    if cond is None: return w, args
    w=f"({w}) AND {cond}" if w else cond
    return w, (args+[val] if val is not None else args)

@app.post("/api/login")
def login(body:dict=Body(...)):
    u=(body.get("username") or "").strip(); pw=body.get("password") or ""
    c=db(); c.autocommit=True; cur=c.cursor()
    cur.execute("SELECT username,salt,pw_hash,name,is_admin,is_active,expires_at FROM auth_users WHERE username=%s",(u,))
    row=cur.fetchone()
    if not row or not hmac.compare_digest(_hash_pw(pw,row["salt"]), row["pw_hash"]):
        c.close(); raise HTTPException(401,"账号或密码错误")
    if not row["is_active"]:
        c.close(); raise HTTPException(403,"账号已停用，请联系管理员")
    if row["expires_at"] and row["expires_at"] < datetime.datetime.now(_SH).date():
        c.close(); raise HTTPException(403,"账号已过期，请联系管理员")
    cur.execute("""UPDATE auth_users SET first_login_at=COALESCE(first_login_at,now()),
        last_login_at=now(), login_count=COALESCE(login_count,0)+1 WHERE username=%s""",(u,))
    c.close()
    admin=bool(row["is_admin"])
    return {"ok":True,"token":_make_token(u,role="admin" if admin else "user"),
            "username":u,"admin":admin,"name":row["name"] or u}

@app.get("/api/me")
def me(request:Request):  # 能进到这里说明中间件已放行(token 有效)
    auth=request.headers.get("authorization",""); tok=auth[7:] if auth.startswith("Bearer ") else request.cookies.get("token","")
    d=_token_data(tok); sub=d.get("u") if d else None; admin=bool(d and d.get("r")=="admin"); user=None; name=None
    if sub:
        try:
            c=db(); cur=c.cursor()
            cur.execute("SELECT id,open_id,name,avatar_url,email,source,is_admin,last_login_at,login_count FROM users WHERE open_id=%s",(sub,))
            user=cur.fetchone()
            if not user:   # 密码账号：取显示名
                cur.execute("SELECT name FROM auth_users WHERE username=%s",(sub,)); r=cur.fetchone()
                name=(r["name"] if r else None) or sub
            c.close()
        except Exception: pass
    return {"ok":True,"admin":admin,"user":user,"name":name}

@app.post("/api/heartbeat")
def heartbeat(request:Request, body:dict=Body(...)):
    """前端心跳：把本次活跃秒数累加到 (用户, 今日) 停留时长。单次最多计 120 秒(防刷)。"""
    d=_req_token(request); key=d.get("u") if d else None
    if not key: return {"ok":True}
    sec=min(max(int(body.get("seconds") or 0),0),120)
    if sec<=0: return {"ok":True}
    today=datetime.datetime.now(_SH).date().isoformat()
    c=db(); c.autocommit=True; cur=c.cursor()
    cur.execute("""INSERT INTO user_activity(user_key,date,seconds) VALUES(%s,%s,%s)
        ON CONFLICT(user_key,date) DO UPDATE SET seconds=user_activity.seconds+EXCLUDED.seconds, updated_at=now()""",(key,today,sec))
    c.close(); return {"ok":True}

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

# ============================ 自定义列「常用列」预设 ============================
# 主账号(管理员=密码登录/is_admin)存的预设 is_shared=true，全员可见并可套用；
# 子账号(普通飞书用户)存的仅自己可见、不共享。删除仅本人或管理员可操作。
def _req_user(request:Request):
    auth=request.headers.get("authorization",""); tok=auth[7:] if auth.startswith("Bearer ") else request.cookies.get("token","")
    d=_token_data(tok) or {}
    return (d.get("u"), bool(d.get("r")=="admin"))

@app.get("/api/column_presets")
def list_column_presets(request:Request, page:str):
    sub,_admin=_req_user(request)
    c=db(); cur=c.cursor()
    cur.execute("""SELECT id,page,owner,owner_name,name,is_shared,columns FROM column_presets
        WHERE page=%s AND (is_shared=true OR owner=%s) ORDER BY is_shared DESC, updated_at DESC""",(page,sub))
    rows=cur.fetchall(); c.close()
    for r in rows: r["mine"]=(r["owner"]==sub)   # mine=本人所建(可删)
    return {"presets":rows}

@app.post("/api/column_presets")
def save_column_preset(request:Request, body:dict=Body(...)):
    sub,admin=_req_user(request)
    if not sub: raise HTTPException(401,"未登录")
    page=(body.get("page") or "").strip(); name=(body.get("name") or "").strip(); cols=body.get("columns")
    if not page or not name: raise HTTPException(400,"缺少页面或预设名")
    if not isinstance(cols,list) or not cols: raise HTTPException(400,"列配置为空")
    oname=None
    try:
        c0=db(); cu0=c0.cursor(); cu0.execute("SELECT name FROM users WHERE open_id=%s",(sub,))
        r0=cu0.fetchone(); c0.close(); oname=(r0 or {}).get("name")
    except Exception: pass
    if not oname: oname="管理员" if admin else sub
    c=db(); c.autocommit=True; cur=c.cursor()
    cur.execute("""INSERT INTO column_presets(page,owner,owner_name,name,is_shared,columns)
        VALUES(%s,%s,%s,%s,%s,%s)
        ON CONFLICT(page,owner,name) DO UPDATE SET columns=EXCLUDED.columns,
          is_shared=EXCLUDED.is_shared, owner_name=EXCLUDED.owner_name, updated_at=now()
        RETURNING id""",
        (page,sub,oname,name,admin,psycopg2.extras.Json(cols)))
    pid=cur.fetchone()["id"]; c.close()
    return {"ok":True,"id":pid,"is_shared":admin}

@app.delete("/api/column_presets/{pid}")
def delete_column_preset(request:Request, pid:int):
    sub,admin=_req_user(request)
    c=db(); c.autocommit=True; cur=c.cursor()
    if admin: cur.execute("DELETE FROM column_presets WHERE id=%s",(pid,))
    else:     cur.execute("DELETE FROM column_presets WHERE id=%s AND owner=%s",(pid,sub))
    c.close(); return {"ok":True}

# ============================ 飞书登录(OAuth) + 本地开发免登录 ============================
# 配置优先环境变量，其次本地 feishu_config.json(已加入 .git/info/exclude，含 app_secret，勿提交)。
# app_secret 是敏感信息，任何日志/接口都不回显。
_FEISHU_FILE=os.path.join(HERE,"feishu_config.json")
def _feishu_cfg():
    d={}
    try: d=json.load(open(_FEISHU_FILE,encoding="utf-8"))
    except Exception: pass
    dev=os.environ.get("DEV_LOGIN"); dev=dev if dev is not None else d.get("dev_login")
    return {"app_id":os.environ.get("FEISHU_APP_ID") or d.get("app_id") or "",
            "app_secret":os.environ.get("FEISHU_APP_SECRET") or d.get("app_secret") or "",
            "redirect_uri":os.environ.get("FEISHU_REDIRECT_URI") or d.get("redirect_uri") or "",
            "dev_login":str(dev).lower() in ("1","true","yes","on")}

def _feishu_state():   # 无状态 CSRF：签名的时间戳，回调时校验签名 + 10 分钟有效期
    ts=str(int(time.time()))
    return ts+"."+hmac.new(_SECRET,("fs"+ts).encode(),hashlib.sha256).hexdigest()[:16]
def _feishu_state_ok(s):
    try:
        ts,sig=s.split(".")
        return hmac.compare_digest(sig,hmac.new(_SECRET,("fs"+ts).encode(),hashlib.sha256).hexdigest()[:16]) and int(ts)>=time.time()-600
    except Exception: return False

def _feishu_post(url, body, bearer=None):
    hdr={"Content-Type":"application/json; charset=utf-8","Accept-Encoding":"identity"}
    if bearer: hdr["Authorization"]="Bearer "+bearer
    req=urllib.request.Request(url,data=json.dumps(body).encode(),headers=hdr,method="POST")
    return json.loads(urllib.request.urlopen(req,timeout=30).read().decode("utf-8","replace"))

def _feishu_get(url, bearer):
    req=urllib.request.Request(url,headers={"Authorization":"Bearer "+bearer,"Accept-Encoding":"identity"},method="GET")
    return json.loads(urllib.request.urlopen(req,timeout=30).read().decode("utf-8","replace"))

def _login_redirect(**q):   # 带参跳回前端(hash 路由)登录页
    return RedirectResponse("/#/login?"+urllib.parse.urlencode(q),status_code=302)

def _upsert_user(open_id, u):
    """飞书登录用户落库(开放注册)：按 open_id UPSERT，刷新资料与登录统计。返回 is_active(禁用者拦在登录外)。
    失败仅记录并放行(返回 True)，不因 DB 抖动阻断登录。"""
    try:
        c=db(); c.autocommit=True; cur=c.cursor()
        cur.execute("""INSERT INTO users(open_id,union_id,feishu_user_id,name,avatar_url,email,mobile,source,last_login_at,login_count)
            VALUES(%s,%s,%s,%s,%s,%s,%s,'feishu',now(),1)
            ON CONFLICT(open_id) DO UPDATE SET
                union_id=EXCLUDED.union_id, feishu_user_id=EXCLUDED.feishu_user_id,
                name=EXCLUDED.name, avatar_url=EXCLUDED.avatar_url,
                email=COALESCE(EXCLUDED.email, users.email), mobile=COALESCE(EXCLUDED.mobile, users.mobile),
                last_login_at=now(), login_count=users.login_count+1, updated_at=now()
            RETURNING is_active, is_admin""",
            (open_id, u.get("union_id"), str(u.get("user_id") or "") or None, u.get("name"),
             u.get("avatar_url"), u.get("email") or u.get("enterprise_email"), u.get("mobile")))
        row=cur.fetchone(); c.close()
        return dict(row) if row else None
    except Exception as e:
        print("[feishu] 用户落库失败:", repr(e)[:150], flush=True)
        return None

@app.get("/api/auth_config")
def auth_config():
    """前端登录页据此决定显示哪种登录入口(飞书 / 开发免登录)。不回显任何密钥。"""
    cfg=_feishu_cfg()
    return {"feishu_enabled":bool(cfg["app_id"] and cfg["app_secret"] and cfg["redirect_uri"]),
            "dev_login":cfg["dev_login"]}

@app.get("/api/feishu/login_url")
def feishu_login_url():
    # 新版 OAuth2 授权入口(accounts.feishu.cn，用 client_id)
    cfg=_feishu_cfg()
    if not (cfg["app_id"] and cfg["redirect_uri"]): raise HTTPException(400,"未配置飞书登录")
    q=urllib.parse.urlencode({"client_id":cfg["app_id"],"redirect_uri":cfg["redirect_uri"],
                              "response_type":"code","state":_feishu_state()})
    return {"url":"https://accounts.feishu.cn/open-apis/authen/v1/authorize?"+q}

@app.get("/api/feishu/callback")
def feishu_callback(code:str=None, state:str=None):
    """飞书授权回调(OAuth2)：code 换 user_access_token → user_info 拿用户名 → 签发本平台 token → 跳回登录页。"""
    cfg=_feishu_cfg()
    if not (cfg["app_id"] and cfg["app_secret"]): return _login_redirect(err="飞书登录未配置")
    if not code or not _feishu_state_ok(state or ""): return _login_redirect(err="飞书登录校验失败")
    try:
        # 1) OAuth2 授权码换 user_access_token(v2，直接用 client_id/secret，无需先取 app_access_token)
        tk=_feishu_post("https://open.feishu.cn/open-apis/authen/v2/oauth/token",
                        {"grant_type":"authorization_code","client_id":cfg["app_id"],
                         "client_secret":cfg["app_secret"],"code":code,"redirect_uri":cfg["redirect_uri"]})
        uat=tk.get("access_token")
        if not uat: raise RuntimeError(f"token失败 code={tk.get('code')} err={tk.get('error') or tk.get('error_description') or tk.get('msg')}")
        # 2) 用 user_access_token 拿用户信息
        info=_feishu_get("https://open.feishu.cn/open-apis/authen/v1/user_info", uat)
        u=info.get("data") or {}
        name=u.get("name") or u.get("open_id") or "飞书用户"
        oid=u.get("open_id")
        row=_upsert_user(oid, u) if oid else None   # 落库/更新用户
        if row is not None and not row.get("is_active"):   # 禁用者拦在门外
            print(f"[feishu] 已禁用用户尝试登录: {name}", flush=True)
            return _login_redirect(err="系统登录失败，请联系站外投放团队")
        role="admin" if (row and row.get("is_admin")) else "user"   # 飞书用户默认普通，除非 is_admin
        print(f"[feishu] 登录成功(OAuth2) token_code={tk.get('code')} info_code={info.get('code')} name={name} role={role}", flush=True)
    except Exception as e:
        print(f"[feishu] 登录失败: {e}", flush=True)
        return _login_redirect(err=f"飞书登录失败:{e}")
    # token 主体用 open_id(稳定标识)，便于 /api/me 反查用户；显示名走 name 参数
    return _login_redirect(token=_make_token(oid or name, role=role), name=name)

@app.post("/api/dev_login")
def dev_login():
    """本地开发免登录：仅当配置 dev_login=true(本地)才可用，服务器默认关闭。"""
    if not _feishu_cfg()["dev_login"]: raise HTTPException(403,"开发免登录未开启")
    return {"ok":True,"token":_make_token("dev",role="admin"),"username":"dev","admin":True}   # 本地dev=管理员

@app.get("/api/users")
def list_users():
    """用户管理：列出所有飞书登录用户(按最近登录倒序)。today_seconds=今日在网页停留秒数。"""
    today=datetime.datetime.now(_SH).date().isoformat()
    c=db(); cur=c.cursor()
    cur.execute("""SELECT u.id,u.open_id,u.name,u.avatar_url,u.email,u.mobile,u.source,u.is_active,u.is_admin,
        u.first_login_at,u.last_login_at,u.login_count, COALESCE(a.seconds,0) today_seconds
        FROM users u LEFT JOIN user_activity a ON a.user_key=u.open_id AND a.date=%s
        ORDER BY u.last_login_at DESC NULLS LAST, u.id DESC""",(today,))
    rows=cur.fetchall(); c.close()
    return {"users":rows}

@app.post("/api/users/set_active")
def set_user_active(body:dict=Body(...)):
    """启用/禁用用户(禁用后无法再次登录；已签发的 token 到期前仍有效)。"""
    uid=body.get("id")
    if not uid: raise HTTPException(400,"缺少 id")
    c=db(); c.autocommit=True; cur=c.cursor()
    cur.execute("UPDATE users SET is_active=%s,updated_at=now() WHERE id=%s",(bool(body.get("is_active")),uid))
    c.close(); return {"ok":True}

# ============================ 账号密码用户管理(管理员) ============================
# 外部账号一律普通用户(is_admin=false)，按 代理商/账户 分配数据范围。内置 skg 为管理员，不可删/停。
@app.get("/api/auth_accounts")
def list_auth_accounts():
    today=datetime.datetime.now(_SH).date().isoformat()
    c=db(); cur=c.cursor()
    cur.execute("""SELECT au.username,au.name,au.is_admin,au.is_active,au.note,au.expires_at,
        au.scope_agencies,au.scope_stores,au.scope_accounts,au.first_login_at,au.last_login_at,au.login_count,au.created_at,
        COALESCE(a.seconds,0) today_seconds
        FROM auth_users au LEFT JOIN user_activity a ON a.user_key=au.username AND a.date=%s
        ORDER BY au.is_admin DESC, au.created_at NULLS FIRST, au.username""",(today,))
    rows=[dict(r) for r in cur.fetchall()]
    for r in rows:
        r["expires_at"]=str(r["expires_at"]) if r["expires_at"] else None
        r["first_login_at"]=fmt_dt(r["first_login_at"])
        r["last_login_at"]=fmt_dt(r["last_login_at"]); r["created_at"]=fmt_dt(r["created_at"])
        r["scope_agencies"]=list(r["scope_agencies"] or []); r["scope_stores"]=list(r["scope_stores"] or [])
        r["scope_accounts"]=list(r["scope_accounts"] or [])
    c.close(); return {"accounts":rows}

@app.post("/api/auth_accounts")
def create_auth_account(body:dict=Body(...)):
    u=(body.get("username") or "").strip(); pw=body.get("password") or ""
    if not u: raise HTTPException(400,"用户名必填")
    if len(pw)<6: raise HTTPException(400,"密码至少 6 位")
    c=db(); c.autocommit=True; cur=c.cursor()
    cur.execute("SELECT 1 FROM auth_users WHERE username=%s",(u,))
    if cur.fetchone(): c.close(); raise HTTPException(400,"用户名已存在")
    salt=secrets.token_hex(16)
    cur.execute("""INSERT INTO auth_users(username,salt,pw_hash,name,is_admin,is_active,note,expires_at,scope_agencies,scope_stores,scope_accounts)
        VALUES(%s,%s,%s,%s,false,true,%s,%s,%s,%s,%s)""",
        (u,salt,_hash_pw(pw,salt),(body.get("name") or u),body.get("note"),(body.get("expires_at") or None),
         psycopg2.extras.Json(body.get("scope_agencies") or []),psycopg2.extras.Json(body.get("scope_stores") or []),
         psycopg2.extras.Json(body.get("scope_accounts") or [])))
    c.close(); return {"ok":True}

@app.put("/api/auth_accounts/{username}")
def update_auth_account(username:str, body:dict=Body(...)):
    c=db(); c.autocommit=True; cur=c.cursor()
    cur.execute("SELECT is_admin FROM auth_users WHERE username=%s",(username,)); row=cur.fetchone()
    if not row: c.close(); raise HTTPException(404,"账号不存在")
    sets=[]; args=[]
    for k in ("name","note"):
        if k in body: sets.append(f"{k}=%s"); args.append(body[k])
    if "is_active" in body:
        if username=="skg" and not body["is_active"]: c.close(); raise HTTPException(400,"内置管理员不可停用")
        sets.append("is_active=%s"); args.append(bool(body["is_active"]))
    if "expires_at" in body: sets.append("expires_at=%s"); args.append(body["expires_at"] or None)
    if "scope_agencies" in body: sets.append("scope_agencies=%s"); args.append(psycopg2.extras.Json(body["scope_agencies"] or []))
    if "scope_stores" in body: sets.append("scope_stores=%s"); args.append(psycopg2.extras.Json(body["scope_stores"] or []))
    if "scope_accounts" in body: sets.append("scope_accounts=%s"); args.append(psycopg2.extras.Json(body["scope_accounts"] or []))
    if body.get("password"):
        if len(body["password"])<6: c.close(); raise HTTPException(400,"密码至少 6 位")
        salt=secrets.token_hex(16)
        sets += ["salt=%s","pw_hash=%s"]; args += [salt,_hash_pw(body["password"],salt)]
    if sets:
        sets.append("updated_at=now()"); args.append(username)
        cur.execute(f"UPDATE auth_users SET {','.join(sets)} WHERE username=%s",args)
    c.close(); return {"ok":True}

@app.delete("/api/auth_accounts/{username}")
def delete_auth_account(username:str):
    if username=="skg": raise HTTPException(400,"内置管理员不可删除")
    c=db(); c.autocommit=True; cur=c.cursor()
    cur.execute("DELETE FROM auth_users WHERE username=%s",(username,)); c.close(); return {"ok":True}

@app.get("/api/scope_options")
def scope_options():
    """数据范围分配下拉：代理商 + 店铺 + 账户(entity_id+名称)列表。"""
    c=db(); cur=c.cursor()
    cur.execute("SELECT DISTINCT agency v FROM account_meta WHERE agency IS NOT NULL AND agency<>'' ORDER BY v")
    agencies=[r["v"] for r in cur.fetchall()]
    cur.execute("SELECT DISTINCT store v FROM account_meta WHERE store IS NOT NULL AND store<>'' ORDER BY v")
    stores=[r["v"] for r in cur.fetchall()]
    cur.execute("""SELECT entity_id, max(entity_name) name FROM ad_daily WHERE level=ANY(%s) AND cost IS NOT NULL
        GROUP BY entity_id ORDER BY max(entity_name) NULLS LAST""",(ACCOUNT_LEVELS,))
    accounts=[{"id":r["entity_id"],"name":r["name"] or r["entity_id"]} for r in cur.fetchall()]
    c.close(); return {"agencies":agencies,"stores":stores,"accounts":accounts}

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
def meta(request:Request):
    # 数据范围隔离：普通密码账号只看范围内账户所在平台/层级
    sc,sv=_scope_cond(request); sw=f" WHERE {sc}" if sc else ""; sa=[sv] if sv is not None else []
    c=db(); cur=c.cursor()
    cur.execute(f"SELECT DISTINCT platform FROM ad_daily{sw} ORDER BY platform", sa)
    plats=[r["platform"] for r in cur.fetchall()]
    cur.execute(f"SELECT DISTINCT platform,level FROM ad_daily{sw} ORDER BY platform,level", sa)
    levels={}
    for r in cur.fetchall(): levels.setdefault(r["platform"],[]).append(r["level"])
    cur.execute(f"SELECT min(date) mn, max(date) mx FROM ad_daily{sw}", sa)
    rng=cur.fetchone()
    if plats:
        cur.execute("SELECT platform,tag FROM accounts WHERE platform = ANY(%s) ORDER BY platform,tag",(plats,))
    else:
        cur.execute("SELECT platform,tag FROM accounts WHERE false")
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
 "conversion_rate":"SUM(conversions)*100.0/NULLIF(SUM(clicks),0)",   # 转化率 = 转化数/点击量
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
# 实时真实付款的「已付款类」订单状态(与前端订单明细 PAID_STATUSES 保持一致)：
# 已付款/已完成(小飞机)、支付(麦斯)、订单付款(微橙)、已结算(沸点)、成交(通用)；退款/失效/拆单/待付款 不计
_PAID_STATUS_RE = "(已付款|已完成|订单付款|支付|成交|已结算)"

@app.get("/api/detail")
def detail(request:Request, platform:str, level:str, login:str=None, start:str=None, end:str=None,
           search:str=None, sort:str="cost", limit:int=50, offset:int=0):
    cond=["platform=%s","level=%s","cost IS NOT NULL"]; args=[platform, level]
    if login: cond.append("login_account=%s"); args.append(login)
    if start: cond.append("date>=%s"); args.append(start)
    if end: cond.append("date<=%s"); args.append(end)
    if search: cond.append("(entity_name ILIKE %s OR entity_id ILIKE %s)"); args += [f"%{search}%", f"%{search}%"]
    w=" AND ".join(cond)
    w,args=_apply_scope(w,args,request)
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
def summary(request:Request, platforms:str=None, levels:str="", start:str=None, end:str=None):
    pl=platforms.split(",") if platforms else None
    w,args=_where(pl, levels or None, start, end)
    w,args=_apply_scope(w,args,request)
    c=db(); cur=c.cursor()
    cur.execute(f"""SELECT SUM(cost) cost, SUM(real_pay_amount) rpay,
        SUM(real_pay_amount)/NULLIF(SUM(cost),0) rroi, SUM(real_orders) rord,
        SUM(refund_rate*cost)/NULLIF(SUM(cost),0) refund FROM ad_daily WHERE {w}""",args)
    r=cur.fetchone(); c.close()
    f=lambda x: float(x) if x is not None else 0
    return {"cost":f(r["cost"]),"real_pay_amount":f(r["rpay"]),"real_roi":round(f(r["rroi"]),2),
            "real_orders":int(r["rord"] or 0),"refund_rate":round(f(r["refund"]),2)}

@app.get("/api/trend")
def trend(request:Request, metric:str="cost", gran:str="day", group:str="platform",
          platforms:str=None, levels:str=None, start:str=None, end:str=None, topn:int=10):
    if metric not in METRICS: raise HTTPException(400,"unknown metric")
    pl=platforms.split(",") if platforms else None
    w,args=_where(pl, levels or None, start, end)
    w,args=_apply_scope(w,args,request)
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
def table(request:Request, platforms:str=None, levels:str=None, start:str=None, end:str=None, limit:int=500, offset:int=0):
    pl=platforms.split(",") if platforms else None
    w,args=_where(pl, levels, start, end)
    w,args=_apply_scope(w,args,request)
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
    # 一次 GROUP BY 聚合 ad_daily 再 JOIN，避免每账号 3 个关联子查询(全表扫多次)导致慢
    cur.execute("""SELECT a.id,a.platform,a.tag,a.enabled,a.token_status,a.token_updated_at,a.note,
        a.username, COALESCE(a.is_historical,false) AS is_historical,
        (a.password IS NOT NULL AND a.password<>'') AS has_pw,
        s.first_date, s.last_date, COALESCE(s.rows,0) AS rows
        FROM accounts a
        LEFT JOIN (SELECT login_account, min(date) first_date, max(date) last_date, count(*) rows
                   FROM ad_daily GROUP BY login_account) s ON s.login_account=a.tag
        ORDER BY COALESCE(a.is_historical,false), a.platform, a.tag""")
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

# ============================ 单账户历史回填 ============================
# 新增/历史账号手动补历史数据(定时任务只抓最近15天)。后台线程逐天抓，断点续跑跳过已抓的天(UPSERT幂等)。
_BACKFILL_JOBS={}            # aid -> {state,total,done,rows,orders,errs,msg,started,finished}
_BACKFILL_LOCK=threading.Lock()
_MAX_BACKFILL=3             # 同时回填的账号上限，防一次点太多打爆接口

def _find_login(aid):
    import fetchers as F
    return next((l for l in F.load_logins(enabled_only=False) if l.get("id")==aid), None)

def _do_backfill(aid, start_s, end_s, do_orders):
    import crawl, fetchers as F, db as DB, order_fetchers as OF
    from concurrent.futures import ThreadPoolExecutor, as_completed
    job=_BACKFILL_JOBS[aid]
    try:
        lg=_find_login(aid)
        if not lg or not lg.get("auth"):
            job.update(state="error", msg="账号未登录，请先自动/手动登录", finished=True); return
        p=lg["platform"]; tag=lg["tag"]
        s=datetime.date.fromisoformat(start_s); e=datetime.date.fromisoformat(end_s)
        all_days=[s+datetime.timedelta(days=i) for i in range((e-s).days+1)]
        conn0=DB.connect(); done=DB.done_set(conn0,p,tag); conn0.close()
        levels=F.LEVELS.get(p,[])
        order_ok=do_orders and p in OF.ORDER_FETCH
        level_days={lv:[d for d in all_days if (p,tag,lv,d.isoformat()) not in done] for lv in levels}
        order_days=[d for d in all_days if (p,tag,"订单",d.isoformat()) not in done] if order_ok else []
        job["total"]=sum(len(v) for v in level_days.values())+len(order_days)
        if not job["total"]:
            job.update(state="done", msg="该区间已全部抓过，无需回填", finished=True); return
        # ---- 广告：各层级并发，层级内逐天(实时进度)。auth 失败标记，稍后统一重登补齐 ----
        def run_level(lv):
            conn=DB.connect(); auth_fail=False
            try:
                for d in level_days[lv]:
                    try:
                        rows=crawl._fetch_retry(lg,lv,d); DB.upsert(conn,rows); DB.mark_progress(conn,p,tag,lv,d,len(rows))
                        with _BACKFILL_LOCK: job["rows"]+=len(rows); job["done"]+=1
                    except Exception as ex:
                        with _BACKFILL_LOCK: job["errs"]+=1
                        if crawl._auth_err(ex): auth_fail=True; break
                        with _BACKFILL_LOCK: job["done"]+=1
            finally:
                conn.close()
            return auth_fail
        auth_fail=False
        active=[lv for lv in levels if level_days[lv]]
        if active:
            with ThreadPoolExecutor(max_workers=min(4,len(active))) as ex:
                for f in as_completed([ex.submit(run_level,lv) for lv in active]):
                    if f.result(): auth_fail=True
        # auth 失败 -> 重登一次，把该登录仍缺的天补齐(重算 done)
        if auth_fail:
            crawl.refresh_login(aid); lg=_find_login(aid) or lg
            conn=DB.connect()
            try:
                done2=DB.done_set(conn,p,tag)
                for lv in active:
                    for d in level_days[lv]:
                        if (p,tag,lv,d.isoformat()) in done2: continue
                        try:
                            rows=crawl._fetch_retry(lg,lv,d); DB.upsert(conn,rows); DB.mark_progress(conn,p,tag,lv,d,len(rows))
                            with _BACKFILL_LOCK: job["rows"]+=len(rows)
                        except Exception:
                            with _BACKFILL_LOCK: job["errs"]+=1
            finally:
                conn.close()
        # ---- 订单：逐天 ----
        if order_days:
            conn=DB.connect(); OF.ensure_orders_table(conn)
            try:
                for d in order_days:
                    try:
                        rows=OF.fetch_orders(lg,d); OF.upsert_orders(conn,rows); DB.mark_progress(conn,p,tag,"订单",d,len(rows))
                        with _BACKFILL_LOCK: job["orders"]+=len(rows)
                    except Exception as ex:
                        with _BACKFILL_LOCK: job["errs"]+=1
                        if crawl._auth_err(ex): crawl.refresh_login(aid); lg=_find_login(aid) or lg
                    with _BACKFILL_LOCK: job["done"]+=1
            finally:
                conn.close()
        job.update(state="done", msg=f"完成：广告 {job['rows']} 行，订单 {job['orders']} 单"+(f"，{job['errs']} 天失败" if job['errs'] else ""))
        try:
            c=db(); c.autocommit=True; cur=c.cursor()
            st="ok" if not job["errs"] else "error"
            cur.execute("""INSERT INTO runs (task_id,kind,started_at,finished_at,status,rows_written,detail)
                VALUES (NULL,'backfill',%s,now(),%s,%s,%s)""",
                (job.get("started"), st, job["rows"], f"[回填]{tag} {start_s}~{end_s}：广告{job['rows']}行 订单{job['orders']}单"+(f" {job['errs']}天失败" if job['errs'] else "")))
            c.close()
        except Exception: pass
    except Exception as e:
        job.update(state="error", msg=repr(e)[:200])
    finally:
        job["finished"]=True

@app.post("/api/accounts/{aid}/backfill")
def account_backfill(aid:int, body:dict=Body(...)):
    start=(body.get("start") or "2025-01-01").strip()
    end=(body.get("end") or datetime.datetime.now(_SH).date().isoformat()).strip()
    do_orders=bool(body.get("orders", True))
    try: datetime.date.fromisoformat(start); datetime.date.fromisoformat(end)
    except Exception: raise HTTPException(400,"日期格式错误")
    if start>end: raise HTTPException(400,"起始日期不能晚于结束日期")
    lg=_find_login(aid)
    if not lg: raise HTTPException(404,"账号不存在")
    if not lg.get("auth"): raise HTTPException(400,"账号未登录，请先「自动登录」或「手动登录」再回填")
    with _BACKFILL_LOCK:
        cur=_BACKFILL_JOBS.get(aid)
        if cur and cur.get("state")=="running": raise HTTPException(409,"该账号正在回填中")
        if sum(1 for j in _BACKFILL_JOBS.values() if j.get("state")=="running")>=_MAX_BACKFILL:
            raise HTTPException(429,f"同时回填的账号已达上限（{_MAX_BACKFILL}），请等其它账号跑完再试")
        _BACKFILL_JOBS[aid]={"state":"running","total":0,"done":0,"rows":0,"orders":0,"errs":0,
                             "msg":"启动中…","started":datetime.datetime.now(),"finished":False}
    threading.Thread(target=_do_backfill,args=(aid,start,end,do_orders),daemon=True).start()
    return {"ok":True,"msg":"已开始回填"}

@app.get("/api/accounts/{aid}/backfill_status")
def account_backfill_status(aid:int):
    j=_BACKFILL_JOBS.get(aid)
    if not j: return {"state":"idle"}
    pct=min(100,round(j["done"]*100/j["total"])) if j.get("total") else 0
    return {"state":j["state"],"total":j["total"],"done":j["done"],"pct":pct,
            "rows":j["rows"],"orders":j["orders"],"errs":j["errs"],"msg":j.get("msg","")}

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
# 「现存账户」子查询：投放账户管理里能看到的账户(ad_daily 里有消耗数据的)。
# 属性下拉候选只取这些账户上填的值——已改名/合并/删除的账户残留在 account_meta 的旧类目/产品不再出现。
_LIVE_ACCT_SUB="SELECT DISTINCT entity_id FROM ad_daily WHERE level = ANY(%s) AND cost IS NOT NULL"

@app.get("/api/account_board")
def account_board(request:Request, start:str=None, end:str=None, platform:str=None, search:str=None,
                  account:list[str]=Query(None),
                  category:list[str]=Query(None), product:list[str]=Query(None), ecom_platform:list[str]=Query(None),
                  ad_channel:list[str]=Query(None), store:list[str]=Query(None), agency:list[str]=Query(None),
                  sort:str="cost", desc:bool=True, limit:int=100, offset:int=0, mode:str="summary"):
    cond=["level = ANY(%s)","cost IS NOT NULL"]; args=[ACCOUNT_LEVELS]
    scond,sval=_scope_cond(request)                                   # 数据范围隔离(entity_id)
    if scond:
        cond.append(scond)
        if sval is not None: args.append(sval)
    if platform: cond.append("platform=%s"); args.append(platform)
    if start: cond.append("date>=%s"); args.append(start)
    if end: cond.append("date<=%s"); args.append(end)
    if account: cond.append("entity_name = ANY(%s)"); args.append(account)   # 账户名称(多选)
    if search: cond.append("(entity_name ILIKE %s OR entity_id ILIKE %s)"); args+=[f"%{search}%",f"%{search}%"]
    # 投放账户 6 属性(类目/投放产品/…)多选筛选，值来自 account_meta，按 entity_id 关联
    mc=[]; ma=[]
    for f,v in (("category",category),("product",product),("ecom_platform",ecom_platform),
                ("store",store),("ad_channel",ad_channel),("agency",agency)):
        if v: mc.append(f"{f} = ANY(%s)"); ma.append(v)
    if mc:
        cond.append("entity_id IN (SELECT entity_id FROM account_meta WHERE "+" AND ".join(mc)+")")
        args.extend(ma)
    w=" AND ".join(cond)
    if sort not in _DETAIL_METRICS: sort="cost"
    # 统计方式：summary=区间汇总(不分期)；daily/weekly/monthly=按日/周(周一起)/月分组，每账户每期一行
    # date_trunc('week',...) 以周一为一周起点，符合「周一到周日为一周」
    _PERIODS={"daily":"date","weekly":"date_trunc('week', date)::date","monthly":"date_trunc('month', date)::date"}
    grouped = mode in _PERIODS
    pexpr = _PERIODS.get(mode)
    grp = "platform,login_account,entity_id" + (f",{pexpr}" if grouped else "")
    datesel = f"({pexpr})::text AS date, " if grouped else ""     # 返回分期起始日(周=周一,月=1号),前端据 mode 格式化
    order = ("date DESC, " if grouped else "") + f"{_DETAIL_METRICS[sort]} {'DESC' if desc else 'ASC'} NULLS LAST"
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
    # 实时真实付款：口径与订单明细的「是否当天真实付款」完全一致(点击=付款同日 且 状态属已付款类)，来自 orders 表
    # 已付款类状态：已付款/已完成(小飞机) 支付(麦斯) 订单付款(微橙) 已结算(沸点) 成交(通用)；退款/失效/拆单/待付款 不计
    ocond=["o.pay_time IS NOT NULL","o.click_time IS NOT NULL","o.pay_time::date=o.click_time::date","o.order_status ~ %s"]
    oargs=[_PAID_STATUS_RE]
    if platform: ocond.append("o.platform=%s"); oargs.append(platform)
    if start: ocond.append("o.pay_time::date>=%s"); oargs.append(start)
    if end: ocond.append("o.pay_time::date<=%s"); oargs.append(end)
    ow=" AND ".join(ocond)
    _OPERIODS={"daily":"o.pay_time::date","weekly":"date_trunc('week', o.pay_time)::date","monthly":"date_trunc('month', o.pay_time)::date"}
    opexpr=_OPERIODS.get(mode)
    odatesel=f"({opexpr})::text AS d, " if grouped else ""
    ogrp="o.platform,o.ad_account_id"+(f",{opexpr}" if grouped else "")
    cur.execute(f"SELECT o.platform, o.ad_account_id, {odatesel} SUM(o.pay_amount) rtpay FROM orders o WHERE {ow} GROUP BY {ogrp}", oargs)
    rtmap={}
    for r in cur.fetchall():
        k=(r["platform"],r["ad_account_id"])+((r["d"],) if grouped else ())
        rtmap[k]=float(r["rtpay"] or 0)
    # 合计行的实时真实付款：限定在当前筛选的账户集合内(与表格口径一致)
    cur.execute(f"SELECT COALESCE(SUM(o.pay_amount),0) rtpay FROM orders o WHERE {ow} AND o.ad_account_id IN (SELECT DISTINCT entity_id FROM ad_daily WHERE {w})", oargs+args)
    tot_rtpay=float(cur.fetchone()["rtpay"] or 0)
    c.close()
    def rnd_metrics(d):
        for k in _DETAIL_METRICS:
            if d.get(k) is not None: d[k]=round(float(d[k]),2)
        return d
    def add_rt(d, rtpay):
        d["rt_real_pay"]=round(rtpay,2)
        cost=float(d.get("cost") or 0)
        d["rt_real_roi"]=round(rtpay/cost,2) if cost else 0
        return d
    def rnd(d):
        rnd_metrics(d)
        _t=tagmap.get((d["platform"],d["entity_id"]),[])
        d["tags"]=_t if isinstance(_t,list) else []   # 防脏数据(jsonb 空对象{})导致前端 .join 报错
        m=metamap.get(d["entity_id"]) or {}
        for f in META_FIELDS: d[f]=m.get(f)
        k=(d["platform"],d["entity_id"])+((d["date"],) if grouped else ())
        add_rt(d, rtmap.get(k,0.0))
        return d
    return {"total":total,"rows":[rnd(r) for r in rows],"totals":add_rt(rnd_metrics(totals), tot_rtpay)}

@app.get("/api/account_board_meta")
def account_board_meta(request:Request, platform:str=None):
    """账户看板筛选下拉选项：账户名称候选 + 6 个投放属性候选。普通密码账号只出范围内的选项。"""
    cond=["level = ANY(%s)","cost IS NOT NULL"]; args=[ACCOUNT_LEVELS]
    scond,sval=_scope_cond(request)
    if scond:
        cond.append(scond)
        if sval is not None: args.append(sval)
    if platform: cond.append("platform=%s"); args.append(platform)
    w=" AND ".join(cond)
    c=db(); cur=c.cursor()
    cur.execute(f"SELECT DISTINCT entity_name v FROM ad_daily WHERE {w} AND entity_name IS NOT NULL AND entity_name<>'' ORDER BY v", args)
    accounts=[r["v"] for r in cur.fetchall()]
    mopts={}
    for f in META_FIELDS:
        if scond:   # 受限用户：属性取值只出范围内(已是现存账户子集)的
            cur.execute(f"""SELECT DISTINCT {f} v FROM account_meta WHERE {f} IS NOT NULL AND {f}<>''
                AND entity_id IN (SELECT entity_id FROM ad_daily WHERE {w}) ORDER BY v""", args)
        else:       # 只取现存账户上填的值(排除已改名/合并/删除账户的残留)
            cur.execute(f"""SELECT DISTINCT {f} v FROM account_meta WHERE {f} IS NOT NULL AND {f}<>''
                AND entity_id IN ({_LIVE_ACCT_SUB}) ORDER BY v""",(ACCOUNT_LEVELS,))
        mopts[f]=[r["v"] for r in cur.fetchall()]
    c.close()
    return {"accounts":accounts,"meta_options":mopts,
            "meta_fields":[{"key":k,"label":META_LABELS[k]} for k in META_FIELDS]}

# ============================ 实时数据看板（数据看板第一屏） ============================
# 按「当天在投的账户」自动汇总：类目→产品 分组明细 + 产品小计 + 总计 + 电商平台(渠道)×店铺 汇总。
# 6 分组维度 = account_meta：类目category/产品product/渠道ecom_platform/店铺store/投放渠道ad_channel/代理商agency
# 「真实」口径 = 订单表当天真实付款(点击=付款同日且已付款类)，与账户看板「实时真实付款」一致。
# 「上一个小时消耗」无小时级数据源，返回 None（前端显示 —）。
@app.get("/api/realtime_board")
def realtime_board(request:Request, date:str=None):
    day = date or datetime.datetime.now(_SH).date().isoformat()
    yday = (datetime.date.fromisoformat(day) - datetime.timedelta(days=1)).isoformat()
    scond,sval=_scope_cond(request); sc=f" AND {scond}" if scond else ""   # 数据范围隔离(entity_id)
    sx=[sval] if sval is not None else []
    c=db(); cur=c.cursor()
    # 今日各账户 ad_daily 聚合（消耗/直投成交/退款率*消耗）
    cur.execute(f"""SELECT entity_id, max(entity_name) entity_name, SUM(cost) cost,
        SUM(direct_real_orders) dro, SUM(direct_real_pay_amount) drp, SUM(refund_rate*cost) rrn
        FROM ad_daily WHERE level=ANY(%s) AND date=%s AND cost>0{sc} GROUP BY entity_id""",[ACCOUNT_LEVELS,day]+sx)
    today={r["entity_id"]:dict(r) for r in cur.fetchall()}
    # 昨日各账户消耗
    cur.execute(f"SELECT entity_id, SUM(cost) cost FROM ad_daily WHERE level=ANY(%s) AND date=%s{sc} GROUP BY entity_id",[ACCOUNT_LEVELS,yday]+sx)
    ycost={r["entity_id"]:float(r["cost"] or 0) for r in cur.fetchall()}
    # 今日/昨日 各账户「当天真实付款」（orders：点击=付款同日 且 已付款类）
    def rt_by_acct(dd):
        cur.execute(f"""SELECT o.ad_account_id eid, SUM(o.pay_amount) pay, count(*) n FROM orders o
            WHERE o.pay_time::date=%s AND o.click_time IS NOT NULL AND o.pay_time::date=o.click_time::date
              AND o.order_status ~ %s GROUP BY o.ad_account_id""",(dd,_PAID_STATUS_RE))
        return {r["eid"]:(float(r["pay"] or 0), int(r["n"])) for r in cur.fetchall()}
    trt=rt_by_acct(day); yrt=rt_by_acct(yday)
    cur.execute("SELECT * FROM account_meta"); meta={r["entity_id"]:dict(r) for r in cur.fetchall()}
    cur.execute("SELECT max(fetched_at) t FROM ad_daily WHERE date=%s",(day,)); last_upd=cur.fetchone()["t"]
    c.close()
    DIMS=["category","product","ecom_platform","store","ad_channel","agency"]
    def raw0(): return dict(cost=0.0,real_pay=0.0,real_orders=0,dro=0.0,drp=0.0,rrn=0.0,y_cost=0.0,y_real_pay=0.0)
    def add(a, eid):
        t=today[eid]
        a["cost"]+=float(t["cost"] or 0); a["dro"]+=float(t["dro"] or 0); a["drp"]+=float(t["drp"] or 0)
        a["rrn"]+=float(t["rrn"] or 0)
        p,n=trt.get(eid,(0,0)); a["real_pay"]+=p; a["real_orders"]+=n
        a["y_cost"]+=ycost.get(eid,0); a["y_real_pay"]+=yrt.get(eid,(0,0))[0]
    def merge(a,b):
        for k in a: a[k]+=b[k]
        return a
    def derive(a):
        cost=a["cost"]; yc=a["y_cost"]
        rroi=a["real_pay"]/cost if cost else None
        yroi=a["y_real_pay"]/yc if yc else None
        return {
            "cost":round(a["cost"],2),
            "real_orders":int(a["real_orders"]),
            "real_pay":round(a["real_pay"],2),
            "real_roi":round(rroi,2) if rroi is not None else None,
            "roi_vs_yesterday":round(rroi-yroi,2) if (rroi is not None and yroi is not None) else None,
            "refund_rate":round(a["rrn"]/cost,2) if cost else None,
            "direct_real_orders":int(a["dro"]),
            "direct_real_pay":round(a["drp"],2),
            "direct_real_roi":round(a["drp"]/cost,2) if cost else None,
            "y_cost":round(a["y_cost"],2),
            "y_real_pay":round(a["y_real_pay"],2),
            "y_real_roi":round(yroi,2) if yroi is not None else None,
        }
    # 按 6 维组合聚合（相同属性的账户合并成一行）
    combos={}
    for eid in today:
        m=meta.get(eid) or {}
        key=tuple((m.get(d) or "").strip() for d in DIMS)
        combos.setdefault(key, raw0()); add(combos[key], eid)
    def dimval(key,i): return key[i] or ("未分类" if i==0 else "")
    rows=[]
    # —— 类目 → 产品 明细 + 产品小计（未分类类目排最后）——
    cats=sorted({k[0] for k in combos}, key=lambda x:(x=="" , x))
    for cat in cats:
        prods=sorted({k[1] for k in combos if k[0]==cat}, key=lambda x:(x=="", x))
        for prod in prods:
            grp=[(k,v) for k,v in combos.items() if k[0]==cat and k[1]==prod]
            grp.sort(key=lambda kv:kv[0])
            for k,v in grp:
                d=derive(v)
                d.update(row_type="detail", category=cat or "未分类", product=k[1],
                         ecom_platform=k[2], store=k[3], ad_channel=k[4], agency=k[5])
                rows.append(d)
            # 该品只有一行明细时不再显示小计（避免和明细行重复）
            if len(grp) > 1:
                sub=raw0()
                for _,v in grp: merge(sub,v)
                ds=derive(sub); ds.update(row_type="subtotal", category=cat or "未分类",
                    product=(prod or "未命名")+"-小计", ecom_platform="", store="", ad_channel="", agency="")
                rows.append(ds)
    # —— 总计 ——
    tot=raw0()
    for v in combos.values(): merge(tot,v)
    dt=derive(tot); dt.update(row_type="total", label="总计"); rows.append(dt)
    # —— 电商平台(渠道) × 店铺 汇总段：京东盛德 / 京东-小计 / 天猫... ——
    ecoms=sorted({k[2] for k in combos if k[2]}, key=lambda x:x)
    for ec in ecoms:
        stores=sorted({k[3] for k in combos if k[2]==ec}, key=lambda x:(x=="", x))
        for st in stores:
            a=raw0()
            for k,v in combos.items():
                if k[2]==ec and k[3]==st: merge(a,v)
            d=derive(a); d.update(row_type="platform", label=f"{ec}{st or '其他'}"); rows.append(d)
        a=raw0()
        for k,v in combos.items():
            if k[2]==ec: merge(a,v)
        d=derive(a); d.update(row_type="platform_subtotal", label=f"{ec}-小计"); rows.append(d)
    return {"date":day, "updated_at":fmt_dt(last_upd),
            "active_accounts":len(today), "rows":rows}

@app.post("/api/account_tags")
def set_account_tags(body:dict=Body(...)):
    c=db(); c.autocommit=True; cur=c.cursor()
    cur.execute("""INSERT INTO account_tags(platform,entity_id,tags) VALUES(%s,%s,%s)
        ON CONFLICT(platform,entity_id) DO UPDATE SET tags=EXCLUDED.tags, updated_at=now()""",
        (body["platform"], body["entity_id"], psycopg2.extras.Json(body.get("tags",[]))))
    c.close(); return {"ok":True}

# ============================ 投放账户管理(账户自定义属性) ============================
# 6 个业务属性：类目/投放产品/电商平台/投放渠道/店铺/代理商，按 账户ID 存，供账户看板自定义列展示
META_FIELDS=["category","product","ecom_platform","store","ad_channel","agency"]
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
    # 每个字段已有的去重取值(仅现存账户上填的，排除已改名/合并/删除账户残留)，前端做下拉候选
    options={}
    for f in META_FIELDS:
        cur.execute(f"""SELECT DISTINCT {f} v FROM account_meta WHERE {f} IS NOT NULL AND {f}<>''
            AND entity_id IN ({_LIVE_ACCT_SUB}) ORDER BY v""",(ACCOUNT_LEVELS,))
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
        # 诊断: 合法xlsx应以 PK\x03\x04(504b0304) 开头; 非PK说明文件在上传前已被破坏(如被安全软件加密/被转码)
        head=data[:16]
        hint=""
        if head[:2]!=b'PK':
            try: txt=head.decode('utf-8','replace')
            except: txt=""
            hint=f"｜收到 {len(data)} 字节, 头部={head.hex()} ({txt!r}), 非zip → 文件在上传前已损坏(疑被终端安全软件加密), 不是本系统能修的"
        raise HTTPException(400, "无法解析文件，请上传导出的 .xlsx："+repr(e)[:60]+hint)
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
    c=db(); c.autocommit=True; cur=c.cursor(); updated=0; skipped=0; skipped_ids=[]
    cur.execute("SELECT DISTINCT entity_id FROM ad_daily WHERE level = ANY(%s)", (ACCOUNT_LEVELS,))
    valid_ids={row["entity_id"] for row in cur.fetchall()}   # 系统里真实存在的账户ID(账户级)
    cols=list(field_idx.keys()); setc=",".join(f"{f}=EXCLUDED.{f}" for f in cols)
    for r in allrows[1:]:
        if idx_id>=len(r) or r[idx_id] in (None,""): continue
        eid=_eid(r[idx_id])
        vals=[ (str(r[i]).strip() if i<len(r) and r[i] not in (None,"") else None) for i in (field_idx[f] for f in cols) ]
        if not any(vals): continue   # 整行属性都空的账户跳过，不创建空记录
        if eid not in valid_ids:      # 只导入系统真实存在的账户ID，未知ID跳过并计数
            skipped+=1
            if len(skipped_ids)<10: skipped_ids.append(eid)
            continue
        cur.execute(f"""INSERT INTO account_meta(entity_id,{','.join(cols)}) VALUES(%s,{','.join(['%s']*len(cols))})
            ON CONFLICT(entity_id) DO UPDATE SET {setc}, updated_at=now()""", [eid]+vals)
        updated+=1
    c.close(); return {"updated":updated,"skipped":skipped,"skipped_ids":skipped_ids}

@app.get("/api/health")
def health(): return {"ok":True,"ts":str(datetime.datetime.now())}

# ============================ 订单明细 API ============================
_ORDER_SORTS={"pay_time","order_date","pay_amount","click_time","refund_time","product_price"}
def _order_meta_filter(cond, args, category, product, ecom_platform, ad_channel, store, agency):
    """按投放账户 6 属性(值来自 account_meta，按 ad_account_id 关联)筛选订单。各属性支持多选(值为列表, OR)。"""
    mc=[]; ma=[]
    for f,v in (("category",category),("product",product),("ecom_platform",ecom_platform),
                ("store",store),("ad_channel",ad_channel),("agency",agency)):
        if v: mc.append(f"{f} = ANY(%s)"); ma.append(v)
    if mc:
        cond.append("ad_account_id IN (SELECT entity_id FROM account_meta WHERE "+" AND ".join(mc)+")")
        args.extend(ma)
@app.get("/api/order_meta")
def order_meta(request:Request):
    scond,sval=_scope_cond(request,"ad_account_id"); ow=f" WHERE {scond}" if scond else ""   # 范围隔离
    sx=[sval] if sval is not None else []
    c=db(); cur=c.cursor()
    cur.execute(f"SELECT DISTINCT platform FROM orders{ow} ORDER BY platform", sx); plats=[r["platform"] for r in cur.fetchall()]
    cur.execute(f"SELECT DISTINCT platform,order_type FROM orders{ow} ORDER BY 1,2", sx)
    types={}
    for r in cur.fetchall(): types.setdefault(r["platform"],[]).append(r["order_type"])
    cur.execute(f"SELECT DISTINCT platform,login_account FROM orders{ow} ORDER BY 1,2", sx)
    logins={}
    for r in cur.fetchall(): logins.setdefault(r["platform"],[]).append(r["login_account"])
    cur.execute(f"SELECT min(order_date) mn, max(order_date) mx FROM orders{ow}", sx); rng=cur.fetchone()
    # 广告账户名称候选(多选筛选用)
    awhere=f"{ow} AND ad_account_name IS NOT NULL AND ad_account_name<>''" if ow else "WHERE ad_account_name IS NOT NULL AND ad_account_name<>''"
    cur.execute(f"SELECT DISTINCT ad_account_name v FROM orders {awhere} ORDER BY v", sx)
    accounts=[r["v"] for r in cur.fetchall()]
    # 6 个投放属性(类目/投放产品/…)的可选值，来自 account_meta；受限用户只出范围内账户的取值
    mopts={}
    for f in META_FIELDS:
        if scond:
            cur.execute(f"""SELECT DISTINCT {f} v FROM account_meta WHERE {f} IS NOT NULL AND {f}<>''
                AND entity_id IN (SELECT ad_account_id FROM orders{ow}) ORDER BY v""", sx)
        else:       # 只取有订单的现存账户上填的值
            cur.execute(f"""SELECT DISTINCT {f} v FROM account_meta WHERE {f} IS NOT NULL AND {f}<>''
                AND entity_id IN (SELECT DISTINCT ad_account_id FROM orders) ORDER BY v""")
        mopts[f]=[r["v"] for r in cur.fetchall()]
    c.close()
    return {"platforms":plats,"types":types,"logins":logins,"accounts":accounts,
            "meta_options":mopts,"meta_fields":[{"key":k,"label":META_LABELS[k]} for k in META_FIELDS],
            "date_min":str(rng["mn"]) if rng["mn"] else None,"date_max":str(rng["mx"]) if rng["mx"] else None}

@app.get("/api/orders")
def orders(request:Request, platform:str=None, login:str=None, order_type:str=None, start:str=None, end:str=None,
           search:str=None, account:list[str]=Query(None),
           category:list[str]=Query(None), product:list[str]=Query(None), ecom_platform:list[str]=Query(None),
           ad_channel:list[str]=Query(None), store:list[str]=Query(None), agency:list[str]=Query(None),
           sort:str="pay_time", limit:int=50, offset:int=0):
    cond=[]; args=[]
    scond,sval=_scope_cond(request,"ad_account_id")                  # 数据范围隔离
    if scond:
        cond.append(scond)
        if sval is not None: args.append(sval)
    if platform: cond.append("platform=%s"); args.append(platform)
    if login: cond.append("login_account=%s"); args.append(login)
    if order_type: cond.append("order_type=%s"); args.append(order_type)
    if account: cond.append("ad_account_name = ANY(%s)"); args.append(account)   # 广告账户名称(多选)
    if start: cond.append("order_date>=%s"); args.append(start)
    if end: cond.append("order_date<=%s"); args.append(end)
    if search:
        cond.append("(order_no ILIKE %s OR main_order_no ILIKE %s OR ad_account_name ILIKE %s OR product_info ILIKE %s)")
        args += [f"%{search}%"]*4
    _order_meta_filter(cond, args, category, product, ecom_platform, ad_channel, store, agency)
    w=" AND ".join(cond) or "true"
    sort_col=sort if sort in _ORDER_SORTS else "pay_time"
    c=db(); cur=c.cursor()
    cur.execute(f"SELECT count(*) n, COALESCE(sum(pay_amount),0) amt FROM orders WHERE {w}", args)
    agg=cur.fetchone()
    cur.execute(f"SELECT * FROM orders WHERE {w} ORDER BY {sort_col} DESC NULLS LAST LIMIT %s OFFSET %s", args+[limit,offset])
    rows=[dict(r) for r in cur.fetchall()]
    # B-G 人工列：按广告账号ID 绑定 account_meta（在账户看板配置）
    ids=list({r["ad_account_id"] for r in rows if r.get("ad_account_id")})
    metamap={}
    if ids:
        cur.execute(f"SELECT entity_id,{','.join(META_FIELDS)} FROM account_meta WHERE entity_id = ANY(%s)",(ids,))
        metamap={r["entity_id"]:dict(r) for r in cur.fetchall()}
    for r in rows:
        for k in ("click_time","pay_time","refund_time"): r[k]=str(r[k]) if r[k] else None
        r["order_date"]=str(r["order_date"]) if r["order_date"] else None
        r["fetched_at"]=fmt_dt(r.get("fetched_at"))
        for k in ("product_price","pay_amount"): r[k]=float(r[k]) if r[k] is not None else None
        m=metamap.get(r.get("ad_account_id")) or {}
        for f in META_FIELDS: r[f]=m.get(f)   # 用 account_meta 覆盖(orders表自身B-G列忽略)
    c.close()
    return {"total":agg["n"], "sum_pay":float(agg["amt"] or 0), "rows":rows}

# 订单导出列(顺序与前端订单明细一致)
_ORDER_EXPORT_COLS=[
    ("platform","平台"),("order_type","订单类型"),
    ("ad_account_name","广告账户名称"),("ad_account_id","广告账户ID"),
    ("ad_name","广告名称"),("material_name","视频素材名称"),
    ("main_order_no","主订单号"),("order_no","订单号"),("product_id","商品ID"),
    ("product_info","商品信息"),("product_price","商品单价"),("pay_amount","付款金额"),
    ("order_status","订单状态"),("callback_status","回传"),
    ("click_time","点击时间"),("pay_time","付款时间"),("refund_time","退款时间"),
    # 派生字段（与前端订单页 enrich 一致）
    ("click_to_pay","点击到付款时间"),("pay_to_refund","付款到退款时间"),
    ("reflow_days","回流天数"),("same_day_real_pay","是否当天真实付款"),
    ("attribution","归因"),("ad_position","广告投放位置"),
]+[(f,META_LABELS[f]) for f in META_FIELDS]
_TEXTFMT_COLS={"ad_account_id","main_order_no","order_no","product_id"}   # 长数字设文本,防Excel科学计数

# 派生字段计算（复刻前端 Orders.vue enrich；click_time/pay_time/refund_time 是 datetime）
_PAID_STATUSES=["已付款","已完成","订单付款","支付","成交","已结算"]
def _fmt_dur(sec):
    if sec is None or sec<0: return ""
    s=int(sec); d=s//86400; h=(s%86400)//3600; m=(s%3600)//60
    if d: return f"{d}天{h}时"
    if h: return f"{h}时{m}分"
    return f"{m}分"
def _order_calc(r):
    ct,pt,rt=r.get("click_time"),r.get("pay_time"),r.get("refund_time")
    r["click_to_pay"]=_fmt_dur((pt-ct).total_seconds()) if (ct and pt) else ""
    r["pay_to_refund"]=_fmt_dur((rt-pt).total_seconds()) if (pt and rt) else ""
    if ct and pt:
        dd=(pt.date()-ct.date()).days
        r["reflow_days"]=dd
        paid=any(s in (r.get("order_status") or "") for s in _PAID_STATUSES)
        r["same_day_real_pay"]="是" if (dd==0 and paid) else "否"
    else:
        r["reflow_days"]=None; r["same_day_real_pay"]=""
    return r

@app.get("/api/orders/export")
def orders_export(request:Request, platform:str=None, login:str=None, order_type:str=None, start:str=None, end:str=None,
                  search:str=None, account:list[str]=Query(None),
                  category:list[str]=Query(None), product:list[str]=Query(None), ecom_platform:list[str]=Query(None),
                  ad_channel:list[str]=Query(None), store:list[str]=Query(None), agency:list[str]=Query(None), sort:str="pay_time"):
    """导出当前筛选的订单为 xlsx(全部匹配行,不分页)。筛选口径与 /api/orders 完全一致。"""
    import io, openpyxl
    from urllib.parse import quote
    from fastapi.responses import StreamingResponse
    cond=[]; args=[]
    scond,sval=_scope_cond(request,"ad_account_id")                  # 数据范围隔离
    if scond:
        cond.append(scond)
        if sval is not None: args.append(sval)
    if platform: cond.append("platform=%s"); args.append(platform)
    if login: cond.append("login_account=%s"); args.append(login)
    if order_type: cond.append("order_type=%s"); args.append(order_type)
    if account: cond.append("ad_account_name = ANY(%s)"); args.append(account)
    if start: cond.append("order_date>=%s"); args.append(start)
    if end: cond.append("order_date<=%s"); args.append(end)
    if search:
        cond.append("(order_no ILIKE %s OR main_order_no ILIKE %s OR ad_account_name ILIKE %s OR product_info ILIKE %s)")
        args += [f"%{search}%"]*4
    _order_meta_filter(cond, args, category, product, ecom_platform, ad_channel, store, agency)
    w=" AND ".join(cond) or "true"
    sort_col=sort if sort in _ORDER_SORTS else "pay_time"
    c=db(); cur=c.cursor()
    cur.execute(f"SELECT * FROM orders WHERE {w} ORDER BY {sort_col} DESC NULLS LAST", args)
    rows=[dict(r) for r in cur.fetchall()]
    ids=list({r["ad_account_id"] for r in rows if r.get("ad_account_id")})
    metamap={}
    if ids:
        cur.execute(f"SELECT entity_id,{','.join(META_FIELDS)} FROM account_meta WHERE entity_id = ANY(%s)",(ids,))
        metamap={r["entity_id"]:dict(r) for r in cur.fetchall()}
    c.close()
    wb=openpyxl.Workbook(); ws=wb.active; ws.title="订单明细"
    ws.append([lbl for _,lbl in _ORDER_EXPORT_COLS])
    def cell(r,key):
        if key in META_FIELDS:
            m=metamap.get(r.get("ad_account_id")) or {}; return m.get(key) or ""
        v=r.get(key)
        if v is None: return ""
        if key in ("product_price","pay_amount"): return float(v)          # 数值
        if key=="reflow_days": return int(v)                                # 回流天数(数值)
        if key in ("click_time","pay_time","refund_time","order_date"): return str(v)
        return str(v)
    for r in rows:
        _order_calc(r)                                    # 补派生字段(点击到付款/回流天数等)
        ws.append([cell(r,k) for k,_ in _ORDER_EXPORT_COLS])
    # 长数字列设文本格式,防科学计数
    for ci,(k,_) in enumerate(_ORDER_EXPORT_COLS, start=1):
        if k in _TEXTFMT_COLS:
            for row in ws.iter_rows(min_row=2, min_col=ci, max_col=ci):
                for c2 in row: c2.number_format="@"
    buf=io.BytesIO(); wb.save(buf); buf.seek(0)
    fn=quote("订单明细.xlsx")
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{fn}"})

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
        category text, product text, ecom_platform text, store text, ad_channel text, agency text,
        updated_at timestamptz DEFAULT now())""")
    cur.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS daily_time text")  # 每日定时(HH:MM)，空则用 interval_minutes
    cur.execute("ALTER TABLE accounts ADD COLUMN IF NOT EXISTS is_historical boolean DEFAULT false")  # 历史账号：不再抓取、列表置底
    # 登录账户表：默认种子账户 skg
    cur.execute("""CREATE TABLE IF NOT EXISTS auth_users (
        username text PRIMARY KEY, salt text, pw_hash text, updated_at timestamptz DEFAULT now())""")
    # 账号密码用户扩展：显示名/角色/启停/备注/有效期/数据范围(代理商+账户)/登录统计
    for col,ddl in (("name","text"),("is_admin","boolean DEFAULT false"),("is_active","boolean DEFAULT true"),
                    ("note","text"),("expires_at","date"),
                    ("scope_agencies","jsonb DEFAULT '[]'::jsonb"),("scope_stores","jsonb DEFAULT '[]'::jsonb"),("scope_accounts","jsonb DEFAULT '[]'::jsonb"),
                    ("first_login_at","timestamptz"),("last_login_at","timestamptz"),("login_count","int DEFAULT 0"),("created_at","timestamptz DEFAULT now()")):
        cur.execute(f"ALTER TABLE auth_users ADD COLUMN IF NOT EXISTS {col} {ddl}")
    cur.execute("SELECT count(*) n FROM auth_users")
    if cur.fetchone()["n"]==0:
        salt=secrets.token_hex(16)
        cur.execute("INSERT INTO auth_users(username,salt,pw_hash,name,is_admin) VALUES(%s,%s,%s,%s,true)",
            ("skg", salt, _hash_pw("skg@A168", salt), "主管理员"))
    else:
        cur.execute("UPDATE auth_users SET is_admin=true WHERE username='skg'")   # 内置 skg 恒为管理员
    # 用户表：飞书登录用户(开放注册，首次登录自动建号)。与共享密码账户 auth_users 相互独立。
    cur.execute("""CREATE TABLE IF NOT EXISTS users (
        id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
        open_id text UNIQUE, union_id text, feishu_user_id text,
        name text, avatar_url text, email text, mobile text,
        source text DEFAULT 'feishu', is_active boolean DEFAULT true, is_admin boolean DEFAULT false,
        first_login_at timestamptz DEFAULT now(), last_login_at timestamptz, login_count int DEFAULT 0,
        created_at timestamptz DEFAULT now(), updated_at timestamptz DEFAULT now())""")
    # 用户在网页的停留时长：按 (用户标识, 日期) 累加活跃秒数(前端心跳上报)。飞书=open_id，密码账号=username。
    cur.execute("""CREATE TABLE IF NOT EXISTS user_activity (
        user_key text, date date, seconds int DEFAULT 0, updated_at timestamptz DEFAULT now(),
        PRIMARY KEY(user_key, date))""")
    # 自定义列「常用列」预设：管理员(主账号)存的 is_shared=true 全员可见；普通用户(子账号)存的仅自己可见
    cur.execute("""CREATE TABLE IF NOT EXISTS column_presets (
        id serial PRIMARY KEY,
        page text NOT NULL,                 -- 页面标识：account_board / orders
        owner text NOT NULL,                -- 归属用户(token sub：飞书 open_id 或 密码账户 username)
        owner_name text,                    -- 归属显示名(展示用)
        name text NOT NULL,                 -- 预设名
        is_shared boolean DEFAULT false,    -- 是否共享(管理员存的为 true)
        columns jsonb NOT NULL,             -- 有序列配置 [{key,pinned}]
        created_at timestamptz DEFAULT now(), updated_at timestamptz DEFAULT now(),
        UNIQUE(page, owner, name))""")
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
