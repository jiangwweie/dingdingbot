from __future__ import annotations

import json

import pytest
from sqlalchemy import text

from src.application.action_time.exchange_command import (
    mark_exchange_command_dispatching,
    record_exchange_command_outcome,
)
from src.application.action_time.exchange_command_reconciliation import (
    lookup_unknown_exchange_command,
    reconcile_unknown_exchange_commands,
    run_one_unknown_exchange_command_reconciliation,
)
from src.application.action_time.netting_domain_hold import (
    upsert_exchange_command_domain_hold,
    upsert_netting_domain_hold,
)
from src.domain.ticket_bound_exchange_command import (
    ExchangeCommandOutcomeClass,
    ExchangeOrderLookupRequest,
    ExchangeOrderLookupResult,
    ExchangeOrderLookupStatus,
    ExchangeOrderLookupView,
    ExchangeCommandState,
    required_exchange_order_lookup_view,
)
from tests.unit.test_action_time_ticket_materialization import NOW_MS
from tests.unit.test_ticket_bound_protected_submit_attempt import (
    _create_ready_protected_submit,
    _prepare_real_submit,
)
from tests.unit.test_ticket_bound_runtime_safety_state_materialization import (
    pg_control_connection,
)


def test_conditional_lookup_request_conserves_role_type_and_identity() -> None:
    request = ExchangeOrderLookupRequest(
        exchange_id="binance_usdm",
        gateway_symbol="SOL/USDT:USDT",
        command_kind="place_order",
        order_role="SL",
        order_type="stop_market",
        client_order_id="brc-client-sl",
    )

    assert request.order_role == "SL"
    assert request.order_type == "stop_market"
    assert request.client_order_id == "brc-client-sl"


def test_lookup_result_requires_exchange_identity_for_found_status() -> None:
    with pytest.raises(ValueError, match="found lookup requires exchange_order_id"):
        ExchangeOrderLookupResult(
            status="found",
            lookup_view="conditional_algo_order",
            identity_kind="clientAlgoId",
            observed_at_ms=1,
            client_order_id="brc-client-sl",
            gateway_symbol="SOL/USDT:USDT",
        )


def test_not_found_lookup_result_preserves_required_view_evidence() -> None:
    result = ExchangeOrderLookupResult(
        status="not_found",
        lookup_view="conditional_algo_order",
        identity_kind="clientAlgoId",
        observed_at_ms=2,
        client_order_id="brc-client-sl",
        gateway_symbol="SOL/USDT:USDT",
    )

    assert result.exchange_order_id is None
    assert result.lookup_view.value == "conditional_algo_order"


@pytest.mark.parametrize(
    ("exchange_id", "order_role", "order_type", "expected_view"),
    [
        ("binance_usdm", "ENTRY", "market", "regular_order"),
        ("binance_usdm", "SL", "stop_market", "conditional_algo_order"),
        ("okx_swap", "SL", "stop_market", "regular_order"),
    ],
)
def test_required_lookup_view_is_resolved_from_the_typed_venue_request(
    exchange_id: str,
    order_role: str,
    order_type: str,
    expected_view: str,
) -> None:
    request = ExchangeOrderLookupRequest(
        exchange_id=exchange_id,
        gateway_symbol="SOL/USDT:USDT",
        command_kind="place_order",
        order_role=order_role,
        order_type=order_type,
        client_order_id="brc-client-id",
    )

    assert required_exchange_order_lookup_view(request).value == expected_view


