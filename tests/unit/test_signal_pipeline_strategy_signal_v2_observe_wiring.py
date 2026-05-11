from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from src.application.signal_pipeline import SignalPipeline
from src.domain.models import Direction, KlineData, PatternResult, SignalAttempt


class _AsyncLock:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeQueue:
    def __init__(self) -> None:
        self.items = []

    def put_nowait(self, item) -> None:
        self.items.append(item)


class _FakeRepository:
    def __init__(self) -> None:
        self.saved_signals = []
        self.superseded = []

    async def save_signal(self, signal, signal_id, status):
        self.saved_signals.append((signal, signal_id, status))

    async def update_superseded_by(self, superseded_signal_id, signal_id):
        self.superseded.append((superseded_signal_id, signal_id))


class _FakeStatusTracker:
    def __init__(self) -> None:
        self.updated = []

    async def track_signal(self, signal):
        return "signal-1"

    async def update_status(self, signal_id, status):
        self.updated.append((signal_id, status))


class _FakeNotificationService:
    def __init__(self) -> None:
        self.sent = []

    async def send_signal(self, signal, **kwargs):
        self.sent.append((signal, kwargs))


class _FakeObserveWriter:
    def __init__(self, *, fail: bool = False, mutate: bool = False) -> None:
        self.fail = fail
        self.mutate = mutate
        self.calls = []
        self.snapshots = []

    def write_observations(self, *, kline, attempts, source_context_id=None):
        self.calls.append(
            {
                "kline": kline,
                "attempts": attempts,
                "source_context_id": source_context_id,
            }
        )
        if self.fail:
            raise RuntimeError("observe writer unavailable")
        if self.mutate and attempts:
            attempts[0].final_result = "MUTATED_BY_WRITER"
        for attempt in attempts:
            if attempt.pattern is not None and attempt.final_result in {"SIGNAL_FIRED", "FILTERED"}:
                self.snapshots.append((attempt.strategy_name, attempt.final_result))


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


def _pattern(direction: Direction = Direction.LONG) -> PatternResult:
    return PatternResult(
        strategy_name="pinbar",
        direction=direction,
        score=Decimal("0.8"),
        details={"wick_ratio": 0.7},
    )


def _attempt(final_result: str, pattern: PatternResult | None) -> SignalAttempt:
    return SignalAttempt(
        strategy_name="pinbar",
        pattern=pattern,
        filter_results=[],
        final_result=final_result,
        kline_timestamp=1234567890,
    )


def _pipeline(
    attempts,
    *,
    observe_writer=None,
    repository=None,
    queue=None,
    allowed_directions=None,
):
    pipeline = object.__new__(SignalPipeline)
    pipeline._repository = repository
    pipeline._strategy_signal_v2_observe_writer = observe_writer
    pipeline._runtime_allowed_directions = set(allowed_directions or [])
    pipeline._signal_executor = None
    pipeline._cooldown_seconds = 0
    pipeline._signal_cooldown_cache = {}
    pipeline._signal_cache = {}
    pipeline._status_tracker = _FakeStatusTracker()
    pipeline._notification_service = _FakeNotificationService()
    pipeline._ensure_flush_worker = lambda: None
    pipeline._get_runner_lock = lambda: _AsyncLock()
    pipeline._store_kline = lambda kline: None
    pipeline._run_strategy = lambda kline: attempts
    pipeline._get_attempts_queue = lambda: queue

    calls = SimpleNamespace(risk=0, executor=0)

    async def calculate_risk(kline, direction, attempt, strategy_name="unknown", score=0.0):
        calls.risk += 1
        return SimpleNamespace(strategy_name=strategy_name, direction=direction, score=score)

    async def check_cover(kline, attempt, score):
        return False, None, None

    async def check_opposing_signal(kline, attempt):
        return None

    async def signal_executor(signal, strategy):
        calls.executor += 1

    pipeline._calculate_risk = calculate_risk
    pipeline._check_cover = check_cover
    pipeline._check_opposing_signal = check_opposing_signal
    pipeline._build_execution_strategy = lambda signal: SimpleNamespace(name="strategy")
    pipeline._signal_executor = signal_executor
    return pipeline, calls


