# -*- coding: utf-8 -*-
"""四平台各维度抓取器：给定 (login, level, date) 返回归一化到统一指标的行列表。
统一指标字段见 DBCOLS。只返回当天有消耗(cost>0)的行。"""
import json, os, time, datetime, urllib.request, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"

DBCOLS = ["platform","login_account","level","date","entity_id","entity_name","account_id","account_name",
 "parent_id","parent_name","channel","cost","impressions","clicks","ctr","cpm","cpc","conversions",
 "conversion_cost","orders","pay_amount","roi","real_pay_amount","real_orders","real_roi","refund_rate",
 # 直投归因（小飞机=直推 / 沸点=直接 / 微橙=单品 / 麦斯=主投品）：下单(gross) 与 成交(net) 两组
 "direct_orders","direct_pay_amount","direct_roi","direct_real_orders","direct_real_pay_amount","direct_real_roi"]

def _num(v):
    try: return float(str(v).replace(",","")) if v is not None and v!="" else None
    except: return None
def _i(v):
    n=_num(v); return int(n) if n is not None else None
def _r(v,nd=2):
    n=_num(v); return round(n,nd) if n is not None else None
def _div(a,b):
    a,b=_num(a),_num(b); return round(a/b,4) if (a is not None and b) else None

# ============================ 登录注册表 ============================
def _ms_token():
    try: return json.load(open(os.path.join(HERE,"ms_token.json")))
    except: return {"t":"","s":""}

DSN = "postgresql://postgres:postgres@localhost:5432/ad_data"
def load_logins(enabled_only=True):
    """从 DB accounts 表读取登录；失败则回退 creds.json。"""
    try:
        import psycopg2
        conn=psycopg2.connect(DSN); cur=conn.cursor()
        q="SELECT platform,tag,auth,id FROM accounts"+(" WHERE enabled" if enabled_only else "")+" ORDER BY platform,tag"
        cur.execute(q)
        rows=[{"platform":r[0],"tag":r[1],"auth":dict(r[2]),"id":r[3]} for r in cur.fetchall()]
        conn.close()
        if rows: return rows
    except Exception:
        pass
    ms=_ms_token()
    reg=json.load(open(os.path.join(HERE,"creds.json"),encoding="utf-8"))
    for lg in reg:
        if lg["platform"]=="麦斯" and lg["auth"].get("_from_file"):
            lg["auth"]["x_token"]=ms.get("t",""); lg["auth"]["signip"]=ms.get("s","")
    return reg

# ============================ 小飞机 ============================
XFJ_MET=['impressions','adx_metric_0','click_rate','cpm','cpc','adx_metric_7','convert_cost','cost',
 'cid_trans_order_num','cid_trans_payment_amount','cid_trans_real_payment_amount','cid_trans_real_order_num',
 'adx_metric_323','adx_metric_326','cid_trans_direct_real_order_num','cid_trans_direct_real_payment_amount',
 'cid_trans_direct_roi','cid_trans_direct_real_roi','cid_refund_rate']
XFJ_LEVELS={
 "推广账号":{"uri":"v1/account/list","_type":"ACCOUNT_REPORT","extra":{"WithFavorite":True,"needAdveringProp":False},
   "id":["ExternalId","account_id","_id"],"name":["Name"],"acc_id":["ExternalId","account_id","_id"],"acc_name":["Name"],"par_id":[],"par_name":[],"ext3":["ExternalId"]},
 "广告组":{"uri":"v1/plan/list","_type":"PLAN_REPORT","extra":{"OnlySubmitSuccess":False,"AccountId":"","PlanId":"","CampaignId":"","AdxSubIds":[]},
   "id":["plan_id","_id"],"name":["Name"],"acc_id":["AccountExternalId","AccountId"],"acc_name":["AccountName"],"par_id":["AccountExternalId","AccountId"],"par_name":["AccountName"],"ext3":["AccountExternalId","ExternalId"]},
 "广告":{"uri":"v1/campaign/list","_type":"CAMPAIGN_REPORT","extra":{"OnlySubmitSuccess":False,"WithCidLevel":False,"AccountId":"","PlanId":"","CampaignId":"","AdxSubIds":[],"AdxSubId":""},
   "id":["campaign_id","_id"],"name":["Name"],"acc_id":["AccountExternalId","AccountId"],"acc_name":["AccountName"],"par_id":["PlanId"],"par_name":["PlanName"],"ext3":["ExternalId"]},
 "创意":{"uri":"v1/creative/list","_type":"CREATIVE_REPORT","extra":{"WithMaterial":True,"OnlySubmitSuccess":False,"AccountId":"","PlanId":"","CampaignId":"","AdxSubIds":[]},
   "id":["creative_id","_id"],"name":["Name","Title","title"],"acc_id":["AccountExternalId","AccountId"],"acc_name":["AccountName"],"par_id":["campaign_id","CampaignId"],"par_name":["CampaignName"],"ext3":["ExternalId"]},
}
def _ts(day,end=False):
    mid=(datetime.datetime(day.year,day.month,day.day)-datetime.datetime(1970,1,1)).total_seconds()
    return int(mid)-8*3600+(24*3600-1 if end else 0)
