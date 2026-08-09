#!/usr/bin/env python3
"""Probe restored production facts through the Owner Console read-only role."""

from __future__ import annotations

import argparse
import asyncio
import json
import stat
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.owner_console.restore_local_dml_snapshot import (
    validate_local_target,
    verify_snapshot_metadata,
)
from src.trading_kernel.application.owner_console.models import (
    ReviewListQuery,
    SignalListQuery,
    TradeListQuery,
)
from src.trading_kernel.infrastructure.pg_owner_read_repository import (
    PostgresOwnerReadRepository,
    _review_center_ticket_query,
    _signal_list_query,
    _trade_list_query,
    create_owner_read_engine,
    owner_read_transaction,
)

_WINDOW_MS = 90 * 86_400_000
_EXPLAIN_BUDGET_MS = 2_400.0
_REPOSITORY_BUDGET_MS = 3_000.0


def _read_dsn(path: Path, *, database_name: str) -> str:
    status = path.stat()
    if not stat.S_ISREG(status.st_mode):
        raise ValueError("read-role DSN path must be a regular file")
    if status.st_mode & (stat.S_IRGRP | stat.S_IROTH):
        raise ValueError("read-role DSN file must be mode 0600")
    dsn = path.read_text(encoding="utf-8").strip()
    url = make_url(dsn)
    if url.drivername != "postgresql+asyncpg":
        raise ValueError("read-role DSN must use postgresql+asyncpg")
    host = url.host or str(url.query.get("host", ""))
    validate_local_target(host=host, database_name=database_name)
    if url.database != database_name or url.username != "brc_owner_console":
        raise ValueError("read-role DSN identity differs from restored target")
    return dsn


def _window(metadata: dict[str, Any]) -> tuple[int, int]:
    raw_capture = str(metadata["captured_at_utc"])
    try:
        captured_at = datetime.fromisoformat(raw_capture.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("snapshot capture time is invalid") from error
    if captured_at.tzinfo is None:
        raise ValueError("snapshot capture time must include UTC")
    captured_at = captured_at.astimezone(UTC)
    to_ms = int(captured_at.timestamp() * 1_000) + 1
    return to_ms - _WINDOW_MS, to_ms


def _explain_document(raw: object) -> dict[str, Any]:
    payload = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(payload, list) or len(payload) != 1:
        raise RuntimeError("EXPLAIN returned an invalid document")
    document = payload[0]
    if not isinstance(document, dict) or not isinstance(document.get("Plan"), dict):
        raise TypeError("EXPLAIN returned an invalid plan")
    return document


def _plan_flags(node: object) -> tuple[bool, bool]:
    if isinstance(node, list):
        flags = tuple(_plan_flags(item) for item in node)
        return any(flag[0] for flag in flags), any(flag[1] for flag in flags)
    if not isinstance(node, dict):
        return False, False
    node_type = str(node.get("Node Type", ""))
    sort_method = str(node.get("Sort Method", ""))
    child_flags = _plan_flags(node.get("Plans", ()))
    return (
        node_type == "Seq Scan" or child_flags[0],
        "external" in sort_method.lower() or child_flags[1],
    )


async def _explain(
    *,
    engine: AsyncEngine,
    statement: sa.Select[Any],
) -> tuple[float, float, bool, bool]:
    compiled = statement.compile(
        dialect=postgresql.dialect(),
        compile_kwargs={"literal_binds": True},
    )
    sql = "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + str(compiled)
    async with owner_read_transaction(engine) as connection:
        result = await connection.exec_driver_sql(sql)
        document = _explain_document(result.scalar_one())
    sequential_scan, external_sort = _plan_flags(document["Plan"])
    return (
        float(document.get("Planning Time", 0.0)),
        float(document.get("Execution Time", 0.0)),
        sequential_scan,
        external_sort,
    )


async def _repository_read(
    *,
    engine: AsyncEngine,
    query: SignalListQuery | TradeListQuery | ReviewListQuery,
) -> tuple[float, int]:
    started = time.perf_counter()
    async with owner_read_transaction(engine) as connection:
        repository = PostgresOwnerReadRepository(connection)
        if isinstance(query, SignalListQuery):
            returned_rows = len(
                (await repository.read_signal_page_facts(query)).items
            )
        elif isinstance(query, TradeListQuery):
            returned_rows = len(
                (await repository.read_trade_page_facts(query)).items
            )
        else:
            returned_rows = len(
                (await repository.read_review_center_facts(query)).items
            )
    elapsed_ms = (time.perf_counter() - started) * 1_000
    return elapsed_ms, returned_rows


async def run_probes(
    *,
    database_name: str,
    metadata_path: Path,
    read_dsn_path: Path,
) -> list[dict[str, object]]:
    snapshot_path = metadata_path.with_suffix(".sql.gz")
    metadata = verify_snapshot_metadata(
        snapshot_path=snapshot_path,
        metadata_path=metadata_path,
    )
    dsn = _read_dsn(read_dsn_path, database_name=database_name)
    from_ms, to_ms = _window(metadata)
    signal_query = SignalListQuery(from_ms=from_ms, to_ms=to_ms, limit=100)
    trade_query = TradeListQuery(from_ms=from_ms, to_ms=to_ms, limit=100)
    review_query = ReviewListQuery(from_ms=from_ms, to_ms=to_ms, limit=100)
    probes: tuple[
        tuple[
            str,
            SignalListQuery | TradeListQuery | ReviewListQuery,
            sa.Select[Any],
        ],
        ...,
    ] = (
        (
            "signal",
            signal_query,
            _signal_list_query(query=signal_query, cursor=None),
        ),
        (
            "trade",
            trade_query,
            _trade_list_query(query=trade_query, cursor=None),
        ),
        (
            "review",
            review_query,
            _review_center_ticket_query(query=review_query, cursor=None),
        ),
    )
    engine = create_owner_read_engine(dsn)
    results: list[dict[str, object]] = []
    try:
        for name, query, statement in probes:
            planning_ms, execution_ms, sequential_scan, external_sort = await _explain(
                engine=engine,
                statement=statement,
            )
            repository_ms, returned_rows = await _repository_read(
                engine=engine,
                query=query,
            )
            results.append(
                {
                    "query": name,
                    "snapshot_sha256": metadata["sha256"],
                    "source_row_count": metadata["parity_counts"][
                        {
                            "signal": "brc_signal_events",
                            "trade": "brc_trade_tickets",
                            "review": "brc_trade_reviews",
                        }[name]
                    ],
                    "planning_time_ms": round(planning_ms, 3),
                    "execution_time_ms": round(execution_ms, 3),
                    "repository_elapsed_ms": round(repository_ms, 3),
                    "returned_rows": returned_rows,
                    "sequential_scan": sequential_scan,
                    "external_sort": external_sort,
                    "passed": (
                        execution_ms < _EXPLAIN_BUDGET_MS
                        and repository_ms < _REPOSITORY_BUDGET_MS
                    ),
                }
            )
    finally:
        await engine.dispose()
    return results


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-name", required=True)
    parser.add_argument("--snapshot-metadata", required=True, type=Path)
    parser.add_argument("--read-dsn-file", type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    read_dsn_path = args.read_dsn_file or (
        args.snapshot_metadata.parent / f"{args.database_name}.read-dsn"
    )
    results = asyncio.run(
        run_probes(
            database_name=args.database_name,
            metadata_path=args.snapshot_metadata,
            read_dsn_path=read_dsn_path,
        )
    )
    print(json.dumps(results, sort_keys=True, separators=(",", ":")))
    return 0 if all(bool(result["passed"]) for result in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
