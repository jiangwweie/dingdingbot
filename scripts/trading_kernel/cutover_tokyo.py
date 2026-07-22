#!/usr/bin/env python3
"""Run the crash-safe, resume-safe destructive Tokyo kernel cutover."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from enum import StrEnum
import inspect
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import AsyncContextManager, Protocol, cast

from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.trading_kernel.verify_flat_cutover import (  # noqa: E402
    CutoverFactsAdapter,
    CutoverPlan,
    CutoverVerification,
    build_plan_from_args,
    load_cutover_adapter,
    verify_cutover_facts,
)


OPS_SCHEMA = "brc_cutover_ops"


class CutoverPhase(StrEnum):
    PLAN_IDENTITIES = "plan_identities"
    FENCE_EXCHANGE_WRITES = "fence_exchange_writes"
    STOP_OLD_WRITERS = "stop_old_writers"
    VERIFY_FINAL_FLAT = "verify_final_flat"
    CREATE_SHORT_LIVED_SNAPSHOT = "create_short_lived_snapshot"
    REBUILD_APPLICATION_SCHEMA = "rebuild_application_schema"
    SEED_CURRENT_AUTHORITY = "seed_current_authority"
    DEPLOY_EXACT_RELEASE = "deploy_exact_release"
    CERTIFY_SCHEMA_AND_READONLY = "certify_schema_and_readonly"
    ENABLE_OBSERVATION_MONITOR = "enable_observation_monitor"
    CERTIFY_SIGNAL_TO_TICKET_NO_WRITE = "certify_signal_to_ticket_no_write"
    CERTIFY_ENTRY_FENCED = "certify_entry_fenced"


CUTOVER_PHASES = (
    CutoverPhase.PLAN_IDENTITIES,
    CutoverPhase.FENCE_EXCHANGE_WRITES,
    CutoverPhase.STOP_OLD_WRITERS,
    CutoverPhase.VERIFY_FINAL_FLAT,
    CutoverPhase.CREATE_SHORT_LIVED_SNAPSHOT,
    CutoverPhase.REBUILD_APPLICATION_SCHEMA,
    CutoverPhase.SEED_CURRENT_AUTHORITY,
    CutoverPhase.DEPLOY_EXACT_RELEASE,
    CutoverPhase.CERTIFY_SCHEMA_AND_READONLY,
    CutoverPhase.ENABLE_OBSERVATION_MONITOR,
    CutoverPhase.CERTIFY_SIGNAL_TO_TICKET_NO_WRITE,
    CutoverPhase.CERTIFY_ENTRY_FENCED,
)


class CutoverBlocked(RuntimeError):
    def __init__(self, blockers: tuple[str, ...]) -> None:
        self.blockers = blockers
        super().__init__(",".join(blockers))


class CutoverResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: str
    cutover_id: str
    completed_phases: tuple[CutoverPhase, ...]


class CutoverPhaseRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    phase: CutoverPhase
    phase_order: int
    status: str
    attempt_count: int
    started_at_ms: int | None
    completed_at_ms: int | None
    last_error: str | None


class CutoverJournalSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    cutover_id: str
    run_status: str
    server_id: str
    database_identity: str
    venue_id: str
    account_id: str
    runtime_profile_id: str
    application_schema: str
    target_commit: str
    target_schema_revision: str
    target_seed_identity: str
    target_release_id: str
    phases: tuple[CutoverPhaseRecord, ...]

    def phase_status(self, phase: CutoverPhase) -> str | None:
        return next(
            (record.status for record in self.phases if record.phase is phase),
            None,
        )


class CutoverAdapter(CutoverFactsAdapter, Protocol):
    async def apply_phase(self, phase: CutoverPhase, plan: CutoverPlan) -> None: ...

    async def phase_satisfied(
        self,
        phase: CutoverPhase,
        plan: CutoverPlan,
    ) -> bool: ...


class CutoverJournal(Protocol):
    def run_lock(self, cutover_id: str) -> AsyncContextManager[None]: ...

    async def ensure_run(self, plan: CutoverPlan, *, now_ms: int) -> None: ...

    async def phase_status(
        self,
        cutover_id: str,
        phase: CutoverPhase,
    ) -> str | None: ...

    async def mark_phase_started(
        self,
        cutover_id: str,
        phase: CutoverPhase,
        *,
        phase_order: int,
        now_ms: int,
    ) -> None: ...

    async def mark_phase_completed(
        self,
        cutover_id: str,
        phase: CutoverPhase,
        *,
        now_ms: int,
    ) -> None: ...

    async def mark_phase_failed(
        self,
        cutover_id: str,
        phase: CutoverPhase,
        *,
        error: str,
        now_ms: int,
    ) -> None: ...

    async def mark_run_completed(self, cutover_id: str, *, now_ms: int) -> None: ...


class PostgresCutoverJournal:
    def __init__(self, database_url: str) -> None:
        if not database_url.startswith("postgresql+asyncpg://"):
            raise ValueError("journal database URL must use postgresql+asyncpg")
        self._engine: AsyncEngine = create_async_engine(database_url)

    async def close(self) -> None:
        await self._engine.dispose()

    async def _ensure_schema(self) -> None:
        async with self._engine.begin() as connection:
            await connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {OPS_SCHEMA}"))
            await connection.execute(
                text(
                    f"""
                    CREATE TABLE IF NOT EXISTS {OPS_SCHEMA}.cutover_runs (
                        cutover_id TEXT PRIMARY KEY,
                        server_id TEXT NOT NULL,
                        database_identity TEXT NOT NULL,
                        venue_id TEXT NOT NULL,
                        account_id TEXT NOT NULL,
                        runtime_profile_id TEXT NOT NULL,
                        application_schema TEXT NOT NULL,
                        target_commit TEXT NOT NULL,
                        target_schema_revision TEXT NOT NULL,
                        target_seed_identity TEXT NOT NULL,
                        target_release_id TEXT NOT NULL,
                        status TEXT NOT NULL,
                        created_at_ms BIGINT NOT NULL,
                        updated_at_ms BIGINT NOT NULL
                    )
                    """
                )
            )
            await connection.execute(
                text(
                    f"""
                    CREATE TABLE IF NOT EXISTS {OPS_SCHEMA}.cutover_phases (
                        cutover_id TEXT NOT NULL REFERENCES
                            {OPS_SCHEMA}.cutover_runs(cutover_id) ON DELETE CASCADE,
                        phase TEXT NOT NULL,
                        phase_order INTEGER NOT NULL,
                        status TEXT NOT NULL,
                        attempt_count INTEGER NOT NULL,
                        started_at_ms BIGINT NULL,
                        completed_at_ms BIGINT NULL,
                        last_error TEXT NULL,
                        PRIMARY KEY (cutover_id, phase)
                    )
                    """
                )
            )

    @asynccontextmanager
    async def run_lock(self, cutover_id: str) -> AsyncIterator[None]:
        await self._ensure_schema()
        async with self._engine.connect() as connection:
            acquired = bool(
                (
                    await connection.execute(
                        text("SELECT pg_try_advisory_lock(hashtext(:cutover_id))"),
                        {"cutover_id": cutover_id},
                    )
                ).scalar_one()
            )
            if not acquired:
                raise CutoverBlocked(("cutover_already_running",))
            try:
                yield
            finally:
                await connection.execute(
                    text("SELECT pg_advisory_unlock(hashtext(:cutover_id))"),
                    {"cutover_id": cutover_id},
                )

    async def ensure_run(self, plan: CutoverPlan, *, now_ms: int) -> None:
        await self._ensure_schema()
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    f"""
                    INSERT INTO {OPS_SCHEMA}.cutover_runs (
                        cutover_id,
                        server_id,
                        database_identity,
                        venue_id,
                        account_id,
                        runtime_profile_id,
                        application_schema,
                        target_commit,
                        target_schema_revision,
                        target_seed_identity,
                        target_release_id,
                        status,
                        created_at_ms,
                        updated_at_ms
                    ) VALUES (
                        :cutover_id,
                        :server_id,
                        :database_identity,
                        :venue_id,
                        :account_id,
                        :runtime_profile_id,
                        :application_schema,
                        :target_commit,
                        :target_schema_revision,
                        :target_seed_identity,
                        :target_release_id,
                        'running',
                        :now_ms,
                        :now_ms
                    )
                    ON CONFLICT (cutover_id) DO NOTHING
                    """
                ),
                {
                    "cutover_id": plan.cutover_id,
                    "server_id": plan.server_id,
                    "database_identity": plan.database_identity,
                    "venue_id": plan.venue_id,
                    "account_id": plan.account_id,
                    "runtime_profile_id": plan.runtime_profile_id,
                    "application_schema": plan.application_schema,
                    "target_commit": plan.target_commit,
                    "target_schema_revision": plan.target_schema_revision,
                    "target_seed_identity": plan.target_seed_identity,
                    "target_release_id": plan.target_release_id,
                    "now_ms": now_ms,
                },
            )
            row = (
                await connection.execute(
                    text(
                        f"""
                        SELECT server_id,
                               database_identity,
                               venue_id,
                               account_id,
                               runtime_profile_id,
                               application_schema,
                               target_commit,
                               target_schema_revision,
                               target_seed_identity,
                               target_release_id
                          FROM {OPS_SCHEMA}.cutover_runs
                         WHERE cutover_id = :cutover_id
                        """
                    ),
                    {"cutover_id": plan.cutover_id},
                )
            ).mappings().one()
        actual = (
            str(row["server_id"]),
            str(row["database_identity"]),
            str(row["venue_id"]),
            str(row["account_id"]),
            str(row["runtime_profile_id"]),
            str(row["application_schema"]),
            str(row["target_commit"]),
            str(row["target_schema_revision"]),
            str(row["target_seed_identity"]),
            str(row["target_release_id"]),
        )
        expected = (
            plan.server_id,
            plan.database_identity,
            plan.venue_id,
            plan.account_id,
            plan.runtime_profile_id,
            plan.application_schema,
            plan.target_commit,
            plan.target_schema_revision,
            plan.target_seed_identity,
            plan.target_release_id,
        )
        if actual != expected:
            raise CutoverBlocked(("cutover_identity_conflict",))

    async def phase_status(
        self,
        cutover_id: str,
        phase: CutoverPhase,
    ) -> str | None:
        await self._ensure_schema()
        async with self._engine.connect() as connection:
            value = (
                await connection.execute(
                    text(
                        f"""
                        SELECT status
                          FROM {OPS_SCHEMA}.cutover_phases
                         WHERE cutover_id = :cutover_id
                           AND phase = :phase
                        """
                    ),
                    {"cutover_id": cutover_id, "phase": phase.value},
                )
            ).scalar_one_or_none()
        return None if value is None else str(value)

    async def mark_phase_started(
        self,
        cutover_id: str,
        phase: CutoverPhase,
        *,
        phase_order: int,
        now_ms: int,
    ) -> None:
        await self._upsert_phase(
            cutover_id,
            phase,
            phase_order=phase_order,
            status="started",
            now_ms=now_ms,
            error=None,
        )

    async def mark_phase_completed(
        self,
        cutover_id: str,
        phase: CutoverPhase,
        *,
        now_ms: int,
    ) -> None:
        await self._update_phase(
            cutover_id,
            phase,
            status="completed",
            now_ms=now_ms,
            error=None,
        )

    async def mark_phase_failed(
        self,
        cutover_id: str,
        phase: CutoverPhase,
        *,
        error: str,
        now_ms: int,
    ) -> None:
        await self._update_phase(
            cutover_id,
            phase,
            status="failed",
            now_ms=now_ms,
            error=_sanitize_error(error),
        )

    async def _upsert_phase(
        self,
        cutover_id: str,
        phase: CutoverPhase,
        *,
        phase_order: int,
        status: str,
        now_ms: int,
        error: str | None,
    ) -> None:
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    f"""
                    INSERT INTO {OPS_SCHEMA}.cutover_phases (
                        cutover_id,
                        phase,
                        phase_order,
                        status,
                        attempt_count,
                        started_at_ms,
                        completed_at_ms,
                        last_error
                    ) VALUES (
                        :cutover_id,
                        :phase,
                        :phase_order,
                        :status,
                        1,
                        :now_ms,
                        NULL,
                        :error
                    )
                    ON CONFLICT (cutover_id, phase) DO UPDATE SET
                        phase_order = EXCLUDED.phase_order,
                        status = EXCLUDED.status,
                        attempt_count = {OPS_SCHEMA}.cutover_phases.attempt_count + 1,
                        started_at_ms = EXCLUDED.started_at_ms,
                        completed_at_ms = NULL,
                        last_error = EXCLUDED.last_error
                    """
                ),
                {
                    "cutover_id": cutover_id,
                    "phase": phase.value,
                    "phase_order": phase_order,
                    "status": status,
                    "now_ms": now_ms,
                    "error": error,
                },
            )

    async def _update_phase(
        self,
        cutover_id: str,
        phase: CutoverPhase,
        *,
        status: str,
        now_ms: int,
        error: str | None,
    ) -> None:
        async with self._engine.begin() as connection:
            result = await connection.execute(
                text(
                    f"""
                    UPDATE {OPS_SCHEMA}.cutover_phases
                       SET status = :status,
                           completed_at_ms = :completed_at_ms,
                           last_error = :error
                     WHERE cutover_id = :cutover_id
                       AND phase = :phase
                    """
                ),
                {
                    "cutover_id": cutover_id,
                    "phase": phase.value,
                    "status": status,
                    "completed_at_ms": now_ms if status == "completed" else None,
                    "error": error,
                },
            )
        if result.rowcount != 1:
            raise RuntimeError("cutover phase journal row is missing")

    async def mark_run_completed(self, cutover_id: str, *, now_ms: int) -> None:
        async with self._engine.begin() as connection:
            result = await connection.execute(
                text(
                    f"""
                    UPDATE {OPS_SCHEMA}.cutover_runs
                       SET status = 'completed',
                           updated_at_ms = :now_ms
                     WHERE cutover_id = :cutover_id
                    """
                ),
                {"cutover_id": cutover_id, "now_ms": now_ms},
            )
        if result.rowcount != 1:
            raise RuntimeError("cutover run journal row is missing")

    async def load_snapshot(self, cutover_id: str) -> CutoverJournalSnapshot | None:
        await self._ensure_schema()
        async with self._engine.connect() as connection:
            run = (
                await connection.execute(
                    text(
                        f"""
                        SELECT cutover_id,
                               status,
                               server_id,
                               database_identity,
                               venue_id,
                               account_id,
                               runtime_profile_id,
                               application_schema,
                               target_commit,
                               target_schema_revision,
                               target_seed_identity,
                               target_release_id
                          FROM {OPS_SCHEMA}.cutover_runs
                         WHERE cutover_id = :cutover_id
                        """
                    ),
                    {"cutover_id": cutover_id},
                )
            ).mappings().one_or_none()
            if run is None:
                return None
            phase_rows = (
                await connection.execute(
                    text(
                        f"""
                        SELECT phase,
                               phase_order,
                               status,
                               attempt_count,
                               started_at_ms,
                               completed_at_ms,
                               last_error
                          FROM {OPS_SCHEMA}.cutover_phases
                         WHERE cutover_id = :cutover_id
                         ORDER BY phase_order
                        """
                    ),
                    {"cutover_id": cutover_id},
                )
            ).mappings().all()
        return CutoverJournalSnapshot(
            cutover_id=str(run["cutover_id"]),
            run_status=str(run["status"]),
            server_id=str(run["server_id"]),
            database_identity=str(run["database_identity"]),
            venue_id=str(run["venue_id"]),
            account_id=str(run["account_id"]),
            runtime_profile_id=str(run["runtime_profile_id"]),
            application_schema=str(run["application_schema"]),
            target_commit=str(run["target_commit"]),
            target_schema_revision=str(run["target_schema_revision"]),
            target_seed_identity=str(run["target_seed_identity"]),
            target_release_id=str(run["target_release_id"]),
            phases=tuple(
                CutoverPhaseRecord(
                    phase=CutoverPhase(str(row["phase"])),
                    phase_order=int(row["phase_order"]),
                    status=str(row["status"]),
                    attempt_count=int(row["attempt_count"]),
                    started_at_ms=(
                        None
                        if row["started_at_ms"] is None
                        else int(row["started_at_ms"])
                    ),
                    completed_at_ms=(
                        None
                        if row["completed_at_ms"] is None
                        else int(row["completed_at_ms"])
                    ),
                    last_error=(
                        None if row["last_error"] is None else str(row["last_error"])
                    ),
                )
                for row in phase_rows
            ),
        )


async def plan_cutover(
    adapter: CutoverFactsAdapter,
    plan: CutoverPlan,
) -> CutoverVerification:
    facts = await adapter.inspect_preconditions(plan)
    return verify_cutover_facts(plan, facts, require_writer_fence=False)


async def run_cutover(
    adapter: CutoverAdapter,
    journal: CutoverJournal,
    plan: CutoverPlan,
    *,
    now_ms: int,
) -> CutoverResult:
    async with journal.run_lock(plan.cutover_id):
        await journal.ensure_run(plan, now_ms=now_ms)
        rebuild_index = CUTOVER_PHASES.index(
            CutoverPhase.REBUILD_APPLICATION_SCHEMA
        )
        destructive_started = False
        for destructive_phase in CUTOVER_PHASES[rebuild_index:]:
            if (
                await journal.phase_status(plan.cutover_id, destructive_phase)
                is not None
            ):
                destructive_started = True
                break
        if not destructive_started:
            initial = await plan_cutover(adapter, plan)
            if initial.blockers:
                raise CutoverBlocked(
                    tuple(blocker.value for blocker in initial.blockers)
                )

        for index, phase in enumerate(CUTOVER_PHASES, start=1):
            status = await journal.phase_status(plan.cutover_id, phase)
            if destructive_started and index <= rebuild_index:
                if status != "completed":
                    raise CutoverBlocked(
                        ("pre_destruction_phase_incomplete_after_schema_rebuild",)
                    )
                continue
            if phase is CutoverPhase.PLAN_IDENTITIES:
                if status != "completed":
                    await journal.mark_phase_started(
                        plan.cutover_id,
                        phase,
                        phase_order=index,
                        now_ms=now_ms,
                    )
                    await journal.mark_phase_completed(
                        plan.cutover_id,
                        phase,
                        now_ms=now_ms,
                    )
                continue

            if phase is CutoverPhase.VERIFY_FINAL_FLAT:
                await _run_final_verification(
                    adapter,
                    journal,
                    plan,
                    phase_order=index,
                    now_ms=now_ms,
                )
                continue

            if await adapter.phase_satisfied(phase, plan):
                if status != "completed":
                    await journal.mark_phase_started(
                        plan.cutover_id,
                        phase,
                        phase_order=index,
                        now_ms=now_ms,
                    )
                    await journal.mark_phase_completed(
                        plan.cutover_id,
                        phase,
                        now_ms=now_ms,
                    )
                continue

            await journal.mark_phase_started(
                plan.cutover_id,
                phase,
                phase_order=index,
                now_ms=now_ms,
            )
            try:
                await adapter.apply_phase(phase, plan)
                if not await adapter.phase_satisfied(phase, plan):
                    raise RuntimeError(f"cutover postcondition failed: {phase.value}")
            except Exception as exc:
                await journal.mark_phase_failed(
                    plan.cutover_id,
                    phase,
                    error=str(exc),
                    now_ms=now_ms,
                )
                raise
            await journal.mark_phase_completed(
                plan.cutover_id,
                phase,
                now_ms=now_ms,
            )

        await journal.mark_run_completed(plan.cutover_id, now_ms=now_ms)

    return CutoverResult(
        status="completed",
        cutover_id=plan.cutover_id,
        completed_phases=CUTOVER_PHASES,
    )


async def _run_final_verification(
    adapter: CutoverAdapter,
    journal: CutoverJournal,
    plan: CutoverPlan,
    *,
    phase_order: int,
    now_ms: int,
) -> None:
    phase = CutoverPhase.VERIFY_FINAL_FLAT
    await journal.mark_phase_started(
        plan.cutover_id,
        phase,
        phase_order=phase_order,
        now_ms=now_ms,
    )
    facts = await adapter.inspect_preconditions(plan)
    verification = verify_cutover_facts(plan, facts, require_writer_fence=True)
    if verification.blockers:
        blockers = tuple(blocker.value for blocker in verification.blockers)
        await journal.mark_phase_failed(
            plan.cutover_id,
            phase,
            error=",".join(blockers),
            now_ms=now_ms,
        )
        raise CutoverBlocked(blockers)
    await journal.mark_phase_completed(
        plan.cutover_id,
        phase,
        now_ms=now_ms,
    )


def _sanitize_error(error: str) -> str:
    bounded = error[:2_000]
    return re.sub(
        r"postgresql(?:\+asyncpg)?://[^\s]+",
        "postgresql://***",
        bounded,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--adapter-factory", required=True, help="module:callable")
    parser.add_argument(
        "--journal-database-url",
        default=os.getenv("TRADING_KERNEL_DATABASE_URL", ""),
    )
    parser.add_argument("--cutover-id", required=True)
    parser.add_argument("--server-id", required=True)
    parser.add_argument("--database-identity", required=True)
    parser.add_argument("--venue-id", required=True)
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--runtime-profile-id", required=True)
    parser.add_argument("--application-schema", default="public")
    parser.add_argument("--target-commit", required=True)
    parser.add_argument("--target-schema-revision", default="0001_initial")
    parser.add_argument("--target-seed-identity", required=True)
    parser.add_argument("--target-release-id", required=True)
    parser.add_argument("--now-ms", type=int)
    return parser


async def _run(args: argparse.Namespace) -> int:
    plan = build_plan_from_args(args)
    loaded = await load_cutover_adapter(args.adapter_factory)
    if not callable(getattr(loaded, "apply_phase", None)) or not callable(
        getattr(loaded, "phase_satisfied", None)
    ):
        raise TypeError("cutover adapter must expose apply_phase and phase_satisfied")
    adapter = cast(CutoverAdapter, loaded)
    journal: PostgresCutoverJournal | None = None
    try:
        if args.plan:
            result: BaseModel = await plan_cutover(adapter, plan)
        else:
            journal = PostgresCutoverJournal(
                str(args.journal_database_url or "").strip()
            )
            result = await run_cutover(
                adapter,
                journal,
                plan,
                now_ms=args.now_ms or int(time.time() * 1_000),
            )
        print(json.dumps(result.model_dump(mode="json"), sort_keys=True))
        status = str(getattr(result, "status", "fail"))
        return 0 if status in {"pass", "completed"} else 1
    finally:
        if journal is not None:
            await journal.close()
        close = getattr(adapter, "close", None)
        if callable(close):
            closed = close()
            if inspect.isawaitable(closed):
                await closed


def main(argv: list[str] | None = None) -> int:
    try:
        return asyncio.run(_run(_parser().parse_args(argv)))
    except CutoverBlocked as exc:
        print(json.dumps({"status": "blocked", "blockers": exc.blockers}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
