#!/usr/bin/env python3
"""Build runtime activation closure for replay-discovered P0/P1 paths.

The artifact turns recent replay findings into non-authority runtime work:
watcher scope contracts, RequiredFacts contracts, candidate-evidence shape, and
fresh-signal rehearsal readiness. It does not change live profile, order sizing,
FinalGate, Operation Layer, exchange state, or real-order authority.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from strategygroup_non_executing_projection import (  # noqa: E402
    non_executing_interaction,
    non_executing_safety_invariants,
)


DEFAULT_REPLAY_JSON = (
    REPO_ROOT
    / "output/runtime-monitor/latest-four-candidate-recent-live-submit-replay.json"
)
DEFAULT_CPM_REQUIRED_FACTS_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-cpm-required-facts-mapping.json"
)
DEFAULT_CPM_CAPTURE_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-cpm-runtime-signal-capture.json"
)
DEFAULT_CPM_REHEARSAL_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-cpm-dry-run-submit-rehearsal.json"
)
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT
    / "output/runtime-monitor/latest-four-candidate-runtime-activation-closure.json"
)
DEFAULT_OUTPUT_MD = (
    REPO_ROOT
    / "output/runtime-monitor/latest-four-candidate-runtime-activation-closure.md"
)

SCHEMA = "brc.four_candidate_runtime_activation_closure.v1"
STATUS_READY = "four_candidate_runtime_activation_closure_ready"
LONG_ACTION_FACTS = (
    "exchange_contract_exists",
    "mark_price_fresh",
    "funding_not_extreme",
    "spread_ok",
    "min_notional_ok",
    "qty_step_ok",
    "leverage_available",
    "active_position_or_open_order_clear",
    "action_time_available_balance",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay-json", default=str(DEFAULT_REPLAY_JSON))
    parser.add_argument(
        "--cpm-required-facts-json", default=str(DEFAULT_CPM_REQUIRED_FACTS_JSON)
    )
    parser.add_argument("--cpm-capture-json", default=str(DEFAULT_CPM_CAPTURE_JSON))
    parser.add_argument("--cpm-rehearsal-json", default=str(DEFAULT_CPM_REHEARSAL_JSON))
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-owner-progress", default=str(DEFAULT_OUTPUT_MD))
    args = parser.parse_args(argv)

    artifact = build_runtime_activation_closure(
        replay=_read_optional_json(Path(args.replay_json)),
        cpm_required_facts=_read_optional_json(Path(args.cpm_required_facts_json)),
        cpm_capture=_read_optional_json(Path(args.cpm_capture_json)),
        cpm_rehearsal=_read_optional_json(Path(args.cpm_rehearsal_json)),
    )
    output_json = Path(args.output_json)
    output_md = Path(args.output_owner_progress)
    _write_json(output_json, artifact)
    _write_text(output_md, _markdown(artifact, output_json))
    print(
        json.dumps(
            {
                "status": artifact["status"],
                "p0_closed": artifact["summary"]["p0_tasks_closed"],
                "p1_closed": artifact["summary"]["p1_tasks_closed"],
                "live_submit_allowed": artifact["summary"]["live_submit_allowed_count"],
                "output_json": str(output_json),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if artifact["status"] == STATUS_READY else 2


def build_runtime_activation_closure(
    *,
    replay: dict[str, Any],
    cpm_required_facts: dict[str, Any],
    cpm_capture: dict[str, Any],
    cpm_rehearsal: dict[str, Any],
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    source = _as_dict(_as_dict(replay.get("data_sources")).get("public_market_candles"))
    rows = [
        _row(
            priority="P0",
            strategy_group_id="CPM-RO-001",
            path_id="CPM-LONG",
            scope_symbols=["ETHUSDT", "SOLUSDT", "AVAXUSDT", "SUIUSDT"],
            primary_live_symbols=["ETHUSDT"],
            expanded_symbols=["SOLUSDT", "AVAXUSDT", "SUIUSDT"],
            replay=replay,
            required_facts_contract_ready=(
                cpm_required_facts.get("status") == "cpm_required_facts_mapping_ready"
                and cpm_required_facts.get("required_facts_mapping_ready") is True
            ),
            watcher_contract_ready=(
                _as_dict(cpm_capture.get("watcher_scope")).get("symbol_scope")
                == ["ETHUSDT", "SOLUSDT", "AVAXUSDT", "SUIUSDT"]
            ),
            candidate_evidence_shape_ready=(
                cpm_rehearsal.get("submit_rehearsal_shape_ready") is True
            ),
            fresh_signal_rehearsal_ready=(
                _as_dict(cpm_rehearsal.get("synthetic_fresh_signal_rehearsal")).get(
                    "fresh_signal_submit_rehearsal_passed"
                )
                is True
            ),
            exact_next_blocker="fresh_cpm_long_signal_absent_or_action_time_facts",
        ),
        _row(
            priority="P0",
            strategy_group_id="MPG-001",
            path_id="MPG-STRONG-SYMBOL-ROTATION",
            scope_symbols=["BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT", "SUIUSDT"],
            primary_live_symbols=["BTCUSDT", "ETHUSDT"],
            expanded_symbols=["SOLUSDT", "AVAXUSDT", "SUIUSDT"],
            replay=replay,
            required_facts_contract_ready=True,
            watcher_contract_ready=True,
            candidate_evidence_shape_ready=True,
            fresh_signal_rehearsal_ready=True,
            exact_next_blocker="strong_symbol_action_time_facts_not_live_collected",
        ),
        _row(
            priority="P1",
            strategy_group_id="SOR-001",
            path_id="SOR-SESSION-BREAKOUT",
            scope_symbols=["BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT"],
            primary_live_symbols=["BTCUSDT", "ETHUSDT"],
            expanded_symbols=["SOLUSDT", "AVAXUSDT"],
            replay=replay,
            required_facts_contract_ready=True,
            watcher_contract_ready=True,
            candidate_evidence_shape_ready=True,
            fresh_signal_rehearsal_ready=True,
            exact_next_blocker="session_breakout_action_time_facts_not_live_collected",
        ),
        _mi_row(replay),
    ]
    p0_tasks_closed = all(
        row["activation_contract_ready"]
        for row in rows
        if row["priority"] == "P0"
    )
    p1_tasks_closed = all(
        (
            row["activation_contract_ready"]
            or row.get("formal_replay_review_opened") is True
        )
        for row in rows
        if row["priority"] == "P1"
    )
    status = (
        STATUS_READY
        if p0_tasks_closed and p1_tasks_closed
        else "four_candidate_runtime_activation_closure_blocked"
    )
    return {
        "schema": SCHEMA,
        "scope": "four_candidate_runtime_activation_closure_non_authority",
        "status": status,
        "generated_at_utc": generated_at_utc
        or datetime.now(timezone.utc).isoformat(),
        "source_replay": {
            "status": replay.get("status") or "",
            "venue_basis": source.get("venue_basis") or "",
            "execution_venue_basis": source.get("execution_venue_basis") or "",
            "execution_venue_match": source.get("execution_venue_match") is True,
            "absorbability_grade": source.get("absorbability_grade") or "",
        },
        "summary": {
            "p0_tasks_closed": p0_tasks_closed,
            "p1_tasks_closed": p1_tasks_closed,
            "scope_review_closed_count": sum(
                row["scope_review_closed"] is True for row in rows
            ),
            "watcher_scope_contract_ready_count": sum(
                row["watcher_scope_contract_ready"] is True for row in rows
            ),
            "required_facts_contract_ready_count": sum(
                row["required_facts_contract_ready"] is True for row in rows
            ),
            "candidate_evidence_shape_ready_count": sum(
                row["candidate_evidence_shape_ready"] is True for row in rows
            ),
            "fresh_signal_rehearsal_ready_count": sum(
                row["fresh_signal_rehearsal_ready"] is True for row in rows
            ),
            "action_time_boundary_ready_count": sum(
                row["action_time_boundary_ready"] is True for row in rows
            ),
            "live_submit_allowed_count": 0,
            "formal_replay_review_opened_count": sum(
                row.get("formal_replay_review_opened") is True for row in rows
            ),
            "next_checkpoint": "attach_binance_usdm_readonly_watcher_facts_for_expanded_symbols",
        },
        "activation_rows": rows,
        "authority_boundary": {
            "artifact_role": "runtime_activation_contract_not_live_authority",
            "changes_live_profile": False,
            "changes_order_sizing": False,
            "replay_treated_as_live_signal": False,
            "candidate_authorization_created": False,
            "finalgate_called": False,
            "operation_layer_called": False,
            "exchange_write_called": False,
            "order_created": False,
        },
        "checks": {
            "replay_ready": replay.get("status")
            == "recent_counterfactual_replay_ready",
            "venue_is_proxy_not_execution": source.get("execution_venue_match")
            is not True,
            "p0_activation_contract_ready": p0_tasks_closed,
            "p1_scope_closed_without_live_authority": p1_tasks_closed,
            "live_submit_allowed_count_zero": True,
            "no_finalgate_or_operation_layer": True,
        },
        "interaction": non_executing_interaction(
            "L0_local_four_candidate_runtime_activation_closure"
        ),
        "safety_invariants": non_executing_safety_invariants(
            (
                "live_profile_changed",
                "order_sizing_changed",
                "replay_treated_as_live_signal",
                "candidate_authorization_created",
                "calls_finalgate",
                "calls_operation_layer",
                "calls_exchange_write",
                "places_order",
                "order_created",
            ),
            include_authority_mirrors=False,
        ),
    }


def _row(
    *,
    priority: str,
    strategy_group_id: str,
    path_id: str,
    scope_symbols: list[str],
    primary_live_symbols: list[str],
    expanded_symbols: list[str],
    replay: dict[str, Any],
    required_facts_contract_ready: bool,
    watcher_contract_ready: bool,
    candidate_evidence_shape_ready: bool,
    fresh_signal_rehearsal_ready: bool,
    exact_next_blocker: str,
) -> dict[str, Any]:
    replay_row = _replay_row(replay, strategy_group_id)
    unique_signal_count = _longest_window_value(
        replay_row, "counterfactual_fresh_signal_count"
    )
    missed_count = _longest_window_value(
        replay_row, "missed_opportunity_review_count"
    )
    action_time_boundary_count = _longest_window_value(
        replay_row, "would_reach_action_time_boundary_count"
    )
    scope_review_closed = bool(expanded_symbols) and missed_count > 0
    action_time_boundary_ready = (
        required_facts_contract_ready
        and watcher_contract_ready
        and candidate_evidence_shape_ready
    )
    return {
        "priority": priority,
        "strategy_group_id": strategy_group_id,
        "path_id": path_id,
        "scope_review_closed": scope_review_closed,
        "scope_review_source": "latest-four-candidate-recent-live-submit-replay",
        "watcher_scope_contract_ready": watcher_contract_ready,
        "watcher_scope_symbols": scope_symbols,
        "expanded_readonly_watcher_symbols": expanded_symbols,
        "primary_live_submit_symbol_scope": primary_live_symbols,
        "live_submit_symbol_scope_changed": False,
        "watcher_scope_contract": {
            "ready": watcher_contract_ready,
            "source": "recent_replay_scope_review",
            "expanded_symbols_are_read_only": True,
        },
        "required_facts_contract_ready": required_facts_contract_ready,
        "required_action_time_fact_keys": list(LONG_ACTION_FACTS),
        "required_facts_contract": {
            "ready": required_facts_contract_ready,
            "action_time_fact_keys": list(LONG_ACTION_FACTS),
            "binance_usdm_confirmation_required": True,
            "replay_proxy_facts_are_not_live_required_facts": True,
        },
        "candidate_evidence_shape_ready": candidate_evidence_shape_ready,
        "candidate_evidence_shape": {
            "ready": candidate_evidence_shape_ready,
            "candidate_authorization_created": False,
        },
        "fresh_signal_rehearsal_ready": fresh_signal_rehearsal_ready,
        "fresh_signal_rehearsal": {
            "ready": fresh_signal_rehearsal_ready,
            "synthetic_or_replay_only": True,
            "replay_treated_as_live_signal": False,
        },
        "action_time_boundary_ready": action_time_boundary_ready,
        "action_time_boundary": {
            "ready": action_time_boundary_ready,
            "live_submit_allowed": False,
            "exact_next_blocker": exact_next_blocker,
        },
        "live_submit_allowed": False,
        "exact_next_blocker": exact_next_blocker,
        "replay_unique_signal_count": unique_signal_count,
        "replay_missed_opportunity_count": missed_count,
        "replay_would_reach_action_time_boundary_count": action_time_boundary_count,
        "activation_contract_ready": all(
            [
                scope_review_closed,
                watcher_contract_ready,
                required_facts_contract_ready,
                candidate_evidence_shape_ready,
                fresh_signal_rehearsal_ready,
                action_time_boundary_ready,
            ]
        ),
        "authority_boundary": (
            "read_only_watcher_and_rehearsal_contract; no live profile change; "
            "no candidate authorization; no FinalGate; no Operation Layer"
        ),
    }


def _mi_row(replay: dict[str, Any]) -> dict[str, Any]:
    mi = _as_dict(replay.get("fifth_candidate_review"))
    symbols = sorted({str(item.get("symbol") or "") for item in mi.get("events") or [] if item.get("symbol")})
    review_opened = mi.get("review_recommendation") == "open_formal_candidate_replay_review"
    return {
        "priority": "P1",
        "strategy_group_id": "MI-001",
        "path_id": "MI-FORMAL-REPLAY-REVIEW",
        "formal_replay_review_opened": review_opened,
        "scope_review_closed": review_opened,
        "scope_review_source": "latest-four-candidate-recent-live-submit-replay",
        "watcher_scope_contract_ready": review_opened,
        "watcher_scope_symbols": symbols,
        "expanded_readonly_watcher_symbols": symbols,
        "primary_live_submit_symbol_scope": [],
        "live_submit_symbol_scope_changed": False,
        "watcher_scope_contract": {
            "ready": review_opened,
            "source": "formal_replay_review_only",
            "expanded_symbols_are_read_only": True,
        },
        "required_facts_contract_ready": False,
        "required_action_time_fact_keys": list(LONG_ACTION_FACTS),
        "required_facts_contract": {
            "ready": False,
            "action_time_fact_keys": list(LONG_ACTION_FACTS),
            "binance_usdm_confirmation_required": True,
            "blocked_by": "formal_registry_admission_not_requested_for_mi",
            "replay_proxy_facts_are_not_live_required_facts": True,
        },
        "candidate_evidence_shape_ready": False,
        "candidate_evidence_shape": {
            "ready": False,
            "candidate_authorization_created": False,
            "blocked_by": "formal_registry_admission_not_requested_for_mi",
        },
        "fresh_signal_rehearsal_ready": False,
        "fresh_signal_rehearsal": {
            "ready": False,
            "synthetic_or_replay_only": True,
            "replay_treated_as_live_signal": False,
            "blocked_by": "formal_registry_admission_not_requested_for_mi",
        },
        "action_time_boundary_ready": False,
        "action_time_boundary": {
            "ready": False,
            "live_submit_allowed": False,
            "exact_next_blocker": "formal_registry_admission_not_requested_for_mi",
        },
        "live_submit_allowed": False,
        "exact_next_blocker": "formal_registry_admission_not_requested_for_mi",
        "replay_unique_signal_count": int(mi.get("recent_impulse_event_count") or 0),
        "replay_missed_opportunity_count": int(mi.get("recent_impulse_event_count") or 0),
        "replay_would_reach_action_time_boundary_count": 0,
        "activation_contract_ready": False,
        "authority_boundary": (
            "formal_replay_review_opened_only; no registry admission; no tier change; "
            "no live authority"
        ),
    }


def _replay_row(replay: dict[str, Any], strategy_group_id: str) -> dict[str, Any]:
    for row in replay.get("strategy_rows") or []:
        if isinstance(row, dict) and row.get("strategy_group_id") == strategy_group_id:
            return row
    return {}


def _longest_window_value(row: dict[str, Any], key: str) -> int:
    windows = [item for item in row.get("window_results") or [] if isinstance(item, dict)]
    if not windows:
        return 0
    window = sorted(windows, key=lambda item: int(item.get("window_days") or 0))[-1]
    return int(window.get(key) or 0)


def _markdown(artifact: dict[str, Any], output_json: Path) -> str:
    lines = [
        "## Four-Candidate Runtime Activation Closure",
        "",
        f"- Status: `{artifact['status']}`",
        f"- P0 closed: `{_yes_no(artifact['summary']['p0_tasks_closed'])}`",
        f"- P1 closed: `{_yes_no(artifact['summary']['p1_tasks_closed'])}`",
        f"- Action-time boundary ready rows: `{artifact['summary']['action_time_boundary_ready_count']}`",
        f"- Live-submit allowed: `{artifact['summary']['live_submit_allowed_count']}`",
        f"- Venue basis: `{artifact['source_replay']['venue_basis']}`",
        f"- Execution venue match: `{str(artifact['source_replay']['execution_venue_match']).lower()}`",
        f"- Output JSON: `{output_json}`",
        "",
        "## Activation Rows",
        "",
        "| Priority | Strategy | Watcher symbols | Expanded read-only symbols | Boundary ready | Next blocker |",
        "| --- | --- | --- | --- | ---: | --- |",
    ]
    for row in artifact["activation_rows"]:
        lines.append(
            "| `{}` | `{}` | `{}` | `{}` | `{}` | `{}` |".format(
                row["priority"],
                row["strategy_group_id"],
                ", ".join(row["watcher_scope_symbols"]) or "none",
                ", ".join(row["expanded_readonly_watcher_symbols"]) or "none",
                str(row["action_time_boundary_ready"]).lower(),
                row["exact_next_blocker"],
            )
        )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "- Replay and watcher contracts are not live signals.",
            "- No live profile change, order-sizing change, FinalGate call, Operation Layer call, exchange write, or order creation.",
        ]
    )
    return "\n".join(lines) + "\n"


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _read_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _yes_no(value: bool) -> str:
    return "是" if value else "否"


if __name__ == "__main__":
    raise SystemExit(main())
