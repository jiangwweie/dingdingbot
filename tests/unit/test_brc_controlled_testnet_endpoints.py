from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.application.bounded_risk_campaign_service import BoundedRiskCampaignService
from src.domain.bounded_risk_campaign import BrcAttemptStatus
from src.domain.execution_intent import ExecutionIntent, ExecutionIntentStatus
from src.domain.models import Direction, Order, OrderRole, OrderStatus, OrderType, SignalResult
from src.interfaces import api as api_module
from src.interfaces.api_console_runtime import router as runtime_router


ETH = "ETH/USDT:USDT"
BTC = "BTC/USDT:USDT"
PROFILE = "brc_btc_eth_testnet_runtime"


class InMemoryBrcRepo:
    def __init__(self) -> None:
        self.campaign = None
        self.switches = []
        self.events = []
        self.mock_pnl_events = []

    async def initialize(self) -> None:
        return None

    async def get_current_campaign(self):
        if self.campaign is None or self.campaign.status.value == "ended":
            return None
        return self.campaign

    async def get_latest_campaign(self):
        return self.campaign

    async def save_campaign(self, campaign):
        self.campaign = campaign
        return campaign

    async def append_switch_decision(self, decision):
        self.switches.append(decision)
        return decision

    async def append_campaign_event(
        self,
        *,
        campaign_id: str,
        event_type: str,
        occurred_at_ms: int,
        symbol: Optional[str] = None,
        attempt_id: Optional[str] = None,
        reason: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ):
        row = {
            "campaign_id": campaign_id,
            "sequence_number": len(self.events) + 1,
            "event_type": event_type,
            "symbol": symbol,
            "attempt_id": attempt_id,
            "reason": reason,
            "metadata": dict(metadata or {}),
            "occurred_at_ms": occurred_at_ms,
        }
        self.events.append(row)
        return row

    async def append_mock_pnl_event(self, event):
        self.mock_pnl_events.append(event)
        return event

    async def list_switch_decisions(self, campaign_id: str):
        return [item for item in self.switches if item.campaign_id == campaign_id]

    async def list_campaign_events(self, campaign_id: str):
        return [item for item in self.events if item["campaign_id"] == campaign_id]

    async def list_mock_pnl_events(self, campaign_id: str):
        return [item for item in self.mock_pnl_events if item.campaign_id == campaign_id]


class MutablePositionRepo:
    def __init__(self) -> None:
        self.active = []

    async def list_active(self, *, symbol=None, limit=10):
        positions = list(self.active)
        if symbol is not None:
            positions = [position for position in positions if position.symbol == symbol]
        return positions[:limit]


class EmptyOrderRepo:
    async def get_open_orders(self, symbol=None):
        return []


class FakeCampaignStateService:
    def __init__(self) -> None:
        self.state = SimpleNamespace(
            scope_key="runtime:default",
            status="observe",
            reason=None,
            updated_by="system",
            updated_at_ms=1,
            active_strategy_contract_id=None,
            active_session_id=None,
            source="test",
        )

    def get_state(self):
        return self.state

    async def set_state(self, **kwargs):
        self.state = SimpleNamespace(
            scope_key="runtime:default",
            status=kwargs["status"],
            reason=kwargs.get("reason"),
            updated_by=kwargs.get("updated_by", "test"),
            updated_at_ms=2,
            active_strategy_contract_id=kwargs.get("active_strategy_contract_id"),
            active_session_id=kwargs.get("active_session_id"),
            source="test",
        )
        return self.state


def _app():
    app = FastAPI()
    app.include_router(runtime_router)
    return app


def _patch_api_module(monkeypatch, **attrs):
    for name, value in attrs.items():
        monkeypatch.setattr(api_module, name, value)


def _config_provider(*, profile=PROFILE, symbols=(ETH, BTC), testnet=True):
    resolved = SimpleNamespace(
        profile_name=profile,
        environment=SimpleNamespace(exchange_testnet=testnet),
        market=SimpleNamespace(symbols=list(symbols)),
    )
    return SimpleNamespace(resolved_config=resolved)


