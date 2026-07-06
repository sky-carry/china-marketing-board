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

## 已知限制（token 刷新）
- 本镜像**未内置 Playwright/浏览器**，因此**服务器上不能重新登录/自动重登**。
- 迁移过来的 token 有效期约数天；过期后对应账号抓取会停（其它账号不受影响）。
- 刷新办法（二选一，后续可自动化）：
  1. 在有浏览器的机器上跑 `auth_login.py`/`auth_autologin.py`，`DATABASE_URL` 指向本服务器库（需开放/隧道 5432）后写回 token；
  2. 后续给镜像加 headless Playwright + chromium 实现服务器端自动重登（沸点/微橙/麦斯 可密码重登；小飞机需短信，仍需人工）。
