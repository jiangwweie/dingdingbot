"""Close a failed/repreviewed adjustment only after its actual effects are known."""

from src.trading_kernel.application.owner_operation_facts import (
    OwnerPositionObservation,
)
from src.trading_kernel.application.ports import KernelUnitOfWork
from src.trading_kernel.domain.aggregate import AggregateStatus, TradeAggregate
from src.trading_kernel.domain.commands import (
    CancelCommandPayload,
    ExchangeCommand,
    OrderCommandPayload,
)
from src.trading_kernel.domain.commands import ExchangeCommandKind as K
from src.trading_kernel.domain.commands import ExchangeCommandStatus as S
from src.trading_kernel.domain.events import OwnerProfitPlanRetired
from src.trading_kernel.domain.owner_position_operation import OwnerPositionPreview
from src.trading_kernel.domain.reducer import reduce_event


async def finish_owner_adjustment(
    uow: KernelUnitOfWork,
    *,
    aggregate: TradeAggregate,
    row: dict,
    commands: tuple[ExchangeCommand, ...],
    observation: OwnerPositionObservation,
    state: str,
    reason: str,
    now_ms: int,
) -> str:
    a = aggregate
    facts = observation.facts
    requested = row["payload"].get("end_requested") or {
        "state": state,
        "reason": reason,
        "requested_at_ms": now_ms,
    }
    state, reason = requested["state"], requested["reason"]
    row = {**row, "payload": {**row["payload"], "end_requested": requested}}
    own = [
        c
        for c in commands
        if getattr(c.payload, "owner_operation_id", None) == row["operation_id"]
    ]
    if (
        any(c.status in {S.CLAIMED, S.OUTCOME_UNKNOWN} for c in own)
        or a.management_mode.value != "AUTO"
        or a.protection_operation_id == row["operation_id"]
        or a.status
        not in {AggregateStatus.POSITION_PROTECTED, AggregateStatus.RUNNER_PROTECTED}
        or facts.ticket_id != a.identity.ticket_id
        or facts.management_revision != a.management_revision
        or facts.management_mode is not a.management_mode
        or facts.stop_price is None
        or facts.stop_price != a.active_stop_price
        or facts.position_quantity != a.position_qty
        or facts.protected_quantity != facts.position_quantity
        or facts.stop_triggered
        or facts.protection_order_id != a.active_stop_exchange_order_id
        or not facts.observed_at_ms <= now_ms < facts.valid_until_ms
    ):
        await uow.owner_position_operations.transition(
            operation_id=row["operation_id"],
            expected_version=row["version"],
            state="review_required",
            payload=row["payload"],
            reason="owner_adjustment_effects_unresolved",
            now_ms=now_ms,
        )
        return "review_required"
    # Never discard a submitted replacement TP whose venue effect has not been
    # installed/retired. Closing this operation must not abandon a live exit.
    if any(
        c.kind is K.TAKE_PROFIT and c.status in {S.ACCEPTED, S.RECONCILED_ACCEPTED}
        for c in own
    ):
        await uow.owner_position_operations.transition(
            operation_id=row["operation_id"],
            expected_version=row["version"],
            state="review_required",
            payload=row["payload"],
            reason="owner_tp_accepted_requires_observation",
            now_ms=now_ms,
        )
        return "review_required"
    p = OwnerPositionPreview.model_validate(row["payload"]["preview"])
    old = next(
        (
            o
            for o in observation.orders
            if o.evidence.terms.exchange_order_id == p.source_tp_order_id
        ),
        None,
    )
    retired = None
    if p.source_tp_order_id is not None:
        if old is None or old.evidence.executed_quantity != a.tp1_filled_qty:
            await uow.owner_position_operations.transition(
                operation_id=row["operation_id"],
                expected_version=row["version"],
                state="review_required",
                payload=row["payload"],
                reason="old_tp_effects_unresolved",
                now_ms=now_ms,
            )
            return "review_required"
        if old.status in {"CANCELED", "EXPIRED", "EXPIRED_IN_MATCH"}:
            cancellation = any(
                c.kind is K.CANCEL_ORDER
                and isinstance(c.payload, CancelCommandPayload)
                and c.payload.exchange_order_id == p.source_tp_order_id
                and c.payload.order_namespace == "regular"
                and c.status in {S.ACCEPTED, S.RECONCILED_ACCEPTED, S.RECONCILED_ABSENT}
                for c in own
            )
            if not cancellation:
                await uow.owner_position_operations.transition(
                    operation_id=row["operation_id"],
                    expected_version=row["version"],
                    state="review_required",
                    payload=row["payload"],
                    reason="old_tp_cancel_cause_unresolved",
                    now_ms=now_ms,
                )
                return "review_required"
            source = next((c for c in commands if c.command_id == old.command_id), None)
            if source is None or not isinstance(source.payload, OrderCommandPayload):
                raise ValueError("retired_tp_source_missing")
            ev = OwnerProfitPlanRetired(
                event_id=f"event:{a.identity.ticket_id}:{a.last_event_sequence + 1}",
                ticket_id=a.identity.ticket_id,
                sequence=a.last_event_sequence + 1,
                occurred_at_ms=now_ms,
                operation_id=row["operation_id"],
                command_id=old.command_id,
                exchange_order_id=p.source_tp_order_id,
                source_kind="manual"
                if source.payload.owner_operation_id is not None
                else "retired_automatic",
                evidence=old.evidence,
            )
            await uow.commit_reduction(
                event=ev, reduction=reduce_event(a, ev), expected_version=a.version
            )
            retired = p.source_tp_order_id
        elif old.status not in {"NEW", "PARTIALLY_FILLED"}:
            await uow.owner_position_operations.transition(
                operation_id=row["operation_id"],
                expected_version=row["version"],
                state="review_required",
                payload=row["payload"],
                reason="old_tp_terminal_unresolved",
                now_ms=now_ms,
            )
            return "review_required"
    for c in own:
        if c.status is S.PREPARED:
            await uow.exchange_commands.mark_prepared_superseded(
                command_id=c.command_id,
                observed_at_ms=now_ms,
                reason="owner_adjustment_ended_requires_new_confirmation",
            )
    effects = {
        "retired_tp_order_id": retired,
        "old_tp_order_id": p.source_tp_order_id,
        "old_tp_still_active": p.source_tp_order_id is not None and retired is None,
        "protection_order_id": facts.protection_order_id,
        "protection_price": str(facts.stop_price),
        "position_quantity": str(facts.position_quantity),
        "protection_confirmed": True,
        "protection_changed": facts.protection_order_id != p.protection_order_id,
        "new_tp_order_id": None,
        "requested_instruction_applied": False,
        "observed_at_ms": facts.observed_at_ms,
    }
    payload = {
        **row["payload"],
        "actual_effects": effects,
        "result": {"state": state, "actual_effects": effects},
        "facts": facts.model_dump(mode="json"),
    }
    await uow.owner_position_operations.transition(
        operation_id=row["operation_id"],
        expected_version=row["version"],
        state=state,
        payload=payload,
        reason=reason,
        now_ms=now_ms,
        completed=True,
    )
    return state
