from __future__ import annotations

import asyncio
import subprocess
import sys
from collections.abc import AsyncGenerator, Mapping
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal, cast
from uuid import uuid4

import asyncpg
import pytest
import pytest_asyncio
import sqlalchemy as sa
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from scripts.trading_kernel.certify_readonly import _certify
from scripts.trading_kernel.cutover_tokyo import (
    CUTOVER_PHASES,
    CutoverBlocked,
    CutoverPhase,
    PostgresCutoverJournal,
    plan_cutover,
    run_cutover,
)
from scripts.trading_kernel.verify_flat_cutover import (
    CutoverBlocker,
    CutoverFacts,
    CutoverPlan,
    verify_cutover_facts,
)
from src.trading_kernel.infrastructure.pg_models import (
    metadata,
    runtime_capabilities_current,
    schema_metadata,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_authority_seed import (
    ArmAcceptancePolicyRequest,
    RuntimeAuthoritySeedRequest,
    arm_acceptance_policy,
    build_runtime_seed_identity,
    seed_runtime_authority,
)
from tests.trading_kernel.integration.test_issue_ticket import (
    ADMIN_DSN,
    SAFE_DATABASE,
    _database_url,
    _run_alembic,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
BASELINE_SCHEMA_REVISION: Literal["0001_trading_kernel_baseline_v3"] = (
    "0001_trading_kernel_baseline_v3"
)
@pytest_asyncio.fixture
async def journal_database_url() -> AsyncGenerator[str, None]:
    database_name = f"brc_kernel_test_{uuid4().hex[:12]}"
    assert SAFE_DATABASE.fullmatch(database_name)
    admin = await asyncpg.connect(ADMIN_DSN)
    await admin.execute(f'CREATE DATABASE "{database_name}"')
    try:
        yield _database_url(database_name)
    finally:
        await admin.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = $1 AND pid <> pg_backend_pid()",
            database_name,
        )
        await admin.execute(f'DROP DATABASE IF EXISTS "{database_name}"')
        await admin.close()


def test_cutover_plan_freezes_exact_target_identity_and_phase_order() -> None:
    plan = _plan()

    assert plan.target_commit == "a" * 40
    assert plan.target_schema_revision == "0001_trading_kernel_baseline_v3"
    assert plan.target_seed_identity.startswith("sha256:")
    assert "exchange_instrument_ids" not in CutoverPlan.model_fields
    assert CUTOVER_PHASES == (
        CutoverPhase.PLAN_IDENTITIES,
        CutoverPhase.STAGE_EXACT_RELEASE,
        CutoverPhase.FENCE_EXCHANGE_WRITES,
        CutoverPhase.STOP_RUNTIME_WRITERS,
        CutoverPhase.VERIFY_FINAL_FLAT,
        CutoverPhase.REBUILD_APPLICATION_SCHEMA,
        CutoverPhase.SEED_CURRENT_AUTHORITY,
        CutoverPhase.DEPLOY_EXACT_RELEASE,
        CutoverPhase.CERTIFY_SCHEMA_AND_READONLY,
        CutoverPhase.START_READONLY_WORKERS,
        CutoverPhase.COMPLETE_TARGET_CERTIFICATION,
        CutoverPhase.START_LIFECYCLE,
        CutoverPhase.START_ENTRY_FENCED,
        CutoverPhase.FINAL_POSTFLIGHT,
        CutoverPhase.UNFENCE_ENTRY,
    )
    with pytest.raises(ValidationError):
        _plan(target_commit="not-a-commit")
    with pytest.raises(ValidationError):
        _plan(target_seed_identity="sha256:not-a-digest")


def test_cutover_plan_rejects_the_retired_operator_probe_scope() -> None:
    with pytest.raises(ValidationError):
        _plan(exchange_instrument_ids=("binance-usdm:BTCUSDT:perpetual",))


@pytest.mark.asyncio
async def test_plan_mode_is_side_effect_free() -> None:
    plan = _plan()
    adapter = FakeCutoverAdapter(_facts(plan))

    result = await plan_cutover(adapter, plan)

    assert result.status == "pass"
    assert result.blockers == ()
    assert adapter.apply_calls == []


@pytest.mark.asyncio
async def test_apply_stages_exact_release_before_target_release_preflight() -> None:
    """The target release must exist before it can safely run its readonly probe."""

    plan = _plan()
    adapter = TargetReleaseStagingAdapter(_facts(plan))
    journal = MemoryCutoverJournal()

    result = await run_cutover(adapter, journal, plan, now_ms=1_000)

    assert result.status == "completed"
    assert adapter.apply_calls[0] is CutoverPhase.STAGE_EXACT_RELEASE


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ({"server_id": "wrong-server"}, CutoverBlocker.SERVER_IDENTITY_MISMATCH),
        (
            {"database_identity": "wrong-database"},
            CutoverBlocker.DATABASE_IDENTITY_MISMATCH,
        ),
        ({"venue_id": "wrong-venue"}, CutoverBlocker.VENUE_IDENTITY_MISMATCH),
        ({"account_id": "wrong-account"}, CutoverBlocker.ACCOUNT_IDENTITY_MISMATCH),
        ({"account_mode": "one_way"}, CutoverBlocker.ACCOUNT_MODE_INVALID),
        ({"non_flat_positions": 1}, CutoverBlocker.POSITIONS_NOT_FLAT),
        ({"open_orders": 1}, CutoverBlocker.OPEN_ORDERS_PRESENT),
        ({"protection_orders": 1}, CutoverBlocker.PROTECTION_RESIDUE_PRESENT),
        ({"nonterminal_tickets": 1}, CutoverBlocker.OLD_TICKETS_NONTERMINAL),
        ({"active_budgets": 1}, CutoverBlocker.ACTIVE_BUDGETS_PRESENT),
        ({"unresolved_outcomes": 1}, CutoverBlocker.COMMAND_OUTCOME_UNKNOWN),
        ({"open_incidents": 1}, CutoverBlocker.RUNTIME_INCIDENT_OPEN),
        ({"target_commit": "c" * 40}, CutoverBlocker.TARGET_COMMIT_MISMATCH),
        (
            {"target_schema_revision": "wrong_revision"},
            CutoverBlocker.TARGET_SCHEMA_MISMATCH,
        ),
        (
            {"target_seed_identity": "sha256:" + "d" * 64},
            CutoverBlocker.TARGET_SEED_IDENTITY_MISMATCH,
        ),
        (
            {"active_new_writers": ("new-worker",)},
            CutoverBlocker.NEW_WRITER_ACTIVE,
        ),
        (
            {"active_old_writers": ("old-worker",)},
            CutoverBlocker.OLD_WRITER_ACTIVE,
        ),
        (
            {"exchange_writes_fenced": False},
            CutoverBlocker.WRITER_FENCE_MISSING,
        ),
    ],
)
def test_each_cutover_precondition_has_an_exact_blocker(
    change: dict[str, object],
    expected: CutoverBlocker,
) -> None:
    plan = _plan()
    facts = _facts(plan).model_copy(
        update={
            "active_old_writers": (),
            "exchange_writes_fenced": True,
            **change,
        }
    )

    result = verify_cutover_facts(plan, facts, require_writer_fence=True)

    assert expected in result.blockers
    assert result.status == "fail"


