"""One bounded durable-receiver tick hosted by Reconciliation, not a new writer."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from src.trading_kernel.domain.product_identity import PRODUCT_ID


def management_scope(venue_id: str, account_id: str) -> str:
    return f"{PRODUCT_ID}:{venue_id}:{account_id}"


class FeedTickResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    status: str
    detail: str | None = None


async def persist_management_feed_once(
    uow_factory, source, *, worker_id, runtime_commit, now_ms, clock_ms
):
    from src.trading_kernel.application.runtime_fence import runtime_writer_is_certified
    from src.trading_kernel.infrastructure.runtime_identity import (
        CURRENT_SCHEMA_REVISION,
    )

    if not await runtime_writer_is_certified(
        uow_factory,
        worker_id=worker_id,
        runtime_commit=runtime_commit,
        schema_revision=CURRENT_SCHEMA_REVISION,
        observed_at_ms=now_ms,
    ):
        return FeedTickResult(status="runtime_fenced")
    states = source.management_feed_batches()
    blocked_reasons = set()
    # Receipt durability must not wait for an older event's canonical application.
    for state in states:
        scope = management_scope(state["venue_id"], state["account_id"])
        async with uow_factory() as u:
            current = await u.management.get_feed(scope)
            if (
                current is not None
                and await u.management.received_epoch(scope, current["epoch_id"])
                is None
            ):
                await u.management.persist_received_batch(
                    scope_key=scope,
                    epoch_id=current["epoch_id"],
                    events=[],
                    connected_at_ms=current["connected_at_ms"],
                    now_ms=clock_ms(),
                    worker_id=worker_id,
                )
            watermark = await u.management.persist_received_batch(
                scope_key=scope,
                epoch_id=state["epoch_id"],
                events=state["events"],
                connected_at_ms=state["connected_at_ms"],
                now_ms=clock_ms(),
                gap_reason=state["gap_reason"],
                connection_observed_at_ms=state.get("connection_observed_at_ms"),
                backlog_pending=state["backlog_pending"],
                worker_id=worker_id,
            )
        source.acknowledge_management_events(state["epoch_id"], watermark)
    processed_scopes = set()
    for state in states:
        scope = management_scope(state["venue_id"], state["account_id"])
        if scope in processed_scopes:
            continue
        processed_scopes.add(scope)
        async with uow_factory() as u:
            await u.management.lock_receiver(scope)
            current = await u.management.get_feed(scope, for_update=True)
            # Receipts can arrive while runtime certification or ownership
            # locking is awaited. Check processing time, not tick start.
            now_ms = clock_ms()

            async def apply_observer(ticket_id, evidence, *, observed_at_ms=now_ms):
                from src.trading_kernel.application.observe_trade_management import (
                    is_flat_closure_observation,
                    observe_trade_management,
                )
                from src.trading_kernel.domain.trade_management import ManagementMode

                a = await u.aggregates.get_for_update(ticket_id)
                if a is None:
                    return False
                if evidence.exchange_event_at_ms < a.ticket.created_at_ms:
                    return True
                if is_flat_closure_observation(a):
                    await observe_trade_management(
                        u, ticket_id=ticket_id, evidence=evidence, now_ms=observed_at_ms
                    )
                    return True
                if a.management_mode is not ManagementMode.MANUAL and (
                    a.active_stop_exchange_order_id is None
                    or a.post_fill_stress_status != "passed"
                ):
                    return False
                commands = await u.management.pending_command_rows(ticket_id)
                if any(
                    c["status"] in ("claimed", "dispatch_started", "outcome_unknown")
                    for c in commands
                ):
                    return False
                from src.trading_kernel.application.management_intents import (
                    system_intents_for,
                )

                exact = await u.management.command_rows_for_order(
                    ticket_id,
                    evidence.terms.order_namespace,
                    evidence.terms.exchange_order_id,
                )
                own = system_intents_for(
                    evidence, exact
                ) or await u.management.child_system_intents(ticket_id, evidence)
                if (
                    evidence.terms.order_namespace == "regular"
                    and not own
                    and a.management_mode is not ManagementMode.MANUAL
                    and not await u.management.has_evidence(
                        ticket_id, evidence.evidence_id
                    )
                ):
                    return False
                await observe_trade_management(
                    u, ticket_id=ticket_id, evidence=evidence, now_ms=observed_at_ms
                )
                return True

            if current is not None:
                active_receipt = await u.management.received_epoch(
                    scope, current["epoch_id"]
                )
                await u.management.persist_stream_batch(
                    scope_key=scope,
                    epoch_id=current["epoch_id"],
                    events=[],
                    connected_at_ms=current["connected_at_ms"],
                    now_ms=now_ms,
                    apply_observer=apply_observer,
                    account_id=state["account_id"],
                    application_runtime_commit=runtime_commit,
                    replay_only=True,
                    worker_id=worker_id,
                    backlog_pending=False
                    if active_receipt is None
                    else active_receipt["backlog_pending"],
                )
                current = await u.management.get_feed(scope)
                if (
                    current["applied_watermark"] < current["persisted_watermark"]
                    or active_receipt is not None
                    and active_receipt["backlog_pending"]
                ):
                    blocked_reasons.add("previous_epoch_unapplied")
                    continue
            pending = await u.management.next_received_epoch(
                scope, exclude_epoch=None if current is None else current["epoch_id"]
            )
            target = (
                state["epoch_id"]
                if pending is None and current is None
                else pending["epoch_id"]
                if pending
                else current["epoch_id"]
            )
            if current is None or current["epoch_id"] != target:
                await u.management.start_feed(
                    scope_key=scope,
                    epoch_id=target,
                    worker_id=worker_id,
                    runtime_commit=runtime_commit,
                    now_ms=now_ms,
                )
            # Target owns its persisted receipt facts, not the current socket's
            # connection/health metadata after a restart.
            receipt = await u.management.received_epoch(scope, target)
            watermark = await u.management.persist_stream_batch(
                scope_key=scope,
                epoch_id=target,
                events=[],
                connected_at_ms=None if receipt is None else receipt["connected_at_ms"],
                now_ms=now_ms,
                gap_reason=None if receipt is None else receipt["gap_reason"],
                worker_id=worker_id,
                backlog_pending=False
                if receipt is None
                else receipt["backlog_pending"],
                apply_observer=apply_observer,
                account_id=state["account_id"],
                application_runtime_commit=runtime_commit,
                replay_only=True,
            )
            from src.trading_kernel.application.ports import (
                MonitorOwnerStatus,
                MonitorStateRecord,
            )

            ready = await u.management.feed_ready(
                scope, now_ms=now_ms, runtime_commit=runtime_commit, clock_ms=clock_ms
            )
            feed = await u.management.get_feed(scope)
            if not ready:
                blocked_reasons.add(
                    (feed["health_reason"] or "management_receiver_not_ready")
                    if feed
                    else "management_feed_missing"
                )
            await u.monitors.save_if_changed(
                MonitorStateRecord(
                    monitor_key=f"management-feed:{scope}",
                    owner_status=MonitorOwnerStatus.RUNNING
                    if ready
                    else MonitorOwnerStatus.TEMPORARILY_UNAVAILABLE,
                    summary="管理接收已就绪"
                    if ready
                    else f"管理接收受限：{feed['health_reason'] if feed else 'missing'}",
                    intervention="none"
                    if ready
                    else "系统重连或重试；保持普通自动处置受限",
                    updated_at_ms=now_ms,
                )
            )
        # Raw receipts were acknowledged after their independent transaction.
        if feed is not None and feed["health_reason"] in {
            "management_stream_protocol_invalid",
            "management_receive_sequence_gap",
            "management_receive_queue_overflow",
            "management_epoch_queue_overflow",
            "private_stream_disconnected",
            "private_stream_watch_failed",
            "private_stream_close_failed",
            "management_receiver_protocol_gap",
        }:
            restart = getattr(source, "restart_management_transport", None)
            if callable(restart):
                await restart(state["epoch_id"])
    return FeedTickResult(
        status=(
            "management_feed_recovering"
            if blocked_reasons
            else "management_feed_persisted"
        )
        if states
        else "management_feed_unavailable",
        detail=",".join(sorted(blocked_reasons)) if blocked_reasons else None,
    )
