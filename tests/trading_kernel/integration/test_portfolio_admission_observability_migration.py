from __future__ import annotations

import json
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.ext.asyncio import AsyncEngine

from src.trading_kernel.infrastructure import pg_models
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_identity import (
    CURRENT_SCHEMA_REVISION,
)
from src.trading_kernel.infrastructure.strategy_registry_seed import (
    seed_strategy_registry,
)
from tests.trading_kernel.integration.test_sor_v3_compatible_migration import (
    HEAD_REVISION,
    _claim_values,
    _run_migration,
    _seed_v4_history,
    _ticket_values,
    compatible_migration_engine,
)

__all__ = ["compatible_migration_engine"]

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
        "version_event_spec_ids": (
            "event_spec:BRF2-001:BRF2-SHORT:v2",
        ),
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
        "version_event_spec_ids": (
            "event_spec:CPM-RO-001:CPM-LONG:v2",
        ),
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


def test_runtime_identity_points_to_portfolio_admission_head() -> None:
    assert CURRENT_SCHEMA_REVISION == HEAD_REVISION


def test_alembic_has_one_exact_portfolio_admission_head() -> None:
    config = Config("migrations/trading_kernel/alembic.ini")
    heads = ScriptDirectory.from_config(config).get_heads()

    assert heads == [HEAD_REVISION]


@pytest.mark.asyncio
async def test_0003_creates_shadow_table_matching_current_metadata(
    compatible_migration_engine: AsyncEngine,
) -> None:
    engine = compatible_migration_engine
    result = _run_migration(_database_url(engine), "upgrade", "head")
    assert result.returncode == 0, result.stderr[-4000:]

    async with engine.connect() as connection:
        tables = await connection.run_sync(
            lambda sync: set(sa.inspect(sync).get_table_names())
        )
        columns = await connection.run_sync(
            lambda sync: {
                column["name"]
                for column in sa.inspect(sync).get_columns(
                    "brc_shadow_outcomes_current"
                )
            }
        )

    assert "brc_shadow_outcomes_current" in tables
    assert columns == {
        "shadow_outcome_id",
        "admission_decision_id",
        "status",
        "evaluation_kind",
        "exchange_instrument_id",
        "position_side",
        "timeframe",
        "entry_reference_price",
        "initial_stop_price",
        "initial_risk_per_unit",
        "horizon_start_ms",
        "horizon_end_ms",
        "claim_owner",
        "claim_token",
        "lease_until_ms",
        "max_favorable_price",
        "max_adverse_price",
        "mfe_r",
        "mae_r",
        "observed_through_ms",
        "completion_reason",
        "projection_version",
        "created_at_ms",
        "completed_at_ms",
    }


