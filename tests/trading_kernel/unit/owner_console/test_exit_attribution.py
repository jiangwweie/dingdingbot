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
        ("owner_flatten_all:authorization:1", "Owner 全部持仓受控平仓"),
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

    assert attribution.label == "退出原因未识别"


def test_controlled_exit_classification_uses_the_same_canonical_codes() -> None:
    assert is_controlled_exit("owner_flatten_all:authorization:1") is True
    assert is_controlled_exit("deployment_drain:release:1") is True
    assert is_controlled_exit("initial_stop_triggered") is False


def test_exit_breakdown_groups_authorizations_without_losing_raw_reason() -> None:
    from src.trading_kernel.application.owner_console.exit_attribution import (
        exit_reason_group,
    )
    assert exit_reason_group("owner_flatten_all:authorization:1") == exit_reason_group("owner_flatten_all:authorization:2") == "owner_flatten_all"
    assert canonical_exit_attribution("owner_flatten_all:authorization:1").code == "owner_flatten_all:authorization:1"
