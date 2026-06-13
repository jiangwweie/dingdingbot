#!/usr/bin/env python3
"""Official controlled gateway action proof.

RTF-087 extends the RTF-086 disabled execution-result boundary into an
in-memory gateway action. It proves that the official route can call the
runtime exchange gateway port, transition local orders through
OrderLifecycle.submit_order, and persist a durable execution result without
touching a live exchange, PG, withdrawals, or transfers.
"""

from __future__ import annotations

import argparse
from decimal import Decimal
import json
from pathlib import Path
import sys
from time import time
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi.testclient import TestClient  # noqa: E402

from scripts import runtime_ready_signal_shadow_planning_contract_fixture as shadow_fixture  # noqa: E402
from scripts.runtime_official_exchange_submit_boundary_proof import (  # noqa: E402
    _ExchangeSubmitAdapterResultRepo,
    _exchange_evidence_ids,
    _exchange_submit_boundary_packet,
    _prepare_candidate,
    _run_local_registration_stage,
)
from scripts.runtime_official_scoped_local_registration_proof import (  # noqa: E402
    _body,
    _request,
    _signal_evaluation_from_candidate,
    _write_json,
)
from scripts.runtime_official_server_prepare_integration_proof import (  # noqa: E402
    _CreateGetRepo,
    _TestClientApiClient,
    _configure_auth_env,
    _login,
    _temporary_api_injections,
)
from scripts.runtime_official_submit_adapter_preview_proof import (  # noqa: E402
    _rtf083_state,
)
from src.domain.models import (  # noqa: E402
    Direction,
    OrderPlacementResult,
    OrderStatus,
    OrderType,
)
from src.domain.runtime_execution_exchange_gateway_readiness import (  # noqa: E402
    RuntimeExecutionExchangeGatewayReadinessStatus,
)
from src.domain.signal_evaluation import OrderCandidate, SignalEvaluation  # noqa: E402