@pytest.mark.asyncio
async def test_0003_migrates_exact_policy_v3_to_v4_with_entry_disabled(
    compatible_migration_engine: AsyncEngine,
) -> None:
    engine = compatible_migration_engine
    result = _run_migration(_database_url(engine), "upgrade", SOURCE_REVISION)
    assert result.returncode == 0, result.stderr[-4000:]
    await _insert_source_policy_v3(engine)

    result = _run_migration(_database_url(engine), "upgrade", HEAD_REVISION)
    assert result.returncode == 0, result.stderr[-4000:]

    async with engine.connect() as connection:
        policy = (
            await connection.execute(
                sa.text(
                    "SELECT policy_version, new_entry_submit_enabled, "
                    "max_concurrent_tickets, max_strategy_group_concurrent_tickets, "
                    "family_ticket_limits, max_ticket_stop_risk_fraction, "
                    "max_gross_stop_risk_fraction, "
                    "max_ticket_initial_margin_fraction, "
                    "max_gross_initial_margin_utilization, "
                    "directional_stop_risk_limit_fraction, "
                    "min_materialization_ratio "
                    "FROM brc_owner_policy_current "
                    "WHERE owner_policy_id = 'policy-main'"
                )
            )
        ).mappings().one()
        defaults = await connection.run_sync(
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

    assert policy["policy_version"] == 4
    assert policy["new_entry_submit_enabled"] is False
    assert policy["max_concurrent_tickets"] == 3
    assert policy["max_strategy_group_concurrent_tickets"] is None
    assert policy["family_ticket_limits"] == {
        "long_continuation": 1,
        "opening_range": 2,
        "rally_failure_short": 1,
    }
    assert Decimal(policy["max_ticket_stop_risk_fraction"]) == Decimal("0.02")
    assert Decimal(policy["max_gross_stop_risk_fraction"]) == Decimal("0.06")
    assert Decimal(policy["max_ticket_initial_margin_fraction"]) == Decimal("0.30")
    assert Decimal(policy["max_gross_initial_margin_utilization"]) == Decimal("0.90")
    assert Decimal(policy["directional_stop_risk_limit_fraction"]) == Decimal("0.04")
    assert Decimal(policy["min_materialization_ratio"]) == Decimal("0.50")
    assert defaults == {
        "family_ticket_limits": None,
        "directional_stop_risk_limit_fraction": None,
        "min_materialization_ratio": None,
    }


@pytest.mark.asyncio
async def test_0003_downgrade_to_0002_is_forbidden(
    compatible_migration_engine: AsyncEngine,
) -> None:
    engine = compatible_migration_engine
    result = _run_migration(_database_url(engine), "upgrade", "head")
    assert result.returncode == 0, result.stderr[-4000:]

    result = _run_migration(_database_url(engine), "downgrade", SOURCE_REVISION)

    assert result.returncode != 0
    assert "fix-forward" in result.stderr
    async with engine.connect() as connection:
        assert await connection.scalar(
            sa.text("SELECT version_num FROM alembic_version")
        ) == HEAD_REVISION


@pytest.mark.asyncio
async def test_0002_terminal_source_columns_are_equal_after_0003(
    compatible_migration_engine: AsyncEngine,
) -> None:
    engine = compatible_migration_engine
    await _prepare_production_shaped_0002(engine)
    before = await _source_history_manifest(engine, exact_source_shape=True)

    result = _run_migration(_database_url(engine), "upgrade", HEAD_REVISION)

    assert result.returncode == 0, result.stderr[-4000:]
    assert await _source_history_manifest(engine, exact_source_shape=False) == before


@pytest.mark.asyncio
async def test_0003_refuses_active_ticket_before_any_schema_or_data_mutation(
    compatible_migration_engine: AsyncEngine,
) -> None:
    engine = compatible_migration_engine
    await _prepare_production_shaped_0002(engine)
    async with engine.begin() as connection:
        await connection.execute(
            sa.text(
                "UPDATE brc_trade_tickets "
                "SET status = 'entry_prepared', terminal_at_ms = NULL "
                "WHERE ticket_id = 'ticket-v3-terminal'"
            )
        )
    before = await _pre_upgrade_authority_state(engine)

    result = _run_migration(_database_url(engine), "upgrade", HEAD_REVISION)

    assert result.returncode != 0
    assert "active Ticket" in result.stderr
    assert await _pre_upgrade_authority_state(engine) == before


@pytest.mark.asyncio
async def test_0003_refuses_source_event_timeframe_drift_before_any_mutation(
    compatible_migration_engine: AsyncEngine,
) -> None:
    engine = compatible_migration_engine
    await _prepare_production_shaped_0002(engine)
    async with engine.begin() as connection:
        await connection.execute(
            sa.text(
                "UPDATE brc_event_specs SET timeframe = '1h' "
                "WHERE event_spec_id = 'event_spec:SOR-001:SOR-LONG:v3'"
            )
        )
    before = await _pre_upgrade_authority_state(engine)

    result = _run_migration(_database_url(engine), "upgrade", HEAD_REVISION)

    assert result.returncode != 0
    assert "certified Registry source" in result.stderr
    assert await _pre_upgrade_authority_state(engine) == before


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("blocker", "expected_error"),
    (
        ("position", "nonzero internal Position"),
        ("budget_reservation", "active Budget Reservation"),
        ("netting_domain", "unreleased Netting Domain"),
        ("entry_lane_status", "ENTRY lane"),
        ("entry_lane_owner", "ENTRY lane"),
        ("exchange_command", "unresolved Exchange Command"),
        ("incident", "open Incident"),
        ("aggregate_closure", "nonterminal Aggregate closure"),
    ),
)
async def test_0003_refuses_each_nonflat_source_before_any_mutation(
    compatible_migration_engine: AsyncEngine,
    blocker: str,
    expected_error: str,
) -> None:
    engine = compatible_migration_engine
    await _prepare_production_shaped_0002(engine)
    await _install_nonflat_blocker(engine, blocker)
    before = await _pre_upgrade_authority_state(engine)

    result = _run_migration(_database_url(engine), "upgrade", HEAD_REVISION)

    assert result.returncode != 0
    assert expected_error in result.stderr
    assert await _pre_upgrade_authority_state(engine) == before


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("drift_sql", "parameters"),
    (
        (
            (
                "UPDATE brc_event_specs "
                "SET execution_semantics = CAST(:value AS jsonb) "
                "WHERE event_spec_id = 'event_spec:SOR-001:SOR-LONG:v3'"
            ),
            {"value": '{"source":"drifted"}'},
        ),
        (
            (
                "UPDATE brc_exit_policies SET policy = CAST(:value AS jsonb) "
                "WHERE exit_policy_id = "
                "'exit-policy:SOR-001:SOR-LONG:sor-v3-right-tail-v1'"
            ),
            {"value": '{"runner":{"timeframe":"1h"}}'},
        ),
        (
            (
                "UPDATE brc_exit_policies SET semantic_hash = :value "
                "WHERE exit_policy_id = "
                "'exit-policy:SOR-001:SOR-LONG:sor-v3-right-tail-v1'"
            ),
            {"value": "sha256:" + "0" * 64},
        ),
    ),
    ids=("execution-semantics", "exit-policy-payload", "exit-policy-hash"),
)
async def test_0003_refuses_literal_registry_semantic_drift_before_any_mutation(
    compatible_migration_engine: AsyncEngine,
    drift_sql: str,
    parameters: dict[str, str],
) -> None:
    engine = compatible_migration_engine
    await _prepare_production_shaped_0002(engine)
    async with engine.begin() as connection:
        await connection.execute(sa.text(drift_sql), parameters)
    before = await _pre_upgrade_authority_state(engine)

    result = _run_migration(_database_url(engine), "upgrade", HEAD_REVISION)

    assert result.returncode != 0
    assert "certified Registry source" in result.stderr
    assert await _pre_upgrade_authority_state(engine) == before


