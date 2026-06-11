from __future__ import annotations

import json
import sys

from scripts import runtime_active_observation_monitor


class _FakeClient:
    def __init__(self, items):
        self.items = items
        self.calls = []

    def request_json(self, method, path, *, query=None, body=None):
        self.calls.append(
            {
                "method": method,
                "path": path,
                "query": query,
                "body": body,
            }
        )
        return {"http_status": 200, "body": self.items}


def _args(**overrides):
    values = {
        "env_file": None,
        "api_base": "http://unit",
        "source": "live_market",
        "include_exchange": False,
        "allow_prepare_records": False,
        "max_runtimes": 100,
        "max_cycles_per_runtime": 1,
        "interval_seconds": 0.0,
        "continue_on_blocked": False,
        "one_hour_limit": 25,
        "four_hour_limit": 25,
        "timeout_seconds": 10.0,
        "playbook_id": None,
        "output_dir": "output/unit-active-monitor",
        "output_json": None,
        "include_runtime_packets": False,
        "owner_operator_id": "owner",
        "owner_confirmation_reference": "owner-authorized-unit",
        "reason": "unit test",
    }
    values.update(overrides)
    return type("Args", (), values)()


def _runtime(runtime_id, *, status="active", symbol="AVAX/USDT:USDT", side="short"):
    return {
        "runtime_instance_id": runtime_id,
        "status": status,
        "symbol": symbol,
        "side": side,
        "strategy_family_id": "BTPC-001",
        "strategy_family_version_id": "BTPC-001-v0",
    }


def test_active_monitor_runs_only_active_runtimes_without_side_effects(tmp_path):
    client = _FakeClient(
        [
            _runtime("runtime-active-1"),
            _runtime("runtime-revoked", status="revoked"),
            _runtime("runtime-active-2", symbol="BNB/USDT:USDT", side="long"),
        ]
    )
    seen = []

    def builder(args):
        seen.append(
            {
                "runtime_instance_id": args.runtime_instance_id,
                "symbol": args.symbol,
                "side": args.side,
                "allow_prepare_records": args.allow_prepare_records,
                "four_hour_limit": args.four_hour_limit,
                "output_json": args.output_json,
            }
        )
        return {
            "status": "waiting_for_signal",
            "ready_for_prepare": False,
            "ready_for_final_gate_preflight": False,
            "blockers": ["strategy_signal_not_ready_for_shadow_candidate_prepare"],
            "warnings": [],
            "operator_command_plan": {"next_step": "wait"},
            "latest_packet": {
                "observation_payload": {
                    "signal_packet": {
                        "evaluation_result": {
                            "status": "observe_only",
                            "evaluator_id": "BTPC001PriceActionEvaluator",
                            "can_call_semantic_binding": False,
                            "semantics_binding_found": True,
                            "strategy_candidate_mode": (
                                "shadow_order_candidate_allowed"
                            ),
                            "output": {
                                "signal_type": "no_action",
                                "required_execution_mode": "observe_only",
                                "side": "none",
                                "reason_codes": [
                                    (
                                        "btpc_no_action_no_bear_pullback_"
                                        "continuation"
                                    )
                                ],
                                "human_summary": (
                                    "BTPC v0 did not confirm bear-trend "
                                    "pullback continuation."
                                ),
                                "confidence": "0.25",
                                "timestamp_ms": 1781197200000,
                                "data_quality": {"status": "ok"},
                                "signal_snapshot": {
                                    "context_tags": {
                                        "market_state": "TREND_DOWN",
                                        "entry_pattern": "none",
                                    }
                                },
                            },
                        }
                    }
                }
            },
            "safety_invariants": {
                "prepare_records_created": False,
                "exchange_write_called": False,
                "order_created": False,
                "order_lifecycle_called": False,
            },
        }

    packet = runtime_active_observation_monitor._build_packet(
        _args(output_dir=str(tmp_path)),
        client=client,
        monitor_builder=builder,
    )

    assert [item["runtime_instance_id"] for item in seen] == [
        "runtime-active-1",
        "runtime-active-2",
    ]
    assert {item["four_hour_limit"] for item in seen} == {25}
    assert packet["status"] == "waiting_for_signal"
    assert packet["active_runtime_count"] == 2
    assert packet["monitored_runtime_count"] == 2
    assert packet["safety_invariants"]["exchange_write_called"] is False
    assert packet["safety_invariants"]["order_lifecycle_called"] is False
    assert packet["operator_command_plan"]["places_order"] is False
    for summary in packet["runtime_summaries"]:
        report_path = summary["report_path"]
        with open(report_path, encoding="utf-8") as handle:
            report = json.load(handle)
        assert report["runtime_instance_id"] in {
            "runtime-active-1",
            "runtime-active-2",
        }
        assert report["safety_invariants"]["exchange_write_called"] is False
    signal_summary = packet["runtime_summaries"][0]["signal_summary"]
    assert signal_summary["evaluation_status"] == "observe_only"
    assert signal_summary["reason_codes"] == [
        "btpc_no_action_no_bear_pullback_continuation"
    ]
    assert signal_summary["human_summary"].startswith("BTPC v0")
    assert signal_summary["context_tags"]["market_state"] == "TREND_DOWN"


