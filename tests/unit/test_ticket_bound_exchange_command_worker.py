from __future__ import annotations

# ruff: noqa: F401, F811

import asyncio
from decimal import Decimal
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from sqlalchemy import event, text

from src.application.action_time.exchange_command import (
    claim_next_exchange_command,
)
from src.application.action_time.exchange_command_worker import (
    run_one_ticket_bound_exchange_command,
)
from src.application.action_time.lifecycle_exchange_command_materializer import (
    materialize_lifecycle_exchange_commands,
)
from src.application.action_time.orphan_protection_cleanup_command import (
    prepare_ticket_bound_orphan_protection_cleanup_command,
)
from src.domain.exceptions import InvalidOrderError
from tests.unit.test_action_time_ticket_materialization import NOW_MS
from tests.unit.test_ticket_bound_protected_submit_attempt import (
    _create_ready_protected_submit,
    _prepare_real_submit,
)
from tests.unit.test_ticket_bound_runtime_safety_state_materialization import (
    pg_control_connection,
)
from tests.unit.test_ticket_bound_orphan_protection_cleanup_command import (
    _flat_position_live_protection,
)


class _WorkerGateway:
    runtime_account_id = "owner-subaccount-runtime-v0"
    runtime_exchange_id = "binance_usdm"

    def __init__(self, *, tracker=None, fail: bool = False) -> None:
        self.tracker = tracker
        self.fail = fail
        self.calls: list[dict] = []

    async def place_order(self, **kwargs):
        if self.tracker is not None:
            assert self.tracker["transactions"] == 0
        self.calls.append(dict(kwargs))
        if self.fail:
            raise TimeoutError("ambiguous exchange timeout")
        return SimpleNamespace(
            is_success=True,
            exchange_order_id=f"exchange-{kwargs['client_order_id']}",
            filled_qty=kwargs["amount"],
            average_exec_price=Decimal("2000"),
            exchange_order_status="FILLED",
            selected_leverage=kwargs.get("desired_leverage"),
            exchange_configured_initial_leverage=kwargs.get("desired_leverage"),
            leverage_verified_at_ms=(
                NOW_MS + 4999 if kwargs.get("desired_leverage") else None
            ),
        )

    async def cancel_order(self, **kwargs):
        if self.tracker is not None:
            assert self.tracker["transactions"] == 0
        self.calls.append(dict(kwargs))
        return SimpleNamespace(
            is_success=True,
            exchange_order_id=kwargs["exchange_order_id"],
        )


@pytest.mark.asyncio
async def test_worker_commits_claim_before_exchange_io_and_result_after(
    pg_control_connection,
):
    ids = _create_ready_protected_submit(pg_control_connection)
    _prepare_real_submit(pg_control_connection, ids)
    pg_control_connection.commit()
    engine = pg_control_connection.engine
    tracker = {"transactions": 0}

    def began(_conn):
        tracker["transactions"] += 1

    def ended(_conn):
        tracker["transactions"] = max(0, tracker["transactions"] - 1)

    event.listen(engine, "begin", began)
    event.listen(engine, "commit", ended)
    event.listen(engine, "rollback", ended)
    gateway = _WorkerGateway(tracker=tracker)
    try:
        result = await run_one_ticket_bound_exchange_command(
            engine,
            gateway=gateway,
            worker_id="unit-worker",
            now_ms=NOW_MS + 5000,
            command_sources=("protected_submit",),
        )
    finally:
        event.remove(engine, "begin", began)
        event.remove(engine, "commit", ended)
        event.remove(engine, "rollback", ended)

    assert result["status"] == "command_confirmed"
    assert result["command_kind"] == "place_order"
    assert result["exchange_write_called"] is True
    assert len(gateway.calls) == 1
    assert gateway.calls[0]["symbol"] == "ETH/USDT:USDT"
    assert gateway.calls[0]["position_side"] is None
    assert gateway.calls[0]["desired_leverage"] == 2
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT order_role, command_state, claim_token, exchange_result "
                "FROM brc_ticket_bound_exchange_commands "
                "WHERE exchange_command_id = :command_id"
            ),
            {"command_id": result["exchange_command_id"]},
        ).mappings().one()
    assert row["order_role"] == "ENTRY"
    assert row["command_state"] == "confirmed_submitted"
    assert row["claim_token"]
    exchange_result = row["exchange_result"]
    if isinstance(exchange_result, str):
        import json

        exchange_result = json.loads(exchange_result)
    assert exchange_result["selected_leverage"] == 2
    assert exchange_result["exchange_configured_initial_leverage"] == 2
    assert exchange_result["leverage_verified_at_ms"] == NOW_MS + 4999


@pytest.mark.asyncio
async def test_worker_hard_stops_tampered_tp1_market_before_gateway_dispatch(
    pg_control_connection,
):
    ids = _create_ready_protected_submit(pg_control_connection)
    _prepare_real_submit(pg_control_connection, ids)
    pg_control_connection.commit()
    gateway = _WorkerGateway()
    engine = pg_control_connection.engine

    for offset in (5000, 6000):
        result = await run_one_ticket_bound_exchange_command(
            engine,
            gateway=gateway,
            worker_id=f"unit-worker-{offset}",
            now_ms=NOW_MS + offset,
            command_sources=("protected_submit",),
        )
        assert result["status"] == "command_confirmed"
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE brc_ticket_bound_exchange_commands "
                "SET order_type = 'market', price = NULL "
                "WHERE order_role = 'TP1'"
            )
        )

    result = await run_one_ticket_bound_exchange_command(
        engine,
        gateway=gateway,
        worker_id="unit-worker-tp1",
        now_ms=NOW_MS + 7000,
        command_sources=("protected_submit",),
    )

    assert result["status"] == "command_hard_stopped"
    assert result["blockers"] == ["tp1_requires_limit_price"]
    assert result["exchange_write_called"] is False
    assert len(gateway.calls) == 2


