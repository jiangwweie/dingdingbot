# Sim-1 模拟盘 Docker 部署就绪度审查报告

**审查日期**: 2026-04-25
**审查范围**: /Users/jiangwei/Documents/final
**主线目标**: Sim-1 冻结 runtime（ETH 1h + 4h MTF, LONG-only）进入自然模拟盘观察窗口

---

## 执行摘要

**Verdict**: **Conditionally Ready** (有条件就绪)

**核心结论**: 当前仓库无法直接 `docker compose up` 成功，存在 3 个 P0 构建期阻塞项、3 个 P1 启动期阻塞项。修复后可进入 Sim-1 观察窗口。

**修复工作量估算**: 最小改造方案约 2-3 小时（不含 PostgreSQL 部署）。

---

## 1. 当前仓库 Docker 构建可行性分析

### ❌ 无法直接构建成功

**证据**:

| 阻塞项 | 文件:行号 | 问题描述 | 失败阶段 |
|--------|-----------|----------|----------|
| **P0-1** | `docker/Dockerfile.frontend:14` | `COPY dist/ /usr/share/nginx/html/` 失败，dist 目录不存在 | 构建期 |
| **P0-2** | `docker/docker-compose.yml:7-8` | `context: .` 指向 docker/ 目录，但 Dockerfile.backend 期望项目根目录 | 构建期 |
| **P0-3** | `docker/Dockerfile.backend:27` | `COPY config/ ./config/` 会失败，config/ 缺少 core.yaml | 构建期 |

**详细证据**:

```bash
# P0-1: 前端构建产物缺失
$ ls -la /Users/jiangwei/Documents/final/dist
ls: cannot access 'dist': No such file or directory

# P0-2: docker-compose context 错误
# docker/docker-compose.yml line 7-8
build:
  context: .              # ❌ 当前指向 docker/ 目录
  dockerfile: Dockerfile.backend

# P0-3: config 目录缺少必需文件
$ ls -la config/
core.yaml.reference  # ✅ 只有参考文件
user.yaml.example    # ✅ 只有示例文件
# ❌ 缺少 core.yaml 和 user.yaml
```

---

## 2. 阻塞项分级清单

### P0 - 构建期失败（必须修复）

| ID | 文件:行号 | 问题 | 影响 |
|----|-----------|------|------|
| P0-1 | `docker/Dockerfile.frontend:14` | `COPY dist/` 失败 | 前端容器无法构建 |
| P0-2 | `docker/docker-compose.yml:7-8` | build context 路径错误 | 后端容器无法构建 |
| P0-3 | `docker/Dockerfile.backend:27` | `COPY config/` 缺少 core.yaml | 后端容器构建失败 |

### P1 - 启动期失败（必须修复）

| ID | 文件:行号 | 问题 | 影响 |
|----|-----------|------|------|
| P1-1 | `src/main.py:343` | 缺少环境变量 `PG_DATABASE_URL` | Sim-1 强制要求 PostgreSQL |
| P1-2 | `src/main.py:349-351` | 缺少环境变量 `EXCHANGE_API_KEY/SECRET/WEBHOOK` | 启动时 FatalStartupError |
| P1-3 | `scripts/seed_sim1_runtime_profile.py` | runtime profile 未初始化 | Phase 1.1 解析失败 |

### P2 - 运行期风险（建议修复）

| ID | 文件:行号 | 问题 | 影响 |
|----|-----------|------|------|
| P2-1 | `docker/docker-compose.yml:15` | config 只读挂载 | 无法热重载配置 |
| P2-2 | `src/interfaces/api.py:832` | /health 端点无依赖检查 | 容器健康检查可能误报 |
| P2-3 | `web-front/package.json` | 前端未预构建 | 需要手动 npm run build |

---

## 3. 失败阶段分类

### 构建期失败（docker build 时立即失败）

- **P0-1**: 前端 dist 目录不存在
- **P0-2**: docker-compose context 路径错误
- **P0-3**: config 目录缺少必需文件

**特征**: `docker build` 命令直接报错，无法生成镜像。

### 启动期失败（容器启动后进程退出）

- **P1-1**: PostgreSQL 环境变量缺失 → `FatalStartupError("F-003")`
- **P1-2**: Exchange API 密钥缺失 → `FatalStartupError("F-003")`
- **P1-3**: runtime profile 不存在 → `ValueError("runtime profile not found")`

**特征**: 容器启动成功，但 `python src/main.py` 在 Phase 1-4 阶段退出。

