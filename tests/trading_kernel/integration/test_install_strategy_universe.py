from __future__ import annotations

import importlib
import importlib.util
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from src.trading_kernel.domain.strategy_universe import build_strategy_universe


@pytest.mark.asyncio
async def test_install_strategy_universe_exposes_typed_application_boundary() -> None:
    """Catches an untyped request or an install use case that bypasses its port."""

    assert importlib.util.find_spec(
        "src.trading_kernel.application.install_strategy_universe"
    ) is not None
    module = importlib.import_module(
        "src.trading_kernel.application.install_strategy_universe"
    )
    request = module.UniverseInstallRequest(
        event_spec_id="event_spec:SOR-001:SOR-LONG:v2",
        runtime_profile_id="tiny-live-v1",
        owner_policy_id="policy-main",
        exchange_instrument_ids=(
            "binance-usdm:SOLUSDT:perpetual",
            "binance-usdm:BTCUSDT:perpetual",
        ),
        installed_at_ms=1_800_000_000_000,
    )
    expected = module.UniverseInstallResult(
        status=module.UniverseInstallStatus.INSTALLED,
        universe=build_strategy_universe(
            universe_version_id="universe:sor-long:v1",
            strategy_group_id="SOR-001",
            event_spec_id=request.event_spec_id,
            universe_version=1,
            exchange_instrument_ids=request.exchange_instrument_ids,
            installed_at_ms=request.installed_at_ms,
        ),
        lifecycle_state="warming",
        inserted_instrument_count=2,
        inserted_version_count=1,
        inserted_member_count=2,
        inserted_scope_count=2,
    )

    class _Repository:
        async def install(self, actual_request: object) -> object:
            assert actual_request is request
            return expected

    actual = await module.install_strategy_universe(
        SimpleNamespace(strategy_universes=_Repository()),
        request,
    )

    assert request.exchange_instrument_ids == (
        "binance-usdm:BTCUSDT:perpetual",
        "binance-usdm:SOLUSDT:perpetual",
    )
    assert actual == expected
    assert actual.total_inserted_count == 7
    with pytest.raises(ValidationError):
        module.UniverseInstallRequest(
            **request.model_dump(mode="python"),
            rank=1,
        )
