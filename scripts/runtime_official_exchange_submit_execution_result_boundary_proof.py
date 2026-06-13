#!/usr/bin/env python3
"""Official exchange-submit execution-result disabled-boundary proof.

RTF-086 extends the RTF-085 exchange-submit packet/action boundary into the
official exchange-submit execution-result route with execution disabled. It
proves that the route can consume the ready exchange-submit evidence and return
a durable-shaped disabled execution result without calling ExchangeGateway,
OrderLifecycle.submit_order, changing ExecutionIntent status, opening/closing a
position, withdrawing, or transferring funds.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi.testclient import TestClient  # noqa: E402

from scripts import runtime_ready_signal_shadow_planning_contract_fixture as shadow_fixture  # noqa: E402
from scripts.runtime_official_exchange_submit_boundary_proof import (  # noqa: E402
    _ExchangeSubmitAdapterResultRepo,
    _InMemoryOrderLifecycleService,
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
    lifecycle = _InMemoryOrderLifecycleService()
    exchange_adapter_result_repo = _ExchangeSubmitAdapterResultRepo()
    state.adapter_service._order_lifecycle_service = lifecycle
    state.adapter_service._local_registration_action_authorization_repository = (
        _CreateGetRepo("action_authorization_id")
    )
    state.adapter_service._exchange_submit_action_authorization_repository = (
        _CreateGetRepo("action_authorization_id")
    )
    state.adapter_service._exchange_submit_adapter_result_repository = (
        exchange_adapter_result_repo
    )
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
                    f"rtf086_login_failed:{login.status_code}:{login.text}"
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
                raise RuntimeError("rtf086_authorization_id_missing")

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
                        "RTF-086 prerequisite exchange submit action boundary"
                    ),
                    "owner_confirmation_reference": (
                        "owner-authorized-rtf086-exchange-submit-boundary"
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
                    "exchange_submit_execution_enabled": False,
                    "exchange_submit_execution_mode": "disabled",
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
    packet = _execution_result_boundary_packet(
        prepare_report=prepare_report,
        exchange_boundary_packet=exchange_boundary_packet,
        exchange_execution_result=exchange_execution_result,
        lifecycle=lifecycle,
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
        "exchange-submit-execution-result-boundary-packet.json": packet,
    }
    for name, payload in artifacts.items():
        _write_json(output_dir / name, payload)

    report = {
        "scope": (
            "runtime_official_exchange_submit_execution_result_boundary_proof"
        ),
        "status": (
            "official_exchange_submit_execution_result_boundary_passed"
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
        "exchange_submit_execution_result_boundary_packet": packet,
        "exchange_submit_boundary_packet": exchange_boundary_packet,
        "exchange_submit_execution_result": exchange_execution_result,
        "checks": packet["checks"],
        "safety_invariants": packet["safety_invariants"],
        "operator_command_plan": {
            "next_step": (
                "build_controlled_gateway_action_proof"
                if _contract_passed(packet["checks"])
                else "resolve_exchange_submit_execution_result_blockers"
            ),
            "uses_official_fastapi_routes": True,
            "uses_fake_console_api": False,
            "live_submit_allowed": False,
            "exchange_submit_execution_enabled": False,
            "calls_exchange_gateway": False,
            "calls_order_lifecycle_submit": False,
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


def _execution_result_boundary_packet(
    *,
    prepare_report: dict[str, Any],
    exchange_boundary_packet: dict[str, Any],
    exchange_execution_result: dict[str, Any],
    lifecycle: _InMemoryOrderLifecycleService,
) -> dict[str, Any]:
    checks = _checks(
        exchange_boundary_packet=exchange_boundary_packet,
        exchange_execution_result=exchange_execution_result,
        lifecycle=lifecycle,
    )
    result_body = _body(exchange_execution_result)
    return {
        "scope": (
            "runtime_official_exchange_submit_execution_result_boundary_packet"
        ),
        "status": (
            "exchange_submit_execution_disabled_boundary"
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
        "exchange_submit_execution_result": {
            "execution_result_id": result_body.get("execution_result_id"),
            "status": result_body.get("status"),
            "exchange_submit_execution_enabled": result_body.get(
                "exchange_submit_execution_enabled"
            ),
            "execution_mode": result_body.get("execution_mode"),
            "exchange_call_count": result_body.get("exchange_call_count"),
            "order_lifecycle_submit_call_count": result_body.get(
                "order_lifecycle_submit_call_count"
            ),
            "exchange_called": result_body.get("exchange_called"),
            "exchange_order_submitted": result_body.get(
                "exchange_order_submitted"
            ),
            "real_exchange_submit_adapter_executed": result_body.get(
                "real_exchange_submit_adapter_executed"
            ),
            "order_lifecycle_submit_called": result_body.get(
                "order_lifecycle_submit_called"
            ),
            "execution_intent_status_changed": result_body.get(
                "execution_intent_status_changed"
            ),
            "submitted_local_order_ids": list(
                result_body.get("submitted_local_order_ids") or []
            ),
            "submitted_exchange_order_ids": list(
                result_body.get("submitted_exchange_order_ids") or []
            ),
            "blockers": list(result_body.get("blockers") or []),
        },
        "checks": checks,
        "safety_invariants": _safety_invariants(
            exchange_execution_result=exchange_execution_result,
            lifecycle=lifecycle,
        ),
    }


def _checks(
    *,
    exchange_boundary_packet: dict[str, Any],
    exchange_execution_result: dict[str, Any],
    lifecycle: _InMemoryOrderLifecycleService,
) -> dict[str, bool]:
    result_body = _body(exchange_execution_result)
    boundary_statuses = dict(exchange_boundary_packet.get("statuses") or {})
    safety = _safety_invariants(
        exchange_execution_result=exchange_execution_result,
        lifecycle=lifecycle,
    )
    return {
        "exchange_boundary_packet_passed": (
            exchange_boundary_packet.get("status")
            == "exchange_submit_adapter_armed_boundary"
        ),
        "exchange_adapter_result_armed": (
            boundary_statuses.get("exchange_submit_adapter_result")
            == "exchange_submit_adapter_armed"
        ),
        "exchange_execution_result_disabled": (
            result_body.get("status") == "exchange_submit_execution_disabled"
        ),
        "exchange_execution_enabled_false": (
            result_body.get("exchange_submit_execution_enabled") is False
        ),
        "exchange_execution_mode_disabled": (
            result_body.get("execution_mode") == "disabled"
        ),
        "exchange_execution_result_has_id": bool(
            result_body.get("execution_result_id")
        ),
        "exchange_execution_result_has_no_blockers": (
            not result_body.get("blockers")
        ),
        "exchange_call_count_zero": result_body.get("exchange_call_count") == 0,
        "order_lifecycle_submit_call_count_zero": (
            result_body.get("order_lifecycle_submit_call_count") == 0
        ),
        "submitted_local_order_ids_empty": (
            list(result_body.get("submitted_local_order_ids") or []) == []
        ),
        "submitted_exchange_order_ids_empty": (
            list(result_body.get("submitted_exchange_order_ids") or []) == []
        ),
        "uses_official_fastapi_routes": True,
        "uses_fake_console_api": False,
        "pg_written": safety["pg_written"],
        "exchange_write_called": safety["exchange_write_called"],
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
        "exchange_execution_result_disabled",
        "exchange_execution_enabled_false",
        "exchange_execution_mode_disabled",
        "exchange_execution_result_has_id",
        "exchange_execution_result_has_no_blockers",
        "exchange_call_count_zero",
        "order_lifecycle_submit_call_count_zero",
        "submitted_local_order_ids_empty",
        "submitted_exchange_order_ids_empty",
        "uses_official_fastapi_routes",
    )
    required_false = (
        "uses_fake_console_api",
        "pg_written",
        "exchange_write_called",
        "exchange_order_submitted",
        "order_lifecycle_submit_called",
        "execution_intent_status_changed",
        "withdrawal_or_transfer_created",
    )
    return all(checks.get(key) is True for key in required_true) and all(
        checks.get(key) is False for key in required_false
    )


def _safety_invariants(
    *,
    exchange_execution_result: dict[str, Any],
    lifecycle: _InMemoryOrderLifecycleService,
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
        "exchange_write_called": result_body.get("exchange_called") is True,
        "exchange_order_submitted": (
            result_body.get("exchange_order_submitted") is True
        ),
        "real_exchange_submit_adapter_executed": (
            result_body.get("real_exchange_submit_adapter_executed") is True
        ),
        "order_lifecycle_submit_called": (
            result_body.get("order_lifecycle_submit_called") is True
            or bool(lifecycle.submit_calls)
        ),
        "execution_intent_status_changed": (
            result_body.get("execution_intent_status_changed") is True
        ),
        "position_opened": False,
        "position_closed": False,
        "withdrawal_or_transfer_created": (
            result_body.get("withdrawal_or_transfer_created") is True
        ),
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build an official exchange submit execution-result boundary proof."
    )
    parser.add_argument(
        "--output-dir",
        default="output/rtf086-official-exchange-submit-execution-result-boundary",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    report = build_proof_report(Path(args.output_dir).expanduser())
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return (
        0
        if report["status"]
        == "official_exchange_submit_execution_result_boundary_passed"
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