def _first(it,keys):
    for k in keys:
        v=it.get(k)
        if v not in (None,"",0): return v
    for k in keys:
        if k in it: return it.get(k)
    return None
def fetch_xfj(login,level,day):
    a=login["auth"]; cfg=XFJ_LEVELS[level]; M=1e6
    # 一个小飞机登录可挂多个「项目」，op_uid 即项目 ID；op_uids 有值则逐项目抓，否则退回单个 op_uid
    op_uids=[str(x) for x in (a.get("op_uids") or [a["op_uid"]])]
    items=[]
    for op_uid in op_uids:
        cookie=f'lang=zhCN; td.token={a["token"]}; td-op-uid={op_uid}; td.sid={a["sid"]}'
        hdr={'authorization':'Bearer '+a["token"],'content-type':'application/json; charset=UTF-8','cookie':cookie,
             'td-op-uid':op_uid,'td-product':'td','x-requested-with':'XMLHttpRequest','accept-encoding':'identity','user-agent':UA}
        got=[]; page=1                                  # got: 本项目累计；每个 op_uid 独立翻页
        while True:
            data={'begindate':_ts(day),'enddate':_ts(day,True),'page':page,'limit':200,'metrics':XFJ_MET,
                  'order':'cost|-1','WithLevel':True,'WithCidConvertCfg':True,'_type':cfg["_type"]}
            data.update(cfg["extra"])
            body=json.dumps({'type':'message','mid':page,'req':1,'uri':cfg["uri"],'__uid_4_track':int(op_uid),
                  'td-op-uid':op_uid,'source':'td.web','version':'1782784101','hash':'#serving','data':data}).encode()
            req=urllib.request.Request('https://td.smallfighter.com/'+cfg["uri"],data=body,headers=hdr,method='POST')
            d=json.loads(urllib.request.urlopen(req,timeout=60).read())['data']
            page_items=d.get('items') or []
            got+=page_items
            if len(got)>=d.get('total',0) or not page_items: break
            page+=1; time.sleep(0.1)
        items+=got
    out=[]
    for it in items:
        cost=_num(it.get('cost'))
        if not cost: continue
        cost/=M; pay=(_num(it.get('cid_trans_payment_amount')) or 0)/M; rpay=(_num(it.get('cid_trans_real_payment_amount')) or 0)/M
        dpay=(_num(it.get('adx_metric_326')) or 0)/M; drpay=(_num(it.get('cid_trans_direct_real_payment_amount')) or 0)/M
        out.append({"entity_id":str(_first(it,cfg["id"])),"entity_name":_first(it,cfg["name"]),
            "account_id":str(_first(it,cfg["acc_id"]) or ""),"account_name":_first(it,cfg["acc_name"]),
            "parent_id":str(_first(it,cfg["par_id"]) or "") or None,"parent_name":_first(it,cfg["par_name"]),
            "channel":it.get("AdxName"),
            "cost":round(cost,2),"impressions":_i(it.get('impressions')),"clicks":_i(it.get('adx_metric_0')),
            "ctr":_r((_num(it.get('click_rate')) or 0)/100),"cpm":_r((_num(it.get('cpm')) or 0)/M),"cpc":_r((_num(it.get('cpc')) or 0)/M),
            "conversions":_i(it.get('adx_metric_7')),"conversion_cost":_r((_num(it.get('convert_cost')) or 0)/M),
            "orders":_i(it.get('cid_trans_order_num')),"pay_amount":round(pay,2),"roi":_div(pay,cost),
            "real_pay_amount":round(rpay,2),"real_orders":_i(it.get('cid_trans_real_order_num')),"real_roi":_div(rpay,cost),
            "refund_rate":_r((_num(it.get('cid_refund_rate')) or 0)/100),
            "direct_orders":_i(it.get('adx_metric_323')),"direct_pay_amount":round(dpay,2),"direct_roi":_div(dpay,cost),
            "direct_real_orders":_i(it.get('cid_trans_direct_real_order_num')),"direct_real_pay_amount":round(drpay,2),"direct_real_roi":_div(drpay,cost)})
    return out