@pytest.mark.asyncio
async def test_final_verification_blocks_before_schema_destruction() -> None:
    plan = _plan()
    adapter = FakeCutoverAdapter(
        _facts(plan),
        final_fact_change={"open_orders": 1},
    )
    journal = MemoryCutoverJournal()

    with pytest.raises(CutoverBlocked, match="open_orders_present"):
        await run_cutover(adapter, journal, plan, now_ms=1_000)

    assert CutoverPhase.REBUILD_APPLICATION_SCHEMA not in adapter.apply_calls


@pytest.mark.asyncio
async def test_interrupted_apply_resumes_at_first_unverified_phase(
    journal_database_url: str,
) -> None:
    plan = _plan()
    adapter = FakeCutoverAdapter(
        _facts(plan),
        fail_after_effect_once=CutoverPhase.FENCE_EXCHANGE_WRITES,
    )
    journal = PostgresCutoverJournal(journal_database_url)
    try:
        with pytest.raises(RuntimeError, match="simulated cutover crash"):
            await run_cutover(adapter, journal, plan, now_ms=1_000)

        failed = await journal.load_snapshot(plan.cutover_id)
        assert failed is not None
        assert failed.run_status == "running"
        assert failed.phase_status(CutoverPhase.FENCE_EXCHANGE_WRITES) == "failed"

        completed = await run_cutover(adapter, journal, plan, now_ms=2_000)
        snapshot = await journal.load_snapshot(plan.cutover_id)
    finally:
        await journal.close()

    assert completed.status == "completed"
    assert completed.completed_phases == CUTOVER_PHASES
    assert snapshot is not None
    assert snapshot.run_status == "completed"
    assert all(record.status == "completed" for record in snapshot.phases)
    assert adapter.apply_calls.count(CutoverPhase.FENCE_EXCHANGE_WRITES) == 1
    assert adapter.apply_calls.count(CutoverPhase.REBUILD_APPLICATION_SCHEMA) == 1


