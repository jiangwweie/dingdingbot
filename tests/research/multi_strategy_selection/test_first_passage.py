from decimal import Decimal

from research.multi_strategy_selection.first_passage import (
    PathBar,
    PathLabel,
    evaluate_signal_path,
)


def _bar(open_ms: int, high: str, low: str) -> PathBar:
    return PathBar(open_time_ms=open_ms, close_time_ms=open_ms + 899_999, high=Decimal(high), low=Decimal(low))


def test_long_and_short_signal_first_passage() -> None:
    long_result = evaluate_signal_path(
        side="long", anchor=Decimal(100), stop=Decimal(90), trigger_close_ms=999,
        bars_15m=(_bar(999, "111", "99"),), bars_1m_by_15m={},
    )
    short_result = evaluate_signal_path(
        side="short", anchor=Decimal(100), stop=Decimal(110), trigger_close_ms=999,
        bars_15m=(_bar(999, "101", "89"),), bars_1m_by_15m={},
    )
    assert long_result.label is PathLabel.SIGNAL_TP1_FIRST
    assert short_result.label is PathLabel.SIGNAL_TP1_FIRST


def test_trigger_bar_is_never_used_and_same_15m_uses_1m_order() -> None:
    result = evaluate_signal_path(
        side="long", anchor=Decimal(100), stop=Decimal(90), trigger_close_ms=999,
        bars_15m=(
            _bar(0, "120", "80"),
            _bar(1_000, "111", "89"),
        ),
        bars_1m_by_15m={1_000: (
            PathBar(open_time_ms=1_000, close_time_ms=60_999, high=Decimal(101), low=Decimal(89)),
            PathBar(open_time_ms=61_000, close_time_ms=120_999, high=Decimal(111), low=Decimal(99)),
        )},
    )
    assert result.label is PathLabel.SIGNAL_STOP_FIRST
    assert result.first_path_at_ms == 60_999


def test_same_1m_touch_remains_ambiguous() -> None:
    result = evaluate_signal_path(
        side="long", anchor=Decimal(100), stop=Decimal(90), trigger_close_ms=999,
        bars_15m=(_bar(1_000, "111", "89"),),
        bars_1m_by_15m={1_000: (
            PathBar(open_time_ms=1_000, close_time_ms=60_999, high=Decimal(111), low=Decimal(89)),
        )},
    )
    assert result.label is PathLabel.AMBIGUOUS
