"""
v3.0 数据库基础设施

提供异步数据库连接和 Session 管理。
当前同时支持：
- 旧链路默认数据库（保留 SQLite 兼容）
- PG 核心链路新增实现（双轨迁移）
"""

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import StaticPool
from typing import AsyncGenerator, Optional
import os


class Base(DeclarativeBase):
    """SQLAlchemy 模型基类"""
    pass


# 数据库 URL 配置
# 开发环境：SQLite
# 生产环境：PostgreSQL
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite+aiosqlite:///./data/v3_dev.db"
)

PG_DATABASE_URL = os.getenv("PG_DATABASE_URL")


def _default_execution_intent_backend() -> str:
    """
    当前推荐的小范围实切策略：
    - 配置了 PG_DATABASE_URL 时，ExecutionIntent 默认走 postgres
    - orders / positions 仍保持 sqlite，避免一次性扩大切换面
    """
    return "postgres" if PG_DATABASE_URL else "sqlite"


CORE_ORDER_BACKEND = os.getenv("CORE_ORDER_BACKEND", "sqlite").lower()
CORE_EXECUTION_INTENT_BACKEND = os.getenv(
    "CORE_EXECUTION_INTENT_BACKEND",
    _default_execution_intent_backend(),
).lower()
CORE_POSITION_BACKEND = os.getenv("CORE_POSITION_BACKEND", "sqlite").lower()


def _get_positive_int_env(name: str, default: int) -> int:
    """读取正整数环境变量，非法值回退默认值。"""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _build_pg_engine_kwargs() -> dict:
    """构建 PostgreSQL engine 配置。

    单实例执行主链的主要目标是避免：
    1. 连接失活后长时间悬挂；
    2. SQL 在持锁区内无限等待，拖住业务锁。
    """
    command_timeout_seconds = _get_positive_int_env("PG_COMMAND_TIMEOUT_SECONDS", 15)
    statement_timeout_ms = _get_positive_int_env("PG_STATEMENT_TIMEOUT_MS", 15000)
    lock_timeout_ms = _get_positive_int_env("PG_LOCK_TIMEOUT_MS", 5000)
    idle_tx_timeout_ms = _get_positive_int_env("PG_IDLE_TX_TIMEOUT_MS", 15000)
    pool_timeout_seconds = _get_positive_int_env("PG_POOL_TIMEOUT_SECONDS", 10)

    return {
        "echo": os.getenv("SQL_ECHO", "false").lower() == "true",
        "pool_pre_ping": True,
        "pool_recycle": 1800,
        "pool_timeout": pool_timeout_seconds,
        "connect_args": {
            "command_timeout": command_timeout_seconds,
            "server_settings": {
                "statement_timeout": str(statement_timeout_ms),
                "lock_timeout": str(lock_timeout_ms),
                "idle_in_transaction_session_timeout": str(idle_tx_timeout_ms),
            },
        },
    }


