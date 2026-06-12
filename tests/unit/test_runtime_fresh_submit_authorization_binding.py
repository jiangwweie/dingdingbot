from __future__ import annotations

import json
from decimal import Decimal

import pytest
from fastapi import HTTPException

from scripts import runtime_fresh_submit_authorization_binding_api_flow as api_flow
from src.application.runtime_fresh_submit_authorization_binding_service import (
    RuntimeFreshSubmitAuthorizationBindingService,
)
from src.application.runtime_fresh_submit_authorization_resolution_service import (
    RuntimeFreshSubmitAuthorizationResolutionService,
)
from src.domain.brc_audit_ids import BrcSemanticIds
from src.domain.execution_intent import ExecutionIntent, ExecutionIntentStatus
from src.domain.runtime_execution_plan import (
    RuntimeExecutionIntentDraft,
    RuntimeExecutionIntentDraftStatus,
    RuntimeExecutionPlanStatus,
)
from src.domain.runtime_final_gate_preview import RuntimeFinalGatePreviewVerdict
from src.domain.runtime_fresh_submit_authorization_binding import (
    RuntimeFreshSubmitAuthorizationBindingSource,
    RuntimeFreshSubmitAuthorizationBindingStatus,
)
from src.interfaces import api_trading_console
from src.interfaces.api_trading_console import (
    RuntimeFreshSubmitAuthorizationBindingRequest,
)
from tests.unit.test_runtime_fresh_submit_authorization_resolution import (
    _Repo as _AuthorizationRepo,
    _authorization,
    _handoff,
)


class _IntentRepo:
    def __init__(self, *intents: ExecutionIntent) -> None:
        self.intents = {intent.id: intent for intent in intents}
        self.candidate_calls: list[str] = []

    async def get_by_order_candidate_id(
        self,
        order_candidate_id: str,
    ) -> ExecutionIntent | None:
        self.candidate_calls.append(order_candidate_id)
        matches = [
            intent
            for intent in self.intents.values()
            if intent.order_candidate_id == order_candidate_id
        ]
        return matches[-1] if matches else None


class _DraftRepo:
    def __init__(self, *drafts: RuntimeExecutionIntentDraft) -> None:
        self.drafts = list(drafts)
        self.candidate_calls: list[tuple[str, int]] = []

    async def list_for_order_candidate(
        self,
        order_candidate_id: str,
        *,
        limit: int = 20,
    ) -> list[RuntimeExecutionIntentDraft]:
        self.candidate_calls.append((order_candidate_id, limit))
        return [
            draft
            for draft in self.drafts
            if draft.order_candidate_id == order_candidate_id
        ][:limit]


class _Adapter:
    def __init__(
        self,
        *,
        intent: ExecutionIntent | None = None,
        authorization_id: str = "fresh-auth-created-1",
    ) -> None:
        self.intent = intent or _intent()
        self.authorization_id = authorization_id
        self.created_intent_drafts: list[str] = []
        self.created_authorizations: list[tuple[str, bool]] = []

    async def create_recorded_intent_from_draft(
        self,
        runtime_execution_intent_draft_id: str,
    ) -> ExecutionIntent:
        self.created_intent_drafts.append(runtime_execution_intent_draft_id)
        return self.intent.model_copy(
            update={
                "id": f"intent-from-{runtime_execution_intent_draft_id}",
                "runtime_execution_intent_draft_id": (
                    runtime_execution_intent_draft_id
                ),
            }
        )

    async def create_submit_authorization_for_intent(
        self,
        execution_intent_id: str,
        *,
        owner_confirmed_for_submit: bool,
    ):
        self.created_authorizations.append(
            (execution_intent_id, owner_confirmed_for_submit)
        )
        return _authorization(
            authorization_id=self.authorization_id,
            execution_intent_id=execution_intent_id,
            runtime_execution_intent_draft_id="draft-1",
        )


def _intent(**overrides) -> ExecutionIntent:
    values = {
        "id": "intent-1",
        "symbol": "BNB/USDT:USDT",
        "status": ExecutionIntentStatus.RECORDED,
        "source_type": "brc_runtime_order_candidate",
        "source_id": "order-candidate-1",
        "runtime_execution_intent_draft_id": "draft-1",
        "runtime_instance_id": "runtime-1",
        "trial_binding_id": "trial-1",
        "strategy_family_id": "CPM-001",
        "strategy_family_version_id": "CPM-001-v1",
        "signal_evaluation_id": "signal-eval-1",
        "order_candidate_id": "order-candidate-1",
    }
    values.update(overrides)
    return ExecutionIntent(**values)


