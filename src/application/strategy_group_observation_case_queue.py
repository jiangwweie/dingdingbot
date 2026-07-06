"""Read-only observation case queue for strategy-group would-enter signals."""

from __future__ import annotations

from collections import defaultdict
from typing import Literal

from pydantic import BaseModel, Field

from src.application.strategy_group_forward_review import StrategyGroupForwardReviewRecord
from src.application.strategy_group_live_readonly_observation import StrategyGroupObservationRecord


CaseStatus = Literal["open", "pending_forward_review", "forward_review_complete"]


class ObservationCaseForwardReview(BaseModel):
    review_window: str
    review_status: str
    review_due_at_ms: int
    forward_return_pct: str | None = None
    mfe_pct: str | None = None
    mae_pct: str | None = None
    calculated_at_ms: int | None = None
    notes: str | None = None


class ObservationCaseQueueItem(BaseModel):
    case_id: str
    observation_id: str
    strategy_group_id: str
    candidate_id: str
    symbol: str
    side: str
    signal_type: Literal["would_enter"]
    case_status: CaseStatus
    owner_review_status: str = "owner_review_pending"
    observed_at_ms: int
    recorded_at_ms: int | None = None
    market_bar_timestamp_ms: int
    market_bar_close: str | None = None
    source_type: str
    market_source: str
    review_windows: list[str] = Field(default_factory=list)
    completed_review_windows: list[str] = Field(default_factory=list)
    pending_review_windows: list[str] = Field(default_factory=list)
    forward_reviews: list[ObservationCaseForwardReview] = Field(default_factory=list)
    risk_tags: list[str] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
    human_summary: str
    owner_interpretation: str
    source_refs: list[str] = Field(default_factory=list)
    not_order: Literal[True] = True
    not_execution_intent: Literal[True] = True
    no_execution_permission: Literal[True] = True
    no_order_permission: Literal[True] = True
    no_runtime_start: Literal[True] = True


class ObservationCaseQueueResponse(BaseModel):
    generated_from: str = "strategy_group_observation_case_queue_v1"
    queue_status: str
    sink_source: str = "pg_brc_strategy_group_observations"
    forward_review_source: str = "pg_brc_strategy_group_forward_reviews"
    case_count: int
    cases: list[ObservationCaseQueueItem] = Field(default_factory=list)
    excluded_signal_types: list[str] = Field(default_factory=lambda: ["no_action", "invalid"])
    supported_future_cases: dict[str, str] = Field(default_factory=dict)
    non_permissions: dict[str, bool] = Field(default_factory=lambda: _non_permissions())
    source_refs: list[str] = Field(
        default_factory=lambda: [
            "pg_strategy_group_observation_case_queue_readmodel",
            "pg_strategy_group_live_readonly_observations",
            "pg_strategy_group_forward_reviews",
        ]
    )


def build_observation_case_queue(
    observations: list[StrategyGroupObservationRecord],
    forward_reviews: list[StrategyGroupForwardReviewRecord],
    *,
    candidate_id: str | None = None,
    strategy_group_id: str | None = None,
    status: str | None = None,
) -> ObservationCaseQueueResponse:
    """Build a review-only case queue from persisted observation evidence.

    Only ``would_enter`` observations become cases. ``no_action`` and
    ``invalid`` records stay as observation history, because they do not need
    Owner case review.
    """

    reviews_by_observation: dict[str, list[StrategyGroupForwardReviewRecord]] = defaultdict(list)
    for review in forward_reviews:
        reviews_by_observation[review.observation_id].append(review)

    items = [
        _case_item(observation, reviews_by_observation.get(observation.record_id, []))
        for observation in observations
        if observation.signal_type == "would_enter"
    ]

    if candidate_id:
        items = [item for item in items if item.candidate_id == candidate_id]
    if strategy_group_id:
        items = [item for item in items if item.strategy_group_id == strategy_group_id]
    if status:
        items = [item for item in items if item.case_status == status]

    items.sort(key=lambda item: (item.observed_at_ms, item.recorded_at_ms or 0), reverse=True)
    return ObservationCaseQueueResponse(
        queue_status="available",
        case_count=len(items),
        cases=items,
        supported_future_cases={
            "CPM-RO-001": (
                "future CPM would_enter signals will enter the same Owner review queue with "
                "owner_special_observation / OOS-negative risk tags"
            )
        },
    )


def blocked_observation_case_queue(*, reason: str) -> ObservationCaseQueueResponse:
    return ObservationCaseQueueResponse(
        queue_status=f"blocked_{reason}",
        case_count=0,
        cases=[],
        supported_future_cases={
            "CPM-RO-001": "supported when PG observation records are available"
        },
    )


