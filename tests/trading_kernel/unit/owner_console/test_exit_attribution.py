from __future__ import annotations

import pytest

from src.trading_kernel.application.owner_console.exit_attribution import (
    canonical_exit_attribution,
    is_controlled_exit,
)


@pytest.mark.parametrize(
    ("code", "label"),
    (
        ("initial_stop_triggered", "初始止损触发"),
        ("failed_breakout_reclaimed", "假突破回收退出"),
        ("time_stop_hit", "持仓时间到期退出"),
        ("owner_flatten_all:authorization:1", "Owner 手动平仓"),
        ("deployment_drain:release:1", "部署前安全退出"),
        ("external_flat_exit_fills_unavailable", "外部平仓已确认，成交明细不可得"),
    ),
)
def test_canonical_exit_attribution_maps_persisted_reason_codes(
    code: str,
    label: str,
) -> None:
    attribution = canonical_exit_attribution(code)

    assert attribution.code == code
    assert attribution.label == label


def test_unknown_persisted_exit_code_remains_readable_without_guessing() -> None:
    attribution = canonical_exit_attribution("venue_truth_timeout")

    assert attribution.label == "系统请求退出（venue_truth_timeout）"


def test_controlled_exit_classification_uses_the_same_canonical_codes() -> None:
    assert is_controlled_exit("owner_flatten_all:authorization:1") is True
    assert is_controlled_exit("deployment_drain:release:1") is True
    assert is_controlled_exit("initial_stop_triggered") is False
