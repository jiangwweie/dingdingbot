from decimal import Decimal as D

import pytest
import sqlalchemy as sa

from src.trading_kernel.application.verified_exit_closure import record_verified_exit
from src.trading_kernel.domain.events import ManagementReviewRequired
from src.trading_kernel.domain.reducer import reduce_event
from src.trading_kernel.domain.verified_exit_closure import VerifiedExitClosureProof
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from tests.trading_kernel.support.lifecycle import (
    reach_position_protected,
    registered_sor_long_ticket,
)


async def setup(engine, *, review=True):
    t = registered_sor_long_ticket()
    await reach_position_protected(engine, t)
    async with PostgresKernelUnitOfWork(engine) as u:
        a = await u.aggregates.get_for_update(t.identity.ticket_id)
        if review:
            event = ManagementReviewRequired(
                event_id="review-natural",
                ticket_id=t.identity.ticket_id,
                sequence=a.last_event_sequence + 1,
                occurred_at_ms=5000,
                evidence_id="tp-terminal",
                reason="tp1_terminal_attribution_unknown",
            )
            await u.commit_reduction(
                event=event,
                reduction=reduce_event(a, event),
                expected_version=a.version,
            )
        a = await u.aggregates.get(t.identity.ticket_id)
        refs = await u.exchange_commands.list_order_references(t.identity.ticket_id)
        rows = await u.management.command_rows(t.identity.ticket_id)
    from src.trading_kernel.domain.trade_management import OrderTerms

    orders = []
    entry_id = None
    exit_id = "stop-child"
    for ref in refs:
        row = next(r for r in rows if r["command_id"] == ref.command_id)
        p = row["request_payload"]
        kind = ref.command_kind.value
        terms = OrderTerms(
            venue_id=t.identity.netting_domain.venue_id,
            account_id=t.identity.netting_domain.account_id,
            exchange_instrument_id=t.identity.netting_domain.exchange_instrument_id,
            position_side=t.identity.netting_domain.position_side,
            order_namespace=ref.namespace.value,
            exchange_order_id=ref.submitted_exchange_order_id,
            client_order_id=ref.venue_client_order_id,
            side=p["side"],
            order_type=p["order_type"].upper(),
            quantity=D(p["quantity"]),
            price=None if p.get("limit_price") is None else D(p["limit_price"]),
            trigger_price=None if p.get("stop_price") is None else D(p["stop_price"]),
            close_position=False,
            reduce_only=p["reduce_only"],
            time_in_force=p.get("time_in_force") or "GTC",
            working_type="CONTRACT_PRICE",
            price_protect=False,
            activation_price=None,
            callback_rate=None,
            price_match="NONE",
            self_trade_prevention_mode="EXPIRE_MAKER",
            good_till_date_ms=0,
        )
        if kind == "entry":
            entry_id = ref.submitted_exchange_order_id
        orders.append(
            {
                "reference": ref,
                "terms": terms,
                "status": "FINISHED"
                if kind == "initial_stop"
                else "FILLED"
                if kind == "entry"
                else "EXPIRED",
                "executed_quantity": t.quantity
                if kind in {"entry", "initial_stop"}
                else D(0),
                "actual_order_id": exit_id if kind == "initial_stop" else None,
                "updated_at_ms": 6000,
            }
        )
    proof = VerifiedExitClosureProof(
        ticket_id=t.identity.ticket_id,
        domain=t.identity.netting_domain,
        expected_version=a.version,
        management_revision=a.management_revision,
        entry_quantity=t.quantity,
        orders=orders,
        entry_fills=[
            {
                "trade_id": "entry1",
                "order_id": entry_id,
                "quantity": t.quantity,
                "price": t.entry_reference_price,
                "occurred_at_ms": 3000,
            }
        ],
        exit_fills=[
            {
                "trade_id": "stop1",
                "order_id": exit_id,
                "quantity": t.quantity,
                "price": t.initial_stop_price,
                "occurred_at_ms": 6000,
            }
        ],
        snapshot={
            "netting_domain": t.identity.netting_domain,
            "quantity": D(0),
            "average_entry_price": None,
            "open_orders": [],
            "observed_at_ms": 7000,
        },
        observed_at_ms=7000,
        valid_until_ms=37000,
    )
    return t, proof


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
