# -*- coding: utf-8 -*-
"""
微橙 (business.douyongtuan.com) 数据统计→巨量引擎 报表抓取脚本
-------------------------------------------------
抓取「账户 / 计划 / 素材」三个维度（巨量引擎 platform=1），全量翻页导出 CSV
（UTF-8-BOM，Excel 直接打开）。微橙的数值已是成品（元/比率），无需换算。

【认证免手填】运行时弹出浏览器：
  - 已登录则几秒内自动取到 session_id 继续；
  - 未登录/过期则在窗口里登录一次，自动继续。
  登录态存于脚本同目录 .wc_profile 文件夹。

【每次只需改】下面 START_DATE / END_DATE。运行：python scrape_weicheng.py
"""
import json, csv, os, time, urllib.request, urllib.parse
from playwright.sync_api import sync_playwright

# ============================ 配置区 ============================
START_DATE = "2026-06-01"
END_DATE   = "2026-06-30"
PLATFORM   = 1          # 1 = 巨量引擎
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTDIR     = SCRIPT_DIR
PROFILE    = os.path.join(SCRIPT_DIR, ".wc_profile")
ENTRY_URL  = "https://business.douyongtuan.com/#/tiktok"
BASE       = "https://taotik.douyongtuan.com/business/"
SID_OVERRIDE = ""       # 可选：直接填 session_id 跳过开浏览器
CID_OVERRIDE = ""       # 可选：直接填 customer_id
# ===============================================================

CLICK = """(name)=>{const els=[...document.querySelectorAll('*')].filter(e=>e.children.length===0&&(e.textContent||'').trim()===name);if(els.length){els[0].click();return true}return false}"""


def get_auth():
    if SID_OVERRIDE and CID_OVERRIDE:
        return SID_OVERRIDE, CID_OVERRIDE
    grabbed = {}
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(PROFILE, headless=False, args=["--start-maximized"], no_viewport=True)
        pg = ctx.pages[0] if ctx.pages else ctx.new_page()

        def on_req(req):
            if "taotik.douyongtuan.com/business/" in req.url and req.post_data:
                q = urllib.parse.parse_qs(req.post_data)
                if "session_id" in q:
                    grabbed["sid"] = q["session_id"][0]
                    grabbed["cid"] = q.get("customer_id", [""])[0]
        pg.on("request", on_req)
        try: pg.goto(ENTRY_URL, timeout=60000)
        except Exception: pass
        print(">>> 若未自动继续，请在浏览器登录微橙（最多等 6 分钟）...")
        for _ in range(180):
            if grabbed.get("sid"): break
            # 进入 数据统计 → 巨量引擎 触发接口
            try:
                pg.evaluate(CLICK, "数据统计"); pg.wait_for_timeout(800)
                pg.evaluate(CLICK, "巨量引擎")
            except Exception: pass
            time.sleep(2)
        ctx.close()
    if not grabbed.get("sid"):
        raise SystemExit("未能获取 session_id，请确认已登录后重试。")
    print(f">>> 已获取 session_id: {grabbed['sid'][:10]}...  customer_id={grabbed.get('cid')}")
    return grabbed["sid"], grabbed.get("cid")


SID, CID = get_auth()
H = {"content-type": "application/x-www-form-urlencoded", "accept": "application/json, text/plain, */*",
     "origin": "https://business.douyongtuan.com", "referer": "https://business.douyongtuan.com/",
     "accept-encoding": "identity",
     "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"}


