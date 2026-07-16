# -*- coding: utf-8 -*-
"""逐笔电商订单抓取器：给定 (login, day) 返回归一化到统一订单字段的行列表。
统一字段按小飞机口径(见 ORDER_COLS)。B-G(类目/投放产品/电商平台/投放渠道/店铺/代理商)人工填，此处不爬。
时间字段统一存 'YYYY-MM-DD HH:MM:SS' 字符串(或 None)。金额统一存「元」。
数据源(已逆向)：
  小飞机 CID: cid/order/jdCidList(京东联盟PRO) + cid/order/lltProList(流量通PRO)
  沸点: api.fifay.cn/fifay-ad/report/order/get
  微橙: taotik.douyongtuan.com/business/TaokeChannelOrder/findsDev
  麦斯: preapi.maxengine.cn/admin/uds/order/lists
"""
import json, datetime, urllib.request, urllib.parse
from fetchers import UA, _num, _ts

# 统一订单字段（对应飞书表 A + H~X；B-G 人工列另存，默认空）
ORDER_COLS = [
    "platform", "login_account", "order_type",          # 来源平台 / 我方登录 / 订单类型(小飞机分两种)
    "ad_account_name", "ad_account_id", "ad_name", "material_name",  # I~L
    "main_order_no", "order_no", "product_id",            # M,N (order_no 为主键一部分), N后新增商品ID
    "product_info", "product_price", "pay_amount",        # O,P,Q
    "order_status", "callback_status",                    # R,S
    "click_time", "pay_time", "refund_time",              # T,U,V
    "attribution", "ad_position",                         # W,X
]

def _dt(v):
    """归一化时间：接受 'YYYY-MM-DD HH:MM:SS' 字符串或 unix 秒；无效返回 None。"""
    if v in (None, "", 0, "0", "-", "--", "0000-00-00 00:00:00"):
        return None
    if isinstance(v, (int, float)) or (isinstance(v, str) and v.isdigit()):
        try:
            t = int(v)
            if t <= 0:
                return None
            return datetime.datetime.utcfromtimestamp(t + 8 * 3600).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return None
    return str(v)

def _row(**kw):
    r = {c: None for c in ORDER_COLS}
    r.update(kw)
    return r

# ============================ 小飞机 CID 订单 ============================
_XFJ_STATUS = {"0": "无效归因", "1": "待付款", "2": "已付款", "3": "已退款",
               "4": "拆单", "5": "已完成", "6": "已付定金"}   # validCode -> 中文；未知保留原值
# 归因触点 tracePoint -> 中文（与小飞机后台一致）：3=点击 2=有效触点 1=曝光；未知保留原值
_XFJ_TRACE = {"1": "曝光归因", "2": "有效触点归因", "3": "点击归因"}
XFJ_ORDER_TYPES = {
    "京东联盟PRO": {"url": "/v1/cid/order/jdCidList", "_type": "CID_JDCID_ORDER_REPORT", "level": 133, "Type": 133,
                 "extra": {"TracePoints": [], "AdxIds": []},
                 "cols": ["OrderUid", "OrderId", "OrderParentId", "AccountExtId", "AccountName", "CampaignName",
                          "ClickAdxMid3Name", "GoodInfos", "Order.skuName", "Order.skuId", "Order.price", "Order.cosPrice",
                          "OrderTime", "PayTime", "RefundTime", "ClickTime", "ClickAdxCSiteName", "TracePoint"]},
    "流量通PRO": {"url": "/v1/cid/order/lltProList", "_type": "CID_LLTPRO_ORDER_REPORT", "level": 129, "Type": 120,
                "extra": {"AttributionTypes": []},
                "cols": ["SubOrderId", "SellerNick", "AdxAccountId", "AccountName", "AdxCampaignId", "CampaignName",
                         "ClickAdxMid3Name", "GoodInfos", "Order.item_id", "Payment", "Status", "OrderTime", "PayTime", "PayOrderType"]},
}

def _xfj_hdr(a, op):
    return {"authorization": "Bearer " + a["cid_token"], "td-op-uid": str(op),
            "content-type": "application/json;charset=UTF-8", "accept-encoding": "identity", "user-agent": UA}

