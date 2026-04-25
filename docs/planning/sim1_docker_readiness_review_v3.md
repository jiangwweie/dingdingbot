# Sim-1 模拟盘 Docker 部署就绪度审查报告（修订版 v3）

**审查日期**: 2026-04-25
**审查范围**: /Users/jiangwei/Documents/final
**主线目标**: Sim-1 冻结 runtime（ETH 1h + 4h MTF, LONG-only）进入自然模拟盘观察窗口
**硬约束**:
1. YAML 已彻底废弃，不再作为启动配置来源
2. 前端处于重构期（gemimi-web-front 是重构主线，web-front 是旧前端）
3. 数据库处于 SQLite + PostgreSQL 共存切换期（非全量 PG 迁移）

---

## 当前阶段边界

**前端状态**:
- **旧前端**: `web-front/`（当前 Docker 服务的前端）
- **重构主线**: `gemimi-web-front/`（未在 Docker 中使用）
- **Dockerfile.frontend**: 服务 `web-front/`（`docker/Dockerfile.frontend:11`）

**数据库状态**:
- **execution_intent**: PostgreSQL 强制（Sim-1 要求）
- **orders/positions**: SQLite 默认（可配置为 PG）
- **signals/config**: SQLite（旧链路兼容）
- **v3_dev.db**: 196MB（主数据库）

**Sim-1 主线优先级**:
- **P0**: 后端模拟盘观察路径（backend + readonly observation）
- **P1**: 前端只读观察面（可选，可降级）
- **P2**: 前端切换到 gemimi-web-front（后续重构）

---

## 执行摘要

**Verdict**: **Not Ready** (未就绪)

**核心结论**: 当前仓库**无法**直接 `docker compose up` 成功，存在 **5 个 P0 启动期阻塞项**（backend 相关）。前端问题降级为 P1。修复工作量约 1-2 小时。

**最大风险**: 容器读取错误挂载目录 + 拿不到环境变量，导致 runtime profile not found 和 FatalStartupError。

**重要纠正**（相比 v2 版本）:
- ❌ **P0-NEW-1**: bind mount 路径错误（`./config` → 应为 `../config`）
- ❌ **P0-NEW-2**: dockerfile 路径未同步修改（context 改后 dockerfile 路径也需改）
- ❌ **P0-NEW-3**: 环境变量未注入容器（宿主机 .env 不等于容器内可读）
- ⚠️ **P1-NEW**: 前端仍服务旧前端（web-front），但非 Sim-1 阻塞项

---

## 1. 当前仓库 Docker 部署可行性分析

### ❌ 无法启动成功

**证据**:

| 阻塞项 | 文件:行号 | 问题描述 | 失败阶段 |
|--------|-----------|----------|----------|
| **P0-1** | `docker/docker-compose.yml:14-19` | bind mount 路径错误，挂载到空目录 | 启动期 |
| **P0-2** | `docker/docker-compose.yml:7-8, 61-62` | context 改后 dockerfile 路径未同步（backend + frontend） | 构建期 |
| **P0-3** | `docker/docker-compose.yml:30` + `docker/Dockerfile.backend:42` | 健康检查路径错误（compose + Dockerfile） | 运行期 |
| **P0-4** | `docker/docker-compose.yml:20-26` | 环境变量未注入容器 | 启动期 |
| **P0-5** | `scripts/seed_sim1_runtime_profile.py` | runtime profile 未初始化 | 启动期 |

**详细证据**:

```yaml
# P0-1: bind mount 路径错误
# docker/docker-compose.yml:14-19
volumes:
  - ./config:/app/config:ro  # ❌ 相对 docker/ 目录，应为 ../config
  - ./data:/app/data         # ❌ 相对 docker/ 目录，应为 ../data
  - ./logs:/app/logs         # ❌ 相对 docker/ 目录，应为 ../logs
```

```bash
# 证据：docker/ 目录下不存在 config/data/logs
$ ls -la docker/ | grep -E "config|data|logs"
# 无输出

# 证据：仓库根目录下存在 config/data/logs
$ ls -la . | grep -E "config|data|logs"
drwxr-xr-x    8 jiangwei  staff    256  4月 23 20:55 config
drwxr-xr-x   22 jiangwei  staff    704  4月 24 09:36 data
drwxr-xr-x   15 jiangwei  staff    480  4月 24 16:29 logs
```

