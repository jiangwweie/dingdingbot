# 盯盘狗 🐶 Docker 模拟盘部署指南

> **最后更新**: 2026-04-26
> **适用版本**: v3.0 Phase 5 (sim1_eth_runtime)

---

## 架构概览

```
┌─────────────────────────────────────────────────────────┐
│  docker-compose.yml (后端 + PG)                          │
│                                                         │
│  ┌──────────────┐    ┌──────────────────────────────┐   │
│  │  PostgreSQL   │◄──│  Backend (FastAPI + uvicorn)  │   │
│  │  16-alpine    │   │  python src/main.py           │   │
│  │  :5432        │   │  :8000                        │   │
│  └──────────────┘    └──────────────────────────────┘   │
│                                                         │
│  Network: dingdingbot-net                               │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  docker-compose.frontend.yml (前端，可插拔)              │
│                                                         │
│  ┌──────────────────────────────┐                       │
│  │  Frontend (nginx + React)    │                       │
│  │  :5173 → :80                 │                       │
│  │  proxy /api/ → backend:8000  │                       │
│  └──────────────────────────────┘                       │
│                                                         │
│  Network: dingdingbot-net (external)                    │
└─────────────────────────────────────────────────────────┘
```

**设计原则**：
- 后端 + PG 为核心栈，前端可插拔独立部署
- 前端通过 nginx 反向代理访问后端 API
- 修改 `docker/nginx.conf` 中的 `proxy_pass` 即可切换后端地址

---

## 快速启动

### 1. 启动后端 + PostgreSQL

```bash
cd docker
docker compose up -d
```

等待后端健康检查通过（约 30s）：

```bash
docker compose ps
# 两个容器 STATUS 均为 (healthy) 即启动成功
```

### 2. 启动前端（可选）

```bash
# 确保后端网络已创建
docker network ls | grep dingdingbot

# 启动前端
docker compose -f docker-compose.frontend.yml up -d
```

### 3. 验证

```bash
# 后端健康检查
curl http://localhost:8000/api/runtime/health | python3 -m json.tool

# 前端访问
open http://localhost:5173
```

---

## 目录结构

```
docker/
├── docker-compose.yml              # 后端 + PG 核心栈
├── docker-compose.frontend.yml     # 前端独立部署（可插拔）
├── Dockerfile.backend              # 后端镜像（两阶段构建）
├── Dockerfile.frontend             # 前端镜像（已废弃，改用 gemimi-web-front/Dockerfile）
├── nginx.conf                      # 前端 nginx 配置（API 代理 + SPA fallback）
└── .env.docker                     # 敏感环境变量（已 .gitignore）

gemimi-web-front/
├── Dockerfile                      # 前端镜像（两阶段构建）
└── nginx.default.conf              # 镜像内默认 nginx 配置
```

**宿主机挂载**：

| 容器路径 | 宿主机路径 | 用途 |
|---------|-----------|------|
| `/app/data` | `../data` | SQLite 数据库、配置快照 |
| `/app/logs` | `../logs` | 应用日志 |
| `/var/lib/postgresql/data` | `pg_data` (Docker volume) | PG 数据持久化 |

---

## 环境变量说明

