from __future__ import annotations

# ruff: noqa: F401, F811

import asyncio
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from scripts import run_ticket_bound_lifecycle_maintenance_once as lifecycle_cli
from src.application.action_time import exchange_command_worker
from src.infrastructure.binance_usdm_account_risk_snapshot import FullAccountRiskSnapshot
from tests.unit.test_action_time_ticket_materialization import NOW_MS
from tests.unit.test_ticket_bound_protected_submit_attempt import (
    _create_ready_protected_submit,
    _prepare_real_submit,
)
from tests.unit.test_ticket_bound_runtime_safety_state_materialization import (
    pg_control_connection,
)


def test_cli_global_deadline_defaults_below_systemd_timeout():
    args = lifecycle_cli._parse_args(["--database-url", "postgresql://unit"])

    assert args.global_deadline_seconds == 28.0
    assert args.global_deadline_seconds < 35.0
    assert args.entry_command_timeout_seconds == 6.0
    assert args.initial_stop_command_timeout_seconds == 6.0
    assert args.tp1_command_timeout_seconds == 4.0
    assert args.deadline_commit_margin_seconds == 5.0
    assert args.entry_result_commit_reserve_seconds == 1.0
    assert args.initial_stop_result_commit_reserve_seconds == 1.0
    assert args.deadline_shutdown_reserve_seconds == 1.0


def test_cli_passes_the_exact_invocation_deadline_and_phase_budgets():
    args = lifecycle_cli._parse_args(["--database-url", "postgresql://unit"])

    assert lifecycle_cli._exchange_command_deadline_kwargs(
        args,
        absolute_deadline_at=123.456,
    ) == {
        "absolute_deadline_at": 123.456,
        "entry_network_timeout_seconds": 6.0,
        "initial_stop_network_timeout_seconds": 6.0,
        "tp1_network_timeout_seconds": 4.0,
        "deadline_commit_margin_seconds": 5.0,
        "entry_result_commit_reserve_seconds": 1.0,
        "initial_stop_result_commit_reserve_seconds": 1.0,
        "shutdown_reserve_seconds": 1.0,
    }


@pytest.mark.parametrize(
    "flag",
    (
        "--entry-command-timeout-seconds",
        "--initial-stop-command-timeout-seconds",
        "--tp1-command-timeout-seconds",
        "--deadline-commit-margin-seconds",
        "--entry-result-commit-reserve-seconds",
        "--initial-stop-result-commit-reserve-seconds",
        "--deadline-shutdown-reserve-seconds",
    ),
)
@pytest.mark.parametrize("value", ("nan", "inf", "-inf"))
def test_cli_rejects_non_finite_exchange_command_budgets(flag, value):
    with pytest.raises(SystemExit):
        lifecycle_cli._parse_args(
            ["--database-url", "postgresql://unit", flag, value]
        )


@pytest.mark.parametrize(
    "extra_args",
    (
        ("--global-deadline-seconds", "15"),
        ("--command-lease-ms", "10999"),
    ),
)
def test_cli_rejects_invalid_deadline_and_lease_inequalities(extra_args):
    with pytest.raises(SystemExit):
        lifecycle_cli._parse_args(
            ["--database-url", "postgresql://unit", *extra_args]
        )


def test_expired_global_deadline_blocks_next_stage(monkeypatch):
    monkeypatch.setattr(lifecycle_cli.time, "monotonic", lambda: 100.0)

    with pytest.raises(
        TimeoutError,
        match="lifecycle_global_deadline_exceeded:exchange_snapshot",
    ):
        lifecycle_cli._remaining_seconds(100.0, "exchange_snapshot")


@pytest.mark.asyncio
async def test_awaitable_is_cancelled_when_global_deadline_expires(monkeypatch):
    monkeypatch.setattr(lifecycle_cli.time, "monotonic", lambda: 100.0)
    coroutine = asyncio.sleep(0)
    try:
        with pytest.raises(TimeoutError):
            await lifecycle_cli._await_before_deadline(
                coroutine,
                deadline_at=100.0,
                stage="durable_exchange_command",
            )
    finally:
        coroutine.close()


