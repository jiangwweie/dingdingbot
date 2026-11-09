"""Select meaningful transitions and freeze facts after all reductions in a UoW."""

from decimal import Decimal
from typing import Literal

from src.trading_kernel.application.notice_templates import format_number
from src.trading_kernel.domain import events as ev
from src.trading_kernel.domain.aggregate import AggregateStatus, TradeAggregate
from src.trading_kernel.domain.instrument_identity import (
    parse_binance_usdm_instrument_id,
)
from src.trading_kernel.domain.notices import NoticeKind, NoticeSnapshot, StopView
from src.trading_kernel.domain.position import PositionSnapshot, VenueOrderSnapshot
from src.trading_kernel.domain.trade_management import (
    ManagementMode,
    OrderAction,
    OrderEvidence,
)

# Registry/Detector semantics, never an activation or routing authority.
STRATEGY_LABELS = {
    "CPM": "趋势回调收复",
    "MPG": "领涨动量突破",
    "MI": "相对强势脉冲",
    "BRF2": "反弹衰竭做空",
    "SOR-1H": "小时开盘区间突破",
}


def build_notices(
    before: TradeAggregate | None,
    final: TradeAggregate,
    events: tuple[ev.TradeEvent, ...],
    position: PositionSnapshot | None,
    order_evidence: tuple[OrderEvidence, ...] = (),
) -> tuple[NoticeSnapshot, ...]:
    if not events and not order_evidence:
        return ()
    source_event_id = events[-1].event_id if events else order_evidence[-1].evidence_id
    source_at_ms = (
        events[-1].occurred_at_ms if events else order_evidence[-1].exchange_event_at_ms
    )
    kinds: list[NoticeKind] = []
    takeover = any(isinstance(e, ev.ManualTakeoverConfirmed) for e in events)
    if takeover:
        kinds.append(NoticeKind.TAKEOVER)
    flat = final.position_qty == 0 and (
        before is not None
        and before.position_qty > 0
        or any(
            isinstance(e, (ev.PositionFlatConfirmed, ev.ExternalFlatDetected))
            for e in events
        )
    )
    manual = final.management_mode is ManagementMode.MANUAL
    known_manual = (
        manual
        and final.management_observed_at_ms is not None
        and (
            final.manual_takeover_at_ms is not None
            and final.management_observed_at_ms >= final.manual_takeover_at_ms
        )
    )
    # A takeover alone does not verify the post-App position or its orders.
    residual = (
        len(final.management_orders)
        if known_manual
        else (
            sum(
                value is not None
                for value in (
                    final.active_stop_exchange_order_id,
                    final.tp1_exchange_order_id,
                    final.pending_cancel_exchange_order_id,
                )
            )
            if final.management_mode is ManagementMode.AUTO
            else None
        )
    )
    if flat:
        kinds.append(
            NoticeKind.RESIDUAL
            if residual is None or residual > 0
            else NoticeKind.CLOSED
        )
    elif (
        before is not None
        and before.status
        in {
            AggregateStatus.MANUAL_FLAT_PENDING_ORDERS,
            AggregateStatus.RECONCILIATION_PENDING,
            AggregateStatus.CANCEL_REJECTED,
            AggregateStatus.CANCEL_OUTCOME_UNKNOWN,
        }
        and final.status is AggregateStatus.SETTLEMENT_PENDING
    ):
        kinds.append(NoticeKind.CLOSED)
        residual = 0
    if final.management_mode is ManagementMode.REVIEW_REQUIRED:
        if (
            before is None
            or before.management_mode is not ManagementMode.REVIEW_REQUIRED
            or before.management_reason != final.management_reason
        ):
            kinds.append(NoticeKind.REVIEW)
    elif any(isinstance(e, ev.ManagementReviewCleared) for e in events):
        kinds.append(NoticeKind.REVIEW_CLEARED)
    if not flat and not takeover:
        if (
            any(
                isinstance(e, ev.PostFillStressAssessed) and e.status == "passed"
                for e in events
            )
            and final.management_mode is ManagementMode.AUTO
        ):
            kinds.append(NoticeKind.OPENED)
        if any(isinstance(e, ev.TakeProfitFilled) for e in events):
            kinds.append(NoticeKind.TP1)
        if manual and before is not None and known_manual:
            if final.manual_risk_reason is not None and (
                final.manual_risk_reason != before.manual_risk_reason
                or final.protected_qty < before.protected_qty
                and final.position_qty >= before.position_qty
            ):
                kinds.append(NoticeKind.RISK)
            elif (
                final.manual_risk_reason is None
                and before.manual_risk_reason is not None
            ):
                kinds.append(NoticeKind.RECOVERED)
            elif (
                final.manual_risk_at_stop is not None
                and before.manual_risk_at_stop is not None
                and final.manual_risk_at_stop > before.manual_risk_at_stop
            ):
                kinds.append(NoticeKind.RISK)
        if any(
            isinstance(
                e,
                (
                    ev.EntryOutcomeUnknown,
                    ev.EntryPartiallyFilled,
                    ev.InitialStopRejected,
                    ev.InitialStopOutcomeUnknown,
                    ev.ProtectionReplacementRejected,
                    ev.ProtectionReplacementOutcomeUnknown,
                    ev.ControlledFlattenRejected,
                    ev.ControlledFlattenOutcomeUnknown,
                    ev.ExitRejected,
                    ev.ExitOutcomeUnknown,
                ),
            )
            for e in events
        ):
            kinds.append(NoticeKind.RISK)
    manual_fills = tuple(
        item
        for item in order_evidence
        if manual
        and known_manual
        and item.coverage_complete
        and item.action is OrderAction.TRADE
        and item.terms.reduces_position
        and (
            item.terms.exchange_order_id == final.tp1_exchange_order_id
            or item.terms.order_type in {"STOP", "STOP_MARKET"}
        )
        and final.management_observed_at_ms is not None
        and final.management_observed_at_ms >= item.received_at_ms
    )
    if manual_fills and not flat and not takeover:
        kinds.append(NoticeKind.MANUAL_FILL)
    if not kinds:
        return ()
    quantity = final.position_qty if not manual or known_manual else None
    stops: list[StopView] = []
    protected: Decimal | None = final.protected_qty
    protection: Literal["full", "partial", "none", "unknown"] = (
        "full"
        if quantity is not None and final.protected_qty >= quantity > 0
        else "partial"
        if final.protected_qty > 0
        else "none"
    )
    facts_at: int | None = source_at_ms
    if manual:
        facts_at = final.management_observed_at_ms
        if not known_manual:
            protection, protected = "unknown", None
        else:
            for raw in final.management_orders:
                order = VenueOrderSnapshot.model_validate(raw)
                terms = order.terms
                if (
                    terms is not None
                    and terms.reduces_position
                    and terms.order_type in {"STOP_MARKET", "STOP"}
                    and terms.trigger_price is not None
                    and order.remaining_quantity != 0
                ):
                    stops.append(
                        StopView(
                            price=terms.trigger_price,
                            quantity=final.position_qty
                            if terms.close_position
                            else order.remaining_quantity
                            or terms.quantity
                            or Decimal(0),
                            full_position=terms.close_position,
                        )
                    )
            if (
                final.manual_risk_reason
                in {"manual_order_facts_incomplete", "manual_risk_inputs_invalid"}
                or final.manual_risk_reason == "manual_stop_allocation_unproven"
                and len(stops) > 1
            ):
                protection, protected = "unknown", None
    elif (
        final.active_stop_exchange_order_id is not None
        and final.active_stop_price is not None
    ):
        stops.append(
            StopView(
                price=final.active_stop_price,
                quantity=final.protected_qty,
                full_position=final.protected_qty >= final.position_qty,
            )
        )
    elif quantity:
        protection = "unknown"
        protected = None
    if final.management_mode is ManagementMode.REVIEW_REQUIRED:
        protection, protected, stops = "unknown", None, []
        quantity = None
        facts_at = None
    if (
        final.status is AggregateStatus.ENTRY_OUTCOME_UNKNOWN
        or final.manual_risk_reason == "manual_order_facts_incomplete"
    ):
        quantity, protected, protection, stops = None, None, "unknown", []
    identity = final.identity
    family = next(
        (
            name
            for name in STRATEGY_LABELS
            if identity.runtime.strategy_group_id == name
            or identity.runtime.strategy_group_id.startswith(name + "-")
        ),
        "策略",
    )
    fill = next(
        (e for e in reversed(events) if isinstance(e, ev.TakeProfitFilled)), None
    )
    snapshots = tuple(
        NoticeSnapshot(
            fill_quantity=fill.filled_qty
            if fill is not None and kind is NoticeKind.TP1
            else None,
            fill_price=fill.average_fill_price
            if fill is not None and kind is NoticeKind.TP1
            else None,
            ticket_id=identity.ticket_id,
            event_id=source_event_id,
            state_version=final.version,
            kind=kind,
            severity="critical"
            if kind in {NoticeKind.RISK, NoticeKind.REVIEW}
            else "info",
            symbol=parse_binance_usdm_instrument_id(
                identity.netting_domain.exchange_instrument_id
            ).base_asset,
            side=identity.netting_domain.position_side,
            mode=final.management_mode.value,
            quantity=quantity,
            entry_price=final.average_fill_price,
            stops=tuple(stops),
            protection=protection,
            protected_quantity=protected,
            strategy=family,
            strategy_semantics=STRATEGY_LABELS.get(family, "交易机会"),
            event_at_ms=source_at_ms,
            facts_at_ms=facts_at,
            residual_order_count=residual,
            new_entry_restricted=manual and final.manual_risk_reason is not None,
            risk_at_stop=final.manual_risk_at_stop
            if manual
            else final.actual_stop_risk,
        )
        for kind in dict.fromkeys(kinds)
    )
    if manual_fills and not flat and not takeover:
        base = next(item for item in snapshots if item.kind is NoticeKind.MANUAL_FILL)
        snapshots = tuple(
            item for item in snapshots if item.kind is not NoticeKind.MANUAL_FILL
        ) + tuple(
            base.model_copy(
                update={
                    "event_id": f"manual-fill:{item.terms.exchange_order_id}:{format_number(item.executed_quantity)}",
                    "event_at_ms": item.exchange_event_at_ms,
                    "fill_quantity": item.executed_quantity,
                    "fill_price": None,
                    "fill_role": "TP1"
                    if item.terms.exchange_order_id == final.tp1_exchange_order_id
                    else "止损",
                }
            )
            for item in manual_fills
        )
    return snapshots
