from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
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
                "SELECT order_role, command_state, claim_token "
                "FROM brc_ticket_bound_exchange_commands "
                "WHERE exchange_command_id = :command_id"
            ),
            {"command_id": result["exchange_command_id"]},
        ).mappings().one()
    assert row["order_role"] == "ENTRY"
    assert row["command_state"] == "confirmed_submitted"
    assert row["claim_token"]


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
            "SET netting_domain_key = :isolated_domain "
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
        command_sources=("protected_submit",),
    )

    assert claimed["exchange_command_id"] == sl["exchange_command_id"]
    assert claimed["order_role"] == "SL"
