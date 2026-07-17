# -*- coding: utf-8 -*-
"""四平台各维度抓取器：给定 (login, level, date) 返回归一化到统一指标的行列表。
统一指标字段见 DBCOLS。只返回当天有消耗(cost>0)的行。"""
import json, os, time, datetime, urllib.request, urllib.parse, threading

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

DSN = os.environ.get("DATABASE_URL","postgresql://postgres:postgres@localhost:5432/ad_data")
def load_logins(enabled_only=True):
    """从 DB accounts 表读取登录；失败则回退 creds.json。"""
    try:
        import psycopg2
        conn=psycopg2.connect(DSN); cur=conn.cursor()
        q="SELECT platform,tag,auth,id FROM accounts"+(" WHERE enabled AND NOT COALESCE(is_historical,false)" if enabled_only else "")+" ORDER BY platform,tag"
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
# 账户级(推广账号)改走 CID报表接口：v1/account/list 只含「广告管理」里的账户，会漏掉停投账户；
# CID报表(cid.smallfighter.com)含所有账户(含停投)，是超集；Keys=["account_id"] 让服务器聚合成「一账户一行」。
def fetch_xfj_account(login,day):
    a=login["auth"]; M=1e6
    op_uids=[str(x) for x in (a.get("op_uids") or [a["op_uid"]])]   # 逐项目抓
    items=[]
    for op_uid in op_uids:
        cookie=f'lang=zhCN; td.token={a["token"]}; td-op-uid={op_uid}; td.sid={a["sid"]}'
        hdr={'authorization':'Bearer '+a["token"],'content-type':'application/json; charset=UTF-8','cookie':cookie,
             'td-op-uid':op_uid,'td-product':'cid','origin':'https://cid.smallfighter.com',
             'referer':'https://cid.smallfighter.com/','accept-encoding':'identity','user-agent':UA}
        got=[]; page=1
        while True:
            data={"order":"cost|-1","IsCid":True,"needMulProject":True,"Keys":["account_id"],
              "userIds":[],"spaceBelongIds":[],"BeginDate":_ts(day),"EndDate":_ts(day,True),"TimeKeys":"",
              "accountIds":[],"LabelKey":0,"channelIds":[],"ecpIds":[],"Type":155,"_type":"CID_REPORT",
              "page":page,"limit":200,"metrics":XFJ_MET,"SelectedColumns":XFJ_MET,"Level":3,"AscribeKey":0,
              "accountStatus":[],"adxSubIds":[],"isAggregateByUser":False,"isAggregateByBizType":False,
              "isNotFilterDeletedAccount":False,"cidGoodIds":[],"CidBusinessIds":[],"CidOperationIds":[],
              "NeedSpaceBelong":False,"NeedCidOperator":False}
            body=json.dumps({"mid":page,"source":"td.web.vue","hash":"#/cid/report",
                  "url":"/v1/cid/report/list","data":data}).encode()
            req=urllib.request.Request('https://cid.smallfighter.com/v1/cid/report/list',data=body,headers=hdr,method='POST')
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
        eid=str(it.get('AccountExternalId') or '')
        out.append({"entity_id":eid,"entity_name":it.get('AccountName'),
            "account_id":eid,"account_name":it.get('AccountName'),
            "parent_id":None,"parent_name":None,"channel":it.get('ChannelName') or it.get('AdxName'),
            "cost":round(cost,2),"impressions":_i(it.get('impressions')),"clicks":_i(it.get('adx_metric_0')),
            "ctr":_r((_num(it.get('click_rate')) or 0)/100),"cpm":_r((_num(it.get('cpm')) or 0)/M),"cpc":_r((_num(it.get('cpc')) or 0)/M),
            "conversions":_i(it.get('adx_metric_7')),"conversion_cost":_r((_num(it.get('convert_cost')) or 0)/M),
            "orders":_i(it.get('cid_trans_order_num')),"pay_amount":round(pay,2),"roi":_div(pay,cost),
            "real_pay_amount":round(rpay,2),"real_orders":_i(it.get('cid_trans_real_order_num')),"real_roi":_div(rpay,cost),
            "refund_rate":_r((_num(it.get('cid_refund_rate')) or 0)/100),
            "direct_orders":_i(it.get('adx_metric_323')),"direct_pay_amount":round(dpay,2),"direct_roi":_div(dpay,cost),
            "direct_real_orders":_i(it.get('cid_trans_direct_real_order_num')),"direct_real_pay_amount":round(drpay,2),"direct_real_roi":_div(drpay,cost)})
    return out

def fetch_xfj(login,level,day):
    if level=="素材": return fetch_xfj_material(login,day)   # 素材走 CID 独立接口
    if level=="推广账号": return fetch_xfj_account(login,day)  # 账户级走 CID报表(含停投账户)
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