# ============================ 沸点 ============================
FD_LEVELS={"账户维度":"ADVERTISER","项目维度":"PROJECT","计划维度":"PROMOTION","素材维度":"MATERIAL"}
FD_IDNAME={"ADVERTISER":(["advertiserId"],["advertiserName"],[],[]),
 "PROJECT":(["projectId"],["projectName"],["advertiserId"],["advertiserName"]),
 "PROMOTION":(["adId"],["adName"],["projectId"],["projectName"]),
 "MATERIAL":(["materialId"],["materialName"],["advertiserId"],["advertiserName"])}
def fetch_fd(login,level,day):
    a=login["auth"]; art=FD_LEVELS[level]; H=100
    hdr={"accept":"application/json","content-type":"application/json","did":a["did"],"token":a["token"],
         "version":"1.0.2","platform":"h5","origin":"https://admin.fifay.cn","referer":"https://admin.fifay.cn/","accept-encoding":"identity","user-agent":UA}
    ds=day.isoformat(); items=[]; page=1
    while True:
        b=json.dumps({"current":page,"pageSize":200,"startDate":ds,"endDate":ds,"adReportType":art,"orderDesc":2}).encode()
        req=urllib.request.Request("https://api.fifay.cn/fifay-ad/report/union/get",data=b,headers=hdr,method="POST")
        d=json.loads(urllib.request.urlopen(req,timeout=60).read())["data"]
        items+=d.get("list") or []
        if d.get("endPage") or len(items)>=d.get("total",0) or not d.get("list"): break
        page+=1; time.sleep(0.1)
    idk,namek,pidk,pnamek=FD_IDNAME[art]; out=[]
    for it in items:
        cost=_num(it.get('cost'))
        if not cost: continue
        cost/=H; conv=_num(it.get('convertCount'))
        out.append({"entity_id":str(_first(it,idk)),"entity_name":_first(it,namek),
            "account_id":str(_first(it,["advertiserId"]) or ""),"account_name":_first(it,["advertiserName"]),
            "parent_id":str(_first(it,pidk) or "") or None,"parent_name":_first(it,pnamek),"channel":"沸点",
            "cost":round(cost,2),"impressions":_i(it.get('showCount')),"clicks":_i(it.get('clickCount')),
            "ctr":_r((_num(it.get('ctr')) or 0)/H),"cpm":_r((_num(it.get('cpm')) or 0)/H),"cpc":_r((_num(it.get('cpc')) or 0)/H),
            "conversions":_i(it.get('convertCount')),"conversion_cost":_div(cost,conv),
            "orders":_i(it.get('originOrderCount')),"pay_amount":_r((_num(it.get('originOrderAmount')) or 0)/H),"roi":_r((_num(it.get('originOrderRoi')) or 0)/H),
            "real_pay_amount":_r((_num(it.get('orderAmount')) or 0)/H),"real_orders":_i(it.get('orderCount')),"real_roi":_r((_num(it.get('orderRoi')) or 0)/H),
            "refund_rate":_r((_num(it.get('refundOrderRate')) or 0)/H),
            "direct_orders":_i(it.get('directOriginOrderCount')),"direct_pay_amount":_r((_num(it.get('directOriginOrderAmount')) or 0)/H),"direct_roi":_r((_num(it.get('directOriginOrderRoi')) or 0)/H),
            "direct_real_orders":_i(it.get('directOrderCount')),"direct_real_pay_amount":_r((_num(it.get('directOrderAmount')) or 0)/H),"direct_real_roi":_r((_num(it.get('directOrderRoi')) or 0)/H)})
    return out

# ============================ 微橙 ============================
WC_LEVELS={"账户":"SecondAccountData/businessFindsDev","计划":"PlanData/businessFindsDev","素材":"MaterialData/findsDev"}
WC_IDNAME={"账户":(["advertiser_id"],["advertiser_name"],[],[]),
 "计划":(["promotion_id","project_id"],["promotion_name","project_name"],["project_id"],["project_name"]),
 "素材":(["material_id"],["material_name"],["promotion_id","project_id"],["promotion_name","project_name"])}