@pytest.mark.parametrize(
    ("order_role", "expected_view"),
    [
        ("ENTRY", "regular_order"),
        ("TP1", "regular_order"),
        ("SL", "conditional_algo_order"),
    ],
)
@pytest.mark.asyncio
async def test_unknown_place_command_uses_persisted_required_view(
    pg_control_connection,
    order_role: str,
    expected_view: str,
):
    command = _unknown_place_command(pg_control_connection, order_role=order_role)
    gateway = _TypedLookupGateway(_found_result(command, expected_view))

    report = await reconcile_unknown_exchange_commands(
        pg_control_connection,
        gateway=gateway,
        now_ms=NOW_MS + 5000,
        max_commands=10,
    )

    assert report["reconciled_submitted"] == 1
    assert _command_state(pg_control_connection, order_role=order_role) == (
        "reconciled_submitted"
    )
    assert gateway.requests[0][0].order_role == order_role
    assert gateway.requests[0][0].order_type == command["order_type"]
    assert gateway.requests[0][0].client_order_id == command["client_order_id"]
    assert gateway.requests[0][0].gateway_symbol == command["gateway_symbol"]
    assert gateway.requests[0][0].order_role == order_role
    assert gateway.result.lookup_view.value == expected_view
    assert gateway.place_order_calls == 0


@pytest.mark.asyncio
async def test_unknown_command_reconciles_absent_after_visibility_window(
    pg_control_connection,
):
    command = _unknown_place_command(pg_control_connection, order_role="ENTRY")
    gateway = _TypedLookupGateway(_not_found_result(command))

    report = await reconcile_unknown_exchange_commands(
        pg_control_connection,
        gateway=gateway,
        now_ms=NOW_MS + 40_000,
        max_commands=10,
    )

    assert report["reconciled_absent"] == 1
    assert _command_state(pg_control_connection) == "reconciled_absent"
    assert report["automatic_resubmit_called"] is False
    assert gateway.place_order_calls == 0


@pytest.mark.asyncio
async def test_unknown_command_stays_pending_inside_visibility_window(
    pg_control_connection,
):
    command = _unknown_place_command(pg_control_connection, order_role="ENTRY")

    report = await reconcile_unknown_exchange_commands(
        pg_control_connection,
        gateway=_TypedLookupGateway(_not_found_result(command)),
        now_ms=NOW_MS + 10_000,
        max_commands=10,
    )

    assert report["pending_visibility"] == 1
    assert _command_state(pg_control_connection) == "outcome_unknown"


@pytest.mark.asyncio
async def test_contradictory_client_identity_hard_stops_command(
    pg_control_connection,
):
    command = _unknown_place_command(pg_control_connection, order_role="ENTRY")
    gateway = _TypedLookupGateway(
        _found_result(
            command,
            "regular_order",
            client_order_id="different-client-id",
        )
    )

    report = await reconcile_unknown_exchange_commands(
        pg_control_connection,
        gateway=gateway,
        now_ms=NOW_MS + 5000,
        max_commands=10,
    )

    assert report["hard_stopped"] == 1
    assert _command_state(pg_control_connection) == "hard_stopped"


@pytest.mark.asyncio
async def test_production_reconciliation_worker_commits_around_lookup(
    pg_control_connection,
):
    command = _unknown_place_command(pg_control_connection, order_role="ENTRY")
    pg_control_connection.commit()
    gateway = _TypedLookupGateway(_found_result(command, "regular_order"))

    report = await run_one_unknown_exchange_command_reconciliation(
        pg_control_connection.engine,
        gateway=gateway,
        now_ms=NOW_MS + 5000,
    )

    assert report["status"] == "reconciled_submitted"
    assert report["exchange_read_called"] is True
    assert report["exchange_write_called"] is False
    assert _command_state(pg_control_connection) == "reconciled_submitted"


@pytest.mark.asyncio
async def test_conditional_regular_view_evidence_hard_stops_command(
    pg_control_connection,
):
    command = _unknown_place_command(pg_control_connection, order_role="SL")
    gateway = _TypedLookupGateway(_found_result(command, "regular_order"))

    report = await reconcile_unknown_exchange_commands(
        pg_control_connection,
        gateway=gateway,
        now_ms=NOW_MS + 5_000,
        max_commands=10,
    )

    assert report["hard_stopped"] == 1
    assert _command_state(pg_control_connection, order_role="SL") == "hard_stopped"
    evidence = _exchange_result(pg_control_connection, order_role="SL")
    assert evidence["lookup_view"] == "regular_order"
    assert evidence["error_message"] == "required_lookup_view_mismatch"