def _guard(armed=True):
    svc = MagicMock()
    svc.is_armed = MagicMock(return_value=armed)
    return svc


def _gks(active=False):
    svc = MagicMock()
    svc.is_active = MagicMock(return_value=active)
    return svc


def _position(symbol, qty):
    return SimpleNamespace(
        id=f"pos-{symbol}",
        signal_id=f"sig-{symbol}",
        symbol=symbol,
        current_qty=qty,
    )


def _gateway(price=Decimal("2100"), min_notional=Decimal("20")):
    gw = MagicMock()
    gw.fetch_ticker_price = AsyncMock(return_value=price)
    gw.get_min_notional = MagicMock(return_value=min_notional)
    gw.fetch_positions = AsyncMock(return_value=[])
    gw.fetch_open_orders = AsyncMock(return_value=[])
    return gw


def _intent(symbol):
    return ExecutionIntent(
        id=f"intent-{symbol.split('/')[0].lower()}",
        signal_id=f"sig-{symbol.split('/')[0].lower()}",
        signal=SignalResult(
            symbol=symbol,
            timeframe="1h",
            direction=Direction.LONG,
            entry_price=Decimal("100"),
            suggested_stop_loss=Decimal("99"),
            suggested_position_size=Decimal("0.001"),
            current_leverage=1,
            tags=[],
            risk_reward_info="brc-test",
            status="PENDING",
            strategy_name="brc_test",
        ),
        status=ExecutionIntentStatus.SUBMITTED,
    )


def _orchestrator():
    orch = MagicMock()
    orch.execute_signal = AsyncMock(side_effect=lambda signal, strategy: _intent(signal.symbol))
    orch.list_protection_health_blocks = MagicMock(return_value={})
    orch.is_symbol_blocked = MagicMock(return_value=False)

    async def close(position, reason, max_amount):
        order = Order(
            id=f"exit-{position.symbol.split('/')[0].lower()}",
            signal_id=position.signal_id,
            exchange_order_id=f"ex-{position.symbol.split('/')[0].lower()}",
            symbol=position.symbol,
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.EXIT,
            requested_qty=Decimal(str(position.current_qty)),
            filled_qty=Decimal(str(position.current_qty)),
            status=OrderStatus.FILLED,
            created_at=1,
            updated_at=1,
            reduce_only=True,
            average_exec_price=Decimal("2100"),
        )
        return {"close_order": order, "terminalized_protection_orders": []}

    orch.execute_controlled_close = AsyncMock(side_effect=close)
    return orch


async def _brc_service():
    repo = InMemoryBrcRepo()
    service = BoundedRiskCampaignService(repo)
    await service.initialize()
    return service


@pytest.fixture(autouse=True)
def _reset_brc_guards(monkeypatch):
    import src.interfaces.api_console_runtime as mod

    mod._CONTROLLED_ENTRY_EXECUTED_BY_SYMBOL.clear()
    mod._CONTROLLED_CLOSE_EXECUTED_BY_SYMBOL.clear()
    monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "true")
    monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "true")
    yield
    mod._CONTROLLED_ENTRY_EXECUTED_BY_SYMBOL.clear()
    mod._CONTROLLED_CLOSE_EXECUTED_BY_SYMBOL.clear()


