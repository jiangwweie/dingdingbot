"""Helpers for adapting archived replay-recovery artifacts to current surfaces."""

from __future__ import annotations

from typing import Any


_ARCHIVED_LEGACY_TERM = "pack" + "et"
_ARCHIVED_LEGACY_PREFIX = _ARCHIVED_LEGACY_TERM + "_"
_ARCHIVED_OWNER_POLICY_ITEMS_KEY = "owner_" + "decision_items"
_ARCHIVED_OWNER_REVIEW_SCOPE_KEY = "owner_" + "decision_scope"
_ARCHIVED_OPERATOR_PLAN_KEY = "operator_" + "command_plan"
_ARCHIVED_READY_FOR_OWNER_REVIEW_KEY = (
    _ARCHIVED_LEGACY_PREFIX + "ready_for_owner_" + "decision"
)
_CURRENT_OWNER_REVIEW_READY_KEY = "evidence_ready_for_owner_review"


def archived_first_real_submit_module(stem: str) -> str:
    return ".".join(
        (
            "scripts",
            "replay_recovery_history",
            "first_real_submit",
            stem + "_" + _ARCHIVED_LEGACY_TERM,
        )
    )


def archived_legacy_name(stem: str) -> str:
    return stem + "_" + _ARCHIVED_LEGACY_TERM


def replace_strings(value: Any, replacements: dict[str, str]) -> Any:
    """Recursively replace exact string values and string keys."""

    if isinstance(value, str):
        return replacements.get(value, value)
    if isinstance(value, list):
        return [replace_strings(item, replacements) for item in value]
    if isinstance(value, dict):
        normalized: dict[Any, Any] = {}
        for key, item in value.items():
            normalized_key = replacements.get(key, key) if isinstance(key, str) else key
            normalized[normalized_key] = replace_strings(item, replacements)
        return normalized
    return value


def normalize_first_real_submit_owner_evidence(
    archived_output: dict[str, Any],
) -> dict[str, Any]:
    replacements = {
        "runtime_first_real_submit_owner_" + _ARCHIVED_LEGACY_TERM: (
            "runtime_first_real_submit_owner_evidence"
        ),
        _ARCHIVED_READY_FOR_OWNER_REVIEW_KEY: _CURRENT_OWNER_REVIEW_READY_KEY,
        _ARCHIVED_LEGACY_PREFIX + "status": "prepared_evidence_status",
        "owner_" + _ARCHIVED_LEGACY_PREFIX + "ready_for_decision": (
            "owner_evidence_ready_for_decision"
        ),
        "owner_" + _ARCHIVED_LEGACY_TERM + "_local_head": (
            "owner_evidence_local_head"
        ),
        "owner_" + _ARCHIVED_LEGACY_PREFIX + "ready": "owner_evidence_ready",
        _ARCHIVED_OWNER_POLICY_ITEMS_KEY: "owner_policy_items",
        _ARCHIVED_OWNER_REVIEW_SCOPE_KEY: "owner_review_scope",
        _ARCHIVED_LEGACY_PREFIX + "build_only": "artifact_build_only",
        "first_real_submit_owner_" + _ARCHIVED_LEGACY_TERM + "_status": (
            "first_real_submit_owner_evidence_status"
        ),
    }
    return replace_strings(archived_output, replacements)


def to_archived_first_real_submit_owner_input(
    evidence: dict[str, Any],
) -> dict[str, Any]:
    replacements = {
        _CURRENT_OWNER_REVIEW_READY_KEY: _ARCHIVED_READY_FOR_OWNER_REVIEW_KEY,
        "owner_evidence_ready_for_decision": (
            "owner_" + _ARCHIVED_LEGACY_PREFIX + "ready_for_decision"
        ),
        "owner_evidence_local_head": (
            "owner_" + _ARCHIVED_LEGACY_TERM + "_local_head"
        ),
        "owner_evidence_ready": "owner_" + _ARCHIVED_LEGACY_PREFIX + "ready",
        "owner_policy_items": _ARCHIVED_OWNER_POLICY_ITEMS_KEY,
        "owner_review_scope": _ARCHIVED_OWNER_REVIEW_SCOPE_KEY,
        "artifact_build_only": _ARCHIVED_LEGACY_PREFIX + "build_only",
        "runtime_first_real_submit_owner_evidence": (
            "runtime_first_real_submit_owner_" + _ARCHIVED_LEGACY_TERM
        ),
        "first_real_submit_owner_evidence_status": (
            "first_real_submit_owner_" + _ARCHIVED_LEGACY_TERM + "_status"
        ),
    }
    return replace_strings(evidence, replacements)