### 后端核心变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `PG_DATABASE_URL` | - | PostgreSQL 连接串（容器内用服务名 `postgres`） |
| `PG_SSL_DISABLED` | `false` | 设为 `true` 禁用 SSL（Docker 内网必须） |
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/v3_dev.db` | SQLite 主库路径 |
| `RUNTIME_PROFILE` | `sim1_eth_runtime` | 运行时配置档案 |
| `CORE_EXECUTION_INTENT_BACKEND` | 自动检测 | `postgres` 或 `sqlite` |
| `CORE_ORDER_BACKEND` | `sqlite` | `postgres` 或 `sqlite` |
| `CORE_POSITION_BACKEND` | `sqlite` | `postgres` 或 `sqlite` |
| `EXCHANGE_NAME` | - | 交易所名称（`binance`） |
| `EXCHANGE_TESTNET` | `false` | 是否使用测试网 |
| `EXCHANGE_API_KEY` | - | 交易所 API Key |
| `EXCHANGE_API_SECRET` | - | 交易所 API Secret |
| `FEISHU_WEBHOOK_URL` | - | 飞书通知 Webhook |

### 自动检测逻辑

- `CORE_EXECUTION_INTENT_BACKEND`：当 `PG_DATABASE_URL` 已配置时，默认为 `postgres`；否则为 `sqlite`
- `CORE_ORDER_BACKEND` / `CORE_POSITION_BACKEND`：默认 `sqlite`，需显式设置为 `postgres`

---

## 运维操作

### 查看日志

```bash
# 后端实时日志
docker compose logs -f backend

# PG 日志
docker compose logs -f postgres

# 前端日志
docker compose -f docker-compose.frontend.yml logs -f frontend
```

### 重启

```bash
# 重启后端
docker compose restart backend

# 完全重建（代码变更后）
docker compose down
docker compose build --no-cache backend
docker compose up -d
```

### 清空 PG 数据

```bash
# 进入 PG 容器
docker compose exec postgres psql -U dingdingbot -d dingdingbot

# 清空核心表
TRUNCATE execution_intents, orders, positions CASCADE;
```

### 删除 PG 重建

```bash
docker compose down
docker volume rm docker_pg_data
docker compose up -d
```

### 健康检查

```bash
# 后端健康状态
curl -sf http://localhost:8000/api/runtime/health | python3 -m json.tool

# 关键字段：
#   pg_status: OK
#   exchange_status: OK
#   notification_status: DEGRADED (testnet 正常)
```

---

## 踩坑记录

### 1. PG 容器与后端不在同一网络

**现象**：后端日志报 `ConnectionError: unexpected connection_lost() call` 或 `ConnectionDoesNotExistError`

**根因**：docker-compose.yml 中 postgres 服务没有声明 `networks`，默认加入 `docker_default` 网络；而 backend 声明了 `dingdingbot-net`。两个容器在不同子网，无法通信。

**修复**：给 postgres 服务显式添加 `networks: [dingdingbot-net]`

```yaml
postgres:
  # ...
  networks:
    - dingdingbot-net  # 必须与 backend 在同一网络
```

**诊断方法**：

```bash
# 检查容器所在网络和 IP
docker inspect dingdingbot-pg --format '{{json .NetworkSettings.Networks}}'
docker inspect dingdingbot-backend --format '{{json .NetworkSettings.Networks}}'

# 如果 PG 在 172.19.x.x，backend 在 172.20.x.x → 网络隔离
```

### 2. asyncpg SSL 升级失败

**现象**：asyncpg 连接 PG 时报 `ConnectionError: unexpected connection_lost() call`，堆栈指向 `_create_ssl_connection`

**根因**：asyncpg 默认 `sslmode=prefer`，即使传入 `ssl=None` 也会被覆盖为 `prefer`（源码 `_parse_connect_dsn_and_args` 第 244 行）。`prefer` 模式先尝试 SSL 握手，PG 容器未配置 SSL 导致握手失败。

**修复**（三重保险）：

1. **PG_DATABASE_URL 添加 `?ssl=disable`**：asyncpg 解析 DSN query 参数设置 sslmode
2. **`PG_SSL_DISABLED=true` 环境变量**：`database.py` 中将 `ssl=None` 传入 `connect_args`
3. **asyncpg 版本锁定 `<0.31.0`**：0.31.0 有已知 SSL 行为变更

```yaml
environment:
  - PG_DATABASE_URL=postgresql+asyncpg://dingdingbot:dingdingbot_dev@postgres:5432/dingdingbot?ssl=disable
  - PG_SSL_DISABLED=true
