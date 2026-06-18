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
        return self


class StrategyGroupReplayReport(StrategyGroupReplayModel):
    schema_version: Literal["brc.strategygroup.runtime_replay_report.v1"] = (
        REPLAY_REPORT_SCHEMA
    )
    status: Literal["passed", "blocked"]
    generated_at_ms: int = Field(ge=0)
    strategy_group_id: Literal["MPG-001"]
    replay_samples: list[StrategyGroupReplayEvent] = Field(default_factory=list)
    synthetic_fixtures: list[StrategyGroupReplayEvent] = Field(default_factory=list)
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
) -> StrategyGroupReplayEvent:
    return StrategyGroupReplayEvent(
        event_id=event_id,
        strategy_group_id="MPG-001",
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
        review_recommendation=review_recommendation,
        notes=notes or [],
    )


def mpg001_replay_sample_event(*, observed_at_ms: int) -> StrategyGroupReplayEvent:
    return _event(
        event_id="mpg-001-replay-sample-001",
        fixture_case="historical_momentum_continuation_sample",
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
        review_recommendation=ReplayReviewRecommendation.KEEP_OBSERVING,
        notes=[
            "Historical replay sample only.",
            "May exercise dry-run chain shape but is not a live market signal.",
        ],
    )


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


def build_mpg001_replay_lab_packet(
    *, generated_at_ms: int
) -> StrategyGroupReplayReport:
    replay_samples = [mpg001_replay_sample_event(observed_at_ms=generated_at_ms)]
    fixtures = synthetic_signal_fixtures(observed_at_ms=generated_at_ms)
    fixture_cases = {item.fixture_case for item in fixtures}
    fresh_pass = next(item for item in fixtures if item.fixture_case == "fresh_signal_pass")
    blocked_fixtures = [item for item in fixtures if item.fixture_case != "fresh_signal_pass"]

    checks = {
        "mpg001_replay_sample_present": len(replay_samples) == 1,
        "synthetic_fixture_cases_present": fixture_cases
        == EXPECTED_SYNTHETIC_FIXTURE_CASES,
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
            for item in [*replay_samples, *fixtures]
        ),
    }
    blockers = [name for name, ok in checks.items() if ok is not True]
    status: Literal["passed", "blocked"] = "passed" if not blockers else "blocked"
    return StrategyGroupReplayReport(
        status=status,
        generated_at_ms=generated_at_ms,
        strategy_group_id="MPG-001",
        replay_samples=replay_samples,
        synthetic_fixtures=fixtures,
        checks=checks,
        blockers=blockers,
        owner_summary=StrategyGroupReplayOwnerSummary(
            current_state="P0.5 replay_ready" if status == "passed" else "P0.5 replay_blocked",
            next_action=(
                "Use replay/synthetic rehearsal while P0 waits for a real fresh signal."
            ),
            summary_lines=[
                "MPG-001 replay sample is available.",
                "Synthetic fixtures cover fresh, stale, missing fact, conflict, protection, and profile-boundary cases.",
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