```yaml
# P0-2: dockerfile 路径未同步
# docker/docker-compose.yml:7-8
build:
  context: .              # ❌ 应为 ..
  dockerfile: Dockerfile.backend  # ❌ context 改后应为 docker/Dockerfile.backend
```

```yaml
# P0-4: 环境变量未注入
# docker/docker-compose.yml:20-26
environment:
  - TZ=Asia/Shanghai
  - PYTHONPATH=/app
  - DATABASE_URL=sqlite+aiosqlite:///./data/v3_dev.db
  - SQL_ECHO=false
  # ❌ 缺少 PG_DATABASE_URL、EXCHANGE_API_KEY、EXCHANGE_API_SECRET、FEISHU_WEBHOOK_URL、RUNTIME_PROFILE、CORE_EXECUTION_INTENT_BACKEND
```

```python
# P0-5: runtime profile 未初始化
# src/main.py:217
runtime_profile_name = os.environ.get("RUNTIME_PROFILE", "sim1_eth_runtime")
# 如果 data 目录挂载错误，runtime_profile 表不存在
```

---

## 2. 阻塞项分级清单（修订版 v3）

### P0 - Backend 启动期失败（必须修复，阻塞 Sim-1 模拟盘观察）

| ID | 文件:行号 | 问题 | 影响 |
|----|-----------|------|------|
| **P0-1** | `docker/docker-compose.yml:14-19` | bind mount 路径错误 | 容器挂载到空目录，runtime profile not found |
| **P0-2** | `docker/docker-compose.yml:7-8` | backend context/dockerfile 路径错误 | `docker build` 找不到 Dockerfile |
| **P0-3** | `docker/docker-compose.yml:30` + `docker/Dockerfile.backend:42` | backend 健康检查路径错误 | 容器健康检查失败 |
| **P0-4** | `docker/docker-compose.yml:20-26` | 环境变量未注入容器 | FatalStartupError("F-003") |
| **P0-5** | `scripts/seed_sim1_runtime_profile.py` | runtime profile 未初始化 | ValueError("runtime profile not found") |

### P1 - Frontend 相关（不阻塞 backend-only Sim-1 观察链路）

| ID | 文件:行号 | 问题 | 影响 |
|----|-----------|------|------|
| P1-1 | `docker/docker-compose.yml:61-62` | frontend context/dockerfile 路径错误 | frontend 构建失败（不影响 backend） |
| P1-2 | `docker/Dockerfile.frontend:11` | 服务旧前端 web-front，而非重构主线 gemimi-web-front | 前端观察面使用旧版 UI |

### P2 - 环境变量配置（必须配置，但不阻塞构建）

| ID | 文件:行号 | 问题 | 影响 |
|----|-----------|------|------|
| P2-1 | `.env` | 缺少 PostgreSQL 配置 | 需要创建 .env 文件 |
| P2-2 | `.env` | 缺少 Exchange API 密钥 | 需要配置 API 密钥 |

### P3 - 运行期风险（建议修复）

| ID | 文件:行号 | 问题 | 影响 |
|----|-----------|------|------|
| P3-1 | `src/interfaces/api.py:832` | /api/health 端点无依赖检查 | 容器健康检查可能误报 |
| P3-2 | `docker/Dockerfile.backend:27` | `COPY config/` 复制无用文件 | 镜像包含冗余文件 |

---

## 3. 失败阶段分类（修订版 v3）

### 构建期失败（docker build 时立即失败）

- **P0-2**: backend context/dockerfile 路径错误 → `docker build` 找不到 Dockerfile
- **P1-1**: frontend context/dockerfile 路径错误 → frontend 构建失败（不影响 backend）

### 启动期失败（容器启动后进程退出）

- **P0-1**: bind mount 路径错误 → 容器挂载到空目录 → runtime profile not found
- **P0-4**: 环境变量未注入容器 → FatalStartupError("F-003")
- **P0-5**: runtime profile 未初始化 → ValueError("runtime profile not found")
- **P2-1/P2-2**: 缺少环境变量 → FatalStartupError("F-003")

