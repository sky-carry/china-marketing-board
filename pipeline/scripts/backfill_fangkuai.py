# -*- coding: utf-8 -*-
"""一次性回填：方块(新巨量·历史数据) 账户级逐日抓取 -> ad_daily。
token 取自 accounts 表(方块·SKG旗舰店-京东)；过期需重新登录(图形验证码)后更新该账号 auth.token。
用法: python backfill_fangkuai.py [start] [end]   默认 2025-01-01 .. 今天
"""
import sys, io, os, time, datetime, psycopg2, psycopg2.extras
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # scripts/ 下仍能 import 父目录 pipeline/ 的核心模块
import fetchers as F
import db as DB

TAG="方块·SKG旗舰店-京东"
start=datetime.date.fromisoformat(sys.argv[1]) if len(sys.argv)>1 else datetime.date(2025,1,1)
end=datetime.date.fromisoformat(sys.argv[2]) if len(sys.argv)>2 else datetime.date.today()

c=psycopg2.connect(DB.DSN if hasattr(DB,'DSN') else "postgresql://postgres:postgres@localhost:5432/ad_data")
cur=c.cursor(); cur.execute("SELECT platform,tag,auth FROM accounts WHERE tag=%s",(TAG,))
r=cur.fetchone(); c.close()
if not r: raise SystemExit("未找到方块账号，请先插入 accounts 记录")
login={"platform":r[0],"tag":r[1],"auth":dict(r[2])}

days=[start+datetime.timedelta(days=i) for i in range((end-start).days+1)]
print(f"回填 方块 {start}~{end} 共 {len(days)} 天", flush=True)
conn=DB.connect(); total=0; withdata=0; fails=0; t0=time.time()
for i,day in enumerate(days):
    try:
        rows=F.fetch(login,"账户",day)
        DB.upsert(conn,rows); DB.mark_progress(conn,"方块",TAG,"账户",day,len(rows))
        total+=len(rows); withdata+=1 if rows else 0
    except Exception as e:
        fails+=1
        if fails<=3 or fails%20==0: print(f"  !! {day} 失败: {repr(e)[:80]}", flush=True)
        if "token" in repr(e).lower() or "401" in repr(e) or "登录" in repr(e):
            print("  token 可能失效，停止。请重新登录更新 auth.token 后重跑。", flush=True); break
    if (i+1)%30==0:
        print(f"  …{i+1}/{len(days)} 天, 有数据 {withdata} 天, 入库 {total} 行, 用时 {int(time.time()-t0)}s", flush=True)
    time.sleep(0.05)
conn.close()
print(f"\n完成: 有数据 {withdata} 天, 入库 {total} 行, 失败 {fails}, 用时 {int(time.time()-t0)}s", flush=True)
