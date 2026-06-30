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
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from src.domain.required_facts_readiness import (  # noqa: E402
    RequiredFactDisableSpec,
    RequiredFactObservationSpec,
    assess_required_fact_observation,
    required_fact_disable_specs_from_rows,
    required_fact_observation_specs_from_rows,
)
from strategygroup_non_executing_projection import (  # noqa: E402
    non_executing_interaction,
    non_executing_safety_invariants,
)

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

    artifact = build_brf2_runtime_signal_capture(
        required_facts_mapping=_read_optional_json(
            Path(args.required_facts_mapping_json)
        ),
        owner_policy=_read_optional_json(Path(args.owner_policy_json)),
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
                "fact_input_present": artifact["fact_input_present"],
                "watcher_tick_present": artifact["watcher_tick_present"],
                "fresh_signal_present": artifact["signal_detector_preview"][
                    "fresh_signal_present"
                ],
                "shadow_candidate_shape_ready": artifact["shadow_candidate_shape"][
                    "shadow_candidate_ready"
                ],
                "output_json": str(output_json),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if artifact["status"] == "brf2_runtime_signal_capture_ready" else 2


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
    required_fact_specs = required_fact_observation_specs_from_rows(
        required_facts_mapping.get("required_fact_observation_specs") or []
    )
    required_fact_keys = [spec.key for spec in required_fact_specs]
    disable_fact_specs = required_fact_disable_specs_from_rows(
        required_facts_mapping.get("disable_fact_observation_specs") or []
    )
    disable_fact_keys = [spec.key for spec in disable_fact_specs]
    required_status = [
        _required_fact_status(spec, facts.get(spec.key))
        for spec in required_fact_specs
    ]
    disable_status = [
        _disable_fact_status(spec, facts.get(spec.key))
        for spec in disable_fact_specs
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
    fact_authority = str(fact_input.get("fact_authority") or "")
    fact_authority_boundary = _as_dict(fact_input.get("fact_authority_boundary"))
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
        "fact_authority": fact_authority,
        "fact_authority_boundary": fact_authority_boundary,
        "signal_detector_preview": {
            "detector_ready": detector_ready,
            "fact_input_present": fact_input_present,
            "watcher_tick_present": watcher_tick_present,
            "fact_input_status": fact_input_status,
            "fresh_signal_present": fresh_signal_present,
            "current_signal_state": current_signal_state,
            "first_blocker_class": first_blocker["class"],
            "first_blocker_owner": first_blocker["owner"],
            "signal_capture_checkpoint": first_blocker["repair_checkpoint"],
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
        "shadow_candidate_shape": {
            "shadow_candidate_ready": fresh_signal_present,
            "shadow_candidate_type": (
                "brf2_non_executing_short_signal_candidate_evidence"
            ),
            "strategy_group_id": "BRF2-001",
            "side": "short",
            "signal_id": str(fresh_signal_rule.get("signal_id") or ""),
            "fact_authority": fact_authority,
            "fact_authority_boundary": fact_authority_boundary,
        },
        "checks": {
            "mapping_ready": mapping_ready,
            "fact_input_present": fact_input_present,
            "watcher_tick_present": watcher_tick_present,
            "fresh_signal_present": fresh_signal_present,
            "missing_required_fact_count": len(missing_required),
            "active_disable_fact_count": len(active_disable),
        },
        "interaction": _interaction(),
        "safety_invariants": _safety_invariants(),
    }


def _required_fact_status(
    spec: RequiredFactObservationSpec,
    fact: dict[str, Any] | None,
) -> dict[str, Any]:
    raw_state = _normalized_state(fact) if fact else ""
    fresh = (
        bool(fact)
        and fact.get("fresh") is not False
        and fact.get("stale") is not True
    )
    return assess_required_fact_observation(
        fact_key=spec.key,
        fact_present=bool(fact),
        raw_status=raw_state,
        fresh=fresh,
        accepted_statuses=spec.accepted_statuses,
    ).as_signal_observation_row()


def _disable_fact_status(
    spec: RequiredFactDisableSpec,
    fact: dict[str, Any] | None,
) -> dict[str, Any]:
    if not fact:
        return {
            "fact_key": spec.key,
            "state": "missing",
            "raw_state": "",
            "fresh": False,
        }
    raw_state = _normalized_state(fact)
    fresh = fact.get("fresh") is not False and fact.get("stale") is not True
    state = (
        "disable_active"
        if raw_state in spec.active_statuses
        else "clear"
    )
    return {
        "fact_key": spec.key,
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


def _facts_by_key(source_artifact: dict[str, Any]) -> dict[str, dict[str, Any]]:
    facts = source_artifact.get("facts", source_artifact)
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
    source_artifact: dict[str, Any],
    facts: dict[str, dict[str, Any]],
) -> bool:
    if source_artifact.get("status") == "brf2_runtime_signal_facts_missing_watcher_input":
        return False
    if source_artifact.get("fact_input_present") is False:
        return False
    return source_artifact.get("fact_input_present") is True or bool(facts)


def _signal_context(source_artifact: dict[str, Any]) -> dict[str, Any]:
    context = _as_dict(source_artifact.get("source_signal_context"))
    if not context:
        context = _as_dict(source_artifact.get("signal_context"))
    if not context:
        context = {
            key: source_artifact.get(key)
            for key in (
                "signal_observation_id",
                "runtime_instance_id",
                "symbol",
                "exchange_symbol",
                "market",
                "timeframe",
                "closed_at_utc",
                "source",
                "source_strategy_group_id",
                "source_candidate_id",
                "source_signal_type",
            )
            if source_artifact.get(key) not in {None, ""}
        }
    return {
        "signal_observation_id": str(context.get("signal_observation_id") or ""),
        "runtime_instance_id": str(context.get("runtime_instance_id") or ""),
        "symbol": str(context.get("symbol") or ""),
        "exchange_symbol": str(context.get("exchange_symbol") or ""),
        "market": str(context.get("market") or ""),
        "timeframe": str(context.get("timeframe") or ""),
        "closed_at_utc": str(context.get("closed_at_utc") or ""),
        "source": str(context.get("source") or "runtime_watcher_read_only_fact_input"),
        "source_strategy_group_id": str(context.get("source_strategy_group_id") or ""),
        "source_candidate_id": str(context.get("source_candidate_id") or ""),
        "source_signal_type": str(context.get("source_signal_type") or ""),
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
            "repair_checkpoint": "build_brf2_required_facts_mapping",
        }
    if not fact_input_present:
        return {
            "class": "brf2_watcher_fact_input_missing",
            "owner": "engineering",
            "repair_checkpoint": "attach_brf2_watcher_fact_input_producer",
        }
    if active_disable:
        return {
            "class": f"{active_disable[0]}_disable_active",
            "owner": "market",
            "repair_checkpoint": "continue_brf2_armed_observation_until_disable_clears",
        }
    if missing_required:
        return {
            "class": "fresh_brf2_short_signal_absent",
            "owner": "market",
            "repair_checkpoint": "continue_brf2_armed_observation_until_fresh_signal",
        }
    return {
        "class": "brf2_fresh_short_signal_present_non_executing",
        "owner": "runtime",
        "repair_checkpoint": "build_brf2_shadow_candidate_evidence",
    }


def _markdown(artifact: dict[str, Any], output_json: Path) -> str:
    preview = artifact["signal_detector_preview"]
    lines = [
        "## BRF2 Runtime Signal Capture",
        "",
        f"- Status: `{artifact['status']}`",
        f"- Generated: `{artifact['generated_at_utc']}`",
        f"- Output JSON: `{output_json}`",
        f"- StrategyGroup: `{artifact['strategy_group_id']}`",
        f"- Fact input present: `{_yes_no(artifact.get('fact_input_present') is True)}`",
        f"- Watcher tick present: `{_yes_no(artifact.get('watcher_tick_present') is True)}`",
        f"- Signal state: `{preview['current_signal_state']}`",
        f"- First blocker: `{preview['first_blocker_class']}`",
        f"- Shadow candidate shape ready: `{_yes_no(artifact['shadow_candidate_shape']['shadow_candidate_ready'])}`",
        f"- Fact authority: `{artifact.get('fact_authority') or 'none'}`",
        "- Action-time RequiredFacts satisfied: `否`",
        "",
        "## No-Action Attribution",
        "",
        f"- Missing required facts: `{', '.join(preview['missing_required_fact_keys']) or 'none'}`",
        f"- Active disable facts: `{', '.join(preview['active_disable_fact_keys']) or 'none'}`",
        "",
        "## Boundary",
        "",
        "- This artifact is watcher-facing and non-executing.",
        "- Read-only observation facts can classify armed observation, but cannot satisfy action-time submit facts.",
        "- It does not call FinalGate, Operation Layer, or exchange write.",
        "- A fresh signal here can only prepare the next non-executing shadow-candidate evidence shape.",
    ]
    return "\n".join(lines) + "\n"


def _interaction() -> dict[str, Any]:
    return non_executing_interaction("L0_local_brf2_runtime_signal_capture")


def _safety_invariants() -> dict[str, bool]:
    return non_executing_safety_invariants(
        (
            "candidate_created",
        ),
        include_authority_mirrors=False,
    )


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
