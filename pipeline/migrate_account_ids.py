# -*- coding: utf-8 -*-
"""历史数据账户ID/名称迁移：内部id -> 巨量长id。
- 小飞机 推广账号: entity_id 内部_id -> ExternalId；深层 广告组/广告/创意 account_id 内部AccountId -> AccountExternalId，account_name -> AccountName
- 微橙 账户: entity_id second_account_id -> advertiser_id，名称 公司名 -> advertiser_name；深层 计划/素材 account_id -> advertiser_id，account_name -> advertiser_name
账户级 entity_id 是主键一部分，迁移用「先改不冲突、再删冲突旧行」保证不丢数据。
运行: python migrate_account_ids.py
"""
import io, sys, json, datetime, urllib.request, urllib.parse
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, "d:/skgcode/china-marketing-board/pipeline")
import fetchers as F
import psycopg2

DSN = "postgresql://postgres:postgres@localhost:5432/ad_data"
XFJ_LOGINS = ["小飞机·sdjr@shun.tt", "小飞机·135796@qq.com", "小飞机·ayh@kdys001.com"]
WC_LOGINS = ["微橙·SKG", "微橙·SKG品牌"]


def xfj_map(tag):
    lg = [l for l in F.load_logins() if l["tag"] == tag][0]; a = lg["auth"]; cfg = F.XFJ_LEVELS["推广账号"]
    cookie = f'lang=zhCN; td.token={a["token"]}; td-op-uid={a["op_uid"]}; td.sid={a["sid"]}'
    hdr = {"authorization": "Bearer " + a["token"], "content-type": "application/json; charset=UTF-8", "cookie": cookie,
           "td-op-uid": a["op_uid"], "td-product": "td", "x-requested-with": "XMLHttpRequest", "accept-encoding": "identity", "user-agent": F.UA}
    beg = int((datetime.datetime(2025, 1, 1) - datetime.datetime(1970, 1, 1)).total_seconds()) - 8 * 3600
    end = int((datetime.datetime(2026, 7, 3) - datetime.datetime(1970, 1, 1)).total_seconds()) - 8 * 3600
    m = {}; page = 1
    while True:
        data = {"begindate": beg, "enddate": end, "page": page, "limit": 200, "metrics": F.XFJ_MET, "order": "cost|-1",
                "WithLevel": True, "WithCidConvertCfg": True, "_type": cfg["_type"]}; data.update(cfg["extra"])
        body = json.dumps({"type": "message", "mid": page, "req": 1, "uri": cfg["uri"], "__uid_4_track": int(a["op_uid"]),
                           "td-op-uid": a["op_uid"], "source": "td.web", "version": "1782784101", "hash": "#serving", "data": data}).encode()
        d = json.loads(urllib.request.urlopen(urllib.request.Request("https://td.smallfighter.com/" + cfg["uri"], data=body, headers=hdr, method="POST"), timeout=60).read())["data"]
        its = d.get("items") or []
        for it in its:
            iid = str(it.get("_id") or it.get("account_id")); ext = it.get("ExternalId"); nm = it.get("Name")
            if iid and ext: m[iid] = (str(ext), nm)
        if len(its) < 200: break
        page += 1
    return m


def wc_map(tag):
    lg = [l for l in F.load_logins() if l["tag"] == tag][0]; a = lg["auth"]
    hdr = {"content-type": "application/x-www-form-urlencoded", "accept": "application/json", "origin": "https://business.douyongtuan.com",
           "referer": "https://business.douyongtuan.com/", "accept-encoding": "identity", "user-agent": F.UA}
    m = {}; page = 1
    while True:
        data = {"session_id": a["session_id"], "customer_id": a["customer_id"], "page": page, "pageSize": 200,
                "start_time": "2025-01-01 00:00:00", "end_time": "2026-07-03 23:59:59", "platform": 1}
        d = json.loads(urllib.request.urlopen(urllib.request.Request("https://taotik.douyongtuan.com/business/SecondAccountData/businessFindsDev",
            data=urllib.parse.urlencode(data).encode(), headers=hdr, method="POST"), timeout=60).read().decode("utf-8", "replace"))["data"]
        for it in d.get("data") or []:
            sid = str(it.get("second_account_id")); adv = it.get("advertiser_id"); nm = it.get("advertiser_name")
            if sid and adv: m[sid] = (str(adv), nm)
        if page >= d.get("last_page", 1): break
        page += 1
    return m