@pytest.mark.asyncio
async def test_entry_drain_uses_the_invocation_absolute_deadline_without_resetting_budget(
    monkeypatch,
    pg_control_connection,
):
    """ENTRY can consume the invocation budget; the SL drain cannot renew it."""

    ids = _create_ready_protected_submit(pg_control_connection)
    _prepare_real_submit(pg_control_connection, ids)
    pg_control_connection.commit()
    clock = {"now": 100.0}

    class DeadlineConsumingGateway:
        runtime_account_id = "owner-subaccount-runtime-v0"
        runtime_exchange_id = "binance_usdm"

        def __init__(self) -> None:
            self.calls: list[dict] = []

        async def place_order(self, **kwargs):
            self.calls.append(dict(kwargs))
            if kwargs["order_type"] == "market":
                clock["now"] = 109.999
            return SimpleNamespace(
                is_success=True,
                exchange_order_id=f"exchange-{kwargs['client_order_id']}",
                filled_qty=kwargs["amount"],
                average_exec_price=Decimal("2000"),
                exchange_order_status="FILLED",
            )

    monkeypatch.setattr(
        exchange_command_worker.time,
        "monotonic",
        lambda: clock["now"],
    )
    gateway = DeadlineConsumingGateway()
    result = await exchange_command_worker.run_one_ticket_bound_exchange_command(
        pg_control_connection.engine,
        gateway=gateway,
        worker_id="absolute-deadline-worker",
        now_ms=NOW_MS + 5000,
        command_sources=("protected_submit",),
        dispatch_timeout_seconds=10.0,
        absolute_deadline_at=110.0,
        entry_network_timeout_seconds=1.0,
        initial_stop_network_timeout_seconds=1.0,
        tp1_network_timeout_seconds=1.0,
        entry_result_commit_reserve_seconds=0.25,
        initial_stop_result_commit_reserve_seconds=0.25,
        shutdown_reserve_seconds=0.5,
        drain_initial_protection=True,
    )

    assert result["order_role"] == "ENTRY"
    assert result["initial_protection_complete"] is False
    assert [call["order_type"] for call in gateway.calls] == ["market"]
    assert pg_control_connection.execute(
        text(
            "SELECT command_state FROM brc_ticket_bound_exchange_commands "
            "WHERE order_role = 'SL'"
        )
    ).scalar_one() == "prepared"
    assert result["exchange_telemetry"]["exchange_request_count"] == 1
    assert result["exchange_telemetry"]["absolute_deadline_at"] == 110.0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("remaining_seconds", "expected_gateway_calls"),
    ((4.999, 0), (5.0, 0), (6.0, 1)),
)
async def test_worker_fails_closed_at_deadline_commit_margin_boundary(
    monkeypatch,
    pg_control_connection,
    remaining_seconds,
    expected_gateway_calls,
):
    ids = _create_ready_protected_submit(pg_control_connection)
    prepared = _prepare_real_submit(pg_control_connection, ids)
    pg_control_connection.commit()
    await exchange_command_worker.run_one_ticket_bound_exchange_command(
        pg_control_connection.engine,
        gateway=_DeadlineGateway(),
        worker_id="deadline-boundary-entry",
        now_ms=NOW_MS + 5000,
        command_sources=("protected_submit",),
        allowed_roles=("ENTRY",),
    )
    clock = {"now": 100.0}
    monkeypatch.setattr(
        exchange_command_worker.time,
        "monotonic",
        lambda: clock["now"],
    )
    gateway = _DeadlineGateway()
    result = await exchange_command_worker.run_one_ticket_bound_exchange_command(
        pg_control_connection.engine,
        gateway=gateway,
        worker_id="deadline-boundary-stop",
        now_ms=NOW_MS + 5001,
        lease_ms=6_000,
        command_sources=("protected_submit",),
        source_command_id=prepared["protected_submit_attempt_id"],
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        allowed_roles=("SL",),
        dispatch_timeout_seconds=10.0,
        absolute_deadline_at=clock["now"] + remaining_seconds,
    )

    assert len(gateway.calls) == expected_gateway_calls
    if expected_gateway_calls:
        assert result["status"] == "command_confirmed"
        assert result["exchange_telemetry"]["phases"][0][
            "effective_timeout_seconds"
        ] == 1.0
    else:
        assert result["first_blocker"] == (
            "exchange_command_deadline_budget_exhausted_before_io"
        )
        assert pg_control_connection.execute(
            text(
                "SELECT command_state FROM brc_ticket_bound_exchange_commands "
                "WHERE order_role = 'SL'"
            )
        ).scalar_one() == "prepared"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("remaining_seconds", "expected_gateway_calls"),
    ((14.999, 0), (15.0, 1)),
)
async def test_worker_reserves_initial_protection_budget_before_entry_claim(
    monkeypatch,
    pg_control_connection,
    remaining_seconds,
    expected_gateway_calls,
):
    ids = _create_ready_protected_submit(pg_control_connection)
    _prepare_real_submit(pg_control_connection, ids)
    pg_control_connection.commit()
    clock = {"now": 100.0}
    monkeypatch.setattr(
        exchange_command_worker.time,
        "monotonic",
        lambda: clock["now"],
    )
    gateway = _DeadlineGateway()
    result = await exchange_command_worker.run_one_ticket_bound_exchange_command(
        pg_control_connection.engine,
        gateway=gateway,
        worker_id="pre-entry-reserve-worker",
        now_ms=NOW_MS + 5000,
        lease_ms=35_000,
        command_sources=("protected_submit",),
        allowed_roles=("ENTRY",),
        dispatch_timeout_seconds=10.0,
        absolute_deadline_at=clock["now"] + remaining_seconds,
    )

    assert len(gateway.calls) == expected_gateway_calls
    if expected_gateway_calls:
        assert result["status"] == "command_confirmed"
    else:
        assert result["first_blocker"] == (
            "protection_deadline_budget_insufficient_before_entry"
        )
        command = pg_control_connection.execute(
            text(
                "SELECT command_state, execution_attempt_count FROM "
                "brc_ticket_bound_exchange_commands WHERE order_role = 'ENTRY'"
            )
        ).mappings().one()
        assert command == {
            "command_state": "prepared",
            "execution_attempt_count": 0,
        }
        assert result["exchange_telemetry"]["exchange_request_count"] == 0


