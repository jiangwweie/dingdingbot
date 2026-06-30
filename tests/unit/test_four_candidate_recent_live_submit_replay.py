from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "build_four_candidate_recent_live_submit_replay.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_four_candidate_recent_live_submit_replay",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _tradeability() -> dict:
    return {
        "decision_rows": [
            {
                "strategy_group_id": "MPG-001",
                "stage": "armed_observation",
                "decision": "not_tradable_market_wait",
                "can_trade_now": False,
                "first_blocker_class": "fresh_executable_signal_absent",
                "blocker_owner": "market",
            },
            {
                "strategy_group_id": "BRF2-001",
                "stage": "armed_observation",
                "decision": "not_tradable_market_wait",
                "can_trade_now": False,
                "first_blocker_class": "short_squeeze_risk_state_disable_active",
                "blocker_owner": "market",
            },
            {
                "strategy_group_id": "SOR-001",
                "stage": "armed_observation",
                "decision": "not_tradable_market_wait",
                "can_trade_now": False,
                "first_blocker_class": "fresh_session_range_signal_absent",
                "blocker_owner": "market",
            },
            {
                "strategy_group_id": "CPM-RO-001",
                "stage": "armed_observation",
                "decision": "not_tradable_market_wait",
                "can_trade_now": False,
                "first_blocker_class": "fresh_cpm_long_signal_absent",
                "blocker_owner": "market",
            },
        ]
    }


def _hourly_rows(*, start_ms: int, count: int, base: float, step: float) -> list[list]:
    rows = []
    price = base
    for index in range(count):
        price += step
        high = price * 1.006
        low = price * 0.994
        rows.append(
            [
                start_ms + index * 60 * 60 * 1000,
                f"{price - step / 2:.6f}",
                f"{high:.6f}",
                f"{low:.6f}",
                f"{price:.6f}",
                "1000",
            ]
        )
    return rows


def _sor_15m_rows(*, start_ms: int, count: int, base: float) -> list[list]:
    rows = []
    for index in range(count):
        timestamp = start_ms + index * 15 * 60 * 1000
        minute_of_day = (timestamp // 60000) % (24 * 60)
        price = base
        if 13 * 60 + 30 <= minute_of_day < 14 * 60 + 30:
            price = base * (1 + (minute_of_day - (13 * 60 + 30)) / 100000)
        elif 14 * 60 + 30 <= minute_of_day <= 18 * 60:
            price = base * 1.02
        rows.append(
            [
                timestamp,
                f"{price * 0.998:.6f}",
                f"{price * 1.004:.6f}",
                f"{price * 0.996:.6f}",
                f"{price:.6f}",
                "800",
            ]
        )
    return rows


def _market_data() -> dict:
    start_ms = 1_800_000_000_000
    rising = _hourly_rows(start_ms=start_ms, count=400, base=100, step=0.18)
    strong = _hourly_rows(start_ms=start_ms, count=400, base=80, step=0.32)
    falling = _hourly_rows(start_ms=start_ms, count=400, base=200, step=-0.22)
    flat = _hourly_rows(start_ms=start_ms, count=400, base=50, step=0.01)
    sor = _sor_15m_rows(start_ms=start_ms, count=14 * 24 * 4, base=100)
    return {
        "source": "coinbase_exchange_public_candles_fallback",
        "primary_source_error": "HTTPError:451 unavailable",
        "symbols": {
            "BTCUSDT": {"1h": falling, "15m": sor},
            "ETHUSDT": {"1h": rising, "15m": sor},
            "SOLUSDT": {"1h": strong, "15m": sor},
            "AVAXUSDT": {"1h": strong, "15m": sor},
            "SUIUSDT": {"1h": strong, "15m": sor},
            "OPUSDT": {"1h": flat, "15m": sor},
        }
    }


def test_recent_counterfactual_replay_is_non_authority_and_finds_review_signals():
    module = _load_module()

    artifact = module.build_recent_live_submit_replay(
        tradeability=_tradeability(),
        market_data=_market_data(),
        generated_at_utc="2026-06-30T00:00:00+00:00",
    )

    assert artifact["status"] == "recent_counterfactual_replay_ready"
    assert artifact["summary"]["counterfactual_review_signal_count"] > 0
    assert artifact["summary"]["missed_opportunity_review_count"] > 0
    assert artifact["summary"]["unique_review_signal_count"] > 0
    assert artifact["summary"]["window_cumulative_signal_count"] >= artifact["summary"]["unique_review_signal_count"]
    assert artifact["summary"]["window_cumulative_missed_opportunity_count"] >= artifact["summary"]["unique_missed_opportunity_count"]
    assert artifact["summary"]["would_reach_action_time_boundary_count"] > 0
    assert artifact["summary"]["counterfactual_live_submit_allowed_count"] == 0
    source = artifact["data_sources"]["public_market_candles"]
    assert source["venue_basis"] == "coinbase_spot_proxy"
    assert source["execution_venue_match"] is False
    assert source["absorbability_grade"] == "review_only_proxy"
    assert source["primary_source_error"] == "HTTPError:451 unavailable"
    assert artifact["authority_boundary"]["tradeability_decision_source"] is False
    assert artifact["authority_boundary"]["runtime_safety_state_source"] is False
    assert artifact["authority_boundary"]["candidate_authorization_created"] is False
    assert artifact["authority_boundary"]["finalgate_called"] is False
    assert artifact["authority_boundary"]["operation_layer_called"] is False
    assert artifact["authority_boundary"]["exchange_write_called"] is False
    assert artifact["authority_boundary"]["order_created"] is False
    assert artifact["interaction"]["remote_interaction_count"] == 0
    assert artifact["interaction"]["approaches_real_order"] is False
    mpg = next(
        row for row in artifact["strategy_rows"] if row["strategy_group_id"] == "MPG-001"
    )
    assert all("per_symbol_results" in window for window in mpg["window_results"])
    assert {
        item["symbol"] for item in mpg["window_results"][0]["per_symbol_results"]
    } == set(mpg["replay_symbol_universe"])
    top_event = artifact["summary"]["top_missed_events"][0]
    assert top_event["exact_next_blocker"]
    assert top_event["live_submit_allowed"] is False


def test_brf2_counterfactual_short_uses_event_time_squeeze_proxy():
    module = _load_module()

    artifact = module.build_recent_live_submit_replay(
        tradeability=_tradeability(),
        market_data=_market_data(),
        generated_at_utc="2026-06-30T00:00:00+00:00",
    )
    brf2 = next(
        row for row in artifact["strategy_rows"] if row["strategy_group_id"] == "BRF2-001"
    )
    events = [
        event
        for window in brf2["window_results"]
        for event in window["counterfactual_events"]
    ]

    assert events
    assert all(
        event["event_time_squeeze_proxy"]["funding_proxy"]
        == "unavailable_cross_venue_spot_proxy"
        for event in events
    )
    assert all(
        event["first_blocker_class"] == "short_squeeze_risk_state_disable_active"
        for event in events
        if event["event_time_squeeze_proxy"]["squeeze_disable_active"]
    )
    assert all(
        event["would_reach_action_time_boundary"]
        == (not event["event_time_squeeze_proxy"]["squeeze_disable_active"])
        for event in events
    )
    assert all(event["symbol_scope_review_required"] is False for event in events)
    assert all(event["live_submit_allowed"] is False for event in events)
    assert "BRF2-001" not in artifact["summary"]["symbol_scope_review_strategy_ids"]
    assert all(
        item["symbol_scope_review_required"] is False
        for window in brf2["window_results"]
        for item in window["per_symbol_results"]
    )
