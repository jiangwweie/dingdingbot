"""Pure evidence classification for permanent per-Ticket App handover.

Not a runtime permission switch: callers must persist the decision atomically
with commands and projections, and supply complete scoped venue evidence.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ManagementMode(StrEnum):
    AUTO = "AUTO"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    MANUAL = "MANUAL"


class ManagementDecision(StrEnum):
    SYSTEM = "system"
    NATURAL = "natural"
    EXTERNAL = "external"
    UNRESOLVED = "unresolved"
    OUT_OF_SCOPE = "out_of_scope"


class OrderAction(StrEnum):
    NEW = "new"
    AMENDMENT = "amendment"
    CANCEL = "cancel"
    TRADE = "trade"
    EXPIRED = "expired"
    TRIGGERED = "triggered"
    REJECTED = "rejected"
    STATUS = "status"
    MISSING = "missing"


class OrderTerms(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    venue_id: str
    account_id: str
    exchange_instrument_id: str
    position_side: Literal["long", "short"]
    order_namespace: Literal["regular", "conditional"]
    exchange_order_id: str
    client_order_id: str | None
    side: Literal["buy", "sell"]
    order_type: Literal[
        "LIMIT",
        "MARKET",
        "STOP",
        "STOP_MARKET",
        "TAKE_PROFIT",
        "TAKE_PROFIT_MARKET",
        "TRAILING_STOP_MARKET",
    ]
    quantity: Decimal | None
    price: Decimal | None
    trigger_price: Decimal | None
    close_position: bool
    reduce_only: bool
    time_in_force: str
    working_type: Literal["MARK_PRICE", "CONTRACT_PRICE"] | None
    price_protect: bool
    activation_price: Decimal | None
    callback_rate: Decimal | None
    price_match: str
    self_trade_prevention_mode: str
    good_till_date_ms: int = Field(ge=0)

    @field_validator(
        "venue_id",
        "account_id",
        "exchange_instrument_id",
        "exchange_order_id",
        "time_in_force",
        "price_match",
        "self_trade_prevention_mode",
    )
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("identity and order enums must be nonblank")
        return value

    @field_validator(
        "quantity",
        "price",
        "trigger_price",
        "activation_price",
        "callback_rate",
        mode="before",
    )
    @classmethod
    def finite_positive(cls, value: object) -> Decimal | None:
        if value is None:
            return None
        if isinstance(value, (bool, float)):
            raise TypeError("financial values require exact decimals")
        d = Decimal(str(value))
        if not d.is_finite() or d <= 0:
            raise ValueError("order terms must be finite and positive")
        return d

    @model_validator(mode="after")
    def shape(self) -> OrderTerms:
        if self.close_position:
            if (
                self.quantity is not None
                or self.reduce_only
                or self.order_type not in {"STOP_MARKET", "TAKE_PROFIT_MARKET"}
            ):
                raise ValueError(
                    "close-all requires market trigger without fixed quantity/reduce-only"
                )
        elif self.quantity is None:
            raise ValueError("fixed-quantity order requires quantity")
        if (
            self.order_type in {"LIMIT", "STOP", "TAKE_PROFIT"}
            and self.price is None
            and self.price_match == "NONE"
        ):
            raise ValueError("limit order requires price or price-match mode")
        if (
            self.order_type
            in {"STOP", "STOP_MARKET", "TAKE_PROFIT", "TAKE_PROFIT_MARKET"}
            and self.trigger_price is None
        ):
            raise ValueError("conditional order requires trigger price")
        if self.order_type == "TRAILING_STOP_MARKET" and self.callback_rate is None:
            raise ValueError("trailing stop requires callback rate")
        return self

    @property
    def identity(self) -> tuple[str, ...]:
        return (
            self.venue_id,
            self.account_id,
            self.exchange_instrument_id,
            self.position_side,
            self.order_namespace,
            self.exchange_order_id,
        )

    @property
    def reduces_position(self) -> bool:
        # Hedge-mode closing SELL LONG / BUY SHORT need not have reduceOnly=true.
        return self.side == ("sell" if self.position_side == "long" else "buy")

    def terms_digest(self) -> str:
        data = self.model_dump(mode="python")
        for k, v in data.items():
            if isinstance(v, Decimal):
                data[k] = format(v.normalize(), "f")
        return (
            "sha256:"
            + hashlib.sha256(
                json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
        )


class OrderEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    evidence_id: str = Field(min_length=1)
    terms: OrderTerms
    action: OrderAction
    exchange_event_at_ms: int = Field(gt=0)
    received_at_ms: int = Field(gt=0)
    created_at_ms: int | None = Field(default=None, gt=0)
    source_event_at_ms: int | None = Field(default=None, gt=0)
    executed_quantity: Decimal = Field(ge=0, allow_inf_nan=False)
    coverage_complete: bool
    known_command_outcome_pending: bool
    before_terms: OrderTerms | None = None

    @model_validator(mode="after")
    def shape(self) -> OrderEvidence:
        if (
            self.created_at_ms is not None
            and self.exchange_event_at_ms < self.created_at_ms
        ):
            raise ValueError("order update precedes creation")
        if (
            self.terms.quantity is not None
            and self.executed_quantity > self.terms.quantity
        ):
            raise ValueError("execution exceeds fixed order quantity")
        if (
            self.before_terms is not None
            and self.before_terms.identity != self.terms.identity
        ):
            raise ValueError("amendment before/after identity differs")
        if self.action is OrderAction.TRADE and self.executed_quantity <= 0:
            raise ValueError("trade requires execution")
        return self


class SystemOrderIntent(BaseModel):
    """Must originate from durable Command + confirmed venue result, not ID prefix."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    command_id: str = Field(min_length=1)
    action: Literal[OrderAction.NEW, OrderAction.AMENDMENT, OrderAction.CANCEL]
    terms: OrderTerms
    exchange_event_at_ms: int = Field(gt=0)


class ClassifiedOrderEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    decision: ManagementDecision
    reason: str


def classify_order_evidence(
    evidence: OrderEvidence, *, system_intents: tuple[SystemOrderIntent, ...]
) -> ClassifiedOrderEvidence:
    def result(decision: ManagementDecision, reason: str) -> ClassifiedOrderEvidence:
        return ClassifiedOrderEvidence(decision=decision, reason=reason)

    if not evidence.coverage_complete or evidence.known_command_outcome_pending:
        return result(
            ManagementDecision.UNRESOLVED, "order_history_incomplete_or_command_unknown"
        )
    matching = tuple(
        i for i in system_intents if i.terms.identity == evidence.terms.identity
    )
    exact = tuple(i for i in matching if i.terms == evidence.terms)
    if any(
        i.action == evidence.action
        and i.exchange_event_at_ms == evidence.exchange_event_at_ms
        for i in exact
    ):
        return result(ManagementDecision.SYSTEM, "exact_durable_command_result")
    if evidence.action is OrderAction.MISSING:
        return result(
            ManagementDecision.UNRESOLVED, "order_absence_is_not_cancellation"
        )
    if evidence.action in {
        OrderAction.EXPIRED,
        OrderAction.TRIGGERED,
        OrderAction.REJECTED,
        OrderAction.STATUS,
    }:
        return result(
            ManagementDecision.NATURAL if exact else ManagementDecision.UNRESOLVED,
            "venue_status_change" if exact else "unattributed_status_change",
        )
    if evidence.action is OrderAction.TRADE and exact:
        return result(ManagementDecision.NATURAL, "known_order_execution")
    if not evidence.terms.reduces_position:
        return result(ManagementDecision.OUT_OF_SCOPE, "external_exposure_increase")
    if evidence.action is OrderAction.AMENDMENT:
        if evidence.before_terms is None or evidence.before_terms == evidence.terms:
            return result(ManagementDecision.UNRESOLVED, "amendment_terms_unproven")
        return result(ManagementDecision.EXTERNAL, "external_order_amendment")
    if evidence.action is OrderAction.CANCEL and matching:
        return result(ManagementDecision.EXTERNAL, "external_order_cancel")
    if matching and evidence.action is OrderAction.NEW:
        return result(
            ManagementDecision.UNRESOLVED, "known_order_creation_time_or_terms_drift"
        )
    if evidence.terms.client_order_id and evidence.terms.client_order_id.startswith(
        "brc-"
    ):
        return result(
            ManagementDecision.UNRESOLVED, "kernel_order_not_matched_to_command"
        )
    return result(
        ManagementDecision.EXTERNAL, "external_order_" + evidence.action.value
    )


class TradeManagement(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    ticket_id: str = Field(min_length=1)
    mode: ManagementMode = ManagementMode.AUTO
    revision: int = Field(default=1, gt=0)
    reason: str | None = None
    takeover_evidence_id: str | None = None
    takeover_detected_at_ms: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def shape(self) -> TradeManagement:
        if self.mode is ManagementMode.MANUAL:
            if (
                not self.takeover_evidence_id
                or self.takeover_detected_at_ms is None
                or not self.reason
            ):
                raise ValueError(
                    "manual state requires exact evidence and detection time"
                )
        elif (
            self.takeover_evidence_id is not None
            or self.takeover_detected_at_ms is not None
        ):
            raise ValueError("takeover evidence belongs only to permanent manual state")
        if self.mode is ManagementMode.REVIEW_REQUIRED and not self.reason:
            raise ValueError("review needs reason")
        return self

    @property
    def permits_automatic_mutation(self) -> bool:
        return self.mode is ManagementMode.AUTO


def transition_management(
    state: TradeManagement,
    evidence: OrderEvidence,
    *,
    system_intents: tuple[SystemOrderIntent, ...],
    initial_protection_confirmed: bool,
) -> TradeManagement:
    if state.mode is ManagementMode.MANUAL:
        return state
    classification = classify_order_evidence(evidence, system_intents=system_intents)
    if classification.decision in {
        ManagementDecision.SYSTEM,
        ManagementDecision.NATURAL,
    }:
        return state
    external = classification.decision is ManagementDecision.EXTERNAL
    mode = (
        ManagementMode.MANUAL
        if external and initial_protection_confirmed
        else ManagementMode.REVIEW_REQUIRED
    )
    reason = (
        "intervention_before_initial_protection"
        if external and not initial_protection_confirmed
        else classification.reason
    )
    if mode == state.mode and reason == state.reason:
        return state
    return TradeManagement(
        ticket_id=state.ticket_id,
        mode=mode,
        revision=state.revision + 1,
        reason=reason,
        takeover_evidence_id=evidence.evidence_id
        if mode is ManagementMode.MANUAL
        else None,
        takeover_detected_at_ms=evidence.received_at_ms
        if mode is ManagementMode.MANUAL
        else None,
    )
