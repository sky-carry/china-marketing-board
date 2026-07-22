# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目是什么

SKG（健康电器品牌）效果广告投放数据聚合平台：定时逆向抓取 4 个第三方投放工具后台（小飞机 smallfighter / 沸点 fifay / 微橙 douyongtuan / 麦斯 maxengine，另有历史平台「博擎」），把各家报表归一为统一指标写入 PostgreSQL，用 FastAPI + Vue 看板展示。业务字段含义（ROI、direct_* 直投归因、平台迁移去重规则等）详见 `docs/业务说明.md`；沸点接口细节在 `docs/沸点报表API对接文档.md`。

数据库表名/平台名/层级名都是中文（如 platform='小飞机'、level='推广账号'），代码注释也是中文，保持这个风格。金额统一存「元」，时间统一上海时区。

## 常用命令

```powershell
# 本地起后端（含每5分钟定时抓取；或双击 启动平台.bat）
cd pipeline; python -m uvicorn app:app --host 0.0.0.0 --port 8770

# 前端开发（vite dev server，/api 代理到 127.0.0.1:8770）
cd pipeline/web; npm run dev
# 前端构建（产物 web/dist 由后端根路径托管，改完前端必须 build 才能在 8770 看到）
cd pipeline/web; npm run build

# 历史回填（断点续跑，已抓的天跳过；或双击 手动回填.bat）
cd pipeline; python backfill.py 2025-01-01

# 手动刷新某账号登录凭证
cd pipeline; python auth_autologin.py <账号ID>   # 密码自动重登（沸点/微橙/麦斯），退出码3=小飞机需人工短信
cd pipeline; python auth_login.py <账号ID>       # 弹浏览器人工登录（Playwright）
```

没有测试、没有 lint。数据库连接一律走环境变量 `DATABASE_URL`（默认 `postgresql://postgres:postgres@localhost:5432/ad_data`）。

## 双实例：本地 + 服务器

本地（Windows，端口 8770，本机 Postgres 5432）和服务器（**生产：120.79.214.225**，Docker，端口 8060 与 80，容器内 db / 宿主机 5433 仅本机）各跑一套完整系统。**改动先在本地做好验证，用户明确说"推到服务器"才部署**；排查报错先分清来自哪套实例。（旧机器 124.223.55.175 已弃用，别再往那部署。）

服务器部署（详见 `docs/运维手册.md` / `docs/DEPLOY.md`）：

```bash
ssh root@120.79.214.225
cd /home/code/china-marketing-board
git pull && docker compose up -d --build app   # 只重建 app，db 不动；多阶段 Dockerfile 会自动构建前端
docker compose logs -f app
```

小飞机账号触发短信验证时用仓库根目录 `小飞机登录.bat`：本地建 SSH 隧道（5433→服务器 db）+ 本地浏览器登录，凭证直接写回服务器库。

## 架构（pipeline/ 全部后端）

数据流：**fetchers.py**（各平台×各层级抓取器，纯 HTTP 逆向接口，归一化为 `DBCOLS` 统一列，只返回 cost>0 的行）→ **db.py**（UPSERT 进 `ad_daily`，主键 `(platform,login_account,level,entity_id,date)`；`dedupe_migrated_accounts()` 按 `MIGRATION_DEDUP` 表清理平台迁移残留行）→ **crawl.py**（滚动窗口抓取：线程池并发、瞬时错误重试、token 失效时子进程调 `auth_autologin.py` 自动重登再重抓）。订单明细是平行的一条链：**order_fetchers.py** → 独立 `orders` 表（逐笔电商订单，主键 `(platform,order_type,order_no)`），挂在同一套定时任务里。

**app.py** 是唯一入口，四合一：

1. **查询/管理 API**（`/api/*`）：看板聚合查询（METRICS 字典定义指标 SQL，比率类按明细重算而非平均）、账号 CRUD、任务与运行记录、订单明细、账户属性 Excel 导入导出。
2. **登录鉴权**：单账户共享（auth_users 表），HMAC 无状态 token，中间件拦所有 `/api/*`（`_PUBLIC_API` 例外）。签名密钥在 `auth_secret.txt`，删了会登出所有人。
3. **定时调度**：APScheduler 进程内调度。任务存 `tasks` 表（每5分钟当日实时 + 每日08:30近15天补数 + 每3小时 token 保活）。**Postgres 建议锁（key 918273645）保证多实例只有一个跑调度**——本地和服务器连不同库所以各自都能调度。启动时 `_ensure_tables()` 自动建/迁移部分表。
4. **前端静态托管**：`web/dist` 挂根路径，API 路由先注册优先匹配。

登录凭证存 `accounts` 表的 auth jsonb（`creds.json` 仅是回退备份）；浏览器登录态在 `pipeline/profiles/`（勿动、勿提交清理）。账号可标记 `is_historical`（不再抓取、数据保留）。

前端 `pipeline/web/`：Vue 3 + Vite + Element Plus + ECharts，页面在 `src/views/`（Dashboard 看板 / AccountBoard 账户看板 / AdvAccounts 账户属性 / Orders 订单明细 / Accounts 账号管理 / Tasks 定时任务），API 封装在 `src/api.js`。

## 注意事项

- **新增数据库表/列必须同时加中文注释**（`COMMENT ON TABLE/COLUMN ... IS '...'`）：同步更新 `pipeline/scripts/comments.sql`（可重复执行的注释脚本），并在**本地 + 服务器两个库**都执行。查漏光标（应为 0）：`SELECT c.relname||'.'||a.attname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace AND n.nspname='public' JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped LEFT JOIN pg_description d ON d.objoid=c.oid AND d.objsubid=a.attnum WHERE c.relkind='r' AND d.description IS NULL;`
- 抓取相关改动要考虑限流：沸点接口有 42901 限流（已做串行化+退避），改 fetchers 时别破坏。
- `归档/` 是历史归档目录，不参与运行。
- 本机有终端安全软件（DLP）会加密部分文件（如 `.gitignore` 读出来是二进制乱码）——遇到"文件损坏/非PK头"类问题先怀疑它，不是代码 bug。
- `creds.json`、`auth_secret.txt`、`ms_token.json`、`profiles/` 含真实凭证，改代码时不要打印/外泄其内容。
