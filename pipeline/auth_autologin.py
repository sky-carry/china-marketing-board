# -*- coding: utf-8 -*-
"""密码自动重登 + 登录态续期。
- 沸点/微橙/麦斯：纯用户名密码，可全自动填表登录。
- 小飞机：需图形+短信验证码，无法纯密码自动；靠 persistent profile 会话续期，
  会话失效时标记 need_login 让用户手动登一次。

用法(子进程): python auth_autologin.py <account_id>
返回: 打印 OK/FAIL/NEED_LOGIN，并把新凭证写回 DB。
"""
import os
import sys, os, io, time, json, urllib.parse
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import psycopg2, psycopg2.extras
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
DSN = os.environ.get("DATABASE_URL","postgresql://postgres:postgres@localhost:5432/ad_data")
PROFILES = os.path.join(HERE, "profiles")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36")

ENTRY = {
    "小飞机": "https://td.smallfighter.com/#serving",
    "沸点": "https://admin.fifay.cn/admin/index.html",
    "微橙": "https://business.douyongtuan.com/#/tiktok",
    "麦斯": "https://ad.maxengine.cn/media_data/xhs",
}
PW_PLATFORMS = ("沸点", "微橙", "麦斯")  # 可纯密码自动登录

CLICK = ("(name)=>{let e=[...document.querySelectorAll('*')].filter(x=>x.children.length===0&&"
         "(x.textContent||'').trim()===name);e.sort((a,b)=>a.textContent.length-b.textContent.length);"
         "if(e.length){e[0].click();return true}return false}")

# 数据页地址：抓 token 的接口要在这些页面上才会触发
DATA_URL = {
    "沸点": "https://admin.fifay.cn/admin/index.html#/data?tab=1",
}


def trigger_data(pg, platform):
    """登录后导航/点击到能触发带凭证接口的数据页。"""
    try:
        if platform == "沸点":
            pg.evaluate(CLICK, "抖音数据看板")
            pg.wait_for_timeout(800)
            if "/data" not in pg.url:
                pg.goto(DATA_URL["沸点"], timeout=30000)
        elif platform == "麦斯":
            pg.evaluate(CLICK, "广告平台"); pg.wait_for_timeout(600); pg.evaluate(CLICK, "聚光平台")
        elif platform == "微橙":
            pg.evaluate(CLICK, "数据统计"); pg.wait_for_timeout(500); pg.evaluate(CLICK, "巨量引擎")
    except Exception:
        pass


def profile_dir(tag):
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in tag)
    d = os.path.join(PROFILES, safe)
    os.makedirs(d, exist_ok=True)
    return d


def make_capturer(platform, g):
    def on_req(req):
        u = req.url
        h = req.headers
        if platform == "小飞机" and "/v1/" in u and req.method == "POST":
            if h.get("authorization", "").startswith("Bearer "):
                g["token"] = h["authorization"][7:]
                g["op_uid"] = h.get("td-op-uid", "")
                for part in h.get("cookie", "").split("; "):
                    if part.startswith("td.sid="):
                        g["sid"] = part[7:]
        elif platform == "沸点" and "api.fifay.cn" in u:
            if h.get("token"):
                g["token"] = h["token"]
                g["did"] = h.get("did", "")
        elif platform == "微橙" and "taotik.douyongtuan.com/business/" in u and req.post_data:
            q = urllib.parse.parse_qs(req.post_data)
            if "session_id" in q:
                g["session_id"] = q["session_id"][0]
                g["customer_id"] = q.get("customer_id", [""])[0]
        elif platform == "麦斯" and "preapi.maxengine.cn/admin/" in u:
            if h.get("x-token"):
                g["x_token"] = h["x-token"]
                g["signip"] = h.get("signip", "") or g.get("signip", "")
    return on_req


def need_keys(platform):
    return (("token", "sid", "op_uid") if platform == "小飞机" else
            ("token", "did") if platform == "沸点" else
            ("session_id",) if platform == "微橙" else ("x_token",))