@pytest.mark.asyncio
async def test_journal_rejects_same_cutover_id_with_changed_plan_identity(
    journal_database_url: str,
) -> None:
    plan = _plan(cutover_id="tokyo-kernel-identity-lock")
    changed_identities = (
        {"server_id": "wrong-server"},
        {"database_identity": "wrong-database"},
        {"venue_id": "wrong-venue"},
        {"account_id": "wrong-account"},
        {"runtime_profile_id": "wrong-profile"},
        {"application_schema": "wrong_schema"},
        {"target_commit": "c" * 40},
        {"target_seed_identity": "sha256:" + "d" * 64},
        {"target_release_id": "wrong-release"},
    )
    journal = PostgresCutoverJournal(journal_database_url)
    try:
        await journal.ensure_run(plan, now_ms=1_000)
        for change in changed_identities:
            changed_plan = _plan(
                cutover_id=plan.cutover_id,
                **change,
            )
            with pytest.raises(CutoverBlocked, match="cutover_identity_conflict"):
                await journal.ensure_run(changed_plan, now_ms=2_000)
    finally:
        await journal.close()


@pytest.mark.asyncio
async def test_resume_after_entry_fence_certification_does_not_restart_cutover(
    journal_database_url: str,
) -> None:
    plan = _plan(cutover_id="tokyo-kernel-final-phase-crash")
    adapter = FakeCutoverAdapter(
        _facts(plan),
        fail_after_effect_once=CutoverPhase.START_ENTRY_FENCED,
    )
    journal = PostgresCutoverJournal(journal_database_url)
    try:
        with pytest.raises(RuntimeError, match="simulated cutover crash"):
            await run_cutover(adapter, journal, plan, now_ms=1_000)

        completed = await run_cutover(adapter, journal, plan, now_ms=2_000)
    finally:
        await journal.close()

    assert completed.status == "completed"
    assert adapter.apply_calls.count(CutoverPhase.REBUILD_APPLICATION_SCHEMA) == 1
    assert adapter.apply_calls.count(CutoverPhase.START_ENTRY_FENCED) == 1


@pytest.mark.asyncio
async def test_disposable_postgres_rehearsal_rebuilds_clean_schema_and_seeds_authority(
    journal_database_url: str,
) -> None:
    plan = _plan(cutover_id="tokyo-kernel-postgres-rehearsal")
    engine = create_async_engine(journal_database_url)
    async with engine.begin() as connection:
        await connection.execute(
            text("CREATE TABLE legacy_execution_path (legacy_id TEXT PRIMARY KEY)")
        )
        await connection.execute(
            text("INSERT INTO legacy_execution_path VALUES ('legacy-1')")
        )
    adapter = LocalPostgresCutoverAdapter(journal_database_url, plan)
    journal = PostgresCutoverJournal(journal_database_url)
    try:
        result = await run_cutover(adapter, journal, plan, now_ms=1_000)
        async with engine.connect() as connection:
            actual_tables = {
                str(name)
                for name in (
                    await connection.execute(
                        text(
                            """
                            SELECT relname
                              FROM pg_catalog.pg_class
                             WHERE relkind IN ('r', 'p')
                               AND relnamespace = 'public'::regnamespace
                             ORDER BY relname
                            """
                        )
                    )
                ).scalars()
            }
            seed_identity = (
                await connection.execute(
                    sa.select(schema_metadata.c.metadata_value).where(
                        schema_metadata.c.metadata_key == "seed_identity"
                    )
                )
            ).scalar_one()
            capability_rows = (
                await connection.execute(
                    sa.select(
                        runtime_capabilities_current.c.capability_key,
                        runtime_capabilities_current.c.enabled,
                    )
                )
            ).all()
            capabilities: dict[str, bool] = {
                str(row[0]): bool(row[1]) for row in capability_rows
            }
    finally:
        await adapter.close()
        await journal.close()
        await engine.dispose()

    assert result.status == "completed"
    assert actual_tables == set(metadata.tables) | {"alembic_version"}
    assert "legacy_execution_path" not in actual_tables
    assert seed_identity == plan.target_seed_identity
    assert capabilities == {
        "exchange_commands": True,
        "strategy_signal_ingest": True,
    }


