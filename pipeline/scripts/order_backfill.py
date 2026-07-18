# -*- coding: utf-8 -*-
"""订单回填：抓取 [start,end] 每天 × 各平台/登录的逐笔订单 -> UPSERT 入 orders 表。
断点续跑：crawl_progress 里 level='订单' 记录已完成的 (平台,登录,日)。
用法: python order_backfill.py [start] [end] [platforms] [login] [all]
  start/end: YYYY-MM-DD (默认 2025-01-01 .. 今天)
  platforms: 逗号分隔(默认 小飞机,沸点,微橙,麦斯)
  login:     逗号分隔 tag 过滤(默认 all)
  all:       第5参数非空 -> 含历史/停用账号
"""
import sys, io, os, time, datetime
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # scripts/ 下仍能 import 父目录 pipeline/ 的核心模块
import fetchers as F
import order_fetchers as OF
import db as DB

LEVEL = "订单"

def daterange(a, b):
    d = a; out = []
    while d <= b:
        out.append(d); d += datetime.timedelta(days=1)
    return out

def main():
    args = sys.argv[1:]
    start = datetime.date.fromisoformat(args[0]) if len(args) > 0 and args[0] else datetime.date(2025, 1, 1)
    end = datetime.date.fromisoformat(args[1]) if len(args) > 1 and args[1] else datetime.date.today()
    plat_arg = args[2] if len(args) > 2 and args[2] else ",".join(OF.ORDER_PLATFORMS)
    login_arg = args[3] if len(args) > 3 else "all"
    inc_all = len(args) > 4 and args[4] not in ("", "0", "false", "no")
    want_p = set(plat_arg.split(","))
    logins = [l for l in F.load_logins(enabled_only=not inc_all) if l["platform"] in want_p and l["platform"] in OF.ORDER_FETCH]
    if login_arg != "all":
        wt = set(login_arg.split(",")); logins = [l for l in logins if l["tag"] in wt]
    days = daterange(start, end)
    conn = DB.connect(); OF.ensure_orders_table(conn)
    done = DB.done_set(conn)
    print(f"订单回填 {start}~{end} ({len(days)}天) | 登录 {len(logins)} | levels={LEVEL}", flush=True)
    t0 = time.time(); total_orders = 0; fails = []
    for lg in logins:
        p = lg["platform"]; tag = lg["tag"]; cnt = 0
        for day in days:
            if (p, tag, LEVEL, day.isoformat()) in done:
                continue
            ok = False
            for attempt in range(3):
                try:
                    rows = OF.fetch_orders(lg, day)
                    OF.upsert_orders(conn, rows)
                    DB.mark_progress(conn, p, tag, LEVEL, day, len(rows))
                    total_orders += len(rows); cnt += 1; ok = True
                    break
                except Exception as e:
                    if attempt == 2:
                        fails.append((p, tag, day.isoformat(), repr(e)[:70]))
                    else:
                        time.sleep(2)
            if not ok:
                print(f"  !! {p}/{tag} @ {day} 失败,跳过该登录后续: {fails[-1][-1] if fails else ''}", flush=True)
                break
            time.sleep(0.03)
        print(f"[{p}/{tag}] 新增 {cnt} 天 (累计入库 {total_orders} 单, 用时 {int(time.time()-t0)}s)", flush=True)
    conn.close()
    print(f"\n完成: 入库 {total_orders} 单, 失败 {len(fails)}", flush=True)
    if fails:
        print("失败示例:", fails[:3], flush=True)

if __name__ == "__main__":
    main()
