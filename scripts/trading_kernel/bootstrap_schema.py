#!/usr/bin/env python3
"""Upgrade an empty PostgreSQL database to the trading-kernel baseline."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from alembic import command
from alembic.config import Config


REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_CONFIG = REPO_ROOT / "migrations" / "trading_kernel" / "alembic.ini"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.getenv("TRADING_KERNEL_DATABASE_URL", ""),
        help="PostgreSQL SQLAlchemy URL; defaults to TRADING_KERNEL_DATABASE_URL",
    )
    args = parser.parse_args()
    database_url = args.database_url.strip()
    if not database_url.startswith("postgresql+asyncpg://"):
        parser.error("database URL must use postgresql+asyncpg")

    os.environ["TRADING_KERNEL_DATABASE_URL"] = database_url
    config = Config(str(ALEMBIC_CONFIG))
    command.upgrade(config, "head")
    print("trading kernel schema is at head")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