@pytest.mark.asyncio
async def test_worker_dispatches_one_explicit_gtc_limit_tp1_without_market_fallback(
    pg_control_connection,
):
    ids = _create_ready_protected_submit(pg_control_connection)
    prepared = _prepare_real_submit(pg_control_connection, ids)
    pg_control_connection.commit()
    gateway = _WorkerGateway()
    engine = pg_control_connection.engine

    results = []
    for offset in (5000, 6000, 7000):
        results.append(
            await run_one_ticket_bound_exchange_command(
                engine,
                gateway=gateway,
                worker_id=f"unit-worker-{offset}",
                now_ms=NOW_MS + offset,
                command_sources=("protected_submit",),
            )
        )

    assert [result["status"] for result in results] == [
        "command_confirmed",
        "command_confirmed",
        "command_confirmed",
    ]
    tp1_calls = [call for call in gateway.calls if call["order_type"] == "limit"]
    assert len(tp1_calls) == 1
    assert tp1_calls[0]["time_in_force"] == "GTC"
    assert "post_only" not in tp1_calls[0]
    assert all(call["order_type"] != "market" for call in tp1_calls)
    attempt_status = pg_control_connection.execute(
        text(
            "SELECT status FROM brc_ticket_bound_protected_submit_attempts "
            "WHERE protected_submit_attempt_id = :attempt_id"
        ),
        {"attempt_id": prepared["protected_submit_attempt_id"]},
    ).scalar_one()
    assert attempt_status == "submitted"


@pytest.mark.asyncio
async def test_worker_classifies_gtx_post_only_rejection_without_market_retry(
    pg_control_connection,
):
    ids = _create_ready_protected_submit(pg_control_connection)
    _prepare_real_submit(pg_control_connection, ids)
    pg_control_connection.execute(
        text(
            "UPDATE brc_ticket_bound_exchange_commands "
            "SET execution_style = 'passive_limit_gtx', time_in_force = 'GTX', "
            "post_only = true WHERE order_role = 'TP1'"
        )
    )
    pg_control_connection.commit()
    engine = pg_control_connection.engine

    class _PostOnlyRejectingGateway(_WorkerGateway):
        async def place_order(self, **kwargs):
            self.calls.append(dict(kwargs))
            if kwargs.get("post_only") is True:
                raise InvalidOrderError("post_only_would_take", "F-012")
            return SimpleNamespace(
                is_success=True,
                exchange_order_id=f"exchange-{kwargs['client_order_id']}",
                filled_qty=kwargs["amount"],
                average_exec_price=Decimal("2000"),
                exchange_order_status="FILLED",
            )

    gateway = _PostOnlyRejectingGateway()
    for offset in (5000, 6000):
        result = await run_one_ticket_bound_exchange_command(
            engine,
            gateway=gateway,
            worker_id=f"unit-worker-{offset}",
            now_ms=NOW_MS + offset,
            command_sources=("protected_submit",),
        )
        assert result["status"] == "command_confirmed"

    rejected = await run_one_ticket_bound_exchange_command(
        engine,
        gateway=gateway,
        worker_id="unit-worker-gtx",
        now_ms=NOW_MS + 7000,
        command_sources=("protected_submit",),
    )

    assert rejected["status"] == "command_rejected"
    assert rejected["command_state"] == "confirmed_rejected"
    assert rejected["exchange_write_called"] is True
    gtx_calls = [call for call in gateway.calls if call.get("post_only")]
    assert len(gtx_calls) == 1
    assert gtx_calls[0]["order_type"] == "limit"
    assert gtx_calls[0]["time_in_force"] == "GTX"


@pytest.mark.asyncio
async def test_worker_persists_ambiguous_outcome_and_blocks_later_commands(
    pg_control_connection,
):
    ids = _create_ready_protected_submit(pg_control_connection)
    _prepare_real_submit(pg_control_connection, ids)
    pg_control_connection.commit()
    engine = pg_control_connection.engine
    gateway = _WorkerGateway(fail=True)

    first = await run_one_ticket_bound_exchange_command(
        engine,
        gateway=gateway,
        worker_id="unit-worker",
        now_ms=NOW_MS + 5000,
        command_sources=("protected_submit",),
    )
    second = await run_one_ticket_bound_exchange_command(
        engine,
        gateway=_WorkerGateway(),
        worker_id="unit-worker-2",
        now_ms=NOW_MS + 6000,
        command_sources=("protected_submit",),
    )

    assert first["status"] == "command_outcome_unknown"
    assert first["command_state"] == "outcome_unknown"
    assert second["status"] == "no_prepared_command"
    assert len(gateway.calls) == 1
    with engine.connect() as conn:
        hold = conn.execute(
            text(
                "SELECT status, source_kind, source_id, netting_domain_key "
                "FROM brc_ticket_bound_scope_freezes"
            )
        ).mappings().one()
    assert hold["status"] == "active"
    assert hold["source_kind"] == "exchange_command"
    assert hold["source_id"] == first["exchange_command_id"]
    assert hold["netting_domain_key"].endswith("|one_way|BOTH")


@pytest.mark.asyncio
async def test_worker_owned_dispatch_timeout_persists_outcome_unknown(
    pg_control_connection,
):
    ids = _create_ready_protected_submit(pg_control_connection)
    _prepare_real_submit(pg_control_connection, ids)
    pg_control_connection.commit()

    class HangingGateway(_WorkerGateway):
        async def place_order(self, **kwargs):
            self.calls.append(dict(kwargs))
            await asyncio.sleep(60)

    gateway = HangingGateway()
    result = await run_one_ticket_bound_exchange_command(
        pg_control_connection.engine,
        gateway=gateway,
        worker_id="deadline-owned-worker",
        now_ms=NOW_MS + 5000,
        command_sources=("protected_submit",),
        dispatch_timeout_seconds=0.01,
    )

    assert result["status"] == "command_outcome_unknown"
    assert result["command_state"] == "outcome_unknown"
    assert result["exchange_write_called"] is True
    assert len(gateway.calls) == 1


