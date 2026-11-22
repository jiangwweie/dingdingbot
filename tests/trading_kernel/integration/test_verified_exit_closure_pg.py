
import pytest
import sqlalchemy as sa

from src.trading_kernel.application.verified_exit_closure import record_verified_exit
from src.trading_kernel.domain.reducer import reduce_event
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from tests.trading_kernel.support.verified_exit import protected_proof as setup


@pytest.mark.asyncio
@pytest.mark.parametrize("review", [False, True])
async def test_exact_natural_closure_preserves_management_and_releases_once(
    head_template_engine, review
):
    e = head_template_engine
    t, p = await setup(e, review=review)
    for now in [7001, 7002]:
        async with PostgresKernelUnitOfWork(e) as u:
            assert (
                await record_verified_exit(u, proof=p, now_ms=now)
                == "settlement_pending"
            )
    async with PostgresKernelUnitOfWork(e) as u:
        a = await u.aggregates.get(t.identity.ticket_id)
        assert a.position_qty == a.protected_qty == 0
        assert a.management_mode.value == ("REVIEW_REQUIRED" if review else "AUTO")
        assert a.status.value == "settlement_pending"
        from src.trading_kernel.application.settle_ticket import (
            RecordTradeReviewRequest,
            SettleTicketRequest,
            record_trade_review,
            settle_ticket,
        )

        await settle_ticket(
            u, SettleTicketRequest(ticket_id=t.identity.ticket_id, settled_at_ms=7003)
        )
        await record_trade_review(
            u,
            RecordTradeReviewRequest(
                ticket_id=t.identity.ticket_id,
                review_id="closed-review",
                outcome="initial_stop_triggered",
                metrics={"economics_completeness": "incomplete_evidence"},
                decision_impact={},
                recorded_at_ms=7004,
            ),
        )
    async with e.connect() as c:
        assert (
            await c.scalar(
                sa.text(
                    "SELECT count(*) FROM brc_trade_events WHERE event_type='VerifiedExitClosed'"
                )
            )
            == 1
        )
        assert (
            await c.scalar(
                sa.text("SELECT active_ticket_count FROM brc_account_exposure_current")
            )
            == 0
        )
        assert (
            await c.scalar(
                sa.text(
                    "SELECT count(*) FROM brc_budget_reservations WHERE status='active'"
                )
            )
            == 0
        )
        assert (
            await c.scalar(sa.text("SELECT count(*) FROM brc_exchange_commands")) == 3
        )


@pytest.mark.asyncio
async def test_unknown_or_wrong_proof_rolls_back_without_release(head_template_engine):
    e = head_template_engine
    t, p = await setup(e)
    with pytest.raises(ValueError, match="version"):
        async with PostgresKernelUnitOfWork(e) as u:
            await record_verified_exit(
                u, proof=p.model_copy(update={"expected_version": 1}), now_ms=7001
            )
    async with PostgresKernelUnitOfWork(e) as u:
        assert (await u.aggregates.get(t.identity.ticket_id)).position_qty == t.quantity


@pytest.mark.asyncio
async def test_exact_causal_incidents_resolve_but_extra_incident_blocks(
    head_template_engine,
):
    from src.trading_kernel.application.ports import RuntimeIncidentRecord
    from src.trading_kernel.domain.incident_blocking import EntryBlockScope

    e = head_template_engine
    t, p = await setup(e)
    async with PostgresKernelUnitOfWork(e) as u:
        await u.incidents.add(
            RuntimeIncidentRecord(
                incident_id="cause",
                ticket_id=t.identity.ticket_id,
                incident_kind="lifecycle_facts_contradictory",
                status="open",
                first_blocker="lifecycle_facts_contradictory",
                entry_block_scope=EntryBlockScope.ACCOUNT_CAPACITY,
                entry_block_key=f"{t.identity.netting_domain.venue_id}:{t.identity.netting_domain.account_id}",
                details={},
                opened_at_ms=6001,
            )
        )
    with pytest.raises(ValueError, match="incident"):
        async with PostgresKernelUnitOfWork(e) as u:
            await record_verified_exit(u, proof=p, now_ms=7001)
    p = p.model_copy(update={"incident_ids": ("cause",)})
    async with PostgresKernelUnitOfWork(e) as u:
        await record_verified_exit(u, proof=p, now_ms=7001)
    async with e.connect() as c:
        assert (
            await c.scalar(
                sa.text(
                    "SELECT status FROM brc_runtime_incidents WHERE incident_id='cause'"
                )
            )
            == "resolved"
        )


@pytest.mark.asyncio
async def test_preview_rollback_keeps_original_events_budget_and_incidents(
    head_template_engine,
):
    e = head_template_engine
    _t, p = await setup(e)
    async with e.connect() as c:
        before = {
            n: (
                await c.execute(
                    sa.text("SELECT to_jsonb(t)::text FROM " + n + " t ORDER BY 1")
                )
            )
            .scalars()
            .all()
            for n in [
                "brc_trade_events",
                "brc_trade_aggregates",
                "brc_budget_reservations",
                "brc_account_exposure_current",
                "brc_exchange_commands",
            ]
        }
    with pytest.raises(RuntimeError, match="preview"):
        async with PostgresKernelUnitOfWork(e) as u:
            await record_verified_exit(u, proof=p, now_ms=7001)
            raise RuntimeError("preview")
    async with e.connect() as c:
        assert before == {
            n: (
                await c.execute(
                    sa.text("SELECT to_jsonb(t)::text FROM " + n + " t ORDER BY 1")
                )
            )
            .scalars()
            .all()
            for n in before
        }


