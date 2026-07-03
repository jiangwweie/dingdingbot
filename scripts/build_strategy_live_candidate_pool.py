#!/usr/bin/env python3
"""Build the five StrategyGroup live-candidate pool control snapshot."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.infrastructure.runtime_control_state_repository import (  # noqa: E402
    FileBackedRuntimeControlStateRepository,
)

from scripts.build_daily_live_enablement_table import (  # noqa: E402
    AUTHORITY_BOUNDARY as DAILY_AUTHORITY_BOUNDARY,
    CONTRACT_BLOCKER_CLASSES,
    WIP_LANES,
)


SCHEMA = "brc.strategy_live_candidate_pool.v1"
OWNER_AUTHORIZATION_SCHEMA = "brc.owner_pretrade_runtime_authorization.v0"
DEFAULT_DAILY_TABLE_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-daily-live-enablement-table.json"
)
DEFAULT_TRADEABILITY_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-strategygroup-tradeability-decision.json"
)
DEFAULT_REPLAY_LIVE_PARITY_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-replay-live-parity-audit.json"
)
DEFAULT_ACTION_TIME_BOUNDARY_JSON = (
    REPO_ROOT
    / "output/runtime-monitor/latest-strategy-fresh-signal-action-time-boundary.json"
)
DEFAULT_SOR_DETECTOR_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-sor-session-detector-facts.json"
)
DEFAULT_MI_TRIAL_ADMISSION_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-mi-trial-admission-decision.json"
)
DEFAULT_BRF2_RUNTIME_SIGNAL_FACTS_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-brf2-runtime-signal-facts.json"
)
DEFAULT_SINGLE_LANE_TASK_PACKET_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-single-lane-task-packet.json"
)
DEFAULT_RUNTIME_ACTIVE_MONITOR_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-runtime-active-observation-status.json"
)
DEFAULT_OWNER_PRETRADE_AUTHORIZATION_JSON = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/owner-pretrade-runtime-authorization-v0.json"
)
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-strategy-live-candidate-pool.json"
)
DEFAULT_OUTPUT_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-strategy-live-candidate-pool.md"
)

AUTHORITY_BOUNDARY = (
    "live_candidate_pool_is_read_model; "
    "no_finalgate_no_operation_layer_no_exchange_write_no_live_profile_or_sizing_change"
)
CANDIDATE_POSITIONING = {
    "MPG-001": "selective leader continuation long candidate",
    "CPM-RO-001": "reclaim / pullback recovery long candidate",
    "MI-001": "relative strength / cross-asset candidate",
    "SOR-001": "session / flow confirmation candidate",
    "BRF2-001": "conditional failed-rebound short candidate",
}
DEFAULT_CANDIDATE_UNIVERSE = {
    "CPM-RO-001": ("ETHUSDT", "SOLUSDT", "AVAXUSDT", "SUIUSDT"),
    "MPG-001": ("OPUSDT", "SOLUSDT", "AVAXUSDT", "SUIUSDT"),
    "MI-001": ("AVAXUSDT", "SOLUSDT", "ETHUSDT"),
    "SOR-001": ("ETHUSDT", "SOLUSDT", "BTCUSDT", "AVAXUSDT"),
    "BRF2-001": ("BTCUSDT", "ETHUSDT", "AVAXUSDT"),
}
PLACEHOLDER_SYMBOLS = {
    "strategy_scope",
    "brf2_research_supported_symbols_only",
}
PRIMARY_SYMBOLS = {
    "CPM-RO-001": "ETHUSDT",
    "MPG-001": "OPUSDT",
    "MI-001": "AVAXUSDT",
    "SOR-001": "ETHUSDT",
    "BRF2-001": "BTCUSDT",
}
STRATEGY_SIDE = {
    "CPM-RO-001": "long",
    "MPG-001": "long",
    "MI-001": "long",
    "SOR-001": "long",
    "BRF2-001": "short",
}
ACTION_TIME_BLOCKERS = {
    "private_action_time_facts_required",
    "fresh_mpg_signal_or_private_action_time_facts",
    "fresh_sor_session_range_signal_absent",
}
RESIDUAL_DEPLOY_BLOCKERS = {
    "artifact_missing",
    "schema_invalid",
    "detector_not_attached",
    "watcher_tick_missing",
    "scope_not_attached",
    "replay_live_rule_mismatch",
    "action_time_boundary_not_reproduced",
    "action_time_preflight_ready",
    "policy_scope_missing",
    "runtime_profile_scope_missing",
    "active_position_resolution",
    "hard_safety_stop",
}
ACTION_TIME_BLOCKED_STATUSES = {
    "blocked_public_facts",
    "blocked_action_time_rehearsal",
}
ACTION_TIME_SCOPE_STATES = {
    "live_submit_allowed",
    "conditional_action_time_rehearsal_allowed",
}
ACTION_TIME_INPUT_BLOCKERS = {
    "action_time_boundary_not_reproduced",
    "active_position_resolution",
    "artifact_missing",
    "detector_not_attached",
    "watcher_tick_missing",
    "scope_not_attached",
    "policy_scope_missing",
    "hard_safety_stop",
    "replay_live_rule_mismatch",
}
SCOPED_LIVE_SUBMIT_STRATEGIES = {
    "CPM-RO-001",
    "MPG-001",
    "MI-001",
    "SOR-001",
}
P0_P1_ITEMS = (
    ("P0", "five_strategy_candidate_pool_control_surface"),
    ("P0", "mpg_watcher_closure"),
    ("P0", "sor_watcher_closure"),
    ("P0", "mi_scope_closure"),
    ("P0", "cpm_computed_refresh"),
    ("P0", "brf2_conditionalization"),
    ("P0", "no_authority_leakage"),
    ("P1", "candidate_pool_validator"),
    ("P1", "output_whitelist_gate"),
    ("P1", "no_stale_facts"),
    ("P1", "review_report"),
    ("P1", "postdeploy_validation_script"),
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--daily-table-json", default=str(DEFAULT_DAILY_TABLE_JSON))
    parser.add_argument("--tradeability-json", default=str(DEFAULT_TRADEABILITY_JSON))
    parser.add_argument(
        "--replay-live-parity-json", default=str(DEFAULT_REPLAY_LIVE_PARITY_JSON)
    )
    parser.add_argument(
        "--action-time-boundary-json", default=str(DEFAULT_ACTION_TIME_BOUNDARY_JSON)
    )
    parser.add_argument("--sor-detector-json", default=str(DEFAULT_SOR_DETECTOR_JSON))
    parser.add_argument(
        "--mi-trial-admission-json", default=str(DEFAULT_MI_TRIAL_ADMISSION_JSON)
    )
    parser.add_argument(
        "--brf2-runtime-signal-facts-json",
        default=str(DEFAULT_BRF2_RUNTIME_SIGNAL_FACTS_JSON),
    )
    parser.add_argument(
        "--single-lane-task-packet-json",
        default=str(DEFAULT_SINGLE_LANE_TASK_PACKET_JSON),
    )
    parser.add_argument(
        "--runtime-active-monitor-json",
        default=str(DEFAULT_RUNTIME_ACTIVE_MONITOR_JSON),
        help=(
            "Optional runtime active monitor/status artifact with "
            "candidate_universe_coverage."
        ),
    )
    parser.add_argument(
        "--owner-pretrade-authorization-json",
        default=str(DEFAULT_OWNER_PRETRADE_AUTHORIZATION_JSON),
        help="Machine-readable Owner pre-trade runtime authorization.",
    )
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-owner-progress", default=str(DEFAULT_OUTPUT_MD))
    args = parser.parse_args(argv)

    repository = FileBackedRuntimeControlStateRepository()
    inputs = repository.candidate_pool_inputs(
        daily_table_json=Path(args.daily_table_json),
        tradeability_json=Path(args.tradeability_json),
        replay_live_parity_json=Path(args.replay_live_parity_json),
        action_time_boundary_json=Path(args.action_time_boundary_json),
        sor_detector_json=Path(args.sor_detector_json),
        mi_trial_admission_json=Path(args.mi_trial_admission_json),
        brf2_runtime_signal_facts_json=Path(args.brf2_runtime_signal_facts_json),
        single_lane_task_packet_json=Path(args.single_lane_task_packet_json),
        runtime_active_monitor_json=Path(args.runtime_active_monitor_json),
        owner_pretrade_authorization_json=Path(args.owner_pretrade_authorization_json),
    )
    artifact = build_strategy_live_candidate_pool(
        daily_table=inputs["daily_table"],
        tradeability=inputs["tradeability"],
        replay_live_parity=inputs["replay_live_parity"],
        action_time_boundary=inputs["action_time_boundary"],
        sor_detector=inputs["sor_detector"],
        mi_trial_admission=inputs["mi_trial_admission"],
        brf2_runtime_signal_facts=inputs["brf2_runtime_signal_facts"],
        single_lane_task_packet=inputs["single_lane_task_packet"],
        runtime_active_monitor=inputs["runtime_active_monitor"],
        owner_pretrade_authorization=inputs["owner_pretrade_authorization"],
    )
    output_json = Path(args.output_json)
    output_md = Path(args.output_owner_progress)
    _write_json(output_json, artifact)
    _write_text(output_md, _markdown(artifact, output_json))
    print(
        json.dumps(
            {
                "status": artifact["status"],
                "candidate_count": artifact["summary"]["candidate_count"],
                "p0_cleared": artifact["summary"]["p0_cleared"],
                "p1_cleared_or_waived": artifact["summary"][
                    "p1_cleared_or_waived"
                ],
                "deploy_ready": artifact["summary"]["deploy_ready"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def build_strategy_live_candidate_pool(
    *,
    daily_table: dict[str, Any],
    tradeability: dict[str, Any],
    replay_live_parity: dict[str, Any],
    action_time_boundary: dict[str, Any],
    single_lane_task_packet: dict[str, Any],
    sor_detector: dict[str, Any] | None = None,
    mi_trial_admission: dict[str, Any] | None = None,
    brf2_runtime_signal_facts: dict[str, Any] | None = None,
    runtime_active_monitor: dict[str, Any] | None = None,
    owner_pretrade_authorization: dict[str, Any] | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    runtime_active_monitor = runtime_active_monitor or {}
    owner_pretrade_authorization = (
        owner_pretrade_authorization
        if owner_pretrade_authorization is not None
        else _read_json(DEFAULT_OWNER_PRETRADE_AUTHORIZATION_JSON)
    )
    generated = (
        generated_at_utc
        or str(daily_table.get("generated_at_utc") or "")
        or datetime.now(timezone.utc).isoformat()
    )
    source_validation = _source_validation(
        daily_table=daily_table,
        tradeability=tradeability,
        replay_live_parity=replay_live_parity,
        action_time_boundary=action_time_boundary,
        single_lane_task_packet=single_lane_task_packet,
    )
    daily_rows = {
        str(row.get("strategy_group_id") or ""): row
        for row in _dict_rows(daily_table.get("rows"))
    }
    tradeability_rows = {
        str(row.get("strategy_group_id") or ""): row
        for row in _dict_rows(tradeability.get("decision_rows"))
    }
    candidate_rows = [
        _candidate_row(
            strategy_group_id=strategy_group_id,
            daily_row=daily_rows.get(strategy_group_id, {}),
            tradeability_row=tradeability_rows.get(strategy_group_id, {}),
            action_row=_action_time_row(
                action_time_boundary=action_time_boundary,
                strategy_group_id=strategy_group_id,
                symbol=str(
                    daily_rows.get(strategy_group_id, {}).get("symbol") or ""
                ),
            ),
        )
        for strategy_group_id in WIP_LANES
    ]
    symbol_readiness_rows = _symbol_readiness_rows(
        candidate_rows=candidate_rows,
        daily_rows=daily_rows,
        replay_live_parity=replay_live_parity,
        action_time_boundary=action_time_boundary,
        sor_detector=sor_detector or {},
        mi_trial_admission=mi_trial_admission or {},
        brf2_runtime_signal_facts=brf2_runtime_signal_facts or {},
        tradeability_rows=tradeability_rows,
        runtime_active_monitor=runtime_active_monitor,
        owner_pretrade_authorization=owner_pretrade_authorization,
    )
    candidate_rows = _sync_candidate_rows_with_symbol_readiness(
        candidate_rows,
        symbol_readiness_rows,
    )
    promotion_candidates = [
        row
        for row in symbol_readiness_rows
        if row["promotion_state"] == "promotion_candidate"
    ]
    eligible_action_time_rows = [
        row
        for row in symbol_readiness_rows
        if row["promotion_state"] == "action_time_lane"
    ]
    selected_action_time_row = _select_action_time_row(eligible_action_time_rows)
    action_time_lane_inputs = (
        [_action_time_lane_input(selected_action_time_row)]
        if selected_action_time_row
        else []
    )
    arbitration = _arbitration(
        promotion_candidates=promotion_candidates,
        eligible_action_time_rows=eligible_action_time_rows,
        selected_action_time_row=selected_action_time_row,
    )
    no_trade_audit = _no_trade_audit(
        symbol_readiness_rows=symbol_readiness_rows,
        action_time_lane_inputs=action_time_lane_inputs,
        arbitration=arbitration,
    )
    p0_p1_review = _p0_p1_review(candidate_rows, source_validation)
    p0_cleared = all(
        row["status"] == "cleared"
        for row in p0_p1_review
        if row["priority"] == "P0"
    )
    p1_cleared_or_waived = all(
        row["status"] in {"cleared", "waived", "waived_with_reason"}
        for row in p0_p1_review
        if row["priority"] == "P1"
    )
    deploy_ready = (
        p0_cleared
        and p1_cleared_or_waived
        and not _residual_deploy_blockers(candidate_rows)
    )
    return {
        "schema": SCHEMA,
        "scope": "five_strategy_live_candidate_pool_non_authority",
        "status": (
            "strategy_live_candidate_pool_ready"
            if source_validation["valid"]
            else "strategy_live_candidate_pool_source_invalid"
        ),
        "generated_at_utc": generated,
        "source_validation": source_validation,
        "pretrade_runtime": {
            "name": "Multi-Strategy Multi-Symbol Pre-Trade Runtime V0",
            "principle": (
                "wide_observation_medium_candidate_narrow_action_time_"
                "single_intent_submit"
            ),
            "active_strategy_groups": list(WIP_LANES),
            "candidate_symbols_per_strategy_group": {
                strategy_group_id: len(
                    [
                        row
                        for row in symbol_readiness_rows
                        if row["strategy_group_id"] == strategy_group_id
                    ]
                )
                for strategy_group_id in WIP_LANES
            },
            "owner_authorization": _owner_authorization_summary(
                owner_pretrade_authorization
            ),
        },
        "candidate_universe": _candidate_universe(symbol_readiness_rows),
        "server_runtime_coverage": _runtime_coverage(runtime_active_monitor),
        "candidate_rows": candidate_rows,
        "symbol_readiness_rows": symbol_readiness_rows,
        "promotion_candidates": promotion_candidates,
        "action_time_lane_inputs": action_time_lane_inputs,
        "arbitration": arbitration,
        "no_trade_audit": no_trade_audit,
        "p0_p1_review": p0_p1_review,
        "summary": {
            "candidate_count": len(candidate_rows),
            "symbol_readiness_count": len(symbol_readiness_rows),
            "fresh_candidate_count": len(promotion_candidates),
            "action_time_lane_input_count": len(action_time_lane_inputs),
            "top_action_time_candidate": arbitration["selected_action_time_candidate"],
            "wip_lane_count": len(WIP_LANES),
            "p0_cleared": p0_cleared,
            "p1_cleared_or_waived": p1_cleared_or_waived,
            "deploy_ready": deploy_ready,
            "non_authority": True,
        },
        "checks": {
            "source_validation_passed": source_validation["valid"],
            "five_wip_candidates_present": {
                row["strategy_group_id"] for row in candidate_rows
            }
            == set(WIP_LANES),
            "all_rows_have_required_candidate_fields": all(
                _candidate_row_complete(row) for row in candidate_rows
            ),
            "each_strategy_has_multiple_candidate_symbols": all(
                count >= 2
                for count in {
                    row["strategy_group_id"]: len(
                        [
                            candidate
                            for candidate in symbol_readiness_rows
                            if candidate["strategy_group_id"]
                            == row["strategy_group_id"]
                        ]
                    )
                    for row in candidate_rows
                }.values()
            ),
            "readonly_signal_cannot_order": all(
                row["scope_state"] != "readonly_only"
                for row in action_time_lane_inputs
            ),
            "single_real_submit_candidate": len(action_time_lane_inputs) <= 1
            and len(_dict_rows(arbitration.get("deferred_action_time_candidates")))
            == max(len(eligible_action_time_rows) - 1, 0),
            "p0_cleared": p0_cleared,
            "p1_cleared_or_waived": p1_cleared_or_waived,
            "deploy_ready": deploy_ready,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
            "order_created": False,
        },
        "authority_boundary": AUTHORITY_BOUNDARY,
        "safety_invariants": {
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
            "order_created": False,
            "live_profile_changed": False,
            "order_sizing_changed": False,
        },
    }


def _action_time_row(
    *,
    action_time_boundary: dict[str, Any],
    strategy_group_id: str,
    symbol: str,
) -> dict[str, Any]:
    fallback: dict[str, Any] = {}
    for row in _dict_rows(action_time_boundary.get("strategy_rows")):
        if str(row.get("strategy_group_id") or "") != strategy_group_id:
            continue
        if symbol and str(row.get("symbol") or "") == symbol:
            return row
        if not fallback:
            fallback = row
    return fallback


def _symbol_readiness_rows(
    *,
    candidate_rows: list[dict[str, Any]],
    daily_rows: dict[str, dict[str, Any]],
    replay_live_parity: dict[str, Any],
    action_time_boundary: dict[str, Any],
    sor_detector: dict[str, Any],
    mi_trial_admission: dict[str, Any],
    brf2_runtime_signal_facts: dict[str, Any],
    tradeability_rows: dict[str, dict[str, Any]],
    runtime_active_monitor: dict[str, Any],
    owner_pretrade_authorization: dict[str, Any],
) -> list[dict[str, Any]]:
    parity_rows = _dict_rows(replay_live_parity.get("per_symbol_mismatch_table"))
    sor_facts = _sor_detector_symbol_facts(sor_detector)
    mi_facts = _mi_trial_admission_symbol_facts(mi_trial_admission)
    brf2_facts = _brf2_runtime_signal_symbol_facts(brf2_runtime_signal_facts)
    action_rows = _dict_rows(action_time_boundary.get("strategy_rows"))
    runtime_coverage_rows = _dict_rows(
        _runtime_coverage(runtime_active_monitor).get("rows")
    )
    result: list[dict[str, Any]] = []
    for candidate in candidate_rows:
        strategy_group_id = str(candidate.get("strategy_group_id") or "")
        daily_row = daily_rows.get(strategy_group_id, {})
        symbols = _candidate_symbols(
            strategy_group_id=strategy_group_id,
            selected_symbol=str(candidate.get("selected_symbol") or ""),
            parity_rows=parity_rows,
            action_rows=action_rows,
        )
        for symbol in symbols:
            parity_row = _matching_symbol_row(parity_rows, strategy_group_id, symbol)
            if strategy_group_id == "SOR-001":
                parity_row = _merge_symbol_fact_row(
                    parity_row,
                    sor_facts.get(symbol, {}),
                )
            if strategy_group_id == "MI-001":
                parity_row = _merge_symbol_fact_row(
                    parity_row,
                    mi_facts.get(symbol, {}),
                )
            if strategy_group_id == "BRF2-001":
                parity_row = _merge_symbol_fact_row(
                    parity_row,
                    brf2_facts.get(symbol, {}),
                )
            action_row = _matching_symbol_row(action_rows, strategy_group_id, symbol)
            runtime_coverage_row = _matching_symbol_row(
                runtime_coverage_rows,
                strategy_group_id,
                symbol,
            ) or _missing_runtime_coverage_row(strategy_group_id, symbol)
            runtime_coverage_row = _normalize_runtime_coverage_row(
                runtime_coverage_row,
                strategy_group_id,
                symbol,
            )
            result.append(
                _symbol_readiness_row(
                    strategy_group_id=strategy_group_id,
                    symbol=symbol,
                    candidate=candidate,
                    daily_row=daily_row,
                    tradeability_row=tradeability_rows.get(strategy_group_id, {}),
                    parity_row=parity_row,
                    action_row=action_row,
                    runtime_coverage_row=runtime_coverage_row,
                    owner_pretrade_authorization=owner_pretrade_authorization,
                )
            )
    return result


def _merge_symbol_fact_row(
    base: dict[str, Any],
    override: dict[str, Any],
) -> dict[str, Any]:
    if not override:
        return base
    merged = dict(base)
    merged.update(override)
    return merged


def _sor_detector_symbol_facts(detector: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if detector.get("status") != "sor_session_detector_facts_ready":
        return {}
    rows: dict[str, dict[str, Any]] = {}
    for row in _dict_rows(detector.get("symbol_detector_rows")):
        symbol = str(row.get("symbol") or "")
        if not symbol:
            continue
        missing = [
            str(item)
            for item in row.get("missing_required_trigger_facts") or []
            if str(item or "")
        ]
        candle_tick_present = bool(row.get("latest_candle_close_time_utc")) and (
            "opening_range_available" not in missing
        )
        public_facts_ready = row.get("public_facts_ready") is True
        watcher_tick_present = public_facts_ready and candle_tick_present
        rows[symbol] = {
            "blocker_class": (
                "computed_not_satisfied"
                if watcher_tick_present and missing
                else "market_wait_validated"
                if watcher_tick_present
                else "watcher_tick_missing"
            ),
            "detector_attached": True,
            "watcher_tick_present": watcher_tick_present,
            "computed": watcher_tick_present,
            "fresh_signal_present": row.get("fresh_session_range_signal") is True,
            "failed_facts": missing if watcher_tick_present else [],
            "next_action": (
                "continue_observation_with_failed_fact_matrix"
                if watcher_tick_present
                else "refresh_or_repair_watcher_public_fact_input"
            ),
        }
    return rows


def _mi_trial_admission_symbol_facts(
    admission: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    if admission.get("status") != "mi_trial_admission_decision_ready":
        return {}
    rows: dict[str, dict[str, Any]] = {}
    for row in _dict_rows(admission.get("symbol_evidence")):
        symbol = str(row.get("symbol") or "")
        if not _symbol_authorized("MI-001", symbol):
            continue
        failed = _mi_failed_facts(row)
        rows[symbol] = {
            "blocker_class": (
                "computed_not_satisfied" if failed else "market_wait_validated"
            ),
            "detector_attached": True,
            "watcher_tick_present": True,
            "computed": True,
            "fresh_signal_present": False,
            "failed_facts": failed,
            "next_action": (
                "continue_observation_with_failed_fact_matrix"
                if failed
                else "wait_for_fresh_signal_or_refresh_action_time_facts"
            ),
            "evidence_source": "mi_trial_admission_decision:symbol_evidence",
        }
    return rows


def _mi_failed_facts(row: dict[str, Any]) -> list[str]:
    failed: list[str] = []
    if row.get("replay_supported") is not True:
        failed.append("replay_supported")
    if row.get("public_facts_ready") is not True:
        failed.append("public_facts_ready")
    liquidity = _as_dict(row.get("liquidity"))
    for key in ("spread_ok", "min_notional_ok", "qty_step_ok"):
        if liquidity.get(key) is not True:
            failed.append(key)
    if row.get("funding_not_extreme") is not True:
        failed.append("funding_not_extreme")
    if str(row.get("strategy_fit") or "") == "not_supported_by_current_replay":
        failed.append("strategy_fit")
    return sorted(set(failed))


def _brf2_runtime_signal_symbol_facts(
    facts_artifact: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    status = str(facts_artifact.get("status") or "")
    if not status:
        return {}
    symbols = DEFAULT_CANDIDATE_UNIVERSE["BRF2-001"]
    if status == "brf2_runtime_signal_facts_missing_watcher_input":
        return {
            symbol: {
                "blocker_class": "watcher_tick_missing",
                "detector_attached": True,
                "watcher_tick_present": False,
                "computed": False,
                "fresh_signal_present": False,
                "failed_facts": [],
                "next_action": "attach_brf2_watcher_fact_input_producer",
                "evidence_source": "brf2_runtime_signal_facts:missing_watcher_input",
            }
            for symbol in symbols
        }
    if status != "brf2_runtime_signal_facts_ready":
        return {}
    per_symbol_rows = _dict_rows(facts_artifact.get("per_symbol_facts"))
    if per_symbol_rows:
        rows: dict[str, dict[str, Any]] = {}
        for row in per_symbol_rows:
            symbol = _normalize_symbol(row.get("symbol"))
            if not _symbol_authorized("BRF2-001", symbol):
                continue
            failed = _brf2_failed_facts(_as_dict(row.get("facts")))
            watcher_tick_present = row.get("watcher_tick_present") is True
            computed = row.get("fact_input_present") is True and watcher_tick_present
            rows[symbol] = {
                "blocker_class": (
                    "computed_not_satisfied" if failed else "market_wait_validated"
                ),
                "detector_attached": True,
                "watcher_tick_present": watcher_tick_present,
                "computed": computed,
                "fresh_signal_present": row.get("fresh_signal_present") is True,
                "failed_facts": failed if computed else [],
                "next_action": (
                    "continue_observation_with_failed_fact_matrix"
                    if failed
                    else "wait_for_fresh_signal_or_refresh_action_time_facts"
                ),
                "evidence_source": "brf2_runtime_signal_facts:per_symbol_facts",
            }
        for symbol in symbols:
            rows.setdefault(
                symbol,
                {
                    "blocker_class": "watcher_tick_missing",
                    "detector_attached": True,
                    "watcher_tick_present": False,
                    "computed": False,
                    "fresh_signal_present": False,
                    "failed_facts": [],
                    "next_action": "attach_brf2_watcher_fact_input_producer",
                    "evidence_source": "brf2_runtime_signal_facts:missing_symbol_fact_input",
                },
            )
        return rows
    observed_symbol = _normalize_symbol(
        _as_dict(facts_artifact.get("signal_context")).get("symbol")
        or _as_dict(facts_artifact.get("source_signal_context")).get("symbol")
    )
    observed_symbol_authorized = _symbol_authorized("BRF2-001", observed_symbol)
    failed = _brf2_failed_facts(_as_dict(facts_artifact.get("facts")))
    rows: dict[str, dict[str, Any]] = {}
    for symbol in symbols:
        if not observed_symbol_authorized or symbol != observed_symbol:
            rows[symbol] = {
                "blocker_class": "watcher_tick_missing",
                "detector_attached": True,
                "watcher_tick_present": False,
                "computed": False,
                "fresh_signal_present": False,
                "failed_facts": [],
                "next_action": "attach_brf2_watcher_fact_input_producer",
                "evidence_source": "brf2_runtime_signal_facts:missing_symbol_fact_input",
            }
            continue
        rows[symbol] = {
            "blocker_class": (
                "computed_not_satisfied" if failed else "market_wait_validated"
            ),
            "detector_attached": True,
            "watcher_tick_present": facts_artifact.get("watcher_tick_present") is True,
            "computed": facts_artifact.get("fact_input_present") is True,
            "fresh_signal_present": False,
            "failed_facts": failed,
            "next_action": (
                "continue_observation_with_failed_fact_matrix"
                if failed
                else "wait_for_fresh_signal_or_refresh_action_time_facts"
            ),
            "evidence_source": "brf2_runtime_signal_facts:facts",
        }
    return rows


def _brf2_failed_facts(facts: dict[str, Any]) -> list[str]:
    if not facts:
        return ["brf2_runtime_signal_facts"]
    failed: list[str] = []
    accepted = {
        "closed_1h_ohlcv": {"fresh", "present", "ready"},
        "closed_5m_ohlcv": {"fresh", "present", "ready"},
        "rally_context": {"bear_or_weak_reclaim", "ready", "weak_rally"},
        "rally_failure_trigger_state": {"active", "confirmed", "ready"},
        "short_squeeze_risk_state": {"clear", "clear_or_bounded"},
        "strong_reclaim_disable_state": {"clear", "false", "inactive"},
        "liquidity_downshift_state": {"clear", "false", "inactive"},
        "spread_liquidity_state": {"acceptable", "normal", "ready"},
    }
    disable_active = {
        "short_squeeze_risk_state": {"bounded", "red", "unbounded", "unknown"},
        "strong_reclaim_disable_state": {"active", "true"},
        "rally_extension_invalidates_failure_state": {"active", "true"},
        "liquidity_downshift_state": {"active", "true"},
        "spread_liquidity_state": {"missing", "wide_spread", "thin_volume", "unknown"},
    }
    for fact_key, accepted_statuses in accepted.items():
        status = str(_as_dict(facts.get(fact_key)).get("status") or "").lower()
        if status not in accepted_statuses:
            failed.append(fact_key)
    for fact_key, active_statuses in disable_active.items():
        status = str(_as_dict(facts.get(fact_key)).get("status") or "").lower()
        if status in active_statuses:
            failed.append(fact_key)
    return sorted(set(failed))


def _normalize_symbol(value: Any) -> str:
    symbol = str(value or "").upper()
    if not symbol:
        return ""
    symbol = symbol.split(":", 1)[0].replace("/", "")
    return symbol


def _candidate_symbols(
    *,
    strategy_group_id: str,
    selected_symbol: str,
    parity_rows: list[dict[str, Any]],
    action_rows: list[dict[str, Any]],
) -> list[str]:
    symbols: list[str] = []
    for symbol in DEFAULT_CANDIDATE_UNIVERSE.get(strategy_group_id, ()):
        symbols.append(symbol)
    for symbol in (
        selected_symbol,
        *(
            str(row.get("symbol") or "")
            for row in parity_rows
            if str(row.get("strategy_group_id") or "") == strategy_group_id
        ),
        *(
            str(row.get("symbol") or "")
            for row in action_rows
            if str(row.get("strategy_group_id") or "") == strategy_group_id
        ),
    ):
        if _symbol_authorized(strategy_group_id, symbol):
            symbols.append(symbol)
    if not symbols:
        symbols.append(PRIMARY_SYMBOLS.get(strategy_group_id, "strategy_scope"))
    return sorted(set(symbols), key=lambda symbol: (_symbol_role(strategy_group_id, symbol), symbol))


def _symbol_authorized(strategy_group_id: str, symbol: str) -> bool:
    if not symbol or symbol in PLACEHOLDER_SYMBOLS:
        return False
    authorized = set(DEFAULT_CANDIDATE_UNIVERSE.get(strategy_group_id, ()))
    return symbol in authorized


def _owner_authorization_summary(
    authorization: dict[str, Any],
) -> dict[str, Any]:
    valid = _owner_authorization_valid(authorization)
    strategy_groups = _as_dict(authorization.get("strategy_groups"))
    return {
        "schema": str(authorization.get("schema") or ""),
        "status": str(authorization.get("status") or ""),
        "valid": valid,
        "pretrade_candidate_allowed": authorization.get(
            "pretrade_candidate_allowed"
        )
        is True,
        "action_time_rehearsal_allowed": authorization.get(
            "action_time_rehearsal_allowed"
        )
        is True,
        "v0_single_action_time_lane": authorization.get(
            "v0_single_action_time_lane"
        )
        is True,
        "v0_single_real_submit_intent": authorization.get(
            "v0_single_real_submit_intent"
        )
        is True,
        "scoped_live_submit_strategy_groups": sorted(
            strategy_group_id
            for strategy_group_id in WIP_LANES
            if _as_dict(strategy_groups.get(strategy_group_id)).get(
                "live_submit_allowed"
            )
            == "scoped"
        ),
        "conditional_hard_gated_strategy_groups": sorted(
            strategy_group_id
            for strategy_group_id in WIP_LANES
            if _as_dict(strategy_groups.get(strategy_group_id)).get(
                "live_submit_allowed"
            )
            == "conditional_hard_gated"
        ),
        "authority_boundary": str(authorization.get("authority_boundary") or ""),
    }


def _owner_authorization_valid(authorization: dict[str, Any]) -> bool:
    if authorization.get("schema") != OWNER_AUTHORIZATION_SCHEMA:
        return False
    if authorization.get("status") != "owner_pretrade_runtime_authorization_recorded":
        return False
    if authorization.get("pretrade_candidate_allowed") is not True:
        return False
    if authorization.get("action_time_rehearsal_allowed") is not True:
        return False
    if authorization.get("v0_single_action_time_lane") is not True:
        return False
    if authorization.get("v0_single_real_submit_intent") is not True:
        return False
    strategy_groups = _as_dict(authorization.get("strategy_groups"))
    for strategy_group_id, symbols in DEFAULT_CANDIDATE_UNIVERSE.items():
        row = _as_dict(strategy_groups.get(strategy_group_id))
        if row.get("pretrade_candidate_allowed") is not True:
            return False
        if row.get("action_time_rehearsal_allowed") is not True:
            return False
        if set(str(item) for item in row.get("candidate_symbols") or []) != set(
            symbols
        ):
            return False
    return True


def _symbol_owner_authorization(
    authorization: dict[str, Any],
    strategy_group_id: str,
    symbol: str,
) -> dict[str, Any]:
    if not _owner_authorization_valid(authorization):
        return {
            "pretrade_candidate_allowed": False,
            "action_time_rehearsal_allowed": False,
            "live_submit_allowed": "none",
            "real_submit_required_gates": [],
            "authority_boundary": "owner_pretrade_authorization_missing_or_invalid",
        }
    strategy_groups = _as_dict(authorization.get("strategy_groups"))
    row = _as_dict(strategy_groups.get(strategy_group_id))
    symbols = {str(item) for item in row.get("candidate_symbols") or []}
    symbol_allowed = symbol in symbols and _symbol_authorized(strategy_group_id, symbol)
    return {
        "pretrade_candidate_allowed": bool(
            symbol_allowed and row.get("pretrade_candidate_allowed") is True
        ),
        "action_time_rehearsal_allowed": bool(
            symbol_allowed and row.get("action_time_rehearsal_allowed") is True
        ),
        "live_submit_allowed": (
            str(row.get("live_submit_allowed") or "none")
            if symbol_allowed
            else "none"
        ),
        "real_submit_required_gates": [
            str(item) for item in row.get("real_submit_required_gates") or []
        ]
        if symbol_allowed
        else [],
        "authority_boundary": str(authorization.get("authority_boundary") or ""),
    }


def _matching_symbol_row(
    rows: list[dict[str, Any]], strategy_group_id: str, symbol: str
) -> dict[str, Any]:
    for row in rows:
        if (
            str(row.get("strategy_group_id") or "") == strategy_group_id
            and str(row.get("symbol") or "") == symbol
        ):
            return row
    return {}


def _missing_runtime_coverage_row(strategy_group_id: str, symbol: str) -> dict[str, Any]:
    return {
        "strategy_group_id": strategy_group_id,
        "symbol": symbol,
        "state": "runtime_profile_scope_missing",
        "blocker_class": "runtime_profile_scope_missing",
        "active_runtime_instance_ids": [],
        "selected_runtime_instance_ids": [],
        "next_action": "bind_or_start_pretrade_runtime_for_candidate_symbol",
        "authority_boundary": AUTHORITY_BOUNDARY,
    }


def _normalize_runtime_coverage_row(
    row: dict[str, Any], strategy_group_id: str, symbol: str
) -> dict[str, Any]:
    normalized = dict(row)
    normalized.setdefault("strategy_group_id", strategy_group_id)
    normalized.setdefault("symbol", symbol)
    normalized.setdefault("state", "runtime_profile_scope_missing")
    normalized.setdefault("blocker_class", "runtime_profile_scope_missing")
    normalized.setdefault("active_runtime_instance_ids", [])
    normalized.setdefault("selected_runtime_instance_ids", [])
    normalized.setdefault(
        "next_action",
        "bind_or_start_pretrade_runtime_for_candidate_symbol",
    )
    normalized.setdefault("authority_boundary", AUTHORITY_BOUNDARY)
    return normalized


def _symbol_readiness_row(
    *,
    strategy_group_id: str,
    symbol: str,
    candidate: dict[str, Any],
    daily_row: dict[str, Any],
    tradeability_row: dict[str, Any],
    parity_row: dict[str, Any],
    action_row: dict[str, Any],
    runtime_coverage_row: dict[str, Any],
    owner_pretrade_authorization: dict[str, Any],
) -> dict[str, Any]:
    runtime_active = _server_runtime_scope_ready(runtime_coverage_row)
    detector_ready = parity_row.get("detector_attached") is True
    watcher_present = (
        parity_row.get("watcher_tick_present") is True
        if parity_row
        else runtime_active
    )
    computed = parity_row.get("computed") is True
    failed_facts = [
        str(item)
        for item in parity_row.get("failed_facts", [])
        if isinstance(item, str)
    ]
    public_facts_state = _public_facts_state(
        parity_row=parity_row,
        computed=computed,
        failed_facts=failed_facts,
    )
    signal_state = _signal_state(action_row, parity_row)
    scope_state = _scope_state(
        strategy_group_id=strategy_group_id,
        symbol=symbol,
        candidate=candidate,
        daily_row=daily_row,
        tradeability_row=tradeability_row,
        owner_pretrade_authorization=owner_pretrade_authorization,
    )
    owner_authorization = _symbol_owner_authorization(
        owner_pretrade_authorization,
        strategy_group_id,
        symbol,
    )
    risk_state = _risk_state(parity_row)
    action_time_scope_missing = (
        signal_state == "fresh"
        and scope_state in ACTION_TIME_SCOPE_STATES
        and public_facts_state["state"] == "satisfied"
        and not runtime_active
    )
    first_blocker = _symbol_first_blocker(
        candidate=candidate,
        action_row=action_row,
        parity_row=parity_row,
        detector_ready=detector_ready,
        watcher_present=watcher_present,
        public_facts_state=public_facts_state,
        signal_state=signal_state,
        scope_state=scope_state,
        risk_state=risk_state,
        runtime_scope_missing=action_time_scope_missing,
    )
    promotion_state = _promotion_state(
        public_facts_state=public_facts_state,
        signal_state=signal_state,
        scope_state=scope_state,
        risk_state=risk_state,
        first_blocker=first_blocker,
        runtime_scope_missing=action_time_scope_missing,
    )
    return {
        "strategy_group_id": strategy_group_id,
        "symbol_or_basket": symbol,
        "symbol": symbol,
        "asset_class": "crypto_perpetual",
        "side": str(candidate.get("side") or STRATEGY_SIDE.get(strategy_group_id, "unknown")),
        "candidate_role": _candidate_role(strategy_group_id, symbol),
        "observation_scope": (
            "active_observation" if watcher_present else "readonly"
        ),
        "detector_state": "ready" if detector_ready else "missing",
        "watcher_state": "fresh" if watcher_present else "missing",
        "public_facts_state": public_facts_state,
        "signal_state": signal_state,
        "risk_state": risk_state,
        "scope_state": scope_state,
        "owner_authorization": owner_authorization,
        "promotion_state": promotion_state,
        "first_blocker": first_blocker,
        "next_action": _symbol_next_action(first_blocker, candidate, action_row),
        "stop_condition": _symbol_stop_condition(first_blocker),
        "evidence_ref": _symbol_evidence_ref(
            strategy_group_id=strategy_group_id,
            symbol=symbol,
            first_blocker=first_blocker,
            parity_row=parity_row,
            action_row=action_row,
            runtime_coverage_row=runtime_coverage_row,
        ),
        "action_time": _action_time_readiness(action_row),
        "server_runtime_coverage": runtime_coverage_row or {},
        "authority_boundary": AUTHORITY_BOUNDARY,
    }


def _public_facts_state(
    *, parity_row: dict[str, Any], computed: bool, failed_facts: list[str]
) -> dict[str, Any]:
    if not parity_row:
        return {
            "state": "missing",
            "missing": ["per_symbol_replay_live_parity_row"],
            "computed_not_satisfied": [],
            "satisfied": [],
        }
    if not computed:
        return {
            "state": "missing",
            "missing": ["computed_public_facts"],
            "computed_not_satisfied": [],
            "satisfied": [],
        }
    if failed_facts:
        return {
            "state": "computed_not_satisfied",
            "missing": [],
            "computed_not_satisfied": failed_facts,
            "satisfied": [],
        }
    return {
        "state": "satisfied",
        "missing": [],
        "computed_not_satisfied": [],
        "satisfied": ["strategy_public_fact_matrix"],
    }


def _signal_state(action_row: dict[str, Any], parity_row: dict[str, Any] | None = None) -> str:
    if _as_dict(parity_row).get("fresh_signal_present") is True:
        return "fresh"
    blocker = str(action_row.get("first_blocker") or "")
    if not action_row:
        return "absent"
    if "stale" in blocker:
        return "stale"
    if blocker.startswith("fresh_") and blocker.endswith("_absent"):
        return "absent"
    if blocker in ACTION_TIME_BLOCKERS or "private_action_time_facts" in blocker:
        return "fresh"
    if action_row.get("action_time_path_ready") is True:
        return "fresh"
    return "absent"


def _scope_state(
    *,
    strategy_group_id: str,
    symbol: str,
    candidate: dict[str, Any],
    daily_row: dict[str, Any],
    tradeability_row: dict[str, Any],
    owner_pretrade_authorization: dict[str, Any],
) -> str:
    owner_authorization = _symbol_owner_authorization(
        owner_pretrade_authorization,
        strategy_group_id,
        symbol,
    )
    if (
        owner_authorization.get("pretrade_candidate_allowed") is True
        and owner_authorization.get("action_time_rehearsal_allowed") is True
        and owner_authorization.get("live_submit_allowed") == "scoped"
        and strategy_group_id in SCOPED_LIVE_SUBMIT_STRATEGIES
    ):
        return "live_submit_allowed"
    if (
        strategy_group_id == "BRF2-001"
        and owner_authorization.get("pretrade_candidate_allowed") is True
        and owner_authorization.get("action_time_rehearsal_allowed") is True
        and owner_authorization.get("live_submit_allowed")
        == "conditional_hard_gated"
    ):
        return "conditional_action_time_rehearsal_allowed"
    policy = _as_dict(tradeability_row.get("policy_scope"))
    live_symbols = (
        policy.get("live_submit_symbols")
        or policy.get("live_submit_symbol_scope")
        or _as_dict(policy.get("live_submit_scope")).get("symbols")
    )
    if isinstance(live_symbols, list) and symbol in {
        str(item) for item in live_symbols
    }:
        return "live_submit_allowed"
    canonical = _as_dict(daily_row.get("canonical_lane"))
    if canonical.get("symbol") == symbol and candidate.get("first_blocker") not in {
        "scope_not_attached",
        "policy_scope_missing",
        "runtime_profile_scope_missing",
    }:
        return "trial_scope_proposed"
    if strategy_group_id == "BRF2-001":
        return "readonly_only"
    if symbol == str(candidate.get("selected_symbol") or "") and candidate.get(
        "first_blocker"
    ) not in {"scope_not_attached", "policy_scope_missing"}:
        return "trial_scope_proposed"
    return "readonly_only"


def _risk_state(parity_row: dict[str, Any]) -> str:
    failed = {
        str(item)
        for item in parity_row.get("failed_facts", [])
        if isinstance(item, str)
    }
    if failed & {"funding_not_extreme", "spread_ok", "liquidity_ok", "squeeze_disable"}:
        return "warning"
    return "acceptable"


def _symbol_first_blocker(
    *,
    candidate: dict[str, Any],
    action_row: dict[str, Any],
    parity_row: dict[str, Any],
    detector_ready: bool,
    watcher_present: bool,
    public_facts_state: dict[str, Any],
    signal_state: str,
    scope_state: str,
    risk_state: str,
    runtime_scope_missing: bool = False,
) -> str:
    if runtime_scope_missing:
        return "runtime_profile_scope_missing"
    if not detector_ready:
        return "detector_not_attached"
    if public_facts_state["state"] == "computed_not_satisfied":
        return "computed_not_satisfied"
    if not watcher_present:
        return "watcher_tick_missing"
    if public_facts_state["state"] == "missing":
        return "artifact_missing"
    if risk_state == "disable":
        return "hard_safety_stop"
    if signal_state == "fresh" and scope_state == "readonly_only":
        return "scope_not_attached"
    if signal_state == "fresh" and scope_state in ACTION_TIME_SCOPE_STATES:
        return _fresh_action_time_blocker(action_row)
    if signal_state == "fresh":
        return "runtime_profile_scope_missing"
    return str(parity_row.get("blocker_class") or candidate.get("first_blocker") or "computed_not_satisfied")


def _fresh_action_time_blocker(action_row: dict[str, Any]) -> str:
    readiness = _as_dict(action_row.get("required_facts_readiness"))
    if action_row.get("action_time_path_ready") is not True:
        return "action_time_boundary_not_reproduced"
    if readiness.get("public_facts_ready") is not True:
        return "action_time_boundary_not_reproduced"
    if readiness.get("private_action_time_facts_ready") is not True:
        return "action_time_boundary_not_reproduced"
    if readiness.get("active_position_or_open_order_clear") is not True:
        return "active_position_resolution"
    if readiness.get("action_time_available_balance") is not True:
        return "action_time_boundary_not_reproduced"
    return "action_time_preflight_ready"


def _promotion_state(
    *,
    public_facts_state: dict[str, Any],
    signal_state: str,
    scope_state: str,
    risk_state: str,
    first_blocker: str,
    runtime_scope_missing: bool = False,
) -> str:
    if runtime_scope_missing:
        return "idle"
    if signal_state != "fresh" or public_facts_state["state"] != "satisfied":
        return "idle"
    if risk_state == "disable":
        return "blocked"
    if scope_state in ACTION_TIME_SCOPE_STATES:
        if first_blocker in ACTION_TIME_INPUT_BLOCKERS:
            return "idle"
        return "action_time_lane"
    return "promotion_candidate"


def _symbol_next_action(
    first_blocker: str,
    candidate: dict[str, Any],
    action_row: dict[str, Any] | None = None,
) -> str:
    action_next = str(_as_dict(action_row).get("next_action") or "")
    if (
        first_blocker == "action_time_preflight_ready"
        and _action_time_private_facts_ready(_as_dict(action_row))
    ):
        return "prepare_non_executing_finalgate_preflight_input"
    if (
        first_blocker == "action_time_boundary_not_reproduced"
        and action_next
        and action_next != "wait_for_fresh_signal_then_refresh_private_action_time_facts"
    ):
        return action_next
    if (
        first_blocker == "market_wait_validated"
        and action_next
        and action_next != "wait_for_fresh_signal_then_refresh_private_action_time_facts"
    ):
        return action_next
    return {
        "detector_not_attached": "attach_detector_for_candidate_symbol",
        "watcher_tick_missing": "refresh_readonly_watcher_for_candidate_symbol",
        "artifact_missing": "produce_per_symbol_readiness_evidence",
        "computed_not_satisfied": "continue_observation_with_failed_fact_matrix",
        "scope_not_attached": "produce_scoped_live_observation_or_scope_proposal",
        "runtime_profile_scope_missing": (
            "bind_or_start_pretrade_runtime_for_candidate_symbol"
        ),
        "action_time_boundary_not_reproduced": (
            "repair_non_executing_action_time_rehearsal_path"
        ),
        "action_time_preflight_ready": (
            "prepare_non_executing_finalgate_preflight_input"
        ),
        "market_wait_validated": "wait_for_fresh_signal_or_refresh_action_time_facts",
        "hard_safety_stop": "resolve_hard_safety_stop",
    }.get(first_blocker, str(candidate.get("next_engineering_action") or "reclassify_symbol_blocker"))


def _symbol_stop_condition(first_blocker: str) -> str:
    if first_blocker == "market_wait_validated":
        return "fresh signal expires or action-time lane is selected"
    if first_blocker == "action_time_preflight_ready":
        return "preflight input is prepared, stale facts appear, or lane is reclassified"
    if first_blocker == "scope_not_attached":
        return "scope proposal accepted, explicitly deferred, or symbol parked"
    return "blocker moves, repeats through stop review, or symbol exits candidate universe"


def _symbol_evidence_ref(
    *,
    strategy_group_id: str,
    symbol: str,
    first_blocker: str,
    parity_row: dict[str, Any],
    action_row: dict[str, Any],
    runtime_coverage_row: dict[str, Any] | None = None,
) -> str:
    if runtime_coverage_row and runtime_coverage_row.get("blocker_class") == first_blocker:
        return (
            "runtime_active_observation_status:candidate_universe_coverage:"
            f"{strategy_group_id}/{symbol} first_blocker={first_blocker}"
        )
    if first_blocker == "runtime_profile_scope_missing" and not runtime_coverage_row:
        return (
            "runtime_active_observation_status:candidate_universe_coverage:"
            f"{strategy_group_id}/{symbol} missing_active_watcher_scope"
        )
    if parity_row:
        evidence_source = str(parity_row.get("evidence_source") or "")
        if evidence_source:
            return (
                f"{evidence_source}:{strategy_group_id}/{symbol} "
                f"first_blocker={first_blocker}"
            )
        source_blocker = str(parity_row.get("blocker_class") or "")
        source_detail = (
            f" source_blocker_class={source_blocker}"
            if source_blocker != first_blocker
            else ""
        )
        return (
            "output/runtime-monitor/latest-replay-live-parity-audit.json:"
            f"{strategy_group_id}/{symbol} first_blocker={first_blocker}"
            f"{source_detail} watcher_tick_present={parity_row.get('watcher_tick_present')}"
        )
    if action_row:
        return (
            "output/runtime-monitor/latest-strategy-fresh-signal-action-time-boundary.json:"
            f"{strategy_group_id}/{symbol} first_blocker={action_row.get('first_blocker')}"
        )
    return f"default_candidate_universe:{strategy_group_id}/{symbol}"


def _runtime_coverage(runtime_active_monitor: dict[str, Any]) -> dict[str, Any]:
    coverage = runtime_active_monitor.get("candidate_universe_coverage")
    if isinstance(coverage, dict):
        return coverage
    latest = runtime_active_monitor.get("latest_summary")
    if isinstance(latest, dict):
        coverage = latest.get("candidate_universe_coverage")
        if isinstance(coverage, dict):
            return coverage
    return {}


def _server_runtime_scope_ready(runtime_coverage_row: dict[str, Any]) -> bool:
    active_ids = runtime_coverage_row.get("active_runtime_instance_ids") or []
    selected_ids = runtime_coverage_row.get("selected_runtime_instance_ids") or []
    return (
        str(runtime_coverage_row.get("state") or "") == "active_watcher_scope"
        and bool(active_ids)
        and bool(selected_ids)
    )


def _candidate_role(strategy_group_id: str, symbol: str) -> str:
    if symbol == PRIMARY_SYMBOLS.get(strategy_group_id):
        return "primary"
    if strategy_group_id == "BRF2-001":
        return "conditional"
    return "secondary"


def _symbol_role(strategy_group_id: str, symbol: str) -> int:
    return 0 if symbol == PRIMARY_SYMBOLS.get(strategy_group_id) else 1


def _action_time_lane_input(row: dict[str, Any]) -> dict[str, Any]:
    server_runtime_coverage = _as_dict(row.get("server_runtime_coverage"))
    return {
        "strategy_group_id": row["strategy_group_id"],
        "symbol": row["symbol"],
        "side": row["side"],
        "active_runtime_instance_ids": list(
            server_runtime_coverage.get("active_runtime_instance_ids") or []
        ),
        "selected_runtime_instance_ids": list(
            server_runtime_coverage.get("selected_runtime_instance_ids") or []
        ),
        "server_runtime_coverage": server_runtime_coverage,
        "runtime_profile": "selected_profile_required_at_action_time",
        "scope_state": row["scope_state"],
        "owner_authorization": row["owner_authorization"],
        "first_blocker": row["first_blocker"],
        "next_action": row["next_action"],
        "signal_state": row["signal_state"],
        "public_facts_state": row["public_facts_state"],
        "risk_state": row["risk_state"],
        "action_time": row["action_time"],
        "authority_boundary": (
            "action_time_lane_input_is_non_executing; "
            "no_finalgate_no_operation_layer_no_exchange_write"
        ),
    }


def _select_action_time_row(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None
    return sorted(
        rows,
        key=lambda row: (
            _strategy_priority(str(row.get("strategy_group_id") or "")),
            str(row.get("symbol") or ""),
        ),
    )[0]


def _arbitration(
    *,
    promotion_candidates: list[dict[str, Any]],
    eligible_action_time_rows: list[dict[str, Any]],
    selected_action_time_row: dict[str, Any] | None,
) -> dict[str, Any]:
    selected = ""
    deferred: list[dict[str, str]] = []
    if selected_action_time_row:
        sorted_inputs = [selected_action_time_row]
        selected = (
            f"{sorted_inputs[0]['strategy_group_id']}:{sorted_inputs[0]['symbol']}:"
            f"{sorted_inputs[0]['side']}"
        )
    for row in eligible_action_time_rows:
        if row is selected_action_time_row:
            continue
        deferred.append(
            {
                "strategy_group_id": str(row.get("strategy_group_id") or ""),
                "symbol": str(row.get("symbol") or ""),
                "side": str(row.get("side") or ""),
                "reason": "deferred_by_single_action_time_candidate_rule",
            }
        )
    return {
        "promotion_candidate_count": len(promotion_candidates),
        "eligible_action_time_candidate_count": len(eligible_action_time_rows),
        "action_time_lane_input_count": 1 if selected_action_time_row else 0,
        "selected_action_time_candidate": selected or "none",
        "deferred_action_time_candidates": deferred,
        "single_real_submit_candidate": True,
        "rule": (
            "multiple promotion candidates may exist; real submit path may select "
            "at most one action-time candidate"
        ),
    }


def _strategy_priority(strategy_group_id: str) -> int:
    return {strategy_group_id: index for index, strategy_group_id in enumerate(WIP_LANES)}.get(
        strategy_group_id, 99
    )


def _no_trade_audit(
    *,
    symbol_readiness_rows: list[dict[str, Any]],
    action_time_lane_inputs: list[dict[str, Any]],
    arbitration: dict[str, Any],
) -> dict[str, Any]:
    blocker_counts: dict[str, int] = {}
    for row in symbol_readiness_rows:
        blocker = str(row.get("first_blocker") or "unknown")
        blocker_counts[blocker] = blocker_counts.get(blocker, 0) + 1
    return {
        "status": (
            "action_time_candidate_present"
            if action_time_lane_inputs
            else "no_action_time_candidate"
        ),
        "reason": (
            "one_or_more_live_scope_candidates_can_enter_action_time"
            if action_time_lane_inputs
            else "candidate_pool_has_no_live_submit_allowed_fresh_satisfied_symbol"
        ),
        "blocker_counts": blocker_counts,
        "selected_action_time_candidate": arbitration["selected_action_time_candidate"],
    }


def _residual_deploy_blockers(candidate_rows: list[dict[str, Any]]) -> list[str]:
    residual: list[str] = []
    for row in candidate_rows:
        strategy_group_id = str(row.get("strategy_group_id") or "")
        first_blocker = str(row.get("first_blocker") or "")
        if first_blocker in RESIDUAL_DEPLOY_BLOCKERS:
            residual.append(f"{strategy_group_id}:{first_blocker}")
        readiness_status = str(
            _as_dict(row.get("action_time_readiness")).get("status") or ""
        )
        if readiness_status in ACTION_TIME_BLOCKED_STATUSES:
            residual.append(f"{strategy_group_id}:action_time:{readiness_status}")
    return residual


def _candidate_universe(
    symbol_readiness_rows: list[dict[str, Any]],
) -> dict[str, list[str]]:
    universe: dict[str, list[str]] = {}
    for row in symbol_readiness_rows:
        universe.setdefault(row["strategy_group_id"], []).append(row["symbol"])
    return {key: sorted(set(values)) for key, values in universe.items()}


def _candidate_row(
    *,
    strategy_group_id: str,
    daily_row: dict[str, Any],
    tradeability_row: dict[str, Any],
    action_row: dict[str, Any],
) -> dict[str, Any]:
    first_blocker = str(daily_row.get("first_blocker") or "artifact_missing")
    selected_symbol = str(daily_row.get("symbol") or "strategy_scope")
    return {
        "strategy_group_id": strategy_group_id,
        "candidate_status": _candidate_status(strategy_group_id, first_blocker),
        "candidate_positioning": CANDIDATE_POSITIONING.get(
            strategy_group_id, "live candidate"
        ),
        "selected_symbol": selected_symbol,
        "side": str(daily_row.get("side") or "unknown"),
        "stage": str(daily_row.get("stage") or "unknown"),
        "daily_rank": int(daily_row.get("closest_to_live_rank") or 0),
        "first_blocker": first_blocker,
        "blocker_owner": str(
            tradeability_row.get("blocker_owner")
            or _blocker_owner(first_blocker)
        ),
        "evidence": str(daily_row.get("first_blocker_evidence") or ""),
        "next_engineering_action": str(
            daily_row.get("next_engineering_action") or ""
        ),
        "trigger_condition": _trigger_condition(strategy_group_id, selected_symbol),
        "market_condition": _market_condition(strategy_group_id, first_blocker),
        "action_time_readiness": _action_time_readiness(action_row),
        "stop_condition": str(daily_row.get("stop_condition") or ""),
        "exit_condition": _exit_condition(strategy_group_id, first_blocker),
        "owner_action_required": str(daily_row.get("owner_action_required") or "no"),
        "authority_boundary": DAILY_AUTHORITY_BOUNDARY,
    }


def _sync_candidate_rows_with_symbol_readiness(
    candidate_rows: list[dict[str, Any]],
    symbol_readiness_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_strategy: dict[str, list[dict[str, Any]]] = {}
    for row in symbol_readiness_rows:
        by_strategy.setdefault(str(row.get("strategy_group_id") or ""), []).append(row)

    synced: list[dict[str, Any]] = []
    for candidate in candidate_rows:
        strategy_group_id = str(candidate.get("strategy_group_id") or "")
        summary = _strategy_summary_symbol_row(
            strategy_group_id,
            by_strategy.get(strategy_group_id, []),
        )
        if not summary or not _server_runtime_scope_ready(
            _as_dict(summary.get("server_runtime_coverage"))
        ):
            synced.append(candidate)
            continue
        first_blocker = str(summary.get("first_blocker") or candidate["first_blocker"])
        selected_symbol = str(summary.get("symbol") or candidate["selected_symbol"])
        updated = dict(candidate)
        updated.update(
            {
                "candidate_status": _candidate_status(strategy_group_id, first_blocker),
                "selected_symbol": selected_symbol,
                "side": str(summary.get("side") or candidate["side"]),
                "first_blocker": first_blocker,
                "blocker_owner": _blocker_owner(first_blocker),
                "evidence": str(summary.get("evidence_ref") or candidate["evidence"]),
                "next_engineering_action": str(
                    summary.get("next_action")
                    or candidate["next_engineering_action"]
                ),
                "trigger_condition": _trigger_condition(
                    strategy_group_id,
                    selected_symbol,
                ),
                "market_condition": _market_condition(strategy_group_id, first_blocker),
                "action_time_readiness": summary.get("action_time")
                or candidate["action_time_readiness"],
                "stop_condition": str(
                    summary.get("stop_condition") or candidate["stop_condition"]
                ),
                "exit_condition": _exit_condition(strategy_group_id, first_blocker),
            }
        )
        synced.append(updated)
    return synced


def _strategy_summary_symbol_row(
    strategy_group_id: str,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    if not rows:
        return {}
    promotion_priority = {
        "action_time_lane": 0,
        "promotion_candidate": 1,
        "blocked": 2,
        "idle": 3,
    }
    return sorted(
        rows,
        key=lambda row: (
            promotion_priority.get(str(row.get("promotion_state") or ""), 9),
            _symbol_role(strategy_group_id, str(row.get("symbol") or "")),
            str(row.get("symbol") or ""),
        ),
    )[0]


def _candidate_status(strategy_group_id: str, first_blocker: str) -> str:
    if strategy_group_id == "BRF2-001" and first_blocker == "computed_not_satisfied":
        return "candidate_conditional_observation"
    return {
        "watcher_tick_missing": "candidate_runtime_input_blocked",
        "scope_not_attached": "candidate_scope_decision_pending",
        "computed_not_satisfied": "candidate_market_condition_wait",
        "market_wait_validated": "candidate_market_wait_validated",
        "action_time_preflight_ready": "candidate_action_time_preflight_ready",
        "policy_scope_missing": "candidate_owner_policy_pending",
        "hard_safety_stop": "candidate_safety_blocked",
    }.get(first_blocker, "candidate_engineering_blocked")


def _blocker_owner(first_blocker: str) -> str:
    if first_blocker in {"computed_not_satisfied", "market_wait_validated"}:
        return "market"
    if first_blocker == "action_time_preflight_ready":
        return "engineering"
    if first_blocker == "policy_scope_missing":
        return "owner"
    if first_blocker == "hard_safety_stop":
        return "safety"
    if first_blocker == "watcher_tick_missing":
        return "runtime"
    return "engineering"


def _trigger_condition(strategy_group_id: str, symbol: str) -> str:
    return {
        "MPG-001": f"{symbol} selective leader continuation signal with fresh public facts",
        "CPM-RO-001": f"{symbol} pullback reclaim signal with htf_trend_intact and reclaim_confirmed",
        "MI-001": f"{symbol} relative strength admission and scoped observation lane accepted",
        "SOR-001": f"{symbol} session opening range plus breakout and follow-through confirmation",
        "BRF2-001": "failed-rebound short setup after squeeze / strong-uptrend disable clears",
    }.get(strategy_group_id, "fresh eligible signal under selected StrategyGroup rules")


def _market_condition(strategy_group_id: str, first_blocker: str) -> str:
    if first_blocker == "watcher_tick_missing":
        return "public market facts must refresh before market condition can be trusted"
    if strategy_group_id == "BRF2-001":
        return "conditional short only when bullish/squeeze disable state clears"
    if first_blocker == "computed_not_satisfied":
        return "strategy fact matrix must clear on the next detector tick"
    if first_blocker == "scope_not_attached":
        return "market condition is secondary until scope/admission is attached"
    return "selected lane must satisfy its fresh eligible signal contract"


def _action_time_readiness(action_row: dict[str, Any]) -> dict[str, Any]:
    if not action_row:
        return {
            "status": "not_applicable_current_stage",
            "action_time_path_ready": False,
            "public_facts_ready": False,
            "private_action_time_facts_ready": False,
        }
    readiness = _as_dict(action_row.get("required_facts_readiness"))
    path_ready = action_row.get("action_time_path_ready") is True
    public_ready = readiness.get("public_facts_ready") is True
    private_ready = _action_time_private_facts_ready(action_row)
    if not public_ready:
        status = "blocked_public_facts"
    elif path_ready and private_ready:
        status = "ready_for_finalgate_preflight"
    elif path_ready:
        status = "ready_for_private_action_time_facts"
    else:
        status = "blocked_action_time_rehearsal"
    return {
        "status": status,
        "action_time_path_ready": path_ready,
        "public_facts_ready": public_ready,
        "private_action_time_facts_ready": private_ready,
        "first_blocker": str(action_row.get("first_blocker") or ""),
        "next_action": str(action_row.get("next_action") or ""),
    }


def _action_time_private_facts_ready(action_row: dict[str, Any]) -> bool:
    readiness = _as_dict(action_row.get("required_facts_readiness"))
    return (
        readiness.get("private_action_time_facts_ready") is True
        and readiness.get("active_position_or_open_order_clear") is True
        and readiness.get("action_time_available_balance") is True
    )


def _exit_condition(strategy_group_id: str, first_blocker: str) -> str:
    if strategy_group_id == "BRF2-001":
        return "exit mainline if bullish/squeeze disable remains active through the stop review window"
    if first_blocker == "scope_not_attached":
        return "exit or support-only if scoped admission is rejected"
    if first_blocker == "computed_not_satisfied":
        return "exit if repeated detector windows keep failing the same fact matrix"
    if first_blocker == "watcher_tick_missing":
        return "exit or downgrade if public facts cannot be refreshed through approved read-only paths"
    return "exit under WIP stop rule if blocker does not move"


def _p0_p1_review(
    candidate_rows: list[dict[str, Any]],
    source_validation: dict[str, Any],
) -> list[dict[str, Any]]:
    by_strategy = {row["strategy_group_id"]: row for row in candidate_rows}
    result: list[dict[str, Any]] = []
    for priority, item in P0_P1_ITEMS:
        status, evidence, next_action = _p0_p1_status(item, by_strategy, source_validation)
        result.append(
            {
                "priority": priority,
                "item": item,
                "status": status,
                "evidence": evidence,
                "next_action": next_action,
            }
        )
    return result


def _p0_p1_status(
    item: str,
    by_strategy: dict[str, dict[str, Any]],
    source_validation: dict[str, Any],
) -> tuple[str, str, str]:
    if item == "five_strategy_candidate_pool_control_surface":
        complete = len(by_strategy) == len(WIP_LANES) and all(
            _candidate_row_complete(row) for row in by_strategy.values()
        )
        return (
            "cleared" if complete else "open",
            "candidate_rows contain required fields for all active WIP lanes",
            "complete missing candidate fields",
        )
    if item == "mpg_watcher_closure":
        row = by_strategy.get("MPG-001", {})
        blocker = row.get("first_blocker")
        return (
            "open"
            if blocker in {"watcher_tick_missing", "scope_not_attached"}
            else "cleared",
            f"MPG-001 first_blocker={blocker}",
            row.get("next_engineering_action") or "refresh MPG public facts",
        )
    if item == "sor_watcher_closure":
        row = by_strategy.get("SOR-001", {})
        blocker = row.get("first_blocker")
        return (
            "open"
            if blocker in {"watcher_tick_missing", "scope_not_attached"}
            else "cleared",
            f"SOR-001 first_blocker={blocker}",
            row.get("next_engineering_action") or "refresh SOR public facts",
        )
    if item == "mi_scope_closure":
        row = by_strategy.get("MI-001", {})
        blocker = row.get("first_blocker")
        return (
            "open"
            if blocker in {"scope_not_attached", "policy_scope_missing"}
            else "cleared",
            f"MI-001 first_blocker={blocker}",
            row.get("next_engineering_action") or "close MI scope/admission",
        )
    if item == "cpm_computed_refresh":
        row = by_strategy.get("CPM-RO-001", {})
        blocker = row.get("first_blocker")
        return (
            "cleared"
            if blocker
            in {
                "computed_not_satisfied",
                "market_wait_validated",
                "action_time_boundary_not_reproduced",
            }
            else "open",
            f"CPM-RO-001 first_blocker={blocker}",
            row.get("next_engineering_action") or "refresh CPM detector facts",
        )
    if item == "brf2_conditionalization":
        row = by_strategy.get("BRF2-001", {})
        return (
            "cleared"
            if row.get("candidate_status") == "candidate_conditional_observation"
            else "open",
            f"BRF2-001 candidate_status={row.get('candidate_status')}",
            "keep BRF2 conditional or exit under stop review",
        )
    if item == "no_authority_leakage":
        return ("cleared", "candidate pool is non-executing", "preserve authority boundary")
    if item == "candidate_pool_validator":
        return ("cleared", "validator script is present and must pass", "run validator")
    if item == "output_whitelist_gate":
        return (
            "cleared",
            "deploy gate reruns validate_output_artifact_scope.py --git-status",
            "run validate_output_artifact_scope.py --git-status",
        )
    if item == "no_stale_facts":
        watcher_missing = [
            row["strategy_group_id"]
            for row in by_strategy.values()
            if row.get("first_blocker") == "watcher_tick_missing"
        ]
        blocked_public = [
            row["strategy_group_id"]
            for row in by_strategy.values()
            if _as_dict(row.get("action_time_readiness")).get("status")
            == "blocked_public_facts"
        ]
        if watcher_missing:
            return (
                "open",
                "watcher_tick_missing rows prove public facts are not current: "
                + ",".join(sorted(watcher_missing)),
                "refresh approved public facts path",
            )
        if blocked_public:
            return (
                "waived_with_reason",
                "non-executing deploy may proceed, but action-time public facts "
                "are not cleared for: "
                + ",".join(sorted(blocked_public)),
                "refresh action-time public facts before treating lane as market_wait_validated",
            )
        return (
            "cleared",
            "watcher and action-time public facts are current or not applicable",
            "refresh approved public facts path",
        )
    if item == "review_report":
        return (
            "cleared",
            "candidate pool includes machine-readable p0_p1_review rows",
            "rerun candidate pool after blocker refresh",
        )
    if item == "postdeploy_validation_script":
        deploy_gate = REPO_ROOT / "scripts/validate_strategy_live_candidate_pool_deploy_gate.py"
        return (
            "cleared" if deploy_gate.exists() else "open",
            "deploy gate validator checks candidate pool, Daily Table, Single Lane Packet, "
            "monitor sequence, output scope, and authority leakage",
            "run validate_strategy_live_candidate_pool_deploy_gate.py before deploy",
        )
    return ("open", "unknown review item", "classify review item")


def _candidate_row_complete(row: dict[str, Any]) -> bool:
    required = (
        "candidate_status",
        "selected_symbol",
        "side",
        "first_blocker",
        "blocker_owner",
        "evidence",
        "next_engineering_action",
        "trigger_condition",
        "market_condition",
        "action_time_readiness",
        "stop_condition",
        "exit_condition",
    )
    return all(str(row.get(key) or "") for key in required)


def _source_validation(
    *,
    daily_table: dict[str, Any],
    tradeability: dict[str, Any],
    replay_live_parity: dict[str, Any],
    action_time_boundary: dict[str, Any],
    single_lane_task_packet: dict[str, Any],
) -> dict[str, Any]:
    _ = single_lane_task_packet
    sources = {
        "daily_table": daily_table.get("status") == "daily_live_enablement_table_ready"
        and _as_dict(daily_table.get("source_validation")).get("valid") is True,
        "tradeability": tradeability.get("status") == "tradeability_decision_ready",
        "replay_live_parity": replay_live_parity.get("status")
        == "replay_live_parity_audit_ready",
        "action_time_boundary": action_time_boundary.get("status")
        == "strategy_fresh_signal_action_time_boundary_ready",
    }
    return {
        "valid": all(sources.values()),
        "sources": sources,
    }


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _markdown(artifact: dict[str, Any], output_json: Path) -> str:
    lines = [
        "## Strategy Live Candidate Pool",
        "",
        f"- Status: `{artifact['status']}`",
        f"- Candidate count: `{artifact['summary']['candidate_count']}`",
        f"- Symbol readiness rows: `{artifact['summary']['symbol_readiness_count']}`",
        f"- Fresh promotion candidates: `{artifact['summary']['fresh_candidate_count']}`",
        f"- Top action-time candidate: `{artifact['summary']['top_action_time_candidate']}`",
        f"- P0 cleared: `{artifact['summary']['p0_cleared']}`",
        f"- P1 cleared or waived: `{artifact['summary']['p1_cleared_or_waived']}`",
        f"- Deploy ready: `{artifact['summary']['deploy_ready']}`",
        f"- Output JSON: `{output_json}`",
        "",
        "| StrategyGroup | Symbol | Status | First blocker | Next action |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in artifact["candidate_rows"]:
        lines.append(
            "| {strategy_group_id} | {selected_symbol} | {candidate_status} | "
            "{first_blocker} | {next_engineering_action} |".format(**row)
        )
    lines.extend(
        [
            "",
            "## Per-Symbol Readiness",
            "",
            "| StrategyGroup | Symbol | Facts | Signal | Scope | Promotion | First blocker |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in artifact["symbol_readiness_rows"]:
        facts = _as_dict(row.get("public_facts_state")).get("state", "unknown")
        lines.append(
            "| {strategy_group_id} | {symbol} | {facts} | {signal_state} | "
            "{scope_state} | {promotion_state} | {first_blocker} |".format(
                facts=facts,
                **row,
            )
        )
    return "\n".join(lines) + "\n"


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


if __name__ == "__main__":
    raise SystemExit(main())
