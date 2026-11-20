"""Resolve a persisted phone intent into the existing execution plan."""

import asyncio
from decimal import Decimal

from src.trading_kernel.application.owner_operation_facts import (
    OwnerOperationFactsSource,
)
from src.trading_kernel.application.ports import UnitOfWorkFactory
from src.trading_kernel.domain.aggregate import AggregateStatus
from src.trading_kernel.domain.commands import (
    ExchangeCommand,
    ExchangeCommandKind,
    ExchangeCommandStatus,
    OrderCommandPayload,
    build_command_id,
    build_venue_client_order_id,
)
from src.trading_kernel.domain.events import OwnerPositionExitRequested
from src.trading_kernel.domain.owner_position_intent import OwnerPositionIntent
from src.trading_kernel.domain.owner_position_operation import (
    OwnerPositionPreview,
    preview_position_operation,
)
from src.trading_kernel.domain.owner_reduction import (
    OwnerReductionPreview,
    preview_owner_reduction,
)
from src.trading_kernel.domain.reducer import reduce_event


async def prepare_owner_position_intent(
    factory: UnitOfWorkFactory,
    source: OwnerOperationFactsSource,
    row: dict,
    *,
    now_ms: int,
    timeout_seconds: float,
) -> str:
    intent = OwnerPositionIntent.model_validate(row["payload"]["intent"])
    deadline = row["payload"]["start_deadline_ms"]
    async with factory() as u:
        a = await u.aggregates.get(intent.ticket_id)
        if a is None:
            return "ticket_missing"
        commands = tuple(await u.exchange_commands.list_for_ticket(intent.ticket_id))
        refs = {
            r.command_id: r.submitted_exchange_order_id
            for r in await u.exchange_commands.list_order_references(intent.ticket_id)
        }
        domain = a.identity.netting_domain
        rules = await u.signals.get_instrument_rules(
            domain.venue_id, domain.exchange_instrument_id
        )

    plan: OwnerPositionPreview | OwnerReductionPreview | None = None
    state = "rejected"
    discard: tuple[ExchangeCommand, ...] = ()
    observed = None
    if a.status is AggregateStatus.TERMINAL:
        reason, state = "already_flat", "closed"
    elif now_ms >= deadline:
        reason, state = "owner_start_window_expired", "expired"
    elif a.management_revision != row["payload"]["management_revision"]:
        reason, state = "device_or_management_changed", "revoked"
    elif rules is None:
        reason = "position_rules_unavailable"
    else:
        if intent.kind in {"position_close", "position_reduce"} and a.status is AggregateStatus.TP1_PENDING:
            # Unsent TP is fenced by the active operation. The final EXIT
            # gate also checks that none of these commands can have reached Binance.
            discard = tuple(
                c
                for c in commands
                if c.kind is ExchangeCommandKind.TAKE_PROFIT
                and c.status is ExchangeCommandStatus.PREPARED
                and c.command_id not in refs
            )
        try:
            observed = await asyncio.wait_for(
                source.read_owner_position(
                    aggregate=a,
                    commands=tuple(c for c in commands if c not in discard),
                    accepted_order_ids=refs,
                    operation_id=row["operation_id"],
                ),
                timeout=min(timeout_seconds, (deadline - now_ms) / 1000),
            )
            facts = observed.facts
            now_ms = max(now_ms, facts.observed_at_ms)
            if now_ms >= deadline:
                state = "expired"
                raise ValueError("owner_start_window_expired")
            if intent.kind == "position_reduce":
                assert intent.amount is not None
                plan = preview_owner_reduction(
                    aggregate=a,
                    facts=facts,
                    requested_quantity=intent.amount,
                    quantity_step=rules.quantity_step,
                    minimum_quantity=rules.min_quantity,
                    minimum_notional=rules.min_notional,
                    now_ms=now_ms,
                )
            else:
                if (
                    intent.kind in {"manual_tp_set", "manual_tp_cancel"}
                    and a.tp1_exchange_order_id != intent.tp_order_id
                ):
                    raise ValueError("profit_plan_changed")
                if (
                    intent.kind == "protection_tighten"
                    and intent.price is not None
                    and facts.stop_price is not None
                    and facts.stop_price == a.active_stop_price
                    and facts.observed_at_ms <= now_ms < facts.valid_until_ms
                    and not facts.stop_triggered
                    and (
                        facts.current_price > facts.stop_price
                        if domain.position_side == "long"
                        else facts.current_price < facts.stop_price
                    )
                    and facts.protection_order_id == a.active_stop_exchange_order_id
                    and facts.protected_quantity
                    == facts.position_quantity
                    == a.position_qty
                    and (
                        facts.stop_price >= Decimal(intent.price)
                        if domain.position_side == "long"
                        else facts.stop_price <= Decimal(intent.price)
                    )
                ):
                    state = "completed"
                    raise ValueError("stop_already_tight_enough")
                plan = preview_position_operation(
                    aggregate=a,
                    facts=facts,
                    kind=intent.kind,
                    quantity_step=rules.quantity_step,
                    minimum_quantity=rules.min_quantity,
                    minimum_notional=rules.min_notional,
                    now_ms=now_ms,
                    price_tick=rules.price_tick,
                    price=None if intent.price is None else Decimal(intent.price),
                    quantity=intent.amount,
                )
            plan = plan.model_copy(update={"expires_at_ms": deadline})
            reason = None
        except (ValueError, TypeError, ArithmeticError, KeyError) as exc:
            reason = str(exc)[:200] if isinstance(exc, ValueError) else "position_facts_invalid"
        except Exception:  # noqa: BLE001 - no executable plan without a complete venue observation.
            reason, state = "position_facts_unavailable", "facts_unavailable"

    async with factory() as u:
        current = await u.aggregates.get_for_update(intent.ticket_id)
        latest = await u.owner_position_operations.get(
            row["operation_id"], for_update=True
        )
        if current is None or latest is None or latest["version"] != row["version"]:
            return "source_changed"
        if current.version != a.version:
            return "source_changed"
        if plan is not None and not await u.owner_position_operations.authority_current(
            latest, management_revision=current.management_revision
        ):
            plan, reason, state = None, "device_revoked", "revoked"
        if plan is None:
            await u.owner_position_operations.transition(
                operation_id=row["operation_id"],
                expected_version=row["version"],
                state=state,
                payload=row["payload"],
                reason=reason,
                now_ms=now_ms,
                completed=state != "facts_unavailable",
            )
            return state
        assert plan is not None and observed is not None
        if (
            isinstance(plan, OwnerReductionPreview)
            and observed.protection_close_position
            and plan.cancel_tp_order_id is None
        ):
            # The first exact observation is sufficient for this branch.
            # Atomically publish the plan and the one market reduction.
            kind = ExchangeCommandKind.OWNER_REDUCE
            generation = await u.exchange_commands.next_generation(
                ticket_id=intent.ticket_id, kind=kind
            )
            command_id = build_command_id(
                ticket_id=intent.ticket_id, kind=kind, generation=generation
            )
            await u.exchange_commands.add(
                ExchangeCommand(
                    command_id=command_id,
                    ticket_identity=a.identity,
                    management_revision=a.management_revision,
                    kind=kind,
                    generation=generation,
                    idempotency_key=command_id,
                    venue_client_order_id=build_venue_client_order_id(command_id),
                    payload=OrderCommandPayload(
                        side="sell" if plan.side == "long" else "buy",
                        quantity=plan.reduction_quantity,
                        order_type="market",
                        reduce_only=True,
                        owner_operation_id=row["operation_id"],
                    ),
                    status=ExchangeCommandStatus.PREPARED,
                    created_at_ms=now_ms,
                    deadline_at_ms=min(deadline, now_ms + 30_000),
                )
            )
            await u.owner_position_operations.install_intent_plan(
                latest,
                plan,
                now_ms=now_ms,
                command_id=command_id,
                facts=observed.facts.model_dump(mode="json"),
                deferred_tp_ids=tuple(c.command_id for c in discard),
            )
            return "reduction_pending"
        await u.owner_position_operations.install_intent_plan(
            latest,
            plan,
            now_ms=now_ms,
            deferred_tp_ids=tuple(c.command_id for c in discard),
        )
        if (
            isinstance(plan, OwnerPositionPreview)
            and plan.kind == "position_close"
            and plan.source_tp_order_id is None
            and observed.facts.tp_state == "absent"
        ):
            event = OwnerPositionExitRequested(
                event_id=f"event:{intent.ticket_id}:{a.last_event_sequence + 1}",
                ticket_id=intent.ticket_id,
                sequence=a.last_event_sequence + 1,
                occurred_at_ms=now_ms,
                operation_id=row["operation_id"],
            )
            await u.commit_reduction(
                event=event,
                reduction=reduce_event(current, event),
                expected_version=a.version,
            )
            prepared = await u.exchange_commands.list_for_ticket(intent.ticket_id)
            await u.owner_position_operations.transition(
                operation_id=row["operation_id"],
                expected_version=row["version"] + 1,
                state="closure_pending",
                reason=None,
                now_ms=now_ms,
                payload={
                    **latest["payload"],
                    "preview": plan.model_dump(mode="json"),
                    "deferred_tp_ids": [c.command_id for c in discard],
                    "facts": observed.facts.model_dump(mode="json"),
                    "prepared_command_ids": [
                        c.command_id
                        for c in prepared
                        if c.kind is ExchangeCommandKind.EXIT
                        and getattr(c.payload, "owner_operation_id", None)
                        == row["operation_id"]
                    ],
                },
            )
            return "closure_pending"
    return "intent_planned"
