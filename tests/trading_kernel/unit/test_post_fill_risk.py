from __future__ import annotations

from decimal import Decimal

import pytest

from src.trading_kernel.domain.post_fill_risk import (
    PostFillDisposition,
    PostFillRiskRequest,
    PostFillRiskStatus,
    assess_post_fill_risk,
)


def _request(**changes: object) -> PostFillRiskRequest:
    payload: dict[str, object] = {
        "position_side": "long",
        "filled_quantity": Decimal("0.001"),
        "average_fill_price": Decimal("60000"),
        "initial_stop_price": Decimal("57000"),
        "planned_stop_risk_budget": Decimal("3.00"),
        "post_fill_stop_risk_limit": Decimal("3.30"),
        "current_liquidation_price": Decimal("50000"),
        "min_liquidation_distance_to_stop_distance_ratio": Decimal("2.0"),
    }
    payload.update(changes)
    return PostFillRiskRequest.model_validate(payload)


@pytest.mark.parametrize(
    ("actual_stop_risk", "expected"),
    [
        (Decimal("3.00"), PostFillRiskStatus.WITHIN_BUDGET),
        (Decimal("3.30"), PostFillRiskStatus.TOLERATED_OVERRUN),
        (Decimal("3.300000000000000001"), PostFillRiskStatus.HARD_OVERRUN),
    ],
)
def test_post_fill_risk_uses_exact_frozen_limit(
    actual_stop_risk: Decimal,
    expected: PostFillRiskStatus,
) -> None:
    decision = assess_post_fill_risk(
        _request(initial_stop_price=Decimal("60000") - actual_stop_risk * 1000)
    )

    assert decision.actual_stop_risk == actual_stop_risk
    assert decision.status is expected


def test_wrong_side_stop_requests_immediate_flatten() -> None:
    decision = assess_post_fill_risk(_request(initial_stop_price=Decimal("60001")))

    assert decision.status is PostFillRiskStatus.PROTECTION_DIRECTION_INVALID
    assert decision.disposition is PostFillDisposition.FLATTEN_IMMEDIATELY


@pytest.mark.parametrize(
    "liquidation_price",
    [None, Decimal("58000")],
)
def test_missing_or_degraded_liquidation_evidence_requires_protect_then_flatten(
    liquidation_price: Decimal | None,
) -> None:
    decision = assess_post_fill_risk(
        _request(current_liquidation_price=liquidation_price)
    )

    assert decision.status is PostFillRiskStatus.LIQUIDATION_SAFETY_DEGRADED
    assert decision.disposition is PostFillDisposition.FLATTEN_AFTER_PROTECTION


def test_hard_risk_overrun_requires_protect_then_flatten() -> None:
    decision = assess_post_fill_risk(
        _request(initial_stop_price=Decimal("56699.999999999999999"))
    )

    assert decision.status is PostFillRiskStatus.HARD_OVERRUN
    assert decision.disposition is PostFillDisposition.FLATTEN_AFTER_PROTECTION


def test_liquidation_evidence_uses_stop_to_liquidation_distance() -> None:
    decision = assess_post_fill_risk(_request())

    assert decision.actual_liquidation_distance == Decimal("7000")
    assert decision.actual_liquidation_distance_to_stop_distance_ratio == (
        Decimal(7) / Decimal(3)
    )