@pytest.mark.asyncio
async def test_0003_backfills_only_deterministic_family_for_terminal_sor_v3(
    compatible_migration_engine: AsyncEngine,
) -> None:
    engine = compatible_migration_engine
    await _prepare_production_shaped_0002(engine)
    async with engine.connect() as connection:
        before = (
            await connection.execute(
                sa.text(
                    "SELECT planned_stop_risk_budget, risk_at_stop, reserved_margin "
                    "FROM brc_capacity_claims "
                    "WHERE capacity_claim_id = 'claim-v3-terminal'"
                )
            )
        ).one()

    result = _run_migration(_database_url(engine), "upgrade", HEAD_REVISION)
    assert result.returncode == 0, result.stderr[-4000:]

    async with engine.connect() as connection:
        claim = (
            await connection.execute(
                sa.text(
                    "SELECT exposure_family, active_family_ticket_count_at_claim, "
                    "family_ticket_limit, directional_risk_at_stop_at_claim, "
                    "directional_stop_risk_limit_fraction, min_materialization_ratio, "
                    "minimum_stop_risk_budget, planned_stop_risk_budget, "
                    "risk_at_stop, reserved_margin FROM brc_capacity_claims "
                    "WHERE capacity_claim_id = 'claim-v3-terminal'"
                )
            )
        ).one()
        ticket = (
            await connection.execute(
                sa.text(
                    "SELECT exposure_family, active_family_ticket_count_at_claim, "
                    "family_ticket_limit, directional_risk_at_stop_at_claim, "
                    "directional_stop_risk_limit_fraction, min_materialization_ratio, "
                    "minimum_stop_risk_budget FROM brc_trade_tickets "
                    "WHERE ticket_id = 'ticket-v3-terminal'"
                )
            )
        ).one()

    assert claim[0] == "opening_range"
    assert ticket[0] == "opening_range"
    assert claim[1:7] == (None,) * 6
    assert ticket[1:7] == (None,) * 6
    assert claim[7:] == before


