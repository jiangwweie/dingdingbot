#!/usr/bin/env python3
"""Verify first bounded live-order closure evidence against the cutover contract.

This script is local verification only. It does not call Tokyo, FinalGate,
Operation Layer, exchange write paths, or OrderLifecycle. It only answers
whether a supplied live evidence packet satisfies the first-live-closure
contract.
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

from scripts import runtime_live_cutover_readiness as live_cutover  # noqa: E402


DEFAULT_OUTPUT_DIR = Path("output/strategygroup-runtime-pilot/live-closure-evidence")
DEFAULT_OUTPUT_JSON = DEFAULT_OUTPUT_DIR / "runtime-live-closure-evidence-verification.json"
OFFICIAL_LIVE_SOURCE_KINDS = {
    "official_live_closure_evidence",
    "official_runtime_live_closure",
    "runtime_live_closure_evidence",
}
GLOBAL_REJECT_REASONS = {
    "official_live_closure_source_missing",
    "local_rehearsal_evidence",
    "dry_run_or_rehearsal_evidence",
    "controlled_in_memory_execution",
    "live_submit_proof_missing",
    "live_exchange_not_called",
    "real_order_not_placed",
}


def build_live_closure_evidence_verification(
    evidence_packet: dict[str, Any],
    *,
    contract: dict[str, Any] | None = None,
    generated_at_ms: int | None = None,
) -> dict[str, Any]:
    contract = contract or live_cutover.build_live_closure_cutover_contract()
    evidence = _evidence_map(evidence_packet)
    source_ready = _official_live_source_ready(evidence_packet)
    reject_reasons = _reject_reasons(
        evidence_packet,
        evidence=evidence,
        source_ready=source_ready,
    )
    stages = _stage_verifications(
        contract=contract, evidence=evidence, reject_reasons=reject_reasons
    )
    present_evidence_keys = [
        key
        for key in _required_evidence_keys(contract)
        if _evidence_present(evidence.get(key))
    ]
    missing_evidence_keys = [
        key
        for key in _required_evidence_keys(contract)
        if not _evidence_present(evidence.get(key))
    ]
    if present_evidence_keys and not source_ready:
        reject_reasons = sorted(
            {*reject_reasons, "official_live_closure_source_missing"}
        )
        stages = _stage_verifications(
            contract=contract, evidence=evidence, reject_reasons=reject_reasons
        )
    rejected_stages = [stage for stage in stages if stage["status"] == "rejected"]
    global_reject_reasons = [
        reason for reason in reject_reasons if reason in GLOBAL_REJECT_REASONS
    ]
    complete_stages = [stage for stage in stages if stage["status"] == "complete"]
    first_incomplete_stage = next(
        (stage["name"] for stage in stages if stage["status"] != "complete"),
        None,
    )
    if rejected_stages or global_reject_reasons:
        status = "blocked_live_closure_rejected"
        owner_state = "需要介入"
    elif not stages:
        status = "live_closure_contract_missing"
        owner_state = "需要介入"
    elif len(complete_stages) == len(stages):
        status = "live_closure_complete"
        owner_state = "完成"
    elif not present_evidence_keys:
        status = "live_closure_not_started"
        owner_state = "等待机会"
    else:
        status = "live_closure_in_progress"
        owner_state = "处理中"

    return {
        "scope": "runtime_live_closure_evidence_verification",
        "status": status,
        "owner_state": owner_state,
        "generated_at_ms": generated_at_ms or int(time.time() * 1000),
        "contract_scope": contract.get("scope"),
        "contract_status": contract.get("status"),
        "official_live_source_ready": source_ready,
        "stage_count": len(stages),
        "completed_stage_count": len(complete_stages),
        "first_incomplete_stage": first_incomplete_stage,
        "present_evidence_keys": present_evidence_keys,
        "missing_evidence_keys": missing_evidence_keys,
        "reject_reasons": reject_reasons,
        "stages": stages,
        "completion": {
            "first_bounded_real_order_complete": status == "live_closure_complete",
            "real_order_closure_proven": status == "live_closure_complete",
            "mock_signal_treated_as_real_signal": "synthetic_signal" in reject_reasons
            or "replay_signal" in reject_reasons,
            "disabled_smoke_treated_as_real_execution_proof": "disabled_smoke_only"
            in reject_reasons,
        },
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


def _stage_verifications(
    *,
    contract: dict[str, Any],
    evidence: dict[str, Any],
    reject_reasons: list[str],
) -> list[dict[str, Any]]:
    stages = contract.get("stages")
    if not isinstance(stages, list):
        return []
    verifications: list[dict[str, Any]] = []
    previous_stage_complete = True
    for raw_stage in stages:
        if not isinstance(raw_stage, dict):
            continue
        required_keys = [
            str(item) for item in raw_stage.get("required_evidence_keys") or []
        ]
        stage_reject_reasons = [
            str(item)
            for item in raw_stage.get("reject_if") or []
            if str(item) in reject_reasons
        ]
        missing = [
            key for key in required_keys if not _evidence_present(evidence.get(key))
        ]
        if stage_reject_reasons:
            status = "rejected"
        elif not previous_stage_complete:
            status = "blocked_by_previous_stage"
        elif missing:
            status = "missing_evidence"
        else:
            status = "complete"
        previous_stage_complete = status == "complete"
        verifications.append(
            {
                "name": str(raw_stage.get("name") or ""),
                "status": status,
                "required_evidence_keys": required_keys,
                "missing_evidence_keys": missing,
                "reject_reasons": stage_reject_reasons,
                "next_action": str(raw_stage.get("next_action") or ""),
            }
        )
    return verifications


def _evidence_map(packet: dict[str, Any]) -> dict[str, Any]:
    evidence = packet.get("evidence")
    if isinstance(evidence, dict):
        return evidence
    return {
        key: value
        for key, value in packet.items()
        if key
        not in {
            "scope",
            "status",
            "reject_reasons",
            "rejected_reasons",
            "flags",
            "safety_invariants",
            "metadata",
            "source_kind",
            "evidence_source",
            "official_live_closure_evidence",
        }
    }


def _reject_reasons(
    packet: dict[str, Any],
    *,
    evidence: dict[str, Any],
    source_ready: bool,
) -> list[str]:
    reasons: set[str] = set()
    for key in ("reject_reasons", "rejected_reasons"):
        items = packet.get(key)
        if isinstance(items, list):
            reasons.update(str(item) for item in items if str(item))
    flags = packet.get("flags")
    if isinstance(flags, dict):
        reasons.update(str(key) for key, value in flags.items() if value is True)
    safety = packet.get("safety_invariants")
    if isinstance(safety, dict):
        if safety.get("mock_signal_treated_as_real_signal") is True:
            reasons.add("synthetic_signal")
        if safety.get("disabled_smoke_treated_as_real_execution_proof") is True:
            reasons.add("disabled_smoke_only")
    if source_ready and _evidence_present(evidence.get("exchange_submit_execution_result_id")):
        proof = packet.get("live_submit_proof")
        if not isinstance(proof, dict):
            reasons.add("live_submit_proof_missing")
        else:
            if proof.get("exchange_result_present") is not True:
                reasons.add("live_submit_proof_missing")
            if proof.get("live_exchange_called") is not True:
                reasons.add("live_exchange_not_called")
            if proof.get("real_order_placed") is not True:
                reasons.add("real_order_not_placed")
    return sorted(reasons)


def _official_live_source_ready(packet: dict[str, Any]) -> bool:
    if packet.get("official_live_closure_evidence") is True:
        return True
    if str(packet.get("source_kind") or "") in OFFICIAL_LIVE_SOURCE_KINDS:
        return True
    if str(packet.get("evidence_source") or "") in OFFICIAL_LIVE_SOURCE_KINDS:
        return True
    metadata = packet.get("metadata")
    if isinstance(metadata, dict):
        if metadata.get("official_live_closure_evidence") is True:
            return True
        if str(metadata.get("source_kind") or "") in OFFICIAL_LIVE_SOURCE_KINDS:
            return True
        if str(metadata.get("evidence_source") or "") in OFFICIAL_LIVE_SOURCE_KINDS:
            return True
    return False


def _required_evidence_keys(contract: dict[str, Any]) -> list[str]:
    keys = contract.get("required_evidence_keys")
    if isinstance(keys, list):
        return [str(item) for item in keys if str(item)]
    return [
        key
        for stage in contract.get("stages") or []
        if isinstance(stage, dict)
        for key in [str(item) for item in stage.get("required_evidence_keys") or []]
        if key
    ]


def _evidence_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify first bounded live-order closure evidence."
    )
    parser.add_argument("--evidence-json", required=True)
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    packet = build_live_closure_evidence_verification(
        _read_json(Path(args.evidence_json).expanduser())
    )
    _write_json(Path(args.output_json).expanduser(), packet)
    print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True))
    success_statuses = {
        "live_closure_complete",
        "live_closure_in_progress",
        "live_closure_not_started",
    }
    return 0 if packet["status"] in success_statuses else 2


if __name__ == "__main__":
    raise SystemExit(main())
