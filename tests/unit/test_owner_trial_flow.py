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
    OwnerLiveAuthorizationActivationRequest,
    OwnerRiskAcknowledgementCreateRequest,
    OwnerTrialFlowError,
    OwnerTrialFlowService,
)
from src.infrastructure.owner_trial_flow_repository import PgOwnerTrialFlowRepository
from src.infrastructure.pg_models import (
    PGBrcBoundedLiveTrialAuthorizationORM,
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
        await conn.run_sync(PGBrcBoundedLiveTrialAuthorizationORM.__table__.create)
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


async def _create_valid_draft(service: OwnerTrialFlowService):
    acknowledgement = await _acknowledge_all(service)
    return await service.create_authorization_draft(
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


def _activation_request(**patch):
    payload = {
        "carrier_id": "MI-001-BNB-LONG",
        "symbol": "BNB/USDT:USDT",
        "side": "long",
        "max_notional": "20",
        "quantity": "0.01",
        "leverage": "1",
        "protection_plan_type": "single_tp_plus_sl",
    }
    payload.update(patch)
    return OwnerLiveAuthorizationActivationRequest(**payload)


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


def test_explicit_live_authorization_can_be_activated_without_execution_or_order():
    async def scenario():
        service, engine = await _service()
        try:
            draft = await _create_valid_draft(service)
            authorization = await service.activate_live_authorization(
                draft.draft_id,
                _activation_request(),
                operator_id="owner",
            )
            current = await service.current()

            assert authorization.draft_id == draft.draft_id
            assert authorization.status == "owner_live_authorized_pending_final_preflight"
            assert authorization.live_authorized is True
            assert authorization.single_use is True
            assert authorization.consumed is False
            assert authorization.live_ready is False
            assert authorization.order_permission_granted is False
            assert authorization.execution_permission_granted is False
            assert authorization.execution_intent_created is False
            assert authorization.order_created is False
            assert authorization.next_executable is False
            assert authorization.final_preflight_required is True
            assert authorization.hard_blockers == ["startup_guard_status_unavailable_runtime_not_started"]
            assert current.live_authorization == authorization
            assert current.authorization_status == "owner_live_authorized_pending_final_preflight"
            assert current.hard_blockers[0]["blocker_id"] == "startup_guard_status_unavailable_runtime_not_started"
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_live_authorization_rejects_wrong_scope_duplicate_and_missing_acknowledgement():
    async def scenario():
        service, engine = await _service()
        try:
            draft = await _create_valid_draft(service)
            bad_requests = [
                ("unsupported_carrier", {"carrier_id": "MI-001-SOL-LONG"}),
                ("symbol_mismatch", {"symbol": "SOL/USDT:USDT"}),
                ("side_mismatch", {"side": "short"}),
                ("cap_violation", {"max_notional": "19"}),
                ("cap_violation", {"quantity": "0.009"}),
                ("cap_violation", {"leverage": "0.5"}),
            ]
            for code, patch in bad_requests:
                with pytest.raises(OwnerTrialFlowError) as excinfo:
                    await service.activate_live_authorization(
                        draft.draft_id,
                        _activation_request(**patch),
                    )
                assert excinfo.value.code == code

            await service.activate_live_authorization(
                draft.draft_id,
                _activation_request(),
                operator_id="owner",
            )
            with pytest.raises(OwnerTrialFlowError) as duplicate:
                await service.activate_live_authorization(
                    draft.draft_id,
                    _activation_request(),
                    operator_id="owner",
                )
            assert duplicate.value.code == "live_authorization_already_exists"
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_live_authorization_rejects_draft_without_linked_acknowledgement():
    async def scenario():
        service, engine = await _service()
        try:
            session_maker = service._repository._session_maker
            now = int(time.time() * 1000)
            async with session_maker() as session:
                async with session.begin():
                    session.add(
                        PGBrcBoundedLiveTrialAuthorizationDraftORM(
                            draft_id="draft-orphan",
                            carrier_id="MI-001-BNB-LONG",
                            strategy_family_id="MI-001",
                            symbol="BNB/USDT:USDT",
                            side="long",
                            max_notional="20",
                            quantity="0.01",
                            leverage="1",
                            protection_plan_type="single_tp_plus_sl",
                            single_use=True,
                            status="pending_owner_live_authorization",
                            live_ready=False,
                            order_permission_granted=False,
                            execution_permission_granted=False,
                            execution_intent_created=False,
                            order_created=False,
                            auto_execution_enabled=False,
                            consumed=False,
                            linked_acknowledgement_id="ack-missing",
                            source="owner_console",
                            non_live_metadata_only=True,
                            hard_gate_snapshot_json={},
                            warning_acknowledgement_snapshot_json={},
                            metadata_json={},
                            created_at_ms=now,
                            updated_at_ms=now,
                        )
                    )

            with pytest.raises(OwnerTrialFlowError) as excinfo:
                await service.activate_live_authorization(
                    "draft-orphan",
                    _activation_request(),
                )
            assert excinfo.value.code == "linked_acknowledgement_missing"
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

            authorization = client.post(
                f"/api/brc/owner-trial-flow/authorization-draft/{draft.json()['draft_id']}/activate-live-authorization",
                json={
                    "carrier_id": "MI-001-BNB-LONG",
                    "symbol": "BNB/USDT:USDT",
                    "side": "long",
                    "max_notional": "20",
                    "quantity": "0.01",
                    "leverage": "1",
                    "protection_plan_type": "single_tp_plus_sl",
                },
            )
            assert authorization.status_code == 200
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
    auth_payload = authorization.json()
    assert auth_payload["status"] == "owner_live_authorized_pending_final_preflight"
    assert auth_payload["live_authorized"] is True
    assert auth_payload["final_preflight_required"] is True
    assert auth_payload["next_executable"] is False
    assert auth_payload["execution_intent_created"] is False
    assert auth_payload["order_created"] is False
    assert auth_payload["order_permission_granted"] is False


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
                auth_count = await session.scalar(select(func.count()).select_from(PGBrcBoundedLiveTrialAuthorizationORM))
                tables = (
                    await session.execute(
                        text("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('execution_intents', 'orders')")
                    )
                ).scalars().all()
            assert ack_count == 1
            assert draft_count == 1
            assert auth_count == 0
            assert tables == []
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_owner_trial_flow_mainline_repository_is_pg_only():
    from src.interfaces import api_brc_console

    assert "SqliteOwnerTrialFlowRepository" not in api_brc_console.__dict__
    assert api_brc_console.PgOwnerTrialFlowRepository is PgOwnerTrialFlowRepository
