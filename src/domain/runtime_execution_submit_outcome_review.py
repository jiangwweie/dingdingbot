"""Read-only classification of exchange-submit outcomes.

This model classifies a recorded exchange-submit execution result and trusted
local order facts into the attempt-outcome policy vocabulary. It is evidence
only: it does not release budget, mutate runtime state, create/cancel orders,
or call an exchange.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.brc_audit_ids import BrcSemanticIds
from src.domain.models import Order, OrderStatus
from src.domain.runtime_execution_attempt_outcome_policy import (
    RuntimeExecutionAttemptOutcomeKind,
)
from src.domain.runtime_execution_exchange_submit_execution_result import (
    RuntimeExecutionExchangeSubmitExecutionResult,
    RuntimeExecutionExchangeSubmitExecutionStatus,
)


class RuntimeExecutionSubmitOutcomeReviewModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuntimeExecutionSubmitOutcomeReviewStatus(str, Enum):
    BLOCKED = "blocked"
    CLASSIFIED_READY_FOR_ATTEMPT_OUTCOME_POLICY = (
        "classified_ready_for_attempt_outcome_policy"
    )


class RuntimeExecutionSubmitObservedOutcome(str, Enum):
    EXCHANGE_SUBMIT_NOT_COMPLETED = "exchange_submit_not_completed"
    ENTRY_SUBMIT_REJECTED_BEFORE_EXCHANGE = (
        "entry_submit_rejected_before_exchange"
    )
    SUBMITTED_NO_FILL_OPEN = "submitted_no_fill_open"
    SUBMITTED_NO_FILL_CANCELLED = "submitted_no_fill_cancelled"
    SUBMITTED_NO_FILL_EXPIRED = "submitted_no_fill_expired"
    SUBMITTED_PARTIAL_FILL = "submitted_partial_fill"
    SUBMITTED_FULL_FILL = "submitted_full_fill"
    ENTRY_FILLED_PROTECTION_CREATION_FAILED = (
        "entry_filled_protection_creation_failed"
    )
    UNRESOLVED = "unresolved"


class RuntimeExecutionSubmitOutcomeReview(
    RuntimeExecutionSubmitOutcomeReviewModel
):
    review_id: str = Field(min_length=1, max_length=620)
    exchange_submit_execution_result_id: str = Field(min_length=1, max_length=540)
    authorization_id: str = Field(min_length=1, max_length=220)
    execution_intent_id: str = Field(min_length=1, max_length=64)
    runtime_instance_id: str = Field(min_length=1, max_length=128)
    source_type: Optional[str] = Field(default=None, max_length=64)
    source_id: Optional[str] = Field(default=None, max_length=128)
    semantic_ids: BrcSemanticIds
    symbol: str = Field(min_length=1, max_length=128)
    status: RuntimeExecutionSubmitOutcomeReviewStatus
    observed_outcome: RuntimeExecutionSubmitObservedOutcome
    recommended_attempt_outcome_kind: Optional[
        RuntimeExecutionAttemptOutcomeKind
    ] = None
    attempt_outcome_policy_ready: bool
    entry_order_id: Optional[str] = Field(default=None, max_length=260)
    entry_order_status: Optional[str] = Field(default=None, max_length=64)
    entry_requested_qty: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    entry_filled_qty: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    protection_order_ids: list[str] = Field(default_factory=list)
    missing_order_ids: list[str] = Field(default_factory=list)
    post_submit_reconciliation_required: bool = False
    post_submit_reconciliation_evidence_id: Optional[str] = Field(
        default=None,
        max_length=260,
    )
    post_submit_reconciliation_status: Optional[str] = Field(
        default=None,
        max_length=64,
    )
    post_submit_reconciliation_checked_at_ms: Optional[int] = Field(
        default=None,
        ge=0,
    )
    post_submit_reconciliation_mismatch_count: int = Field(default=0, ge=0)
    post_submit_reconciliation_severe_count: int = Field(default=0, ge=0)
    post_submit_reconciliation_warning_count: int = Field(default=0, ge=0)
    submitted_to_exchange: bool
    any_fill: bool
    partial_fill: bool = False
    full_fill: bool = False
    no_fill: bool = False
    protection_creation_failed: bool = False
    requires_reconciliation_before_retry: bool = False
    blocks_attempt_outcome_policy_until_resolved: bool = False
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    not_execution_authority: Literal[True] = True
    not_budget_mutation_authority: Literal[True] = True
    runtime_state_mutated: Literal[False] = False
    attempt_counter_mutated: Literal[False] = False
    budget_released: Literal[False] = False
    budget_consumed: Literal[False] = False
    execution_intent_status_changed: Literal[False] = False
    order_created: Literal[False] = False
    order_cancelled: Literal[False] = False
    position_closed: Literal[False] = False
    exchange_called: Literal[False] = False
    exchange_order_submitted: Literal[False] = False
    order_lifecycle_called: Literal[False] = False
    owner_bounded_execution_called: Literal[False] = False
    withdrawal_instruction_created: Literal[False] = False
    transfer_instruction_created: Literal[False] = False
    created_at_ms: int = Field(ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_review(self) -> "RuntimeExecutionSubmitOutcomeReview":
        _reject_forbidden_metadata_fields(
            "runtime submit outcome review",
            {"metadata": self.metadata},
        )
        if (
            self.status
            == RuntimeExecutionSubmitOutcomeReviewStatus
            .CLASSIFIED_READY_FOR_ATTEMPT_OUTCOME_POLICY
        ):
            if self.blockers:
                raise ValueError("classified submit outcome review cannot have blockers")
            if self.recommended_attempt_outcome_kind is None:
                raise ValueError(
                    "classified submit outcome review requires attempt outcome kind"
                )
            if not self.attempt_outcome_policy_ready:
                raise ValueError(
                    "classified submit outcome review must be policy-ready"
                )
        if self.status == RuntimeExecutionSubmitOutcomeReviewStatus.BLOCKED:
            if not self.blockers:
                raise ValueError("blocked submit outcome review requires blockers")
            if self.attempt_outcome_policy_ready:
                raise ValueError("blocked submit outcome review cannot be policy-ready")
        if self.any_fill and self.no_fill:
            raise ValueError("submit outcome cannot be both filled and no-fill")
        if self.partial_fill and not self.any_fill:
            raise ValueError("partial fill requires any_fill")
        if self.full_fill and not self.any_fill:
            raise ValueError("full fill requires any_fill")
        if self.protection_creation_failed and not self.any_fill:
            raise ValueError("protection creation failure requires fill evidence")
        return self


def build_runtime_execution_submit_outcome_review(
    *,
    exchange_submit_execution_result: RuntimeExecutionExchangeSubmitExecutionResult,
    local_orders: list[Order] | None,
    post_submit_reconciliation_report: Any | None = None,
    post_submit_reconciliation_mismatches: list[Any] | None = None,
    now_ms: int,
    additional_blockers: list[str] | None = None,
    additional_warnings: list[str] | None = None,
) -> RuntimeExecutionSubmitOutcomeReview:
    result = exchange_submit_execution_result
    blockers = list(additional_blockers or [])
    warnings = list(result.warnings)
    warnings.extend(additional_warnings or [])
    order_by_id = {order.id: order for order in local_orders or []}
    entry_order_id = result.entry_order_id or _submitted_entry_order_id(result)
    protection_order_ids = list(result.protection_order_ids)
    missing_order_ids: list[str] = []
    reconciliation = _post_submit_reconciliation_evidence(
        result=result,
        report=post_submit_reconciliation_report,
        mismatches=post_submit_reconciliation_mismatches or [],
    )
    blockers.extend(reconciliation["blockers"])
    warnings.extend(reconciliation["warnings"])

    if result.status in {
        RuntimeExecutionExchangeSubmitExecutionStatus.BLOCKED,
        RuntimeExecutionExchangeSubmitExecutionStatus
        .EXCHANGE_SUBMIT_EXECUTION_DISABLED,
        RuntimeExecutionExchangeSubmitExecutionStatus
        .EXCHANGE_SUBMIT_EXECUTION_LOCK_ACQUIRED,
    }:
        blockers.append("exchange_submit_execution_not_completed")
        return _review(
            result=result,
            now_ms=now_ms,
            status=RuntimeExecutionSubmitOutcomeReviewStatus.BLOCKED,
            observed_outcome=(
                RuntimeExecutionSubmitObservedOutcome.EXCHANGE_SUBMIT_NOT_COMPLETED
            ),
            recommended_attempt_outcome_kind=None,
            entry_order_id=entry_order_id,
            entry_order=None,
            protection_order_ids=protection_order_ids,
            missing_order_ids=missing_order_ids,
            reconciliation=reconciliation,
            submitted_to_exchange=False,
            any_fill=False,
            no_fill=True,
            blockers=blockers,
            warnings=warnings,
        )

    if (
        result.status
        == RuntimeExecutionExchangeSubmitExecutionStatus.ENTRY_SUBMIT_FAILED
    ):
        return _review(
            result=result,
            now_ms=now_ms,
            status=(
                RuntimeExecutionSubmitOutcomeReviewStatus
                .CLASSIFIED_READY_FOR_ATTEMPT_OUTCOME_POLICY
            ),
            observed_outcome=(
                RuntimeExecutionSubmitObservedOutcome
                .ENTRY_SUBMIT_REJECTED_BEFORE_EXCHANGE
            ),
            recommended_attempt_outcome_kind=(
                RuntimeExecutionAttemptOutcomeKind.SUBMIT_REJECTED_BEFORE_EXCHANGE
            ),
            entry_order_id=entry_order_id or result.failed_local_order_id,
            entry_order=order_by_id.get(entry_order_id or ""),
            protection_order_ids=protection_order_ids,
            missing_order_ids=missing_order_ids,
            reconciliation=reconciliation,
            submitted_to_exchange=False,
            any_fill=False,
            no_fill=True,
            blockers=[],
            warnings=warnings,
        )

    if entry_order_id is None:
        blockers.append("entry_order_id_missing")
        entry_order = None
    else:
        entry_order = order_by_id.get(entry_order_id)
        if entry_order is None:
            blockers.append("entry_order_fact_missing")
            missing_order_ids.append(entry_order_id)

    for order_id in protection_order_ids:
        if order_id not in order_by_id:
            blockers.append("protection_order_fact_missing")
            missing_order_ids.append(order_id)

    if blockers:
        return _review(
            result=result,
            now_ms=now_ms,
            status=RuntimeExecutionSubmitOutcomeReviewStatus.BLOCKED,
            observed_outcome=RuntimeExecutionSubmitObservedOutcome.UNRESOLVED,
            recommended_attempt_outcome_kind=None,
            entry_order_id=entry_order_id,
            entry_order=entry_order,
            protection_order_ids=protection_order_ids,
            missing_order_ids=missing_order_ids,
            reconciliation=reconciliation,
            submitted_to_exchange=result.exchange_order_submitted,
            any_fill=False,
            no_fill=False,
            blockers=blockers,
            warnings=warnings,
        )

    assert entry_order is not None
    observed, outcome_kind, outcome_blockers, outcome_warnings = (
        _classify_entry_outcome(result, entry_order)
    )
    blockers.extend(outcome_blockers)
    warnings.extend(outcome_warnings)
    any_fill = entry_order.filled_qty > Decimal("0")
    partial_fill = (
        any_fill
        and entry_order.requested_qty > Decimal("0")
        and entry_order.filled_qty < entry_order.requested_qty
    )
    full_fill = (
        any_fill
        and entry_order.requested_qty > Decimal("0")
        and entry_order.filled_qty >= entry_order.requested_qty
    )
    no_fill = not any_fill

    if blockers:
        status = RuntimeExecutionSubmitOutcomeReviewStatus.BLOCKED
        outcome_kind = None
    else:
        status = (
            RuntimeExecutionSubmitOutcomeReviewStatus
            .CLASSIFIED_READY_FOR_ATTEMPT_OUTCOME_POLICY
        )

    return _review(
        result=result,
        now_ms=now_ms,
        status=status,
        observed_outcome=observed,
        recommended_attempt_outcome_kind=outcome_kind,
        entry_order_id=entry_order_id,
        entry_order=entry_order,
        protection_order_ids=protection_order_ids,
        missing_order_ids=missing_order_ids,
        reconciliation=reconciliation,
        submitted_to_exchange=result.exchange_order_submitted,
        any_fill=any_fill,
        partial_fill=partial_fill,
        full_fill=full_fill,
        no_fill=no_fill,
        protection_creation_failed=(
            observed
            == RuntimeExecutionSubmitObservedOutcome
            .ENTRY_FILLED_PROTECTION_CREATION_FAILED
        ),
        requires_reconciliation_before_retry=_requires_reconciliation(outcome_kind),
        blockers=blockers,
        warnings=warnings,
    )


def _classify_entry_outcome(
    result: RuntimeExecutionExchangeSubmitExecutionResult,
    entry_order: Order,
) -> tuple[
    RuntimeExecutionSubmitObservedOutcome,
    RuntimeExecutionAttemptOutcomeKind | None,
    list[str],
    list[str],
]:
    blockers: list[str] = []
    warnings: list[str] = []
    requested_qty = entry_order.requested_qty
    filled_qty = entry_order.filled_qty

    if requested_qty <= Decimal("0"):
        blockers.append("entry_order_requested_qty_invalid")
    if filled_qty < Decimal("0"):
        blockers.append("entry_order_filled_qty_invalid")
    if filled_qty > requested_qty and requested_qty > Decimal("0"):
        warnings.append("entry_order_filled_qty_exceeds_requested_qty")

    if (
        result.status
        == RuntimeExecutionExchangeSubmitExecutionStatus.PROTECTION_SUBMIT_FAILED
    ):
        if filled_qty <= Decimal("0"):
            blockers.append("protection_submit_failed_entry_fill_state_unresolved")
            return (
                RuntimeExecutionSubmitObservedOutcome.UNRESOLVED,
                None,
                blockers,
                warnings,
            )
        return (
            RuntimeExecutionSubmitObservedOutcome
            .ENTRY_FILLED_PROTECTION_CREATION_FAILED,
            RuntimeExecutionAttemptOutcomeKind
            .ENTRY_FILLED_PROTECTION_CREATION_FAILED,
            blockers,
            warnings,
        )

    if filled_qty <= Decimal("0"):
        if entry_order.status == OrderStatus.EXPIRED:
            return (
                RuntimeExecutionSubmitObservedOutcome.SUBMITTED_NO_FILL_EXPIRED,
                RuntimeExecutionAttemptOutcomeKind.SUBMITTED_NO_FILL_EXPIRED,
                blockers,
                warnings,
            )
        if entry_order.status in {OrderStatus.CANCELED, OrderStatus.REJECTED}:
            if entry_order.status == OrderStatus.REJECTED:
                warnings.append("entry_order_rejected_after_exchange_submission")
            return (
                RuntimeExecutionSubmitObservedOutcome.SUBMITTED_NO_FILL_CANCELLED,
                RuntimeExecutionAttemptOutcomeKind.SUBMITTED_NO_FILL_CANCELLED,
                blockers,
                warnings,
            )
        if entry_order.status in {OrderStatus.SUBMITTED, OrderStatus.OPEN}:
            blockers.append("entry_order_still_open_no_fill_unresolved")
            return (
                RuntimeExecutionSubmitObservedOutcome.SUBMITTED_NO_FILL_OPEN,
                None,
                blockers,
                warnings,
            )
        blockers.append("entry_order_status_unresolved_for_no_fill")
        return (
            RuntimeExecutionSubmitObservedOutcome.UNRESOLVED,
            None,
            blockers,
            warnings,
        )

    if requested_qty > Decimal("0") and filled_qty < requested_qty:
        return (
            RuntimeExecutionSubmitObservedOutcome.SUBMITTED_PARTIAL_FILL,
            RuntimeExecutionAttemptOutcomeKind.SUBMITTED_PARTIAL_FILL,
            blockers,
            warnings,
        )

    return (
        RuntimeExecutionSubmitObservedOutcome.SUBMITTED_FULL_FILL,
        RuntimeExecutionAttemptOutcomeKind.SUBMITTED_FULL_FILL,
        blockers,
        warnings,
    )


def _review(
    *,
    result: RuntimeExecutionExchangeSubmitExecutionResult,
    now_ms: int,
    status: RuntimeExecutionSubmitOutcomeReviewStatus,
    observed_outcome: RuntimeExecutionSubmitObservedOutcome,
    recommended_attempt_outcome_kind: RuntimeExecutionAttemptOutcomeKind | None,
    entry_order_id: str | None,
    entry_order: Order | None,
    protection_order_ids: list[str],
    missing_order_ids: list[str],
    reconciliation: dict[str, Any],
    submitted_to_exchange: bool,
    any_fill: bool,
    blockers: list[str],
    warnings: list[str],
    partial_fill: bool = False,
    full_fill: bool = False,
    no_fill: bool = False,
    protection_creation_failed: bool = False,
    requires_reconciliation_before_retry: bool = False,
) -> RuntimeExecutionSubmitOutcomeReview:
    normalized_blockers = _dedupe(blockers)
    return RuntimeExecutionSubmitOutcomeReview(
        review_id=(
            "runtime-submit-outcome-review-"
            f"{result.execution_result_id}"
        ),
        exchange_submit_execution_result_id=result.execution_result_id,
        authorization_id=result.authorization_id,
        execution_intent_id=result.execution_intent_id,
        runtime_instance_id=result.runtime_instance_id,
        source_type=result.source_type,
        source_id=result.source_id,
        semantic_ids=result.semantic_ids,
        symbol=result.symbol,
        status=status,
        observed_outcome=observed_outcome,
        recommended_attempt_outcome_kind=recommended_attempt_outcome_kind,
        attempt_outcome_policy_ready=(
            status
            == RuntimeExecutionSubmitOutcomeReviewStatus
            .CLASSIFIED_READY_FOR_ATTEMPT_OUTCOME_POLICY
        ),
        entry_order_id=entry_order_id,
        entry_order_status=_optional_status(entry_order),
        entry_requested_qty=entry_order.requested_qty if entry_order else None,
        entry_filled_qty=entry_order.filled_qty if entry_order else None,
        protection_order_ids=protection_order_ids,
        missing_order_ids=_dedupe(missing_order_ids),
        post_submit_reconciliation_required=bool(reconciliation["required"]),
        post_submit_reconciliation_evidence_id=reconciliation["evidence_id"],
        post_submit_reconciliation_status=reconciliation["status"],
        post_submit_reconciliation_checked_at_ms=reconciliation["checked_at_ms"],
        post_submit_reconciliation_mismatch_count=reconciliation["mismatch_count"],
        post_submit_reconciliation_severe_count=reconciliation["severe_count"],
        post_submit_reconciliation_warning_count=reconciliation["warning_count"],
        submitted_to_exchange=submitted_to_exchange,
        any_fill=any_fill,
        partial_fill=partial_fill,
        full_fill=full_fill,
        no_fill=no_fill,
        protection_creation_failed=protection_creation_failed,
        requires_reconciliation_before_retry=requires_reconciliation_before_retry,
        blocks_attempt_outcome_policy_until_resolved=bool(normalized_blockers),
        blockers=normalized_blockers,
        warnings=_dedupe(warnings),
        created_at_ms=now_ms,
        metadata={
            "scope": "runtime_execution_submit_outcome_review",
            "read_only_order_fact_classification": True,
            "exchange_submit_execution_status": result.status.value,
            "post_submit_reconciliation_required": bool(reconciliation["required"]),
            "post_submit_reconciliation_evidence_id": reconciliation["evidence_id"],
            "post_submit_reconciliation_status": reconciliation["status"],
            "does_not_release_budget": True,
            "does_not_mutate_runtime_state": True,
            "does_not_change_execution_intent_status": True,
            "does_not_create_cancel_or_close_orders": True,
            "does_not_call_order_lifecycle": True,
            "does_not_call_exchange": True,
            "does_not_create_withdrawal_or_transfer": True,
        },
    )


def _submitted_entry_order_id(
    result: RuntimeExecutionExchangeSubmitExecutionResult,
) -> str | None:
    for order in result.submitted_orders:
        if order.order_role == "ENTRY":
            return order.local_order_id
    return None


def _requires_reconciliation(
    outcome_kind: RuntimeExecutionAttemptOutcomeKind | None,
) -> bool:
    return outcome_kind in {
        RuntimeExecutionAttemptOutcomeKind.SUBMITTED_NO_FILL_CANCELLED,
        RuntimeExecutionAttemptOutcomeKind.SUBMITTED_NO_FILL_EXPIRED,
        RuntimeExecutionAttemptOutcomeKind.SUBMITTED_PARTIAL_FILL,
        RuntimeExecutionAttemptOutcomeKind
        .ENTRY_FILLED_PROTECTION_CREATION_FAILED,
        RuntimeExecutionAttemptOutcomeKind.POSITION_CLOSED_AFTER_FILL,
        RuntimeExecutionAttemptOutcomeKind.RECOVERY_RESOLVED,
    }


def _post_submit_reconciliation_evidence(
    *,
    result: RuntimeExecutionExchangeSubmitExecutionResult,
    report: Any | None,
    mismatches: list[Any],
) -> dict[str, Any]:
    required = result.status in {
        RuntimeExecutionExchangeSubmitExecutionStatus
        .EXCHANGE_SUBMIT_ORDERS_SUBMITTED,
        RuntimeExecutionExchangeSubmitExecutionStatus.PROTECTION_SUBMIT_FAILED,
    } and result.exchange_order_submitted
    evidence_id = _optional_str(getattr(report, "report_id", None))
    checked_at_ms = _optional_int(getattr(report, "checked_at_ms", None))
    is_fetch_failure = bool(getattr(report, "is_fetch_failure", False))
    is_consistent = bool(getattr(report, "is_consistent", False))
    severe_count = _optional_int(getattr(report, "severe_count", None))
    warning_count = _optional_int(getattr(report, "warning_count", None))
    mismatch_count = len(mismatches)
    if severe_count is None:
        severe_count = sum(
            1
            for mismatch in mismatches
            if getattr(mismatch, "severity", None) in {"SEVERE", "CRITICAL"}
        )
    if warning_count is None:
        warning_count = sum(
            1
            for mismatch in mismatches
            if getattr(mismatch, "severity", None) == "WARNING"
        )
    status = None
    blockers: list[str] = []
    warnings: list[str] = []

    if report is not None:
        status = (
            "fetch_failure"
            if is_fetch_failure
            else "clean"
            if is_consistent
            else "mismatch"
        )
        report_symbol = _optional_str(getattr(report, "symbol", None))
        report_runtime_id = _optional_str(getattr(report, "runtime_instance_id", None))
        if report_symbol and report_symbol != result.symbol:
            blockers.append("post_submit_reconciliation_symbol_mismatch")
        if report_runtime_id and report_runtime_id != result.runtime_instance_id:
            blockers.append("post_submit_reconciliation_runtime_mismatch")

    if required and not evidence_id:
        blockers.append("post_submit_reconciliation_evidence_missing")
    if is_fetch_failure:
        blockers.append("post_submit_reconciliation_fetch_failure")
    if required and severe_count > 0:
        blockers.append("post_submit_reconciliation_severe_mismatch_present")
    if required and report is not None and not is_consistent and severe_count == 0:
        warnings.append("post_submit_reconciliation_warning_mismatch_present")

    return {
        "required": required,
        "evidence_id": evidence_id,
        "status": status,
        "checked_at_ms": checked_at_ms,
        "mismatch_count": mismatch_count,
        "severe_count": severe_count,
        "warning_count": warning_count,
        "blockers": blockers,
        "warnings": warnings,
    }


def _optional_status(order: Order | None) -> str | None:
    if order is None:
        return None
    return order.status.value


def _optional_str(value: Any | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: Any | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _reject_forbidden_metadata_fields(scope: str, value: dict[str, Any]) -> None:
    forbidden = {
        "api_key",
        "api_secret",
        "secret",
        "credential",
        "exchange_payload",
        "place_order",
        "submit_order",
        "withdrawal_payload",
        "transfer_payload",
    }
    for key in _walk_keys(value):
        if key.lower() in forbidden:
            raise ValueError(f"{scope} contains forbidden field: {key}")


def _walk_keys(value: Any) -> list[str]:
    keys: list[str] = []
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="python")
    if isinstance(value, dict):
        for key, nested in value.items():
            keys.append(str(key))
            keys.extend(_walk_keys(nested))
    elif isinstance(value, list):
        for item in value:
            keys.extend(_walk_keys(item))
    return keys
