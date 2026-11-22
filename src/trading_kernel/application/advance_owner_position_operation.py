"""Advance a durable Owner intent through existing Kernel commands, one step per tick."""

import asyncio

from src.trading_kernel.application.owner_cooperation_capability import (
    owner_cooperation_enabled,
)
from src.trading_kernel.application.owner_operation_facts import (
    OwnerOperationFactsSource,
    owner_operation_fact_blocker,
)
from src.trading_kernel.application.ports import UnitOfWorkFactory
from src.trading_kernel.application.record_owner_reduction import record_owner_reduction
from src.trading_kernel.domain.aggregate import AggregateStatus as A
from src.trading_kernel.domain.commands import (
    CancelCommandPayload,
    ExchangeCommand,
    OrderCommandPayload,
    build_command_id,
    build_venue_client_order_id,
)
from src.trading_kernel.domain.commands import (
    ExchangeCommandKind as K,
)
from src.trading_kernel.domain.commands import (
    ExchangeCommandStatus as S,
)
from src.trading_kernel.domain.events import (
    ExitRequested,
    ManagementReviewRequired,
    OwnerAutomaticTpRestoreRequested,
    OwnerProtectionRequested,
)
from src.trading_kernel.domain.owner_reduction import OwnerReductionPhase as P
from src.trading_kernel.domain.owner_reduction import (
    OwnerReductionState,
    advance_owner_reduction,
)
from src.trading_kernel.domain.reducer import reduce_event