@pytest.mark.asyncio
async def test_manual_system_exit_can_close_without_restoring_auto_or_venue_writes(
    head_template_engine,
):
    from src.trading_kernel.application.verified_exit_closure import (
        settle_verified_exit,
    )
    from src.trading_kernel.domain.events import ManualTakeoverConfirmed

    e = head_template_engine
    t, p = await setup(e, review=False)
    async with PostgresKernelUnitOfWork(e) as u:
        a = await u.aggregates.get(t.identity.ticket_id)
        ev = ManualTakeoverConfirmed(
            event_id="owner-real",
            ticket_id=t.identity.ticket_id,
            sequence=a.last_event_sequence + 1,
            occurred_at_ms=5000,
            evidence_id="observed-app",
            reason="external_order_amendment",
        )
        await u.commit_reduction(
            event=ev, reduction=reduce_event(a, ev), expected_version=a.version
        )
        a = await u.aggregates.get(t.identity.ticket_id)
    p = p.model_copy(
        update={
            "expected_version": a.version,
            "management_revision": a.management_revision,
        }
    )
    async with PostgresKernelUnitOfWork(e) as u:
        assert await settle_verified_exit(u, proof=p, now_ms=7001) == "terminal"
    async with PostgresKernelUnitOfWork(e) as u:
        a = await u.aggregates.get(t.identity.ticket_id)
        assert a.management_mode.value == "MANUAL" and a.manual_takeover_at_ms == 5000
        assert len(await u.exchange_commands.list_for_ticket(t.identity.ticket_id)) == 3
        from src.trading_kernel.application.review_window import _review_window

        window = _review_window(
            await u.events.list_for_ticket(t.identity.ticket_id),
            exposure_started_at_ms=t.created_at_ms,
        )
        assert window.exit_time_ms == 6000 and not window.external_flat


@pytest.mark.asyncio
@pytest.mark.parametrize("reported_time_in_force", ["GTE_GTC", "IOC"])
async def test_close_all_stop_default_time_in_force_at_strategy_exit(
    head_template_engine, reported_time_in_force,
):
    from src.trading_kernel.application.reconcile_ticket import (
        ExitTicketRequest,
        request_exit,
    )
    from src.trading_kernel.infrastructure.pg_models import exchange_commands
    from tests.trading_kernel.support.command_dispatch import dispatch_for_ticket
    from tests.trading_kernel.support.dispatch_venues import KindAwareAcceptingVenue

    engine = head_template_engine
    ticket, old_proof = await setup(engine, review=False)
    ticket_id = ticket.identity.ticket_id
    async with engine.begin() as connection:
        stop_row = (await connection.execute(
            sa.select(exchange_commands).where(exchange_commands.c.ticket_id == ticket_id,
                                               exchange_commands.c.command_kind == "initial_stop")
        )).mappings().one()
        await connection.execute(sa.insert(exchange_commands).values({
            **dict(stop_row),
            "command_id": "fixture-replacement",
            "command_kind": "replace_protection",
            "idempotency_key": "fixture:replacement",
            "venue_client_order_id": "fixture-replacement-client",
            "request_payload": {**stop_row["request_payload"], "close_position":True,"reduce_only":False},
            "result_payload": {**stop_row["result_payload"],"exchange_order_id":"fixture-replacement-stop"},
            "created_at_ms": 4000,
            "completed_at_ms": 4100,
        }))
    async with PostgresKernelUnitOfWork(engine) as u:
        await request_exit(u, ExitTicketRequest(ticket_id=ticket_id, reason="pre_tp1_time_stop_hit", requested_at_ms=5000))
    await dispatch_for_ticket(engine, KindAwareAcceptingVenue(observed_at_ms=5101), ticket_id, now_ms=5100)
    async with PostgresKernelUnitOfWork(engine) as u:
        aggregate = await u.aggregates.get(ticket_id)
        references = await u.exchange_commands.list_order_references(ticket_id)
    assert aggregate.status.value == "exit_accepted"
    payload = old_proof.model_dump(mode="python")
    payload["expected_version"] = aggregate.version
    payload["management_revision"] = aggregate.management_revision
    orders = payload["orders"]
    initial_stop = next(row for row in orders if row["reference"]["command_kind"] == "initial_stop")
    initial_stop.update(status="CANCELED", executed_quantity="0", actual_order_id=None)
    replacement = next(ref for ref in references if ref.command_kind.value == "replace_protection")
    exit_ref = next(ref for ref in references if ref.command_kind.value == "exit")
    orders += (
        {
            **initial_stop, "status":"EXPIRED", "reference": replacement,
            "terms": {**initial_stop["terms"], "exchange_order_id":replacement.submitted_exchange_order_id,
                "client_order_id":replacement.venue_client_order_id, "quantity":None,
                "reduce_only":False,"close_position":True,"time_in_force":reported_time_in_force},
        },
        {
            **initial_stop, "status":"FILLED", "executed_quantity":ticket.quantity,"reference":exit_ref,
            "terms":{**initial_stop["terms"], "exchange_order_id":exit_ref.submitted_exchange_order_id,
                "client_order_id":exit_ref.venue_client_order_id,"order_namespace":"regular",
                "order_type":"MARKET","trigger_price":None,"time_in_force":"GTC"},
        },
    )
    payload["orders"] = orders
    payload["exit_fills"][0]["order_id"] = exit_ref.submitted_exchange_order_id
    proof = type(old_proof).model_validate(payload)
    async with PostgresKernelUnitOfWork(engine) as u:
        if reported_time_in_force == "IOC":
            with pytest.raises(ValueError, match="closure order instruction differs"):
                await record_verified_exit(u, proof=proof, now_ms=7001)
        else:
            assert await record_verified_exit(u, proof=proof, now_ms=7001) == "settlement_pending"
