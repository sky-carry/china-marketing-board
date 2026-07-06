# -*- coding: utf-8 -*-
"""PostgreSQL 入库：UPSERT 到 ad_daily，并记录 crawl_progress。"""
import os, psycopg2, psycopg2.extras
from fetchers import DBCOLS

DSN = os.environ.get("DATABASE_URL","postgresql://postgres:postgres@localhost:5432/ad_data")
_MET = [c for c in DBCOLS if c not in ("platform","login_account","level","entity_id","date")]

def connect():
    return psycopg2.connect(DSN)

def upsert(conn, rows):
    if not rows: return 0
    cols = DBCOLS
    vals = [[r.get(c) for c in cols] for r in rows]
    setclause = ",".join(f"{c}=EXCLUDED.{c}" for c in _MET) + ",fetched_at=now()"
    sql = f"INSERT INTO ad_daily ({','.join(cols)}) VALUES %s " \
          f"ON CONFLICT (platform,login_account,level,entity_id,date) DO UPDATE SET {setclause}"
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(cur, sql, vals, page_size=500)
    conn.commit()
    return len(rows)

def mark_progress(conn, platform, login, level, day, nrows):
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO crawl_progress (platform,login_account,level,date,rows,fetched_at)
            VALUES (%s,%s,%s,%s,%s,now())
            ON CONFLICT (platform,login_account,level,date) DO UPDATE SET rows=EXCLUDED.rows,fetched_at=now()""",
            (platform, login, level, day, nrows))
    conn.commit()

def done_set(conn, platform=None, login=None):
    q = "SELECT platform,login_account,level,date FROM crawl_progress"
    cond=[]; args=[]
    if platform: cond.append("platform=%s"); args.append(platform)
    if login: cond.append("login_account=%s"); args.append(login)
    if cond: q+=" WHERE "+" AND ".join(cond)
    with conn.cursor() as cur:
        cur.execute(q, args)
        return {(r[0],r[1],r[2],r[3].isoformat()) for r in cur.fetchall()}
