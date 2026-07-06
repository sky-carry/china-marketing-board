# -*- coding: utf-8 -*-
"""建 accounts 表 + tasks/runs 表，并把现有 creds.json 迁入（麦斯 token 从 ms_token.json 取实值）。"""
import os
import psycopg2, psycopg2.extras, json, os, io, sys
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
HERE=os.path.dirname(os.path.abspath(__file__))
DSN=os.environ.get("DATABASE_URL","postgresql://postgres:postgres@localhost:5432/ad_data")
c=psycopg2.connect(DSN); c.autocommit=True; cur=c.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS accounts (
  id serial PRIMARY KEY,
  platform text NOT NULL,
  tag text NOT NULL UNIQUE,
  auth jsonb NOT NULL,
  enabled boolean DEFAULT true,
  token_status text DEFAULT 'unknown',
  token_updated_at timestamptz,
  note text,
  created_at timestamptz DEFAULT now()
);""")
cur.execute("""
CREATE TABLE IF NOT EXISTS tasks (
  id serial PRIMARY KEY,
  name text NOT NULL,
  kind text NOT NULL,              -- rolling | backfill
  platform text,                   -- null=全部
  window_days int DEFAULT 15,
  interval_minutes int DEFAULT 5,
  enabled boolean DEFAULT true,
  last_run_at timestamptz,
  last_status text,
  created_at timestamptz DEFAULT now()
);""")
cur.execute("""
CREATE TABLE IF NOT EXISTS runs (
  id serial PRIMARY KEY,
  task_id int,
  kind text,
  started_at timestamptz DEFAULT now(),
  finished_at timestamptz,
  status text,                     -- running | ok | error
  rows_written int DEFAULT 0,
  detail text
);""")

# migrate creds.json
reg=json.load(open(os.path.join(HERE,"creds.json"),encoding="utf-8"))
ms=json.load(open(os.path.join(HERE,"ms_token.json"))) if os.path.exists(os.path.join(HERE,"ms_token.json")) else {}
for lg in reg:
    auth=dict(lg["auth"])
    if auth.get("_from_file"):
        auth={"x_token":ms.get("t",""),"signip":ms.get("s","")}
    cur.execute("""INSERT INTO accounts (platform,tag,auth,enabled,token_status,token_updated_at)
        VALUES (%s,%s,%s,true,'ok',now())
        ON CONFLICT (tag) DO UPDATE SET platform=EXCLUDED.platform, auth=EXCLUDED.auth""",
        (lg["platform"], lg["tag"], psycopg2.extras.Json(auth)))
    print("upsert account:", lg["platform"], lg["tag"])

cur.execute("SELECT count(*) FROM accounts"); print("accounts 总数:", cur.fetchone()[0])
c.close()