def test_active_monitor_allows_prepare_records_only_when_explicit():
    client = _FakeClient([_runtime("runtime-active-1")])

    def builder(args):
        assert args.allow_prepare_records is True
        return {
            "status": "ready_for_final_gate_preflight",
            "ready_for_prepare": False,
            "ready_for_final_gate_preflight": True,
            "blockers": [],
            "warnings": [],
            "operator_command_plan": {
                "prepared_authorization_id": "auth-1",
                "signal_input_json": "/tmp/signal.json",
            },
            "safety_invariants": {
                "prepare_records_created": True,
                "shadow_candidate_created": True,
                "runtime_execution_intent_draft_created": True,
                "recorded_execution_intent_created": True,
                "submit_authorization_created": True,
                "protection_plan_created": True,
                "executable_execution_intent_created": False,
                "exchange_write_called": False,
                "order_created": False,
                "order_lifecycle_called": False,
            },
        }

    packet = runtime_active_observation_monitor._build_packet(
        _args(allow_prepare_records=True),
        client=client,
        monitor_builder=builder,
    )

    assert packet["status"] == "ready_for_final_gate_preflight"
    assert packet["operator_command_plan"]["creates_shadow_candidate"] is True
    assert packet["operator_command_plan"]["creates_execution_intent"] is False
    assert packet["safety_invariants"]["prepare_records_created"] is True
    assert packet["safety_invariants"]["shadow_candidate_created"] is True
    assert packet["safety_invariants"]["recorded_execution_intent_created"] is True
    assert packet["safety_invariants"]["executable_execution_intent_created"] is False
    assert packet["safety_invariants"]["exchange_write_called"] is False
    assert packet["safety_invariants"]["order_created"] is False
    summary = packet["runtime_summaries"][0]
    assert summary["created_records"] == {
        "shadow_candidate_created": True,
        "runtime_execution_intent_draft_created": True,
        "recorded_execution_intent_created": True,
        "submit_authorization_created": True,
        "protection_plan_created": True,
        "executable_execution_intent_created": False,
    }
    assert summary["forbidden_effects"]["order_lifecycle_called"] is False


def test_active_monitor_handles_no_active_runtimes():
    packet = runtime_active_observation_monitor._build_packet(
        _args(),
        client=_FakeClient([_runtime("runtime-revoked", status="revoked")]),
        monitor_builder=lambda args: {"status": "waiting_for_signal"},
    )

    assert packet["status"] == "no_active_runtimes"
    assert packet["active_runtime_count"] == 0
    assert packet["monitored_runtime_count"] == 0
    assert packet["operator_command_plan"]["next_step"] == (
        "start_or_authorize_a_runtime_before_monitoring"
    )
    assert packet["safety_invariants"]["exchange_write_called"] is False


def test_active_monitor_cli_can_write_output_json(monkeypatch, capsys, tmp_path):
    output_path = tmp_path / "active-monitor.json"

    def fake_build_packet(args):
        return {
            "status": "waiting_for_signal",
            "active_runtime_count": 1,
            "safety_invariants": {"exchange_write_called": False},
        }

    monkeypatch.setattr(
        runtime_active_observation_monitor,
        "_build_packet",
        fake_build_packet,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "runtime_active_observation_monitor.py",
            "--output-json",
            str(output_path),
        ],
    )

    assert runtime_active_observation_monitor.main() == 0

    stdout_payload = json.loads(capsys.readouterr().out)
    file_payload = json.loads(output_path.read_text())
    assert file_payload == stdout_payload
    assert file_payload["status"] == "waiting_for_signal"
