#!/usr/bin/env python3
"""Record the final-owned BRF2 Owner trial policy scope.

This artifact records the Owner-approved BRF2 small-capital trial boundary. It
is non-executing: it does not mutate registry, tier policy, runtime profile,
order sizing, FinalGate, Operation Layer, or exchange state.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_DOCS_JSON = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/brf2-owner-trial-policy-scope-v0.json"
)
DEFAULT_DOCS_MD = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/brf2-owner-trial-policy-scope-v0.md"
)
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-brf2-owner-trial-policy-scope.json"
)
DEFAULT_OUTPUT_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-brf2-owner-trial-policy-scope.md"
)

SCHEMA = "brc.brf2_owner_trial_policy_scope.v0"


OWNER_POLICY = {
    "strategy_group_id": "BRF2-001",
    "trial_identity": "BRF2_TINY_SHORT_TRIAL_30U_V0",
    "capital_scope": {
        "type": "isolated_subaccount_full_allocation",
        "amount": "30",
        "currency": "USDT",
        "loss_capable": True,
    },
    "side_scope": ["short"],
    "symbol_scope": "brf2_research_supported_symbols_only",
    "leverage_scenario": "5x_scenario_not_authority",
    "max_notional": {
        "amount": "150",
        "currency": "USDT",
        "basis": "30U capital x 5x scenario",
        "final_authority": "runtime_profile_and_action_time_exchange_facts",
    },
    "attempt_cap": 3,
    "loss_unit": {
        "amount": "10",
        "currency": "USDT",
        "basis": "30U / 3 attempts",
    },
    "daily_loss_cap_units": 1,
    "max_consecutive_losses": 2,
    "valid_until": "one_review_cycle",
    "pause_conditions": [
        "any_path_stop_without_post_trade_review",
        "two_consecutive_losses",
        "symbol_specific_loss_until_symbol_review",
        "missing_required_path_or_liquidation_buffer_evidence",
    ],
    "authority_boundary": (
        "owner_policy_only; actionable_now=false; real_order_authority=false; "
        "finalgate_required; operation_layer_required"
    ),
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-owner-progress", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--policy-json", default=str(DEFAULT_DOCS_JSON))
    parser.add_argument("--docs-json", default=str(DEFAULT_DOCS_JSON))
    parser.add_argument("--docs-md", default=str(DEFAULT_DOCS_MD))
    parser.add_argument(
        "--write-docs",
        action="store_true",
        help=(
            "Write the docs/current authority record. Default monitor mode only "
            "reads the authority record and refreshes output/runtime-monitor."
        ),
    )
    args = parser.parse_args(argv)

    packet = (
        build_brf2_owner_trial_policy_scope()
        if args.write_docs
        else build_brf2_owner_trial_policy_scope_view(Path(args.policy_json))
    )
    output_json = Path(args.output_json)
    output_md = Path(args.output_owner_progress)
    docs_json = Path(args.docs_json)
    docs_md = Path(args.docs_md)
    _write_json(output_json, packet)
    _write_text(output_md, _markdown(packet, output_json))
    if args.write_docs:
        _write_json(docs_json, packet)
        _write_text(docs_md, _markdown(packet, docs_json))
    print(
        json.dumps(
            {
                "status": packet["status"],
                "strategy_group_id": packet["policy"]["strategy_group_id"],
                "trial_identity": packet["policy"]["trial_identity"],
                "brf2_policy_scope_recorded": packet[
                    "brf2_policy_scope_recorded"
                ],
                "owner_policy_scope_missing": packet[
                    "owner_policy_scope_missing"
                ],
                "output_json": str(output_json),
                "policy_json": str(args.policy_json),
                "docs_json": str(docs_json) if args.write_docs else "",
                "docs_written": bool(args.write_docs),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if packet["status"] == "brf2_owner_trial_policy_scope_recorded" else 2


def build_brf2_owner_trial_policy_scope(
    *, generated_at_utc: str | None = None
) -> dict[str, Any]:
    generated = generated_at_utc or datetime.now(timezone.utc).isoformat()
    return {
        "schema": SCHEMA,
        "scope": "final_owned_brf2_owner_trial_policy_scope_non_executing",
        "status": "brf2_owner_trial_policy_scope_recorded",
        "generated_at_utc": generated,
        "policy": OWNER_POLICY,
        "brf2_policy_scope_recorded": True,
        "owner_policy_recorded": True,
        "owner_policy_scope_missing": False,
        "brf2_stage_after_policy": "admitted_trial_asset",
        "brf2_new_first_blocker": "required_facts_mapping_gap",
        "brf2_next_action": "close_brf2_required_facts_mapping_for_armed_observation",
        "checks": {
            "owner_policy_recorded": True,
            "owner_policy_scope_missing": False,
            "capital_scope_amount": "30",
            "capital_scope_currency": "USDT",
            "loss_capable": True,
            "side_scope_short_only": True,
            "max_notional_amount": "150",
            "leverage_scenario_is_not_authority": True,
            "attempt_cap": 3,
            "loss_unit_amount": "10",
            "actionable_now": False,
            "real_order_authority": False,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
        },
        "final_evidence_packet": {
            "closed_engineering_problem": (
                "BRF2 Owner trial policy is now recorded as a final-owned "
                "machine-readable policy scope instead of remaining a chat-only "
                "or proposal-only blocker"
            ),
            "capability_unlocked": (
                "main control can advance BRF2 from Owner policy blocker to "
                "admitted trial asset with a later engineering facts blocker"
            ),
            "brf2_policy_scope_recorded": True,
            "brf2_stage_after_policy": "admitted_trial_asset",
            "brf2_new_first_blocker": "required_facts_mapping_gap",
            "three_strategy_portfolio_status": "pending_downstream_regeneration",
            "tests_run": [
                "python3 -m py_compile scripts/build_brf2_owner_trial_policy_scope.py scripts/build_strategygroup_trial_asset_admission_proposal.py scripts/build_strategygroup_three_strategy_live_trial_portfolio.py scripts/build_strategygroup_tradeability_verdict.py scripts/run_strategygroup_runtime_local_monitor_sequence.py",
                "python3 -m pytest tests/unit/test_brf2_owner_trial_policy_scope.py tests/unit/test_strategygroup_trial_asset_admission_proposal.py tests/unit/test_strategygroup_three_strategy_live_trial_portfolio.py tests/unit/test_strategygroup_tradeability_verdict.py tests/unit/test_strategygroup_runtime_local_monitor_sequence.py tests/unit/test_strategygroup_current_artifact_contract.py -q",
                "python3 -m pytest tests/unit/test_strategygroup_* -q",
                "python3 -m compileall scripts tests",
                "python3 -m pytest tests/unit -q",
                "git diff --check",
            ],
            "files_changed": [
                "scripts/build_brf2_owner_trial_policy_scope.py",
                "scripts/build_strategygroup_trial_asset_admission_proposal.py",
                "scripts/build_strategygroup_three_strategy_live_trial_portfolio.py",
                "scripts/build_strategygroup_tradeability_verdict.py",
                "scripts/run_strategygroup_runtime_local_monitor_sequence.py",
                "tests/unit/test_brf2_owner_trial_policy_scope.py",
                "tests/unit/test_strategygroup_trial_asset_admission_proposal.py",
                "tests/unit/test_strategygroup_three_strategy_live_trial_portfolio.py",
                "tests/unit/test_strategygroup_tradeability_verdict.py",
                "tests/unit/test_strategygroup_runtime_local_monitor_sequence.py",
                "tests/unit/test_strategygroup_current_artifact_contract.py",
                "docs/current/strategy-group-handoffs/brf2-owner-trial-policy-scope-v0.json",
                "docs/current/strategy-group-handoffs/brf2-owner-trial-policy-scope-v0.md",
                "output/runtime-monitor/latest-brf2-owner-trial-policy-scope.json",
                "output/runtime-monitor/latest-brf2-owner-trial-policy-scope.md",
                "output/runtime-monitor/latest-strategygroup-trial-asset-admission-proposal.json",
                "output/runtime-monitor/latest-three-strategy-live-trial-portfolio.json",
                "output/runtime-monitor/latest-strategygroup-tradeability-verdict.json",
                "output/runtime-monitor/latest-local-monitor-sequence.json",
            ],
            "deploy_status": "not_deployed",
        },
        "interaction": _interaction(),
        "safety_invariants": _safety_invariants(),
    }


def build_brf2_owner_trial_policy_scope_view(
    policy_json: Path = DEFAULT_DOCS_JSON,
    *,
    view_generated_at_utc: str | None = None,
) -> dict[str, Any]:
    """Build a monitor view from the stable docs/current authority record."""

    if policy_json.exists():
        packet = _read_json(policy_json)
    else:
        packet = build_brf2_owner_trial_policy_scope()
    view_generated = view_generated_at_utc or datetime.now(timezone.utc).isoformat()
    view_packet = dict(packet)
    view_packet["source_policy_json"] = str(policy_json)
    view_packet["view_generated_at_utc"] = view_generated
    view_packet["view_mode"] = "monitor_view_from_final_owned_policy"
    return view_packet


def _markdown(packet: dict[str, Any], output_json: Path) -> str:
    policy = packet["policy"]
    capital = policy["capital_scope"]
    max_notional = policy["max_notional"]
    loss_unit = policy["loss_unit"]
    lines = [
        "## BRF2 Owner Trial Policy Scope V0",
        "",
        f"- Status: `{packet['status']}`",
        f"- Generated: `{packet['generated_at_utc']}`",
        f"- Output JSON: `{output_json}`",
        f"- StrategyGroup: `{policy['strategy_group_id']}`",
        f"- Trial identity: `{policy['trial_identity']}`",
        f"- Policy recorded: `{_yes_no(packet['brf2_policy_scope_recorded'])}`",
        f"- Owner policy scope missing: `{_yes_no(packet['owner_policy_scope_missing'])}`",
        f"- Actionable now: `{_yes_no(False)}`",
        f"- Real order authority: `{_yes_no(False)}`",
        "",
        "## Scope",
        "",
        "| Field | Value |",
        "| --- | --- |",
        (
            "| Capital scope | "
            f"`{capital['amount']} {capital['currency']} isolated full allocation` |"
        ),
        f"| Loss capable | `{_yes_no(bool(capital['loss_capable']))}` |",
        f"| Side scope | `{', '.join(policy['side_scope'])}` |",
        f"| Symbol scope | `{policy['symbol_scope']}` |",
        f"| Leverage scenario | `{policy['leverage_scenario']}` |",
        (
            "| Max notional | "
            f"`{max_notional['amount']} {max_notional['currency']} ({max_notional['basis']})` |"
        ),
        f"| Attempt cap | `{policy['attempt_cap']}` |",
        (
            "| Loss unit | "
            f"`{loss_unit['amount']} {loss_unit['currency']} ({loss_unit['basis']})` |"
        ),
        f"| Daily loss cap units | `{policy['daily_loss_cap_units']}` |",
        f"| Max consecutive losses | `{policy['max_consecutive_losses']}` |",
        f"| Valid until | `{policy['valid_until']}` |",
        "",
        "## Boundary",
        "",
        "- This record is Owner policy only.",
        "- It does not set actionable_now or real_order_authority.",
        "- FinalGate and Operation Layer remain required at action time.",
        "- The 5x value is a scenario, not unconditional order authority.",
    ]
    return "\n".join(lines) + "\n"


def _interaction() -> dict[str, Any]:
    return {
        "level": "L0_local_brf2_owner_trial_policy_scope",
        "remote_interaction_count": 0,
        "mutates_remote_files": False,
        "approaches_real_order": False,
        "calls_finalgate": False,
        "calls_operation_layer": False,
        "calls_exchange_write": False,
        "places_order": False,
    }


def _safety_invariants() -> dict[str, bool]:
    return {
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
        "withdrawal_or_transfer_created": False,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _yes_no(value: bool) -> str:
    return "是" if value else "否"


if __name__ == "__main__":
    raise SystemExit(main())