def create_engine(db_url: Optional[str] = None) -> AsyncEngine:
    """
    创建异步数据库引擎

    SQLite 配置：
    - connect_args={'check_same_thread': False}: 允许多线程访问
    - poolclass=StaticPool: 单连接池（SQLite 简单性）

    PostgreSQL 配置：
    - pool_size: 连接池大小
    - max_overflow: 最大溢出连接数
    """
    if db_url is None:
        db_url = DATABASE_URL

    # SQLite 特殊配置
    if db_url.startswith("sqlite"):
        return create_async_engine(
            db_url,
            echo=os.getenv("SQL_ECHO", "false").lower() == "true",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    else:
        # PostgreSQL 配置
        return create_async_engine(
            db_url,
            pool_size=20,
            max_overflow=40,
            **_build_pg_engine_kwargs(),
        )


# 全局引擎实例（延迟初始化）
_engine: Optional[AsyncEngine] = None
_pg_engine: Optional[AsyncEngine] = None
_pg_async_session_maker: Optional[async_sessionmaker[AsyncSession]] = None


def get_engine() -> AsyncEngine:
    """获取全局引擎实例"""
    global _engine
    if _engine is None:
        _engine = create_engine()
    return _engine


def create_pg_engine(db_url: Optional[str] = None) -> AsyncEngine:
    """创建 PG 专用引擎。

    双轨迁移阶段，核心表的新实现统一走 PG_DATABASE_URL。
    """
    resolved_url = db_url or PG_DATABASE_URL
    if not resolved_url:
        raise ValueError("PG_DATABASE_URL 未配置，无法初始化 PostgreSQL 核心链路")
    if not resolved_url.startswith("postgresql"):
        raise ValueError(f"PG_DATABASE_URL 必须是 PostgreSQL DSN，当前为: {resolved_url}")
    return create_async_engine(
        resolved_url,
        pool_size=10,
        max_overflow=20,
        **_build_pg_engine_kwargs(),
    )


def get_core_backend_settings() -> dict[str, str]:
    """获取核心链路后端配置。"""
    return {
        "order": CORE_ORDER_BACKEND,
        "execution_intent": CORE_EXECUTION_INTENT_BACKEND,
        "position": CORE_POSITION_BACKEND,
    }


def validate_pg_core_configuration() -> None:
    """严格校验 PG 核心链路配置。

    仅当任一核心后端明确设置为 `postgres` 时才要求 `PG_DATABASE_URL`。
    默认 SQLite 链路不受影响。
    """
    backends = get_core_backend_settings()
    invalid = {name: backend for name, backend in backends.items() if backend not in {"sqlite", "postgres"}}
    if invalid:
        raise ValueError(
            "核心后端配置非法，允许值仅为 sqlite/postgres: "
            + ", ".join(f"{name}={backend}" for name, backend in invalid.items())
        )

    if "postgres" not in backends.values():
        return

    if not PG_DATABASE_URL:
        raise ValueError(
            "PG_DATABASE_URL 未配置，但核心后端已选择 postgres；请显式配置 PostgreSQL DSN"
        )

    if not PG_DATABASE_URL.startswith("postgresql"):
        raise ValueError(
            f"PG_DATABASE_URL 必须是 PostgreSQL DSN，当前为: {PG_DATABASE_URL}"
        )


def get_pg_engine() -> AsyncEngine:
    """获取 PG 核心链路全局引擎。"""
    global _pg_engine
    if _pg_engine is None:
        _pg_engine = create_pg_engine()
    return _pg_engine


# Session Factory
async_session_maker = async_sessionmaker(
    get_engine(),
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    获取数据库 Session（依赖注入用）

    用法:
        @app.get("/api/v3/accounts/{id}")
        async def get_account(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """初始化数据库（创建所有表）"""
    from src.infrastructure.database import Base
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def init_pg_core_db() -> None:
    """初始化 PG 核心表。

    仅创建迁移阶段新增 PG 真源需要的核心表。
    """
    from src.infrastructure.pg_models import PGCoreBase

    engine = get_pg_engine()
    async with engine.begin() as conn:
        await conn.run_sync(PGCoreBase.metadata.create_all)


def get_pg_session_maker() -> async_sessionmaker[AsyncSession]:
    """返回 PG 核心链路 sessionmaker。"""
    global _pg_async_session_maker
    if _pg_async_session_maker is None:
        _pg_async_session_maker = async_sessionmaker(
            get_pg_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
    return _pg_async_session_maker


async def probe_pg_connectivity(
    session_maker: Optional[async_sessionmaker[AsyncSession]] = None,
) -> bool:
    """轻量探测 PG 连通性。

    优先使用注入的 session_maker；失败时返回 False。
    """
    try:
        maker = session_maker or get_pg_session_maker()
        async with maker() as session:
            await session.execute(text("SELECT 1"))
        return True
    except (ValueError, SQLAlchemyError, OSError):
        return False


async def close_db():
    """关闭数据库连接并复位可重建的全局 PG 资源。

    迁移阶段需要支持同进程内多次 startup/shutdown：
    - 不在 shutdown 时隐式创建新的 engine
    - PG dispose 后显式清空 engine/sessionmaker，下一次 startup 可重新初始化
    - SQLite 旧链路继续复用模块级 sessionmaker，不在本轮扩大 reset 范围
    """
    global _pg_engine, _pg_async_session_maker

    if _engine is not None:
        await _engine.dispose()

    if _pg_engine is not None:
        await _pg_engine.dispose()
        _pg_engine = None

    if _pg_async_session_maker is not None:
        _pg_async_session_maker = None
