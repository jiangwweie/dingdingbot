"""Finite allowlist for strategy-trial controlled testnet carriers."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.application.strategy_trial_readiness import RiskCapProfile, StrategyProfile


class StrategyTrialControlledTestnetCarrier(BaseModel):
    model_config = ConfigDict(frozen=True)

    carrier_id: str
    strategy_profile: StrategyProfile
    risk_cap_profile: RiskCapProfile
    runtime_symbol: str
    runtime_symbol_key: str
    allowed_runtime_profiles: tuple[str, ...]
    required_market_symbols: tuple[str, ...]
    amount_max: Decimal = Field(gt=Decimal("0"))
    min_notional_default: Decimal = Field(gt=Decimal("0"))
    max_notional: Decimal = Field(gt=Decimal("0"))
    amount_step: Decimal | None = Field(default=None, gt=Decimal("0"))
    leverage: Literal[1] = 1
    testnet_rehearsal_enabled: Literal[True] = True
    live_ready: Literal[False] = False
    auto_execution_ready: Literal[False] = False
    no_auto_reentry: Literal[True] = True
    no_averaging_down: Literal[True] = True
    no_arbitrary_symbol: Literal[True] = True
    no_arbitrary_side: Literal[True] = True
    no_arbitrary_leverage: Literal[True] = True


def mi001_bnb_long_testnet_carrier() -> StrategyTrialControlledTestnetCarrier:
    strategy_profile = StrategyProfile(
        strategy_group="MI",
        strategy_id="MI-001",
        candidate_id="MI-001-BNB-LONG",
        symbol="BNBUSDT",
        side="long",
        execution_mode="owner_confirm_each_entry",
    )
    risk_cap_profile = RiskCapProfile(
        cap_profile_id="MI-001-BNB-LONG-controlled-testnet-carrier-cap-v0",
        profile_status="present",
        max_concurrent_position=1,
        max_daily_attempts=1,
        max_trial_attempts=1,
        max_notional_usdt="20",
        leverage="1x_testnet_fixed",
    )
    return StrategyTrialControlledTestnetCarrier(
        carrier_id="MI-001-BNB-LONG",
        strategy_profile=strategy_profile,
        risk_cap_profile=risk_cap_profile,
        runtime_symbol="BNB/USDT:USDT",
        runtime_symbol_key="bnb",
        allowed_runtime_profiles=(
            "strategy_trial_bnb_testnet_runtime",
            "brc_strategy_trial_bnb_testnet_runtime",
        ),
        required_market_symbols=("BNB/USDT:USDT",),
        amount_max=Decimal("0.01"),
        min_notional_default=Decimal("5"),
        max_notional=Decimal("20"),
        amount_step=Decimal("0.001"),
    )


def strategy_trial_controlled_testnet_carriers() -> dict[str, StrategyTrialControlledTestnetCarrier]:
    carrier = mi001_bnb_long_testnet_carrier()
    return {carrier.carrier_id: carrier}


def get_strategy_trial_controlled_testnet_carrier(
    carrier_id: str,
) -> StrategyTrialControlledTestnetCarrier | None:
    return strategy_trial_controlled_testnet_carriers().get(carrier_id)