def test_systemd_runtime_workers_are_four_explicit_bounded_roles() -> None:
    systemd_dir = REPO_ROOT / "deploy/systemd"
    assert not (systemd_dir / "brc-trading-kernel-worker.service").exists()
    assert not (systemd_dir / "brc-trading-kernel-worker.timer").exists()

    runtime_slice = (
        systemd_dir / "brc-trading-kernel.slice"
    ).read_text(encoding="utf-8")
    assert "CPUQuota=100%" in runtime_slice
    assert "MemoryMax=1G" in runtime_slice
    assert "TasksMax=128" in runtime_slice

    for role in ("entry", "lifecycle"):
        service = (
            systemd_dir / f"brc-trading-kernel-{role}-worker.service"
        ).read_text(encoding="utf-8")
        assert not (
            systemd_dir / f"brc-trading-kernel-{role}-worker.timer"
        ).exists()

        assert "Type=simple" in service
        assert "Restart=on-failure" in service
        assert "RestartSec=5s" in service
        assert "Slice=brc-trading-kernel.slice" in service
        assert "scripts/trading_kernel/run_command_worker_once.py" in service
        assert f"--worker-role {role}" in service
        assert "--run-forever" in service
        assert "--poll-interval-ms 2000" in service
        assert "--timeout-seconds ${TRADING_KERNEL_TIMEOUT_SECONDS}" in service
        if role == "entry":
            assert "ConditionPathExists=!/etc/brc/trading-kernel.write-fenced" not in service
            assert "while test -e /etc/brc/trading-kernel.write-fenced" in service
            assert "--runtime-commit ${TRADING_KERNEL_RUNTIME_COMMIT}" in service
            assert "--schema-revision ${TRADING_KERNEL_SCHEMA_REVISION}" in service
            assert (
                "--action-fact-validity-ms "
                "${TRADING_KERNEL_ACTION_FACT_VALIDITY_MS}"
            ) in service
        else:
            assert (
                "--idle-poll-interval-ms ${TRADING_KERNEL_IDLE_POLL_INTERVAL_MS}"
                in service
            )

    observation_service = (
        systemd_dir / "brc-trading-kernel-observation-worker.service"
    ).read_text(encoding="utf-8")
    assert not (
        systemd_dir / "brc-trading-kernel-observation-worker.timer"
    ).exists()
    assert "Type=simple" in observation_service
    assert "Restart=on-failure" in observation_service
    assert "Slice=brc-trading-kernel.slice" in observation_service
    assert "scripts/trading_kernel/run_observation_worker_once.py" in observation_service
    assert "--run-forever" in observation_service
    assert "--poll-interval-ms 5000" in observation_service
    assert "--runtime-scope-id" not in observation_service

    reconciliation_service = (
        systemd_dir / "brc-trading-kernel-reconciliation-worker.service"
    ).read_text(encoding="utf-8")
    assert not (
        systemd_dir / "brc-trading-kernel-reconciliation-worker.timer"
    ).exists()
    assert "Type=simple" in reconciliation_service
    assert "Restart=on-failure" in reconciliation_service
    assert "Slice=brc-trading-kernel.slice" in reconciliation_service
    assert (
        "scripts/trading_kernel/run_reconciliation_worker_once.py"
        in reconciliation_service
    )
    assert "--run-forever" in reconciliation_service
    assert "--poll-interval-ms 5000" in reconciliation_service


