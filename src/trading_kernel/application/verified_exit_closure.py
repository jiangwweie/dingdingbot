"""One proof-gated accounting closure for routine reconciliation and maintenance."""

from __future__ import annotations

from decimal import Decimal

from src.trading_kernel.application.ports import KernelUnitOfWork
from src.trading_kernel.domain.aggregate import AggregateStatus
from src.trading_kernel.domain.events import VerifiedExitClosed
from src.trading_kernel.domain.reducer import reduce_event
from src.trading_kernel.domain.verified_exit_closure import VerifiedExitClosureProof

CAUSAL_CLOSURE_INCIDENTS = frozenset(
    {"lifecycle_facts_contradictory", "lifecycle_facts_unavailable"}
)


async def record_verified_exit(
    uow: KernelUnitOfWork, *, proof: VerifiedExitClosureProof, now_ms: int
) -> str:
    proof = VerifiedExitClosureProof.model_validate(proof.model_dump())
    a = await uow.aggregates.get_for_update(proof.ticket_id)
    if a is None or a.identity.netting_domain != proof.domain:
        raise ValueError("closure Ticket identity differs")
    if a.status in {
        AggregateStatus.SETTLEMENT_PENDING,
        AggregateStatus.REVIEW_PENDING,
        AggregateStatus.TERMINAL,
    }:
        events = await uow.events.list_for_ticket(proof.ticket_id)
        closed = next((e for e in events if isinstance(e, VerifiedExitClosed)), None)
        if closed is None or closed.proof.content_digest() != proof.content_digest():
            raise ValueError("closure has unrelated predecessor or changed proof")
        return a.status.value
    if (
        a.version != proof.expected_version
        or a.management_revision != proof.management_revision
    ):
        raise ValueError("closure source version changed")
    if not proof.observed_at_ms <= now_ms < proof.valid_until_ms:
        raise ValueError("closure proof expired")
    rows = await uow.management.command_rows(proof.ticket_id)
    if any(
        r["status"] in {"prepared", "claimed", "dispatch_started", "outcome_unknown"}
        for r in rows
    ):
        raise ValueError("closure has unknown command")
    references = await uow.exchange_commands.list_order_references(proof.ticket_id)
    if {r.command_id: r for r in references} != {
        o.reference.command_id: o.reference for o in proof.orders
    }:
        raise ValueError("closure does not cover exact durable orders")
    commands = {r["command_id"]: r for r in rows}
    for o in proof.orders:
        row = commands[o.reference.command_id]
        p = row["request_payload"]
        t = o.terms
        from src.trading_kernel.domain.trade_management import OrderTerms

        saved = row["result_payload"].get("management_baseline") or row[
            "result_payload"
        ].get("venue_payload", {}).get("management_baseline")
        if saved is not None and OrderTerms.model_validate(saved) != t:
            raise ValueError("closure terms differ from persisted baseline")
        if (
            t.reduce_only != p["reduce_only"]
            or t.close_position
            or t.time_in_force != (p.get("time_in_force") or "GTC")
        ):
            raise ValueError("closure order instruction differs")
        if (
            row["status"] not in {"accepted", "reconciled_accepted"}
            or t.side != p["side"]
            or t.order_type.lower() != p["order_type"]
            or t.quantity != Decimal(p["quantity"])
        ):
            raise ValueError("closure terms differ from original command")
        for term, key in [(t.price, "limit_price"), (t.trigger_price, "stop_price")]:
            if term != (None if p.get(key) is None else Decimal(p[key])):
                raise ValueError("closure price differs from original command")
    incidents = await uow.incidents.list_open_for_ticket(proof.ticket_id)
    if set(proof.incident_ids) != {i.incident_id for i in incidents} or any(
        i.incident_kind not in CAUSAL_CLOSURE_INCIDENTS for i in incidents
    ):
        raise ValueError("closure causal incident set differs")
    event = VerifiedExitClosed(
        event_id=f"event:{proof.ticket_id}:{a.last_event_sequence + 1}",
        ticket_id=proof.ticket_id,
        sequence=a.last_event_sequence + 1,
        occurred_at_ms=now_ms,
        proof=proof,
    )
    await uow.commit_reduction(
        event=event, reduction=reduce_event(a, event), expected_version=a.version
    )
    await uow.positions.upsert(ticket_id=proof.ticket_id, snapshot=proof.snapshot)
    from src.trading_kernel.application.ports import (
        MonitorOwnerStatus,
        MonitorStateRecord,
    )

    await uow.monitors.save_if_changed(
        MonitorStateRecord(
            monitor_key=f"lifecycle-facts:{proof.ticket_id}",
            owner_status=MonitorOwnerStatus.RUNNING,
            summary="准确退出已核实；交易进入只读结算",
            intervention="none",
            ticket_id=proof.ticket_id,
            updated_at_ms=now_ms,
        )
    )
    return "settlement_pending"


async def settle_verified_exit(
    uow: KernelUnitOfWork, *, proof: VerifiedExitClosureProof, now_ms: int
) -> str:
    from src.trading_kernel.application.settle_ticket import (
        RecordTradeReviewRequest,
        SettleTicketRequest,
        record_trade_review,
        settle_ticket,
    )

    state = await record_verified_exit(uow, proof=proof, now_ms=now_ms)
    if state == "terminal":
        return state
    if state == "settlement_pending":
        await settle_ticket(
            uow, SettleTicketRequest(ticket_id=proof.ticket_id, settled_at_ms=now_ms)
        )
    entry_value = sum((f.quantity * f.price for f in proof.entry_fills), Decimal(0))
    exit_value = sum((f.quantity * f.price for f in proof.exit_fills), Decimal(0))
    gross = (exit_value - entry_value) * (
        1 if proof.domain.position_side == "long" else -1
    )
    await record_trade_review(
        uow,
        RecordTradeReviewRequest(
            ticket_id=proof.ticket_id,
            review_id=f"review:verified-exit:{proof.ticket_id}",
            outcome=proof.exit_reason,
            metrics={
                "exit_reason": proof.exit_reason,
                "gross_realized_pnl_quote": str(gross),
                "net_pnl_quote": None,
                "economics_completeness": "incomplete_evidence",
                "unavailable_reason": "fees_and_funding_not_yet_valued",
                "entry_quantity": str(proof.entry_quantity),
                "exit_quantity": str(proof.exit_quantity),
                "verified_exit_proof_digest": proof.digest(),
                "verified_exit_proof": proof.model_dump(mode="json"),
            },
            decision_impact={
                "status": "recorded",
                "economics_completeness": "incomplete_evidence",
                "source": "verified_exit_closure",
            },
            recorded_at_ms=now_ms,
        ),
    )
    return "terminal"
