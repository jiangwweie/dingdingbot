from __future__ import annotations

import asyncio
import json
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.application.owner_trial_flow import (
    BoundedLiveTrialAuthorizationDraftCreateRequest,
    OwnerRiskAcknowledgementCreateRequest,
    OwnerTrialFlowError,
    OwnerTrialFlowService,
)
from src.infrastructure.owner_trial_flow_repository import PgOwnerTrialFlowRepository
from src.infrastructure.pg_models import (
    PGBrcBoundedLiveTrialAuthorizationDraftORM,
    PGBrcOwnerRiskAcknowledgementORM,
)


async def _service() -> tuple[OwnerTrialFlowService, object]:
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
    return OwnerTrialFlowService(PgOwnerTrialFlowRepository(session_maker)), engine


async def _acknowledge_all(service: OwnerTrialFlowService):
    current = await service.current()
    return await service.create_risk_acknowledgement(
        OwnerRiskAcknowledgementCreateRequest(
            carrier_id="MI-001-BNB-LONG",
            acknowledged_warning_codes=[
                str(item["warning_id"])
                for item in current.strategy_warnings
            ],
        ),
        operator_id="owner",
    )


def test_risk_acknowledgement_can_be_persisted_to_pg_for_supported_carrier():
    async def scenario():
        service, engine = await _service()
        try:
            acknowledgement = await service.create_risk_acknowledgement(
                OwnerRiskAcknowledgementCreateRequest(
                    carrier_id="MI-001-BNB-LONG",
                    acknowledged_warning_codes=[
                        "strategy_not_proven_profitable",
                        "limited_live_observation_sample",
                    ],
                ),
                operator_id="owner",
            )
            current = await service.current()

            assert acknowledgement.carrier_id == "MI-001-BNB-LONG"
            assert acknowledgement.strategy_family_id == "MI-001"
            assert acknowledgement.non_live_metadata_only is True
            assert acknowledgement.acknowledged_warning_codes == [
                "strategy_not_proven_profitable",
                "limited_live_observation_sample",
            ]
            assert current.latest_acknowledgement == acknowledgement
            assert "strategy_not_proven_profitable" in current.acknowledged_warnings
            assert current.authorization_draft is None
            assert current.live_ready is False
            assert current.execution_intent_created is False
            assert current.order_created is False
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_authorization_draft_can_be_persisted_to_pg_after_full_acknowledgement():
    async def scenario():
        service, engine = await _service()
        try:
            acknowledgement = await _acknowledge_all(service)
            draft = await service.create_authorization_draft(
                BoundedLiveTrialAuthorizationDraftCreateRequest(
                    carrier_id="MI-001-BNB-LONG",
                    linked_acknowledgement_id=acknowledgement.acknowledgement_id,
                    symbol="BNB/USDT:USDT",
                    side="long",
                    max_notional="20",
                    quantity="0.01",
                    leverage="1",
                    protection_plan_type="single_tp_plus_sl",
                ),
                operator_id="owner",
            )
            current = await service.current()
            fetched = await service.get_draft(draft.draft_id)

            assert fetched == draft
            assert draft.status == "pending_owner_live_authorization"
            assert draft.live_ready is False
            assert draft.order_permission_granted is False
            assert draft.execution_permission_granted is False
            assert draft.execution_intent_created is False
            assert draft.order_created is False
            assert draft.auto_execution_enabled is False
            assert draft.consumed is False
            assert current.authorization_draft == draft
            assert current.authorization_status == "pending_owner_live_authorization"
            assert current.hard_blockers[0]["blocker_id"] == "missing_explicit_live_authorization"
            assert current.unacknowledged_warnings == []
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_authorization_draft_rejects_unsupported_carrier_wrong_scope_and_cap():
    async def scenario():
        service, engine = await _service()
        try:
            with pytest.raises(OwnerTrialFlowError, match="Unsupported owner trial carrier"):
                await service.create_risk_acknowledgement(
                    OwnerRiskAcknowledgementCreateRequest(
                        carrier_id="MI-001-SOL-LONG",
                        acknowledged_warning_codes=["strategy_not_proven_profitable"],
                    )
                )

            acknowledgement = await _acknowledge_all(service)
            bad_requests = [
                ("symbol_mismatch", {"symbol": "SOL/USDT:USDT", "side": "long", "max_notional": "20", "quantity": "0.01", "leverage": "1"}),
                ("side_mismatch", {"symbol": "BNB/USDT:USDT", "side": "short", "max_notional": "20", "quantity": "0.01", "leverage": "1"}),
                ("cap_violation", {"symbol": "BNB/USDT:USDT", "side": "long", "max_notional": "21", "quantity": "0.01", "leverage": "1"}),
                ("cap_violation", {"symbol": "BNB/USDT:USDT", "side": "long", "max_notional": "20", "quantity": "0.02", "leverage": "1"}),
            ]
            for code, patch in bad_requests:
                with pytest.raises(OwnerTrialFlowError) as excinfo:
                    await service.create_authorization_draft(
                        BoundedLiveTrialAuthorizationDraftCreateRequest(
                            carrier_id="MI-001-BNB-LONG",
                            linked_acknowledgement_id=acknowledgement.acknowledgement_id,
                            protection_plan_type="single_tp_plus_sl",
                            **patch,
                        )
                    )
                assert excinfo.value.code == code
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_incomplete_acknowledgement_cannot_create_authorization_draft():
    async def scenario():
        service, engine = await _service()
        try:
            acknowledgement = await service.create_risk_acknowledgement(
                OwnerRiskAcknowledgementCreateRequest(
                    carrier_id="MI-001-BNB-LONG",
                    acknowledged_warning_codes=["strategy_not_proven_profitable"],
                )
            )

            with pytest.raises(OwnerTrialFlowError) as excinfo:
                await service.create_authorization_draft(
                    BoundedLiveTrialAuthorizationDraftCreateRequest(
                        carrier_id="MI-001-BNB-LONG",
                        linked_acknowledgement_id=acknowledgement.acknowledgement_id,
                        symbol="BNB/USDT:USDT",
                        side="long",
                        max_notional="20",
                        quantity="0.01",
                        leverage="1",
                        protection_plan_type="single_tp_plus_sl",
                    )
                )
            assert excinfo.value.code == "strategy_warning_acknowledgement_incomplete"
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_owner_trial_flow_api_persists_pg_metadata_without_execution_or_order(monkeypatch):
    from src.interfaces import api_brc_console
    from src.interfaces.api import app
    from src.interfaces.operator_auth import OperatorSession, require_operator_session

    service, engine = asyncio.run(_service())
    api_brc_console._owner_trial_flow_service = service
    app.dependency_overrides[require_operator_session] = lambda: OperatorSession(
        username="owner",
        expires_at=int(time.time()) + 3600,
    )

    try:
        with TestClient(app) as client:
            current = client.get("/api/brc/owner-trial-flow/current")
            assert current.status_code == 200
            warning_codes = [item["warning_id"] for item in current.json()["strategy_warnings"]]

            ack = client.post(
                "/api/brc/owner-trial-flow/risk-acknowledgement",
                json={
                    "carrier_id": "MI-001-BNB-LONG",
                    "acknowledged_warning_codes": warning_codes,
                },
            )
            assert ack.status_code == 200

            draft = client.post(
                "/api/brc/owner-trial-flow/authorization-draft",
                json={
                    "carrier_id": "MI-001-BNB-LONG",
                    "linked_acknowledgement_id": ack.json()["acknowledgement_id"],
                    "symbol": "BNB/USDT:USDT",
                    "side": "long",
                    "max_notional": "20",
                    "quantity": "0.01",
                    "leverage": "1",
                    "protection_plan_type": "single_tp_plus_sl",
                },
            )
            assert draft.status_code == 200
    finally:
        app.dependency_overrides.pop(require_operator_session, None)
        api_brc_console._owner_trial_flow_service = None
        asyncio.run(engine.dispose())

    payload = draft.json()
    assert payload["status"] == "pending_owner_live_authorization"
    assert payload["live_ready"] is False
    assert payload["order_permission_granted"] is False
    assert payload["execution_permission_granted"] is False
    assert payload["execution_intent_created"] is False
    assert payload["order_created"] is False
    raw_payload = json.dumps(payload)
    assert "place_order" not in raw_payload
    assert "ExecutionIntent" not in raw_payload