### 运行期风险（启动后可能异常）

- **P0-3**: backend 健康检查路径错误 → 容器健康检查失败
- **P1-2**: frontend 服务旧前端 → 前端观察面使用旧版 UI
- **P3-1**: 健康检查无依赖 → 容器状态误判
- **P3-2**: COPY config/ 冗余 → 镜像包含无用文件

---

## 4. P0 阻塞项详细分析

### P0-1: bind mount 路径错误

**问题**:
```yaml
# docker/docker-compose.yml:14-19
volumes:
  - ./config:/app/config:ro  # ❌ 相对 docker/ 目录
  - ./data:/app/data         # ❌ 相对 docker/ 目录
  - ./logs:/app/logs         # ❌ 相对 docker/ 目录
```

**影响**:
- 容器挂载到 `docker/config`、`docker/data`、`docker/logs`（空目录）
- 实际数据在仓库根目录的 `config/`、`data/`、`logs/`
- runtime profile seed 会失败（`data/v3_dev.db` 不存在）
- SQLite 状态会错位
- 日志目录也会错位

**证据**:
```bash
# docker/ 目录下不存在 config/data/logs
$ ls -la docker/ | grep -E "config|data|logs"
# 无输出

# 仓库根目录下存在 config/data/logs
$ ls -la . | grep -E "config|data|logs"
drwxr-xr-x    8 jiangwei  staff    256  4月 23 20:55 config
drwxr-xr-x   22 jiangwei  staff    704  4月 24 09:36 data
drwxr-xr-x   15 jiangwei  staff    480  4月 24 16:29 logs
```

**修复方案**:
```yaml
volumes:
  - ../config:/app/config:ro  # ✅ 相对仓库根目录
  - ../data:/app/data         # ✅ 相对仓库根目录
  - ../logs:/app/logs         # ✅ 相对仓库根目录
```

### P0-2: backend context/dockerfile 路径错误

**问题**:
```yaml
# docker/docker-compose.yml:7-8 (backend)
build:
  context: .              # ❌ 应为 ..
  dockerfile: Dockerfile.backend  # ❌ context 改后应为 docker/Dockerfile.backend
```

**影响**:
- 如果只改 `context: .` → `context: ..`
- docker-compose 会去仓库根目录找 `Dockerfile.backend`
- 实际文件在 `docker/Dockerfile.backend`
- 构建失败：`failed to solve: failed to read dockerfile`

**修复方案**:
```yaml
# backend
build:
  context: ..                      # ✅ 指向仓库根目录
  dockerfile: docker/Dockerfile.backend  # ✅ 相对仓库根目录
```

### P1-1: frontend context/dockerfile 路径错误（不阻塞 backend）

**问题**:
```yaml
# docker/docker-compose.yml:61-62 (frontend)
build:
  context: .              # ❌ 应为 ..
  dockerfile: Dockerfile.frontend  # ❌ context 改后应为 docker/Dockerfile.frontend
```

**影响**:
- frontend 构建失败
- **不影响 backend-only Sim-1 观察链路**

**修复方案**:
```yaml
# frontend
build:
  context: ..                      # ✅ 指向仓库根目录
  dockerfile: docker/Dockerfile.frontend  # ✅ 相对仓库根目录
```

**说明**: frontend 问题不阻塞 backend，可在 backend 稳定后再修复。

### P0-3: 健康检查路径错误（compose + Dockerfile）

**问题**:
```yaml
# docker/docker-compose.yml:30
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/health"]  # ❌ 应为 /api/health
```

```dockerfile
# docker/Dockerfile.backend:42
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1  # ❌ 应为 /api/health
```

**影响**:
- 容器健康检查失败
- 可能被误判为 unhealthy

**修复方案**:
```yaml
# docker/docker-compose.yml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/api/health"]  # ✅ 改为 /api/health
```

```dockerfile
# docker/Dockerfile.backend
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1  # ✅ 改为 /api/health
```