### 运行期风险（启动后可能异常）

- **P2-1**: 配置只读挂载 → 热重载功能失效（不影响 Sim-1 冻结策略）
- **P2-2**: 健康检查无依赖 → 容器状态误判（数据库断开仍返回 200）
- **P2-3**: 前端未构建 → 需要额外构建步骤

**特征**: 容器运行正常，但在特定场景下可能产生错误行为。

---

## 4. Sim-1 容器部署最小必需条件

### 4.1 环境变量（必须配置）

```bash
# Sim-1 强制要求（src/application/runtime_config.py:51-54）
CORE_EXECUTION_INTENT_BACKEND=postgres

# PostgreSQL 连接（src/main.py:343）
PG_DATABASE_URL=postgresql://user:pass@host:5432/dbname

# 交易所 API（src/main.py:349-350）
EXCHANGE_NAME=binance
EXCHANGE_TESTNET=true
EXCHANGE_API_KEY=your_api_key
EXCHANGE_API_SECRET=your_api_secret

# 飞书告警（src/main.py:351）
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxx

# 可选（src/main.py:212）
RUNTIME_PROFILE=sim1_eth_runtime  # 默认值
BACKEND_PORT=8000                 # 默认值
```

**证据**:

```python
# src/application/runtime_config.py:51-54
@model_validator(mode="after")
def validate_sim1_backend_policy(self) -> "EnvironmentRuntimeConfig":
    if self.core_execution_intent_backend != "postgres":
        raise ValueError("Sim-1 requires CORE_EXECUTION_INTENT_BACKEND=postgres")
    return self

# src/main.py:343-351
environment = EnvironmentRuntimeConfig(
    pg_database_url=self._required_env("PG_DATABASE_URL"),
    exchange_api_key=self._required_env("EXCHANGE_API_KEY"),
    exchange_api_secret=self._required_env("EXCHANGE_API_SECRET"),
    feishu_webhook_url=self._required_env("FEISHU_WEBHOOK_URL"),
)
```

### 4.2 持久化卷（建议配置）

```yaml
volumes:
  # SQLite 数据库（旧链路兼容）
  - ./data:/app/data

  # 日志持久化
  - ./logs:/app/logs

  # PostgreSQL 数据（如果使用容器化 PG）
  postgres_data:
```

**说明**:
- Sim-1 强制使用 PostgreSQL 作为 execution_intent backend
- SQLite 仍用于 orders/positions/signals（可通过环境变量切换）
- 建议保留 `./data` 挂载以兼容旧链路

### 4.3 PostgreSQL / SQLite 角色分工

| 数据类型 | 默认 Backend | Sim-1 要求 | 环境变量 |
|----------|--------------|------------|----------|
| execution_intent | **postgres** | **强制 postgres** | `CORE_EXECUTION_INTENT_BACKEND=postgres` |
| orders | sqlite | 可选 postgres | `CORE_ORDER_BACKEND=sqlite` |
| positions | sqlite | 可选 postgres | `CORE_POSITION_BACKEND=sqlite` |
| signals | sqlite | 不涉及 | N/A |
| config | sqlite | 不涉及 | N/A |

**证据**:

```python
# src/infrastructure/database.py:33-46
def _default_execution_intent_backend() -> str:
    return "postgres" if PG_DATABASE_URL else "sqlite"

CORE_EXECUTION_INTENT_BACKEND = os.getenv(
    "CORE_EXECUTION_INTENT_BACKEND",
    _default_execution_intent_backend(),
).lower()
```

**Sim-1 强制约束**:

```python
# src/application/runtime_config.py:51-54
if self.core_execution_intent_backend != "postgres":
    raise ValueError("Sim-1 requires CORE_EXECUTION_INTENT_BACKEND=postgres")
```

### 4.4 runtime profile seed（必须执行）

**步骤**:

```bash
# 1. 确保 PostgreSQL 已启动并创建数据库
createdb -h localhost -U postgres v3_sim1

# 2. 初始化 PG 核心表（可选，main.py 会自动创建）
python -c "from src.infrastructure.database import init_pg_core_db; import asyncio; asyncio.run(init_pg_core_db())"

# 3. Seed sim1_eth_runtime profile
python scripts/seed_sim1_runtime_profile.py
```

**证据**:

