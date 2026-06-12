from __future__ import annotations

import json

import pytest
from fastapi import HTTPException

from scripts import runtime_persisted_draft_source_readiness_api_flow as api_flow
from src.application.runtime_persisted_draft_source_readiness_bridge_service import (
    RuntimePersistedDraftSourceReadinessBridgeService,
    strategy_planning_packet_from_intent_draft_source,
)
from src.application.runtime_strategy_signal_intent_draft_source_service import (
    RuntimeStrategySignalIntentDraftSourcePacket,
    RuntimeStrategySignalIntentDraftSourceService,
    RuntimeStrategySignalIntentDraftSourceStatus,
)
from src.domain.runtime_executable_submit_readiness import (
    RuntimeExecutableSubmitReadinessEvidence,
    RuntimeExecutableSubmitReadinessStatus,
)
from src.interfaces import api_trading_console
from src.interfaces.api_trading_console import (
    RuntimePersistedDraftSourceReadinessPreviewRequest,
)
from tests.unit.test_runtime_strategy_signal_intent_draft_source import (
    _ExecutionPlanning,
    _Scheduler,
    _async_value,
    _candidate,
    _draft,
    _runtime,
    _scheduler_result,
    _signal_input,
)


def _evidence(**overrides):
    values = {
        "final_gate_preview_id": "final-gate-preview-rtf015",
        "final_gate_passed": True,
        "runtime_grant_authorization_id": "runtime-grant-rtf015",
        "trusted_submit_fact_snapshot_id": "trusted-facts-rtf015",
        "submit_idempotency_policy_id": "idem-rtf015",
        "attempt_outcome_policy_id": "attempt-policy-rtf015",
        "protection_creation_failure_policy_id": "protection-failure-rtf015",
        "local_registration_enablement_decision_id": "local-enable-rtf015",
        "exchange_submit_enablement_decision_id": "exchange-enable-rtf015",
        "exchange_submit_action_authorization_id": "exchange-action-auth-rtf015",
        "order_lifecycle_submit_enablement_id": "ol-submit-enable-rtf015",
        "exchange_submit_adapter_enablement_id": "exchange-adapter-enable-rtf015",
        "deployment_readiness_evidence_id": "deploy-ready-rtf015",
        "protection_required_and_ready": True,
        "active_position_source_trusted": True,
        "account_facts_fresh": True,
        "duplicate_submit_guard_ready": True,
    }
    values.update(overrides)
    return RuntimeExecutableSubmitReadinessEvidence(**values)


async def _ready_source() -> RuntimeStrategySignalIntentDraftSourcePacket:
    service = RuntimeStrategySignalIntentDraftSourceService(
        scheduler_planning_service=_Scheduler(_scheduler_result(candidate=_candidate())),
        runtime_execution_planning_service=_ExecutionPlanning(_draft()),
    )
    return await service.record_ready_intent_draft_source(
        _signal_input(),
        runtime=_runtime(),
        allow_shadow_candidate_creation=True,
        allow_intent_draft_creation=True,
        owner_reviewed=True,
        owner_confirmed_for_intent=True,
        active_positions_count=0,
    )


@pytest.mark.asyncio
async def test_bridge_builds_ready_readiness_from_persisted_draft_source():
    source = await _ready_source()
    service = RuntimePersistedDraftSourceReadinessBridgeService()

    packet = await service.preview_from_intent_draft_source(
        intent_draft_source_packet=source,
        evidence=_evidence(),
    )

    assert packet.status == (
        RuntimeExecutableSubmitReadinessStatus.READY_FOR_EXECUTABLE_SUBMIT
    )
    assert packet.order_candidate_id == source.order_candidate_id
    assert packet.signal_evaluation_id == source.signal_evaluation_id
    assert packet.source_authorization_id.startswith("persisted-draft-source:")
    assert packet.source_authorization_id != "runtime-grant-rtf015"
    assert "readiness_from_persisted_intent_draft_source" in packet.warnings
    assert packet.execution_intent_created is False
    assert packet.order_created is False
    assert packet.order_lifecycle_called is False
    assert packet.exchange_called is False


@pytest.mark.asyncio
async def test_bridge_blocks_when_source_is_not_ready():
    source = await _ready_source()
    values = source.model_dump(mode="python")
    values.update(
        {
            "status": RuntimeStrategySignalIntentDraftSourceStatus.BLOCKED,
            "ready_for_official_handoff_source": False,
            "runtime_execution_intent_draft_id": None,
            "draft_status": None,
            "blockers": ["unit_source_blocker"],
        }
    )
    blocked_source = RuntimeStrategySignalIntentDraftSourcePacket(**values)
    strategy_packet = strategy_planning_packet_from_intent_draft_source(
        blocked_source,
    )

    assert strategy_packet.status.value == "blocked_by_strategy_planning"
    assert "unit_source_blocker" in strategy_packet.blockers
    assert "intent_draft_source_not_ready" in strategy_packet.blockers
    assert "runtime_execution_intent_draft_id_missing" in strategy_packet.blockers

    service = RuntimePersistedDraftSourceReadinessBridgeService()
    packet = await service.preview_from_intent_draft_source(
        intent_draft_source_packet=blocked_source,
        evidence=_evidence(),
    )

    assert packet.status == RuntimeExecutableSubmitReadinessStatus.BLOCKED
    assert "strategy_planning:unit_source_blocker" in packet.blockers
    assert packet.exchange_order_submitted is False


