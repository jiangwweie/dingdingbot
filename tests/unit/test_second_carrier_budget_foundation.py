from __future__ import annotations

import asyncio
import json
import time
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.application.multi_carrier_budget_authorization import (
    MultiCarrierBudgetAuthorizationCreateRequest,
    MultiCarrierBudgetAuthorizationError,
    MultiCarrierBudgetAuthorizationService,
)
from src.application.strategy_trial_carrier_expansion import (
    build_second_carrier_expansion_bootstrap,
)
from src.infrastructure.pg_models import (
    PGBrcBoundedLiveTrialAuthorizationORM,
    PGBrcBoundedLiveTrialAuthorizationDraftORM,
    PGBrcMultiCarrierBudgetAuthorizationORM,
    PGBrcOwnerRiskAcknowledgementORM,
)
from src.infrastructure.pg_multi_carrier_budget_authorization_repository import (
    PgMultiCarrierBudgetAuthorizationRepository,
)


async def _service() -> tuple[MultiCarrierBudgetAuthorizationService, object]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_maker = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(PGBrcOwnerRiskAcknowledgementORM.__table__.create)
        await conn.run_sync(PGBrcBoundedLiveTrialAuthorizationDraftORM.__table__.create)
        await conn.run_sync(PGBrcBoundedLiveTrialAuthorizationORM.__table__.create)
        await conn.run_sync(PGBrcMultiCarrierBudgetAuthorizationORM.__table__.create)
    return MultiCarrierBudgetAuthorizationService(
        PgMultiCarrierBudgetAuthorizationRepository(session_maker),
    ), engine


def _valid_budget_request(**patch):
    payload = {
        "allowed_carrier_ids": ["MI-001-BNB-LONG", "TB-BTC-SHORT"],
        "per_carrier_caps": {
            "MI-001-BNB-LONG": Decimal("20"),
            "TB-BTC-SHORT": Decimal("20"),
        },
        "global_budget": Decimal("30"),
        "max_attempts": 2,
        "daily_loss_limit": Decimal("20"),
        "max_concurrent_positions": 1,
        "cooldown_seconds": 3600,
        "valid_from_ms": 1_800_000_000_000,
        "valid_until_ms": 1_800_086_400_000,
    }
    payload.update(patch)
    return MultiCarrierBudgetAuthorizationCreateRequest(**payload)


def test_second_carrier_expansion_represents_tb_btc_short_generically():
    expansion = build_second_carrier_expansion_bootstrap()

    assert expansion.first_carrier_id == "MI-001-BNB-LONG"
    assert expansion.selected_second_carrier_id == "TB-BTC-SHORT"
    assert expansion.generic_chain == [
        "StrategyFamily",
        "Carrier",
        "RiskCapProfile",
        "ProtectionPlan",
        "Trial",
    ]

    carriers = {carrier.carrier_id: carrier for carrier in expansion.carriers}
    second = carriers["TB-BTC-SHORT"]
    assert second.strategy_family == "TB"
    assert second.symbol == "BTCUSDT"
    assert second.runtime_symbol == "BTC/USDT:USDT"
    assert second.side == "short"
    assert second.role == "second_carrier_bootstrap"
    assert second.risk_cap_draft.per_carrier_cap == Decimal("20")
    assert second.protection_feasibility.protection_plan_type == "single_tp_plus_sl"
    assert second.observation_readiness_state == "metadata_ready_observation_gap_disclosed"
    assert second.evidence_gap_warning is True
    assert second.budget_foundation_eligible is True
    assert any("No TB-BTC-SHORT controlled testnet" in item for item in second.testnet_rehearsal_gap_summary)

    assert carriers["MI-001-BNB-LONG"].role == "first_carrier"
    assert carriers["MI-001-SOL-LONG"].budget_foundation_eligible is False
    assert expansion.non_permissions["execution_intent_created"] is False
    assert expansion.non_permissions["order_created"] is False
    assert expansion.non_permissions["live_ready"] is False


