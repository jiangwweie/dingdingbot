from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from src.domain.strategygroup_runtime_replay import (
    EXPECTED_SYNTHETIC_FIXTURE_CASES,
    build_mpg001_replay_lab_packet,
)


def test_mpg001_replay_lab_contract_is_non_executing_and_owner_readable() -> None:
    packet = build_mpg001_replay_lab_packet(generated_at_ms=1781750000000)

    assert packet.status == "passed"
    assert packet.strategy_group_id == "MPG-001"
    assert packet.checks == {
        "mpg001_replay_sample_present": True,
        "synthetic_fixture_cases_present": True,
        "fresh_pass_reaches_prepare_chain": True,
        "blocked_fixtures_do_not_reach_operation_layer": True,
        "replay_report_owner_readable": True,
        "external_framework_sidecar_only": True,
        "no_replay_or_synthetic_signal_has_live_authority": True,
    }
    assert packet.safety_invariants == {
        "replay_only": True,
        "synthetic_signals_are_not_live_market_signals": True,
        "external_framework_is_sidecar_only": True,
        "calls_tokyo_api": False,
        "finalgate_bypassed": False,
        "operation_layer_bypassed": False,
        "exchange_write_called": False,
        "real_order_created": False,
        "withdrawal_or_transfer_created": False,
        "modifies_secret_or_credentials": False,
        "modifies_live_profile": False,
        "modifies_order_sizing_defaults": False,
    }
    assert packet.owner_summary.current_state == "P0.5 replay_ready"
    assert packet.owner_summary.next_action == (
        "Use replay/synthetic rehearsal while P0 waits for a real fresh signal."
    )


def test_mpg001_replay_lab_covers_required_synthetic_fixtures() -> None:
    packet = build_mpg001_replay_lab_packet(generated_at_ms=1781750000000)

    fixture_cases = {item.fixture_case for item in packet.synthetic_fixtures}
    assert fixture_cases == EXPECTED_SYNTHETIC_FIXTURE_CASES

    fresh = next(
        item for item in packet.synthetic_fixtures if item.fixture_case == "fresh_signal_pass"
    )
    assert fresh.signal_confidence == Decimal("0.62")
    assert fresh.stage_results["prepare_chain_ready"] is True
    assert fresh.stage_results["operation_layer_shape_reachable"] is True
    assert fresh.stage_results["real_submit_allowed"] is False

    blocked = [
        item
        for item in packet.synthetic_fixtures
        if item.fixture_case != "fresh_signal_pass"
    ]
    assert blocked
    assert all(item.stage_results["operation_layer_shape_reachable"] is False for item in blocked)
    assert all(item.stage_results["real_submit_allowed"] is False for item in packet.synthetic_fixtures)
    assert all(item.not_live_market_signal is True for item in packet.synthetic_fixtures)


def test_replay_report_keeps_freqtrade_as_future_sidecar_not_authority() -> None:
    packet = build_mpg001_replay_lab_packet(generated_at_ms=1781750000000)

    assert packet.external_adapter_policy == {
        "freqtrade_role": "future_sidecar_research_adapter",
        "may_supply": [
            "external_backtest_summary",
            "signal_windows",
            "entry_exit_samples",
            "metric_summary",
            "parameter_sensitivity",
        ],
        "must_not_supply": [
            "FinalGate authority",
            "Operation Layer authority",
            "real-submit permission",
            "Owner state",
            "live signal identity",
        ],
    }
    assert packet.checks["external_framework_sidecar_only"] is True


def test_tracked_mpg001_replay_samples_match_runtime_contract() -> None:
    replay_dir = Path("docs/current/strategy-group-handoffs/MPG-001/replay")
    sample = json.loads(
        (replay_dir / "mpg-001-replay-sample.json").read_text(encoding="utf-8")
    )
    fixtures = json.loads(
        (replay_dir / "synthetic-signal-fixtures.json").read_text(encoding="utf-8")
    )

    assert sample["schema_version"] == "brc.strategygroup.runtime_replay_event.v1"
    assert sample["strategy_group_id"] == "MPG-001"
    assert sample["event_kind"] == "historical_window"
    assert sample["replay_only"] is True
    assert sample["not_live_market_signal"] is True
    assert sample["not_execution_authority"] is True
    assert sample["operation_layer_submit_allowed"] is False
    assert sample["exchange_write_allowed"] is False
    assert sample["real_order_allowed"] is False

    assert fixtures["schema_version"] == "brc.strategygroup.synthetic_fixture_set.v1"
    assert fixtures["strategy_group_id"] == "MPG-001"
    assert {item["fixture_case"] for item in fixtures["fixtures"]} == (
        EXPECTED_SYNTHETIC_FIXTURE_CASES
    )
    assert all(item["replay_only"] is True for item in fixtures["fixtures"])
    assert all(item["not_live_market_signal"] is True for item in fixtures["fixtures"])
    assert all(item["real_order_allowed"] is False for item in fixtures["fixtures"])