_WC_NAME={}  # advertiser_id -> advertiser_name（抓账户级时填充，供深层维度补账户名）
def fetch_wc(login,level,day):
    a=login["auth"]; ep=WC_LEVELS[level]
    hdr={"content-type":"application/x-www-form-urlencoded","accept":"application/json, text/plain, */*",
         "origin":"https://business.douyongtuan.com","referer":"https://business.douyongtuan.com/","accept-encoding":"identity","user-agent":UA}
    ds=day.isoformat(); items=[]; page=1
    while True:
        data={"session_id":a["session_id"],"customer_id":a["customer_id"],"page":page,"pageSize":200,
              "start_time":ds+" 00:00:00","end_time":ds+" 23:59:59","platform":1}
        req=urllib.request.Request("https://taotik.douyongtuan.com/business/"+ep,data=urllib.parse.urlencode(data).encode(),headers=hdr,method="POST")
        d=json.loads(urllib.request.urlopen(req,timeout=60).read().decode("utf-8","replace"))["data"]
        items+=d.get("data") or []
        if page>=d.get("last_page",1) or not d.get("data"): break
        page+=1; time.sleep(0.1)
    idk,namek,pidk,pnamek=WC_IDNAME[level]; out=[]
    for it in items:
        cost=_num(it.get('scost'))
        if not cost: continue
        adv_id=_first(it,["advertiser_id"]); adv_name=_first(it,["advertiser_name"])
        if level=="账户" and adv_id and adv_name:      # 账户级顺带缓存账户名，供深层补名
            _WC_NAME[str(adv_id)]=adv_name
        acc_name=adv_name or _WC_NAME.get(str(adv_id))  # 深层接口不返回账户名，查缓存
        out.append({"entity_id":str(_first(it,idk)),"entity_name":_first(it,namek),
            "account_id":str(adv_id or ""),"account_name":acc_name,
            "parent_id":str(_first(it,pidk) or "") or None,"parent_name":_first(it,pnamek),"channel":"巨量引擎",
            "cost":_r(cost),"impressions":_i(it.get('sshow')),"clicks":_i(it.get('sclick')),
            "ctr":_r(it.get('sctr')),"cpm":_r(it.get('cpm_platform')),"cpc":_r(it.get('cpc_platform')),
            "conversions":_i(it.get('sconvert')),"conversion_cost":_r(it.get('sconvert_cost')),
            "orders":_i(it.get('sall_alipay_count')),"pay_amount":_r(it.get('sall_alipay_total_price')),"roi":_r(it.get('ROI_all')),
            "real_pay_amount":_r(it.get('salipay_total_price')),"real_orders":_i(it.get('salipay_count')),"real_roi":_r(it.get('ROI')),
            "refund_rate":_r(it.get('refund_rate')),
            "direct_orders":_i(it.get('sall_single_count')),"direct_pay_amount":_r(it.get('sall_single_total_price')),"direct_roi":_r(it.get('ROI_all_single')),
            "direct_real_orders":_i(it.get('ssingle_count')),"direct_real_pay_amount":_r(it.get('ssingle_total_price')),"direct_real_roi":_r(it.get('ROI_single'))})
    return out

# ============================ 麦斯 ============================
MS_LEVELS={"账户":"adv_data/lists","计划":"xhs/campaign_data/lists","单元":"xhs/unit_data/lists","创意":"xhs/creativity_data/lists"}
MS_IDNAME={"账户":(["advertiser_id"],["advertiser_name"],[],[]),
 "计划":(["campaign_id"],["campaign_name"],["advertiser_id"],["advertiser_name"]),
 "单元":(["unit_id"],["unit_name"],["campaign_id"],["campaign_name"]),
 "创意":(["creativity_id"],["creativity_name"],["unit_id"],["unit_name"])}
MS_CF=["company","advertiser_id","costs","shows","clicks","converts","click_rate","convert_cost","cpc","cpm",
 "all_no","all_gmv","all_gsv_no","all_gsv","gmv_roi","gsv_roi","direct_all_no","direct_all_gmv","direct_all_gsv_no","direct_all_gsv",
 "direct_gmv_roi","direct_gsv_roi","refund_gmv","refund_no"]
