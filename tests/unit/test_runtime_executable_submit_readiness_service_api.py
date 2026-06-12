from decimal import Decimal

import pytest
from fastapi import HTTPException

from src.application.runtime_executable_submit_readiness_service import (
    RuntimeExecutableSubmitReadinessService,
)
from src.domain.runtime_executable_submit_readiness import (
    RuntimeExecutableSubmitReadinessEvidence,
    RuntimeExecutableSubmitReadinessStatus,
)
from tests.unit.test_runtime_next_attempt_strategy_planning import (
    _Planner,
    _ready_release_packet,
    _runtime,
    _signal_input,
)
from src.application.runtime_next_attempt_strategy_planning_service import (
    RuntimeNextAttemptStrategyPlanningService,
)
from src.application.runtime_strategy_signal_planning_service import (
    RuntimeStrategySignalCandidatePlanningStatus,
)


def _evidence(**overrides):
    values = {
        "final_gate_preview_id": "final-gate-preview-1",
        "final_gate_passed": True,
        "runtime_grant_authorization_id": "runtime-grant-1",
        "trusted_submit_fact_snapshot_id": "trusted-facts-1",
        "submit_idempotency_policy_id": "idem-1",
        "attempt_outcome_policy_id": "attempt-policy-1",
        "protection_creation_failure_policy_id": "protection-failure-1",
        "local_registration_enablement_decision_id": "local-enable-1",
        "exchange_submit_enablement_decision_id": "exchange-enable-1",
        "exchange_submit_action_authorization_id": "exchange-action-auth-1",
        "order_lifecycle_submit_enablement_id": "ol-submit-enable-1",
        "exchange_submit_adapter_enablement_id": "exchange-adapter-enable-1",
        "deployment_readiness_evidence_id": "deploy-ready-1",
        "protection_required_and_ready": True,
        "active_position_source_trusted": True,
        "account_facts_fresh": True,
        "duplicate_submit_guard_ready": True,
    }
    values.update(overrides)
    return RuntimeExecutableSubmitReadinessEvidence(**values)


async def _ready_strategy_packet():
    planner = _Planner(
        planning_status=(
            RuntimeStrategySignalCandidatePlanningStatus.SHADOW_CANDIDATE_CREATED
        ),
    )
    service = RuntimeNextAttemptStrategyPlanningService(
        strategy_signal_planner=planner,
    )
    return await service.plan_from_release_gate(
        next_attempt_release_packet=_ready_release_packet(),
        signal_input=_signal_input(),
        runtime=_runtime(boundary={"budget_reserved": Decimal("0")}),
    )


@pytest.mark.asyncio
async def test_service_builds_ready_executable_submit_preview():
    strategy_packet = await _ready_strategy_packet()
    service = RuntimeExecutableSubmitReadinessService()

    packet = await service.preview_from_strategy_planning_packet(
        strategy_planning_packet=strategy_packet,
        evidence=_evidence(),
    )

    assert packet.status == (
        RuntimeExecutableSubmitReadinessStatus.READY_FOR_EXECUTABLE_SUBMIT
    )
    assert packet.executable_submit_ready is True
    assert packet.order_candidate_id == strategy_packet.order_candidate_id
    assert packet.order_lifecycle_called is False
    assert packet.exchange_called is False


@pytest.mark.asyncio
async def test_service_carries_strategy_planning_blockers():
    strategy_packet = await _ready_strategy_packet()
    strategy_packet.blockers.append("unit_blocker")
    service = RuntimeExecutableSubmitReadinessService()

    packet = await service.preview_from_strategy_planning_packet(
        strategy_planning_packet=strategy_packet,
        evidence=_evidence(),
    )

    assert packet.status == RuntimeExecutableSubmitReadinessStatus.BLOCKED
    assert "strategy_planning:unit_blocker" in packet.blockers


@pytest.mark.asyncio
async def test_trading_console_executable_submit_readiness_endpoint():
    from src.interfaces.api_trading_console import (
        RuntimeExecutableSubmitReadinessPreviewRequest,
        runtime_executable_submit_readiness_preview,
    )

    strategy_packet = await _ready_strategy_packet()
    response = await runtime_executable_submit_readiness_preview(
        strategy_packet.runtime_instance_id,
        RuntimeExecutableSubmitReadinessPreviewRequest(
            strategy_planning_packet=strategy_packet,
            evidence=_evidence(),
            additional_warnings=["unit_endpoint"],
        ),
    )

    assert response.status == (
        RuntimeExecutableSubmitReadinessStatus.READY_FOR_EXECUTABLE_SUBMIT
    )
    assert "unit_endpoint" in response.warnings
    assert "trading_console_api_non_executing_preview" in response.warnings
    assert response.exchange_order_submitted is False


@pytest.mark.asyncio
async def test_trading_console_executable_submit_readiness_endpoint_blocks_runtime_mismatch():
    from src.interfaces.api_trading_console import (
        RuntimeExecutableSubmitReadinessPreviewRequest,
        runtime_executable_submit_readiness_preview,
    )

    strategy_packet = await _ready_strategy_packet()
    with pytest.raises(HTTPException) as exc_info:
        await runtime_executable_submit_readiness_preview(
            "different-runtime",
            RuntimeExecutableSubmitReadinessPreviewRequest(
                strategy_planning_packet=strategy_packet,
                evidence=_evidence(),
            ),
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "strategy_planning_packet_runtime_mismatch"