def _draft(**overrides) -> RuntimeExecutionIntentDraft:
    semantic_ids = BrcSemanticIds(
        runtime_instance_id="runtime-1",
        trial_binding_id="trial-1",
        strategy_family_id="CPM-001",
        strategy_family_version_id="CPM-001-v1",
        signal_evaluation_id="signal-eval-1",
        order_candidate_id="order-candidate-1",
    )
    values = {
        "draft_id": "draft-1",
        "plan_id": "plan-1",
        "runtime_instance_id": "runtime-1",
        "order_candidate_id": "order-candidate-1",
        "signal_evaluation_id": "signal-eval-1",
        "semantic_ids": semantic_ids,
        "status": RuntimeExecutionIntentDraftStatus.READY_FOR_INTENT_CREATION,
        "symbol": "BNB/USDT:USDT",
        "side": "long",
        "candidate_order_type": "market",
        "proposed_quantity": Decimal("0.1"),
        "intended_notional": Decimal("30"),
        "owner_reviewed": True,
        "owner_confirmed_for_intent": True,
        "source_plan_status": RuntimeExecutionPlanStatus.READY_FOR_INTENT_DRAFT,
        "final_gate_verdict": RuntimeFinalGatePreviewVerdict.PASS,
        "created_at_ms": 1_765_000_000_020,
    }
    values.update(overrides)
    return RuntimeExecutionIntentDraft(**values)


@pytest.mark.asyncio
async def test_binding_reuses_existing_resolved_fresh_authorization():
    service = RuntimeFreshSubmitAuthorizationBindingService(
        adapter_service=_Adapter(),
        resolution_service=RuntimeFreshSubmitAuthorizationResolutionService(
            submit_authorization_repository=_AuthorizationRepo(_authorization()),
        ),
        intent_repository=_IntentRepo(),
        draft_repository=_DraftRepo(),
    )

    packet = await service.bind_for_handoff(
        handoff=_handoff(),
        requested_fresh_submit_authorization_id="fresh-auth-1",
    )

    assert packet.status == (
        RuntimeFreshSubmitAuthorizationBindingStatus.BOUND_EXISTING_AUTHORIZATION
    )
    assert packet.binding_source == (
        RuntimeFreshSubmitAuthorizationBindingSource.EXISTING_RESOLUTION
    )
    assert packet.fresh_submit_authorization_id == "fresh-auth-1"
    assert packet.execution_intent_id == "intent-1"
    assert packet.runtime_execution_intent_draft_id == "draft-1"
    assert packet.ready_for_disabled_smoke_call is True
    assert packet.creates_execution_intent is False
    assert packet.creates_submit_authorization is False
    assert packet.calls_official_submit_endpoint is False
    assert packet.exchange_called is False
    assert packet.order_lifecycle_called is False


@pytest.mark.asyncio
async def test_binding_creates_authorization_from_existing_intent_when_missing():
    adapter = _Adapter(authorization_id="fresh-auth-from-intent")
    service = RuntimeFreshSubmitAuthorizationBindingService(
        adapter_service=adapter,
        resolution_service=RuntimeFreshSubmitAuthorizationResolutionService(
            submit_authorization_repository=_AuthorizationRepo(),
        ),
        intent_repository=_IntentRepo(_intent()),
        draft_repository=_DraftRepo(),
    )

    packet = await service.bind_for_handoff(handoff=_handoff())

    assert packet.status == RuntimeFreshSubmitAuthorizationBindingStatus.CREATED_AUTHORIZATION
    assert packet.binding_source == RuntimeFreshSubmitAuthorizationBindingSource.EXISTING_INTENT
    assert packet.fresh_submit_authorization_id == "fresh-auth-from-intent"
    assert packet.execution_intent_id == "intent-1"
    assert packet.creates_execution_intent is False
    assert packet.creates_submit_authorization is True
    assert adapter.created_authorizations == [("intent-1", True)]


@pytest.mark.asyncio
async def test_binding_creates_intent_and_authorization_from_latest_ready_draft():
    adapter = _Adapter(authorization_id="fresh-auth-from-draft")
    service = RuntimeFreshSubmitAuthorizationBindingService(
        adapter_service=adapter,
        resolution_service=RuntimeFreshSubmitAuthorizationResolutionService(
            submit_authorization_repository=_AuthorizationRepo(),
        ),
        intent_repository=_IntentRepo(),
        draft_repository=_DraftRepo(
            _draft(status=RuntimeExecutionIntentDraftStatus.OWNER_CONFIRMATION_REQUIRED),
            _draft(),
        ),
    )

    packet = await service.bind_for_handoff(handoff=_handoff())

    assert packet.status == (
        RuntimeFreshSubmitAuthorizationBindingStatus.CREATED_INTENT_AND_AUTHORIZATION
    )
    assert packet.binding_source == (
        RuntimeFreshSubmitAuthorizationBindingSource.LATEST_READY_DRAFT
    )
    assert packet.fresh_submit_authorization_id == "fresh-auth-from-draft"
    assert packet.execution_intent_id == "intent-from-draft-1"
    assert packet.runtime_execution_intent_draft_id == "draft-1"
    assert packet.creates_execution_intent is True
    assert packet.creates_submit_authorization is True
    assert adapter.created_intent_drafts == ["draft-1"]
    assert adapter.created_authorizations == [("intent-from-draft-1", True)]


