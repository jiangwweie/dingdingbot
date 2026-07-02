"""Right-tail trade review metrics for bounded runtime experiments.

This module is pure domain logic. It evaluates explicit trade-path facts for
review and learning only. It cannot create orders, execution intents, exchange
requests, withdrawal instructions, or runtime budget mutations.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class RightTailReviewModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RightTailTradeClassification(str, Enum):
    RIGHT_TAIL_WIN = "right_tail_win"
    ORDINARY_WIN = "ordinary_win"
    SMALL_BOUNDED_LOSS = "small_bounded_loss"
    LOSS_BOUNDARY_BREACH = "loss_boundary_breach"
    FLAT_OR_COST = "flat_or_cost"
    REVIEW_INPUTS_REQUIRED = "review_inputs_required"


class StopEffectiveness(str, Enum):
    EFFECTIVE_BOUNDED_LOSS = "effective_bounded_loss"
    INEFFECTIVE_BOUNDARY_BREACHED = "ineffective_boundary_breached"
    NOT_APPLICABLE_WIN = "not_applicable_win"
    NOT_REVIEWABLE_MISSING_RISK_BASIS = "not_reviewable_missing_risk_basis"


class AttemptContinuationQuality(str, Enum):
    CAPTURED_RIGHT_TAIL = "captured_right_tail"
    CONTINUE_AFTER_SMALL_LOSS = "continue_after_small_loss"
    REVISE_EXIT_POLICY = "revise_exit_policy"
    PARK_OR_REDUCE = "park_or_reduce"
    REVIEW_REQUIRED = "review_required"


class RightTailTradePathFacts(RightTailReviewModel):
    trade_id: str = Field(min_length=1, max_length=128)
    symbol: str = Field(min_length=1, max_length=128)
    side: Literal["long", "short"]
    strategy_family_id: Optional[str] = Field(default=None, max_length=128)
    strategy_family_version_id: Optional[str] = Field(default=None, max_length=128)
    runtime_instance_id: Optional[str] = Field(default=None, max_length=128)
    order_candidate_id: Optional[str] = Field(default=None, max_length=128)
    source_review_id: Optional[str] = Field(default=None, max_length=128)
    entry_price: Optional[Decimal] = Field(default=None, gt=Decimal("0"))
    exit_price: Optional[Decimal] = Field(default=None, gt=Decimal("0"))
    mfe_price: Optional[Decimal] = Field(default=None, gt=Decimal("0"))
    mae_price: Optional[Decimal] = Field(default=None, gt=Decimal("0"))
    realized_pnl: Optional[Decimal] = None
    max_loss_budget: Optional[Decimal] = Field(default=None, gt=Decimal("0"))
    protection_stop_price: Optional[Decimal] = Field(default=None, gt=Decimal("0"))
    opened_at_ms: Optional[int] = Field(default=None, ge=0)
    closed_at_ms: Optional[int] = Field(default=None, ge=0)
    exit_reason: Optional[str] = Field(default=None, max_length=128)
    runner_required: bool = True
    runner_preserved: Optional[bool] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RightTailTradeReviewResult(RightTailReviewModel):
    trade_id: str
    status: Literal["reviewed", "review_inputs_required"]
    classification: RightTailTradeClassification
    symbol: str
    side: Literal["long", "short"]
    strategy_family_id: Optional[str] = None
    strategy_family_version_id: Optional[str] = None
    runtime_instance_id: Optional[str] = None
    source_review_id: Optional[str] = None
    required_inputs: list[str] = Field(default_factory=list)
    mfe_pct: Optional[Decimal] = None
    mae_pct: Optional[Decimal] = None
    realized_move_pct: Optional[Decimal] = None
    r_multiple: Optional[Decimal] = None
    tail_win_size: Decimal = Decimal("0")
    realized_pnl: Optional[Decimal] = None
    winner_hold_time_ms: Optional[int] = None
    runner_giveback_pct: Optional[Decimal] = None
    runner_capped_too_early: Optional[bool] = None
    stop_effectiveness: StopEffectiveness = (
        StopEffectiveness.NOT_REVIEWABLE_MISSING_RISK_BASIS
    )
    attempt_continuation_quality: AttemptContinuationQuality = (
        AttemptContinuationQuality.REVIEW_REQUIRED
    )
    warnings: list[str] = Field(default_factory=list)
    places_order: Literal[False] = False
    creates_execution_intent: Literal[False] = False
    calls_exchange: Literal[False] = False
    mutates_runtime_budget: Literal[False] = False
    mutates_strategy_pnl: Literal[False] = False
    creates_withdrawal_instruction: Literal[False] = False


class RightTailReviewSummary(RightTailReviewModel):
    status: Literal["empty", "reviewed", "review_inputs_required"]
    source_policy: Literal["explicit_trade_path_facts_only"] = (
        "explicit_trade_path_facts_only"
    )
    trade_count: int = 0
    reviewed_trade_count: int = 0
    missing_input_trade_count: int = 0
    right_tail_win_count: int = 0
    small_loss_count: int = 0
    loss_boundary_breach_count: int = 0
    max_r_multiple: Optional[Decimal] = None
    max_mfe_pct: Optional[Decimal] = None
    max_mae_pct: Optional[Decimal] = None
    largest_tail_win: Decimal = Decimal("0")
    average_small_loss: Optional[Decimal] = None
    single_tail_win_covers_small_losses: Optional[Decimal] = None
    payoff_asymmetry_present: bool = False
    trade_reviews: list[RightTailTradeReviewResult] = Field(default_factory=list)
    required_inputs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    no_action_guarantee: dict[str, bool] = Field(
        default_factory=lambda: {
            "places_order": False,
            "creates_execution_intent": False,
            "calls_exchange": False,
            "mutates_runtime_budget": False,
            "mutates_strategy_pnl": False,
            "creates_withdrawal_instruction": False,
        }
    )


def review_right_tail_trade_path(
    facts: RightTailTradePathFacts,
    *,
    tail_win_r_threshold: Decimal = Decimal("3"),
    tail_win_pct_threshold: Decimal = Decimal("5"),
    runner_giveback_threshold_pct: Decimal = Decimal("1"),
) -> RightTailTradeReviewResult:
    required_inputs = _missing_required_inputs(facts)
    if required_inputs:
        return RightTailTradeReviewResult(
            trade_id=facts.trade_id,
            status="review_inputs_required",
            classification=RightTailTradeClassification.REVIEW_INPUTS_REQUIRED,
            symbol=facts.symbol,
            side=facts.side,
            strategy_family_id=facts.strategy_family_id,
            strategy_family_version_id=facts.strategy_family_version_id,
            runtime_instance_id=facts.runtime_instance_id,
            source_review_id=facts.source_review_id,
            required_inputs=required_inputs,
            warnings=["right_tail_review_requires_explicit_trade_path_facts"],
        )

    assert facts.entry_price is not None
    assert facts.exit_price is not None
    assert facts.mfe_price is not None
    assert facts.mae_price is not None
    assert facts.realized_pnl is not None

    mfe_pct = max(
        Decimal("0"),
        _directional_pct(facts.side, facts.entry_price, facts.mfe_price),
    )
    mae_pct = min(
        Decimal("0"),
        _directional_pct(facts.side, facts.entry_price, facts.mae_price),
    )
    realized_move_pct = _directional_pct(
        facts.side,
        facts.entry_price,
        facts.exit_price,
    )
    r_multiple = _r_multiple(facts, realized_move_pct)
    winner_hold_time_ms = (
        facts.closed_at_ms - facts.opened_at_ms
        if facts.opened_at_ms is not None and facts.closed_at_ms is not None
        else None
    )
    runner_giveback_pct = max(
        Decimal("0"),
        mfe_pct - max(realized_move_pct, Decimal("0")),
    )
    runner_capped = _runner_capped_too_early(
        facts=facts,
        runner_giveback_pct=runner_giveback_pct,
        threshold=runner_giveback_threshold_pct,
    )
    classification = _classify_trade(
        facts=facts,
        realized_move_pct=realized_move_pct,
        r_multiple=r_multiple,
        tail_win_r_threshold=tail_win_r_threshold,
        tail_win_pct_threshold=tail_win_pct_threshold,
    )
    stop_effectiveness = _stop_effectiveness(
        classification=classification,
        r_multiple=r_multiple,
    )
    attempt_quality = _attempt_continuation_quality(
        classification=classification,
        runner_capped=runner_capped,
    )
    return RightTailTradeReviewResult(
        trade_id=facts.trade_id,
        status="reviewed",
        classification=classification,
        symbol=facts.symbol,
        side=facts.side,
        strategy_family_id=facts.strategy_family_id,
        strategy_family_version_id=facts.strategy_family_version_id,
        runtime_instance_id=facts.runtime_instance_id,
        source_review_id=facts.source_review_id,
        mfe_pct=_q(mfe_pct),
        mae_pct=_q(mae_pct),
        realized_move_pct=_q(realized_move_pct),
        r_multiple=_q(r_multiple) if r_multiple is not None else None,
        tail_win_size=(
            facts.realized_pnl
            if classification == RightTailTradeClassification.RIGHT_TAIL_WIN
            else Decimal("0")
        ),
        realized_pnl=facts.realized_pnl,
        winner_hold_time_ms=winner_hold_time_ms,
        runner_giveback_pct=_q(runner_giveback_pct),
        runner_capped_too_early=runner_capped,
        stop_effectiveness=stop_effectiveness,
        attempt_continuation_quality=attempt_quality,
        warnings=_trade_warnings(facts=facts, runner_capped=runner_capped),
    )


def summarize_right_tail_reviews(
    trade_facts: list[RightTailTradePathFacts],
) -> RightTailReviewSummary:
    if not trade_facts:
        return RightTailReviewSummary(
            status="empty",
            required_inputs=["live_lifecycle_review.metadata.right_tail_trade_path"],
            warnings=["no_explicit_right_tail_trade_path_facts"],
        )

    reviews = [review_right_tail_trade_path(item) for item in trade_facts]
    reviewed = [item for item in reviews if item.status == "reviewed"]
    missing = [item for item in reviews if item.status != "reviewed"]
    right_tail_wins = [
        item for item in reviewed
        if item.classification == RightTailTradeClassification.RIGHT_TAIL_WIN
    ]
    small_losses = [
        item for item in reviewed
        if item.classification == RightTailTradeClassification.SMALL_BOUNDED_LOSS
        and item.realized_pnl is not None
    ]
    breaches = [
        item for item in reviewed
        if item.classification == RightTailTradeClassification.LOSS_BOUNDARY_BREACH
    ]
    small_loss_amounts = [abs(item.realized_pnl or Decimal("0")) for item in small_losses]
    average_small_loss = (
        sum(small_loss_amounts, Decimal("0")) / Decimal(len(small_loss_amounts))
        if small_loss_amounts
        else None
    )
    largest_tail_win = max(
        [item.tail_win_size for item in right_tail_wins] or [Decimal("0")]
    )
    coverage = (
        largest_tail_win / average_small_loss
        if average_small_loss is not None and average_small_loss > Decimal("0")
        else None
    )
    max_r_multiple = _max_optional([item.r_multiple for item in reviewed])
    max_mfe_pct = _max_optional([item.mfe_pct for item in reviewed])
    max_mae_pct = _min_optional([item.mae_pct for item in reviewed])
    required_inputs = sorted(
        {
            required
            for item in missing
            for required in item.required_inputs
        }
    )
    return RightTailReviewSummary(
        status="review_inputs_required" if missing else "reviewed",
        trade_count=len(reviews),
        reviewed_trade_count=len(reviewed),
        missing_input_trade_count=len(missing),
        right_tail_win_count=len(right_tail_wins),
        small_loss_count=len(small_losses),
        loss_boundary_breach_count=len(breaches),
        max_r_multiple=max_r_multiple,
        max_mfe_pct=max_mfe_pct,
        max_mae_pct=max_mae_pct,
        largest_tail_win=largest_tail_win,
        average_small_loss=_q(average_small_loss) if average_small_loss is not None else None,
        single_tail_win_covers_small_losses=_q(coverage) if coverage is not None else None,
        payoff_asymmetry_present=bool(
            (max_r_multiple is not None and max_r_multiple >= Decimal("3"))
            or (coverage is not None and coverage >= Decimal("3"))
        ),
        trade_reviews=reviews,
        required_inputs=required_inputs,
        warnings=sorted(
            {
                warning
                for item in reviews
                for warning in item.warnings
            }
        ),
    )


def _missing_required_inputs(facts: RightTailTradePathFacts) -> list[str]:
    missing: list[str] = []
    for key in [
        "entry_price",
        "exit_price",
        "mfe_price",
        "mae_price",
        "realized_pnl",
        "opened_at_ms",
        "closed_at_ms",
    ]:
        if getattr(facts, key) is None:
            missing.append(key)
    if facts.max_loss_budget is None and facts.protection_stop_price is None:
        missing.append("max_loss_budget_or_protection_stop_price")
    return missing


def _directional_pct(side: Literal["long", "short"], entry: Decimal, price: Decimal) -> Decimal:
    if side == "long":
        return ((price - entry) / entry) * Decimal("100")
    return ((entry - price) / entry) * Decimal("100")


def _r_multiple(
    facts: RightTailTradePathFacts,
    realized_move_pct: Decimal,
) -> Optional[Decimal]:
    if facts.max_loss_budget is not None and facts.realized_pnl is not None:
        return facts.realized_pnl / facts.max_loss_budget
    if facts.protection_stop_price is None or facts.entry_price is None:
        return None
    stop_risk_pct = abs(
        _directional_pct(facts.side, facts.entry_price, facts.protection_stop_price)
    )
    if stop_risk_pct == Decimal("0"):
        return None
    return realized_move_pct / stop_risk_pct


def _classify_trade(
    *,
    facts: RightTailTradePathFacts,
    realized_move_pct: Decimal,
    r_multiple: Optional[Decimal],
    tail_win_r_threshold: Decimal,
    tail_win_pct_threshold: Decimal,
) -> RightTailTradeClassification:
    assert facts.realized_pnl is not None
    if facts.realized_pnl > Decimal("0"):
        if (
            r_multiple is not None and r_multiple >= tail_win_r_threshold
        ) or realized_move_pct >= tail_win_pct_threshold:
            return RightTailTradeClassification.RIGHT_TAIL_WIN
        return RightTailTradeClassification.ORDINARY_WIN
    if facts.realized_pnl < Decimal("0"):
        if r_multiple is not None and r_multiple >= Decimal("-1"):
            return RightTailTradeClassification.SMALL_BOUNDED_LOSS
        return RightTailTradeClassification.LOSS_BOUNDARY_BREACH
    return RightTailTradeClassification.FLAT_OR_COST


def _runner_capped_too_early(
    *,
    facts: RightTailTradePathFacts,
    runner_giveback_pct: Decimal,
    threshold: Decimal,
) -> Optional[bool]:
    if not facts.runner_required:
        return False
    if facts.runner_preserved is True:
        return False
    if facts.runner_preserved is False:
        return runner_giveback_pct >= threshold
    return None


def _stop_effectiveness(
    *,
    classification: RightTailTradeClassification,
    r_multiple: Optional[Decimal],
) -> StopEffectiveness:
    if classification in {
        RightTailTradeClassification.RIGHT_TAIL_WIN,
        RightTailTradeClassification.ORDINARY_WIN,
        RightTailTradeClassification.FLAT_OR_COST,
    }:
        return StopEffectiveness.NOT_APPLICABLE_WIN
    if r_multiple is None:
        return StopEffectiveness.NOT_REVIEWABLE_MISSING_RISK_BASIS
    if classification == RightTailTradeClassification.SMALL_BOUNDED_LOSS:
        return StopEffectiveness.EFFECTIVE_BOUNDED_LOSS
    return StopEffectiveness.INEFFECTIVE_BOUNDARY_BREACHED


def _attempt_continuation_quality(
    *,
    classification: RightTailTradeClassification,
    runner_capped: Optional[bool],
) -> AttemptContinuationQuality:
    if classification == RightTailTradeClassification.RIGHT_TAIL_WIN:
        return AttemptContinuationQuality.CAPTURED_RIGHT_TAIL
    if classification == RightTailTradeClassification.SMALL_BOUNDED_LOSS:
        return AttemptContinuationQuality.CONTINUE_AFTER_SMALL_LOSS
    if classification == RightTailTradeClassification.LOSS_BOUNDARY_BREACH:
        return AttemptContinuationQuality.PARK_OR_REDUCE
    if runner_capped is True:
        return AttemptContinuationQuality.REVISE_EXIT_POLICY
    return AttemptContinuationQuality.REVIEW_REQUIRED


def _trade_warnings(
    *,
    facts: RightTailTradePathFacts,
    runner_capped: Optional[bool],
) -> list[str]:
    warnings: list[str] = []
    if facts.runner_required and runner_capped is None:
        warnings.append("runner_preservation_not_assessed")
    if runner_capped is True:
        warnings.append("runner_may_have_been_capped_too_early")
    return warnings


def _max_optional(values: list[Optional[Decimal]]) -> Optional[Decimal]:
    present = [item for item in values if item is not None]
    return max(present) if present else None


def _min_optional(values: list[Optional[Decimal]]) -> Optional[Decimal]:
    present = [item for item in values if item is not None]
    return min(present) if present else None


def _q(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"))