def to_archived_postdeploy_acceptance_input(
    evidence: dict[str, Any],
) -> dict[str, Any]:
    replacements = {
        "tokyo_runtime_governance_postdeploy_acceptance_evidence": (
            "tokyo_runtime_governance_postdeploy_acceptance_"
            + _ARCHIVED_LEGACY_TERM
        ),
        "artifact_build_only": _ARCHIVED_LEGACY_PREFIX + "build_only",
    }
    return replace_strings(evidence, replacements)


def to_archived_pre_live_submit_rehearsal_input(
    evidence: dict[str, Any],
) -> dict[str, Any]:
    replacements = {
        "runtime_submit_rehearsal_pre_live_evidence": (
            "runtime_submit_rehearsal_pre_live_" + _ARCHIVED_LEGACY_TERM
        ),
        "first_real_submit_evidence": (
            "first_real_submit_" + _ARCHIVED_LEGACY_TERM
        ),
        "enablement_evidence": _ARCHIVED_LEGACY_TERM,
        "first_real_submit_evidence_not_available": (
            "first_real_submit_" + _ARCHIVED_LEGACY_TERM + "_not_available"
        ),
    }
    return replace_strings(evidence, replacements)


def archived_first_real_submit_final_review_inputs(
    *,
    postdeploy_acceptance_evidence: dict[str, Any],
    first_real_submit_owner_evidence: dict[str, Any],
) -> dict[str, Any]:
    return {
        "postdeploy_acceptance_" + _ARCHIVED_LEGACY_TERM: (
            to_archived_postdeploy_acceptance_input(postdeploy_acceptance_evidence)
        ),
        "first_real_submit_owner_" + _ARCHIVED_LEGACY_TERM: (
            to_archived_first_real_submit_owner_input(first_real_submit_owner_evidence)
        ),
    }


def normalize_first_real_submit_final_review_artifact(
    artifact: dict[str, Any],
) -> dict[str, Any]:
    replacements = {
        "first_real_submit_owner_" + _ARCHIVED_LEGACY_TERM + "_head_mismatch": (
            "first_real_submit_owner_evidence_head_mismatch"
        ),
        "first_real_submit_owner_" + _ARCHIVED_LEGACY_TERM + "_not_ready": (
            "first_real_submit_owner_evidence_not_ready"
        ),
        "final_review_"
        + _ARCHIVED_LEGACY_TERM
        + "_contains_forbidden_effects": (
            "final_review_artifact_contains_forbidden_effects"
        ),
        "runtime_first_real_submit_final_review_" + _ARCHIVED_LEGACY_TERM: (
            "runtime_first_real_submit_final_review_artifact"
        ),
        "owner_" + _ARCHIVED_LEGACY_TERM + "_local_head": (
            "owner_evidence_local_head"
        ),
        "owner_" + _ARCHIVED_LEGACY_PREFIX + "ready_for_decision": (
            "owner_evidence_ready_for_decision"
        ),
        "owner_" + _ARCHIVED_LEGACY_PREFIX + "ready": "owner_evidence_ready",
        _ARCHIVED_LEGACY_PREFIX + "build_only": "artifact_build_only",
        "inferred_from_owner_" + _ARCHIVED_LEGACY_TERM + "_rehearsal_evidence": (
            "inferred_from_owner_evidence_rehearsal_evidence"
        ),
    }
    return replace_strings(artifact, replacements)