```

```txt
# requirements.txt
asyncpg>=0.29.0,<0.31.0
```

**关键认知**：asyncpg 的 `ssl=None` 参数 ≠ 禁用 SSL。`None` 表示"未指定"，asyncpg 会回退到 `PGSSLMODE` 环境变量，最终默认 `prefer`。只有 `ssl=False` 或 DSN 中 `sslmode=disable` 才真正禁用。

### 3. python-multipart 缺失

**现象**：后端启动到 Phase 9（API 服务器）时崩溃，报 `RuntimeError: Form data requires "python-multipart" to be installed`

**根因**：FastAPI 从某个版本起将 `python-multipart` 从自动依赖改为可选依赖。项目 `api.py` 中有 `@app.post("/api/config/import")` 端点使用了 `UploadFile`，需要 `python-multipart`。

**修复**：在 `requirements.txt` 中添加 `python-multipart>=0.0.6`

### 4. Dockerfile 两阶段构建优化

**原问题**：单阶段构建每次代码变更都重新安装全部 pip 依赖，构建耗时 2-3 分钟。

**优化**：改为两阶段构建（builder + runtime），依赖安装与代码复制分离：

```dockerfile
# Stage 1: Install dependencies
FROM python:3.11-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: Runtime
FROM python:3.11-slim
COPY --from=builder /install /usr/local
COPY src/ src/
COPY config/ config/
```

**效果**：代码变更时只需重新执行 Stage 2（< 5s），依赖不变时 Stage 1 使用缓存。

### 5. 前端 Dockerfile 构建上下文问题

**现象**：`COPY docker/nginx.conf` 和 `COPY gemimi-web-front/` 失败

**根因**：Docker 构建上下文（build context）决定了 COPY 指令能访问的文件范围。当 `context: ../gemimi-web-front` 时，只能访问该目录内的文件，无法引用 `docker/nginx.conf`。

**修复**：将 Dockerfile 放在 `gemimi-web-front/` 目录下，nginx 默认配置也放在该目录。生产环境通过 volume 挂载覆盖：

```yaml
volumes:
  - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro
```

---

## 启动阶段说明

后端 `main.py` 启动流程（Phase 1-9）：

| Phase | 说明 | 依赖 |
|-------|------|------|
| 1 | ConfigManager 初始化 | SQLite |
| 1.1 | RuntimeConfigResolver 解析运行时配置 | SQLite runtime_profiles |
| 1.5 | Signal 数据库初始化 | SQLite |
| 2 | 配置快照准备 | - |
| 3 | 通知渠道初始化 | FEISHU_WEBHOOK_URL |
| 4 | ExchangeGateway 初始化 | Binance API |
| 4.2 | 启动对账 | PG |
| 4.3 | 对账执行 | PG |
| 4.4 | Circuit breaker 重建 | PG |
| 4.5 | API Key 权限检查 | Binance sapi (testnet 跳过) |
| 5 | SignalPipeline 创建 | Runtime config |
| 6 | 历史数据预热 | Binance OHLCV |
| 7 | 资产轮询启动 | Binance |
| 8 | WebSocket 订阅 | Binance WS |
| 9 | REST API 服务器启动 | python-multipart |

**SYSTEM READY** 出现在 Phase 8 之后，Phase 9 是 API 服务器启动。

---

## sim1_eth_runtime 配置档案

| 参数 | 值 |
|------|-----|
| 交易对 | ETH/USDT:USDT |
| 主周期 | 1h |
| MTF 周期 | 4h |
| 允许方向 | LONG only |
| 触发器 | Pinbar (min_wick_ratio=0.6, max_body_ratio=0.3) |
| 过滤器 | EMA50 + MTF EMA60 |
| TP 目标 | [1.0R, 3.5R] |
| TP 比例 | [50%, 50%] |
| 最大杠杆 | 20x |
| 单笔最大亏损 | 1% |
| 每日最大亏损 | 0.1% |
| 每日最大交易数 | 10 |
| 预热K线数 | 100 |