async def advance_owner_position_operation(
    uow_factory: UnitOfWorkFactory,
    facts_source: OwnerOperationFactsSource,
    *,
    now_ms: int,
    timeout_seconds: float,
    runtime_commit: str,
    schema_revision: str,
) -> str | None:
    async with uow_factory() as u:
        capability = await u.signals.get_runtime_capability("exchange_commands")
        if not owner_cooperation_enabled(
            capability, runtime_commit=runtime_commit, schema_revision=schema_revision
        ):
            return None
        rows = await u.owner_position_operations.due(now_ms=now_ms, limit=1)
        if not rows:
            return None
        row = rows[0]
        a = await u.aggregates.get(row["ticket_id"])
    if "intent" in row["payload"] and row["payload"].get("preview") is None:
        from src.trading_kernel.application.prepare_owner_position_intent import (
            prepare_owner_position_intent,
        )

        return await prepare_owner_position_intent(
            uow_factory, facts_source, row, now_ms=now_ms, timeout_seconds=timeout_seconds
        )
    if row["authorization_id"] is None:
        async with uow_factory() as u:
            await u.owner_position_operations.transition(
                operation_id=row["operation_id"],
                expected_version=row["version"],
                state="expired",
                payload=row["payload"],
                reason="preview_expired",
                now_ms=now_ms,
                completed=True,
            )
        return "preview_expired"
    if row["kind"] != "position_reduce":
        from src.trading_kernel.application.advance_owner_adjustment import (
            advance_owner_adjustment,
        )

        return await advance_owner_adjustment(
            uow_factory,
            facts_source,
            row,
            now_ms=now_ms,
            timeout_seconds=timeout_seconds,
        )
    assert a is not None
    async with uow_factory() as u:
        s = (
            OwnerReductionState.model_validate(row["payload"]["reduction_state"])
            if row["authorization_id"]
            else None
        )
        if s is None:
            await u.owner_position_operations.transition(
                operation_id=row["operation_id"],
                expected_version=row["version"],
                state="expired",
                payload=row["payload"],
                reason="preview_expired",
                now_ms=now_ms,
                completed=True,
            )
            return "preview_expired"
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
            start_deadline_ms=row["payload"].get("start_deadline_ms"),
        ):
            return "unstarted_commands_expired"

        accepted_order_ids = {
            r.command_id: r.submitted_exchange_order_id
            for r in await u.exchange_commands.list_order_references(row["ticket_id"])
        }
        if row["state"] == "restoring_original_tp":
            restores = [
                c
                for c in commands
                if c.command_id in row["payload"].get("restoration_command_ids", [])
            ]
            if any(
                c.status in {S.ACCEPTED, S.RECONCILED_ACCEPTED}
                and c.command_id in accepted_order_ids
                for c in restores
            ):
                await u.owner_position_operations.transition(
                    operation_id=row["operation_id"],
                    expected_version=row["version"],
                    state="failed",
                    payload=row["payload"],
                    reason="reduction_not_executed_original_tp_restored",
                    now_ms=now_ms,
                    completed=True,
                )
                return "restored"
            if any(c.status is S.REJECTED for c in restores):
                await u.owner_position_operations.transition(
                    operation_id=row["operation_id"],
                    expected_version=row["version"],
                    state="review_required",
                    payload=row["payload"],
                    reason="original_tp_restore_rejected",
                    now_ms=now_ms,
                )
                return "review_required"
        restoring_tp = row["state"] == "restoring_original_tp" and a.status in {
            A.TP1_PENDING,
            A.TP1_OUTCOME_UNKNOWN,
        }
        pending_protection = a.protection_operation_id == row[
            "operation_id"
        ] and a.status.value.startswith("runner_")
        if (
            a.status not in {A.POSITION_PROTECTED, A.RUNNER_PROTECTED, A.TP1_PENDING}
            and not pending_protection
            and not restoring_tp
        ):
            if a.status is A.TERMINAL:
                await u.owner_position_operations.transition(
                    operation_id=row["operation_id"],
                    expected_version=row["version"],
                    state="closed",
                    payload=row["payload"],
                    reason="ticket_terminal",
                    now_ms=now_ms,
                    completed=True,
                )
            else:
                await u.owner_position_operations.transition(
                    operation_id=row["operation_id"],
                    expected_version=row["version"],
                    state="closure_pending",
                    payload=row["payload"],
                    reason="original_lifecycle_pending",
                    now_ms=now_ms,
                )
            return "lifecycle_pending"
        if not await u.owner_position_operations.authority_current(
            row, management_revision=a.management_revision
        ) and not row["payload"].get("prepared_command_ids"):
            await u.owner_position_operations.transition(
                operation_id=row["operation_id"],
                expected_version=row["version"],
                state="revoked",
                payload=row["payload"],
                reason="device_revoked",
                now_ms=now_ms,
                completed=True,
            )
            return "revoked"
    original_exit_reason = None
    async with uow_factory() as u:
        profile = await u.exit_profiles.get_profile(
            exit_profile_id=a.ticket.exit_policy_id,
            semantic_hash=a.ticket.exit_policy_semantic_hash,
        )
        rules = await u.signals.get_instrument_rules(
            a.identity.netting_domain.venue_id,
            a.identity.netting_domain.exchange_instrument_id,
        )
        references = await u.exchange_commands.list_order_references(
            a.identity.ticket_id
        )
    try:
        if profile is None or rules is None:
            raise ValueError("operation_original_policy_or_rules_missing")
        from src.trading_kernel.application.owner_operation_exit import (
            read_original_operation_exit,
        )

        deferred_tp_ids = set(row["payload"].get("deferred_tp_ids", ()))
        observation = await asyncio.wait_for(
            facts_source.read_owner_reduction(
                aggregate=a,
                state=s,
                authorization_id=row["authorization_id"],
                commands=tuple(c for c in commands if c.command_id not in deferred_tp_ids
                               or c.status is not S.PREPARED),
                accepted_order_ids=accepted_order_ids,
            ),
            timeout=timeout_seconds,
        )
        if (
            (
                s.phase in {P.PREVIEWED, P.TP_CANCELLING}
                or any(
                    c.kind is K.OWNER_REDUCE
                    and c.status is S.PREPARED
                    and getattr(c.payload, "owner_operation_id", None)
                    == row["operation_id"]
                    for c in commands
                )
            )
            and not observation.facts.stop_triggered
            and observation.facts.position_quantity == a.position_qty
        ):
            original_exit_reason = await asyncio.wait_for(
                read_original_operation_exit(
                    facts_source,
                    aggregate=a,
                    profile=profile.profile,
                    rules=rules,
                    references=references,
                    now_ms=now_ms,
                ),
                timeout=timeout_seconds,
            )
    except Exception as exc:  # noqa: BLE001 - no facts means no new exchange effect.
        async with uow_factory() as u:
            latest_op = await u.owner_position_operations.get(
                row["operation_id"], for_update=True
            )
            if latest_op and latest_op["version"] == row["version"]:
                await u.owner_position_operations.transition(
                    operation_id=row["operation_id"],
                    expected_version=row["version"],
                    state="restoring_original_tp"
                    if restoring_tp
                    else "facts_unavailable",
                    payload=row["payload"],
                    reason=owner_operation_fact_blocker(exc),
                    now_ms=now_ms,
                )
        return "facts_unavailable"
    now_ms = max(now_ms, observation.facts.observed_at_ms)
    async with uow_factory() as u:
        latest = await u.aggregates.get_for_update(row["ticket_id"])
        op = await u.owner_position_operations.get(row["operation_id"], for_update=True)
        if (
            latest is None
            or latest.version != a.version
            or op is None
            or op["version"] != row["version"]
        ):
            return "source_changed"
        a = latest
        payload = {
            **row["payload"],
            "facts": observation.facts.model_dump(mode="json"),
            "protection_close_position": observation.protection_close_position,
        }
        f = observation.facts
        if (
            f.reduction_operation_id == row["operation_id"]
            and f.reduction_state == "terminal"
            and 0 < f.reduction_filled_quantity <= s.preview.reduction_quantity
        ):
            payload["result"] = {
                "execution_state": "filled" if f.reduction_filled_quantity == s.preview.reduction_quantity else "partial",
                "requested_quantity": str(s.preview.reduction_quantity),
                "executed_quantity": str(f.reduction_filled_quantity),
                "remaining_quantity": str(f.position_quantity),
                "management_state": "pending",
            }
        ids = list(payload.get("prepared_command_ids", []))
        ids.extend(
            c.command_id
            for c in commands
            if getattr(c.payload, "owner_operation_id", None) == row["operation_id"]
            and c.command_id not in ids
        )

        def fields():
            return {
                "event_id": f"event:{a.identity.ticket_id}:{a.last_event_sequence + 1}",
                "ticket_id": a.identity.ticket_id,
                "sequence": a.last_event_sequence + 1,
                "occurred_at_ms": now_ms,
            }

        async def save(stage, reason, *, completed=False):
            payload["prepared_command_ids"] = ids
            payload["reduction_state"] = s.model_dump(mode="json")
            await u.owner_position_operations.transition(
                operation_id=row["operation_id"],
                expected_version=row["version"],
                state=stage,
                payload=payload,
                reason=reason,
                now_ms=now_ms,
                completed=completed,
            )

        if (
            row["state"] == "restoring_original_tp"
            and a.tp1_exchange_order_id != s.preview.cancel_tp_order_id
        ):
            await save(
                "failed", "reduction_not_executed_original_tp_restored", completed=True
            )
            return "restored"
        if restoring_tp:
            restored = [
                c
                for c in commands
                if c.kind is K.TAKE_PROFIT
                and c.command_id in payload.get("restoration_command_ids", [])
            ]
            if any(
                c.status is S.PREPARED and c.deadline_at_ms <= now_ms for c in restored
            ):
                for c in restored:
                    if c.status is S.PREPARED:
                        await u.exchange_commands.mark_prepared_superseded(
                            command_id=c.command_id,
                            observed_at_ms=now_ms,
                            reason="original_tp_restore_unstarted_expired",
                        )
                review = ManagementReviewRequired(
                    **fields(),
                    evidence_id="restore-expired:" + row["operation_id"],
                    reason="original_tp_restore_requires_repreview",
                )
                await u.commit_reduction(
                    event=review,
                    reduction=reduce_event(a, review),
                    expected_version=a.version,
                )
                await save("review_required", "original_tp_restore_unstarted_expired")
                return "review_required"
            # Only normal lifecycle-created successors of this exact original plan
            # may replace a reconciled-absent restoration command.
            started = payload.get("restoration_started_at_ms", row["created_at_ms"])
            for c in commands:
                if (
                    c.kind is K.TAKE_PROFIT
                    and c.status is S.PREPARED
                    and c.created_at_ms >= started
                    and isinstance(c.payload, OrderCommandPayload)
                    and c.payload.owner_operation_id is None
                    and c.payload.quantity == a.tp1_target_qty
                    and c.payload.limit_price == s.preview.tp_trigger_price
                    and c.command_id not in payload.get("restoration_command_ids", [])
                ):
                    payload.setdefault("restoration_command_ids", []).append(
                        c.command_id
                    )
            await save("restoring_original_tp", "original_tp_restore_in_progress")
            return "restoring_original_tp"
        from src.trading_kernel.application.handoff_owner_operation import (
            handoff_natural_tp,
        )

        if await handoff_natural_tp(
            u,
            aggregate=a,
            row=row,
            commands=commands,
            filled_quantity=observation.facts.tp_filled_quantity,
            position_quantity=observation.facts.position_quantity,
            now_ms=now_ms,
        ):
            return "handed_to_lifecycle"
        if pending_protection:
            await save("protection_converting", "protection_truth_pending")
            return "protection_converting"
        authority = await u.owner_position_operations.authority_current(
            row, management_revision=a.management_revision
        )
        # A Stop/quantity race is a verified-management incident, never forged MANUAL.
        if observation.facts.stop_triggered or observation.facts.position_quantity == 0:
            await u.aggregates.expedite_reconciliation(
                a.identity.ticket_id, due_at_ms=now_ms
            )
            if a.management_mode.value == "AUTO":
                ev = ManagementReviewRequired(
                    **fields(),
                    evidence_id=f"owner-stop-race:{row['operation_id']}:{now_ms}",
                    reason="owner_operation_stop_or_flat_requires_closure",
                )
                await u.commit_reduction(
                    event=ev, reduction=reduce_event(a, ev), expected_version=a.version
                )
            await save("review_required", "stop_or_flat_requires_readonly_closure")
            return "review_required"
        if original_exit_reason is not None:
            for c in commands:
                if (
                    c.status is S.PREPARED
                    and getattr(c.payload, "owner_operation_id", None)
                    == row["operation_id"]
                ):
                    await u.exchange_commands.mark_prepared_superseded(
                        command_id=c.command_id,
                        observed_at_ms=now_ms,
                        reason="original_strategy_exit_priority",
                    )
            exit_event = ExitRequested(**fields(), reason=original_exit_reason)
            await u.commit_reduction(
                event=exit_event,
                reduction=reduce_event(a, exit_event),
                expected_version=a.version,
            )
            await save("closure_pending", "original_strategy_exit_priority")
            return "closure_pending"
        if not authority:
            for c in commands:
                if (
                    c.status is S.PREPARED
                    and getattr(c.payload, "owner_operation_id", None)
                    == row["operation_id"]
                ):
                    await u.exchange_commands.mark_prepared_superseded(
                        command_id=c.command_id,
                        observed_at_ms=now_ms,
                        reason="owner_authority_revoked_before_send",
                    )
            if observation.facts.reduction_state == "not_sent":
                s = s.model_copy(update={"phase": P.RESTORE_REQUIRED})
        failed_protection = [
            c
            for c in commands
            if c.kind is K.REPLACE_PROTECTION
            and isinstance(c.payload, OrderCommandPayload)
            and c.payload.owner_operation_id == row["operation_id"]
            and c.status in {S.REJECTED, S.SUPERSEDED}
        ]
        if failed_protection and not observation.protection_close_position:
            await save(
                "failed",
                "protection_conversion_rejected_original_plan_kept",
                completed=True,
            )
            return "failed"
        if (
            "intent" in payload and now_ms >= payload["start_deadline_ms"]
            and s.phase is P.PREVIEWED and not ids
        ):
            await save("expired", "owner_start_window_expired", completed=True)
            return "expired"
        if not observation.protection_close_position and s.phase is P.PREVIEWED:
            if (
                not authority
                or observation.facts.position_quantity != s.preview.source_quantity
            ):
                await save("rejected", "authority_or_position_changed", completed=True)
                return "rejected"
            protection_event = OwnerProtectionRequested(
                **fields(),
                operation_id=row["operation_id"],
                stop_price=s.preview.stop_price,
                close_position=True,
                source_watermark_ms=observation.facts.observed_at_ms,
            )
            await u.commit_reduction(
                event=protection_event,
                reduction=reduce_event(a, protection_event),
                expected_version=a.version,
            )
            added = [
                c.command_id
                for c in await u.exchange_commands.list_for_ticket(a.identity.ticket_id)
                if isinstance(c.payload, OrderCommandPayload)
                and c.payload.owner_operation_id == row["operation_id"]
            ]
            ids.extend(c for c in added if c not in ids)
            await save("protection_converting", "confirm_close_all_before_reduction")
            return "protection_converting"
        if observation.protection_close_position and s.phase is P.PREVIEWED:
            s = s.model_copy(
                update={
                    "confirmed_protection_order_id": a.active_stop_exchange_order_id
                }
            )
        if s.phase is P.RESTORE_REQUIRED:
            f = observation.facts
            if (
                f.reduction_state in {"unknown", "working"}
                or f.unresolved_other_command
            ):
                await save("restore_required", "command_truth_pending")
                return "restore_required"
            if (
                f.reduction_filled_quantity > 0
                or f.position_quantity != s.preview.source_quantity
                or f.tp_filled_quantity != s.preview.source_tp_filled_quantity
            ):
                await save("review_required", "restore_position_or_fill_changed")
                return "review_required"
            if f.tp_state == "open" or s.preview.cancel_tp_order_id is None:
                await save(
                    "rejected",
                    "operation_not_executed_original_plan_kept",
                    completed=True,
                )
                return "rejected"
            if f.tp_state != "cancelled":
                await save("restore_required", "tp_terminal_unproven")
                return "restore_required"
            target = s.preview.tp_trigger_price
            if target is None or (
                f.current_price >= target
                if s.preview.side == "long"
                else f.current_price <= target
            ):
                await save("review_required", "original_tp_restore_price_crossed")
                return "review_required"
            ev_restore = OwnerAutomaticTpRestoreRequested(
                **fields(),
                operation_id=row["operation_id"],
                original_tp_order_id=s.preview.cancel_tp_order_id,
            )
            await u.commit_reduction(
                event=ev_restore,
                reduction=reduce_event(a, ev_restore),
                expected_version=a.version,
            )
            payload["restoration_started_at_ms"] = now_ms
            payload["restoration_command_ids"] = [
                c.command_id
                for c in await u.exchange_commands.list_for_ticket(row["ticket_id"])
                if c.kind is K.TAKE_PROFIT and c.status is S.PREPARED
            ]
            await save("restoring_original_tp", "restore_unexecuted_original_plan")
            return "restoring_original_tp"
        decision = advance_owner_reduction(s, observation.facts, now_ms=now_ms)
        s = decision.state

        async def prepare(kind, terms):
            generation = await u.exchange_commands.next_generation(
                ticket_id=a.identity.ticket_id, kind=kind
            )
            cid = build_command_id(
                ticket_id=a.identity.ticket_id, kind=kind, generation=generation
            )
            c = ExchangeCommand(
                command_id=cid,
                ticket_identity=a.identity,
                management_revision=a.management_revision,
                kind=kind,
                generation=generation,
                idempotency_key=cid,
                venue_client_order_id=build_venue_client_order_id(cid),
                payload=terms,
                status=S.PREPARED,
                created_at_ms=now_ms,
                deadline_at_ms=min(now_ms + 30_000, payload.get("start_deadline_ms", now_ms + 30_000))
                if kind is K.OWNER_REDUCE else now_ms + 30_000,
            )
            await u.exchange_commands.add(c)
            ids.append(cid)

        if decision.action == "cancel_original_tp" and authority:
            assert decision.cancel_order_id is not None
            await prepare(
                K.CANCEL_ORDER,
                CancelCommandPayload(
                    exchange_order_id=decision.cancel_order_id,
                    order_namespace="regular",
                    purpose="owner_tp",
                    owner_operation_id=row["operation_id"],
                ),
            )
        elif decision.action == "prepare_reduction" and authority:
            existing = [
                c
                for c in commands
                if c.kind is K.OWNER_REDUCE
                and isinstance(c.payload, OrderCommandPayload)
                and c.payload.owner_operation_id == row["operation_id"]
            ]
            if not existing:
                await prepare(
                    K.OWNER_REDUCE,
                    OrderCommandPayload(
                        side="sell" if s.preview.side == "long" else "buy",
                        quantity=s.preview.reduction_quantity,
                        order_type="market",
                        reduce_only=True,
                        owner_operation_id=row["operation_id"],
                    ),
                )
        elif decision.action == "record_reduction":
            if observation.proof is None:
                await save("review_required", "actual_reduction_proof_missing")
                return "review_required"
            for c in commands:
                if c.command_id in deferred_tp_ids and c.status is S.PREPARED:
                    await u.exchange_commands.mark_prepared_superseded(
                        command_id=c.command_id, observed_at_ms=now_ms,
                        reason="owner_reduction_replaces_unplaced_tp",
                    )
            await record_owner_reduction(u, proof=observation.proof, now_ms=now_ms)
            payload["result"] = {
                "execution_state": "filled" if s.actual_reduction_quantity == s.preview.reduction_quantity else "partial",
                "requested_quantity": str(s.preview.reduction_quantity),
                "executed_quantity": str(s.actual_reduction_quantity),
                "remaining_quantity": str(observation.proof.remaining_quantity),
                "management_state": s.phase.value,
            }
            await save(s.phase.value, decision.reason, completed=True)
            return "completed"
        elif decision.action == "restore_or_reconcile":
            # Never place a replacement quantity exit while a close is unresolved.
            # Restoration is an explicit next phase, not a blind retry.
            await save("restore_required", decision.reason)
            return "restore_required"
        await save(
            s.phase.value, decision.reason, completed=decision.action == "rejected"
        )
        return s.phase.value
