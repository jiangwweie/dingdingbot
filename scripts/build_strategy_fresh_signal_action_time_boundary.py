#!/usr/bin/env python3
"""Build non-executing fresh-signal to action-time boundary readiness."""

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


DEFAULT_CPM_CAPTURE_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-cpm-runtime-signal-capture.json"
)
DEFAULT_CPM_REHEARSAL_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-cpm-dry-run-submit-rehearsal.json"
)
DEFAULT_MPG_READINESS_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-mpg-action-time-facts-readiness.json"
)
DEFAULT_MPG_EVIDENCE_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-mpg-runtime-activation-evidence.json"
)
DEFAULT_SOR_EVIDENCE_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-sor-runtime-activation-evidence.json"
)
DEFAULT_SOR_DETECTOR_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-sor-session-detector-facts.json"
)
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-strategy-fresh-signal-action-time-boundary.json"
)
DEFAULT_OUTPUT_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-strategy-fresh-signal-action-time-boundary.md"
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cpm-capture-json", default=str(DEFAULT_CPM_CAPTURE_JSON))
    parser.add_argument("--cpm-rehearsal-json", default=str(DEFAULT_CPM_REHEARSAL_JSON))
    parser.add_argument("--mpg-readiness-json", default=str(DEFAULT_MPG_READINESS_JSON))
    parser.add_argument("--mpg-evidence-json", default=str(DEFAULT_MPG_EVIDENCE_JSON))
    parser.add_argument("--sor-evidence-json", default=str(DEFAULT_SOR_EVIDENCE_JSON))
    parser.add_argument("--sor-detector-json", default=str(DEFAULT_SOR_DETECTOR_JSON))
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-owner-progress", default=str(DEFAULT_OUTPUT_MD))
    args = parser.parse_args(argv)

    artifact = build_strategy_fresh_signal_action_time_boundary(
        cpm_capture=_read_optional_json(Path(args.cpm_capture_json)),
        cpm_rehearsal=_read_optional_json(Path(args.cpm_rehearsal_json)),
        mpg_readiness=_read_optional_json(Path(args.mpg_readiness_json)),
        mpg_evidence=_read_optional_json(Path(args.mpg_evidence_json)),
        sor_evidence=_read_optional_json(Path(args.sor_evidence_json)),
        sor_detector=_read_optional_json(Path(args.sor_detector_json)),
    )
    output_json = Path(args.output_json)
    output_md = Path(args.output_owner_progress)
    _write_json(output_json, artifact)
    _write_text(output_md, _markdown(artifact, output_json))
    print(
        json.dumps(
            {
                "status": artifact["status"],
                "fresh_signal_present_count": artifact["summary"][
                    "fresh_signal_present_count"
                ],
                "would_enter_finalgate_if_private_facts_ready_count": artifact[
                    "summary"
                ]["would_enter_finalgate_if_private_facts_ready_count"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def build_strategy_fresh_signal_action_time_boundary(
    *,
    cpm_capture: dict[str, Any],
    cpm_rehearsal: dict[str, Any],
    mpg_readiness: dict[str, Any],
    mpg_evidence: dict[str, Any],
    sor_evidence: dict[str, Any],
    sor_detector: dict[str, Any] | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    generated = generated_at_utc or datetime.now(timezone.utc).isoformat()
    rows = [
        _cpm_row(cpm_capture, cpm_rehearsal),
        _evidence_row(
            strategy_group_id="MPG-001",
            path_id="MPG-STRONG-SYMBOL-ROTATION",
            signal_absent_blocker="fresh_mpg_signal_absent",
            readiness=mpg_readiness,
            evidence=mpg_evidence,
        ),
        _sor_row(sor_evidence, sor_detector or {}),
    ]
    return {
        "schema": "brc.strategy_fresh_signal_action_time_boundary.v1",
        "scope": "fresh_signal_action_time_boundary_non_authority",
        "status": "strategy_fresh_signal_action_time_boundary_ready",
        "generated_at_utc": generated,
        "strategy_rows": rows,
        "summary": {
            "strategy_count": len(rows),
            "fresh_signal_present_count": sum(
                row["fresh_signal_present"] is True for row in rows
            ),
            "would_enter_finalgate_if_private_facts_ready_count": sum(
                row["would_enter_finalgate_if_private_facts_ready"] is True
                for row in rows
            ),
            "live_submit_allowed_count": 0,
        },
        "checks": {
            "required_facts_readiness_projected": True,
            "public_facts_refresh_projected": True,
            "private_action_time_facts_pending": True,
            "candidate_evidence_shape_projected": True,
            "dry_run_submit_rehearsal_projected": True,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
            "order_created": False,
            "live_submit_allowed": False,
        },
        "interaction": non_executing_interaction(
            "L0_local_strategy_fresh_signal_action_time_boundary"
        ),
        "safety_invariants": non_executing_safety_invariants(
            tuple(), include_authority_mirrors=False
        ),
    }


def _cpm_row(capture: dict[str, Any], rehearsal: dict[str, Any]) -> dict[str, Any]:
    preview = _as_dict(capture.get("signal_detector_preview"))
    fresh = preview.get("fresh_signal_present") is True
    public_ready = capture.get("status") == "cpm_runtime_signal_capture_ready"
    candidate_shape = _as_dict(capture.get("shadow_candidate_shape")).get(
        "shadow_candidate_ready"
    ) is True or rehearsal.get("submit_rehearsal_shape_ready") is True
    would_enter = public_ready and candidate_shape
    return _row(
        strategy_group_id="CPM-RO-001",
        symbol="ETHUSDT",
        path_id="CPM-LONG",
        fresh_signal_present=fresh,
        current_signal_state=str(preview.get("current_signal_state") or "unknown"),
        public_facts_ready=public_ready,
        candidate_evidence_shape_ready=candidate_shape,
        dry_run_submit_rehearsal_ready=rehearsal.get("submit_rehearsal_shape_ready")
        is True,
        would_enter_finalgate_if_private_facts_ready=would_enter,
        first_blocker=(
            "private_action_time_facts_required"
            if fresh
            else str(preview.get("first_blocker_class") or "fresh_cpm_long_signal_absent")
        ),
        blocker_owner="runtime" if fresh else str(preview.get("first_blocker_owner") or "market"),
    )


def _evidence_row(
    *,
    strategy_group_id: str,
    path_id: str,
    signal_absent_blocker: str,
    readiness: dict[str, Any],
    evidence: dict[str, Any],
) -> dict[str, Any]:
    public_ready = (
        readiness.get("checks", {}).get("public_facts_ready_for_readonly_symbols") is True
        or evidence.get("runtime_artifact_ready") is True
    )
    candidate_shape = evidence.get("candidate_evidence_shape_ready") is True
    rehearsal_ready = evidence.get("fresh_signal_rehearsal_ready") is True
    would_enter = public_ready and candidate_shape and rehearsal_ready
    return _row(
        strategy_group_id=strategy_group_id,
        symbol=_first_symbol(readiness, evidence, default="SOLUSDT"),
        path_id=path_id,
        fresh_signal_present=False,
        current_signal_state="fresh_signal_absent",
        public_facts_ready=public_ready,
        candidate_evidence_shape_ready=candidate_shape,
        dry_run_submit_rehearsal_ready=rehearsal_ready,
        would_enter_finalgate_if_private_facts_ready=would_enter,
        first_blocker=(
            str(readiness.get("first_blocker") or evidence.get("next_blocker") or signal_absent_blocker)
        ),
        blocker_owner=str(readiness.get("blocker_owner") or "market"),
    )


def _sor_row(evidence: dict[str, Any], detector: dict[str, Any]) -> dict[str, Any]:
    detector_summary = _as_dict(detector.get("summary"))
    detector_rows = [
        row
        for row in detector.get("symbol_detector_rows") or []
        if isinstance(row, dict)
    ]
    selected_row = _sor_selected_detector_row(detector_rows)
    selected_symbol = str(selected_row.get("symbol") or "SOLUSDT")
    fresh = int(detector_summary.get("fresh_session_signal_count") or 0) > 0
    public_ready = (
        evidence.get("runtime_artifact_ready") is True
        and _sor_detector_row_public_ready(selected_row)
    )
    candidate_shape = evidence.get("candidate_evidence_shape_ready") is True
    rehearsal_ready = evidence.get("fresh_signal_rehearsal_ready") is True
    would_enter = public_ready and candidate_shape and rehearsal_ready
    first_blocker = (
        "watcher_tick_missing"
        if not public_ready
        else "private_action_time_facts_required"
        if fresh
        else str(
            detector_summary.get("first_blocker")
            or evidence.get("next_blocker")
            or "fresh_sor_session_range_signal_absent"
        )
    )
    return _row(
        strategy_group_id="SOR-001",
        symbol=selected_symbol,
        path_id="SOR-SESSION-BREAKOUT",
        fresh_signal_present=fresh,
        current_signal_state=(
            "fresh_signal_present" if fresh else "fresh_signal_absent"
        ),
        public_facts_ready=public_ready,
        candidate_evidence_shape_ready=candidate_shape,
        dry_run_submit_rehearsal_ready=rehearsal_ready,
        would_enter_finalgate_if_private_facts_ready=would_enter,
        first_blocker=first_blocker,
        blocker_owner="runtime" if fresh or not public_ready else "market",
    )


def _row(
    *,
    strategy_group_id: str,
    symbol: str,
    path_id: str,
    fresh_signal_present: bool,
    current_signal_state: str,
    public_facts_ready: bool,
    candidate_evidence_shape_ready: bool,
    dry_run_submit_rehearsal_ready: bool,
    would_enter_finalgate_if_private_facts_ready: bool,
    first_blocker: str,
    blocker_owner: str,
) -> dict[str, Any]:
    return {
        "strategy_group_id": strategy_group_id,
        "symbol": symbol,
        "path_id": path_id,
        "fresh_signal_present": fresh_signal_present,
        "current_signal_state": current_signal_state,
        "required_facts_readiness": {
            "public_facts_ready": public_facts_ready,
            "private_action_time_facts_ready": False,
            "private_action_time_fact_keys_pending": [
                "active_position_or_open_order_clear",
                "action_time_available_balance",
            ],
        },
        "candidate_evidence_shape_ready": candidate_evidence_shape_ready,
        "dry_run_submit_rehearsal_ready": dry_run_submit_rehearsal_ready,
        "action_time_path_ready": would_enter_finalgate_if_private_facts_ready,
        "would_enter_finalgate_if_private_facts_ready": (
            would_enter_finalgate_if_private_facts_ready
        ),
        "calls_finalgate": False,
        "calls_operation_layer": False,
        "calls_exchange_write": False,
        "places_order": False,
        "order_created": False,
        "live_submit_allowed": False,
        "first_blocker": first_blocker,
        "blocker_owner": blocker_owner,
        "next_action": (
            "refresh_or_repair_watcher_public_fact_input"
            if first_blocker == "watcher_tick_missing"
            else "wait_for_fresh_signal_then_refresh_private_action_time_facts"
            if not fresh_signal_present
            else "refresh_private_action_time_facts_before_finalgate"
        ),
        "post_action_expected_state": (
            "action_time_finalgate_boundary_ready"
            if would_enter_finalgate_if_private_facts_ready
            else "remain_non_authority_until_required_facts_close"
        ),
    }


def _first_symbol(*artifacts: dict[str, Any], default: str) -> str:
    for artifact in artifacts:
        watcher = _as_dict(artifact.get("watcher_scope"))
        for key in (
            "scoped_live_observation_proposal_symbols",
            "expanded_readonly_watcher_symbols",
            "primary_live_submit_symbol_scope",
            "symbol_scope",
        ):
            symbols = watcher.get(key)
            if isinstance(symbols, list):
                for symbol in symbols:
                    text = str(symbol or "")
                    if text:
                        return text
    return default


def _sor_selected_symbol(detector_rows: list[dict[str, Any]]) -> str:
    return str(_sor_selected_detector_row(detector_rows).get("symbol") or "SOLUSDT")


def _sor_selected_detector_row(detector_rows: list[dict[str, Any]]) -> dict[str, Any]:
    for row in detector_rows:
        if row.get("fresh_session_range_signal") is True:
            return row
    for row in detector_rows:
        symbol = str(row.get("symbol") or "")
        if symbol:
            return row
    return {}


def _sor_detector_row_public_ready(row: dict[str, Any]) -> bool:
    missing_facts = _string_list(row.get("missing_required_trigger_facts"))
    return (
        row.get("public_facts_ready") is True
        and bool(row.get("latest_candle_close_time_utc"))
        and "opening_range_available" not in missing_facts
    )


def _markdown(artifact: dict[str, Any], output_json: Path) -> str:
    lines = [
        "## Strategy Fresh Signal Action-Time Boundary",
        "",
        f"- Status: `{artifact['status']}`",
        f"- Fresh signals present: `{artifact['summary']['fresh_signal_present_count']}`",
        f"- Would enter FinalGate if private facts ready: `{artifact['summary']['would_enter_finalgate_if_private_facts_ready_count']}`",
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


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list | tuple | set):
        return [str(item) for item in value if str(item)]
    return []


if __name__ == "__main__":
    raise SystemExit(main())
