# -*- coding: utf-8 -*-
"""
沸点投放 (admin.fifay.cn) 数据报表抓取脚本
-------------------------------------------------
功能：抓取「账户/项目/计划/素材/产品」维度(report/union/get) +「店铺(PA)/商品(PA)」+「订单」维度，
      全量翻页，分别导出 CSV（UTF-8-BOM，Excel 直接打开）。金额自动 ÷100 转元，比率 ÷100。

【认证免手填】运行时会弹出浏览器：
  - 如果已登录（首次登录后会被记住），脚本几秒内自动取到 token 并继续；
  - 如果未登录/登录过期，请在弹出的窗口里登录一次，脚本会自动继续。
  登录态保存在脚本同目录的 .fifay_profile 文件夹里。

【每次只需改】下面的 START_DATE / END_DATE。
依赖：playwright（已安装）。运行：python scrape_fifay.py
"""
import json, csv, os, time, datetime, urllib.request
from playwright.sync_api import sync_playwright

# ============================ 配置区 ============================
START_DATE = "2026-06-01"
END_DATE   = "2026-06-30"
PAGE       = 200
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTDIR     = SCRIPT_DIR
PROFILE    = os.path.join(SCRIPT_DIR, ".fifay_profile")
DATA_URL   = "https://admin.fifay.cn/admin/index.html#/data?tab=1"
# 可选：若已知 token/did 可直接填，跳过开浏览器（一般留空即可）
TOKEN_OVERRIDE = ""
DID_OVERRIDE   = ""
# ===============================================================


def get_auth():
    """用持久化浏览器自动获取 token / did（必要时等待用户登录）"""
    if TOKEN_OVERRIDE and DID_OVERRIDE:
        return TOKEN_OVERRIDE, DID_OVERRIDE
    grabbed = {}
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(PROFILE, headless=False, args=["--start-maximized"], no_viewport=True)
        pg = ctx.pages[0] if ctx.pages else ctx.new_page()

        def on_req(req):
            if "api.fifay.cn" in req.url:
                h = req.headers
                if h.get("token"):
                    grabbed["token"] = h.get("token")
                    grabbed["did"] = h.get("did", "")
        pg.on("request", on_req)
        try: pg.goto(DATA_URL, timeout=60000)
        except Exception: pass
        print(">>> 若未自动继续，请在弹出的浏览器里登录沸点投放（最多等 6 分钟）...")
        for _ in range(180):
            if grabbed.get("token"): break
            # 不停点一下「项目维度」触发接口请求以便抓到 token
            try:
                pg.evaluate("""()=>{const e=[...document.querySelectorAll('*')].find(x=>x.children.length===0&&(x.textContent||'').trim()==='项目维度');if(e)e.click();}""")
            except Exception: pass
            time.sleep(2)
        ctx.close()
    if not grabbed.get("token"):
        raise SystemExit("未能获取 token，请确认已登录后重试。")
    print(f">>> 已获取 token: {grabbed['token'][:8]}...")
    return grabbed["token"], grabbed.get("did", "")


TOKEN, DID = get_auth()
HEADERS = {
    "accept": "application/json", "content-type": "application/json", "accept-encoding": "identity",
    "did": DID, "token": TOKEN, "version": "1.0.2", "platform": "h5",
    "origin": "https://admin.fifay.cn", "referer": "https://admin.fifay.cn/",
    "traceid": "00000000-0000-0000-0000-000000000000",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
}


