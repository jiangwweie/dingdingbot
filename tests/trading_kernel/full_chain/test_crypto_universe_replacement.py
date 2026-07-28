from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from scripts.trading_kernel.certify_readonly import _certify
from src.trading_kernel.application.advance_strategy_universe import (
    UniverseActivationRequest,
    UniverseActivationStatus,
    advance_strategy_universe,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import (
    PostgresKernelUnitOfWork,
)
from tests.trading_kernel.integration.universe_activation_support import (
    NOW_MS,
    make_warming_ready,
    prepare_active_and_warming,
)
from tests.trading_kernel.integration.universe_activation_support import (
    activation_engine as _activation_engine,  # noqa: F401
)


@pytest.mark.asyncio
async def test_replacement_keeps_one_active_universe_and_readonly_bounded(
    _activation_engine: AsyncEngine,  # noqa: F811
) -> None:
    """Catches an unavailable window, dual active pool, or unbounded manifest."""

    old_version_id, new_version_id = await prepare_active_and_warming(
        _activation_engine
    )
    database_url = _activation_engine.url.render_as_string(hide_password=False)
    before = await _certify(database_url, require_flat=True)

    await make_warming_ready(
        _activation_engine,
        universe_version_id=new_version_id,
    )
    async with PostgresKernelUnitOfWork(_activation_engine) as uow:
        activated = await advance_strategy_universe(
            uow,
            UniverseActivationRequest(
                universe_version_id=new_version_id,
                attempted_at_ms=NOW_MS,
            ),
        )
    after = await _certify(database_url, require_flat=True)

    assert activated.status is UniverseActivationStatus.ACTIVATED
    assert activated.previous_universe_version_id == old_version_id
    assert before["status"] == "pass"
    assert before["strategy_universe"]["scope_lifecycle_counts"] == {
        "active": 2,
        "warming": 2,
        "retired": 0,
    }
    assert after["status"] == "pass"
    assert after["strategy_universe"]["current_count"] == 1
    assert after["strategy_universe"]["scope_lifecycle_counts"] == {
        "active": 2,
        "warming": 0,
        "retired": 2,
    }
    assert after["active_counts"] == {
        "tickets": 0,
        "commands": 0,
        "positions": 0,
        "incidents": 0,
    }
