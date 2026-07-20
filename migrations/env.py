"""Alembic 迁移环境配置（异步支持）"""

from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool, text
from alembic import context
import asyncio
import os
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

# Import both legacy and PG mappings.  Alembic remains the only production
# schema writer; these metadata objects are used for mapping/drift inspection,
# never by runtime create_all calls.
from src.infrastructure.database import Base
from src.infrastructure.pg_models import PGCoreBase

# 导入模型（确保 metadata 包含所有表）
# from src.domain.models import Account, Signal, Order, Position

# Alembic Config
config = context.config

runtime_database_url = os.getenv("PG_DATABASE_URL") or os.getenv("DATABASE_URL")
if runtime_database_url:
    config.set_main_option("sqlalchemy.url", runtime_database_url)

# 日志配置
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Keep both declarative registries visible to Alembic.  Migration-only objects
# are intentionally handled by the schema capability registry rather than
# being silently created by the application at startup.
target_metadata = (Base.metadata, PGCoreBase.metadata)


def run_migrations_offline() -> None:
    """
    离线模式运行迁移

    不使用真实数据库连接，直接生成 SQL 脚本。
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    在线模式运行迁移

    对于 SQLite（开发环境），使用同步引擎避免 greenlet 冲突。
    对于 PostgreSQL（生产环境），使用异步引擎。
    """
    connectable = config.attributes.get("connection", None)
    url = config.get_main_option("sqlalchemy.url")

    if connectable is None:
        # 判断是否为 SQLite
        if url.startswith("sqlite"):
            # SQLite：使用同步引擎
            connectable = engine_from_config(
                config.get_section(config.config_ini_section, {}),
                prefix="sqlalchemy.",
                poolclass=pool.NullPool,
                future=True,
            )
        else:
            # PostgreSQL/其他：使用异步引擎
            connectable = create_async_engine(
                url,
                poolclass=pool.NullPool,
                future=True,
            )

    # 异步迁移上下文
    if isinstance(connectable, AsyncEngine):
        # 异步引擎：使用 asyncio 运行
        asyncio.run(run_async_migrations(connectable))
    else:
        # 同步连接（SQLite 或离线模式）
        with connectable.begin() as connection:
            # 启用 SQLite 外键检查
            if url.startswith("sqlite"):
                connection.execute(text("PRAGMA foreign_keys = ON"))

            context.configure(
                connection=connection,
                target_metadata=target_metadata,
            )
            context.run_migrations()


async def run_async_migrations(engine: AsyncEngine):
    """异步运行迁移"""
    async with engine.begin() as connection:
        await connection.run_sync(do_run_migrations)

    await engine.dispose()


def do_run_migrations(connection):
    """执行迁移（同步上下文）"""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
    )

    with context.begin_transaction():
        context.run_migrations()


# 模式选择
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
