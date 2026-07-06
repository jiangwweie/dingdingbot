from __future__ import annotations

from decimal import Decimal

import pytest

from src.application.config import ConfigRepository


@pytest.mark.asyncio
async def test_config_repository_backtest_configs_persist_via_kv_repository(tmp_path):
    repo = ConfigRepository()
    await repo.initialize(db_path=str(tmp_path / "config.db"))

    try:
        defaults = await repo.get_backtest_configs(profile_name="trial")
        assert defaults["slippage_rate"] == Decimal("0.001")

        saved = await repo.save_backtest_configs(
            {
                "slippage_rate": Decimal("0.002"),
                "funding_rate_enabled": False,
            },
            profile_name="trial",
            changed_by="test",
        )

        assert saved == 2
        persisted = await repo.get_backtest_configs(profile_name="trial")
        assert persisted["slippage_rate"] == Decimal("0.002")
        assert persisted["funding_rate_enabled"] is False
        assert persisted["fee_rate"] == Decimal("0.0004")
    finally:
        await repo.close()
