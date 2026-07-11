"""Typed Action-Time execution pricing and one sizing/risk decision.

The producer boundary is the nested ``facts`` object persisted by the
production public-fact collector. Loose top-level aliases are intentionally not
accepted because they allowed unit fixtures to bypass the real PG shape.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


RISK_RESERVATION_BASIS = "entry_reference_stop_distance_v0"
NUMERIC_STORAGE_EPSILON = Decimal("0.000000000000001")


class ActionTimePricingReference(BaseModel):
    """Fresh executable-side pricing plus exchange quantity rules."""

    model_config = ConfigDict(frozen=True)

    side: Literal["long", "short"]
    entry_reference_price: Decimal = Field(gt=Decimal("0"))
    entry_reference_kind: Literal["best_ask", "best_bid"]
    mark_price: Decimal = Field(gt=Decimal("0"))
    bid_price: Decimal = Field(gt=Decimal("0"))
    ask_price: Decimal = Field(gt=Decimal("0"))
    qty_step: Decimal = Field(gt=Decimal("0"))
    min_notional: Decimal = Field(gt=Decimal("0"))
    source_fact_snapshot_id: str = Field(min_length=1)
    observed_at_ms: int = Field(gt=0)
    valid_until_ms: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_reference(self) -> "ActionTimePricingReference":
        decimal_values = (
            self.entry_reference_price,
            self.mark_price,
            self.bid_price,
            self.ask_price,
            self.qty_step,
            self.min_notional,
        )
        if not all(value.is_finite() for value in decimal_values):
            raise ValueError("pricing values must be finite")
        if self.ask_price < self.bid_price:
            raise ValueError("best ask must not be below best bid")
        expected_kind = "best_ask" if self.side == "long" else "best_bid"
        expected_price = self.ask_price if self.side == "long" else self.bid_price
        if self.entry_reference_kind != expected_kind:
            raise ValueError("entry reference kind does not match side")
        if self.entry_reference_price != expected_price:
            raise ValueError("entry reference price does not match side quote")
        if self.valid_until_ms <= self.observed_at_ms:
            raise ValueError("pricing validity must follow observation")
        return self

    def fact_values(self) -> dict[str, Any]:
        return {
            key: _decimal_text(value) if isinstance(value, Decimal) else value
            for key, value in self.model_dump().items()
        }


class TicketSizingRiskDecision(BaseModel):
    """One immutable quantity and stop-risk decision reused downstream."""

    model_config = ConfigDict(frozen=True)

    side: Literal["long", "short"]
    entry_reference_price: Decimal = Field(gt=Decimal("0"))
    stop_price: Decimal = Field(gt=Decimal("0"))
    target_notional: Decimal = Field(gt=Decimal("0"))
    raw_qty: Decimal = Field(gt=Decimal("0"))
    intended_qty: Decimal = Field(gt=Decimal("0"))
    qty_step: Decimal = Field(gt=Decimal("0"))
    min_notional: Decimal = Field(gt=Decimal("0"))
    rounded_notional: Decimal = Field(gt=Decimal("0"))
    risk_at_stop: Decimal = Field(gt=Decimal("0"))
    risk_reservation_basis: str = Field(min_length=1)
    pricing_source_fact_snapshot_id: str = Field(min_length=1)
    pricing_valid_until_ms: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_decision(self) -> "TicketSizingRiskDecision":
        decimal_values = (
            self.entry_reference_price,
            self.stop_price,
            self.target_notional,
            self.raw_qty,
            self.intended_qty,
            self.qty_step,
            self.min_notional,
            self.rounded_notional,
            self.risk_at_stop,
        )
        if not all(value.is_finite() for value in decimal_values):
            raise ValueError("sizing/risk values must be finite")
        if self.intended_qty % self.qty_step != 0:
            raise ValueError("intended quantity must align to quantity step")
        expected_raw_qty = self.target_notional / self.entry_reference_price
        if self.raw_qty != expected_raw_qty:
            raise ValueError("raw quantity does not match target notional")
        if self.intended_qty != _floor_to_step(expected_raw_qty, self.qty_step):
            raise ValueError("intended quantity does not match target notional")
        if self.rounded_notional != self.intended_qty * self.entry_reference_price:
            raise ValueError("rounded notional does not match quantity and price")
        if self.rounded_notional < self.min_notional:
            raise ValueError("rounded notional is below exchange minimum")
        if self.risk_at_stop != (
            abs(self.entry_reference_price - self.stop_price) * self.intended_qty
        ):
            raise ValueError("risk at stop does not match reserved decision")
        if self.side == "long" and self.stop_price >= self.entry_reference_price:
            raise ValueError("long stop must be below entry")
        if self.side == "short" and self.stop_price <= self.entry_reference_price:
            raise ValueError("short stop must be above entry")
        if self.risk_reservation_basis != RISK_RESERVATION_BASIS:
            raise ValueError("risk reservation basis is invalid")
        return self

    def reservation_values(self) -> dict[str, Any]:
        return {
            "entry_reference_price": self.entry_reference_price,
            "stop_price": self.stop_price,
            "intended_qty": self.intended_qty,
            "risk_at_stop": self.risk_at_stop,
            "risk_reservation_basis": self.risk_reservation_basis,
        }


class PricingReferenceResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    reference: ActionTimePricingReference | None = None
    blockers: tuple[str, ...] = ()


class SizingRiskDecisionResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    decision: TicketSizingRiskDecision | None = None
    blockers: tuple[str, ...] = ()


def materialize_action_time_pricing_reference(
    *,
    side: str,
    source_values: dict[str, Any],
    source_fact_snapshot_id: str,
    observed_at_ms: int,
    valid_until_ms: int,
    now_ms: int,
) -> PricingReferenceResult:
    normalized_side = str(side or "").strip().lower()
    blockers: list[str] = []
    if normalized_side not in {"long", "short"}:
        blockers.append("action_time_pricing_side_missing_or_invalid")

    facts = _as_dict(source_values.get("facts"))
    if not facts:
        blockers.append("action_time_public_facts_object_missing")
    if source_values.get("public_facts_ready") is not True:
        blockers.append("action_time_public_facts_not_ready")
    if source_values.get("mark_price_fresh") is not True:
        blockers.append("action_time_mark_price_not_fresh")
    if source_values.get("spread_ok") is not True:
        blockers.append("action_time_spread_not_acceptable")
    if source_values.get("qty_step_ok") is not True:
        blockers.append("action_time_qty_step_not_ready")
    if source_values.get("min_notional_ok") is not True:
        blockers.append("action_time_min_notional_not_ready")
    if not source_fact_snapshot_id:
        blockers.append("action_time_pricing_source_snapshot_missing")
    if observed_at_ms <= 0 or observed_at_ms > now_ms:
        blockers.append("action_time_pricing_observation_invalid")
    if valid_until_ms <= now_ms:
        blockers.append("action_time_pricing_source_stale")

    mark_price = _positive_decimal(facts.get("mark_price"))
    bid_price = _positive_decimal(facts.get("bid_price"))
    ask_price = _positive_decimal(facts.get("ask_price"))
    qty_step = _positive_decimal(facts.get("qty_step"))
    min_notional = _positive_decimal(facts.get("min_notional"))
    if mark_price is None:
        blockers.append("action_time_mark_price_invalid")
    if bid_price is None:
        blockers.append("action_time_bid_price_invalid")
    if ask_price is None:
        blockers.append("action_time_ask_price_invalid")
    if qty_step is None:
        blockers.append("action_time_qty_step_invalid")
    if min_notional is None:
        blockers.append("action_time_min_notional_invalid")
    if bid_price is not None and ask_price is not None and ask_price < bid_price:
        blockers.append("action_time_best_quote_crossed")

    reference_kind = "best_ask" if normalized_side == "long" else "best_bid"
    entry_reference_price = (
        ask_price if normalized_side == "long" else bid_price
    )
    if entry_reference_price is None:
        blockers.append(f"action_time_entry_reference_missing:{reference_kind}")
    blockers = _dedupe(blockers)
    if blockers:
        return PricingReferenceResult(blockers=tuple(blockers))

    assert mark_price is not None
    assert bid_price is not None
    assert ask_price is not None
    assert qty_step is not None
    assert min_notional is not None
    assert entry_reference_price is not None
    try:
        reference = ActionTimePricingReference(
            side=normalized_side,
            entry_reference_price=entry_reference_price,
            entry_reference_kind=reference_kind,
            mark_price=mark_price,
            bid_price=bid_price,
            ask_price=ask_price,
            qty_step=qty_step,
            min_notional=min_notional,
            source_fact_snapshot_id=source_fact_snapshot_id,
            observed_at_ms=observed_at_ms,
            valid_until_ms=valid_until_ms,
        )
    except ValueError as exc:
        return PricingReferenceResult(
            blockers=(f"action_time_pricing_reference_invalid:{exc}",)
        )
    return PricingReferenceResult(reference=reference)


def materialize_ticket_sizing_risk_decision(
    *,
    pricing_reference: ActionTimePricingReference,
    target_notional: Decimal | str | int,
    stop_price: Decimal | str | int,
) -> SizingRiskDecisionResult:
    blockers: list[str] = []
    target = _positive_decimal(target_notional)
    stop = _positive_decimal(stop_price)
    if target is None:
        blockers.append("budget_reservation_target_notional_invalid")
    if stop is None:
        blockers.append("risk_reservation_stop_price_missing")

    entry = pricing_reference.entry_reference_price
    raw_qty = target / entry if target is not None else Decimal("0")
    intended_qty = _floor_to_step(raw_qty, pricing_reference.qty_step)
    rounded_notional = intended_qty * entry
    if intended_qty <= 0:
        blockers.append("risk_reservation_intended_qty_invalid")
    if intended_qty > 0 and rounded_notional < pricing_reference.min_notional:
        blockers.append("risk_reservation_rounded_notional_below_exchange_minimum")
    if stop is not None:
        if pricing_reference.side == "long" and stop >= entry:
            blockers.append("risk_reservation_stop_side_not_protective")
        if pricing_reference.side == "short" and stop <= entry:
            blockers.append("risk_reservation_stop_side_not_protective")
    risk_at_stop = (
        abs(entry - stop) * intended_qty
        if stop is not None and intended_qty > 0
        else Decimal("0")
    )
    if risk_at_stop <= 0:
        blockers.append("risk_at_stop_invalid")
    blockers = _dedupe(blockers)
    if blockers:
        return SizingRiskDecisionResult(blockers=tuple(blockers))

    assert target is not None
    assert stop is not None
    try:
        decision = TicketSizingRiskDecision(
            side=pricing_reference.side,
            entry_reference_price=entry,
            stop_price=stop,
            target_notional=target,
            raw_qty=raw_qty,
            intended_qty=intended_qty,
            qty_step=pricing_reference.qty_step,
            min_notional=pricing_reference.min_notional,
            rounded_notional=rounded_notional,
            risk_at_stop=risk_at_stop,
            risk_reservation_basis=RISK_RESERVATION_BASIS,
            pricing_source_fact_snapshot_id=(
                pricing_reference.source_fact_snapshot_id
            ),
            pricing_valid_until_ms=pricing_reference.valid_until_ms,
        )
    except ValueError as exc:
        return SizingRiskDecisionResult(
            blockers=(f"ticket_sizing_risk_decision_invalid:{exc}",)
        )
    return SizingRiskDecisionResult(decision=decision)


def pricing_reference_from_action_time_fact_values(
    fact_values: dict[str, Any],
) -> PricingReferenceResult:
    payload = _as_dict(fact_values.get("execution_pricing"))
    if not payload:
        return PricingReferenceResult(
            blockers=("action_time_execution_pricing_missing",)
        )
    try:
        return PricingReferenceResult(
            reference=ActionTimePricingReference.model_validate(payload)
        )
    except ValueError as exc:
        return PricingReferenceResult(
            blockers=(f"action_time_execution_pricing_invalid:{exc}",)
        )


def sizing_risk_decision_from_budget(
    *,
    budget: dict[str, Any],
    pricing_reference: ActionTimePricingReference,
) -> SizingRiskDecisionResult:
    lineage_blockers: list[str] = []
    if str(budget.get("side") or "").strip().lower() != pricing_reference.side:
        lineage_blockers.append("risk_reservation_side_pricing_mismatch")
    if not _decimal_equal(
        _decimal(budget.get("entry_reference_price")),
        pricing_reference.entry_reference_price,
    ):
        lineage_blockers.append("risk_reservation_entry_reference_mismatch")
    stored_qty = _decimal(budget.get("intended_qty"))
    canonical_qty = _nearest_step(stored_qty, pricing_reference.qty_step)
    if not _decimal_equal(stored_qty, canonical_qty):
        canonical_qty = stored_qty
    stored_entry = _decimal(budget.get("entry_reference_price"))
    stored_stop = _decimal(budget.get("stop_price"))
    stored_target = _decimal(budget.get("target_notional"))
    if stored_target <= 0:
        lineage_blockers.append("budget_reservation_target_notional_invalid")
    if stored_target > 0 and stored_entry > 0:
        expected_qty = _floor_to_step(
            stored_target / stored_entry,
            pricing_reference.qty_step,
        )
        if not _decimal_equal(canonical_qty, expected_qty):
            lineage_blockers.append(
                "risk_reservation_intended_qty_target_notional_mismatch"
            )
    if (
        canonical_qty > 0
        and stored_entry > 0
        and canonical_qty * stored_entry < pricing_reference.min_notional
    ):
        lineage_blockers.append(
            "risk_reservation_rounded_notional_below_exchange_minimum"
        )
    expected_risk = abs(stored_entry - stored_stop) * canonical_qty
    stored_risk = _decimal(budget.get("risk_at_stop"))
    canonical_risk = (
        expected_risk
        if _decimal_equal(stored_risk, expected_risk)
        else stored_risk
    )
    payload = {
        "side": budget.get("side"),
        "entry_reference_price": budget.get("entry_reference_price"),
        "stop_price": budget.get("stop_price"),
        "target_notional": stored_target,
        "raw_qty": (
            _decimal(budget.get("target_notional"))
            / _decimal(budget.get("entry_reference_price"))
            if _decimal(budget.get("target_notional")) > 0
            and _decimal(budget.get("entry_reference_price")) > 0
            else Decimal("0")
        ),
        "intended_qty": canonical_qty,
        "qty_step": pricing_reference.qty_step,
        "min_notional": pricing_reference.min_notional,
        "rounded_notional": (
            canonical_qty * stored_entry
        ),
        "risk_at_stop": canonical_risk,
        "risk_reservation_basis": budget.get("risk_reservation_basis"),
        "pricing_source_fact_snapshot_id": (
            pricing_reference.source_fact_snapshot_id
        ),
        "pricing_valid_until_ms": pricing_reference.valid_until_ms,
    }
    try:
        decision = TicketSizingRiskDecision.model_validate(payload)
    except ValueError as exc:
        blockers = budget_stop_risk_blockers(budget)
        return SizingRiskDecisionResult(
            blockers=tuple(
                _dedupe(lineage_blockers + blockers)
                or [f"ticket_sizing_risk_reservation_invalid:{exc}"]
            )
        )
    if lineage_blockers:
        return SizingRiskDecisionResult(blockers=tuple(_dedupe(lineage_blockers)))
    return SizingRiskDecisionResult(decision=decision)


def budget_stop_risk_blockers(budget: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    side = str(budget.get("side") or "").strip().lower()
    entry = _positive_decimal(budget.get("entry_reference_price"))
    stop = _positive_decimal(budget.get("stop_price"))
    qty = _positive_decimal(budget.get("intended_qty"))
    risk = _positive_decimal(budget.get("risk_at_stop"))
    if entry is None:
        blockers.append("risk_reservation_entry_reference_price_missing")
    if stop is None:
        blockers.append("risk_reservation_stop_price_missing")
    if qty is None:
        blockers.append("risk_reservation_intended_qty_invalid")
    if risk is None:
        blockers.append("risk_at_stop_invalid")
    if str(budget.get("risk_reservation_basis") or "") != RISK_RESERVATION_BASIS:
        blockers.append("risk_reservation_basis_missing_or_invalid")
    if entry is not None and stop is not None:
        if side == "long" and stop >= entry:
            blockers.append("risk_reservation_stop_side_not_protective")
        elif side == "short" and stop <= entry:
            blockers.append("risk_reservation_stop_side_not_protective")
        elif side not in {"long", "short"}:
            blockers.append("risk_reservation_side_missing_or_invalid")
    if entry is not None and stop is not None and qty is not None and risk is not None:
        expected_risk = abs(entry - stop) * qty
        if not _decimal_equal(risk, expected_risk):
            blockers.append("risk_reservation_risk_at_stop_mismatch")
    return _dedupe(blockers)


def _floor_to_step(value: Decimal, step: Decimal) -> Decimal:
    if value <= 0 or step <= 0:
        return Decimal("0")
    return (value // step) * step


def _nearest_step(value: Decimal, step: Decimal) -> Decimal:
    if value <= 0 or step <= 0:
        return value
    units = (value / step).to_integral_value(rounding=ROUND_HALF_UP)
    return units * step


def _decimal_equal(left: Decimal, right: Decimal) -> bool:
    return abs(left - right) <= NUMERIC_STORAGE_EPSILON


def _positive_decimal(value: Any) -> Decimal | None:
    parsed = _decimal_or_none(value)
    if parsed is None or not parsed.is_finite() or parsed <= 0:
        return None
    return parsed


def _decimal(value: Any) -> Decimal:
    parsed = _decimal_or_none(value)
    return parsed if parsed is not None else Decimal("0")


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _decimal_text(value: Decimal) -> str:
    return format(value, "f")


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