@pytest.mark.asyncio
async def test_non_binance_stop_lookup_accepts_regular_view(
    pg_control_connection,
):
    command = {
        **_unknown_place_command(pg_control_connection, order_role="SL"),
        "exchange_id": "okx_swap",
    }
    gateway = _TypedLookupGateway(_found_result(command, "regular_order"))

    decision = await lookup_unknown_exchange_command(
        command=command,
        gateway=gateway,
        now_ms=NOW_MS + 5_000,
    )

    assert decision["status"] == "reconciled_submitted"
    assert gateway.requests[0][0].exchange_id == "okx_swap"
    assert decision["lookup_evidence"]["lookup_view"] == "regular_order"


@pytest.mark.asyncio
async def test_runner_stop_command_uses_conditional_required_view(
    pg_control_connection,
):
    source = _unknown_place_command(pg_control_connection, order_role="SL")
    command = {
        **source,
        "order_role": "RUNNER_SL",
        "order_type": "stop_market",
        "client_order_id": "runner-client-id",
    }
    gateway = _TypedLookupGateway(
        ExchangeOrderLookupResult(
            status=ExchangeOrderLookupStatus.FOUND,
            lookup_view=ExchangeOrderLookupView.CONDITIONAL_ALGO_ORDER,
            identity_kind="clientAlgoId",
            observed_at_ms=NOW_MS + 5_000,
            exchange_order_id="runner-algo-id",
            client_order_id="runner-client-id",
            gateway_symbol=source["gateway_symbol"],
        )
    )

    decision = await lookup_unknown_exchange_command(
        command=command,
        gateway=gateway,
        now_ms=NOW_MS + 5_000,
    )

    assert decision["status"] == "reconciled_submitted"
    assert gateway.requests[0][0].order_role == "RUNNER_SL"
    assert gateway.requests[0][0].order_type == "stop_market"
    assert decision["lookup_evidence"]["lookup_view"] == "conditional_algo_order"


@pytest.mark.asyncio
async def test_lookup_failure_retains_unknown_state_and_its_domain_hold(
    pg_control_connection,
):
    command = _unknown_place_command(pg_control_connection, order_role="ENTRY")
    upsert_exchange_command_domain_hold(
        pg_control_connection,
        command=command,
        blockers=["network_ambiguous"],
        now_ms=NOW_MS + 2_000,
    )
    gateway = _TypedLookupGateway(RuntimeError("readonly lookup failed"))

    report = await reconcile_unknown_exchange_commands(
        pg_control_connection,
        gateway=gateway,
        now_ms=NOW_MS + 5_000,
        max_commands=10,
    )

    assert report["lookup_failed"] == 1
    assert _command_state(pg_control_connection) == "outcome_unknown"
    assert _hold_status(
        pg_control_connection,
        source_kind="exchange_command",
        source_id=command["exchange_command_id"],
    ) == "active"
    assert gateway.place_order_calls == 0
    assert gateway.cancel_order_calls == 0


