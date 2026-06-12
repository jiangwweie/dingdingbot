from __future__ import annotations

import json
import sys

import pytest
from fastapi import HTTPException

from scripts import runtime_fresh_submit_authorization_resolution_api_flow as api_flow
from src.interfaces import api_trading_console
from src.interfaces.api_trading_console import (
    RuntimeFreshSubmitAuthorizationResolutionRequest,
)
from src.application.runtime_fresh_submit_authorization_resolution_service import (
    RuntimeFreshSubmitAuthorizationResolutionService,
)
from src.domain.brc_audit_ids import BrcSemanticIds
from src.domain.runtime_execution_submit_authorization import (
    RuntimeExecutionSubmitAuthorization,
    RuntimeExecutionSubmitAuthorizationStatus,
)
from src.domain.runtime_fresh_submit_authorization_resolution import (
    RuntimeFreshSubmitAuthorizationResolutionSource,
    RuntimeFreshSubmitAuthorizationResolutionStatus,
    build_runtime_fresh_submit_authorization_resolution_packet,
)
from src.domain.runtime_official_submit_handoff import (
    RuntimeOfficialSubmitHandoffMode,
    RuntimeOfficialSubmitHandoffPacket,
    build_runtime_official_submit_handoff_packet,
)
from tests.unit.test_runtime_official_submit_handoff import _readiness


class _Repo:
    def __init__(self, *authorizations: RuntimeExecutionSubmitAuthorization) -> None:
        self.items = {item.authorization_id: item for item in authorizations}
        self.get_calls: list[str] = []
        self.candidate_calls: list[str] = []

    async def get(self, authorization_id: str):
        self.get_calls.append(authorization_id)
        return self.items.get(authorization_id)

    async def get_by_order_candidate_id(self, order_candidate_id: str):
        self.candidate_calls.append(order_candidate_id)
        matches = [
            item
            for item in self.items.values()
            if item.semantic_ids.order_candidate_id == order_candidate_id
        ]
        return matches[-1] if matches else None


def _authorization(**overrides) -> RuntimeExecutionSubmitAuthorization:
    values = {
        "authorization_id": "fresh-auth-1",
        "execution_intent_id": "intent-1",
        "runtime_execution_intent_draft_id": "draft-1",
        "source_type": "brc_runtime_order_candidate",
        "source_id": "order-candidate-1",
        "status": (
            RuntimeExecutionSubmitAuthorizationStatus
            .APPROVED_PENDING_CONTROLLED_SUBMIT
        ),
        "semantic_ids": BrcSemanticIds(
            runtime_instance_id="runtime-1",
            trial_binding_id="trial-1",
            strategy_family_id="CPM-001",
            strategy_family_version_id="CPM-001-v1",
            signal_evaluation_id="signal-eval-1",
            order_candidate_id="order-candidate-1",
        ),
        "symbol": "BNB/USDT:USDT",
        "side": "long",
        "created_at_ms": 1_765_000_000_010,
    }
    values.update(overrides)
    return RuntimeExecutionSubmitAuthorization(**values)


def _handoff(**overrides):
    values = {
        "readiness_packet": _readiness(),
        "fresh_submit_authorization_id": "fresh-auth-1",
        "now_ms": 1_765_000_000_001,
    }
    values.update(overrides)
    return build_runtime_official_submit_handoff_packet(**values)


@pytest.mark.asyncio
async def test_resolves_explicit_persisted_fresh_submit_authorization():
    service = RuntimeFreshSubmitAuthorizationResolutionService(
        submit_authorization_repository=_Repo(_authorization()),
    )

    packet = await service.resolve_for_handoff(
        handoff=_handoff(),
        requested_fresh_submit_authorization_id="fresh-auth-1",
    )

    assert packet.status == RuntimeFreshSubmitAuthorizationResolutionStatus.RESOLVED
    assert packet.resolution_source == (
        RuntimeFreshSubmitAuthorizationResolutionSource.EXPLICIT_AUTHORIZATION_ID
    )
    assert packet.resolved_fresh_submit_authorization_id == "fresh-auth-1"
    assert packet.official_endpoint_path.endswith(
        "/runtime-execution-first-real-submit-actions/authorizations/fresh-auth-1"
    )
    assert packet.official_query[
        "owner_confirmed_for_first_real_submit_action"
    ] is False
    assert packet.ready_for_disabled_smoke_call is True
    assert packet.calls_official_submit_endpoint is False
    assert packet.exchange_called is False