def migrate_acct_entity(cur, tag, level, old, new, name):
    """账户级：entity_id(主键)内部->长id，同步 account_id/entity_name/account_name。先改不冲突、再删冲突旧行。"""
    cur.execute("""UPDATE ad_daily a SET entity_id=%s, entity_name=%s, account_id=%s, account_name=%s
        WHERE login_account=%s AND level=%s AND entity_id=%s
        AND NOT EXISTS (SELECT 1 FROM ad_daily b WHERE b.platform=a.platform AND b.login_account=a.login_account
                        AND b.level=a.level AND b.entity_id=%s AND b.date=a.date)""",
        (new, name, new, name, tag, level, old, new))
    moved = cur.rowcount
    cur.execute("DELETE FROM ad_daily WHERE login_account=%s AND level=%s AND entity_id=%s", (tag, level, old))
    return moved, cur.rowcount


def migrate_deep_acct(cur, tag, levels, old, new, name):
    """深层：只改 account_id/account_name（entity_id 不变）。"""
    cur.execute("UPDATE ad_daily SET account_id=%s, account_name=%s WHERE login_account=%s AND level = ANY(%s) AND account_id=%s",
        (new, name, tag, levels, old))
    return cur.rowcount


def migrate_tags(cur, platform, old, new):
    cur.execute("SELECT 1 FROM account_tags WHERE platform=%s AND entity_id=%s", (platform, new))
    if cur.fetchone():
        cur.execute("DELETE FROM account_tags WHERE platform=%s AND entity_id=%s", (platform, old))  # 新id已有标签，弃旧
    else:
        cur.execute("UPDATE account_tags SET entity_id=%s WHERE platform=%s AND entity_id=%s", (new, platform, old))


def main():
    c = psycopg2.connect(DSN); c.autocommit = True; cur = c.cursor()
    XFJ_DEEP = ["广告组", "广告", "创意"]; WC_DEEP = ["计划", "素材"]
    tot_acct = 0; tot_deep = 0; tot_drop = 0

    for tag in XFJ_LOGINS:
        m = xfj_map(tag)
        print(f"[{tag}] 账户对照 {len(m)} 个")
        for old, (new, name) in m.items():
            mv, dr = migrate_acct_entity(cur, tag, "推广账号", old, new, name); tot_acct += mv; tot_drop += dr
            tot_deep += migrate_deep_acct(cur, tag, XFJ_DEEP, old, new, name)
            migrate_tags(cur, "小飞机", old, new)

    for tag in WC_LOGINS:
        m = wc_map(tag)
        print(f"[{tag}] 账户对照 {len(m)} 个")
        for old, (new, name) in m.items():
            mv, dr = migrate_acct_entity(cur, tag, "账户", old, new, name); tot_acct += mv; tot_drop += dr
            tot_deep += migrate_deep_acct(cur, tag, WC_DEEP, old, new, name)
            migrate_tags(cur, "微橙", old, new)

    print(f"\n账户级迁移 {tot_acct} 行, 去重丢弃 {tot_drop} 行, 深层account更新 {tot_deep} 行")

    # 复查: 账户级 entity_id 是否还有短内部id(纯数字<10位 视为内部)
    for plat, lvl in (("小飞机", "推广账号"), ("微橙", "账户")):
        cur.execute("SELECT DISTINCT entity_id FROM ad_daily WHERE platform=%s AND level=%s", (plat, lvl))
        ids = [r[0] for r in cur.fetchall()]
        short = [i for i in ids if i and i.isdigit() and len(i) < 12]
        print(f"[{plat}·{lvl}] 账户级 entity_id 共 {len(ids)} 个, 疑似仍是内部短id: {short[:10]}")
    c.close()


if __name__ == "__main__":
    main()
