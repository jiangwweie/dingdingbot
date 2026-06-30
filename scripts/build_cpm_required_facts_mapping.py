#!/usr/bin/env python3
"""Build CPM-LONG RequiredFacts mapping for armed observation.

The mapping is non-executing and read-model only. It defines what CPM-LONG must
observe before a fresh signal can move into the official runtime chain.
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


DEFAULT_OWNER_POLICY_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-cpm-owner-trial-policy-scope.json"
)
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-cpm-required-facts-mapping.json"
)
DEFAULT_OUTPUT_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-cpm-required-facts-mapping.md"
)

SCHEMA = "brc.cpm_required_facts_mapping.v1"
STRATEGY_GROUP_ID = "CPM-RO-001"

FRESH_SIGNAL_RULE = {
    "signal_id": "cpm_long_pullback_reclaim_signal_v1",
    "side": "long",
    "timeframes": ["15m_closed", "1h_closed", "4h_closed"],
    "freshness_window_ms": 900_000,
    "description": (
        "CPM-LONG is fresh when higher-timeframe trend is intact, pullback "
        "depth remains normal, reclaim is confirmed, liquidity/funding are "
        "acceptable, and no position/open-order conflict exists."
    ),
}

REQUIRED_FACTS = [
    ("htf_trend_intact", "strategy", "trend_classifier", "satisfied"),
    ("pullback_depth_normal", "strategy", "pullback_depth_classifier", "satisfied"),
    ("reclaim_confirmed", "strategy", "reclaim_classifier", "satisfied"),
    ("invalidated_below_level", "risk", "strategy_risk_model", "satisfied"),
    ("liquidity_ok", "market_or_execution_context", "liquidity_proxy", "satisfied"),
    ("funding_not_extreme", "derivatives", "funding_proxy", "satisfied"),
    (
        "active_position_or_open_order_clear",
        "account_action_time",
        "runtime_action_time_exchange_facts",
        "satisfied",
    ),
    (
        "action_time_available_balance",
        "account_action_time",
        "runtime_action_time_exchange_facts",
        "satisfied",
    ),
]

DISABLE_FACTS = [
    ("htf_trend_broken", ["true", "active", True]),
    ("pullback_depth_abnormal", ["true", "active", True]),
    ("reclaim_failed_or_stale", ["true", "active", "stale", True]),
    ("liquidity_not_ok", ["true", "active", True]),
    ("funding_extreme", ["true", "active", True]),
    ("active_position_or_open_order_conflict", ["true", "active", True]),
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner-policy-json", default=str(DEFAULT_OWNER_POLICY_JSON))
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-owner-progress", default=str(DEFAULT_OUTPUT_MD))
    args = parser.parse_args(argv)

    artifact = build_cpm_required_facts_mapping(
        owner_policy=_read_optional_json(Path(args.owner_policy_json))
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
                "output_json": str(output_json),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if artifact["required_facts_mapping_ready"] else 2


def build_cpm_required_facts_mapping(
    *, owner_policy: dict[str, Any] | None = None, generated_at_utc: str | None = None
) -> dict[str, Any]:
    policy_ready = (
        (owner_policy or {}).get("status") == "cpm_owner_trial_policy_scope_recorded"
        and (owner_policy or {}).get("owner_policy_recorded") is True
    )
    required_specs = [
        {
            "fact_key": key,
            "class": fact_class,
            "source": source,
            "freshness": "action_time_required" if key.startswith("action_time") else "runtime_watcher_readonly",
            "accepted_statuses": ["true", "ready", accepted],
            "missing_behavior": "block_live_submit",
        }
        for key, fact_class, source, accepted in REQUIRED_FACTS
    ]
    disable_specs = [
        {
            "fact_key": key,
            "active_statuses": values,
            "blocker": key,
            "behavior": "block_live_submit",
        }
        for key, values in DISABLE_FACTS
    ]
    return {
        "schema": SCHEMA,
        "scope": "cpm_required_facts_mapping_for_armed_observation",
        "status": (
            "cpm_required_facts_mapping_ready"
            if policy_ready
            else "cpm_required_facts_mapping_blocked_policy"
        ),
        "generated_at_utc": generated_at_utc
        or datetime.now(timezone.utc).isoformat(),
        "strategy_group_id": STRATEGY_GROUP_ID,
        "path_id": "CPM-LONG",
        "current_stage": "admitted_trial_asset" if policy_ready else "trial_asset_admission_candidate",
        "after_next_state": "armed_observation",
        "required_facts_mapping_ready": policy_ready,
        "live_required_facts_authority": False,
        "action_time_refresh_required": True,
        "fresh_signal_rule": FRESH_SIGNAL_RULE,
        "required_facts": [
            {
                "fact_key": key,
                "class": fact_class,
                "source": source,
                "missing_behavior": "block_live_submit",
            }
            for key, fact_class, source, _accepted in REQUIRED_FACTS
        ],
        "required_fact_observation_specs": required_specs,
        "disable_facts": [
            {"fact_key": key, "active_statuses": values}
            for key, values in DISABLE_FACTS
        ],
        "disable_fact_observation_specs": disable_specs,
        "watcher_scope": {
            "symbols": ["ETHUSDT", "SOLUSDT", "AVAXUSDT", "SUIUSDT"],
            "primary_live_submit_symbols": ["ETHUSDT"],
            "expanded_readonly_symbols": ["SOLUSDT", "AVAXUSDT", "SUIUSDT"],
            "timeframes": ["15m", "1h", "4h"],
            "cadence": "5-15m near reclaim; 15-30m otherwise",
            "signal_rule": "cpm_long_pullback_reclaim_signal_v1",
            "scope_boundary": (
                "expanded symbols are read-only watcher scope until Binance USD-M "
                "contract, mark, funding, spread, minNotional, qtyStep, leverage, "
                "position, and open-order facts pass action-time checks"
            ),
        },
        "checks": {
            "owner_policy_recorded": policy_ready,
            "required_fact_count": len(REQUIRED_FACTS),
            "disable_fact_count": len(DISABLE_FACTS),
            "action_time_available_balance_mapped": True,
            "active_position_or_open_order_clear_mapped": True,
            "expanded_watcher_scope_symbols_mapped": policy_ready,
            "expanded_scope_does_not_change_live_profile": True,
        },
        "interaction": non_executing_interaction("L0_local_cpm_required_facts_mapping"),
        "safety_invariants": non_executing_safety_invariants(
            ("live_required_facts_authority",),
            include_authority_mirrors=False,
        ),
    }


def _markdown(artifact: dict[str, Any], output_json: Path) -> str:
    return "\n".join(
        [
            "## CPM RequiredFacts Mapping",
            "",
            f"- Status: `{artifact['status']}`",
            f"- StrategyGroup: `{artifact['strategy_group_id']}`",
            f"- RequiredFacts ready: `{_yes_no(artifact['required_facts_mapping_ready'])}`",
            f"- Action-time refresh required: `{_yes_no(artifact['action_time_refresh_required'])}`",
            f"- Output JSON: `{output_json}`",
            "",
            "## Boundary",
            "",
            "- Mapping only; not live RequiredFacts authority.",
            "- Action-time exchange balance and account conflict facts remain required.",
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
