"""Tighten, one manual limit plan and full close using the sole Kernel Command ledger."""

import asyncio

from src.trading_kernel.application.owner_operation_facts import (
    OwnerOperationFactsSource,
)
from src.trading_kernel.application.ports import UnitOfWorkFactory
from src.trading_kernel.domain.aggregate import AggregateStatus as A
from src.trading_kernel.domain.commands import (
    CancelCommandPayload,
    ExchangeCommand,
    OrderCommandPayload,
    build_command_id,
    build_venue_client_order_id,
)
from src.trading_kernel.domain.commands import ExchangeCommandKind as K
from src.trading_kernel.domain.commands import ExchangeCommandStatus as S
from src.trading_kernel.domain.events import (
    OwnerPositionExitRequested,
    OwnerProfitPlanCancelled,
    OwnerProfitPlanInstalled,
    OwnerProtectionRequested,
)
from src.trading_kernel.domain.owner_position_operation import OwnerPositionPreview
from src.trading_kernel.domain.reducer import reduce_event


async def advance_owner_adjustment(
    factory: UnitOfWorkFactory,
    source: OwnerOperationFactsSource,
    row: dict,
    *,
    now_ms: int,
    timeout_seconds: float,
) -> str:
    p = OwnerPositionPreview.model_validate(row["payload"]["preview"])
    async with factory() as u:
        a = await u.aggregates.get_for_update(row["ticket_id"])
        actual = await u.owner_position_operations.get(
            row["operation_id"], for_update=True
        )
        if actual is None:
            return "operation_missing"
        if actual["completed_at_ms"] is not None:
            return actual["state"]
        if actual["version"] != row["version"]:
            return "source_changed"
        row = actual
        if a is None:
            return "ticket_missing"
        commands = tuple(await u.exchange_commands.list_for_ticket(row["ticket_id"]))
        from src.trading_kernel.application.owner_operation_expiration import (
            expire_unstarted_owner_commands,
        )

        if await expire_unstarted_owner_commands(
            u,
            aggregate=a,
            commands=commands,
            operation_id=row["operation_id"],
            now_ms=now_ms,
        ):
            return "unstarted_commands_expired"

        refs = {
            r.command_id: r.submitted_exchange_order_id
            for r in await u.exchange_commands.list_order_references(row["ticket_id"])
        }
    if a.status is A.TERMINAL:
        async with factory() as u:
            await u.owner_position_operations.transition(
                operation_id=row["operation_id"],
                expected_version=row["version"],
                state="closed",
                payload=row["payload"],
                reason="ticket_terminal",
                now_ms=now_ms,
                completed=True,
            )
        return "closed"
    pending_protection = a.protection_operation_id == row[
        "operation_id"
    ] and a.status.value.startswith("runner_")
    pending_exit = (
        p.kind == "position_close"
        and a.status is A.EXIT_PENDING
        and any(
            c.kind is K.EXIT
            and getattr(c.payload, "owner_operation_id", None) == row["operation_id"]
            and c.status is S.PREPARED
            for c in commands
        )
    )
    if (
        a.status not in {A.POSITION_PROTECTED, A.RUNNER_PROTECTED}
        and not pending_protection
        and not pending_exit
    ):
        async with factory() as u:
            await u.owner_position_operations.transition(
                operation_id=row["operation_id"],
                expected_version=row["version"],
                state="review_required"
                if a.status.value == "exit_rejected"
                else "closure_pending",
                payload=row["payload"],
                reason="exit_rejected_protection_retained"
                if a.status.value == "exit_rejected"
                else "original_lifecycle_pending",
                now_ms=now_ms,
            )
        return "lifecycle_pending"
    try:
        o = await asyncio.wait_for(
            source.read_owner_position(
                aggregate=a,
                commands=commands,
                accepted_order_ids=refs,
                operation_id=row["operation_id"],
            ),
            timeout=timeout_seconds,
        )
    except Exception as exc:  # noqa: BLE001 - no verified fact grants an effect.
        async with factory() as u:
            await u.owner_position_operations.transition(
                operation_id=row["operation_id"],
                expected_version=row["version"],
                state="facts_unavailable",
                payload=row["payload"],
                reason=f"facts:{type(exc).__name__}",
                now_ms=now_ms,
            )
        return "facts_unavailable"
    now_ms = max(now_ms, o.facts.observed_at_ms)
    async with factory() as u:
        current = await u.aggregates.get_for_update(row["ticket_id"])
        latest = await u.owner_position_operations.get(
            row["operation_id"], for_update=True
        )
        if (
            current is None
            or current.version != a.version
            or latest is None
            or latest["version"] != row["version"]
        ):
            return "source_changed"
        payload = {
            **row["payload"],
            "facts": o.facts.model_dump(mode="json"),
            "protection_close_position": o.protection_close_position,
        }
        ids = list(payload.get("prepared_command_ids", []))
        ids.extend(
            c.command_id
            for c in commands
            if getattr(c.payload, "owner_operation_id", None) == row["operation_id"]
            and c.command_id not in ids
        )

        async def save(state, reason=None, completed=False):
            payload["prepared_command_ids"] = ids
            await u.owner_position_operations.transition(
                operation_id=row["operation_id"],
                expected_version=row["version"],
                state=state,
                payload=payload,
                reason=reason,
                now_ms=now_ms,
                completed=completed,
            )
            return state

        from src.trading_kernel.application.handoff_owner_operation import (
            handoff_natural_tp,
        )

        if await handoff_natural_tp(
            u,
            aggregate=current,
            row=row,
            commands=commands,
            filled_quantity=o.facts.tp_filled_quantity,
            position_quantity=o.facts.position_quantity,
            now_ms=now_ms,
        ):
            return "handed_to_lifecycle"
        if payload.get("end_requested"):
            from src.trading_kernel.application.finish_owner_adjustment import (
                finish_owner_adjustment,
            )

            end = payload["end_requested"]
            return await finish_owner_adjustment(
                u,
                aggregate=current,
                row={**row, "payload": payload},
                commands=commands,
                observation=o,
                state=end["state"],
                reason=end["reason"],
                now_ms=now_ms,
            )
        if pending_exit:
            return await save("closure_pending", "full_close_facts_refreshed")
        if pending_protection:
            return await save("protection_pending", "protection_truth_pending")
        if o.facts.position_quantity == 0 or o.facts.stop_triggered:
            await u.aggregates.expedite_reconciliation(
                row["ticket_id"], due_at_ms=now_ms
            )
            return await save("closure_pending", "stop_or_flat_requires_reconciliation")
        own = [
            c
            for c in commands
            if getattr(c.payload, "owner_operation_id", None) == row["operation_id"]
        ]
        working = any(
            c.status in {S.PREPARED, S.CLAIMED, S.OUTCOME_UNKNOWN} for c in own
        )
        if not await u.owner_position_operations.authority_current(
            row, management_revision=a.management_revision
        ):
            for c in own:
                if c.status is S.PREPARED:
                    await u.exchange_commands.mark_prepared_superseded(
                        command_id=c.command_id,
                        observed_at_ms=now_ms,
                        reason="owner_authority_revoked_before_send",
                    )
            return await save(
                "review_required" if working else "revoked",
                "device_or_management_changed",
                completed=not working and not own,
            )

        def fields():
            return {
                "event_id": f"event:{a.identity.ticket_id}:{a.last_event_sequence + 1}",
                "ticket_id": a.identity.ticket_id,
                "sequence": a.last_event_sequence + 1,
                "occurred_at_ms": now_ms,
            }

        async def commit(ev):
            await u.commit_reduction(
                event=ev, reduction=reduce_event(a, ev), expected_version=a.version
            )

        async def finish(state, reason):
            from src.trading_kernel.application.finish_owner_adjustment import (
                finish_owner_adjustment,
            )

            return await finish_owner_adjustment(
                u,
                aggregate=current,
                row={**row, "payload": payload},
                commands=commands,
                observation=o,
                state=state,
                reason=reason,
                now_ms=now_ms,
            )

        if row["first_blocker"] == "owner_tp_target_crossed_repreview_required":
            return await finish(
                "repreview_required", "owner_tp_target_crossed_repreview_required"
            )
        if p.kind == "protection_tighten":
            assert p.price is not None
            if o.facts.stop_price is None:
                return await save("review_required", "protection_price_missing")
            if a.active_stop_exchange_order_id != p.protection_order_id:
                improved = (
                    o.facts.stop_price >= p.price
                    if p.side == "long"
                    else o.facts.stop_price <= p.price
                )
                return await save(
                    "completed" if improved else "review_required",
                    None if improved else "stop_not_confirmed",
                    completed=improved,
                )
            if own:
                if any(
                    c.status in {S.REJECTED, S.SUPERSEDED, S.RECONCILED_ABSENT}
                    for c in own
                ):
                    return await finish(
                        "failed", "stop_not_sent_or_rejected_original_protection_kept"
                    )
                return await save("protection_pending")
            if (
                a.version != p.aggregate_version
                or o.facts.position_quantity != p.source_quantity
                or now_ms >= p.expires_at_ms
            ):
                return await save("rejected", "preview_changed", completed=True)
            crossed = (
                p.price >= o.facts.current_price
                if p.side == "long"
                else p.price <= o.facts.current_price
            )
            if crossed:
                return await save("rejected", "stop_price_crossed", completed=True)
            ev = OwnerProtectionRequested(
                **fields(),
                operation_id=row["operation_id"],
                stop_price=p.price,
                close_position=o.protection_close_position,
                source_watermark_ms=o.facts.observed_at_ms,
            )
            await commit(ev)
            ids.extend(
                c.command_id
                for c in await u.exchange_commands.list_for_ticket(row["ticket_id"])
                if getattr(c.payload, "owner_operation_id", None) == row["operation_id"]
                and c.command_id not in ids
            )
            return await save("protection_pending")
        if p.kind == "manual_tp_set" and not o.protection_close_position:
            assert a.active_stop_price is not None
            conversion = [c for c in own if c.kind is K.REPLACE_PROTECTION]
            if conversion:
                if any(
                    c.status in {S.REJECTED, S.SUPERSEDED, S.RECONCILED_ABSENT}
                    for c in conversion
                ):
                    return await finish("failed", "protection_conversion_not_executed")
                return await save("protection_pending")
            ev = OwnerProtectionRequested(
                **fields(),
                operation_id=row["operation_id"],
                stop_price=a.active_stop_price,
                close_position=True,
                source_watermark_ms=o.facts.observed_at_ms,
            )
            await commit(ev)
            ids.extend(
                c.command_id
                for c in await u.exchange_commands.list_for_ticket(row["ticket_id"])
                if getattr(c.payload, "owner_operation_id", None) == row["operation_id"]
                and c.command_id not in ids
            )
            return await save("protection_pending")
        new_plans = [c for c in own if c.kind is K.TAKE_PROFIT]
        if p.kind == "manual_tp_set" and new_plans:
            assert p.price is not None and p.quantity is not None
            new_plan = new_plans[0]
            accepted_plan = next(
                (x for x in o.orders if x.command_id == new_plan.command_id), None
            )
            if accepted_plan is not None and accepted_plan.status in {
                "NEW",
                "PARTIALLY_FILLED",
                "FILLED",
            }:
                if (
                    o.facts.position_quantity
                    != p.source_quantity - accepted_plan.evidence.executed_quantity
                    or o.facts.tp_filled_quantity != p.source_tp_filled_quantity
                ):
                    return await save(
                        "review_required", "manual_tp_fill_or_position_changed"
                    )
                await commit(
                    OwnerProfitPlanInstalled(
                        **fields(),
                        operation_id=row["operation_id"],
                        command_id=new_plan.command_id,
                        exchange_order_id=accepted_plan.evidence.terms.exchange_order_id,
                        replaces_exchange_order_id=p.source_tp_order_id,
                        price=p.price,
                        quantity=p.quantity,
                        evidence=accepted_plan.evidence,
                    )
                )
                return await save("completed", completed=True)
        # Never carry an old size through an interleaved fill. The original lifecycle
        # must record that fill before a new phone operation can be previewed.
        if (
            o.facts.position_quantity != p.source_quantity
            or o.facts.tp_filled_quantity != p.source_tp_filled_quantity
        ):
            return await save("review_required", "position_or_tp_changed")
        tp = next(
            (
                x
                for x in o.orders
                if x.evidence.terms.exchange_order_id == p.source_tp_order_id
            ),
            None,
        )
        if p.source_tp_order_id and (
            tp is None or tp.status not in {"CANCELED", "EXPIRED", "EXPIRED_IN_MATCH"}
        ):
            cancel_attempts = [c for c in own if c.kind is K.CANCEL_ORDER]
            if cancel_attempts:
                if not working and any(
                    c.status in {S.REJECTED, S.SUPERSEDED, S.RECONCILED_ABSENT}
                    for c in cancel_attempts
                ):
                    return await save("failed", "tp_cancel_rejected", completed=True)
                return await save("tp_cancelling")
            if now_ms >= p.expires_at_ms:
                return await save("rejected", "preview_expired", completed=True)
            generation = await u.exchange_commands.next_generation(
                ticket_id=row["ticket_id"], kind=K.CANCEL_ORDER
            )
            cid = build_command_id(
                ticket_id=row["ticket_id"], kind=K.CANCEL_ORDER, generation=generation
            )
            await u.exchange_commands.add(
                ExchangeCommand(
                    command_id=cid,
                    ticket_identity=a.identity,
                    management_revision=a.management_revision,
                    kind=K.CANCEL_ORDER,
                    generation=generation,
                    idempotency_key=cid,
                    venue_client_order_id=build_venue_client_order_id(cid),
                    payload=CancelCommandPayload(
                        exchange_order_id=p.source_tp_order_id,
                        order_namespace="regular",
                        purpose="owner_tp",
                        owner_operation_id=row["operation_id"],
                    ),
                    status=S.PREPARED,
                    created_at_ms=now_ms,
                    deadline_at_ms=now_ms + 30000,
                )
            )
            ids.append(cid)
            return await save("tp_cancelling")
        if p.kind == "manual_tp_cancel":
            assert p.source_tp_order_id is not None and tp is not None
            await commit(
                OwnerProfitPlanCancelled(
                    **fields(),
                    evidence=tp.evidence,
                    operation_id=row["operation_id"],
                    exchange_order_id=p.source_tp_order_id,
                )
            )
            return await save("completed", completed=True)
        if p.kind == "position_close":
            exit_attempts = [c for c in own if c.kind is K.EXIT]
            if exit_attempts:
                return await save(
                    "review_required", "full_close_not_executed_protection_retained"
                )

            # Existing lifecycle owns market exit, residual cleanup, settlement and review.
            await commit(
                OwnerPositionExitRequested(**fields(), operation_id=row["operation_id"])
            )
            ids.extend(
                c.command_id
                for c in await u.exchange_commands.list_for_ticket(row["ticket_id"])
                if getattr(c.payload, "owner_operation_id", None) == row["operation_id"]
                and c.command_id not in ids
            )
            return await save("closure_pending")
        assert p.price is not None and p.quantity is not None
        plans = [c for c in own if c.kind is K.TAKE_PROFIT]
        if plans:
            plan = plans[0]
            order = next((x for x in o.orders if x.command_id == plan.command_id), None)
            if order is not None and order.status in {
                "NEW",
                "PARTIALLY_FILLED",
                "FILLED",
            }:
                await commit(
                    OwnerProfitPlanInstalled(
                        **fields(),
                        operation_id=row["operation_id"],
                        command_id=plan.command_id,
                        exchange_order_id=order.evidence.terms.exchange_order_id,
                        replaces_exchange_order_id=p.source_tp_order_id,
                        price=p.price,
                        quantity=p.quantity,
                        evidence=order.evidence,
                    )
                )
                return await save("completed", completed=True)
            if plan.status in {S.REJECTED, S.SUPERSEDED, S.RECONCILED_ABSENT}:
                return await finish(
                    "failed", "manual_tp_not_sent_or_rejected_protection_retained"
                )
            if plan.status is S.PREPARED:
                from src.trading_kernel.domain.owner_command_prices import (
                    owner_command_price_blocker,
                )

                assert isinstance(plan.payload, OrderCommandPayload)
                crossed_pending = owner_command_price_blocker(
                    kind=plan.kind,
                    payload=plan.payload,
                    position_side=p.side,
                    current_price=o.facts.current_price,
                )
                if crossed_pending is not None:
                    return await finish(
                        "repreview_required", crossed_pending + "_repreview_required"
                    )
            return await save("tp_pending")
        from src.trading_kernel.domain.owner_command_prices import (
            owner_command_price_blocker,
        )

        proposed_tp = OrderCommandPayload(
            side="sell" if p.side == "long" else "buy",
            quantity=p.quantity,
            order_type="limit",
            reduce_only=True,
            limit_price=p.price,
            time_in_force="GTC",
            owner_operation_id=row["operation_id"],
        )
        tp_price_blocker = owner_command_price_blocker(
            kind=K.TAKE_PROFIT,
            payload=proposed_tp,
            position_side=p.side,
            current_price=o.facts.current_price,
        )
        if tp_price_blocker is not None:
            return await finish(
                "repreview_required", tp_price_blocker + "_repreview_required"
            )
        generation = await u.exchange_commands.next_generation(
            ticket_id=row["ticket_id"], kind=K.TAKE_PROFIT
        )
        cid = build_command_id(
            ticket_id=row["ticket_id"], kind=K.TAKE_PROFIT, generation=generation
        )
        await u.exchange_commands.add(
            ExchangeCommand(
                command_id=cid,
                ticket_identity=a.identity,
                management_revision=a.management_revision,
                kind=K.TAKE_PROFIT,
                generation=generation,
                idempotency_key=cid,
                venue_client_order_id=build_venue_client_order_id(cid),
                payload=OrderCommandPayload(
                    side="sell" if p.side == "long" else "buy",
                    quantity=p.quantity,
                    order_type="limit",
                    reduce_only=True,
                    limit_price=p.price,
                    time_in_force="GTC",
                    owner_operation_id=row["operation_id"],
                ),
                status=S.PREPARED,
                created_at_ms=now_ms,
                deadline_at_ms=now_ms + 30000,
            )
        )
        ids.append(cid)
        return await save("tp_pending")
