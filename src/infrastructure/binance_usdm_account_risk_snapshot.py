"""Full-account, read-only Binance USD-M risk snapshot collection."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


SignedGet = Callable[[str], Awaitable[Any]]


class ExchangePositionRow(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exchange_symbol: str = Field(min_length=1)
    position_qty: Decimal
    entry_price: Decimal
    position_side: str = "BOTH"


class ExchangeOpenOrderRow(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exchange_symbol: str = Field(min_length=1)
    exchange_order_id: str = ""
    algo_id: str = ""
    client_order_id: str = ""
    side: str = ""
    position_side: str = "BOTH"
    reduce_only: bool | None = None
    close_position: bool | None = None
    order_type: str = ""
    quantity: Decimal | None = None
    price: Decimal | None = None
    trigger_price: Decimal | None = None


class FullAccountRiskSnapshot(BaseModel):
    """Typed account facts with an explicit fail-closed state."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    snapshot_ready: bool
    failure_code: str | None = None
    account_id: str = Field(min_length=1)
    exchange_id: str = Field(min_length=1)
    total_wallet_balance: Decimal | None = None
    available_balance: Decimal | None = None
    exchange_total_initial_margin: Decimal | None = None
    can_trade: bool | None = None
    position_mode: Literal["one_way", "hedge"] | None = None
    positions: tuple[ExchangePositionRow, ...] = ()
    regular_open_orders: tuple[ExchangeOpenOrderRow, ...] = ()
    algo_open_orders: tuple[ExchangeOpenOrderRow, ...] = ()
    source_snapshot_id: str = Field(min_length=1)
    observed_at_ms: int = Field(gt=0)
    valid_until_ms: int = Field(gt=0)
    symbol_filter_applied: Literal[False] = False
    exchange_write_called: Literal[False] = False


class BinanceUsdmAccountRiskSnapshotProvider:
    """Collect every required account surface concurrently outside any PG transaction."""

    _PATHS = (
        "/fapi/v2/account",
        "/fapi/v2/positionRisk",
        "/fapi/v1/openOrders",
        "/fapi/v1/openAlgoOrders",
        "/fapi/v1/positionSide/dual",
    )

    def __init__(
        self,
        *,
        account_id: str,
        exchange_id: str,
        signed_get: SignedGet,
        now_ms: Callable[[], int] | None = None,
        validity_ms: int = 60_000,
    ) -> None:
        if not account_id or not exchange_id:
            raise ValueError("account_id and exchange_id are required")
        if validity_ms <= 0:
            raise ValueError("validity_ms must be positive")
        self._account_id = account_id
        self._exchange_id = exchange_id
        self._signed_get = signed_get
        self._now_ms = now_ms or _now_ms
        self._validity_ms = validity_ms

    async def fetch(self, *, timeout_seconds: float) -> FullAccountRiskSnapshot:
        observed_at_ms = self._now_ms()
        snapshot_id = _snapshot_id(
            self._account_id,
            self._exchange_id,
            observed_at_ms,
        )
        if timeout_seconds <= 0:
            return self._failed(snapshot_id, observed_at_ms, "account_risk_snapshot_timeout_invalid")
        try:
            account, positions, regular_orders, algo_orders, account_mode = (
                await asyncio.wait_for(
                    asyncio.gather(*(self._signed_get(path) for path in self._PATHS)),
                    timeout=timeout_seconds,
                )
            )
            return _normalize_snapshot(
                account_id=self._account_id,
                exchange_id=self._exchange_id,
                snapshot_id=snapshot_id,
                observed_at_ms=observed_at_ms,
                valid_until_ms=observed_at_ms + self._validity_ms,
                account=account,
                positions=positions,
                regular_orders=regular_orders,
                algo_orders=algo_orders,
                account_mode=account_mode,
            )
        except Exception:
            return self._failed(
                snapshot_id,
                observed_at_ms,
                "account_risk_snapshot_fetch_failed",
            )

    def _failed(
        self,
        snapshot_id: str,
        observed_at_ms: int,
        failure_code: str,
    ) -> FullAccountRiskSnapshot:
        return FullAccountRiskSnapshot(
            snapshot_ready=False,
            failure_code=failure_code,
            account_id=self._account_id,
            exchange_id=self._exchange_id,
            source_snapshot_id=snapshot_id,
            observed_at_ms=observed_at_ms,
            valid_until_ms=observed_at_ms + self._validity_ms,
        )