**问题**:
```yaml
# docker/docker-compose.yml:20-26
environment:
  - TZ=Asia/Shanghai
  - PYTHONPATH=/app
  - DATABASE_URL=sqlite+aiosqlite:///./data/v3_dev.db
  - SQL_ECHO=false
  # ❌ 缺少 Sim-1 必需的环境变量
```

**影响**:
- 容器启动时缺少 `PG_DATABASE_URL`、`EXCHANGE_API_KEY`、`EXCHANGE_API_SECRET`、`FEISHU_WEBHOOK_URL`、`RUNTIME_PROFILE`、`CORE_EXECUTION_INTENT_BACKEND`
- `src/main.py:343` → `FatalStartupError("F-003")`
- `src/main.py:349-351` → `FatalStartupError("F-003")`

**证据**:
```python
# src/main.py:27-30
if load_dotenv is not None:
    repo_root = Path(__file__).resolve().parents[1]
    load_dotenv(repo_root / ".env")
    load_dotenv(repo_root / ".env.local", override=True)
```

**说明**:
- main.py 会尝试 `load_dotenv()`，但容器内 `/app` 目录可能没有 `.env` 文件
- Dockerfile.backend 没有 `COPY .env`
- 在宿主机创建 `.env` 文件不等于容器内能读取

**修复方案**:

**方案 A: 使用 env_file（推荐）**
```yaml
# docker/docker-compose.yml
services:
  backend:
    env_file:
      - ../.env  # ✅ 从宿主机读取 .env 文件
    environment:
      - TZ=Asia/Shanghai
      - PYTHONPATH=/app
```

**方案 B: 显式注入环境变量**
```yaml
# docker/docker-compose.yml
services:
  backend:
    environment:
      - TZ=Asia/Shanghai
      - PYTHONPATH=/app
      - PG_DATABASE_URL=${PG_DATABASE_URL}
      - EXCHANGE_API_KEY=${EXCHANGE_API_KEY}
      - EXCHANGE_API_SECRET=${EXCHANGE_API_SECRET}
      - FEISHU_WEBHOOK_URL=${FEISHU_WEBHOOK_URL}
      - RUNTIME_PROFILE=${RUNTIME_PROFILE:-sim1_eth_runtime}
      - CORE_EXECUTION_INTENT_BACKEND=${CORE_EXECUTION_INTENT_BACKEND:-postgres}
```

**重要**: PostgreSQL DSN 必须使用 `postgresql+asyncpg://` 格式

**证据**:
```bash
# .env.local.example:10-11
# Format: postgresql+asyncpg://USER:PASSWORD@HOST:PORT/DATABASE
PG_DATABASE_URL=postgresql+asyncpg://dingdingbot:dingdingbot_dev@localhost:5432/dingdingbot
```

```python
# src/infrastructure/database.py:10
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
```

**说明**: 项目使用 SQLAlchemy async engine，需要 `asyncpg` 驱动，DSN 必须使用 `postgresql+asyncpg://` 格式。

**推荐配置**:
```bash
PG_DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/v3_sim1
```

---

## 5. YAML 残留专项审查

**结论**: ✅ **YAML 已不参与启动流程**

**证据**:
```python
# src/application/config_manager.py:908
"""Build default core configuration (hardcoded defaults).
No YAML file fallback — DB or defaults only.
"""
```

**残留清单**:
- 启动链路残留: **0 个**（已完全移除）
- 接口残留: **3 个**（导入/导出工具，不影响启动）
- 文档残留: **40+ 个**（误导维护者）
- 注释残留: **4 个**（误导维护者）

**详细清单**: `docs/planning/yaml_deprecation_checklist.md`

---

## 6. Sim-1 容器部署最小必需条件

### 6.1 环境变量（必须配置）

```bash
# Sim-1 强制要求
CORE_EXECUTION_INTENT_BACKEND=postgres

# PostgreSQL 连接
PG_DATABASE_URL=postgresql://user:pass@host:5432/v3_sim1

# 交易所 API（测试网）
EXCHANGE_NAME=binance
EXCHANGE_TESTNET=true
EXCHANGE_API_KEY=your_testnet_api_key
EXCHANGE_API_SECRET=your_testnet_api_secret

# 飞书告警
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxx

# Runtime Profile
RUNTIME_PROFILE=sim1_eth_runtime
```

