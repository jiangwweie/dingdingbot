"""Pure offline fill-path evidence; never an admission or lifecycle authority."""

from collections.abc import Mapping
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from typing import Literal

from pydantic import BaseModel, ConfigDict, JsonValue, ValidationError

from src.trading_kernel.domain.commands import (
    ExchangeCommand,
    ExchangeCommandKind,
    ExchangeCommandStatus,
    OrderCommandPayload,
)
from src.trading_kernel.domain.order_attribution import (
    AttributedTradeFill,
    OrderRole,
    attribution_digest,
)
from src.trading_kernel.domain.ticket import TradeTicket


class ReviewExecutionEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticket_id: str
    review_id: str | None
    status: Literal["COMPLETE", "EVIDENCE_INCOMPLETE"]
    missing: tuple[str, ...] = ()
    attribution_digest: str | None = None
    entry_fills: tuple[AttributedTradeFill, ...] = ()
    exit_fills: tuple[AttributedTradeFill, ...] = ()
    actual_entry_quantity: Decimal | None = None
    actual_entry_vwap: Decimal | None = None
    first_entry_fill_at_ms: int | None = None
    last_exit_fill_at_ms: int | None = None
    initial_stop_distance: Decimal | None = None


def build_review_execution_evidence(*, ticket: TradeTicket, review_id: str | None,
    review_ticket_id: str | None, metrics: Mapping[str, JsonValue],
    commands: tuple[ExchangeCommand, ...]) -> ReviewExecutionEvidence:
    """Use only exact attributed venue fills, never position observation times."""
    ticket_id = ticket.identity.ticket_id
    missing: list[str] = []
    if review_id is None:
        missing.append("REVIEW_MISSING")
    if review_ticket_id != ticket_id:
        missing.append("REVIEW_TICKET_IDENTITY")
    rows = metrics.get("order_attribution")
    fills: tuple[AttributedTradeFill, ...] = ()
    if not isinstance(rows, list) or not rows:
        missing.append("ATTRIBUTED_FILLS_MISSING")
    elif len(rows) > 1000:
        missing.append("ATTRIBUTED_FILLS_BOUND_EXCEEDED")
    else:
        try:
            with localcontext(Context(prec=38, rounding=ROUND_HALF_EVEN)):
                fills = tuple(AttributedTradeFill.model_validate(row) for row in rows)
        except (ValidationError, ValueError):
            missing.append("ATTRIBUTED_FILLS_INVALID")
    digest = metrics.get("order_attribution_digest")
    if fills:
        with localcontext(Context(prec=38, rounding=ROUND_HALF_EVEN)):
            if digest != attribution_digest(fills):
                missing.append("ATTRIBUTION_DIGEST_MISMATCH")
    by_id = {command.command_id: command for command in commands}
    seen: set[tuple[str, str]] = set()
    for fill in fills:
        key = (fill.exchange_order_id, fill.exchange_trade_id)
        if key in seen:
            missing.append("DUPLICATE_TRADE_IDENTITY")
        seen.add(key)
        command = by_id.get(fill.command_id)
        allowed_kinds = ({ExchangeCommandKind.ENTRY} if fill.role is OrderRole.ENTRY else
            {ExchangeCommandKind.INITIAL_STOP, ExchangeCommandKind.TAKE_PROFIT,
                ExchangeCommandKind.EXIT, ExchangeCommandKind.CONTROLLED_FLATTEN,
                ExchangeCommandKind.REPLACE_PROTECTION})
        if command is None or command.ticket_identity != ticket.identity or command.kind not in allowed_kinds or command.status not in {
            ExchangeCommandStatus.ACCEPTED,ExchangeCommandStatus.RECONCILED_ACCEPTED}:
            missing.append("FILL_COMMAND_IDENTITY")
        elif fill.occurred_at_ms < command.created_at_ms:
            missing.append("FILL_PRECEDES_COMMAND")
        elif isinstance(command.payload,OrderCommandPayload):
            entry_side="buy" if ticket.identity.netting_domain.position_side=="long" else "sell"
            expected_side=entry_side if fill.role is OrderRole.ENTRY else "sell" if entry_side=="buy" else "buy"
            if command.payload.side!=expected_side or command.payload.reduce_only!=(fill.role is OrderRole.EXIT):
                missing.append("FILL_COMMAND_SIDE")
    entries = tuple(sorted((fill for fill in fills if fill.role is OrderRole.ENTRY),
        key=lambda fill: (fill.occurred_at_ms, fill.exchange_order_id, fill.exchange_trade_id)))
    exits = tuple(sorted((fill for fill in fills if fill.role is OrderRole.EXIT),
        key=lambda fill: (fill.occurred_at_ms, fill.exchange_order_id, fill.exchange_trade_id)))
    if not entries:
        missing.append("ENTRY_FILLS_MISSING")
    if not exits:
        missing.append("EXIT_FILLS_MISSING")
    with localcontext(Context(prec=38, rounding=ROUND_HALF_EVEN)):
        qty = sum((fill.quantity for fill in entries), Decimal(0))
        closed = sum((fill.quantity for fill in exits), Decimal(0))
        if qty <= 0 or qty > ticket.quantity or qty != closed:
            missing.append("EXECUTED_QUANTITY_MISMATCH")
        declared = metrics.get("executed_entry_quantity", metrics.get("entry_quantity"))
        if declared is None:
            missing.append("REVIEW_EXECUTED_QUANTITY_MISSING")
        else:
            try:
                if not isinstance(declared,(str,int)) or isinstance(declared,bool) or Decimal(str(declared))!=qty:
                    missing.append("REVIEW_EXECUTED_QUANTITY_MISMATCH")
            except (ValueError,ArithmeticError):
                missing.append("REVIEW_EXECUTED_QUANTITY_INVALID")
        if entries and exits and min(fill.occurred_at_ms for fill in exits) < min(fill.occurred_at_ms for fill in entries):
            missing.append("EXIT_PRECEDES_ENTRY")
        if missing:
            return ReviewExecutionEvidence(ticket_id=ticket_id, review_id=review_id,
                status="EVIDENCE_INCOMPLETE", missing=tuple(sorted(set(missing))))
        vwap = sum((fill.quantity * fill.price for fill in entries), Decimal(0)) / qty
        distance = (vwap-ticket.initial_stop_price if ticket.identity.netting_domain.position_side=="long" else ticket.initial_stop_price-vwap)
        if distance <= 0:
            return ReviewExecutionEvidence(ticket_id=ticket_id, review_id=review_id,
                status="EVIDENCE_INCOMPLETE", missing=("INVALID_INITIAL_STOP_DISTANCE",))
    return ReviewExecutionEvidence(ticket_id=ticket_id, review_id=review_id, status="COMPLETE",
        attribution_digest=str(digest), entry_fills=entries, exit_fills=exits,
        actual_entry_quantity=qty, actual_entry_vwap=vwap,
        first_entry_fill_at_ms=entries[0].occurred_at_ms, last_exit_fill_at_ms=exits[-1].occurred_at_ms,
        initial_stop_distance=distance)
