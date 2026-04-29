# v3 Phase 0 - 技术选型报告

**创建日期**: 2026-03-30
**阶段**: Phase 0 - v3 准备
**负责人**: Backend Dev

---

## 1. 技术选型总览

| 技术领域 | 选型方案 | 理由 |
|---------|---------|------|
| ORM | SQLAlchemy 2.0 async | 异步支持 + Alembic 集成 |
| 迁移工具 | Alembic | 行业标准，可回滚 |
| 数据库 | SQLite (开发) / PostgreSQL (生产) | 轻量 vs 高并发 |
| 并发控制 | asyncio.Lock + 数据库行级锁 | 双层保护 |

---

## 2. SQLAlchemy 2.0 async

### 2.1 选型理由

1. **异步原生支持**: `async_sessionmaker` + `AsyncSession`
2. **Alembic 集成**: 官方支持，迁移脚本自动生成
3. **类型友好**: 与 Pydantic v2 配合良好
4. **向后兼容**: 可逐步迁移现有代码

### 2.2 核心依赖

```toml
# requirements.txt
sqlalchemy>=2.0.0
aiosqlite>=0.19.0  # SQLite 异步驱动
asyncpg>=0.29.0    # PostgreSQL 异步驱动（生产环境）
alembic>=1.13.0    # 数据库迁移工具
```

### 2.3 配置示例

```python
# src/infrastructure/database.py
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

# 开发环境：SQLite
DATABASE_URL = "sqlite+aiosqlite:///./v3_dev.db"

# 生产环境：PostgreSQL
# DATABASE_URL = "postgresql+asyncpg://user:password@localhost/v3_prod"

engine = create_async_engine(DATABASE_URL, echo=True)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)

async def get_db() -> AsyncSession:
    async with async_session_maker() as session:
        yield session
```

---

## 3. Alembic 迁移工具

### 3.1 选型理由

1. **行业标准**: SQLAlchemy 官方迁移工具
2. **可回滚**: 自动生成 downgrade 脚本
3. **版本控制**: 迁移版本追踪
4. **异步支持**: 支持异步数据库操作

### 3.2 目录结构

```
migrations/
├── versions/
│   ├── 001_unify_direction_enum.py
│   ├── 002_create_orders_positions.py
│   └── ...
├── env.py
└── script.py.mako
```

### 3.3 配置示例

```python
# alembic.ini
[alembic]
script_location = migrations
sqlalchemy.url = sqlite+aiosqlite:///./v3_dev.db

# migrations/env.py
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context

config = context.config
target_metadata = Base.metadata  # 导入 SQLAlchemy Base

def run_migrations_online():
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
    )
    # 异步迁移逻辑
```

---

## 4. 数据库选型

### 4.1 开发环境：SQLite

| 优势 | 说明 |
|------|------|
| 零配置 | 无需安装数据库服务 |
| 轻量 | 单文件数据库 |
| 测试友好 | 易于创建/销毁 |

### 4.2 生产环境：PostgreSQL

| 优势 | 说明 |
|------|------|
| 高并发 | 支持高并发读写 |
| 行级锁 | `SELECT FOR UPDATE` 支持 |
| JSON 支持 | 灵活的数据结构 |

### 4.3 兼容性策略

使用 SQLAlchemy 抽象层，代码层面无需修改：
- 开发：`sqlite+aiosqlite://`
- 生产：`postgresql+asyncpg://`

---

## 5. 并发安全设计

### 5.1 双层锁机制

```python
# 第一层：asyncio Lock（进程内）
_position_locks: Dict[str, asyncio.Lock] = {}

async with _position_locks[position_id]:
    # 第二层：数据库行级锁（跨进程）
    async with db.begin():
        position = await db.execute(
            select(Position).where(Position.id == position_id).with_for_update()
        )
        # 临界区操作
```

### 5.2 场景对比

| 场景 | 锁类型 | 作用范围 |
|------|--------|---------|
| 单进程并发 | asyncio.Lock | 协程同步 |
| 多进程并发 | 数据库行级锁 | 跨进程同步 |
| 极端行情 | 双层锁 | 全面保护 |

---

## 6. 依赖版本锁定

```txt
# requirements.txt (精确版本)
sqlalchemy==2.0.25
aiosqlite==0.19.0
asyncpg==0.29.0
alembic==1.13.1
```

---

## 7. 开发环境搭建

### 7.1 Docker Compose（开发）

```yaml
version: '3.8'
services:
  app:
    build: .
    volumes:
      - .:/app
      - ./v3_dev.db:/app/data/v3_dev.db
    environment:
      - DATABASE_URL=sqlite+aiosqlite:///./data/v3_dev.db
    ports:
      - "8000:8000"

  # 可选：PostgreSQL（生产环境模拟）
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_USER: v3
      POSTGRES_PASSWORD: v3_password
      POSTGRES_DB: v3_prod
    ports:
      - "5432:5432"
```

### 7.2 本地开发

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 初始化数据库
alembic upgrade head

# 3. 运行应用
python src/main.py
```

---

## 8. 技术验证清单

| 验证项 | 状态 | 备注 |
|--------|------|------|
| SQLAlchemy async 连接 | ⏳ | Phase 0 完成 |
| Alembic 迁移脚本 | ⏳ | Phase 0 完成 |
| SQLite/PostgreSQL 兼容 | ⏳ | Phase 0 完成 |
| asyncio.Lock 测试 | ⏳ | Phase 5 完成 |
| 数据库行级锁测试 | ⏳ | Phase 5 完成 |

---

## 9. 下一步行动

- [ ] 创建 `requirements.txt` 更新
- [ ] 创建 `src/infrastructure/database.py`
- [ ] 创建 Alembic 配置
- [ ] 编写数据库迁移脚本
- [ ] 编写单元测试验证连接

---

*本技术选型报告作为 Phase 0 的技术决策依据。*
