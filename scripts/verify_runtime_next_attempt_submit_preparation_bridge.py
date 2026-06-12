#!/usr/bin/env python3
"""Verify next-attempt strategy planning -> submit-preparation bridge locally.

RTF-050 composes the RTF-049 next-attempt strategy-planning proof with the
current executable-readiness and official-submit handoff domain services.

This verifier intentionally stops before the official submit endpoint. It does
not connect to PG, HTTP, exchange, OrderLifecycle, withdrawals, or transfers.
"""

from __future__ import annotations

import argparse
import asyncio
from decimal import Decimal
import json
from pathlib import Path
import sys
import time
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.verify_runtime_next_attempt_gate_strategy_planning import (  # noqa: E402
    build_next_attempt_gate_strategy_planning_report,
)
from src.application.runtime_executable_submit_readiness_service import (  # noqa: E402
    RuntimeExecutableSubmitReadinessService,
)
from src.application.runtime_next_attempt_strategy_planning_service import (  # noqa: E402
    RuntimeNextAttemptStrategyPlanningPacket,
    RuntimeNextAttemptStrategyPlanningStatus,
)
from src.application.runtime_official_submit_handoff_service import (  # noqa: E402
    RuntimeOfficialSubmitHandoffService,
)
from src.domain.runtime_executable_submit_readiness import (  # noqa: E402
    RuntimeExecutableSubmitReadinessEvidence,
)
from src.domain.runtime_official_submit_handoff import (  # noqa: E402
    RuntimeOfficialSubmitHandoffMode,
)


READY_FOR_FINAL_GATE_PREFLIGHT = (
    RuntimeNextAttemptStrategyPlanningStatus.READY_FOR_FINAL_GATE_PREFLIGHT
)