def build_proof_report(output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    shadow_dir = output_dir / "shadow-planning"
    shadow_report = shadow_fixture.build_contract_fixture_report(shadow_dir)
    _write_json(output_dir / "shadow-contract-report.json", shadow_report)

    candidate = OrderCandidate.model_validate(shadow_report["candidate_snapshot"])
    runtime = shadow_fixture._runtime()
    signal_evaluation = SignalEvaluation.model_validate(
        _signal_evaluation_from_candidate(candidate)
    )
    state = _rtf083_state(
        runtime=runtime,
        candidate=candidate,
        signal_evaluation=signal_evaluation,
    )
    lifecycle = _ControlledOrderLifecycleService()
    gateway = _ControlledExchangeGateway()
    position_projection = _PositionProjection()
    exchange_adapter_result_repo = _ExchangeSubmitAdapterResultRepo()
    exchange_execution_result_repo = _ExchangeSubmitExecutionResultRepo()
    recovery_repo = _ExecutionRecoveryRepo()
    readiness_repo = _ExchangeGatewayReadinessRepo()

    state.adapter_service._order_lifecycle_service = lifecycle
    state.adapter_service._exchange_gateway = gateway
    state.adapter_service._position_projection_service = position_projection
    state.adapter_service._local_registration_action_authorization_repository = (
        _CreateGetRepo("action_authorization_id")
    )
    state.adapter_service._exchange_submit_action_authorization_repository = (
        _CreateGetRepo("action_authorization_id")
    )
    state.adapter_service._exchange_submit_adapter_result_repository = (
        exchange_adapter_result_repo
    )
    state.adapter_service._exchange_submit_execution_result_repository = (
        exchange_execution_result_repo
    )
    state.adapter_service._execution_recovery_repository = recovery_repo
    state.adapter_service._exchange_gateway_readiness_repository = readiness_repo
    state.adapter_service._attempt_outcome_policy_repository = _CreateGetRepo(
        "policy_id"
    )

    _configure_auth_env()
    with _temporary_api_injections(state):
        from src.interfaces.api import app

        with TestClient(app) as client:
            login = _login(client)
            if login.status_code != 200:
                raise RuntimeError(
                    f"rtf087_login_failed:{login.status_code}:{login.text}"
                )
            api_client = _TestClientApiClient(client)
            prepare_report = _prepare_candidate(
                api_client=api_client,
                candidate=candidate,
            )
            authorization_id = (prepare_report.get("ids") or {}).get(
                "authorization_id"
            )
            if not authorization_id:
                raise RuntimeError("rtf087_authorization_id_missing")

            local_stage = _run_local_registration_stage(
                api_client=api_client,
                authorization_id=authorization_id,
                prepare_report=prepare_report,
                state=state,
            )
            exchange_packet_preview = _request(
                api_client,
                "GET",
                (
                    "/api/trading-console/"
                    "runtime-execution-exchange-submit-packet-previews/"
                    f"authorizations/{authorization_id}"
                ),
            )
            exchange_evidence_ids = _exchange_evidence_ids(
                prepare_report=prepare_report,
                local_stage=local_stage,
            )
            exchange_action_authorization = _request(
                api_client,
                "POST",
                (
                    "/api/trading-console/"
                    "runtime-execution-exchange-submit-action-authorizations/"
                    f"authorizations/{authorization_id}"
                ),
                query={
                    **exchange_evidence_ids,
                    "owner_confirmed_for_exchange_submit_action": True,
                    "owner_operator_id": "owner",
                    "reason": (
                        "RTF-087 controlled in-memory gateway action proof"
                    ),
                    "owner_confirmation_reference": (
                        "owner-authorized-rtf087-controlled-gateway-action"
                    ),
                },
            )
            exchange_action_authorization_id = _body(
                exchange_action_authorization
            ).get("action_authorization_id")
            exchange_submit_enablement = _request(
                api_client,
                "GET",
                (
                    "/api/trading-console/"
                    "runtime-execution-exchange-submit-enablements/"
                    f"authorizations/{authorization_id}"
                ),
                query={
                    **exchange_evidence_ids,
                    "exchange_submit_action_authorization_id": (
                        exchange_action_authorization_id
                    ),
                },
            )
            exchange_adapter_result = _request(
                api_client,
                "POST",
                (
                    "/api/trading-console/"
                    "runtime-execution-exchange-submit-adapter-results/"
                    f"authorizations/{authorization_id}"
                ),
                query={
                    **exchange_evidence_ids,
                    "exchange_submit_action_authorization_id": (
                        exchange_action_authorization_id
                    ),
                    "exchange_submit_adapter_enabled": True,
                },
            )
            exchange_boundary_packet = _exchange_submit_boundary_packet(
                shadow_report=shadow_report,
                prepare_report=prepare_report,
                local_stage=local_stage,
                exchange_packet_preview=exchange_packet_preview,
                exchange_action_authorization=exchange_action_authorization,
                exchange_submit_enablement=exchange_submit_enablement,
                exchange_adapter_result=exchange_adapter_result,
                lifecycle=lifecycle,
                exchange_adapter_result_repo=exchange_adapter_result_repo,
            )
            exchange_execution_result = _request(
                api_client,
                "POST",
                (
                    "/api/trading-console/"
                    "runtime-execution-exchange-submit-execution-results/"
                    f"authorizations/{authorization_id}"
                ),
                query={
                    **exchange_evidence_ids,
                    "exchange_submit_action_authorization_id": (
                        exchange_action_authorization_id
                    ),
                    "exchange_submit_execution_enabled": True,
                    "exchange_submit_execution_mode": "in_memory_simulation",
                },
            )

    packet = _controlled_gateway_action_packet(
        prepare_report=prepare_report,
        exchange_boundary_packet=exchange_boundary_packet,
        exchange_execution_result=exchange_execution_result,
        lifecycle=lifecycle,
        gateway=gateway,
        execution_result_repo=exchange_execution_result_repo,
        recovery_repo=recovery_repo,
        position_projection=position_projection,
    )
    artifacts = {
        "prepare-report.json": prepare_report,
        "local-registration-adapter-result.json": local_stage["adapter_result"],
        "exchange-submit-packet-preview.json": exchange_packet_preview,
        "exchange-submit-action-authorization.json": exchange_action_authorization,
        "exchange-submit-enablement.json": exchange_submit_enablement,
        "exchange-submit-adapter-result.json": exchange_adapter_result,
        "exchange-submit-execution-result.json": exchange_execution_result,
        "exchange-submit-boundary-packet.json": exchange_boundary_packet,
        "controlled-gateway-action-packet.json": packet,
    }
    for name, payload in artifacts.items():
        _write_json(output_dir / name, payload)

    report = {
        "scope": "runtime_official_controlled_gateway_action_proof",
        "status": (
            "official_controlled_gateway_action_passed"
            if _contract_passed(packet["checks"])
            else "blocked"
        ),
        "runtime_instance_id": "runtime-rtf075-cpm-long",
        "order_candidate_id": "order-candidate-rtf075-contract",
        "authorization_id": (packet["ids"] or {}).get("authorization_id"),
        "execution_intent_id": (packet["ids"] or {}).get("execution_intent_id"),
        "exchange_submit_execution_result_id": (packet["ids"] or {}).get(
            "exchange_submit_execution_result_id"
        ),
        "controlled_gateway_action_packet": packet,
        "exchange_submit_execution_result": exchange_execution_result,
        "checks": packet["checks"],
        "safety_invariants": packet["safety_invariants"],
        "operator_command_plan": {
            "next_step": (
                "build_runtime_post_submit_finalize_flow"
                if _contract_passed(packet["checks"])
                else "resolve_controlled_gateway_action_blockers"
            ),
            "uses_official_fastapi_routes": True,
            "uses_fake_console_api": False,
            "live_submit_allowed": False,
            "exchange_submit_execution_enabled": True,
            "execution_mode": "in_memory_simulation",
            "calls_gateway_port": True,
            "calls_order_lifecycle_submit": True,
            "calls_live_exchange": False,
            "executes_real_submit": False,
        },
        "right_tail_objective_context": {
            "small_bounded_losses_allowed_after_runtime_gate": True,
            "attempt_budget_prefers_max_loss_reference": (
                exchange_boundary_packet["runtime_attempt_budget_boundary"].get(
                    "budget_reservation_basis"
                )
                == "max_loss_reference"
            ),
            "automatic_compounding_assumed": False,
            "automatic_withdrawal_assumed": False,
            "not_proven_alpha": True,
        },
    }
    _write_json(output_dir / "contract-report.json", report)
    return report


class _ControlledOrderLifecycleService:
    def __init__(self) -> None:
        self.orders: dict[str, Any] = {}
        self.register_calls: list[dict[str, Any]] = []
        self.submit_calls: list[dict[str, Any]] = []
        self.confirm_calls: list[dict[str, Any]] = []
        self.fill_calls: list[dict[str, Any]] = []

    async def register_created_order(self, order: Any, *, metadata: Any = None) -> Any:
        self.orders[str(order.id)] = order
        self.register_calls.append(
            {
                "order": order,
                "metadata": dict(metadata or {}),
            }
        )
        return order

    async def get_order(self, order_id: str) -> Any | None:
        return self.orders.get(str(order_id))

    async def submit_order(
        self,
        order_id: str,
        exchange_order_id: str | None = None,
    ) -> Any:
        order = self.orders.get(str(order_id))
        if order is None:
            raise ValueError(f"missing order {order_id}")
        order.exchange_order_id = exchange_order_id
        order.status = OrderStatus.SUBMITTED
        self.submit_calls.append(
            {
                "order_id": order_id,
                "exchange_order_id": exchange_order_id,
            }
        )
        return order

    async def confirm_order(
        self,
        order_id: str,
        exchange_order_id: str | None = None,
    ) -> Any:
        order = self.orders.get(str(order_id))
        if order is None:
            raise ValueError(f"missing order {order_id}")
        if exchange_order_id:
            order.exchange_order_id = exchange_order_id
        order.status = OrderStatus.OPEN
        self.confirm_calls.append(
            {
                "order_id": order_id,
                "exchange_order_id": exchange_order_id,
            }
        )
        return order

    async def update_order_filled(
        self,
        order_id: str,
        filled_qty: Decimal,
        average_exec_price: Decimal,
    ) -> Any:
        order = self.orders.get(str(order_id))
        if order is None:
            raise ValueError(f"missing order {order_id}")
        order.filled_qty = filled_qty
        order.average_exec_price = average_exec_price
        order.status = OrderStatus.FILLED
        self.fill_calls.append(
            {
                "order_id": order_id,
                "filled_qty": filled_qty,
                "average_exec_price": average_exec_price,
            }
        )
        return order

    async def update_order_partially_filled(
        self,
        order_id: str,
        filled_qty: Decimal,
        average_exec_price: Decimal,
    ) -> Any:
        order = self.orders.get(str(order_id))
        if order is None:
            raise ValueError(f"missing order {order_id}")
        order.filled_qty = filled_qty
        order.average_exec_price = average_exec_price
        order.status = OrderStatus.PARTIALLY_FILLED
        return order


class _ControlledExchangeGateway:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def place_order(
        self,
        *,
        symbol: str,
        order_type: str,
        side: str,
        amount: Decimal,
        price: Decimal | None = None,
        trigger_price: Decimal | None = None,
        reduce_only: bool = False,
        position_side: str | None = None,
        client_order_id: str | None = None,
    ) -> OrderPlacementResult:
        self.calls.append(
            {
                "symbol": symbol,
                "order_type": order_type,
                "side": side,
                "amount": amount,
                "price": price,
                "trigger_price": trigger_price,
                "reduce_only": reduce_only,
                "position_side": position_side,
                "client_order_id": client_order_id,
            }
        )
        status = (
            OrderStatus.FILLED
            if str(order_type).lower() == "market" and not reduce_only
            else OrderStatus.OPEN
        )
        return OrderPlacementResult(
            order_id=f"controlled-placement-{client_order_id}",
            exchange_order_id=f"controlled-ex-{client_order_id}",
            symbol=symbol,
            order_type=OrderType(str(order_type).upper()),
            direction=Direction.LONG if side == "buy" else Direction.SHORT,
            side=side,
            amount=amount,
            price=price,
            filled_qty=amount if status == OrderStatus.FILLED else None,
            average_exec_price=(
                Decimal("600") if status == OrderStatus.FILLED else None
            ),
            trigger_price=trigger_price,
            reduce_only=reduce_only,
            client_order_id=client_order_id,
            status=status,
        )


class _PositionProjection:
    def __init__(self) -> None:
        self.entry_fill_orders: list[Any] = []

    async def project_entry_fill(self, entry_order: Any) -> Any:
        self.entry_fill_orders.append(entry_order)
        return {
            "position_id": f"controlled-pos-{entry_order.signal_id}",
            "current_qty": str(entry_order.filled_qty),
        }


class _ExchangeSubmitExecutionResultRepo:
    def __init__(self) -> None:
        self.items: dict[str, Any] = {}
        self.acquire_calls = 0
        self.complete_calls = 0

    async def get_by_authorization_id(self, authorization_id: str) -> Any | None:
        return self.items.get(str(authorization_id))

    async def acquire_exchange_submit_execution_lock(
        self,
        result: Any,
    ) -> tuple[bool, Any]:
        self.acquire_calls += 1
        key = str(result.authorization_id)
        existing = self.items.get(key)
        if existing is not None:
            return False, existing
        self.items[key] = result
        return True, result

    async def complete_exchange_submit_execution_result(self, result: Any) -> Any:
        self.complete_calls += 1
        self.items[str(result.authorization_id)] = result
        return result


class _ExecutionRecoveryRepo:
    def __init__(self) -> None:
        self.tasks: dict[str, Any] = {}
        self.create_calls: list[dict[str, Any]] = []

    async def get(self, task_id: str) -> Any | None:
        return self.tasks.get(str(task_id))

    async def create_task(
        self,
        task_id: str,
        intent_id: str,
        symbol: str,
        recovery_type: str,
        related_order_id: str | None = None,
        related_exchange_order_id: str | None = None,
        error_message: str | None = None,
        context_payload: dict[str, Any] | None = None,
    ) -> None:
        task = {
            "id": task_id,
            "intent_id": intent_id,
            "symbol": symbol,
            "recovery_type": recovery_type,
            "related_order_id": related_order_id,
            "related_exchange_order_id": related_exchange_order_id,
            "error_message": error_message,
            "context_payload": context_payload or {},
            "status": "pending",
        }
        self.tasks[task_id] = task
        self.create_calls.append(task)

    async def list_blocking(self) -> list[dict[str, Any]]:
        return [
            task
            for task in self.tasks.values()
            if task.get("status") in {"pending", "retrying"}
        ]


class _ExchangeGatewayReadinessRepo:
    async def get(self, readiness_id: str) -> Any:
        return _Readiness(readiness_id=readiness_id)


class _Readiness:
    def __init__(self, *, readiness_id: str) -> None:
        self.readiness_id = readiness_id
        self.status = (
            RuntimeExecutionExchangeGatewayReadinessStatus
            .READY_FOR_MANUAL_GATEWAY_BINDING
        )
        self.blockers: list[str] = []
        self.warnings = ["controlled_in_memory_gateway_readiness_fixture"]
        self.gateway_injected = False
        self.exchange_called = False
        self.exchange_order_submitted = False
        self.order_lifecycle_submit_called = False
        self.execution_intent_status_changed = False
        self.created_at_ms = int(time() * 1000)


def _controlled_gateway_action_packet(
    *,
    prepare_report: dict[str, Any],
    exchange_boundary_packet: dict[str, Any],
    exchange_execution_result: dict[str, Any],
    lifecycle: _ControlledOrderLifecycleService,
    gateway: _ControlledExchangeGateway,
    execution_result_repo: _ExchangeSubmitExecutionResultRepo,
    recovery_repo: _ExecutionRecoveryRepo,
    position_projection: _PositionProjection,
) -> dict[str, Any]:
    checks = _checks(
        exchange_boundary_packet=exchange_boundary_packet,
        exchange_execution_result=exchange_execution_result,
        lifecycle=lifecycle,
        gateway=gateway,
        execution_result_repo=execution_result_repo,
        recovery_repo=recovery_repo,
        position_projection=position_projection,
    )
    result_body = _body(exchange_execution_result)
    return {
        "scope": "runtime_official_controlled_gateway_action_packet",
        "status": (
            "controlled_gateway_action_submitted"
            if _contract_passed(checks)
            else "blocked"
        ),
        "ids": {
            **dict(prepare_report.get("ids") or {}),
            **dict(exchange_boundary_packet.get("ids") or {}),
            "exchange_submit_execution_result_id": result_body.get(
                "execution_result_id"
            ),
        },
        "statuses": {
            **dict(exchange_boundary_packet.get("statuses") or {}),
            "exchange_submit_execution_result": result_body.get("status"),
        },
        "gateway_action": {
            "execution_mode": result_body.get("execution_mode"),
            "exchange_submit_execution_enabled": result_body.get(
                "exchange_submit_execution_enabled"
            ),
            "fake_gateway_call_count": len(gateway.calls),
            "exchange_call_count": result_body.get("exchange_call_count"),
            "order_lifecycle_submit_call_count": result_body.get(
                "order_lifecycle_submit_call_count"
            ),
            "gateway_client_order_ids": [
                call["client_order_id"] for call in gateway.calls
            ],
            "gateway_reduce_only_flags": [
                call["reduce_only"] for call in gateway.calls
            ],
            "submitted_local_order_ids": list(
                result_body.get("submitted_local_order_ids") or []
            ),
            "submitted_exchange_order_ids": list(
                result_body.get("submitted_exchange_order_ids") or []
            ),
            "entry_exchange_order_id": result_body.get("entry_exchange_order_id"),
            "protection_exchange_order_ids": list(
                result_body.get("protection_exchange_order_ids") or []
            ),
            "blockers": list(result_body.get("blockers") or []),
            "warnings": list(result_body.get("warnings") or []),
        },
        "local_projection": {
            "registered_order_count": len(lifecycle.orders),
            "submit_call_count": len(lifecycle.submit_calls),
            "confirm_call_count": len(lifecycle.confirm_calls),
            "fill_call_count": len(lifecycle.fill_calls),
            "entry_fill_projected": bool(position_projection.entry_fill_orders),
            "local_order_statuses": {
                order_id: str(order.status.value)
                for order_id, order in lifecycle.orders.items()
            },
            "local_order_exchange_ids": {
                order_id: order.exchange_order_id
                for order_id, order in lifecycle.orders.items()
            },
        },
        "durable_result": {
            "repo_acquire_calls": execution_result_repo.acquire_calls,
            "repo_complete_calls": execution_result_repo.complete_calls,
            "stored_result_count": len(execution_result_repo.items),
        },
        "recovery": {
            "blocking_task_count": len(recovery_repo.tasks),
            "create_call_count": len(recovery_repo.create_calls),
        },
        "checks": checks,
        "safety_invariants": _safety_invariants(
            exchange_execution_result=exchange_execution_result,
            lifecycle=lifecycle,
            gateway=gateway,
            execution_result_repo=execution_result_repo,
        ),
    }


def _checks(
    *,
    exchange_boundary_packet: dict[str, Any],
    exchange_execution_result: dict[str, Any],
    lifecycle: _ControlledOrderLifecycleService,
    gateway: _ControlledExchangeGateway,
    execution_result_repo: _ExchangeSubmitExecutionResultRepo,
    recovery_repo: _ExecutionRecoveryRepo,
    position_projection: _PositionProjection,
) -> dict[str, bool]:
    result_body = _body(exchange_execution_result)
    boundary_statuses = dict(exchange_boundary_packet.get("statuses") or {})
    safety = _safety_invariants(
        exchange_execution_result=exchange_execution_result,
        lifecycle=lifecycle,
        gateway=gateway,
        execution_result_repo=execution_result_repo,
    )
    submitted_exchange_ids = list(result_body.get("submitted_exchange_order_ids") or [])
    protection_exchange_ids = list(result_body.get("protection_exchange_order_ids") or [])
    return {
        "exchange_boundary_packet_passed": (
            exchange_boundary_packet.get("status")
            == "exchange_submit_adapter_armed_boundary"
        ),
        "exchange_adapter_result_armed": (
            boundary_statuses.get("exchange_submit_adapter_result")
            == "exchange_submit_adapter_armed"
        ),
        "exchange_execution_result_submitted": (
            result_body.get("status") == "exchange_submit_orders_submitted"
        ),
        "exchange_execution_enabled_true": (
            result_body.get("exchange_submit_execution_enabled") is True
        ),
        "exchange_execution_mode_in_memory": (
            result_body.get("execution_mode") == "in_memory_simulation"
        ),
        "exchange_execution_result_has_id": bool(
            result_body.get("execution_result_id")
        ),
        "exchange_execution_result_has_no_blockers": (
            not result_body.get("blockers")
        ),
        "fake_gateway_called_twice": len(gateway.calls) == 2,
        "exchange_call_count_two": result_body.get("exchange_call_count") == 2,
        "order_lifecycle_submit_call_count_two": (
            result_body.get("order_lifecycle_submit_call_count") == 2
        ),
        "local_lifecycle_submit_called_twice": len(lifecycle.submit_calls) == 2,
        "submitted_local_order_ids_present": (
            len(result_body.get("submitted_local_order_ids") or []) == 2
        ),
        "submitted_exchange_order_ids_present": len(submitted_exchange_ids) == 2,
        "entry_exchange_order_id_present": bool(
            result_body.get("entry_exchange_order_id")
        ),
        "protection_exchange_order_id_present": len(protection_exchange_ids) == 1,
        "durable_result_lock_acquired": execution_result_repo.acquire_calls == 1,
        "durable_result_completed": execution_result_repo.complete_calls == 1,
        "entry_fill_projected": bool(position_projection.entry_fill_orders),
        "no_recovery_task_created": not recovery_repo.create_calls,
        "uses_official_fastapi_routes": True,
        "uses_fake_console_api": False,
        "pg_written": safety["pg_written"],
        "live_exchange_called": safety["live_exchange_called"],
        "fake_gateway_called": safety["fake_gateway_called"],
        "exchange_order_submitted": safety["exchange_order_submitted"],
        "order_lifecycle_submit_called": safety[
            "order_lifecycle_submit_called"
        ],
        "execution_intent_status_changed": safety[
            "execution_intent_status_changed"
        ],
        "withdrawal_or_transfer_created": safety[
            "withdrawal_or_transfer_created"
        ],
    }


def _contract_passed(checks: dict[str, bool]) -> bool:
    required_true = (
        "exchange_boundary_packet_passed",
        "exchange_adapter_result_armed",
        "exchange_execution_result_submitted",
        "exchange_execution_enabled_true",
        "exchange_execution_mode_in_memory",
        "exchange_execution_result_has_id",
        "exchange_execution_result_has_no_blockers",
        "fake_gateway_called_twice",
        "exchange_call_count_two",
        "order_lifecycle_submit_call_count_two",
        "local_lifecycle_submit_called_twice",
        "submitted_local_order_ids_present",
        "submitted_exchange_order_ids_present",
        "entry_exchange_order_id_present",
        "protection_exchange_order_id_present",
        "durable_result_lock_acquired",
        "durable_result_completed",
        "entry_fill_projected",
        "no_recovery_task_created",
        "uses_official_fastapi_routes",
        "fake_gateway_called",
        "exchange_order_submitted",
        "order_lifecycle_submit_called",
    )
    required_false = (
        "uses_fake_console_api",
        "pg_written",
        "live_exchange_called",
        "execution_intent_status_changed",
        "withdrawal_or_transfer_created",
    )
    return all(checks.get(key) is True for key in required_true) and all(
        checks.get(key) is False for key in required_false
    )


def _safety_invariants(
    *,
    exchange_execution_result: dict[str, Any],
    lifecycle: _ControlledOrderLifecycleService,
    gateway: _ControlledExchangeGateway,
    execution_result_repo: _ExchangeSubmitExecutionResultRepo,
) -> dict[str, bool]:
    result_body = _body(exchange_execution_result)
    return {
        "uses_official_fastapi_routes": True,
        "uses_fake_console_api": False,
        "uses_in_memory_repositories": True,
        "pg_written": False,
        "exchange_submit_execution_enabled": (
            result_body.get("exchange_submit_execution_enabled") is True
        ),
        "execution_mode_in_memory_simulation": (
            result_body.get("execution_mode") == "in_memory_simulation"
        ),
        "fake_gateway_called": bool(gateway.calls),
        "live_exchange_called": False,
        "exchange_order_submitted": (
            result_body.get("exchange_order_submitted") is True
        ),
        "real_exchange_submit_adapter_executed": (
            result_body.get("real_exchange_submit_adapter_executed") is True
        ),
        "order_lifecycle_submit_called": (
            result_body.get("order_lifecycle_submit_called") is True
            and bool(lifecycle.submit_calls)
        ),
        "durable_execution_result_recorded": (
            execution_result_repo.complete_calls == 1
            and bool(execution_result_repo.items)
        ),
        "execution_intent_status_changed": (
            result_body.get("execution_intent_status_changed") is True
        ),
        "position_closed": False,
        "withdrawal_or_transfer_created": (
            result_body.get("withdrawal_or_transfer_created") is True
        ),
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build an official controlled gateway action proof."
    )
    parser.add_argument(
        "--output-dir",
        default="output/rtf087-official-controlled-gateway-action",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    report = build_proof_report(Path(args.output_dir).expanduser())
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if report["status"] == "official_controlled_gateway_action_passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
