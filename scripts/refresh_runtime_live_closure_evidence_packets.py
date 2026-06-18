#!/usr/bin/env python3
"""Refresh first bounded live-order closure evidence from report JSON files.

The refresher reads local JSON reports and writes:

- runtime-live-closure-evidence.json
- runtime-live-closure-evidence-verification.json

It does not call Tokyo, FinalGate, Operation Layer, exchange write paths, or
OrderLifecycle. It only projects already-recorded evidence into the canonical
first-live-order closure contract.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts import runtime_live_closure_evidence_packet as packet_builder  # noqa: E402
from scripts import runtime_live_closure_evidence_verifier as verifier  # noqa: E402
from scripts import runtime_live_cutover_readiness as live_cutover  # noqa: E402


DEFAULT_REPORT_DIR = Path(
    "output/strategygroup-runtime-pilot/live-closure-evidence-source-reports"
)
EVIDENCE_FILENAME = "runtime-live-closure-evidence.json"
VERIFICATION_FILENAME = "runtime-live-closure-evidence-verification.json"
REFRESH_FILENAME = "runtime-live-closure-evidence-refresh.json"
GENERATED_FILENAMES = {
    EVIDENCE_FILENAME,
    VERIFICATION_FILENAME,
    REFRESH_FILENAME,
}
NON_LIVE_SOURCE_TOKENS = {
    "controlled",
    "disabled_smoke",
    "dry-run",
    "dry_run",
    "in_memory_simulation",
    "local_cycle",
    "mock",
    "paper",
    "rehearsal",
    "sample",
    "synthetic",
    "testnet",
}
PASSIVE_REPORT_SOURCE_TOKENS = {
    "active_observation",
    "attempt_budget",
    "bootstrap",
    "catalog",
    "deployment_readiness",
    "goal_status",
    "handoff",
    "intake",
    "operator_packet",
    "product_state_refresh",
    "runtime_execution_chain_closure_status",
    "source_readiness",
}
LIVE_CLOSURE_SOURCE_MARKERS = {
    "action_time_finalgate",
    "action_time_final_gate",
    "candidate_authorization",
    "exchange_submit",
    "finalgate",
    "final_gate",
    "fresh_signal_ready",
    "hard_stop",
    "live_facts",
    "operation_layer",
    "official_entry_chain",
    "official_operation_layer_submit_ready",
    "official_post_submit_close_loop",
    "post_submit",
    "protection",
    "reconciliation",
    "required_facts",
    "runtime_grant",
    "runtime_signal_watcher_live_signal",
    "settlement",
    "submit_outcome_review",
}


def build_refresh_report(
    *,
    report_dir: Path,
    output_json: Path | None = None,
    verification_output_json: Path | None = None,
    refresh_output_json: Path | None = None,
    recursive: bool = False,
    include_all_json: bool = False,
    strict_read_errors: bool = False,
    generated_at_ms: int | None = None,
) -> dict[str, Any]:
    generated_at_ms = generated_at_ms or int(time.time() * 1000)
    report_dir = report_dir.expanduser()
    output_json = output_json or report_dir / EVIDENCE_FILENAME
    verification_output_json = (
        verification_output_json or report_dir / VERIFICATION_FILENAME
    )
    refresh_output_json = refresh_output_json or report_dir / REFRESH_FILENAME

    discovered = _discover_json_files(report_dir=report_dir, recursive=recursive)
    included_packets: list[dict[str, Any]] = []
    included_files: list[str] = []
    skipped_files: list[dict[str, str]] = []
    read_errors: list[dict[str, str]] = []

    for path in discovered:
        try:
            packet = _read_json(path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            read_errors.append({"path": str(path), "error": str(exc)})
            continue
        non_live_reason = _non_live_source_reason(path=path, packet=packet)
        if non_live_reason and not include_all_json:
            skipped_files.append({"path": str(path), "reason": non_live_reason})
            continue
        included_packets.append(packet)
        included_files.append(str(path))

    evidence_packet = packet_builder.build_live_closure_evidence_packet(
        included_packets,
        source_kind="official_live_closure_evidence",
        official_live_source=True,
        generated_at_ms=generated_at_ms,
    )
    evidence_packet["refresh"] = {
        "scope": "runtime_live_closure_evidence_refresh",
        "report_dir": str(report_dir),
        "recursive": recursive,
        "include_all_json": include_all_json,
        "discovered_json_count": len(discovered),
        "included_json_count": len(included_packets),
        "skipped_json_count": len(skipped_files),
        "read_error_count": len(read_errors),
        "included_files": included_files,
        "skipped_files": skipped_files,
        "read_errors": read_errors,
    }
    verification_packet = verifier.build_live_closure_evidence_verification(
        evidence_packet,
        generated_at_ms=generated_at_ms,
    )
    refresh_report = _refresh_report(
        report_dir=report_dir,
        output_json=output_json,
        verification_output_json=verification_output_json,
        refresh_output_json=refresh_output_json,
        evidence_packet=evidence_packet,
        verification_packet=verification_packet,
        discovered=discovered,
        included_packets=included_packets,
        skipped_files=skipped_files,
        read_errors=read_errors,
        recursive=recursive,
        include_all_json=include_all_json,
        strict_read_errors=strict_read_errors,
        generated_at_ms=generated_at_ms,
    )

    _write_json(output_json, evidence_packet)
    _write_json(verification_output_json, verification_packet)
    _write_json(refresh_output_json, refresh_report)
    return refresh_report


def _refresh_report(
    *,
    report_dir: Path,
    output_json: Path,
    verification_output_json: Path,
    refresh_output_json: Path,
    evidence_packet: dict[str, Any],
    verification_packet: dict[str, Any],
    discovered: list[Path],
    included_packets: list[dict[str, Any]],
    skipped_files: list[dict[str, str]],
    read_errors: list[dict[str, str]],
    recursive: bool,
    include_all_json: bool,
    strict_read_errors: bool,
    generated_at_ms: int,
) -> dict[str, Any]:
    verification_status = str(verification_packet.get("status") or "")
    if read_errors and strict_read_errors:
        status = "live_closure_refresh_read_error"
        owner_state = "需要介入"
    elif verification_status == "live_closure_complete":
        status = "live_closure_refresh_complete"
        owner_state = "完成"
    elif verification_status == "live_closure_in_progress":
        status = "live_closure_refresh_in_progress"
        owner_state = "处理中"
    elif verification_status == "live_closure_not_started":
        status = "live_closure_refresh_not_started"
        owner_state = "等待机会"
    else:
        status = "live_closure_refresh_rejected"
        owner_state = "需要介入"
    completion = verification_packet.get("completion")
    if not isinstance(completion, dict):
        completion = {}
    return {
        "scope": "runtime_live_closure_evidence_refresh",
        "status": status,
        "owner_state": owner_state,
        "generated_at_ms": generated_at_ms,
        "report_dir": str(report_dir),
        "output_json": str(output_json),
        "verification_output_json": str(verification_output_json),
        "refresh_output_json": str(refresh_output_json),
        "recursive": recursive,
        "include_all_json": include_all_json,
        "strict_read_errors": strict_read_errors,
        "source_counts": {
            "discovered_json": len(discovered),
            "included_json": len(included_packets),
            "skipped_json": len(skipped_files),
            "read_errors": len(read_errors),
        },
        "evidence": {
            "present_evidence_keys": list(evidence_packet.get("present_evidence_keys") or []),
            "missing_evidence_keys": list(evidence_packet.get("missing_evidence_keys") or []),
            "reject_reasons": list(evidence_packet.get("reject_reasons") or []),
        },
        "verification": {
            "status": verification_status,
            "owner_state": verification_packet.get("owner_state"),
            "first_incomplete_stage": verification_packet.get("first_incomplete_stage"),
            "completed_stage_count": verification_packet.get("completed_stage_count"),
            "stage_count": verification_packet.get("stage_count"),
            "reject_reasons": list(verification_packet.get("reject_reasons") or []),
            "first_bounded_real_order_complete": (
                completion.get("first_bounded_real_order_complete") is True
            ),
            "real_order_closure_proven": (
                completion.get("real_order_closure_proven") is True
            ),
        },
        "skipped_files": skipped_files,
        "read_errors": read_errors,
        "safety_invariants": {
            "calls_tokyo_api": False,
            "calls_live_finalgate": False,
            "calls_live_operation_layer": False,
            "exchange_write_called": False,
            "order_lifecycle_called": False,
            "withdrawal_or_transfer_created": False,
            "modifies_secret_or_credentials": False,
            "modifies_live_profile": False,
            "modifies_order_sizing_defaults": False,
        },
    }


def _discover_json_files(*, report_dir: Path, recursive: bool) -> list[Path]:
    pattern = "**/*.json" if recursive else "*.json"
    return sorted(
        path
        for path in report_dir.glob(pattern)
        if path.is_file() and path.name not in GENERATED_FILENAMES
    )


def _non_live_source_reason(*, path: Path, packet: dict[str, Any]) -> str | None:
    text = f"{path.name} {_status_text(packet)}".lower()
    for token in sorted(NON_LIVE_SOURCE_TOKENS):
        if token in text:
            return f"non_live_source_token:{token}"
    for token in sorted(PASSIVE_REPORT_SOURCE_TOKENS):
        if token in text:
            return f"passive_report_source_token:{token}"
    if not _looks_like_live_closure_source(text):
        return "not_live_closure_source"
    return None


def _status_text(packet: dict[str, Any]) -> str:
    values = _collect_values_for_keys(
        packet,
        {
            "scope",
            "status",
            "source_kind",
            "execution_mode",
            "mode",
            "scenario",
        },
    )
    return " ".join(str(item) for item in values if str(item))


def _looks_like_live_closure_source(text: str) -> bool:
    return any(token in text for token in LIVE_CLOSURE_SOURCE_MARKERS)


def _collect_values_for_keys(value: Any, keys: set[str]) -> list[Any]:
    values: list[Any] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key) in keys:
                values.append(child)
            values.extend(_collect_values_for_keys(child, keys))
    elif isinstance(value, list):
        for child in value:
            values.extend(_collect_values_for_keys(child, keys))
    return values


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.expanduser().parent.mkdir(parents=True, exist_ok=True)
    path.expanduser().write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Refresh first bounded live-order closure evidence packets."
    )
    parser.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR))
    parser.add_argument("--output-json")
    parser.add_argument("--verification-output-json")
    parser.add_argument("--refresh-output-json")
    parser.add_argument("--recursive", action="store_true")
    parser.add_argument(
        "--include-all-json",
        action="store_true",
        help="Include controlled, dry-run, mock, synthetic, and sample JSON sources.",
    )
    parser.add_argument(
        "--strict-read-errors",
        action="store_true",
        help="Treat malformed JSON files in the report directory as refresh blockers.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    report_dir = Path(args.report_dir).expanduser()
    refresh_report = build_refresh_report(
        report_dir=report_dir,
        output_json=Path(args.output_json).expanduser() if args.output_json else None,
        verification_output_json=(
            Path(args.verification_output_json).expanduser()
            if args.verification_output_json
            else None
        ),
        refresh_output_json=(
            Path(args.refresh_output_json).expanduser()
            if args.refresh_output_json
            else None
        ),
        recursive=args.recursive,
        include_all_json=args.include_all_json,
        strict_read_errors=args.strict_read_errors,
    )
    print(json.dumps(refresh_report, ensure_ascii=False, indent=2, sort_keys=True))
    success_statuses = {
        "live_closure_refresh_complete",
        "live_closure_refresh_in_progress",
        "live_closure_refresh_not_started",
    }
    return 0 if refresh_report["status"] in success_statuses else 2


if __name__ == "__main__":
    raise SystemExit(main())
