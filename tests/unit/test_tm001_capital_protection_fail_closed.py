from __future__ import annotations

import json
from decimal import Decimal

import pytest

from src.application.capital_protection import CapitalProtectionManager
from src.application.decision_trace import TraceService
from src.domain.models import CapitalProtectionConfig, OrderType
from src.infrastructure.jsonl_trace_sink import JsonlTraceSink


class _FakeAccountService:
    async def get_balance(self) -> Decimal:
        return Decimal("1000")


class _FakeNotifier:
    async def send_alert(self, title: str, message: str) -> None:
        return None


class _FakeGateway:
    def __init__(
        self,
        *,
        market_info_error: Exception | None = None,
        ticker_error: Exception | None = None,
    ) -> None:
        self._market_info_error = market_info_error
        self._ticker_error = ticker_error

    async def fetch_ticker_price(self, symbol: str) -> Decimal:
        if self._ticker_error is not None:
            raise self._ticker_error
        return Decimal("100")

    async def get_market_info(self, symbol: str):
        if self._market_info_error is not None:
            raise self._market_info_error
        return {
            "min_quantity": Decimal("0.001"),
            "quantity_precision": 3,
            "step_size": Decimal("0.001"),
        }


def _build_manager(
    gateway: _FakeGateway | None = None,
    *,
    trace_service: TraceService | None = None,
) -> CapitalProtectionManager:
    config = CapitalProtectionConfig()
    config.daily["max_trade_count"] = 10
    config.daily["max_loss_amount"] = Decimal("100")
    return CapitalProtectionManager(
        config=config,
        account_service=_FakeAccountService(),
        notifier=_FakeNotifier(),
        gateway=gateway or _FakeGateway(),
        trace_service=trace_service,
    )


async def _run_safe_limit_check(
    manager: CapitalProtectionManager,
    *,
    order_type: OrderType = OrderType.LIMIT,
    price: Decimal | None = Decimal("100"),
):
    return await manager.pre_order_check(
        symbol="ETH/USDT:USDT",
        order_type=order_type,
        amount=Decimal("0.1"),
        price=price,
        trigger_price=None,
        stop_loss=Decimal("99"),
    )


def _assert_fail_closed_result(result) -> None:
    assert result.allowed is False
    assert result.reason is not None
    assert result.reason_message is not None


@pytest.mark.asyncio
async def test_quantity_precision_internal_exception_fails_closed():
    manager = _build_manager(
        _FakeGateway(market_info_error=RuntimeError("market info unavailable"))
    )

    result = await _run_safe_limit_check(manager)

    _assert_fail_closed_result(result)
    assert result.reason == "QUANTITY_PRECISION_CHECK_ERROR"


@pytest.mark.asyncio
async def test_price_reasonability_internal_exception_fails_closed():
    manager = _build_manager(
        _FakeGateway(ticker_error=RuntimeError("ticker unavailable"))
    )

    result = await _run_safe_limit_check(manager)

    _assert_fail_closed_result(result)
    assert result.reason == "PRICE_REASONABILITY_CHECK_ERROR"


@pytest.mark.asyncio
async def test_pre_order_check_normal_path_still_allows_safe_order():
    manager = _build_manager()

    result = await _run_safe_limit_check(manager)

    assert result.allowed is True
    assert result.reason is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("gateway", "expected_reason"),
    [
        (
            _FakeGateway(market_info_error=RuntimeError("market info unavailable")),
            "QUANTITY_PRECISION_CHECK_ERROR",
        ),
        (
            _FakeGateway(ticker_error=RuntimeError("ticker unavailable")),
            "PRICE_REASONABILITY_CHECK_ERROR",
        ),
    ],
)
async def test_internal_exception_paths_emit_deny_trace(tmp_path, gateway, expected_reason):
    trace_path = tmp_path / "risk_decision.jsonl"
    trace_service = TraceService(sinks=[JsonlTraceSink(trace_path)])
    manager = _build_manager(gateway, trace_service=trace_service)

    result = await _run_safe_limit_check(manager)

    assert result.allowed is False
    assert result.reason == expected_reason

    payload = json.loads(trace_path.read_text(encoding="utf-8").splitlines()[0])
    assert payload["event_type"] == "risk.pre_order_check"
    assert payload["decision"] == "deny"
    assert payload["reason"] == expected_reason
