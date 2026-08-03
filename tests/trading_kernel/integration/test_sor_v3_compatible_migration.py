from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import AsyncGenerator
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from migrations.trading_kernel import v4_schema
from src.trading_kernel.infrastructure import pg_models
from src.trading_kernel.infrastructure.pg_repositories import (
    PostgresCapacityClaimRepository,
    PostgresTicketRepository,
)
from tests.trading_kernel.integration.test_issue_ticket import (
    ADMIN_DSN,
    SAFE_DATABASE,
    _database_url,
)

V4_REVISION = "0001_trading_kernel_baseline_v4"
HEAD_REVISION = "0003_portfolio_admission_observability"
SEMANTIC_DIGEST = "sha256:" + "a" * 64
EXIT_POLICY_HASH = "sha256:" + "b" * 64
FACT_DIGEST = "sha256:" + "c" * 64
DECISION_DIGEST_1 = "sha256:" + "d" * 64
DECISION_DIGEST_2 = "sha256:" + "e" * 64
REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest_asyncio.fixture
async def compatible_migration_engine() -> AsyncGenerator[AsyncEngine, None]:
    database_name = f"brc_kernel_test_{uuid4().hex[:12]}"
    assert SAFE_DATABASE.fullmatch(database_name)
    admin = await asyncpg.connect(ADMIN_DSN)
    await admin.execute(f'CREATE DATABASE "{database_name}"')
    database_url = _database_url(database_name)
    result = _run_migration(database_url, "upgrade", V4_REVISION)
    assert result.returncode == 0, result.stderr[-4000:]
    engine = create_async_engine(database_url)
    try:
        yield engine
    finally:
        await engine.dispose()
        await admin.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = $1 AND pid <> pg_backend_pid()",
            database_name,
        )
        await admin.execute(f'DROP DATABASE IF EXISTS "{database_name}"')
        await admin.close()


@pytest.mark.asyncio
async def test_production_shaped_v4_history_upgrades_without_lineage_loss(
    compatible_migration_engine: AsyncEngine,
) -> None:
    engine = compatible_migration_engine
    await _assert_v4_shape(engine)
    await _seed_v4_history(engine)
    before = await _preservation_manifest(engine)

    database_url = engine.url.render_as_string(hide_password=False)
    result = _run_migration(database_url, "upgrade", "head")
    assert result.returncode == 0, result.stderr[-4000:]

    after = await _preservation_manifest(engine)
    assert after == before
    await _assert_head_shape_and_backfill(engine)


@pytest.mark.asyncio
async def test_0002_downgrade_refuses_after_v3_registry_rows(
    compatible_migration_engine: AsyncEngine,
) -> None:
    engine = compatible_migration_engine
    await _seed_v4_history(engine)
    database_url = engine.url.render_as_string(hide_password=False)
    result = _run_migration(database_url, "upgrade", "head")
    assert result.returncode == 0, result.stderr[-4000:]
    await _insert_v3_event_with_reused_event_id(engine)

    result = _run_migration(database_url, "downgrade", V4_REVISION)

    assert result.returncode != 0
    assert "fix-forward" in result.stderr
    async with engine.connect() as connection:
        assert await connection.scalar(
            sa.text("SELECT version_num FROM alembic_version")
        ) == HEAD_REVISION


