from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest
import pytest_asyncio
import sqlalchemy as sa
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

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
    entry_lane_current,
    event_specs,
    instrument_rules_current,
    instruments,
    metadata,
    owner_policy_current,
    runtime_capabilities_current,
    runtime_profiles,
    runtime_scopes_current,
    schema_metadata,
    strategy_groups,
    strategy_versions,
)
from tests.trading_kernel.integration.test_issue_ticket import (
    ADMIN_DSN,
    SAFE_DATABASE,
    _database_url,
    _run_alembic,
)


REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest_asyncio.fixture
async def journal_database_url() -> str:
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
    assert plan.target_schema_revision == "0001_initial"
    assert plan.target_seed_identity == "sha256:" + "b" * 64
    assert CUTOVER_PHASES == (
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
        CutoverPhase.ENABLE_EXCHANGE_COMMANDS,
    )
    with pytest.raises(ValidationError):
        _plan(target_commit="not-a-commit")
    with pytest.raises(ValidationError):
        _plan(target_seed_identity="sha256:not-a-digest")


@pytest.mark.asyncio
async def test_plan_mode_is_side_effect_free() -> None:
    plan = _plan()
    adapter = FakeCutoverAdapter(_facts(plan))

    result = await plan_cutover(adapter, plan)

    assert result.status == "pass"
    assert result.blockers == ()
    assert adapter.apply_calls == []


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
async def test_final_verification_blocks_before_snapshot_or_schema_destruction() -> None:
    plan = _plan()
    adapter = FakeCutoverAdapter(
        _facts(plan),
        final_fact_change={"open_orders": 1},
    )
    journal = MemoryCutoverJournal()

    with pytest.raises(CutoverBlocked, match="open_orders_present"):
        await run_cutover(adapter, journal, plan, now_ms=1_000)

    assert CutoverPhase.CREATE_SHORT_LIVED_SNAPSHOT not in adapter.apply_calls
    assert CutoverPhase.REBUILD_APPLICATION_SCHEMA not in adapter.apply_calls


@pytest.mark.asyncio
async def test_interrupted_apply_resumes_at_first_unverified_phase(
    journal_database_url: str,
) -> None:
    plan = _plan()
    adapter = FakeCutoverAdapter(
        _facts(plan),
        fail_after_effect_once=CutoverPhase.CREATE_SHORT_LIVED_SNAPSHOT,
    )
    journal = PostgresCutoverJournal(journal_database_url)
    try:
        with pytest.raises(RuntimeError, match="simulated cutover crash"):
            await run_cutover(adapter, journal, plan, now_ms=1_000)

        failed = await journal.load_snapshot(plan.cutover_id)
        assert failed is not None
        assert failed.run_status == "running"
        assert failed.phase_status(CutoverPhase.CREATE_SHORT_LIVED_SNAPSHOT) == "failed"

        completed = await run_cutover(adapter, journal, plan, now_ms=2_000)
        snapshot = await journal.load_snapshot(plan.cutover_id)
    finally:
        await journal.close()

    assert completed.status == "completed"
    assert completed.completed_phases == CUTOVER_PHASES
    assert snapshot is not None
    assert snapshot.run_status == "completed"
    assert all(record.status == "completed" for record in snapshot.phases)
    assert adapter.apply_calls.count(
        CutoverPhase.CREATE_SHORT_LIVED_SNAPSHOT
    ) == 1
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
async def test_resume_after_exchange_command_enable_effect_does_not_restart_cutover(
    journal_database_url: str,
) -> None:
    plan = _plan(cutover_id="tokyo-kernel-final-phase-crash")
    adapter = FakeCutoverAdapter(
        _facts(plan),
        fail_after_effect_once=CutoverPhase.ENABLE_EXCHANGE_COMMANDS,
        activate_new_writer_on_enable=True,
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
    assert adapter.apply_calls.count(CutoverPhase.ENABLE_EXCHANGE_COMMANDS) == 1


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
            capabilities = dict(
                (
                    await connection.execute(
                        sa.select(
                            runtime_capabilities_current.c.capability_key,
                            runtime_capabilities_current.c.enabled,
                        )
                    )
                ).all()
            )
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
        "observation_monitor": True,
        "signal_to_ticket": True,
    }


def test_systemd_worker_unit_is_bounded_and_timer_driven() -> None:
    service = (
        REPO_ROOT / "deploy/systemd/brc-trading-kernel-worker.service"
    ).read_text(encoding="utf-8")
    timer = (
        REPO_ROOT / "deploy/systemd/brc-trading-kernel-worker.timer"
    ).read_text(encoding="utf-8")

    assert "Type=oneshot" in service
    assert "scripts/trading_kernel/run_worker_once.py" in service
    assert "--runtime-commit ${TRADING_KERNEL_RUNTIME_COMMIT}" in service
    assert "--schema-revision ${TRADING_KERNEL_SCHEMA_REVISION}" in service
    assert "--timeout-seconds ${TRADING_KERNEL_TIMEOUT_SECONDS}" in service
    assert "OnUnitActiveSec=2s" in timer
    assert "Persistent=false" in timer