@pytest.mark.asyncio
async def test_expired_dispatch_lease_becomes_unknown_without_second_dispatch(
    pg_control_connection,
):
    ids = _create_ready_protected_submit(pg_control_connection)
    _prepare_real_submit(pg_control_connection, ids)
    pg_control_connection.commit()
    with pg_control_connection.begin():
        claimed = claim_next_exchange_command(
            pg_control_connection,
            claim_owner="dead-worker",
            now_ms=NOW_MS + 5000,
            lease_ms=100,
        )
    gateway = _WorkerGateway()

    result = await run_one_ticket_bound_exchange_command(
        pg_control_connection.engine,
        gateway=gateway,
        worker_id="new-worker",
        now_ms=NOW_MS + 5200,
        command_sources=("protected_submit",),
    )

    assert result["status"] == "outcome_unknown_persisted"
    assert result["expired_command_ids"] == [claimed["exchange_command_id"]]
    assert gateway.calls == []


@pytest.mark.asyncio
async def test_worker_does_not_claim_or_call_gateway_when_capability_disabled(
    pg_control_connection,
):
    ids = _create_ready_protected_submit(pg_control_connection)
    _prepare_real_submit(pg_control_connection, ids)
    pg_control_connection.execute(
        text(
            "UPDATE brc_runtime_capabilities_current "
            "SET status = 'disabled', certification_ref = 'unit:phase-one' "
            "WHERE capability_id = 'ticket_lifecycle_durable_mutation'"
        )
    )
    pg_control_connection.commit()
    gateway = _WorkerGateway()

    result = await run_one_ticket_bound_exchange_command(
        pg_control_connection.engine,
        gateway=gateway,
        worker_id="unit-worker",
        now_ms=NOW_MS + 5000,
        command_sources=("protected_submit",),
    )

    assert result["status"] == "durable_mutation_capability_not_ready"
    assert result["blockers"] == ["lifecycle_mutation_capability_not_ready"]
    assert gateway.calls == []
    with pg_control_connection.engine.connect() as conn:
        assert conn.execute(
            text(
                "SELECT count(*) FROM brc_ticket_bound_exchange_commands "
                "WHERE command_state = 'dispatching'"
            )
        ).scalar_one() == 0


@pytest.mark.asyncio
async def test_lifecycle_worker_never_dispatches_protected_submit_entry(
    pg_control_connection,
):
    ids = _create_ready_protected_submit(pg_control_connection)
    _prepare_real_submit(pg_control_connection, ids)
    pg_control_connection.commit()
    gateway = _WorkerGateway()

    result = await run_one_ticket_bound_exchange_command(
        pg_control_connection.engine,
        gateway=gateway,
        worker_id="lifecycle-worker",
        now_ms=NOW_MS + 5000,
        command_sources=(
            "protection_recovery",
            "runner_mutation",
            "orphan_cleanup",
        ),
    )

    assert result["status"] == "no_prepared_command"
    assert gateway.calls == []
    with pg_control_connection.engine.connect() as conn:
        states = conn.execute(
            text(
                "SELECT DISTINCT command_state "
                "FROM brc_ticket_bound_exchange_commands"
            )
        ).scalars().all()
    assert states == ["prepared"]


@pytest.mark.asyncio
async def test_worker_never_claims_terminal_failed_protected_submit_attempt(
    pg_control_connection,
):
    ids = _create_ready_protected_submit(pg_control_connection)
    prepared = _prepare_real_submit(pg_control_connection, ids)
    pg_control_connection.execute(
        text(
            "UPDATE brc_ticket_bound_protected_submit_attempts "
            "SET status = 'submit_failed', exchange_write_called = false "
            "WHERE protected_submit_attempt_id = :attempt_id"
        ),
        {"attempt_id": prepared["protected_submit_attempt_id"]},
    )
    pg_control_connection.execute(
        text(
            "UPDATE brc_action_time_tickets SET status = 'expired' "
            "WHERE ticket_id = :ticket_id"
        ),
        {"ticket_id": ids["ticket_id"]},
    )
    pg_control_connection.commit()
    gateway = _WorkerGateway()

    result = await run_one_ticket_bound_exchange_command(
        pg_control_connection.engine,
        gateway=gateway,
        worker_id="stale-protected-submit-worker",
        now_ms=NOW_MS + 5000,
        command_sources=("protected_submit",),
    )

    assert result["status"] == "no_prepared_command"
    assert result["exchange_write_called"] is False
    assert gateway.calls == []


@pytest.mark.asyncio
async def test_two_concurrent_workers_cannot_dispatch_a_second_command(
    pg_control_connection,
):
    ids = _create_ready_protected_submit(pg_control_connection)
    _prepare_real_submit(pg_control_connection, ids)
    pg_control_connection.commit()
    started = asyncio.Event()
    release = asyncio.Event()

    class BlockingGateway(_WorkerGateway):
        async def place_order(self, **kwargs):
            self.calls.append(dict(kwargs))
            started.set()
            await release.wait()
            return SimpleNamespace(
                is_success=True,
                exchange_order_id=f"exchange-{kwargs['client_order_id']}",
            )

    first_gateway = BlockingGateway()
    first_task = asyncio.create_task(
        run_one_ticket_bound_exchange_command(
            pg_control_connection.engine,
            gateway=first_gateway,
            worker_id="concurrent-worker-a",
            now_ms=NOW_MS + 5000,
            command_sources=("protected_submit",),
        )
    )
    await started.wait()
    second_gateway = _WorkerGateway()
    second = await run_one_ticket_bound_exchange_command(
        pg_control_connection.engine,
        gateway=second_gateway,
        worker_id="concurrent-worker-b",
        now_ms=NOW_MS + 5001,
        command_sources=("protected_submit",),
    )
    release.set()
    first = await first_task

    assert first["status"] == "command_confirmed"
    assert second["status"] == "no_prepared_command"
    assert len(first_gateway.calls) == 1
    assert second_gateway.calls == []


