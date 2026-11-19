"""Owner position intents preserve automation and never expand position risk."""

from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.trading_kernel.domain.aggregate import AggregateStatus, TradeAggregate
from src.trading_kernel.domain.owner_reduction import OwnerReductionFacts


class OwnerPositionPreview(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal[
        "protection_tighten", "manual_tp_set", "manual_tp_cancel", "position_close"
    ]
    ticket_id: str = Field(min_length=1)
    aggregate_version: int = Field(gt=0)
    management_revision: int = Field(gt=0)
    side: Literal["long", "short"]
    source_quantity: Decimal = Field(gt=0, allow_inf_nan=False)
    protection_order_id: str = Field(min_length=1)
    stop_price: Decimal = Field(gt=0, allow_inf_nan=False)
    source_tp_order_id: str | None
    source_tp_filled_quantity: Decimal = Field(ge=0, allow_inf_nan=False)
    price: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    quantity: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    created_at_ms: int = Field(gt=0)
    expires_at_ms: int = Field(gt=0)


def preview_position_operation(
    *,
    aggregate: TradeAggregate,
    facts: OwnerReductionFacts,
    kind: str,
    quantity_step: Decimal,
    price_tick: Decimal,
    minimum_quantity: Decimal,
    minimum_notional: Decimal,
    now_ms: int,
    price: Decimal | None = None,
    quantity: Decimal | None = None,
) -> OwnerPositionPreview:
    a, f = aggregate, facts
    if (
        a.status
        not in {AggregateStatus.POSITION_PROTECTED, AggregateStatus.RUNNER_PROTECTED}
        or a.management_mode.value != "AUTO"
        or f.management_mode.value != "AUTO"
        or f.ticket_id != a.identity.ticket_id
        or f.management_revision != a.management_revision
        or f.position_quantity != a.position_qty
        or f.tp_order_id != a.tp1_exchange_order_id
        or f.tp_filled_quantity != a.tp1_filled_qty
        or f.position_quantity <= 0
        or not f.observed_at_ms <= now_ms < f.valid_until_ms
        or f.unresolved_other_command
        or f.stop_triggered
        or f.reduction_state != "not_sent"
        or not f.protection_order_id
        or f.protection_order_id != a.active_stop_exchange_order_id
        or f.protected_quantity != a.position_qty
        or f.stop_price != a.active_stop_price
    ):
        raise ValueError("position_operation_source_unavailable")
    if any(
        not isinstance(x, Decimal) or not x.is_finite() or x <= 0
        for x in (quantity_step, price_tick, minimum_quantity, minimum_notional)
    ):
        raise ValueError("position_operation_rules_invalid")
    assert f.stop_price is not None
    long = a.identity.netting_domain.position_side == "long"
    if kind == "protection_tighten":
        if price is None or quantity is not None or not price.is_finite():
            raise ValueError("stop_price_required")
        price = (price / price_tick).to_integral_value(
            rounding=ROUND_FLOOR if long else ROUND_CEILING
        ) * price_tick
        if not (
            f.stop_price < price < f.current_price
            if long
            else f.current_price < price < f.stop_price
        ):
            raise ValueError("stop_must_tighten_and_not_cross")
    elif kind == "manual_tp_set":
        if (
            price is None
            or quantity is None
            or not price.is_finite()
            or not quantity.is_finite()
        ):
            raise ValueError("manual_tp_price_and_quantity_required")
        price = (price / price_tick).to_integral_value(
            rounding=ROUND_CEILING if long else ROUND_FLOOR
        ) * price_tick
        quantity = (quantity / quantity_step).to_integral_value(
            rounding=ROUND_FLOOR
        ) * quantity_step
        if (
            not (price > f.current_price if long else price < f.current_price)
            or quantity < minimum_quantity
            or quantity * price < minimum_notional
            or quantity > f.position_quantity
            or f.tp_state in {"partial", "unknown"}
        ):
            raise ValueError("manual_tp_unexecutable")
    elif kind == "manual_tp_cancel":
        if (
            price is not None
            or quantity is not None
            or a.manual_profit_plan is None
            or f.tp_order_id is None
            or f.tp_state not in {"open", "partial"}
        ):
            raise ValueError("manual_tp_not_cancellable")
    elif kind == "position_close":
        if price is not None or quantity is not None:
            raise ValueError("full_close_forbids_partial_terms")
    else:
        raise ValueError("unsupported_owner_operation")
    return OwnerPositionPreview.model_validate(
        {
            "kind": kind,
            "ticket_id": a.identity.ticket_id,
            "aggregate_version": a.version,
            "management_revision": a.management_revision,
            "side": a.identity.netting_domain.position_side,
            "source_quantity": a.position_qty,
            "protection_order_id": f.protection_order_id,
            "stop_price": f.stop_price,
            "source_tp_order_id": f.tp_order_id,
            "source_tp_filled_quantity": f.tp_filled_quantity,
            "price": price,
            "quantity": quantity,
            "created_at_ms": now_ms,
            "expires_at_ms": now_ms + 30000,
        }
    )
