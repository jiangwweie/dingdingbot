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
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_CAPITAL_TRIAL_BRIDGE_JSON = (
    REPO_ROOT
    / "output/runtime-monitor/latest-strategygroup-capital-trial-readiness-bridge.json"
)
DEFAULT_TRIAL_PACKET_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-strategygroup-capital-trial-packet-v0.json"
)
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT
    / "output/runtime-monitor/latest-strategygroup-trial-asset-admission-proposal.json"
)
DEFAULT_OUTPUT_MD = (
    REPO_ROOT
    / "output/runtime-monitor/latest-strategygroup-trial-asset-admission-proposal.md"
)
DEFAULT_BRF2_OWNER_TRIAL_POLICY_SCOPE_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-brf2-owner-trial-policy-scope.json"
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--capital-trial-readiness-bridge-json",
        default=str(DEFAULT_CAPITAL_TRIAL_BRIDGE_JSON),
    )
    parser.add_argument(
        "--trial-packet-json",
        default=str(DEFAULT_TRIAL_PACKET_JSON),
    )
    parser.add_argument(
        "--brf2-owner-trial-policy-scope-json",
        default=str(DEFAULT_BRF2_OWNER_TRIAL_POLICY_SCOPE_JSON),
    )
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-owner-progress", default=str(DEFAULT_OUTPUT_MD))
    args = parser.parse_args(argv)

    packet = build_trial_asset_admission_proposal(
        capital_trial_bridge=_read_json(Path(args.capital_trial_readiness_bridge_json)),
        trial_packet=_read_json(Path(args.trial_packet_json)),
        brf2_owner_trial_policy_scope=_read_optional_json(
            Path(args.brf2_owner_trial_policy_scope_json)
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
                "strategy_group_id": packet["proposal"].get("strategy_group_id"),
                "owner_policy_required": packet["proposal"].get(
                    "owner_policy_required"
                ),
                "output_json": str(output_json),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if packet["status"] == "trial_asset_admission_proposal_ready" else 2


def build_trial_asset_admission_proposal(
    *,
    capital_trial_bridge: dict[str, Any],
    trial_packet: dict[str, Any],
    brf2_owner_trial_policy_scope: dict[str, Any] | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    selected = _as_dict(capital_trial_bridge.get("selected_non_mpg_trial_candidate"))
    strategy_group_id = str(
        selected.get("strategy_group_id") or trial_packet.get("strategy_group_id") or ""
    )
    proposal = (
        _proposal(
            strategy_group_id=strategy_group_id,
            selected=selected,
            trial_packet=trial_packet,
            brf2_owner_trial_policy_scope=brf2_owner_trial_policy_scope or {},
        )
        if strategy_group_id
        else {}
    )
    owner_policy_recorded = _policy_recorded(
        strategy_group_id=strategy_group_id,
        packet=brf2_owner_trial_policy_scope or {},
    )
    status = (
        "trial_asset_admission_proposal_ready"
        if proposal and not _forbidden_effects(capital_trial_bridge, trial_packet)
        else "trial_asset_admission_proposal_needs_input"
    )
    forbidden_effects = _forbidden_effects(capital_trial_bridge, trial_packet)
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
            "owner_decision_required_now": False,
            "owner_intervention_required": False,
        },
        "checks": {
            "proposal_generated": bool(proposal),
            "registry_policy_mutated": False,
            "tier_policy_mutated": False,
            "runtime_profile_mutated": False,
            "order_sizing_mutated": False,
            "actionable_now": False,
            "real_order_authority": False,
            "owner_policy_required": bool(proposal) and not owner_policy_recorded,
            "owner_policy_recorded": owner_policy_recorded,
            "owner_policy_scope_missing": bool(proposal) and not owner_policy_recorded,
            "owner_decision_required": False,
            "forbidden_effects": forbidden_effects,
        },
        "interaction": _interaction(),
        "safety_invariants": {
            "actionable_now": False,
            "real_order_authority": False,
            "registry_authority_changed": False,
            "tier_policy_changed": False,
            "live_profile_changed": False,
            "order_sizing_changed": False,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
        },
    }


def _proposal(
    *,
    strategy_group_id: str,
    selected: dict[str, Any],
    trial_packet: dict[str, Any],
    brf2_owner_trial_policy_scope: dict[str, Any],
) -> dict[str, Any]:
    required_facts = _string_list(
        selected.get("required_facts_draft") or trial_packet.get("required_facts_draft")
    )
    disable_facts = _string_list(
        selected.get("disable_or_review_facts_draft")
        or trial_packet.get("disable_or_review_facts_draft")
    )
    risk_envelope = _as_dict(selected.get("risk_envelope")) or _as_dict(
        trial_packet.get("risk_envelope")
    )
    side_scope = _string_list(selected.get("side_scope") or trial_packet.get("side_scope"))
    symbol_scope = _string_list(
        selected.get("symbol_scope") or trial_packet.get("symbol_scope")
    )
    owner_policy_recorded = _policy_recorded(
        strategy_group_id=strategy_group_id,
        packet=brf2_owner_trial_policy_scope,
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
    next_action = (
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
                "actionable_now=false; real_order_authority=false"
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
        "next_action": next_action,
        "after_next_state": after_next_state,
        "actionable_now": False,
        "real_order_authority": False,
    }


def _policy_recorded(*, strategy_group_id: str, packet: dict[str, Any]) -> bool:
    policy = _as_dict(packet.get("policy"))
    return (
        strategy_group_id == "BRF2-001"
        and packet.get("status") == "brf2_owner_trial_policy_scope_recorded"
        and packet.get("brf2_policy_scope_recorded") is True
        and packet.get("owner_policy_scope_missing") is False
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
        "authority_boundary": policy.get("authority_boundary"),
    }


def _markdown(packet: dict[str, Any], output_json: Path) -> str:
    proposal = _as_dict(packet.get("proposal"))
    fields = _string_list(
        _as_dict(packet.get("owner_policy_checkpoint")).get("owner_policy_fields")
    )
    lines = [
        "## StrategyGroup Trial Asset Admission Proposal",
        "",
        f"- Status: `{packet['status']}`",
        f"- Generated: `{packet['generated_at_utc']}`",
        f"- Output JSON: `{output_json}`",
        f"- StrategyGroup: `{proposal.get('strategy_group_id', 'none')}`",
        f"- Current stage: `{proposal.get('current_stage', 'none')}`",
        f"- Proposed stage: `{proposal.get('proposed_stage', 'none')}`",
        f"- Owner policy required: `{_yes_no(proposal.get('owner_policy_required') is True)}`",
        f"- Owner policy recorded: `{_yes_no(proposal.get('owner_policy_recorded') is True)}`",
        f"- Next action: `{proposal.get('next_action', 'none')}`",
        f"- Real order authority: `{_yes_no(False)}`",
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


def _forbidden_effects(*packets: dict[str, Any]) -> list[str]:
    found: list[str] = []
    for index, packet in enumerate(packets):
        _walk(packet, prefix=f"source[{index}]", found=found)
    return list(dict.fromkeys(found))


def _walk(value: Any, *, prefix: str, found: list[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}.{key}"
            if key in {
                "actionable_now",
                "real_order_authority",
                "calls_finalgate",
                "calls_operation_layer",
                "calls_exchange_write",
                "places_order",
                "registry_authority_changed",
                "tier_policy_changed",
                "live_profile_changed",
                "order_sizing_changed",
            } and item is True:
                found.append(path)
            _walk(item, prefix=path, found=found)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _walk(item, prefix=f"{prefix}[{index}]", found=found)


def _interaction() -> dict[str, Any]:
    return {
        "level": "L0_local_trial_asset_admission_proposal",
        "remote_interaction_count": 0,
        "mutates_remote_files": False,
        "approaches_real_order": False,
        "calls_finalgate": False,
        "calls_operation_layer": False,
        "calls_exchange_write": False,
        "places_order": False,
    }


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