# 小飞机 CID 素材报表(cid.smallfighter.com，独立 Bearer token，与 td 分开登录)
# 指标缩放同 td：金额÷1e6、rate÷100；cidm_metric_1/2/3/4 = 下单数/成交数/下单金额/成交金额
XFJ_MAT_MET=["cost","impressions","adx_metric_0","click_rate","cpc","cpm","cidm_metric_1","cidm_metric_2","cidm_metric_3","cidm_metric_4"]
def fetch_xfj_material(login,day):
    a=login["auth"]; M=1e6
    tok=a.get("cid_token"); op=str(a.get("cid_op_uid") or a.get("op_uid") or "")
    if not tok: raise RuntimeError("小飞机CID token missing login(未登录CID)")
    hdr={"authorization":"Bearer "+tok,"td-op-uid":op,"content-type":"application/json;charset=UTF-8",
         "accept-encoding":"identity","user-agent":UA}
    items=[]; page=1
    while True:
        data={"order":"cost|-1","WithRelateAccount":False,"IncludeAdxDeleted":True,"withRelateDerive":False,"All":True,
              "createType":3,"type":0,"begindate":_ts(day),"enddate":_ts(day,True),"userIds":[],"WithRelateExternalId":False,
              "WithMaterialAweme":True,"page":page,"limit":200,"findFolder":False,"includeSubFolder":False,"filterType":5,
              "metrics":XFJ_MAT_MET,"level":13,"Type":3,"_type":"MATERIAL_REPORT","WithRelCampaign":False,"WithMaterialUrl":False}
        body=json.dumps({"mid":page,"source":"td.web.vue","url":"/v1/material/listLimit","data":data}).encode()
        req=urllib.request.Request("https://cid.smallfighter.com/v1/material/listLimit",data=body,headers=hdr,method="POST")
        resp=json.loads(urllib.request.urlopen(req,timeout=60).read().decode("utf-8","replace"))
        if resp.get("code")!=0:   # 非0多为登录态失效；含 token/login 关键字以触发自动重登
            raise RuntimeError(f"小飞机CID material token expired login code={resp.get('code')} msg={resp.get('msg') or resp.get('message')}")
        d=resp.get("data") or {}; its=d.get("items") or []
        items+=its
        if len(items)>=d.get("total",0) or not its: break
        page+=1; time.sleep(0.1)
    out=[]
    for it in items:
        cost=_num(it.get('cost'))
        if not cost: continue
        cost/=M; pay=(_num(it.get('cidm_metric_3')) or 0)/M; rpay=(_num(it.get('cidm_metric_4')) or 0)/M
        out.append({"entity_id":str(it.get('_id')),"entity_name":it.get('Name'),
            "account_id":"","account_name":None,"parent_id":None,"parent_name":None,"channel":"小飞机素材",
            "cost":round(cost,2),"impressions":_i(it.get('impressions')),"clicks":_i(it.get('adx_metric_0')),
            "ctr":_r((_num(it.get('click_rate')) or 0)/100),"cpm":_r((_num(it.get('cpm')) or 0)/M),"cpc":_r((_num(it.get('cpc')) or 0)/M),
            "conversions":None,"conversion_cost":None,
            "orders":_i(it.get('cidm_metric_1')),"pay_amount":round(pay,2),"roi":_div(pay,cost),
            "real_pay_amount":round(rpay,2),"real_orders":_i(it.get('cidm_metric_2')),"real_roi":_div(rpay,cost),
            "refund_rate":None})
    return out

# ============================ 沸点 ============================
FD_LEVELS={"账户维度":"ADVERTISER","项目维度":"PROJECT","计划维度":"PROMOTION","素材维度":"MATERIAL"}
FD_IDNAME={"ADVERTISER":(["advertiserId"],["advertiserName"],[],[]),
 "PROJECT":(["projectId"],["projectName"],["advertiserId"],["advertiserName"]),
 "PROMOTION":(["adId"],["adName"],["projectId"],["projectName"]),
 "MATERIAL":(["materialId"],["materialName"],["advertiserId"],["advertiserName"])}
# 官方API取数字段：direct*/间接数据须显式请求才返回（见 docs/沸点报表API对接文档.md）
FD_API_FIELDS=["showCount","clickCount","cost","convertCount","ctr","cpm","cpc",
 "originOrderCount","originOrderAmount","originOrderRoi","orderCount","orderAmount","orderRoi","refundOrderRate",
 "directOriginOrderCount","directOriginOrderAmount","directOriginOrderRoi",
 "directOrderCount","directOrderAmount","directOrderRoi"]

def _fd_rows(art, items):
    """沸点原始 list -> 统一指标行。网页接口与官方API字段一致，共用此映射：金额÷100转元，比率÷100转百分数。"""
    idk,namek,pidk,pnamek=FD_IDNAME[art]; H=100; out=[]
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