@pytest.mark.asyncio
async def test_readonly_certification_reports_exact_runtime_authority(
    journal_database_url: str,
) -> None:
    await asyncio.to_thread(_run_alembic, journal_database_url, "upgrade", "head")
    engine = create_async_engine(journal_database_url)
    plan = _plan()
    try:
        async with PostgresKernelUnitOfWork(engine) as uow:
            await seed_runtime_authority(
                uow,
                RuntimeAuthoritySeedRequest(
                    account_id=plan.account_id,
                    runtime_commit=plan.target_commit,
                    schema_revision=cast(
                        Literal["0001_trading_kernel_baseline_v3"],
                        plan.target_schema_revision,
                    ),
                    seeded_at_ms=1_000,
                ),
            )
        payload = await _certify(journal_database_url, require_flat=True)
    finally:
        await engine.dispose()

    assert payload["status"] == "pass"
    assert payload["runtime_identity"] == {
        "runtime_commit": plan.target_commit,
        "schema_revision": plan.target_schema_revision,
        "seed_identity": plan.target_seed_identity,
    }
    assert payload["table_allowlist"] == {
        "status": "pass",
        "count": len(metadata.tables),
        "tables": sorted(metadata.tables),
    }
    assert payload["runtime_scope_count"] == 0
    assert payload["capabilities"] == {
        "exchange_commands": False,
        "strategy_signal_ingest": True,
    }
    assert payload["owner_policy"] == {
        "owner_policy_id": "policy-main",
        "policy_version": 1,
        "enabled": True,
        "new_entry_submit_enabled": False,
        "max_concurrent_tickets": 3,
        "max_ticket_stop_risk_fraction": "0.03",
        "max_gross_stop_risk_fraction": "0.06",
        "max_ticket_initial_margin_fraction": "0.45",
        "max_gross_initial_margin_utilization": "0.9",
        "max_leverage": 10,
        "supported_margin_mode": "cross",
        "post_stop_stress_multiple": "2",
        "max_post_fill_stop_risk_overrun_fraction": "0.1",
    }
    assert payload["release_counts"] == {
        "budget_reservations": 0,
        "released_budget_reservations": 0,
        "active_budget_reservations": 0,
    }
    assert payload["active_counts"] == {
        "tickets": 0,
        "commands": 0,
        "positions": 0,
        "incidents": 0,
    }
    assert payload["owner_projection"] is None
    assert payload["database_integrity_pass"] is True
    assert payload["flatness_pass"] is True
    assert payload["universe_bootstrap_pass"] is False
    assert payload["entry_promotion_pass"] is False


@pytest.mark.asyncio
async def test_readonly_certification_accepts_enabled_exchange_commands_under_controlled_policy(
    journal_database_url: str,
) -> None:
    await asyncio.to_thread(_run_alembic, journal_database_url, "upgrade", "head")
    engine = create_async_engine(journal_database_url)
    plan = _plan()
    try:
        async with PostgresKernelUnitOfWork(engine) as uow:
            await seed_runtime_authority(
                uow,
                RuntimeAuthoritySeedRequest(
                    account_id=plan.account_id,
                    runtime_commit=plan.target_commit,
                    schema_revision=cast(
                        Literal["0001_trading_kernel_baseline_v3"],
                        plan.target_schema_revision,
                    ),
                    seeded_at_ms=1_000,
                ),
            )
        async with engine.begin() as connection:
            await connection.execute(
                sa.update(runtime_capabilities_current)
                .where(
                    runtime_capabilities_current.c.capability_key
                    == "exchange_commands"
                )
                .values(enabled=True)
            )
        payload = await _certify(journal_database_url, require_flat=True)
    finally:
        await engine.dispose()

    assert payload["status"] == "pass"
    assert payload["capabilities"] == {
        "exchange_commands": True,
        "strategy_signal_ingest": True,
    }
    owner_policy = payload["owner_policy"]
    assert isinstance(owner_policy, Mapping)
    assert owner_policy["new_entry_submit_enabled"] is False


def test_readonly_certification_cli_loads_outside_repository(
    tmp_path: Path,
) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/trading_kernel/certify_readonly.py"),
            "--help",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


