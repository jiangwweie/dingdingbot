#!/usr/bin/env python3
"""Build MI-001 formal trial admission decision."""

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


DEFAULT_REPLAY_JSON = (
    REPO_ROOT
    / "output/runtime-monitor/latest-four-candidate-recent-live-submit-replay.json"
)
DEFAULT_PUBLIC_FACTS_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-binance-usdm-public-facts.json"
)
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-mi-trial-admission-decision.json"
)
DEFAULT_OUTPUT_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-mi-trial-admission-decision.md"
)

SYMBOLS = ("AVAXUSDT", "SOLUSDT", "ETHUSDT")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay-json", default=str(DEFAULT_REPLAY_JSON))
    parser.add_argument("--public-facts-json", default=str(DEFAULT_PUBLIC_FACTS_JSON))
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-owner-progress", default=str(DEFAULT_OUTPUT_MD))
    args = parser.parse_args(argv)

    artifact = build_mi_trial_admission_decision(
        replay=_read_optional_json(Path(args.replay_json)),
        public_facts=_read_optional_json(Path(args.public_facts_json)),
    )
    output_json = Path(args.output_json)
    output_md = Path(args.output_owner_progress)
    _write_json(output_json, artifact)
    _write_text(output_md, _markdown(artifact, output_json))
    print(
        json.dumps(
            {
                "status": artifact["status"],
                "decision": artifact["trial_admission_decision"],
                "first_blocker": artifact["tradeability"]["first_blocker"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def build_mi_trial_admission_decision(
    *,
    replay: dict[str, Any],
    public_facts: dict[str, Any],
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    generated = generated_at_utc or datetime.now(timezone.utc).isoformat()
    public_by_symbol = {
        str(row.get("symbol") or ""): row
        for row in public_facts.get("symbols") or []
        if isinstance(row, dict)
    }
    replay_symbols = _replay_symbols(replay)
    symbol_rows = [
        _symbol_row(symbol, public_by_symbol.get(symbol, {}), replay_symbols)
        for symbol in SYMBOLS
    ]
    replay_supported = [row["symbol"] for row in symbol_rows if row["replay_supported"]]
    public_ready = [row["symbol"] for row in symbol_rows if row["public_facts_ready"]]
    decision = (
        "trial_asset_admission_candidate"
        if replay_supported and public_ready
        else "park"
    )
    first_blocker = (
        "mi_owner_policy_and_required_facts_mapping_needed"
        if decision == "trial_asset_admission_candidate"
        else "mi_replay_or_public_facts_insufficient"
    )
    return {
        "schema": "brc.mi_trial_admission_decision.v1",
        "scope": "mi_trial_admission_decision_non_authority",
        "status": "mi_trial_admission_decision_ready",
        "generated_at_utc": generated,
        "strategy_group_id": "MI-001",
        "trial_admission_decision": decision,
        "promotion_scope": "trial_admission",
        "strategy_role": "momentum_initiation_high_beta_long_candidate",
        "side": "long",
        "symbol_scope": {
            "reviewed_symbols": list(SYMBOLS),
            "readonly_watcher_candidates": public_ready,
            "primary_live_submit_symbol_scope": [],
            "live_submit_scope_changed": False,
        },
        "required_facts": [
            "impulse_breakout_confirmed",
            "relative_strength_confirmed",
            "liquidity_ok",
            "funding_not_extreme",
            "active_position_or_open_order_clear",
            "action_time_available_balance",
        ],
        "risk_envelope": {
            "capital_scope_source": "action_time_exchange_available_balance",
            "live_profile_changed": False,
            "order_sizing_changed": False,
            "trial_risk_policy_status": "owner_policy_not_recorded_for_mi",
        },
        "watcher_scope": {
            "source": "binance_usdm_public_facts_readonly",
            "symbol_scope": public_ready,
            "cadence": "15m/1h impulse initiation review",
            "read_only": True,
        },
        "replay_evidence": {
            "replay_supported_symbols": replay_supported,
            "formal_replay_review_opened": bool(replay_supported),
            "source": "latest_four_candidate_recent_live_submit_replay",
        },
        "symbol_evidence": symbol_rows,
        "tradeability": {
            "can_trade_now": False,
            "decision": "not_tradable_trial_admission",
            "first_blocker": first_blocker,
            "blocker_owner": "owner_policy" if decision != "park" else "engineering",
            "next_action": "record_mi_owner_trial_policy_and_required_facts_mapping",
            "post_action_expected_state": "armed_observation_candidate_without_live_authority",
        },
        "checks": {
            "formal_trial_admission_decision_recorded": True,
            "live_submit_allowed": False,
            "candidate_authorization_created": False,
            "finalgate_called": False,
            "operation_layer_called": False,
            "exchange_write_called": False,
            "order_created": False,
            "live_profile_changed": False,
            "order_sizing_changed": False,
        },
        "interaction": non_executing_interaction("L0_local_mi_trial_admission_decision"),
        "safety_invariants": {
            **non_executing_safety_invariants(tuple(), include_authority_mirrors=False),
            "live_profile_changed": False,
            "order_sizing_changed": False,
        },
    }


def _symbol_row(
    symbol: str,
    public_row: dict[str, Any],
    replay_symbols: set[str],
) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "replay_supported": symbol in replay_symbols,
        "public_facts_ready": public_row.get("public_facts_ready") is True,
        "liquidity": {
            "spread_ok": public_row.get("spread_ok") is True,
            "min_notional_ok": public_row.get("min_notional_ok") is True,
            "qty_step_ok": public_row.get("qty_step_ok") is True,
            "spread_bps": _as_dict(public_row.get("facts")).get("spread_bps"),
        },
        "funding_not_extreme": public_row.get("funding_not_extreme") is True,
        "strategy_fit": "formal_replay_review_opened" if symbol in replay_symbols else "not_supported_by_current_replay",
    }


def _replay_symbols(replay: dict[str, Any]) -> set[str]:
    symbols: set[str] = set()
    for item in _as_dict(replay.get("summary")).get("should_promote_scope_change") or []:
        if not isinstance(item, dict):
            continue
        if item.get("strategy_group_id") != "MI-001":
            continue
        symbols.update(str(symbol) for symbol in item.get("candidate_symbols") or [])
    return symbols


def _markdown(artifact: dict[str, Any], output_json: Path) -> str:
    return "\n".join(
        [
            "## MI Trial Admission Decision",
            "",
            f"- Status: `{artifact['status']}`",
            f"- Decision: `{artifact['trial_admission_decision']}`",
            f"- First blocker: `{artifact['tradeability']['first_blocker']}`",
            f"- Output JSON: `{output_json}`",
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


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


if __name__ == "__main__":
    raise SystemExit(main())
