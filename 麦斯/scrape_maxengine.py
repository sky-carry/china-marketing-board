# -*- coding: utf-8 -*-
"""
麦斯引擎 (ad.maxengine.cn) 广告平台→聚光平台(小红书) 报表抓取脚本
-------------------------------------------------
抓取聚光平台「账户 / 计划 / 单元 / 创意 / 关键词」5 个维度，全量翻页导出 CSV
（UTF-8-BOM，Excel 直接打开）。麦斯数值已是成品（元/比率），脚本只去掉千位逗号。

【认证免手填】运行时弹出浏览器：已登录则几秒内自动取到 x-token 继续；
  未登录/过期则在窗口里登录一次。登录态存于脚本同目录 .ms_profile。

【每次只需改】下面 START_DATE / END_DATE。运行：python scrape_maxengine.py
"""
import json, csv, os, time, urllib.request
from playwright.sync_api import sync_playwright

# ============================ 配置区 ============================
START_DATE = "2026-06-01"
END_DATE   = "2026-06-30"
MEDIA_TYPE = 11          # 11 = 小红书聚光平台
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTDIR     = SCRIPT_DIR
PROFILE    = os.path.join(SCRIPT_DIR, ".ms_profile")
ENTRY_URL  = "https://ad.maxengine.cn/media_data/xhs"
API        = "https://preapi.maxengine.cn/admin/"
XTOKEN_OVERRIDE = ""     # 可选：直接填 x-token / signip 跳过开浏览器
SIGNIP_OVERRIDE = ""
# ===============================================================


CLICK = """(name)=>{let els=[...document.querySelectorAll('*')].filter(e=>(e.textContent||'').trim()===name&&e.getBoundingClientRect().width>0);els.sort((a,b)=>a.textContent.length-b.textContent.length);if(els.length){els[0].click();return true}return false}"""


def get_auth():
    if XTOKEN_OVERRIDE and SIGNIP_OVERRIDE:
        return XTOKEN_OVERRIDE, SIGNIP_OVERRIDE
    g = {}
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(PROFILE, headless=False, args=["--start-maximized"], no_viewport=True)
        pg = ctx.pages[0] if ctx.pages else ctx.new_page()

        def on_req(req):
            if "preapi.maxengine.cn/admin/" in req.url:
                h = req.headers
                if h.get("x-token"):
                    g["xtoken"] = h["x-token"]
                    if h.get("signip"): g["signip"] = h["signip"]
        pg.on("request", on_req)
        try: pg.goto(ENTRY_URL, timeout=60000)
        except Exception: pass
        print(">>> 请在弹出的浏览器里登录麦斯引擎（若已登录会自动继续，最多等 6 分钟）...")
        # 登录后 app 会自动发带 x-token 的接口请求即被捕获；同时轻量点一下菜单帮助触发（登录页时无害）
        for i in range(180):
            if g.get("xtoken"): break
            try:
                pg.evaluate(CLICK, "广告平台"); pg.wait_for_timeout(800)
                pg.evaluate(CLICK, "聚光平台")
            except Exception: pass
            # 兜底取 signip
            if not g.get("signip"):
                try: g["signip"] = pg.evaluate("()=>localStorage.getItem('signip')||''") or ""
                except Exception: pass
            time.sleep(1.5)
        ctx.close()
    if not g.get("xtoken"):
        raise SystemExit("未能获取 x-token，请确认已登录后重试。")
    print(f">>> 已获取 x-token: {g['xtoken'][:12]}...  signip={g.get('signip')}")
    return g["xtoken"], g.get("signip")


XTOKEN, SIGNIP = get_auth()
H = {"x-token": XTOKEN, "signip": SIGNIP, "request-source": "max", "accept-encoding": "identity",
     "content-type": "application/json;charset=UTF-8", "accept": "application/json, text/plain, */*",
     "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"}


def base_payload(custom_fields):
    return {"page": 1, "rows": 100, "total": 0, "media_type": MEDIA_TYPE, "order_time_type": 1,
            "start_time": START_DATE, "end_time": END_DATE, "times": [START_DATE, END_DATE],
            "query_type": "advertiser_id", "keyword": "", "custom_fields": custom_fields,
            "customer_ids": [], "parent_customer_ids": [], "salesman_ids": [], "companys": [],
            "admin_ids_1": [], "admin_ids_2": [], "goods_type": "", "conv_rate_type": "", "wait_time_type": "",
            "conv_gmv_type": "", "conv_gmv_rate": "", "marketing_target": [],
            "advance_search": [{"field": ""}, {"field": ""}], "monitor_link_exception": "", "is_uds": 0}


def fetch_all(ep, custom_fields):
    page, items, total, td = 1, [], 0, None
    while True:
        p = base_payload(custom_fields); p["page"] = page
        req = urllib.request.Request(API + ep, data=json.dumps(p).encode(), headers=H, method="POST")
        with urllib.request.urlopen(req, timeout=60) as r:
            d = (json.loads(r.read().decode("utf-8", "replace")).get("data") or {})
        rows = d.get("data") or []
        items += rows; total = d.get("total", 0); td = d.get("total_data")
        last = d.get("last_page", 1)
        print(f"    {ep} page {page}/{last}: +{len(rows)} ({len(items)}/{total})")
        if page >= last or not rows or len(items) >= total: break
        page += 1; time.sleep(0.15)
    return items, td