def test_owner_trial_flow_pg_repository_does_not_create_execution_intent_or_order():
    async def scenario():
        service, engine = await _service()
        try:
            acknowledgement = await _acknowledge_all(service)
            await service.create_authorization_draft(
                BoundedLiveTrialAuthorizationDraftCreateRequest(
                    carrier_id="MI-001-BNB-LONG",
                    linked_acknowledgement_id=acknowledgement.acknowledgement_id,
                    symbol="BNB/USDT:USDT",
                    side="long",
                    max_notional="20",
                    quantity="0.01",
                    leverage="1",
                    protection_plan_type="single_tp_plus_sl",
                ),
                operator_id="owner",
            )
            session_maker = service._repository._session_maker
            async with session_maker() as session:
                ack_count = await session.scalar(select(func.count()).select_from(PGBrcOwnerRiskAcknowledgementORM))
                draft_count = await session.scalar(select(func.count()).select_from(PGBrcBoundedLiveTrialAuthorizationDraftORM))
                tables = (
                    await session.execute(
                        text("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('execution_intents', 'orders')")
                    )
                ).scalars().all()
            assert ack_count == 1
            assert draft_count == 1
            assert tables == []
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_owner_trial_flow_mainline_repository_is_pg_only():
    from src.interfaces import api_brc_console

    assert "SqliteOwnerTrialFlowRepository" not in api_brc_console.__dict__
    assert api_brc_console.PgOwnerTrialFlowRepository is PgOwnerTrialFlowRepository