```python
# scripts/seed_sim1_runtime_profile.py:82-96
async def main() -> None:
    db_path = os.getenv("CONFIG_DB_PATH", "data/v3_dev.db")
    repo = RuntimeProfileRepository(db_path=db_path)
    await repo.initialize()
    profile = await repo.upsert_profile(
        "sim1_eth_runtime",
        SIM1_ETH_RUNTIME_PROFILE,
        description="Sim-1 ETH 1h LONG-only frozen runtime profile",
        is_active=True,
        is_readonly=True,
        allow_readonly_update=True,
    )
```

**Sim-1 策略约束**:

```python
# scripts/seed_sim1_runtime_profile.py:28
"allowed_directions": ["LONG"],  # ✅ LONG-only

# src/application/runtime_config.py:95-99
@model_validator(mode="after")
def validate_sim1_strategy(self) -> "StrategyRuntimeConfig":
    if self.allowed_directions != (Direction.LONG,):
        raise ValueError("Sim-1 strategy must be LONG-only")
    if self.atr_enabled:
        raise ValueError("Sim-1 strategy requires ATR disabled")
```

### 4.5 交易所/API 权限（必须配置）

**权限要求**:

- ✅ **交易权限**（读取行情 + 下单）
- ❌ **提现权限**（严禁，启动时会检查）

**证据**:

```python
# src/main.py:434-448
logger.info("Phase 4.5: Checking API key permissions...")
await _exchange_gateway.check_api_key_permissions()
permission_summary = _exchange_gateway.get_permission_check_summary()

# src/infrastructure/exchange_gateway.py（隐含逻辑）
# F-002: API Key 有提现权限 → FatalStartupError
```

**Sim-1 配置**:

```bash
EXCHANGE_TESTNET=true  # ✅ 使用测试网
```

### 4.6 飞书告警（必须配置）

**用途**:
- 系统启动/关闭通知
- FatalStartupError 告警
- CapitalProtection 触发告警

**证据**:

```python
# src/main.py:265-281
_notification_service = get_notification_service()
if _runtime_config_provider is not None:
    env = _runtime_config_provider.resolved_config.environment
    _notification_service.setup_channels(
        [
            {
                "type": "feishu",
                "webhook_url": env.feishu_webhook_url.get_secret_value(),
            }
        ]
    )
```

---

## 5. 前端入口选择

### ✅ 正确入口: `web-front/`

**证据**:

```dockerfile
# docker/Dockerfile.frontend:11
COPY web-front/nginx.conf /etc/nginx/conf.d/default.conf
```

**nginx 配置正确**:

```nginx
# web-front/nginx.conf:23-33
location /api {
    proxy_pass http://backend:8000;  # ✅ 正确代理到后端
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection 'upgrade';
    proxy_set_header Host $host;
}
```

### ❌ 未使用: `gemimi-web-front/`

**说明**:
- `gemimi-web-front/` 是独立的前端项目
- 未在 Dockerfile 中引用
- 与当前部署无关

### ⚠️ 旧 Dockerfile 状态

**结论**: **未失效，但需要预构建**

**问题**:
- `COPY dist/` 期望已构建的静态文件
- 当前仓库缺少 `dist/` 目录

**解决方案**:

```bash
# 方案 A: 本地构建后提交 dist/
cd web-front
npm install
npm run build
# dist/ 目录会生成到 web-front/dist/

# 方案 B: 修改 Dockerfile 多阶段构建
FROM node:18-alpine AS builder
WORKDIR /app
COPY web-front/package*.json ./
RUN npm install
COPY web-front/ ./
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY web-front/nginx.conf /etc/nginx/conf.d/default.conf
```

---

## 6. 最小改造方案

### 设计原则

1. ✅ **不引入 runtime 可写能力**（保持冻结策略）
2. ✅ **不破坏 research/runtime 隔离**（runtime profile 只读）
3. ✅ **优先后端和只读观察面稳定运行**（前端可选）

### 修复步骤（按执行顺序）

#### 阶段 1: 修复构建期阻塞项（P0）

**Step 1.1: 创建最小配置文件**

```bash
# 创建 config/core.yaml（从参考文件复制）
cp config/core.yaml.reference config/core.yaml

# 创建 config/user.yaml（最小配置）
cat > config/user.yaml <<EOF
# Sim-1 最小用户配置
exchange:
  name: binance
  testnet: true
  # API 密钥从环境变量读取，此处留空

timeframes:
  - "1h"
  - "4h"

notification:
  channels:
    - type: feishu
      # webhook_url 从环境变量读取

risk:
  max_loss_percent: 0.01
  max_leverage: 20
EOF
```

