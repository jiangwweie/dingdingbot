#!/usr/bin/env python3
"""Build CPM identity routing decision for trial admission.

This artifact records the engineering/product identity decision that CPM-LONG
is a standalone trial StrategyGroup, not an MPG member role and not observe-only.
It is non-executing and does not mutate runtime state.
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


DEFAULT_OUTPUT_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-cpm-identity-routing-decision.json"
)
DEFAULT_OUTPUT_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-cpm-identity-routing-decision.md"
)

SCHEMA = "brc.cpm_identity_routing_decision.v1"
STRATEGY_GROUP_ID = "CPM-RO-001"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-owner-progress", default=str(DEFAULT_OUTPUT_MD))
    args = parser.parse_args(argv)

    artifact = build_cpm_identity_routing_decision()
    output_json = Path(args.output_json)
    output_md = Path(args.output_owner_progress)
    _write_json(output_json, artifact)
    _write_text(output_md, _markdown(artifact, output_json))
    print(
        json.dumps(
            {
                "status": artifact["status"],
                "strategy_group_id": artifact["strategy_group_id"],
                "identity_decision": artifact["identity_decision"],
                "output_json": str(output_json),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def build_cpm_identity_routing_decision(
    *, generated_at_utc: str | None = None
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "scope": "cpm_identity_routing_decision_non_executing",
        "status": "cpm_identity_routing_decision_ready",
        "generated_at_utc": generated_at_utc
        or datetime.now(timezone.utc).isoformat(),
        "strategy_group_id": STRATEGY_GROUP_ID,
        "path_id": "CPM-LONG",
        "identity_decision": "standalone_trial_asset",
        "cpm_long_vs_mpg_long_distinct": True,
        "accepted_alternatives": [
            "merge_into_MPG_member_role",
            "observe_only_keep",
        ],
        "decision_evidence": {
            "trigger_difference": (
                "CPM-LONG waits for trend-intact pullback depth plus reclaim; "
                "MPG-LONG waits for momentum continuation and persistence."
            ),
            "invalidation_difference": (
                "CPM-LONG invalidates below pullback/reclaim structure; MPG "
                "invalidates on momentum exhaustion or continuation failure."
            ),
            "time_stop_difference": (
                "CPM-LONG has reclaim follow-through staleness; MPG has "
                "continuation persistence decay."
            ),
            "independent_required_facts": [
                "htf_trend_intact",
                "pullback_depth_normal",
                "reclaim_confirmed",
                "invalidated_below_level",
                "liquidity_ok",
                "funding_not_extreme",
                "active_position_or_open_order_clear",
                "action_time_available_balance",
            ],
        },
        "checks": {
            "registry_identity_closed": True,
            "standalone_trial_asset": True,
            "merge_into_mpg_member_role": False,
            "observe_only_keep": False,
        },
        "interaction": non_executing_interaction("L0_local_cpm_identity_routing"),
        "safety_invariants": non_executing_safety_invariants(
            (
                "registry_authority_changed",
                "tier_policy_changed",
                "execution_attempt_created",
                "authorization_evidence_created",
            ),
            include_authority_mirrors=False,
        ),
    }


def _markdown(artifact: dict[str, Any], output_json: Path) -> str:
    return "\n".join(
        [
            "## CPM Identity Routing Decision",
            "",
            f"- Status: `{artifact['status']}`",
            f"- StrategyGroup: `{artifact['strategy_group_id']}`",
            f"- Decision: `{artifact['identity_decision']}`",
            f"- CPM distinct from MPG: `{_yes_no(artifact['cpm_long_vs_mpg_long_distinct'])}`",
            f"- Output JSON: `{output_json}`",
            "",
            "## Boundary",
            "",
            "- This artifact closes identity routing only.",
            "- It does not grant runtime submit authority.",
        ]
    ) + "\n"


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
