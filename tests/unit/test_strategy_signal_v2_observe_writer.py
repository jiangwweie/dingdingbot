from __future__ import annotations

from decimal import Decimal
from typing import Any

from src.application.strategy_signal_v2_observe_writer import (
    PatternStrategySignalObserveWriter,
)
from src.domain.models import Direction, FilterResult, KlineData, PatternResult, SignalAttempt


def _kline() -> KlineData:
    return KlineData(
        symbol="ETH/USDT:USDT",
        timeframe="4h",
        timestamp=1234567890,
        open=Decimal("100"),
        high=Decimal("110"),
        low=Decimal("95"),
        close=Decimal("108"),
        volume=Decimal("1000"),
    )


def _pattern() -> PatternResult:
    return PatternResult(
        strategy_name="pinbar",
        direction=Direction.LONG,
        score=Decimal("0.8"),
        details={"wick_ratio": 0.7},
    )


def _attempt(final_result: str, pattern: PatternResult | None = None) -> SignalAttempt:
    return SignalAttempt(
        strategy_name="pinbar",
        pattern=pattern,
        filter_results=[
            ("ema_trend", FilterResult(passed=True, reason="trend_match")),
        ] if pattern else [],
        final_result=final_result,
        kline_timestamp=1234567890,
    )


class _FailingAdapter:
    _adapter_version = "failing"

    def adapt(self, **kwargs):
        raise RuntimeError("adapter unavailable")


class _FailingSink:
    def write(self, snapshot):
        raise RuntimeError("disk unavailable")


class _CaptureObserveSink:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def write(self, snapshot):
        self.events.append(snapshot)


def test_signal_fired_attempt_with_pattern_captures_one_snapshot():
    sink = _CaptureObserveSink()
    writer = PatternStrategySignalObserveWriter(
        sink=sink,
    )

    writer.write_observations(
        kline=_kline(),
        attempts=[_attempt("SIGNAL_FIRED", _pattern())],
        source_context_id="ctx-fired",
    )

    payloads = sink.events
    assert len(payloads) == 1
    payload = payloads[0]
    assert payload["schema"] == "strategy_signal_v2"
    assert payload["schema_version"] == "v1"
    assert payload["observe_only"] is True
    assert payload["adapter_status"] == "ok"
    assert payload["attempt_context"]["final_result"] == "SIGNAL_FIRED"
    assert payload["attempt_context"]["kline_timestamp"] == 1234567890
    assert payload["adapter_version"] == "v1"
    assert payload["source_context_id"] == "ctx-fired"


def test_filtered_attempt_with_pattern_captures_one_snapshot():
    sink = _CaptureObserveSink()
    writer = PatternStrategySignalObserveWriter(
        sink=sink,
    )

    writer.write_observations(
        kline=_kline(),
        attempts=[_attempt("FILTERED", _pattern())],
    )

    payloads = sink.events
    assert len(payloads) == 1
    assert payloads[0]["attempt_context"]["final_result"] == "FILTERED"


def test_no_pattern_attempt_writes_nothing():
    sink = _CaptureObserveSink()
    writer = PatternStrategySignalObserveWriter(
        sink=sink,
    )

    writer.write_observations(
        kline=_kline(),
        attempts=[_attempt("NO_PATTERN", None)],
    )

    assert sink.events == []


def test_snapshot_includes_strategy_signal_v2_model_dump():
    sink = _CaptureObserveSink()
    writer = PatternStrategySignalObserveWriter(
        sink=sink,
    )

    writer.write_observations(
        kline=_kline(),
        attempts=[_attempt("SIGNAL_FIRED", _pattern())],
        adapter_version="v2",
    )

    snapshot = sink.events[0]
    signal = snapshot["strategy_signal_v2"]
    assert signal["strategy_id"] == "pinbar_v2"
    assert signal["strategy_family"] == "pattern"
    assert signal["entry_policy"]["kind"] == "market_after_confirmed_close"
    assert signal["lifecycle_exit_policy"]["kind"] == "none"
    assert signal["metadata"]["pattern_details"] == {"wick_ratio": 0.7}
    assert snapshot["adapter_version"] == "v2"


def test_adapter_failure_logs_warning_and_does_not_raise(caplog):
    sink = _CaptureObserveSink()
    writer = PatternStrategySignalObserveWriter(
        adapter=_FailingAdapter(),
        sink=sink,
    )

    writer.write_observations(
        kline=_kline(),
        attempts=[_attempt("SIGNAL_FIRED", _pattern())],
    )

    snapshot = sink.events[0]
    assert snapshot["adapter_status"] == "failed"
    assert "RuntimeError: adapter unavailable" in snapshot["error"]
    assert "StrategySignalV2 observe adapter failed" in caplog.text


def test_sink_write_failure_logs_warning_and_does_not_raise(caplog):
    writer = PatternStrategySignalObserveWriter(sink=_FailingSink())

    writer.write_observations(
        kline=_kline(),
        attempts=[_attempt("SIGNAL_FIRED", _pattern())],
    )

    assert "StrategySignalV2 observe sink write failed" in caplog.text


def test_writer_has_no_runtime_risk_or_execution_dependencies():
    writer = PatternStrategySignalObserveWriter()

    assert not hasattr(writer, "_risk_calculator")
    assert not hasattr(writer, "_execution_orchestrator")
    assert not hasattr(writer, "_order_strategy")
    assert not hasattr(writer, "_global_kill_switch")
    assert not hasattr(writer, "_owner_gate")
    assert not hasattr(writer, "_human_gate")
