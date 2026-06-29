#!/usr/bin/env python3
"""Build a non-applying StrategyGroup trial asset admission proposal.

This converts the selected capital-trial intake candidate into a final-owned
trial asset admission proposal. It does not mutate registry, tier policy,
runtime profile, order sizing, FinalGate, Operation Layer, or exchange state.
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
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from strategygroup_non_executing_projection import (  # noqa: E402
    LEGACY_AUTHORITY_MIRROR_KEYS,
    non_executing_interaction,
    non_executing_safety_invariants,
    recursive_true_key_paths,
)

DEFAULT_OUTPUT_JSON = (
    REPO_ROOT
    / "output/runtime-monitor/latest-strategygroup-trial-asset-admission-proposal.json"
)
DEFAULT_OUTPUT_MD = (
    REPO_ROOT
    / "output/runtime-monitor/latest-strategygroup-trial-asset-admission-proposal.md"
)
SCHEMA = "brc.strategygroup_trial_asset_admission_proposal.v1"

OWNER_POLICY_FIELDS = (
    "capital_scope",
    "max_notional",
    "valid_until",
    "slippage_limit",
    "trial_identity",
    "symbol_scope",
    "side_scope",
    "leverage_scenario",
    "attempt_cap",
    "loss_unit",
)

LEGACY_AUTHORITY_MIRROR_TRUE_KEYS = LEGACY_AUTHORITY_MIRROR_KEYS


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--capital-trial-envelope-projection-json",
    )
    parser.add_argument(
        "--trial-envelope-json",
    )
    parser.add_argument(
        "--brf2-owner-trial-policy-scope-json",
    )
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-owner-progress", default=str(DEFAULT_OUTPUT_MD))
    args = parser.parse_args(argv)

    proposal_artifact = build_trial_asset_admission_proposal(
        capital_trial_envelope_projection=_read_optional_json(
            Path(args.capital_trial_envelope_projection_json)
        )
        if args.capital_trial_envelope_projection_json
        else {},
        trial_envelope=_read_optional_json(Path(args.trial_envelope_json))
        if args.trial_envelope_json
        else {},
        brf2_owner_trial_policy_scope=_read_optional_json(
            Path(args.brf2_owner_trial_policy_scope_json)
        )
        if args.brf2_owner_trial_policy_scope_json
        else {},
    )
    output_json = Path(args.output_json)
    output_md = Path(args.output_owner_progress)
    _write_json(output_json, proposal_artifact)
    _write_text(output_md, _markdown(proposal_artifact, output_json))
    print(
        json.dumps(
            {
                "status": proposal_artifact["status"],
                "strategy_group_id": proposal_artifact["proposal"].get("strategy_group_id"),
                "owner_policy_required": proposal_artifact["proposal"].get(
                    "owner_policy_required"
                ),
                "output_json": str(output_json),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return (
        0
        if proposal_artifact["status"] == "trial_asset_admission_proposal_ready"
        else 2
    )


def build_trial_asset_admission_proposal(
    *,
    capital_trial_envelope_projection: dict[str, Any],
    trial_envelope: dict[str, Any],
    brf2_owner_trial_policy_scope: dict[str, Any] | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    selected = _as_dict(capital_trial_envelope_projection.get("selected_non_mpg_trial_candidate"))
    strategy_group_id = str(
        selected.get("strategy_group_id") or trial_envelope.get("strategy_group_id") or ""
    )
    proposal = (
        _proposal(
            strategy_group_id=strategy_group_id,
            selected=selected,
            trial_envelope=trial_envelope,
            brf2_owner_trial_policy_scope=brf2_owner_trial_policy_scope or {},
        )
        if strategy_group_id
        else {}
    )
    owner_policy_recorded = _policy_recorded(
        strategy_group_id=strategy_group_id,
        artifact=brf2_owner_trial_policy_scope or {},
    )
    status = (
        "trial_asset_admission_proposal_ready"
        if proposal and not _forbidden_effects(capital_trial_envelope_projection, trial_envelope)
        else "trial_asset_admission_proposal_needs_input"
    )
    forbidden_effects = _forbidden_effects(capital_trial_envelope_projection, trial_envelope)
    if forbidden_effects:
        status = "blocked_forbidden_effect"
    return {
        "schema": SCHEMA,
        "scope": "strategygroup_trial_asset_admission_proposal_non_applying",
        "status": status,
        "generated_at_utc": generated_at_utc
        or datetime.now(timezone.utc).isoformat(),
        "proposal": proposal,
        "owner_policy_checkpoint": {
            "owner_policy_required": bool(proposal) and not owner_policy_recorded,
            "owner_policy_recorded": owner_policy_recorded,
            "owner_policy_scope_missing": bool(proposal) and not owner_policy_recorded,
            "owner_policy_fields": list(OWNER_POLICY_FIELDS) if proposal else [],
            "owner_policy_confirmation_required_now": False,
            "owner_intervention_required": False,
        },
        "checks": {
            "proposal_generated": bool(proposal),
            "registry_policy_mutated": False,
            "tier_policy_mutated": False,
            "runtime_profile_mutated": False,
            "order_sizing_mutated": False,
            "owner_policy_required": bool(proposal) and not owner_policy_recorded,
            "owner_policy_recorded": owner_policy_recorded,
            "owner_policy_scope_missing": bool(proposal) and not owner_policy_recorded,
            "owner_policy_confirmation_required": False,
            "forbidden_effects": forbidden_effects,
        },
        "interaction": _interaction(),
        "safety_invariants": _safety_invariants(),
    }


def _proposal(
    *,
    strategy_group_id: str,
    selected: dict[str, Any],
    trial_envelope: dict[str, Any],
    brf2_owner_trial_policy_scope: dict[str, Any],
) -> dict[str, Any]:
    required_facts = _string_list(
        selected.get("required_facts_draft") or trial_envelope.get("required_facts_draft")
    )
    disable_facts = _string_list(
        selected.get("disable_or_review_facts_draft")
        or trial_envelope.get("disable_or_review_facts_draft")
    )
    risk_envelope = _as_dict(selected.get("risk_envelope")) or _as_dict(
        trial_envelope.get("risk_envelope")
    )
    side_scope = _string_list(selected.get("side_scope") or trial_envelope.get("side_scope"))
    symbol_scope = _string_list(
        selected.get("symbol_scope") or trial_envelope.get("symbol_scope")
    )
    owner_policy_recorded = _policy_recorded(
        strategy_group_id=strategy_group_id,
        artifact=brf2_owner_trial_policy_scope,
    )
    owner_policy = _as_dict(brf2_owner_trial_policy_scope.get("policy"))
    owner_defaults = (
        _owner_policy_defaults(owner_policy)
        if owner_policy_recorded
        else {
            "capital_scope": "owner_policy_required",
            "max_notional": "owner_policy_required",
            "valid_until": "owner_policy_required",
            "slippage_limit": "owner_policy_required",
            "trial_identity": "owner_policy_required",
            "symbol_scope": symbol_scope or ["owner_policy_required"],
            "side_scope": side_scope or ["short"],
            "leverage_scenario": "owner_policy_required",
            "attempt_cap": risk_envelope.get(
                "attempt_cap_per_review_cycle", "owner_policy_required"
            ),
            "loss_unit": risk_envelope.get(
                "daily_loss_cap_units", "owner_policy_required"
            ),
        }
    )
    proposed_stage = (
        "admitted_trial_asset"
        if owner_policy_recorded
        else "trial_asset_admission_candidate"
    )
    non_authority_checkpoint = (
        "close_brf2_required_facts_mapping_for_armed_observation"
        if owner_policy_recorded
        else "record_owner_trial_scope_policy"
    )
    after_next_state = "armed_observation" if owner_policy_recorded else "admitted_trial_asset"
    return {
        "strategy_group_id": strategy_group_id,
        "current_stage": "tiny_live_intake_candidate",
        "proposed_stage": proposed_stage,
        "proposal_type": "non_applying_registry_tier_runtime_admission_draft",
        "owner_policy_required": not owner_policy_recorded,
        "owner_policy_recorded": owner_policy_recorded,
        "owner_policy_scope_missing": not owner_policy_recorded,
        "owner_policy_fields": list(OWNER_POLICY_FIELDS),
        "owner_policy_defaults": owner_defaults,
        "proposed_registry_row": {
            "strategy_group_id": strategy_group_id,
            "default_tier": "trial_admission",
            "trial_eligible": False,
            "supported_sides": side_scope or ["short"],
            "evidence_status": "trial_asset_admission_proposal",
            "required_facts_summary": {
                "strategy": required_facts,
                "disable_or_review": disable_facts,
            },
            "risk_envelope": risk_envelope,
            "authority_boundary": (
                "proposal_only; not_registry_authority; not_runtime_admission; "
                "finalgate_required; operation_layer_required; no_exchange_write"
            ),
        },
        "proposed_tier_policy_row": {
            "tier": "trial_admission",
            "mode": proposed_stage,
            "reason": (
                "Owner trial scope recorded; RequiredFacts mapping remains before armed observation"
                if owner_policy_recorded
                else "Owner policy and scoped risk boundary required before armed observation"
            ),
        },
        "runtime_admission_plan": {
            "watcher_scope": "short_read_only_or_armed_observation_after_policy",
            "required_facts_draft": required_facts,
            "disable_or_review_facts_draft": disable_facts,
            "fresh_signal_source": "future_runtime_observation_only",
            "protection_plan_required": True,
            "review_ledger_required": True,
        },
        "non_authority_checkpoint": non_authority_checkpoint,
        "after_next_state": after_next_state,
    }


def _policy_recorded(*, strategy_group_id: str, artifact: dict[str, Any]) -> bool:
    policy = _as_dict(artifact.get("policy"))
    return (
        strategy_group_id == "BRF2-001"
        and artifact.get("status") == "brf2_owner_trial_policy_scope_recorded"
        and artifact.get("brf2_policy_scope_recorded") is True
        and artifact.get("owner_policy_scope_missing") is False
        and policy.get("strategy_group_id") == "BRF2-001"
    )


def _owner_policy_defaults(policy: dict[str, Any]) -> dict[str, Any]:
    return {
        "capital_scope": _as_dict(policy.get("capital_scope")),
        "max_notional": _as_dict(policy.get("max_notional")),
        "valid_until": policy.get("valid_until"),
        "slippage_limit": "action_time_runtime_fact_required",
        "trial_identity": policy.get("trial_identity"),
        "symbol_scope": policy.get("symbol_scope"),
        "side_scope": _string_list(policy.get("side_scope")),
        "leverage_scenario": policy.get("leverage_scenario"),
        "attempt_cap": policy.get("attempt_cap"),
        "loss_unit": _as_dict(policy.get("loss_unit")),
        "daily_loss_cap_units": policy.get("daily_loss_cap_units"),
        "max_consecutive_losses": policy.get("max_consecutive_losses"),
        "pause_conditions": _string_list(policy.get("pause_conditions")),
        "authority_boundary": (
            "owner_policy_only; finalgate_required; operation_layer_required; "
            "no_exchange_write"
        ),
    }


def _markdown(artifact: dict[str, Any], output_json: Path) -> str:
    proposal = _as_dict(artifact.get("proposal"))
    fields = _string_list(
        _as_dict(artifact.get("owner_policy_checkpoint")).get("owner_policy_fields")
    )
    lines = [
        "## StrategyGroup Trial Asset Admission Proposal",
        "",
        f"- Status: `{artifact['status']}`",
        f"- Generated: `{artifact['generated_at_utc']}`",
        f"- Output JSON: `{output_json}`",
        f"- StrategyGroup: `{proposal.get('strategy_group_id', 'none')}`",
        f"- Current stage: `{proposal.get('current_stage', 'none')}`",
        f"- Proposed stage: `{proposal.get('proposed_stage', 'none')}`",
        f"- Owner policy required: `{_yes_no(proposal.get('owner_policy_required') is True)}`",
        f"- Owner policy recorded: `{_yes_no(proposal.get('owner_policy_recorded') is True)}`",
        f"- Next checkpoint: `{proposal.get('non_authority_checkpoint', 'none')}`",
        "",
        "## Owner Policy Fields",
        "",
        "| Field | Value |",
        "| --- | --- |",
    ]
    defaults = _as_dict(proposal.get("owner_policy_defaults"))
    for field in fields:
        lines.append(f"| `{field}` | `{defaults.get(field, 'owner_policy_required')}` |")
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "- This proposal is not applied to registry or tier policy.",
            "- It does not mutate live profile or order sizing.",
            "- It does not call FinalGate, Operation Layer, or exchange write.",
        ]
    )
    return "\n".join(lines) + "\n"


def _forbidden_effects(*artifacts: dict[str, Any]) -> list[str]:
    effects = recursive_true_key_paths(
        *artifacts,
        true_keys=(
            "calls_finalgate",
            "calls_operation_layer",
            "calls_exchange_write",
            "places_order",
            "registry_authority_changed",
            "tier_policy_changed",
            "live_profile_changed",
            "order_sizing_changed",
        ),
    )
    legacy_mirrors = [
        f"legacy_authority_mirror_present:{path}"
        for path in recursive_true_key_paths(
            *artifacts,
            true_keys=LEGACY_AUTHORITY_MIRROR_TRUE_KEYS,
        )
    ]
    return [*effects, *legacy_mirrors]


def _interaction() -> dict[str, Any]:
    return non_executing_interaction("L0_local_trial_asset_admission_proposal")


def _safety_invariants() -> dict[str, bool]:
    return non_executing_safety_invariants(
        (
            "registry_authority_changed",
            "tier_policy_changed",
        ),
        include_withdrawal_or_transfer=False,
    )


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return _read_json(path)


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
