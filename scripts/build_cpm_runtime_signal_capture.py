#!/usr/bin/env python3
"""Build CPM runtime signal capture read model."""

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


DEFAULT_REQUIRED_FACTS_MAPPING_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-cpm-required-facts-mapping.json"
)
DEFAULT_FACT_INPUT_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-cpm-runtime-signal-facts.json"
)
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-cpm-runtime-signal-capture.json"
)
DEFAULT_OUTPUT_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-cpm-runtime-signal-capture.md"
)

SCHEMA = "brc.cpm_runtime_signal_capture.v1"
STRATEGY_GROUP_ID = "CPM-RO-001"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--required-facts-mapping-json",
        default=str(DEFAULT_REQUIRED_FACTS_MAPPING_JSON),
    )
    parser.add_argument("--fact-input-json", default=str(DEFAULT_FACT_INPUT_JSON))
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-owner-progress", default=str(DEFAULT_OUTPUT_MD))
    args = parser.parse_args(argv)

    artifact = build_cpm_runtime_signal_capture(
        required_facts_mapping=_read_optional_json(
            Path(args.required_facts_mapping_json)
        ),
        fact_input=_read_optional_json(Path(args.fact_input_json)),
    )
    output_json = Path(args.output_json)
    output_md = Path(args.output_owner_progress)
    _write_json(output_json, artifact)
    _write_text(output_md, _markdown(artifact, output_json))
    print(
        json.dumps(
            {
                "status": artifact["status"],
                "strategy_group_id": artifact["strategy_group_id"],
                "signal_state": artifact["signal_detector_preview"][
                    "current_signal_state"
                ],
                "first_blocker": artifact["signal_detector_preview"][
                    "first_blocker_class"
                ],
                "output_json": str(output_json),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if artifact["status"] == "cpm_runtime_signal_capture_ready" else 2


def build_cpm_runtime_signal_capture(
    *,
    required_facts_mapping: dict[str, Any],
    fact_input: dict[str, Any],
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    mapping_ready = (
        required_facts_mapping.get("status") == "cpm_required_facts_mapping_ready"
        and required_facts_mapping.get("required_facts_mapping_ready") is True
    )
    facts = _as_dict(fact_input.get("facts"))
    required_specs = [
        _as_dict(row)
        for row in required_facts_mapping.get("required_fact_observation_specs") or []
    ]
    disable_specs = [
        _as_dict(row)
        for row in required_facts_mapping.get("disable_fact_observation_specs") or []
    ]
    required_status = [_required_status(row, facts) for row in required_specs]
    disable_status = [_disable_status(row, facts) for row in disable_specs]
    action_time_keys = {
        "active_position_or_open_order_clear",
        "action_time_available_balance",
    }
    missing_required = [
        row["fact_key"]
        for row in required_status
        if row["state"] != "satisfied" and row["fact_key"] not in action_time_keys
    ]
    action_time_pending = [
        row["fact_key"]
        for row in required_status
        if row["fact_key"] in action_time_keys
    ]
    active_disable = [
        row["fact_key"] for row in disable_status if row["state"] == "disable_active"
    ]
    fresh_signal_present = mapping_ready and not missing_required and not active_disable
    if not mapping_ready:
        state = "mapping_not_ready"
        blocker = "cpm_required_facts_mapping_gap"
        owner = "engineering"
        checkpoint = "close_cpm_required_facts_mapping"
    elif active_disable:
        state = "blocked_by_disable_fact"
        blocker = active_disable[0]
        owner = "market"
        checkpoint = "continue_cpm_armed_observation_until_disable_clears"
    elif fresh_signal_present:
        state = "fresh_signal_present"
        blocker = "cpm_candidate_authorization_evidence_not_created"
        owner = "runtime"
        checkpoint = "prepare_cpm_shadow_candidate_authorization_evidence"
    else:
        state = "fresh_signal_absent"
        blocker = "fresh_cpm_long_signal_absent"
        owner = "market"
        checkpoint = "continue_cpm_long_armed_observation_until_reclaim_signal"
    return {
        "schema": SCHEMA,
        "scope": "cpm_runtime_signal_capture_read_model",
        "status": (
            "cpm_runtime_signal_capture_ready"
            if mapping_ready
            else "cpm_runtime_signal_capture_blocked"
        ),
        "generated_at_utc": generated_at_utc
        or datetime.now(timezone.utc).isoformat(),
        "strategy_group_id": STRATEGY_GROUP_ID,
        "path_id": "CPM-LONG",
        "fact_input_status": str(fact_input.get("status") or "missing"),
        "fact_input_present": fact_input.get("fact_input_present") is True,
        "watcher_tick_present": fact_input.get("watcher_tick_present") is True,
        "watcher_scope": {
            "strategy_group_id": STRATEGY_GROUP_ID,
            "signal_id": "cpm_long_pullback_reclaim_signal_v1",
            "symbol_scope": ["ETHUSDT", "SOLUSDT", "AVAXUSDT", "SUIUSDT"],
            "primary_live_submit_symbol_scope": ["ETHUSDT"],
            "expanded_readonly_symbol_scope": ["SOLUSDT", "AVAXUSDT", "SUIUSDT"],
            "side_scope": ["long"],
            "timeframes": ["15m", "1h", "4h"],
            "cadence": "5-15m near reclaim; 15-30m otherwise",
            "source_mode": "runtime_watcher_read_only_fact_input",
            "live_submit_scope_boundary": (
                "read-only expanded watcher symbols cannot submit until action-time "
                "Binance USD-M facts and official runtime gates pass"
            ),
        },
        "fact_authority": str(fact_input.get("fact_authority") or ""),
        "fact_authority_boundary": _as_dict(fact_input.get("fact_authority_boundary")),
        "signal_detector_preview": {
            "detector_ready": mapping_ready,
            "fact_input_present": fact_input.get("fact_input_present") is True,
            "watcher_tick_present": fact_input.get("watcher_tick_present") is True,
            "fresh_signal_present": fresh_signal_present,
            "current_signal_state": state,
            "first_blocker_class": blocker,
            "first_blocker_owner": owner,
            "signal_capture_checkpoint": checkpoint,
            "required_fact_status": required_status,
            "disable_fact_status": disable_status,
            "missing_required_fact_keys": missing_required,
            "action_time_pending_fact_keys": action_time_pending,
            "active_disable_fact_keys": active_disable,
        },
        "shadow_candidate_shape": {
            "shadow_candidate_ready": fresh_signal_present,
            "shadow_candidate_type": "cpm_non_executing_long_signal_candidate_evidence",
            "strategy_group_id": STRATEGY_GROUP_ID,
            "side": "long",
            "signal_id": "cpm_long_pullback_reclaim_signal_v1",
        },
        "checks": {
            "mapping_ready": mapping_ready,
            "watcher_scope_ready": mapping_ready,
            "expanded_watcher_scope_ready": mapping_ready,
            "primary_live_submit_symbol_scope_unchanged": True,
            "fresh_signal_present": fresh_signal_present,
            "missing_required_fact_count": len(missing_required),
            "action_time_pending_fact_count": len(action_time_pending),
            "active_disable_fact_count": len(active_disable),
        },
        "interaction": non_executing_interaction("L0_local_cpm_runtime_signal_capture"),
        "safety_invariants": non_executing_safety_invariants(
            tuple(), include_authority_mirrors=False
        ),
    }


def _required_status(spec: dict[str, Any], facts: dict[str, Any]) -> dict[str, Any]:
    key = str(spec.get("fact_key") or "")
    fact = _as_dict(facts.get(key))
    raw = str(fact.get("status") or fact.get("state") or "")
    accepted = {str(value).lower() for value in spec.get("accepted_statuses") or []}
    if key in {"active_position_or_open_order_clear", "action_time_available_balance"}:
        state = "action_time_required"
    elif fact and raw.lower() in accepted and fact.get("fresh") is not False:
        state = "satisfied"
    else:
        state = "not_satisfied"
    return {
        "fact_key": key,
        "state": state,
        "raw_state": raw,
        "fresh": fact.get("fresh") is not False if fact else False,
    }


def _disable_status(spec: dict[str, Any], facts: dict[str, Any]) -> dict[str, Any]:
    key = str(spec.get("fact_key") or "")
    fact = _as_dict(facts.get(key))
    raw = str(fact.get("status") or fact.get("state") or "")
    active = {str(value).lower() for value in spec.get("active_statuses") or []}
    state = "disable_active" if raw.lower() in active else "clear"
    return {
        "fact_key": key,
        "state": state,
        "raw_state": raw,
        "fresh": fact.get("fresh") is not False if fact else False,
    }


def _markdown(artifact: dict[str, Any], output_json: Path) -> str:
    preview = artifact["signal_detector_preview"]
    return "\n".join(
        [
            "## CPM Runtime Signal Capture",
            "",
            f"- Status: `{artifact['status']}`",
            f"- Signal state: `{preview['current_signal_state']}`",
            f"- First blocker: `{preview['first_blocker_class']}` / `{preview['first_blocker_owner']}`",
            f"- Watcher scope ready: `{_yes_no(artifact['checks']['watcher_scope_ready'])}`",
            f"- Output JSON: `{output_json}`",
        ]
    ) + "\n"


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