def fetch_fd_legacy(login,level,day):
    """【备份】沸点网页后台接口：借登录态 token/did（会过期）。"""
    a=login["auth"]; art=FD_LEVELS[level]
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
    return _fd_rows(art, items)

# 沸点官方API有调用频率限制(code=42901 apiKey调用超限)。生产是多线程并发抓取,
# 8个线程同时打同一个key会瞬间超限。故全局串行化+最小间隔,超限则退避重试。
_FD_LOCK = threading.Lock()
_FD_LAST = [0.0]
_FD_COOLDOWN = [0.0]       # 命中42901后的全局冷却截止时间戳(所有线程共同遵守，让key真正歇够)
_FD_MIN_GAP = 2.5          # 相邻沸点API调用最小间隔(秒)
def _fd_api_post(url, body, hdr):
    """串行+限速+42901【全局】退避 的沸点API请求。返回解析后的 resp dict。
    关键：撞到42901时设全局冷却并在锁内统一等待——否则某线程退避时其它线程仍在打接口，
    apiKey 从不歇息、退避形同虚设(此前偶发少量单元耗尽重试仍42901的根因)。"""
    for attempt in range(6):
        with _FD_LOCK:      # 序列化: 同一时刻只允许一个沸点API请求在飞
            wait = max(_FD_MIN_GAP - (time.time() - _FD_LAST[0]), _FD_COOLDOWN[0] - time.time(), 0.0)
            if wait > 0: time.sleep(wait)               # 冷却在锁内等 → 其它线程一并阻塞，全局停手
            req = urllib.request.Request(url, data=body, headers=hdr, method="POST")
            resp = json.loads(urllib.request.urlopen(req, timeout=60).read().decode("utf-8","replace"))
            _FD_LAST[0] = time.time()
            if resp.get("code") == 42901:
                _FD_COOLDOWN[0] = time.time() + (60 + attempt*40)   # 递增全局冷却:60,100,140,180,220s
        if resp.get("code") == 42901 and attempt < 5:
            continue
        return resp
    return resp

def fetch_fd_api(login,level,day):
    """沸点官方开放API：Bearer 令牌（稳定，不依赖登录态）。字段/单位与网页接口一致；direct/间接须 customizeFields。"""
    a=login["auth"]; art=FD_LEVELS[level]
    hdr={"Authorization":"Bearer "+a["api_key"],"Content-Type":"application/json","accept-encoding":"identity","user-agent":UA}
    ds=day.isoformat(); items=[]; page=1
    while True:
        b=json.dumps({"adReportType":art,"startDate":ds,"endDate":ds,"current":page,"pageSize":200,
                      "customizeFields":FD_API_FIELDS}).encode()
        resp=_fd_api_post("https://api.fifay.cn/fifay-ad/report/union/get", b, hdr)
        code=resp.get("code")
        if code!=200:   # 40001=令牌过期(含 token/expired 关键字以便判为鉴权错误); 42901退避后仍超限也会到这
            raise RuntimeError(f"沸点API {'token expired login' if code==40001 else 'error'} code={code} msg={resp.get('message')}")
        d=resp.get("data") or {}
        items+=d.get("list") or []
        if d.get("endPage") or len(items)>=d.get("total",0) or not d.get("list"): break
        page+=1; time.sleep(0.1)
    return _fd_rows(art, items)

def fetch_fd(login,level,day):
    """沸点入口：账号 auth 含 api_key 走官方API，否则回退网页接口(备份)。"""
    return fetch_fd_api(login,level,day) if login["auth"].get("api_key") else fetch_fd_legacy(login,level,day)

# ============================ 博擎 (fifay 换皮，同一套接口/字段) ============================
# 博擎(bccid.jingcaiplus.com) 是沸点(fifay) 的白标系统，连接口都用 api.fifay.cn，字段与沸点一致。
BQ_LEVELS={"账户维度":"ADVERTISER"}
def fetch_bq(login,level,day):
    a=login["auth"]; art=BQ_LEVELS[level]
    hdr={"accept":"application/json","content-type":"application/json","did":a["did"],"token":a["token"],
         "version":"1.0.2","platform":"h5","origin":"https://bccid.jingcaiplus.com","referer":"https://bccid.jingcaiplus.com/","accept-encoding":"identity","user-agent":UA}
    ds=day.isoformat(); items=[]; page=1
    while True:
        b=json.dumps({"current":page,"pageSize":200,"startDate":ds,"endDate":ds,"adReportType":art,"orderDesc":2}).encode()
        req=urllib.request.Request("https://api.fifay.cn/fifay-ad/report/union/get",data=b,headers=hdr,method="POST")
        resp=json.loads(urllib.request.urlopen(req,timeout=60).read().decode("utf-8","replace"))
        if resp.get("code")!=200:   # 非200多为登录态失效，抛含 token/login 关键字的错误以触发自动重登
            raise RuntimeError(f"博擎 token expired login code={resp.get('code')} msg={resp.get('message')}")
        d=resp.get("data") or {}
        items+=d.get("list") or []
        if d.get("endPage") or len(items)>=d.get("total",0) or not d.get("list"): break
        page+=1; time.sleep(0.1)
    rows=_fd_rows(art, items)
    for r in rows: r["channel"]="博擎"
    return rows

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

