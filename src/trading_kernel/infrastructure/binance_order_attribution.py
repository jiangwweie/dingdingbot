"""Binance USD-M regular/algo order namespace resolution."""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from decimal import Decimal
from typing import Protocol

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
)

from src.trading_kernel.domain.instrument_identity import (
    parse_binance_usdm_instrument_id,
)
from src.trading_kernel.domain.order_attribution import (
    OrderNamespace,
    ResolvedOrderIdentity,
    TicketOrderReference,
)


class BinanceAlgoOrderClient(Protocol):
    def fapiPrivateGetAlgoOrder(self, params: Mapping[str, object]) -> object: ...


class BinanceAlgoOrderAttributionError(RuntimeError):
    """A Binance algo response cannot prove the frozen command identity."""


class BinanceAlgoOrderSnapshot(BaseModel):
    """Typed protocol boundary for Binance USD-M Query Algo Order."""

    model_config = ConfigDict(
        frozen=True,
        populate_by_name=True,
        extra="ignore",
    )

    algo_id: str = Field(alias="algoId")
    client_algo_id: str = Field(alias="clientAlgoId")
    symbol: str
    side: str
    position_side: str = Field(alias="positionSide")
    order_type: str = Field(alias="orderType")
    quantity: Decimal
    algo_status: str = Field(alias="algoStatus")
    actual_order_id: str | None = Field(alias="actualOrderId", default=None)
    actual_quantity: Decimal | None = Field(alias="actualQty", default=None)

    @field_validator("algo_id", "client_algo_id", mode="before")
    @classmethod
    def _normalize_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("Binance algo identity must be non-blank")
        return normalized

    @field_validator(
        "symbol",
        "side",
        "position_side",
        "order_type",
        "algo_status",
        mode="before",
    )
    @classmethod
    def _normalize_enum_field(cls, value: object) -> str:
        normalized = str(value or "").strip().upper()
        if not normalized:
            raise ValueError("Binance algo enum field must be non-blank")
        return normalized

    @field_validator("actual_order_id", mode="before")
    @classmethod
    def _normalize_optional_identity(cls, value: object) -> str | None:
        normalized = str(value or "").strip()
        return normalized or None

    @field_validator("quantity")
    @classmethod
    def _require_positive_quantity(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or value <= 0:
            raise ValueError("Binance quantity must be finite and positive")
        return value

    @field_validator("actual_quantity")
    @classmethod
    def _require_nonnegative_actual_quantity(
        cls,
        value: Decimal | None,
    ) -> Decimal | None:
        if value is not None and (not value.is_finite() or value < 0):
            raise ValueError("Binance actualQty must be finite and non-negative")
        return value


_NOT_TRIGGERED_TERMINAL_STATUSES = {"CANCELED", "EXPIRED", "REJECTED"}


async def resolve_binance_order_identity(
    *,
    exchange: object,
    reference: TicketOrderReference,
    observed_at_ms: int,
) -> ResolvedOrderIdentity:
    """Resolve an accepted Binance order into the sole legal trade order id."""

    if reference.namespace is OrderNamespace.REGULAR:
        return ResolvedOrderIdentity(
            reference=reference,
            resolution_status="executable",
            actual_order_id=reference.submitted_exchange_order_id,
            resolved_at_ms=observed_at_ms,
        )

    lookup = getattr(exchange, "fapiPrivateGetAlgoOrder", None)
    if not callable(lookup):
        raise TypeError("Binance venue lacks exact algo order lookup")
    response = lookup({"algoId": reference.submitted_exchange_order_id})
    if inspect.isawaitable(response):
        response = await response
    snapshot = _parse_algo_order_snapshot(response)

    expectation = reference.conditional_expectation
    if expectation is None:
        raise BinanceAlgoOrderAttributionError(
            "conditional order lacks frozen command expectation"
        )
    expected_symbol = parse_binance_usdm_instrument_id(
        expectation.exchange_instrument_id
    ).symbol
    _require_exact_identity(
        field="algoId",
        actual=snapshot.algo_id,
        expected=reference.submitted_exchange_order_id,
    )
    _require_exact_identity(
        field="clientAlgoId",
        actual=snapshot.client_algo_id,
        expected=reference.venue_client_order_id,
    )
    _require_exact_identity(
        field="symbol",
        actual=snapshot.symbol,
        expected=expected_symbol,
    )
    _require_exact_identity(
        field="side",
        actual=snapshot.side,
        expected=expectation.side.upper(),
    )
    _require_exact_identity(
        field="positionSide",
        actual=snapshot.position_side,
        expected=expectation.position_side.upper(),
    )
    _require_exact_identity(
        field="orderType",
        actual=snapshot.order_type,
        expected=expectation.order_type.upper(),
    )
    if snapshot.quantity != expectation.quantity:
        raise BinanceAlgoOrderAttributionError(
            "Binance quantity differs from frozen command identity"
        )

    if snapshot.actual_order_id is not None:
        if snapshot.actual_quantity is None:
            raise BinanceAlgoOrderAttributionError(
                "Binance actualQty is unavailable for executable algo order"
            )
        if snapshot.actual_quantity != expectation.quantity:
            raise BinanceAlgoOrderAttributionError(
                "Binance actualQty differs from frozen command quantity"
            )
        return ResolvedOrderIdentity(
            reference=reference,
            resolution_status="executable",
            actual_order_id=snapshot.actual_order_id,
            resolved_at_ms=observed_at_ms,
        )

    if snapshot.algo_status not in _NOT_TRIGGERED_TERMINAL_STATUSES:
        raise BinanceAlgoOrderAttributionError(
            "Binance algo order has no actual order identity yet"
        )
    if snapshot.actual_quantity not in {None, Decimal(0)}:
        raise BinanceAlgoOrderAttributionError(
            "Binance untriggered algo actualQty must be absent or zero"
        )
    return ResolvedOrderIdentity(
        reference=reference,
        resolution_status="not_triggered",
        actual_order_id=None,
        resolved_at_ms=observed_at_ms,
    )


def _parse_algo_order_snapshot(response: object) -> BinanceAlgoOrderSnapshot:
    if not isinstance(response, Mapping):
        raise TypeError("Binance algo order response is not a mapping")
    try:
        return BinanceAlgoOrderSnapshot.model_validate(response)
    except ValidationError as exc:
        first_error = exc.errors(include_input=False)[0]
        field = str(first_error.get("loc", ("response",))[0])
        raise BinanceAlgoOrderAttributionError(
            f"Binance {field} violates the typed algo order protocol"
        ) from exc


def _require_exact_identity(
    *,
    field: str,
    actual: str,
    expected: str,
) -> None:
    if actual != expected:
        raise BinanceAlgoOrderAttributionError(
            f"Binance {field} differs from frozen command identity"
        )
