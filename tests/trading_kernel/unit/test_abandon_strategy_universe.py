from __future__ import annotations

import pytest

from src.trading_kernel.application.abandon_strategy_universe import (
    AbandonStrategyUniverseRequest,
)


def test_abandon_request_requires_exact_warming_identity_and_stable_reason() -> None:
    request = AbandonStrategyUniverseRequest(
        universe_version_id="universe:mpg:v1",
        reason_code="market_identity_conflict",
        attempted_at_ms=1_800_000_000_000,
    )

    assert request.universe_version_id == "universe:mpg:v1"
    assert request.reason_code == "market_identity_conflict"

    with pytest.raises(ValueError):
        AbandonStrategyUniverseRequest(
            universe_version_id=" ",
            reason_code="market identity conflict",
            attempted_at_ms=1,
        )