### 6.2 持久化卷（必须正确挂载）

```yaml
volumes:
  - ../config:/app/config:ro  # ✅ 相对仓库根目录
  - ../data:/app/data         # ✅ 相对仓库根目录
  - ../logs:/app/logs         # ✅ 相对仓库根目录
```

### 6.3 PostgreSQL / SQLite 共存状态

**Sim-1 强制约束**: `CORE_EXECUTION_INTENT_BACKEND=postgres`

```python
# src/application/runtime_config.py:51-54
if self.core_execution_intent_backend != "postgres":
    raise ValueError("Sim-1 requires CORE_EXECUTION_INTENT_BACKEND=postgres")
```

**数据库分工**（SQLite + PostgreSQL 共存）:

| 数据类型 | 默认 Backend | Sim-1 要求 | 环境变量 | 说明 |
|----------|--------------|------------|----------|------|
| execution_intent | **postgres** | **强制 postgres** | `CORE_EXECUTION_INTENT_BACKEND=postgres` | Sim-1 强制要求 |
| orders | sqlite | 可选 postgres | `CORE_ORDER_BACKEND=sqlite` | 默认 SQLite |
| positions | sqlite | 可选 postgres | `CORE_POSITION_BACKEND=sqlite` | 默认 SQLite |
| signals | sqlite | 不涉及 | N/A | 旧链路兼容 |
| config | sqlite | 不涉及 | N/A | 旧链路兼容 |

**证据**:
```python
# src/infrastructure/database.py:42-47
CORE_ORDER_BACKEND = os.getenv("CORE_ORDER_BACKEND", "sqlite").lower()
CORE_EXECUTION_INTENT_BACKEND = os.getenv(
    "CORE_EXECUTION_INTENT_BACKEND",
    _default_execution_intent_backend(),
).lower()
CORE_POSITION_BACKEND = os.getenv("CORE_POSITION_BACKEND", "sqlite").lower()
```

**重要**:
- Sim-1 **不是**全量迁移到 PostgreSQL
- `data/` 目录挂载仍然必需（SQLite 数据库文件）
- v3_dev.db 已有 196MB 数据，需保留

### 6.4 runtime profile seed（必须执行）

**重要**: seed 脚本必须写入宿主机的 `data/` 目录，容器通过 bind mount 读取同一份数据。

**步骤**:

```bash
# 1. 确保 PostgreSQL 已启动并创建数据库
createdb -h localhost -U postgres v3_sim1

# 2. 确认 compose volumes 已修复为 ../data
# docker/docker-compose.yml
volumes:
  - ../data:/app/data  # ✅ 挂载宿主机 data/ 目录

# 3. 在仓库根目录执行 seed 脚本
cd /Users/jiangwei/Documents/final  # ✅ 必须在仓库根目录
python scripts/seed_sim1_runtime_profile.py

# 4. 验证数据已写入
ls -la data/v3_dev.db  # ✅ 确认数据库文件存在
```

**证据**:
```python
# scripts/seed_sim1_runtime_profile.py:83-84
db_path = os.getenv("CONFIG_DB_PATH", "data/v3_dev.db")  # ✅ 相对路径
repo = RuntimeProfileRepository(db_path=db_path)
```

**说明**:
- seed 脚本使用相对路径 `data/v3_dev.db`
- 必须在仓库根目录执行，确保写入宿主机的 `data/` 目录
- 容器通过 `../data:/app/data` bind mount 读取同一份数据
- 如果在错误目录执行，容器启动后会报 `runtime profile not found`

---

## 7. 最小改造方案（修订版 v3）

### 设计原则

1. ✅ **不引入 runtime 可写能力**（保持冻结策略）
2. ✅ **不破坏 research/runtime 隔离**（runtime profile 只读）
3. ✅ **优先 backend 和只读观察面稳定运行**（frontend 可选，可降级）
4. ✅ **承认数据库混合态**（SQLite + PostgreSQL 共存，非全量 PG 迁移）

### 修复步骤（按执行顺序）

#### 阶段 1: 修复 P0 阻塞项（backend，预计 30 分钟）

