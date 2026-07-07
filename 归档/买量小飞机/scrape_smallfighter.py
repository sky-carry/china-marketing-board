# -*- coding: utf-8 -*-
"""
买量小飞机 (td.smallfighter.com) 项目报表抓取脚本
-------------------------------------------------
功能：调用平台底层接口，把「推广账号 / 广告组 / 广告 / 创意 / 抖音 / 商品」
      各标签页的报表数据全量翻页抓取，分别导出为 CSV（UTF-8-BOM，Excel 直接打开）。

每次使用前只需更新下面【配置区】的两项：
  1) TOKEN  —— 登录令牌（会过期，约几天）
  2) td.sid —— 会话 cookie（在 COOKIE 里）
  以及要抓取的日期范围 START_DATE / END_DATE。

如何获取最新 TOKEN 和 td.sid：
  浏览器登录平台 → F12 → Network(网络) → 点任意标签刷新 → 找到 v1/account/list 请求
  → 在 Request Headers 里复制 authorization 的 Bearer 后面那串 = TOKEN
  → 复制 cookie 里的 td.sid=... 的值 = SID
"""
import json, csv, os, time, datetime, urllib.request

# ============================ 配置区（每次更新这里）============================
TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6IldTaUFma2o1LTZ5b25QTDRRVUZEdWFxak43eHRzVVhrIiwiaWF0IjoxNzgyNjk5MTA4LCJleHAiOjE3ODMzMDM5MDh9.7iCakK3qRovXXB6UTByNI4mKcdXirB_xKZmUuqt7gK0"
SID   = "s%3AWSiAfkj5-6yonPL4QUFDuaqjN7xtsUXk.7vJiCsbpOYiS3IMe1IwHdAHvYBeuAwC%2BT9K0bunJFBQ"
DEVICE_ID = "d8937f3a38991173b73a84129da5e73d"
OP_UID    = "82406"          # td-op-uid，账号标识，一般不变

START_DATE = "2026-06-01"    # 开始日期（含），按北京时间
END_DATE   = "2026-06-28"    # 结束日期（含）

OUTDIR = os.path.dirname(os.path.abspath(__file__))   # 默认输出到脚本所在目录
PAGE_LIMIT = 200             # 每页条数
# ============================================================================

# 报表指标（key 顺序对应下方 METRIC_HEAD）
METRICS = ["cost", "impressions", "adx_metric_0", "click_rate", "cpm", "cpc",
           "cid_trans_real_payment_amount", "cid_trans_real_order_num"]
METRIC_HEAD = ["总消费(元)", "展示量", "点击量", "点击率(%)", "CPM(元)", "CPC(元)",
               "真实付款金额(元)", "真实订单数"]


def date_to_ts(date_str, end_of_day=False):
    """北京时间(UTC+8)的某天 0 点 / 23:59:59 转 unix 秒"""
    d = datetime.datetime.strptime(date_str, "%Y-%m-%d")
    midnight_utc = (datetime.datetime(d.year, d.month, d.day) - datetime.datetime(1970, 1, 1)).total_seconds()
    secs = int(midnight_utc) - 8 * 3600          # 北京 0 点 = UTC 前一天 16 点
    return secs + (24 * 3600 - 1 if end_of_day else 0)


BEGIN = date_to_ts(START_DATE)
END   = date_to_ts(END_DATE, end_of_day=True)

COOKIE = (f"lang=zhCN; deviceid={DEVICE_ID}; td.token={TOKEN}; td-op-uid={OP_UID}; "
          f"td.sid={SID}; dateCountType=1; begindate={BEGIN}; enddate={END}")
HEADERS = {
    "accept": "application/json, text/javascript, */*; q=0.01",
    "authorization": "Bearer " + TOKEN,
    "content-type": "application/json; charset=UTF-8",
    "accept-encoding": "identity",
    "cookie": COOKIE,
    "origin": "https://td.smallfighter.com",
    "referer": "https://td.smallfighter.com/",
    "td-op-uid": OP_UID, "td-product": "td", "x-requested-with": "XMLHttpRequest",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
}


def call(uri, extra, page, limit):
    data = {"begindate": BEGIN, "enddate": END, "page": page, "limit": limit,
            "metrics": METRICS, "order": "cost|-1", "WithLevel": True,
            "haveDateCompare": False, "WithCidConvertCfg": True,
            "WithClueConvertCfg": False, "PeriodType": 3}
    data.update(extra)
    payload = {"type": "message", "mid": page, "req": 1, "uri": uri, "__uid_4_track": int(OP_UID),
               "td-op-uid": OP_UID, "source": "td.web", "version": "1782784101",
               "hash": "#serving", "data": data}
    req = urllib.request.Request("https://td.smallfighter.com/" + uri,
                                 data=json.dumps(payload).encode("utf-8"),
                                 headers=HEADERS, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))["data"]


def fetch_all(uri, extra):
    page, items, total = 1, [], None
    while True:
        d = call(uri, extra, page, PAGE_LIMIT)
        its = d.get("items", []) or []
        items += its
        total = d.get("total", 0)
        print(f"    {uri}  page {page}: +{len(its)}  ({len(items)}/{total})")
        if len(items) >= total or not its:
            break
        page += 1
        time.sleep(0.2)
    return items, total


# ---- 数值格式化（已验证缩放规则）----
def money(v):                       # 金额：原值 / 1,000,000
    try: return round(float(v) / 1_000_000, 2)
    except Exception: return ""
def money3(v):                      # 金额保留 3 位（真实付款金额）
    try: return round(float(v) / 1_000_000, 3)
    except Exception: return ""
def rate(v):                        # 点击率：原值 / 100 = 百分数
    try: return round(float(v) / 100, 3)
    except Exception: return ""
