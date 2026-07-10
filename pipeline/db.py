# -*- coding: utf-8 -*-
"""PostgreSQL 入库：UPSERT 到 ad_daily，并记录 crawl_progress。"""
import os, psycopg2, psycopg2.extras
from fetchers import DBCOLS

DSN = os.environ.get("DATABASE_URL","postgresql://postgres:postgres@localhost:5432/ad_data")
_MET = [c for c in DBCOLS if c not in ("platform","login_account","level","entity_id","date")]

def connect():
    return psycopg2.connect(DSN)

_KEY = ("platform","login_account","level","entity_id","date")
def upsert(conn, rows):
    if not rows: return 0
    # 同批按主键去重(保留最后一条)：接口翻页排序不稳可能返回重复实体，否则 ON CONFLICT 同批撞键报错
    dedup = {}
    for r in rows: dedup[tuple(r.get(c) for c in _KEY)] = r
    rows = list(dedup.values())
    cols = DBCOLS
    vals = [[r.get(c) for c in cols] for r in rows]
    setclause = ",".join(f"{c}=EXCLUDED.{c}" for c in _MET) + ",fetched_at=now()"
    sql = f"INSERT INTO ad_daily ({','.join(cols)}) VALUES %s " \
          f"ON CONFLICT (platform,login_account,level,entity_id,date) DO UPDATE SET {setclause}"
    try:
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(cur, sql, vals, page_size=500)
        conn.commit()
    except Exception:
        conn.rollback()   # 回滚，避免事务中止后污染同一连接的后续写入
        raise
    return len(rows)

def mark_progress(conn, platform, login, level, day, nrows):
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO crawl_progress (platform,login_account,level,date,rows,fetched_at)
            VALUES (%s,%s,%s,%s,%s,now())
            ON CONFLICT (platform,login_account,level,date) DO UPDATE SET rows=EXCLUDED.rows,fetched_at=now()""",
            (platform, login, level, day, nrows))
    conn.commit()

# ============================ 平台迁移去重 ============================
# 规则背景：投放机构把某账户从 A 平台迁到 B 平台后，A 平台仍会残留该账户「同 ID 同日」的行，
# 但数据不完整（通常只有消费，无真实付款/ROI/直投）。应删除 A(残留) 的行、保留 B(权威完整)。
# 账户级 entity_id 各平台都用巨量广告主ID，可直接按 (entity_id, date) 跨平台匹配。
# 详见 docs/业务说明.md「平台迁移去重规则」。以后新增迁移方向，往下表加一行即可。
MIGRATION_DEDUP = [
    # (残留平台, 残留账户层级, 权威平台, 权威账户层级)
    ("小飞机", "推广账号", "沸点", "账户维度"),
]
def dedupe_migrated_accounts(conn):
    """删除因投放机构平台迁移产生的重复账户行（残留方），按 entity_id+date 跨平台匹配。返回删除行数。"""
    total = 0
    with conn.cursor() as cur:
        for stale_p, stale_lv, keep_p, keep_lv in MIGRATION_DEDUP:
            cur.execute("""DELETE FROM ad_daily a
                WHERE a.platform=%s AND a.level=%s AND EXISTS (
                    SELECT 1 FROM ad_daily b
                    WHERE b.platform=%s AND b.level=%s AND b.entity_id=a.entity_id AND b.date=a.date)""",
                (stale_p, stale_lv, keep_p, keep_lv))
            total += cur.rowcount
    conn.commit()
    return total

def done_set(conn, platform=None, login=None):
    q = "SELECT platform,login_account,level,date FROM crawl_progress"
    cond=[]; args=[]
    if platform: cond.append("platform=%s"); args.append(platform)
    if login: cond.append("login_account=%s"); args.append(login)
    if cond: q+=" WHERE "+" AND ".join(cond)
    with conn.cursor() as cur:
        cur.execute(q, args)
        return {(r[0],r[1],r[2],r[3].isoformat()) for r in cur.fetchall()}
