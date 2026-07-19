"""Durable command semantics for ticket-bound exchange writes.

The command is persisted before dispatch and resolved from authoritative
exchange truth after an ambiguous outcome.  This module is pure domain logic;
it does not perform database or exchange I/O.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from hashlib import sha256
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ExchangeCommandModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExchangeCommandState(str, Enum):
    PREPARED = "prepared"
    DISPATCHING = "dispatching"
    CONFIRMED_SUBMITTED = "confirmed_submitted"
    CONFIRMED_REJECTED = "confirmed_rejected"
    OUTCOME_UNKNOWN = "outcome_unknown"
    RECONCILED_SUBMITTED = "reconciled_submitted"
    RECONCILED_ABSENT = "reconciled_absent"
    HARD_STOPPED = "hard_stopped"


class ExchangeCommandOutcomeClass(str, Enum):
    PENDING = "pending"
    EXCHANGE_ACCEPTED = "exchange_accepted"
    AUTHORITATIVE_REJECTION = "authoritative_rejection"
    NETWORK_AMBIGUOUS = "network_ambiguous"
    INCOMPLETE_RESPONSE = "incomplete_response"
    RECONCILED_EXCHANGE_TRUTH = "reconciled_exchange_truth"
    RECONCILED_ABSENCE = "reconciled_absence"
    CONTRADICTORY_TRUTH = "contradictory_truth"


class ExchangeOrderLookupView(str, Enum):
    REGULAR_ORDER = "regular_order"
    CONDITIONAL_ALGO_ORDER = "conditional_algo_order"
    COMPLETE_OPEN_ORDERS = "complete_open_orders"


class ExchangeOrderLookupStatus(str, Enum):
    FOUND = "found"
    NOT_FOUND = "not_found"
    CANCEL_EFFECT_CONFIRMED = "cancel_effect_confirmed"


class ExchangeOrderLookupRequest(ExchangeCommandModel):
    """One durable command's required readonly exchange lookup."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    exchange_id: str = Field(min_length=1, max_length=128)
    gateway_symbol: str = Field(min_length=1, max_length=128)
    command_kind: str = Field(pattern="^(place_order|cancel_order)$")
    order_role: str = Field(pattern="^(ENTRY|SL|TP1|RUNNER_SL|FINAL_EXIT)$")
    order_type: str = Field(min_length=1, max_length=64)
    client_order_id: str = Field(min_length=1, max_length=36)
    target_exchange_order_id: Optional[str] = Field(default=None, max_length=192)


def required_exchange_order_lookup_view(
    request: ExchangeOrderLookupRequest,
) -> ExchangeOrderLookupView:
    """Return the one readonly lookup view required by a durable command."""

    if request.command_kind != "place_order":
        raise ValueError("client-id lookup only supports place_order commands")
    if request.exchange_id.lower() != "binance_usdm":
        return ExchangeOrderLookupView.REGULAR_ORDER

    order_role = request.order_role.upper()
    order_type = request.order_type.lower()
    if order_role in {"SL", "RUNNER_SL"} and order_type == "stop_market":
        return ExchangeOrderLookupView.CONDITIONAL_ALGO_ORDER
    if order_role in {"ENTRY", "TP1", "RUNNER_SL", "FINAL_EXIT"} and order_type != "stop_market":
        return ExchangeOrderLookupView.REGULAR_ORDER
    raise ValueError("unsupported Binance command role/type lookup combination")


