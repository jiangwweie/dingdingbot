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


@pytest.mark.asyncio
async def test_config_repository_import_from_yaml_imports_explicit_kv_bundle(tmp_path):
    repo = ConfigRepository()
    await repo.initialize(db_path=str(tmp_path / "config.db"))
    yaml_path = tmp_path / "kv-config.yaml"
    yaml_path.write_text(
        """
profile_name: trial
config_entries:
  custom.feature_enabled: true
backtest:
  initial_balance: !decimal "2500"
  fee_rate: !decimal "0.0007"
""".lstrip(),
        encoding="utf-8",
    )

    try:
        imported = await repo.import_from_yaml(str(yaml_path), changed_by="test")

        assert imported["profile_name"] == "trial"
        backtest = await repo.get_backtest_configs(profile_name="trial")
        assert backtest["initial_balance"] == Decimal("2500")
        assert backtest["fee_rate"] == Decimal("0.0007")

        config_entry_repo = await repo._ensure_config_entry_repository()
        custom_entries = await config_entry_repo.get_entries_by_prefix("custom")
        assert custom_entries["custom.feature_enabled"] is True
    finally:
        await repo.close()


@pytest.mark.asyncio
async def test_config_repository_import_from_yaml_rejects_implicit_runtime_table_import(tmp_path):
    repo = ConfigRepository()
    await repo.initialize(db_path=str(tmp_path / "config.db"))
    yaml_path = tmp_path / "runtime-config.yaml"
    yaml_path.write_text(
        """
risk:
  max_leverage: 3
system:
  signal_cooldown_seconds: 600
""".lstrip(),
        encoding="utf-8",
    )

    try:
        with pytest.raises(ValueError, match="explicit KV sections"):
            await repo.import_from_yaml(str(yaml_path), changed_by="test")
    finally:
        await repo.close()