async def _assert_v4_shape(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        shapes = await connection.run_sync(
            lambda sync: {
                table: {
                    column["name"]
                    for column in sa.inspect(sync).get_columns(table)
                }
                for table in (
                    "brc_signal_events",
                    "brc_owner_policy_current",
                    "brc_capacity_claims",
                    "brc_trade_tickets",
                )
            }
        )
        event_uniques = await connection.run_sync(
            lambda sync: {
                tuple(item["column_names"])
                for item in sa.inspect(sync).get_unique_constraints(
                    "brc_event_specs"
                )
            }
        )
    assert "exposure_episode_id" not in shapes["brc_signal_events"]
    assert (
        "max_strategy_group_concurrent_tickets"
        not in shapes["brc_owner_policy_current"]
    )
    assert "exit_policy_id" not in shapes["brc_capacity_claims"]
    assert "exit_policy_id" not in shapes["brc_trade_tickets"]
    assert event_uniques == {("event_id",)}


async def _seed_v4_history(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            sa.insert(v4_schema.strategy_groups).values(
                strategy_group_id="SOR-001",
                display_name="SOR-001",
                active_version_id="sgv:SOR-001:v2",
                status="active",
                updated_at_ms=900,
            )
        )
        await connection.execute(
            sa.insert(v4_schema.strategy_versions).values(
                strategy_version_id="sgv:SOR-001:v2",
                strategy_group_id="SOR-001",
                version=2,
                semantics={"producer": "persistent-state-v2"},
                status="active",
                created_at_ms=900,
            )
        )
        await connection.execute(
            sa.insert(v4_schema.event_specs).values(
                event_spec_id="event_spec:SOR-001:SOR-LONG:v2",
                strategy_version_id="sgv:SOR-001:v2",
                event_id="SOR-LONG",
                position_side="long",
                timeframe="15m",
                freshness_window_ms=900_000,
                event_time_authority="close_time",
                entry_order_type="market",
                protection_reference_fact_definition_id="fact:range-low:v1",
                exit_policy_id="exit-policy:SOR-001:SOR-LONG:right-tail-v1",
                execution_semantics={},
                status="active",
                created_at_ms=900,
            )
        )
        await connection.execute(
            sa.insert(v4_schema.exit_policies).values(
                exit_policy_id="exit-policy:SOR-001:SOR-LONG:right-tail-v1",
                exit_policy_version="right-tail-v1",
                event_spec_id="event_spec:SOR-001:SOR-LONG:v2",
                position_side="long",
                policy={"tp1": "1R"},
                semantic_hash=EXIT_POLICY_HASH,
                status="active",
                created_at_ms=900,
            )
        )
        await connection.execute(
            sa.insert(v4_schema.instruments).values(
                exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
                venue_id="binance-usdm",
                asset_class="crypto",
                venue_symbol="BTCUSDT",
                contract_kind="perpetual",
                status="active",
            )
        )
        await connection.execute(
            sa.insert(v4_schema.strategy_universe_versions).values(
                universe_version_id="universe:sor-long:v2:1",
                strategy_group_id="SOR-001",
                event_spec_id="event_spec:SOR-001:SOR-LONG:v2",
                universe_version=1,
                semantic_digest=SEMANTIC_DIGEST,
                lifecycle_state="active",
                installed_at_ms=900,
                activated_at_ms=950,
                retired_at_ms=None,
                abandoned_at_ms=None,
                abandon_reason_code=None,
            )
        )
        await connection.execute(
            sa.insert(v4_schema.strategy_universe_members).values(
                universe_version_id="universe:sor-long:v2:1",
                exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
            )
        )
        await connection.execute(
            sa.insert(v4_schema.owner_policy_current).values(
                owner_policy_id="policy-main",
                policy_version=7,
                enabled=True,
                new_entry_submit_enabled=False,
                priority_rank=1,
                max_concurrent_tickets=3,
                max_ticket_stop_risk_fraction=Decimal("0.03"),
                max_gross_stop_risk_fraction=Decimal("0.06"),
                max_ticket_initial_margin_fraction=Decimal("0.45"),
                max_gross_initial_margin_utilization=Decimal("0.90"),
                max_leverage=10,
                supported_margin_mode="cross",
                post_stop_stress_multiple=Decimal(2),
                max_post_fill_stop_risk_overrun_fraction=Decimal("0.10"),
                scope={},
                updated_at_ms=900,
            )
        )
        for index, created_at_ms in ((1, 1_000), (2, 2_000)):
            await connection.execute(
                sa.insert(v4_schema.signal_events).values(
                    signal_event_id=f"signal-v2-{index}",
                    runtime_scope_id=f"scope-v2-{index}",
                    runtime_scope_version=1,
                    strategy_group_id="SOR-001",
                    strategy_version_id="sgv:SOR-001:v2",
                    event_spec_id="event_spec:SOR-001:SOR-LONG:v2",
                    universe_version_id="universe:sor-long:v2:1",
                    universe_semantic_digest=SEMANTIC_DIGEST,
                    exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
                    position_side="long",
                    fact_digest=FACT_DIGEST,
                    occurred_at_ms=created_at_ms - 200,
                    observed_at_ms=created_at_ms - 100,
                    expires_at_ms=created_at_ms + 800,
                )
            )
            await connection.execute(
                sa.insert(v4_schema.capacity_claims).values(
                    **_claim_values(index=index, created_at_ms=created_at_ms)
                )
            )
            await connection.execute(
                sa.insert(v4_schema.trade_tickets).values(
                    **_ticket_values(index=index, created_at_ms=created_at_ms + 100)
                )
            )
        await connection.execute(
            sa.insert(v4_schema.budget_reservations).values(
                budget_reservation_id="reservation-v2-2",
                ticket_id="ticket-v2-2",
                owner_policy_id="policy-main",
                venue_id="binance-usdm",
                account_id="account-main",
                reserved_notional=Decimal(100),
                reserved_risk=Decimal(1),
                reserved_margin=Decimal(20),
                planned_stop_risk_budget=Decimal(1),
                risk_reservation_basis="planned_stop_distance",
                status="active",
                created_at_ms=2_100,
                released_at_ms=None,
            )
        )
        await connection.execute(
            sa.insert(v4_schema.exchange_commands).values(
                command_id="command-v2-2-entry",
                ticket_id="ticket-v2-2",
                command_kind="entry",
                generation=1,
                idempotency_key="idempotency-v2-2-entry",
                venue_client_order_id="client-v2-2-entry",
                status="outcome_unknown",
                quantity=Decimal(1),
                request_payload={},
                result_payload=None,
                claim_owner=None,
                lease_until_ms=None,
                created_at_ms=2_100,
                deadline_at_ms=3_000,
                completed_at_ms=None,
            )
        )
        await connection.execute(
            sa.insert(v4_schema.runtime_incidents).values(
                incident_id="incident-v2-2",
                ticket_id="ticket-v2-2",
                incident_kind="unknown_entry_outcome",
                status="open",
                first_blocker="exchange_truth_unresolved",
                entry_block_scope="account_capacity",
                entry_block_key="binance-usdm:account-main",
                details={},
                opened_at_ms=2_200,
                resolved_at_ms=None,
            )
        )
        await connection.execute(
            sa.insert(v4_schema.trade_reviews).values(
                review_id="review-v2-1",
                ticket_id="ticket-v2-1",
                revision=1,
                supersedes_review_id=None,
                outcome="closed",
                metrics={"net_pnl_quote": "1"},
                decision_impact={"entry_semantics": "v2"},
                created_at_ms=3_100,
            )
        )


def _claim_values(*, index: int, created_at_ms: int) -> dict[str, object]:
    decision_digest = DECISION_DIGEST_1 if index == 1 else DECISION_DIGEST_2
    return {
        "capacity_claim_id": f"claim-v2-{index}",
        "ticket_id": f"ticket-v2-{index}",
        "signal_event_id": f"signal-v2-{index}",
        "exposure_episode_id": f"episode-v2-{index}",
        "strategy_group_id": "SOR-001",
        "strategy_version_id": "sgv:SOR-001:v2",
        "event_spec_id": "event_spec:SOR-001:SOR-LONG:v2",
        "universe_version_id": "universe:sor-long:v2:1",
        "universe_semantic_digest": SEMANTIC_DIGEST,
        "runtime_profile_id": "tiny-live-v1",
        "owner_policy_id": "policy-main",
        "owner_policy_version": 7,
        "runtime_scope_id": f"scope-v2-{index}",
        "runtime_scope_version": 1,
        "account_id": "account-main",
        "venue_id": "binance-usdm",
        "exchange_instrument_id": "binance-usdm:BTCUSDT:perpetual",
        "position_side": "long",
        "netting_domain_key": f"domain-v2-{index}",
        "fact_digest": FACT_DIGEST,
        "entry_admission_snapshot_digest": "sha256:" + "1" * 64,
        "account_entry_health_digest": "sha256:" + "2" * 64,
        "instrument_entry_health_digest": "sha256:" + "3" * 64,
        "instrument_rules_projection_version": 1,
        "account_capacity_domain_key": "binance-usdm:account-main",
        "leverage_domain_key": (
            "binance-usdm:account-main:binance-usdm:BTCUSDT:perpetual"
        ),
        "total_wallet_balance_at_claim": Decimal(100),
        "total_margin_balance_at_claim": Decimal(100),
        "total_initial_margin_at_claim": Decimal(0),
        "total_maintenance_margin_at_claim": Decimal(0),
        "available_margin_at_claim": Decimal(100),
        "mark_price_at_claim": Decimal(100),
        "position_mode_at_claim": "independent_sides",
        "margin_mode_at_claim": "cross",
        "active_ticket_count_at_claim": index - 1,
        "remaining_slots_at_claim": 4 - index,
        "gross_risk_at_stop_at_claim": Decimal(index - 1),
        "current_reserved_margin_at_claim": Decimal(20 * (index - 1)),
        "max_ticket_stop_risk_fraction": Decimal("0.03"),
        "max_gross_stop_risk_fraction": Decimal("0.06"),
        "max_ticket_initial_margin_fraction": Decimal("0.45"),
        "max_gross_initial_margin_utilization": Decimal("0.90"),
        "planned_stop_risk_budget": Decimal(1),
        "max_post_fill_stop_risk_overrun_fraction": Decimal("0.10"),
        "post_fill_stop_risk_limit": Decimal("1.1"),
        "post_stop_stress_multiple": Decimal(2),
        "ticket_margin_budget": Decimal(45),
        "required_leverage": 5,
        "selected_leverage": 5,
        "configured_leverage_at_claim": 5,
        "leverage_change_required": False,
        "exchange_max_leverage": 10,
        "reserved_margin": Decimal(20),
        "cross_margin_stress_evidence": {},
        "entry_reference_price": Decimal(100),
        "quantity": Decimal(1),
        "notional": Decimal(100),
        "risk_at_stop": Decimal(1),
        "entry_order_type": "market",
        "entry_limit_price": None,
        "initial_stop_price": Decimal(99),
        "take_profit_prices": ["101"],
        "take_profit_quantities": ["0.5"],
        "decision_digest": decision_digest,
        "created_at_ms": created_at_ms,
        "expires_at_ms": created_at_ms + 1_000,
    }


def _ticket_values(*, index: int, created_at_ms: int) -> dict[str, object]:
    terminal_at_ms = 3_000 if index == 1 else None
    return {
        "ticket_id": f"ticket-v2-{index}",
        "exposure_episode_id": f"episode-v2-{index}",
        "signal_event_id": f"signal-v2-{index}",
        "strategy_group_id": "SOR-001",
        "strategy_version_id": "sgv:SOR-001:v2",
        "event_spec_id": "event_spec:SOR-001:SOR-LONG:v2",
        "universe_version_id": "universe:sor-long:v2:1",
        "universe_semantic_digest": SEMANTIC_DIGEST,
        "runtime_profile_id": "tiny-live-v1",
        "owner_policy_id": "policy-main",
        "owner_policy_version": 7,
        "runtime_scope_id": f"scope-v2-{index}",
        "runtime_scope_version": 1,
        "account_id": "account-main",
        "venue_id": "binance-usdm",
        "exchange_instrument_id": "binance-usdm:BTCUSDT:perpetual",
        "position_side": "long",
        "netting_domain_key": f"domain-v2-{index}",
        "active_netting_domain_key": (
            None if terminal_at_ms is not None else f"domain-v2-{index}"
        ),
        "entry_reference_price": Decimal(100),
        "quantity": Decimal(1),
        "notional": Decimal(100),
        "capacity_claim_id": f"claim-v2-{index}",
        "planned_stop_risk_budget": Decimal(1),
        "post_fill_stop_risk_limit": Decimal("1.1"),
        "selected_leverage": 5,
        "leverage_change_required": False,
        "reserved_margin": Decimal(20),
        "risk_reservation_basis": "planned_stop_distance",
        "margin_mode": "cross",
        "cross_margin_stress_model_id": "cross-margin-stop-stress-v1",
        "post_stop_stress_multiple": Decimal(2),
        "claim_stress_proof_digest": "sha256:" + "4" * 64,
        "risk_at_stop": Decimal(1),
        "entry_order_type": "market",
        "entry_limit_price": None,
        "initial_stop_price": Decimal(99),
        "take_profit_prices": ["101"],
        "take_profit_quantities": ["0.5"],
        "fact_digest": FACT_DIGEST,
        "decision_digest": (
            DECISION_DIGEST_1 if index == 1 else DECISION_DIGEST_2
        ),
        "status": "terminal" if terminal_at_ms is not None else "issued",
        "created_at_ms": created_at_ms,
        "expires_at_ms": created_at_ms + 1_000,
        "terminal_at_ms": terminal_at_ms,
    }


async def _preservation_manifest(engine: AsyncEngine) -> dict[str, object]:
    async with engine.connect() as connection:
        counts = {
            table: int(
                await connection.scalar(
                    sa.text(f"SELECT count(*) FROM {table}")
                )
                or 0
            )
            for table in (
                "brc_signal_events",
                "brc_capacity_claims",
                "brc_trade_tickets",
                "brc_budget_reservations",
                "brc_exchange_commands",
                "brc_runtime_incidents",
                "brc_trade_reviews",
            )
        }
        ticket_rows = tuple(
            tuple(row)
            for row in (
                await connection.execute(
                    sa.text(
                        """
                        SELECT ticket_id, exposure_episode_id, signal_event_id,
                               status, terminal_at_ms
                          FROM brc_trade_tickets
                      ORDER BY ticket_id
                        """
                    )
                )
            ).all()
        )
    return {"counts": counts, "tickets": ticket_rows}


async def _assert_head_shape_and_backfill(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        revision = await connection.scalar(
            sa.text("SELECT version_num FROM alembic_version")
        )
        signal_rows = (
            await connection.execute(
                sa.text(
                    """
                    SELECT signal_event_id, exposure_episode_id
                      FROM brc_signal_events
                  ORDER BY signal_event_id
                    """
                )
            )
        ).all()
        claim_rows = (
            await connection.execute(
                sa.text(
                    """
                    SELECT capacity_claim_id, exposure_episode_id,
                           exit_policy_id, exit_policy_semantic_hash,
                           active_strategy_group_ticket_count_at_claim,
                           max_strategy_group_concurrent_tickets,
                           remaining_strategy_group_slots_at_claim
                      FROM brc_capacity_claims
                  ORDER BY capacity_claim_id
                    """
                )
            )
        ).mappings().all()
        ticket_rows = (
            await connection.execute(
                sa.text(
                    """
                    SELECT ticket_id, exit_policy_id,
                           exit_policy_semantic_hash, terminal_at_ms
                      FROM brc_trade_tickets
                  ORDER BY ticket_id
                    """
                )
            )
        ).mappings().all()
        policy_columns = await connection.run_sync(
            lambda sync: {
                column["name"]: column["default"]
                for column in sa.inspect(sync).get_columns(
                    "brc_owner_policy_current"
                )
                if column["name"]
                in {
                    "family_ticket_limits",
                    "directional_stop_risk_limit_fraction",
                    "min_materialization_ratio",
                }
            }
        )
        historical_ticket = await PostgresTicketRepository(
            connection
        ).get_historical_terminal("ticket-v2-1")
        historical_claim = await PostgresCapacityClaimRepository(
            connection
        ).get_historical_terminal("claim-v2-1")
        policy_limit = await connection.scalar(
            sa.text(
                """
                SELECT max_strategy_group_concurrent_tickets
                  FROM brc_owner_policy_current
                 WHERE owner_policy_id = 'policy-main'
                """
            )
        )
        head_columns = await connection.run_sync(
            lambda sync: {
                table: {
                    column["name"]
                    for column in sa.inspect(sync).get_columns(table)
                }
                for table in (
                    "brc_signal_events",
                    "brc_owner_policy_current",
                    "brc_capacity_claims",
                    "brc_trade_tickets",
                )
            }
        )
        ticket_indexes = await connection.run_sync(
            lambda sync: {
                index["name"]
                for index in sa.inspect(sync).get_indexes("brc_trade_tickets")
            }
        )

    assert revision == HEAD_REVISION
    assert signal_rows == [
        ("signal-v2-1", "legacy:signal:signal-v2-1"),
        ("signal-v2-2", "legacy:signal:signal-v2-2"),
    ]
    assert [row["exposure_episode_id"] for row in claim_rows] == [
        "episode-v2-1",
        "episode-v2-2",
    ]
    assert [row["active_strategy_group_ticket_count_at_claim"] for row in claim_rows] == [0, 1]
    assert [row["max_strategy_group_concurrent_tickets"] for row in claim_rows] == [2, 2]
    assert [row["remaining_strategy_group_slots_at_claim"] for row in claim_rows] == [2, 1]
    assert all(row["exit_policy_id"] == "exit-policy:SOR-001:SOR-LONG:right-tail-v1" for row in claim_rows)
    assert all(row["exit_policy_semantic_hash"] == EXIT_POLICY_HASH for row in claim_rows)
    assert all(row["exit_policy_id"] == "exit-policy:SOR-001:SOR-LONG:right-tail-v1" for row in ticket_rows)
    assert all(row["exit_policy_semantic_hash"] == EXIT_POLICY_HASH for row in ticket_rows)
    assert ticket_rows[1]["terminal_at_ms"] is None
    assert policy_limit is None
    assert policy_columns == {
        "family_ticket_limits": None,
        "directional_stop_risk_limit_fraction": None,
        "min_materialization_ratio": None,
    }
    assert historical_ticket is not None
    assert historical_ticket.ticket_id == "ticket-v2-1"
    assert historical_ticket.exposure_family == "opening_range"
    assert historical_claim is not None
    assert historical_claim.capacity_claim_id == "claim-v2-1"
    assert historical_claim.exposure_family == "opening_range"
    for table_name, table in (
        ("brc_signal_events", pg_models.signal_events),
        ("brc_owner_policy_current", pg_models.owner_policy_current),
        ("brc_capacity_claims", pg_models.capacity_claims),
        ("brc_trade_tickets", pg_models.trade_tickets),
    ):
        assert head_columns[table_name] == set(table.c.keys())
    assert "ix_brc_trade_tickets_active_strategy_group" in ticket_indexes


async def _insert_v3_event_with_reused_event_id(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            sa.insert(pg_models.strategy_versions).values(
                strategy_version_id="sgv:SOR-001:v3",
                strategy_group_id="SOR-001",
                version=3,
                semantics={"producer": "edge-cross-v3"},
                status="active",
                created_at_ms=4_000,
            )
        )
        await connection.execute(
            sa.insert(pg_models.event_specs).values(
                event_spec_id="event_spec:SOR-001:SOR-LONG:v3",
                strategy_version_id="sgv:SOR-001:v3",
                event_id="SOR-LONG",
                position_side="long",
                timeframe="15m",
                freshness_window_ms=900_000,
                event_time_authority="close_time",
                entry_order_type="market",
                protection_reference_fact_definition_id="fact:range-low:v3",
                exit_policy_id="exit-policy:SOR-001:SOR-LONG:sor-v3-right-tail-v1",
                execution_semantics={},
                status="active",
                created_at_ms=4_000,
            )
        )


def _run_migration(
    database_url: str,
    *arguments: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        (
            sys.executable,
            "-m",
            "alembic",
            "-c",
            "migrations/trading_kernel/alembic.ini",
            *arguments,
        ),
        cwd=REPO_ROOT,
        env=os.environ | {"TRADING_KERNEL_DATABASE_URL": database_url},
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