class FakeCutoverAdapter:
    def __init__(
        self,
        facts: CutoverFacts,
        *,
        final_fact_change: dict[str, object] | None = None,
        fail_after_effect_once: CutoverPhase | None = None,
    ) -> None:
        self.facts = facts
        self.final_fact_change = final_fact_change or {}
        self.fail_after_effect_once = fail_after_effect_once
        self.failed_once = False
        self.apply_calls: list[CutoverPhase] = []
        self.satisfied: set[CutoverPhase] = set()

    async def inspect_preconditions(self, plan: CutoverPlan) -> CutoverFacts:
        del plan
        if CutoverPhase.STOP_RUNTIME_WRITERS in self.satisfied:
            return self.facts.model_copy(update=self.final_fact_change)
        return self.facts

    async def apply_phase(self, phase: CutoverPhase, plan: CutoverPlan) -> None:
        del plan
        self.apply_calls.append(phase)
        if phase is CutoverPhase.FENCE_EXCHANGE_WRITES:
            self.facts = self.facts.model_copy(
                update={"exchange_writes_fenced": True}
            )
        elif phase is CutoverPhase.STOP_RUNTIME_WRITERS:
            self.facts = self.facts.model_copy(update={"active_new_writers": ()})
        self.satisfied.add(phase)
        if phase is self.fail_after_effect_once and not self.failed_once:
            self.failed_once = True
            raise RuntimeError("simulated cutover crash")

    async def phase_satisfied(
        self,
        phase: CutoverPhase,
        plan: CutoverPlan,
    ) -> bool:
        del plan
        return phase in self.satisfied


class TargetReleaseStagingAdapter(FakeCutoverAdapter):
    """Model target-release preflight, which is unavailable until staging completes."""

    async def inspect_preconditions(self, plan: CutoverPlan) -> CutoverFacts:
        if CutoverPhase.STAGE_EXACT_RELEASE not in self.satisfied:
            raise RuntimeError("target release is not staged")
        return await super().inspect_preconditions(plan)