@pytest.mark.asyncio
async def test_brc_rejects_wrong_profile(monkeypatch):
    _patch_api_module(
        monkeypatch,
        _runtime_config_provider=_config_provider(profile="phase5e_btc_eth_testnet_runtime"),
        _brc_campaign_service=await _brc_service(),
    )

    with TestClient(_app()) as client:
        resp = client.post("/api/runtime/test/brc/campaigns", json={"reason": "x"})

    assert resp.status_code == 403
    assert "brc_btc_eth_testnet_runtime" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_brc_entry_rejects_body_override(monkeypatch):
    service = await _brc_service()
    await service.create_campaign(
        bucket_id="bucket",
        authorized_amount=Decimal("500"),
        max_campaign_loss=Decimal("120"),
        profit_protect_trigger=Decimal("100"),
        reason="test",
    )
    await service.switch_playbook(
        new_playbook_id="PB-004-BRC-CONTROLLED-TESTNET",
        reason_category="evidence_driven",
        reason_text="owner authorized",
        evidence_refs=["evidence"],
    )
    await service.arm_attempt(symbol=ETH, reason="eth")
    _patch_api_module(
        monkeypatch,
        _runtime_config_provider=_config_provider(),
        _brc_campaign_service=service,
        _execution_orchestrator=_orchestrator(),
        _exchange_gateway=_gateway(),
        _startup_trading_guard_service=_guard(),
        _global_kill_switch_service=_gks(),
        _position_repo=MutablePositionRepo(),
    )

    with TestClient(_app()) as client:
        resp = client.post(
            "/api/runtime/test/brc/eth/execute-controlled-entry",
            json={"amount": "999", "leverage": 50},
        )

    assert resp.status_code == 400
    assert "server-controlled" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_brc_blocked_intent_does_not_record_attempt_entry(monkeypatch):
    service = await _brc_service()
    await service.create_campaign(
        bucket_id="bucket",
        authorized_amount=Decimal("500"),
        max_campaign_loss=Decimal("120"),
        profit_protect_trigger=Decimal("100"),
        reason="test",
    )
    await service.switch_playbook(
        new_playbook_id="PB-004-BRC-CONTROLLED-TESTNET",
        reason_category="evidence_driven",
        reason_text="owner authorized",
        evidence_refs=["evidence"],
    )
    await service.arm_attempt(symbol=ETH, reason="eth")
    orch = _orchestrator()
    blocked = _intent(ETH)
    blocked.status = ExecutionIntentStatus.BLOCKED
    blocked.blocked_reason = "DAILY_TRADE_COUNT_LIMIT"
    orch.execute_signal = AsyncMock(return_value=blocked)
    _patch_api_module(
        monkeypatch,
        _runtime_config_provider=_config_provider(),
        _brc_campaign_service=service,
        _execution_orchestrator=orch,
        _exchange_gateway=_gateway(),
        _startup_trading_guard_service=_guard(),
        _global_kill_switch_service=_gks(),
        _position_repo=MutablePositionRepo(),
        _trace_service=None,
    )

    with TestClient(_app()) as client:
        resp = client.post("/api/runtime/test/brc/eth/execute-controlled-entry")

    assert resp.status_code == 200
    assert resp.json()["status"] == "blocked"
    assert resp.json()["attempt_locked"] is False
    campaign = await service.require_current_campaign()
    assert campaign.last_attempt.status == BrcAttemptStatus.ARMED


