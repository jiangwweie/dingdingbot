"""Read-only Binance USDT futures account facts source for trial readiness.

The source intentionally exposes only account balance reads. It is not an
exchange gateway, does not carry order methods, and does not mutate account or
runtime state.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Optional, Protocol

from src.application.trial_readiness_account_facts import (
    AccountFactsFreshnessStatus,
    AccountFactsReconciliationStatus,
    AccountFactsSourceType,
    TrialReadinessAccountFacts,
)


class BinanceBalanceReadOnlyClient(Protocol):
    async def fetch_balance(self, params: Optional[dict[str, Any]] = None) -> Mapping[str, Any]: ...

    async def close(self) -> None: ...


class BinanceUsdtFuturesAccountFactsSource:
    """Fetch USDT futures equity facts through a balance-only client."""

    def __init__(
        self,
        *,
        balance_client: BinanceBalanceReadOnlyClient,
        source_id: str = "binance_usdt_futures_live_read_only",
        account_id: str = "configured_binance_usdt_futures_account",
    ) -> None:
        self._balance_client = balance_client
        self._source_id = source_id
        self._account_id = account_id

    async def close(self) -> None:
        await self._balance_client.close()

    async def read_trial_readiness_account_facts(
        self,
        *,
        candidate_id: str,
        symbol: str,
        side: str,
        generated_at_ms: int,
    ) -> TrialReadinessAccountFacts:
        balance = await self._balance_client.fetch_balance({"type": "future"})
        account_equity = _extract_account_equity(balance)
        available_margin = _extract_available_margin(balance)
        exchange_timestamp = _parse_int(balance.get("timestamp"))
        timestamp_ms = exchange_timestamp or generated_at_ms
        notes = [
            f"candidate={candidate_id}",
            f"symbol={symbol}",
            f"side={side}",
            "source=Binance USDT futures balance read",
            "account_equity_prefers_totalMarginBalance",
            "available_margin_prefers_availableBalance",
        ]
        if exchange_timestamp is None:
            notes.append("exchange timestamp missing; using local read timestamp")

        return TrialReadinessAccountFacts(
            account_id=self._account_id,
            account_type="binance_usdt_futures",
            source_id=self._source_id,
            source_type=AccountFactsSourceType.BINANCE_USDT_FUTURES_READ_ONLY,
            account_equity=account_equity,
            available_margin=available_margin,
            timestamp_ms=timestamp_ms,
            freshness_status=AccountFactsFreshnessStatus.FRESH,
            reconciliation_status=AccountFactsReconciliationStatus.CLEAN,
            read_only_guarantee=True,
            external_call_performed=True,
            external_call_type="read_only_account_query",
            notes=tuple(notes),
        )


class CcxtBinanceUsdtFuturesBalanceClient:
    """Minimal ccxt adapter exposing only `fetch_balance` and `close`."""

    def __init__(
        self,
        *,
        api_key: str,
        api_secret: str,
        testnet: bool,
        timeout_ms: int = 30000,
    ) -> None:
        import ccxt.async_support as ccxt_async

        self._exchange = ccxt_async.binance(
            {
                "apiKey": api_key,
                "secret": api_secret,
                "enableRateLimit": True,
                "timeout": timeout_ms,
                "options": {
                    "defaultType": "future",
                    "adjustForTimeDifference": True,
                    "recvWindow": 30000,
                },
            }
        )
        if testnet:
            self._exchange.set_sandbox_mode(True)

    async def fetch_balance(self, params: Optional[dict[str, Any]] = None) -> Mapping[str, Any]:
        return await self._exchange.fetch_balance(params or {"type": "future"})

    async def close(self) -> None:
        await self._exchange.close()


def _extract_account_equity(balance: Mapping[str, Any]) -> Optional[Decimal]:
    info = balance.get("info")
    if isinstance(info, Mapping):
        for key in ("totalMarginBalance", "totalWalletBalance"):
            value = _decimal_or_none(info.get(key))
            if value is not None:
                return value
    return _nested_decimal(balance, "total", "USDT") or _nested_decimal(balance, "USDT", "total")


def _extract_available_margin(balance: Mapping[str, Any]) -> Optional[Decimal]:
    info = balance.get("info")
    if isinstance(info, Mapping):
        value = _decimal_or_none(info.get("availableBalance"))
        if value is not None:
            return value
    return _nested_decimal(balance, "free", "USDT") or _nested_decimal(balance, "USDT", "free")


def _nested_decimal(mapping: Mapping[str, Any], first: str, second: str) -> Optional[Decimal]:
    value = mapping.get(first)
    if not isinstance(value, Mapping):
        return None
    return _decimal_or_none(value.get(second))


def _decimal_or_none(value: object) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _parse_int(value: object) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
