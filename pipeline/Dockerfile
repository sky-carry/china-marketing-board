# ---------- 阶段1：构建前端（Vue3 + Vite → 静态 dist）----------
FROM node:20-alpine AS webbuild
WORKDIR /web
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# ---------- 阶段2：Python 运行时（FastAPI 后端 + 托管前端静态）----------
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 TZ=Asia/Shanghai
COPY requirements.txt .
# 国内服务器直连 pypi.org 极慢，使用清华镜像加速
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple --timeout 60 -r requirements.txt
# Playwright + Chromium：服务器端自动重登 沸点/微橙/麦斯（headless，无需人工）；浏览器走 npmmirror 镜像
ENV PLAYWRIGHT_DOWNLOAD_HOST=https://cdn.npmmirror.com/binaries/playwright
# apt 换清华 Debian 镜像（--with-deps 要 apt 装 chromium 系统库；官方源国内极慢）
RUN (sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || true) \
 && (sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list 2>/dev/null || true) \
 && pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple playwright \
 && playwright install --with-deps chromium
# 后端代码
COPY *.py ./
# 前端构建产物（app.py 从 web/dist 托管）
COPY --from=webbuild /web/dist ./web/dist
EXPOSE 8060
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8060", "--log-level", "info"]