@pytest.mark.asyncio
async def test_entry_rejection_terminalizes_undispatched_protection_siblings(
    pg_control_connection,
):
    """An authoritative ENTRY rejection must not strand SL/TP1 or the Attempt."""

    ids = _create_ready_protected_submit(pg_control_connection)
    prepared = _prepare_real_submit(pg_control_connection, ids)
    pg_control_connection.commit()

    class EntryRejectingGateway(_WorkerGateway):
        async def place_order(self, **kwargs):
            self.calls.append(dict(kwargs))
            raise InvalidOrderError("entry_rejected", "ENTRY-REJECTED")

    result = await run_one_ticket_bound_exchange_command(
        pg_control_connection.engine,
        gateway=EntryRejectingGateway(),
        worker_id="entry-rejection-worker",
        now_ms=NOW_MS + 5000,
        command_sources=("protected_submit",),
    )

    assert result["status"] == "command_rejected"
    commands = list(
        pg_control_connection.execute(
            text(
                "SELECT order_role, command_state "
                "FROM brc_ticket_bound_exchange_commands "
                "WHERE protected_submit_attempt_id = :attempt_id "
                "ORDER BY order_role"
            ),
            {"attempt_id": prepared["protected_submit_attempt_id"]},
        ).mappings()
    )
    assert {row["order_role"]: row["command_state"] for row in commands} == {
        "ENTRY": "confirmed_rejected",
        "SL": "reconciled_absent",
        "TP1": "reconciled_absent",
    }
    attempt = pg_control_connection.execute(
        text(
            "SELECT status, blockers FROM brc_ticket_bound_protected_submit_attempts "
            "WHERE protected_submit_attempt_id = :attempt_id"
        ),
        {"attempt_id": prepared["protected_submit_attempt_id"]},
    ).mappings().one()
    assert attempt["status"] == "submit_failed"
    assert "entry_rejected" in str(attempt["blockers"])


@pytest.mark.asyncio
async def test_worker_binds_partial_entry_fill_before_initial_stop_dispatch(
    pg_control_connection,
):
    """A partial ENTRY fill must resize SL before the worker sends that SL."""

    ids = _create_ready_protected_submit(pg_control_connection)
    _prepare_real_submit(pg_control_connection, ids)
    pg_control_connection.execute(
        text("UPDATE brc_exchange_instruments SET quantity_step = 0.001")
    )
    pg_control_connection.commit()

    class PartialFillGateway(_WorkerGateway):
        async def place_order(self, **kwargs):
            self.calls.append(dict(kwargs))
            return SimpleNamespace(
                is_success=True,
                exchange_order_id=f"exchange-{kwargs['client_order_id']}",
                filled_qty=Decimal(str(kwargs["amount"])) / Decimal("2"),
                average_exec_price=Decimal("2000"),
            )

    gateway = PartialFillGateway()
    result = await run_one_ticket_bound_exchange_command(
        pg_control_connection.engine,
        gateway=gateway,
        worker_id="partial-fill-worker",
        now_ms=NOW_MS + 5000,
        command_sources=("protected_submit",),
        dispatch_timeout_seconds=1,
        drain_initial_protection=True,
    )

    assert len(gateway.calls) >= 2, repr(result)
    initial_stop = next(
        call
        for call in gateway.calls
        if call.get("order_type") == "stop_market"
    )
    assert Decimal(str(initial_stop["amount"])) == Decimal("0.005")


@pytest.mark.asyncio
async def test_entry_effect_crossing_ticket_ttl_submits_ticket_and_drains_its_initial_stop(
    pg_control_connection,
):
    """An ENTRY effect keeps its same-source initial stop claimable past TTL."""

    ids = _create_ready_protected_submit(pg_control_connection)
    prepared = _prepare_real_submit(pg_control_connection, ids)
    pg_control_connection.commit()

    class ExpiringEntryGateway(_WorkerGateway):
        def __init__(self, engine) -> None:
            super().__init__()
            self.engine = engine

        async def place_order(self, **kwargs):
            self.calls.append(dict(kwargs))
            if kwargs["order_type"] == "market":
                with self.engine.begin() as conn:
                    conn.execute(
                        text(
                            "UPDATE brc_action_time_tickets "
                            "SET expires_at_ms = :expires_at_ms "
                            "WHERE ticket_id = :ticket_id"
                        ),
                        {
                            "expires_at_ms": NOW_MS + 5000,
                            "ticket_id": ids["ticket_id"],
                        },
                    )
            return SimpleNamespace(
                is_success=True,
                exchange_order_id=f"exchange-{kwargs['client_order_id']}",
                filled_qty=kwargs["amount"],
                average_exec_price=Decimal("2000"),
                exchange_order_status="FILLED",
            )

    gateway = ExpiringEntryGateway(pg_control_connection.engine)
    result = await run_one_ticket_bound_exchange_command(
        pg_control_connection.engine,
        gateway=gateway,
        worker_id="entry-expiry-worker",
        now_ms=NOW_MS + 5000,
        command_sources=("protected_submit",),
        drain_initial_protection=True,
    )

    assert result["initial_protection_complete"] is True
    assert [call["order_type"] for call in gateway.calls[:2]] == [
        "market",
        "stop_market",
    ]
    rows = {
        row["order_role"]: row
        for row in pg_control_connection.execute(
            text(
                "SELECT order_role, command_state, source_command_id, "
                "protected_submit_attempt_id "
                "FROM brc_ticket_bound_exchange_commands "
                "WHERE protected_submit_attempt_id = :attempt_id"
            ),
            {"attempt_id": prepared["protected_submit_attempt_id"]},
        ).mappings()
    }
    assert rows["ENTRY"]["command_state"] == "confirmed_submitted"
    assert rows["SL"]["command_state"] == "confirmed_submitted"
    assert rows["SL"]["source_command_id"] == prepared[
        "protected_submit_attempt_id"
    ]
    assert rows["SL"]["protected_submit_attempt_id"] == prepared[
        "protected_submit_attempt_id"
    ]
    assert pg_control_connection.execute(
        text(
            "SELECT status FROM brc_action_time_tickets "
            "WHERE ticket_id = :ticket_id"
        ),
        {"ticket_id": ids["ticket_id"]},
    ).scalar_one() == "submitted"


