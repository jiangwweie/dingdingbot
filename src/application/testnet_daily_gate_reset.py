"""Guarded daily-gate reset planning for BNB strategy-trial testnet rehearsal."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

from src.application.capital_protection import (
    DAILY_RISK_STATS_SCOPE_KEY,
    resolve_daily_risk_stats_scope_key,
)


BNB_TESTNET_PROFILE = "strategy_trial_bnb_testnet_runtime"
BNB_TESTNET_CARRIER_ID = "MI-001-BNB-LONG"
BNB_TESTNET_SYMBOL = "BNB/USDT:USDT"


DailyGateScopeClassification = Literal[
    "strategy_trial_bnb_profile_counter",
    "global_live_or_unknown_counter",
    "unknown_unsafe_counter",
]


class DailyGateResetRefusal(ValueError):
    """Raised when a daily-gate reset would be broad, live, or ambiguous."""


@dataclass(frozen=True)
class DailyGateResetRequest:
    profile_name: str | None
    trading_env: str | None
    exchange_testnet: bool | None
    symbol: str | None
    carrier_id: str | None
    stats_date: date


@dataclass(frozen=True)
class DailyGateResetPlan:
    scope_key: str
    stats_date: date
    profile_name: str
    trading_env: Literal["testnet"]
    exchange_testnet: Literal[True]
    symbol: Literal["BNB/USDT:USDT"]
    carrier_id: Literal["MI-001-BNB-LONG"]
    scope_classification: DailyGateScopeClassification
    reset_trade_count_to: Literal[0] = 0
    reset_realized_pnl: Literal[False] = False
    live_ready: Literal[False] = False
    execution_permission_granted: Literal[False] = False
    order_permission_granted: Literal[False] = False


def build_bnb_testnet_daily_gate_reset_plan(
    request: DailyGateResetRequest,
) -> DailyGateResetPlan:
    """Build a narrow BNB testnet reset plan or refuse the reset.

    This is intentionally stricter than the runtime gate itself. It only permits
    the BNB strategy-trial testnet runtime profile and refuses any broad/default
    daily-risk scope.
    """

    profile_name = (request.profile_name or "").strip()
    trading_env = (request.trading_env or "").strip().lower()
    symbol = (request.symbol or "").strip()
    carrier_id = (request.carrier_id or "").strip()

    if trading_env == "live":
        raise DailyGateResetRefusal("refuse_live_trading_env")
    if trading_env != "testnet":
        raise DailyGateResetRefusal("refuse_non_testnet_trading_env")
    if request.exchange_testnet is not True:
        raise DailyGateResetRefusal("refuse_exchange_testnet_false_or_unknown")
    if not profile_name:
        raise DailyGateResetRefusal("refuse_missing_profile")
    if profile_name != BNB_TESTNET_PROFILE:
        raise DailyGateResetRefusal("refuse_unapproved_profile")
    if symbol != BNB_TESTNET_SYMBOL:
        raise DailyGateResetRefusal("refuse_unapproved_symbol")
    if carrier_id != BNB_TESTNET_CARRIER_ID:
        raise DailyGateResetRefusal("refuse_unapproved_carrier")

    scope_key = resolve_daily_risk_stats_scope_key(
        profile_name=profile_name,
        trading_env=trading_env,
        exchange_testnet=request.exchange_testnet,
    )
    if scope_key == DAILY_RISK_STATS_SCOPE_KEY or not scope_key.startswith("runtime_profile:"):
        raise DailyGateResetRefusal("refuse_broad_or_global_daily_risk_scope")

    return DailyGateResetPlan(
        scope_key=scope_key,
        stats_date=request.stats_date,
        profile_name=profile_name,
        trading_env="testnet",
        exchange_testnet=True,
        symbol=BNB_TESTNET_SYMBOL,
        carrier_id=BNB_TESTNET_CARRIER_ID,
        scope_classification="strategy_trial_bnb_profile_counter",
    )