@pytest.mark.asyncio
async def test_0003_installs_vnext_registry_and_retires_exact_source_lineage(
    compatible_migration_engine: AsyncEngine,
) -> None:
    engine = compatible_migration_engine
    await _prepare_production_shaped_0002(engine)

    result = _run_migration(_database_url(engine), "upgrade", HEAD_REVISION)
    assert result.returncode == 0, result.stderr[-4000:]
    async with PostgresKernelUnitOfWork(engine) as uow:
        registry_seed = await seed_strategy_registry(uow, seeded_at_ms=2_000)

    async with engine.connect() as connection:
        groups = dict(
            (
                await connection.execute(
                    sa.text(
                        "SELECT strategy_group_id, active_version_id "
                        "FROM brc_strategy_groups ORDER BY strategy_group_id"
                    )
                )
            ).all()
        )
        versions = (
            await connection.execute(
                sa.text(
                    "SELECT strategy_version_id, status "
                    "FROM brc_strategy_versions "
                    "WHERE strategy_group_id IN "
                    "('BRF2-001','CPM-RO-001','MI-001','MPG-001','SOR-001') "
                    "AND strategy_version_id NOT IN ('sgv:SOR-001:v2') "
                    "ORDER BY strategy_version_id"
                )
            )
        ).all()
        events = (
            await connection.execute(
                sa.text(
                    "SELECT event_spec_id, status FROM brc_event_specs "
                    "WHERE event_spec_id IN ("
                    "'event_spec:BRF2-001:BRF2-SHORT:v2',"
                    "'event_spec:BRF2-001:BRF2-SHORT:v3',"
                    "'event_spec:CPM-RO-001:CPM-LONG:v2',"
                    "'event_spec:CPM-RO-001:CPM-LONG:v3',"
                    "'event_spec:MI-001:MI-LONG:v2',"
                    "'event_spec:MI-001:MI-LONG:v3',"
                    "'event_spec:MPG-001:MPG-LONG:v2',"
                    "'event_spec:MPG-001:MPG-LONG:v3',"
                    "'event_spec:SOR-001:SOR-LONG:v3',"
                    "'event_spec:SOR-001:SOR-LONG:v4',"
                    "'event_spec:SOR-001:SOR-SHORT:v3',"
                    "'event_spec:SOR-001:SOR-SHORT:v4') "
                    "ORDER BY event_spec_id"
                )
            )
        ).all()
        target_policies = (
            await connection.execute(
                sa.text(
                    "SELECT exit_policy_id, event_spec_id, status "
                    "FROM brc_exit_policies "
                    "WHERE exit_policy_id LIKE :suffix "
                    "ORDER BY event_spec_id"
                ),
                {"suffix": "%:portfolio-admission-v1"},
            )
        ).all()
        universe_counts = (
            await connection.execute(
                sa.text(
                    "SELECT count(*) FILTER (WHERE right(event_spec_id, 2) "
                    "IN ('v2','v3')), "
                    "count(*) FILTER (WHERE right(event_spec_id, 2) = 'v4') "
                    "FROM brc_strategy_universe_versions"
                )
            )
        ).one()

    assert groups == {
        "BRF2-001": "sgv:BRF2-001:v3",
        "CPM-RO-001": "sgv:CPM-RO-001:v3",
        "MI-001": "sgv:MI-001:v3",
        "MPG-001": "sgv:MPG-001:v3",
        "SOR-001": "sgv:SOR-001:v4",
    }
    assert registry_seed.total_inserted_count == 0
    assert versions == [
        ("sgv:BRF2-001:v2", "retired"),
        ("sgv:BRF2-001:v3", "active"),
        ("sgv:CPM-RO-001:v2", "retired"),
        ("sgv:CPM-RO-001:v3", "active"),
        ("sgv:MI-001:v2", "retired"),
        ("sgv:MI-001:v3", "active"),
        ("sgv:MPG-001:v2", "retired"),
        ("sgv:MPG-001:v3", "active"),
        ("sgv:SOR-001:v3", "retired"),
        ("sgv:SOR-001:v4", "active"),
    ]
    assert events == [
        ("event_spec:BRF2-001:BRF2-SHORT:v2", "retired"),
        ("event_spec:BRF2-001:BRF2-SHORT:v3", "active"),
        ("event_spec:CPM-RO-001:CPM-LONG:v2", "retired"),
        ("event_spec:CPM-RO-001:CPM-LONG:v3", "active"),
        ("event_spec:MI-001:MI-LONG:v2", "retired"),
        ("event_spec:MI-001:MI-LONG:v3", "active"),
        ("event_spec:MPG-001:MPG-LONG:v2", "retired"),
        ("event_spec:MPG-001:MPG-LONG:v3", "active"),
        ("event_spec:SOR-001:SOR-LONG:v3", "retired"),
        ("event_spec:SOR-001:SOR-LONG:v4", "active"),
        ("event_spec:SOR-001:SOR-SHORT:v3", "retired"),
        ("event_spec:SOR-001:SOR-SHORT:v4", "active"),
    ]
    assert target_policies == [
        (
            "exit-policy:BRF2-001:BRF2-SHORT:portfolio-admission-v1",
            "event_spec:BRF2-001:BRF2-SHORT:v3",
            "active",
        ),
        (
            "exit-policy:CPM-RO-001:CPM-LONG:portfolio-admission-v1",
            "event_spec:CPM-RO-001:CPM-LONG:v3",
            "active",
        ),
        (
            "exit-policy:MI-001:MI-LONG:portfolio-admission-v1",
            "event_spec:MI-001:MI-LONG:v3",
            "active",
        ),
        (
            "exit-policy:MPG-001:MPG-LONG:portfolio-admission-v1",
            "event_spec:MPG-001:MPG-LONG:v3",
            "active",
        ),
        (
            "exit-policy:SOR-001:SOR-LONG:portfolio-admission-v1",
            "event_spec:SOR-001:SOR-LONG:v4",
            "active",
        ),
        (
            "exit-policy:SOR-001:SOR-SHORT:portfolio-admission-v1",
            "event_spec:SOR-001:SOR-SHORT:v4",
            "active",
        ),
    ]
    assert universe_counts == (2, 0)


