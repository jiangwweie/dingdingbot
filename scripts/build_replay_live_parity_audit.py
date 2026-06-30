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
    return (
        coverage.get("detector_or_watcher_ready") is True
        and symbol in set(coverage.get("symbol_scope") or [])
        and gate.get("required_facts_replay_shape_present") is True
        and gate.get("would_reach_action_time_boundary") is True
    )


def _mismatch_event(event: dict[str, Any], coverage: dict[str, Any]) -> dict[str, Any]:
    symbol = str(event.get("symbol") or "")
    if coverage.get("detector_or_watcher_ready") is not True:
        reason = "signal_capture_defect:live_detector_artifact_missing"
        owner = "engineering"
    elif symbol not in set(coverage.get("symbol_scope") or []):
        reason = "signal_capture_defect:symbol_scope_not_attached"
        owner = "engineering"
    elif _as_dict(event.get("gate_breakdown")).get("would_reach_action_time_boundary") is not True:
        reason = "signal_capture_defect:action_time_boundary_not_reproduced"
        owner = "runtime"
    else:
        reason = "signal_capture_defect:required_facts_shape_not_reproduced"
        owner = "runtime"
    return {
        "strategy_group_id": event.get("strategy_group_id"),
        "symbol": symbol,
        "event_time_utc": event.get("event_time_utc"),
        "mismatch_reason": reason,
        "first_blocker_class": reason,
        "first_blocker_owner": owner,
        "next_action": "attach_live_detector_or_action_time_boundary_for_replay_signal",
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
                    "mismatch_count": 0,
                    "mismatch_reasons": [],
                },
            )
            bucket["mismatch_count"] += 1
            reason = mismatch["mismatch_reason"]
            if reason not in bucket["mismatch_reasons"]:
                bucket["mismatch_reasons"].append(reason)
    return sorted(buckets.values(), key=lambda item: (item["strategy_group_id"], item["symbol"]))


def _is_replay_signal(event: dict[str, Any]) -> bool:
    return (
        event.get("fresh_like_signal_seen") is True
        or event.get("counterfactual_fresh_signal_present") is True
    )


def _cpm_coverage(cpm_facts: dict[str, Any]) -> dict[str, Any]:
    watcher = _as_dict(cpm_facts.get("watcher_scope"))
    return {
        "detector_source": cpm_facts.get("detector_source_mode"),
        "detector_or_watcher_ready": cpm_facts.get("status") == "cpm_runtime_signal_facts_ready",
        "symbol_scope": watcher.get("symbol_scope") or [],
        "primary_live_submit_scope": watcher.get("primary_live_submit_symbol_scope") or [],
        "readonly_symbols": watcher.get("expanded_readonly_symbol_scope") or [],
    }


def _watcher_coverage(artifact: dict[str, Any]) -> dict[str, Any]:
    watcher = _as_dict(artifact.get("watcher_scope"))
    return {
        "detector_source": watcher.get("source") or artifact.get("scope"),
        "detector_or_watcher_ready": (
            artifact.get("runtime_artifact_ready") is True
            or artifact.get("status") in {
                "mpg_expanded_watcher_facts_ready",
                "runtime_activation_evidence_ready",
            }
        ),
        "symbol_scope": watcher.get("symbol_scope") or [],
        "primary_live_submit_scope": watcher.get("primary_live_submit_symbol_scope") or [],
        "readonly_symbols": watcher.get("expanded_readonly_watcher_symbols") or [],
    }


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
