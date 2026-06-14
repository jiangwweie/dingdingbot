#!/usr/bin/env python3
"""Build a main-control intake packet from StrategyGroup handoff packs.

The builder is intentionally read-only. It reads research-window handoff JSON
files and emits a main-control packet for Strategy Picker, RequiredFacts
readiness, watcher scope, and armed-observation review. It never registers a
runtime, creates candidates, calls exchange APIs, mutates PG, or authorizes
execution.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HANDOFF_DIR = PROJECT_ROOT / "docs/current/strategy-group-handoffs"
DEFAULT_SOURCE_REPO = str(PROJECT_ROOT)
DEFAULT_SOURCE_BRANCH = "codex/strategygroup-runtime-pilot"
DEFAULT_SOURCE_COMMIT = "repo-local-current-pilot-handoff"

REQUIRED_FIELDS = {
    "strategy_group_id",
    "version",
    "supported_symbols",
    "supported_sides",
    "signal_ready_rule",
    "required_facts",
    "risk_defaults",
    "hard_stops",
    "sample_signal_packet",
    "sample_no_signal_packet",
    "sample_stale_signal_packet",
    "sample_conflict_packet",
}
SUPPLEMENT_FILES = {
    "admission_priority": "main-control-admission-priority.md",
    "required_facts_map": "main-control-required-facts-map.md",
    "conflict_policy": "main-control-conflict-policy.md",
    "watcher_cadence": "main-control-watcher-cadence.md",
    "handoff_index": "main-control-handoff-index.md",
    "task_card": "main-control-task-card.md",
}
WATCHER_CADENCE = {
    "MPG-001": {
        "watcher_poll_cadence": "5-15m",
        "business_signal_validity": "15-30m",
        "candidate_packet_freshness_seconds": 120,
    },
    "FBS-001": {
        "watcher_poll_cadence": "5-15m",
        "business_signal_validity": "15-30m",
        "candidate_packet_freshness_seconds": 120,
    },
    "TEQ-001": {
        "watcher_poll_cadence": "5-15m",
        "business_signal_validity": "15-30m",
        "candidate_packet_freshness_seconds": 120,
    },
    "PMR-001": {
        "watcher_poll_cadence": "15-60m",
        "business_signal_validity": "30-60m",
        "candidate_packet_freshness_seconds": 120,
    },
    "SOR-001": {
        "watcher_poll_cadence": "5m near session window; 15-60m outside",
        "business_signal_validity": "5-15m near trigger",
        "candidate_packet_freshness_seconds": 120,
    },
}
ADMISSION_RANK = {
    "MPG-001": 1,
    "TEQ-001": 2,
    "FBS-001": 3,
    "SOR-001": 4,
    "PMR-001": 5,
}
DEFAULT_BADGES = {
    "MPG-001": "first_batch",
    "TEQ-001": "equity_like_perp",
    "FBS-001": "high_facts_threshold",
    "PMR-001": "overlay_role_split",
    "SOR-001": "session_window",
}
OBSERVE_ONLY_GROUPS = {"PMR-001"}
CONDITIONAL_GROUPS = {"SOR-001"}
HIGH_FACT_THRESHOLD_GROUPS = {"FBS-001"}
UNSAFE_FLAGS = {
    "exchange_write_called",
    "order_created",
    "order_lifecycle_called",
    "execution_intent_created",
    "runtime_budget_mutated",
    "withdrawal_or_transfer_created",
}


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


def _sample_status(data: dict[str, Any], key: str) -> str:
    packet = data.get(key)
    if isinstance(packet, dict):
        return str(packet.get("status") or "unknown")
    return "missing"


def _fact_rows(strategy_group_id: str, required_facts: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not isinstance(required_facts, dict):
        return rows
    for category, facts in required_facts.items():
        if not isinstance(facts, list):
            continue
        for fact in facts:
            rows.append(
                {
                    "strategy_group_id": strategy_group_id,
                    "category": str(category),
                    "fact_key": str(fact),
                    "readiness_source": _source_for_fact_category(str(category)),
                    "current_status": "requires_main_control_fact_validation",
                    "missing_behavior": _missing_behavior(str(category), str(fact)),
                }
            )
    return rows


def _source_for_fact_category(category: str) -> str:
    return {
        "account": "account_position_open_order_read_model",
        "exchange": "exchange_symbol_rules_cache",
        "market": "market_data_or_derivatives_fact_source",
        "derivatives": "derivatives_fact_source",
        "risk": "main_control_risk_and_protection_planner",
        "strategy": "strategy_group_evaluator",
    }.get(category, "main_control_fact_source")


def _missing_behavior(category: str, fact_key: str) -> str:
    if category in {"account", "exchange"}:
        return "block_candidate_prepare"
    if "protection" in fact_key or "exit" in fact_key:
        return "block_candidate_prepare"
    if "funding" in fact_key or "mark" in fact_key:
        return "block_armed_observation_for_perps"
    if "session" in fact_key:
        return "block_or_observe_only_by_strategy"
    return "requires_main_control_readiness_review"


def _group_row(path: Path, data: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    strategy_group_id = str(data.get("strategy_group_id") or path.parent.name)
    missing = sorted(REQUIRED_FIELDS.difference(data))
    mode = data.get("mode_recommendation") if isinstance(data.get("mode_recommendation"), dict) else {}
    default_mode = str(mode.get("default") or "unknown")
    supported_symbols = data.get("supported_symbols") if isinstance(data.get("supported_symbols"), list) else []
    supported_sides = data.get("supported_sides") if isinstance(data.get("supported_sides"), list) else []
    risk_defaults = data.get("risk_defaults") if isinstance(data.get("risk_defaults"), dict) else {}
    fact_rows = _fact_rows(strategy_group_id, data.get("required_facts"))
    fact_categories = sorted({row["category"] for row in fact_rows})
    if missing:
        intake_status = "blocked_handoff_incomplete"
    elif strategy_group_id in OBSERVE_ONLY_GROUPS or default_mode == "observe_only":
        intake_status = "observe_only_intake_ready"
    elif strategy_group_id in CONDITIONAL_GROUPS:
        intake_status = "conditional_armed_observation_intake_ready"
    else:
        intake_status = "armed_observation_intake_ready"
    blockers = [f"missing_field:{field}" for field in missing]
    warnings: list[str] = []
    if strategy_group_id in HIGH_FACT_THRESHOLD_GROUPS:
        warnings.append("high_facts_threshold_required")
    if strategy_group_id in OBSERVE_ONLY_GROUPS:
        warnings.append("observe_only_until_role_session_mark_readiness")
    if strategy_group_id in CONDITIONAL_GROUPS:
        warnings.append("session_window_branch_selection_required")

    row = {
        "strategy_group_id": strategy_group_id,
        "version": str(data.get("version") or "unknown"),
        "name": str(data.get("name") or strategy_group_id),
        "source_path": str(path),
        "intake_status": intake_status,
        "picker": {
            "show": not missing,
            "rank": ADMISSION_RANK.get(strategy_group_id, 999),
            "default_mode": default_mode,
            "badge": DEFAULT_BADGES.get(strategy_group_id, "experimental"),
        },
        "supported_symbols": [str(item) for item in supported_symbols],
        "supported_symbol_count": len(supported_symbols),
        "supported_sides": [str(item) for item in supported_sides],
        "risk_defaults": risk_defaults,
        "required_fact_categories": fact_categories,
        "required_fact_count": len(fact_rows),
        "watcher_scope": WATCHER_CADENCE.get(
            strategy_group_id,
            {
                "watcher_poll_cadence": "manual_review",
                "business_signal_validity": "manual_review",
                "candidate_packet_freshness_seconds": 120,
            },
        ),
        "sample_statuses": {
            "signal": _sample_status(data, "sample_signal_packet"),
            "no_signal": _sample_status(data, "sample_no_signal_packet"),
            "stale_signal": _sample_status(data, "sample_stale_signal_packet"),
            "conflict": _sample_status(data, "sample_conflict_packet"),
        },
        "hard_stop_count": len(data.get("hard_stops") or []),
        "blockers": blockers,
        "warnings": warnings,
        "execution_boundary": {
            "research_handoff_only": True,
            "runtime_registration_authorized": False,
            "candidate_creation_authorized": False,
            "final_gate_input": False,
            "operation_layer_input": False,
            "real_submit_authorized": False,
        },
    }
    return row, fact_rows, blockers


def build_packet(
    *,
    handoff_dir: Path,
    source_repo: str = DEFAULT_SOURCE_REPO,
    source_branch: str = DEFAULT_SOURCE_BRANCH,
    source_commit: str = DEFAULT_SOURCE_COMMIT,
    require_supplements: bool = False,
) -> dict[str, Any]:
    generated_at_ms = int(time.time() * 1000)
    handoff_dir = handoff_dir.expanduser()
    handoff_paths = sorted(handoff_dir.glob("*/handoff.json"))
    supplements = {
        name: {
            "path": str(handoff_dir / filename),
            "present": (handoff_dir / filename).exists(),
        }
        for name, filename in SUPPLEMENT_FILES.items()
    }
    groups: list[dict[str, Any]] = []
    required_fact_matrix: list[dict[str, Any]] = []
    blockers: list[str] = []
    warnings: list[str] = []
    for path in handoff_paths:
        row, fact_rows, row_blockers = _group_row(path, _read_json(path))
        groups.append(row)
        required_fact_matrix.extend(fact_rows)
        blockers.extend([f"{row['strategy_group_id']}:{item}" for item in row_blockers])

    missing_supplements = [
        name for name, status in supplements.items() if not status["present"]
    ]
    missing_supplement_codes = [
        f"supplement_missing:{name}" for name in missing_supplements
    ]
    if require_supplements:
        blockers.extend(missing_supplement_codes)
    else:
        warnings.extend(missing_supplement_codes)
    if not handoff_paths:
        blockers.append("handoff_json_missing")
    groups.sort(key=lambda item: (item["picker"]["rank"], item["strategy_group_id"]))
    armed_ready = [
        item["strategy_group_id"]
        for item in groups
        if item["intake_status"] in {
            "armed_observation_intake_ready",
            "conditional_armed_observation_intake_ready",
        }
    ]
    observe_only = [
        item["strategy_group_id"]
        for item in groups
        if item["intake_status"] == "observe_only_intake_ready"
    ]
    status = "blocked_handoff_intake" if blockers else "ready_for_main_control_intake"
    return {
        "scope": "strategy_group_handoff_main_control_intake",
        "status": status,
        "generated_at_ms": generated_at_ms,
        "source_anchor": {
            "repo": source_repo,
            "branch": source_branch,
            "commit": source_commit,
            "handoff_dir": str(handoff_dir),
        },
        "counts": {
            "strategy_groups": len(groups),
            "armed_observation_intake_ready": len(armed_ready),
            "observe_only_intake_ready": len(observe_only),
            "required_fact_rows": len(required_fact_matrix),
            "supplements_present": sum(1 for value in supplements.values() if value["present"]),
            "supplements_expected": len(SUPPLEMENT_FILES),
        },
        "strategy_picker": groups,
        "required_facts_matrix": required_fact_matrix,
        "watcher_scope": [
            {
                "strategy_group_id": item["strategy_group_id"],
                **item["watcher_scope"],
                "default_mode": item["picker"]["default_mode"],
                "intake_status": item["intake_status"],
            }
            for item in groups
        ],
        "supplements": supplements,
        "next_main_control_steps": [
            "record strategy handoff intake",
            "validate exchange symbol rules for supported symbols",
            "build RequiredFacts readiness from trusted runtime facts",
            "wire watcher scope without runtime registration",
            "prepare shadow candidate only after fresh signal and fact pass",
        ],
        "hard_stops_before_real_submit": [
            "missing exchange symbol rules",
            "active same-symbol position or open order",
            "stale market or derivatives facts",
            "missing protection plan",
            "signal conflict",
            "FinalGate failure",
            "Operation Layer bypass",
        ],
        "safety_invariants": {
            **{name: False for name in sorted(UNSAFE_FLAGS)},
            "reads_research_handoff_only": True,
            "registers_runtime": False,
            "creates_candidate": False,
            "authorizes_execution": False,
            "places_order": False,
            "mutates_pg": False,
        },
        "blockers": sorted(set(blockers)),
        "warnings": sorted(set(warnings)),
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a main-control StrategyGroup handoff intake packet.",
    )
    parser.add_argument("--handoff-dir", default=str(DEFAULT_HANDOFF_DIR))
    parser.add_argument("--source-repo", default=DEFAULT_SOURCE_REPO)
    parser.add_argument("--source-branch", default=DEFAULT_SOURCE_BRANCH)
    parser.add_argument("--source-commit", default=DEFAULT_SOURCE_COMMIT)
    parser.add_argument(
        "--require-supplements",
        action="store_true",
        help="Treat missing main-control supplement markdown files as blockers.",
    )
    parser.add_argument("--output-json", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    packet = build_packet(
        handoff_dir=Path(args.handoff_dir),
        source_repo=args.source_repo,
        source_branch=args.source_branch,
        source_commit=args.source_commit,
        require_supplements=args.require_supplements,
    )
    _write_json(Path(args.output_json).expanduser(), packet)
    print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if packet["status"] == "ready_for_main_control_intake" else 2


if __name__ == "__main__":
    raise SystemExit(main())
