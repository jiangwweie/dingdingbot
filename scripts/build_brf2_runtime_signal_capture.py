#!/usr/bin/env python3
"""Build BRF2 runtime signal capture read model.

This artifact attaches the BRF2 RequiredFacts mapping to a watcher-facing
signal-capture contract. It is non-executing: it does not fetch exchange data,
call FinalGate, call Operation Layer, create candidates, create orders, mutate
runtime profile, or change sizing.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_REQUIRED_FACTS_MAPPING_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-brf2-required-facts-mapping.json"
)
DEFAULT_OWNER_POLICY_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-brf2-owner-trial-policy-scope.json"
)
DEFAULT_FACT_INPUT_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-brf2-runtime-signal-facts.json"
)
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-brf2-runtime-signal-capture.json"
)
DEFAULT_OUTPUT_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-brf2-runtime-signal-capture.md"
)

SCHEMA = "brc.brf2_runtime_signal_capture.v1"

ACCEPTED_FACT_STATES = {
    "closed_1h_ohlcv": {"ready", "present", "fresh"},
    "closed_5m_ohlcv": {"ready", "present", "fresh"},
    "rally_context": {"bear_or_weak_reclaim", "weak_rally", "ready"},
    "rally_failure_trigger_state": {"confirmed", "ready", "active"},
    "short_squeeze_risk_state": {"clear", "bounded", "clear_or_bounded"},
    "strong_reclaim_disable_state": {"false", "clear", "inactive"},
    "liquidity_downshift_state": {"false", "clear", "inactive"},
    "spread_liquidity_state": {"acceptable", "ready", "normal"},
}

DISABLE_ACTIVE_STATES = {
    "short_squeeze_risk_state": {"red", "unbounded", "unknown"},
    "strong_reclaim_disable_state": {"true", "active"},
    "rally_extension_invalidates_failure_state": {"true", "active"},
    "liquidity_downshift_state": {"true", "active"},
    "spread_liquidity_state": {"missing", "wide_spread", "thin_volume", "unknown"},
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--required-facts-mapping-json",
        default=str(DEFAULT_REQUIRED_FACTS_MAPPING_JSON),
    )
    parser.add_argument("--owner-policy-json", default=str(DEFAULT_OWNER_POLICY_JSON))
    parser.add_argument("--fact-input-json", default=str(DEFAULT_FACT_INPUT_JSON))
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-owner-progress", default=str(DEFAULT_OUTPUT_MD))
    args = parser.parse_args(argv)

    packet = build_brf2_runtime_signal_capture(
        required_facts_mapping=_read_optional_json(
            Path(args.required_facts_mapping_json)
        ),
        owner_policy=_read_optional_json(Path(args.owner_policy_json)),
        fact_input=_read_optional_json(Path(args.fact_input_json)),
    )
    output_json = Path(args.output_json)
    output_md = Path(args.output_owner_progress)
    _write_json(output_json, packet)
    _write_text(output_md, _markdown(packet, output_json))
    print(
        json.dumps(
            {
                "status": packet["status"],
                "strategy_group_id": packet["strategy_group_id"],
                "signal_state": packet["signal_detector_preview"][
                    "current_signal_state"
                ],
                "fact_input_present": packet["fact_input_present"],
                "watcher_tick_present": packet["watcher_tick_present"],
                "fresh_signal_present": packet["signal_detector_preview"][
                    "fresh_signal_present"
                ],
                "candidate_packet_ready": packet["candidate_packet_shape"][
                    "candidate_packet_ready"
                ],
                "output_json": str(output_json),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if packet["status"] == "brf2_runtime_signal_capture_ready" else 2


def build_brf2_runtime_signal_capture(
    *,
    required_facts_mapping: dict[str, Any],
    owner_policy: dict[str, Any] | None = None,
    fact_input: dict[str, Any] | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    fact_input = fact_input or {}
    mapping_ready = (
        required_facts_mapping.get("status") == "brf2_required_facts_mapping_ready"
        and required_facts_mapping.get("required_facts_mapping_ready") is True
    )
    facts = _facts_by_key(fact_input)
    fact_input_status = str(fact_input.get("status") or "missing")
    fact_input_present = _fact_input_present(fact_input, facts)
    watcher_tick_present = fact_input.get("watcher_tick_present") is True
    required_fact_keys = [
        str(item)
        for item in required_facts_mapping.get("required_fact_keys") or []
        if str(item)
    ]
    disable_fact_keys = [
        str(item)
        for item in required_facts_mapping.get("disable_fact_keys") or []
        if str(item)
    ]
    required_status = [
        _fact_status(fact_key, facts.get(fact_key), required=True)
        for fact_key in required_fact_keys
    ]
    disable_status = [
        _fact_status(fact_key, facts.get(fact_key), required=False)
        for fact_key in disable_fact_keys
    ]
    missing_required = [
        row["fact_key"]
        for row in required_status
        if row["state"] in {"missing", "stale", "not_satisfied"}
    ]
    active_disable = [
        row["fact_key"] for row in disable_status if row["state"] == "disable_active"
    ]
    detector_ready = mapping_ready and bool(required_fact_keys)
    fresh_signal_present = (
        detector_ready
        and fact_input_present
        and not missing_required
        and not active_disable
    )
    current_signal_state = (
        "fresh_signal_present"
        if fresh_signal_present
        else "fact_input_missing"
        if detector_ready and not fact_input_present
        else "blocked_by_disable_fact"
        if active_disable
        else "fresh_signal_absent"
        if detector_ready
        else "mapping_not_ready"
    )
    first_blocker = _first_blocker(
        detector_ready=detector_ready,
        fact_input_present=fact_input_present,
        missing_required=missing_required,
        active_disable=active_disable,
    )
    policy = _as_dict((owner_policy or {}).get("policy"))
    fresh_signal_rule = _as_dict(required_facts_mapping.get("fresh_signal_rule"))
    source_signal_context = _signal_context(fact_input or {})
    return {
        "schema": SCHEMA,
        "scope": "brf2_runtime_signal_capture_read_model",
        "status": (
            "brf2_runtime_signal_capture_ready"
            if detector_ready
            else "brf2_runtime_signal_capture_blocked"
        ),
        "generated_at_utc": generated_at_utc
        or datetime.now(timezone.utc).isoformat(),
        "strategy_group_id": "BRF2-001",
        "fact_input_status": fact_input_status,
        "fact_input_present": fact_input_present,
        "watcher_tick_present": watcher_tick_present,
        "watcher_scope": {
            "strategy_group_id": "BRF2-001",
            "signal_id": str(fresh_signal_rule.get("signal_id") or ""),
            "symbol_scope": policy.get(
                "symbol_scope",
                "brf2_research_supported_symbols_only",
            ),
            "side_scope": ["short"],
            "timeframes": fresh_signal_rule.get("timeframes") or [],
            "freshness_window_ms": fresh_signal_rule.get("freshness_window_ms"),
            "source_mode": "runtime_watcher_read_only_fact_input",
        },
        "source_signal_context": source_signal_context,
        "signal_detector_preview": {
            "detector_ready": detector_ready,
            "fact_input_present": fact_input_present,
            "watcher_tick_present": watcher_tick_present,
            "fact_input_status": fact_input_status,
            "fresh_signal_present": fresh_signal_present,
            "current_signal_state": current_signal_state,
            "first_blocker_class": first_blocker["class"],
            "first_blocker_owner": first_blocker["owner"],
            "next_action": first_blocker["next_action"],
            "required_fact_status": required_status,
            "disable_fact_status": disable_status,
            "missing_required_fact_keys": missing_required,
            "active_disable_fact_keys": active_disable,
        },
        "no_action_attribution": {
            "attribution_ready": detector_ready,
            "strategy_group_id": "BRF2-001",
            "reason": first_blocker["class"],
            "missing_required_fact_keys": missing_required,
            "active_disable_fact_keys": active_disable,
            "blocked_fact_count": len(missing_required) + len(active_disable),
            "blocker_owner": first_blocker["owner"],
        },
        "candidate_packet_shape": {
            "candidate_packet_ready": fresh_signal_present,
            "candidate_packet_type": "brf2_non_executing_short_signal_candidate",
            "strategy_group_id": "BRF2-001",
            "side": "short",
            "signal_id": str(fresh_signal_rule.get("signal_id") or ""),
            "would_bind_required_facts": required_fact_keys,
            "would_bind_disable_facts": disable_fact_keys,
            "required_next_chain": [
                "live_watcher_signal_packet_id",
                "required_facts_readiness_packet_id",
                "candidate_authorization_evidence",
                "action_time_finalgate_packet_id",
                "operation_layer_submit_authorization_id",
            ],
            "forbidden_until_action_time": [
                "actionable_now",
                "real_order_authority",
                "finalgate_call",
                "operation_layer_call",
                "exchange_write",
                "order_creation",
            ],
        },
        "checks": {
            "mapping_ready": mapping_ready,
            "fact_input_present": fact_input_present,
            "watcher_tick_present": watcher_tick_present,
            "fact_input_status_ready": fact_input_status
            == "brf2_runtime_signal_facts_ready",
            "watcher_scope_ready": detector_ready,
            "signal_detector_preview_ready": detector_ready,
            "no_action_attribution_ready": detector_ready,
            "candidate_packet_shape_ready": detector_ready,
            "fresh_signal_present": fresh_signal_present,
            "missing_required_fact_count": len(missing_required),
            "active_disable_fact_count": len(active_disable),
            "actionable_now": False,
            "real_order_authority": False,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
        },
        "interaction": _interaction(),
        "safety_invariants": _safety_invariants(),
    }


def _fact_status(
    fact_key: str,
    fact: dict[str, Any] | None,
    *,
    required: bool,
) -> dict[str, Any]:
    if not fact:
        return {
            "fact_key": fact_key,
            "state": "missing",
            "raw_state": "",
            "fresh": False,
        }
    raw_state = _normalized_state(fact)
    fresh = fact.get("fresh") is not False and fact.get("stale") is not True
    if not fresh:
        state = "stale"
    elif required:
        state = (
            "satisfied"
            if raw_state in ACCEPTED_FACT_STATES.get(fact_key, {"ready"})
            else "not_satisfied"
        )
    else:
        state = (
            "disable_active"
            if raw_state in DISABLE_ACTIVE_STATES.get(fact_key, set())
            else "clear"
        )
    return {
        "fact_key": fact_key,
        "state": state,
        "raw_state": raw_state,
        "fresh": fresh,
    }


def _normalized_state(fact: dict[str, Any]) -> str:
    for key in ("state", "status", "value", "classification", "signal_state"):
        if key in fact:
            value = fact.get(key)
            if isinstance(value, bool):
                return str(value).lower()
            return str(value or "").strip().lower()
    return "ready" if fact.get("ready") is True else ""


def _facts_by_key(packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    facts = packet.get("facts", packet)
    if isinstance(facts, dict):
        return {str(key): _as_dict(value) for key, value in facts.items()}
    if isinstance(facts, list):
        rows: dict[str, dict[str, Any]] = {}
        for row in facts:
            item = _as_dict(row)
            fact_key = str(item.get("fact_key") or item.get("key") or "")
            if fact_key:
                rows[fact_key] = item
        return rows
    return {}


def _fact_input_present(
    packet: dict[str, Any],
    facts: dict[str, dict[str, Any]],
) -> bool:
    if packet.get("status") == "brf2_runtime_signal_facts_missing_watcher_input":
        return False
    if packet.get("fact_input_present") is False:
        return False
    return packet.get("fact_input_present") is True or bool(facts)


def _signal_context(packet: dict[str, Any]) -> dict[str, Any]:
    context = _as_dict(packet.get("signal_context"))
    if not context:
        context = {
            key: packet.get(key)
            for key in (
                "signal_packet_id",
                "runtime_instance_id",
                "symbol",
                "exchange_symbol",
                "market",
                "timeframe",
                "closed_at_utc",
                "source",
            )
            if packet.get(key) not in {None, ""}
        }
    return {
        "signal_packet_id": str(context.get("signal_packet_id") or ""),
        "runtime_instance_id": str(context.get("runtime_instance_id") or ""),
        "symbol": str(context.get("symbol") or ""),
        "exchange_symbol": str(context.get("exchange_symbol") or ""),
        "market": str(context.get("market") or ""),
        "timeframe": str(context.get("timeframe") or ""),
        "closed_at_utc": str(context.get("closed_at_utc") or ""),
        "source": str(context.get("source") or "runtime_watcher_read_only_fact_input"),
    }


def _first_blocker(
    *,
    detector_ready: bool,
    fact_input_present: bool,
    missing_required: list[str],
    active_disable: list[str],
) -> dict[str, str]:
    if not detector_ready:
        return {
            "class": "brf2_required_facts_mapping_not_ready",
            "owner": "engineering",
            "next_action": "build_brf2_required_facts_mapping",
        }
    if not fact_input_present:
        return {
            "class": "brf2_watcher_fact_input_missing",
            "owner": "engineering",
            "next_action": "attach_brf2_watcher_fact_input_producer",
        }
    if active_disable:
        return {
            "class": f"{active_disable[0]}_disable_active",
            "owner": "market",
            "next_action": "continue_brf2_armed_observation_until_disable_clears",
        }
    if missing_required:
        return {
            "class": "fresh_brf2_short_signal_absent",
            "owner": "market",
            "next_action": "continue_brf2_armed_observation_until_fresh_signal",
        }
    return {
        "class": "brf2_fresh_short_signal_present_non_executing",
        "owner": "runtime",
        "next_action": "build_brf2_non_executing_candidate_packet",
    }


def _markdown(packet: dict[str, Any], output_json: Path) -> str:
    preview = packet["signal_detector_preview"]
    lines = [
        "## BRF2 Runtime Signal Capture",
        "",
        f"- Status: `{packet['status']}`",
        f"- Generated: `{packet['generated_at_utc']}`",
        f"- Output JSON: `{output_json}`",
        f"- StrategyGroup: `{packet['strategy_group_id']}`",
        f"- Fact input present: `{_yes_no(packet.get('fact_input_present') is True)}`",
        f"- Watcher tick present: `{_yes_no(packet.get('watcher_tick_present') is True)}`",
        f"- Signal state: `{preview['current_signal_state']}`",
        f"- First blocker: `{preview['first_blocker_class']}`",
        f"- Candidate packet ready: `{_yes_no(packet['candidate_packet_shape']['candidate_packet_ready'])}`",
        f"- Actionable now: `{_yes_no(False)}`",
        f"- Real order authority: `{_yes_no(False)}`",
        "",
        "## No-Action Attribution",
        "",
        f"- Missing required facts: `{', '.join(preview['missing_required_fact_keys']) or 'none'}`",
        f"- Active disable facts: `{', '.join(preview['active_disable_fact_keys']) or 'none'}`",
        "",
        "## Boundary",
        "",
        "- This packet is watcher-facing and non-executing.",
        "- It does not call FinalGate, Operation Layer, or exchange write.",
        "- A fresh signal here can only prepare the next non-executing candidate packet shape.",
    ]
    return "\n".join(lines) + "\n"


def _interaction() -> dict[str, Any]:
    return {
        "level": "L0_local_brf2_runtime_signal_capture",
        "remote_interaction_count": 0,
        "mutates_remote_files": False,
        "approaches_real_order": False,
        "calls_finalgate": False,
        "calls_operation_layer": False,
        "calls_exchange_write": False,
        "places_order": False,
    }


def _safety_invariants() -> dict[str, bool]:
    return {
        "actionable_now": False,
        "real_order_authority": False,
        "candidate_created": False,
        "execution_intent_created": False,
        "calls_finalgate": False,
        "calls_operation_layer": False,
        "calls_exchange_write": False,
        "places_order": False,
        "live_profile_changed": False,
        "order_sizing_changed": False,
        "withdrawal_or_transfer_created": False,
    }


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _read_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


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
