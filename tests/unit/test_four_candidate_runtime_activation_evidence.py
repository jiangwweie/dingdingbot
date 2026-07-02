from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "build_four_candidate_runtime_activation_evidence.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_four_candidate_runtime_activation_evidence",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _public_facts(generated_at_utc: str = "2026-06-30T00:00:00+00:00") -> dict:
    return {
        "status": "binance_usdm_public_facts_ready",
        "generated_at_utc": generated_at_utc,
        "symbols": [
            _symbol("BTCUSDT"),
            _symbol("ETHUSDT"),
            _symbol("SOLUSDT"),
            _symbol("AVAXUSDT"),
            _symbol("SUIUSDT"),
        ],
    }


def _symbol(symbol: str) -> dict:
    return {
        "symbol": symbol,
        "public_facts_ready": True,
        "exchange_contract_exists": True,
        "mark_price_fresh": True,
        "mark_price_observed_at_utc": "2026-06-29T23:59:30+00:00",
        "mark_price_age_seconds": 30,
        "max_mark_price_age_seconds": 300,
        "funding_not_extreme": True,
        "spread_ok": True,
        "min_notional_ok": True,
        "qty_step_ok": True,
        "leverage_available": True,
        "facts": {"spread_bps": 0.1, "min_notional": "5", "qty_step": "0.001"},
    }


def _window(days: int, signals: int, missed: int, boundary: int) -> dict:
    return {
        "window_days": days,
        "counterfactual_fresh_signal_count": signals,
        "missed_opportunity_review_count": missed,
        "would_reach_action_time_boundary_count": boundary,
    }


def _replay() -> dict:
    return {
        "summary": {
            "should_promote_scope_change": [
                {
                    "strategy_group_id": "MPG-001",
                    "candidate_symbols": ["SOLUSDT", "AVAXUSDT", "SUIUSDT", "OPUSDT"],
                },
                {
                    "strategy_group_id": "SOR-001",
                    "candidate_symbols": ["SOLUSDT", "AVAXUSDT"],
                },
                {
                    "strategy_group_id": "CPM-RO-001",
                    "candidate_symbols": ["SOLUSDT", "AVAXUSDT", "SUIUSDT"],
                },
            ]
        },
        "strategy_rows": [
            {
                "strategy_group_id": "MPG-001",
                "window_results": [_window(14, 93, 93, 12)],
            },
            {
                "strategy_group_id": "SOR-001",
                "window_results": [_window(14, 14, 14, 6)],
            },
        ],
    }


def test_builds_mpg_sor_runtime_evidence_without_live_authority():
    module = _load_module()

    artifacts = module.build_four_candidate_runtime_activation_evidence(
        public_facts=_public_facts(),
        replay=_replay(),
        cpm_capture={"current_signal_state": "fresh_signal_absent"},
        generated_at_utc="2026-06-30T00:00:00+00:00",
    )

    mpg = artifacts["mpg"]
    sor = artifacts["sor"]
    assert mpg["runtime_artifact_ready"] is True
    assert sor["runtime_artifact_ready"] is True
    assert mpg["watcher_scope"]["symbol_scope"] == [
        "BTCUSDT",
        "ETHUSDT",
        "SOLUSDT",
        "AVAXUSDT",
        "SUIUSDT",
    ]
    assert sor["watcher_scope"]["symbol_scope"] == [
        "BTCUSDT",
        "ETHUSDT",
        "SOLUSDT",
        "AVAXUSDT",
    ]
    for artifact in [mpg, sor]:
        assert artifact["live_submit_allowed"] is False
        assert artifact["checks"]["finalgate_called"] is False
        assert artifact["checks"]["operation_layer_called"] is False
        assert artifact["checks"]["exchange_write_called"] is False
        assert artifact["checks"]["order_created"] is False


def test_scope_decision_and_cpm_path_remain_non_authority():
    module = _load_module()

    artifacts = module.build_four_candidate_runtime_activation_evidence(
        public_facts=_public_facts(),
        replay=_replay(),
        cpm_capture={"current_signal_state": "fresh_signal_absent"},
        generated_at_utc="2026-06-30T00:00:00+00:00",
    )

    scope = artifacts["scope_decision"]
    cpm = artifacts["cpm_fresh_path"]
    assert scope["summary"]["primary_live_submit_scope_changed_count"] == 0
    assert scope["checks"]["live_profile_changed"] is False
    assert scope["checks"]["order_sizing_changed"] is False
    assert cpm["public_fact_path_ready"] is True
    assert cpm["fresh_signal_present"] is False
    assert cpm["next_blocker"] == "fresh_cpm_long_signal_absent"
    assert cpm["finalgate_called"] is False
    assert cpm["operation_layer_called"] is False
    assert cpm["live_submit_allowed"] is False


def test_stale_public_facts_do_not_make_runtime_artifacts_ready():
    module = _load_module()

    artifacts = module.build_four_candidate_runtime_activation_evidence(
        public_facts=_public_facts(
            generated_at_utc="2026-06-29T23:00:00+00:00"
        ),
        replay=_replay(),
        cpm_capture={"current_signal_state": "fresh_signal_absent"},
        generated_at_utc="2026-06-30T00:00:00+00:00",
    )

    mpg = artifacts["mpg"]
    sor = artifacts["sor"]
    cpm = artifacts["cpm_fresh_path"]
    assert mpg["runtime_artifact_ready"] is False
    assert sor["runtime_artifact_ready"] is False
    assert mpg["checks"]["public_facts_artifact_fresh"] is False
    assert mpg["next_blocker"] == "binance_usdm_public_facts_stale_or_unavailable"
    assert cpm["public_fact_path_ready"] is False
    assert cpm["next_blocker"] == "binance_usdm_public_facts_stale_or_unavailable"
