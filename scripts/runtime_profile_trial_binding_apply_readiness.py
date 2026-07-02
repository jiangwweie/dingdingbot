#!/usr/bin/env python3
"""Resolve a trial binding and build runtime profile apply readiness.

RTF-038 consumes an RTF-037 profile-confirmation plan plus a read-only trial
binding list. It picks a compatible binding and produces the ready apply plan
that can later be submitted through official APIs. The script itself is
read-only and non-mutating.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts import runtime_profile_confirmation_apply_plan as apply_plan  # noqa: E402


READY_STATUS = "ready_for_runtime_profile_apply_with_trial_binding"
WAITING_STATUS = "waiting_for_matching_trial_binding"
BLOCKED_STATUS = "blocked_runtime_profile_trial_binding_apply_readiness"

ELIGIBLE_BINDING_STATUSES = {
    "binding_reserved",
    "campaign_created",
    "runtime_constraints_installed",
}
TERMINAL_BINDING_STATUSES = {
    "cancelled",
    "expired",
    "invalidated",
    "runtime_installed",
}


def _load_json(path: str) -> dict[str, Any] | list[Any]:
    return json.loads(Path(path).expanduser().read_text(encoding="utf-8"))


def _normalize_bindings(raw: dict[str, Any] | list[Any]) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        values = raw
    elif isinstance(raw, dict):
        values = (
            raw.get("trial_bindings")
            or raw.get("bindings")
            or raw.get("items")
            or raw.get("data")
            or []
        )
    else:
        raise ValueError("trial bindings JSON must be an object or list")
    if not isinstance(values, list):
        raise ValueError("trial bindings JSON list field must be an array")
    result: list[dict[str, Any]] = []
    for item in values:
        if not isinstance(item, dict):
            raise ValueError("trial binding item must be an object")
        result.append(item)
    return result


def _binding_id(binding: dict[str, Any]) -> str | None:
    value = binding.get("binding_id") or binding.get("trial_binding_id")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _binding_status(binding: dict[str, Any]) -> str:
    return str(binding.get("binding_status") or binding.get("status") or "").strip()


def _created_at(binding: dict[str, Any]) -> int:
    value = binding.get("updated_at_ms") or binding.get("created_at_ms") or 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _match_score(binding: dict[str, Any], version_id: str) -> tuple[int, int]:
    status = _binding_status(binding)
    status_rank = {
        "runtime_constraints_installed": 30,
        "campaign_created": 20,
        "binding_reserved": 10,
    }.get(status, 0)
    version_match = 100 if binding.get("strategy_family_version_id") == version_id else 0
    return (version_match + status_rank, _created_at(binding))


def _candidate_summary(binding: dict[str, Any], version_id: str) -> dict[str, Any]:
    status = _binding_status(binding)
    binding_id = _binding_id(binding)
    invalidated = bool(binding.get("invalidated_at_ms")) or status in TERMINAL_BINDING_STATUSES
    version_matches = binding.get("strategy_family_version_id") == version_id
    eligible_status = status in ELIGIBLE_BINDING_STATUSES
    blockers: list[str] = []
    if not binding_id:
        blockers.append("trial_binding_id_missing")
    if not version_matches:
        blockers.append("strategy_family_version_mismatch")
    if invalidated:
        blockers.append("trial_binding_invalid_or_terminal")
    if not eligible_status:
        blockers.append("trial_binding_status_not_eligible")
    return {
        "binding_id": binding_id,
        "strategy_family_version_id": binding.get("strategy_family_version_id"),
        "binding_status": status,
        "trial_env": binding.get("trial_env"),
        "trial_stage": binding.get("trial_stage"),
        "execution_mode": binding.get("execution_mode"),
        "campaign_id": binding.get("campaign_id"),
        "runtime_carrier_id": binding.get("runtime_carrier_id"),
        "created_at_ms": binding.get("created_at_ms"),
        "updated_at_ms": binding.get("updated_at_ms"),
        "eligible": not blockers,
        "blockers": blockers,
    }


def _select_binding(
    *,
    bindings: list[dict[str, Any]],
    strategy_family_version_id: str,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    candidates = [
        _candidate_summary(binding, strategy_family_version_id)
        for binding in bindings
    ]
    eligible_ids = {item["binding_id"] for item in candidates if item["eligible"]}
    eligible_raw = [
        binding for binding in bindings if _binding_id(binding) in eligible_ids
    ]
    if not eligible_raw:
        return None, candidates
    selected = sorted(
        eligible_raw,
        key=lambda item: _match_score(item, strategy_family_version_id),
        reverse=True,
    )[0]
    return selected, candidates


def _safety_invariants() -> dict[str, bool]:
    return {
        "trial_binding_read_only": True,
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
        "withdrawal_or_transfer_created": False,
    }


def _source_confirmation_record(apply_source_artifact: dict[str, Any]) -> dict[str, Any]:
    source = apply_source_artifact.get("source_confirmation_record")
    if isinstance(source, dict):
        return source
    return apply_source_artifact


def _owner_confirmation_value(
    *,
    apply_source_artifact: dict[str, Any],
    override: str | None,
) -> str | None:
    if override is not None:
        return override
    owner_confirmation = apply_source_artifact.get("owner_confirmation")
    if not isinstance(owner_confirmation, dict):
        return None
    if owner_confirmation.get("matches") is True:
        required = owner_confirmation.get("required_value")
        if isinstance(required, str) and required.strip():
            return required
    return None


def build_apply_readiness(
    *,
    apply_confirmation_record: dict[str, Any],
    trial_bindings_payload: dict[str, Any] | list[Any],
    owner_confirmation_value: str | None = None,
) -> dict[str, Any]:
    apply_source_artifact = apply_confirmation_record
    apply_confirmation_record = _source_confirmation_record(apply_source_artifact)
    owner_confirmation_value = _owner_confirmation_value(
        apply_source_artifact=apply_source_artifact,
        override=owner_confirmation_value,
    )
    strategy_family_version_id = str(
        apply_confirmation_record.get("strategy_family_version_id") or ""
    )
    if not strategy_family_version_id:
        return {
            "scope": "runtime_profile_trial_binding_apply_readiness",
            "status": BLOCKED_STATUS,
            "selected_trial_binding": None,
            "candidate_trial_bindings": [],
            "apply_plan": None,
            "checks": {
                "ready_for_runtime_profile_apply_with_trial_binding": False,
                "blockers": ["strategy_family_version_id_missing"],
            },
            "blockers": ["strategy_family_version_id_missing"],
            "warnings": [],
            "safety_invariants": _safety_invariants(),
        }

    bindings = _normalize_bindings(trial_bindings_payload)
    selected_raw, candidates = _select_binding(
        bindings=bindings,
        strategy_family_version_id=strategy_family_version_id,
    )
    if selected_raw is None:
        return {
            "scope": "runtime_profile_trial_binding_apply_readiness",
            "status": WAITING_STATUS,
            "strategy_family_id": apply_confirmation_record.get("strategy_family_id"),
            "strategy_family_version_id": strategy_family_version_id,
            "symbol": apply_confirmation_record.get("symbol"),
            "side": apply_confirmation_record.get("side"),
            "selected_trial_binding": None,
            "candidate_trial_bindings": candidates,
            "apply_plan": None,
            "checks": {
                "ready_for_runtime_profile_apply_with_trial_binding": False,
                "matching_trial_binding_found": False,
                "owner_confirmation_available": owner_confirmation_value is not None,
                "blockers": ["matching_trial_binding_not_found"],
            },
            "blockers": ["matching_trial_binding_not_found"],
            "warnings": [
                "trial_binding_may_need_official_admission_reservation_flow",
            ],
            "safety_invariants": _safety_invariants(),
        }

    selected = _candidate_summary(selected_raw, strategy_family_version_id)
    trial_binding_id = str(selected["binding_id"])
    nested_apply = apply_plan.build_apply_plan(
        confirmation_record=apply_confirmation_record,
        trial_binding_id=trial_binding_id,
        owner_confirmation_value=owner_confirmation_value,
    )
    ready = (
        nested_apply.get("status")
        == apply_plan.READY_STATUS
        and nested_apply.get("checks", {}).get(
            "ready_for_owner_authorized_runtime_profile_apply"
        )
        is True
    )
    blockers = list(nested_apply.get("blockers") or [])
    return {
        "scope": "runtime_profile_trial_binding_apply_readiness",
        "status": READY_STATUS if ready else nested_apply.get("status", BLOCKED_STATUS),
        "strategy_family_id": apply_confirmation_record.get("strategy_family_id"),
        "strategy_family_version_id": strategy_family_version_id,
        "symbol": apply_confirmation_record.get("symbol"),
        "side": apply_confirmation_record.get("side"),
        "selected_trial_binding": selected,
        "candidate_trial_bindings": candidates,
        "apply_plan": nested_apply,
        "checks": {
            "ready_for_runtime_profile_apply_with_trial_binding": ready,
            "matching_trial_binding_found": True,
            "owner_confirmation_available": owner_confirmation_value is not None,
            "owner_confirmation_matches": nested_apply.get("owner_confirmation", {}).get(
                "matches"
            )
            is True,
            "api_apply_plan_ready": nested_apply.get("api_apply_plan") is not None,
            "blockers": blockers,
        },
        "blockers": blockers,
        "warnings": [
            "apply_readiness_does_not_submit_api_requests",
            (
                "input_was_rtf037_apply_plan"
                if apply_source_artifact is not apply_confirmation_record
                else "input_was_rtf036_confirmation_record"
            ),
            *list(nested_apply.get("warnings") or []),
        ],
        "safety_invariants": _safety_invariants(),
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Resolve a trial binding for RTF-037 apply readiness.",
    )
    parser.add_argument("--apply-confirmation-record-json", required=True)
    parser.add_argument("--trial-bindings-json", required=True)
    parser.add_argument("--owner-confirmation-value")
    parser.add_argument("--output-json")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    readiness = build_apply_readiness(
        apply_confirmation_record=_load_json(args.apply_confirmation_record_json),
        trial_bindings_payload=_load_json(args.trial_bindings_json),
        owner_confirmation_value=args.owner_confirmation_value,
    )
    payload = json.dumps(readiness, ensure_ascii=False, indent=2, sort_keys=True, default=str)
    if args.output_json:
        output_path = Path(args.output_json).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 2 if readiness["status"] == BLOCKED_STATUS else 0


if __name__ == "__main__":
    raise SystemExit(main())
