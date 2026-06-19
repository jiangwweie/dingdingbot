"""StrategyGroup runtime replay contract.

The replay lab is a non-executing rehearsal surface. It can describe
historical or synthetic signal windows, but it must never authorize a live
signal, Operation Layer submit, exchange write, or real order.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.strategy_family_signal import reject_forbidden_execution_fields


REPLAY_EVENT_SCHEMA = "brc.strategygroup.runtime_replay_event.v1"
REPLAY_REPORT_SCHEMA = "brc.strategygroup.runtime_replay_report.v1"
EXPECTED_SYNTHETIC_FIXTURE_CASES = {
    "no_signal",
    "fresh_signal_pass",
    "stale_signal",
    "missing_required_facts",
    "active_position_conflict",
    "open_order_conflict",
    "protection_missing",
    "allocated_profile_boundary_mismatch",
}
EXPECTED_MPG001_REPLAY_CORPUS_CASES = {
    "trend_continuation",
    "false_breakout",
    "fast_reversal",
    "choppy_no_trade",
    "stale_signal",
    "missing_facts",
    "active_position_conflict",
    "protection_missing",
}
EXPECTED_BTPC001_L2_REPLAY_CASES = {
    "bear_pullback_would_enter",
    "no_signal_bear_trend_not_ready",
    "strong_uptrend_conflict",
    "missing_derivatives_context",
    "stale_signal",
}
EXPECTED_VCB001_L1_REPLAY_CASES = {
    "compression_breakout_would_enter",
    "no_signal_no_compression",
    "false_breakout_disable_needed",
    "missing_compression_context",
    "stale_signal",
}
EXPECTED_LSR001_L1_REPLAY_CASES = {
    "liquidity_sweep_long_would_enter_current_v0",
    "short_revival_rewrite_needed",
    "no_signal_no_sweep_reclaim",
    "missing_range_context",
    "stale_signal",
}
EXPECTED_BRF001_L1_REPLAY_CASES = {
    "bear_rally_failure_short_would_enter",
    "no_signal_rally_not_failed",
    "short_squeeze_risk_revision_needed",
    "missing_rally_context",
    "stale_signal",
}
EXPECTED_POST_SUBMIT_SIMULATOR_CASES = {
    "entry_accepted_protection_ok",
    "entry_filled_sl_creation_failed",
    "partial_fill",
    "submit_rejected_before_acceptance",
    "position_closed_by_sl",
    "position_closed_by_tp1",
    "active_position_remains_open",
}


class StrategyGroupReplayModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReplayEventKind(str, Enum):
    HISTORICAL_WINDOW = "historical_window"
    SYNTHETIC_SIGNAL_FIXTURE = "synthetic_signal_fixture"


class ReplaySource(str, Enum):
    LOCAL_RUNTIME_REPLAY = "local_runtime_replay"
    EXTERNAL_SIDECAR_ADAPTER = "external_sidecar_adapter"


class ReplayReviewRecommendation(str, Enum):
    PROMOTE = "promote"
    KEEP_OBSERVING = "keep_observing"
    REVISE = "revise"
    PARK = "park"
    KILL = "kill"


class StrategyGroupReplayOwnerSummary(StrategyGroupReplayModel):
    current_state: str = Field(min_length=1, max_length=128)
    owner_intervention_required: Literal[False] = False
    next_action: str = Field(min_length=1, max_length=256)
    summary_lines: list[str] = Field(default_factory=list)


class StrategyGroupReplayCostReview(StrategyGroupReplayModel):
    fee_estimate_usdt: Decimal = Field(ge=Decimal("0"))
    slippage_estimate_usdt: Decimal = Field(ge=Decimal("0"))
    funding_impact_usdt: Decimal
    min_qty_step_size_impact: str = Field(min_length=1, max_length=256)
    fill_slot_assumption: str = Field(
        default="single_slot_review_only_not_execution_authority",
        min_length=1,
        max_length=256,
    )
    leverage_survival_note: str = Field(
        default="review_only_no_owner_profile_or_leverage_change",
        min_length=1,
        max_length=512,
    )
    net_edge_note: str = Field(min_length=1, max_length=512)
    does_not_lower_owner_selected_leverage: Literal[True] = True
    not_submit_authority: Literal[True] = True


def _default_cost_review() -> StrategyGroupReplayCostReview:
    return StrategyGroupReplayCostReview(
        fee_estimate_usdt=Decimal("0"),
        slippage_estimate_usdt=Decimal("0"),
        funding_impact_usdt=Decimal("0"),
        min_qty_step_size_impact="not_evaluated",
        net_edge_note="cost review skeleton only; not submit authority",
    )


class StrategyGroupReplayEvent(StrategyGroupReplayModel):
    schema_version: Literal["brc.strategygroup.runtime_replay_event.v1"] = (
        REPLAY_EVENT_SCHEMA
    )
    event_id: str = Field(min_length=1, max_length=192)
    strategy_group_id: str = Field(min_length=1, max_length=128)
    fixture_case: str = Field(min_length=1, max_length=128)
    event_kind: ReplayEventKind
    replay_source: ReplaySource = ReplaySource.LOCAL_RUNTIME_REPLAY
    symbol: str = Field(min_length=1, max_length=128)
    side: str = Field(min_length=1, max_length=32)
    observed_at_ms: int = Field(ge=0)
    freshness_window_seconds: int = Field(default=120, ge=1)
    signal_confidence: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    signal_status: str = Field(min_length=1, max_length=128)
    required_facts_ready: bool
    blocker_class: str = Field(min_length=1, max_length=128)
    expected_owner_state: str = Field(min_length=1, max_length=128)
    stage_results: dict[str, bool] = Field(default_factory=dict)
    simulated_exit_outcome: str = Field(min_length=1, max_length=128)
    cost_review: StrategyGroupReplayCostReview = Field(
        default_factory=_default_cost_review
    )
    review_recommendation: ReplayReviewRecommendation
    notes: list[str] = Field(default_factory=list)
    replay_only: Literal[True] = True
    not_live_market_signal: Literal[True] = True
    not_execution_authority: Literal[True] = True
    operation_layer_submit_allowed: Literal[False] = False
    exchange_write_allowed: Literal[False] = False
    real_order_allowed: Literal[False] = False

    @model_validator(mode="after")
    def _validate_replay_boundary(self) -> "StrategyGroupReplayEvent":
        reject_forbidden_execution_fields(
            self.model_dump(mode="python"),
            root="strategygroup_replay_event",
        )
        if self.event_kind == ReplayEventKind.SYNTHETIC_SIGNAL_FIXTURE:
            if self.fixture_case not in EXPECTED_SYNTHETIC_FIXTURE_CASES:
                raise ValueError("unknown synthetic fixture case")
        if self.event_kind == ReplayEventKind.HISTORICAL_WINDOW:
            known_historical_cases = (
                EXPECTED_MPG001_REPLAY_CORPUS_CASES
                | {"historical_momentum_continuation_sample"}
                | EXPECTED_BTPC001_L2_REPLAY_CASES
                | EXPECTED_VCB001_L1_REPLAY_CASES
                | EXPECTED_LSR001_L1_REPLAY_CASES
                | EXPECTED_BRF001_L1_REPLAY_CASES
            )
            if self.fixture_case not in known_historical_cases:
                raise ValueError("unknown historical replay case")
        return self


class StrategyGroupPostSubmitSimulatorCase(StrategyGroupReplayModel):
    case: str = Field(min_length=1, max_length=128)
    input_state: str = Field(min_length=1, max_length=256)
    expected_runtime_state: str = Field(min_length=1, max_length=256)
    protection_status: str = Field(min_length=1, max_length=128)
    reduce_only_recovery_shape_reachable: bool
    finalize_shape_checked: Literal[True] = True
    reconciliation_shape_checked: Literal[True] = True
    budget_settlement_shape_checked: Literal[True] = True
    review_shape_checked: Literal[True] = True
    operation_layer_live_submit_called: Literal[False] = False
    exchange_write_called: Literal[False] = False
    real_order_created: Literal[False] = False
    review_recommendation: ReplayReviewRecommendation
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_simulator_boundary(self) -> "StrategyGroupPostSubmitSimulatorCase":
        if self.case not in EXPECTED_POST_SUBMIT_SIMULATOR_CASES:
            raise ValueError("unknown post-submit simulator case")
        reject_forbidden_execution_fields(
            self.model_dump(mode="python"),
            root="strategygroup_post_submit_simulator_case",
        )
        return self


class StrategyGroupReplayReport(StrategyGroupReplayModel):
    schema_version: Literal["brc.strategygroup.runtime_replay_report.v1"] = (
        REPLAY_REPORT_SCHEMA
    )
    status: Literal["passed", "blocked"]
    generated_at_ms: int = Field(ge=0)
    strategy_group_id: Literal["MPG-001"]
    replay_samples: list[StrategyGroupReplayEvent] = Field(default_factory=list)
    l2_shadow_replay_samples: list[StrategyGroupReplayEvent] = Field(
        default_factory=list
    )
    l1_observe_replay_samples: list[StrategyGroupReplayEvent] = Field(
        default_factory=list
    )
    synthetic_fixtures: list[StrategyGroupReplayEvent] = Field(default_factory=list)
    post_submit_simulator_matrix: list[StrategyGroupPostSubmitSimulatorCase] = Field(
        default_factory=list
    )
    checks: dict[str, bool]
    blockers: list[str] = Field(default_factory=list)
    owner_summary: StrategyGroupReplayOwnerSummary
    external_adapter_policy: dict[str, Any]
    safety_invariants: dict[str, bool]

    @model_validator(mode="after")
    def _validate_report_boundary(self) -> "StrategyGroupReplayReport":
        reject_forbidden_execution_fields(
            self.model_dump(mode="python"),
            root="strategygroup_replay_report",
        )
        return self


def _base_stage_results(
    *,
    prepare_chain_ready: bool,
    operation_layer_shape_reachable: bool,
) -> dict[str, bool]:
    return {
        "signal_evaluated": True,
        "required_facts_gate_checked": True,
        "prepare_chain_ready": prepare_chain_ready,
        "candidate_authorization_dry_run_ready": prepare_chain_ready,
        "finalgate_dry_run_reachable": prepare_chain_ready,
        "operation_layer_shape_reachable": operation_layer_shape_reachable,
        "real_submit_allowed": False,
        "exchange_write_called": False,
    }


def _event(
    *,
    strategy_group_id: str = "MPG-001",
    event_id: str,
    fixture_case: str,
    event_kind: ReplayEventKind,
    symbol: str,
    side: str,
    observed_at_ms: int,
    signal_confidence: Decimal,
    signal_status: str,
    required_facts_ready: bool,
    blocker_class: str,
    expected_owner_state: str,
    prepare_chain_ready: bool,
    operation_layer_shape_reachable: bool,
    simulated_exit_outcome: str,
    review_recommendation: ReplayReviewRecommendation,
    notes: list[str] | None = None,
    cost_review: StrategyGroupReplayCostReview | None = None,
) -> StrategyGroupReplayEvent:
    return StrategyGroupReplayEvent(
        event_id=event_id,
        strategy_group_id=strategy_group_id,
        fixture_case=fixture_case,
        event_kind=event_kind,
        symbol=symbol,
        side=side,
        observed_at_ms=observed_at_ms,
        signal_confidence=signal_confidence,
        signal_status=signal_status,
        required_facts_ready=required_facts_ready,
        blocker_class=blocker_class,
        expected_owner_state=expected_owner_state,
        stage_results=_base_stage_results(
            prepare_chain_ready=prepare_chain_ready,
            operation_layer_shape_reachable=operation_layer_shape_reachable,
        ),
        simulated_exit_outcome=simulated_exit_outcome,
        cost_review=cost_review or _default_cost_review(),
        review_recommendation=review_recommendation,
        notes=notes or [],
    )


def _cost_review(
    *,
    fee: str,
    slippage: str,
    funding: str,
    min_qty_step: str,
    note: str,
    fill_slot: str = "single_slot_review_only_not_execution_authority",
    leverage_survival: str = "review_only_no_owner_profile_or_leverage_change",
) -> StrategyGroupReplayCostReview:
    return StrategyGroupReplayCostReview(
        fee_estimate_usdt=Decimal(fee),
        slippage_estimate_usdt=Decimal(slippage),
        funding_impact_usdt=Decimal(funding),
        min_qty_step_size_impact=min_qty_step,
        fill_slot_assumption=fill_slot,
        leverage_survival_note=leverage_survival,
        net_edge_note=note,
    )


def mpg001_replay_sample_event(*, observed_at_ms: int) -> StrategyGroupReplayEvent:
    return _event(
        event_id="mpg-001-replay-sample-001",
        fixture_case="trend_continuation",
        event_kind=ReplayEventKind.HISTORICAL_WINDOW,
        symbol="MSTRUSDT",
        side="long",
        observed_at_ms=observed_at_ms,
        signal_confidence=Decimal("0.62"),
        signal_status="fresh_signal_replay",
        required_facts_ready=True,
        blocker_class="none",
        expected_owner_state="processing",
        prepare_chain_ready=True,
        operation_layer_shape_reachable=True,
        simulated_exit_outcome="tp1_then_runner_or_hard_stop_review",
        cost_review=_cost_review(
            fee="0.018",
            slippage="0.035",
            funding="0.000",
            min_qty_step="passes_min_qty_and_step_size_shape",
            note="trend continuation sample has positive gross-edge shape after estimated friction",
        ),
        review_recommendation=ReplayReviewRecommendation.KEEP_OBSERVING,
        notes=[
            "Historical replay sample only.",
            "May exercise dry-run chain shape but is not a live market signal.",
        ],
    )


def mpg001_replay_corpus(*, observed_at_ms: int) -> list[StrategyGroupReplayEvent]:
    blocked_stage = {
        "prepare_chain_ready": False,
        "operation_layer_shape_reachable": False,
    }
    return [
        mpg001_replay_sample_event(observed_at_ms=observed_at_ms),
        _event(
            event_id="mpg-001-replay-false-breakout",
            fixture_case="false_breakout",
            event_kind=ReplayEventKind.HISTORICAL_WINDOW,
            symbol="MSTRUSDT",
            side="long",
            observed_at_ms=observed_at_ms + 1_000,
            signal_confidence=Decimal("0.58"),
            signal_status="fresh_signal_replay_false_breakout",
            required_facts_ready=True,
            blocker_class="review_only_warning",
            expected_owner_state="processing",
            prepare_chain_ready=True,
            operation_layer_shape_reachable=True,
            simulated_exit_outcome="hard_stop_or_fast_review_loss_shape",
            cost_review=_cost_review(
                fee="0.018",
                slippage="0.048",
                funding="0.000",
                min_qty_step="passes_min_qty_and_step_size_shape",
                note="false breakout keeps execution path valid but review should revise signal quality",
            ),
            review_recommendation=ReplayReviewRecommendation.REVISE,
            notes=["Replay warning only; weak evidence is not a live-safety blocker."],
        ),
        _event(
            event_id="mpg-001-replay-fast-reversal",
            fixture_case="fast_reversal",
            event_kind=ReplayEventKind.HISTORICAL_WINDOW,
            symbol="COINUSDT",
            side="long",
            observed_at_ms=observed_at_ms + 2_000,
            signal_confidence=Decimal("0.55"),
            signal_status="fresh_signal_replay_fast_reversal",
            required_facts_ready=True,
            blocker_class="review_only_warning",
            expected_owner_state="processing",
            prepare_chain_ready=True,
            operation_layer_shape_reachable=True,
            simulated_exit_outcome="runner_invalidated_before_tp1_shape",
            cost_review=_cost_review(
                fee="0.016",
                slippage="0.052",
                funding="-0.003",
                min_qty_step="passes_min_qty_and_step_size_shape",
                note="fast reversal remains useful to rehearse exit and review downgrade behavior",
            ),
            review_recommendation=ReplayReviewRecommendation.REVISE,
            notes=["Exercises fast exit review shape without live authority."],
        ),
        _event(
            event_id="mpg-001-replay-choppy-no-trade",
            fixture_case="choppy_no_trade",
            event_kind=ReplayEventKind.HISTORICAL_WINDOW,
            symbol="MSTRUSDT",
            side="none",
            observed_at_ms=observed_at_ms + 3_000,
            signal_confidence=Decimal("0.31"),
            signal_status="no_trade_choppy_regime",
            required_facts_ready=True,
            blocker_class="waiting_for_market",
            expected_owner_state="waiting_for_opportunity",
            simulated_exit_outcome="not_applicable",
            cost_review=_cost_review(
                fee="0",
                slippage="0",
                funding="0",
                min_qty_step="not_applicable_no_trade",
                note="choppy window should stay quiet and preserve capital for right-tail windows",
            ),
            review_recommendation=ReplayReviewRecommendation.KEEP_OBSERVING,
            notes=["No candidate/auth should be generated in choppy replay."],
            **blocked_stage,
        ),
        _event(
            event_id="mpg-001-replay-stale-signal",
            fixture_case="stale_signal",
            event_kind=ReplayEventKind.HISTORICAL_WINDOW,
            symbol="MSTRUSDT",
            side="long",
            observed_at_ms=observed_at_ms - 300_000,
            signal_confidence=Decimal("0.63"),
            signal_status="stale_signal_replay",
            required_facts_ready=True,
            blocker_class="missing_fact",
            expected_owner_state="temporarily_unavailable",
            simulated_exit_outcome="not_applicable",
            cost_review=_cost_review(
                fee="0",
                slippage="0",
                funding="0",
                min_qty_step="not_applicable_stale_signal",
                note="stale replay must prove freshness rejection before submit authority",
            ),
            review_recommendation=ReplayReviewRecommendation.REVISE,
            notes=["Stale replay never reaches Operation Layer shape."],
            **blocked_stage,
        ),
        _event(
            event_id="mpg-001-replay-missing-facts",
            fixture_case="missing_facts",
            event_kind=ReplayEventKind.HISTORICAL_WINDOW,
            symbol="MSTRUSDT",
            side="long",
            observed_at_ms=observed_at_ms + 4_000,
            signal_confidence=Decimal("0.61"),
            signal_status="fresh_signal_replay_missing_facts",
            required_facts_ready=False,
            blocker_class="missing_fact",
            expected_owner_state="temporarily_unavailable",
            simulated_exit_outcome="not_applicable",
            cost_review=_cost_review(
                fee="0",
                slippage="0",
                funding="0",
                min_qty_step="not_evaluated_missing_facts",
                note="missing facts block before any execution-cost authority matters",
            ),
            review_recommendation=ReplayReviewRecommendation.REVISE,
            notes=["RequiredFacts missing blocks prepare chain."],
            **blocked_stage,
        ),
        _event(
            event_id="mpg-001-replay-active-position-conflict",
            fixture_case="active_position_conflict",
            event_kind=ReplayEventKind.HISTORICAL_WINDOW,
            symbol="MSTRUSDT",
            side="long",
            observed_at_ms=observed_at_ms + 5_000,
            signal_confidence=Decimal("0.60"),
            signal_status="fresh_signal_replay_active_position_conflict",
            required_facts_ready=True,
            blocker_class="active_position_resolution",
            expected_owner_state="needs_intervention",
            simulated_exit_outcome="not_applicable",
            cost_review=_cost_review(
                fee="0",
                slippage="0",
                funding="0",
                min_qty_step="not_applicable_conflict",
                note="active position conflict blocks duplicate exposure regardless of edge",
            ),
            review_recommendation=ReplayReviewRecommendation.REVISE,
            notes=["Conflict replay must not reach Operation Layer shape."],
            **blocked_stage,
        ),
        _event(
            event_id="mpg-001-replay-protection-missing",
            fixture_case="protection_missing",
            event_kind=ReplayEventKind.HISTORICAL_WINDOW,
            symbol="MSTRUSDT",
            side="long",
            observed_at_ms=observed_at_ms + 6_000,
            signal_confidence=Decimal("0.60"),
            signal_status="fresh_signal_replay_protection_missing",
            required_facts_ready=True,
            blocker_class="hard_safety_stop",
            expected_owner_state="needs_intervention",
            simulated_exit_outcome="not_applicable",
            cost_review=_cost_review(
                fee="0",
                slippage="0",
                funding="0",
                min_qty_step="not_applicable_missing_protection",
                note="missing protection remains a mechanical hard stop, not generic risk aversion",
            ),
            review_recommendation=ReplayReviewRecommendation.REVISE,
            notes=["Protection-missing replay proves hard stop behavior."],
            **blocked_stage,
        ),
    ]


def btpc001_l2_shadow_replay_corpus(
    *, observed_at_ms: int
) -> list[StrategyGroupReplayEvent]:
    blocked_stage = {
        "prepare_chain_ready": False,
        "operation_layer_shape_reachable": False,
    }
    return [
        _event(
            strategy_group_id="BTPC-001",
            event_id="btpc-001-l2-bear-pullback-would-enter",
            fixture_case="bear_pullback_would_enter",
            event_kind=ReplayEventKind.HISTORICAL_WINDOW,
            symbol="SOLUSDT",
            side="short",
            observed_at_ms=observed_at_ms + 10_000,
            signal_confidence=Decimal("0.57"),
            signal_status="would_enter_observe_only",
            required_facts_ready=True,
            blocker_class="review_only_warning",
            expected_owner_state="running",
            prepare_chain_ready=True,
            operation_layer_shape_reachable=False,
            simulated_exit_outcome="l2_shadow_review_only_no_submit",
            cost_review=_cost_review(
                fee="0.014",
                slippage="0.041",
                funding="0.002",
                min_qty_step="review_only_exchange_rules_shape_present",
                note="BTPC L2 would-enter sample expands observation coverage without L4 authority",
            ),
            review_recommendation=ReplayReviewRecommendation.KEEP_OBSERVING,
            notes=[
                "L2 shadow candidate observation only.",
                "This can create review evidence but cannot enter FinalGate or Operation Layer.",
            ],
        ),
        _event(
            strategy_group_id="BTPC-001",
            event_id="btpc-001-l2-no-signal-bear-trend-not-ready",
            fixture_case="no_signal_bear_trend_not_ready",
            event_kind=ReplayEventKind.HISTORICAL_WINDOW,
            symbol="ETHUSDT",
            side="none",
            observed_at_ms=observed_at_ms + 11_000,
            signal_confidence=Decimal("0.22"),
            signal_status="no_signal",
            required_facts_ready=True,
            blocker_class="waiting_for_market",
            expected_owner_state="waiting_for_opportunity",
            simulated_exit_outcome="not_applicable",
            cost_review=_cost_review(
                fee="0",
                slippage="0",
                funding="0",
                min_qty_step="not_applicable_no_signal",
                note=(
                    "no-signal replay keeps BTPC observation visible without "
                    "creating candidate authority"
                ),
            ),
            review_recommendation=ReplayReviewRecommendation.KEEP_OBSERVING,
            notes=["Bear trend context was not mature enough for would-enter."],
            **blocked_stage,
        ),
        _event(
            strategy_group_id="BTPC-001",
            event_id="btpc-001-l2-strong-uptrend-conflict",
            fixture_case="strong_uptrend_conflict",
            event_kind=ReplayEventKind.HISTORICAL_WINDOW,
            symbol="BTCUSDT",
            side="short",
            observed_at_ms=observed_at_ms + 12_000,
            signal_confidence=Decimal("0.54"),
            signal_status="signal_conflict",
            required_facts_ready=True,
            blocker_class="review_only_warning",
            expected_owner_state="running",
            simulated_exit_outcome="not_applicable",
            cost_review=_cost_review(
                fee="0",
                slippage="0",
                funding="0",
                min_qty_step="not_applicable_conflict",
                note=(
                    "strong-uptrend disable classifier blocks BTPC L2 review "
                    "promotion, not P0 live readiness"
                ),
            ),
            review_recommendation=ReplayReviewRecommendation.REVISE,
            notes=["Short-side BTPC signal must stay blocked during strong-uptrend conflict."],
            **blocked_stage,
        ),
        _event(
            strategy_group_id="BTPC-001",
            event_id="btpc-001-l2-missing-derivatives-context",
            fixture_case="missing_derivatives_context",
            event_kind=ReplayEventKind.HISTORICAL_WINDOW,
            symbol="AVAXUSDT",
            side="short",
            observed_at_ms=observed_at_ms + 13_000,
            signal_confidence=Decimal("0.56"),
            signal_status="would_enter_missing_required_facts",
            required_facts_ready=False,
            blocker_class="missing_fact",
            expected_owner_state="temporarily_unavailable",
            simulated_exit_outcome="not_applicable",
            cost_review=_cost_review(
                fee="0",
                slippage="0",
                funding="0",
                min_qty_step="not_evaluated_missing_derivatives_context",
                note="BTPC requires derivatives context before L2 shadow evidence can be trusted",
            ),
            review_recommendation=ReplayReviewRecommendation.REVISE,
            notes=["Missing OI/crowding context blocks L2 review readiness."],
            **blocked_stage,
        ),
        _event(
            strategy_group_id="BTPC-001",
            event_id="btpc-001-l2-stale-signal",
            fixture_case="stale_signal",
            event_kind=ReplayEventKind.HISTORICAL_WINDOW,
            symbol="SOLUSDT",
            side="short",
            observed_at_ms=observed_at_ms - 300_000,
            signal_confidence=Decimal("0.58"),
            signal_status="stale_signal",
            required_facts_ready=True,
            blocker_class="missing_fact",
            expected_owner_state="temporarily_unavailable",
            simulated_exit_outcome="not_applicable",
            cost_review=_cost_review(
                fee="0",
                slippage="0",
                funding="0",
                min_qty_step="not_applicable_stale_signal",
                note="BTPC stale replay proves L2 freshness rejection before any promotion review",
            ),
            review_recommendation=ReplayReviewRecommendation.REVISE,
            notes=["Stale BTPC observation cannot become shadow candidate evidence."],
            **blocked_stage,
        ),
    ]


def vcb001_l1_observe_replay_corpus(
    *, observed_at_ms: int
) -> list[StrategyGroupReplayEvent]:
    blocked_stage = {
        "prepare_chain_ready": False,
        "operation_layer_shape_reachable": False,
    }
    return [
        _event(
            strategy_group_id="VCB-001",
            event_id="vcb-001-l1-compression-breakout-would-enter",
            fixture_case="compression_breakout_would_enter",
            event_kind=ReplayEventKind.HISTORICAL_WINDOW,
            symbol="LINKUSDT",
            side="long",
            observed_at_ms=observed_at_ms + 20_000,
            signal_confidence=Decimal("0.60"),
            signal_status="would_enter_observe_only",
            required_facts_ready=True,
            blocker_class="review_only_warning",
            expected_owner_state="running",
            simulated_exit_outcome="l1_observe_review_only_no_shadow_candidate",
            cost_review=_cost_review(
                fee="0.012",
                slippage="0.038",
                funding="0.001",
                min_qty_step="review_only_exchange_rules_shape_present",
                note=(
                    "VCB L1 would-enter sample makes compression-breakout "
                    "opportunities visible without L2 or L4 authority"
                ),
            ),
            review_recommendation=ReplayReviewRecommendation.KEEP_OBSERVING,
            notes=[
                "L1 observe-only replay.",
                "Would-enter review evidence must not create shadow candidate, FinalGate, Operation Layer, or order authority.",
            ],
            **blocked_stage,
        ),
        _event(
            strategy_group_id="VCB-001",
            event_id="vcb-001-l1-no-signal-no-compression",
            fixture_case="no_signal_no_compression",
            event_kind=ReplayEventKind.HISTORICAL_WINDOW,
            symbol="ETHUSDT",
            side="none",
            observed_at_ms=observed_at_ms + 21_000,
            signal_confidence=Decimal("0.24"),
            signal_status="no_signal",
            required_facts_ready=True,
            blocker_class="waiting_for_market",
            expected_owner_state="waiting_for_opportunity",
            simulated_exit_outcome="not_applicable",
            cost_review=_cost_review(
                fee="0",
                slippage="0",
                funding="0",
                min_qty_step="not_applicable_no_signal",
                note="no-compression replay keeps VCB quiet without hiding the StrategyGroup from review",
            ),
            review_recommendation=ReplayReviewRecommendation.KEEP_OBSERVING,
            notes=["Compression did not contract enough before breakout."],
            **blocked_stage,
        ),
        _event(
            strategy_group_id="VCB-001",
            event_id="vcb-001-l1-false-breakout-disable-needed",
            fixture_case="false_breakout_disable_needed",
            event_kind=ReplayEventKind.HISTORICAL_WINDOW,
            symbol="LINKUSDT",
            side="long",
            observed_at_ms=observed_at_ms + 22_000,
            signal_confidence=Decimal("0.56"),
            signal_status="would_enter_but_disable_classifier_missing",
            required_facts_ready=True,
            blocker_class="review_only_warning",
            expected_owner_state="running",
            simulated_exit_outcome="false_breakout_review_revise_classifier",
            cost_review=_cost_review(
                fee="0.012",
                slippage="0.057",
                funding="0.001",
                min_qty_step="review_only_false_breakout_cost_shape",
                note="false-breakout sample should revise VCB classifier before any L2 promotion",
            ),
            review_recommendation=ReplayReviewRecommendation.REVISE,
            notes=[
                "False-breakout disable state is not mature enough for L2.",
                "This is observation evidence, not a blocker for MPG P0 live readiness.",
            ],
            **blocked_stage,
        ),
        _event(
            strategy_group_id="VCB-001",
            event_id="vcb-001-l1-missing-compression-context",
            fixture_case="missing_compression_context",
            event_kind=ReplayEventKind.HISTORICAL_WINDOW,
            symbol="AVAXUSDT",
            side="long",
            observed_at_ms=observed_at_ms + 23_000,
            signal_confidence=Decimal("0.59"),
            signal_status="would_enter_missing_required_facts",
            required_facts_ready=False,
            blocker_class="missing_fact",
            expected_owner_state="temporarily_unavailable",
            simulated_exit_outcome="not_applicable",
            cost_review=_cost_review(
                fee="0",
                slippage="0",
                funding="0",
                min_qty_step="not_evaluated_missing_compression_context",
                note="VCB requires compression window and false-breakout context before L2 review",
            ),
            review_recommendation=ReplayReviewRecommendation.REVISE,
            notes=["Missing compression context keeps the sample observe-only."],
            **blocked_stage,
        ),
        _event(
            strategy_group_id="VCB-001",
            event_id="vcb-001-l1-stale-signal",
            fixture_case="stale_signal",
            event_kind=ReplayEventKind.HISTORICAL_WINDOW,
            symbol="LINKUSDT",
            side="long",
            observed_at_ms=observed_at_ms - 300_000,
            signal_confidence=Decimal("0.60"),
            signal_status="stale_signal",
            required_facts_ready=True,
            blocker_class="missing_fact",
            expected_owner_state="temporarily_unavailable",
            simulated_exit_outcome="not_applicable",
            cost_review=_cost_review(
                fee="0",
                slippage="0",
                funding="0",
                min_qty_step="not_applicable_stale_signal",
                note="VCB stale replay proves freshness rejection before observation promotion review",
            ),
            review_recommendation=ReplayReviewRecommendation.REVISE,
            notes=["Stale VCB observation cannot become L2 review evidence."],
            **blocked_stage,
        ),
    ]


def lsr001_l1_observe_replay_corpus(
    *, observed_at_ms: int
) -> list[StrategyGroupReplayEvent]:
    blocked_stage = {
        "prepare_chain_ready": False,
        "operation_layer_shape_reachable": False,
    }
    return [
        _event(
            strategy_group_id="LSR-001",
            event_id="lsr-001-l1-liquidity-sweep-long-would-enter-current-v0",
            fixture_case="liquidity_sweep_long_would_enter_current_v0",
            event_kind=ReplayEventKind.HISTORICAL_WINDOW,
            symbol="XRPUSDT",
            side="long",
            observed_at_ms=observed_at_ms + 30_000,
            signal_confidence=Decimal("0.58"),
            signal_status="would_enter_observe_only_current_v0",
            required_facts_ready=True,
            blocker_class="review_only_warning",
            expected_owner_state="running",
            simulated_exit_outcome="l1_observe_review_only_no_shadow_candidate",
            cost_review=_cost_review(
                fee="0.011",
                slippage="0.044",
                funding="0.000",
                min_qty_step="review_only_exchange_rules_shape_present",
                note=(
                    "LSR current-v0 long sweep sample keeps liquidity-sweep "
                    "observations visible without L2 or L4 authority"
                ),
            ),
            review_recommendation=ReplayReviewRecommendation.KEEP_OBSERVING,
            notes=[
                "L1 observe-only replay.",
                "Current broader preview long-side semantics conflict with the stronger short-revival research lane.",
            ],
            **blocked_stage,
        ),
        _event(
            strategy_group_id="LSR-001",
            event_id="lsr-001-l1-short-revival-rewrite-needed",
            fixture_case="short_revival_rewrite_needed",
            event_kind=ReplayEventKind.HISTORICAL_WINDOW,
            symbol="XRPUSDT",
            side="short",
            observed_at_ms=observed_at_ms + 31_000,
            signal_confidence=Decimal("0.55"),
            signal_status="rewrite_required_before_would_enter",
            required_facts_ready=True,
            blocker_class="review_only_warning",
            expected_owner_state="running",
            simulated_exit_outcome="rewrite_review_no_candidate",
            cost_review=_cost_review(
                fee="0.011",
                slippage="0.052",
                funding="0.000",
                min_qty_step="review_only_rewrite_cost_shape",
                note=(
                    "short-revival sample documents the side-specific rewrite "
                    "gap before any L2 promotion review"
                ),
            ),
            review_recommendation=ReplayReviewRecommendation.REVISE,
            notes=[
                "Research lead is short upper-range revival, while current local evaluator is long sweep.",
                "This case exists to keep the rewrite gap visible without changing runtime scope.",
            ],
            **blocked_stage,
        ),
        _event(
            strategy_group_id="LSR-001",
            event_id="lsr-001-l1-no-signal-no-sweep-reclaim",
            fixture_case="no_signal_no_sweep_reclaim",
            event_kind=ReplayEventKind.HISTORICAL_WINDOW,
            symbol="ETHUSDT",
            side="none",
            observed_at_ms=observed_at_ms + 32_000,
            signal_confidence=Decimal("0.23"),
            signal_status="no_signal",
            required_facts_ready=True,
            blocker_class="waiting_for_market",
            expected_owner_state="waiting_for_opportunity",
            simulated_exit_outcome="not_applicable",
            cost_review=_cost_review(
                fee="0",
                slippage="0",
                funding="0",
                min_qty_step="not_applicable_no_signal",
                note="no-sweep replay keeps LSR quiet without hiding the StrategyGroup from review",
            ),
            review_recommendation=ReplayReviewRecommendation.KEEP_OBSERVING,
            notes=["No reclaim/rejection after sweep, so no observation candidate should be created."],
            **blocked_stage,
        ),
        _event(
            strategy_group_id="LSR-001",
            event_id="lsr-001-l1-missing-range-context",
            fixture_case="missing_range_context",
            event_kind=ReplayEventKind.HISTORICAL_WINDOW,
            symbol="ADAUSDT",
            side="long",
            observed_at_ms=observed_at_ms + 33_000,
            signal_confidence=Decimal("0.57"),
            signal_status="would_enter_missing_required_facts",
            required_facts_ready=False,
            blocker_class="missing_fact",
            expected_owner_state="temporarily_unavailable",
            simulated_exit_outcome="not_applicable",
            cost_review=_cost_review(
                fee="0",
                slippage="0",
                funding="0",
                min_qty_step="not_evaluated_missing_range_context",
                note="LSR requires range and sweep context before observation promotion review",
            ),
            review_recommendation=ReplayReviewRecommendation.REVISE,
            notes=["Missing range context keeps the sample observe-only."],
            **blocked_stage,
        ),
        _event(
            strategy_group_id="LSR-001",
            event_id="lsr-001-l1-stale-signal",
            fixture_case="stale_signal",
            event_kind=ReplayEventKind.HISTORICAL_WINDOW,
            symbol="XRPUSDT",
            side="long",
            observed_at_ms=observed_at_ms - 300_000,
            signal_confidence=Decimal("0.58"),
            signal_status="stale_signal",
            required_facts_ready=True,
            blocker_class="missing_fact",
            expected_owner_state="temporarily_unavailable",
            simulated_exit_outcome="not_applicable",
            cost_review=_cost_review(
                fee="0",
                slippage="0",
                funding="0",
                min_qty_step="not_applicable_stale_signal",
                note="LSR stale replay proves freshness rejection before observation promotion review",
            ),
            review_recommendation=ReplayReviewRecommendation.REVISE,
            notes=["Stale LSR observation cannot become L2 review evidence."],
            **blocked_stage,
        ),
    ]


def brf001_l1_observe_replay_corpus(
    *, observed_at_ms: int
) -> list[StrategyGroupReplayEvent]:
    blocked_stage = {
        "prepare_chain_ready": False,
        "operation_layer_shape_reachable": False,
    }
    return [
        _event(
            strategy_group_id="BRF-001",
            event_id="brf-001-l1-bear-rally-failure-short-would-enter",
            fixture_case="bear_rally_failure_short_would_enter",
            event_kind=ReplayEventKind.HISTORICAL_WINDOW,
            symbol="SOLUSDT",
            side="short",
            observed_at_ms=observed_at_ms + 40_000,
            signal_confidence=Decimal("0.56"),
            signal_status="would_enter_observe_only",
            required_facts_ready=True,
            blocker_class="review_only_warning",
            expected_owner_state="running",
            simulated_exit_outcome="l1_observe_review_only_no_shadow_candidate",
            cost_review=_cost_review(
                fee="0.014",
                slippage="0.047",
                funding="0.001",
                min_qty_step="review_only_exchange_rules_shape_present",
                note=(
                    "BRF L1 would-enter sample makes bear-rally-failure "
                    "short observations visible without L2 or L4 authority"
                ),
            ),
            review_recommendation=ReplayReviewRecommendation.KEEP_OBSERVING,
            notes=[
                "L1 observe-only replay.",
                "Rally-high protection shape is visible but cannot authorize a shadow candidate.",
            ],
            **blocked_stage,
        ),
        _event(
            strategy_group_id="BRF-001",
            event_id="brf-001-l1-no-signal-rally-not-failed",
            fixture_case="no_signal_rally_not_failed",
            event_kind=ReplayEventKind.HISTORICAL_WINDOW,
            symbol="ETHUSDT",
            side="none",
            observed_at_ms=observed_at_ms + 41_000,
            signal_confidence=Decimal("0.24"),
            signal_status="no_signal",
            required_facts_ready=True,
            blocker_class="waiting_for_market",
            expected_owner_state="waiting_for_opportunity",
            simulated_exit_outcome="not_applicable",
            cost_review=_cost_review(
                fee="0",
                slippage="0",
                funding="0",
                min_qty_step="not_applicable_no_signal",
                note="rally-not-failed replay keeps BRF quiet without hiding it from review",
            ),
            review_recommendation=ReplayReviewRecommendation.KEEP_OBSERVING,
            notes=["Rally did not fail, so BRF should not create observation evidence."],
            **blocked_stage,
        ),
        _event(
            strategy_group_id="BRF-001",
            event_id="brf-001-l1-short-squeeze-risk-revision-needed",
            fixture_case="short_squeeze_risk_revision_needed",
            event_kind=ReplayEventKind.HISTORICAL_WINDOW,
            symbol="BTCUSDT",
            side="short",
            observed_at_ms=observed_at_ms + 42_000,
            signal_confidence=Decimal("0.53"),
            signal_status="would_enter_squeeze_risk_revision_needed",
            required_facts_ready=True,
            blocker_class="review_only_warning",
            expected_owner_state="running",
            simulated_exit_outcome="squeeze_risk_review_no_candidate",
            cost_review=_cost_review(
                fee="0.015",
                slippage="0.058",
                funding="0.004",
                min_qty_step="review_only_squeeze_risk_cost_shape",
                note=(
                    "short-squeeze-risk sample should revise BRF classifier "
                    "before any L2 promotion review"
                ),
            ),
            review_recommendation=ReplayReviewRecommendation.REVISE,
            notes=[
                "Short-side rally failure can be right-tail, but squeeze risk must stay visible.",
                "This warning is review evidence, not a P0 live-order blocker.",
            ],
            **blocked_stage,
        ),
        _event(
            strategy_group_id="BRF-001",
            event_id="brf-001-l1-missing-rally-context",
            fixture_case="missing_rally_context",
            event_kind=ReplayEventKind.HISTORICAL_WINDOW,
            symbol="SOLUSDT",
            side="short",
            observed_at_ms=observed_at_ms + 43_000,
            signal_confidence=Decimal("0.55"),
            signal_status="would_enter_missing_required_facts",
            required_facts_ready=False,
            blocker_class="missing_fact",
            expected_owner_state="temporarily_unavailable",
            simulated_exit_outcome="not_applicable",
            cost_review=_cost_review(
                fee="0",
                slippage="0",
                funding="0",
                min_qty_step="not_evaluated_missing_rally_context",
                note="BRF requires rally-high, rejection close, and squeeze-risk context before promotion review",
            ),
            review_recommendation=ReplayReviewRecommendation.REVISE,
            notes=["Missing rally context keeps BRF observe-only."],
            **blocked_stage,
        ),
        _event(
            strategy_group_id="BRF-001",
            event_id="brf-001-l1-stale-signal",
            fixture_case="stale_signal",
            event_kind=ReplayEventKind.HISTORICAL_WINDOW,
            symbol="SOLUSDT",
            side="short",
            observed_at_ms=observed_at_ms - 300_000,
            signal_confidence=Decimal("0.56"),
            signal_status="stale_signal",
            required_facts_ready=True,
            blocker_class="missing_fact",
            expected_owner_state="temporarily_unavailable",
            simulated_exit_outcome="not_applicable",
            cost_review=_cost_review(
                fee="0",
                slippage="0",
                funding="0",
                min_qty_step="not_applicable_stale_signal",
                note="BRF stale replay proves freshness rejection before observation promotion review",
            ),
            review_recommendation=ReplayReviewRecommendation.REVISE,
            notes=["Stale BRF observation cannot become L2 review evidence."],
            **blocked_stage,
        ),
    ]


def synthetic_signal_fixtures(*, observed_at_ms: int) -> list[StrategyGroupReplayEvent]:
    blocked_stage = {
        "prepare_chain_ready": False,
        "operation_layer_shape_reachable": False,
    }
    return [
        _event(
            event_id="mpg-001-synthetic-no-signal",
            fixture_case="no_signal",
            event_kind=ReplayEventKind.SYNTHETIC_SIGNAL_FIXTURE,
            symbol="MSTRUSDT",
            side="none",
            observed_at_ms=observed_at_ms,
            signal_confidence=Decimal("0"),
            signal_status="waiting_for_signal",
            required_facts_ready=True,
            blocker_class="waiting_for_market",
            expected_owner_state="waiting_for_opportunity",
            simulated_exit_outcome="not_applicable",
            review_recommendation=ReplayReviewRecommendation.KEEP_OBSERVING,
            notes=["No candidate/auth should be generated."],
            **blocked_stage,
        ),
        _event(
            event_id="mpg-001-synthetic-fresh-pass",
            fixture_case="fresh_signal_pass",
            event_kind=ReplayEventKind.SYNTHETIC_SIGNAL_FIXTURE,
            symbol="MSTRUSDT",
            side="long",
            observed_at_ms=observed_at_ms,
            signal_confidence=Decimal("0.62"),
            signal_status="fresh_signal_pass",
            required_facts_ready=True,
            blocker_class="none",
            expected_owner_state="processing",
            prepare_chain_ready=True,
            operation_layer_shape_reachable=True,
            simulated_exit_outcome="entry_filled_protection_ok_shape",
            review_recommendation=ReplayReviewRecommendation.KEEP_OBSERVING,
            notes=["Exercises the non-executing fast chain."],
        ),
        _event(
            event_id="mpg-001-synthetic-stale",
            fixture_case="stale_signal",
            event_kind=ReplayEventKind.SYNTHETIC_SIGNAL_FIXTURE,
            symbol="MSTRUSDT",
            side="long",
            observed_at_ms=observed_at_ms - 300_000,
            signal_confidence=Decimal("0.62"),
            signal_status="stale_signal",
            required_facts_ready=True,
            blocker_class="missing_fact",
            expected_owner_state="temporarily_unavailable",
            simulated_exit_outcome="not_applicable",
            review_recommendation=ReplayReviewRecommendation.REVISE,
            notes=["Stale signal must not enter Operation Layer shape."],
            **blocked_stage,
        ),
        _event(
            event_id="mpg-001-synthetic-missing-facts",
            fixture_case="missing_required_facts",
            event_kind=ReplayEventKind.SYNTHETIC_SIGNAL_FIXTURE,
            symbol="MSTRUSDT",
            side="long",
            observed_at_ms=observed_at_ms,
            signal_confidence=Decimal("0.62"),
            signal_status="fresh_signal_missing_facts",
            required_facts_ready=False,
            blocker_class="missing_fact",
            expected_owner_state="temporarily_unavailable",
            simulated_exit_outcome="not_applicable",
            review_recommendation=ReplayReviewRecommendation.REVISE,
            notes=["RequiredFacts gate blocks before prepare chain."],
            **blocked_stage,
        ),
        _event(
            event_id="mpg-001-synthetic-active-position",
            fixture_case="active_position_conflict",
            event_kind=ReplayEventKind.SYNTHETIC_SIGNAL_FIXTURE,
            symbol="MSTRUSDT",
            side="long",
            observed_at_ms=observed_at_ms,
            signal_confidence=Decimal("0.62"),
            signal_status="fresh_signal_active_position_conflict",
            required_facts_ready=True,
            blocker_class="active_position_resolution",
            expected_owner_state="needs_intervention",
            simulated_exit_outcome="not_applicable",
            review_recommendation=ReplayReviewRecommendation.REVISE,
            notes=["Active position conflict blocks new real action."],
            **blocked_stage,
        ),
        _event(
            event_id="mpg-001-synthetic-open-order",
            fixture_case="open_order_conflict",
            event_kind=ReplayEventKind.SYNTHETIC_SIGNAL_FIXTURE,
            symbol="MSTRUSDT",
            side="long",
            observed_at_ms=observed_at_ms,
            signal_confidence=Decimal("0.62"),
            signal_status="fresh_signal_open_order_conflict",
            required_facts_ready=True,
            blocker_class="active_position_resolution",
            expected_owner_state="needs_intervention",
            simulated_exit_outcome="not_applicable",
            review_recommendation=ReplayReviewRecommendation.REVISE,
            notes=["Open order conflict blocks duplicate exposure."],
            **blocked_stage,
        ),
        _event(
            event_id="mpg-001-synthetic-protection-missing",
            fixture_case="protection_missing",
            event_kind=ReplayEventKind.SYNTHETIC_SIGNAL_FIXTURE,
            symbol="MSTRUSDT",
            side="long",
            observed_at_ms=observed_at_ms,
            signal_confidence=Decimal("0.62"),
            signal_status="fresh_signal_protection_missing",
            required_facts_ready=True,
            blocker_class="hard_safety_stop",
            expected_owner_state="needs_intervention",
            simulated_exit_outcome="not_applicable",
            review_recommendation=ReplayReviewRecommendation.REVISE,
            notes=["Protection missing blocks live action."],
            **blocked_stage,
        ),
        _event(
            event_id="mpg-001-synthetic-profile-boundary-mismatch",
            fixture_case="allocated_profile_boundary_mismatch",
            event_kind=ReplayEventKind.SYNTHETIC_SIGNAL_FIXTURE,
            symbol="MSTRUSDT",
            side="long",
            observed_at_ms=observed_at_ms,
            signal_confidence=Decimal("0.62"),
            signal_status="fresh_signal_profile_boundary_mismatch",
            required_facts_ready=True,
            blocker_class="hard_safety_stop",
            expected_owner_state="needs_intervention",
            simulated_exit_outcome="not_applicable",
            review_recommendation=ReplayReviewRecommendation.REVISE,
            notes=[
                "Only selected StrategyGroup/symbol/side/profile boundary mismatch blocks.",
                "Generic risk aversion must not block in-boundary opportunities.",
            ],
            **blocked_stage,
        ),
    ]


def external_replay_adapter_policy() -> dict[str, Any]:
    return {
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


def post_submit_simulator_matrix() -> list[StrategyGroupPostSubmitSimulatorCase]:
    return [
        StrategyGroupPostSubmitSimulatorCase(
            case="entry_accepted_protection_ok",
            input_state="entry accepted and exchange-native hard stop created",
            expected_runtime_state="finalize_reconcile_settle_review_shape_ready",
            protection_status="ok",
            reduce_only_recovery_shape_reachable=False,
            review_recommendation=ReplayReviewRecommendation.KEEP_OBSERVING,
            notes=["Normal accepted-entry path with protection present."],
        ),
        StrategyGroupPostSubmitSimulatorCase(
            case="entry_filled_sl_creation_failed",
            input_state="entry filled but exchange-native SL creation failed",
            expected_runtime_state="reduce_only_recovery_shape_ready",
            protection_status="failed",
            reduce_only_recovery_shape_reachable=True,
            review_recommendation=ReplayReviewRecommendation.REVISE,
            notes=["Recovery shape is standing-authorized but still non-executing here."],
        ),
        StrategyGroupPostSubmitSimulatorCase(
            case="partial_fill",
            input_state="entry partially filled before final protection/reconciliation",
            expected_runtime_state="partial_fill_reconcile_and_budget_shape_ready",
            protection_status="partial",
            reduce_only_recovery_shape_reachable=False,
            review_recommendation=ReplayReviewRecommendation.KEEP_OBSERVING,
            notes=["Partial fill keeps lifecycle open until reconciliation completes."],
        ),
        StrategyGroupPostSubmitSimulatorCase(
            case="submit_rejected_before_acceptance",
            input_state="exchange submit rejected before order acceptance",
            expected_runtime_state="no_position_no_budget_consumption_review_shape",
            protection_status="not_applicable",
            reduce_only_recovery_shape_reachable=False,
            review_recommendation=ReplayReviewRecommendation.REVISE,
            notes=["Rejected submit must not be projected as active exposure."],
        ),
        StrategyGroupPostSubmitSimulatorCase(
            case="position_closed_by_sl",
            input_state="position closed by exchange-native stop loss",
            expected_runtime_state="closed_by_sl_reconcile_settle_review_shape",
            protection_status="closed_by_sl",
            reduce_only_recovery_shape_reachable=False,
            review_recommendation=ReplayReviewRecommendation.REVISE,
            notes=["SL closure must finalize and enter review."],
        ),
        StrategyGroupPostSubmitSimulatorCase(
            case="position_closed_by_tp1",
            input_state="position partially or fully closed by TP1",
            expected_runtime_state="tp1_reconcile_runner_review_shape",
            protection_status="tp1",
            reduce_only_recovery_shape_reachable=False,
            review_recommendation=ReplayReviewRecommendation.KEEP_OBSERVING,
            notes=["TP1 path checks runner/remainder review shape."],
        ),
        StrategyGroupPostSubmitSimulatorCase(
            case="active_position_remains_open",
            input_state="entry remains open and protected after post-submit checks",
            expected_runtime_state="monitor_open_position_shape",
            protection_status="ok_open",
            reduce_only_recovery_shape_reachable=False,
            review_recommendation=ReplayReviewRecommendation.KEEP_OBSERVING,
            notes=["Open protected position remains monitored, not falsely completed."],
        ),
    ]


def build_mpg001_replay_lab_packet(
    *, generated_at_ms: int
) -> StrategyGroupReplayReport:
    replay_samples = mpg001_replay_corpus(observed_at_ms=generated_at_ms)
    l2_shadow_samples = btpc001_l2_shadow_replay_corpus(
        observed_at_ms=generated_at_ms
    )
    l1_observe_samples = vcb001_l1_observe_replay_corpus(
        observed_at_ms=generated_at_ms
    )
    l1_observe_samples.extend(
        lsr001_l1_observe_replay_corpus(observed_at_ms=generated_at_ms)
    )
    l1_observe_samples.extend(
        brf001_l1_observe_replay_corpus(observed_at_ms=generated_at_ms)
    )
    fixtures = synthetic_signal_fixtures(observed_at_ms=generated_at_ms)
    simulator_matrix = post_submit_simulator_matrix()
    replay_cases = {item.fixture_case for item in replay_samples}
    btpc_cases = {item.fixture_case for item in l2_shadow_samples}
    lsr_cases = {
        item.fixture_case
        for item in l1_observe_samples
        if item.strategy_group_id == "LSR-001"
    }
    brf_cases = {
        item.fixture_case
        for item in l1_observe_samples
        if item.strategy_group_id == "BRF-001"
    }
    fixture_cases = {item.fixture_case for item in fixtures}
    fresh_pass = next(item for item in fixtures if item.fixture_case == "fresh_signal_pass")
    blocked_fixtures = [item for item in fixtures if item.fixture_case != "fresh_signal_pass"]
    btpc_would_enter = next(
        item
        for item in l2_shadow_samples
        if item.fixture_case == "bear_pullback_would_enter"
    )
    btpc_blocked = [
        item
        for item in l2_shadow_samples
        if item.fixture_case != "bear_pullback_would_enter"
    ]
    vcb_would_enter = next(
        item
        for item in l1_observe_samples
        if item.fixture_case == "compression_breakout_would_enter"
    )
    lsr_would_enter = next(
        item
        for item in l1_observe_samples
        if item.fixture_case == "liquidity_sweep_long_would_enter_current_v0"
    )
    brf_would_enter = next(
        item
        for item in l1_observe_samples
        if item.fixture_case == "bear_rally_failure_short_would_enter"
    )

    checks = {
        "mpg001_replay_sample_present": bool(replay_samples),
        "mpg001_replay_corpus_cases_present": (
            replay_cases == EXPECTED_MPG001_REPLAY_CORPUS_CASES
        ),
        "btpc001_l2_shadow_replay_cases_present": (
            btpc_cases == EXPECTED_BTPC001_L2_REPLAY_CASES
        ),
        "btpc001_l2_would_enter_review_shape_present": (
            btpc_would_enter.signal_status == "would_enter_observe_only"
            and btpc_would_enter.required_facts_ready is True
            and btpc_would_enter.stage_results.get("prepare_chain_ready") is True
            and btpc_would_enter.stage_results.get("operation_layer_shape_reachable")
            is False
            and btpc_would_enter.real_order_allowed is False
        ),
        "btpc001_l2_blocked_cases_do_not_reach_operation_layer": all(
            item.stage_results.get("operation_layer_shape_reachable") is False
            for item in btpc_blocked
        ),
        "vcb001_l1_observe_replay_cases_present": (
            {
                item.fixture_case
                for item in l1_observe_samples
                if item.strategy_group_id == "VCB-001"
            }
            == EXPECTED_VCB001_L1_REPLAY_CASES
        ),
        "vcb001_l1_would_enter_review_shape_present": (
            vcb_would_enter.signal_status == "would_enter_observe_only"
            and vcb_would_enter.required_facts_ready is True
            and vcb_would_enter.stage_results.get("prepare_chain_ready") is False
            and vcb_would_enter.stage_results.get("operation_layer_shape_reachable")
            is False
            and vcb_would_enter.real_order_allowed is False
        ),
        "vcb001_l1_cases_do_not_reach_prepare_or_operation_layer": all(
            item.stage_results.get("prepare_chain_ready") is False
            and item.stage_results.get("operation_layer_shape_reachable") is False
            for item in l1_observe_samples
            if item.strategy_group_id == "VCB-001"
        ),
        "lsr001_l1_observe_replay_cases_present": (
            lsr_cases == EXPECTED_LSR001_L1_REPLAY_CASES
        ),
        "lsr001_l1_would_enter_review_shape_present": (
            lsr_would_enter.signal_status == "would_enter_observe_only_current_v0"
            and lsr_would_enter.required_facts_ready is True
            and lsr_would_enter.stage_results.get("prepare_chain_ready") is False
            and lsr_would_enter.stage_results.get("operation_layer_shape_reachable")
            is False
            and lsr_would_enter.real_order_allowed is False
        ),
        "lsr001_l1_cases_do_not_reach_prepare_or_operation_layer": all(
            item.stage_results.get("prepare_chain_ready") is False
            and item.stage_results.get("operation_layer_shape_reachable") is False
            for item in l1_observe_samples
            if item.strategy_group_id == "LSR-001"
        ),
        "brf001_l1_observe_replay_cases_present": (
            brf_cases == EXPECTED_BRF001_L1_REPLAY_CASES
        ),
        "brf001_l1_would_enter_review_shape_present": (
            brf_would_enter.signal_status == "would_enter_observe_only"
            and brf_would_enter.required_facts_ready is True
            and brf_would_enter.stage_results.get("prepare_chain_ready") is False
            and brf_would_enter.stage_results.get("operation_layer_shape_reachable")
            is False
            and brf_would_enter.real_order_allowed is False
        ),
        "brf001_l1_cases_do_not_reach_prepare_or_operation_layer": all(
            item.stage_results.get("prepare_chain_ready") is False
            and item.stage_results.get("operation_layer_shape_reachable") is False
            for item in l1_observe_samples
            if item.strategy_group_id == "BRF-001"
        ),
        "synthetic_fixture_cases_present": fixture_cases
        == EXPECTED_SYNTHETIC_FIXTURE_CASES,
        "post_submit_simulator_cases_present": (
            {item.case for item in simulator_matrix}
            == EXPECTED_POST_SUBMIT_SIMULATOR_CASES
        ),
        "post_submit_simulator_non_executing": all(
            not item.exchange_write_called
            and not item.real_order_created
            and not item.operation_layer_live_submit_called
            for item in simulator_matrix
        ),
        "cost_review_skeleton_present": all(
            item.cost_review.not_submit_authority
            and item.cost_review.min_qty_step_size_impact
            and item.cost_review.net_edge_note
            for item in [*replay_samples, *l2_shadow_samples, *l1_observe_samples]
        ),
        "fresh_pass_reaches_prepare_chain": (
            fresh_pass.stage_results.get("prepare_chain_ready") is True
            and fresh_pass.stage_results.get("operation_layer_shape_reachable") is True
            and fresh_pass.stage_results.get("real_submit_allowed") is False
        ),
        "blocked_fixtures_do_not_reach_operation_layer": all(
            item.stage_results.get("operation_layer_shape_reachable") is False
            for item in blocked_fixtures
        ),
        "replay_report_owner_readable": True,
        "external_framework_sidecar_only": True,
        "no_replay_or_synthetic_signal_has_live_authority": all(
            item.not_live_market_signal
            and item.not_execution_authority
            and not item.real_order_allowed
            and not item.exchange_write_allowed
            and not item.operation_layer_submit_allowed
            for item in [
                *replay_samples,
                *l2_shadow_samples,
                *l1_observe_samples,
                *fixtures,
            ]
        ),
    }
    blockers = [name for name, ok in checks.items() if ok is not True]
    status: Literal["passed", "blocked"] = "passed" if not blockers else "blocked"
    return StrategyGroupReplayReport(
        status=status,
        generated_at_ms=generated_at_ms,
        strategy_group_id="MPG-001",
        replay_samples=replay_samples,
        l2_shadow_replay_samples=l2_shadow_samples,
        l1_observe_replay_samples=l1_observe_samples,
        synthetic_fixtures=fixtures,
        post_submit_simulator_matrix=simulator_matrix,
        checks=checks,
        blockers=blockers,
        owner_summary=StrategyGroupReplayOwnerSummary(
            current_state="P0.5 replay_ready" if status == "passed" else "P0.5 replay_blocked",
            next_action=(
                "Use replay/synthetic rehearsal while P0 waits for a real fresh signal."
            ),
            summary_lines=[
                "MPG-001 replay corpus is available.",
                (
                    "BTPC-001 L2 shadow replay corpus expands opportunity "
                    "coverage without L4 authority."
                ),
                (
                    "VCB-001 L1 observe-only replay corpus expands volatility "
                    "breakout visibility without L2 or L4 authority."
                ),
                (
                    "LSR-001 L1 observe-only replay corpus keeps liquidity-sweep "
                    "and short-revival rewrite gaps visible without L2 or L4 authority."
                ),
                (
                    "BRF-001 L1 observe-only replay corpus expands bear-rally-failure "
                    "short visibility without L2 or L4 authority."
                ),
                (
                    "Synthetic fixtures cover fresh, stale, missing fact, "
                    "conflict, protection, and profile-boundary cases."
                ),
                (
                    "Post-submit simulator covers accepted, failed-protection, "
                    "partial-fill, reject, closed, and still-open shapes."
                ),
                "Cost/slippage/funding fields are review inputs only.",
                "Replay output is non-executing and cannot authorize a real order.",
            ],
        ),
        external_adapter_policy=external_replay_adapter_policy(),
        safety_invariants={
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
        },
    )
