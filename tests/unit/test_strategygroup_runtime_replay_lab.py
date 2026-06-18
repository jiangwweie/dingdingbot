from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from src.domain.strategygroup_runtime_replay import (
    EXPECTED_SYNTHETIC_FIXTURE_CASES,
    EXPECTED_MPG001_REPLAY_CORPUS_CASES,
    EXPECTED_POST_SUBMIT_SIMULATOR_CASES,
    build_mpg001_replay_lab_packet,
)
from scripts.run_strategygroup_runtime_replay_lab import _owner_markdown


def test_mpg001_replay_lab_contract_is_non_executing_and_owner_readable() -> None:
    packet = build_mpg001_replay_lab_packet(generated_at_ms=1781750000000)

    assert packet.status == "passed"
    assert packet.strategy_group_id == "MPG-001"
    assert packet.checks == {
        "mpg001_replay_sample_present": True,
        "mpg001_replay_corpus_cases_present": True,
        "synthetic_fixture_cases_present": True,
        "post_submit_simulator_cases_present": True,
        "post_submit_simulator_non_executing": True,
        "cost_review_skeleton_present": True,
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


def test_mpg001_replay_lab_covers_multi_window_replay_corpus_with_cost_review() -> None:
    packet = build_mpg001_replay_lab_packet(generated_at_ms=1781750000000)

    corpus_cases = {item.fixture_case for item in packet.replay_samples}
    assert corpus_cases == EXPECTED_MPG001_REPLAY_CORPUS_CASES
    assert packet.checks["mpg001_replay_corpus_cases_present"] is True
    assert packet.checks["cost_review_skeleton_present"] is True

    for event in packet.replay_samples:
        assert event.replay_only is True
        assert event.not_live_market_signal is True
        assert event.operation_layer_submit_allowed is False
        assert event.exchange_write_allowed is False
        assert event.real_order_allowed is False
        assert event.cost_review.fee_estimate_usdt >= Decimal("0")
        assert event.cost_review.slippage_estimate_usdt >= Decimal("0")
        assert event.cost_review.funding_impact_usdt is not None
        assert event.cost_review.min_qty_step_size_impact
        assert event.cost_review.net_edge_note
        assert event.cost_review.not_submit_authority is True


def test_post_submit_simulator_matrix_is_non_executing_and_review_ready() -> None:
    packet = build_mpg001_replay_lab_packet(generated_at_ms=1781750000000)

    simulator_cases = {item.case for item in packet.post_submit_simulator_matrix}
    assert simulator_cases == EXPECTED_POST_SUBMIT_SIMULATOR_CASES
    assert packet.checks["post_submit_simulator_cases_present"] is True
    assert packet.checks["post_submit_simulator_non_executing"] is True

    protection_failed = next(
        item
        for item in packet.post_submit_simulator_matrix
        if item.case == "entry_filled_sl_creation_failed"
    )
    assert protection_failed.protection_status == "failed"
    assert protection_failed.reduce_only_recovery_shape_reachable is True
    assert protection_failed.operation_layer_live_submit_called is False
    assert protection_failed.exchange_write_called is False

    for item in packet.post_submit_simulator_matrix:
        assert item.finalize_shape_checked is True
        assert item.reconciliation_shape_checked is True
        assert item.budget_settlement_shape_checked is True
        assert item.review_shape_checked is True
        assert item.real_order_created is False
        assert item.exchange_write_called is False


def test_owner_markdown_summarizes_replay_corpus_post_submit_and_cost_review() -> None:
    packet = build_mpg001_replay_lab_packet(generated_at_ms=1781750000000)

    text = _owner_markdown(packet)

    assert "- Replay samples: 8" in text
    assert "- Post-submit simulator cases: 7" in text
    assert "- Cost review skeleton: present" in text
    assert "- Exchange write: 否" in text
    assert "- 接近真实订单: 否" in text


def test_tracked_mpg001_replay_corpus_and_post_submit_matrix_exist() -> None:
    replay_dir = Path("docs/current/strategy-group-handoffs/MPG-001/replay")
    corpus = json.loads(
        (replay_dir / "mpg-001-replay-corpus.json").read_text(encoding="utf-8")
    )
    post_submit = json.loads(
        (replay_dir / "post-submit-simulator-matrix.json").read_text(encoding="utf-8")
    )

    assert corpus["schema_version"] == "brc.strategygroup.runtime_replay_corpus.v1"
    assert corpus["strategy_group_id"] == "MPG-001"
    assert {item["fixture_case"] for item in corpus["replay_samples"]} == (
        EXPECTED_MPG001_REPLAY_CORPUS_CASES
    )
    assert all(item["not_live_market_signal"] is True for item in corpus["replay_samples"])
    assert all(item["real_order_allowed"] is False for item in corpus["replay_samples"])
    assert all("cost_review" in item for item in corpus["replay_samples"])

    assert post_submit["schema_version"] == "brc.strategygroup.post_submit_simulator_matrix.v1"
    assert post_submit["strategy_group_id"] == "MPG-001"
    assert {item["case"] for item in post_submit["cases"]} == (
        EXPECTED_POST_SUBMIT_SIMULATOR_CASES
    )
    assert all(item["real_order_created"] is False for item in post_submit["cases"])
    assert all(item["exchange_write_called"] is False for item in post_submit["cases"])