@pytest.mark.asyncio
async def test_0003_migrated_ticket_indexes_exactly_match_current_metadata(
    compatible_migration_engine: AsyncEngine,
) -> None:
    engine = compatible_migration_engine
    await _prepare_production_shaped_0002(engine)

    result = _run_migration(_database_url(engine), "upgrade", HEAD_REVISION)
    assert result.returncode == 0, result.stderr[-4000:]

    async with engine.connect() as connection:
        indexes = await connection.run_sync(
            lambda sync: {
                index["name"]: tuple(index["column_names"])
                for index in sa.inspect(sync).get_indexes("brc_trade_tickets")
            }
        )

    assert indexes == {
        "ix_brc_trade_tickets_active_directional_risk": (
            "venue_id",
            "account_id",
            "position_side",
            "terminal_at_ms",
        ),
        "ix_brc_trade_tickets_active_family": (
            "venue_id",
            "account_id",
            "exposure_family",
            "terminal_at_ms",
        ),
        "ix_brc_trade_tickets_instrument_window": (
            "venue_id",
            "account_id",
            "exchange_instrument_id",
            "created_at_ms",
            "terminal_at_ms",
        ),
        "uq_brc_trade_tickets_active_netting_domain_key": (
            "active_netting_domain_key",
        ),
        "uq_brc_trade_tickets_signal_event_id": ("signal_event_id",),
    }


