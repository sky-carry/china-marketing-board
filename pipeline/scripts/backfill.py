# -*- coding: utf-8 -*-
"""断点续跑回填：抓取 [start,end] 每天 × 指定平台/层级/登录 -> UPSERT 入库。
用法: python backfill.py [start] [end] [platforms] [levels]
  start/end: YYYY-MM-DD (默认 2025-01-01 .. 今天)
  platforms: 逗号分隔平台名, 或 all (默认 all)
  levels:    逗号分隔层级名, 或 all (默认 all；也可用 account 只跑各平台账户层)
已在 crawl_progress 里的 (平台,登录,层级,日期) 会跳过（除非删表重跑）。
"""
import sys, io, os, time, datetime
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # scripts/ 下仍能 import 父目录 pipeline/ 的核心模块
import fetchers as F
import db as DB

ACCOUNT_LEVEL={"小飞机":"推广账号","沸点":"账户维度","微橙":"账户","麦斯":"账户"}

def daterange(a,b):
    d=a; out=[]
    while d<=b: out.append(d); d+=datetime.timedelta(days=1)
    return out

def main():
    args=sys.argv[1:]
    start=datetime.date.fromisoformat(args[0]) if len(args)>0 and args[0] else datetime.date(2025,1,1)
    end=datetime.date.fromisoformat(args[1]) if len(args)>1 and args[1] else datetime.date.today()
    plat_arg=args[2] if len(args)>2 else "all"
    level_arg=args[3] if len(args)>3 else "all"
    login_arg=args[4] if len(args)>4 else "all"     # 按登录标识过滤(逗号分隔 tag)
    inc_all=len(args)>5 and args[5] not in ("","0","false","no")  # 第6参数=含历史/停用账号
    logins=F.load_logins(enabled_only=not inc_all)
    if plat_arg!="all":
        want=set(plat_arg.split(",")); logins=[l for l in logins if l["platform"] in want]
    if login_arg!="all":
        wt=set(login_arg.split(",")); logins=[l for l in logins if l["tag"] in wt]
    days=daterange(start,end)
    conn=DB.connect()
    done=DB.done_set(conn)
    print(f"回填 {start}~{end} ({len(days)}天) | 登录数 {len(logins)} | 已完成 {len(done)} 条(平台,登录,层级,日) | levels={level_arg}",flush=True)
    total_rows=0; total_cells=0; fails=[]; t0=time.time()
    # 组装任务：每个 (login, level)
    tasks=[]
    for lg in logins:
        p=lg["platform"]
        levels=F.LEVELS[p] if level_arg=="all" else ([ACCOUNT_LEVEL[p]] if level_arg=="account" else [x for x in level_arg.split(",") if x in F.LEVELS[p]])
        for lv in levels: tasks.append((lg,lv))
    for lg,lv in tasks:
        p=lg["platform"]; tag=lg["tag"]; cnt=0
        for day in days:
            key=(p,tag,lv,day.isoformat())
            if key in done: continue
            ok=False
            for attempt in range(3):
                try:
                    rows=F.fetch(lg,lv,day)
                    DB.upsert(conn,rows)
                    DB.mark_progress(conn,p,tag,lv,day,len(rows))
                    total_rows+=len(rows); total_cells+=1; cnt+=1; ok=True
                    break
                except Exception as e:
                    if attempt==2: fails.append((p,tag,lv,day.isoformat(),repr(e)[:60]))
                    else: time.sleep(2)
            if not ok:
                # token 失效等：跳过该 (login,level) 后续，避免刷屏（可重跑续上）
                print(f"  !! {p}/{lv} @ {day} 失败，跳过该流后续: {fails[-1][-1] if fails else ''}",flush=True)
                break
            time.sleep(0.03)
        print(f"[{p}/{lv}] 新增 {cnt} 天  (累计入库 {total_rows} 行, 用时 {int(time.time()-t0)}s)",flush=True)
    conn.close()
    print(f"\n本次完成: 新写 {total_cells} 个(流,日), 入库 {total_rows} 行, 失败 {len(fails)}",flush=True)
    if fails:
        byp={}
        for f in fails: byp[f[0]]=byp.get(f[0],0)+1
        print("失败分布:",byp,"示例:",fails[:3],flush=True)

if __name__=="__main__":
    main()