**Step 1.1: 修复 docker-compose.yml（必须同时修改 6 处）**

```yaml
# docker/docker-compose.yml
services:
  backend:
    build:
      context: ..                      # ✅ 修改 1: context 路径
      dockerfile: docker/Dockerfile.backend  # ✅ 修改 2: dockerfile 路径
    volumes:
      - ../config:/app/config:ro      # ✅ 修改 3: volumes 路径
      - ../data:/app/data
      - ../logs:/app/logs
    env_file:
      - ../.env                        # ✅ 修改 4: 注入环境变量
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/health"]  # ✅ 修改 5: 健康检查路径

  frontend:
    build:
      context: ..                      # ✅ 修改 6: context 路径
      dockerfile: docker/Dockerfile.frontend  # ✅ 修改 7: dockerfile 路径
```

**Step 1.2: 修复 Dockerfile.backend 健康检查**

```dockerfile
# docker/Dockerfile.backend:42
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1  # ✅ 修改 8: 健康检查路径
```

**Step 1.2: 注入环境变量（选择方案 A 或 B）**

**方案 A: 使用 env_file（推荐）**
```yaml
# docker/docker-compose.yml
services:
  backend:
    env_file:
      - ../.env  # ✅ 从宿主机读取 .env 文件
    environment:
      - TZ=Asia/Shanghai
      - PYTHONPATH=/app
```

**方案 B: 显式注入环境变量**
```yaml
# docker/docker-compose.yml
services:
  backend:
    environment:
      - TZ=Asia/Shanghai
      - PYTHONPATH=/app
      - PG_DATABASE_URL=${PG_DATABASE_URL}
      - EXCHANGE_API_KEY=${EXCHANGE_API_KEY}
      - EXCHANGE_API_SECRET=${EXCHANGE_API_SECRET}
      - FEISHU_WEBHOOK_URL=${FEISHU_WEBHOOK_URL}
      - RUNTIME_PROFILE=${RUNTIME_PROFILE:-sim1_eth_runtime}
      - CORE_EXECUTION_INTENT_BACKEND=${CORE_EXECUTION_INTENT_BACKEND:-postgres}
```

#### 阶段 2: 修复 P1 阻塞项（环境变量，预计 1-2 小时）

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

volumes:
  postgres_data:
```

**Step 2.2: 创建 .env 文件**

```bash
# 创建 .env 文件（不要提交到 git）
cat > .env <<EOF
# Sim-1 强制要求
CORE_EXECUTION_INTENT_BACKEND=postgres

# PostgreSQL（必须使用 postgresql+asyncpg:// 格式）
PG_DATABASE_URL=postgresql+asyncpg://v3:v3_password@postgres:5432/v3_sim1

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

**重要**: PostgreSQL DSN 必须使用 `postgresql+asyncpg://` 格式（与 `.env.local.example` 一致）。

**Step 2.3: Seed runtime profile（必须在仓库根目录执行）**

```bash
# 方式 1: 直接运行脚本（必须在仓库根目录）
cd /Users/jiangwei/Documents/final  # ✅ 切换到仓库根目录
python scripts/seed_sim1_runtime_profile.py

# 验证数据已写入
ls -la data/v3_dev.db  # ✅ 确认数据库文件存在

# 方式 2: 在容器启动时自动执行（修改 Dockerfile.backend）
# 在 CMD 之前添加：
# RUN python scripts/seed_sim1_runtime_profile.py
```

**重要**: seed 脚本使用相对路径 `data/v3_dev.db`，必须在仓库根目录执行，确保写入宿主机的 `data/` 目录。容器通过 `../data:/app/data` bind mount 读取同一份数据。

#### 阶段 C: Frontend 选择（P1，可延后）

**当前状态**: Dockerfile.frontend 服务旧前端 `web-front/`

**选项 A: 保持旧前端（快速启动）**
- 不修改 Dockerfile.frontend
- 前端观察面使用旧版 UI
- 优先级: P1（可延后）

**选项 B: 切换到重构主线（gemimi-web-front）**
- 修改 Dockerfile.frontend:
  ```dockerfile
  COPY gemimi-web-front/nginx.conf /etc/nginx/conf.d/default.conf
  COPY gemimi-web-front/dist/ /usr/share/nginx/html/
  ```