def _normalize_snapshot(
    *,
    account_id: str,
    exchange_id: str,
    snapshot_id: str,
    observed_at_ms: int,
    valid_until_ms: int,
    account: Any,
    positions: Any,
    regular_orders: Any,
    algo_orders: Any,
    account_mode: Any,
) -> FullAccountRiskSnapshot:
    if not isinstance(account, dict):
        raise ValueError("account payload is malformed")
    if not isinstance(positions, list):
        raise ValueError("position payload is malformed")
    if not isinstance(regular_orders, list) or not isinstance(algo_orders, list):
        raise ValueError("open-order payload is malformed")
    if not isinstance(account_mode, dict) or not isinstance(
        account_mode.get("dualSidePosition"), bool
    ):
        raise ValueError("account mode payload is malformed")
    total_wallet_balance = _positive_decimal(account.get("totalWalletBalance"))
    available_balance = _nonnegative_decimal(account.get("availableBalance"))
    total_initial_margin = _nonnegative_decimal(account.get("totalInitialMargin"))
    can_trade = account.get("canTrade")
    if (
        total_wallet_balance is None
        or available_balance is None
        or total_initial_margin is None
        or not isinstance(can_trade, bool)
    ):
        raise ValueError("account capacity fields are malformed")
    normalized_positions = tuple(
        _position_row(row)
        for row in positions
        if _nonzero_position(row)
    )
    normalized_regular = tuple(_order_row(row, algo=False) for row in regular_orders)
    normalized_algo = tuple(_order_row(row, algo=True) for row in algo_orders)
    return FullAccountRiskSnapshot(
        snapshot_ready=True,
        account_id=account_id,
        exchange_id=exchange_id,
        total_wallet_balance=total_wallet_balance,
        available_balance=available_balance,
        exchange_total_initial_margin=total_initial_margin,
        can_trade=can_trade,
        position_mode="hedge" if account_mode["dualSidePosition"] else "one_way",
        positions=normalized_positions,
        regular_open_orders=normalized_regular,
        algo_open_orders=normalized_algo,
        source_snapshot_id=snapshot_id,
        observed_at_ms=observed_at_ms,
        valid_until_ms=valid_until_ms,
    )


def _nonzero_position(row: Any) -> bool:
    if not isinstance(row, dict):
        raise ValueError("position row is malformed")
    quantity = _decimal(row.get("positionAmt"))
    if quantity is None:
        raise ValueError("position quantity is malformed")
    return quantity != 0


def _position_row(row: dict[str, Any]) -> ExchangePositionRow:
    quantity = _decimal(row.get("positionAmt"))
    entry_price = _positive_decimal(row.get("entryPrice"))
    symbol = str(row.get("symbol") or "").strip()
    if quantity is None or entry_price is None or not symbol:
        raise ValueError("position row is malformed")
    return ExchangePositionRow(
        exchange_symbol=symbol,
        position_qty=quantity,
        entry_price=entry_price,
        position_side=str(row.get("positionSide") or "BOTH").upper(),
    )


def _order_row(row: Any, *, algo: bool) -> ExchangeOpenOrderRow:
    if not isinstance(row, dict):
        raise ValueError("open order row is malformed")
    symbol = str(row.get("symbol") or "").strip()
    if not symbol:
        raise ValueError("open order symbol is missing")
    quantity = _decimal(row.get("origQty") or row.get("quantity"))
    price = _decimal(row.get("price"))
    return ExchangeOpenOrderRow(
        exchange_symbol=symbol,
        exchange_order_id=str(row.get("orderId") or ""),
        algo_id=str(row.get("algoId") or "") if algo else "",
        client_order_id=str(row.get("clientOrderId") or ""),
        side=str(row.get("side") or "").upper(),
        position_side=str(row.get("positionSide") or "BOTH").upper(),
        reduce_only=(row.get("reduceOnly") if isinstance(row.get("reduceOnly"), bool) else None),
        close_position=(row.get("closePosition") if isinstance(row.get("closePosition"), bool) else None),
        order_type=str(row.get("type") or row.get("algoType") or ""),
        quantity=quantity,
        price=price,
        trigger_price=_decimal(row.get("stopPrice") or row.get("triggerPrice")),
    )


def _decimal(value: Any) -> Decimal | None:
    try:
        decimal = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return decimal if decimal.is_finite() else None


def _positive_decimal(value: Any) -> Decimal | None:
    decimal = _decimal(value)
    return decimal if decimal is not None and decimal > 0 else None


def _nonnegative_decimal(value: Any) -> Decimal | None:
    decimal = _decimal(value)
    return decimal if decimal is not None and decimal >= 0 else None


def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _snapshot_id(account_id: str, exchange_id: str, observed_at_ms: int) -> str:
    raw = f"{account_id}|{exchange_id}|{observed_at_ms}".encode("utf-8")
    return f"account_risk_snapshot:{sha256(raw).hexdigest()[:32]}"