@pytest.mark.asyncio
async def test_trading_console_persisted_draft_source_readiness_endpoint():
    source = await _ready_source()

    response = await (
        api_trading_console.runtime_persisted_draft_source_readiness_preview(
            source.runtime_instance_id,
            RuntimePersistedDraftSourceReadinessPreviewRequest(
                intent_draft_source_packet=source,
                evidence=_evidence(),
                additional_warnings=["unit_endpoint"],
            ),
        )
    )

    assert response.status == (
        RuntimeExecutableSubmitReadinessStatus.READY_FOR_EXECUTABLE_SUBMIT
    )
    assert "unit_endpoint" in response.warnings
    assert (
        "trading_console_api_non_executing_persisted_draft_source_readiness_preview"
        in response.warnings
    )
    assert response.order_lifecycle_called is False
    assert response.exchange_called is False


@pytest.mark.asyncio
async def test_trading_console_persisted_draft_source_readiness_endpoint_blocks_runtime_mismatch():
    source = await _ready_source()

    with pytest.raises(HTTPException) as exc:
        await api_trading_console.runtime_persisted_draft_source_readiness_preview(
            "different-runtime",
            RuntimePersistedDraftSourceReadinessPreviewRequest(
                intent_draft_source_packet=source,
                evidence=_evidence(),
            ),
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == "intent_draft_source_packet_runtime_mismatch"


def test_persisted_draft_source_readiness_api_flow_posts_request(tmp_path):
    source_path = tmp_path / "source.json"
    evidence_path = tmp_path / "evidence.json"
    source_path.write_text(
        json.dumps({"api_payload": _ready_source_sync().model_dump(mode="json")}),
        encoding="utf-8",
    )
    evidence_path.write_text(
        json.dumps(_evidence().model_dump(mode="json")),
        encoding="utf-8",
    )
    client = _Client()

    report = api_flow._build_packet(
        _args(tmp_path, source_path=source_path, evidence_path=evidence_path),
        client=client,
    )

    assert report["status"] == "ready_for_executable_submit"
    assert report["safety_invariants"]["execution_intent_created"] is False
    assert report["safety_invariants"]["order_lifecycle_called"] is False
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["method"] == "POST"
    assert call["path"] == (
        "/api/trading-console/strategy-runtimes/runtime-rtf014/"
        "persisted-draft-source-readiness-previews"
    )
    assert (
        call["body"]["intent_draft_source_packet"]["runtime_instance_id"]
        == "runtime-rtf014"
    )
    assert call["body"]["non_executing"] is True


def _ready_source_sync() -> RuntimeStrategySignalIntentDraftSourcePacket:
    scheduler = _scheduler_result(candidate=_candidate())
    draft = _draft()
    return RuntimeStrategySignalIntentDraftSourcePacket(
        packet_id="runtime-strategy-signal-intent-draft-source-eval-rtf014",
        runtime_instance_id="runtime-rtf014",
        strategy_family_id="CPM-RO-001",
        strategy_family_version_id="CPM-RO-001-v0",
        symbol="ETH/USDT:USDT",
        status=RuntimeStrategySignalIntentDraftSourceStatus.PERSISTED_READY_INTENT_DRAFT,
        scheduler_planning=scheduler,
        signal_evaluation_id="eval-rtf014",
        order_candidate_id="order-candidate-rtf014",
        runtime_execution_intent_draft_id=draft.draft_id,
        draft_status=draft.status,
        ready_for_official_handoff_source=True,
        allow_shadow_candidate_creation=True,
        allow_intent_draft_creation=True,
        owner_reviewed=True,
        owner_confirmed_for_intent=True,
        signal_evaluation_created=True,
        order_candidate_created=True,
        runtime_execution_intent_draft_created=True,
    )


class _Client:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def request_json(self, method, path, *, query=None, body=None):
        self.calls.append(
            {
                "method": method,
                "path": path,
                "query": query,
                "body": body,
            }
        )
        return {
            "http_status": 200,
            "body": {
                "status": "ready_for_executable_submit",
                "packet_id": "runtime-executable-submit-readiness-unit",
                "source_strategy_planning_packet_id": "strategy-plan-unit",
                "source_authorization_id": "persisted-draft-source:unit",
                "signal_evaluation_id": "eval-rtf014",
                "order_candidate_id": "order-candidate-rtf014",
                "executable_submit_ready": True,
                "blockers": [],
                "warnings": ["unit"],
            },
        }


def _args(tmp_path, *, source_path, evidence_path, **overrides):
    values = {
        "runtime_instance_id": "runtime-rtf014",
        "intent_draft_source_json": str(source_path),
        "evidence_json": str(evidence_path),
        "first_real_submit_packet_json": None,
        "additional_warning": None,
        "additional_blocker": None,
        "env_file": None,
        "api_base": "http://unit",
    }
    values.update(overrides)
    return type("Args", (), values)()