@pytest.mark.asyncio
async def test_correct_view_absence_resolves_only_matching_command_hold(
    pg_control_connection,
):
    command = _unknown_place_command(pg_control_connection, order_role="ENTRY")
    upsert_exchange_command_domain_hold(
        pg_control_connection,
        command=command,
        blockers=["network_ambiguous"],
        now_ms=NOW_MS + 2_000,
    )
    upsert_netting_domain_hold(
        pg_control_connection,
        account_id=command["account_id"],
        runtime_profile_id=command["runtime_profile_id"],
        exchange_id=command["exchange_id"],
        exchange_instrument_id=command["exchange_instrument_id"],
        position_mode=command["position_mode"],
        position_bucket=command["position_bucket"],
        netting_domain_key=command["netting_domain_key"],
        source_ticket_id=command["ticket_id"],
        strategy_group_id=command["strategy_group_id"],
        symbol=command["symbol"],
        side=command["side"],
        source_kind="unit",
        source_id="other-risk-source",
        blockers=["other_unresolved_risk"],
        next_action="unit_test",
        authority_boundary="unit_test",
        now_ms=NOW_MS + 2_000,
    )

    report = await reconcile_unknown_exchange_commands(
        pg_control_connection,
        gateway=_TypedLookupGateway(_not_found_result(command)),
        now_ms=NOW_MS + 40_000,
        max_commands=10,
    )

    assert report["reconciled_absent"] == 1
    assert _hold_status(
        pg_control_connection,
        source_kind="exchange_command",
        source_id=command["exchange_command_id"],
    ) == "resolved"
    assert _hold_status(
        pg_control_connection,
        source_kind="unit",
        source_id="other-risk-source",
    ) == "active"
    evidence = _exchange_result(pg_control_connection)
    assert evidence == {
        "client_order_id": command["client_order_id"],
        "error_message": None,
        "exchange_order_id": None,
        "exchange_status": None,
        "gateway_symbol": command["gateway_symbol"],
        "identity_kind": "origClientOrderId",
        "lookup_status": "not_found",
        "lookup_view": "regular_order",
        "observed_at_ms": NOW_MS + 5_000,
        "visibility_window_elapsed": True,
    }


@pytest.mark.asyncio
async def test_cancel_target_absent_from_complete_views_confirms_cancel_effect(
    pg_control_connection,
):
    command = _unknown_place_command(pg_control_connection, order_role="ENTRY")
    pg_control_connection.execute(
        text(
            "UPDATE brc_ticket_bound_exchange_commands "
            "SET command_kind = 'cancel_order', target_exchange_order_id = 'algo-1' "
            "WHERE exchange_command_id = :exchange_command_id"
        ),
        {"exchange_command_id": command["exchange_command_id"]},
    )
    command = _command_row(pg_control_connection, order_role="ENTRY")
    gateway = _TypedLookupGateway(None, open_orders=[])

    report = await reconcile_unknown_exchange_commands(
        pg_control_connection,
        gateway=gateway,
        now_ms=NOW_MS + 5_000,
        max_commands=10,
    )

    assert report["reconciled_submitted"] == 1
    assert _command_state(pg_control_connection) == "reconciled_submitted"
    assert gateway.open_order_calls == [command["gateway_symbol"]]
    assert gateway.place_order_calls == 0
    assert gateway.cancel_order_calls == 0
    evidence = _exchange_result(pg_control_connection)
    assert evidence["lookup_status"] == "cancel_effect_confirmed"
    assert evidence["lookup_view"] == "complete_open_orders"


@pytest.mark.asyncio
async def test_single_and_batch_reconciliation_apply_the_same_typed_decision(
    pg_control_connection,
):
    ids = _create_ready_protected_submit(pg_control_connection)
    _prepare_real_submit(pg_control_connection, ids)
    entry = _mark_command_unknown(pg_control_connection, order_role="ENTRY")
    stop = _mark_command_unknown(pg_control_connection, order_role="SL")
    gateway = _TypedLookupGateway(_found_result_factory())

    single = await run_one_unknown_exchange_command_reconciliation(
        pg_control_connection.engine,
        gateway=gateway,
        now_ms=NOW_MS + 5_000,
    )
    batch = await reconcile_unknown_exchange_commands(
        pg_control_connection,
        gateway=gateway,
        now_ms=NOW_MS + 5_000,
        max_commands=10,
    )

    assert single["status"] == "reconciled_submitted"
    assert batch["reconciled_submitted"] == 1
    assert _command_state(pg_control_connection, order_role="ENTRY") == (
        "reconciled_submitted"
    )
    assert _command_state(pg_control_connection, order_role="SL") == (
        "reconciled_submitted"
    )
    assert {request.order_role for request, _ in gateway.requests} == {"ENTRY", "SL"}
    assert gateway.place_order_calls == 0
    assert gateway.cancel_order_calls == 0