def fetch_xfj_orders(login, day):
    a = login["auth"]
    if not a.get("cid_token"):
        raise RuntimeError("小飞机CID token missing login(未登录CID)")
    # 一个小飞机登录可挂多个项目(op_uid)；订单也须逐项目抓，否则漏掉其它项目的订单
    op_uids = [str(x) for x in (a.get("op_uids") or [a.get("cid_op_uid") or a.get("op_uid")])]
    out = []
    for op in op_uids:
        for otype, cfg in XFJ_ORDER_TYPES.items():
            hdr = _xfj_hdr(a, op)
            page = 1
            while True:
                data = {"order": "PayTime|-1", "level": cfg["level"], "Type": cfg["Type"], "_type": cfg["_type"],
                        "PayTimeRange": {"begindate": _ts(day), "enddate": _ts(day, True)},
                        "page": page, "limit": 200, "metrics": [], "SelectedColumns": cfg["cols"]}
                data.update(cfg["extra"])
                body = json.dumps({"mid": page, "source": "td.web.vue", "url": cfg["url"], "data": data}).encode()
                req = urllib.request.Request("https://cid.smallfighter.com" + cfg["url"], data=body, headers=hdr, method="POST")
                resp = json.loads(urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace"))
                if resp.get("code") != 0:
                    raise RuntimeError(f"小飞机CID订单 token expired login code={resp.get('code')} msg={resp.get('msg') or resp.get('message')}")
                d = resp.get("data") or {}
                items = d.get("items") or []
                for it in items:
                    o = it.get("Order") or {}
                    # 点击时间在嵌套 Click/Impression 子对象里
                    ck = (it.get("Click") or {}).get("clickTime") or (it.get("Impression") or {}).get("clickTime") or it.get("ClickTime")
                    if otype == "流量通PRO":     # 淘宝订单：金额在 Order 子对象，单位分÷100
                        ap = _num(o.get("actual_pay_fee")); pay = ap / 100 if ap is not None else None
                        pf = _num(o.get("pay_fee")); price = pf / 100 if pf is not None else None
                        product = o.get("pay_item_name") or o.get("item_name")
                        status = _XFJ_STATUS.get(str(o.get("order_status") or it.get("Status") or ""), str(o.get("order_status") or it.get("Status") or ""))
                        pid = str(o.get("item_id") or o.get("pay_item_id") or "") or None   # 淘宝商品id
                    else:                        # 京东联盟PRO：金额单位元
                        pay = _num(o.get("cosPrice")); price = _num(o.get("price"))
                        product = o.get("skuName") or it.get("GoodInfos")
                        vc = str(it.get("Status") or o.get("validCode") or "")
                        status = _XFJ_STATUS.get(vc, vc)   # validCode 2=已付款
                        pid = str(o.get("skuId") or it.get("OrderGoodExtId") or "") or None  # 京东商品SKU id
                    # 回传状态：有成功回传记录=回传成功；被扣量/无记录=未回传
                    conv = it.get("ConvHistory") or []
                    if any(isinstance(cc, dict) and cc.get("ResponseSuc") for cc in conv):
                        callback = "回传成功"
                    elif it.get("AdConvAbortN") or it.get("AdConvAbortCause"):
                        callback = "未回传(扣量)"
                    else:
                        callback = "未回传"
                    out.append(_row(
                        platform="小飞机", login_account=login["tag"], order_type=otype,
                        ad_account_name=it.get("AccountName"), ad_account_id=str(it.get("AccountExtId") or it.get("AdxAccountId") or ""),
                        ad_name=it.get("CampaignName"), material_name=it.get("ClickAdxMid3Name") or it.get("CreativeName"),
                        main_order_no=str(it.get("OrderParentId") or o.get("parentId") or "") or None,
                        order_no=str(it.get("OrderId") or it.get("SubOrderId") or o.get("orderId") or ""),
                        product_id=pid,
                        product_info=product, product_price=price, pay_amount=pay,
                        order_status=status, callback_status=callback,
                        click_time=_dt(ck), pay_time=_dt(it.get("PayTime") or o.get("payTime")),
                        refund_time=_dt(it.get("RefundTime")),
                        attribution=(lambda tp: _XFJ_TRACE.get(tp, tp) or None)(str(it.get("TracePoint") or it.get("AttrType") or o.get("tracePoint") or "")),
                        ad_position=it.get("ClickAdxCSiteName")))
                if len(items) < 200 or not items:
                    break
                page += 1
    return out

# ============================ 沸点 电商订单 ============================
# 归因触点 tracePoint 字典：3=联盟点击, 2=有效播放+点击；未知码保留原值
_FD_TRACE = {"3": "联盟点击", "2": "有效播放+点击"}
def _fd_trace(v):
    return None if v is None else _FD_TRACE.get(str(v), str(v))
# 回传状态：convertStatus 直接返回中文文案(实测有 "未回传"，为空则代表已回传——
# 已用样本验证 null→已回传、字符串"未回传"→未回传)。原样透传，仅空值兜底为已回传。
def _fd_callback(v):
    return "已回传" if v in (None, "", "-", "--") else str(v)

def fetch_fd_orders(login, day):
    a = login["auth"]
    hdr = {"accept": "application/json", "content-type": "application/json", "did": a["did"], "token": a["token"],
           "version": "1.0.2", "platform": "h5", "origin": "https://admin.fifay.cn", "referer": "https://admin.fifay.cn/",
           "accept-encoding": "identity", "user-agent": UA}
    ds = day.isoformat(); out = []; page = 1
    while True:
        b = json.dumps({"current": page, "pageSize": 200, "startDate": ds, "endDate": ds}).encode()
        req = urllib.request.Request("https://api.fifay.cn/fifay-ad/report/order/get", data=b, headers=hdr, method="POST")
        resp = json.loads(urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace"))
        if resp.get("code") != 200:
            raise RuntimeError(f"沸点订单 token expired login code={resp.get('code')} msg={resp.get('message')}")
        d = resp.get("data") or {}; lst = d.get("list") or []
        for it in lst:
            out.append(_row(
                platform="沸点", login_account=login["tag"], order_type="电商订单",
                ad_account_name=it.get("advertiserName"), ad_account_id=str(it.get("advertiserId") or ""),
                ad_name=it.get("adName"), material_name=str(it.get("materialId") or "") or None,
                main_order_no=str(it.get("orderParentNo") or ""), order_no=str(it.get("orderNo") or ""),
                product_info=it.get("goodsInfo"),
                product_price=(_num(it.get("goodsPrice")) or 0) / 100 if it.get("goodsPrice") is not None else None,
                pay_amount=(_num(it.get("payMoney")) or 0) / 100 if it.get("payMoney") is not None else None,
                order_status=it.get("orderStatus"), callback_status=_fd_callback(it.get("convertStatus")),
                click_time=_dt(it.get("orderClickTime")), pay_time=_dt(it.get("orderPayTime")),
                refund_time=_dt(it.get("orderRefundTime")),
                attribution=_fd_trace(it.get("tracePoint")), ad_position=it.get("channelSite")))
        if d.get("endPage") or len(lst) < 200 or not lst:
            break
        page += 1
    return out

# ============================ 微橙 淘客渠道订单 ============================
# 微橙订单状态看 tk_status（12=订单付款 / 13=订单失效）；响应里的 order_status 字段恒为 1，不可用
_WC_ORDER_STATUS = {"12": "订单付款", "13": "订单失效"}
# 微橙回传状态看 is_event_compute（1=未回传 / 2=已回传 / 3=无需回传 / 4=回传失败）；convert_status 恒为 1，不可用
_WC_CALLBACK = {"1": "未回传", "2": "已回传", "3": "无需回传", "4": "回传失败"}
def fetch_wc_orders(login, day):
    a = login["auth"]
    hdr = {"content-type": "application/x-www-form-urlencoded", "accept": "application/json",
           "origin": "https://business.douyongtuan.com", "referer": "https://business.douyongtuan.com/",
           "accept-encoding": "identity", "user-agent": UA}
    ds = day.isoformat(); out = []; page = 1
    while True:
        data = {"session_id": a["session_id"], "customer_id": a["customer_id"], "page": page,
                "start_time": ds + " 00:00:00", "end_time": ds + " 23:59:59"}
        req = urllib.request.Request("https://taotik.douyongtuan.com/business/TaokeChannelOrder/findsDev",
            data=urllib.parse.urlencode(data).encode(), headers=hdr, method="POST")
        d = json.loads(urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")).get("data") or {}
        lst = d.get("data") or []
        for it in lst:
            sa = it.get("secondAccount") or {}; pd = it.get("planData") or {}; md = it.get("materialData") or {}
            out.append(_row(
                platform="微橙", login_account=login["tag"], order_type="淘客渠道订单",
                ad_account_name=sa.get("name") or sa.get("advertiser_name"),
                ad_account_id=str(it.get("advertiserId") or it.get("second_account_id") or ""),
                ad_name=pd.get("promotion_name") or pd.get("name"),
                material_name=md.get("material_name") or str(it.get("material_id") or "") or None,
                main_order_no=str(it.get("trade_parent_id") or ""), order_no=str(it.get("trade_id") or ""),
                product_id=str(it.get("item_id") or "") or None,
                product_info=it.get("item_title"), product_price=_num(it.get("item_price")),
                pay_amount=_num(it.get("alipay_total_price")),
                order_status=_WC_ORDER_STATUS.get(str(it.get("tk_status") or ""), str(it.get("tk_status") or "")) or None,
                callback_status=_WC_CALLBACK.get(str(it.get("is_event_compute") or ""), str(it.get("is_event_compute") or "")) or None,
                click_time=_dt(it.get("click_time")), pay_time=_dt(it.get("tb_paid_time")),
                refund_time=_dt(it.get("refund_time")),
                attribution=None, ad_position=it.get("csite_name")))
        if page >= (d.get("last_page") or 1) or not lst:
            break
        page += 1
    return out

# ============================ 麦斯 聚光平台 淘宝-流量通Pro 订单 ============================
MS_ORDER_FIELDS = ["order_id", "sub_order_id", "advertiser_id", "advertiser_name", "campaign_name", "unit_name",
    "creativity_name", "material_id", "pay_item_id", "pay_item_name", "item_name", "order_status_title", "actual_pay_fee",
    "conv_status_title", "click_time", "order_pay_time", "order_refund_time", "attribution_type", "order_create_time"]

def fetch_ms_orders(login, day):
    a = login["auth"]
    hdr = {"x-token": a["x_token"], "signip": a.get("signip", ""), "request-source": "max", "accept-encoding": "identity",
           "content-type": "application/json;charset=UTF-8", "accept": "application/json, text/plain, */*", "user-agent": UA}
    ds = day.isoformat(); out = []; page = 1
    while True:
        payload = {"custom_fields": MS_ORDER_FIELDS, "media_type": "11", "page": page, "rows": 200,
                   "is_ad_order": 1, "prod_type": 2, "createTimes": [ds, ds],
                   "create_start_time": ds, "create_end_time": ds,
                   "advertiser_ids": [], "query_type": "order_id", "keyword": ""}   # 媒体11=小红书聚光, 按下单时间过滤
        req = urllib.request.Request("https://preapi.maxengine.cn/admin/uds/order/lists",
            data=json.dumps(payload).encode(), headers=hdr, method="POST")
        d = (json.loads(urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")).get("data") or {})
        lst = d.get("data") or d.get("list") or []
        for it in lst:
            out.append(_row(
                platform="麦斯", login_account=login["tag"], order_type="淘宝-流量通Pro",
                ad_account_name=it.get("advertiser_name"), ad_account_id=str(it.get("advertiser_id") or ""),
                ad_name=it.get("unit_name") or it.get("campaign_name"), material_name=it.get("creativity_name"),
                main_order_no=str(it.get("order_id") or ""), order_no=str(it.get("sub_order_id") or it.get("order_id") or ""),
                product_id=str(it.get("pay_item_id") or "") or None,   # 下单商品id
                product_info=it.get("pay_item_name") or it.get("item_name"), product_price=None,
                pay_amount=_num(it.get("actual_pay_fee")),
                order_status=it.get("order_status_title"), callback_status=it.get("conv_status_title"),
                click_time=_dt(it.get("click_time")), pay_time=_dt(it.get("order_pay_time")),
                refund_time=_dt(it.get("order_refund_time")),
                attribution=str(it.get("attribution_type") or "") or None, ad_position=None))
        if len(lst) < 200 or not lst:
            break
        page += 1
    return out

ORDER_FETCH = {"小飞机": fetch_xfj_orders, "沸点": fetch_fd_orders, "微橙": fetch_wc_orders, "麦斯": fetch_ms_orders}
ORDER_PLATFORMS = list(ORDER_FETCH)

def fetch_orders(login, day):
    fn = ORDER_FETCH.get(login["platform"])
    if not fn:
        return []
    rows = fn(login, day)
    ds = day.isoformat()
    for r in rows:
        r["order_date"] = ds
    return [r for r in rows if r.get("order_no")]

# ============================ 入库 ============================
# 人工列(B-G)：抓取不覆盖，仅人工维护
MANUAL_COLS = ["category", "product", "ecom_platform", "channel", "shop", "agency"]
CRAWL_COLS = [c for c in ORDER_COLS if c not in ("platform", "order_type")] + ["order_date"]
ALL_COLS = ORDER_COLS + ["order_date"] + MANUAL_COLS
_OKEY = ("platform", "order_type", "order_no")

def ensure_orders_table(conn):
    with conn.cursor() as cur:
        cur.execute("""CREATE TABLE IF NOT EXISTS orders (
            platform text, login_account text, order_type text, order_date date,
            ad_account_name text, ad_account_id text, ad_name text, material_name text,
            main_order_no text, order_no text, product_id text,
            product_info text, product_price numeric, pay_amount numeric,
            order_status text, callback_status text,
            click_time timestamp, pay_time timestamp, refund_time timestamp,
            attribution text, ad_position text,
            category text, product text, ecom_platform text, channel text, shop text, agency text,
            fetched_at timestamptz DEFAULT now(),
            PRIMARY KEY (platform, order_type, order_no))""")
        cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS product_id text")  # 存量表补列
        cur.execute("CREATE INDEX IF NOT EXISTS idx_orders_platform_date ON orders(platform, order_date)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_orders_login ON orders(login_account)")
    conn.commit()

def crawl_orders_window(window_days=15, platform=None):
    """订单滚动抓取：重抓最近 window_days 天并 UPSERT。供定时任务调用。
    token 失效时通过 crawl.refresh_login 子进程自动重登(与广告数据共用同一套登录凭证)。"""
    import fetchers as F, db as DB, crawl
    logins = F.load_logins()   # enabled 且非历史
    if platform: logins = [l for l in logins if l["platform"] == platform]
    logins = [l for l in logins if l["platform"] in ORDER_FETCH]
    end = datetime.date.today(); start = end - datetime.timedelta(days=window_days - 1)
    days = [start + datetime.timedelta(days=i) for i in range((end - start).days + 1)]
    tag2id = {l["tag"]: l.get("id") for l in logins}
    conn = DB.connect(); ensure_orders_table(conn)
    total = 0; errs = []; bad = set()
    for lg in logins:
        p = lg["platform"]; tag = lg["tag"]
        if not lg.get("auth"):
            continue
        for day in days:
            try:
                rows = fetch_orders(lg, day)
                upsert_orders(conn, rows)
                DB.mark_progress(conn, p, tag, "订单", day, len(rows))
                total += len(rows)
            except Exception as e:
                errs.append(f"{p}/{tag}/{day}: {repr(e)[:50]}")
                if crawl._auth_err(e): bad.add(tag)
                break   # 该登录本天失败,跳过剩余天
    conn.close()
    relogin = []
    for tag in bad:                       # 失效登录自动重登,下一轮恢复
        aid = tag2id.get(tag)
        if aid:
            code, _ = crawl.refresh_login(aid); relogin.append(tag)
    return {"orders": total, "bad_logins": list(bad), "errors": len(errs), "relogin": relogin}

def upsert_orders(conn, rows):
    """写订单：按 (platform,order_type,order_no) UPSERT。冲突只更新爬取列，保留人工列(B-G)。"""
    if not rows:
        return 0
    import psycopg2.extras
    dedup = {}
    for r in rows:
        dedup[tuple(r.get(k) for k in _OKEY)] = r
    rows = list(dedup.values())
    cols = ORDER_COLS + ["order_date"]     # 只写爬取列(含 order_date)；人工列走默认 NULL
    vals = [[r.get(c) for c in cols] for r in rows]
    setclause = ",".join(f"{c}=EXCLUDED.{c}" for c in cols if c not in _OKEY) + ",fetched_at=now()"
    sql = f"INSERT INTO orders ({','.join(cols)}) VALUES %s ON CONFLICT (platform,order_type,order_no) DO UPDATE SET {setclause}"
    try:
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(cur, sql, vals, page_size=500)
        conn.commit()
    except Exception:
        conn.rollback(); raise
    return len(rows)