def num(v):
    try: return int(v)
    except Exception:
        try: return float(v)
        except Exception: return "" if v is None else v


def metric_cols(it):
    return [money(it.get("cost")), num(it.get("impressions")), num(it.get("adx_metric_0")),
            rate(it.get("click_rate")), money(it.get("cpm")), money(it.get("cpc")),
            money3(it.get("cid_trans_real_payment_amount")), num(it.get("cid_trans_real_order_num"))]


def write_csv(fn, header, rows):
    p = os.path.join(OUTDIR, fn)
    with open(p, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"  -> {p}  ({len(rows)} 行)")
    return len(rows)


def g(d, *path, default=""):
    cur = d
    for k in path:
        cur = cur.get(k) if isinstance(cur, dict) else None
    return default if cur is None else cur


# ============================ 各标签定义 ============================
def rows_account(items):
    out = []
    for it in items:
        feed = f'{g(it,"QuotaInfo","FeedUsedQuota",default=0)}/{g(it,"QuotaInfo","FeedTotalQuota",default=0)}'
        srch = f'{g(it,"QuotaInfo","SearchUsedQuota",default=0)}/{g(it,"QuotaInfo","SearchTotalQuota",default=0)}'
        out.append([it.get("Name"), it.get("account_id") or it.get("_id"), it.get("AdxName"),
                    it.get("StatusText"), feed, srch, it.get("Budget")] + metric_cols(it))
    return out

def rows_plan(items):
    return [[it.get("Name"), it.get("plan_id") or it.get("_id"), it.get("AccountName"),
             it.get("AccountId"), it.get("AdxName"), it.get("StatusText")] + metric_cols(it) for it in items]

def rows_campaign(items):
    return [[it.get("Name"), it.get("campaign_id") or it.get("_id"), it.get("PlanName"),
             it.get("AccountName"), it.get("AccountId"), it.get("AdxName"), it.get("StatusText")] + metric_cols(it) for it in items]

def rows_generic(items):            # 创意/抖音/商品：通用列（这些标签某些时间段可能无数据）
    return [[it.get("Name") or it.get("Title"), it.get("_id"),
             it.get("AccountName"), it.get("AdxName"), it.get("StatusText")] + metric_cols(it) for it in items]

TABS = [
    {"file": "01_推广账号.csv", "name": "推广账号", "uri": "v1/account/list",
     "extra": {"_type": "ACCOUNT_REPORT", "WithFavorite": True, "needAdveringProp": False},
     "header": ["账号名称", "账号ID", "所属渠道", "状态", "信息流计划数", "搜索计划数", "预算(元)"] + METRIC_HEAD,
     "rows": rows_account},
    {"file": "02_广告组.csv", "name": "广告组", "uri": "v1/plan/list",
     "extra": {"_type": "PLAN_REPORT", "OnlySubmitSuccess": False, "AccountId": "", "PlanId": "", "CampaignId": "", "AdxSubIds": []},
     "header": ["广告组名称", "广告组ID", "所属账号", "账号ID", "所属渠道", "状态"] + METRIC_HEAD,
     "rows": rows_plan},
    {"file": "03_广告.csv", "name": "广告", "uri": "v1/campaign/list",
     "extra": {"_type": "CAMPAIGN_REPORT", "OnlySubmitSuccess": False, "WithCidLevel": False,
               "AccountId": "", "PlanId": "", "CampaignId": "", "AdxSubIds": [], "AdxSubId": ""},
     "header": ["广告名称", "广告ID", "所属广告组", "所属账号", "账号ID", "所属渠道", "状态"] + METRIC_HEAD,
     "rows": rows_campaign},
    {"file": "04_创意.csv", "name": "创意", "uri": "v1/creative/list",
     "extra": {"_type": "CREATIVE_REPORT", "WithMaterial": True, "OnlySubmitSuccess": False,
               "AccountId": "", "PlanId": "", "CampaignId": "", "AdxSubIds": []},
     "header": ["名称", "ID", "所属账号", "所属渠道", "状态"] + METRIC_HEAD, "rows": rows_generic},
    {"file": "05_抖音.csv", "name": "抖音", "uri": "v1/aweme/list",
     "extra": {"_type": "AWEME_ACCOUNT_REPORT", "AccountId": "", "PlanId": "", "CampaignId": ""},
     "header": ["名称", "ID", "所属账号", "所属渠道", "状态"] + METRIC_HEAD, "rows": rows_generic},
    {"file": "06_商品.csv", "name": "商品", "uri": "v1/goods/list",
     "extra": {"_type": "PRODUCT_REPORT", "AccountId": "", "PlanId": "", "CampaignId": ""},
     "header": ["名称", "ID", "所属账号", "所属渠道", "状态"] + METRIC_HEAD, "rows": rows_generic},
]


def main():
    print(f"日期范围: {START_DATE} ~ {END_DATE}  (begindate={BEGIN}, enddate={END})")
    print(f"输出目录: {OUTDIR}\n")
    summary = []
    for t in TABS:
        print(f"[{t['name']}] {t['uri']}")
        try:
            items, total = fetch_all(t["uri"], t["extra"])
        except Exception as e:
            print(f"  !! 抓取失败: {e}")
            summary.append((t["name"], "失败", str(e)[:60]))
            continue
        if not items:
            print(f"  (该时间段无数据，跳过)")
            summary.append((t["name"], 0, "无数据"))
            continue
        n = write_csv(t["file"], t["header"], t["rows"](items))
        summary.append((t["name"], n, t["file"]))
    print("\n==== 汇总 ====")
    for name, n, note in summary:
        print(f"  {name}: {n}  {note}")


if __name__ == "__main__":
    main()
