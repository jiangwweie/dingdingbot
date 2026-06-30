#!/usr/bin/env python3
"""Build an auditable apply plan for a runtime profile confirmation.

RTF-037 consumes an RTF-036 confirmation record and prepares the exact official API
requests needed to record a promotion confirmation and create a shadow runtime
draft. This script is deliberately non-mutating: it does not call APIs, write
PG, create runtimes, activate runtimes, create candidates/intents/orders, call
OrderLifecycle, or touch exchange.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any


READY_STATUS = "ready_for_owner_authorized_runtime_profile_apply"
WAITING_STATUS = "waiting_for_owner_runtime_profile_confirmation"
BLOCKED_STATUS = "blocked_runtime_profile_confirmation_apply_plan"


def _load_json(path: str) -> dict[str, Any]:
    value = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _slug(value: str, *, max_length: int = 120) -> str:
    text = re.sub(r"[^A-Za-z0-9_.=-]+", "-", value.strip())
    text = re.sub(r"-+", "-", text).strip("-").lower()
    return (text or "runtime-profile-confirmation")[:max_length].strip("-")


def _proposal(confirmation_record: dict[str, Any]) -> dict[str, Any]:
    template = confirmation_record.get("promotion_confirmation_request_template") or {}
    proposal = template.get("runtime_profile_proposal_snapshot") or {}
    if not isinstance(proposal, dict):
        return {}
    return proposal


def _expected_owner_confirmation(confirmation_record: dict[str, Any]) -> str:
    proposal = _proposal(confirmation_record)
    strategy_family_id = str(confirmation_record.get("strategy_family_id") or "")
    strategy_family_version_id = str(
        confirmation_record.get("strategy_family_version_id") or ""
    )
    symbol = str(confirmation_record.get("symbol") or "")
    side = str(confirmation_record.get("side") or "").lower()
    total_loss_budget = str(proposal.get("total_loss_budget") or "")
    max_notional = str(proposal.get("max_notional_per_attempt") or "")
    max_attempts = str(proposal.get("max_attempts") or "")
    return (
        "runtime-profile-confirm:"
        f"{strategy_family_id}:{strategy_family_version_id}:{symbol}:{side}:"
        f"budget={total_loss_budget}:notional={max_notional}:attempts={max_attempts}:"
        "owner-authorized"
    )


def _safety_invariants() -> dict[str, bool]:
    return {
        "confirmation_record_replay_only": True,
        "database_write": False,
        "promotion_confirmation_record_created": False,
        "runtime_profile_mutated": False,
        "runtime_created": False,
        "runtime_enabled": False,
        "runtime_activated": False,
        "signal_evaluation_created": False,
        "order_candidate_created": False,
        "execution_intent_created": False,
        "executable_execution_intent_created": False,
        "order_created": False,
        "order_lifecycle_called": False,
        "exchange_write_called": False,
        "attempt_counter_mutated": False,
        "runtime_budget_mutated": False,
        "position_opened": False,
        "position_closed": False,
        "withdrawal_or_transfer_created": False,
    }


def _blocked(
    *,
    confirmation_record: dict[str, Any],
    blockers: list[str],
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    expected = _expected_owner_confirmation(confirmation_record)
    return {
        "scope": "runtime_profile_confirmation_apply_plan",
        "status": BLOCKED_STATUS,
        "source_status": confirmation_record.get("status"),
        "strategy_family_id": confirmation_record.get("strategy_family_id"),
        "strategy_family_version_id": confirmation_record.get("strategy_family_version_id"),
        "symbol": confirmation_record.get("symbol"),
        "side": confirmation_record.get("side"),
        "owner_confirmation": {
            "required_value": expected,
            "provided": False,
            "matches": False,
        },
        "api_apply_plan": None,
        "checks": {
            "ready_for_owner_authorized_runtime_profile_apply": False,
            "blockers": sorted(set(blockers)),
        },
        "blockers": sorted(set(blockers)),
        "warnings": list(warnings or []),
        "safety_invariants": _safety_invariants(),
    }


def build_apply_plan(
    *,
    confirmation_record: dict[str, Any],
    trial_binding_id: str | None = None,
    owner_confirmation_value: str | None = None,
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings = [
        *list(confirmation_record.get("warnings") or []),
        "apply_plan_does_not_call_api",
        "apply_plan_does_not_create_runtime",
        "apply_plan_does_not_place_order",
    ]
    if confirmation_record.get("status") != "ready_for_owner_codex_runtime_profile_confirmation":
        blockers.append("runtime_profile_confirmation_record_not_ready")
    if not confirmation_record.get("promotion_confirmation_request_template"):
        blockers.append("promotion_confirmation_request_template_missing")
    if not confirmation_record.get("runtime_draft_request_template"):
        blockers.append("runtime_draft_request_template_missing")
    gate = confirmation_record.get("promotion_gate_preview") or {}
    if gate.get("status") != "ready_for_controlled_runtime_execution_design":
        blockers.append("promotion_gate_preview_not_ready")
    source_safety = confirmation_record.get("safety_invariants") or {}
    if source_safety.get("runtime_created") or source_safety.get("exchange_write_called"):
        blockers.append("source_confirmation_record_contains_mutation")
    if blockers:
        return _blocked(
            confirmation_record=confirmation_record,
            blockers=blockers,
            warnings=warnings,
        )

    expected = _expected_owner_confirmation(confirmation_record)
    provided = owner_confirmation_value is not None
    matches = owner_confirmation_value == expected
    if not provided or not matches:
        status = WAITING_STATUS
        apply_blockers = ["owner_runtime_profile_confirmation_missing"]
        if provided and not matches:
            apply_blockers = ["owner_runtime_profile_confirmation_mismatch"]
        return {
            "scope": "runtime_profile_confirmation_apply_plan",
            "status": status,
            "source_status": confirmation_record.get("status"),
            "strategy_family_id": confirmation_record.get("strategy_family_id"),
            "strategy_family_version_id": confirmation_record.get(
                "strategy_family_version_id"
            ),
            "symbol": confirmation_record.get("symbol"),
            "side": confirmation_record.get("side"),
            "owner_confirmation": {
                "required_value": expected,
                "provided": provided,
                "matches": matches,
            },
            "source_confirmation_record": confirmation_record,
            "api_apply_plan": None,
            "checks": {
                "ready_for_owner_authorized_runtime_profile_apply": False,
                "owner_confirmation_matches": matches,
                "trial_binding_id_supplied": trial_binding_id is not None,
                "blockers": apply_blockers,
            },
            "blockers": apply_blockers,
            "warnings": warnings,
            "safety_invariants": _safety_invariants(),
        }

    if not trial_binding_id:
        return {
            "scope": "runtime_profile_confirmation_apply_plan",
            "status": BLOCKED_STATUS,
            "source_status": confirmation_record.get("status"),
            "strategy_family_id": confirmation_record.get("strategy_family_id"),
            "strategy_family_version_id": confirmation_record.get(
                "strategy_family_version_id"
            ),
            "symbol": confirmation_record.get("symbol"),
            "side": confirmation_record.get("side"),
            "owner_confirmation": {
                "required_value": expected,
                "provided": True,
                "matches": True,
            },
            "source_confirmation_record": confirmation_record,
            "api_apply_plan": None,
            "checks": {
                "ready_for_owner_authorized_runtime_profile_apply": False,
                "owner_confirmation_matches": True,
                "trial_binding_id_supplied": False,
                "blockers": ["trial_binding_id_required_for_runtime_draft"],
            },
            "blockers": ["trial_binding_id_required_for_runtime_draft"],
            "warnings": warnings,
            "safety_invariants": _safety_invariants(),
        }

    confirmation_request = dict(
        confirmation_record["promotion_confirmation_request_template"]
    )
    evidence_refs = list(confirmation_request.get("evidence_refs") or [])
    evidence_refs.append(f"owner-confirmation://{_slug(expected)}")
    confirmation_request["evidence_refs"] = evidence_refs
    confirmation_request["metadata"] = {
        **dict(confirmation_request.get("metadata") or {}),
        "owner_runtime_profile_confirmation_recorded": True,
        "owner_confirmation_value_matches_required": True,
        "rtf037_apply_plan_ready": True,
    }
    confirmation_id = str(confirmation_request["confirmation_id"])
    runtime_draft_body = {
        **dict(
            (confirmation_record.get("runtime_draft_request_template") or {}).get("body")
            or {}
        ),
        "trial_binding_id": trial_binding_id,
    }
    runtime_draft_body["metadata"] = {
        **dict(runtime_draft_body.get("metadata") or {}),
        "source": "rtf037_runtime_profile_confirmation_apply_plan",
        "owner_runtime_profile_confirmation_id": confirmation_id,
        "execution_enabled": False,
        "shadow_mode": True,
    }
    api_requests = [
        {
            "step": "record_promotion_confirmation",
            "method": "POST",
            "path": "/api/brc/strategy-runtime-promotion-confirmations",
            "body": confirmation_request,
            "expected_effect": "creates_promotion_confirmation_record_only",
            "does_not_create_runtime": True,
            "does_not_create_order": True,
            "does_not_call_exchange": True,
        },
        {
            "step": "create_shadow_runtime_draft",
            "method": "POST",
            "path": (
                "/api/brc/strategy-runtime-promotion-confirmations/"
                f"{confirmation_id}/runtime-drafts"
            ),
            "body": runtime_draft_body,
            "expected_effect": "creates_execution_disabled_shadow_runtime_draft",
            "execution_enabled": False,
            "shadow_mode": True,
            "does_not_create_order": True,
            "does_not_call_exchange": True,
        },
    ]
    return {
        "scope": "runtime_profile_confirmation_apply_plan",
        "status": READY_STATUS,
        "source_status": confirmation_record.get("status"),
        "strategy_family_id": confirmation_record.get("strategy_family_id"),
        "strategy_family_version_id": confirmation_record.get("strategy_family_version_id"),
        "symbol": confirmation_record.get("symbol"),
        "side": confirmation_record.get("side"),
        "runtime_instance_id": confirmation_record.get("runtime_instance_id"),
        "trial_binding_id": trial_binding_id,
        "owner_confirmation": {
            "required_value": expected,
            "provided": True,
            "matches": True,
        },
        "source_confirmation_record": confirmation_record,
        "api_apply_plan": {
            "ready_to_apply": True,
            "requests": api_requests,
            "creates_promotion_confirmation_record_when_applied": True,
            "creates_shadow_runtime_draft_when_applied": True,
            "execution_enabled_after_apply": False,
            "places_order_when_applied": False,
            "calls_exchange_when_applied": False,
            "requires_post_creation_full_cycle_probe": True,
        },
        "checks": {
            "ready_for_owner_authorized_runtime_profile_apply": True,
            "owner_confirmation_matches": True,
            "trial_binding_id_supplied": True,
            "promotion_confirmation_request_ready": True,
            "runtime_draft_request_ready": True,
            "blockers": [],
        },
        "blockers": [],
        "warnings": warnings,
        "safety_invariants": _safety_invariants(),
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build RTF-037 runtime profile confirmation apply plan.",
    )
    parser.add_argument("--confirmation-record-json", required=True)
    parser.add_argument("--trial-binding-id")
    parser.add_argument("--owner-confirmation-value")
    parser.add_argument("--output-json")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    plan = build_apply_plan(
        confirmation_record=_load_json(args.confirmation_record_json),
        trial_binding_id=args.trial_binding_id,
        owner_confirmation_value=args.owner_confirmation_value,
    )
    payload = json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True, default=str)
    if args.output_json:
        output_path = Path(args.output_json).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 2 if plan["status"] == BLOCKED_STATUS else 0


if __name__ == "__main__":
    raise SystemExit(main())
