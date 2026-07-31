#!/usr/bin/env python3
"""Append exact SOR v2 historical evidence classifications to terminal Reviews."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

from sqlalchemy.ext.asyncio import create_async_engine

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading_kernel.application.classify_sor_v2_history import (
    ClassifySorV2HistoryRequest,
    classify_sor_v2_history,
)
from src.trading_kernel.domain.review import SorV2HistoryClassification
from src.trading_kernel.infrastructure.pg_unit_of_work import (
    PostgresKernelUnitOfWork,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.getenv("TRADING_KERNEL_DATABASE_URL", ""),
        help="PostgreSQL SQLAlchemy URL; defaults to TRADING_KERNEL_DATABASE_URL",
    )
    parser.add_argument(
        "--ticket-id",
        action="append",
        required=True,
        help="Exact terminal SOR v2 Ticket; repeat for one classification set",
    )
    parser.add_argument(
        "--classification",
        required=True,
        choices=tuple(item.value for item in SorV2HistoryClassification),
    )
    parser.add_argument("--classified-at-ms", type=int)
    return parser


async def _run(args: argparse.Namespace) -> int:
    database_url = str(args.database_url or "").strip()
    if not database_url.startswith("postgresql+asyncpg://"):
        raise ValueError("database URL must use postgresql+asyncpg")
    ticket_ids = tuple(dict.fromkeys(str(item).strip() for item in args.ticket_id))
    if not ticket_ids or any(not ticket_id for ticket_id in ticket_ids):
        raise ValueError("classification requires non-blank exact Ticket identities")
    classified_at_ms = args.classified_at_ms or int(time.time() * 1_000)
    classification = SorV2HistoryClassification(args.classification)
    engine = create_async_engine(database_url)
    try:
        async with PostgresKernelUnitOfWork(engine) as uow:
            results = [
                await classify_sor_v2_history(
                    uow,
                    ClassifySorV2HistoryRequest(
                        ticket_id=ticket_id,
                        classification=classification,
                        classified_at_ms=classified_at_ms + index,
                    ),
                )
                for index, ticket_id in enumerate(ticket_ids)
            ]
        print(
            json.dumps(
                {
                    "schema": "brc.trading_kernel.sor_v2_history_classification.v1",
                    "status": "pass",
                    "classification": classification.value,
                    "results": [
                        result.model_dump(mode="json") for result in results
                    ],
                },
                sort_keys=True,
            )
        )
        return 0
    finally:
        await engine.dispose()


def main() -> None:
    raise SystemExit(asyncio.run(_run(_parser().parse_args())))


if __name__ == "__main__":
    main()