class ExchangeOrderLookupResult(ExchangeCommandModel):
    """Typed readonly exchange evidence from the command's required view."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: ExchangeOrderLookupStatus
    lookup_view: ExchangeOrderLookupView
    identity_kind: str = Field(min_length=1, max_length=64)
    observed_at_ms: int = Field(ge=0)
    exchange_order_id: Optional[str] = Field(default=None, max_length=192)
    client_order_id: str = Field(min_length=1, max_length=36)
    gateway_symbol: str = Field(min_length=1, max_length=128)
    exchange_status: Optional[str] = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def _require_exchange_identity_when_found(self) -> "ExchangeOrderLookupResult":
        if (
            self.status is ExchangeOrderLookupStatus.FOUND
            and not self.exchange_order_id
        ):
            raise ValueError("found lookup requires exchange_order_id")
        return self


class TicketBoundExchangeCommand(ExchangeCommandModel):
    exchange_command_id: str = Field(min_length=1, max_length=192)
    protected_submit_attempt_id: str = Field(min_length=1, max_length=192)
    ticket_id: str = Field(min_length=1, max_length=192)
    operation_submit_command_id: str = Field(min_length=1, max_length=192)
    account_id: str = Field(min_length=1, max_length=128)
    strategy_group_id: str = Field(min_length=1, max_length=128)
    runtime_profile_id: str = Field(min_length=1, max_length=128)
    exchange_instrument_id: str = Field(min_length=1, max_length=192)
    exposure_episode_id: str = Field(min_length=1, max_length=192)
    exchange_id: str = Field(min_length=1, max_length=128)
    gateway_symbol: str = Field(min_length=1, max_length=128)
    symbol: str = Field(min_length=1, max_length=128)
    order_role: str = Field(pattern="^(ENTRY|SL|TP1|RUNNER_SL|FINAL_EXIT)$")
    side: str = Field(pattern="^(long|short)$")
    gateway_side: str = Field(min_length=1, max_length=32)
    local_order_id: str = Field(min_length=1, max_length=192)
    parent_order_id: Optional[str] = Field(default=None, max_length=192)
    client_order_id: str = Field(min_length=1, max_length=36)
    command_generation: int = Field(ge=1)
    request_fingerprint: str = Field(min_length=1, max_length=192)
    order_type: str = Field(min_length=1, max_length=64)
    execution_style: Optional[Literal["limit_gtc", "passive_limit_gtx"]] = None
    time_in_force: Optional[Literal["GTC", "GTX"]] = None
    post_only: bool = False
    market_fallback_allowed: Literal[False] = False
    amount: Decimal = Field(gt=Decimal("0"))
    price: Optional[Decimal] = Field(default=None, gt=Decimal("0"))
    stop_price: Optional[Decimal] = Field(default=None, gt=Decimal("0"))
    desired_leverage: Optional[int] = Field(default=None, ge=1, le=125)
    reduce_only: bool = False
    reduce_intent: str = Field(pattern="^(open_position|reduce_position)$")
    position_mode: str = Field(pattern="^(one_way|hedge)$")
    position_side: Optional[str] = Field(default=None, pattern="^(LONG|SHORT)$")
    position_bucket: str = Field(pattern="^(BOTH|LONG|SHORT)$")
    netting_domain_key: str = Field(min_length=1, max_length=640)
    command_kind: str = Field(pattern="^(place_order|cancel_order)$")
    command_source: str = Field(
        pattern=(
            "^(protected_submit|protection_recovery|runner_mutation|"
            "orphan_cleanup|exit_policy_runner|exit_policy_close|"
            "exit_policy_tp1_reprice)$"
        )
    )
    source_command_id: str = Field(min_length=1, max_length=192)
    target_exchange_order_id: Optional[str] = Field(default=None, max_length=192)
    authority_source_ref: str = Field(min_length=1, max_length=256)
    command_state: ExchangeCommandState
    outcome_class: ExchangeCommandOutcomeClass = ExchangeCommandOutcomeClass.PENDING
    exchange_order_id: Optional[str] = Field(default=None, max_length=192)
    exchange_error_code: Optional[str] = Field(default=None, max_length=128)
    exchange_error_message: Optional[str] = Field(default=None, max_length=1000)
    prepared_at_ms: int = Field(ge=0)
    dispatch_started_at_ms: Optional[int] = Field(default=None, ge=0)
    resolved_at_ms: Optional[int] = Field(default=None, ge=0)
    updated_at_ms: int = Field(ge=0)
    claim_owner: Optional[str] = Field(default=None, max_length=128)
    claim_token: Optional[str] = Field(default=None, max_length=192)
    claim_started_at_ms: Optional[int] = Field(default=None, ge=0)
    claim_expires_at_ms: Optional[int] = Field(default=None, ge=0)
    execution_attempt_count: int = Field(default=0, ge=0)
    last_reconciled_at_ms: Optional[int] = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _validate_resolution(self) -> "TicketBoundExchangeCommand":
        submitted_states = {
            ExchangeCommandState.CONFIRMED_SUBMITTED,
            ExchangeCommandState.RECONCILED_SUBMITTED,
        }
        if self.command_state in submitted_states and not self.exchange_order_id:
            raise ValueError("submitted command requires exchange_order_id")
        if self.command_state == ExchangeCommandState.CONFIRMED_REJECTED and (
            self.outcome_class
            != ExchangeCommandOutcomeClass.AUTHORITATIVE_REJECTION
        ):
            raise ValueError(
                "confirmed rejection requires authoritative rejection"
            )
        if self.position_mode == "one_way" and (
            self.position_side is not None or self.position_bucket != "BOTH"
        ):
            raise ValueError("one-way command must use BOTH without positionSide")
        if self.position_mode == "hedge" and (
            self.position_side not in {"LONG", "SHORT"}
            or self.position_bucket != self.position_side
        ):
            raise ValueError("hedge command requires matching positionSide bucket")
        if self.reduce_intent == "open_position" and self.order_role != "ENTRY":
            raise ValueError("only ENTRY may open position")
        if self.reduce_intent == "reduce_position" and self.order_role == "ENTRY":
            raise ValueError("ENTRY may not carry reduce intent")
        if self.desired_leverage is not None and self.order_role != "ENTRY":
            raise ValueError("only ENTRY may carry desired leverage")
        if self.command_kind == "place_order" and self.order_role == "TP1":
            validate_tp1_execution_contract(
                order_type=self.order_type,
                price=self.price,
                execution_style=self.execution_style,
                time_in_force=self.time_in_force,
                post_only=self.post_only,
                market_fallback_allowed=self.market_fallback_allowed,
            )
        return self


def validate_tp1_execution_contract(
    *,
    order_type: str,
    price: Decimal | None,
    execution_style: str | None,
    time_in_force: str | None,
    post_only: bool,
    market_fallback_allowed: bool,
) -> None:
    if str(order_type or "").lower() != "limit" or price is None:
        raise ValueError("tp1_requires_limit_price")
    if market_fallback_allowed:
        raise ValueError("tp1_market_fallback_forbidden")
    if execution_style == "limit_gtc" and (
        time_in_force != "GTC" or post_only
    ):
        raise ValueError("tp1_gtc_contract_invalid")
    if execution_style == "passive_limit_gtx" and (
        time_in_force != "GTX" or not post_only
    ):
        raise ValueError("tp1_post_only_requires_gtx")
    if execution_style is None:
        raise ValueError("tp1_execution_style_required")
    if execution_style not in {"limit_gtc", "passive_limit_gtx"}:
        raise ValueError("tp1_execution_style_invalid")


_ALLOWED_TRANSITIONS: dict[
    ExchangeCommandState,
    set[ExchangeCommandState],
] = {
    ExchangeCommandState.PREPARED: {
        ExchangeCommandState.DISPATCHING,
        ExchangeCommandState.RECONCILED_ABSENT,
    },
    ExchangeCommandState.DISPATCHING: {
        ExchangeCommandState.CONFIRMED_SUBMITTED,
        ExchangeCommandState.CONFIRMED_REJECTED,
        ExchangeCommandState.OUTCOME_UNKNOWN,
        ExchangeCommandState.HARD_STOPPED,
    },
    ExchangeCommandState.OUTCOME_UNKNOWN: {
        ExchangeCommandState.RECONCILED_SUBMITTED,
        ExchangeCommandState.RECONCILED_ABSENT,
        ExchangeCommandState.HARD_STOPPED,
    },
}


def command_transition_blockers(
    *,
    current: ExchangeCommandState,
    target: ExchangeCommandState,
    outcome_class: ExchangeCommandOutcomeClass,
) -> list[str]:
    """Return fail-closed blockers for a proposed command transition."""

    blockers: list[str] = []
    if target not in _ALLOWED_TRANSITIONS.get(current, set()):
        blockers.append("exchange_command_transition_not_allowed")

    required_outcomes = {
        ExchangeCommandState.CONFIRMED_SUBMITTED: {
            ExchangeCommandOutcomeClass.EXCHANGE_ACCEPTED,
        },
        ExchangeCommandState.CONFIRMED_REJECTED: {
            ExchangeCommandOutcomeClass.AUTHORITATIVE_REJECTION,
        },
        ExchangeCommandState.OUTCOME_UNKNOWN: {
            ExchangeCommandOutcomeClass.NETWORK_AMBIGUOUS,
            ExchangeCommandOutcomeClass.INCOMPLETE_RESPONSE,
        },
        ExchangeCommandState.RECONCILED_SUBMITTED: {
            ExchangeCommandOutcomeClass.RECONCILED_EXCHANGE_TRUTH,
        },
        ExchangeCommandState.RECONCILED_ABSENT: {
            ExchangeCommandOutcomeClass.RECONCILED_ABSENCE,
        },
        ExchangeCommandState.HARD_STOPPED: {
            ExchangeCommandOutcomeClass.CONTRADICTORY_TRUTH,
        },
    }
    accepted = required_outcomes.get(target)
    if accepted is not None and outcome_class not in accepted:
        if target == ExchangeCommandState.CONFIRMED_REJECTED:
            blockers.append(
                "confirmed_rejected_requires_authoritative_rejection"
            )
        else:
            blockers.append("exchange_command_outcome_class_mismatch")
    return blockers


def deterministic_client_order_id(
    ticket_id: str,
    operation_submit_command_id: str,
    order_role: str,
    command_generation: int,
) -> str:
    """Build a stable, venue-safe idempotency key of at most 36 characters."""

    if not ticket_id or not operation_submit_command_id or not order_role:
        raise ValueError("client order id identity fields must be non-empty")
    if command_generation < 1:
        raise ValueError("command_generation must be positive")
    identity = "|".join(
        (
            ticket_id,
            operation_submit_command_id,
            order_role.upper(),
            str(command_generation),
        )
    )
    return f"brc-{sha256(identity.encode('utf-8')).hexdigest()[:32]}"