- 需要先构建 gemimi-web-front
- 优先级: P2（后续重构）

**选项 C: 暂不启动 frontend**
- 只启动 backend 容器
- 通过 API 或日志观察 Sim-1 状态
- 优先级: P0（当前推荐）

**建议**: Sim-1 观察窗口优先 backend 稳定性，frontend 可暂时不启动或保持旧版。

#### 阶段 D: 验证部署（测试）

```bash
# 构建镜像
docker compose -f docker/docker-compose.yml build

# 启动服务
docker compose -f docker/docker-compose.yml up -d

# 查看日志
docker compose -f docker/docker-compose.yml logs -f backend

# 健康检查
curl http://localhost:8000/api/health

# 验证 runtime profile
docker compose -f docker/docker-compose.yml exec backend \
  python -c "from src.infrastructure.runtime_profile_repository import RuntimeProfileRepository; import asyncio; repo = RuntimeProfileRepository(); asyncio.run(repo.initialize()); profile = asyncio.run(repo.get_profile('sim1_eth_runtime')); print(profile)"
```

---

## 8. Readiness Verdict（修订版 v3）

### 最终判定: **Not Ready** (未就绪)

**理由**:
- ✅ 代码架构支持 Sim-1 冻结策略（runtime_config.py 强制约束）
- ✅ 启动流程完整（main.py Phase 1-9）
- ✅ YAML 不再是启动必需（硬约束已满足）
- ❌ 存在 5 个 P0 启动期阻塞项（必须修复）
- ❌ 容器会读取错误挂载目录（bind mount 路径错误）
- ❌ 容器拿不到环境变量（未注入）

**修复后状态**: **Ready for Sim-1 Observation Window**

---

## 9. 修复 Checklist（按执行顺序）

### ✅ 阶段 A: Backend P0 阻塞项修复（预计 30 分钟）

- [ ] **P0-1**: 修复 bind mount 路径（`./config` → `../config`，`./data` → `../data`，`./logs` → `../logs`）
- [ ] **P0-2**: 修复 backend context 和 dockerfile 路径
  - backend: `context: .` → `context: ..`，`dockerfile: Dockerfile.backend` → `dockerfile: docker/Dockerfile.backend`
- [ ] **P0-3**: 修复 backend 健康检查路径（compose + Dockerfile.backend）
  - compose: `/health` → `/api/health`
  - Dockerfile.backend: `/health` → `/api/health`
- [ ] **P0-4**: 注入环境变量（添加 `env_file: ../.env` 或显式注入）
- [ ] **验证**: `docker compose -f docker/docker-compose.yml build backend` 成功

### ✅ 阶段 B: 环境变量配置（P2，预计 1-2 小时）

- [ ] **P2-1**: 部署 PostgreSQL 或配置外部 PG 连接
- [ ] **P2-1**: 创建 Sim-1 数据库（`createdb v3_sim1`）
- [ ] **P2-2**: 创建 `.env` 文件（使用 `postgresql+asyncpg://` 格式）
- [ ] **P0-5**: 运行 `scripts/seed_sim1_runtime_profile.py`（必须在仓库根目录执行）
- [ ] **验证**: `docker compose -f docker/docker-compose.yml up -d backend` 启动成功

### ⚠️ 阶段 C: Frontend 选择（P1，可延后）

- [ ] **P1-1**: 修复 frontend context 和 dockerfile 路径（如需启动 frontend）
- [ ] **P1-2**: 决定前端方案
  - 选项 A: 保持旧前端 web-front（快速启动）
  - 选项 B: 切换到 gemimi-web-front（需先构建）
  - 选项 C: 暂不启动 frontend（当前推荐）
- [ ] **验证**: 前端观察面可访问（如启动）

### ⚠️ 阶段 D: 运行期优化（P3，可选）

- [ ] **P2-1**: 增强 `/api/health` 端点依赖检查（数据库连接状态）
- [ ] **P2-2**: 移除 `docker/Dockerfile.backend:27` 的 `COPY config/`（可选）
- [ ] **验证**: 模拟盘观察窗口稳定运行 24 小时