@pytest.mark.asyncio
async def test_binding_blocks_without_authorization_intent_or_ready_draft():
    service = RuntimeFreshSubmitAuthorizationBindingService(
        adapter_service=_Adapter(),
        resolution_service=RuntimeFreshSubmitAuthorizationResolutionService(
            submit_authorization_repository=_AuthorizationRepo(),
        ),
        intent_repository=_IntentRepo(),
        draft_repository=_DraftRepo(
            _draft(status=RuntimeExecutionIntentDraftStatus.OWNER_CONFIRMATION_REQUIRED),
        ),
    )

    packet = await service.bind_for_handoff(handoff=_handoff())

    assert packet.status == RuntimeFreshSubmitAuthorizationBindingStatus.BLOCKED
    assert "ready_runtime_execution_intent_draft_not_found" in packet.blockers
    assert "resolution:fresh_submit_authorization_not_found" in packet.blockers
    assert packet.ready_for_disabled_smoke_call is False
    assert packet.creates_execution_intent is False
    assert packet.creates_submit_authorization is False


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
                "status": "created_authorization",
                "blockers": [],
                "warnings": ["unit"],
                "fresh_submit_authorization_id": "fresh-auth-created-1",
                "execution_intent_id": "intent-1",
                "runtime_execution_intent_draft_id": "draft-1",
                "ready_for_fresh_authorization_resolution": True,
                "ready_for_disabled_smoke_call": True,
                "binding_source": "existing_intent",
                "creates_execution_intent": False,
                "creates_submit_authorization": True,
            },
        }


def _args(tmp_path, **overrides):
    handoff_path = tmp_path / "handoff.json"
    handoff_path.write_text(
        json.dumps({"api_payload": _handoff().model_dump(mode="json")}),
        encoding="utf-8",
    )
    values = {
        "runtime_instance_id": "runtime-1",
        "handoff_json": str(handoff_path),
        "requested_fresh_submit_authorization_id": None,
        "allow_create_from_existing_intent": True,
        "allow_create_intent_from_latest_draft": True,
        "additional_warning": None,
        "additional_blocker": None,
        "env_file": None,
        "api_base": "http://unit",
    }
    values.update(overrides)
    return type("Args", (), values)()


def test_binding_api_flow_posts_binding_request(tmp_path):
    client = _Client()

    report = api_flow._build_report(_args(tmp_path), client=client)

    assert report["status"] == "created_authorization"
    assert report["operator_action_preview"]["ready_for_disabled_smoke_call"] is True
    assert report["safety_invariants"]["creates_submit_authorization"] is True
    assert report["safety_invariants"]["calls_official_submit_endpoint"] is False
    assert report["safety_invariants"]["exchange_write_called"] is False
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["method"] == "POST"
    assert call["path"] == (
        "/api/trading-console/strategy-runtimes/runtime-1/"
        "official-submit-handoff-fresh-authorizations/bind"
    )
    assert call["body"]["handoff_packet"]["handoff_id"].startswith(
        "runtime-official-submit-handoff-runtime-1"
    )
    assert call["body"]["allow_create_from_existing_intent"] is True
    assert call["body"]["allow_create_intent_from_latest_draft"] is True
    assert call["body"]["no_exchange_side_effects"] is True


@pytest.mark.asyncio
async def test_trading_console_binding_endpoint_rejects_runtime_mismatch():
    with pytest.raises(HTTPException) as exc:
        await (
            api_trading_console
            .runtime_official_submit_handoff_fresh_authorization_binding(
                "other-runtime",
                RuntimeFreshSubmitAuthorizationBindingRequest(
                    handoff_packet=_handoff(),
                    no_exchange_side_effects=True,
                ),
            )
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == "handoff_packet_runtime_mismatch"


@pytest.mark.asyncio
async def test_trading_console_binding_endpoint_binds_existing_authorization(
    monkeypatch,
):
    monkeypatch.setattr(
        api_trading_console,
        "_build_pg_runtime_submit_authorization_repo",
        lambda: _AuthorizationRepo(_authorization()),
    )
    monkeypatch.setattr(
        api_trading_console,
        "_build_pg_execution_intent_repo",
        lambda: _IntentRepo(),
    )
    monkeypatch.setattr(
        api_trading_console,
        "_runtime_execution_intent_adapter_service",
        lambda: _async_value(_Adapter()),
    )
    monkeypatch.setattr(
        (
            "src.infrastructure.pg_runtime_execution_intent_draft_repository"
            ".PgRuntimeExecutionIntentDraftRepository"
        ),
        lambda: _DraftRepo(),
    )

    packet = await (
        api_trading_console
        .runtime_official_submit_handoff_fresh_authorization_binding(
            "runtime-1",
            RuntimeFreshSubmitAuthorizationBindingRequest(
                handoff_packet=_handoff(),
                requested_fresh_submit_authorization_id="fresh-auth-1",
                no_exchange_side_effects=True,
            ),
        )
    )

    assert packet.status == (
        RuntimeFreshSubmitAuthorizationBindingStatus.BOUND_EXISTING_AUTHORIZATION
    )
    assert packet.fresh_submit_authorization_id == "fresh-auth-1"


async def _async_value(value):
    return value
