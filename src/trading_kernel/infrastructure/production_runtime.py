"""Exact production factories for the Binance USD-M trading-kernel runtime."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
import math
import os
import time
from typing import Literal

import ccxt.async_support as ccxt_async  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, SecretStr, field_validator

from src.trading_kernel.domain.strategy_registry import registered_strategy_contracts
from src.trading_kernel.infrastructure.binance_public_market_source import (
    CcxtBinancePublicMarketSource,
)
from src.trading_kernel.infrastructure.venue_adapter import CcxtVenueAdapter


BINANCE_USDM_VENUE_ID: Literal["binance-usdm"] = "binance-usdm"
BINANCE_USDM_POSITION_MODE: Literal["independent_sides"] = "independent_sides"
LIVE_ENVIRONMENT: Literal["live"] = "live"
_EXPECTED_UNIQUE_INSTRUMENTS = 6


class ProductionRuntimeSettings(BaseModel):
    """Masked, exact identity and credential inputs for the live venue adapter."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    environment: Literal["live"]
    venue_id: Literal["binance-usdm"]
    account_id: str
    account_position_mode: Literal["independent_sides"]
    api_key: SecretStr
    api_secret: SecretStr
    timeout_seconds: float
    exit_taker_fee_rate: Decimal

    @field_validator("account_id", mode="before")
    @classmethod
    def _require_account_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("account identity must be non-blank")
        return normalized

    @field_validator("api_key", "api_secret", mode="before")
    @classmethod
    def _require_credential(cls, value: object) -> object:
        if isinstance(value, SecretStr):
            normalized = value.get_secret_value().strip()
        else:
            normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("production venue credential must be non-blank")
        return normalized

    @field_validator("timeout_seconds")
    @classmethod
    def _require_timeout(cls, value: float) -> float:
        if not math.isfinite(value) or value <= 0:
            raise ValueError("production venue timeout must be positive and finite")
        return value

    @field_validator("exit_taker_fee_rate")
    @classmethod
    def _require_fee_rate(cls, value: Decimal) -> Decimal:
        if not Decimal("0") <= value < Decimal("1"):
            raise ValueError("exit taker fee rate must be in [0, 1)")
        return value

    @classmethod
    def from_environment(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> "ProductionRuntimeSettings":
        values = os.environ if environ is None else environ
        identity = _read_exact_identity(values, require_account=True)
        return cls(
            environment=LIVE_ENVIRONMENT,
            venue_id=BINANCE_USDM_VENUE_ID,
            account_id=identity.account_id,
            account_position_mode=BINANCE_USDM_POSITION_MODE,
            api_key=SecretStr(_required(values, "TRADING_KERNEL_API_KEY")),
            api_secret=SecretStr(_required(values, "TRADING_KERNEL_API_SECRET")),
            timeout_seconds=_timeout_seconds(values),
            exit_taker_fee_rate=_decimal_environment(
                values,
                "TRADING_KERNEL_EXIT_TAKER_FEE_RATE",
            ),
        )


class _ProductionIdentity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    account_id: str = ""


def build_binance_usdm_market_source() -> CcxtBinancePublicMarketSource:
    """Build the credential-free public closed-candle source."""

    values = os.environ
    _read_exact_identity(values, require_account=False)
    timeout_seconds = _timeout_seconds(values)
    exchange = ccxt_async.binanceusdm(
        {
            "enableRateLimit": True,
            "timeout": _timeout_ms(timeout_seconds),
            "options": {
                "defaultType": "future",
                "adjustForTimeDifference": True,
            },
        }
    )
    return CcxtBinancePublicMarketSource(
        exchange=exchange,
        venue_symbols=_canonical_venue_symbols(),
        timeout_seconds=timeout_seconds,
    )


def build_binance_usdm_venue_adapter() -> CcxtVenueAdapter:
    """Build the sole authenticated Binance USD-M venue mutation boundary."""

    settings = ProductionRuntimeSettings.from_environment()
    exchange = ccxt_async.binanceusdm(
        {
            "apiKey": settings.api_key.get_secret_value(),
            "secret": settings.api_secret.get_secret_value(),
            "enableRateLimit": True,
            "timeout": _timeout_ms(settings.timeout_seconds),
            "options": {
                "defaultType": "future",
                "adjustForTimeDifference": True,
                "warnOnFetchOpenOrdersWithoutSymbol": False,
            },
        }
    )
    venue_symbols = _canonical_venue_symbols()
    instrument_keys = tuple(
        (settings.venue_id, exchange_instrument_id)
        for exchange_instrument_id in venue_symbols
    )
    return CcxtVenueAdapter(
        exchanges={(settings.venue_id, settings.account_id): exchange},
        venue_symbols={
            (settings.venue_id, exchange_instrument_id): venue_symbol
            for exchange_instrument_id, venue_symbol in venue_symbols.items()
        },
        settlement_assets={key: "USDT" for key in instrument_keys},
        taker_fee_rates={
            key: settings.exit_taker_fee_rate for key in instrument_keys
        },
        clock_ms=lambda: int(time.time() * 1_000),
    )


def canonical_binance_usdm_instruments() -> tuple[str, ...]:
    """Return the exact sorted canonical instrument identities used in production."""

    return tuple(_canonical_venue_symbols())


def _read_exact_identity(
    values: Mapping[str, str],
    *,
    require_account: bool,
) -> _ProductionIdentity:
    environment = _required(values, "TRADING_KERNEL_ENVIRONMENT")
    if environment != LIVE_ENVIRONMENT:
        raise ValueError("production environment identity must be live")
    venue_id = _required(values, "TRADING_KERNEL_VENUE_ID")
    if venue_id != BINANCE_USDM_VENUE_ID:
        raise ValueError("production venue identity must be binance-usdm")
    position_mode = _required(values, "TRADING_KERNEL_ACCOUNT_POSITION_MODE")
    if position_mode != BINANCE_USDM_POSITION_MODE:
        raise ValueError(
            "production account position mode identity must be independent_sides"
        )
    account_id = (
        _required(values, "TRADING_KERNEL_ACCOUNT_ID") if require_account else ""
    )
    return _ProductionIdentity(account_id=account_id)


def _canonical_venue_symbols() -> dict[str, str]:
    by_instrument: dict[str, str] = {}
    for contract in registered_strategy_contracts():
        for instrument in contract.candidate_instruments:
            venue_symbol = instrument.venue_symbol
            if not venue_symbol.endswith("USDT") or len(venue_symbol) <= 4:
                raise RuntimeError("Registry contains a non-USDT production instrument")
            ccxt_symbol = f"{venue_symbol[:-4]}/USDT:USDT"
            existing = by_instrument.get(instrument.exchange_instrument_id)
            if existing is not None and existing != ccxt_symbol:
                raise RuntimeError("Registry contains contradictory venue symbol mapping")
            by_instrument[instrument.exchange_instrument_id] = ccxt_symbol
    if len(by_instrument) != _EXPECTED_UNIQUE_INSTRUMENTS:
        raise RuntimeError("production Registry must contain exactly six instruments")
    return dict(sorted(by_instrument.items()))


def _required(values: Mapping[str, str], key: str) -> str:
    normalized = str(values.get(key) or "").strip()
    if not normalized:
        raise ValueError(f"{key} is required")
    return normalized


def _timeout_seconds(values: Mapping[str, str]) -> float:
    raw = _required(values, "TRADING_KERNEL_TIMEOUT_SECONDS")
    try:
        timeout = float(raw)
    except ValueError as exc:
        raise ValueError("TRADING_KERNEL_TIMEOUT_SECONDS must be numeric") from exc
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("TRADING_KERNEL_TIMEOUT_SECONDS must be positive and finite")
    return timeout


def _timeout_ms(timeout_seconds: float) -> int:
    return max(1, int(timeout_seconds * 1_000))


def _decimal_environment(values: Mapping[str, str], key: str) -> Decimal:
    raw = _required(values, key)
    try:
        return Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError(f"{key} must be a decimal") from exc
