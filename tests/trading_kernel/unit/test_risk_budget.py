from decimal import Decimal

import pytest

from src.trading_kernel.domain.directional_risk import (
    DirectionalControl,
    effective_directional_limit,
)
from src.trading_kernel.domain.risk_budget import RiskBudget, RiskBudgetChangeRequest


@pytest.mark.parametrize("r", ["0.020", "0.025", "0.030"])
def test_budget_links_all_limits_and_direction(r):
    budget = RiskBudget(baseline=r)
    assert budget.gross == Decimal(r) * 3
    assert budget.directional == Decimal(r) * 2
    assert budget.minimum == Decimal(r) / 2
    control = DirectionalControl(
        venue_id="v", account_id="a", version=1, view="bearish", effective_at_ms=1
    )
    assert effective_directional_limit(control, "long", budget.directional) == Decimal(
        r
    )
    assert (
        effective_directional_limit(control, "short", budget.directional)
        == Decimal(r) * 2
    )


@pytest.mark.parametrize("r", ["0.019", "0.031", "0.0205", "NaN", "Infinity", "-0.02"])
def test_outside_certified_budget_rejected(r):
    with pytest.raises(ValueError):
        RiskBudget(baseline=r)


def test_change_request_requires_identity_and_both_versions():
    with pytest.raises(ValueError):
        RiskBudgetChangeRequest(
            venue_id="v",
            account_id="a",
            owner_policy_id="policy-main",
            expected_policy_version=0,
            expected_directional_version=1,
            baseline="0.03",
            owner_identity="owner",
            reason="change",
            idempotency_key="k",
            requested_at_ms=1,
        )
