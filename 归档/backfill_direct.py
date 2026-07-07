# -*- coding: utf-8 -*-
"""一次性回填：为历史数据补齐 direct_*（直投归因）6 列。
只重抓 crawl_progress 里已有的 (平台,登录,层级,日) 组合，重抓即 UPSERT 覆盖填新列。
可续跑：已填过 direct_pay_amount 的日期自动跳过（滚动任务已补的近 15 天也会跳过）。
用法: python backfill_direct.py            # 全部
      python backfill_direct.py 小飞机      # 仅某平台
进度写入 backfill_direct.log。
"""
import sys, io, os, time, datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
import fetchers as F
import db as DB

HERE=os.path.dirname(os.path.abspath(__file__))
LOG=os.path.join(HERE,"backfill_direct.log")
WORKERS=8
plat_filter=sys.argv[1] if len(sys.argv)>1 else None

def log(m):
    line=f"{datetime.datetime.now().strftime('%H:%M:%S')} {m}"
    print(line,flush=True)
    with open(LOG,"a",encoding="utf-8") as f: f.write(line+"\n")

def load_units():
    """从 ad_daily 取真正需要填的行：direct_pay_amount 为 NULL 的 (平台,登录,层级,日)。
    只含有真实数据的日期（天然免抓空天）、天然可续跑（已填的行不再是 NULL）。"""
    logins={l["tag"]:l for l in F.load_logins() if l.get("auth")}
    conn=DB.connect(); cur=conn.cursor()
    cur.execute("SELECT DISTINCT platform,login_account,level,date FROM ad_daily WHERE direct_pay_amount IS NULL")
    need=cur.fetchall()
    conn.close()
    units={}
    for p,lo,lv,d in need:
        if lo not in logins: continue           # 该登录已无凭证，跳过
        if plat_filter and p!=plat_filter: continue
        units.setdefault((p,lo,lv),[]).append(d)
    return logins, units

def do_unit(login, level, days):
    """重抓一个 (登录,层级) 的所有待填日期，独立连接。返回 (rows, cells, fails)。"""
    p=login["platform"]; tag=login["tag"]
    conn=DB.connect(); rows=cells=0; fails=0
    try:
        for day in sorted(days):
            for attempt in range(3):
                try:
                    r=F.fetch(login,level,day)
                    DB.upsert(conn,r)
                    rows+=len(r); cells+=1
                    break
                except Exception as e:
                    if attempt==2: fails+=1
                    else: time.sleep(2)
            time.sleep(0.03)
    finally:
        conn.close()
    return rows,cells,fails

def main():
    open(LOG,"w").close()
    logins,units=load_units()
    total_days=sum(len(v) for v in units.values())
    log(f"待回填单元 {len(units)} 个, 待填日期合计 {total_days} 条 (平台过滤={plat_filter or '全部'})")
    if not units:
        log("无待回填数据（可能已全部补齐）。"); return
    t0=time.time(); done_units=0; R=C=Fl=0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs={ex.submit(do_unit, logins[lo], lv, days):(p,lo,lv,len(days)) for (p,lo,lv),days in units.items()}
        for fut in as_completed(futs):
            p,lo,lv,nd=futs[fut]
            try: r,c,f=fut.result()
            except Exception as e: r,c,f=0,0,nd; log(f"  !! {p}/{lo}/{lv} 单元异常 {repr(e)[:80]}")
            R+=r; C+=c; Fl+=f; done_units+=1
            log(f"[{done_units}/{len(units)}] {p}/{lo}/{lv}: 填{c}/{nd}天 入库{r}行 失败{f} | 累计入库{R}行 用时{int(time.time()-t0)}s")
    log(f"\n完成: 单元{len(units)} 填{C}个(流,日) 入库{R}行 失败{Fl} 用时{int(time.time()-t0)}s")

if __name__=="__main__":
    main()