def fill_password_login(pg, platform, user, pw):
    """在登录页填账号密码并提交。返回 True 表示已提交。"""
    try:
        if platform == "沸点":
            pg.wait_for_selector("input.ant-input", timeout=15000)
            ins = pg.query_selector_all("input.ant-input")
            if len(ins) < 2:
                return False
            ins[0].fill(user); ins[1].fill(pw)
            pg.evaluate(CLICK, "登 录")
            return True
        elif platform == "微橙":
            # 切到"密码登录"tab
            pg.wait_for_timeout(1500)
            pg.evaluate(CLICK, "密码登录")
            pg.wait_for_timeout(500)
            pg.fill("input[placeholder='请输入用户名']", user)
            pg.fill("input[placeholder='请输入密码']", pw)
            pg.evaluate(CLICK, "登录")
            return True
        elif platform == "麦斯":
            pg.wait_for_selector("input[placeholder='请输入登录账号']", timeout=15000)
            pg.fill("input[placeholder='请输入登录账号']", user)
            pg.fill("input[placeholder='请输入登录密码']", pw)
            pg.evaluate(CLICK, "立即登录")
            return True
    except Exception as e:
        print("fill err:", repr(e)[:120], flush=True)
    return False


def run(account_id, headless=True):
    c = psycopg2.connect(DSN); c.autocommit = True
    cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT platform,tag,username,password,auth FROM accounts WHERE id=%s", (account_id,))
    row = cur.fetchone()
    if not row:
        print("FAIL account not found"); return 1
    platform, tag = row["platform"], row["tag"]
    user, pw = row.get("username"), row.get("password")
    old_auth = dict(row.get("auth") or {})   # 保留 op_uids 等自定义字段，重登时合并而非覆盖
    need = need_keys(platform)
    g = {}

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            profile_dir(tag), headless=headless, user_agent=UA,
            # --no-sandbox / --disable-dev-shm-usage：容器内以 root 运行 Chromium 的必需项
            args=["--no-proxy-server", "--start-maximized", "--no-sandbox", "--disable-dev-shm-usage"],
            no_viewport=True)
        pg = ctx.pages[0] if ctx.pages else ctx.new_page()
        pg.on("request", make_capturer(platform, g))
        try:
            pg.goto(ENTRY[platform], timeout=60000)
        except Exception:
            pass
        pg.wait_for_timeout(3000)

        # 第一阶段：看现有 profile 会话是否还有效（触发导航拿 token）
        for _ in range(6):
            if all(k in g for k in need):
                break
            trigger_data(pg, platform)
            if platform == "小飞机" and "token" not in g:
                try:
                    for ck in ctx.cookies():
                        if ck["name"] == "td.token": g["token"] = ck["value"]
                        elif ck["name"] == "td-op-uid": g["op_uid"] = ck["value"]
                        elif ck["name"] == "td.sid": g["sid"] = urllib.parse.quote(ck["value"], safe="")
                except Exception:
                    pass
            if platform == "麦斯" and "signip" not in g:
                try: g["signip"] = pg.evaluate("()=>localStorage.getItem('signip')||''") or ""
                except Exception: pass
            time.sleep(2)

        session_ok = all(k in g for k in need)

        # 第二阶段：会话失效 + 支持纯密码 → 自动填表登录
        if not session_ok and platform in PW_PLATFORMS and user and pw:
            cur_url = pg.url
            if "login" not in cur_url.lower():
                # 可能停在别处，主动去登录页
                try: pg.goto(ENTRY[platform], timeout=30000)
                except Exception: pass
                pg.wait_for_timeout(2000)
            print(">>> 会话失效，尝试密码自动登录 %s / %s" % (platform, tag), flush=True)
            if fill_password_login(pg, platform, user, pw):
                pg.wait_for_timeout(2500)
                for _ in range(15):
                    if all(k in g for k in need):
                        break
                    trigger_data(pg, platform)
                    if platform == "麦斯" and "signip" not in g:
                        try: g["signip"] = pg.evaluate("()=>localStorage.getItem('signip')||''") or ""
                        except Exception: pass
                    time.sleep(2)
                session_ok = all(k in g for k in need)

        ctx.close()

    if session_ok:
        merged = {**old_auth, **g}   # 合并：新抓到的 token 覆盖旧值，保留 op_uids 等未变字段
        cur.execute("UPDATE accounts SET auth=%s, token_status='ok', token_updated_at=now() WHERE id=%s",
                    (psycopg2.extras.Json(merged), account_id))
        print("OK 已更新凭证:", list(g.keys())); return 0
    if platform == "小飞机":
        cur.execute("UPDATE accounts SET token_status='need_login' WHERE id=%s", (account_id,))
        print("NEED_LOGIN 小飞机会话失效，需手动登录(短信验证码)"); return 3
    cur.execute("UPDATE accounts SET token_status='expired' WHERE id=%s", (account_id,))
    print("FAIL 密码登录未取到凭证"); return 2


if __name__ == "__main__":
    aid = int(sys.argv[1])
    hl = not (len(sys.argv) > 2 and sys.argv[2] == "show")
    sys.exit(run(aid, headless=hl))
