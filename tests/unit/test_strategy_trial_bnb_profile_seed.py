from __future__ import annotations

import pytest

from scripts.seed_strategy_trial_bnb_profile import (
    BNB_STRATEGY_TRIAL_PROFILE,
    PROFILE_NAME,
)
from src.application.runtime_config import RuntimeConfigResolver
from src.infrastructure.runtime_profile_repository import RuntimeProfile


class InMemoryRuntimeProfileRepository:
    def __init__(self, profile: RuntimeProfile) -> None:
        self.profile = profile

    async def get_profile(self, name: str):
        if name == self.profile.name:
            return self.profile
        return None


@pytest.mark.asyncio
async def test_bnb_strategy_trial_profile_resolves_to_testnet_bnb_only_scope():
    repo = InMemoryRuntimeProfileRepository(
        RuntimeProfile(
            name=PROFILE_NAME,
            profile_payload=BNB_STRATEGY_TRIAL_PROFILE,
            description="test",
            is_active=False,
            is_readonly=True,
            version=1,
        )
    )
    env = {
        "PG_DATABASE_URL": "postgresql://user:pass@localhost:5432/test",
        "CORE_EXECUTION_INTENT_BACKEND": "postgres",
        "CORE_ORDER_BACKEND": "postgres",
        "CORE_POSITION_BACKEND": "postgres",
        "TRADING_ENV": "testnet",
        "EXCHANGE_NAME": "binance",
        "EXCHANGE_TESTNET": "true",
        "BRC_EXECUTION_PERMISSION_MAX": "intent_recording",
        "EXCHANGE_API_KEY": "x" * 64,
        "EXCHANGE_API_SECRET": "y" * 64,
        "FEISHU_WEBHOOK_URL": "https://example.invalid/webhook",
        "BACKEND_PORT": "8000",
    }

    resolved = await RuntimeConfigResolver(repo, env=env).resolve(PROFILE_NAME)

    assert resolved.profile_name == "strategy_trial_bnb_testnet_runtime"
    assert resolved.environment.trading_env == "testnet"
    assert resolved.environment.exchange_testnet is True
    assert resolved.market.primary_symbol == "BNB/USDT:USDT"
    assert resolved.market.symbols == ["BNB/USDT:USDT"]
    assert resolved.risk.max_leverage == 1
    assert resolved.risk.max_total_exposure == 10
    assert resolved.risk.daily_max_trades == 1


def test_bnb_strategy_trial_profile_has_no_order_permission_metadata():
    non_permissions = BNB_STRATEGY_TRIAL_PROFILE["brc"]["non_permissions"]

    assert BNB_STRATEGY_TRIAL_PROFILE["brc"]["carrier_id"] == "MI-001-BNB-LONG"
    assert BNB_STRATEGY_TRIAL_PROFILE["brc"]["symbol_sequence"] == ["BNB/USDT:USDT"]
    assert non_permissions["live_ready"] is False
    assert non_permissions["auto_execution_ready"] is False
    assert non_permissions["no_arbitrary_symbol"] is True
    assert non_permissions["no_arbitrary_side"] is True
    assert non_permissions["no_arbitrary_leverage"] is True
