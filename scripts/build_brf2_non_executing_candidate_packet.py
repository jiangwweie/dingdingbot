#!/usr/bin/env python3
"""Build a BRF2 non-executing candidate packet from runtime signal capture.

This packet is a local read model. It records the shape needed after a fresh
BRF2 short signal appears, but it does not create authorization evidence, call
FinalGate, call Operation Layer, create orders, mutate runtime profile, or
change sizing.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_RUNTIME_SIGNAL_CAPTURE_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-brf2-runtime-signal-capture.json"
)
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-brf2-non-executing-candidate-packet.json"
)
DEFAULT_OUTPUT_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-brf2-non-executing-candidate-packet.md"
)

SCHEMA = "brc.brf2_non_executing_candidate_packet.v1"
READY_STATUS = "brf2_non_executing_candidate_packet_ready"
WAITING_STATUS = "brf2_non_executing_candidate_packet_waiting_for_fresh_signal"
BLOCKED_STATUS = "brf2_non_executing_candidate_packet_blocked"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--runtime-signal-capture-json",
        default=str(DEFAULT_RUNTIME_SIGNAL_CAPTURE_JSON),
    )
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-owner-progress", default=str(DEFAULT_OUTPUT_MD))
    args = parser.parse_args(argv)

    packet = build_brf2_non_executing_candidate_packet(
        runtime_signal_capture=_read_optional_json(
            Path(args.runtime_signal_capture_json)
        ),
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
                "candidate_packet_ready": packet["candidate_packet_ready"],
                "first_blocker_class": packet["first_blocker"]["class"],
                "output_json": str(output_json),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if packet["status"] in {READY_STATUS, WAITING_STATUS} else 2


def build_brf2_non_executing_candidate_packet(
    *,
    runtime_signal_capture: dict[str, Any],
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    generated = generated_at_utc or datetime.now(timezone.utc).isoformat()
    capture_ready = _status(runtime_signal_capture) == "brf2_runtime_signal_capture_ready"
    preview = _as_dict(runtime_signal_capture.get("signal_detector_preview"))
    watcher_scope = _as_dict(runtime_signal_capture.get("watcher_scope"))
    source_context = _as_dict(runtime_signal_capture.get("source_signal_context"))
    candidate_shape = _as_dict(runtime_signal_capture.get("candidate_packet_shape"))
    fact_authority = str(runtime_signal_capture.get("fact_authority") or "")
    fact_authority_boundary = _as_dict(
        runtime_signal_capture.get("fact_authority_boundary")
    )
    signal_state = str(preview.get("current_signal_state") or "unknown")
    fresh_signal_present = preview.get("fresh_signal_present") is True
    required_fact_status = [_as_dict(row) for row in preview.get("required_fact_status") or []]
    disable_fact_status = [_as_dict(row) for row in preview.get("disable_fact_status") or []]

    if not capture_ready:
        status = BLOCKED_STATUS
        first_blocker = {
            "class": "brf2_runtime_signal_capture_not_ready",
            "owner": "engineering",
            "next_action": "restore_brf2_runtime_signal_capture",
        }
    elif not fresh_signal_present:
        status = WAITING_STATUS
        first_blocker = {
            "class": str(
                preview.get("first_blocker_class") or "fresh_brf2_short_signal_absent"
            ),
            "owner": str(preview.get("first_blocker_owner") or "market"),
            "next_action": str(
                preview.get("next_action")
                or "continue_brf2_armed_observation_until_fresh_signal"
            ),
        }
    else:
        status = READY_STATUS
        first_blocker = {
            "class": "candidate_authorization_evidence_not_created",
            "owner": "runtime",
            "next_action": "prepare_fresh_candidate_authorization_evidence",
        }

    candidate_packet_ready = status == READY_STATUS
    signal_id = str(watcher_scope.get("signal_id") or candidate_shape.get("signal_id") or "")
    signal_packet_id = str(source_context.get("signal_packet_id") or "")
    candidate_packet_id = (
        f"brf2-candidate:{signal_packet_id}"
        if candidate_packet_ready and signal_packet_id
        else f"brf2-candidate:{signal_id}:{generated}"
        if candidate_packet_ready
        else ""
    )
    symbol = str(source_context.get("symbol") or source_context.get("exchange_symbol") or "")

    packet = {
        "schema": SCHEMA,
        "scope": "brf2_non_executing_candidate_packet_read_model",
        "status": status,
        "generated_at_utc": generated,
        "strategy_group_id": "BRF2-001",
        "candidate_packet_ready": candidate_packet_ready,
        "candidate_packet": {
            "candidate_packet_id": candidate_packet_id,
            "candidate_packet_type": "brf2_non_executing_short_signal_candidate",
            "strategy_group_id": "BRF2-001",
            "signal_id": signal_id,
            "source_signal_packet_id": signal_packet_id,
            "source_strategy_group_id": str(
                source_context.get("source_strategy_group_id") or ""
            ),
            "source_candidate_id": str(source_context.get("source_candidate_id") or ""),
            "source_signal_type": str(source_context.get("source_signal_type") or ""),
            "symbol": symbol,
            "symbol_binding_status": (
                "actual_symbol_bound"
                if symbol
                else "symbol_scope_only_requires_action_time_binding"
            ),
            "side": "short",
            "signal_state": signal_state,
            "fresh_signal_present": fresh_signal_present,
            "required_fact_bindings": required_fact_status,
            "disable_fact_bindings": disable_fact_status,
            "required_next_chain": [
                "prepare_fresh_candidate_authorization_evidence",
                "action_time_finalgate_packet_id",
                "operation_layer_submit_authorization_id",
                "protection_plan_id",
                "reconciliation_plan_id",
            ],
            "forbidden_until_action_time": [
                "actionable_now",
                "real_order_authority",
                "finalgate_call",
                "operation_layer_call",
                "exchange_write",
                "order_creation",
            ],
            "fact_authority": fact_authority,
            "fact_authority_boundary": fact_authority_boundary,
        },
        "first_blocker": first_blocker,
        "next_runtime_step": (
            "prepare_fresh_candidate_authorization_evidence"
            if candidate_packet_ready
            else first_blocker["next_action"]
        ),
        "after_next_state": (
            "candidate_authorization_evidence_pending_action_time_finalgate"
            if candidate_packet_ready
            else "armed_observation"
        ),
        "checks": {
            "runtime_signal_capture_ready": capture_ready,
            "fresh_signal_present": fresh_signal_present,
            "candidate_packet_ready": candidate_packet_ready,
            "required_facts_satisfied": _all_required_satisfied(required_fact_status),
            "disable_facts_clear": _all_disable_clear(disable_fact_status),
            "actionable_now": False,
            "real_order_authority": False,
            "action_time_required_facts_satisfied": False,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
        },
        "interaction": _interaction(),
        "safety_invariants": _safety_invariants(candidate_packet_ready),
    }
    return packet


def _all_required_satisfied(rows: list[dict[str, Any]]) -> bool:
    return bool(rows) and all(str(row.get("state") or "") == "satisfied" for row in rows)


def _all_disable_clear(rows: list[dict[str, Any]]) -> bool:
    return bool(rows) and all(str(row.get("state") or "") == "clear" for row in rows)


def _markdown(packet: dict[str, Any], output_json: Path) -> str:
    candidate = _as_dict(packet.get("candidate_packet"))
    first_blocker = _as_dict(packet.get("first_blocker"))
    lines = [
        "## BRF2 Non-Executing Candidate Packet",
        "",
        f"- Status: `{packet['status']}`",
        f"- Generated: `{packet['generated_at_utc']}`",
        f"- Output JSON: `{output_json}`",
        f"- StrategyGroup: `{packet['strategy_group_id']}`",
        f"- Candidate packet ready: `{_yes_no(packet['candidate_packet_ready'])}`",
        f"- Signal state: `{candidate.get('signal_state', 'unknown')}`",
        f"- First blocker: `{first_blocker.get('class', 'missing')}` / `{first_blocker.get('owner', 'unknown')}`",
        f"- Next runtime step: `{packet['next_runtime_step']}`",
        f"- Fact authority: `{candidate.get('fact_authority') or 'none'}`",
        "- Action-time RequiredFacts satisfied: `否`",
        f"- Actionable now: `{_yes_no(False)}`",
        f"- Real order authority: `{_yes_no(False)}`",
        "",
        "## Boundary",
        "",
        "- This packet is non-executing and local/read-model only.",
        "- It preserves read-only signal context without converting it into action-time RequiredFacts.",
        "- It does not call FinalGate, Operation Layer, or exchange write.",
        "- It can only prepare the next official candidate/authorization evidence step.",
    ]
    return "\n".join(lines) + "\n"


def _interaction() -> dict[str, Any]:
    return {
        "level": "L0_local_brf2_non_executing_candidate_packet",
        "remote_interaction_count": 0,
        "mutates_remote_files": False,
        "approaches_real_order": False,
        "calls_finalgate": False,
        "calls_operation_layer": False,
        "calls_exchange_write": False,
        "places_order": False,
    }


def _safety_invariants(candidate_packet_ready: bool) -> dict[str, bool]:
    return {
        "actionable_now": False,
        "real_order_authority": False,
        "candidate_packet_created": candidate_packet_ready,
        "authorization_evidence_created": False,
        "execution_intent_created": False,
        "calls_finalgate": False,
        "calls_operation_layer": False,
        "calls_exchange_write": False,
        "places_order": False,
        "live_profile_changed": False,
        "order_sizing_changed": False,
        "withdrawal_or_transfer_created": False,
    }


def _status(packet: dict[str, Any]) -> str:
    return str(packet.get("status") or "")


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
