# -*- coding: utf-8 -*-
"""阿里妈妈 UD 凭证刷新：从一条 UD 的 cURL(浏览器 F12→Copy as cURL) 解析出
cookie / csrfId / dynamicToken，写进 accounts.auth（platform=阿里妈妈）。

阿里/淘宝登录强反爬，无法自动登录，cookie 需人工定期刷：
  cookie 失效时(账号管理页显示 expired)，在浏览器对任意一条 ud.alimama.com 请求
  右键 Copy as cURL(cmd 或 bash 均可)，存成文件，跑：
      python alimama_setauth.py "<账号tag>" <curl文件>
  账号不存在则新建，存在则只更新 auth。
"""
import sys, os, io, re, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import psycopg2, psycopg2.extras

DSN = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/ad_data")

def _clean(text):
    # 还原 Windows cmd cURL 的 ^ 转义（bash 版无这些，替换后无副作用）
    return (text.replace('^\\^"', '\\"').replace('^%^', '%').replace('^&', '&').replace('^"', '"'))

def parse_curl(text):
    t = _clean(text)
    # cookie：-b "..." 或 -H "cookie: ..."（cookie 值内无双引号）
    m = re.search(r'-b\s+"([^"]*)"', t) or re.search(r'-H\s+"cookie:\s*([^"]*)"', t, re.I)
    cookie = m.group(1).strip() if m else None
    # 请求体（POST）或 URL query（GET）里找 csrfId / dynamicToken
    md = re.search(r'--data-raw\s+"([^"]*)"', t) or re.search(r"--data-raw\s+'([^']*)'", t)
    body = md.group(1) if md else ""
    url = ""
    mu = re.search(r'curl\s+"([^"]+)"', t)
    if mu: url = mu.group(1)
    def find(k):
        for src in (body, url):
            mm = re.search(rf'[?&]?\b{k}=([^&"\s]+)', src)
            if mm: return mm.group(1).strip()
        return None
    return cookie, find("csrfId"), find("dynamicToken")

def _selftest():
    sample = (r'''curl ^"https://ud.alimama.com/advertiser/horizontal/findPage.json^" ^'''
              "\n" r'''  -b ^"unb=2222093527389; wk_unb=UUGjOpzFsZcmrA^%^3D^%^3D; csg=a4c1356f^" ^'''
              "\n" r'''  --data-raw ^"bizCode=udSmart^&csrfId=abc_1_1_1^&dynamicToken=123456^"''')
    ck, cs, dt = parse_curl(sample)
    assert ck == "unb=2222093527389; wk_unb=UUGjOpzFsZcmrA%3D%3D; csg=a4c1356f", ck
    assert cs == "abc_1_1_1", cs
    assert dt == "123456", dt
    print("selftest OK:", cs, dt, "| cookie ok")

def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "--selftest":
        _selftest(); return
    if len(sys.argv) < 3:
        print("用法: python alimama_setauth.py \"<账号tag>\" <curl文件>"); sys.exit(1)
    tag = sys.argv[1]
    text = open(sys.argv[2], encoding="utf-8", errors="replace").read()
    cookie, csrf, dyn = parse_curl(text)
    if not cookie or "unb=" not in cookie:
        print("解析失败：没找到有效 cookie（确认是 ud.alimama.com 的 cURL）"); sys.exit(2)
    auth = {"cookie": cookie}
    if csrf: auth["csrfId"] = csrf
    if dyn: auth["dynamicToken"] = dyn
    if not csrf or not dyn:
        print("⚠ 未解析到 csrfId/dynamicToken（建议用带 --data-raw 的 POST 请求，如 findPage.json/report/query.json）")
    c = psycopg2.connect(DSN); c.autocommit = True; cur = c.cursor()
    cur.execute("""INSERT INTO accounts(platform,tag,auth,enabled,token_status,token_updated_at)
        VALUES('阿里妈妈',%s,%s,true,'ok',now())
        ON CONFLICT (tag) DO UPDATE SET auth=EXCLUDED.auth, token_status='ok', token_updated_at=now()""",
        (tag, psycopg2.extras.Json(auth)))
    c.close()
    print(f"OK 已写入账号「{tag}」：cookie {len(cookie)} 字符, csrfId={'有' if csrf else '无'}, dynamicToken={'有' if dyn else '无'}")

if __name__ == "__main__":
    main()