@pytest.mark.asyncio
async def test_initial_protection_drain_is_pinned_to_the_primary_attempt_source(
    pg_control_connection,
):
    """A foreign eligible SL cannot consume the primary ENTRY drain slot."""

    ids = _create_ready_protected_submit(pg_control_connection)
    primary = _prepare_real_submit(pg_control_connection, ids)
    foreign_ticket_id = "ticket:r12:foreign-source"
    foreign_attempt_id = "protected-submit:r12:foreign-source"
    foreign_operation_command_id = "operation-submit:r12:foreign-source"
    metadata = sa.MetaData()
    tickets = sa.Table("brc_action_time_tickets", metadata, autoload_with=pg_control_connection)
    attempts = sa.Table(
        "brc_ticket_bound_protected_submit_attempts",
        metadata,
        autoload_with=pg_control_connection,
    )
    commands = sa.Table(
        "brc_ticket_bound_exchange_commands",
        metadata,
        autoload_with=pg_control_connection,
    )

    primary_ticket = dict(
        pg_control_connection.execute(
            sa.select(tickets).where(tickets.c.ticket_id == ids["ticket_id"])
        ).mappings().one()
    )
    pg_control_connection.execute(
        tickets.insert().values(
            **{
                **primary_ticket,
                "ticket_id": foreign_ticket_id,
                "action_time_lane_input_id": "lane:r12:foreign-source",
                "ticket_hash": "ticket-hash:r12:foreign-source",
                "exposure_episode_id": "exposure:r12:foreign-source",
            }
        )
    )
    primary_attempt = dict(
        pg_control_connection.execute(
            sa.select(attempts).where(
                attempts.c.protected_submit_attempt_id
                == primary["protected_submit_attempt_id"]
            )
        ).mappings().one()
    )
    pg_control_connection.execute(
        attempts.insert().values(
            **{
                **primary_attempt,
                "protected_submit_attempt_id": foreign_attempt_id,
                "ticket_id": foreign_ticket_id,
                "operation_submit_command_id": foreign_operation_command_id,
                "action_time_lane_input_id": "lane:r12:foreign-source",
            }
        )
    )
    primary_commands = list(
        pg_control_connection.execute(
            sa.select(commands).where(
                commands.c.protected_submit_attempt_id
                == primary["protected_submit_attempt_id"]
            )
        ).mappings()
    )
    for command in primary_commands:
        role = str(command["order_role"])
        copied = {
            **dict(command),
            "exchange_command_id": f"exchange-command:r12:foreign:{role.lower()}",
            "protected_submit_attempt_id": foreign_attempt_id,
            "ticket_id": foreign_ticket_id,
            "operation_submit_command_id": foreign_operation_command_id,
            "source_command_id": foreign_attempt_id,
            "local_order_id": f"local-order:r12:foreign:{role.lower()}",
            "client_order_id": f"r12-foreign-{role.lower()}",
            "netting_domain_key": f"{command['netting_domain_key']}|r12-foreign",
            "exposure_episode_id": "exposure:r12:foreign-source",
        }
        if role == "ENTRY":
            copied.update(
                command_state="confirmed_submitted",
                outcome_class="exchange_accepted",
                exchange_order_id="exchange-r12-foreign-entry",
                exchange_result={
                    "exchange_order_id": "exchange-r12-foreign-entry",
                    "filled_qty": str(command["amount"]),
                    "average_exec_price": "2000",
                    "exchange_order_status": "FILLED",
                },
                resolved_at_ms=NOW_MS + 4000,
            )
        elif role == "SL":
            copied["prepared_at_ms"] = NOW_MS + 3999
        pg_control_connection.execute(commands.insert().values(**copied))
    pg_control_connection.commit()

    gateway = _WorkerGateway()
    result = await run_one_ticket_bound_exchange_command(
        pg_control_connection.engine,
        gateway=gateway,
        worker_id="primary-source-drain-worker",
        now_ms=NOW_MS + 5000,
        command_sources=("protected_submit",),
        source_command_id=primary["protected_submit_attempt_id"],
        protected_submit_attempt_id=primary["protected_submit_attempt_id"],
        allowed_roles=("ENTRY", "SL"),
        drain_initial_protection=True,
    )

    assert result["initial_protection_complete"] is True
    assert [call["order_type"] for call in gateway.calls] == [
        "market",
        "stop_market",
    ]
    primary_sl_state = pg_control_connection.execute(
        text(
            "SELECT command_state FROM brc_ticket_bound_exchange_commands "
            "WHERE protected_submit_attempt_id = :attempt_id "
            "AND order_role = 'SL'"
        ),
        {"attempt_id": primary["protected_submit_attempt_id"]},
    ).scalar_one()
    foreign_sl_state = pg_control_connection.execute(
        text(
            "SELECT command_state FROM brc_ticket_bound_exchange_commands "
            "WHERE protected_submit_attempt_id = :attempt_id "
            "AND order_role = 'SL'"
        ),
        {"attempt_id": foreign_attempt_id},
    ).scalar_one()
    assert primary_sl_state == "confirmed_submitted"
    assert foreign_sl_state == "prepared"


