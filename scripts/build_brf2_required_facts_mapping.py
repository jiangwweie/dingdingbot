#!/usr/bin/env python3
"""Build BRF2 RequiredFacts mapping for armed observation admission.

This artifact closes the engineering mapping gap between admitted BRF2 trial
asset policy and armed observation. It is non-executing: it does not fetch live
facts, call FinalGate, call Operation Layer, create orders, mutate registry, or
change runtime profile or sizing.
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
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from src.domain.required_facts_readiness import (  # noqa: E402
    RequiredFactDisableSpec,
    RequiredFactObservationSpec,
)
from strategygroup_non_executing_projection import (  # noqa: E402
    non_executing_interaction,
    non_executing_safety_invariants,
)

DEFAULT_TRIAL_ASSET_ADMISSION_PROPOSAL_JSON = (
    REPO_ROOT
    / "output/runtime-monitor/latest-strategygroup-trial-asset-admission-proposal.json"
)
DEFAULT_BRF2_OWNER_TRIAL_POLICY_SCOPE_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-brf2-owner-trial-policy-scope.json"
)
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-brf2-required-facts-mapping.json"
)
DEFAULT_OUTPUT_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-brf2-required-facts-mapping.md"
)

SCHEMA = "brc.brf2_required_facts_mapping.v1"

FRESH_SIGNAL_RULE = {
    "signal_id": "brf2_short_rally_failure_fresh_signal_v1",
    "side": "short",
    "timeframes": ["1h_closed", "5m_closed"],
    "freshness_window_ms": 300_000,
    "description": (
        "A BRF2 fresh signal exists when a weak rally forms below the invalidation "
        "zone, closed structure loses/rejects the rally, squeeze and strong-reclaim "
        "disable states are not active, and liquidity is sufficient for observation."
    ),
    "would_enter_when": [
        "closed_1h_ohlcv.ready",
        "closed_5m_ohlcv.ready",
        "rally_context.bear_or_weak_reclaim",
        "rally_failure_trigger_state.confirmed",
        "short_squeeze_risk_state.clear_or_bounded",
        "strong_reclaim_disable_state.false",
        "liquidity_downshift_state.false",
        "spread_liquidity_state.acceptable",
    ],
}

REQUIRED_FACTS = [
    {
        "fact_key": "closed_1h_ohlcv",
        "class": "market",
        "source": "read_only_closed_candle_source",
        "freshness": "latest_closed_1h_bar",
        "missing_behavior": "block_armed_observation",
        "satisfies": "rally_context_and_trend_location",
    },
    {
        "fact_key": "closed_5m_ohlcv",
        "class": "market",
        "source": "read_only_closed_candle_source",
        "freshness": "latest_closed_5m_bar",
        "missing_behavior": "block_armed_observation",
        "satisfies": "fresh_rejection_or_structure_loss_timing",
    },
    {
        "fact_key": "rally_context",
        "class": "strategy",
        "source": "brf2_strategy_classifier",
        "freshness": "derived_from_closed_1h_and_5m",
        "missing_behavior": "block_armed_observation",
        "satisfies": "weak_rally_below_invalidation_zone",
    },
    {
        "fact_key": "rally_failure_trigger_state",
        "class": "strategy",
        "source": "brf2_strategy_classifier",
        "freshness": "derived_from_closed_5m",
        "missing_behavior": "block_armed_observation",
        "satisfies": "closed_candle_rejection_or_structure_loss",
    },
    {
        "fact_key": "short_squeeze_risk_state",
        "class": "derivatives_or_strategy_proxy",
        "source": "squeeze_classifier_or_review_proxy",
        "freshness": "current_review_window",
        "missing_behavior": "block_armed_observation",
        "satisfies": "squeeze_risk_clear_or_bounded",
    },
    {
        "fact_key": "strong_reclaim_disable_state",
        "class": "strategy",
        "source": "brf2_disable_classifier",
        "freshness": "derived_from_closed_1h_and_5m",
        "missing_behavior": "block_armed_observation",
        "satisfies": "not_strong_upside_reclaim",
    },
    {
        "fact_key": "liquidity_downshift_state",
        "class": "market_or_execution_context",
        "source": "spread_volume_liquidity_proxy",
        "freshness": "current_review_window",
        "missing_behavior": "block_armed_observation",
        "satisfies": "liquidity_not_downshifted",
    },
    {
        "fact_key": "spread_liquidity_state",
        "class": "market_or_execution_context",
        "source": "spread_volume_liquidity_proxy",
        "freshness": "current_review_window",
        "missing_behavior": "block_armed_observation",
        "satisfies": "spread_and_volume_observation_acceptable",
    },
]

ACCEPTED_REQUIRED_FACT_STATES = {
    "closed_1h_ohlcv": ("fresh", "present", "ready"),
    "closed_5m_ohlcv": ("fresh", "present", "ready"),
    "rally_context": ("bear_or_weak_reclaim", "ready", "weak_rally"),
    "rally_failure_trigger_state": ("active", "confirmed", "ready"),
    "short_squeeze_risk_state": ("bounded", "clear", "clear_or_bounded"),
    "strong_reclaim_disable_state": ("clear", "false", "inactive"),
    "liquidity_downshift_state": ("clear", "false", "inactive"),
    "spread_liquidity_state": ("acceptable", "normal", "ready"),
}

DISABLE_FACTS = [
    {
        "fact_key": "short_squeeze_risk_state",
        "blocks_when": ["bounded", "red", "unbounded", "unknown"],
        "blocker": "squeeze_risk_not_clear",
    },
    {
        "fact_key": "strong_reclaim_disable_state",
        "blocks_when": [True, "true", "active"],
        "blocker": "strong_reclaim_disable_active",
    },
    {
        "fact_key": "rally_extension_invalidates_failure_state",
        "blocks_when": [True, "true", "active"],
        "blocker": "rally_extension_invalidates_failure",
    },
    {
        "fact_key": "liquidity_downshift_state",
        "blocks_when": [True, "true", "active"],
        "blocker": "liquidity_downshift_active",
    },
    {
        "fact_key": "spread_liquidity_state",
        "blocks_when": ["missing", "wide_spread", "thin_volume", "unknown"],
        "blocker": "spread_liquidity_not_acceptable",
    },
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--trial-asset-admission-proposal-json",
        default=str(DEFAULT_TRIAL_ASSET_ADMISSION_PROPOSAL_JSON),
    )
    parser.add_argument(
        "--brf2-owner-trial-policy-scope-json",
        default=str(DEFAULT_BRF2_OWNER_TRIAL_POLICY_SCOPE_JSON),
    )
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-owner-progress", default=str(DEFAULT_OUTPUT_MD))
    args = parser.parse_args(argv)

    artifact = build_brf2_required_facts_mapping(
        trial_asset_admission_proposal=_read_optional_json(
            Path(args.trial_asset_admission_proposal_json)
        ),
        brf2_owner_trial_policy_scope=_read_optional_json(
            Path(args.brf2_owner_trial_policy_scope_json)
        ),
    )
    output_json = Path(args.output_json)
    output_md = Path(args.output_owner_progress)
    _write_json(output_json, artifact)
    _write_text(output_md, _markdown(artifact, output_json))
    print(
        json.dumps(
            {
                "status": artifact["status"],
                "strategy_group_id": artifact["strategy_group_id"],
                "required_facts_mapping_ready": artifact[
                    "required_facts_mapping_ready"
                ],
                "after_next_state": artifact["after_next_state"],
                "output_json": str(output_json),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if artifact["status"] == "brf2_required_facts_mapping_ready" else 2


def build_brf2_required_facts_mapping(
    *,
    trial_asset_admission_proposal: dict[str, Any] | None = None,
    brf2_owner_trial_policy_scope: dict[str, Any] | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    proposal = _as_dict((trial_asset_admission_proposal or {}).get("proposal"))
    policy_artifact = brf2_owner_trial_policy_scope or {}
    policy_recorded = _policy_recorded(policy_artifact)
    proposal_ready = (
        proposal.get("strategy_group_id") == "BRF2-001"
        and proposal.get("owner_policy_recorded") is True
        and proposal.get("owner_policy_scope_missing") is False
    )
    mapping_ready = policy_recorded and proposal_ready
    blockers = [] if mapping_ready else _blockers(policy_recorded, proposal_ready)
    observation_specs = _required_fact_observation_specs()
    disable_specs = _disable_fact_observation_specs()
    return {
        "schema": SCHEMA,
        "scope": "brf2_required_facts_mapping_for_armed_observation",
        "status": (
            "brf2_required_facts_mapping_ready"
            if mapping_ready
            else "brf2_required_facts_mapping_blocked"
        ),
        "generated_at_utc": generated_at_utc
        or datetime.now(timezone.utc).isoformat(),
        "strategy_group_id": "BRF2-001",
        "current_stage": "admitted_trial_asset" if policy_recorded else "trial_asset_admission_candidate",
        "after_next_state": "armed_observation" if mapping_ready else "admitted_trial_asset",
        "required_facts_mapping_ready": mapping_ready,
        "fresh_signal_rule": FRESH_SIGNAL_RULE,
        "required_facts": REQUIRED_FACTS,
        "required_fact_observation_specs": observation_specs,
        "disable_facts": DISABLE_FACTS,
        "disable_fact_observation_specs": disable_specs,
        "block_conditions": [
            {
                "condition": f"{fact['fact_key']}_missing_or_stale",
                "behavior": fact["missing_behavior"],
            }
            for fact in REQUIRED_FACTS
        ]
        + [
            {
                "condition": disable["blocker"],
                "behavior": "block_armed_observation",
            }
            for disable in DISABLE_FACTS
        ],
        "armed_observation_entry_criteria": {
            "owner_policy_recorded": policy_recorded,
            "trial_asset_admission_proposal_ready": proposal_ready,
            "all_required_fact_observation_specs_mapped": mapping_ready,
            "disable_fact_blockers_mapped": mapping_ready,
            "fresh_signal_rule_mapped": mapping_ready,
        },
        "mapping_checkpoint": (
            "continue_brf2_armed_observation_until_fresh_signal"
            if mapping_ready
            else "close_brf2_required_facts_mapping_for_armed_observation"
        ),
        "first_blocker_after_mapping": (
            "fresh_brf2_short_signal_absent"
            if mapping_ready
            else "required_facts_mapping_gap"
        ),
        "blockers": blockers,
        "checks": {
            "required_facts_mapping_ready": mapping_ready,
            "owner_policy_recorded": policy_recorded,
            "trial_asset_admission_proposal_ready": proposal_ready,
            "fresh_signal_rule_mapped": mapping_ready,
            "required_fact_count": len(REQUIRED_FACTS),
            "disable_fact_count": len(DISABLE_FACTS),
        },
        "interaction": _interaction(),
        "safety_invariants": _safety_invariants(),
    }


def _blockers(policy_recorded: bool, proposal_ready: bool) -> list[str]:
    blockers: list[str] = []
    if not policy_recorded:
        blockers.append("brf2_owner_policy_not_recorded")
    if not proposal_ready:
        blockers.append("brf2_trial_asset_admission_proposal_not_ready")
    return blockers or ["required_facts_mapping_gap"]


def _required_fact_observation_specs() -> list[dict[str, Any]]:
    return [
        RequiredFactObservationSpec(
            key=str(fact["fact_key"]),
            accepted_statuses=ACCEPTED_REQUIRED_FACT_STATES[str(fact["fact_key"])],
        ).as_signal_observation_spec()
        for fact in REQUIRED_FACTS
    ]


def _disable_fact_observation_specs() -> list[dict[str, Any]]:
    return [
        RequiredFactDisableSpec(
            key=str(fact["fact_key"]),
            active_statuses=tuple(
                sorted({str(item).lower() for item in fact["blocks_when"]})
            ),
            blocker=str(fact["blocker"]),
        ).as_signal_disable_spec()
        for fact in DISABLE_FACTS
    ]


def _policy_recorded(policy_artifact: dict[str, Any]) -> bool:
    policy = _as_dict(policy_artifact.get("policy"))
    return (
        policy_artifact.get("status") == "brf2_owner_trial_policy_scope_recorded"
        and policy_artifact.get("brf2_policy_scope_recorded") is True
        and policy_artifact.get("owner_policy_scope_missing") is False
        and policy.get("strategy_group_id") == "BRF2-001"
    )


def _markdown(artifact: dict[str, Any], output_json: Path) -> str:
    lines = [
        "## BRF2 RequiredFacts Mapping",
        "",
        f"- Status: `{artifact['status']}`",
        f"- Generated: `{artifact['generated_at_utc']}`",
        f"- Output JSON: `{output_json}`",
        f"- StrategyGroup: `{artifact['strategy_group_id']}`",
        f"- Current stage: `{artifact['current_stage']}`",
        f"- After next state: `{artifact['after_next_state']}`",
        f"- Mapping ready: `{_yes_no(artifact['required_facts_mapping_ready'])}`",
        "",
        "## Fresh Signal",
        "",
        f"- Signal id: `{artifact['fresh_signal_rule']['signal_id']}`",
        f"- Side: `{artifact['fresh_signal_rule']['side']}`",
        f"- Timeframes: `{', '.join(artifact['fresh_signal_rule']['timeframes'])}`",
        "",
        "## Required Facts",
        "",
        "| Fact | Class | Source | Missing Behavior |",
        "| --- | --- | --- | --- |",
    ]
    for fact in artifact["required_facts"]:
        lines.append(
            "| `{}` | `{}` | `{}` | `{}` |".format(
                fact["fact_key"],
                fact["class"],
                fact["source"],
                fact["missing_behavior"],
            )
        )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "- This mapping does not satisfy live facts.",
            "- It does not call FinalGate, Operation Layer, or exchange write.",
            "- It only closes the BRF2 mapping gap for armed observation.",
        ]
    )
    return "\n".join(lines) + "\n"


def _interaction() -> dict[str, Any]:
    return non_executing_interaction("L0_local_brf2_required_facts_mapping")


def _safety_invariants() -> dict[str, bool]:
    return non_executing_safety_invariants(
        (
            "registry_authority_changed",
            "tier_policy_changed",
        ),
        include_authority_mirrors=False,
    )


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _read_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


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
