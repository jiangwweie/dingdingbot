from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "build_mi_trial_admission_decision.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_mi_trial_admission_decision",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _public_symbol(symbol: str) -> dict:
    return {
        "symbol": symbol,
        "public_facts_ready": True,
        "spread_ok": True,
        "min_notional_ok": True,
        "qty_step_ok": True,
        "funding_not_extreme": True,
        "facts": {"spread_bps": 0.5},
    }


def _public_facts() -> dict:
    return {"symbols": [_public_symbol(symbol) for symbol in ["AVAXUSDT", "ETHUSDT", "SOLUSDT", "SUIUSDT"]]}


def _replay() -> dict:
    return {
        "summary": {
            "should_promote_scope_change": [
                {
                    "strategy_group_id": "MI-001",
                    "candidate_symbols": ["AVAXUSDT", "ETHUSDT", "SOLUSDT", "SUIUSDT"],
                }
            ]
        }
    }


def test_mi_trial_admission_records_candidate_without_live_authority():
    module = _load_module()

    artifact = module.build_mi_trial_admission_decision(
        replay=_replay(),
        public_facts=_public_facts(),
        generated_at_utc="2026-06-30T00:00:00+00:00",
    )

    assert artifact["trial_admission_decision"] == "trial_asset_admission_candidate"
    assert artifact["promotion_scope"] == "trial_admission"
    assert artifact["strategy_role"] == "momentum_initiation_high_beta_long_candidate"
    assert artifact["side"] == "long"
    assert artifact["symbol_scope"]["reviewed_symbols"] == [
        "AVAXUSDT",
        "ETHUSDT",
        "SOLUSDT",
        "SUIUSDT",
    ]
    assert artifact["tradeability"]["can_trade_now"] is False
    assert artifact["tradeability"]["first_blocker"] == (
        "mi_owner_policy_and_required_facts_mapping_needed"
    )
    checks = artifact["checks"]
    assert checks["live_submit_allowed"] is False
    assert checks["candidate_authorization_created"] is False
    assert checks["finalgate_called"] is False
    assert checks["operation_layer_called"] is False
    assert checks["exchange_write_called"] is False
    assert checks["order_created"] is False
    assert checks["live_profile_changed"] is False
    assert checks["order_sizing_changed"] is False


def test_mi_trial_admission_parks_when_replay_or_public_facts_missing():
    module = _load_module()

    artifact = module.build_mi_trial_admission_decision(
        replay={"summary": {}},
        public_facts={"symbols": []},
        generated_at_utc="2026-06-30T00:00:00+00:00",
    )

    assert artifact["trial_admission_decision"] == "park"
    assert artifact["tradeability"]["first_blocker"] == (
        "mi_replay_or_public_facts_insufficient"
    )
    assert artifact["tradeability"]["can_trade_now"] is False
