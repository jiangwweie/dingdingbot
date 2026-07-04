#!/usr/bin/env python3
"""Seed PG runtime control-state foundation rows for current StrategyGroups.

Default behavior is dry-run. Applying writes only PG control-state metadata:
strategy/event/scope/policy/runtime binding/projection ownership. It does not
create live signals, promotion candidates, action-time lanes, tickets, orders,
FinalGate passes, Operation Layer submits, or exchange writes.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import sqlalchemy as sa


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


DEFAULT_RUNTIME_PROFILE_ID = "owner-runtime-console-v1"
DEFAULT_ACCOUNT_ID = "owner-subaccount-runtime-v0"
SEED_VERSION = "runtime-control-state-foundation-v1"
DEFAULT_NOW_MS = 1770000000000


@dataclass(frozen=True)
class EventSeed:
    strategy_group_id: str
    symbols: tuple[str, ...]
    side: str
    event_id: str
    timeframe: str
    freshness_window_ms: int
    time_authority: str
    protection_ref_type: str
    owner_label: str
    wip_slot: str
    tradeability_stage: str
    required_facts: tuple[str, ...]
    disable_facts: tuple[str, ...] = ()


ACTIVE_EVENT_SEEDS: tuple[EventSeed, ...] = (
    EventSeed(
        strategy_group_id="CPM-RO-001",
        symbols=("ETHUSDT", "SOLUSDT", "AVAXUSDT", "SUIUSDT"),
        side="long",
        event_id="CPM-LONG",
        timeframe="1h",
        freshness_window_ms=3_600_000,
        time_authority="trigger_candle_close_time_ms",
        protection_ref_type="pullback_low_reference",
        owner_label="CPM reclaim pullback recovery",
        wip_slot="P0-A",
        tradeability_stage="armed_observation",
        required_facts=(
            "htf_trend_intact",
            "reclaim_confirmed",
            "pullback_low_reference",
        ),
    ),
    EventSeed(
        strategy_group_id="MPG-001",
        symbols=("OPUSDT", "SOLUSDT", "AVAXUSDT", "SUIUSDT"),
        side="long",
        event_id="MPG-LONG",
        timeframe="1h",
        freshness_window_ms=3_600_000,
        time_authority="trigger_candle_close_time_ms",
        protection_ref_type="momentum_floor_reference",
        owner_label="MPG momentum persistence",
        wip_slot="P0-B",
        tradeability_stage="armed_observation",
        required_facts=(
            "momentum_persistence_confirmed",
            "leader_strength_confirmed",
            "momentum_floor_reference",
        ),
    ),
    EventSeed(
        strategy_group_id="MI-001",
        symbols=("AVAXUSDT", "ETHUSDT", "SOLUSDT"),
        side="long",
        event_id="MI-LONG",
        timeframe="1h",
        freshness_window_ms=3_600_000,
        time_authority="trigger_candle_close_time_ms",
        protection_ref_type="impulse_invalidation_reference",
        owner_label="MI relative strength impulse",
        wip_slot="P1-A",
        tradeability_stage="armed_observation",
        required_facts=(
            "impulse_confirmed",
            "relative_strength_confirmed",
            "impulse_invalidation_reference",
        ),
    ),
    EventSeed(
        strategy_group_id="SOR-001",
        symbols=("ETHUSDT", "SOLUSDT", "AVAXUSDT", "BTCUSDT"),
        side="long",
        event_id="SOR-LONG",
        timeframe="15m",
        freshness_window_ms=900_000,
        time_authority="trigger_candle_close_time_ms",
        protection_ref_type="opening_range_low_reference",
        owner_label="SOR opening range breakout",
        wip_slot="P1-B",
        tradeability_stage="armed_observation",
        required_facts=(
            "opening_range_defined",
            "breakout_confirmed",
            "opening_range_low_reference",
        ),
    ),
    EventSeed(
        strategy_group_id="SOR-001",
        symbols=("ETHUSDT", "SOLUSDT", "AVAXUSDT", "BTCUSDT"),
        side="short",
        event_id="SOR-SHORT",
        timeframe="15m",
        freshness_window_ms=900_000,
        time_authority="trigger_candle_close_time_ms",
        protection_ref_type="opening_range_high_reference",
        owner_label="SOR opening range breakdown",
        wip_slot="P1-B",
        tradeability_stage="armed_observation",
        required_facts=(
            "opening_range_defined",
            "breakdown_confirmed",
            "opening_range_high_reference",
        ),
    ),
    EventSeed(
        strategy_group_id="BRF2-001",
        symbols=("BTCUSDT", "AVAXUSDT", "ETHUSDT"),
        side="short",
        event_id="BRF2-SHORT",
        timeframe="1h",
        freshness_window_ms=3_600_000,
        time_authority="trigger_candle_close_time_ms",
        protection_ref_type="rally_high_reference",
        owner_label="BRF2 bear rally failure",
        wip_slot="P2-A",
        tradeability_stage="armed_observation",
        required_facts=(
            "rally_failure_confirmed",
            "short_side_not_disabled",
            "rally_high_reference",
        ),
        disable_facts=("strong_uptrend_disable",),
    ),
)


def build_seed_rows(
    *,
    now_ms: int = DEFAULT_NOW_MS,
    runtime_profile_id: str = DEFAULT_RUNTIME_PROFILE_ID,
    account_id: str = DEFAULT_ACCOUNT_ID,
) -> dict[str, list[dict[str, Any]]]:
    rows: dict[str, list[dict[str, Any]]] = {
        "brc_strategy_groups": [],
        "brc_strategy_group_versions": [],
        "brc_required_fact_contracts": [],
        "brc_strategy_side_event_specs": [],
        "brc_strategy_event_required_facts": [],
        "brc_symbols": [],
        "brc_exchange_instruments": [],
        "brc_symbol_instrument_mappings": [],
        "brc_owner_policy_events": [],
        "brc_owner_policy_current": [],
        "brc_strategy_group_candidate_scope": [],
        "brc_candidate_scope_event_bindings": [],
        "brc_runtime_scope_bindings": [],
        "brc_execution_policies": [],
        "brc_projection_runs": [],
        "brc_current_projection_ownership": [],
    }

    seeds_by_group: dict[str, list[EventSeed]] = {}
    for seed in ACTIVE_EVENT_SEEDS:
        seeds_by_group.setdefault(seed.strategy_group_id, []).append(seed)

    for strategy_group_id, group_seeds in seeds_by_group.items():
        first = group_seeds[0]
        version_id = _strategy_group_version_id(strategy_group_id)
        supported_sides = sorted({seed.side for seed in group_seeds})
        supported_timeframes = sorted({seed.timeframe for seed in group_seeds})
        rows["brc_strategy_groups"].append(
            {
                "strategy_group_id": strategy_group_id,
                "strategy_family_id": None,
                "current_version_id": version_id,
                "owner_label": first.owner_label,
                "status": "active",
                "active_wip_slot": first.wip_slot,
                "default_tier": "L4",
                "tradeability_stage": first.tradeability_stage,
                "owner_visible": True,
                "created_at_ms": now_ms,
                "updated_at_ms": now_ms,
                "metadata": {"seed_version": SEED_VERSION},
            }
        )
        rows["brc_strategy_group_versions"].append(
            {
                "strategy_group_version_id": version_id,
                "strategy_group_id": strategy_group_id,
                "version": 1,
                "status": "current",
                "edge_thesis": _edge_thesis(strategy_group_id),
                "trade_logic": _trade_logic(strategy_group_id),
                "regime_fit": _regime_fit(strategy_group_id),
                "supported_sides": supported_sides,
                "supported_timeframes": supported_timeframes,
                "risk_envelope": {
                    "account_id": account_id,
                    "max_notional": "20",
                    "leverage": "2",
                    "attempt_cap": 1,
                    "loss_unit": "10",
                },
                "promotion_rules": {
                    "fresh_signal_required": True,
                    "action_time_ticket_required": True,
                    "unsupported_side_mirroring_allowed": False,
                },
                "evidence_refs": [
                    "docs/current/RUNTIME_CONTROL_STATE_DB_TABLE_DESIGN.md#confirmed-active-event-seed"
                ],
                "created_at_ms": now_ms,
                "created_by": "codex_seed",
            }
        )

    for symbol in sorted({symbol for seed in ACTIVE_EVENT_SEEDS for symbol in seed.symbols}):
        exchange_symbol = _exchange_symbol(symbol)
        instrument_id = f"binance_usdm:{exchange_symbol}"
        rows["brc_symbols"].append(
            {
                "symbol": symbol,
                "asset_class": "crypto_usdm_perp",
                "status": "active",
                "created_at_ms": now_ms,
            }
        )
        rows["brc_exchange_instruments"].append(
            {
                "exchange_instrument_id": instrument_id,
                "exchange_id": "binance_usdm",
                "exchange_symbol": exchange_symbol,
                "asset_class": "crypto_usdm_perp",
                "price_tick": None,
                "quantity_step": None,
                "min_notional": None,
                "status": "active",
                "created_at_ms": now_ms,
            }
        )
        rows["brc_symbol_instrument_mappings"].append(
            {
                "mapping_id": f"mapping:{symbol}:binance_usdm",
                "symbol": symbol,
                "exchange_instrument_id": instrument_id,
                "status": "active",
                "valid_from_ms": now_ms,
                "valid_until_ms": None,
                "created_at_ms": now_ms,
            }
        )

    for seed in ACTIVE_EVENT_SEEDS:
        event_spec_id = _event_spec_id(seed)
        version_id = _strategy_group_version_id(seed.strategy_group_id)
        rows["brc_strategy_side_event_specs"].append(
            {
                "event_spec_id": event_spec_id,
                "strategy_group_id": seed.strategy_group_id,
                "strategy_group_version_id": version_id,
                "event_id": seed.event_id,
                "side": seed.side,
                "timeframe": seed.timeframe,
                "event_spec_version": "v1",
                "status": "current",
                "freshness_window_ms": seed.freshness_window_ms,
                "time_authority": seed.time_authority,
                "protection_ref_type": seed.protection_ref_type,
                "created_at_ms": now_ms,
                "created_by": "codex_seed",
            }
        )
        _append_required_fact_rows(rows, seed=seed, event_spec_id=event_spec_id, now_ms=now_ms)
        rows["brc_execution_policies"].append(
            {
                "execution_policy_id": f"exec_policy:{event_spec_id}",
                "execution_policy_version": "exec-v1",
                "runtime_profile_id": runtime_profile_id,
                "strategy_group_id": seed.strategy_group_id,
                "event_spec_id": event_spec_id,
                "side": seed.side,
                "order_type": "market",
                "time_in_force": "IOC",
                "reduce_only": False,
                "post_only": False,
                "close_position": False,
                "allowed_slippage_bps": Decimal("25"),
                "price_protection_mode": "bounded_market",
                "submit_deadline_ms": 30_000,
                "cancel_if_not_filled_policy": {"mode": "cancel_remaining"},
                "status": "current",
                "created_at_ms": now_ms,
                "created_by": "codex_seed",
            }
        )

        for rank, symbol in enumerate(seed.symbols, start=1):
            candidate_scope_id = _candidate_scope_id(seed, symbol)
            policy_event_id = f"policy_event:{candidate_scope_id}:v1"
            policy_current_id = f"policy_current:{candidate_scope_id}"
            runtime_scope_binding_id = f"runtime_scope:{candidate_scope_id}:{runtime_profile_id}"
            rows["brc_owner_policy_events"].append(
                {
                    "policy_event_id": policy_event_id,
                    "strategy_group_id": seed.strategy_group_id,
                    "symbol": symbol,
                    "side": seed.side,
                    "event_type": "scope_set",
                    "policy_version": "owner-policy-v1",
                    "payload": {
                        "seed_version": SEED_VERSION,
                        "runtime_profile_id": runtime_profile_id,
                        "live_submit_allowed": "conditional_hard_gated",
                        "conditional_hard_gates": _conditional_hard_gates(seed),
                        "max_notional": "20",
                        "leverage": "2",
                        "attempt_cap": 1,
                    },
                    "created_at_ms": now_ms,
                    "created_by": "codex_seed",
                }
            )
            rows["brc_owner_policy_current"].append(
                {
                    "policy_current_id": policy_current_id,
                    "scope_key": f"side:{seed.strategy_group_id}:{symbol}:{seed.side}",
                    "scope_level": "side",
                    "strategy_group_id": seed.strategy_group_id,
                    "symbol": symbol,
                    "side": seed.side,
                    "enabled_state": "enabled",
                    "tier": "L4",
                    "runtime_profile_id": runtime_profile_id,
                    "pretrade_candidate_allowed": True,
                    "action_time_rehearsal_allowed": True,
                    "live_submit_allowed": "conditional_hard_gated",
                    "max_notional": Decimal("20"),
                    "leverage": Decimal("2"),
                    "attempt_cap": 1,
                    "loss_unit": Decimal("10"),
                    "policy_event_ids": [policy_event_id],
                    "valid_from_ms": now_ms,
                    "valid_until_ms": None,
                    "updated_at_ms": now_ms,
                }
            )
            rows["brc_strategy_group_candidate_scope"].append(
                {
                    "candidate_scope_id": candidate_scope_id,
                    "strategy_group_id": seed.strategy_group_id,
                    "symbol": symbol,
                    "exchange_symbol": _exchange_symbol(symbol),
                    "asset_class": "crypto_usdm_perp",
                    "side": seed.side,
                    "timeframe": seed.timeframe,
                    "candidate_role": "primary" if rank == 1 else "candidate",
                    "observation_scope": "active_wip",
                    "scope_state": "live_submit_allowed",
                    "priority_rank": rank,
                    "policy_current_id": policy_current_id,
                    "status": "active",
                    "valid_from_ms": now_ms,
                    "valid_until_ms": None,
                    "created_at_ms": now_ms,
                    "updated_at_ms": now_ms,
                    "metadata": {
                        "event_id": seed.event_id,
                        "seed_version": SEED_VERSION,
                        "unsupported_side_mirroring_allowed": False,
                    },
                }
            )
            rows["brc_candidate_scope_event_bindings"].append(
                {
                    "binding_id": f"binding:{candidate_scope_id}:{event_spec_id}",
                    "candidate_scope_id": candidate_scope_id,
                    "event_spec_id": event_spec_id,
                    "strategy_group_id": seed.strategy_group_id,
                    "symbol": symbol,
                    "side": seed.side,
                    "status": "active",
                    "valid_from_ms": now_ms,
                    "valid_until_ms": None,
                    "created_at_ms": now_ms,
                }
            )
            rows["brc_runtime_scope_bindings"].append(
                {
                    "runtime_scope_binding_id": runtime_scope_binding_id,
                    "candidate_scope_id": candidate_scope_id,
                    "strategy_group_id": seed.strategy_group_id,
                    "symbol": symbol,
                    "side": seed.side,
                    "runtime_profile_id": runtime_profile_id,
                    "selected_strategygroup_scope": True,
                    "symbol_side_scope_closed": True,
                    "notional_leverage_scope_closed": True,
                    "server_runtime_coverage_required": True,
                    "live_submit_allowed": True,
                    "conditional_hard_gates": _conditional_hard_gates(seed),
                    "policy_current_id": policy_current_id,
                    "status": "active",
                    "valid_from_ms": now_ms,
                    "valid_until_ms": None,
                    "authority_boundary": (
                        "Runtime scope permits progression only through action-time "
                        "facts, Action-Time Ticket, FinalGate, Operation Layer, "
                        "protection, reconciliation, and review."
                    ),
                    "created_at_ms": now_ms,
                    "updated_at_ms": now_ms,
                }
            )

    _append_projection_ownership_rows(rows, now_ms=now_ms)
    validate_seed_rows(rows)
    return rows


def validate_seed_rows(rows: dict[str, list[dict[str, Any]]]) -> None:
    allowed_scope = {
        (seed.strategy_group_id, symbol, seed.side, seed.event_id)
        for seed in ACTIVE_EVENT_SEEDS
        for symbol in seed.symbols
    }
    event_by_id = {
        row["event_spec_id"]: row
        for row in rows.get("brc_strategy_side_event_specs", [])
    }
    candidate_by_id = {
        row["candidate_scope_id"]: row
        for row in rows.get("brc_strategy_group_candidate_scope", [])
    }
    for row in rows.get("brc_strategy_group_candidate_scope", []):
        key = (
            row["strategy_group_id"],
            row["symbol"],
            row["side"],
            str(row["metadata"].get("event_id")),
        )
        if key not in allowed_scope:
            raise ValueError(f"unsupported candidate scope seed: {key}")
    for binding in rows.get("brc_candidate_scope_event_bindings", []):
        candidate = candidate_by_id[binding["candidate_scope_id"]]
        event = event_by_id[binding["event_spec_id"]]
        if (
            binding["strategy_group_id"] != candidate["strategy_group_id"]
            or binding["symbol"] != candidate["symbol"]
            or binding["side"] != candidate["side"]
            or binding["strategy_group_id"] != event["strategy_group_id"]
            or binding["side"] != event["side"]
        ):
            raise ValueError(f"candidate/event binding mismatch: {binding['binding_id']}")
    forbidden_runtime_tables = (
        "brc_live_signal_events",
        "brc_promotion_candidates",
        "brc_action_time_lane_inputs",
        "brc_action_time_tickets",
        "brc_budget_reservations",
        "brc_runtime_safety_state_snapshots",
    )
    for table_name in forbidden_runtime_tables:
        if rows.get(table_name):
            raise ValueError(f"{table_name} must not be seeded by foundation seed")


def seed_runtime_control_state_foundation(
    conn: sa.engine.Connection,
    *,
    now_ms: int = DEFAULT_NOW_MS,
    runtime_profile_id: str = DEFAULT_RUNTIME_PROFILE_ID,
    account_id: str = DEFAULT_ACCOUNT_ID,
) -> dict[str, Any]:
    rows = build_seed_rows(
        now_ms=now_ms,
        runtime_profile_id=runtime_profile_id,
        account_id=account_id,
    )
    table_counts: dict[str, int] = {}
    for table_name, table_rows in rows.items():
        if not table_rows:
            continue
        table_counts[table_name] = _upsert_rows(conn, table_name, table_rows)
    return _report(rows, table_counts=table_counts, applied=True)


def dry_run_report(
    *,
    now_ms: int = DEFAULT_NOW_MS,
    runtime_profile_id: str = DEFAULT_RUNTIME_PROFILE_ID,
    account_id: str = DEFAULT_ACCOUNT_ID,
) -> dict[str, Any]:
    rows = build_seed_rows(
        now_ms=now_ms,
        runtime_profile_id=runtime_profile_id,
        account_id=account_id,
    )
    table_counts = {table_name: len(table_rows) for table_name, table_rows in rows.items()}
    return _report(rows, table_counts=table_counts, applied=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--database-url", default=os.getenv("PG_DATABASE_URL", ""))
    parser.add_argument("--runtime-profile-id", default=DEFAULT_RUNTIME_PROFILE_ID)
    parser.add_argument("--account-id", default=DEFAULT_ACCOUNT_ID)
    parser.add_argument("--now-ms", type=int, default=DEFAULT_NOW_MS)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if not args.apply:
        report = dry_run_report(
            now_ms=args.now_ms,
            runtime_profile_id=args.runtime_profile_id,
            account_id=args.account_id,
        )
        _print_report(report, json_output=args.json)
        return 0

    if not args.database_url:
        print("ERROR: PG_DATABASE_URL or --database-url is required for --apply", file=sys.stderr)
        return 2
    if not args.database_url.startswith(("postgresql://", "postgresql+psycopg://")):
        print("ERROR: runtime control-state seed apply requires PostgreSQL DSN", file=sys.stderr)
        return 2

    engine = sa.create_engine(args.database_url)
    with engine.begin() as conn:
        report = seed_runtime_control_state_foundation(
            conn,
            now_ms=args.now_ms,
            runtime_profile_id=args.runtime_profile_id,
            account_id=args.account_id,
        )
    _print_report(report, json_output=args.json)
    return 0


def _append_required_fact_rows(
    rows: dict[str, list[dict[str, Any]]],
    *,
    seed: EventSeed,
    event_spec_id: str,
    now_ms: int,
) -> None:
    version_id = _strategy_group_version_id(seed.strategy_group_id)
    for fact_key in seed.required_facts:
        fact_contract_id = f"fact_contract:{version_id}:{fact_key}:finalgate"
        rows["brc_required_fact_contracts"].append(
            {
                "fact_contract_id": fact_contract_id,
                "strategy_group_version_id": version_id,
                "fact_key": fact_key,
                "fact_group": _fact_group(fact_key),
                "required_surface": "finalgate",
                "source_kind": "derived" if "reference" in fact_key else "watcher",
                "freshness_ms": seed.freshness_window_ms,
                "missing_blocker_class": "fact_missing",
                "failed_blocker_class": "computed_not_satisfied",
                "required_for_live_submit": True,
                "definition_payload": {
                    "event_id": seed.event_id,
                    "operator": "exists" if "reference" in fact_key else "eq",
                    "expected_value": None if "reference" in fact_key else True,
                },
                "created_at_ms": now_ms,
            }
        )
        rows["brc_strategy_event_required_facts"].append(
            {
                "event_required_fact_id": f"event_fact:{event_spec_id}:{fact_key}",
                "event_spec_id": event_spec_id,
                "required_facts_version_id": f"rf:{event_spec_id}:v1",
                "fact_key": fact_key,
                "fact_role": "required",
                "fact_surface": "finalgate",
                "operator": "exists" if "reference" in fact_key else "eq",
                "expected_value": None if "reference" in fact_key else True,
                "value_source": "runtime_fact_snapshot",
                "disable_on_match": False,
                "missing_blocker_class": "fact_missing",
                "failed_blocker_class": "computed_not_satisfied",
                "freshness_ms": seed.freshness_window_ms,
                "required_for_promotion": True,
                "required_for_ticket": True,
                "required_for_finalgate": True,
                "status": "current",
                "created_at_ms": now_ms,
            }
        )
    for fact_key in seed.disable_facts:
        rows["brc_strategy_event_required_facts"].append(
            {
                "event_required_fact_id": f"event_fact:{event_spec_id}:{fact_key}",
                "event_spec_id": event_spec_id,
                "required_facts_version_id": f"rf:{event_spec_id}:v1",
                "fact_key": fact_key,
                "fact_role": "disable",
                "fact_surface": "finalgate",
                "operator": "eq",
                "expected_value": True,
                "value_source": "runtime_fact_snapshot",
                "disable_on_match": True,
                "missing_blocker_class": "fact_missing",
                "failed_blocker_class": "strategy_disabled",
                "freshness_ms": seed.freshness_window_ms,
                "required_for_promotion": True,
                "required_for_ticket": True,
                "required_for_finalgate": True,
                "status": "current",
                "created_at_ms": now_ms,
            }
        )


def _append_projection_ownership_rows(
    rows: dict[str, list[dict[str, Any]]],
    *,
    now_ms: int,
) -> None:
    for model_type, owner_projector in (
        ("candidate_pool", "pg_candidate_pool_projector"),
        ("daily_live_enablement_table", "pg_daily_table_projector"),
        ("goal_status", "pg_goal_status_projector"),
        ("runtime_safety_state", "pg_runtime_safety_projector"),
        ("server_monitor", "pg_server_monitor_projector"),
        ("tradeability_decision", "pg_tradeability_projector"),
    ):
        projection_run_id = f"projection_seed:{model_type}:v1"
        rows["brc_projection_runs"].append(
            {
                "projection_run_id": projection_run_id,
                "model_type": model_type,
                "owner_projector": owner_projector,
                "code_version": "086",
                "source_mode": "db_backed",
                "projection_target": "production_current",
                "input_watermark": {"seed_version": SEED_VERSION},
                "source_priority": ["pg"],
                "legacy_diagnostics_read": False,
                "legacy_diagnostics_affected_current": False,
                "started_at_ms": now_ms,
                "finished_at_ms": now_ms,
                "status": "succeeded",
                "error_detail": None,
            }
        )
        rows["brc_current_projection_ownership"].append(
            {
                "projection_key": f"current:{model_type}",
                "model_type": model_type,
                "projection_scope_key": "global",
                "owner_projector": owner_projector,
                "export_paths": [],
                "legacy_writer_allowed": False,
                "current_source_mode": "db_backed",
                "sunset_condition": None,
                "updated_at_ms": now_ms,
            }
        )


def _upsert_rows(
    conn: sa.engine.Connection,
    table_name: str,
    rows: list[dict[str, Any]],
) -> int:
    metadata = sa.MetaData()
    table = sa.Table(table_name, metadata, autoload_with=conn)
    pk_columns = list(table.primary_key.columns)
    if len(pk_columns) != 1:
        raise RuntimeError(f"{table_name} must have exactly one primary key")
    pk = pk_columns[0]
    affected = 0
    for row in rows:
        pk_value = row[pk.name]
        existing = conn.execute(
            sa.select(pk).where(pk == pk_value).limit(1)
        ).scalar_one_or_none()
        if existing is None:
            conn.execute(table.insert().values(**row))
        else:
            conn.execute(table.update().where(pk == pk_value).values(**row))
        affected += 1
    return affected


def _report(
    rows: dict[str, list[dict[str, Any]]],
    *,
    table_counts: dict[str, int],
    applied: bool,
) -> dict[str, Any]:
    candidate_scope_rows = rows["brc_strategy_group_candidate_scope"]
    return {
        "schema": "brc.runtime_control_state_foundation_seed.v1",
        "status": "applied" if applied else "dry_run",
        "seed_version": SEED_VERSION,
        "strategy_group_count": len(rows["brc_strategy_groups"]),
        "event_spec_count": len(rows["brc_strategy_side_event_specs"]),
        "candidate_scope_count": len(candidate_scope_rows),
        "unique_symbol_count": len(rows["brc_symbols"]),
        "table_counts": table_counts,
        "strategy_scope_counts": _scope_counts(candidate_scope_rows),
        "forbidden_effects": {
            "live_signal_created": False,
            "promotion_candidate_created": False,
            "action_time_lane_created": False,
            "action_time_ticket_created": False,
            "finalgate_called": False,
            "operation_layer_called": False,
            "exchange_write_called": False,
            "order_created": False,
            "live_profile_changed": False,
            "order_sizing_changed": False,
        },
    }


def _scope_counts(candidate_scope_rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in candidate_scope_rows:
        counts[str(row["strategy_group_id"])] = counts.get(str(row["strategy_group_id"]), 0) + 1
    return counts


def _print_report(report: dict[str, Any], *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return
    print(f"status={report['status']}")
    print(f"strategy_group_count={report['strategy_group_count']}")
    print(f"event_spec_count={report['event_spec_count']}")
    print(f"candidate_scope_count={report['candidate_scope_count']}")


def _strategy_group_version_id(strategy_group_id: str) -> str:
    return f"sgv:{strategy_group_id}:v1"


def _event_spec_id(seed: EventSeed) -> str:
    return f"event_spec:{seed.strategy_group_id}:{seed.event_id}:v1"


def _candidate_scope_id(seed: EventSeed, symbol: str) -> str:
    return f"candidate_scope:{seed.strategy_group_id}:{symbol}:{seed.side}:{seed.event_id}"


def _exchange_symbol(symbol: str) -> str:
    if not symbol.endswith("USDT"):
        raise ValueError(f"unsupported seed symbol: {symbol}")
    base = symbol.removesuffix("USDT")
    return f"{base}/USDT:USDT"


def _fact_group(fact_key: str) -> str:
    if "reference" in fact_key:
        return "protection"
    if "disable" in fact_key:
        return "risk"
    return "strategy"


def _conditional_hard_gates(seed: EventSeed) -> list[str]:
    if seed.strategy_group_id == "BRF2-001" and seed.side == "short":
        return [
            "short_side_disable_clear",
            "squeeze_clear",
            "liquidity_clear",
        ]
    return []


def _edge_thesis(strategy_group_id: str) -> str:
    return {
        "CPM-RO-001": "Recovery continuation after pullback/reclaim confirmation.",
        "MPG-001": "Momentum persistence after leader continuation facts confirm.",
        "MI-001": "Relative-strength impulse continuation with invalidation refs.",
        "SOR-001": "Opening-range session break or breakdown with follow-through.",
        "BRF2-001": "Bear-rally failure after short-side disable facts clear.",
    }[strategy_group_id]


def _trade_logic(strategy_group_id: str) -> str:
    return {
        "CPM-RO-001": "Enter long only after HTF trend and reclaim facts satisfy.",
        "MPG-001": "Enter long only after momentum persistence and leader facts satisfy.",
        "MI-001": "Enter long only after impulse and relative-strength facts satisfy.",
        "SOR-001": "Enter long/short only on independent session break events.",
        "BRF2-001": "Enter short only after rally failure and no short disable.",
    }[strategy_group_id]


def _regime_fit(strategy_group_id: str) -> str:
    return {
        "CPM-RO-001": "Crypto pullback recovery regimes.",
        "MPG-001": "High-beta crypto momentum regimes.",
        "MI-001": "Impulse and relative strength regimes.",
        "SOR-001": "Session opening-range regimes.",
        "BRF2-001": "Failed rebound / bear-rally regimes.",
    }[strategy_group_id]


if __name__ == "__main__":
    raise SystemExit(main())
