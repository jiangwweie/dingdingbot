from __future__ import annotations

import json
import sys

from scripts import runtime_next_attempt_strategy_plan_api_flow


class _Client:
    def __init__(self, *, http_status: int = 200, body: dict | None = None) -> None:
        self.http_status = http_status
        self.body = body or {
            "status": "ready_for_final_gate_preflight",
            "blockers": [],
            "warnings": [],
            "strategy_planning_plan": {
                "places_order": False,
                "calls_order_lifecycle": False,
            },
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


def _write_inputs(tmp_path):
    post_submit = {
        "packet_id": "runtime-post-submit-finalize-auth-1",
        "authorization_id": "auth-1",
        "runtime_instance_id": "runtime-1",
        "status": "finalized_ready_for_next_attempt",
        "next_attempt_gate": {
            "status": "ready_for_fresh_signal",
            "runtime_instance_id": "runtime-1",
            "attempts_remaining": 2,
            "budget_remaining": "30",
            "active_positions_count": 0,
            "max_active_positions": 1,
            "requires_fresh_strategy_signal": True,
            "requires_fresh_authorization": True,
            "consumed_authorization_replay_only": True,
            "pre_submit_rehearsal_retry_allowed": False,
            "blockers": [],
            "warnings": [],
        },
        "consumed_authorization_replay_only": True,
        "old_authorization_submit_retry_allowed": False,
        "pre_submit_rehearsal_retry_allowed": False,
        "local_created_order_requirement_retired": True,
        "blockers": [],
        "warnings": [],
        "not_execution_authority": True,
        "runtime_state_mutated_by_payload": False,
        "execution_intent_created": False,
        "order_created": False,
        "order_cancelled": False,
        "position_closed": False,
        "exchange_called": False,
        "exchange_order_submitted": False,
        "order_lifecycle_called": False,
        "owner_bounded_execution_called": False,
        "withdrawal_or_transfer_created": False,
        "created_at_ms": 1781000000000,
    }
    signal = {
        "evaluation_id": "eval-1",
        "strategy_family_id": "CPM-001",
        "strategy_family_version_id": "CPM-001-v0",
        "symbol": "BNB/USDT:USDT",
        "timestamp_ms": 1781000000000,
        "primary_timeframe": "1h",
        "context_timeframes": ["4h"],
        "market_snapshot": {
            "symbol": "BNB/USDT:USDT",
            "timestamp_ms": 1781000000000,
            "source": "unit",
            "freshness": "fresh",
        },
        "account_facts_snapshot": {
            "source": "unit",
            "truth_level": "exchange_read",
            "timestamp_ms": 1781000000000,
            "freshness": "fresh",
        },
        "source": "unit_test",
        "freshness": "fresh",
    }
    post_path = tmp_path / "post-submit.json"
    signal_path = tmp_path / "signal.json"
    post_path.write_text(json.dumps(post_submit), encoding="utf-8")
    signal_path.write_text(json.dumps(signal), encoding="utf-8")
    return post_path, signal_path


def _args(tmp_path, **overrides):
    post_path, signal_path = _write_inputs(tmp_path)
    values = {
        "runtime_instance_id": "runtime-1",
        "post_submit_finalize_payload_json": str(post_path),
        "signal_input_json": str(signal_path),
        "env_file": None,
        "api_base": "http://unit",
        "context_id": "context-1",
        "expires_at_ms": None,
        "metadata_json": '{"owner":"unit"}',
    }
    values.update(overrides)
    return type("Args", (), values)()


def test_next_attempt_strategy_plan_api_flow_posts_payload_and_signal(tmp_path):
    client = _Client()

    artifact = runtime_next_attempt_strategy_plan_api_flow._build_artifact(
        _args(tmp_path),
        client=client,
    )

    assert artifact["status"] == "ready_for_final_gate_preflight"
    assert artifact["safety_invariants"]["exchange_write_called"] is False
    assert artifact["safety_invariants"]["order_lifecycle_called"] is False
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["method"] == "POST"
    assert call["path"] == (
        "/api/trading-console/strategy-runtimes/runtime-1/"
        "next-attempt-strategy-plans"
    )
    assert "post_submit_finalize_packet" not in call["body"]
    assert call["body"]["post_submit_finalize_payload"]["authorization_id"] == "auth-1"
    assert call["body"]["signal_input"]["evaluation_id"] == "eval-1"
    assert call["body"]["metadata"]["runtime_next_attempt_strategy_plan_api_flow"] is True
    assert call["body"]["metadata"]["owner"] == "unit"
    assert call["body"]["non_executing"] is True


def test_next_attempt_strategy_plan_api_flow_keeps_blocked_http_errors(tmp_path):
    artifact = runtime_next_attempt_strategy_plan_api_flow._build_artifact(
        _args(tmp_path),
        client=_Client(http_status=503, body={"detail": "unavailable"}),
    )

    assert artifact["status"] == "blocked"
    assert artifact["blocked_stage"] == "next_attempt_strategy_plan_api"
    assert "next_attempt_strategy_plan_api_http_503" in artifact["blockers"]
    assert artifact["safety_invariants"]["position_opened"] is False


def test_next_attempt_strategy_plan_api_flow_cli_stdout_is_json_only(
    monkeypatch,
    capsys,
):
    def fake_build_artifact(args):
        print("inner noisy api flow")
        return {"status": "waiting_for_signal", "ok": True}

    monkeypatch.setattr(
        runtime_next_attempt_strategy_plan_api_flow,
        "_build_artifact",
        fake_build_artifact,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "runtime_next_attempt_strategy_plan_api_flow.py",
            "--runtime-instance-id",
            "runtime-1",
            "--post-submit-finalize-payload-json",
            "post.json",
            "--signal-input-json",
            "signal.json",
        ],
    )

    assert runtime_next_attempt_strategy_plan_api_flow.main() == 0

    captured = capsys.readouterr()
    assert captured.out.startswith("{")
    assert "inner noisy api flow" not in captured.out
    assert "inner noisy api flow" in captured.err