class _DeadlineGateway:
    runtime_account_id = "owner-subaccount-runtime-v0"
    runtime_exchange_id = "binance_usdm"

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def place_order(self, **kwargs):
        self.calls.append(dict(kwargs))
        return SimpleNamespace(
            is_success=True,
            exchange_order_id=f"exchange-{kwargs['client_order_id']}",
            filled_qty=kwargs["amount"],
            average_exec_price=Decimal("2000"),
            exchange_order_status="FILLED",
        )


@pytest.mark.asyncio
async def test_entry_sl_tp1_share_one_deadline_and_decreasing_budget(
    monkeypatch,
    pg_control_connection,
):
    ids = _create_ready_protected_submit(pg_control_connection)
    _prepare_real_submit(pg_control_connection, ids)
    pg_control_connection.commit()
    clock = {"now": 100.0}

    class AdvancingGateway(_DeadlineGateway):
        async def place_order(self, **kwargs):
            result = await super().place_order(**kwargs)
            clock["now"] += 1.0
            return result

    monkeypatch.setattr(
        exchange_command_worker.time,
        "monotonic",
        lambda: clock["now"],
    )
    result = await exchange_command_worker.run_one_ticket_bound_exchange_command(
        pg_control_connection.engine,
        gateway=AdvancingGateway(),
        worker_id="same-deadline-worker",
        now_ms=NOW_MS + 5000,
        lease_ms=35_000,
        command_sources=("protected_submit",),
        dispatch_timeout_seconds=10.0,
        absolute_deadline_at=130.0,
        drain_initial_protection=True,
    )

    telemetry = result["exchange_telemetry"]
    assert result["initial_protection_complete"] is True
    assert telemetry["exchange_request_count"] == 3
    assert [item["order_role"] for item in telemetry["phases"]] == [
        "ENTRY",
        "SL",
        "TP1",
    ]
    assert {item["absolute_deadline_at"] for item in telemetry["phases"]} == {
        130.0
    }
    assert [
        item["deadline_remaining_before_seconds"]
        for item in telemetry["phases"]
    ] == [30.0, 29.0, 28.0]
    assert [item["effective_timeout_seconds"] for item in telemetry["phases"]] == [
        6.0,
        6.0,
        4.0,
    ]
    assert all(item["result_commit_latency_ms"] >= 0 for item in telemetry["phases"])
    assert telemetry["entry_to_initial_stop_latency_ms"] == 1_000
    assert [
        item["result_committed_at_monotonic"] for item in telemetry["phases"]
    ] == [101.0, 102.0, 103.0]