def _unknown_place_command(conn, *, order_role: str) -> dict:
    ids = _create_ready_protected_submit(conn)
    _prepare_real_submit(conn, ids)
    return _mark_command_unknown(conn, order_role=order_role)


def _unknown_entry_command(conn) -> dict:
    """Compatibility fixture for lifecycle tests importing this module."""

    return _unknown_place_command(conn, order_role="ENTRY")


def _mark_command_unknown(conn, *, order_role: str) -> dict:
    command = _command_row(conn, order_role=order_role)
    mark_exchange_command_dispatching(
        conn,
        exchange_command_id=command["exchange_command_id"],
        now_ms=NOW_MS + 1000,
    )
    record_exchange_command_outcome(
        conn,
        exchange_command_id=command["exchange_command_id"],
        target_state=ExchangeCommandState.OUTCOME_UNKNOWN,
        outcome_class=ExchangeCommandOutcomeClass.NETWORK_AMBIGUOUS,
        exchange_result={"error_code": "C-001", "error_message": "timeout"},
        now_ms=NOW_MS + 2000,
    )
    return command


def _command_row(conn, *, order_role: str = "ENTRY") -> dict:
    return dict(
        conn.execute(
            text(
                "SELECT * FROM brc_ticket_bound_exchange_commands "
                "WHERE order_role = :order_role"
            ),
            {"order_role": order_role},
        ).mappings().one()
    )


def _command_state(conn, *, order_role: str = "ENTRY") -> str:
    return str(
        conn.execute(
            text(
                "SELECT command_state FROM brc_ticket_bound_exchange_commands "
                "WHERE order_role = :order_role"
            ),
            {"order_role": order_role},
        ).scalar_one()
    )


def _exchange_result(conn, *, order_role: str = "ENTRY") -> dict:
    value = _command_row(conn, order_role=order_role).get("exchange_result")
    if isinstance(value, str):
        return dict(json.loads(value))
    return dict(value or {})


def _hold_status(
    conn,
    *,
    source_kind: str,
    source_id: str,
) -> str:
    return str(
        conn.execute(
            text(
                "SELECT status FROM brc_ticket_bound_scope_freezes "
                "WHERE source_kind = :source_kind AND source_id = :source_id"
            ),
            {"source_kind": source_kind, "source_id": source_id},
        ).scalar_one()
    )


def _lookup_view_for_role(order_role: str) -> ExchangeOrderLookupView:
    return (
        ExchangeOrderLookupView.CONDITIONAL_ALGO_ORDER
        if order_role in {"SL", "RUNNER_SL"}
        else ExchangeOrderLookupView.REGULAR_ORDER
    )


def _found_result(
    command: dict,
    expected_view: str,
    *,
    client_order_id: str | None = None,
    gateway_symbol: str | None = None,
) -> ExchangeOrderLookupResult:
    lookup_view = ExchangeOrderLookupView(expected_view)
    return ExchangeOrderLookupResult(
        status=ExchangeOrderLookupStatus.FOUND,
        lookup_view=lookup_view,
        identity_kind=(
            "clientAlgoId"
            if lookup_view is ExchangeOrderLookupView.CONDITIONAL_ALGO_ORDER
            else "origClientOrderId"
        ),
        observed_at_ms=NOW_MS + 5_000,
        exchange_order_id="exchange-123",
        client_order_id=client_order_id or str(command["client_order_id"]),
        gateway_symbol=gateway_symbol or str(command["gateway_symbol"]),
    )