async def _insert_source_policy_v3(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            sa.text(
                """
                INSERT INTO brc_owner_policy_current (
                    owner_policy_id, policy_version, enabled,
                    new_entry_submit_enabled, priority_rank,
                    max_concurrent_tickets,
                    max_strategy_group_concurrent_tickets,
                    max_ticket_stop_risk_fraction,
                    max_gross_stop_risk_fraction,
                    max_ticket_initial_margin_fraction,
                    max_gross_initial_margin_utilization,
                    max_leverage, supported_margin_mode,
                    post_stop_stress_multiple,
                    max_post_fill_stop_risk_overrun_fraction,
                    scope, updated_at_ms
                ) VALUES (
                    'policy-main', 3, true, true, 1, 3, 2,
                    0.03, 0.06, 0.45, 0.90, 10, 'cross', 2.0, 0.10,
                    '{"runtime_profile_id":"tiny-live-v1",'
                    '"allowed_event_spec_ids":['
                    '"event_spec:BRF2-001:BRF2-SHORT:v2",'
                    '"event_spec:CPM-RO-001:CPM-LONG:v2",'
                    '"event_spec:MI-001:MI-LONG:v2",'
                    '"event_spec:MPG-001:MPG-LONG:v2",'
                    '"event_spec:SOR-001:SOR-LONG:v3",'
                    '"event_spec:SOR-001:SOR-SHORT:v3"]}'::jsonb,
                    1000
                )
                """
            )
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
                "new_entry_submit_enabled = false, "
                "scope = '{\"runtime_profile_id\":\"tiny-live-v1\","
                "\"allowed_event_spec_ids\":["
                "\"event_spec:BRF2-001:BRF2-SHORT:v2\","
                "\"event_spec:CPM-RO-001:CPM-LONG:v2\","
                "\"event_spec:MI-001:MI-LONG:v2\","
                "\"event_spec:MPG-001:MPG-LONG:v2\","
                "\"event_spec:SOR-001:SOR-LONG:v3\","
                "\"event_spec:SOR-001:SOR-SHORT:v3\"]}'::jsonb, "
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
                "('exchange_commands', false, "
                "'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb', "
                "'0002_sor_v3_strategy_group_capacity', "
                "'{\"stage\":\"observation_only\"}'::jsonb, 1000), "
                "('strategy_signal_ingest', true, "
                "'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb', "
                "'0002_sor_v3_strategy_group_capacity', "
                "'{\"stage\":\"observation_only\"}'::jsonb, 1000)"
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
                "result_payload = '{\"exchange_order_id\":\"entry-v2-2\"}'::jsonb, "
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
                "registry_semantic_hash": event[
                    "version_registry_semantic_hash"
                ],
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
                "protection_reference_fact_definition_id": event[
                    "protection_fact_id"
                ],
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
    await connection.execute(sa.insert(pg_models.strategy_versions), list(versions.values()))
    await connection.execute(sa.insert(pg_models.fact_definitions), list(facts.values()))
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
            None
            if time_stop_bars is None
            else {"max_holding_bars": time_stop_bars}
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
            "'{\"exchange_order_id\":\"entry-v3-terminal\"}'::jsonb,NULL,NULL,"
            "4000,4400,4100)"
        ),
        (
            "INSERT INTO brc_trade_reviews VALUES "
            "('review-v3-terminal','ticket-v3-terminal',1,NULL,'closed',"
            "'{\"net_pnl_quote\":\"1\",\"settlement_asset\":\"USDT\"}'::jsonb,"
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
            "'{\"settlement_asset\":\"USDT\"}'::jsonb,4500)"
        ),
    ):
        await connection.execute(sa.text(statement))


async def _install_nonflat_blocker(engine: AsyncEngine, blocker: str) -> None:
    statements: dict[str, tuple[str, dict[str, object]]] = {
        "position": (
            (
                "INSERT INTO brc_positions_current ("
                "netting_domain_key,ticket_id,venue_id,account_id,"
                "exchange_instrument_id,position_side,quantity,average_entry_price,"
                "venue_reported_liquidation_price,"
                "venue_reported_liquidation_observation_status,observed_at_ms,"
                "projection_version) VALUES ("
                "'position-domain','ticket-v3-terminal','binance-usdm','account-main',"
                "'binance-usdm:BTCUSDT:perpetual','long',1,100,NULL,"
                "'not_reported',5000,1)"
            ),
            {},
        ),
        "budget_reservation": (
            (
                "UPDATE brc_budget_reservations SET status = 'active', "
                "released_at_ms = NULL "
                "WHERE budget_reservation_id = 'reservation-v3-terminal'"
            ),
            {},
        ),
        "netting_domain": (
            (
                "UPDATE brc_trade_tickets "
                "SET active_netting_domain_key = netting_domain_key "
                "WHERE ticket_id = 'ticket-v3-terminal'"
            ),
            {},
        ),
        "entry_lane_status": (
            (
                "INSERT INTO brc_entry_lane_current VALUES ("
                "'global-entry','ticket-v3-terminal',NULL,'claimed',"
                "5000,6000,'migration-test-owner',1)"
            ),
            {},
        ),
        "entry_lane_owner": (
            (
                "INSERT INTO brc_entry_lane_current VALUES ("
                "'global-entry',NULL,NULL,'idle',NULL,NULL,'stale-owner',1)"
            ),
            {},
        ),
        "exchange_command": (
            (
                "UPDATE brc_exchange_commands SET status = 'outcome_unknown', "
                "result_payload = NULL, completed_at_ms = NULL "
                "WHERE command_id = 'command-v3-terminal-entry'"
            ),
            {},
        ),
        "incident": (
            (
                "UPDATE brc_runtime_incidents SET status = 'open', "
                "resolved_at_ms = NULL WHERE incident_id = 'incident-v2-2'"
            ),
            {},
        ),
        "aggregate_closure": (
            (
                "UPDATE brc_trade_aggregates SET status = 'protected' "
                "WHERE ticket_id = 'ticket-v3-terminal'"
            ),
            {},
        ),
    }
    statement, parameters = statements[blocker]
    async with engine.begin() as connection:
        await connection.execute(sa.text(statement), parameters)