@pytest.mark.asyncio
async def test_worker_rechecks_deadline_after_claim_before_gateway_io(
    monkeypatch,
    pg_control_connection,
):
    ids = _create_ready_protected_submit(pg_control_connection)
    prepared = _prepare_real_submit(pg_control_connection, ids)
    pg_control_connection.commit()
    await exchange_command_worker.run_one_ticket_bound_exchange_command(
        pg_control_connection.engine,
        gateway=_DeadlineGateway(),
        worker_id="deadline-recheck-entry",
        now_ms=NOW_MS + 5000,
        command_sources=("protected_submit",),
        allowed_roles=("ENTRY",),
    )
    clock = {"calls": 0}

    def monotonic() -> float:
        clock["calls"] += 1
        return 100.0 if clock["calls"] == 1 else 106.0

    monkeypatch.setattr(exchange_command_worker.time, "monotonic", monotonic)
    gateway = _DeadlineGateway()
    result = await exchange_command_worker.run_one_ticket_bound_exchange_command(
        pg_control_connection.engine,
        gateway=gateway,
        worker_id="deadline-recheck-stop",
        now_ms=NOW_MS + 5001,
        lease_ms=35_000,
        command_sources=("protected_submit",),
        source_command_id=prepared["protected_submit_attempt_id"],
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        allowed_roles=("SL",),
        absolute_deadline_at=111.0,
    )

    assert clock["calls"] >= 2
    assert gateway.calls == []
    assert result["first_blocker"] == (
        "exchange_command_deadline_budget_exhausted_before_io"
    )
    assert pg_control_connection.execute(
        text(
            "SELECT command_state, execution_attempt_count FROM "
            "brc_ticket_bound_exchange_commands WHERE order_role = 'SL'"
        )
    ).mappings().one() == {
        "command_state": "prepared",
        "execution_attempt_count": 0,
    }


@pytest.mark.asyncio
async def test_result_commit_latency_excludes_lifecycle_completion_transaction(
    monkeypatch,
    pg_control_connection,
):
    ids = _create_ready_protected_submit(pg_control_connection)
    _prepare_real_submit(pg_control_connection, ids)
    pg_control_connection.commit()
    perf_clock = {"now": 100.0}
    original_completion = (
        exchange_command_worker.apply_completed_lifecycle_exchange_sources
    )

    def delayed_completion(*args, **kwargs):
        perf_clock["now"] += 5.0
        return original_completion(*args, **kwargs)

    monkeypatch.setattr(
        exchange_command_worker.time,
        "perf_counter",
        lambda: perf_clock["now"],
    )
    monkeypatch.setattr(
        exchange_command_worker,
        "apply_completed_lifecycle_exchange_sources",
        delayed_completion,
    )
    result = await exchange_command_worker.run_one_ticket_bound_exchange_command(
        pg_control_connection.engine,
        gateway=_DeadlineGateway(),
        worker_id="result-commit-latency-worker",
        now_ms=NOW_MS + 5000,
        command_sources=("protected_submit",),
        allowed_roles=("ENTRY",),
    )

    assert result["exchange_telemetry"]["phases"][0][
        "result_commit_latency_ms"
    ] == 0