class FakeCutoverAdapter:
    def __init__(
        self,
        facts: CutoverFacts,
        *,
        final_fact_change: dict[str, object] | None = None,
        fail_after_effect_once: CutoverPhase | None = None,
        activate_new_writer_on_enable: bool = False,
    ) -> None:
        self.facts = facts
        self.final_fact_change = final_fact_change or {}
        self.fail_after_effect_once = fail_after_effect_once
        self.activate_new_writer_on_enable = activate_new_writer_on_enable
        self.failed_once = False
        self.apply_calls: list[CutoverPhase] = []
        self.satisfied: set[CutoverPhase] = set()

    async def inspect_preconditions(self, plan: CutoverPlan) -> CutoverFacts:
        del plan
        if CutoverPhase.STOP_OLD_WRITERS in self.satisfied:
            return self.facts.model_copy(update=self.final_fact_change)
        return self.facts

    async def apply_phase(self, phase: CutoverPhase, plan: CutoverPlan) -> None:
        del plan
        self.apply_calls.append(phase)
        if phase is CutoverPhase.FENCE_EXCHANGE_WRITES:
            self.facts = self.facts.model_copy(
                update={"exchange_writes_fenced": True}
            )
        elif phase is CutoverPhase.STOP_OLD_WRITERS:
            self.facts = self.facts.model_copy(update={"active_old_writers": ()})
        elif (
            phase is CutoverPhase.ENABLE_EXCHANGE_COMMANDS
            and self.activate_new_writer_on_enable
        ):
            self.facts = self.facts.model_copy(
                update={
                    "active_new_writers": ("kernel-worker",),
                    "exchange_writes_fenced": False,
                }
            )
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
        self.old_writers = ("legacy-writer",)
        self.new_writers: tuple[str, ...] = ()
        self.release_deployed = False
        self.readonly_certified = False

    async def close(self) -> None:
        await self.engine.dispose()

    async def inspect_preconditions(self, plan: CutoverPlan) -> CutoverFacts:
        return _facts(plan).model_copy(
            update={
                "active_old_writers": self.old_writers,
                "active_new_writers": self.new_writers,
                "exchange_writes_fenced": self.writes_fenced,
            }
        )

    async def apply_phase(self, phase: CutoverPhase, plan: CutoverPlan) -> None:
        if phase is CutoverPhase.FENCE_EXCHANGE_WRITES:
            self.writes_fenced = True
        elif phase is CutoverPhase.STOP_OLD_WRITERS:
            self.old_writers = ()
        elif phase is CutoverPhase.CREATE_SHORT_LIVED_SNAPSHOT:
            async with self.engine.begin() as connection:
                await connection.execute(
                    text("CREATE SCHEMA IF NOT EXISTS brc_cutover_backup_test")
                )
                await connection.execute(
                    text(
                        "CREATE TABLE IF NOT EXISTS "
                        "brc_cutover_backup_test.legacy_execution_path AS "
                        "SELECT * FROM public.legacy_execution_path"
                    )
                )
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
        elif phase is CutoverPhase.ENABLE_OBSERVATION_MONITOR:
            await self._set_capability("observation_monitor", enabled=True)
        elif phase is CutoverPhase.CERTIFY_SIGNAL_TO_TICKET_NO_WRITE:
            await self._set_capability("signal_to_ticket", enabled=True)
        elif phase is CutoverPhase.ENABLE_EXCHANGE_COMMANDS:
            await self._set_capability("exchange_commands", enabled=True)
            self.new_writers = ("kernel-worker",)
            self.writes_fenced = False

    async def phase_satisfied(
        self,
        phase: CutoverPhase,
        plan: CutoverPlan,
    ) -> bool:
        del plan
        if phase is CutoverPhase.FENCE_EXCHANGE_WRITES:
            return self.writes_fenced
        if phase is CutoverPhase.STOP_OLD_WRITERS:
            return not self.old_writers
        if phase is CutoverPhase.CREATE_SHORT_LIVED_SNAPSHOT:
            return await self._relation_exists(
                "brc_cutover_backup_test.legacy_execution_path"
            )
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
        if phase is CutoverPhase.ENABLE_OBSERVATION_MONITOR:
            return await self._capability_enabled("observation_monitor")
        if phase is CutoverPhase.CERTIFY_SIGNAL_TO_TICKET_NO_WRITE:
            return (
                await self._capability_enabled("signal_to_ticket")
                and not await self._capability_enabled("exchange_commands")
            )
        if phase is CutoverPhase.ENABLE_EXCHANGE_COMMANDS:
            return await self._capability_enabled("exchange_commands")
        return False

    async def _seed_authority(self, plan: CutoverPlan) -> None:
        async with self.engine.begin() as connection:
            await connection.execute(
                sa.insert(strategy_groups).values(
                    strategy_group_id="SOR-001",
                    display_name="Session Opening Range",
                    active_version_id="SOR-001:v3",
                    status="active",
                    updated_at_ms=1_000,
                )
            )
            await connection.execute(
                sa.insert(strategy_versions).values(
                    strategy_version_id="SOR-001:v3",
                    strategy_group_id="SOR-001",
                    version=3,
                    semantics={},
                    status="active",
                    created_at_ms=1_000,
                )
            )
            await connection.execute(
                sa.insert(event_specs).values(
                    event_spec_id="SOR-LONG:v3",
                    strategy_version_id="SOR-001:v3",
                    position_side="long",
                    timeframe="15m",
                    entry_order_type="market",
                    execution_semantics={},
                    status="active",
                    created_at_ms=1_000,
                )
            )
            await connection.execute(
                sa.insert(instruments).values(
                    exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
                    venue_id=plan.venue_id,
                    asset_class="crypto_contract",
                    venue_symbol="BTCUSDT",
                    contract_kind="perpetual",
                    status="active",
                )
            )
            await connection.execute(
                sa.insert(instrument_rules_current).values(
                    exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
                    quantity_step=Decimal("0.001"),
                    price_tick=Decimal("0.1"),
                    min_quantity=Decimal("0.001"),
                    min_notional=Decimal("5"),
                    session_and_settlement={},
                    observed_at_ms=1_000,
                    valid_until_ms=10_000,
                    projection_version=1,
                )
            )
            await connection.execute(
                sa.insert(owner_policy_current).values(
                    owner_policy_id="policy-main",
                    policy_version=1,
                    enabled=True,
                    real_submit_enabled=False,
                    max_concurrent_tickets=8,
                    max_gross_notional=Decimal("1000"),
                    scope={},
                    updated_at_ms=1_000,
                )
            )
            await connection.execute(
                sa.insert(runtime_profiles).values(
                    runtime_profile_id=plan.runtime_profile_id,
                    venue_id=plan.venue_id,
                    account_id=plan.account_id,
                    environment="live",
                    position_mode="independent_sides",
                    status="active",
                    updated_at_ms=1_000,
                )
            )
            await connection.execute(
                sa.insert(runtime_scopes_current).values(
                    runtime_scope_id="scope-sor-btc-long",
                    strategy_group_id="SOR-001",
                    strategy_version_id="SOR-001:v3",
                    event_spec_id="SOR-LONG:v3",
                    runtime_profile_id=plan.runtime_profile_id,
                    owner_policy_id="policy-main",
                    exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
                    position_side="long",
                    enabled=True,
                    scope_version=1,
                    updated_at_ms=1_000,
                )
            )
            await connection.execute(
                sa.insert(entry_lane_current).values(
                    lane_id="global-entry",
                    ticket_id=None,
                    signal_event_id=None,
                    status="idle",
                    claimed_at_ms=None,
                    lease_until_ms=None,
                    claim_owner=None,
                    version=0,
                )
            )
            await connection.execute(
                sa.insert(schema_metadata),
                [
                    {
                        "metadata_key": "runtime_commit",
                        "metadata_value": plan.target_commit,
                        "updated_at_ms": 1_000,
                    },
                    {
                        "metadata_key": "schema_revision",
                        "metadata_value": plan.target_schema_revision,
                        "updated_at_ms": 1_000,
                    },
                    {
                        "metadata_key": "seed_identity",
                        "metadata_value": plan.target_seed_identity,
                        "updated_at_ms": 1_000,
                    },
                ],
            )
            await connection.execute(
                sa.insert(runtime_capabilities_current),
                [
                    {
                        "capability_key": capability,
                        "enabled": False,
                        "certified_commit": plan.target_commit,
                        "schema_revision": plan.target_schema_revision,
                        "certification": {},
                        "updated_at_ms": 1_000,
                    }
                    for capability in (
                        "observation_monitor",
                        "signal_to_ticket",
                        "exchange_commands",
                    )
                ],
            )

    async def _set_capability(self, capability: str, *, enabled: bool) -> None:
        async with self.engine.begin() as connection:
            await connection.execute(
                sa.update(runtime_capabilities_current)
                .where(
                    runtime_capabilities_current.c.capability_key == capability
                )
                .values(enabled=enabled, certification={"status": "pass"})
            )

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
    values: dict[str, object] = {
        "cutover_id": "tokyo-kernel-20260722",
        "server_id": "tokyo-primary",
        "database_identity": "brc-production",
        "venue_id": "binance-usdm",
        "account_id": "subaccount-main",
        "runtime_profile_id": "tiny-live-v1",
        "application_schema": "public",
        "target_commit": "a" * 40,
        "target_schema_revision": "0001_initial",
        "target_seed_identity": "sha256:" + "b" * 64,
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
        active_old_writers=("legacy-writer",),
        active_new_writers=(),
        exchange_writes_fenced=False,
    )