def _case_item(
    observation: StrategyGroupObservationRecord,
    reviews: list[StrategyGroupForwardReviewRecord],
) -> ObservationCaseQueueItem:
    ordered_reviews = sorted(reviews, key=lambda review: review.review_due_at_ms)
    review_windows = _review_windows(observation, ordered_reviews)
    completed = [
        review.review_window
        for review in ordered_reviews
        if review.review_status == "completed"
    ]
    pending = [
        window
        for window in review_windows
        if window not in completed
        and _review_status(window, ordered_reviews) in {"pending", "missing"}
    ]
    case_status: CaseStatus = (
        "forward_review_complete"
        if review_windows and not pending and set(completed) >= set(review_windows)
        else "pending_forward_review"
        if pending or ordered_reviews
        else "open"
    )
    forward_review_models = [
        ObservationCaseForwardReview(
            review_window=review.review_window,
            review_status=review.review_status,
            review_due_at_ms=review.review_due_at_ms,
            forward_return_pct=review.forward_return_pct,
            mfe_pct=review.mfe_pct,
            mae_pct=review.mae_pct,
            calculated_at_ms=review.calculated_at_ms,
            notes=review.notes,
        )
        for review in ordered_reviews
    ]
    return ObservationCaseQueueItem(
        case_id=_case_id(observation),
        observation_id=observation.record_id,
        strategy_group_id=observation.strategy_group_id,
        candidate_id=observation.candidate_id,
        symbol=observation.symbol,
        side=observation.side,
        signal_type="would_enter",
        case_status=case_status,
        observed_at_ms=observation.evaluated_at_ms,
        recorded_at_ms=observation.recorded_at_ms,
        market_bar_timestamp_ms=observation.market_bar_timestamp_ms,
        market_bar_close=observation.market_bar_close,
        source_type=observation.source_type,
        market_source=observation.market_source,
        review_windows=review_windows,
        completed_review_windows=completed,
        pending_review_windows=pending,
        forward_reviews=forward_review_models,
        risk_tags=_risk_tags(observation, ordered_reviews),
        reason_codes=list(observation.reason_codes),
        human_summary=observation.human_summary,
        owner_interpretation=_owner_interpretation(observation, ordered_reviews, pending),
        source_refs=_source_refs(observation),
    )


def _case_id(observation: StrategyGroupObservationRecord) -> str:
    if observation.candidate_id == "MI-001-BNB-LONG":
        return "MI-001-BNB-LONG-live-case-001"
    return f"{observation.candidate_id}:{observation.market_bar_timestamp_ms}:owner-review"


def _review_windows(
    observation: StrategyGroupObservationRecord,
    reviews: list[StrategyGroupForwardReviewRecord],
) -> list[str]:
    observed = list(observation.review_windows)
    reviewed = [review.review_window for review in reviews]
    windows: list[str] = []
    for window in observed + reviewed:
        if window not in windows:
            windows.append(window)
    return windows


def _review_status(window: str, reviews: list[StrategyGroupForwardReviewRecord]) -> str:
    for review in reviews:
        if review.review_window == window:
            return review.review_status
    return "missing"


def _risk_tags(
    observation: StrategyGroupObservationRecord,
    reviews: list[StrategyGroupForwardReviewRecord],
) -> list[str]:
    tags: list[str] = ["owner_review_required", "signal_not_order"]
    if observation.strategy_group_id == "MI-001":
        tags.extend(["no_chase_required", "wait_for_confirmation_required", "high_mae_watch"])
        if observation.candidate_id == "MI-001-BNB-LONG":
            tags.append("bnb_live_case_001")
        if any(_negative(review.forward_return_pct) for review in reviews if review.review_status == "completed"):
            tags.extend(["local_exhaustion_watch", "adverse_path_watch"])
    if observation.candidate_id == "CPM-RO-001" or observation.strategy_group_id == "CPM-RO-001":
        tags.extend(
            [
                "owner_special_observation",
                "historical_oos_negative_warning",
                "not_proven_alpha",
                "not_runtime_eligible_by_default",
            ]
        )
    return sorted(set(tags))


def _owner_interpretation(
    observation: StrategyGroupObservationRecord,
    reviews: list[StrategyGroupForwardReviewRecord],
    pending: list[str],
) -> str:
    completed = [review for review in reviews if review.review_status == "completed"]
    if observation.candidate_id == "MI-001-BNB-LONG":
        if completed and any(_negative(review.forward_return_pct) for review in completed):
            return (
                "BNB live case #001 remains an Owner-review case, not a trade. "
                "Completed forward windows include adverse path evidence, so no-chase and "
                "wait-for-confirmation constraints remain active while pending windows finish."
            )
        return (
            "BNB live case #001 is queued for Owner review. The signal is would_enter only; "
            "forward review windows must be inspected before any separate trial decision."
        )
    if observation.candidate_id == "CPM-RO-001":
        return (
            "CPM would-enter is supported as owner_special_observation only. Historical 2021/2022 "
            "OOS evidence was negative, so the case is not proven alpha and not runtime eligible by default."
        )
    if pending:
        return "Would-enter observation is queued for Owner review while forward windows remain pending."
    return "Would-enter observation is queued for Owner review with completed forward review windows."


def _negative(value: str | None) -> bool:
    if value is None:
        return False
    try:
        return value.strip().startswith("-")
    except AttributeError:
        return False


def _source_refs(observation: StrategyGroupObservationRecord) -> list[str]:
    refs = [
        "pg_strategy_group_observation_case_queue_readmodel",
        "pg_strategy_group_live_readonly_observations",
    ]
    if observation.candidate_id == "MI-001-BNB-LONG":
        refs.extend(
            [
                "pg_strategy_group_observation_case_mi001_bnb",
                "pg_strategy_group_forward_review_mi001_bnb",
            ]
        )
    if observation.candidate_id == "CPM-RO-001":
        refs.append("pg_strategy_review_cpm_oos_classification")
    return refs


def _non_permissions() -> dict[str, bool]:
    return {
        "no_trial_start": True,
        "no_execution_intent": True,
        "no_order_permission": True,
        "no_execution_permission": True,
        "no_runtime_start": True,
        "no_automatic_strategy_routing": True,
        "signal_not_order": True,
        "observation_not_execution_readiness": True,
    }