def _not_found_result(command: dict) -> ExchangeOrderLookupResult:
    lookup_view = _lookup_view_for_role(str(command["order_role"]))
    return ExchangeOrderLookupResult(
        status=ExchangeOrderLookupStatus.NOT_FOUND,
        lookup_view=lookup_view,
        identity_kind=(
            "clientAlgoId"
            if lookup_view is ExchangeOrderLookupView.CONDITIONAL_ALGO_ORDER
            else "origClientOrderId"
        ),
        observed_at_ms=NOW_MS + 5_000,
        client_order_id=str(command["client_order_id"]),
        gateway_symbol=str(command["gateway_symbol"]),
    )


def _found_result_factory():
    def _result(
        request: ExchangeOrderLookupRequest,
        observed_at_ms: int,
    ) -> ExchangeOrderLookupResult:
        lookup_view = _lookup_view_for_role(request.order_role)
        return ExchangeOrderLookupResult(
            status=ExchangeOrderLookupStatus.FOUND,
            lookup_view=lookup_view,
            identity_kind=(
                "clientAlgoId"
                if lookup_view is ExchangeOrderLookupView.CONDITIONAL_ALGO_ORDER
                else "origClientOrderId"
            ),
            observed_at_ms=observed_at_ms,
            exchange_order_id=f"exchange-{request.order_role.lower()}",
            client_order_id=request.client_order_id,
            gateway_symbol=request.gateway_symbol,
        )

    return _result


class _TypedLookupGateway:
    def __init__(self, result, *, open_orders=None) -> None:
        self.runtime_account_id = "owner-subaccount-runtime-v0"
        self.runtime_exchange_id = "binance_usdm"
        self.result = result
        self.requests: list[tuple[ExchangeOrderLookupRequest, int]] = []
        self.open_orders = list(open_orders or [])
        self.open_order_calls: list[str] = []
        self.place_order_calls = 0
        self.cancel_order_calls = 0

    async def find_order_by_client_id(
        self,
        request: ExchangeOrderLookupRequest,
        *,
        observed_at_ms: int,
    ) -> ExchangeOrderLookupResult:
        self.requests.append((request, observed_at_ms))
        if isinstance(self.result, Exception):
            raise self.result
        if callable(self.result):
            return self.result(request, observed_at_ms)
        return self.result

    async def fetch_all_open_orders(self, symbol: str):
        self.open_order_calls.append(symbol)
        return self.open_orders

    async def place_order(self, **_kwargs):
        self.place_order_calls += 1
        raise AssertionError("unknown reconciliation must never resubmit")

    async def cancel_order(self, **_kwargs):
        self.cancel_order_calls += 1
        raise AssertionError("unknown reconciliation must never cancel")


class _LookupGateway(_TypedLookupGateway):
    """Compatibility wrapper for legacy lifecycle test imports.

    The production gateway boundary is typed.  This fixture retains the prior
    test helper input shape while translating it to the typed result expected
    by the reconciliation worker.
    """

    async def find_order_by_client_id(
        self,
        request: ExchangeOrderLookupRequest,
        *,
        observed_at_ms: int,
    ) -> ExchangeOrderLookupResult:
        self.requests.append((request, observed_at_ms))
        if self.result is None or isinstance(self.result, Exception) or callable(self.result):
            return await super().find_order_by_client_id(
                request,
                observed_at_ms=observed_at_ms,
            )
        return ExchangeOrderLookupResult(
            status=ExchangeOrderLookupStatus.FOUND,
            lookup_view=_lookup_view_for_role(request.order_role),
            identity_kind=(
                "clientAlgoId"
                if request.order_role in {"SL", "RUNNER_SL"}
                else "origClientOrderId"
            ),
            observed_at_ms=observed_at_ms,
            exchange_order_id=str(
                getattr(self.result, "exchange_order_id", "") or ""
            ),
            client_order_id=str(
                getattr(self.result, "client_order_id", "") or ""
            ),
            gateway_symbol=str(getattr(self.result, "symbol", "") or ""),
        )
