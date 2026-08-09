from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from src.trading_kernel.application.ingest_signal import (
    IngestSignalRequest,
    IngestSignalStatus,
    ingest_signal,
)
from src.trading_kernel.domain.signal import (
    SignalFactSnapshot,
    StrategySignal,
    build_signal_fact_digest,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import (
    PostgresKernelUnitOfWork,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
ADMIN_DSN = os.getenv(
    "BRC_TEST_POSTGRES_ADMIN_URL",
    "postgresql://dingdingbot:dingdingbot_dev@127.0.0.1:5432/postgres",
)
SAFE_DATABASE = re.compile(r"^brc_kernel_test_[a-f0-9]{12}$")
DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64


@pytest.mark.asyncio
async def test_only_current_active_universe_member_can_remain_entry_ready() -> None:
    database_name = f"brc_kernel_test_{uuid4().hex[:12]}"
    admin = await asyncpg.connect(ADMIN_DSN)
    engine = None
    try:
        await admin.execute(f'CREATE DATABASE "{database_name}"')
        database_url = _database_url(database_name)
        _run_alembic(database_url, "upgrade", "head")
        conn = await asyncpg.connect(database_url.replace("+asyncpg", ""))
        try:
            await _seed_active_signal_authority(conn)
        finally:
            await conn.close()

        engine = create_async_engine(database_url)
        signal = _signal()
        async with PostgresKernelUnitOfWork(engine) as uow:
            result = await ingest_signal(
                uow,
                IngestSignalRequest(
                    signal=signal,
                    runtime_commit="commit-test",
                    schema_revision="0004_owner_control_plane",
                    now_ms=1_010,
                ),
            )
            candidates = await uow.signals.list_ready_candidates(
                now_ms=1_010,
                limit=4,
            )

        assert result.status is IngestSignalStatus.CANDIDATE_READY
        assert [item.signal.signal_event_id for item in candidates] == [
            signal.signal_event_id
        ]

        conn = await asyncpg.connect(database_url.replace("+asyncpg", ""))
        try:
            await _switch_current_pointer(conn)
        finally:
            await conn.close()

        async with PostgresKernelUnitOfWork(engine) as uow:
            rejected = await ingest_signal(
                uow,
                IngestSignalRequest(
                    signal=signal.model_copy(
                        update={"signal_event_id": "signal:old-universe-after-switch"}
                    ),
                    runtime_commit="commit-test",
                    schema_revision="0004_owner_control_plane",
                    now_ms=1_011,
                ),
            )
            candidates_after_switch = await uow.signals.list_ready_candidates(
                now_ms=1_011,
                limit=4,
            )

        assert rejected.status is IngestSignalStatus.SCOPE_OR_POLICY_MISMATCH
        assert candidates_after_switch == ()
    finally:
        if engine is not None:
            await engine.dispose()
        await admin.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = $1 AND pid <> pg_backend_pid()",
            database_name,
        )
        await admin.execute(f'DROP DATABASE IF EXISTS "{database_name}"')
        await admin.close()


def _signal() -> StrategySignal:
    facts = (
        SignalFactSnapshot(
            fact_definition_id="fact:stop-reference:v1",
            role="protection_reference",
            value="97.5",
            satisfied=True,
            observed_at_ms=1_000,
            valid_until_ms=2_000,
            projection_version=1,
        ),
    )
    return StrategySignal(
        signal_event_id="signal:active-universe",
        exposure_episode_id="episode:active-universe",
        runtime_scope_id="scope-a",
        runtime_scope_version=1,
        strategy_group_id="sg-a",
        strategy_version_id="sv-a",
        event_spec_id="event-a",
        universe_version_id="uni-a",
        universe_semantic_digest=DIGEST_A,
        exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
        position_side="long",
        fact_digest=build_signal_fact_digest(facts),
        occurred_at_ms=1_000,
        observed_at_ms=1_000,
        expires_at_ms=2_000,
        facts=facts,
    )


async def _seed_active_signal_authority(conn: asyncpg.Connection) -> None:
    statement = """
        INSERT INTO brc_strategy_groups
            (strategy_group_id, display_name, active_version_id, status, updated_at_ms)
        VALUES ('sg-a', 'Strategy A', 'sv-a', 'active', 1000);
        INSERT INTO brc_strategy_versions
            (strategy_version_id, strategy_group_id, version, semantics, status, created_at_ms)
        VALUES ('sv-a', 'sg-a', 1, '{}'::jsonb, 'active', 1000);
        INSERT INTO brc_fact_definitions
            (fact_definition_id, fact_name, value_type, freshness_ms, validation)
        VALUES ('fact:stop-reference:v1', 'stop-reference', 'decimal', 1000, '{}'::jsonb);
        INSERT INTO brc_event_specs (
            event_spec_id, strategy_version_id, event_id, position_side,
            timeframe, freshness_window_ms, event_time_authority,
            entry_order_type, protection_reference_fact_definition_id,
            exit_policy_id, execution_semantics, status, created_at_ms
        ) VALUES (
            'event-a', 'sv-a', 'EVENT-A', 'long', '15m', 1000,
            'candle_close', 'market', 'fact:stop-reference:v1',
            'exit-a', '{}'::jsonb, 'active', 1000
        );
        INSERT INTO brc_event_required_facts
            (event_spec_id, fact_definition_id, role, required)
        VALUES ('event-a', 'fact:stop-reference:v1', 'protection_reference', true);
        INSERT INTO brc_instruments (
            exchange_instrument_id, venue_id, asset_class,
            venue_symbol, contract_kind, status
        ) VALUES (
            'binance-usdm:BTCUSDT:perpetual', 'binance-usdm',
            'crypto', 'BTCUSDT', 'perpetual', 'active'
        );
        INSERT INTO brc_runtime_profiles (
            runtime_profile_id, venue_id, account_id, environment,
            position_mode, status, updated_at_ms
        ) VALUES (
            'profile-a', 'binance-usdm', 'account-a', 'live',
            'independent_sides', 'active', 1000
        );
        INSERT INTO brc_instrument_certification_current (
            runtime_profile_id, exchange_instrument_id, status, blocker_code,
            facts_digest, product_rules_digest, configured_leverage,
            margin_mode, position_mode, observed_at_ms, valid_until_ms,
            next_check_at_ms, lease_owner, lease_expires_at_ms,
            lease_universe_version_id, projection_version
        ) VALUES (
            'profile-a', 'binance-usdm:BTCUSDT:perpetual', 'eligible', NULL,
            $2, $2, 5, 'cross', 'independent_sides', 1000, 2000,
            1500, NULL, NULL, NULL, 1
        );
        INSERT INTO brc_strategy_universe_versions (
            universe_version_id, strategy_group_id, event_spec_id,
            universe_version, semantic_digest, lifecycle_state,
            installed_at_ms, activated_at_ms
        ) VALUES ('uni-a', 'sg-a', 'event-a', 1, $1, 'active', 900, 950);
        INSERT INTO brc_strategy_universe_members
            (universe_version_id, exchange_instrument_id)
        VALUES ('uni-a', 'binance-usdm:BTCUSDT:perpetual');
        INSERT INTO brc_strategy_universe_current (
            event_spec_id, universe_version_id, semantic_digest,
            lifecycle_state, activation_generation, activated_at_ms
        ) VALUES ('event-a', 'uni-a', $1, 'active', 1, 950);
        INSERT INTO brc_owner_policy_current (
            owner_policy_id, policy_version, enabled, new_entry_submit_enabled,
            priority_rank, max_concurrent_tickets,
            max_strategy_group_concurrent_tickets,
            family_ticket_limits,
            max_ticket_stop_risk_fraction, max_gross_stop_risk_fraction,
            max_ticket_initial_margin_fraction,
            max_gross_initial_margin_utilization,
            directional_stop_risk_limit_fraction,
            min_materialization_ratio, max_leverage,
            supported_margin_mode,
            post_stop_stress_multiple,
            max_post_fill_stop_risk_overrun_fraction, scope, updated_at_ms
        ) VALUES (
            'policy-a', 1, true, true, 7, 3, NULL,
            '{"long_continuation":1,"opening_range":2,"rally_failure_short":1}'::jsonb,
            0.02, 0.06, 0.30, 0.9, 0.04, 0.50, 10,
            'cross', 2, 0.1, '{}'::jsonb, 1000
        );
        INSERT INTO brc_runtime_scopes_current (
            runtime_scope_id, strategy_group_id, strategy_version_id,
            event_spec_id, runtime_profile_id, owner_policy_id,
            exchange_instrument_id, position_side, universe_version_id,
            universe_semantic_digest, lifecycle_state,
            observation_enabled, entry_enabled, scope_version,
            warm_closed_bar_time_ms, warm_completed_at_ms, warm_readiness_digest, warm_valid_until_ms,
            updated_at_ms
        ) VALUES (
            'scope-a', 'sg-a', 'sv-a', 'event-a', 'profile-a', 'policy-a',
            'binance-usdm:BTCUSDT:perpetual', 'long', 'uni-a', $1,
            'active', true, true, 1, 900, 900, $1, 2000, 1000
        );
        INSERT INTO brc_facts_current (
            fact_current_id, runtime_scope_id, fact_definition_id, value,
            satisfied, observed_at_ms, valid_until_ms, projection_version
        ) VALUES (
            'fact-current-a', 'scope-a', 'fact:stop-reference:v1',
            '"97.5"'::jsonb, true, 1000, 2000, 1
        );
        INSERT INTO brc_runtime_capabilities_current (
            capability_key, enabled, certified_commit, schema_revision,
            certification, updated_at_ms
        ) VALUES (
            'strategy_signal_ingest', true, 'commit-test',
            '0004_owner_control_plane', '{}'::jsonb, 1000
        )
        """
    await conn.execute(
        statement.replace("$1", f"'{DIGEST_A}'").replace("$2", f"'{DIGEST_B}'")
    )


async def _switch_current_pointer(conn: asyncpg.Connection) -> None:
    statement = """
        INSERT INTO brc_strategy_universe_versions (
            universe_version_id, strategy_group_id, event_spec_id,
            universe_version, semantic_digest, lifecycle_state,
            installed_at_ms, activated_at_ms
        ) VALUES ('uni-b', 'sg-a', 'event-a', 2, $1, 'active', 1001, 1002);
        INSERT INTO brc_strategy_universe_members
            (universe_version_id, exchange_instrument_id)
        VALUES ('uni-b', 'binance-usdm:BTCUSDT:perpetual');
        UPDATE brc_strategy_universe_current
        SET universe_version_id = 'uni-b',
            semantic_digest = $1,
            activation_generation = 2,
            activated_at_ms = 1002
        WHERE event_spec_id = 'event-a'
        """
    await conn.execute(statement.replace("$1", f"'{DIGEST_B}'"))


def _database_url(database_name: str) -> str:
    if SAFE_DATABASE.fullmatch(database_name) is None:
        raise ValueError("unsafe kernel test database name")
    base = ADMIN_DSN.rsplit("/", 1)[0]
    return f"{base.replace('postgresql://', 'postgresql+asyncpg://', 1)}/{database_name}"


def _run_alembic(database_url: str, *args: str) -> None:
    env = {**os.environ, "TRADING_KERNEL_DATABASE_URL": database_url}
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            "migrations/trading_kernel/alembic.ini",
            *args,
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-4000:]
