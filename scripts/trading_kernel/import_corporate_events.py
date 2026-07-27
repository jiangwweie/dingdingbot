#!/usr/bin/env python3
"""Import versioned corporate-event coverage from a reviewed JSON document."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
import time

from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import create_async_engine


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading_kernel.domain.corporate_events import (  # noqa: E402
    CorporateEvent,
    CorporateEventCoverage,
)
from src.trading_kernel.application.apply_corporate_event_authority import (  # noqa: E402
    ApplyCorporateEventAuthorityRequest,
    apply_corporate_event_authority,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import (  # noqa: E402
    PostgresKernelUnitOfWork,
)


class CorporateEventImport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_name: str
    coverage: CorporateEventCoverage
    events: tuple[CorporateEvent, ...]


async def _run(
    database_url: str,
    imports: tuple[CorporateEventImport, ...],
    *,
    observed_at_ms: int,
) -> int:
    engine = create_async_engine(database_url)
    try:
        async with PostgresKernelUnitOfWork(engine) as uow:
            for item in imports:
                await apply_corporate_event_authority(
                    uow,
                    ApplyCorporateEventAuthorityRequest(
                        coverage=item.coverage,
                        events=item.events,
                        source_name=item.source_name,
                        observed_at_ms=observed_at_ms,
                    ),
                )
        print(f'{{"imported_instrument_count":{len(imports)}}}')
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
    parser.add_argument("--observed-at-ms", type=int)
    args = parser.parse_args(argv)
    database_url = args.database_url.strip()
    if not database_url.startswith("postgresql+asyncpg://"):
        parser.error("database URL must use postgresql+asyncpg")
    payload = json.loads(args.input_json.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        parser.error("input JSON must be an array")
    imports = tuple(CorporateEventImport.model_validate(item) for item in payload)
    return asyncio.run(
        _run(
            database_url,
            imports,
            observed_at_ms=args.observed_at_ms or int(time.time() * 1_000),
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
