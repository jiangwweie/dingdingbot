"""Budgeted Autonomy v0.1 policy evaluation.

This module remains pure application logic. It can select a candidate for the
official Owner authorization + FinalGate path, but it never creates
authorizations, execution intents, orders, or exchange calls.
"""

from __future__ import annotations

import time
from decimal import Decimal
from typing import Literal

from pydantic import Field

from src.application.budget_recommendation import BlockerRecord
from src.application.budgeted_autonomy import (
    BudgetedAutonomyAuthorization,
    BudgetedAutonomyCandidateDecision,
    BudgetedAutonomyCandidateInput,
    BudgetedAutonomyLoopEvaluation,
    BudgetedAutonomyModel,
    BudgetedAutonomyPositionEvidence,
    evaluate_budgeted_autonomy_loop,
)


class BudgetedAutonomyDailyState(BudgetedAutonomyModel):
    day_key: str
    attempts_used: int = Field(ge=0, default=0)
    attempts_allowed: int = Field(ge=1, default=1)
    budget_used_notional: Decimal = Field(ge=Decimal("0"), default=Decimal("0"))
    realized_loss: Decimal = Field(ge=Decimal("0"), default=Decimal("0"))
    source: str = "pg_execution_results"


class BudgetedAutonomyV01Evaluation(BudgetedAutonomyModel):
    loop_version: Literal["budgeted_autonomy_v0_1"] = "budgeted_autonomy_v0_1"
    outcome: Literal[
        "closed_reviewed",
        "protected_open_review_pending",
        "blocked_with_retry_condition",
    ]
    base_loop: BudgetedAutonomyLoopEvaluation
    policy: dict[str, object]
    selected_candidate: BudgetedAutonomyCandidateDecision | None = None
    blocked_candidates: list[BudgetedAutonomyCandidateDecision] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    hard_blockers: list[BlockerRecord] = Field(default_factory=list)
    retry_condition: str
    action_allowed: Literal[False] = False
    backend_actionable: Literal[False] = False
    owner_action_enabled: Literal[False] = False
    auto_execution_enabled: Literal[False] = False
    may_execute_live: Literal[False] = False
    creates_authorization: Literal[False] = False
    creates_execution_intent: Literal[False] = False
    places_order: Literal[False] = False
    mutates_pg: Literal[False] = False


def evaluate_budgeted_autonomy_v01(
    *,
    authorization: BudgetedAutonomyAuthorization,
    positions: list[BudgetedAutonomyPositionEvidence],
    candidates: list[BudgetedAutonomyCandidateInput],
    daily_state: BudgetedAutonomyDailyState,
    review_ledger: dict[str, object] | None = None,
    now_ms: int | None = None,
) -> BudgetedAutonomyV01Evaluation:
    observed_now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    base = evaluate_budgeted_autonomy_loop(
        authorization=authorization,
        positions=positions,
        candidates=candidates,
        review_ledger=review_ledger,
        now_ms=observed_now_ms,
    )
    policy_blockers = _policy_blockers(
        authorization=authorization,
        daily_state=daily_state,
        selected_candidate=base.selected_candidate,
    )
    policy_summary = _policy_summary(
        authorization=authorization,
        daily_state=daily_state,
        selected_candidate=base.selected_candidate,
        blockers=policy_blockers,
    )
    if base.outcome in {"closed_reviewed", "protected_open_review_pending"}:
        return BudgetedAutonomyV01Evaluation(
            outcome=base.outcome,
            base_loop=base,
            policy=policy_summary,
            blocked_candidates=base.blocked_candidates,
            warnings=list(base.warnings),
            hard_blockers=[*base.hard_blockers, *policy_blockers],
            retry_condition=base.retry_condition,
        )
    if policy_blockers:
        selected = _blocked_selected_candidate(base.selected_candidate, policy_blockers)
        blocked = list(base.blocked_candidates)
        if selected is not None:
            blocked.insert(0, selected)
        return BudgetedAutonomyV01Evaluation(
            outcome="blocked_with_retry_condition",
            base_loop=base,
            policy=policy_summary,
            selected_candidate=None,
            blocked_candidates=blocked,
            warnings=[*base.warnings, "budgeted_autonomy_v01_policy_blocked"],
            hard_blockers=[*base.hard_blockers, *policy_blockers],
            retry_condition=policy_blockers[0].retry_condition,
        )
    return BudgetedAutonomyV01Evaluation(
        outcome=base.outcome,
        base_loop=base,
        policy=policy_summary,
        selected_candidate=base.selected_candidate,
        blocked_candidates=base.blocked_candidates,
        warnings=list(base.warnings),
        hard_blockers=list(base.hard_blockers),
        retry_condition=base.retry_condition,
    )


