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
    uow_factory, source, *, worker_id, runtime_commit, now_ms
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
    for state in states:
        scope = management_scope(state["venue_id"], state["account_id"])
        async with uow_factory() as u:
            current = await u.management.get_feed(scope)
            if current is None or current["epoch_id"] != state["epoch_id"]:
                await u.management.start_feed(
                    scope_key=scope,
                    epoch_id=state["epoch_id"],
                    worker_id=worker_id,
                    runtime_commit=runtime_commit,
                    now_ms=now_ms,
                )

            async def apply_observer(ticket_id, evidence):
                from src.trading_kernel.application.observe_trade_management import (
                    observe_trade_management,
                )
                from src.trading_kernel.domain.trade_management import ManagementMode

                a = await u.aggregates.get_for_update(ticket_id)
                if a is None:
                    return False
                if evidence.exchange_event_at_ms < a.ticket.created_at_ms:
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
                    u, ticket_id=ticket_id, evidence=evidence, now_ms=now_ms
                )
                return True

            watermark = await u.management.persist_stream_batch(
                scope_key=scope,
                epoch_id=state["epoch_id"],
                events=state["events"],
                connected_at_ms=state["connected_at_ms"],
                now_ms=now_ms,
                gap_reason=state["gap_reason"],
                worker_id=worker_id,
                backlog_pending=state["backlog_pending"],
                apply_observer=apply_observer,
                account_id=state["account_id"],
            )
            from src.trading_kernel.application.ports import (
                MonitorOwnerStatus,
                MonitorStateRecord,
            )

            ready = await u.management.feed_ready(
                scope, now_ms=now_ms, runtime_commit=runtime_commit
            )
            feed = await u.management.get_feed(scope)
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
        # Acknowledge only after __aexit__ has committed all raw input and watermarks.
        source.acknowledge_management_events(state["epoch_id"], watermark)
        if feed is not None and feed["health_reason"] in {
            "management_stream_protocol_invalid",
            "management_receive_sequence_gap",
        }:
            restart = getattr(source, "restart_management_transport", None)
            if callable(restart):
                await restart(state["epoch_id"])
    return FeedTickResult(
        status="management_feed_persisted" if states else "management_feed_unavailable"
    )