async def _source_history_manifest(
    engine: AsyncEngine,
    *,
    exact_source_shape: bool,
) -> dict[str, object]:
    async with engine.connect() as connection:
        actual_columns = await connection.run_sync(
            lambda sync: {
                table_name: tuple(
                    column["name"]
                    for column in sa.inspect(sync).get_columns(table_name)
                )
                for table_name in SOURCE_HISTORY_COLUMNS
            }
        )
        expected_columns = {
            table_name: tuple(columns.split())
            for table_name, columns in SOURCE_HISTORY_COLUMNS.items()
        }
        if exact_source_shape:
            assert actual_columns == expected_columns
        else:
            for table_name, columns in expected_columns.items():
                assert set(columns) <= set(actual_columns[table_name])
        rows: dict[str, tuple[str, ...]] = {}
        for table_name, columns in expected_columns.items():
            result = await connection.execute(
                sa.text(f"SELECT {','.join(columns)} FROM {table_name}")
            )
            rows[table_name] = tuple(
                sorted(
                    json.dumps(
                        [_canonical_value(value) for value in row],
                        ensure_ascii=True,
                        separators=(",", ":"),
                        sort_keys=True,
                    )
                    for row in result.all()
                )
            )
    return {"columns": expected_columns, "rows": rows}


async def _pre_upgrade_authority_state(engine: AsyncEngine) -> dict[str, object]:
    async with engine.connect() as connection:
        inspector_state = await connection.run_sync(
            lambda sync: {
                "tables": tuple(sorted(sa.inspect(sync).get_table_names())),
                "policy_columns": tuple(
                    column["name"]
                    for column in sa.inspect(sync).get_columns(
                        "brc_owner_policy_current"
                    )
                ),
                "claim_columns": tuple(
                    column["name"]
                    for column in sa.inspect(sync).get_columns(
                        "brc_capacity_claims"
                    )
                ),
                "ticket_columns": tuple(
                    column["name"]
                    for column in sa.inspect(sync).get_columns(
                        "brc_trade_tickets"
                    )
                ),
            }
        )
        revision = await connection.scalar(
            sa.text("SELECT version_num FROM alembic_version")
        )
        groups = tuple(
            (
                await connection.execute(
                    sa.text(
                        "SELECT strategy_group_id, display_name, "
                        "active_version_id, status, updated_at_ms "
                        "FROM brc_strategy_groups ORDER BY strategy_group_id"
                    )
                )
            ).all()
        )
        policy = tuple(
            (
                await connection.execute(
                    sa.text(
                        "SELECT owner_policy_id, policy_version, enabled, "
                        "new_entry_submit_enabled, scope, updated_at_ms "
                        "FROM brc_owner_policy_current ORDER BY owner_policy_id"
                    )
                )
            ).all()
        )
    return {
        **inspector_state,
        "revision": revision,
        "groups": groups,
        "policy": policy,
    }


def _canonical_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, Mapping):
        return {
            str(key): _canonical_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    raise TypeError(f"unsupported source value: {type(value).__name__}")


def _database_url(engine: AsyncEngine) -> str:
    return engine.url.render_as_string(hide_password=False)