---

## 10. 建议修改文件清单

### 必须修改（P0）

| 文件 | 修改类型 | 说明 |
|------|----------|------|
| `docker/docker-compose.yml` | **修改** | 1. backend context 路径<br>2. backend dockerfile 路径<br>3. frontend context 路径<br>4. frontend dockerfile 路径<br>5. volumes 路径<br>6. 健康检查路径<br>7. 环境变量注入 |
| `docker/Dockerfile.backend` | **修改** | 健康检查路径 `/health` → `/api/health` |
| `.env` | **新建** | 环境变量配置（使用 `postgresql+asyncpg://` 格式，不提交 git） |

### 必须执行（P0）

| 脚本 | 说明 |
|------|------|
| `scripts/seed_sim1_runtime_profile.py` | 初始化 runtime profile |

### 可选修改（P2）

| 文件 | 修改类型 | 说明 |
|------|----------|------|
| `src/interfaces/api.py` | **修改** | 增强 `/api/health` 端点依赖检查 |
| `docker/Dockerfile.backend` | **修改** | 移除 `COPY config/`（可选） |

---

## 11. "必须现在修" vs "可以后续清理"

### 必须现在修（阻塞 backend-only Sim-1 部署）

| ID | 问题 | 文件 | 优先级 |
|----|------|------|--------|
| P0-1 | bind mount 路径错误 | `docker/docker-compose.yml` | P0 |
| P0-2 | backend context 和 dockerfile 路径错误 | `docker/docker-compose.yml` | P0 |
| P0-3 | backend 健康检查路径错误 | `docker/docker-compose.yml` + `docker/Dockerfile.backend` | P0 |
| P0-4 | 环境变量未注入容器 | `docker/docker-compose.yml` | P0 |
| P0-5 | runtime profile 未初始化 | `scripts/seed_sim1_runtime_profile.py` | P0 |
| P2-1 | PostgreSQL 配置 + .env 文件 | `.env` | P2 |

### 可延后修复（不阻塞 backend-only Sim-1）

| ID | 问题 | 文件 | 优先级 |
|----|------|------|--------|
| P1-1 | frontend context 和 dockerfile 路径错误 | `docker/docker-compose.yml` | P1 |
| P1-2 | 前端选择（web-front 或 gemimi-web-front） | `docker/Dockerfile.frontend` | P1 |
| P3-1 | 健康检查无依赖检查 | `src/interfaces/api.py` | P3 |
| P3-2 | COPY config/ 冗余 | `docker/Dockerfile.backend` | P3 |

---

## 12. 风险提示

### 🔴 高风险

1. **bind mount 路径错误**: 容器挂载到空目录，runtime profile not found
2. **环境变量未注入**: FatalStartupError("F-003")
3. **PostgreSQL 必须可用**: Sim-1 强制要求，无法降级到 SQLite
4. **API Key 权限检查**: 启动时验证无提现权限
5. **Runtime Profile 冻结**: `is_readonly=True`，研究链无法反向污染

### 🟡 中风险

1. **环境变量泄露**: `.env` 文件需加入 `.gitignore`
2. **数据库迁移**: v3_dev.db 已有 196MB 数据

### 🟢 低风险

1. **YAML 残留注释**: 不影响功能，但可能误导维护者

---

## 13. 关键说明

### YAML 不是启动必需项

**证据**:
```python
# src/application/config_manager.py:908
"""Build default core configuration (hardcoded defaults).
No YAML file fallback — DB or defaults only.
"""
```

**结论**: ✅ YAML 已彻底废弃，不再作为启动配置来源。

### Docker readiness 当前最大风险

**风险 1**: 容器读取错误挂载目录
- bind mount 路径错误（`./config` → 应为 `../config`）
- 导致 runtime profile not found

**风险 2**: 容器拿不到环境变量
- 环境变量未注入容器
- 导致 FatalStartupError("F-003")

**修复优先级**: P0 > P1 > P2

---

**审查完成时间**: 2026-04-25
**审查人**: Claude Code (Sonnet 4.6)
**文档版本**: v3.0 (修订版)
