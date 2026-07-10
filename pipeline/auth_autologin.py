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
    "博擎": "https://bccid.jingcaiplus.com/admin/index.html",   # fifay 换皮，登录/接口同沸点
}
PW_PLATFORMS = ("沸点", "微橙", "麦斯", "小飞机", "博擎")  # 可纯密码自动登录(小飞机正常登录只需账号密码，验证码仅多次失败才触发)

CLICK = ("(name)=>{let e=[...document.querySelectorAll('*')].filter(x=>x.children.length===0&&"
         "(x.textContent||'').trim()===name);e.sort((a,b)=>a.textContent.length-b.textContent.length);"
         "if(e.length){e[0].click();return true}return false}")

# 数据页地址：抓 token 的接口要在这些页面上才会触发
DATA_URL = {
    "沸点": "https://admin.fifay.cn/admin/index.html#/data?tab=1",
    "博擎": "https://bccid.jingcaiplus.com/admin/index.html#/data?tab=1",
}


def trigger_data(pg, platform):
    """登录后导航/点击到能触发带凭证接口的数据页。"""
    try:
        if platform in ("沸点", "博擎"):
            pg.evaluate(CLICK, "抖音数据看板")
            pg.wait_for_timeout(800)
            if "/data" not in pg.url:
                pg.goto(DATA_URL[platform], timeout=30000)
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
        elif platform in ("沸点", "博擎") and "api.fifay.cn" in u:   # 博擎也走 api.fifay.cn
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
            ("token", "did") if platform in ("沸点", "博擎") else
            ("session_id",) if platform == "微橙" else ("x_token",))


def fill_password_login(pg, platform, user, pw):
    """在登录页填账号密码并提交。返回 True 表示已提交。"""
    try:
        if platform in ("沸点", "博擎"):
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
        elif platform == "小飞机":
            pg.wait_for_selector("input[placeholder*='邮箱']", timeout=15000)
            pg.fill("input[placeholder*='邮箱']", user)
            pg.fill("input[placeholder*='密码']", pw)
            try: pg.check("input[type=checkbox]", timeout=2000)   # 勾选隐私协议
            except Exception: pass
            pg.press("input[placeholder*='密码']", "Enter")        # 回车提交(页面多处"登录"字样，点击易歧义)
            return True
    except Exception as e:
        print("fill err:", repr(e)[:120], flush=True)
    return False


def grab_cid_token(ctx, user, pw):
    """小飞机 CID 素材系统(cid.smallfighter.com)独立登录，抓 Bearer token。
    profile 已登录则直接抓；否则用账号密码登(CID 正常登录无短信)。返回 {cid_token,cid_op_uid} 或 {}。"""
    g = {}
    pg = ctx.new_page()
    def on_req(req):
        h = req.headers
        if "cid.smallfighter.com/v1" in req.url and h.get("authorization", "").startswith("Bearer "):
            g["cid_token"] = h["authorization"][7:]; g["cid_op_uid"] = h.get("td-op-uid", "")
    pg.on("request", on_req)
    try:
        pg.goto("https://cid.smallfighter.com/#reportMaterial", timeout=60000)
        pg.wait_for_timeout(3000)
        if pg.query_selector("input[placeholder*='邮箱']") and user and pw:   # 显示登录页 -> 密码登录
            try:
                pg.fill("input[placeholder*='邮箱']", user); pg.fill("input[placeholder*='密码']", pw)
                try: pg.check("input[type=checkbox]", timeout=2000)
                except Exception: pass
                pg.press("input[placeholder*='密码']", "Enter")
            except Exception as e:
                print("cid 填表 err", repr(e)[:80], flush=True)
        for _ in range(10):
            if "cid_token" in g: break
            try: pg.goto("https://cid.smallfighter.com/#reportMaterial", timeout=30000)
            except Exception: pass
            pg.wait_for_timeout(1500)
    except Exception as e:
        print("cid grab err", repr(e)[:100], flush=True)
    try: pg.close()
    except Exception: pass
    return g


def _grab_xfj_cookies(ctx, g):
    """从浏览器上下文读取小飞机 token/op_uid/sid；sid 保持浏览器原编码(s%3A...)，勿再 quote(否则双编码)。"""
    try:
        for ck in ctx.cookies():
            if ck["name"] == "td.token": g["token"] = ck["value"]
            elif ck["name"] == "td-op-uid": g["op_uid"] = ck["value"]
            elif ck["name"] == "td.sid": g["sid"] = ck["value"]
    except Exception:
        pass


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
            if platform == "小飞机": _grab_xfj_cookies(ctx, g)
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
                    if platform == "小飞机": _grab_xfj_cookies(ctx, g)   # 登录后 token/op_uid/sid 从 cookie 读
                    if platform == "麦斯" and "signip" not in g:
                        try: g["signip"] = pg.evaluate("()=>localStorage.getItem('signip')||''") or ""
                        except Exception: pass
                    time.sleep(2)
                session_ok = all(k in g for k in need)

        # 小飞机：额外抓 CID 素材系统 token（独立登录），供素材维度抓取
        if platform == "小飞机" and session_ok:
            try:
                cid = grab_cid_token(ctx, user, pw)
                if cid.get("cid_token"): g.update(cid); print("  + CID token 已获取", flush=True)
                else: print("  ! CID token 未获取(不影响 td 维度)", flush=True)
            except Exception as e:
                print("  ! CID 抓取异常:", repr(e)[:100], flush=True)

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