# ============================ 方块(新巨量·抖音千川CID, 历史数据) ============================
# quanyu.fangkuai.link RuoYi后台。登录: POST /prod-api/auth/login {username,password,code,uuid}(图形验证码)->access_token。
# 报表(账户级,逐日): POST selectSuperOceanengineAdvertisersAllData {startDate,endDate=同一天}。数值均自然单位(元/%/倍)，无需缩放。
# 历史数据、平台已停更；auth.token 为登录得到的 access_token(约12h过期，无法免验证码自动续)。
FK_API="https://quanyu.fangkuai.link/prod-api"
FK_EP="/superoceanengine/newSuperOceanengineAdvertisers/selectSuperOceanengineAdvertisersAllData"
def fetch_fk(login,level,day):
    a=login["auth"]; ds=day.isoformat(); items=[]; page=1
    hdr={"Authorization":"Bearer "+a["token"],"Content-Type":"application/json;charset=UTF-8",
         "accept-encoding":"identity","user-agent":UA,"Referer":"https://quanyu.fangkuai.link/"}
    while True:
        body={"pageNum":page,"pageSize":300,"differentiateLineType":"2","lineType":"","selectedField":"",
              "advertiserId":None,"startDate":ds,"endDate":ds}
        req=urllib.request.Request(FK_API+FK_EP,data=json.dumps(body).encode(),headers=hdr,method="POST")
        r=json.loads(urllib.request.urlopen(req,timeout=60).read().decode("utf-8","replace"))
        if r.get("rows") is None and r.get("code") not in (200,None):
            raise RuntimeError(f"方块API code={r.get('code')} msg={r.get('msg')} (token/login 可能失效)")
        rows=r.get("rows") or []; items+=rows
        if len(items)>=(r.get("total") or 0) or not rows: break
        page+=1; time.sleep(0.1)
    out=[]
    for it in items:
        cost=_num(it.get("statCost"))
        if not cost: continue
        out.append({"entity_id":str(it.get("advertiserId")),"entity_name":it.get("advertiserName"),
            "account_id":str(it.get("advertiserId") or ""),"account_name":it.get("advertiserName"),
            "parent_id":None,"parent_name":None,"channel":"巨量千川",
            "cost":_r(cost),"impressions":_i(it.get("showCnt")),"clicks":_i(it.get("clickCnt")),
            "ctr":_r(it.get("ctr")),"cpm":_r(it.get("cpmPlatform")),"cpc":_r(it.get("cpcPlatform")),
            "conversions":_i(it.get("convertCnt")),"conversion_cost":_r(it.get("conversionCost")),
            "orders":_i(it.get("goodsCount")),"pay_amount":_r(it.get("goodsPrice")),"roi":_r(it.get("roi")),
            "real_pay_amount":_r(it.get("dischargeBackGoodsPrice")),"real_orders":_i(it.get("dischargeBackGoodsCount")),"real_roi":_r(it.get("dischargeBackROI")),
            "refund_rate":_r(it.get("goodsPriceRefundRate")),
            "direct_orders":_i(it.get("goodsDirectCount")),"direct_pay_amount":_r(it.get("goodsDirectPrice")),"direct_roi":_r(it.get("directRoi")),
            "direct_real_orders":_i(it.get("directDischargeBackGoodsCount")),"direct_real_pay_amount":_r(it.get("directDischargeBackGoodsPrice")),"direct_real_roi":_r(it.get("directDischargeBackROI"))})
    return out

FETCH={"小飞机":fetch_xfj,"沸点":fetch_fd,"微橙":fetch_wc,"麦斯":fetch_ms,"方块":fetch_fk,"博擎":fetch_bq}
LEVELS={"小飞机":list(XFJ_LEVELS)+["素材"],"沸点":list(FD_LEVELS),"微橙":list(WC_LEVELS),"麦斯":list(MS_LEVELS),"方块":["账户"],"博擎":list(BQ_LEVELS)}

def fetch(login,level,day):
    """返回归一化 dict 列表（含 platform/login_account/level/date）"""
    rows=FETCH[login["platform"]](login,level,day)
    ds=day.isoformat()
    for r in rows:
        r["platform"]=login["platform"]; r["login_account"]=login["tag"]; r["level"]=level; r["date"]=ds
    return rows