def post(path, body):
    req = urllib.request.Request("https://api.fifay.cn/fifay-ad/" + path,
                                 data=json.dumps(body).encode("utf-8"), headers=HEADERS, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_all(path, base):
    cur, items, total, td = 1, [], 0, None
    while True:
        b = dict(base); b["current"] = cur; b["pageSize"] = PAGE
        d = (post(path, b).get("data") or {})
        lst = d.get("list") or []
        items += lst; total = d.get("total", 0); td = d.get("totalData")
        print(f"    {path}[{base.get('adReportType','')}] page {cur}: +{len(lst)} ({len(items)}/{total})")
        if d.get("endPage") or len(items) >= total or not lst: break
        cur += 1; time.sleep(0.15)
    return items, total, td


# ---- 字段缩放 / 中文名 ----
MONEY = {"cost","qfCost","cpc","cpm","orderCost","orderAmount","originOrderAmount","refundOrderAmount",
 "backOrderAmount","originBackOrderAmount","refundBackOrderAmount","inAppOrderGmv","inAppOrderNetGmv",
 "validPlayCost","cpaBid","atv","conversionCost","directOrderAmount","directOriginOrderAmount",
 "directRefundOrderAmount","balance","payMoney","commissionAmount","goodsPrice"}
RATIO = {"ctr","pageClickRate","orderRate","conversionRate","refundOrderRate","orderRoi","noBackOrderRoi",
 "originOrderRoi","inAppOrderRoi","validPlayRate","orderPercent","play25FeedBreak","play50FeedBreak","play75FeedBreak"}
TIME_FIELDS = {"orderCreateTime","orderClickTime","orderPayTime","orderDoneTime","orderRefundTime"}
FIELD_MAP = {
 "advertiserName":"账户名称","advertiserId":"账户ID","advertiserOwnerName":"投手/归属","advertiserStatus":"账户状态",
 "projectName":"项目名称","projectId":"项目ID","projectStatus":"项目状态",
 "adName":"计划名称","adId":"计划ID","adStatus":"计划状态","deepBidType":"出价方式","cpaBid":"出价(元)",
 "materialName":"素材名称","materialId":"素材ID","productName":"产品名称","productId":"产品ID","shopName":"店铺",
 "remark":"备注","balance":"余额(元)","adComment":"广告备注","learningPhase":"学习期",
 "cost":"消费(元)","qfCost":"千川消费(元)","showCount":"展示量","clickCount":"点击量","pageClickCount":"行为数",
 "ctr":"点击率(%)","pageClickRate":"行为率(%)","cpc":"CPC(元)","cpm":"CPM(元)",
 "convertCount":"转化数","conversionCost":"转化成本(元)","conversionRate":"转化率(%)",
 "orderCount":"订单数","orderAmount":"订单金额(元)","orderCost":"订单成本(元)","orderRate":"订单率(%)",
 "orderRoi":"ROI","noBackOrderRoi":"不退款ROI","originOrderRoi":"自然ROI","inAppOrderRoi":"站内ROI",
 "originOrderCount":"自然订单数","originOrderAmount":"自然订单金额(元)","atv":"客单价(元)",
 "refundOrderCount":"退款订单数","refundOrderAmount":"退款订单金额(元)","refundOrderRate":"退款率(%)",
 "backOrderCount":"退货订单数","backOrderAmount":"退货金额(元)","orderPercent":"分成比例(%)",
 "validPlay":"有效播放","validPlayRate":"有效播放率(%)","validPlayCost":"有效播放成本(元)",
 "totalPlay":"总播放","playOver":"完播数","dyLike":"点赞","dyComment":"评论","dyShare":"分享",
 "inAppOrderGmv":"站内成交GMV(元)","inAppOrderNetCount":"站内净成交数","inAppOrderNetGmv":"站内净成交GMV(元)",
 "orderNo":"订单号","orderParentNo":"父订单号","goodsId":"商品ID","goodsInfo":"商品信息","goodsNum":"数量",
 "payMoney":"付款金额(元)","commissionAmount":"佣金(元)","commissionType":"佣金类型","goodsPrice":"商品单价(元)",
 "sellerStore":"店铺","orderStatus":"订单状态","refundStatus":"退款状态","convertStatus":"转化状态",
 "orderCreateTime":"下单时间","orderClickTime":"点击时间","orderPayTime":"付款时间","orderDoneTime":"完成时间",
 "orderSource":"订单来源","channelSite":"渠道","goodsRemark":"商品备注",
}
METRIC_ORDER = ["cost","qfCost","showCount","clickCount","pageClickCount","ctr","pageClickRate","cpc","cpm",
 "convertCount","conversionCost","conversionRate","orderCount","orderAmount","orderCost","orderRate",
 "orderRoi","noBackOrderRoi","atv","originOrderCount","originOrderAmount","originOrderRoi",
 "refundOrderCount","refundOrderAmount","refundOrderRate","backOrderCount","backOrderAmount",
 "inAppOrderGmv","inAppOrderNetCount","inAppOrderNetGmv","validPlay","validPlayRate","validPlayCost",
 "totalPlay","playOver","dyLike","dyComment","dyShare","balance","remark"]


def to_dt(v):
    try:
        n = int(v)
        if n > 1e12: n //= 1000
        if n > 1e9: return datetime.datetime.utcfromtimestamp(n + 8 * 3600).strftime("%Y-%m-%d %H:%M:%S")
    except Exception: pass
    return v


def fmt(k, v):
    if v is None: return ""
    if k in TIME_FIELDS: return to_dt(v)
    if k in MONEY or k in RATIO:
        try: return round(float(v) / 100, 2)
        except Exception: return v
    return v


def write_csv(fn, lead_keys, items, total_data=None):
    if not items:
        print(f"  (无数据，跳过 {fn})"); return 0
    present = set()
    for it in items: present.update(it.keys())
    cols = [k for k in lead_keys if k in present] + [k for k in METRIC_ORDER if k in present and k not in lead_keys]
    head = [FIELD_MAP.get(k, k) for k in cols]
    p = os.path.join(OUTDIR, fn)
    with open(p, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(head)
        if isinstance(total_data, dict) and total_data:
            w.writerow(["合计"] + [fmt(k, total_data.get(k)) for k in cols[1:]])
        for it in items:
            w.writerow([fmt(k, it.get(k)) for k in cols])
    print(f"  -> {p}  ({len(items)} 行)")
    return len(items)


UNION = "report/union/get"
TASKS = [
    ("1_账户维度.csv", UNION, {"adReportType":"ADVERTISER","startDate":START_DATE,"endDate":END_DATE,"orderDesc":2},
     ["advertiserName","advertiserId","advertiserOwnerName","advertiserStatus","remark"]),
    ("2_项目维度.csv", UNION, {"adReportType":"PROJECT","startDate":START_DATE,"endDate":END_DATE,"orderDesc":2},
     ["projectName","projectId","advertiserName","advertiserId","projectStatus","cpaBid"]),
    ("3_计划维度.csv", UNION, {"adReportType":"PROMOTION","startDate":START_DATE,"endDate":END_DATE,"orderDesc":2},
     ["adName","adId","projectId","advertiserName","adStatus","cpaBid"]),
    ("4_素材维度.csv", UNION, {"adReportType":"MATERIAL","startDate":START_DATE,"endDate":END_DATE,"orderDesc":2},
     ["materialName","materialId","advertiserName"]),
    ("7_产品维度.csv", UNION, {"adReportType":"PRODUCT","startDate":START_DATE,"endDate":END_DATE,"orderDesc":2},
     ["productName","productId","advertiserName"]),
]


def main():
    print(f"日期范围: {START_DATE} ~ {END_DATE}\n输出目录: {OUTDIR}\n")
    summary = []
    for fn, path, base, lead in TASKS:
        print(f"[{fn}]")
        items, total, td = fetch_all(path, base)
        summary.append((fn, write_csv(fn, lead, items, td)))
    for fn, path, lead in [("5_店铺维度PA.csv", "pa/shop/report", ["shopName","shopId"]),
                           ("6_商品维度PA.csv", "pa/item/report", ["itemName","itemId","goodsId"])]:
        print(f"[{fn}]")
        items, total, td = fetch_all(path, {"payStartDate":START_DATE,"payEndDate":END_DATE})
        summary.append((fn, write_csv(fn, lead, items, td)))
    print("[8_订单维度.csv]")
    items, total, td = fetch_all("report/order/get", {"startDate":START_DATE,"endDate":END_DATE})
    order_lead = ["orderNo","orderParentNo","orderCreateTime","orderPayTime","goodsInfo","goodsId","goodsNum",
                  "goodsPrice","payMoney","commissionAmount","adName","adId","sellerStore","advertiserName",
                  "advertiserId","orderStatus","refundStatus","materialId","remark"]
    summary.append(("8_订单维度.csv", write_csv("8_订单维度.csv", order_lead, items, td)))
    print("\n==== 汇总 ====")
    for fn, n in summary: print(f"  {fn}: {n}")


if __name__ == "__main__":
    main()