FIELD_MAP = {
 "company":"账户主体名称","advertiser_id":"账户ID","advertiser_name":"账户名称",
 "campaign_id":"计划ID","campaign_name":"计划名称","unit_id":"单元ID","unit_name":"单元名称",
 "creativity_id":"创意ID","creativity_name":"创意名称","keyword_id":"关键词ID","keyword":"关键词",
 "direct_item_id":"主投品ID","placement_title":"广告类型/版位","admin_name_1":"投手(一级)","admin_name_2":"投手(二级)",
 "costs":"消耗","shows":"展示量","clicks":"点击量","converts":"行动数","click_rate":"点击率","convert_rate":"行动率",
 "convert_cost":"行动成本","cpc":"平均点击单价","cpm":"平均千次曝光",
 "all_no":"总下单量","all_gmv":"总下单金额","all_gsv_no":"总成交量","all_gsv":"总成交额",
 "gmv_roi":"总下单ROI","gsv_roi":"总成交ROI","all_no_cost":"下单成本","all_gsv_no_cost":"成交成本",
 "all_avg_price":"下单客单价","all_gsv_avg_price":"成交客单价",
 "direct_all_no":"主投品下单量","direct_all_gmv":"主投品下单金额","direct_all_gsv_no":"主投品成交量","direct_all_gsv":"主投品成交额",
 "direct_gmv_roi":"主投品下单ROI","direct_gsv_roi":"主投品成交ROI",
 "conv_no":"转化数","conv_gmv":"转化金额","conv_roi":"转化ROI","conv_avg_price":"转化客单价","conv_gmv_cost":"转化金额成本",
 "tbp_cart":"淘系加购数","tbp_cart_cost":"淘系加购成本","tbp_collect":"淘系收藏","direct_collect":"主投品收藏","direct_cart":"主投品加购",
}

# 各维度：(文件名, 接口, 前导字段, 指标列 custom_fields)  —— custom_fields 即 UI 默认展示列
DIMS = [
 ("1_账户.csv", "adv_data/lists", ["advertiser_name","advertiser_id","company"],
  ["company","advertiser_id","costs","direct_gmv_roi","direct_all_no","direct_all_gsv_no","all_no","all_gmv",
   "shows","clicks","all_gsv_no","direct_gsv_roi","gsv_roi","gmv_roi","direct_all_gmv"]),
 ("2_计划.csv", "xhs/campaign_data/lists", ["campaign_name","campaign_id","advertiser_name","advertiser_id"],
  ["campaign_name","costs","converts","gsv_roi","all_gsv_avg_price","all_gsv_no","all_gsv_no_cost","tbp_cart_cost",
   "tbp_cart","cpc","cpm","shows","convert_cost","clicks","convert_rate","click_rate","advertiser_name",
   "direct_all_no","direct_all_gmv","direct_all_gsv_no","direct_all_gsv","direct_gmv_roi","direct_gsv_roi","direct_item_id"]),
 ("3_单元.csv", "xhs/unit_data/lists", ["unit_name","unit_id","campaign_name","campaign_id","advertiser_name"],
  ["advertiser_id","admin_name_1","admin_name_2","costs","clicks","click_rate","converts","convert_rate","convert_cost",
   "shows","cpc","cpm","all_no","all_gsv_no","all_no_cost","all_gsv_no_cost","all_gmv","all_gsv","all_avg_price",
   "all_gsv_avg_price","gmv_roi","gsv_roi","conv_no","conv_gmv","conv_gmv_cost","conv_avg_price","conv_roi",
   "campaign_id","campaign_name","placement_title"]),
 ("4_创意.csv", "xhs/creativity_data/lists", ["creativity_name","creativity_id","unit_name","unit_id","campaign_name","advertiser_name"],
  ["creativity_id","campaign_name","campaign_id","conv_roi","conv_avg_price","conv_gmv_cost","conv_gmv","conv_no",
   "gmv_roi","costs","direct_gsv_roi","gsv_roi","all_gsv","direct_all_gsv","all_gsv_avg_price","all_avg_price","all_gmv",
   "all_gsv_no_cost","all_no_cost","all_gsv_no","all_no","cpm","cpc","shows","convert_cost","convert_rate","converts",
   "click_rate","clicks","admin_name_2","admin_name_1","advertiser_id","direct_all_gsv_no","direct_all_no","direct_all_gmv"]),
 ("5_关键词.csv", "xhs/keyword_data/lists", ["keyword","keyword_id","campaign_name","campaign_id","advertiser_name"],
  ["costs","shows","advertiser_id","clicks","click_rate","converts","convert_rate","convert_cost","cpc","cpm",
   "all_no","all_gsv_no","all_no_cost"]),
]


def val(v):
    if v is None or isinstance(v, (dict, list)): return ""
    if isinstance(v, str): return v.replace(",", "")
    return v


def write_csv(fn, lead, custom_fields, items, td):
    if not items:
        print(f"  (无数据，跳过 {fn})"); return 0
    present = set()
    for it in items: present.update(it.keys())
    cols = [k for k in lead if k in present] + [k for k in custom_fields if k in present and k not in lead]
    head = [FIELD_MAP.get(k, k) for k in cols]
    p = os.path.join(OUTDIR, fn)
    with open(p, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(head)
        if isinstance(td, dict) and td:
            w.writerow(["合计"] + [val(td.get(k)) for k in cols[1:]])
        for it in items:
            w.writerow([val(it.get(k)) for k in cols])
    print(f"  -> {p}  ({len(items)} 行)")
    return len(items)


def main():
    print(f"日期范围: {START_DATE} ~ {END_DATE}  media_type={MEDIA_TYPE}(聚光)\n输出目录: {OUTDIR}\n")
    summary = []
    for fn, ep, lead, cf in DIMS:
        print(f"[{fn}]")
        items, td = fetch_all(ep, cf)
        summary.append((fn, write_csv(fn, lead, cf, items, td)))
    print("\n==== 汇总 ====")
    for fn, n in summary:
        print(f"  {fn}: {n}")


if __name__ == "__main__":
    main()
