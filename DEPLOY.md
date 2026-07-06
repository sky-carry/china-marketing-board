# 部署说明（Docker）

## 架构
- **db**：`postgres:18-alpine`，库名 `ad_data`，数据存于命名卷 `cmb_pgdata`（不对外暴露端口）。
- **app**：`pipeline/Dockerfile` 多阶段构建（Node 构建前端 → Python 运行 FastAPI），监听 **8060**，同时托管前端静态页与 `/api/*`。
- 后端通过环境变量 `DATABASE_URL` 连库（compose 内指向 `db` 服务）。

## 首次部署
```bash
# 1) 起数据库
docker compose up -d db
# 2) 等 db healthy 后，导入数据（含历史明细 + 登录凭证）
gunzip -c ad_data.sql.gz | docker compose exec -T db psql -U postgres -d ad_data
# 3) 起应用
docker compose up -d --build app
```
访问：`http://<服务器IP>:8060`

## 日常运维
```bash
docker compose ps                 # 查看状态
docker compose logs -f app        # 看后端日志（含定时抓取）
docker compose up -d --build app  # 更新代码后重建
docker compose restart app        # 重启
```
备份数据库：
```bash
docker compose exec -T db pg_dump -U postgres ad_data | gzip > backup_$(date +%F).sql.gz
```

## 定时抓取
应用启动后自带调度器（Postgres 建议锁保证多实例只跑一个）：
- 每 5 分钟滚动抓当日；每日 08:30 补近 15 天。
- 使用库里 `accounts` 表已存的 token 抓取（纯 HTTP，无需浏览器）。

## Token 刷新
镜像已内置 Playwright + Chromium（headless）。

- **沸点 / 微橙 / 麦斯**：纯账号密码，**服务器全自动刷新**——应用调度每 3 小时保活一次、抓取失败也会自动重登，无需人工。
  手动触发某账号：`docker compose exec app python auth_autologin.py <账号ID>`
- **小飞机**：需短信验证码，无法全自动。会话失效时标记 `need_login`，用**本地登录**写回服务器库：
  1. 本机运行仓库根目录的 `小飞机登录.bat`（Windows），按提示输入账号ID；
  2. 它自动建 SSH 隧道到服务器库(127.0.0.1:5433) → 本地开浏览器登录+短信 → 凭证写回服务器库。
  - 原理：`DATABASE_URL=postgresql://postgres:postgres@localhost:5433/ad_data` + `ssh -N -L 5433:127.0.0.1:5433 root@服务器`，本地跑 `auth_login.py <id>`。

内存：Chromium 重登瞬时约 +300–500MB，已给服务器加 2G swap 兜底，避免 OOM 影响其它容器。