@pytest.mark.asyncio
async def test_restart_after_entry_result_commit_recovers_same_source_initial_stop(
    pg_control_connection,
):
    """The next worker resumes committed ENTRY protection after process loss."""

    ids = _create_ready_protected_submit(pg_control_connection)
    prepared = _prepare_real_submit(pg_control_connection, ids)
    pg_control_connection.commit()
    entry_gateway = _WorkerGateway()
    entry = await run_one_ticket_bound_exchange_command(
        pg_control_connection.engine,
        gateway=entry_gateway,
        worker_id="entry-before-process-loss",
        now_ms=NOW_MS + 5000,
        command_sources=("protected_submit",),
    )
    assert entry["status"] == "command_confirmed"
    assert entry["order_role"] == "ENTRY"
    assert entry_gateway.calls[0]["order_type"] == "market"
    with pg_control_connection.engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE brc_action_time_tickets "
                "SET status = 'expired', expires_at_ms = :expires_at_ms "
                "WHERE ticket_id = :ticket_id"
            ),
            {"expires_at_ms": NOW_MS + 5000, "ticket_id": ids["ticket_id"]},
        )

    pg_control_connection.close()
    restart_gateway = _WorkerGateway()
    recovered = await run_one_ticket_bound_exchange_command(
        pg_control_connection.engine,
        gateway=restart_gateway,
        worker_id="restart-after-entry-result-commit",
        now_ms=NOW_MS + 5001,
        command_sources=("protected_submit",),
    )

    assert recovered["status"] == "command_confirmed"
    assert recovered["order_role"] == "SL"
    assert recovered["source_command_id"] == prepared["protected_submit_attempt_id"]
    assert [call["order_type"] for call in restart_gateway.calls] == ["stop_market"]
    with pg_control_connection.engine.connect() as conn:
        rows = {
            row["order_role"]: row
            for row in conn.execute(
                text(
                    "SELECT order_role, command_state, source_command_id "
                    "FROM brc_ticket_bound_exchange_commands "
                    "WHERE protected_submit_attempt_id = :attempt_id"
                ),
                {"attempt_id": prepared["protected_submit_attempt_id"]},
            ).mappings()
        }
    assert rows["ENTRY"]["command_state"] == "confirmed_submitted"
    assert rows["SL"]["command_state"] == "confirmed_submitted"
    assert rows["SL"]["source_command_id"] == entry["source_command_id"]


@pytest.mark.asyncio
async def test_worker_rejects_lease_shorter_than_dispatch_timeout_and_commit_margin(
    pg_control_connection,
):
    ids = _create_ready_protected_submit(pg_control_connection)
    _prepare_real_submit(pg_control_connection, ids)
    pg_control_connection.commit()

    with pytest.raises(ValueError, match="exchange_command_lease_timeout_budget_invalid"):
        await run_one_ticket_bound_exchange_command(
            pg_control_connection.engine,
            gateway=_WorkerGateway(),
            worker_id="invalid-lease-worker",
            now_ms=NOW_MS + 5000,
            lease_ms=15_000,
            command_sources=("protected_submit",),
            dispatch_timeout_seconds=15,
        )


@pytest.mark.asyncio
async def test_worker_persists_typed_entry_fill_facts_when_schema_is_available(
    pg_control_connection,
):
    ids = _create_ready_protected_submit(pg_control_connection)
    _prepare_real_submit(pg_control_connection, ids)
    for statement in (
        "ALTER TABLE brc_ticket_bound_exchange_commands ADD COLUMN exchange_order_status TEXT",
        "ALTER TABLE brc_ticket_bound_exchange_commands ADD COLUMN executed_qty NUMERIC",
        "ALTER TABLE brc_ticket_bound_exchange_commands ADD COLUMN average_exec_price NUMERIC",
        "ALTER TABLE brc_ticket_bound_exchange_commands ADD COLUMN exchange_observed_at_ms BIGINT",
        "ALTER TABLE brc_ticket_bound_exchange_commands ADD COLUMN result_facts_complete BOOLEAN NOT NULL DEFAULT false",
    ):
        pg_control_connection.execute(text(statement))
    pg_control_connection.commit()

    class FilledGateway(_WorkerGateway):
        async def place_order(self, **kwargs):
            self.calls.append(dict(kwargs))
            return SimpleNamespace(
                is_success=True,
                exchange_order_id=f"exchange-{kwargs['client_order_id']}",
                filled_qty=Decimal("0.005"),
                average_exec_price=Decimal("2000"),
                exchange_order_status="PARTIALLY_FILLED",
            )

    await run_one_ticket_bound_exchange_command(
        pg_control_connection.engine,
        gateway=FilledGateway(),
        worker_id="typed-result-worker",
        now_ms=NOW_MS + 5000,
        command_sources=("protected_submit",),
    )

    row = pg_control_connection.execute(
        text(
            "SELECT executed_qty, average_exec_price, exchange_order_status, "
            "exchange_observed_at_ms, result_facts_complete "
            "FROM brc_ticket_bound_exchange_commands WHERE order_role = 'ENTRY'"
        )
    ).mappings().one()
    assert Decimal(str(row["executed_qty"])) == Decimal("0.005")
    assert Decimal(str(row["average_exec_price"])) == Decimal("2000")
    assert row["exchange_order_status"] == "PARTIALLY_FILLED"
    assert row["exchange_observed_at_ms"] == NOW_MS + 5000
    assert row["result_facts_complete"] in {True, 1}