def _policy_blockers(
    *,
    authorization: BudgetedAutonomyAuthorization,
    daily_state: BudgetedAutonomyDailyState,
    selected_candidate: BudgetedAutonomyCandidateDecision | None,
) -> list[BlockerRecord]:
    blockers: list[BlockerRecord] = []
    if daily_state.attempts_used >= daily_state.attempts_allowed:
        blockers.append(
            _blocker(
                blocker_id="BUDGETED-AUTONOMY-V01-DAILY-ATTEMPTS-EXHAUSTED",
                evidence=(
                    f"attempts_used={daily_state.attempts_used} "
                    f"attempts_allowed={daily_state.attempts_allowed}"
                ),
                recovery_action="Keep new budgeted actions disabled for the rest of the budget day.",
                retry_condition="Wait for the next budget day or Owner creates a fresh scoped budget.",
            )
        )
    if daily_state.realized_loss >= authorization.daily_loss_cap:
        blockers.append(
            _blocker(
                blocker_id="BUDGETED-AUTONOMY-V01-DAILY-LOSS-CAP",
                evidence=(
                    f"realized_loss={daily_state.realized_loss} "
                    f"daily_loss_cap={authorization.daily_loss_cap}"
                ),
                recovery_action="Pause budgeted actions after daily loss cap is reached.",
                retry_condition="Owner review resets or replaces the budget after loss-cap review.",
            )
        )
    if selected_candidate is not None and selected_candidate.estimated_notional_usdt is not None:
        remaining = authorization.max_notional_per_action - daily_state.budget_used_notional
        if remaining <= Decimal("0") or selected_candidate.estimated_notional_usdt > remaining:
            blockers.append(
                _blocker(
                    blocker_id="BUDGETED-AUTONOMY-V01-BUDGET-REMAINING",
                    evidence=(
                        f"candidate_notional={selected_candidate.estimated_notional_usdt} "
                        f"remaining_notional={remaining}"
                    ),
                    recovery_action="Keep candidate disabled until budget remaining can cover the action.",
                    retry_condition="Lower candidate size or wait for a fresh budget window.",
                )
            )
    return blockers


def _policy_summary(
    *,
    authorization: BudgetedAutonomyAuthorization,
    daily_state: BudgetedAutonomyDailyState,
    selected_candidate: BudgetedAutonomyCandidateDecision | None,
    blockers: list[BlockerRecord],
) -> dict[str, object]:
    remaining_attempts = max(daily_state.attempts_allowed - daily_state.attempts_used, 0)
    remaining_notional = max(
        authorization.max_notional_per_action - daily_state.budget_used_notional,
        Decimal("0"),
    )
    remaining_loss = max(authorization.daily_loss_cap - daily_state.realized_loss, Decimal("0"))
    return {
        "policy_version": "budgeted_autonomy_v0_1",
        "daily_attempts": {
            "day_key": daily_state.day_key,
            "used": daily_state.attempts_used,
            "allowed": daily_state.attempts_allowed,
            "remaining": remaining_attempts,
            "source": daily_state.source,
        },
        "position_policy": {
            "max_active_positions": authorization.max_active_positions,
            "single_position_default": authorization.max_active_positions == 1,
        },
        "budget": {
            "max_notional_per_action": str(authorization.max_notional_per_action),
            "used_notional": str(daily_state.budget_used_notional),
            "remaining_notional": str(remaining_notional),
            "selected_candidate_notional": (
                str(selected_candidate.estimated_notional_usdt)
                if selected_candidate and selected_candidate.estimated_notional_usdt is not None
                else None
            ),
        },
        "daily_loss": {
            "cap": str(authorization.daily_loss_cap),
            "realized_loss": str(daily_state.realized_loss),
            "remaining": str(remaining_loss),
        },
        "scope": {
            "allowed_carriers": list(authorization.allowed_carriers),
            "allowed_symbols": list(authorization.allowed_symbols),
            "allowed_sides": list(authorization.allowed_sides),
            "max_leverage": str(authorization.max_leverage),
            "review_required": authorization.review_required,
            "protection_mode": authorization.protection_mode,
        },
        "stop_conditions": [item.id for item in blockers],
        "pause_state": authorization.pause_state,
        "revoked": authorization.revoked,
        "valid_until_ms": authorization.valid_until_ms,
        "action_allowed": False,
        "auto_execution_enabled": False,
    }


def _blocked_selected_candidate(
    candidate: BudgetedAutonomyCandidateDecision | None,
    blockers: list[BlockerRecord],
) -> BudgetedAutonomyCandidateDecision | None:
    if candidate is None:
        return None
    return candidate.model_copy(
        update={
            "status": "blocked",
            "blockers": [*candidate.blockers, *blockers],
        }
    )


def _blocker(
    *,
    blocker_id: str,
    evidence: str,
    recovery_action: str,
    retry_condition: str,
) -> BlockerRecord:
    return BlockerRecord(
        id=blocker_id,
        stage="BudgetedAutonomyV01",
        path="BudgetEnvelope -> DailyPolicy -> CandidateSelector",
        evidence=evidence,
        severity="hard_blocker",
        recovery_action=recovery_action,
        retry_condition=retry_condition,
    )
