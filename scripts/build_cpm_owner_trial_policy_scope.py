#!/usr/bin/env python3
"""Record final-owned CPM Owner trial policy scope.

This artifact records the CPM-LONG trial boundary. It is non-executing: it
does not mutate registry, tier policy, runtime profile, order sizing, FinalGate,
Operation Layer, or exchange state.
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
    non_executing_interaction,
    non_executing_safety_invariants,
)


DEFAULT_IDENTITY_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-cpm-identity-routing-decision.json"
)
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-cpm-owner-trial-policy-scope.json"
)
DEFAULT_OUTPUT_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-cpm-owner-trial-policy-scope.md"
)

SCHEMA = "brc.cpm_owner_trial_policy_scope.v1"
STRATEGY_GROUP_ID = "CPM-RO-001"

OWNER_POLICY = {
    "strategy_group_id": STRATEGY_GROUP_ID,
    "trial_identity": "CPM_LONG_PULLBACK_RECLAIM_TRIAL_V0",
    "capital_scope": {
        "type": "isolated_subaccount_full_allocation",
        "allocation_mode": "full_available_isolated_subaccount",
        "amount_source": "action_time_exchange_available_balance",
        "currency": "USDT",
        "loss_capable": True,
    },
    "side_scope": ["long"],
    "symbol_scope": "cpm_research_supported_symbols_only",
    "leverage_scenario": "5x_scenario_not_authority",
    "max_notional": {
        "currency": "USDT",
        "calculation": "action_time_exchange_available_balance * leverage_scenario",
        "balance_source": "action_time_exchange_available_balance",
        "final_authority": "runtime_profile_and_action_time_exchange_facts",
    },
    "attempt_cap": 3,
    "loss_unit": {
        "currency": "USDT",
        "calculation": "action_time_exchange_available_balance / attempt_cap",
        "balance_source": "action_time_exchange_available_balance",
    },
    "daily_loss_cap_units": 1,
    "max_consecutive_losses": 2,
    "valid_until": "one_review_cycle",
    "pause_conditions": [
        "reclaim_failed_after_entry_without_review",
        "two_consecutive_losses",
        "symbol_specific_loss_until_symbol_review",
        "missing_required_path_or_liquidity_evidence",
    ],
    "authority_boundary": (
        "owner_policy_only; finalgate_required; operation_layer_required; "
        "no_exchange_write"
    ),
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--identity-json", default=str(DEFAULT_IDENTITY_JSON))
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-owner-progress", default=str(DEFAULT_OUTPUT_MD))
    args = parser.parse_args(argv)

    artifact = build_cpm_owner_trial_policy_scope(
        identity_decision=_read_optional_json(Path(args.identity_json))
    )
    output_json = Path(args.output_json)
    output_md = Path(args.output_owner_progress)
    _write_json(output_json, artifact)
    _write_text(output_md, _markdown(artifact, output_json))
    print(
        json.dumps(
            {
                "status": artifact["status"],
                "strategy_group_id": artifact["policy"]["strategy_group_id"],
                "owner_policy_recorded": artifact["owner_policy_recorded"],
                "output_json": str(output_json),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if artifact["owner_policy_recorded"] else 2


def build_cpm_owner_trial_policy_scope(
    *,
    identity_decision: dict[str, Any] | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    identity_ready = (
        (identity_decision or {}).get("status")
        == "cpm_identity_routing_decision_ready"
        and (identity_decision or {}).get("identity_decision")
        == "standalone_trial_asset"
    )
    return {
        "schema": SCHEMA,
        "scope": "final_owned_cpm_owner_trial_policy_scope_non_executing",
        "status": (
            "cpm_owner_trial_policy_scope_recorded"
            if identity_ready
            else "cpm_owner_trial_policy_scope_blocked_identity"
        ),
        "generated_at_utc": generated_at_utc
        or datetime.now(timezone.utc).isoformat(),
        "policy": OWNER_POLICY,
        "cpm_policy_scope_recorded": identity_ready,
        "owner_policy_recorded": identity_ready,
        "owner_policy_scope_missing": not identity_ready,
        "cpm_stage_after_policy": "admitted_trial_asset",
        "cpm_new_first_blocker": "cpm_required_facts_mapping_gap",
        "checks": {
            "identity_decision_standalone_trial_asset": identity_ready,
            "capital_scope_balance_source": "action_time_exchange_available_balance",
            "side_scope_long_only": True,
            "max_notional_source": "runtime_profile_and_action_time_exchange_facts",
            "leverage_scenario_is_not_authority": True,
            "loss_unit_source": "action_time_exchange_available_balance",
        },
        "interaction": non_executing_interaction("L0_local_cpm_owner_policy"),
        "safety_invariants": non_executing_safety_invariants(
            (
                "registry_authority_changed",
                "tier_policy_changed",
                "live_profile_changed",
                "order_sizing_changed",
            ),
            include_authority_mirrors=False,
        ),
    }


def _markdown(artifact: dict[str, Any], output_json: Path) -> str:
    policy = artifact["policy"]
    return "\n".join(
        [
            "## CPM Owner Trial Policy Scope",
            "",
            f"- Status: `{artifact['status']}`",
            f"- StrategyGroup: `{policy['strategy_group_id']}`",
            f"- Trial identity: `{policy['trial_identity']}`",
            f"- Owner policy recorded: `{_yes_no(artifact['owner_policy_recorded'])}`",
            f"- Capital source: `{policy['capital_scope']['amount_source']}`",
            f"- Output JSON: `{output_json}`",
            "",
            "## Boundary",
            "",
            "- Owner policy only; no FinalGate or Operation Layer call.",
            "- No fixed nominal amount is introduced.",
        ]
    ) + "\n"


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
