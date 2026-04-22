# 本地 PostgreSQL 开发环境

## 前置条件

确保已安装 asyncpg 驱动：

```bash
pip install asyncpg
# 或
pip install -r requirements.txt
```

## 启动 PG 容器

```bash
docker compose -f docker-compose.pg.yml up -d
```

## 环境变量配置

**推荐：使用 shell 环境变量（不依赖 .env）**

```bash
export PG_DATABASE_URL="postgresql+asyncpg://dingdingbot:dingdingbot_dev@localhost:5432/dingdingbot"
export CORE_ORDER_BACKEND=postgres
export CORE_EXECUTION_INTENT_BACKEND=postgres
export CORE_POSITION_BACKEND=postgres
```

**备选：在 .env 中配置**

在 `.env` 中取消注释即可启用。

## 连接串

```
PG_DATABASE_URL=postgresql+asyncpg://dingdingbot:dingdingbot_dev@localhost:5432/dingdingbot
```

> 注意：使用 `postgresql+asyncpg://` 前缀，而非 `postgresql://`

## 停止

```bash
docker compose -f docker-compose.pg.yml down
```

## 清理数据（重置数据库）

```bash
docker compose -f docker-compose.pg.yml down -v
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
export CORE_ORDER_BACKEND=postgres
export CORE_EXECUTION_INTENT_BACKEND=postgres
export CORE_POSITION_BACKEND=postgres

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
