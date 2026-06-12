from __future__ import annotations

import json
import sys

from scripts import runtime_post_submit_finalize_api_flow
from src.interfaces import api_trading_console
from src.domain.runtime_post_submit_finalize import (
    RuntimePostSubmitFinalizeStatus,
)
from tests.unit.test_runtime_post_submit_finalize import _ready_review_no_fill_cancelled
from tests.unit.test_runtime_execution_submit_outcome_review import (
    _runtime,
    _settlement,
    _submitted_result,
)
from src.domain.runtime_post_submit_finalize import (
    build_runtime_post_submit_finalize_packet,
)


class _Client:
    def __init__(self, *, http_status: int = 200, body: dict | None = None) -> None:
        self.http_status = http_status
        self.body = body or build_runtime_post_submit_finalize_packet(
            authorization_id="auth-1",
            runtime=_runtime(boundary={"budget_reserved": 0}),
            exchange_submit_execution_result=_submitted_result(),
            submit_outcome_review=_ready_review_no_fill_cancelled(),
            post_submit_budget_settlement=_settlement(),
            active_positions_count=0,
            closed_review_required=False,
            now_ms=1781090000000,
        ).model_dump(mode="json")
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


def _args(**overrides):
    values = {
        "runtime_instance_id": "runtime-1",
        "reservation_id": "runtime-attempt-reservation-auth-1",
        "authorization_id": "auth-1",
        "closed_review_required": False,
        "protection_blocker": None,
        "env_file": None,
        "api_base": "http://unit",
        "metadata_json": '{"owner":"unit"}',
    }
    values.update(overrides)
    return type("Args", (), values)()


def test_post_submit_finalize_api_flow_posts_runtime_finalize_request():
    client = _Client()

    packet = runtime_post_submit_finalize_api_flow._build_packet(
        _args(),
        client=client,
    )

    assert packet["status"] == (
        RuntimePostSubmitFinalizeStatus.FINALIZED_READY_FOR_NEXT_ATTEMPT.value
    )
    assert packet["safety_invariants"]["exchange_write_called"] is False
    assert packet["safety_invariants"]["pre_submit_rehearsal_called"] is False
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["method"] == "POST"
    assert call["path"] == (
        "/api/trading-console/strategy-runtimes/runtime-1/"
        "post-submit-finalize-packets"
    )
    assert call["body"]["authorization_id"] == "auth-1"
    assert call["body"]["reservation_id"] == "runtime-attempt-reservation-auth-1"
    assert call["body"]["metadata"]["runtime_post_submit_finalize_api_flow"] is True
    assert call["body"]["metadata"]["owner"] == "unit"
    assert call["body"]["non_executing"] is True


def test_post_submit_finalize_api_flow_can_omit_authorization_for_latest_result():
    client = _Client()

    packet = runtime_post_submit_finalize_api_flow._build_packet(
        _args(authorization_id=None, reservation_id=None),
        client=client,
    )

    assert packet["authorization_id"] == "auth-1"
    assert "authorization_id" not in client.calls[0]["body"]
    assert "reservation_id" not in client.calls[0]["body"]


def test_post_submit_finalize_api_flow_keeps_blocked_http_errors():
    packet = runtime_post_submit_finalize_api_flow._build_packet(
        _args(),
        client=_Client(http_status=503, body={"detail": "unavailable"}),
    )

    assert packet["status"] == "blocked"
    assert packet["blocked_stage"] == "post_submit_finalize_api"
    assert "post_submit_finalize_api_http_503" in packet["blockers"]
    assert packet["safety_invariants"]["order_lifecycle_called"] is False


def test_post_submit_finalize_api_flow_cli_stdout_is_json_only(monkeypatch, capsys):
    def fake_build_packet(args):
        print("inner noisy finalize flow")
        return {"status": "blocked", "ok": True}

    monkeypatch.setattr(
        runtime_post_submit_finalize_api_flow,
        "_build_packet",
        fake_build_packet,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "runtime_post_submit_finalize_api_flow.py",
            "--runtime-instance-id",
            "runtime-1",
        ],
    )

    assert runtime_post_submit_finalize_api_flow.main() == 0

    captured = capsys.readouterr()
    assert captured.out.startswith("{")
    assert json.loads(captured.out)["status"] == "blocked"
    assert "inner noisy finalize flow" not in captured.out
    assert "inner noisy finalize flow" in captured.err


async def test_trading_console_endpoint_finalizes_latest_submit_without_manual_auth(
    monkeypatch,
):
    packet = build_runtime_post_submit_finalize_packet(
        authorization_id="auth-1",
        runtime=_runtime(boundary={"budget_reserved": 0}),
        exchange_submit_execution_result=_submitted_result(),
        submit_outcome_review=_ready_review_no_fill_cancelled(),
        post_submit_budget_settlement=_settlement(),
        active_positions_count=0,
        closed_review_required=False,
        now_ms=1781090000000,
    )
    service = _FinalizeService(packet)
    result = _submitted_result()

    async def fake_service():
        return service

    async def fake_result_for_finalize(*, runtime_instance_id, authorization_id):
        assert runtime_instance_id == "runtime-1"
        assert authorization_id is None
        return result

    async def fake_active_positions_count(submit_result, *, expected_runtime_instance_id):
        assert submit_result is result
        assert expected_runtime_instance_id == "runtime-1"
        return 0

    monkeypatch.setattr(
        api_trading_console,
        "_runtime_post_submit_finalize_service",
        fake_service,
    )
    monkeypatch.setattr(
        api_trading_console,
        "_runtime_exchange_submit_execution_result_for_finalize",
        fake_result_for_finalize,
    )
    monkeypatch.setattr(
        api_trading_console,
        "_runtime_active_positions_count_for_submit_result",
        fake_active_positions_count,
    )

    response = await (
        api_trading_console.runtime_post_submit_finalize_packet_for_runtime(
            "runtime-1",
            api_trading_console.RuntimePostSubmitFinalizeRequest(),
        )
    )

    assert response.authorization_id == "auth-1"
    assert service.latest_calls == [
        {
            "runtime_instance_id": "runtime-1",
            "reservation_id": None,
            "active_positions_count": 0,
        }
    ]
    assert service.authorization_calls == []


class _FinalizeService:
    def __init__(self, packet) -> None:
        self.packet = packet
        self.latest_calls = []
        self.authorization_calls = []

    async def finalize_latest_for_runtime(
        self,
        runtime_instance_id,
        *,
        reservation_id,
        active_positions_count,
        closed_review_required=False,
        protection_blockers=None,
    ):
        self.latest_calls.append(
            {
                "runtime_instance_id": runtime_instance_id,
                "reservation_id": reservation_id,
                "active_positions_count": active_positions_count,
            }
        )
        return self.packet

    async def finalize_authorization(self, *args, **kwargs):
        self.authorization_calls.append({"args": args, "kwargs": kwargs})
        return self.packet
