# 本地 PostgreSQL 开发环境

## Mac mini 快速开始

### 1. 启动 PG 容器

```bash
docker compose -f docker-compose.pg.yml up -d
```

### 2. 配置环境变量

**推荐方式 1：使用 `.env.local`（不提交到 git）**

```bash
# 复制示例文件
cp .env.local.example .env.local

# 加载环境变量
source .env.local
```

**推荐方式 2：使用 shell 环境变量**

```bash
export PG_DATABASE_URL="postgresql+asyncpg://dingdingbot:dingdingbot_dev@localhost:5432/dingdingbot"
export CORE_EXECUTION_INTENT_BACKEND=postgres
export CORE_ORDER_BACKEND=postgres
export CORE_POSITION_BACKEND=postgres
export RUNTIME_PROFILE=sim1_eth_runtime
```

> ⚠️ **重要**：`.env` 已不再被 git 跟踪。真实 secrets（API key、webhook URL）仅放 `.env.local`（不提交到 git）。不要将 `.env` 重新加入 git 跟踪。

### 3. 验证连接

```bash
# 验证配置校验
python3 -c "
from src.infrastructure.database import validate_pg_core_configuration
validate_pg_core_configuration()
print('✅ PG 核心配置校验通过')
"
```

## 前置条件

确保已安装 asyncpg 驱动：

```bash
pip install asyncpg
# 或
pip install -r requirements.txt
```

**Mac mini 特定要求**：
- Docker Desktop for Mac 已安装并运行
- 推荐配置：内存 ≥ 2GB，CPU ≥ 2 核

## 连接串

```
PG_DATABASE_URL=postgresql+asyncpg://dingdingbot:dingdingbot_dev@localhost:5432/dingdingbot
```

> 注意：使用 `postgresql+asyncpg://` 前缀，而非 `postgresql://`

## 当前迁移状态

**Runtime 执行主线已全量 PG 闭环**（2026-04-26 确认）：

| 执行对象 | 后端 | 状态 |
|----------|------|------|
| Orders | PostgreSQL | ✅ `create_runtime_order_repository()` 硬编码 PG |
| Execution Intents | PostgreSQL | ✅ `create_execution_intent_repository()` PG 优先 |
| Positions | PostgreSQL | ✅ `create_runtime_position_repository()` 硬编码 PG |
| Live Signals | PostgreSQL | ✅ `HybridSignalRepository` 路由到 PG |
| Signal Take Profits | PostgreSQL | ✅ `HybridSignalRepository` 路由到 PG |
| Execution Recovery | PostgreSQL | ✅ `PgExecutionRecoveryRepository` |

**仍在 SQLite 的对象**（详见 `docs/planning/2026-04-26-system-truth-and-sqlite-triage.md`）：
- Config 全套（strategies/risk_configs/system_configs/symbols/notifications 等）
- Runtime Profiles
- Signal Attempts（可观测性）
- Backtest 全链路

> ⚠️ 以下旧版三阶段迁移计划**已完成**，仅保留作历史参考。

---

## ~~当前推荐切换策略~~（已完成）

~~当前阶段推荐按以下顺序小范围实切：~~

1. ~~**先切 `CORE_EXECUTION_INTENT_BACKEND=postgres`**~~ → ✅ 已完成
2. ~~**`CORE_ORDER_BACKEND` 暂时保持 `sqlite`**~~ → ✅ 已切换到 postgres
3. ~~**`CORE_POSITION_BACKEND` 继续保持 `sqlite` / 未启用**~~ → ✅ 已切换到 postgres

## 常用操作

### 查看日志

```bash
docker logs dingdingbot-pg
```

### 进入容器 CLI

```bash
docker exec -it dingdingbot-pg psql -U dingdingbot -d dingdingbot
```

### 停止服务

```bash
docker compose -f docker-compose.pg.yml down
```

### 清理数据（重置数据库）

```bash
docker compose -f docker-compose.pg.yml down -v
```

### 检查容器状态

```bash
docker ps | grep dingdingbot-pg
```

### 检查健康状态

```bash
docker inspect dingdingbot-pg | grep -A 10 "Health"
```

## 连接信息

| 项目 | 值 |
|------|-----|
| Host | localhost |
| Port | 5432 |
| Database | dingdingbot |
| User | dingdingbot |
| Password | dingdingbot_dev |

## CLI 连接

```bash
docker exec -it dingdingbot-pg psql -U dingdingbot -d dingdingbot
```

## 验证初始化链

```bash
# 设置环境变量
export PG_DATABASE_URL="postgresql+asyncpg://dingdingbot:dingdingbot_dev@localhost:5432/dingdingbot"
export CORE_EXECUTION_INTENT_BACKEND=postgres
export CORE_ORDER_BACKEND=postgres
export CORE_POSITION_BACKEND=postgres
export RUNTIME_PROFILE=sim1_eth_runtime
# 当前阶段全部使用 PG：
# export CORE_ORDER_BACKEND=postgres  # 已默认
# export CORE_POSITION_BACKEND=postgres  # 已默认

# 验证配置校验
python3 -c "
from src.infrastructure.database import validate_pg_core_configuration
validate_pg_core_configuration()
print('✅ PG 核心配置校验通过')
"

# 验证引擎创建
python3 -c "
from src.infrastructure.database import get_pg_engine, get_pg_session_maker
engine = get_pg_engine()
sm = get_pg_session_maker()
print('✅ PG 引擎和 sessionmaker 创建成功')
"

# 验证 repository 初始化
python3 -c "
import asyncio
from src.infrastructure.pg_order_repository import PgOrderRepository
from src.infrastructure.pg_execution_intent_repository import PgExecutionIntentRepository
from src.infrastructure.pg_position_repository import PgPositionRepository

async def test_init():
    order_repo = PgOrderRepository()
    intent_repo = PgExecutionIntentRepository()
    position_repo = PgPositionRepository()
    await order_repo.initialize()
    await intent_repo.initialize()
    await position_repo.initialize()
    print('✅ 所有 PG repository 初始化成功')

asyncio.run(test_init())
"
```
