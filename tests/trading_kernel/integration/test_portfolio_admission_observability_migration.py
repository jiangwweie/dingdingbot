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
        await _promote_source_sor_v3_registry(connection)
        await _insert_source_non_sor_v2_registry(connection)
        await connection.execute(
            sa.text(
                "UPDATE brc_owner_policy_current SET policy_version = 3, "
                "new_entry_submit_enabled = true, "
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


async def _insert_source_non_sor_v2_registry(connection: Any) -> None:
    source_rows = (
        (
            "BRF2-001",
            "BRF2 bear rally failure",
            "BRF2-SHORT",
            "short",
            "fact:rally-high:v2",
        ),
        (
            "CPM-RO-001",
            "CPM reclaim pullback recovery",
            "CPM-LONG",
            "long",
            "fact:pullback-low:v2",
        ),
        (
            "MI-001",
            "MI relative strength impulse",
            "MI-LONG",
            "long",
            "fact:impulse-low:v2",
        ),
        (
            "MPG-001",
            "MPG momentum persistence",
            "MPG-LONG",
            "long",
            "fact:momentum-low:v2",
        ),
    )
    for index, (
        strategy_group_id,
        display_name,
        event_id,
        position_side,
        protection_fact_id,
    ) in enumerate(source_rows, start=1):
        strategy_version_id = f"sgv:{strategy_group_id}:v2"
        event_spec_id = f"event_spec:{strategy_group_id}:{event_id}:v2"
        exit_policy_id = f"exit-policy:{strategy_group_id}:{event_id}:right-tail-v1"
        await connection.execute(
            sa.text(
                "INSERT INTO brc_strategy_groups VALUES "
                "(:group_id,:display_name,:version_id,'active',1000)"
            ),
            {
                "group_id": strategy_group_id,
                "display_name": display_name,
                "version_id": strategy_version_id,
            },
        )
        await connection.execute(
            sa.text(
                "INSERT INTO brc_strategy_versions VALUES "
                "(:version_id,:group_id,2,'{}'::jsonb,'active',1000)"
            ),
            {"version_id": strategy_version_id, "group_id": strategy_group_id},
        )
        await connection.execute(
            sa.text(
                "INSERT INTO brc_event_specs VALUES "
                "(:event_spec_id,:version_id,:event_id,:position_side,'1h',"
                "3600000,'trigger_candle_close_time_ms','market',"
                ":protection_fact_id,:exit_policy_id,'{}'::jsonb,'active',1000)"
            ),
            {
                "event_spec_id": event_spec_id,
                "version_id": strategy_version_id,
                "event_id": event_id,
                "position_side": position_side,
                "protection_fact_id": protection_fact_id,
                "exit_policy_id": exit_policy_id,
            },
        )
        await connection.execute(
            sa.text(
                "INSERT INTO brc_exit_policies VALUES "
                "(:exit_policy_id,'right-tail-v1',:event_spec_id,:position_side,"
                "'{}'::jsonb,:semantic_hash,'active',1000)"
            ),
            {
                "exit_policy_id": exit_policy_id,
                "event_spec_id": event_spec_id,
                "position_side": position_side,
                "semantic_hash": "sha256:" + str(index) * 64,
            },
        )


async def _promote_source_sor_v3_registry(connection: Any) -> None:
    await connection.execute(
        sa.text(
            "INSERT INTO brc_fact_definitions VALUES "
            "('fact:range-low:v3','range_low_v3','decimal',900000,'{}'::jsonb),"
            "('fact:range-high:v3','range_high_v3','decimal',900000,'{}'::jsonb)"
        )
    )
    await connection.execute(
        sa.text(
            "INSERT INTO brc_strategy_versions VALUES "
            "('sgv:SOR-001:v3','SOR-001',3,'{}'::jsonb,'active',1000)"
        )
    )
    for event_id, side, protection in (
        ("SOR-LONG", "long", "fact:range-low:v3"),
        ("SOR-SHORT", "short", "fact:range-high:v3"),
    ):
        event_spec_id = f"event_spec:SOR-001:{event_id}:v3"
        policy_id = f"exit-policy:SOR-001:{event_id}:sor-v3-right-tail-v1"
        policy_hash = "sha256:" + ("f" if side == "long" else "e") * 64
        await connection.execute(
            sa.text(
                "INSERT INTO brc_event_specs VALUES "
                "(:event_spec_id,'sgv:SOR-001:v3',:event_id,:side,'15m',"
                "900000,'trigger_candle_close_time_ms','market',:protection,"
                ":policy_id,'{}'::jsonb,'active',1000)"
            ),
            {
                "event_spec_id": event_spec_id,
                "event_id": event_id,
                "side": side,
                "protection": protection,
                "policy_id": policy_id,
            },
        )
        await connection.execute(
            sa.text(
                "INSERT INTO brc_exit_policies VALUES "
                "(:policy_id,'sor-v3-right-tail-v1',:event_spec_id,:side,"
                "'{}'::jsonb,:policy_hash,'active',1000)"
            ),
            {
                "policy_id": policy_id,
                "event_spec_id": event_spec_id,
                "side": side,
                "policy_hash": policy_hash,
            },
        )
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
            "UPDATE brc_strategy_groups SET active_version_id = 'sgv:SOR-001:v3', "
            "updated_at_ms = 1000 WHERE strategy_group_id = 'SOR-001'"
        ),
    ):
        await connection.execute(sa.text(statement))


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
        exit_policy_semantic_hash="sha256:" + "f" * 64,
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
        exit_policy_semantic_hash="sha256:" + "f" * 64,
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
