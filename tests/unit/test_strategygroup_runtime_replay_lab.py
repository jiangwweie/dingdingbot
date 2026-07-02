from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from src.domain.strategygroup_runtime_replay import (
    EXPECTED_BRF001_L1_REPLAY_CASES,
    EXPECTED_BTPC001_L2_REPLAY_CASES,
    EXPECTED_LSR001_L1_REPLAY_CASES,
    EXPECTED_SYNTHETIC_FIXTURE_CASES,
    EXPECTED_MPG001_REPLAY_CORPUS_CASES,
    EXPECTED_POST_SUBMIT_SIMULATOR_CASES,
    EXPECTED_VCB001_L1_REPLAY_CASES,
    build_mpg001_replay_lab_report,
)
from scripts.run_strategygroup_runtime_replay_lab import _owner_markdown


def test_mpg001_replay_lab_contract_is_non_executing_and_owner_readable() -> None:
    report = build_mpg001_replay_lab_report(generated_at_ms=1781750000000)

    assert report.status == "passed"
    assert report.strategy_group_id == "MPG-001"
    assert report.checks == {
        "mpg001_replay_sample_present": True,
        "mpg001_replay_corpus_cases_present": True,
        "btpc001_l2_shadow_replay_cases_present": True,
        "btpc001_l2_would_enter_review_shape_present": True,
        "btpc001_l2_blocked_cases_do_not_reach_operation_layer": True,
        "vcb001_l1_observe_replay_cases_present": True,
        "vcb001_l1_would_enter_review_shape_present": True,
        "vcb001_l1_cases_do_not_reach_prepare_or_operation_layer": True,
        "lsr001_l1_observe_replay_cases_present": True,
        "lsr001_l1_would_enter_review_shape_present": True,
        "lsr001_l1_cases_do_not_reach_prepare_or_operation_layer": True,
        "brf001_l1_observe_replay_cases_present": True,
        "brf001_l1_would_enter_review_shape_present": True,
        "brf001_l1_cases_do_not_reach_prepare_or_operation_layer": True,
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
    assert report.safety_invariants == {
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
    assert report.owner_summary.current_state == "signal_observation_replay_ready"
    assert report.owner_summary.non_authority_checkpoint == (
        "Use replay/synthetic rehearsal while P0 waits for a real fresh signal."
    )


def test_btpc001_l2_shadow_replay_expands_observation_without_execution() -> None:
    report = build_mpg001_replay_lab_report(generated_at_ms=1781750000000)

    cases = {item.fixture_case for item in report.l2_shadow_replay_samples}
    assert cases == EXPECTED_BTPC001_L2_REPLAY_CASES
    assert report.checks["btpc001_l2_shadow_replay_cases_present"] is True
    assert report.checks["btpc001_l2_would_enter_review_shape_present"] is True
    assert (
        report.checks["btpc001_l2_blocked_cases_do_not_reach_operation_layer"]
        is True
    )

    would_enter = next(
        item
        for item in report.l2_shadow_replay_samples
        if item.fixture_case == "bear_pullback_would_enter"
    )
    assert would_enter.strategy_group_id == "BTPC-001"
    assert would_enter.signal_status == "would_enter_observe_only"
    assert would_enter.required_facts_ready is True
    assert would_enter.stage_results["prepare_chain_ready"] is True
    assert would_enter.stage_results["operation_layer_shape_reachable"] is False
    assert would_enter.not_live_market_signal is True
    assert would_enter.not_execution_authority is True
    assert would_enter.operation_layer_submit_allowed is False
    assert would_enter.exchange_write_allowed is False
    assert would_enter.real_order_allowed is False

    blocked = [
        item
        for item in report.l2_shadow_replay_samples
        if item.fixture_case != "bear_pullback_would_enter"
    ]
    assert blocked
    assert all(
        item.stage_results["operation_layer_shape_reachable"] is False
        for item in blocked
    )
    assert all(item.real_order_allowed is False for item in report.l2_shadow_replay_samples)


def test_vcb001_l1_observe_replay_expands_visibility_without_shadow_authority() -> None:
    report = build_mpg001_replay_lab_report(generated_at_ms=1781750000000)

    vcb_samples = [
        item
        for item in report.l1_observe_replay_samples
        if item.strategy_group_id == "VCB-001"
    ]
    cases = {item.fixture_case for item in vcb_samples}
    assert cases == EXPECTED_VCB001_L1_REPLAY_CASES
    assert report.checks["vcb001_l1_observe_replay_cases_present"] is True
    assert report.checks["vcb001_l1_would_enter_review_shape_present"] is True
    assert (
        report.checks["vcb001_l1_cases_do_not_reach_prepare_or_operation_layer"]
        is True
    )

    would_enter = next(
        item
        for item in vcb_samples
        if item.fixture_case == "compression_breakout_would_enter"
    )
    assert would_enter.strategy_group_id == "VCB-001"
    assert would_enter.signal_status == "would_enter_observe_only"
    assert would_enter.required_facts_ready is True
    assert would_enter.stage_results["prepare_chain_ready"] is False
    assert would_enter.stage_results["operation_layer_shape_reachable"] is False
    assert would_enter.not_live_market_signal is True
    assert would_enter.not_execution_authority is True
    assert would_enter.operation_layer_submit_allowed is False
    assert would_enter.exchange_write_allowed is False
    assert would_enter.real_order_allowed is False

    assert all(
        item.stage_results["prepare_chain_ready"] is False
        and item.stage_results["operation_layer_shape_reachable"] is False
        for item in vcb_samples
    )
    assert all(item.real_order_allowed is False for item in vcb_samples)


def test_lsr001_l1_observe_replay_keeps_rewrite_gap_visible_without_shadow_authority() -> None:
    report = build_mpg001_replay_lab_report(generated_at_ms=1781750000000)

    lsr_samples = [
        item
        for item in report.l1_observe_replay_samples
        if item.strategy_group_id == "LSR-001"
    ]
    cases = {item.fixture_case for item in lsr_samples}
    assert cases == EXPECTED_LSR001_L1_REPLAY_CASES
    assert report.checks["lsr001_l1_observe_replay_cases_present"] is True
    assert report.checks["lsr001_l1_would_enter_review_shape_present"] is True
    assert (
        report.checks["lsr001_l1_cases_do_not_reach_prepare_or_operation_layer"]
        is True
    )

    would_enter = next(
        item
        for item in lsr_samples
        if item.fixture_case == "liquidity_sweep_long_would_enter_current_v0"
    )
    assert would_enter.signal_status == "would_enter_observe_only_current_v0"
    assert would_enter.required_facts_ready is True
    assert would_enter.stage_results["prepare_chain_ready"] is False
    assert would_enter.stage_results["operation_layer_shape_reachable"] is False
    assert would_enter.not_live_market_signal is True
    assert would_enter.not_execution_authority is True
    assert would_enter.operation_layer_submit_allowed is False
    assert would_enter.exchange_write_allowed is False
    assert would_enter.real_order_allowed is False

    rewrite = next(
        item
        for item in lsr_samples
        if item.fixture_case == "short_revival_rewrite_needed"
    )
    assert rewrite.review_recommendation.value == "revise"
    assert rewrite.stage_results["prepare_chain_ready"] is False
    assert rewrite.stage_results["operation_layer_shape_reachable"] is False


def test_brf001_l1_observe_replay_expands_bear_rally_failure_visibility_without_shadow_authority() -> None:
    report = build_mpg001_replay_lab_report(generated_at_ms=1781750000000)

    brf_samples = [
        item
        for item in report.l1_observe_replay_samples
        if item.strategy_group_id == "BRF-001"
    ]
    cases = {item.fixture_case for item in brf_samples}
    assert cases == EXPECTED_BRF001_L1_REPLAY_CASES
    assert report.checks["brf001_l1_observe_replay_cases_present"] is True
    assert report.checks["brf001_l1_would_enter_review_shape_present"] is True
    assert (
        report.checks["brf001_l1_cases_do_not_reach_prepare_or_operation_layer"]
        is True
    )

    would_enter = next(
        item
        for item in brf_samples
        if item.fixture_case == "bear_rally_failure_short_would_enter"
    )
    assert would_enter.signal_status == "would_enter_observe_only"
    assert would_enter.required_facts_ready is True
    assert would_enter.stage_results["prepare_chain_ready"] is False
    assert would_enter.stage_results["operation_layer_shape_reachable"] is False
    assert would_enter.not_live_market_signal is True
    assert would_enter.not_execution_authority is True
    assert would_enter.operation_layer_submit_allowed is False
    assert would_enter.exchange_write_allowed is False
    assert would_enter.real_order_allowed is False

    revision = next(
        item
        for item in brf_samples
        if item.fixture_case == "short_squeeze_risk_revision_needed"
    )
    assert revision.review_recommendation.value == "revise"
    assert revision.stage_results["prepare_chain_ready"] is False
    assert revision.stage_results["operation_layer_shape_reachable"] is False


def test_tracked_lsr_vcb_replay_corpus_carries_economic_review_fields() -> None:
    lsr = json.loads(
        Path(
            "docs/current/strategy-group-handoffs/LSR-001/replay/lsr-001-l1-observe-replay-corpus.json"
        ).read_text(encoding="utf-8")
    )
    vcb = json.loads(
        Path(
            "docs/current/strategy-group-handoffs/VCB-001/replay/vcb-001-l1-observe-replay-corpus.json"
        ).read_text(encoding="utf-8")
    )
    required_cases = {
        "liquidity_sweep_long_would_enter_current_v0",
        "short_revival_rewrite_needed",
        "compression_breakout_would_enter",
        "false_breakout_disable_needed",
    }
    samples = {
        item["fixture_case"]: item
        for item in lsr["replay_samples"] + vcb["replay_samples"]
        if item["fixture_case"] in required_cases
    }

    assert set(samples) == required_cases
    for sample in samples.values():
        cost_review = sample["cost_review"]
        assert cost_review["fill_slot_assumption"]
        assert cost_review["leverage_survival_note"]
        assert cost_review["does_not_lower_owner_selected_leverage"] is True
        assert cost_review["not_submit_authority"] is True


def test_mpg001_replay_lab_covers_required_synthetic_fixtures() -> None:
    report = build_mpg001_replay_lab_report(generated_at_ms=1781750000000)

    fixture_cases = {item.fixture_case for item in report.synthetic_fixtures}
    assert fixture_cases == EXPECTED_SYNTHETIC_FIXTURE_CASES

    fresh = next(
        item for item in report.synthetic_fixtures if item.fixture_case == "fresh_signal_pass"
    )
    assert fresh.signal_confidence == Decimal("0.62")
    assert fresh.stage_results["prepare_chain_ready"] is True
    assert fresh.stage_results["operation_layer_shape_reachable"] is True
    assert fresh.stage_results["real_submit_allowed"] is False

    blocked = [
        item
        for item in report.synthetic_fixtures
        if item.fixture_case != "fresh_signal_pass"
    ]
    assert blocked
    assert all(item.stage_results["operation_layer_shape_reachable"] is False for item in blocked)
    assert all(
        item.stage_results["real_submit_allowed"] is False
        for item in report.synthetic_fixtures
    )
    assert all(item.not_live_market_signal is True for item in report.synthetic_fixtures)


def test_replay_report_keeps_freqtrade_as_future_sidecar_not_authority() -> None:
    report = build_mpg001_replay_lab_report(generated_at_ms=1781750000000)

    assert report.external_adapter_policy == {
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
    assert report.checks["external_framework_sidecar_only"] is True


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
    report = build_mpg001_replay_lab_report(generated_at_ms=1781750000000)

    corpus_cases = {item.fixture_case for item in report.replay_samples}
    assert corpus_cases == EXPECTED_MPG001_REPLAY_CORPUS_CASES
    assert report.checks["mpg001_replay_corpus_cases_present"] is True
    assert report.checks["cost_review_skeleton_present"] is True

    for event in report.replay_samples:
        assert event.replay_only is True
        assert event.not_live_market_signal is True
        assert event.operation_layer_submit_allowed is False
        assert event.exchange_write_allowed is False
        assert event.real_order_allowed is False
        assert event.cost_review.fee_estimate_usdt >= Decimal("0")
        assert event.cost_review.slippage_estimate_usdt >= Decimal("0")
        assert event.cost_review.funding_impact_usdt is not None
        assert event.cost_review.min_qty_step_size_impact
        assert event.cost_review.fill_slot_assumption
        assert event.cost_review.leverage_survival_note
        assert event.cost_review.net_edge_note
        assert event.cost_review.does_not_lower_owner_selected_leverage is True
        assert event.cost_review.not_submit_authority is True


def test_post_submit_simulator_matrix_is_non_executing_and_review_ready() -> None:
    report = build_mpg001_replay_lab_report(generated_at_ms=1781750000000)

    simulator_cases = {item.case for item in report.post_submit_simulator_matrix}
    assert simulator_cases == EXPECTED_POST_SUBMIT_SIMULATOR_CASES
    assert report.checks["post_submit_simulator_cases_present"] is True
    assert report.checks["post_submit_simulator_non_executing"] is True

    protection_failed = next(
        item
        for item in report.post_submit_simulator_matrix
        if item.case == "entry_filled_sl_creation_failed"
    )
    assert protection_failed.protection_status == "failed"
    assert protection_failed.reduce_only_recovery_shape_reachable is True
    assert protection_failed.operation_layer_live_submit_called is False
    assert protection_failed.exchange_write_called is False

    for item in report.post_submit_simulator_matrix:
        assert item.finalize_shape_checked is True
        assert item.reconciliation_shape_checked is True
        assert item.budget_settlement_shape_checked is True
        assert item.review_shape_checked is True
        assert item.real_order_created is False
        assert item.exchange_write_called is False


def test_owner_markdown_summarizes_replay_corpus_post_submit_and_cost_review() -> None:
    report = build_mpg001_replay_lab_report(generated_at_ms=1781750000000)

    text = _owner_markdown(report)

    assert "- Replay samples: 8" in text
    assert "- L2 shadow replay samples: 5" in text
    assert "- L1 observe replay samples: 15" in text
    assert "- Post-submit simulator cases: 7" in text
    assert "- Cost review skeleton: present" in text
    assert "- Exchange write: 否" in text
    assert "- 接近真实订单: 否" in text
    assert "## StrategyGroup Replay Review" in text
    assert (
        "| BRF-001 | L1 observe | 5 | 2 | 1 | 3 | observe-only; no prepare chain |"
        in text
    )
    assert (
        "| VCB-001 | L1 observe | 5 | 2 | 1 | 3 | observe-only; no prepare chain |"
        in text
    )
    assert (
        "| LSR-001 | L1 observe | 5 | 2 | 1 | 3 | observe-only; no prepare chain |"
        in text
    )
    assert (
        "| BTPC-001 | L2 shadow | 5 | 2 | 1 | 3 | shadow evidence only; no Operation Layer |"
        in text
    )


def test_tracked_btpc001_l2_shadow_replay_corpus_exists() -> None:
    replay_path = Path(
        "docs/current/strategy-group-handoffs/BTPC-001/replay/"
        "btpc-001-l2-replay-corpus.json"
    )
    corpus = json.loads(replay_path.read_text(encoding="utf-8"))

    assert corpus["schema_version"] == "brc.strategygroup.l2_shadow_replay_corpus.v1"
    assert corpus["strategy_group_id"] == "BTPC-001"
    assert corpus["scope"] == "l2_shadow_candidate_observation_only"
    assert corpus["live_order_eligible"] is False
    assert {item["fixture_case"] for item in corpus["replay_samples"]} == (
        EXPECTED_BTPC001_L2_REPLAY_CASES
    )
    assert any(
        item["fixture_case"] == "bear_pullback_would_enter"
        and item["prepare_chain_ready"] is True
        and item["operation_layer_shape_reachable"] is False
        for item in corpus["replay_samples"]
    )


def test_tracked_vcb001_l1_observe_replay_corpus_exists() -> None:
    replay_path = Path(
        "docs/current/strategy-group-handoffs/VCB-001/replay/"
        "vcb-001-l1-observe-replay-corpus.json"
    )
    corpus = json.loads(replay_path.read_text(encoding="utf-8"))

    assert corpus["schema_version"] == "brc.strategygroup.l1_observe_replay_corpus.v1"
    assert corpus["strategy_group_id"] == "VCB-001"
    assert corpus["scope"] == "l1_observe_only_review"
    assert corpus["live_order_eligible"] is False
    assert {item["fixture_case"] for item in corpus["replay_samples"]} == (
        EXPECTED_VCB001_L1_REPLAY_CASES
    )
    assert any(
        item["fixture_case"] == "compression_breakout_would_enter"
        and item["prepare_chain_ready"] is False
        and item["operation_layer_shape_reachable"] is False
        for item in corpus["replay_samples"]
    )
    assert all(
        item["operation_layer_submit_allowed"] is False
        and item["exchange_write_allowed"] is False
        and item["real_order_allowed"] is False
        for item in corpus["replay_samples"]
    )


def test_tracked_lsr001_l1_observe_replay_corpus_exists() -> None:
    replay_path = Path(
        "docs/current/strategy-group-handoffs/LSR-001/replay/"
        "lsr-001-l1-observe-replay-corpus.json"
    )
    corpus = json.loads(replay_path.read_text(encoding="utf-8"))

    assert corpus["schema_version"] == "brc.strategygroup.l1_observe_replay_corpus.v1"
    assert corpus["strategy_group_id"] == "LSR-001"
    assert corpus["scope"] == "l1_observe_only_review"
    assert corpus["live_order_eligible"] is False
    assert {item["fixture_case"] for item in corpus["replay_samples"]} == (
        EXPECTED_LSR001_L1_REPLAY_CASES
    )
    assert any(
        item["fixture_case"] == "short_revival_rewrite_needed"
        and item["prepare_chain_ready"] is False
        and item["operation_layer_shape_reachable"] is False
        and item["review_recommendation"] == "revise"
        for item in corpus["replay_samples"]
    )
    assert all(
        item["operation_layer_submit_allowed"] is False
        and item["exchange_write_allowed"] is False
        and item["real_order_allowed"] is False
        for item in corpus["replay_samples"]
    )
    assert all(item["replay_only"] is True for item in corpus["replay_samples"])
    assert all(
        item["not_live_market_signal"] is True for item in corpus["replay_samples"]
    )
    assert all(
        item["not_execution_authority"] is True for item in corpus["replay_samples"]
    )
    assert all(
        item["operation_layer_submit_allowed"] is False
        for item in corpus["replay_samples"]
    )
    assert all(item["exchange_write_allowed"] is False for item in corpus["replay_samples"])
    assert all(item["real_order_allowed"] is False for item in corpus["replay_samples"])
    assert all(
        item["cost_review"]["not_submit_authority"] is True
        for item in corpus["replay_samples"]
    )


def test_tracked_brf001_l1_observe_replay_corpus_exists() -> None:
    replay_path = Path(
        "docs/current/strategy-group-handoffs/BRF-001/replay/"
        "brf-001-l1-observe-replay-corpus.json"
    )
    corpus = json.loads(replay_path.read_text(encoding="utf-8"))

    assert corpus["schema_version"] == "brc.strategygroup.l1_observe_replay_corpus.v1"
    assert corpus["strategy_group_id"] == "BRF-001"
    assert corpus["scope"] == "l1_observe_only_review"
    assert corpus["live_order_eligible"] is False
    assert {item["fixture_case"] for item in corpus["replay_samples"]} == (
        EXPECTED_BRF001_L1_REPLAY_CASES
    )
    assert any(
        item["fixture_case"] == "bear_rally_failure_short_would_enter"
        and item["prepare_chain_ready"] is False
        and item["operation_layer_shape_reachable"] is False
        for item in corpus["replay_samples"]
    )
    assert any(
        item["fixture_case"] == "short_squeeze_risk_revision_needed"
        and item["review_recommendation"] == "revise"
        for item in corpus["replay_samples"]
    )
    assert all(
        item["operation_layer_submit_allowed"] is False
        and item["exchange_write_allowed"] is False
        and item["real_order_allowed"] is False
        for item in corpus["replay_samples"]
    )
    assert all(item["replay_only"] is True for item in corpus["replay_samples"])
    assert all(
        item["not_live_market_signal"] is True for item in corpus["replay_samples"]
    )
    assert all(
        item["not_execution_authority"] is True for item in corpus["replay_samples"]
    )
    assert all(
        item["cost_review"]["not_submit_authority"] is True
        for item in corpus["replay_samples"]
    )


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