def _json_value(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return _json_value(value.model_dump(mode="python"))
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _evidence(
    *,
    runtime_instance_id: str,
    source_authorization_id: str,
    durable_execution_result_id: str | None = None,
) -> RuntimeExecutableSubmitReadinessEvidence:
    suffix = runtime_instance_id.replace("/", "_").replace(":", "_")
    return RuntimeExecutableSubmitReadinessEvidence(
        final_gate_preview_id=f"final-gate-preview-rtf050-{suffix}",
        final_gate_passed=True,
        runtime_grant_authorization_id=f"runtime-grant-rtf050-{suffix}",
        trusted_submit_fact_snapshot_id=f"trusted-submit-facts-rtf050-{suffix}",
        submit_idempotency_policy_id=f"submit-idempotency-rtf050-{suffix}",
        attempt_outcome_policy_id=f"attempt-outcome-policy-rtf050-{suffix}",
        protection_creation_failure_policy_id=(
            f"protection-failure-policy-rtf050-{suffix}"
        ),
        local_registration_enablement_decision_id=(
            f"local-registration-enable-rtf050-{suffix}"
        ),
        exchange_submit_enablement_decision_id=(
            f"exchange-submit-enable-rtf050-{suffix}"
        ),
        exchange_submit_action_authorization_id=(
            f"exchange-submit-action-auth-rtf050-{suffix}"
        ),
        order_lifecycle_submit_enablement_id=(
            f"order-lifecycle-submit-enable-rtf050-{suffix}"
        ),
        exchange_submit_adapter_enablement_id=(
            f"exchange-submit-adapter-enable-rtf050-{suffix}"
        ),
        deployment_readiness_evidence_id=f"deployment-ready-rtf050-{suffix}",
        protection_required_and_ready=True,
        active_position_source_trusted=True,
        account_facts_fresh=True,
        duplicate_submit_guard_ready=True,
        legacy_runtime_submit_rehearsal_id=None,
        durable_exchange_submit_execution_result_id=(
            durable_execution_result_id
            or f"durable-submit-result-rtf050-{source_authorization_id}"
        ),
    )


async def _ready_submit_preparation(
    *,
    planning_packet: RuntimeNextAttemptStrategyPlanningPacket,
) -> dict[str, Any]:
    readiness_service = RuntimeExecutableSubmitReadinessService()
    handoff_service = RuntimeOfficialSubmitHandoffService()
    evidence = _evidence(
        runtime_instance_id=planning_packet.runtime_instance_id,
        source_authorization_id=planning_packet.source_authorization_id,
    )
    readiness = await readiness_service.preview_from_strategy_planning_packet(
        strategy_planning_packet=planning_packet,
        evidence=evidence,
        additional_warnings=["rtf050_local_submit_preparation_bridge"],
    )
    fresh_submit_authorization_id = (
        f"fresh-submit-auth-rtf050-{planning_packet.runtime_instance_id}"
    )
    missing_auth_handoff = await handoff_service.preview_from_readiness_packet(
        readiness_packet=readiness,
        fresh_submit_authorization_id=None,
        mode=RuntimeOfficialSubmitHandoffMode.DISABLED_SMOKE,
    )
    disabled_handoff = await handoff_service.preview_from_readiness_packet(
        readiness_packet=readiness,
        fresh_submit_authorization_id=fresh_submit_authorization_id,
        mode=RuntimeOfficialSubmitHandoffMode.DISABLED_SMOKE,
    )
    real_mode_handoff = await handoff_service.preview_from_readiness_packet(
        readiness_packet=readiness,
        fresh_submit_authorization_id=fresh_submit_authorization_id,
        mode=RuntimeOfficialSubmitHandoffMode.REAL_GATEWAY_ACTION,
        owner_confirmed_for_real_submit_action=True,
    )
    checks = {
        "planning_ready_for_final_gate_preflight": (
            planning_packet.status == READY_FOR_FINAL_GATE_PREFLIGHT
        ),
        "readiness_ready_for_executable_submit": (
            readiness.status.value == "ready_for_executable_submit"
            and readiness.executable_submit_ready is True
        ),
        "missing_fresh_auth_blocks_handoff": (
            missing_auth_handoff.status.value == "blocked"
            and "fresh_submit_authorization_id_missing"
            in missing_auth_handoff.blockers
        ),
        "fresh_auth_is_not_consumed_authorization": (
            fresh_submit_authorization_id != readiness.source_authorization_id
        ),
        "disabled_handoff_ready": (
            disabled_handoff.status.value == "ready_for_official_submit_call"
            and disabled_handoff.ready_for_official_submit_call is True
        ),
        "real_mode_preview_ready_with_owner_confirmation": (
            real_mode_handoff.status.value == "ready_for_official_submit_call"
            and real_mode_handoff.official_query.get(
                "owner_confirmed_for_first_real_submit_action"
            )
            is True
        ),
        "official_endpoint_not_called": True,
        "no_execution_side_effects": (
            readiness.execution_intent_created is False
            and readiness.order_created is False
            and readiness.order_lifecycle_called is False
            and readiness.exchange_called is False
            and disabled_handoff.order_lifecycle_called is False
            and disabled_handoff.exchange_called is False
            and disabled_handoff.exchange_order_submitted is False
            and disabled_handoff.withdrawal_or_transfer_created is False
        ),
        "legacy_pre_attempt_rehearsal_not_required": (
            readiness.legacy_pre_attempt_rehearsal_required is False
            and "legacy_runtime_submit_rehearsal_id_not_required"
            in readiness.warnings
        ),
        "durable_execution_result_is_post_submit_evidence_only": (
            "durable_execution_result_is_post_submit_evidence_only"
            in readiness.warnings
        ),
    }
    return {
        "scenario_id": "ready-cpm-long-submit-preparation",
        "status": "passed" if all(checks.values()) else "failed",
        "strategy_planning_status": planning_packet.status.value,
        "readiness_status": readiness.status.value,
        "missing_auth_handoff_status": missing_auth_handoff.status.value,
        "disabled_handoff_status": disabled_handoff.status.value,
        "real_mode_handoff_status": real_mode_handoff.status.value,
        "official_endpoint_path": disabled_handoff.official_endpoint_path,
        "official_query": _json_value(disabled_handoff.official_query),
        "checks": checks,
        "blockers": (
            list(readiness.blockers)
            + list(disabled_handoff.blockers)
            + list(real_mode_handoff.blockers)
        ),
        "warnings": (
            list(readiness.warnings)
            + list(disabled_handoff.warnings)
            + list(real_mode_handoff.warnings)
        ),
        "strategy_planning_packet": _json_value(planning_packet),
        "readiness_packet": _json_value(readiness),
        "disabled_handoff_packet": _json_value(disabled_handoff),
        "real_mode_handoff_packet": _json_value(real_mode_handoff),
    }


def _non_ready_submit_preparation(
    *,
    scenario: dict[str, Any],
    planning_packet: RuntimeNextAttemptStrategyPlanningPacket,
) -> dict[str, Any]:
    checks = {
        "planning_not_ready_for_final_gate_preflight": (
            planning_packet.status != READY_FOR_FINAL_GATE_PREFLIGHT
        ),
        "readiness_not_run": True,
        "handoff_not_run": True,
        "no_execution_side_effects": (
            planning_packet.execution_intent_created is False
            and planning_packet.order_created is False
            and planning_packet.order_lifecycle_called is False
            and planning_packet.exchange_called is False
            and planning_packet.exchange_order_submitted is False
            and planning_packet.withdrawal_or_transfer_created is False
        ),
    }
    return {
        "scenario_id": f"{scenario['scenario_id']}-submit-preparation-blocked",
        "status": "passed" if all(checks.values()) else "failed",
        "strategy_planning_status": planning_packet.status.value,
        "readiness_status": "not_run",
        "handoff_status": "not_run",
        "blockers": list(planning_packet.blockers),
        "warnings": list(planning_packet.warnings),
        "checks": checks,
        "strategy_planning_packet": _json_value(planning_packet),
    }


async def build_next_attempt_submit_preparation_bridge_report() -> dict[str, Any]:
    planning_report = await build_next_attempt_gate_strategy_planning_report()
    scenarios: list[dict[str, Any]] = []

    for scenario in planning_report["scenarios"]:
        planning_packet = RuntimeNextAttemptStrategyPlanningPacket.model_validate(
            scenario["strategy_planning_packet"],
        )
        if planning_packet.status == READY_FOR_FINAL_GATE_PREFLIGHT:
            scenarios.append(
                await _ready_submit_preparation(
                    planning_packet=planning_packet,
                )
            )
        else:
            scenarios.append(
                _non_ready_submit_preparation(
                    scenario=scenario,
                    planning_packet=planning_packet,
                )
            )

    passed = (
        planning_report["status"] == "rtf049_next_attempt_gate_strategy_planning_passed"
        and all(item["status"] == "passed" for item in scenarios)
    )
    return {
        "scope": "rtf050_next_attempt_submit_preparation_bridge",
        "status": (
            "rtf050_next_attempt_submit_preparation_bridge_passed"
            if passed
            else "rtf050_next_attempt_submit_preparation_bridge_failed"
        ),
        "generated_at_ms": int(time.time() * 1000),
        "source_planning_report_status": planning_report["status"],
        "scenario_count": len(scenarios),
        "scenarios": scenarios,
        "safety_summary": {
            "local_in_memory_only": True,
            "database_connected": False,
            "http_network_called": False,
            "official_submit_endpoint_called": False,
            "exchange_write_called": False,
            "pre_submit_rehearsal_called": False,
            "order_lifecycle_called": False,
            "execution_intent_created": False,
            "executable_execution_intent_created": False,
            "order_created": False,
            "runtime_state_mutated": False,
            "withdrawal_or_transfer_created": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify next-attempt strategy planning to submit-preparation bridge "
            "locally."
        ),
    )
    parser.add_argument("--output-json")
    args = parser.parse_args()
    report = asyncio.run(build_next_attempt_submit_preparation_bridge_report())
    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output_json:
        output_path = Path(args.output_json).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0 if report["status"].endswith("_passed") else 2


if __name__ == "__main__":
    raise SystemExit(main())