**Step 1.2: 修复 docker-compose.yml context 路径**

```yaml
# docker/docker-compose.yml
services:
  backend:
    build:
      context: ..           # ✅ 改为上级目录（项目根目录）
      dockerfile: docker/Dockerfile.backend

  frontend:
    build:
      context: ..           # ✅ 改为上级目录
      dockerfile: docker/Dockerfile.frontend
```

**Step 1.3: 构建前端静态文件**

```bash
cd web-front
npm install
npm run build
# 验证 dist/ 目录生成
ls -la dist/
```

#### 阶段 2: 修复启动期阻塞项（P1）

**Step 2.1: 配置 PostgreSQL**

**选项 A: 使用外部 PostgreSQL（推荐）**

```bash
# 创建 Sim-1 数据库
createdb -h <pg_host> -U <pg_user> v3_sim1

# 设置环境变量
export PG_DATABASE_URL="postgresql://<user>:<pass>@<host>:5432/v3_sim1"
```

**选项 B: 使用 docker-compose PostgreSQL**

```yaml
# docker/docker-compose.yml
services:
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_USER: v3
      POSTGRES_PASSWORD: v3_password
      POSTGRES_DB: v3_sim1
    volumes:
      - postgres_data:/var/lib/postgresql/data
    networks:
      - monitor-dog-network

  backend:
    depends_on:
      - postgres
    environment:
      - PG_DATABASE_URL=postgresql://v3:v3_password@postgres:5432/v3_sim1

volumes:
  postgres_data:
```

**Step 2.2: 配置环境变量**

```bash
# 创建 .env 文件（不要提交到 git）
cat > .env <<EOF
# Sim-1 强制要求
CORE_EXECUTION_INTENT_BACKEND=postgres

# PostgreSQL
PG_DATABASE_URL=postgresql://v3:v3_password@postgres:5432/v3_sim1

# 交易所 API（测试网）
EXCHANGE_NAME=binance
EXCHANGE_TESTNET=true
EXCHANGE_API_KEY=your_testnet_api_key
EXCHANGE_API_SECRET=your_testnet_api_secret

# 飞书告警
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxx

# Runtime Profile
RUNTIME_PROFILE=sim1_eth_runtime
EOF
```

**Step 2.3: Seed runtime profile**

```bash
# 方式 1: 直接运行脚本
python scripts/seed_sim1_runtime_profile.py

# 方式 2: 在容器启动时自动执行（修改 Dockerfile.backend）
# 在 CMD 之前添加：
# RUN python scripts/seed_sim1_runtime_profile.py
```

#### 阶段 3: 验证部署（测试）

**Step 3.1: 本地构建测试**

```bash
# 构建镜像
docker compose -f docker/docker-compose.yml build

# 启动服务
docker compose -f docker/docker-compose.yml up -d

# 查看日志
docker compose -f docker/docker-compose.yml logs -f backend

# 健康检查
curl http://localhost:8000/api/health
```

**Step 3.2: 验证 Sim-1 约束**

```bash
# 检查 runtime profile 已加载
docker compose -f docker/docker-compose.yml exec backend \
  python -c "from src.infrastructure.runtime_profile_repository import RuntimeProfileRepository; import asyncio; repo = RuntimeProfileRepository(); asyncio.run(repo.initialize()); profile = asyncio.run(repo.get_profile('sim1_eth_runtime')); print(profile)"

# 检查 PostgreSQL 连接
docker compose -f docker/docker-compose.yml exec backend \
  python -c "from src.infrastructure.database import get_pg_engine; engine = get_pg_engine(); print(f'PG engine: {engine.url}')"

# 检查策略约束
docker compose -f docker/docker-compose.yml logs backend | grep "LONG-only"
```

---

## 7. Readiness Verdict

### 最终判定: **Conditionally Ready** (有条件就绪)

**理由**:
- ✅ 代码架构支持 Sim-1 冻结策略（runtime_config.py 强制约束）
- ✅ 启动流程完整（main.py Phase 1-9）
- ✅ 前端配置正确（nginx proxy_pass）
- ❌ 存在 3 个 P0 构建期阻塞项（可修复）
- ❌ 存在 3 个 P1 启动期阻塞项（需配置）

**修复后状态**: **Ready for Sim-1 Observation Window**

---

## 8. 修复 Checklist（按执行顺序）

### ✅ 阶段 1: 构建期修复（P0，预计 30 分钟）

