#!/usr/bin/env python3
"""Verify official submit action-time bridge locally.

RTF-051 starts from the RTF-050 handoff packet and drives the existing
disabled-smoke official first-real-submit flow with a fake API client. The
goal is to prove the action-time method/path/query contract while preventing a
real gateway action, exchange write, OrderLifecycle call, withdrawal, or
transfer.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys
import time
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts import runtime_official_submit_disabled_smoke_from_handoff as smoke_flow  # noqa: E402
from scripts.verify_runtime_next_attempt_submit_preparation_bridge import (  # noqa: E402
    build_next_attempt_submit_preparation_bridge_report,
)


class _FakeOfficialSubmitClient:
    def __init__(
        self,
        *,
        http_status: int = 200,
        body: dict[str, Any] | None = None,
    ) -> None:
        self.http_status = http_status
        self.body = body or {
            "execution_result_id": "disabled-action-time-result-rtf051",
            "status": "exchange_submit_execution_disabled",
            "exchange_submit_execution_enabled": False,
            "exchange_submit_execution_mode": "disabled",
            "exchange_called": False,
            "order_lifecycle_called": False,
            "withdrawal_or_transfer_created": False,
        }
        self.calls: list[dict[str, Any]] = []

    def request_json(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "method": method,
                "path": path,
                "query": dict(query or {}),
                "body": body,
            }
        )
        return {"http_status": self.http_status, "body": self.body}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _args(*, handoff_json: Path, output: Path | None = None) -> argparse.Namespace:
    return argparse.Namespace(
        handoff_json=str(handoff_json),
        output=str(output) if output else None,
        env_file=None,
        api_base="http://local-rtf051-fake",
    )


def _ready_scenario(report: dict[str, Any]) -> dict[str, Any]:
    for scenario in report.get("scenarios") or []:
        if scenario.get("scenario_id") == "ready-cpm-long-submit-preparation":
            return scenario
    raise RuntimeError("RTF-050 ready submit-preparation scenario not found")


def _required_query_ids_present(query: dict[str, Any]) -> bool:
    required = [
        "trusted_submit_fact_snapshot_id",
        "submit_idempotency_policy_id",
        "attempt_outcome_policy_id",
        "protection_creation_failure_policy_id",
        "local_registration_enablement_decision_id",
        "owner_real_submit_authorization_id",
        "order_lifecycle_submit_enablement_id",
        "exchange_submit_adapter_enablement_id",
        "exchange_submit_action_authorization_id",
        "deployment_readiness_evidence_id",
    ]
    return all(str(query.get(key) or "").strip() for key in required)


def _disabled_smoke_action_time_scenario(
    *,
    handoff_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    client = _FakeOfficialSubmitClient()
    report = smoke_flow._build_report(
        _args(handoff_json=handoff_path, output=output_path),
        client=client,
    )
    call = client.calls[0] if client.calls else {}
    query = dict(call.get("query") or {})
    checks = {
        "disabled_smoke_passed": report["status"] == "disabled_smoke_passed",
        "official_endpoint_called_once": len(client.calls) == 1,
        "method_is_post": call.get("method") == "POST",
        "path_is_official_first_real_submit_action": (
            "runtime-execution-first-real-submit-actions/authorizations/"
            in str(call.get("path") or "")
        ),
        "owner_confirmation_false": (
            query.get("owner_confirmed_for_first_real_submit_action") is False
        ),
        "required_query_ids_present": _required_query_ids_present(query),
        "no_request_body": call.get("body") is None,
        "response_exchange_submit_disabled": (
            report["api_payload"].get("exchange_submit_execution_enabled") is False
            and report["api_payload"].get("exchange_submit_execution_mode")
            == "disabled"
        ),
        "no_real_exchange_effect": (
            report["safety_invariants"]["requests_real_gateway_action"] is False
            and report["safety_invariants"]["exchange_submit_execution_enabled"]
            is False
            and report["safety_invariants"]["exchange_write_called"] is False
            and report["safety_invariants"]["order_lifecycle_called"] is False
            and report["safety_invariants"]["withdrawal_or_transfer_created"]
            is False
        ),
    }
    return {
        "scenario_id": "disabled-smoke-action-time-from-rtf050-handoff",
        "status": "passed" if all(checks.values()) else "failed",
        "report_status": report["status"],
        "http_status": report["http_status"],
        "call_count": len(client.calls),
        "official_call": report["official_call"],
        "blockers": list(report["blockers"]),
        "warnings": list(report["warnings"]),
        "checks": checks,
        "api_payload": report["api_payload"],
        "smoke_report": report,
    }


def _real_mode_refusal_scenario(
    *,
    handoff_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    client = _FakeOfficialSubmitClient()
    report = smoke_flow._build_report(
        _args(handoff_json=handoff_path, output=output_path),
        client=client,
    )
    checks = {
        "blocked_before_call": report["status"] == "blocked",
        "blocked_stage_handoff_precondition": (
            report.get("blocked_stage") == "handoff_precondition"
        ),
        "real_gateway_handoff_refused": (
            "disabled_smoke_refuses_real_gateway_handoff" in report["blockers"]
        ),
        "official_endpoint_not_called": len(client.calls) == 0,
        "no_real_exchange_effect": (
            report["safety_invariants"]["calls_official_submit_endpoint"] is False
            and report["safety_invariants"]["requests_real_gateway_action"] is False
            and report["safety_invariants"]["exchange_write_called"] is False
            and report["safety_invariants"]["order_lifecycle_called"] is False
        ),
    }
    return {
        "scenario_id": "real-gateway-handoff-refused-by-disabled-smoke",
        "status": "passed" if all(checks.values()) else "failed",
        "report_status": report["status"],
        "call_count": len(client.calls),
        "blockers": list(report["blockers"]),
        "warnings": list(report["warnings"]),
        "checks": checks,
        "smoke_report": report,
    }


def _enabled_response_blocks_scenario(
    *,
    handoff_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    client = _FakeOfficialSubmitClient(
        body={
            "execution_result_id": "unexpected-enabled-rtf051",
            "status": "exchange_submit_execution_disabled",
            "exchange_submit_execution_enabled": True,
            "exchange_submit_execution_mode": "real_gateway_action",
        }
    )
    report = smoke_flow._build_report(
        _args(handoff_json=handoff_path, output=output_path),
        client=client,
    )
    checks = {
        "blocked_by_enabled_response": report["status"] == "blocked",
        "official_endpoint_called_once": len(client.calls) == 1,
        "enabled_exchange_submit_detected": (
            "disabled_smoke_response_enabled_exchange_submit"
            in report["blockers"]
        ),
        "unexpected_mode_warned": (
            "disabled_smoke_response_mode:real_gateway_action"
            in report["warnings"]
        ),
        "owner_confirmation_still_false": (
            client.calls[0]["query"]["owner_confirmed_for_first_real_submit_action"]
            is False
        ),
    }
    return {
        "scenario_id": "disabled-smoke-enabled-response-blocked",
        "status": "passed" if all(checks.values()) else "failed",
        "report_status": report["status"],
        "call_count": len(client.calls),
        "blockers": list(report["blockers"]),
        "warnings": list(report["warnings"]),
        "checks": checks,
        "smoke_report": report,
    }


async def build_official_submit_action_time_bridge_report(
    *,
    work_dir: Path | None = None,
) -> dict[str, Any]:
    output_dir = work_dir or Path("output/rtf051-local/action-time-inputs")
    output_dir.mkdir(parents=True, exist_ok=True)
    submit_preparation_report = (
        await build_next_attempt_submit_preparation_bridge_report()
    )
    ready = _ready_scenario(submit_preparation_report)

    disabled_handoff_path = output_dir / "disabled-handoff.json"
    real_handoff_path = output_dir / "real-mode-handoff.json"
    _write_json(disabled_handoff_path, {"packet": ready["disabled_handoff_packet"]})
    _write_json(real_handoff_path, {"packet": ready["real_mode_handoff_packet"]})

    scenarios = [
        _disabled_smoke_action_time_scenario(
            handoff_path=disabled_handoff_path,
            output_path=output_dir / "disabled-smoke-action-time.json",
        ),
        _real_mode_refusal_scenario(
            handoff_path=real_handoff_path,
            output_path=output_dir / "real-mode-refused.json",
        ),
        _enabled_response_blocks_scenario(
            handoff_path=disabled_handoff_path,
            output_path=output_dir / "enabled-response-blocked.json",
        ),
    ]
    passed = (
        submit_preparation_report["status"]
        == "rtf050_next_attempt_submit_preparation_bridge_passed"
        and all(item["status"] == "passed" for item in scenarios)
    )
    return {
        "scope": "rtf051_official_submit_action_time_bridge",
        "status": (
            "rtf051_official_submit_action_time_bridge_passed"
            if passed
            else "rtf051_official_submit_action_time_bridge_failed"
        ),
        "generated_at_ms": int(time.time() * 1000),
        "source_submit_preparation_status": submit_preparation_report["status"],
        "scenario_count": len(scenarios),
        "scenarios": scenarios,
        "artifact_paths": {
            "disabled_handoff": str(disabled_handoff_path),
            "real_mode_handoff": str(real_handoff_path),
        },
        "safety_summary": {
            "local_fake_client_only": True,
            "database_connected": False,
            "http_network_called": False,
            "official_submit_endpoint_contract_exercised": True,
            "real_gateway_action_requested": False,
            "owner_confirmed_for_first_real_submit_action": False,
            "exchange_write_called": False,
            "order_lifecycle_called": False,
            "execution_intent_created": False,
            "order_created": False,
            "runtime_state_mutated": False,
            "withdrawal_or_transfer_created": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify official submit action-time bridge locally.",
    )
    parser.add_argument("--output-json")
    args = parser.parse_args()
    output_path = Path(args.output_json).expanduser() if args.output_json else None
    report = asyncio.run(
        build_official_submit_action_time_bridge_report(
            work_dir=(
                output_path.parent / "action-time-inputs"
                if output_path is not None
                else None
            ),
        )
    )
    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0 if report["status"].endswith("_passed") else 2


if __name__ == "__main__":
    raise SystemExit(main())
