from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "build_four_candidate_runtime_activation_closure.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_four_candidate_runtime_activation_closure",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _window(days: int, signals: int, missed: int, boundary: int) -> dict:
    return {
        "window_days": days,
        "counterfactual_fresh_signal_count": signals,
        "missed_opportunity_review_count": missed,
        "would_reach_action_time_boundary_count": boundary,
    }


def _replay() -> dict:
    return {
        "status": "recent_counterfactual_replay_ready",
        "data_sources": {
            "public_market_candles": {
                "venue_basis": "coinbase_spot_proxy",
                "execution_venue_basis": "binance_usdm_usdt_perps",
                "execution_venue_match": False,
                "absorbability_grade": "review_only_proxy",
            }
        },
        "strategy_rows": [
            {
                "strategy_group_id": "CPM-RO-001",
                "window_results": [
                    _window(3, 10, 10, 3),
                    _window(7, 18, 18, 3),
                    _window(14, 36, 36, 9),
                ],
            },
            {
                "strategy_group_id": "MPG-001",
                "window_results": [
                    _window(3, 30, 30, 6),
                    _window(7, 57, 57, 6),
                    _window(14, 93, 93, 12),
                ],
            },
            {
                "strategy_group_id": "SOR-001",
                "window_results": [
                    _window(3, 3, 3, 1),
                    _window(7, 6, 6, 2),
                    _window(14, 14, 14, 6),
                ],
            },
        ],
        "fifth_candidate_review": {
            "review_recommendation": "open_formal_candidate_replay_review",
            "recent_impulse_event_count": 20,
            "events": [
                {"symbol": "SOLUSDT"},
                {"symbol": "AVAXUSDT"},
                {"symbol": "ETHUSDT"},
            ],
        },
    }


def test_activation_closure_completes_p0_p1_without_live_authority():
    module = _load_module()

    artifact = module.build_runtime_activation_closure(
        replay=_replay(),
        cpm_required_facts={
            "status": "cpm_required_facts_mapping_ready",
            "required_facts_mapping_ready": True,
        },
        cpm_capture={
            "watcher_scope": {
                "symbol_scope": ["ETHUSDT", "SOLUSDT", "AVAXUSDT", "SUIUSDT"]
            }
        },
        cpm_rehearsal={
            "submit_rehearsal_shape_ready": True,
            "synthetic_fresh_signal_rehearsal": {
                "fresh_signal_submit_rehearsal_passed": True
            },
        },
        generated_at_utc="2026-06-30T00:00:00+00:00",
    )

    assert artifact["status"] == "four_candidate_runtime_activation_closure_ready"
    assert artifact["summary"]["p0_tasks_closed"] is True
    assert artifact["summary"]["p1_tasks_closed"] is True
    assert artifact["summary"]["action_time_boundary_ready_count"] == 3
    assert artifact["summary"]["live_submit_allowed_count"] == 0
    assert artifact["summary"]["formal_replay_review_opened_count"] == 1
    assert artifact["source_replay"]["execution_venue_match"] is False
    assert artifact["interaction"]["remote_interaction_count"] == 0
    assert artifact["interaction"]["approaches_real_order"] is False
    assert artifact["authority_boundary"]["finalgate_called"] is False
    assert artifact["authority_boundary"]["operation_layer_called"] is False
    assert artifact["authority_boundary"]["exchange_write_called"] is False
    assert artifact["authority_boundary"]["order_created"] is False
    mi = next(
        row
        for row in artifact["activation_rows"]
        if row["strategy_group_id"] == "MI-001"
    )
    assert mi["formal_replay_review_opened"] is True
    assert mi["activation_contract_ready"] is False
    assert mi["action_time_boundary_ready"] is False
    assert mi["candidate_evidence_shape"]["candidate_authorization_created"] is False


def test_cpm_expands_readonly_watcher_scope_without_live_scope_change():
    module = _load_module()

    artifact = module.build_runtime_activation_closure(
        replay=_replay(),
        cpm_required_facts={
            "status": "cpm_required_facts_mapping_ready",
            "required_facts_mapping_ready": True,
        },
        cpm_capture={
            "watcher_scope": {
                "symbol_scope": ["ETHUSDT", "SOLUSDT", "AVAXUSDT", "SUIUSDT"]
            }
        },
        cpm_rehearsal={
            "submit_rehearsal_shape_ready": True,
            "synthetic_fresh_signal_rehearsal": {
                "fresh_signal_submit_rehearsal_passed": True
            },
        },
        generated_at_utc="2026-06-30T00:00:00+00:00",
    )
    cpm = next(
        row
        for row in artifact["activation_rows"]
        if row["strategy_group_id"] == "CPM-RO-001"
    )

    assert cpm["watcher_scope_symbols"] == [
        "ETHUSDT",
        "SOLUSDT",
        "AVAXUSDT",
        "SUIUSDT",
    ]
    assert cpm["expanded_readonly_watcher_symbols"] == [
        "SOLUSDT",
        "AVAXUSDT",
        "SUIUSDT",
    ]
    assert cpm["primary_live_submit_symbol_scope"] == ["ETHUSDT"]
    assert cpm["live_submit_symbol_scope_changed"] is False
    assert cpm["activation_contract_ready"] is True