def call(path, page):
    data = {"session_id": SID, "customer_id": CID, "page": page,
            "start_time": START_DATE + " 00:00:00", "end_time": END_DATE + " 23:59:59", "platform": PLATFORM}
    req = urllib.request.Request(BASE + path, data=urllib.parse.urlencode(data).encode(), headers=H, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def fetch_all(path):
    page, items, total, stat = 1, [], 0, None
    while True:
        d = (call(path, page).get("data") or {})
        rows = d.get("data") or []
        items += rows; total = d.get("total", 0); stat = d.get("statistics")
        last = d.get("last_page", 1)
        print(f"    {path} page {page}/{last}: +{len(rows)} ({len(items)}/{total})")
        if page >= last or not rows or len(items) >= total: break
        page += 1; time.sleep(0.15)
    return items, total, stat


FIELD_MAP = {
 "name":"名称","account":"账户(邮箱)","advertiser_name":"广告主","advertiser_id":"广告主ID","version":"版本",
 "ad_name":"计划名称","ad_id":"计划ID","material_name":"素材名称","material_id":"素材ID","drop_type":"投放类型",
 "project_name":"项目名称","project_id":"项目ID","promotion_name":"广告名称","promotion_id":"广告ID","create_time":"创建时间",
 "scost":"总消耗(元)","sshow":"展示数","sclick":"点击数","sbutton":"行为数","sbclick":"关键行为数","sconvert":"转化数",
 "sctr":"点击率(%)","ctr":"点击率","cpm_platform":"平均千次展示成本","cpc_platform":"平均点击成本",
 "savg_click_cost":"均点击成本","savg_show_cost":"均千展成本","sconvert_cost":"转化成本","sbuy_cost":"购买成本","order_single":"客单价",
 "salipay_total_price":"今日成交金额","salipay_count":"今日成交订单数","sad_alipay_total_price":"广告成交金额","sad_alipay_count":"广告成交订单数",
 "sall_alipay_total_price":"总成交金额","sall_alipay_count":"总成交订单数","sbf_alipay_total_price":"反流成交金额","sbf_alipay_count":"反流成交订单数",
 "ssingle_total_price":"单品成交金额","ssingle_count":"单品成交订单数","sall_single_total_price":"总单品成交金额","sall_single_count":"总单品成交订单数",
 "sdeposit_total_price":"预售成交金额","sdeposit_remaining_total_price":"预售尾款金额","sdeposit_alipay_count":"预售订单数",
 "ROI":"ROI","ROI_today":"今日ROI","ROI_reflux":"反流ROI","ROI_single":"单品ROI","ROI_all_single":"总单品ROI",
 "ROI_deposit":"预售ROI","ROI_all":"总ROI","ROI_refund":"退款ROI",
 "refund_alipay_price":"退款金额","refund_alipay_count":"退款订单数","refund_rate":"退款率",
 "spa_gmv":"商品GMV","sin_app_order_gmv":"站内成交GMV","sadd_cart_volume":"加购数","sfavorite_baby_volume":"收藏宝贝数",
 "sdirect_add_cart_volume":"直接加购数","sdirect_favorite_baby_volume":"直接收藏数",
 "stotal_play":"总播放","svalid_play":"有效播放","splay_duration_3s":"3秒播放","splay_100_feed_break":"完播数",
 "sphoto_show":"图片展示","sphoto_click":"图片点击","poster_url":"封面","url":"素材链接",
}
SKIP_OBJ = {"secondAccount", "customerData", "plan", "adMaterial", "labels"}
LEAD = {
 "account":  ["name","account","advertiser_name","advertiser_id","version","drop_type"],
 "plan":     ["ad_name","ad_id","advertiser_name","advertiser_id","project_name","promotion_name","create_time"],
 "material": ["material_name","material_id","advertiser_name","project_name","promotion_name","create_time","url"],
}
ORDER = ["scost","sshow","sclick","sbutton","sbclick","sctr","ctr","cpm_platform","cpc_platform","sconvert","sconvert_cost",
 "sbuy_cost","order_single","ROI","ROI_today","ROI_all","ROI_reflux","ROI_single","ROI_deposit","ROI_refund",
 "salipay_total_price","salipay_count","sad_alipay_total_price","sad_alipay_count","sall_alipay_total_price","sall_alipay_count",
 "sbf_alipay_total_price","sbf_alipay_count","ssingle_total_price","ssingle_count","sdeposit_total_price","sdeposit_alipay_count",
 "refund_alipay_price","refund_alipay_count","refund_rate","spa_gmv","sin_app_order_gmv","sadd_cart_volume","sfavorite_baby_volume",
 "stotal_play","svalid_play","splay_duration_3s","splay_100_feed_break","poster_url"]


def val(v):
    if v is None or isinstance(v, (dict, list)): return ""
    return v


def write_csv(fn, lead, items, stat):
    if not items:
        print(f"  (无数据，跳过 {fn})"); return 0
    present = set()
    for it in items:
        for k, v in it.items():
            if k not in SKIP_OBJ and not isinstance(v, (dict, list)): present.add(k)
    cols = [k for k in lead if k in present] + [k for k in ORDER if k in present and k not in lead]
    cols += [k for k in present if k not in cols]
    head = [FIELD_MAP.get(k, k) for k in cols]
    p = os.path.join(OUTDIR, fn)
    with open(p, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(head)
        if isinstance(stat, dict) and stat:
            w.writerow(["合计"] + [val(stat.get(k)) for k in cols[1:]])
        for it in items:
            w.writerow([val(it.get(k)) for k in cols])
    print(f"  -> {p}  ({len(items)} 行)")
    return len(items)


def main():
    print(f"日期范围: {START_DATE} ~ {END_DATE}  platform={PLATFORM}\n输出目录: {OUTDIR}\n")
    tasks = [("1_账户.csv", "SecondAccountData/businessFindsDev", LEAD["account"]),
             ("2_计划.csv", "PlanData/businessFindsDev", LEAD["plan"]),
             ("3_素材.csv", "MaterialData/findsDev", LEAD["material"])]
    summary = []
    for fn, path, lead in tasks:
        print(f"[{fn}]")
        items, total, stat = fetch_all(path)
        summary.append((fn, write_csv(fn, lead, items, stat)))
    print("\n==== 汇总 ====")
    for fn, n in summary:
        print(f"  {fn}: {n}")


if __name__ == "__main__":
    main()