class MemoryCutoverJournal:
    def __init__(self) -> None:
        self.identities: tuple[str, ...] | None = None
        self.statuses: dict[CutoverPhase, str] = {}

    @asynccontextmanager
    async def run_lock(self, cutover_id: str):
        del cutover_id
        yield

    async def ensure_run(self, plan: CutoverPlan, *, now_ms: int) -> None:
        del now_ms
        identity = (
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
        if self.identities is not None and self.identities != identity:
            raise CutoverBlocked(("cutover_identity_conflict",))
        self.identities = identity

    async def phase_status(
        self,
        cutover_id: str,
        phase: CutoverPhase,
    ) -> str | None:
        del cutover_id
        return self.statuses.get(phase)

    async def mark_phase_started(
        self,
        cutover_id: str,
        phase: CutoverPhase,
        *,
        phase_order: int,
        now_ms: int,
    ) -> None:
        del cutover_id, phase_order, now_ms
        self.statuses[phase] = "started"

    async def mark_phase_completed(
        self,
        cutover_id: str,
        phase: CutoverPhase,
        *,
        now_ms: int,
    ) -> None:
        del cutover_id, now_ms
        self.statuses[phase] = "completed"

    async def mark_phase_failed(
        self,
        cutover_id: str,
        phase: CutoverPhase,
        *,
        error: str,
        now_ms: int,
    ) -> None:
        del cutover_id, error, now_ms
        self.statuses[phase] = "failed"

    async def mark_run_completed(self, cutover_id: str, *, now_ms: int) -> None:
        del cutover_id, now_ms


class LocalPostgresCutoverAdapter:
    def __init__(self, database_url: str, plan: CutoverPlan) -> None:
        self.database_url = database_url
        self.plan = plan
        self.engine: AsyncEngine = create_async_engine(database_url)
        self.writes_fenced = False
        self.runtime_writers: tuple[str, ...] = ("runtime-writer",)
        self.release_staged = False
        self.release_deployed = False
        self.readonly_certified = False
        self.observation_enabled = False
        self.signal_to_ticket_no_write_certified = False
        self.lifecycle_enabled = False
        self.entry_started_fenced = False
        self.final_postflight_passed = False
        self.entry_unfenced = False

    async def close(self) -> None:
        await self.engine.dispose()

    async def inspect_preconditions(self, plan: CutoverPlan) -> CutoverFacts:
        return _facts(plan).model_copy(
            update={
                "active_old_writers": (),
                "active_new_writers": self.runtime_writers,
                "exchange_writes_fenced": self.writes_fenced,
            }
        )

    async def apply_phase(self, phase: CutoverPhase, plan: CutoverPlan) -> None:
        if phase is CutoverPhase.FENCE_EXCHANGE_WRITES:
            self.writes_fenced = True
        elif phase is CutoverPhase.STOP_RUNTIME_WRITERS:
            self.runtime_writers = ()
        elif phase is CutoverPhase.STAGE_EXACT_RELEASE:
            self.release_staged = True
        elif phase is CutoverPhase.REBUILD_APPLICATION_SCHEMA:
            async with self.engine.begin() as connection:
                await connection.execute(text("DROP SCHEMA public CASCADE"))
                await connection.execute(text("CREATE SCHEMA public"))
            await self.engine.dispose()
            await asyncio.to_thread(
                _run_alembic,
                self.database_url,
                "upgrade",
                "head",
            )
            self.engine = create_async_engine(self.database_url)
        elif phase is CutoverPhase.SEED_CURRENT_AUTHORITY:
            await self._seed_authority(plan)
        elif phase is CutoverPhase.DEPLOY_EXACT_RELEASE:
            self.release_deployed = True
        elif phase is CutoverPhase.CERTIFY_SCHEMA_AND_READONLY:
            actual = await self._public_tables()
            if actual != set(metadata.tables) | {"alembic_version"}:
                raise RuntimeError("rehearsal schema certification failed")
            self.readonly_certified = True
        elif phase is CutoverPhase.START_READONLY_WORKERS:
            self.observation_enabled = True
        elif phase is CutoverPhase.COMPLETE_TARGET_CERTIFICATION:
            self.signal_to_ticket_no_write_certified = True
        elif phase is CutoverPhase.START_LIFECYCLE:
            self.lifecycle_enabled = True
        elif phase is CutoverPhase.START_ENTRY_FENCED and await self._capability_enabled(
            "exchange_commands"
        ):
            raise RuntimeError("exchange commands must remain disabled")
        elif phase is CutoverPhase.START_ENTRY_FENCED:
            self.entry_started_fenced = True
        elif phase is CutoverPhase.FINAL_POSTFLIGHT:
            if not (
                self.writes_fenced
                and self.observation_enabled
                and self.signal_to_ticket_no_write_certified
                and self.lifecycle_enabled
                and self.entry_started_fenced
            ):
                raise RuntimeError("local final postflight prerequisites failed")
            self.final_postflight_passed = True
        elif phase is CutoverPhase.UNFENCE_ENTRY:
            if not self.final_postflight_passed:
                raise RuntimeError("local final postflight is missing")
            async with PostgresKernelUnitOfWork(self.engine) as uow:
                await arm_acceptance_policy(
                    uow,
                    ArmAcceptancePolicyRequest(armed_at_ms=2_000),
                )
            self.writes_fenced = False
            self.entry_unfenced = True

    async def phase_satisfied(
        self,
        phase: CutoverPhase,
        plan: CutoverPlan,
    ) -> bool:
        del plan
        if phase is CutoverPhase.FENCE_EXCHANGE_WRITES:
            return self.writes_fenced
        if phase is CutoverPhase.STOP_RUNTIME_WRITERS:
            return not self.runtime_writers
        if phase is CutoverPhase.STAGE_EXACT_RELEASE:
            return self.release_staged
        if phase is CutoverPhase.REBUILD_APPLICATION_SCHEMA:
            return (
                await self._relation_exists("public.brc_trade_tickets")
                and not await self._relation_exists("public.legacy_execution_path")
            )
        if phase is CutoverPhase.SEED_CURRENT_AUTHORITY:
            return await self._metadata_matches("seed_identity", self.plan.target_seed_identity)
        if phase is CutoverPhase.DEPLOY_EXACT_RELEASE:
            return self.release_deployed
        if phase is CutoverPhase.CERTIFY_SCHEMA_AND_READONLY:
            return self.readonly_certified
        if phase is CutoverPhase.START_READONLY_WORKERS:
            return self.observation_enabled
        if phase is CutoverPhase.COMPLETE_TARGET_CERTIFICATION:
            return (
                self.signal_to_ticket_no_write_certified
                and not await self._capability_enabled("exchange_commands")
            )
        if phase is CutoverPhase.START_ENTRY_FENCED:
            return (
                self.writes_fenced
                and self.entry_started_fenced
                and not await self._capability_enabled("exchange_commands")
            )
        if phase is CutoverPhase.START_LIFECYCLE:
            return self.lifecycle_enabled and self.writes_fenced
        if phase is CutoverPhase.FINAL_POSTFLIGHT:
            return self.final_postflight_passed and self.writes_fenced
        if phase is CutoverPhase.UNFENCE_ENTRY:
            return (
                self.entry_unfenced
                and not self.writes_fenced
                and await self._capability_enabled("exchange_commands")
            )
        return False

    async def _seed_authority(self, plan: CutoverPlan) -> None:
        async with PostgresKernelUnitOfWork(self.engine) as uow:
            result = await seed_runtime_authority(
                uow,
                RuntimeAuthoritySeedRequest(
                    account_id=plan.account_id,
                    runtime_commit=plan.target_commit,
                    schema_revision=cast(
                        Literal["0001_trading_kernel_baseline_v3"],
                        plan.target_schema_revision,
                    ),
                    seeded_at_ms=1_000,
                ),
            )
        assert result.runtime_seed_semantic_hash == plan.target_seed_identity

    async def _capability_enabled(self, capability: str) -> bool:
        async with self.engine.connect() as connection:
            value = await connection.scalar(
                sa.select(runtime_capabilities_current.c.enabled).where(
                    runtime_capabilities_current.c.capability_key == capability
                )
            )
        return bool(value)

    async def _metadata_matches(self, key: str, expected: str) -> bool:
        async with self.engine.connect() as connection:
            value = await connection.scalar(
                sa.select(schema_metadata.c.metadata_value).where(
                    schema_metadata.c.metadata_key == key
                )
            )
        return value == expected

    async def _relation_exists(self, relation: str) -> bool:
        async with self.engine.connect() as connection:
            value = await connection.scalar(
                text("SELECT to_regclass(:relation)"),
                {"relation": relation},
            )
        return value is not None

    async def _public_tables(self) -> set[str]:
        async with self.engine.connect() as connection:
            return {
                str(name)
                for name in (
                    await connection.execute(
                        text(
                            """
                            SELECT relname
                              FROM pg_catalog.pg_class
                             WHERE relkind IN ('r', 'p')
                               AND relnamespace = 'public'::regnamespace
                            """
                        )
                    )
                ).scalars()
            }


def _plan(**changes: object) -> CutoverPlan:
    runtime_commit = "a" * 40
    schema_revision = BASELINE_SCHEMA_REVISION
    seed_identity = build_runtime_seed_identity(
        RuntimeAuthoritySeedRequest(
            account_id="subaccount-main",
            runtime_commit=runtime_commit,
            schema_revision=schema_revision,
            seeded_at_ms=1_000,
        )
    )
    values: dict[str, object] = {
        "cutover_id": "tokyo-kernel-20260722",
        "server_id": "tokyo-primary",
        "database_identity": "brc-production",
        "venue_id": "binance-usdm",
        "account_id": "subaccount-main",
        "runtime_profile_id": "tiny-live-v1",
        "application_schema": "public",
        "target_commit": runtime_commit,
        "target_schema_revision": schema_revision,
        "target_seed_identity": seed_identity,
        "target_release_id": "release-aaaaaaaaaaaa",
    }
    values.update(changes)
    return CutoverPlan.model_validate(values)


def _facts(plan: CutoverPlan) -> CutoverFacts:
    return CutoverFacts(
        server_id=plan.server_id,
        database_identity=plan.database_identity,
        venue_id=plan.venue_id,
        account_id=plan.account_id,
        account_mode="independent_sides",
        target_commit=plan.target_commit,
        target_schema_revision=plan.target_schema_revision,
        target_seed_identity=plan.target_seed_identity,
        non_flat_positions=0,
        open_orders=0,
        protection_orders=0,
        nonterminal_tickets=0,
        active_budgets=0,
        unresolved_outcomes=0,
        open_incidents=0,
        active_old_writers=(),
        active_new_writers=("runtime-writer",),
        exchange_writes_fenced=False,
    )
