"""One bounded read-only observation per eligible Ticket, inside Reconciliation."""

from __future__ import annotations

import asyncio
from typing import Protocol

from src.trading_kernel.application.management_intents import system_intents_for
from src.trading_kernel.application.observe_trade_management import (
    observe_trade_management,
)
from src.trading_kernel.application.ports import (
    MonitorOwnerStatus,
    MonitorStateRecord,
    UnitOfWorkFactory,
)
from src.trading_kernel.application.reconcile_ticket import (
    ReconcileTicketRequest,
    reconcile_ticket,
)
from src.trading_kernel.domain.events import (
    ManagementReviewCleared,
    ManagementReviewRequired,
)
from src.trading_kernel.domain.management_observation import (
    ManagementScan,
    ManagementScanRequest,
)
from src.trading_kernel.domain.reducer import reduce_event
from src.trading_kernel.domain.trade_management import (
    ManagementDecision,
    ManagementMode,
    OrderTerms,
    classify_order_evidence,
)


class ManagementObservationSource(Protocol):
    async def read_management_scan(
        self, request: ManagementScanRequest
    ) -> ManagementScan: ...


async def observe_management_once(
    uow_factory: UnitOfWorkFactory,
    source: ManagementObservationSource,
    *,
    ticket_id: str,
    now_ms: int,
    timeout_seconds: float = 15,
) -> str:
    async with uow_factory() as u:
        a = await u.aggregates.get(ticket_id)
        if a is None:
            return "ticket_absent"
        if a.management_mode is not ManagementMode.MANUAL and (
            a.active_stop_exchange_order_id is None
            or a.post_fill_stress_status != "passed"
        ):
            return "initial_handover_pending"
        commands = await u.management.command_rows(ticket_id)
        if any(
            c["status"] in ("claimed", "dispatch_started", "outcome_unknown")
            for c in commands
        ):
            return "command_truth_pending"
        coverage = await u.management.get_coverage(ticket_id)
        since = (
            a.ticket.created_at_ms
            if coverage is None or a.management_mode is ManagementMode.REVIEW_REQUIRED
            else max(a.ticket.created_at_ms, coverage["covered_until_ms"] - 1000)
        )
        req = ManagementScanRequest(
            ticket_id=ticket_id,
            domain=a.identity.netting_domain,
            since_ms=since,
            now_ms=now_ms,
            known_orders=tuple(
                OrderTerms.model_validate(r["terms"])
                for r in a.management_orders
                if r.get("terms")
            ),
        )
    try:
        batch = await asyncio.wait_for(
            source.read_management_scan(req), timeout=timeout_seconds
        )
        if (
            batch.ticket_id != ticket_id
            or batch.snapshot.netting_domain != req.domain
            or not since <= batch.covered_until_ms <= now_ms
            or batch.snapshot.observed_at_ms > now_ms
            or (batch.complete and batch.covered_until_ms != now_ms)
            or any(
                item.terms.identity[:4] != (
                    req.domain.venue_id, req.domain.account_id,
                    req.domain.exchange_instrument_id, req.domain.position_side,
                )
                or not item.exchange_event_at_ms <= item.received_at_ms <= now_ms
                for item in batch.evidence
            )
        ):
            raise ValueError("management batch identity/time mismatch")
    except Exception as exc:  # noqa: BLE001 - observation failures must fence facts, not trade.
        async with uow_factory() as u:
            await u.management.save_coverage(
                ticket_id,
                through_ms=since,
                complete=False,
                reason=f"collector:{type(exc).__name__}",
                observed_at_ms=now_ms,
            )
            a = await u.aggregates.get_for_update(ticket_id)
            if (
                a is not None
                and a.management_mode is ManagementMode.AUTO
                and a.active_stop_exchange_order_id is not None
            ):
                ev = ManagementReviewRequired(
                    event_id=f"management-gap:{ticket_id}:{a.version}",
                    ticket_id=ticket_id,
                    sequence=a.last_event_sequence + 1,
                    occurred_at_ms=now_ms,
                    evidence_id=f"gap:{now_ms}",
                    reason="collector_gap",
                )
                await u.commit_reduction(
                    event=ev, reduction=reduce_event(a, ev), expected_version=a.version
                )
        return "management_facts_unavailable"
    async with uow_factory() as u:
        current = await u.aggregates.get_for_update(ticket_id)
        if current is None:
            return "ticket_absent"
        for item in batch.evidence:
            if item.exchange_event_at_ms < current.ticket.created_at_ms:
                continue
            await observe_trade_management(
                u,
                ticket_id=ticket_id,
                evidence=item,
                now_ms=now_ms,
            )
        current = await u.aggregates.get_for_update(ticket_id)
        assert current is not None
        await u.management.save_coverage(
            ticket_id,
            through_ms=batch.covered_until_ms,
            complete=batch.complete,
            reason=batch.reason,
            observed_at_ms=now_ms,
        )
        decisive = all(
            classify_order_evidence(
                item, system_intents=system_intents_for(item, commands)
            ).decision
            in (ManagementDecision.SYSTEM, ManagementDecision.NATURAL)
            for item in batch.evidence
            if item.exchange_event_at_ms >= current.ticket.created_at_ms
        )
        # An empty/partial history is not affirmative coverage of our orders.
        required_orders = {
            str((row["result_payload"] or {}).get("exchange_order_id"))
            for row in await u.management.command_rows(ticket_id)
            if row["status"] in ("accepted", "reconciled_accepted")
            and (row["result_payload"] or {}).get("exchange_order_id") is not None
        }
        observed_orders = {item.terms.exchange_order_id for item in batch.evidence}
        if (
            current.management_mode is ManagementMode.REVIEW_REQUIRED
            and current.management_reason
            in (
                "collector_gap",
                "order_history_incomplete_or_command_unknown",
                "kernel_order_not_matched_to_command",
                "known_order_creation_time_or_terms_drift",
            )
            and batch.complete
            and decisive
            and bool(required_orders)
            and required_orders <= observed_orders
            and req.since_ms == current.ticket.created_at_ms
        ):
            cleared_event = ManagementReviewCleared(
                event_id=f"management-clear:{ticket_id}:{current.version}",
                ticket_id=ticket_id,
                sequence=current.last_event_sequence + 1,
                occurred_at_ms=now_ms,
                coverage_from_ms=req.since_ms,
                coverage_until_ms=batch.covered_until_ms,
            )
            await u.commit_reduction(
                event=cleared_event,
                reduction=reduce_event(current, cleared_event),
                expected_version=current.version,
            )
            current = await u.aggregates.get_for_update(ticket_id)
            assert current is not None
        if (
            current.management_mode is ManagementMode.MANUAL
            and current.status.value
            not in ("settlement_pending", "review_pending", "terminal")
        ):
            await reconcile_ticket(
                u,
                ReconcileTicketRequest(
                    ticket_id=ticket_id,
                    snapshot=batch.snapshot.model_copy(
                        update={
                            "orders_complete": batch.complete
                            and batch.snapshot.orders_complete
                        }
                    ),
                ),
            )
        if batch.complete:
            await u.management.refresh_orders(
                ticket_id,
                [o.model_dump(mode="json") for o in batch.snapshot.open_orders],
            )
        elif (
            current.management_mode is ManagementMode.AUTO
            and current.active_stop_exchange_order_id is not None
        ):
            ev = ManagementReviewRequired(
                event_id=f"management-gap:{ticket_id}:{current.version}",
                ticket_id=ticket_id,
                sequence=current.last_event_sequence + 1,
                occurred_at_ms=now_ms,
                evidence_id=f"gap:{now_ms}",
                reason="collector_gap",
            )
            await u.commit_reduction(
                event=ev,
                reduction=reduce_event(current, ev),
                expected_version=current.version,
            )
        await u.monitors.save_if_changed(
            MonitorStateRecord(
                monitor_key=f"management-feed:{ticket_id}",
                owner_status=MonitorOwnerStatus.RUNNING
                if batch.complete
                else MonitorOwnerStatus.TEMPORARILY_UNAVAILABLE,
                summary="订单观察完整"
                if batch.complete
                else "订单观察缺口；新增准入受限",
                intervention="none" if batch.complete else "verify_order_history",
                ticket_id=ticket_id,
                updated_at_ms=now_ms,
            )
        )
    return current.management_mode.value
