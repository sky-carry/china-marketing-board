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
RUN pip install --no-cache-dir -r requirements.txt
# 后端代码
COPY *.py ./
# 前端构建产物（app.py 从 web/dist 托管）
COPY --from=webbuild /web/dist ./web/dist
EXPOSE 8060
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8060", "--log-level", "info"]
