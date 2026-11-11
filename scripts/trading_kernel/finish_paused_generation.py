#!/usr/bin/env python3
"""Offline, stopped-writer cleanup of one authenticated paused source Generation.

This maintenance command uses the normal coordinator and repository. It never
updates state through SQL, changes Owner controls, or dispatches an order.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.trading_kernel.application.coordinate_selection_materialization import (
    CoordinateGenericGenerationRequest,
    coordinate_selection_materialization_once,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork

SOURCE_SCHEMA = "0015_generic_owner_recovery_v1"
SERVICES = (
    "brc-trading-kernel-observation-worker.service",
    "brc-trading-kernel-entry-worker.service",
    "brc-trading-kernel-lifecycle-worker.service",
    "brc-trading-kernel-reconciliation-worker.service",
    "brc-owner-console-api.service",
)


async def finish_paused_source_generation(
    engine: AsyncEngine, *, source_commit: str, generation_id: str,
    expected_policy_version: int, expected_owner_version: int,
) -> dict[str, object]:
    if re.fullmatch(r"[0-9a-f]{40}", source_commit) is None or expected_policy_version < 1 or expected_owner_version < 1:
        raise ValueError("exact source identity and revisions required")
    async with engine.connect() as connection:
        await connection.execute(sa.text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        await connection.execute(sa.text("SET LOCAL statement_timeout='5s'"))
        identity = {str(k): str(v) for k, v in (await connection.execute(sa.text("SELECT metadata_key,metadata_value FROM brc_schema_metadata WHERE metadata_key IN ('runtime_commit','schema_revision')"))).all()}
        revision = await connection.scalar(sa.text("SELECT version_num FROM alembic_version"))
        if revision != SOURCE_SCHEMA or identity != {"runtime_commit": source_commit, "schema_revision": SOURCE_SCHEMA}:
            raise ValueError("exact source database identity changed")
        policy = (await connection.execute(sa.text("SELECT policy_version,new_entry_submit_enabled FROM brc_owner_policy_current WHERE owner_policy_id='policy-main'"))).mappings().one()
        if policy["policy_version"] != expected_policy_version or policy["new_entry_submit_enabled"] is not False:
            raise ValueError("exact globally paused policy required")
        source = (await connection.execute(sa.text("SELECT g.strategy_group_id,g.lifecycle_state,g.fenced_at_ms,c.entry_state,c.control_version FROM brc_strategy_universe_materialization_generations g JOIN brc_strategy_entry_controls_current c USING(strategy_group_id) WHERE g.materialization_generation_id=:id"), {"id": generation_id})).mappings().one()
        if source["strategy_group_id"] not in {"CPM-RO-001", "MI-001", "MPG-001", "BRF2-001"} or source["entry_state"] != "paused" or source["control_version"] != expected_owner_version or source["fenced_at_ms"] is not None or source["lifecycle_state"] not in {"PENDING", "DESIRED", "ABANDONED"}:
            raise ValueError("exact paused unfenced source required")
        for query in (
            "SELECT EXISTS(SELECT 1 FROM brc_trade_tickets WHERE terminal_at_ms IS NULL)",
            "SELECT EXISTS(SELECT 1 FROM brc_positions_current WHERE quantity<>0)",
            "SELECT EXISTS(SELECT 1 FROM brc_exchange_commands WHERE status IN ('prepared','claimed','dispatch_started','outcome_unknown'))",
            "SELECT EXISTS(SELECT 1 FROM brc_runtime_incidents WHERE status='open')",
        ):
            if await connection.scalar(sa.text(query)):
                raise ValueError("source must be flat and free of unresolved runtime work")
        await connection.rollback()
    result = await coordinate_selection_materialization_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(engine),
        request=CoordinateGenericGenerationRequest(materialization_generation_id=generation_id, worker_id="offline-paused-source-maintenance"),
        clock_ms=lambda: int(time.time() * 1000),
    )
    return result.model_dump(mode="json")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--generation-id", required=True)
    parser.add_argument("--expected-policy-version", required=True, type=int)
    parser.add_argument("--expected-owner-version", required=True, type=int)
    args = parser.parse_args()
    try:
        current = Path("/opt/brc/current")
        if (current / ".brc-runtime-commit").read_text().strip() != args.source_commit or (current / ".brc-schema-revision").read_text().strip() != SOURCE_SCHEMA:
            raise ValueError("source release markers differ")
        if not Path("/etc/brc/trading-kernel.write-fenced").is_file():
            raise ValueError("ENTRY fence required")
        for service in SERVICES:
            status = subprocess.run(("systemctl", "is-active", service), capture_output=True, text=True, timeout=10, check=False)
            if status.stdout.strip() not in {"inactive", "failed"}:
                raise ValueError("all five writers must be stopped")
        async def run() -> dict[str, object]:
            engine = create_async_engine(os.environ["TRADING_KERNEL_DATABASE_URL"])
            try:
                return await finish_paused_source_generation(engine, source_commit=args.source_commit,
                    generation_id=args.generation_id, expected_policy_version=args.expected_policy_version,
                    expected_owner_version=args.expected_owner_version)
            finally:
                await engine.dispose()
        print(json.dumps(asyncio.run(run()), sort_keys=True))
        return 0
    except Exception:  # noqa: BLE001 - never expose database credentials in errors.
        print(json.dumps({"status": "blocked", "reason": "paused_source_cleanup_gate_failed"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
