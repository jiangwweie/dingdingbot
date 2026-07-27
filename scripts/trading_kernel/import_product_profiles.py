#!/usr/bin/env python3
"""Import reviewed U.S.-equity perpetual product profiles from JSON."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
import time

from pydantic import BaseModel, ConfigDict, JsonValue
from sqlalchemy.ext.asyncio import create_async_engine


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading_kernel.domain.product_admission import ProductProfile  # noqa: E402
from src.trading_kernel.infrastructure.pg_unit_of_work import (  # noqa: E402
    PostgresKernelUnitOfWork,
)


class ProductProfileImport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    profile: ProductProfile
    source_payload: dict[str, JsonValue]


async def _run(
    database_url: str,
    imports: tuple[ProductProfileImport, ...],
    *,
    updated_at_ms: int,
) -> int:
    engine = create_async_engine(database_url)
    inserted = 0
    try:
        async with PostgresKernelUnitOfWork(engine) as uow:
            for item in imports:
                inserted += int(
                    await uow.product_admission.upsert_product_profile(
                        item.profile,
                        source_payload=item.source_payload,
                        updated_at_ms=updated_at_ms,
                    )
                )
        print(f'{{"inserted_profile_count":{inserted}}}')
        return 0
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.getenv("TRADING_KERNEL_DATABASE_URL", ""),
    )
    parser.add_argument("--input-json", type=Path, required=True)
    parser.add_argument("--updated-at-ms", type=int)
    args = parser.parse_args(argv)
    database_url = args.database_url.strip()
    if not database_url.startswith("postgresql+asyncpg://"):
        parser.error("database URL must use postgresql+asyncpg")
    payload = json.loads(args.input_json.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        parser.error("input JSON must be an array")
    imports = tuple(ProductProfileImport.model_validate(item) for item in payload)
    return asyncio.run(
        _run(
            database_url,
            imports,
            updated_at_ms=args.updated_at_ms or int(time.time() * 1_000),
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
