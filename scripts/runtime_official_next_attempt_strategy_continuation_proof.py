#!/usr/bin/env python3
"""Official next-attempt strategy continuation proof.

RTF-089 proves the post-submit loop can reconnect to strategy-driven planning:

blocked post-submit gate -> no strategy planner call / no shadow candidate
ready post-submit gate + fresh CPM signal -> shadow candidate planning packet

It uses the official Trading Console next-attempt strategy planning route and
does not create executable intents, local orders, OrderLifecycle handoffs,
exchange requests, transfers, or withdrawals.
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

from scripts import runtime_official_post_submit_finalize_proof as rtf088  # noqa: E402
from scripts import runtime_ready_signal_shadow_planning_contract_fixture as ready_fixture  # noqa: E402
from scripts.runtime_official_scoped_local_registration_proof import (  # noqa: E402
    _body,
    _write_json,
)
from scripts.runtime_official_server_prepare_integration_proof import (  # noqa: E402
    _TestClientApiClient,
    _configure_auth_env,
    _login,
)
from src.domain.runtime_post_submit_finalize import (  # noqa: E402
    RuntimePostSubmitFinalizePacket,
)


def build_proof_report(output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rtf088_report = rtf088.build_proof_report(output_dir / "rtf088-prerequisite")
    _write_json(output_dir / "rtf088-prerequisite-report.json", rtf088_report)

    runtime = ready_fixture._runtime()
    signal_input = ready_fixture._signal_input()
    ready_post_submit = ready_fixture._post_submit_finalize_packet(runtime)
    blocked_post_submit_body = _body(rtf088_report["post_submit_finalize_packet"])
    if not blocked_post_submit_body:
        raise RuntimeError("rtf089_blocked_post_submit_packet_missing")

    blocked_store = ready_fixture._ShadowStore()
    ready_store = ready_fixture._ShadowStore()
    blocked_planning_service = ready_fixture._planning_service(
        runtime=runtime,
        store=blocked_store,
    )
    ready_planning_service = ready_fixture._planning_service(
        runtime=runtime,
        store=ready_store,
    )

    _configure_auth_env()
    with _temporary_next_attempt_injections(
        runtime_service=ready_fixture._RuntimeService(runtime),
        planning_service=blocked_planning_service,
    ):
        from src.interfaces.api import app

        with TestClient(app) as client:
            login = _login(client)
            if login.status_code != 200:
                raise RuntimeError(
                    f"rtf089_blocked_login_failed:{login.status_code}:{login.text}"
                )
            api_client = _TestClientApiClient(client)
            blocked_strategy_plan = _post_next_attempt_strategy_plan(
                api_client=api_client,
                runtime_instance_id=runtime.runtime_instance_id,
                post_submit_finalize_packet=blocked_post_submit_body,
                signal_input=signal_input.model_dump(mode="json"),
                context_id="rtf089-blocked-active-position",
            )

    with _temporary_next_attempt_injections(
        runtime_service=ready_fixture._RuntimeService(runtime),
        planning_service=ready_planning_service,
    ):
        from src.interfaces.api import app

        with TestClient(app) as client:
            login = _login(client)
            if login.status_code != 200:
                raise RuntimeError(
                    f"rtf089_ready_login_failed:{login.status_code}:{login.text}"
                )
            api_client = _TestClientApiClient(client)
            ready_strategy_plan = _post_next_attempt_strategy_plan(
                api_client=api_client,
                runtime_instance_id=runtime.runtime_instance_id,
                post_submit_finalize_packet=ready_post_submit.model_dump(mode="json"),
                signal_input=signal_input.model_dump(mode="json"),
                context_id="rtf089-ready-fresh-cpm-signal",
            )

    packet = _proof_packet(
        rtf088_report=rtf088_report,
        blocked_strategy_plan=blocked_strategy_plan,
        ready_strategy_plan=ready_strategy_plan,
        ready_post_submit=ready_post_submit,
        blocked_store=blocked_store,
        ready_store=ready_store,
    )
    artifacts = {
        "blocked-post-submit-finalize.json": blocked_post_submit_body,
        "ready-post-submit-finalize.json": ready_post_submit.model_dump(mode="json"),
        "signal-input.json": signal_input.model_dump(mode="json"),
        "blocked-next-attempt-strategy-plan.json": blocked_strategy_plan,
        "ready-next-attempt-strategy-plan.json": ready_strategy_plan,
        "next-attempt-strategy-continuation-packet.json": packet,
    }
    for name, payload in artifacts.items():
        _write_json(output_dir / name, payload)

    report = {
        "scope": "runtime_official_next_attempt_strategy_continuation_proof",
        "status": (
            "official_next_attempt_strategy_continuation_passed"
            if _contract_passed(packet["checks"])
            else "blocked"
        ),
        "runtime_instance_id": runtime.runtime_instance_id,
        "order_candidate_id": packet["ready_path"].get("order_candidate_id"),
        "signal_evaluation_id": packet["ready_path"].get("signal_evaluation_id"),
        "blocked_status": packet["blocked_path"].get("status"),
        "ready_status": packet["ready_path"].get("status"),
        "next_attempt_strategy_continuation_packet": packet,
        "checks": packet["checks"],
        "safety_invariants": packet["safety_invariants"],
        "operator_command_plan": {
            "next_step": (
                "run_runtime_final_gate_preflight_for_fresh_shadow_candidate"
                if _contract_passed(packet["checks"])
                else "resolve_next_attempt_strategy_continuation_blockers"
            ),
            "uses_official_fastapi_routes": True,
            "uses_fake_console_api": False,
            "blocked_gate_prevents_shadow_candidate": True,
            "ready_gate_creates_shadow_candidate": True,
            "requires_fresh_authorization_before_submit": True,
            "creates_executable_execution_intent": False,
            "places_order": False,
        },
        "right_tail_objective_context": {
            "small_bounded_losses_allowed_after_runtime_gate": True,
            "fresh_attempt_requires_strategy_signal": True,
            "automatic_compounding_assumed": False,
            "automatic_withdrawal_assumed": False,
            "not_proven_alpha": True,
        },
    }
    _write_json(output_dir / "contract-report.json", report)
    return report


class _temporary_next_attempt_injections:
    def __init__(self, *, runtime_service: Any, planning_service: Any) -> None:
        self.attr_values = {
            "_strategy_runtime_service": runtime_service,
            "_runtime_next_attempt_strategy_planning_service": planning_service,
        }
        self.saved_attrs: dict[str, tuple[bool, Any]] = {}

    def __enter__(self) -> "_temporary_next_attempt_injections":
        import src.interfaces.api as api_module

        self.saved_attrs = {
            key: (hasattr(api_module, key), getattr(api_module, key, None))
            for key in self.attr_values
        }
        for key, value in self.attr_values.items():
            setattr(api_module, key, value)
        return self

    def __exit__(self, *_exc: Any) -> None:
        import src.interfaces.api as api_module

        for key, (exists, value) in self.saved_attrs.items():
            if exists:
                setattr(api_module, key, value)
            elif hasattr(api_module, key):
                delattr(api_module, key)


def _post_next_attempt_strategy_plan(
    *,
    api_client: _TestClientApiClient,
    runtime_instance_id: str,
    post_submit_finalize_packet: dict[str, Any],
    signal_input: dict[str, Any],
    context_id: str,
) -> dict[str, Any]:
    return api_client.request_json(
        "POST",
        (
            "/api/trading-console/strategy-runtimes/"
            f"{runtime_instance_id}/next-attempt-strategy-plans"
        ),
        body={
            "post_submit_finalize_packet": post_submit_finalize_packet,
            "signal_input": signal_input,
            "context_id": context_id,
            "metadata": {
                "runtime_official_next_attempt_strategy_continuation_proof": True,
                "context_id": context_id,
            },
            "non_executing": True,
        },
    )


def _proof_packet(
    *,
    rtf088_report: dict[str, Any],
    blocked_strategy_plan: dict[str, Any],
    ready_strategy_plan: dict[str, Any],
    ready_post_submit: RuntimePostSubmitFinalizePacket,
    blocked_store: Any,
    ready_store: Any,
) -> dict[str, Any]:
    blocked_body = _body(blocked_strategy_plan)
    ready_body = _body(ready_strategy_plan)
    candidate = ready_store.candidate
    proposal = (
        candidate.metadata.get("planning_proposal")
        if candidate is not None
        else None
    )
    checks = _checks(
        rtf088_report=rtf088_report,
        blocked_strategy_plan=blocked_strategy_plan,
        ready_strategy_plan=ready_strategy_plan,
        blocked_store=blocked_store,
        ready_store=ready_store,
        proposal=proposal,
    )
    return {
        "scope": "runtime_official_next_attempt_strategy_continuation_packet",
        "status": (
            "next_attempt_strategy_continuation_ready_for_final_gate"
            if _contract_passed(checks)
            else "blocked"
        ),
        "blocked_path": {
            "http_status": blocked_strategy_plan.get("http_status"),
            "status": blocked_body.get("status"),
            "blockers": list(blocked_body.get("blockers") or []),
            "order_candidate_id": blocked_body.get("order_candidate_id"),
            "operator_command_plan": blocked_body.get("operator_command_plan") or {},
        },
        "ready_path": {
            "http_status": ready_strategy_plan.get("http_status"),
            "status": ready_body.get("status"),
            "next_attempt_gate_status": ready_body.get("next_attempt_gate_status"),
            "signal_evaluation_id": ready_body.get("signal_evaluation_id"),
            "order_candidate_id": ready_body.get("order_candidate_id"),
            "candidate_planning_status": ready_body.get(
                "candidate_planning_status"
            ),
            "operator_command_plan": ready_body.get("operator_command_plan") or {},
            "proposal": proposal,
        },
        "ready_post_submit_gate": {
            "packet_id": ready_post_submit.packet_id,
            "status": ready_post_submit.status.value,
            "next_attempt_gate_status": ready_post_submit.next_attempt_gate.status.value,
            "active_positions_count": (
                ready_post_submit.next_attempt_gate.active_positions_count
            ),
            "old_authorization_submit_retry_allowed": (
                ready_post_submit.old_authorization_submit_retry_allowed
            ),
            "pre_submit_rehearsal_retry_allowed": (
                ready_post_submit.pre_submit_rehearsal_retry_allowed
            ),
        },
        "checks": checks,
        "safety_invariants": _safety_invariants(
            blocked_strategy_plan=blocked_strategy_plan,
            ready_strategy_plan=ready_strategy_plan,
        ),
    }


def _checks(
    *,
    rtf088_report: dict[str, Any],
    blocked_strategy_plan: dict[str, Any],
    ready_strategy_plan: dict[str, Any],
    blocked_store: Any,
    ready_store: Any,
    proposal: Any,
) -> dict[str, bool]:
    blocked_body = _body(blocked_strategy_plan)
    ready_body = _body(ready_strategy_plan)
    ready_operator = ready_body.get("operator_command_plan") or {}
    tp_refs = (
        proposal.get("take_profit_references", [])
        if isinstance(proposal, dict)
        else []
    )
    return {
        "rtf088_prerequisite_passed": (
            rtf088_report.get("status") == "official_post_submit_finalize_passed"
        ),
        "blocked_path_http_ok": blocked_strategy_plan.get("http_status") == 200,
        "blocked_path_blocked_by_post_submit_gate": (
            blocked_body.get("status") == "blocked_by_post_submit_gate"
        ),
        "blocked_path_has_active_position_blocker": (
            "runtime_active_position_slot_in_use"
            in list(blocked_body.get("blockers") or [])
        ),
        "blocked_path_created_no_candidate": (
            blocked_body.get("order_candidate_id") is None
            and blocked_store.candidate is None
        ),
        "ready_path_http_ok": ready_strategy_plan.get("http_status") == 200,
        "ready_path_ready_for_final_gate": (
            ready_body.get("status") == "ready_for_final_gate_preflight"
        ),
        "ready_path_gate_ready": (
            ready_body.get("next_attempt_gate_status") == "ready_for_fresh_signal"
        ),
        "ready_path_shadow_candidate_created": (
            ready_body.get("order_candidate_id") == "order-candidate-rtf075-contract"
            and ready_store.candidate is not None
        ),
        "ready_path_shadow_signal_created": ready_store.evaluation is not None,
        "ready_path_requires_final_gate": (
            ready_operator.get("requires_official_final_gate") is True
        ),
        "fresh_authorization_required_before_submit": (
            ready_body.get("requires_fresh_authorization_before_submit") is True
        ),
        "old_authorization_retry_disallowed": (
            ready_body.get("old_authorization_submit_retry_allowed") is False
        ),
        "pre_submit_rehearsal_retry_disallowed": (
            ready_body.get("pre_submit_rehearsal_retry_allowed") is False
        ),
        "tp1_present": any(
            str(item.get("kind") or "").startswith("tp1")
            for item in tp_refs
            if isinstance(item, dict)
        ),
        "runner_present": any(
            item.get("kind") == "runner" for item in tp_refs if isinstance(item, dict)
        ),
        "right_tail_runner_preserved": any(
            item.get("right_tail_capture") is True
            for item in tp_refs
            if isinstance(item, dict)
        ),
        "uses_official_fastapi_routes": True,
        "uses_fake_console_api": False,
        "execution_intent_created": ready_body.get("execution_intent_created") is True,
        "executable_execution_intent_created": (
            ready_body.get("executable_execution_intent_created") is True
        ),
        "order_created": ready_body.get("order_created") is True,
        "order_lifecycle_called": ready_body.get("order_lifecycle_called") is True,
        "exchange_called": ready_body.get("exchange_called") is True,
        "withdrawal_or_transfer_created": (
            ready_body.get("withdrawal_or_transfer_created") is True
        ),
    }


def _contract_passed(checks: dict[str, bool]) -> bool:
    required_true = (
        "rtf088_prerequisite_passed",
        "blocked_path_http_ok",
        "blocked_path_blocked_by_post_submit_gate",
        "blocked_path_has_active_position_blocker",
        "blocked_path_created_no_candidate",
        "ready_path_http_ok",
        "ready_path_ready_for_final_gate",
        "ready_path_gate_ready",
        "ready_path_shadow_candidate_created",
        "ready_path_shadow_signal_created",
        "ready_path_requires_final_gate",
        "fresh_authorization_required_before_submit",
        "old_authorization_retry_disallowed",
        "pre_submit_rehearsal_retry_disallowed",
        "tp1_present",
        "runner_present",
        "right_tail_runner_preserved",
        "uses_official_fastapi_routes",
    )
    required_false = (
        "uses_fake_console_api",
        "execution_intent_created",
        "executable_execution_intent_created",
        "order_created",
        "order_lifecycle_called",
        "exchange_called",
        "withdrawal_or_transfer_created",
    )
    return all(checks.get(key) is True for key in required_true) and all(
        checks.get(key) is False for key in required_false
    )


def _safety_invariants(
    *,
    blocked_strategy_plan: dict[str, Any],
    ready_strategy_plan: dict[str, Any],
) -> dict[str, bool]:
    blocked_body = _body(blocked_strategy_plan)
    ready_body = _body(ready_strategy_plan)
    return {
        "uses_official_fastapi_routes": True,
        "uses_fake_console_api": False,
        "blocked_path_shadow_candidate_created": bool(
            blocked_body.get("order_candidate_id")
        ),
        "ready_path_shadow_candidate_created": bool(
            ready_body.get("order_candidate_id")
        ),
        "execution_intent_created": (
            ready_body.get("execution_intent_created") is True
        ),
        "executable_execution_intent_created": (
            ready_body.get("executable_execution_intent_created") is True
        ),
        "order_created": ready_body.get("order_created") is True,
        "order_lifecycle_called": ready_body.get("order_lifecycle_called") is True,
        "exchange_called": ready_body.get("exchange_called") is True,
        "exchange_order_submitted": (
            ready_body.get("exchange_order_submitted") is True
        ),
        "runtime_state_mutated": ready_body.get("runtime_state_mutated") is True,
        "withdrawal_or_transfer_created": (
            ready_body.get("withdrawal_or_transfer_created") is True
        ),
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build an official next-attempt strategy continuation proof."
    )
    parser.add_argument(
        "--output-dir",
        default="output/rtf089-official-next-attempt-strategy-continuation",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    report = build_proof_report(Path(args.output_dir).expanduser())
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return (
        0
        if report["status"]
        == "official_next_attempt_strategy_continuation_passed"
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
