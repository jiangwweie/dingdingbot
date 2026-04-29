from __future__ import annotations

import json
from decimal import Decimal

import pytest

from src.application.capital_protection import CapitalProtectionManager
from src.application.decision_trace import TraceService
from src.domain.models import CapitalProtectionConfig, OrderType
from src.infrastructure.jsonl_trace_sink import JsonlTraceSink


class _FakeAccountService:
    async def get_balance(self):
        return Decimal("1000")


class _FakeNotifier:
    async def send_alert(self, title: str, message: str) -> None:
        return None


class _FakeGateway:
    async def fetch_ticker_price(self, symbol: str):
        return Decimal("100")

    async def get_market_info(self, symbol: str):
        return {
            "min_quantity": Decimal("0.001"),
            "quantity_precision": 3,
            "step_size": Decimal("0.001"),
        }


@pytest.mark.asyncio
async def test_capital_protection_emits_risk_decision_trace(tmp_path):
    trace_path = tmp_path / "runtime" / "risk_decision.jsonl"
    service = TraceService(sinks=[JsonlTraceSink(trace_path)])

    manager = CapitalProtectionManager(
        config=CapitalProtectionConfig(),
        account_service=_FakeAccountService(),
        notifier=_FakeNotifier(),
        gateway=_FakeGateway(),
        trace_service=service,
        config_hash="cfg-risk-1",
    )

    result = await manager.pre_order_check(
        symbol="ETH/USDT:USDT",
        order_type=OrderType.MARKET,
        amount=Decimal("0.1"),
        price=None,
        trigger_price=None,
        stop_loss=Decimal("99"),
    )

    assert result.allowed is True

    payload = json.loads(trace_path.read_text(encoding="utf-8").splitlines()[0])
    assert payload["event_type"] == "risk.pre_order_check"
    assert payload["decision"] == "allow"
    assert payload["config_hash"] == "cfg-risk-1"
    assert payload["trace_id"]
    assert payload["lifecycle_id"]
    assert payload["metadata"]["symbol"] == "ETH/USDT:USDT"
    assert payload["metadata"]["order_type"] == "MARKET"