@pytest.mark.asyncio
async def test_resolves_by_order_candidate_when_handoff_id_is_rehearsal_only():
    repo = _Repo(_authorization(authorization_id="persisted-auth-1"))
    service = RuntimeFreshSubmitAuthorizationResolutionService(
        submit_authorization_repository=repo,
    )

    packet = await service.resolve_for_handoff(
        handoff=_handoff(fresh_submit_authorization_id="rehearsal-auth-1"),
    )

    assert packet.status == RuntimeFreshSubmitAuthorizationResolutionStatus.RESOLVED
    assert packet.resolution_source == (
        RuntimeFreshSubmitAuthorizationResolutionSource.ORDER_CANDIDATE_LATEST
    )
    assert packet.requested_fresh_submit_authorization_id == "rehearsal-auth-1"
    assert packet.resolved_fresh_submit_authorization_id == "persisted-auth-1"
    assert repo.get_calls == ["rehearsal-auth-1"]
    assert repo.candidate_calls == ["order-candidate-1"]


@pytest.mark.asyncio
async def test_blocks_when_fresh_authorization_missing():
    service = RuntimeFreshSubmitAuthorizationResolutionService(
        submit_authorization_repository=_Repo(),
    )

    packet = await service.resolve_for_handoff(
        handoff=_handoff(),
        allow_order_candidate_fallback=False,
    )

    assert packet.status == RuntimeFreshSubmitAuthorizationResolutionStatus.BLOCKED
    assert "fresh_submit_authorization_not_found" in packet.blockers
    assert packet.ready_for_disabled_smoke_call is False


def test_blocks_reusing_consumed_authorization():
    handoff = _handoff(fresh_submit_authorization_id="consumed-auth-1")
    packet = build_runtime_fresh_submit_authorization_resolution_packet(
        handoff=handoff,
        authorization=_authorization(authorization_id="consumed-auth-1"),
        resolution_source=(
            RuntimeFreshSubmitAuthorizationResolutionSource.HANDOFF_AUTHORIZATION_ID
        ),
        requested_fresh_submit_authorization_id="consumed-auth-1",
        repository_available=True,
        now_ms=1,
    )

    assert packet.status == RuntimeFreshSubmitAuthorizationResolutionStatus.BLOCKED
    assert "fresh_submit_authorization_reuses_consumed_authorization" in (
        packet.blockers
    )


def test_blocks_already_executed_authorization():
    handoff = _handoff()
    executed_authorization = _authorization().model_copy(
        update={"submit_executed": True},
    )
    packet = build_runtime_fresh_submit_authorization_resolution_packet(
        handoff=handoff,
        authorization=executed_authorization,
        resolution_source=(
            RuntimeFreshSubmitAuthorizationResolutionSource.HANDOFF_AUTHORIZATION_ID
        ),
        requested_fresh_submit_authorization_id="fresh-auth-1",
        repository_available=True,
        now_ms=1,
    )

    assert packet.status == RuntimeFreshSubmitAuthorizationResolutionStatus.BLOCKED
    assert "fresh_submit_authorization_already_executed" in packet.blockers


def test_blocks_real_gateway_handoff():
    handoff = _handoff(
        mode=RuntimeOfficialSubmitHandoffMode.REAL_GATEWAY_ACTION,
        owner_confirmed_for_real_submit_action=True,
    )
    packet = build_runtime_fresh_submit_authorization_resolution_packet(
        handoff=handoff,
        authorization=_authorization(),
        resolution_source=(
            RuntimeFreshSubmitAuthorizationResolutionSource.HANDOFF_AUTHORIZATION_ID
        ),
        requested_fresh_submit_authorization_id="fresh-auth-1",
        repository_available=True,
        now_ms=1,
    )

    assert packet.status == RuntimeFreshSubmitAuthorizationResolutionStatus.BLOCKED
    assert "fresh_authorization_resolution_requires_disabled_smoke_handoff" in (
        packet.blockers
    )


class _Client:
    def __init__(self, *, http_status: int = 200, body: dict | None = None) -> None:
        self.http_status = http_status
        self.body = body or {
            "status": "resolved",
            "blockers": [],
            "warnings": ["unit"],
            "ready_for_disabled_smoke_call": True,
            "official_endpoint_method": "POST",
            "official_endpoint_path": (
                "/api/trading-console/runtime-execution-first-real-submit-actions/"
                "authorizations/fresh-auth-1"
            ),
            "official_query": {
                "owner_confirmed_for_first_real_submit_action": False,
            },
            "resolved_fresh_submit_authorization_id": "fresh-auth-1",
            "resolution_source": "explicit_authorization_id",
        }
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
        return {"http_status": self.http_status, "body": self.body}


