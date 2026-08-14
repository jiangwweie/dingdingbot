"""Exact-source disposable PostgreSQL migration fixtures for tests only."""

import os
import subprocess
import sys
from collections.abc import AsyncGenerator, Mapping
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

import asyncpg
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from migrations.trading_kernel import v4_schema
from src.trading_kernel.infrastructure import pg_models
from tests.trading_kernel.support.postgres import (
    SAFE_TEST_DATABASE as SAFE_DATABASE,
)
from tests.trading_kernel.support.postgres import (
    TEST_POSTGRES_ADMIN_DSN as ADMIN_DSN,
)
from tests.trading_kernel.support.postgres import async_database_url

V4_REVISION = "0001_trading_kernel_baseline_v4"
SOR_V3_REVISION = "0002_sor_v3_strategy_group_capacity"
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
    database_url = async_database_url(database_name)
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
        "decision_digest": (DECISION_DIGEST_1 if index == 1 else DECISION_DIGEST_2),
        "status": "terminal" if terminal_at_ms is not None else "issued",
        "created_at_ms": created_at_ms,
        "expires_at_ms": created_at_ms + 1_000,
        "terminal_at_ms": terminal_at_ms,
    }


async def _preservation_manifest(engine: AsyncEngine) -> dict[str, object]:
    async with engine.connect() as connection:
        counts = {
            table: int(
                await connection.scalar(sa.text(f"SELECT count(*) FROM {table}")) or 0
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


async def _assert_0002_shape_and_backfill(engine: AsyncEngine) -> None:
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
            (
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
            )
            .mappings()
            .all()
        )
        ticket_rows = (
            (
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
            )
            .mappings()
            .all()
        )
        policy_limit = await connection.scalar(
            sa.text(
                """
                SELECT max_strategy_group_concurrent_tickets
                  FROM brc_owner_policy_current
                 WHERE owner_policy_id = 'policy-main'
                """
            )
        )
        ticket_indexes = await connection.run_sync(
            lambda sync: {
                index["name"]
                for index in sa.inspect(sync).get_indexes("brc_trade_tickets")
            }
        )

    assert revision == SOR_V3_REVISION
    assert signal_rows == [
        ("signal-v2-1", "legacy:signal:signal-v2-1"),
        ("signal-v2-2", "legacy:signal:signal-v2-2"),
    ]
    assert [row["exposure_episode_id"] for row in claim_rows] == [
        "episode-v2-1",
        "episode-v2-2",
    ]
    assert [
        row["active_strategy_group_ticket_count_at_claim"] for row in claim_rows
    ] == [0, 1]
    assert [row["max_strategy_group_concurrent_tickets"] for row in claim_rows] == [
        2,
        2,
    ]
    assert [row["remaining_strategy_group_slots_at_claim"] for row in claim_rows] == [
        2,
        1,
    ]
    assert all(
        row["exit_policy_id"] == "exit-policy:SOR-001:SOR-LONG:right-tail-v1"
        for row in claim_rows
    )
    assert all(
        row["exit_policy_semantic_hash"] == EXIT_POLICY_HASH for row in claim_rows
    )
    assert all(
        row["exit_policy_id"] == "exit-policy:SOR-001:SOR-LONG:right-tail-v1"
        for row in ticket_rows
    )
    assert all(
        row["exit_policy_semantic_hash"] == EXIT_POLICY_HASH for row in ticket_rows
    )
    assert ticket_rows[1]["terminal_at_ms"] is None
    assert policy_limit == 2
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


SOURCE_REVISION = "0002_sor_v3_strategy_group_capacity"

SOURCE_HISTORY_COLUMNS = {
    "brc_signal_events": "signal_event_id runtime_scope_id runtime_scope_version strategy_group_id strategy_version_id event_spec_id universe_version_id universe_semantic_digest exchange_instrument_id position_side fact_digest occurred_at_ms observed_at_ms expires_at_ms exposure_episode_id",
    "brc_capacity_claims": "capacity_claim_id ticket_id signal_event_id exposure_episode_id strategy_group_id strategy_version_id event_spec_id universe_version_id universe_semantic_digest runtime_profile_id owner_policy_id owner_policy_version runtime_scope_id runtime_scope_version account_id venue_id exchange_instrument_id position_side netting_domain_key fact_digest entry_admission_snapshot_digest account_entry_health_digest instrument_entry_health_digest instrument_rules_projection_version account_capacity_domain_key leverage_domain_key total_wallet_balance_at_claim total_margin_balance_at_claim total_initial_margin_at_claim total_maintenance_margin_at_claim available_margin_at_claim mark_price_at_claim position_mode_at_claim margin_mode_at_claim active_ticket_count_at_claim remaining_slots_at_claim gross_risk_at_stop_at_claim current_reserved_margin_at_claim max_ticket_stop_risk_fraction max_gross_stop_risk_fraction max_ticket_initial_margin_fraction max_gross_initial_margin_utilization planned_stop_risk_budget max_post_fill_stop_risk_overrun_fraction post_fill_stop_risk_limit post_stop_stress_multiple ticket_margin_budget required_leverage selected_leverage configured_leverage_at_claim leverage_change_required exchange_max_leverage reserved_margin cross_margin_stress_evidence entry_reference_price quantity notional risk_at_stop entry_order_type entry_limit_price initial_stop_price take_profit_prices take_profit_quantities decision_digest created_at_ms expires_at_ms exit_policy_id exit_policy_semantic_hash active_strategy_group_ticket_count_at_claim max_strategy_group_concurrent_tickets remaining_strategy_group_slots_at_claim pre_tp1_reclaim_price exposure_session_end_ms",
    "brc_trade_tickets": "ticket_id exposure_episode_id signal_event_id strategy_group_id strategy_version_id event_spec_id universe_version_id universe_semantic_digest runtime_profile_id owner_policy_id owner_policy_version runtime_scope_id runtime_scope_version account_id venue_id exchange_instrument_id position_side netting_domain_key active_netting_domain_key entry_reference_price quantity notional capacity_claim_id planned_stop_risk_budget post_fill_stop_risk_limit selected_leverage leverage_change_required reserved_margin risk_reservation_basis margin_mode cross_margin_stress_model_id post_stop_stress_multiple claim_stress_proof_digest risk_at_stop entry_order_type entry_limit_price initial_stop_price take_profit_prices take_profit_quantities fact_digest decision_digest status created_at_ms expires_at_ms terminal_at_ms exit_policy_id exit_policy_semantic_hash pre_tp1_reclaim_price exposure_session_end_ms",
    "brc_budget_reservations": "budget_reservation_id ticket_id owner_policy_id venue_id account_id reserved_notional reserved_risk reserved_margin planned_stop_risk_budget risk_reservation_basis status created_at_ms released_at_ms",
    "brc_exchange_commands": "command_id ticket_id command_kind generation idempotency_key venue_client_order_id status quantity request_payload result_payload claim_owner lease_until_ms created_at_ms deadline_at_ms completed_at_ms",
    "brc_runtime_incidents": "incident_id ticket_id incident_kind status first_blocker entry_block_scope entry_block_key details opened_at_ms resolved_at_ms",
    "brc_trade_aggregates": "ticket_id status version last_event_sequence entry_lane_held position_qty average_fill_price actual_stop_risk venue_reported_liquidation_price post_fill_risk_status post_fill_disposition post_fill_stress_status post_fill_stress_proof_digest protected_qty entry_exchange_order_id initial_stop_exchange_order_id active_stop_exchange_order_id active_stop_price tp1_exchange_order_id tp1_target_qty tp1_filled_qty break_even_floor_price pending_replaced_stop_exchange_order_id pending_stop_price pending_stop_watermark_ms runner_stop_watermark_ms pending_cancel_exchange_order_id exit_exchange_order_id review_id lifecycle_due_at_ms reconciliation_due_at_ms updated_at_ms",
    "brc_trade_events": "event_id ticket_id sequence event_type payload occurred_at_ms",
    "brc_trade_reviews": "review_id ticket_id revision supersedes_review_id outcome metrics decision_impact created_at_ms",
}
CERTIFIED_0002_SOURCE_EVENTS = (
    {
        "strategy_group_id": "BRF2-001",
        "display_name": "BRF2 bear rally failure",
        "strategy_version_id": "sgv:BRF2-001:v2",
        "strategy_version": 2,
        "version_event_spec_ids": ("event_spec:BRF2-001:BRF2-SHORT:v2",),
        "version_registry_semantic_hash": (
            "sha256:5c981c7aae2e8d914c27f0cf5611ed0dd0c38b874212ae3f4145a64a78e83e38"
        ),
        "version_source": "committed_old_main_program_v2",
        "event_spec_id": "event_spec:BRF2-001:BRF2-SHORT:v2",
        "event_id": "BRF2-SHORT",
        "position_side": "short",
        "timeframe": "1h",
        "freshness_window_ms": 3_600_000,
        "protection_fact_id": "fact:rally_high_reference:v1",
        "exit_policy_id": "exit-policy:BRF2-001:BRF2-SHORT:right-tail-v1",
        "event_semantic_hash": (
            "sha256:93ec2c387c02442bb4f2d4a936aa035a30376cb1a25df194a15a2d4809a1ab66"
        ),
        "event_source": "committed_old_main_program_v2",
        "facts": (
            (
                "fact:rally_failure_confirmed:v1",
                "rally_failure_confirmed",
                "boolean",
                3_600_000,
                "boolean",
                "condition",
                True,
            ),
            (
                "fact:short_side_not_disabled:v1",
                "short_side_not_disabled",
                "boolean",
                3_600_000,
                "boolean",
                "condition",
                True,
            ),
            (
                "fact:rally_high_reference:v1",
                "rally_high_reference",
                "decimal",
                3_600_000,
                "positive_decimal",
                "protection_reference",
                True,
            ),
            (
                "fact:strong_uptrend_disable:v1",
                "strong_uptrend_disable",
                "boolean",
                3_600_000,
                "boolean",
                "disable",
                True,
            ),
        ),
        "exit_policy_version": "2026-07-22-v1",
        "exit_policy_semantic_hash": (
            "sha256:cfaf3e3ab185ac35a8dadc48aab519dcf75816d2ecb6836fece892612d833f47"
        ),
        "runner_reference_fact": "rally_high_reference",
        "runner_structure_rule": "confirmed_lower_high",
        "time_stop_bars": None,
    },
    {
        "strategy_group_id": "CPM-RO-001",
        "display_name": "CPM reclaim pullback recovery",
        "strategy_version_id": "sgv:CPM-RO-001:v2",
        "strategy_version": 2,
        "version_event_spec_ids": ("event_spec:CPM-RO-001:CPM-LONG:v2",),
        "version_registry_semantic_hash": (
            "sha256:5c981c7aae2e8d914c27f0cf5611ed0dd0c38b874212ae3f4145a64a78e83e38"
        ),
        "version_source": "committed_old_main_program_v2",
        "event_spec_id": "event_spec:CPM-RO-001:CPM-LONG:v2",
        "event_id": "CPM-LONG",
        "position_side": "long",
        "timeframe": "1h",
        "freshness_window_ms": 3_600_000,
        "protection_fact_id": "fact:pullback_low_reference:v1",
        "exit_policy_id": "exit-policy:CPM-RO-001:CPM-LONG:right-tail-v1",
        "event_semantic_hash": (
            "sha256:d4a9ceb2c096a13701ca148438d607bee970deef5d658790aa1081f816661a2e"
        ),
        "event_source": "committed_old_main_program_v2",
        "facts": (
            (
                "fact:htf_trend_intact:v1",
                "htf_trend_intact",
                "boolean",
                3_600_000,
                "boolean",
                "condition",
                True,
            ),
            (
                "fact:reclaim_confirmed:v1",
                "reclaim_confirmed",
                "boolean",
                3_600_000,
                "boolean",
                "condition",
                True,
            ),
            (
                "fact:pullback_low_reference:v1",
                "pullback_low_reference",
                "decimal",
                3_600_000,
                "positive_decimal",
                "protection_reference",
                True,
            ),
        ),
        "exit_policy_version": "2026-07-22-v1",
        "exit_policy_semantic_hash": (
            "sha256:3d67119246c8ff29e47193b88d32e8c43333d39d8cbdd25cf266b7a42871e887"
        ),
        "runner_reference_fact": "pullback_low_reference",
        "runner_structure_rule": "confirmed_higher_low",
        "time_stop_bars": None,
    },
    {
        "strategy_group_id": "MI-001",
        "display_name": "MI relative strength impulse",
        "strategy_version_id": "sgv:MI-001:v2",
        "strategy_version": 2,
        "version_event_spec_ids": ("event_spec:MI-001:MI-LONG:v2",),
        "version_registry_semantic_hash": (
            "sha256:5c981c7aae2e8d914c27f0cf5611ed0dd0c38b874212ae3f4145a64a78e83e38"
        ),
        "version_source": "committed_old_main_program_v2",
        "event_spec_id": "event_spec:MI-001:MI-LONG:v2",
        "event_id": "MI-LONG",
        "position_side": "long",
        "timeframe": "1h",
        "freshness_window_ms": 3_600_000,
        "protection_fact_id": "fact:impulse_invalidation_reference:v1",
        "exit_policy_id": "exit-policy:MI-001:MI-LONG:right-tail-v1",
        "event_semantic_hash": (
            "sha256:533abcf09e68d590f2619507cc5951229bf0a95b18eae8fbf4ae384e21edff0f"
        ),
        "event_source": "committed_old_main_program_v2",
        "facts": (
            (
                "fact:impulse_confirmed:v1",
                "impulse_confirmed",
                "boolean",
                3_600_000,
                "boolean",
                "condition",
                True,
            ),
            (
                "fact:relative_strength_confirmed:v1",
                "relative_strength_confirmed",
                "boolean",
                3_600_000,
                "boolean",
                "condition",
                True,
            ),
            (
                "fact:impulse_invalidation_reference:v1",
                "impulse_invalidation_reference",
                "decimal",
                3_600_000,
                "positive_decimal",
                "protection_reference",
                True,
            ),
        ),
        "exit_policy_version": "2026-07-22-v1",
        "exit_policy_semantic_hash": (
            "sha256:485125ed39c3997e918d3f358ea38fe353a74696916f64cc44c2f8a5e3ba0cde"
        ),
        "runner_reference_fact": "impulse_invalidation_reference",
        "runner_structure_rule": "confirmed_higher_low",
        "time_stop_bars": None,
    },
    {
        "strategy_group_id": "MPG-001",
        "display_name": "MPG momentum persistence",
        "strategy_version_id": "sgv:MPG-001:v2",
        "strategy_version": 2,
        "version_event_spec_ids": ("event_spec:MPG-001:MPG-LONG:v2",),
        "version_registry_semantic_hash": (
            "sha256:5c981c7aae2e8d914c27f0cf5611ed0dd0c38b874212ae3f4145a64a78e83e38"
        ),
        "version_source": "committed_old_main_program_v2",
        "event_spec_id": "event_spec:MPG-001:MPG-LONG:v2",
        "event_id": "MPG-LONG",
        "position_side": "long",
        "timeframe": "1h",
        "freshness_window_ms": 3_600_000,
        "protection_fact_id": "fact:momentum_floor_reference:v1",
        "exit_policy_id": "exit-policy:MPG-001:MPG-LONG:right-tail-v1",
        "event_semantic_hash": (
            "sha256:e7161b5c5b3fb8f2c6edbb134ea1081f80e55db74304e99a84c1cb20e3b93939"
        ),
        "event_source": "committed_old_main_program_v2",
        "facts": (
            (
                "fact:momentum_persistence_confirmed:v1",
                "momentum_persistence_confirmed",
                "boolean",
                3_600_000,
                "boolean",
                "condition",
                True,
            ),
            (
                "fact:leader_strength_confirmed:v1",
                "leader_strength_confirmed",
                "boolean",
                3_600_000,
                "boolean",
                "condition",
                True,
            ),
            (
                "fact:momentum_floor_reference:v1",
                "momentum_floor_reference",
                "decimal",
                3_600_000,
                "positive_decimal",
                "protection_reference",
                True,
            ),
        ),
        "exit_policy_version": "2026-07-22-v1",
        "exit_policy_semantic_hash": (
            "sha256:421d7391e90795b434ff953971d240fbb6205d68191ca06cf9cc34ebd6c3f787"
        ),
        "runner_reference_fact": "momentum_floor_reference",
        "runner_structure_rule": "confirmed_higher_low",
        "time_stop_bars": None,
    },
    {
        "strategy_group_id": "SOR-001",
        "display_name": "SOR opening range breakout and breakdown",
        "strategy_version_id": "sgv:SOR-001:v3",
        "strategy_version": 3,
        "version_event_spec_ids": (
            "event_spec:SOR-001:SOR-LONG:v3",
            "event_spec:SOR-001:SOR-SHORT:v3",
        ),
        "version_registry_semantic_hash": (
            "sha256:d017b33320bea0f40a03dae475f0693f710c5e2c52b9a0e8e90821f4132c5e96"
        ),
        "version_source": "committed_strategy_registry_contract",
        "event_spec_id": "event_spec:SOR-001:SOR-LONG:v3",
        "event_id": "SOR-LONG",
        "position_side": "long",
        "timeframe": "15m",
        "freshness_window_ms": 900_000,
        "protection_fact_id": "fact:opening_range_low_reference_v3:v3",
        "exit_policy_id": "exit-policy:SOR-001:SOR-LONG:sor-v3-right-tail-v1",
        "event_semantic_hash": (
            "sha256:e9fbd06ccf63a5b0bd3079f246312bb52bd4cb1c670cc51ed13343701ae2e392"
        ),
        "event_source": "committed_strategy_registry_contract",
        "facts": (
            (
                "fact:opening_range_defined_v3:v3",
                "opening_range_defined_v3",
                "boolean",
                900_000,
                "boolean",
                "condition",
                True,
            ),
            (
                "fact:breakout_edge_crossed_v3:v3",
                "breakout_edge_crossed_v3",
                "boolean",
                900_000,
                "boolean",
                "condition",
                True,
            ),
            (
                "fact:opening_range_high_reference_v3:v3",
                "opening_range_high_reference_v3",
                "decimal",
                900_000,
                "positive_decimal",
                "lifecycle_reference",
                True,
            ),
            (
                "fact:opening_range_low_reference_v3:v3",
                "opening_range_low_reference_v3",
                "decimal",
                900_000,
                "positive_decimal",
                "protection_reference",
                True,
            ),
            (
                "fact:session_start_ms_v3:v3",
                "session_start_ms_v3",
                "decimal",
                900_000,
                "positive_decimal",
                "identity_reference",
                True,
            ),
            (
                "fact:session_end_ms_v3:v3",
                "session_end_ms_v3",
                "decimal",
                900_000,
                "positive_decimal",
                "lifecycle_reference",
                True,
            ),
        ),
        "exit_policy_version": "2026-07-31-sor-v3",
        "exit_policy_semantic_hash": (
            "sha256:0df1319dba726a769a4a3abe827588e141bcab6b3c83fe5d79d98a109e6a1478"
        ),
        "runner_reference_fact": "opening_range_low_reference_v3",
        "runner_structure_rule": "confirmed_higher_low",
        "time_stop_bars": 96,
    },
    {
        "strategy_group_id": "SOR-001",
        "display_name": "SOR opening range breakout and breakdown",
        "strategy_version_id": "sgv:SOR-001:v3",
        "strategy_version": 3,
        "version_event_spec_ids": (
            "event_spec:SOR-001:SOR-LONG:v3",
            "event_spec:SOR-001:SOR-SHORT:v3",
        ),
        "version_registry_semantic_hash": (
            "sha256:d017b33320bea0f40a03dae475f0693f710c5e2c52b9a0e8e90821f4132c5e96"
        ),
        "version_source": "committed_strategy_registry_contract",
        "event_spec_id": "event_spec:SOR-001:SOR-SHORT:v3",
        "event_id": "SOR-SHORT",
        "position_side": "short",
        "timeframe": "15m",
        "freshness_window_ms": 900_000,
        "protection_fact_id": "fact:opening_range_high_reference_v3:v3",
        "exit_policy_id": "exit-policy:SOR-001:SOR-SHORT:sor-v3-right-tail-v1",
        "event_semantic_hash": (
            "sha256:36ce263f26e1359b1a809683f40b64b0ca8cb98d6ce49d4d79a3bb069a4c1ed5"
        ),
        "event_source": "committed_strategy_registry_contract",
        "facts": (
            (
                "fact:opening_range_defined_v3:v3",
                "opening_range_defined_v3",
                "boolean",
                900_000,
                "boolean",
                "condition",
                True,
            ),
            (
                "fact:breakdown_edge_crossed_v3:v3",
                "breakdown_edge_crossed_v3",
                "boolean",
                900_000,
                "boolean",
                "condition",
                True,
            ),
            (
                "fact:opening_range_low_reference_v3:v3",
                "opening_range_low_reference_v3",
                "decimal",
                900_000,
                "positive_decimal",
                "lifecycle_reference",
                True,
            ),
            (
                "fact:opening_range_high_reference_v3:v3",
                "opening_range_high_reference_v3",
                "decimal",
                900_000,
                "positive_decimal",
                "protection_reference",
                True,
            ),
            (
                "fact:session_start_ms_v3:v3",
                "session_start_ms_v3",
                "decimal",
                900_000,
                "positive_decimal",
                "identity_reference",
                True,
            ),
            (
                "fact:session_end_ms_v3:v3",
                "session_end_ms_v3",
                "decimal",
                900_000,
                "positive_decimal",
                "lifecycle_reference",
                True,
            ),
        ),
        "exit_policy_version": "2026-07-31-sor-v3",
        "exit_policy_semantic_hash": (
            "sha256:aceb71fb7311263fc4c7163b9314aa521ae279cf140d2a4f586e30d7490565bf"
        ),
        "runner_reference_fact": "opening_range_high_reference_v3",
        "runner_structure_rule": "confirmed_lower_high",
        "time_stop_bars": 96,
    },
)


async def _prepare_production_shaped_0002(engine: AsyncEngine) -> None:
    await _seed_v4_history(engine)
    result = _run_migration(_database_url(engine), "upgrade", SOURCE_REVISION)
    assert result.returncode == 0, result.stderr[-4000:]
    async with engine.begin() as connection:
        await _install_certified_0002_registry(connection)
        await connection.execute(
            sa.text(
                "UPDATE brc_owner_policy_current SET policy_version = 3, "
                "new_entry_submit_enabled = true, "
                'scope = \'{"runtime_profile_id":"tiny-live-v1",'
                '"allowed_event_spec_ids":['
                '"event_spec:BRF2-001:BRF2-SHORT:v2",'
                '"event_spec:CPM-RO-001:CPM-LONG:v2",'
                '"event_spec:MI-001:MI-LONG:v2",'
                '"event_spec:MPG-001:MPG-LONG:v2",'
                '"event_spec:SOR-001:SOR-LONG:v3",'
                '"event_spec:SOR-001:SOR-SHORT:v3"]}\'::jsonb, '
                "updated_at_ms = 1000 WHERE owner_policy_id = 'policy-main'"
            )
        )
        await connection.execute(
            sa.text(
                "INSERT INTO brc_runtime_profiles "
                "(runtime_profile_id, venue_id, account_id, environment, "
                "position_mode, status, updated_at_ms) VALUES "
                "('tiny-live-v1', 'binance-usdm', 'subaccount-source-test', "
                "'live', 'independent_sides', 'active', 1000)"
            )
        )
        await connection.execute(
            sa.text(
                "INSERT INTO brc_runtime_capabilities_current "
                "(capability_key, enabled, certified_commit, schema_revision, "
                "certification, updated_at_ms) VALUES "
                "('exchange_commands', true, "
                "'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb', "
                "'0002_sor_v3_strategy_group_capacity', "
                '\'{"stage":"observation_only"}\'::jsonb, 1000), '
                "('strategy_signal_ingest', true, "
                "'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb', "
                "'0002_sor_v3_strategy_group_capacity', "
                '\'{"stage":"observation_only"}\'::jsonb, 1000)'
            )
        )
        await connection.execute(
            sa.text(
                "UPDATE brc_trade_tickets SET status = 'terminal', "
                "active_netting_domain_key = NULL, terminal_at_ms = 3500 "
                "WHERE ticket_id = 'ticket-v2-2'"
            )
        )
        await connection.execute(
            sa.text(
                "UPDATE brc_budget_reservations SET status = 'released', "
                "released_at_ms = 3500 WHERE budget_reservation_id = 'reservation-v2-2'"
            )
        )
        await connection.execute(
            sa.text(
                "UPDATE brc_exchange_commands SET status = 'completed', "
                'result_payload = \'{"exchange_order_id":"entry-v2-2"}\'::jsonb, '
                "completed_at_ms = 3400 WHERE command_id = 'command-v2-2-entry'"
            )
        )
        await connection.execute(
            sa.text(
                "UPDATE brc_runtime_incidents SET status = 'resolved', "
                "resolved_at_ms = 3500 WHERE incident_id = 'incident-v2-2'"
            )
        )
        await connection.execute(
            sa.text(
                "INSERT INTO brc_trade_reviews VALUES "
                "('review-v2-2','ticket-v2-2',1,NULL,'closed',"
                "'{\"net_pnl_quote\":\"0\"}'::jsonb,'{}'::jsonb,3600)"
            )
        )
        await _insert_terminal_chain_rows(connection)


async def _install_certified_0002_registry(connection: Any) -> None:
    for statement in (
        (
            "UPDATE brc_exit_policies SET status = 'retired' "
            "WHERE event_spec_id = 'event_spec:SOR-001:SOR-LONG:v2'"
        ),
        (
            "UPDATE brc_event_specs SET status = 'retired' "
            "WHERE strategy_version_id = 'sgv:SOR-001:v2'"
        ),
        (
            "UPDATE brc_strategy_versions SET status = 'retired' "
            "WHERE strategy_version_id = 'sgv:SOR-001:v2'"
        ),
        (
            "UPDATE brc_strategy_groups SET "
            "display_name = 'SOR opening range breakout and breakdown', "
            "active_version_id = 'sgv:SOR-001:v3', status = 'active', "
            "updated_at_ms = 1000 WHERE strategy_group_id = 'SOR-001'"
        ),
    ):
        await connection.execute(sa.text(statement))

    groups: dict[str, dict[str, object]] = {}
    versions: dict[str, dict[str, object]] = {}
    facts: dict[str, dict[str, object]] = {}
    event_facts: list[dict[str, object]] = []
    events: list[dict[str, object]] = []
    policies: list[dict[str, object]] = []
    for event in CERTIFIED_0002_SOURCE_EVENTS:
        strategy_group_id = str(event["strategy_group_id"])
        strategy_version_id = str(event["strategy_version_id"])
        event_spec_id = str(event["event_spec_id"])
        groups[strategy_group_id] = {
            "strategy_group_id": strategy_group_id,
            "display_name": event["display_name"],
            "active_version_id": strategy_version_id,
            "status": "active",
            "updated_at_ms": 1_000,
        }
        versions[strategy_version_id] = {
            "strategy_version_id": strategy_version_id,
            "strategy_group_id": strategy_group_id,
            "version": event["strategy_version"],
            "semantics": {
                "event_spec_ids": list(event["version_event_spec_ids"]),
                "registry_semantic_hash": event["version_registry_semantic_hash"],
                "source": event["version_source"],
            },
            "status": "active",
            "created_at_ms": 1_000,
        }
        events.append(
            {
                "event_spec_id": event_spec_id,
                "strategy_version_id": strategy_version_id,
                "event_id": event["event_id"],
                "position_side": event["position_side"],
                "timeframe": event["timeframe"],
                "freshness_window_ms": event["freshness_window_ms"],
                "event_time_authority": "trigger_candle_close_time_ms",
                "entry_order_type": "market",
                "protection_reference_fact_definition_id": event["protection_fact_id"],
                "exit_policy_id": event["exit_policy_id"],
                "execution_semantics": {
                    "event_semantic_hash": event["event_semantic_hash"],
                    "signal_grade": "trial_grade_signal",
                    "source": event["event_source"],
                },
                "status": "active",
                "created_at_ms": 1_000,
            }
        )
        for (
            fact_id,
            fact_name,
            value_type,
            freshness_ms,
            satisfaction,
            role,
            required,
        ) in event["facts"]:
            facts[str(fact_id)] = {
                "fact_definition_id": fact_id,
                "fact_name": fact_name,
                "value_type": value_type,
                "freshness_ms": freshness_ms,
                "validation": {"satisfaction": satisfaction},
            }
            event_facts.append(
                {
                    "event_spec_id": event_spec_id,
                    "fact_definition_id": fact_id,
                    "role": role,
                    "required": required,
                }
            )
        policies.append(
            {
                "exit_policy_id": event["exit_policy_id"],
                "exit_policy_version": event["exit_policy_version"],
                "event_spec_id": event_spec_id,
                "position_side": event["position_side"],
                "policy": _certified_0002_exit_policy_payload(event),
                "semantic_hash": event["exit_policy_semantic_hash"],
                "status": "active",
                "created_at_ms": 1_000,
            }
        )

    await connection.execute(
        sa.insert(pg_models.strategy_groups),
        [row for key, row in groups.items() if key != "SOR-001"],
    )
    await connection.execute(
        sa.insert(pg_models.strategy_versions), list(versions.values())
    )
    await connection.execute(
        sa.insert(pg_models.fact_definitions), list(facts.values())
    )
    await connection.execute(sa.insert(pg_models.event_specs), events)
    await connection.execute(sa.insert(pg_models.exit_policies), policies)
    await connection.execute(sa.insert(pg_models.event_required_facts), event_facts)


def _certified_0002_exit_policy_payload(
    event: Mapping[str, object],
) -> dict[str, object]:
    time_stop_bars = event["time_stop_bars"]
    return {
        "exit_policy_id": event["exit_policy_id"],
        "exit_policy_version": event["exit_policy_version"],
        "event_spec_id": event["event_spec_id"],
        "event_id": event["event_id"],
        "position_side": event["position_side"],
        "tp1": {
            "reward_multiple": "1",
            "quantity_fraction": "0.5",
            "execution_style": "limit_gtc",
            "market_fallback_allowed": False,
        },
        "break_even_floor": {
            "exit_fee_basis": "conservative_taker",
            "slippage_buffer_ticks": 2,
            "minimum_improvement_ticks": 2,
        },
        "runner": {
            "kind": "structural_atr",
            "timeframe": event["timeframe"],
            "structure_rule": event["runner_structure_rule"],
            "structure_reference_fact": event["runner_reference_fact"],
            "structure_window_bars": 4,
            "atr_period": 14,
            "atr_buffer_multiple": "0.5",
            "minimum_improvement_ticks": 2,
        },
        "time_stop": (
            None if time_stop_bars is None else {"max_holding_bars": time_stop_bars}
        ),
    }


async def _insert_terminal_chain_rows(connection: Any) -> None:
    await connection.execute(
        sa.text(
            "INSERT INTO brc_strategy_universe_versions VALUES "
            "('universe:sor-long:v3:1','SOR-001',"
            "'event_spec:SOR-001:SOR-LONG:v3',1,:digest,'active',1000,1100,NULL,NULL,NULL)"
        ),
        {"digest": "sha256:" + "9" * 64},
    )
    await connection.execute(
        sa.text(
            "INSERT INTO brc_strategy_universe_members VALUES "
            "('universe:sor-long:v3:1','binance-usdm:BTCUSDT:perpetual')"
        )
    )
    await connection.execute(
        sa.text(
            "INSERT INTO brc_signal_events VALUES "
            "('signal-v3-terminal','scope-v3-terminal',1,'SOR-001','sgv:SOR-001:v3',"
            "'event_spec:SOR-001:SOR-LONG:v3','universe:sor-long:v3:1',:digest,"
            "'binance-usdm:BTCUSDT:perpetual','long',:fact_digest,3600,3700,4500,"
            "'episode-v3-terminal')"
        ),
        {"digest": "sha256:" + "9" * 64, "fact_digest": "sha256:" + "8" * 64},
    )
    claim = _claim_values(index=3, created_at_ms=3_800)
    claim.update(
        capacity_claim_id="claim-v3-terminal",
        ticket_id="ticket-v3-terminal",
        signal_event_id="signal-v3-terminal",
        exposure_episode_id="episode-v3-terminal",
        strategy_version_id="sgv:SOR-001:v3",
        event_spec_id="event_spec:SOR-001:SOR-LONG:v3",
        universe_version_id="universe:sor-long:v3:1",
        universe_semantic_digest="sha256:" + "9" * 64,
        runtime_scope_id="scope-v3-terminal",
        fact_digest="sha256:" + "8" * 64,
        exit_policy_id="exit-policy:SOR-001:SOR-LONG:sor-v3-right-tail-v1",
        exit_policy_semantic_hash=(
            "sha256:0df1319dba726a769a4a3abe827588e141bcab6b3c83fe5d79d98a109e6a1478"
        ),
        active_strategy_group_ticket_count_at_claim=0,
        max_strategy_group_concurrent_tickets=2,
        remaining_strategy_group_slots_at_claim=2,
        decision_digest="sha256:" + "7" * 64,
    )
    ticket = _ticket_values(index=3, created_at_ms=3_900)
    ticket.update(
        ticket_id="ticket-v3-terminal",
        capacity_claim_id="claim-v3-terminal",
        signal_event_id="signal-v3-terminal",
        exposure_episode_id="episode-v3-terminal",
        strategy_version_id="sgv:SOR-001:v3",
        event_spec_id="event_spec:SOR-001:SOR-LONG:v3",
        universe_version_id="universe:sor-long:v3:1",
        universe_semantic_digest="sha256:" + "9" * 64,
        runtime_scope_id="scope-v3-terminal",
        fact_digest="sha256:" + "8" * 64,
        exit_policy_id="exit-policy:SOR-001:SOR-LONG:sor-v3-right-tail-v1",
        exit_policy_semantic_hash=(
            "sha256:0df1319dba726a769a4a3abe827588e141bcab6b3c83fe5d79d98a109e6a1478"
        ),
        decision_digest="sha256:" + "7" * 64,
        status="terminal",
        active_netting_domain_key=None,
        terminal_at_ms=4_500,
    )
    await connection.execute(sa.insert(pg_models.capacity_claims).values(claim))
    await connection.execute(sa.insert(pg_models.trade_tickets).values(ticket))
    for statement in (
        (
            "INSERT INTO brc_budget_reservations VALUES "
            "('reservation-v3-terminal','ticket-v3-terminal','policy-main',"
            "'binance-usdm','account-main',100,1,20,1,'planned_stop_distance',"
            "'released',4000,4500)"
        ),
        (
            "INSERT INTO brc_exchange_commands VALUES "
            "('command-v3-terminal-entry','ticket-v3-terminal','entry',1,"
            "'idem-v3-terminal','client-v3-terminal','completed',1,'{}'::jsonb,"
            '\'{"exchange_order_id":"entry-v3-terminal"}\'::jsonb,NULL,NULL,'
            "4000,4400,4100)"
        ),
        (
            "INSERT INTO brc_trade_reviews VALUES "
            "('review-v3-terminal','ticket-v3-terminal',1,NULL,'closed',"
            '\'{"net_pnl_quote":"1","settlement_asset":"USDT"}\'::jsonb,'
            "'{}'::jsonb,4500)"
        ),
        (
            "INSERT INTO brc_trade_aggregates (ticket_id,status,version,"
            "last_event_sequence,entry_lane_held,position_qty,protected_qty,"
            "tp1_target_qty,tp1_filled_qty,review_id,updated_at_ms) VALUES "
            "('ticket-v3-terminal','terminal',10,10,false,0,0,0,0,"
            "'review-v3-terminal',4500)"
        ),
        (
            "INSERT INTO brc_trade_events VALUES "
            "('event-v3-terminal-settlement','ticket-v3-terminal',10,"
            "'settlement_completed',"
            '\'{"settlement_asset":"USDT"}\'::jsonb,4500)'
        ),
    ):
        await connection.execute(sa.text(statement))


async def _install_source_runtime_identity(engine: AsyncEngine) -> None:
    values = {
        "runtime_commit": "b" * 40,
        "schema_revision": SOURCE_REVISION,
        "seed_identity": "sha256:" + "c" * 64,
    }
    async with engine.begin() as connection:
        for key, value in values.items():
            await connection.execute(
                sa.text(
                    "INSERT INTO brc_schema_metadata "
                    "(metadata_key, metadata_value, updated_at_ms) "
                    "VALUES (:key, :value, 1000) "
                    "ON CONFLICT (metadata_key) DO UPDATE "
                    "SET metadata_value = EXCLUDED.metadata_value, "
                    "updated_at_ms = EXCLUDED.updated_at_ms"
                ),
                {"key": key, "value": value},
            )


def _database_url(engine: AsyncEngine) -> str:
    return engine.url.render_as_string(hide_password=False)