@pytest.mark.asyncio
async def test_worker_accepts_exact_zero_entry_fill_without_dispatching_protection(
    pg_control_connection,
):
    """An exact zero ENTRY fill is not missing truth and must not send SL/TP1."""

    ids = _create_ready_protected_submit(pg_control_connection)
    prepared = _prepare_real_submit(pg_control_connection, ids)
    for statement in (
        "ALTER TABLE brc_ticket_bound_exchange_commands ADD COLUMN exchange_order_status TEXT",
        "ALTER TABLE brc_ticket_bound_exchange_commands ADD COLUMN executed_qty NUMERIC",
        "ALTER TABLE brc_ticket_bound_exchange_commands ADD COLUMN average_exec_price NUMERIC",
        "ALTER TABLE brc_ticket_bound_exchange_commands ADD COLUMN exchange_observed_at_ms BIGINT",
        "ALTER TABLE brc_ticket_bound_exchange_commands ADD COLUMN result_facts_complete BOOLEAN NOT NULL DEFAULT false",
    ):
        pg_control_connection.execute(text(statement))
    pg_control_connection.commit()

    class ZeroFillGateway(_WorkerGateway):
        async def place_order(self, **kwargs):
            self.calls.append(dict(kwargs))
            return SimpleNamespace(
                is_success=True,
                exchange_order_id=f"exchange-{kwargs['client_order_id']}",
                filled_qty=Decimal("0"),
                exchange_order_status="NEW",
            )

    gateway = ZeroFillGateway()
    result = await run_one_ticket_bound_exchange_command(
        pg_control_connection.engine,
        gateway=gateway,
        worker_id="zero-fill-worker",
        now_ms=NOW_MS + 5000,
        command_sources=("protected_submit",),
        drain_initial_protection=True,
    )

    assert result["status"] == "command_confirmed"
    assert result["initial_protection_complete"] is False
    assert [call["order_type"] for call in gateway.calls] == ["market"]
    commands = {
        row["order_role"]: row
        for row in pg_control_connection.execute(
            text(
                "SELECT order_role, command_state, exchange_error_code, "
                "executed_qty, average_exec_price, result_facts_complete "
                "FROM brc_ticket_bound_exchange_commands "
                "WHERE protected_submit_attempt_id = :attempt_id"
            ),
            {"attempt_id": prepared["protected_submit_attempt_id"]},
        ).mappings()
    }
    assert commands["ENTRY"]["command_state"] == "confirmed_submitted"
    assert Decimal(str(commands["ENTRY"]["executed_qty"])) == Decimal("0")
    assert commands["ENTRY"]["average_exec_price"] is None
    assert commands["ENTRY"]["result_facts_complete"] in {True, 1}
    assert {
        role: commands[role]["command_state"] for role in ("SL", "TP1")
    } == {"SL": "reconciled_absent", "TP1": "reconciled_absent"}
    assert {
        commands[role]["exchange_error_code"] for role in ("SL", "TP1")
    } == {"entry_filled_qty_zero_no_protection_dispatch"}
    attempt = pg_control_connection.execute(
        text(
            "SELECT status, exchange_write_called "
            "FROM brc_ticket_bound_protected_submit_attempts "
            "WHERE protected_submit_attempt_id = :attempt_id"
        ),
        {"attempt_id": prepared["protected_submit_attempt_id"]},
    ).mappings().one()
    assert attempt["status"] == "submit_prepared"
    assert attempt["exchange_write_called"] in {True, 1}


@pytest.mark.asyncio
async def test_worker_persists_unknown_when_entry_fill_exceeds_requested_amount(
    pg_control_connection,
):
    ids = _create_ready_protected_submit(pg_control_connection)
    _prepare_real_submit(pg_control_connection, ids)
    for statement in (
        "ALTER TABLE brc_ticket_bound_exchange_commands ADD COLUMN exchange_order_status TEXT",
        "ALTER TABLE brc_ticket_bound_exchange_commands ADD COLUMN executed_qty NUMERIC",
        "ALTER TABLE brc_ticket_bound_exchange_commands ADD COLUMN average_exec_price NUMERIC",
        "ALTER TABLE brc_ticket_bound_exchange_commands ADD COLUMN exchange_observed_at_ms BIGINT",
        "ALTER TABLE brc_ticket_bound_exchange_commands ADD COLUMN result_facts_complete BOOLEAN NOT NULL DEFAULT false",
    ):
        pg_control_connection.execute(text(statement))
    pg_control_connection.commit()

    class ContradictoryFillGateway(_WorkerGateway):
        async def place_order(self, **kwargs):
            self.calls.append(dict(kwargs))
            return SimpleNamespace(
                is_success=True,
                exchange_order_id=f"exchange-{kwargs['client_order_id']}",
                filled_qty=Decimal(str(kwargs["amount"])) * Decimal("2"),
                average_exec_price=Decimal("2000"),
                exchange_order_status="FILLED",
            )

    result = await run_one_ticket_bound_exchange_command(
        pg_control_connection.engine,
        gateway=ContradictoryFillGateway(),
        worker_id="contradictory-fill-worker",
        now_ms=NOW_MS + 5000,
        command_sources=("protected_submit",),
    )

    assert result["status"] == "command_outcome_unknown"
    row = pg_control_connection.execute(
        text(
            "SELECT command_state, outcome_class, exchange_error_code "
            "FROM brc_ticket_bound_exchange_commands WHERE order_role = 'ENTRY'"
        )
    ).mappings().one()
    assert row["command_state"] == "outcome_unknown"
    assert row["outcome_class"] == "incomplete_response"
    assert row["exchange_error_code"] == "exchange_command_executed_qty_exceeds_amount"


@pytest.mark.asyncio
async def test_worker_persists_unknown_when_entry_average_fill_price_is_not_positive(
    pg_control_connection,
):
    ids = _create_ready_protected_submit(pg_control_connection)
    _prepare_real_submit(pg_control_connection, ids)
    for statement in (
        "ALTER TABLE brc_ticket_bound_exchange_commands ADD COLUMN exchange_order_status TEXT",
        "ALTER TABLE brc_ticket_bound_exchange_commands ADD COLUMN executed_qty NUMERIC",
        "ALTER TABLE brc_ticket_bound_exchange_commands ADD COLUMN average_exec_price NUMERIC",
        "ALTER TABLE brc_ticket_bound_exchange_commands ADD COLUMN exchange_observed_at_ms BIGINT",
        "ALTER TABLE brc_ticket_bound_exchange_commands ADD COLUMN result_facts_complete BOOLEAN NOT NULL DEFAULT false",
    ):
        pg_control_connection.execute(text(statement))
    pg_control_connection.commit()

    class InvalidAveragePriceGateway(_WorkerGateway):
        async def place_order(self, **kwargs):
            self.calls.append(dict(kwargs))
            return SimpleNamespace(
                is_success=True,
                exchange_order_id=f"exchange-{kwargs['client_order_id']}",
                filled_qty=kwargs["amount"],
                average_exec_price=Decimal("-1"),
                exchange_order_status="FILLED",
            )

    result = await run_one_ticket_bound_exchange_command(
        pg_control_connection.engine,
        gateway=InvalidAveragePriceGateway(),
        worker_id="invalid-average-price-worker",
        now_ms=NOW_MS + 5000,
        command_sources=("protected_submit",),
    )

    assert result["status"] == "command_outcome_unknown"
    row = pg_control_connection.execute(
        text(
            "SELECT command_state, exchange_error_code "
            "FROM brc_ticket_bound_exchange_commands WHERE order_role = 'ENTRY'"
        )
    ).mappings().one()
    assert row["command_state"] == "outcome_unknown"
    assert row["exchange_error_code"] == "exchange_command_optional_decimal_invalid"


