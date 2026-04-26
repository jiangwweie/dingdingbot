# ── Stage 1: Build ────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# ── Stage 2: Serve ───────────────────────────────────────
FROM nginx:alpine

# 默认 nginx 配置（SPA fallback + API 代理）
# 生产环境可通过 volume 覆盖: - ./nginx.conf:/etc/nginx/conf.d/default.conf
COPY nginx.default.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
