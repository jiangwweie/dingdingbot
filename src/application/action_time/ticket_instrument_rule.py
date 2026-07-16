"""Resolve exact Ticket market rules without loading a venue-wide market cache."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TicketInstrumentRuleError(ValueError):
    """Raised when neither fresh exchange truth nor PG has usable rules."""


class TicketInstrumentRuleSnapshot(BaseModel):
    """Typed rule snapshot used only by one immutable Ticket instrument."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    exchange_instrument_id: str = Field(min_length=1)
    exchange_id: str = Field(min_length=1)
    exchange_market_id: str = Field(min_length=1)
    price_tick: Decimal = Field(gt=0)
    quantity_step: Decimal = Field(gt=0)
    min_notional: Decimal | None = Field(default=None, gt=0)
    source: str = Field(min_length=1)


def resolve_ticket_instrument_rule(
    *,
    instrument: dict[str, Any],
    exchange_snapshot: dict[str, Any] | None = None,
) -> TicketInstrumentRuleSnapshot:
    """Prefer Ticket-scoped exchange truth, with current PG columns as fallback."""

    instrument_id = str(instrument.get("exchange_instrument_id") or "").strip()
    exchange_id = str(instrument.get("exchange_id") or "").strip()
    exchange_symbol = str(instrument.get("exchange_symbol") or "").strip()
    if not instrument_id or not exchange_id or not exchange_symbol:
        raise TicketInstrumentRuleError("instrument_identity_incomplete")

    snapshot = dict(exchange_snapshot or {})
    market_rule = snapshot.get("market_rule")
    if isinstance(market_rule, dict) and market_rule:
        snapshot_instrument_id = str(
            snapshot.get("exchange_instrument_id") or ""
        ).strip()
        rule_instrument_id = str(
            market_rule.get("exchange_instrument_id") or snapshot_instrument_id
        ).strip()
        rule_exchange_id = str(
            market_rule.get("exchange_id") or snapshot.get("exchange_id") or ""
        ).strip()
        if (
            snapshot_instrument_id != instrument_id
            or rule_instrument_id != instrument_id
        ):
            raise TicketInstrumentRuleError("instrument_identity_mismatch")
        if rule_exchange_id != exchange_id:
            raise TicketInstrumentRuleError("exchange_identity_mismatch")
        return _validated_snapshot(
            exchange_instrument_id=instrument_id,
            exchange_id=exchange_id,
            exchange_market_id=str(
                market_rule.get("exchange_market_id") or ""
            ).strip(),
            price_tick=market_rule.get("price_tick"),
            quantity_step=market_rule.get("quantity_step"),
            min_notional=market_rule.get("min_notional"),
            source=str(market_rule.get("source") or "").strip(),
        )

    return _validated_snapshot(
        exchange_instrument_id=instrument_id,
        exchange_id=exchange_id,
        exchange_market_id=exchange_symbol,
        price_tick=instrument.get("price_tick"),
        quantity_step=instrument.get("quantity_step"),
        min_notional=instrument.get("min_notional"),
        source="pg_exchange_instrument_current",
    )


def _validated_snapshot(
    *,
    exchange_instrument_id: str,
    exchange_id: str,
    exchange_market_id: str,
    price_tick: Any,
    quantity_step: Any,
    min_notional: Any,
    source: str,
) -> TicketInstrumentRuleSnapshot:
    if not exchange_market_id:
        raise TicketInstrumentRuleError("exchange_market_id_missing")
    if not source:
        raise TicketInstrumentRuleError("source_missing")
    tick = _positive_decimal(price_tick, "price_tick_invalid")
    step = _positive_decimal(quantity_step, "quantity_step_invalid")
    minimum = (
        None
        if min_notional in (None, "")
        else _positive_decimal(min_notional, "min_notional_invalid")
    )
    return TicketInstrumentRuleSnapshot(
        exchange_instrument_id=exchange_instrument_id,
        exchange_id=exchange_id,
        exchange_market_id=exchange_market_id,
        price_tick=tick,
        quantity_step=step,
        min_notional=minimum,
        source=source,
    )


def _positive_decimal(value: Any, blocker: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise TicketInstrumentRuleError(blocker) from exc
    if not result.is_finite() or result <= 0:
        raise TicketInstrumentRuleError(blocker)
    return result