@pytest.mark.asyncio
async def test_missing_entry_fill_truth_hard_stops_initial_protection_source(
    pg_control_connection,
):
    ids = _create_ready_protected_submit(pg_control_connection)
    prepared = _prepare_real_submit(pg_control_connection, ids)
    pg_control_connection.commit()

    class AcceptedWithoutFillGateway(_WorkerGateway):
        async def place_order(self, **kwargs):
            self.calls.append(dict(kwargs))
            return SimpleNamespace(
                is_success=True,
                exchange_order_id=f"exchange-{kwargs['client_order_id']}",
            )

    result = await run_one_ticket_bound_exchange_command(
        pg_control_connection.engine,
        gateway=AcceptedWithoutFillGateway(),
        worker_id="missing-fill-worker",
        now_ms=NOW_MS + 5000,
        command_sources=("protected_submit",),
        drain_initial_protection=True,
    )

    assert result["initial_protection_complete"] is False
    states = {
        row["order_role"]: row["command_state"]
        for row in pg_control_connection.execute(
            text(
                "SELECT order_role, command_state "
                "FROM brc_ticket_bound_exchange_commands "
                "WHERE protected_submit_attempt_id = :attempt_id"
            ),
            {"attempt_id": prepared["protected_submit_attempt_id"]},
        ).mappings()
    }
    assert states["ENTRY"] == "confirmed_submitted"
    assert states["SL"] == "hard_stopped"
    assert states["TP1"] == "reconciled_absent"
    attempt = pg_control_connection.execute(
        text(
            "SELECT status, blockers FROM brc_ticket_bound_protected_submit_attempts "
            "WHERE protected_submit_attempt_id = :attempt_id"
        ),
        {"attempt_id": prepared["protected_submit_attempt_id"]},
    ).mappings().one()
    assert attempt["status"] in {"submit_failed", "hard_stopped"}
    assert "entry_filled_qty" in str(attempt["blockers"])


@pytest.mark.asyncio
async def test_partial_cleanup_resumes_from_committed_command_without_repeating_cancel(
    pg_control_connection,
):
    set_id = _flat_position_live_protection(pg_control_connection)
    source = prepare_ticket_bound_orphan_protection_cleanup_command(
        pg_control_connection,
        exit_protection_set_id=set_id,
        now_ms=NOW_MS + 6000,
    )
    source_id = source["orphan_protection_cleanup_command_id"]
    materialize_lifecycle_exchange_commands(
        pg_control_connection,
        command_source="orphan_cleanup",
        source_command_id=source_id,
        now_ms=NOW_MS + 7000,
    )
    pg_control_connection.commit()
    gateway = _WorkerGateway()

    first = await run_one_ticket_bound_exchange_command(
        pg_control_connection.engine,
        gateway=gateway,
        worker_id="cleanup-worker-before-restart",
        now_ms=NOW_MS + 8000,
        command_sources=("orphan_cleanup",),
    )
    with pg_control_connection.engine.connect() as conn:
        states_after_first = conn.execute(
            text(
                "SELECT command_state FROM brc_ticket_bound_exchange_commands "
                "WHERE source_command_id = :source_id ORDER BY command_generation"
            ),
            {"source_id": source_id},
        ).scalars().all()
    second = await run_one_ticket_bound_exchange_command(
        pg_control_connection.engine,
        gateway=gateway,
        worker_id="cleanup-worker-after-restart",
        now_ms=NOW_MS + 9000,
        command_sources=("orphan_cleanup",),
    )

    assert first["status"] == "command_confirmed"
    assert states_after_first == ["confirmed_submitted", "prepared"]
    assert second["status"] == "command_confirmed"
    assert len(gateway.calls) == 2
    assert len({call["exchange_order_id"] for call in gateway.calls}) == 2
    with pg_control_connection.engine.connect() as conn:
        assert conn.execute(
            text(
                "SELECT status FROM brc_ticket_bound_orphan_protection_cleanup_commands "
                "WHERE orphan_protection_cleanup_command_id = :source_id"
            ),
            {"source_id": source_id},
        ).scalar_one() == "result_recorded"


def test_terminal_command_blocks_only_its_netting_domain(pg_control_connection):
    ids = _create_ready_protected_submit(pg_control_connection)
    _prepare_real_submit(pg_control_connection, ids)
    rows = list(
        pg_control_connection.execute(
            text(
                "SELECT exchange_command_id, order_role, netting_domain_key "
                "FROM brc_ticket_bound_exchange_commands ORDER BY command_generation"
            )
        ).mappings()
    )
    entry = next(row for row in rows if row["order_role"] == "ENTRY")
    sl = next(row for row in rows if row["order_role"] == "SL")
    pg_control_connection.execute(
        text(
            "UPDATE brc_ticket_bound_exchange_commands "
            "SET command_state = 'outcome_unknown' "
            "WHERE exchange_command_id = :command_id"
        ),
        {"command_id": entry["exchange_command_id"]},
    )
    pg_control_connection.execute(
        text(
            "UPDATE brc_ticket_bound_exchange_commands "
            "SET netting_domain_key = :isolated_domain, "
            "    command_source = 'orphan_cleanup' "
            "WHERE exchange_command_id = :command_id"
        ),
        {
            "command_id": sl["exchange_command_id"],
            "isolated_domain": f"{sl['netting_domain_key']}|isolated-subaccount",
        },
    )

    claimed = claim_next_exchange_command(
        pg_control_connection,
        claim_owner="isolated-domain-worker",
        now_ms=NOW_MS + 5000,
        command_sources=("orphan_cleanup",),
    )

    assert claimed["exchange_command_id"] == sl["exchange_command_id"]
    assert claimed["order_role"] == "SL"