def _args(tmp_path, **overrides):
    handoff_path = tmp_path / "handoff.json"
    handoff_path.write_text(
        json.dumps({"api_payload": _handoff().model_dump(mode="json")}),
        encoding="utf-8",
    )
    values = {
        "runtime_instance_id": "runtime-1",
        "handoff_json": str(handoff_path),
        "requested_fresh_submit_authorization_id": "fresh-auth-1",
        "allow_order_candidate_fallback": True,
        "additional_warning": None,
        "additional_blocker": None,
        "env_file": None,
        "api_base": "http://unit",
    }
    values.update(overrides)
    return type("Args", (), values)()


def test_resolution_api_flow_posts_resolution_request(tmp_path):
    client = _Client()

    report = api_flow._build_report(_args(tmp_path), client=client)

    assert report["status"] == "resolved"
    assert report["operator_action_preview"]["ready_for_disabled_smoke_call"] is True
    assert report["safety_invariants"]["creates_authorization"] is False
    assert report["safety_invariants"]["calls_official_submit_endpoint"] is False
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["method"] == "POST"
    assert call["path"] == (
        "/api/trading-console/strategy-runtimes/runtime-1/"
        "official-submit-handoff-fresh-authorizations/resolve"
    )
    assert call["body"]["handoff_packet"]["handoff_id"].startswith(
        "runtime-official-submit-handoff-runtime-1"
    )
    assert call["body"]["requested_fresh_submit_authorization_id"] == "fresh-auth-1"
    assert call["body"]["non_executing"] is True


@pytest.mark.asyncio
async def test_trading_console_endpoint_resolves_fresh_authorization(monkeypatch):
    monkeypatch.setattr(
        api_trading_console,
        "_build_pg_runtime_submit_authorization_repo",
        lambda: _Repo(_authorization()),
    )

    packet = (
        await api_trading_console
        .runtime_official_submit_handoff_fresh_authorization_resolution(
            "runtime-1",
            RuntimeFreshSubmitAuthorizationResolutionRequest(
                handoff_packet=_handoff(),
                requested_fresh_submit_authorization_id="fresh-auth-1",
                non_executing=True,
            ),
        )
    )

    assert packet.status == RuntimeFreshSubmitAuthorizationResolutionStatus.RESOLVED
    assert packet.resolved_fresh_submit_authorization_id == "fresh-auth-1"
    assert packet.ready_for_disabled_smoke_call is True


@pytest.mark.asyncio
async def test_trading_console_endpoint_rejects_runtime_mismatch(monkeypatch):
    monkeypatch.setattr(
        api_trading_console,
        "_build_pg_runtime_submit_authorization_repo",
        lambda: _Repo(_authorization()),
    )

    with pytest.raises(HTTPException) as exc:
        await (
            api_trading_console
            .runtime_official_submit_handoff_fresh_authorization_resolution(
                "other-runtime",
                RuntimeFreshSubmitAuthorizationResolutionRequest(
                    handoff_packet=_handoff(),
                    non_executing=True,
                ),
            )
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == "handoff_packet_runtime_mismatch"


def test_resolution_api_flow_keeps_http_errors(tmp_path):
    report = api_flow._build_report(
        _args(tmp_path),
        client=_Client(http_status=400, body={"detail": "bad"}),
    )

    assert report["status"] == "blocked"
    assert report["blocked_stage"] == "fresh_submit_authorization_resolution_api"
    assert "fresh_submit_authorization_resolution_api_http_400" in report["blockers"]


def test_resolution_api_flow_cli_stdout_is_json_only(monkeypatch, capsys):
    def fake_build_report(args):
        print("inner noisy fresh authorization resolution")
        return {"status": "blocked", "ok": True}

    monkeypatch.setattr(api_flow, "_build_report", fake_build_report)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "runtime_fresh_submit_authorization_resolution_api_flow.py",
            "--runtime-instance-id",
            "runtime-1",
            "--handoff-json",
            "handoff.json",
        ],
    )

    assert api_flow.main() == 0

    captured = capsys.readouterr()
    assert captured.out.startswith("{")
    assert "inner noisy fresh authorization resolution" not in captured.out
    assert "inner noisy fresh authorization resolution" in captured.err