@pytest.mark.asyncio
async def test_observe_writer_none_preserves_signal_fired_flow():
    attempts = [_attempt("SIGNAL_FIRED", _pattern(Direction.LONG))]
    pipeline, calls = _pipeline(attempts, observe_writer=None)

    await pipeline.process_kline(_kline())

    assert calls.risk == 1
    assert calls.executor == 1
    assert attempts[0].final_result == "SIGNAL_FIRED"


@pytest.mark.asyncio
async def test_observe_writer_called_after_runtime_direction_policy():
    attempts = [_attempt("SIGNAL_FIRED", _pattern(Direction.SHORT))]
    writer = _FakeObserveWriter()
    queue = _FakeQueue()
    pipeline, calls = _pipeline(
        attempts,
        observe_writer=writer,
        repository=_FakeRepository(),
        queue=queue,
        allowed_directions=[Direction.LONG],
    )

    await pipeline.process_kline(_kline())

    assert len(writer.calls) == 1
    observed_attempt = writer.calls[0]["attempts"][0]
    assert observed_attempt.final_result == "FILTERED"
    assert observed_attempt.filter_results[-1][0] == "runtime_direction_policy"
    assert writer.snapshots == [("pinbar", "FILTERED")]
    assert len(queue.items) == 1
    assert calls.risk == 0
    assert calls.executor == 0


@pytest.mark.asyncio
async def test_writer_failure_does_not_block_persistence_risk_or_execution(caplog, monkeypatch):
    from src.application.performance_tracker import PerformanceTracker

    async def check_pending_signals(self, kline, repository):
        return None

    monkeypatch.setattr(PerformanceTracker, "check_pending_signals", check_pending_signals)
    attempts = [_attempt("SIGNAL_FIRED", _pattern(Direction.LONG))]
    queue = _FakeQueue()
    pipeline, calls = _pipeline(
        attempts,
        observe_writer=_FakeObserveWriter(fail=True),
        repository=_FakeRepository(),
        queue=queue,
    )

    await pipeline.process_kline(_kline())

    assert "StrategySignalV2 observe writer failed" in caplog.text
    assert len(queue.items) == 1
    assert calls.risk == 1
    assert calls.executor == 1


@pytest.mark.asyncio
async def test_filtered_attempt_observed_but_not_executed(monkeypatch):
    from src.application.performance_tracker import PerformanceTracker

    async def check_pending_signals(self, kline, repository):
        return None

    monkeypatch.setattr(PerformanceTracker, "check_pending_signals", check_pending_signals)
    attempts = [_attempt("FILTERED", _pattern(Direction.LONG))]
    writer = _FakeObserveWriter()
    queue = _FakeQueue()
    pipeline, calls = _pipeline(
        attempts,
        observe_writer=writer,
        repository=_FakeRepository(),
        queue=queue,
    )

    await pipeline.process_kline(_kline())

    assert writer.snapshots == [("pinbar", "FILTERED")]
    assert len(queue.items) == 1
    assert calls.risk == 0
    assert calls.executor == 0


@pytest.mark.asyncio
async def test_no_pattern_produces_no_observe_snapshot():
    attempts = [_attempt("NO_PATTERN", None)]
    writer = _FakeObserveWriter()
    pipeline, calls = _pipeline(attempts, observe_writer=writer)

    await pipeline.process_kline(_kline())

    assert len(writer.calls) == 1
    assert writer.snapshots == []
    assert calls.risk == 0
    assert calls.executor == 0


@pytest.mark.asyncio
async def test_writer_cannot_mutate_pipeline_attempts_key_fields():
    attempts = [_attempt("SIGNAL_FIRED", _pattern(Direction.LONG))]
    writer = _FakeObserveWriter(mutate=True)
    pipeline, calls = _pipeline(attempts, observe_writer=writer)

    await pipeline.process_kline(_kline())

    assert writer.calls[0]["attempts"][0].final_result == "MUTATED_BY_WRITER"
    assert attempts[0].final_result == "SIGNAL_FIRED"
    assert attempts[0].pattern.direction == Direction.LONG
    assert calls.risk == 1
    assert calls.executor == 1