def test_budget_authorization_foundation_persists_pg_metadata_without_execution_or_order():
    async def scenario():
        service, engine = await _service()
        try:
            budget = await service.create_foundation(_valid_budget_request())
            current = await service.current()
            session_maker = service._repository._session_maker
            async with session_maker() as session:
                budget_count = await session.scalar(
                    select(func.count()).select_from(PGBrcMultiCarrierBudgetAuthorizationORM)
                )
                tables = (
                    await session.execute(
                        text("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('execution_intents', 'orders')")
                    )
                ).scalars().all()

            assert budget_count == 1
            assert current.latest_budget_authorization == budget
            assert budget.budget_authorization_id.startswith("budget-")
            assert {scope.carrier_id for scope in budget.allowed_carriers} == {
                "MI-001-BNB-LONG",
                "TB-BTC-SHORT",
            }
            assert budget.global_budget == Decimal("30")
            assert budget.max_attempts == 2
            assert budget.daily_loss_limit == Decimal("20")
            assert budget.max_concurrent_positions == 1
            assert budget.cooldown_seconds == 3600
            assert budget.status == "draft_disabled_pending_owner_authorization"
            assert budget.live_ready is False
            assert budget.auto_execution_enabled is False
            assert budget.order_permission_granted is False
            assert budget.execution_permission_granted is False
            assert budget.execution_intent_created is False
            assert budget.order_created is False
            assert current.disabled_execution_state["auto_execution_enabled"] is False
            assert tables == []
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_budget_authorization_rejects_bnb_only_and_unsafe_carrier_scope():
    async def scenario():
        service, engine = await _service()
        try:
            with pytest.raises(MultiCarrierBudgetAuthorizationError) as bnb_only:
                await service.create_foundation(
                    _valid_budget_request(
                        allowed_carrier_ids=["MI-001-BNB-LONG"],
                        per_carrier_caps={"MI-001-BNB-LONG": Decimal("20")},
                    )
                )
            assert bnb_only.value.code == "budget_scope_too_narrow"

            with pytest.raises(MultiCarrierBudgetAuthorizationError) as unsafe:
                await service.create_foundation(
                    _valid_budget_request(
                        allowed_carrier_ids=["MI-001-BNB-LONG", "MI-001-SOL-LONG"],
                        per_carrier_caps={
                            "MI-001-BNB-LONG": Decimal("20"),
                            "MI-001-SOL-LONG": Decimal("20"),
                        },
                    )
                )
            assert unsafe.value.code == "unsupported_or_unsafe_carrier_scope"
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_budget_authorization_api_exposes_disabled_pg_scope(monkeypatch):
    from src.interfaces import api_brc_console
    from src.interfaces.api import app
    from src.interfaces.operator_auth import OperatorSession, require_operator_session

    service, engine = asyncio.run(_service())
    api_brc_console._multi_carrier_budget_authorization_service = service
    app.dependency_overrides[require_operator_session] = lambda: OperatorSession(
        username="owner",
        expires_at=int(time.time()) + 3600,
    )

    try:
        with TestClient(app) as client:
            expansion = client.get("/api/brc/strategy-trial-architecture/second-carrier-expansion")
            assert expansion.status_code == 200
            created = client.post(
                "/api/brc/budget-authorizations/foundation",
                json={
                    "allowed_carrier_ids": ["MI-001-BNB-LONG", "TB-BTC-SHORT"],
                    "per_carrier_caps": {
                        "MI-001-BNB-LONG": "20",
                        "TB-BTC-SHORT": "20",
                    },
                    "global_budget": "30",
                    "max_attempts": 2,
                    "daily_loss_limit": "20",
                    "max_concurrent_positions": 1,
                    "cooldown_seconds": 3600,
                    "valid_from_ms": 1800000000000,
                    "valid_until_ms": 1800086400000,
                },
            )
            assert created.status_code == 200
            current = client.get("/api/brc/budget-authorizations/current")
            assert current.status_code == 200

            unsafe = client.post(
                "/api/brc/budget-authorizations/foundation",
                json={
                    "allowed_carrier_ids": ["MI-001-BNB-LONG", "MI-001-SOL-LONG"],
                    "per_carrier_caps": {
                        "MI-001-BNB-LONG": "20",
                        "MI-001-SOL-LONG": "20",
                    },
                    "global_budget": "30",
                    "max_attempts": 2,
                    "daily_loss_limit": "20",
                    "max_concurrent_positions": 1,
                    "cooldown_seconds": 3600,
                },
            )
            assert unsafe.status_code == 400
    finally:
        app.dependency_overrides.pop(require_operator_session, None)
        api_brc_console._multi_carrier_budget_authorization_service = None
        asyncio.run(engine.dispose())

    expansion_payload = expansion.json()
    assert expansion_payload["selected_second_carrier_id"] == "TB-BTC-SHORT"
    assert expansion_payload["non_permissions"]["execution_intent_created"] is False

    created_payload = created.json()
    assert created_payload["status"] == "draft_disabled_pending_owner_authorization"
    assert {item["carrier_id"] for item in created_payload["allowed_carriers"]} == {
        "MI-001-BNB-LONG",
        "TB-BTC-SHORT",
    }
    assert created_payload["live_ready"] is False
    assert created_payload["auto_execution_enabled"] is False
    assert created_payload["order_permission_granted"] is False
    assert created_payload["execution_permission_granted"] is False
    assert created_payload["execution_intent_created"] is False
    assert created_payload["order_created"] is False

    current_payload = current.json()
    assert current_payload["budget_scope_source"] == "pg_metadata"
    assert current_payload["latest_budget_authorization"]["budget_authorization_id"] == created_payload["budget_authorization_id"]
    assert current_payload["disabled_execution_state"]["execution_intent_created"] is False

    raw_payload = json.dumps({"created": created_payload, "current": current_payload})
    assert "execution_intent_created\": true" not in raw_payload
    assert "order_created\": true" not in raw_payload
    assert "auto_execution_enabled\": true" not in raw_payload
