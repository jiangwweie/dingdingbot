"""
v3.0 数据库基础设施

提供异步数据库连接和 Session 管理。
支持 SQLite（开发）和 PostgreSQL（生产）。
"""

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool
from typing import AsyncGenerator, Optional, Union
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


def create_engine(db_url: Optional[str] = None):
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
            echo=os.getenv("SQL_ECHO", "false").lower() == "true",
            pool_size=20,
            max_overflow=40,
        )


# 全局引擎实例（延迟初始化）
_engine: Optional[create_async_engine] = None


def get_engine() -> create_async_engine:
    """获取全局引擎实例"""
    global _engine
    if _engine is None:
        _engine = create_engine()
    return _engine


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


async def close_db():
    """关闭数据库连接"""
    engine = get_engine()
    await engine.dispose()