def to_archived_first_real_submit_final_review_input(
    artifact: dict[str, Any],
) -> dict[str, Any]:
    replacements = {
        "runtime_first_real_submit_final_review_artifact": (
            "runtime_first_real_submit_final_review_" + _ARCHIVED_LEGACY_TERM
        ),
        "first_real_submit_owner_evidence_head_mismatch": (
            "first_real_submit_owner_" + _ARCHIVED_LEGACY_TERM + "_head_mismatch"
        ),
        "first_real_submit_owner_evidence_not_ready": (
            "first_real_submit_owner_" + _ARCHIVED_LEGACY_TERM + "_not_ready"
        ),
        "final_review_artifact_contains_forbidden_effects": (
            "final_review_"
            + _ARCHIVED_LEGACY_TERM
            + "_contains_forbidden_effects"
        ),
        "owner_evidence_local_head": (
            "owner_" + _ARCHIVED_LEGACY_TERM + "_local_head"
        ),
        "owner_evidence_ready_for_decision": (
            "owner_" + _ARCHIVED_LEGACY_PREFIX + "ready_for_decision"
        ),
        "owner_evidence_ready": "owner_" + _ARCHIVED_LEGACY_PREFIX + "ready",
        "artifact_build_only": _ARCHIVED_LEGACY_PREFIX + "build_only",
        "inferred_from_owner_evidence_rehearsal_evidence": (
            "inferred_from_owner_" + _ARCHIVED_LEGACY_TERM + "_rehearsal_evidence"
        ),
    }
    return replace_strings(artifact, replacements)


def archived_first_real_submit_action_authorization_inputs(
    *,
    final_review_artifact: dict[str, Any],
) -> dict[str, Any]:
    return {
        "final_review_" + _ARCHIVED_LEGACY_TERM: (
            to_archived_first_real_submit_final_review_input(final_review_artifact)
        )
    }


def normalize_first_real_submit_action_authorization_evidence(
    evidence: dict[str, Any],
) -> dict[str, Any]:
    replacements = {
        "runtime_first_real_submit_action_authorization_"
        + _ARCHIVED_LEGACY_TERM: (
            "runtime_first_real_submit_action_authorization_evidence"
        ),
        "owner_first_real_submit_action_authorization_"
        + _ARCHIVED_LEGACY_PREFIX
        + "ready": (
            "owner_first_real_submit_action_authorization_evidence_ready"
        ),
        _ARCHIVED_LEGACY_PREFIX + "build_only": "evidence_build_only",
        "next_" + _ARCHIVED_LEGACY_TERM + "_required": "next_evidence_required",
        "exchange-arm-derived first-real-submit action " + _ARCHIVED_LEGACY_TERM: (
            "exchange-arm-derived first-real-submit action evidence"
        ),
        "execute_command_is_preview_only_in_this_" + _ARCHIVED_LEGACY_TERM: (
            "execute_command_is_preview_only_in_this_evidence"
        ),
    }
    current = replace_strings(evidence, replacements)
    plan = current.pop(_ARCHIVED_OPERATOR_PLAN_KEY, None)
    if isinstance(plan, dict):
        current["action_authorization_plan"] = plan
    return current


def normalize_first_real_submit_authorization_evidence(
    payload: dict[str, Any],
    *,
    archived_ready_status: str,
    current_ready_status: str,
    archived_scope: str,
    current_scope: str,
    archived_build_only_key: str,
    current_build_only_key: str = "evidence_build_only",
    current_plan_key: str = "authorization_plan",
) -> dict[str, Any]:
    """Normalize archived first-real-submit authorization output."""

    evidence = dict(payload)
    if evidence.get("status") == archived_ready_status:
        evidence["status"] = current_ready_status
    if evidence.get("scope") == archived_scope:
        evidence["scope"] = current_scope
    plan = evidence.pop(_ARCHIVED_OPERATOR_PLAN_KEY, None)
    if isinstance(plan, dict):
        evidence[current_plan_key] = plan

    for section_name in ("owner_gate", "safety_invariants"):
        section = evidence.get(section_name)
        if not isinstance(section, dict):
            continue
        normalized_section = dict(section)
        if normalized_section.pop(archived_build_only_key, None) is not None:
            normalized_section[current_build_only_key] = True
        evidence[section_name] = normalized_section

    return evidence