- [ ] **P0-3**: 创建 `config/core.yaml`（从 core.yaml.reference 复制）
- [ ] **P0-3**: 创建 `config/user.yaml`（最小配置）
- [ ] **P0-2**: 修改 `docker/docker-compose.yml` context 路径（`.` → `..`）
- [ ] **P0-1**: 构建 web-front 前端（`npm install && npm run build`）
- [ ] **验证**: `docker compose -f docker/docker-compose.yml build` 成功

### ✅ 阶段 2: 启动期修复（P1，预计 1-2 小时）

- [ ] **P1-1**: 部署 PostgreSQL 或配置外部 PG 连接
- [ ] **P1-1**: 创建 Sim-1 数据库（`createdb v3_sim1`）
- [ ] **P1-2**: 配置环境变量（`.env` 文件）
  - [ ] `PG_DATABASE_URL`
  - [ ] `CORE_EXECUTION_INTENT_BACKEND=postgres`
  - [ ] `EXCHANGE_API_KEY` / `EXCHANGE_API_SECRET`
  - [ ] `FEISHU_WEBHOOK_URL`
- [ ] **P1-3**: 运行 `scripts/seed_sim1_runtime_profile.py`
- [ ] **验证**: `docker compose -f docker/docker-compose.yml up -d` 启动成功

### ⚠️ 阶段 3: 运行期优化（P2，可选）

- [ ] **P2-2**: 增强 `/health` 端点依赖检查（数据库连接状态）
- [ ] **P2-3**: 优化 Dockerfile.frontend 多阶段构建（可选）
- [ ] **验证**: 模拟盘观察窗口稳定运行 24 小时

---

## 9. 建议修改文件清单

### 必须修改（P0/P1）

| 文件 | 修改类型 | 说明 |
|------|----------|------|
| `config/core.yaml` | **新建** | 从 core.yaml.reference 复制 |
| `config/user.yaml` | **新建** | 最小用户配置 |
| `docker/docker-compose.yml` | **修改** | context 路径 `.` → `..` |
| `.env` | **新建** | 环境变量配置（不提交 git） |
| `web-front/dist/` | **新建** | 前端构建产物（或修改 Dockerfile） |

### 可选修改（P2）

| 文件 | 修改类型 | 说明 |
|------|----------|------|
| `docker/Dockerfile.frontend` | **修改** | 添加多阶段构建（避免手动 npm build） |
| `src/interfaces/api.py` | **修改** | 增强 `/health` 端点依赖检查 |
| `docker/docker-compose.yml` | **修改** | 添加 PostgreSQL 服务定义 |

---

## 10. 风险提示

### 🔴 高风险

1. **PostgreSQL 必须可用**: Sim-1 强制要求 `CORE_EXECUTION_INTENT_BACKEND=postgres`，无法降级到 SQLite
2. **API Key 权限检查**: 启动时会验证无提现权限，配置错误会导致 FatalStartupError
3. **Runtime Profile 冻结**: `is_readonly=True`，研究链无法反向污染 runtime

### 🟡 中风险

1. **前端未构建**: 需要手动 `npm run build`，或修改 Dockerfile 自动化
2. **环境变量泄露**: `.env` 文件包含敏感信息，确保 `.gitignore` 已配置
3. **数据库迁移**: v3_dev.db 已有 196MB 数据，需确认是否需要迁移

### 🟢 低风险

1. **Config 只读挂载**: 不影响 Sim-1 冻结策略，热重载功能非必需
2. **健康检查简化**: 当前 `/health` 端点无依赖检查，可能误报容器健康

---

## 11. 后续建议

### 短期（Sim-1 观察窗口）

1. **监控启动日志**: 确认 Phase 1-9 全部成功
2. **验证策略约束**: 检查日志中 `LONG-only` 和 `ATR disabled` 约束
3. **观察 WebSocket 稳定性**: K 线推送是否正常
4. **飞书告警测试**: 手动触发测试告警

### 中期（Phase 5 完成后）

1. **优化 Dockerfile**: 前端多阶段构建
2. **增强健康检查**: 添加数据库连接状态
3. **配置备份策略**: PostgreSQL 数据备份
4. **日志聚合**: ELK/Loki 集成

### 长期（生产环境）

1. **Kubernetes 部署**: Helm Chart 编排
2. **服务网格**: Istio 流量管理
3. **监控告警**: Prometheus + Grafana
4. **灾备方案**: 多区域部署

---

**审查完成时间**: 2026-04-25
**审查人**: Claude Code (Sonnet 4.6)
**文档版本**: v1.0