@pytest.mark.asyncio
async def test_tp1_deadline_exhaustion_preserves_confirmed_initial_stop(
    monkeypatch,
    pg_control_connection,
):
    ids = _create_ready_protected_submit(pg_control_connection)
    _prepare_real_submit(pg_control_connection, ids)
    pg_control_connection.commit()
    clock = {"now": 100.0}

    class StopConsumesBudgetGateway(_DeadlineGateway):
        async def place_order(self, **kwargs):
            result = await super().place_order(**kwargs)
            if kwargs["order_type"] == "market":
                clock["now"] = 105.0
            elif kwargs["order_type"] == "stop_market":
                clock["now"] = 120.0
            return result

    monkeypatch.setattr(
        exchange_command_worker.time,
        "monotonic",
        lambda: clock["now"],
    )
    gateway = StopConsumesBudgetGateway()
    result = await exchange_command_worker.run_one_ticket_bound_exchange_command(
        pg_control_connection.engine,
        gateway=gateway,
        worker_id="tp1-budget-exhaustion",
        now_ms=NOW_MS + 5000,
        lease_ms=35_000,
        command_sources=("protected_submit",),
        dispatch_timeout_seconds=10.0,
        absolute_deadline_at=125.0,
        drain_initial_protection=True,
    )

    assert [call["order_type"] for call in gateway.calls] == [
        "market",
        "stop_market",
    ]
    assert result["initial_protection_complete"] is True
    assert result["exchange_telemetry"]["exchange_request_count"] == 2
    assert result["initial_protection_drain"][-1]["first_blocker"] == (
        "exchange_command_deadline_budget_exhausted_before_io"
    )
    states = dict(
        pg_control_connection.execute(
            text(
                "SELECT order_role, command_state FROM "
                "brc_ticket_bound_exchange_commands WHERE order_role IN ('SL', 'TP1')"
            )
        ).all()
    )
    assert states == {"SL": "confirmed_submitted", "TP1": "prepared"}


@pytest.mark.asyncio
@pytest.mark.parametrize(("lease_ms", "allowed"), ((7_000, True), (6_999, False)))
async def test_worker_lease_inequality_uses_deadline_capped_timeout(
    monkeypatch,
    pg_control_connection,
    lease_ms,
    allowed,
):
    ids = _create_ready_protected_submit(pg_control_connection)
    prepared = _prepare_real_submit(pg_control_connection, ids)
    pg_control_connection.commit()
    await exchange_command_worker.run_one_ticket_bound_exchange_command(
        pg_control_connection.engine,
        gateway=_DeadlineGateway(),
        worker_id="lease-cap-entry",
        now_ms=NOW_MS + 5000,
        command_sources=("protected_submit",),
        allowed_roles=("ENTRY",),
    )
    monkeypatch.setattr(exchange_command_worker.time, "monotonic", lambda: 103.0)
    gateway = _DeadlineGateway()
    call = exchange_command_worker.run_one_ticket_bound_exchange_command(
        pg_control_connection.engine,
        gateway=gateway,
        worker_id="lease-cap-stop",
        now_ms=NOW_MS + 5001,
        lease_ms=lease_ms,
        command_sources=("protected_submit",),
        source_command_id=prepared["protected_submit_attempt_id"],
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        allowed_roles=("SL",),
        dispatch_timeout_seconds=10.0,
        absolute_deadline_at=110.0,
    )
    if not allowed:
        with pytest.raises(
            ValueError,
            match="exchange_command_lease_timeout_budget_invalid",
        ):
            await call
        assert gateway.calls == []
        return
    result = await call
    assert result["status"] == "command_confirmed"
    assert result["exchange_telemetry"]["phases"][0][
        "effective_timeout_seconds"
    ] == 2.0


