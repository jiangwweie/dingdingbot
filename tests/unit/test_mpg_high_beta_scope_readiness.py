from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "build_mpg_high_beta_scope_readiness.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_mpg_high_beta_scope_readiness",
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
        "exchange_contract_exists": True,
        "mark_price_fresh": True,
        "funding_not_extreme": True,
        "spread_ok": True,
        "min_notional_ok": True,
        "qty_step_ok": True,
        "leverage_available": True,
        "facts": {
            "spread_bps": 0.5,
            "min_notional": "5",
            "last_funding_rate": "0.0001",
        },
    }


def _public_facts() -> dict:
    return {
        "status": "binance_usdm_public_facts_ready",
        "symbols": [
            _public_symbol("BTCUSDT"),
            _public_symbol("ETHUSDT"),
            _public_symbol("SOLUSDT"),
            _public_symbol("AVAXUSDT"),
            _public_symbol("SUIUSDT"),
        ],
    }


def _replay() -> dict:
    return {
        "summary": {
            "should_promote_scope_change": [
                {
                    "strategy_group_id": "MPG-001",
                    "candidate_symbols": [
                        "SOLUSDT",
                        "AVAXUSDT",
                        "OPUSDT",
                        "SUIUSDT",
                    ],
                }
            ]
        }
    }


def test_mpg_high_beta_scope_approves_readonly_without_live_scope_change():
    module = _load_module()

    artifacts = module.build_mpg_high_beta_scope_readiness(
        public_facts=_public_facts(),
        replay=_replay(),
        generated_at_utc="2026-06-30T00:00:00+00:00",
    )

    scope = artifacts["scope_decision"]
    watcher = artifacts["expanded_watcher"]
    readiness = artifacts["action_time_readiness"]
    assert scope["approved_readonly_watcher_symbols"] == [
        "SOLUSDT",
        "AVAXUSDT",
        "SUIUSDT",
    ]
    assert watcher["watcher_scope"]["symbol_scope"] == [
        "BTCUSDT",
        "ETHUSDT",
        "SOLUSDT",
        "AVAXUSDT",
        "SUIUSDT",
    ]
    assert readiness["private_action_time_facts_ready"] is False
    assert readiness["first_blocker"] == "fresh_mpg_signal_or_private_action_time_facts"
    for artifact in artifacts.values():
        checks = artifact["checks"]
        assert checks["primary_live_submit_scope_changed"] is False
        assert checks["live_profile_changed"] is False
        assert checks["order_sizing_changed"] is False
        assert checks["finalgate_called"] is False
        assert checks["operation_layer_called"] is False
        assert checks["exchange_write_called"] is False
        assert checks["order_created"] is False
        assert checks["live_submit_allowed"] is False


def test_mpg_high_beta_scope_defers_op_without_public_facts():
    module = _load_module()

    artifacts = module.build_mpg_high_beta_scope_readiness(
        public_facts=_public_facts(),
        replay=_replay(),
        generated_at_utc="2026-06-30T00:00:00+00:00",
    )

    op_row = next(
        row
        for row in artifacts["scope_decision"]["symbol_decisions"]
        if row["symbol"] == "OPUSDT"
    )
    assert op_row["scope_decision"] == "defer_primary_or_readonly_scope"
    assert "binance_usdm_public_facts_missing_or_stale" in op_row["rejection_reasons"]
    assert "not_in_current_readonly_watcher_batch" in op_row["rejection_reasons"]
    assert op_row["primary_live_submit_scope_changed"] is False