@pytest.mark.asyncio
async def test_brc_api_acceptance_flow_with_mock_pnl_and_loss_lock(monkeypatch):
    position_repo = MutablePositionRepo()
    service = await _brc_service()
    orch = _orchestrator()
    campaign_state_service = FakeCampaignStateService()
    _patch_api_module(
        monkeypatch,
        _runtime_config_provider=_config_provider(),
        _brc_campaign_service=service,
        _campaign_state_service=campaign_state_service,
        _execution_orchestrator=orch,
        _exchange_gateway=_gateway(price=Decimal("2100"), min_notional=Decimal("1")),
        _startup_trading_guard_service=_guard(),
        _global_kill_switch_service=_gks(),
        _position_repo=position_repo,
        _order_repo=EmptyOrderRepo(),
        _trace_service=None,
    )

    with TestClient(_app()) as client:
        create = client.post("/api/runtime/test/brc/campaigns", json={"reason": "acceptance"})
        assert create.status_code == 200

        switch = client.post(
            "/api/runtime/test/brc/switch-playbook",
            json={
                "reason_text": "owner authorized BRC controlled testnet rehearsal",
                "evidence_refs": ["docs/adr/0012-bounded-risk-campaign-system.md"],
            },
        )
        assert switch.status_code == 200
        assert switch.json()["decision"]["decision_result"] == "allowed"

        arm_eth = client.post("/api/runtime/test/brc/eth/arm-attempt", json={"reason": "eth"})
        assert arm_eth.status_code == 200
        entry_eth = client.post("/api/runtime/test/brc/eth/execute-controlled-entry")
        assert entry_eth.status_code == 200
        position_repo.active = [_position(ETH, Decimal("0.01"))]
        close_eth = client.post("/api/runtime/test/brc/eth/execute-controlled-close")
        assert close_eth.status_code == 200
        position_repo.active = []
        campaign_state_service.state.status = "closed"

        profit = client.post(
            "/api/runtime/test/brc/mock-pnl",
            json={"amount": "120", "source": "testnet_mock", "reason": "mock profit"},
        )
        assert profit.status_code == 200
        assert profit.json()["campaign"]["status"] == "profit_protect"
        assert profit.json()["withdrawal_executed"] is False

        arm_btc = client.post("/api/runtime/test/brc/btc/arm-attempt", json={"reason": "btc"})
        assert arm_btc.status_code == 200
        entry_btc = client.post("/api/runtime/test/brc/btc/execute-controlled-entry")
        assert entry_btc.status_code == 200
        position_repo.active = [_position(BTC, Decimal("0.002"))]
        close_btc = client.post("/api/runtime/test/brc/btc/execute-controlled-close")
        assert close_btc.status_code == 200
        position_repo.active = []
        campaign_state_service.state.status = "closed"

        loss = client.post(
            "/api/runtime/test/brc/mock-pnl",
            json={"amount": "-240", "source": "testnet_mock", "reason": "mock loss"},
        )
        assert loss.status_code == 200
        assert loss.json()["campaign"]["status"] == "loss_locked"

        third = client.post("/api/runtime/test/brc/eth/arm-attempt", json={"reason": "third"})
        assert third.status_code == 409
        assert "loss_locked" in third.json()["detail"]

        evidence = client.get("/api/runtime/test/brc/evidence")
        assert evidence.status_code == 200
        assert len(evidence.json()["evidence"]["campaign"]["attempts"]) == 2
        assert len(evidence.json()["evidence"]["mock_pnl_events"]) == 2

        final = client.post("/api/runtime/test/brc/finalize", json={})
        assert final.status_code == 200
        assert final.json()["campaign"]["outcome"] == "ended_testnet_rehearsal_complete_loss_locked"

        review = client.get("/api/runtime/test/brc/review-packet")
        assert review.status_code == 200
        assert review.json()["review_packet"]["status"] == "ended"
        assert review.json()["review_packet"]["profit_protect_triggered"] is True
        assert review.json()["review_packet"]["loss_lock_triggered"] is True
        assert review.json()["review_packet"]["final_inventory_flat"] is True

        eligibility = client.get("/api/runtime/test/brc/next-eligibility")
        assert eligibility.status_code == 200
        assert eligibility.json()["eligibility"]["decision"] == "owner_review_required"
        assert eligibility.json()["eligibility"]["next_campaign_allowed"] is False

        draft = client.post(
            "/api/runtime/test/brc/operator/draft",
            json={"text": "帮我看复盘报告"},
        )
        assert draft.status_code == 200
        assert draft.json()["draft"]["action"] == "read_review_packet"
        assert draft.json()["draft"]["mutation_intended"] is False

        plan = client.post(
            "/api/runtime/test/brc/operator/plan",
            json={"text": "帮我看下一轮能不能开"},
        )
        assert plan.status_code == 200
        assert plan.json()["plan"]["executable"] is True
        assert plan.json()["plan"]["steps"][0]["mutation_intended"] is False

        blocked_run = client.post(
            "/api/runtime/test/brc/operator/run",
            json={"text": "帮我看下一轮能不能开", "confirmation_phrase": "WRONG"},
        )
        assert blocked_run.status_code == 409
        assert "confirmation phrase mismatch" in blocked_run.json()["detail"]

        run = client.post(
            "/api/runtime/test/brc/operator/run",
            json={
                "text": "帮我看下一轮能不能开",
                "confirmation_phrase": "CONFIRM_READ_ONLY_BRC",
            },
        )
        assert run.status_code == 200
        assert run.json()["run"]["action"] == "read_next_eligibility"
        assert run.json()["run"]["mutation_executed"] is False
        assert run.json()["run"]["withdrawal_executed"] is False
