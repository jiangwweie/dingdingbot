from __future__ import annotations

from decimal import Decimal

from src.application.decision_trace import TraceEvent, TraceService


class _CaptureTraceSink:
    def __init__(self) -> None:
        self.events = []

    def emit(self, event: TraceEvent) -> None:
        self.events.append(event.model_dump(mode="json"))


def test_trace_sink_captures_valid_event_payload():
    sink = _CaptureTraceSink()
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

    assert len(sink.events) == 1
    payload = sink.events[0]
    assert payload["trace_id"] == "trace-1"
    assert payload["lifecycle_id"] == "lifecycle-1"
    assert payload["event_type"] == "risk.pre_order_check"
    assert payload["decision"] == "deny"
    assert payload["reason"] == "DAILY_LOSS_LIMIT"
    assert payload["metadata"]["daily_pnl"] == "12.5"
    assert payload["config_hash"] == "cfg-123"


def test_trace_service_emits_risk_decision():
    sink = _CaptureTraceSink()
    service = TraceService(sinks=[sink])

    event = service.emit_risk_decision(
        lifecycle_id="risk-lifecycle-1",
        decision="allow",
        reason=None,
        metadata={"symbol": "ETH/USDT:USDT"},
        config_hash="cfg-456",
    )

    assert event.trace_id
    payload = sink.events[0]
    assert payload["lifecycle_id"] == "risk-lifecycle-1"
    assert payload["decision"] == "allow"
    assert payload["metadata"]["symbol"] == "ETH/USDT:USDT"
    assert payload["config_hash"] == "cfg-456"
