#!/usr/bin/env python3
"""Build replay/live parity audit for CPM, MPG, and SOR."""

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
DEFAULT_CPM_FACTS_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-cpm-runtime-signal-facts.json"
)
DEFAULT_MPG_WATCHER_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-mpg-expanded-watcher-facts.json"
)
DEFAULT_SOR_EVIDENCE_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-sor-runtime-activation-evidence.json"
)
DEFAULT_OUTPUT_JSON = REPO_ROOT / "output/runtime-monitor/latest-replay-live-parity-audit.json"
DEFAULT_OUTPUT_MD = REPO_ROOT / "output/runtime-monitor/latest-replay-live-parity-audit.md"

STRATEGY_IDS = ("CPM-RO-001", "MPG-001", "SOR-001")
CPM_READY_STATUSES = {
    "cpm_runtime_signal_facts_ready",
    "cpm_runtime_signal_facts_ready_from_fallback",
}
BLOCKER_PRIORITY = {
    "artifact_missing": 10,
    "schema_invalid": 10,
    "detector_not_attached": 20,
    "watcher_tick_missing": 30,
    "scope_not_attached": 40,
    "replay_live_rule_mismatch": 50,
    "action_time_boundary_not_reproduced": 60,
    "computed_not_satisfied": 70,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay-json", default=str(DEFAULT_REPLAY_JSON))
    parser.add_argument("--cpm-facts-json", default=str(DEFAULT_CPM_FACTS_JSON))
    parser.add_argument("--mpg-watcher-json", default=str(DEFAULT_MPG_WATCHER_JSON))
    parser.add_argument("--sor-evidence-json", default=str(DEFAULT_SOR_EVIDENCE_JSON))
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-owner-progress", default=str(DEFAULT_OUTPUT_MD))
    args = parser.parse_args(argv)

    artifact = build_replay_live_parity_audit(
        replay=_read_optional_json(Path(args.replay_json)),
        cpm_facts=_read_optional_json(Path(args.cpm_facts_json)),
        mpg_watcher=_read_optional_json(Path(args.mpg_watcher_json)),
        sor_evidence=_read_optional_json(Path(args.sor_evidence_json)),
    )
    output_json = Path(args.output_json)
    output_md = Path(args.output_owner_progress)
    _write_json(output_json, artifact)
    _write_text(output_md, _markdown(artifact, output_json))
    print(
        json.dumps(
            {
                "status": artifact["status"],
                "replay_signal_count": artifact["summary"]["replay_signal_count"],
                "live_detector_reproduced_count": artifact["summary"][
                    "live_detector_reproduced_count"
                ],
                "mismatch_count": artifact["summary"]["mismatch_count"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def build_replay_live_parity_audit(
    *,
    replay: dict[str, Any],
    cpm_facts: dict[str, Any],
    mpg_watcher: dict[str, Any],
    sor_evidence: dict[str, Any],
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    generated = generated_at_utc or datetime.now(timezone.utc).isoformat()
    coverage = {
        "CPM-RO-001": _cpm_coverage(cpm_facts),
        "MPG-001": _watcher_coverage(mpg_watcher),
        "SOR-001": _watcher_coverage(sor_evidence),
    }
    strategy_rows = [
        _strategy_parity_row(row, coverage.get(str(row.get("strategy_group_id") or ""), {}))
        for row in replay.get("strategy_rows") or []
        if str(row.get("strategy_group_id") or "") in STRATEGY_IDS
    ]
    per_symbol = _per_symbol_rows(strategy_rows)
    replay_count = sum(row["replay_signal_count"] for row in strategy_rows)
    reproduced_count = sum(row["live_detector_reproduced_count"] for row in strategy_rows)
    mismatch_count = sum(row["mismatch_count"] for row in strategy_rows)
    return {
        "schema": "brc.replay_live_parity_audit.v1",
        "scope": "replay_live_parity_audit_non_authority",
        "status": "replay_live_parity_audit_ready",
        "generated_at_utc": generated,
        "strategy_rows": strategy_rows,
        "per_symbol_mismatch_table": per_symbol,
        "summary": {
            "strategy_count": len(strategy_rows),
            "replay_signal_count": replay_count,
            "live_detector_reproduced_count": reproduced_count,
            "mismatch_count": mismatch_count,
            "mismatch_reason_policy": "replay_signal_without_live_reproduction_is_signal_capture_defect_not_market_wait",
        },
        "checks": {
            "replay_signal_without_live_reproduction_marked_signal_capture_defect": True,
            "replay_treated_as_live_signal": False,
            "live_submit_allowed": False,
            "candidate_authorization_created": False,
            "finalgate_called": False,
            "operation_layer_called": False,
            "exchange_write_called": False,
            "order_created": False,
        },
        "interaction": non_executing_interaction("L0_local_replay_live_parity_audit"),
        "safety_invariants": non_executing_safety_invariants(
            tuple(), include_authority_mirrors=False
        ),
    }


def _strategy_parity_row(row: dict[str, Any], coverage: dict[str, Any]) -> dict[str, Any]:
    windows = []
    mismatches = []
    for window in row.get("window_results") or []:
        events = [
            event
            for event in window.get("counterfactual_events") or []
            if _is_replay_signal(event)
        ]
        reproduced = [_event_reproduced(event, coverage) for event in events]
        window_mismatches = [
            _mismatch_event(event, coverage)
            for event, matched in zip(events, reproduced, strict=False)
            if not matched
        ]
        mismatches.extend(window_mismatches)
        windows.append(
            {
                "window_days": window.get("window_days"),
                "replay_signal_count": len(events),
                "live_detector_reproduced_count": sum(1 for item in reproduced if item),
                "mismatch_count": len(window_mismatches),
            }
        )
    replay_count = sum(item["replay_signal_count"] for item in windows)
    reproduced_count = sum(item["live_detector_reproduced_count"] for item in windows)
    return {
        "strategy_group_id": row.get("strategy_group_id"),
        "path_id": row.get("path_id"),
        "coverage": coverage,
        "window_results": windows,
        "replay_signal_count": replay_count,
        "live_detector_reproduced_count": reproduced_count,
        "mismatch_count": replay_count - reproduced_count,
        "mismatch_table": mismatches,
    }


def _event_reproduced(event: dict[str, Any], coverage: dict[str, Any]) -> bool:
    symbol = str(event.get("symbol") or "")
    gate = _as_dict(event.get("gate_breakdown"))
    facts = _symbol_facts(coverage, symbol)
    if facts:
        return (
            coverage.get("detector_attached") is True
            and coverage.get("watcher_tick_present") is True
            and facts.get("computed") is True
            and not facts.get("failed_facts")
            and facts.get("fresh_signal_present") is True
            and not _replay_live_rule_mismatch(event, facts)
            and gate.get("required_facts_replay_shape_present") is True
            and gate.get("would_reach_action_time_boundary") is True
        )
    return (
        coverage.get("detector_or_watcher_ready") is True
        and symbol in set(coverage.get("symbol_scope") or [])
        and gate.get("required_facts_replay_shape_present") is True
        and gate.get("would_reach_action_time_boundary") is True
    )


def _mismatch_event(event: dict[str, Any], coverage: dict[str, Any]) -> dict[str, Any]:
    symbol = str(event.get("symbol") or "")
    facts = _symbol_facts(coverage, symbol)
    detector_attached = coverage.get("detector_attached")
    if detector_attached is None:
        detector_attached = coverage.get("detector_or_watcher_ready") is True
    watcher_tick_present = coverage.get("watcher_tick_present")
    if watcher_tick_present is None:
        watcher_tick_present = coverage.get("detector_or_watcher_ready") is True
    computed = facts.get("computed") if facts else coverage.get("computed")
    failed_facts = list(facts.get("failed_facts") or []) if facts else []

    if detector_attached is not True:
        blocker_class = "detector_not_attached"
        owner = "engineering"
    elif watcher_tick_present is not True:
        blocker_class = "watcher_tick_missing"
        owner = "runtime"
    elif facts and _replay_live_rule_mismatch(event, facts):
        blocker_class = "replay_live_rule_mismatch"
        owner = "engineering"
    elif computed is True and failed_facts:
        blocker_class = "computed_not_satisfied"
        owner = "market"
    elif symbol not in set(coverage.get("symbol_scope") or []):
        blocker_class = "scope_not_attached"
        owner = "engineering"
    elif _as_dict(event.get("gate_breakdown")).get("would_reach_action_time_boundary") is not True:
        blocker_class = "action_time_boundary_not_reproduced"
        owner = "runtime"
    elif computed is not True:
        blocker_class = "artifact_missing"
        owner = "engineering"
    else:
        blocker_class = "replay_live_rule_mismatch"
        owner = "engineering"
    next_action = _next_action(blocker_class)
    return {
        "strategy_group_id": event.get("strategy_group_id"),
        "symbol": symbol,
        "event_time_utc": event.get("event_time_utc"),
        "detector_attached": detector_attached is True,
        "watcher_tick_present": watcher_tick_present is True,
        "computed": computed is True,
        "failed_facts": failed_facts,
        "blocker_class": blocker_class,
        "mismatch_reason": blocker_class,
        "first_blocker_class": blocker_class,
        "first_blocker_owner": owner,
        "next_action": next_action,
    }


def _per_symbol_rows(strategy_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str], dict[str, Any]] = {}
    for strategy in strategy_rows:
        for mismatch in strategy["mismatch_table"]:
            key = (str(strategy["strategy_group_id"]), str(mismatch["symbol"]))
            bucket = buckets.setdefault(
                key,
                {
                    "strategy_group_id": key[0],
                    "symbol": key[1],
                    "detector_attached": mismatch.get("detector_attached") is True,
                    "watcher_tick_present": mismatch.get("watcher_tick_present") is True,
                    "computed": mismatch.get("computed") is True,
                    "failed_facts": [],
                    "blocker_class": mismatch.get("blocker_class")
                    or mismatch.get("first_blocker_class"),
                    "next_action": mismatch.get("next_action"),
                    "blocker_priority": _blocker_priority(
                        str(
                            mismatch.get("blocker_class")
                            or mismatch.get("first_blocker_class")
                            or ""
                        )
                    ),
                    "mismatch_count": 0,
                    "mismatch_reasons": [],
                },
            )
            bucket["mismatch_count"] += 1
            reason = mismatch["mismatch_reason"]
            if reason not in bucket["mismatch_reasons"]:
                bucket["mismatch_reasons"].append(reason)
            for fact in mismatch.get("failed_facts") or []:
                if fact not in bucket["failed_facts"]:
                    bucket["failed_facts"].append(fact)
            blocker_class = str(
                mismatch.get("blocker_class")
                or mismatch.get("first_blocker_class")
                or ""
            )
            priority = _blocker_priority(blocker_class)
            if priority < int(bucket["blocker_priority"]):
                bucket["blocker_class"] = blocker_class
                bucket["next_action"] = mismatch.get("next_action")
                bucket["detector_attached"] = mismatch.get("detector_attached") is True
                bucket["watcher_tick_present"] = (
                    mismatch.get("watcher_tick_present") is True
                )
                bucket["computed"] = mismatch.get("computed") is True
                bucket["blocker_priority"] = priority
    for bucket in buckets.values():
        bucket.pop("blocker_priority", None)
    return sorted(buckets.values(), key=lambda item: (item["strategy_group_id"], item["symbol"]))


def _is_replay_signal(event: dict[str, Any]) -> bool:
    return (
        event.get("fresh_like_signal_seen") is True
        or event.get("counterfactual_fresh_signal_present") is True
    )


def _cpm_coverage(cpm_facts: dict[str, Any]) -> dict[str, Any]:
    watcher = _as_dict(cpm_facts.get("watcher_scope"))
    live_detector = _as_dict(cpm_facts.get("live_detector"))
    per_symbol_facts = _cpm_per_symbol_facts(live_detector)
    detector_attached = bool(
        cpm_facts.get("detector_source_mode") or live_detector.get("source")
    )
    watcher_tick_present = cpm_facts.get("watcher_tick_present") is True
    computed = (
        cpm_facts.get("status") in CPM_READY_STATUSES
        and watcher_tick_present
        and bool(per_symbol_facts)
    )
    return {
        "detector_source": cpm_facts.get("detector_source_mode"),
        "detector_attached": detector_attached,
        "watcher_tick_present": watcher_tick_present,
        "computed": computed,
        "detector_or_watcher_ready": computed,
        "symbol_scope": watcher.get("symbol_scope") or [],
        "primary_live_submit_scope": watcher.get("primary_live_submit_symbol_scope") or [],
        "readonly_symbols": watcher.get("expanded_readonly_symbol_scope") or [],
        "per_symbol_facts": per_symbol_facts,
    }


def _watcher_coverage(artifact: dict[str, Any]) -> dict[str, Any]:
    watcher = _as_dict(artifact.get("watcher_scope"))
    ready = (
        artifact.get("runtime_artifact_ready") is True
        or artifact.get("status") in {
            "mpg_expanded_watcher_facts_ready",
            "runtime_activation_evidence_ready",
        }
    )
    return {
        "detector_source": watcher.get("source") or artifact.get("scope"),
        "detector_attached": ready,
        "watcher_tick_present": ready,
        "computed": ready,
        "detector_or_watcher_ready": ready,
        "symbol_scope": watcher.get("symbol_scope") or [],
        "primary_live_submit_scope": watcher.get("primary_live_submit_symbol_scope") or [],
        "readonly_symbols": watcher.get("expanded_readonly_watcher_symbols") or [],
    }


def _cpm_per_symbol_facts(live_detector: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for row in live_detector.get("per_symbol_signal_facts") or []:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or "")
        if not symbol:
            continue
        trigger_facts = _as_dict(row.get("trigger_facts"))
        failed_facts = list(row.get("missing_required_trigger_facts") or [])
        if not failed_facts:
            failed_facts = [
                fact_name
                for fact_name, fact_payload in trigger_facts.items()
                if _fact_failed(fact_payload)
            ]
        rows[symbol] = {
            "computed": bool(trigger_facts) and row.get("candle_input_missing") is not True,
            "fresh_signal_present": row.get("fresh_signal_present") is True,
            "failed_facts": failed_facts,
            "live_fact_names": sorted(trigger_facts.keys()),
            "timeframe": row.get("timeframe"),
        }
    return rows


def _fact_failed(value: Any) -> bool:
    fact = _as_dict(value)
    return fact.get("status") in {"not_satisfied", "missing", "stale"} or (
        fact.get("value") is False and fact.get("status") != "satisfied"
    )


def _symbol_facts(coverage: dict[str, Any], symbol: str) -> dict[str, Any]:
    return _as_dict(_as_dict(coverage.get("per_symbol_facts")).get(symbol))


def _replay_live_rule_mismatch(event: dict[str, Any], facts: dict[str, Any]) -> bool:
    replay_fact_names = _event_replay_fact_names(event)
    if not replay_fact_names:
        return False
    live_fact_names = set(facts.get("live_fact_names") or [])
    return not replay_fact_names.issubset(live_fact_names)


def _event_replay_fact_names(event: dict[str, Any]) -> set[str]:
    gate = _as_dict(event.get("gate_breakdown"))
    names: set[str] = set()
    for key in (
        "required_facts",
        "required_trigger_facts",
        "replay_required_facts",
        "replay_trigger_facts",
    ):
        names.update(_string_set(event.get(key)))
        names.update(_string_set(gate.get(key)))
    return names


def _string_set(value: Any) -> set[str]:
    if isinstance(value, str):
        return {value}
    if isinstance(value, list | tuple | set):
        return {str(item) for item in value if str(item)}
    return set()


def _next_action(blocker_class: str) -> str:
    return {
        "detector_not_attached": "attach_live_detector_to_parity_audit",
        "watcher_tick_missing": "refresh_or_repair_watcher_public_fact_input",
        "computed_not_satisfied": "continue_observation_with_failed_fact_matrix",
        "replay_live_rule_mismatch": "normalize_replay_and_live_detector_fact_rules",
        "scope_not_attached": "produce_scoped_live_observation_or_scope_proposal",
        "action_time_boundary_not_reproduced": "repair_non_executing_action_time_rehearsal_path",
        "artifact_missing": "generate_or_wire_current_fact_artifact",
    }.get(blocker_class, "repair_replay_live_parity_classification")


def _blocker_priority(blocker_class: str) -> int:
    return BLOCKER_PRIORITY.get(blocker_class, 100)


def _markdown(artifact: dict[str, Any], output_json: Path) -> str:
    lines = [
        "## Replay Live Parity Audit",
        "",
        f"- Status: `{artifact['status']}`",
        f"- Replay signals: `{artifact['summary']['replay_signal_count']}`",
        f"- Live-detector reproduced: `{artifact['summary']['live_detector_reproduced_count']}`",
        f"- Mismatches: `{artifact['summary']['mismatch_count']}`",
        f"- Output JSON: `{output_json}`",
    ]
    return "\n".join(lines) + "\n"


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


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


if __name__ == "__main__":
    raise SystemExit(main())