def fetch_ms(login,level,day):
    a=login["auth"]; ep=MS_LEVELS[level]
    hdr={"x-token":a["x_token"],"signip":a.get("signip",""),"request-source":"max","accept-encoding":"identity",
         "content-type":"application/json;charset=UTF-8","accept":"application/json, text/plain, */*","user-agent":UA}
    ds=day.isoformat(); items=[]; page=1
    while True:
        payload={"page":page,"rows":200,"total":0,"media_type":11,"order_time_type":1,"start_time":ds,"end_time":ds,"times":[ds,ds],
         "query_type":"advertiser_id","keyword":"","custom_fields":MS_CF,"customer_ids":[],"parent_customer_ids":[],"salesman_ids":[],
         "companys":[],"admin_ids_1":[],"admin_ids_2":[],"goods_type":"","conv_rate_type":"","wait_time_type":"","conv_gmv_type":"",
         "conv_gmv_rate":"","marketing_target":[],"advance_search":[{"field":""},{"field":""}],"monitor_link_exception":"","is_uds":0}
        req=urllib.request.Request("https://preapi.maxengine.cn/admin/"+ep,data=json.dumps(payload).encode(),headers=hdr,method="POST")
        d=(json.loads(urllib.request.urlopen(req,timeout=60).read().decode("utf-8","replace")).get("data") or {})
        items+=d.get("data") or []
        if page>=d.get("last_page",1) or not d.get("data"): break
        page+=1; time.sleep(0.1)
    idk,namek,pidk,pnamek=MS_IDNAME[level]; out=[]
    for it in items:
        costs=_num(it.get('costs'))
        if not costs: continue
        shows=_num(it.get('shows')); clicks=_num(it.get('clicks')); conv=_num(it.get('converts')); allgmv=_num(it.get('all_gmv')); refund=_num(it.get('refund_gmv'))
        ctr=_num(it.get('click_rate')); cpm=_num(it.get('cpm')); cpc=_num(it.get('cpc')); ccost=_num(it.get('convert_cost'))
        out.append({"entity_id":str(_first(it,idk)),"entity_name":_first(it,namek),
            "account_id":str(_first(it,["advertiser_id"]) or ""),"account_name":_first(it,["advertiser_name"]),
            "parent_id":str(_first(it,pidk) or "") or None,"parent_name":_first(it,pnamek),"channel":"小红书聚光",
            "cost":_r(costs),"impressions":_i(shows),"clicks":_i(clicks),
            "ctr":_r(ctr if ctr is not None else (clicks/shows*100 if shows else None)),
            "cpm":_r(cpm if cpm is not None else (costs/shows*1000 if shows else None)),
            "cpc":_r(cpc if cpc is not None else (costs/clicks if clicks else None)),
            "conversions":_i(conv),"conversion_cost":_r(ccost if ccost is not None else (costs/conv if conv else None)),
            "orders":_i(it.get('all_no')),"pay_amount":_r(allgmv),"roi":_r(it.get('gmv_roi')),
            "real_pay_amount":_r(it.get('all_gsv')),"real_orders":_i(it.get('all_gsv_no')),"real_roi":_r(it.get('gsv_roi')),
            "refund_rate":_r(refund/allgmv*100 if allgmv else None),
            "direct_orders":_i(it.get('direct_all_no')),"direct_pay_amount":_r(it.get('direct_all_gmv')),"direct_roi":_r(it.get('direct_gmv_roi')),
            "direct_real_orders":_i(it.get('direct_all_gsv_no')),"direct_real_pay_amount":_r(it.get('direct_all_gsv')),"direct_real_roi":_r(it.get('direct_gsv_roi'))})
    return out

FETCH={"小飞机":fetch_xfj,"沸点":fetch_fd,"微橙":fetch_wc,"麦斯":fetch_ms}
LEVELS={"小飞机":list(XFJ_LEVELS),"沸点":list(FD_LEVELS),"微橙":list(WC_LEVELS),"麦斯":list(MS_LEVELS)}

def fetch(login,level,day):
    """返回归一化 dict 列表（含 platform/login_account/level/date）"""
    rows=FETCH[login["platform"]](login,level,day)
    ds=day.isoformat()
    for r in rows:
        r["platform"]=login["platform"]; r["login_account"]=login["tag"]; r["level"]=level; r["date"]=ds
    return rows
