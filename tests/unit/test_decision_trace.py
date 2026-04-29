from __future__ import annotations

import json
from decimal import Decimal

from src.application.decision_trace import TraceEvent, TraceService
from src.infrastructure.jsonl_trace_sink import JsonlTraceSink


def test_jsonl_trace_sink_writes_valid_jsonl(tmp_path):
    path = tmp_path / "runtime" / "risk_decision.jsonl"
    sink = JsonlTraceSink(path)
    event = TraceEvent(
        trace_id="trace-1",
        lifecycle_id="lifecycle-1",
        event_type="risk.pre_order_check",
        decision="deny",
        reason="DAILY_LOSS_LIMIT",
        metadata={"daily_pnl": Decimal("12.5")},
        config_hash="cfg-123",
    )

    sink.emit(event)

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1

    payload = json.loads(lines[0])
    assert payload["trace_id"] == "trace-1"
    assert payload["lifecycle_id"] == "lifecycle-1"
    assert payload["event_type"] == "risk.pre_order_check"
    assert payload["decision"] == "deny"
    assert payload["reason"] == "DAILY_LOSS_LIMIT"
    assert payload["metadata"]["daily_pnl"] == "12.5"
    assert payload["config_hash"] == "cfg-123"


def test_trace_service_emits_risk_decision(tmp_path):
    path = tmp_path / "runtime" / "risk_decision.jsonl"
    service = TraceService(sinks=[JsonlTraceSink(path)])

    event = service.emit_risk_decision(
        lifecycle_id="risk-lifecycle-1",
        decision="allow",
        reason=None,
        metadata={"symbol": "ETH/USDT:USDT"},
        config_hash="cfg-456",
    )

    assert event.trace_id
    payload = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert payload["lifecycle_id"] == "risk-lifecycle-1"
    assert payload["decision"] == "allow"
    assert payload["metadata"]["symbol"] == "ETH/USDT:USDT"
    assert payload["config_hash"] == "cfg-456"