def test_gateway_probe_owns_durable_protected_submit_command_source(
    pg_control_connection,
):
    ids = _create_ready_protected_submit(pg_control_connection)
    _prepare_real_submit(pg_control_connection, ids)

    assert (
        lifecycle_cli._prepared_or_unknown_command_exists(pg_control_connection)
        is True
    )

    pg_control_connection.execute(
        text(
            "UPDATE brc_ticket_bound_exchange_commands "
            "SET command_source = 'protection_recovery' "
            "WHERE order_role = 'SL'"
        )
    )

    assert (
        lifecycle_cli._prepared_or_unknown_command_exists(pg_control_connection)
        is True
    )


def test_active_account_risk_scope_requires_matching_active_policy(
    monkeypatch,
):
    class _Policies:
        c = SimpleNamespace(
            account_id="account_id",
            runtime_profile_id="runtime_profile_id",
            activation_state="activation_state",
        )

    class _Conn:
        def execute(self, _query):
            return SimpleNamespace(
                mappings=lambda: [
                    {
                        "account_id": "account-1",
                        "runtime_profile_id": "profile-1",
                    }
                ]
            )

    monkeypatch.setattr(lifecycle_cli.sa, "inspect", lambda _conn: SimpleNamespace(has_table=lambda _name: True))
    monkeypatch.setattr(lifecycle_cli.sa, "Table", lambda *_args, **_kwargs: _Policies())
    monkeypatch.setattr(lifecycle_cli.sa, "select", lambda *_args: SimpleNamespace(where=lambda *_args: object()))
    scopes = lifecycle_cli._active_account_risk_scopes(
        _Conn(),
        prepared_scopes=[
            {
                "scope": SimpleNamespace(
                    ticket_id="ticket-1",
                    account_id="account-1",
                    runtime_profile_id="profile-1",
                    exchange_id="binance_usdm",
                )
            },
            {
                "scope": SimpleNamespace(
                    ticket_id="ticket-2",
                    account_id="account-1",
                    runtime_profile_id="profile-other",
                    exchange_id="binance_usdm",
                )
            },
        ],
    )

    assert scopes == {
        "account_risk_scope:account-1:profile-1": (
            "account-1",
            "profile-1",
            "binance_usdm",
        ),
        "ticket-1": ("account-1", "profile-1", "binance_usdm"),
    }


@pytest.mark.asyncio
async def test_account_risk_snapshot_prefetch_deduplicates_account_reads(monkeypatch):
    calls: list[tuple[str, str]] = []

    async def fake_fetch(**kwargs):
        calls.append((kwargs["account_id"], kwargs["exchange_id"]))
        return _account_snapshot(kwargs["account_id"], kwargs["exchange_id"])

    monkeypatch.setattr(lifecycle_cli, "_fetch_account_risk_snapshot", fake_fetch)
    snapshots = await lifecycle_cli._prefetch_account_risk_snapshots(
        {
            "ticket-a": ("account-1", "profile-1", "binance_usdm"),
            "ticket-b": ("account-1", "profile-1", "binance_usdm"),
        },
        env_file=Path("/nonexistent"),
        base_url="https://example.invalid",
        timeout_seconds=1.0,
    )

    assert calls == [("account-1", "binance_usdm")]
    assert snapshots["ticket-a"] is snapshots["ticket-b"]
    assert snapshots["ticket-a"].account_id == "account-1"


def _account_snapshot(account_id: str, exchange_id: str) -> FullAccountRiskSnapshot:
    return FullAccountRiskSnapshot(
        snapshot_ready=True,
        account_id=account_id,
        exchange_id=exchange_id,
        total_wallet_balance=Decimal("600"),
        available_balance=Decimal("500"),
        exchange_total_initial_margin=Decimal("100"),
        can_trade=True,
        position_mode="one_way",
        source_snapshot_id="snapshot-1",
        observed_at_ms=1_752_480_000_000,
        valid_until_ms=1_752_480_060_000,
    )
