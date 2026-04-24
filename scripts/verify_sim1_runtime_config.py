#!/usr/bin/env python3
"""
Verify Sim-1 runtime config resolution without starting trading.

This script checks only config parsing, validation, and hash generation.
"""

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from src.application.runtime_config import RuntimeConfigResolver
from src.infrastructure.connection_pool import close_all_connections
from src.infrastructure.runtime_profile_repository import RuntimeProfileRepository


async def main() -> None:
    db_path = os.getenv("CONFIG_DB_PATH", "data/v3_dev.db")
    profile_name = os.getenv("RUNTIME_PROFILE", "sim1_eth_runtime")

    repo = RuntimeProfileRepository(db_path=db_path)
    try:
        await repo.initialize()
        resolver = RuntimeConfigResolver(repo)
        resolved = await resolver.resolve(profile_name)
    finally:
        await repo.close()
        await close_all_connections()

    print("✅ Sim-1 runtime config resolved")
    print(f"   profile={resolved.profile_name}")
    print(f"   version={resolved.version}")
    print(f"   config_hash={resolved.config_hash}")
    print()
    print(json.dumps(resolved.to_safe_summary(), ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
