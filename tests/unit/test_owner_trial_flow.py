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

from src.application.owner_trial_flow import (
    BoundedLiveTrialAuthorizationDraftCreateRequest,
    OwnerLiveAuthorizationActivationRequest,
    OwnerRiskAcknowledgementCreateRequest,
    OwnerTrialFlowError,
    OwnerTrialFlowService,
)
from src.application.bnb_live_execution_bridge import (
    BnbLiveExecutionBridgeDryRunRequest,
    BnbLiveExecutionBridgeDryRunService,
)
from src.application.strategy_trial_preflight_facts import (
    TrialPreflightFact,
    TrialPreflightFactsSnapshot,
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


async def _bridge_service() -> tuple[OwnerTrialFlowService, BnbLiveExecutionBridgeDryRunService, object]:
    service, engine = await _service()
    session_maker = service._repository._session_maker
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "CREATE TABLE orders ("
                "id TEXT PRIMARY KEY, signal_id TEXT NOT NULL, symbol TEXT NOT NULL"
                ")"
            )
        )
        await conn.execute(
            text(
                "CREATE TABLE execution_intents ("
                "id TEXT PRIMARY KEY, signal_id TEXT NOT NULL, symbol TEXT NOT NULL, "
                "status TEXT NOT NULL"
                ")"
            )
        )
        await conn.execute(
            text(
                "CREATE TABLE brc_execution_results ("
                "operation_id TEXT PRIMARY KEY, status TEXT NOT NULL"
                ")"
            )
        )
    bridge = BnbLiveExecutionBridgeDryRunService(
        owner_trial_flow_service=service,
        session_maker=session_maker,
        env={
            "TRADING_ENV": "live",
            "EXCHANGE_TESTNET": "false",
            "RUNTIME_CONTROL_API_ENABLED": "false",
            "RUNTIME_TEST_SIGNAL_INJECTION_ENABLED": "false",
            "BRC_EXECUTION_PERMISSION_MAX": "read_only",
        },
    )
    return service, bridge, engine


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


def _clear_fact_snapshot(
    *,
    startup_guard_clear: bool = False,
    startup_guard_armed: bool = True,
    active_position_count: int = 0,
    open_order_count: int = 0,
    gks_active: bool = False,
    account_freshness: str = "fresh",
    account_read_only_guarantee: bool = True,
    omit_fact_ids: set[str] | None = None,
) -> TrialPreflightFactsSnapshot:
    now = int(time.time() * 1000)
    startup_guard = (
        TrialPreflightFact(
            fact_id="startup_guard",
            status="clear",
            source="test_startup_guard",
            blocking=False,
            observed_at_ms=now,
            evidence={"armed": startup_guard_armed},
        )
        if startup_guard_clear
        else TrialPreflightFact(
            fact_id="startup_guard",
            status="unavailable",
            source="unavailable",
            blocking=True,
            blocker="startup_guard_status_required_before_rehearsal",
            blockers=["startup_guard_status_required_before_rehearsal"],
            observed_at_ms=now,
        )
    )
    facts = [
        TrialPreflightFact(
            fact_id="active_position",
            status="clear",
            source="test_position_reader",
            blocking=False,
            observed_at_ms=now,
            evidence={"active_position_count": active_position_count},
        ),
        TrialPreflightFact(
            fact_id="open_order",
            status="clear",
            source="test_order_reader",
            blocking=False,
            observed_at_ms=now,
            evidence={"open_order_count": open_order_count},
        ),
        TrialPreflightFact(
            fact_id="gks",
            status="clear",
            source="test_gks_reader",
            blocking=False,
            observed_at_ms=now,
            evidence={"active": gks_active},
        ),
        startup_guard,
        TrialPreflightFact(
            fact_id="reconciliation",
            status="clear",
            source="test_reconciliation",
            blocking=False,
            observed_at_ms=now,
            evidence={"status": "clean", "failed_reconciliations_count": 0},
        ),
        TrialPreflightFact(
            fact_id="account_facts",
            status="clear",
            source="test_live_read_only_account_facts",
            blocking=False,
            observed_at_ms=now,
            evidence={
                "freshness": account_freshness,
                "equity_available": True,
                "available_margin_available": True,
                "read_only_guarantee": account_read_only_guarantee,
            },
        ),
    ]
    if omit_fact_ids:
        facts = [fact for fact in facts if fact.fact_id not in omit_fact_ids]
    return TrialPreflightFactsSnapshot(
        generated_at_ms=now,
        candidate_id="MI-001-BNB-LONG",
        symbol="BNB/USDT:USDT",
        side="long",
        facts=facts,
    )


def _replace_fact(
    snapshot: TrialPreflightFactsSnapshot,
    replacement: TrialPreflightFact,
) -> TrialPreflightFactsSnapshot:
    return TrialPreflightFactsSnapshot(
        generated_at_ms=snapshot.generated_at_ms,
        candidate_id=snapshot.candidate_id,
        symbol=snapshot.symbol,
        side=snapshot.side,
        facts=[
            replacement if fact.fact_id == replacement.fact_id else fact
            for fact in snapshot.facts
        ],
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


def test_bnb_live_execution_bridge_blocks_without_explicit_authorization_and_creates_nothing():
    async def scenario():
        service, bridge, engine = await _bridge_service()
        try:
            result = await bridge.run(fact_snapshot=_clear_fact_snapshot(startup_guard_clear=True))
            assert result.bridge_status == "blocked_before_execution_boundary"
            assert "missing_explicit_owner_live_authorization" in result.hard_blockers
            assert result.table_audit.execution_intents is True
            assert result.table_audit.orders is True
            assert result.table_audit.brc_execution_results is True
            assert result.non_permissions["execution_intent_created"] is False
            assert result.non_permissions["order_created"] is False
            assert result.authorization_state.exists is False
            assert result.final_gate_read_model.result == "blocked"
            assert result.final_gate_read_model.execution_boundary_status == "blocked_before_execution_boundary"
            assert result.final_gate_read_model.no_order_created is True
            assert result.final_gate_read_model.no_executable_execution_intent_created is True
            assert result.final_gate_read_model.no_permission_granted is True
            assert result.execution_boundary["would_create_execution_intent_if_all_gates_passed"] is False
            assert result.execution_boundary["would_create_order"] is False

            session_maker = service._repository._session_maker
            async with session_maker() as session:
                intent_count = await session.scalar(text("SELECT count(*) FROM execution_intents"))
                order_count = await session.scalar(text("SELECT count(*) FROM orders"))
            assert intent_count == 0
            assert order_count == 0
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_bnb_live_execution_bridge_uses_authorization_but_stops_on_startup_guard():
    async def scenario():
        service, bridge, engine = await _bridge_service()
        try:
            draft = await _create_valid_draft(service)
            await service.activate_live_authorization(
                draft.draft_id,
                _activation_request(),
                operator_id="owner",
            )

            result = await bridge.run(fact_snapshot=_clear_fact_snapshot())

            assert result.bridge_status == "blocked_before_execution_boundary"
            assert result.final_preflight_result == "blocked"
            assert "startup_guard_status_unavailable_runtime_not_started" not in result.hard_blockers
            assert (
                "startup_guard_status_unavailable_runtime_not_started"
                in result.authorization_hard_blockers_snapshot
            )
            assert "startup_guard_status_required_before_rehearsal" in result.hard_blockers
            assert result.authorization_state.exists is True
            assert result.authorization_state.status == "owner_live_authorized_pending_final_preflight"
            assert result.authorization_state.single_use is True
            assert result.authorization_state.unconsumed is True
            assert result.final_gate_read_model.result == "blocked"
            assert result.final_gate_read_model.runtime_safety_state == "startup_guard_unavailable"
            assert result.final_gate_read_model.startup_guard.state == "unavailable"
            assert result.final_gate_read_model.gks.state == "clear"
            assert result.acknowledged_strategy_warnings
            assert result.strategy_warnings_block_execution is False
            assert result.non_permissions["execution_permission_granted"] is False
            assert result.non_permissions["order_permission_granted"] is False
            assert result.non_permissions["execution_intent_created"] is False
            assert result.non_permissions["order_created"] is False

            session_maker = service._repository._session_maker
            async with session_maker() as session:
                intent_count = await session.scalar(text("SELECT count(*) FROM execution_intents"))
                order_count = await session.scalar(text("SELECT count(*) FROM orders"))
            assert intent_count == 0
            assert order_count == 0
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_bnb_live_execution_bridge_blocks_startup_guard_not_armed_and_gks_blocked():
    async def scenario():
        service, bridge, engine = await _bridge_service()
        try:
            draft = await _create_valid_draft(service)
            await service.activate_live_authorization(
                draft.draft_id,
                _activation_request(),
                operator_id="owner",
            )

            result = await bridge.run(
                fact_snapshot=_clear_fact_snapshot(
                    startup_guard_clear=True,
                    startup_guard_armed=False,
                    gks_active=True,
                )
            )

            assert result.bridge_status == "blocked_before_execution_boundary"
            assert "startup_guard_not_armed" in result.hard_blockers
            assert "gks_active" in result.hard_blockers
            assert result.final_gate_read_model.runtime_safety_state == "startup_guard_not_armed"
            assert result.final_gate_read_model.startup_guard.state == "not_armed"
            assert result.final_gate_read_model.gks.state == "blocked"
            assert result.final_gate_read_model.no_executable_execution_intent_created is True
            assert result.final_gate_read_model.no_order_created is True

            session_maker = service._repository._session_maker
            async with session_maker() as session:
                intent_count = await session.scalar(text("SELECT count(*) FROM execution_intents"))
                order_count = await session.scalar(text("SELECT count(*) FROM orders"))
            assert intent_count == 0
            assert order_count == 0
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_bnb_live_execution_bridge_blocks_startup_guard_not_started():
    async def scenario():
        service, bridge, engine = await _bridge_service()
        try:
            draft = await _create_valid_draft(service)
            await service.activate_live_authorization(
                draft.draft_id,
                _activation_request(),
                operator_id="owner",
            )
            now = int(time.time() * 1000)
            snapshot = _replace_fact(
                _clear_fact_snapshot(startup_guard_clear=True),
                TrialPreflightFact(
                    fact_id="startup_guard",
                    status="unavailable",
                    source="test_runtime_safety_reader",
                    blocking=True,
                    blocker="startup_guard_runtime_not_started",
                    blockers=["startup_guard_runtime_not_started"],
                    observed_at_ms=now,
                    evidence={"runtime_started": False, "runtime_state": "not_started"},
                ),
            )

            result = await bridge.run(fact_snapshot=snapshot)

            assert result.bridge_status == "blocked_before_execution_boundary"
            assert "startup_guard_runtime_not_started" in result.hard_blockers
            assert "startup_guard_not_started" in result.hard_blockers
            assert result.final_gate_read_model.runtime_safety_state == "startup_guard_not_started"
            assert result.final_gate_read_model.startup_guard.state == "not_started"
            assert result.final_gate_read_model.no_executable_execution_intent_created is True
            assert result.final_gate_read_model.no_order_created is True
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_bnb_live_execution_bridge_blocks_startup_guard_blocked_separately_from_not_armed():
    async def scenario():
        service, bridge, engine = await _bridge_service()
        try:
            draft = await _create_valid_draft(service)
            await service.activate_live_authorization(
                draft.draft_id,
                _activation_request(),
                operator_id="owner",
            )
            now = int(time.time() * 1000)
            snapshot = _replace_fact(
                _clear_fact_snapshot(startup_guard_clear=True),
                TrialPreflightFact(
                    fact_id="startup_guard",
                    status="blocked",
                    source="test_startup_guard_reader",
                    blocking=True,
                    blocker="startup_guard_blocked",
                    blockers=["startup_guard_blocked"],
                    observed_at_ms=now,
                    evidence={"armed": True, "blocked": True},
                ),
            )

            result = await bridge.run(fact_snapshot=snapshot)

            assert result.bridge_status == "blocked_before_execution_boundary"
            assert "startup_guard_blocked" in result.hard_blockers
            assert "startup_guard_not_armed" not in result.hard_blockers
            assert result.final_gate_read_model.runtime_safety_state == "startup_guard_blocked"
            assert result.final_gate_read_model.startup_guard.state == "blocked"
            assert result.final_gate_read_model.gks.state == "clear"
            assert result.non_permissions["execution_intent_created"] is False
            assert result.non_permissions["order_created"] is False
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_bnb_live_execution_bridge_blocks_gks_unavailable():
    async def scenario():
        service, bridge, engine = await _bridge_service()
        try:
            draft = await _create_valid_draft(service)
            await service.activate_live_authorization(
                draft.draft_id,
                _activation_request(),
                operator_id="owner",
            )
            now = int(time.time() * 1000)
            snapshot = _replace_fact(
                _clear_fact_snapshot(startup_guard_clear=True),
                TrialPreflightFact(
                    fact_id="gks",
                    status="unavailable",
                    source="unavailable",
                    blocking=True,
                    blocker="gks_status_required_before_rehearsal",
                    blockers=["gks_status_required_before_rehearsal"],
                    observed_at_ms=now,
                ),
            )

            result = await bridge.run(fact_snapshot=snapshot)

            assert result.bridge_status == "blocked_before_execution_boundary"
            assert "gks_status_required_before_rehearsal" in result.hard_blockers
            assert result.execution_plan_preview.status == "preview_blocked_by_hard_gates"
            assert "gks_status_required_before_rehearsal" in result.execution_plan_preview.exact_blockers
            assert result.execution_plan_preview.flags.preview_only is True
            assert result.execution_plan_preview.flags.execution_intent_created is False
            assert result.execution_plan_preview.flags.order_created is False
            assert result.final_gate_read_model.runtime_safety_state == "gks_unavailable"
            assert result.final_gate_read_model.startup_guard.state == "clear"
            assert result.final_gate_read_model.gks.state == "unavailable"
            assert result.non_permissions["execution_permission_granted"] is False
            assert result.non_permissions["order_permission_granted"] is False
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_bnb_live_execution_bridge_blocks_fact_conflicts_and_missing_tables():
    async def scenario():
        service, engine = await _service()
        bridge = BnbLiveExecutionBridgeDryRunService(
            owner_trial_flow_service=service,
            session_maker=service._repository._session_maker,
            env={
                "TRADING_ENV": "live",
                "EXCHANGE_TESTNET": "false",
                "RUNTIME_CONTROL_API_ENABLED": "false",
                "RUNTIME_TEST_SIGNAL_INJECTION_ENABLED": "false",
                "BRC_EXECUTION_PERMISSION_MAX": "read_only",
            },
        )
        try:
            draft = await _create_valid_draft(service)
            await service.activate_live_authorization(
                draft.draft_id,
                _activation_request(),
                operator_id="owner",
            )

            result = await bridge.run(
                fact_snapshot=_clear_fact_snapshot(
                    startup_guard_clear=True,
                    active_position_count=1,
                    open_order_count=2,
                    gks_active=True,
                    account_freshness="stale",
                    account_read_only_guarantee=False,
                    omit_fact_ids={"startup_guard"},
                )
            )

            assert result.bridge_status == "blocked_before_execution_boundary"
            assert "active_position_conflict" in result.hard_blockers
            assert "open_order_conflict" in result.hard_blockers
            assert "gks_active" in result.hard_blockers
            assert "account_facts_not_fresh" in result.hard_blockers
            assert "account_facts_read_only_unverified" in result.hard_blockers
            assert "startup_guard_fact_missing" in result.hard_blockers
            assert "execution_intents_table_missing" in result.hard_blockers
            assert "orders_table_missing" in result.hard_blockers
            assert "result_logging_table_missing" in result.hard_blockers
            assert result.final_gate_read_model.runtime_safety_state == "startup_guard_missing"
            assert result.final_gate_read_model.bnb_position.state == "conflict"
            assert result.final_gate_read_model.bnb_open_order.state == "conflict"
            assert result.final_gate_read_model.gks.state == "blocked"
            assert result.final_gate_read_model.account_facts.state == "stale"
            assert result.final_gate_read_model.startup_guard.state == "missing"
            assert result.final_gate_read_model.persistence_readiness.execution_intents is False
            assert result.final_gate_read_model.persistence_readiness.orders is False
            assert result.final_gate_read_model.persistence_readiness.result_review_logging is False
            assert result.non_permissions["execution_permission_granted"] is False
            assert result.non_permissions["order_permission_granted"] is False
            assert result.non_permissions["execution_intent_created"] is False
            assert result.non_permissions["order_created"] is False
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_bnb_live_execution_bridge_reaches_dry_run_boundary_without_executable_state():
    async def scenario():
        service, bridge, engine = await _bridge_service()
        try:
            draft = await _create_valid_draft(service)
            await service.activate_live_authorization(
                draft.draft_id,
                _activation_request(),
                operator_id="owner",
            )

            result = await bridge.run(fact_snapshot=_clear_fact_snapshot(startup_guard_clear=True))

            assert result.bridge_status == "dry_run_reached_execution_boundary"
            assert result.final_preflight_result == "passed"
            assert result.hard_blockers == []
            assert result.authorization_state.exists is True
            assert result.authorization_state.live_authorized is True
            assert result.authorization_state.live_ready is False
            assert result.authorization_state.execution_permission_granted is False
            assert result.authorization_state.order_permission_granted is False
            assert (
                result.authorization_hard_blockers_snapshot
                == ["startup_guard_status_unavailable_runtime_not_started"]
            )
            assert result.final_gate_read_model.result == "passed"
            assert result.final_gate_read_model.runtime_safety_state == "clear"
            assert result.final_gate_read_model.startup_guard.state == "clear"
            assert result.final_gate_read_model.gks.state == "clear"
            assert result.final_gate_read_model.account_facts.state == "clear"
            assert result.final_gate_read_model.bnb_position.state == "clear"
            assert result.final_gate_read_model.bnb_open_order.state == "clear"
            assert result.final_gate_read_model.persistence_readiness.execution_intents is True
            assert result.final_gate_read_model.persistence_readiness.orders is True
            assert result.final_gate_read_model.persistence_readiness.result_review_logging is True
            assert result.acknowledged_strategy_warnings
            assert result.strategy_warnings_block_execution is False
            assert result.owner_execution_trigger.visible is True
            assert result.owner_execution_trigger.enabled is False
            assert result.owner_execution_trigger.status == "blocked_execution_endpoint_not_available"
            assert result.owner_execution_trigger.endpoint is None
            assert result.owner_execution_trigger.creates_execution_intent_on_click is False
            assert result.owner_execution_trigger.creates_order_on_click is False
            assert result.owner_execution_trigger.order_permission_granted is False
            assert result.owner_execution_trigger.exact_scope == {
                "carrier_id": "MI-001-BNB-LONG",
                "symbol": "BNB/USDT:USDT",
                "side": "long",
                "quantity": "0.01",
                "max_notional": "20",
                "leverage": "1",
                "protection_plan_type": "single_tp_plus_sl",
            }
            assert result.execution_plan_preview.status == "preview_ready"
            assert result.execution_plan_preview.authorization_id is not None
            assert result.execution_plan_preview.draft_id == draft.draft_id
            assert result.execution_plan_preview.carrier_id == "MI-001-BNB-LONG"
            assert result.execution_plan_preview.symbol == "BNB/USDT:USDT"
            assert result.execution_plan_preview.side == "long"
            assert result.execution_plan_preview.max_notional == Decimal("20")
            assert result.execution_plan_preview.quantity == Decimal("0.01")
            assert result.execution_plan_preview.leverage == Decimal("1")
            assert result.execution_plan_preview.entry_order.order_type == "market"
            assert result.execution_plan_preview.entry_order.quantity == Decimal("0.01")
            assert result.execution_plan_preview.protection_plan.plan_type == "single_tp_plus_sl"
            assert result.execution_plan_preview.protection_plan.take_profit_quantity == Decimal("0.01")
            assert result.execution_plan_preview.protection_plan.stop_loss_quantity == Decimal("0.01")
            assert result.execution_plan_preview.expected_record_path == [
                "pg_execution_intents_non_preview_only_after_separate_executable_authorization",
                "pg_orders_after_exchange_write_boundary_only",
                "pg_brc_execution_results",
                "owner_review_record",
            ]
            assert result.execution_plan_preview.expected_review_state == (
                "pending_owner_review_after_execution_result"
            )
            assert result.execution_plan_preview.flags.preview_only is True
            assert result.execution_plan_preview.flags.execution_intent_created is False
            assert result.execution_plan_preview.flags.order_created is False
            assert result.execution_plan_preview.flags.order_permission_granted is False
            assert result.execution_plan_preview.flags.auto_execution_enabled is False
            assert result.execution_plan_preview.executable is False
            assert result.execution_boundary["protection_executable"] is True
            assert result.execution_boundary["exit_cleanup_available"] is True
            assert result.execution_boundary["order_result_logging_available"] is True
            assert result.execution_boundary["would_create_execution_intent_if_all_gates_passed"] is False
            assert result.execution_boundary["would_create_order"] is False
            assert result.non_permissions["live_ready"] is False
            assert result.non_permissions["execution_permission_granted"] is False
            assert result.non_permissions["order_permission_granted"] is False
            assert result.non_permissions["execution_intent_created"] is False
            assert result.non_permissions["order_created"] is False

            session_maker = service._repository._session_maker
            async with session_maker() as session:
                intent_count = await session.scalar(text("SELECT count(*) FROM execution_intents"))
                order_count = await session.scalar(text("SELECT count(*) FROM orders"))
            assert intent_count == 0
            assert order_count == 0
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_bnb_live_execution_bridge_rejects_wrong_scope_and_permission_env():
    async def scenario():
        service, bridge, engine = await _bridge_service()
        try:
            draft = await _create_valid_draft(service)
            await service.activate_live_authorization(
                draft.draft_id,
                _activation_request(),
                operator_id="owner",
            )
            unsafe_env_bridge = BnbLiveExecutionBridgeDryRunService(
                owner_trial_flow_service=service,
                session_maker=service._repository._session_maker,
                env={
                    "TRADING_ENV": "live",
                    "EXCHANGE_TESTNET": "false",
                    "RUNTIME_CONTROL_API_ENABLED": "false",
                    "RUNTIME_TEST_SIGNAL_INJECTION_ENABLED": "false",
                    "BRC_EXECUTION_PERMISSION_MAX": "order_allowed",
                },
            )

            result = await unsafe_env_bridge.run(
                BnbLiveExecutionBridgeDryRunRequest(
                    symbol="SOL/USDT:USDT",
                    side="short",
                    max_notional="19",
                ),
                fact_snapshot=_clear_fact_snapshot(startup_guard_clear=True),
            )

            assert result.bridge_status == "blocked_before_execution_boundary"
            assert "symbol_mismatch" in result.hard_blockers
            assert "side_mismatch" in result.hard_blockers
            assert "cap_mismatch" in result.hard_blockers
            assert "global_permission_not_order_allowed" in result.hard_blockers
            assert result.execution_plan_preview.status == "preview_unavailable_invalid_scope"
            assert "symbol_mismatch" in result.execution_plan_preview.exact_blockers
            assert "side_mismatch" in result.execution_plan_preview.exact_blockers
            assert "cap_mismatch" in result.execution_plan_preview.exact_blockers
            assert result.execution_plan_preview.flags.preview_only is True
            assert result.execution_plan_preview.flags.execution_intent_created is False
            assert result.execution_plan_preview.flags.order_created is False
            assert result.execution_plan_preview.executable is False
            assert result.non_permissions["execution_intent_created"] is False
            assert result.non_permissions["order_created"] is False
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_bnb_live_execution_bridge_api_dry_run_does_not_create_intent_or_order(monkeypatch):
    from src.interfaces import api_brc_console
    from src.interfaces.api import app
    from src.interfaces.operator_auth import OperatorSession, require_operator_session

    service, bridge_service, engine = asyncio.run(_bridge_service())
    api_brc_console._owner_trial_flow_service = service
    app.dependency_overrides[require_operator_session] = lambda: OperatorSession(
        username="owner",
        expires_at=int(time.time()) + 3600,
    )

    async def fake_collect(_profile):
        return _clear_fact_snapshot()

    class FakeCollector:
        collect = staticmethod(fake_collect)

    monkeypatch.setattr(
        api_brc_console,
        "_strategy_trial_preflight_fact_collector",
        lambda _api_module: FakeCollector(),
    )
    monkeypatch.setattr(
        api_brc_console,
        "BnbLiveExecutionBridgeDryRunService",
        lambda **_kwargs: bridge_service,
    )

    try:
        with TestClient(app) as client:
            response = client.post("/api/brc/owner-trial-flow/live-execution-bridge/dry-run", json={})
            assert response.status_code == 200
            payload = response.json()
            assert payload["dry_run_only"] is True
            assert payload["execution_plan_preview"]["flags"]["preview_only"] is True
            assert payload["execution_plan_preview"]["flags"]["execution_intent_created"] is False
            assert payload["execution_plan_preview"]["flags"]["order_created"] is False
            assert payload["execution_plan_preview"]["executable"] is False
            assert payload["non_permissions"]["execution_intent_created"] is False
            assert payload["non_permissions"]["order_created"] is False
            assert payload["execution_boundary"]["would_create_order"] is False
            assert "missing_explicit_owner_live_authorization" in payload["hard_blockers"]
    finally:
        app.dependency_overrides.pop(require_operator_session, None)
        api_brc_console._owner_trial_flow_service = None
        asyncio.run(engine.dispose())


def test_bnb_final_gate_preflight_reads_live_read_only_account_and_flat_bnb(monkeypatch):
    from src.application.strategy_trial_readiness import build_bnb_strategy_trial_readiness
    from src.interfaces import api_brc_console

    class FakeGks:
        def get_state(self):
            return {"active": False, "source": "test_gks"}

    class FakeApiModule:
        _global_kill_switch_service = FakeGks()
        _startup_trading_guard_service = None
        _startup_reconciliation_summary = None
        _exchange_gateway = None

    class FakeBnbReadOnlyClient:
        closed = False

        async def fetch_balance(self, params=None):
            assert params == {"type": "future"}
            return {
                "info": {
                    "totalMarginBalance": "100.00",
                    "availableBalance": "80.00",
                },
                "timestamp": int(time.time() * 1000),
            }

        async def fetch_positions(self, symbol=None):
            assert symbol in {"BNBUSDT", "BNB/USDT:USDT"}
            return []

        async def fetch_open_orders(self, symbol, params=None):
            assert symbol in {"BNBUSDT", "BNB/USDT:USDT"}
            return []

        async def close(self):
            self.closed = True

    client = FakeBnbReadOnlyClient()
    monkeypatch.setenv("TRADING_ENV", "live")
    monkeypatch.setenv("EXCHANGE_TESTNET", "false")
    monkeypatch.setenv("BRC_EXECUTION_PERMISSION_MAX", "read_only")
    monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "false")
    monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "false")
    monkeypatch.setattr(
        api_brc_console,
        "_bnb_final_gate_read_only_client",
        lambda _api_module: {
            "client": client,
            "source": "test_bnb_read_only_client",
            "close_after_read": False,
        },
    )
    async def fake_pg_counts(_symbol):
        return {
            "execution_intents": 0,
            "orders": 0,
            "pg_bnb_active_positions": 0,
            "pg_bnb_open_orders": 0,
        }

    monkeypatch.setattr(
        api_brc_console,
        "_bnb_final_gate_pg_reconciliation_counts",
        fake_pg_counts,
    )

    async def scenario():
        profile = build_bnb_strategy_trial_readiness().strategy_profile
        collector = api_brc_console._strategy_trial_preflight_fact_collector(FakeApiModule())
        snapshot = await collector.collect(profile)
        facts = snapshot.fact_map()

        assert facts["account_facts"].status == "clear"
        assert facts["account_facts"].source == "binance_usdt_futures_live_read_only_final_gate"
        assert facts["account_facts"].evidence["freshness"] == "fresh"
        assert facts["account_facts"].evidence["equity_available"] is True
        assert facts["account_facts"].evidence["available_margin_available"] is True
        assert facts["account_facts"].evidence["external_call_performed"] is True
        assert facts["account_facts"].evidence["read_only_guarantee"] is True
        assert facts["active_position"].status == "clear"
        assert facts["active_position"].evidence["active_position_count"] == 0
        assert facts["open_order"].status == "clear"
        assert facts["open_order"].evidence["open_order_count"] == 0
        assert facts["gks"].status == "clear"
        assert facts["startup_guard"].status == "unavailable"
        assert facts["startup_guard"].blocker == "startup_guard_runtime_not_started"
        assert facts["startup_guard"].evidence["runtime_state"] == "not_started"
        assert facts["reconciliation"].status == "clear"
        assert facts["reconciliation"].evidence["status"] == "clean"
        assert facts["reconciliation"].evidence["pg_execution_intents_count"] == 0
        assert facts["reconciliation"].evidence["pg_orders_count"] == 0
        assert facts["reconciliation"].evidence["exchange_bnb_active_position_count"] == 0
        assert facts["reconciliation"].evidence["exchange_bnb_open_order_count"] == 0

    asyncio.run(scenario())


def test_bnb_final_gate_reconciliation_blocks_when_pg_or_exchange_not_flat(monkeypatch):
    from src.application.strategy_trial_readiness import build_bnb_strategy_trial_readiness
    from src.interfaces import api_brc_console

    class FakeGks:
        def get_state(self):
            return {"active": False, "source": "test_gks"}

    class FakeApiModule:
        _global_kill_switch_service = FakeGks()
        _startup_trading_guard_service = None
        _startup_reconciliation_summary = None
        _exchange_gateway = None

    class FakeBnbReadOnlyClient:
        async def fetch_balance(self, params=None):
            return {
                "info": {
                    "totalMarginBalance": "100.00",
                    "availableBalance": "80.00",
                },
                "timestamp": int(time.time() * 1000),
            }

        async def fetch_positions(self, symbol=None):
            return []

        async def fetch_open_orders(self, symbol, params=None):
            return [{"id": "existing-order", "symbol": symbol, "status": "open"}]

        async def close(self):
            return None

    monkeypatch.setenv("TRADING_ENV", "live")
    monkeypatch.setenv("EXCHANGE_TESTNET", "false")
    monkeypatch.setenv("BRC_EXECUTION_PERMISSION_MAX", "read_only")
    monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "false")
    monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "false")
    monkeypatch.setattr(
        api_brc_console,
        "_bnb_final_gate_read_only_client",
        lambda _api_module: {
            "client": FakeBnbReadOnlyClient(),
            "source": "test_bnb_read_only_client",
            "close_after_read": False,
        },
    )

    async def fake_pg_counts(_symbol):
        return {
            "execution_intents": 1,
            "orders": 0,
            "pg_bnb_active_positions": 0,
            "pg_bnb_open_orders": 0,
        }

    monkeypatch.setattr(
        api_brc_console,
        "_bnb_final_gate_pg_reconciliation_counts",
        fake_pg_counts,
    )

    async def scenario():
        profile = build_bnb_strategy_trial_readiness().strategy_profile
        collector = api_brc_console._strategy_trial_preflight_fact_collector(FakeApiModule())
        snapshot = await collector.collect(profile)
        fact = snapshot.fact_map()["reconciliation"]

        assert fact.status == "blocked"
        assert fact.blocker == "reconciliation_not_clean"
        assert fact.evidence["status"] == "mismatch"
        assert fact.evidence["pg_execution_intents_count"] == 1
        assert fact.evidence["exchange_bnb_open_order_count"] == 1

    asyncio.run(scenario())


def test_bnb_final_gate_scoped_runtime_safety_clearance_reaches_boundary(monkeypatch):
    from src.application.strategy_trial_readiness import build_bnb_strategy_trial_readiness
    from src.interfaces import api_brc_console

    now_ms = int(time.time() * 1000)

    class FakeGks:
        def get_state(self):
            return {
                "active": True,
                "source": "test_global_gks_stays_active",
                "reason": "global_fail_closed",
            }

    class FakeApiModule:
        _global_kill_switch_service = FakeGks()
        _startup_trading_guard_service = None
        _startup_reconciliation_summary = None
        _exchange_gateway = None

    class FakeBnbReadOnlyClient:
        async def fetch_balance(self, params=None):
            return {
                "info": {
                    "totalMarginBalance": "100.00",
                    "availableBalance": "80.00",
                },
                "timestamp": int(time.time() * 1000),
            }

        async def fetch_positions(self, symbol=None):
            return []

        async def fetch_open_orders(self, symbol, params=None):
            return []

        async def close(self):
            return None

    async def fake_scoped_clearance(clearance_type, _profile):
        return {
            "clearance_id": f"{clearance_type}-auth-scoped",
            "authorization_id": "auth-scoped",
            "expires_at_ms": now_ms + 60_000,
            "updated_at_ms": now_ms,
            "reason": "test_scoped_clearance",
        }

    async def fake_pg_counts(_symbol):
        return {
            "execution_intents": 0,
            "orders": 0,
            "pg_bnb_active_positions": 0,
            "pg_bnb_open_orders": 0,
        }

    monkeypatch.setenv("TRADING_ENV", "live")
    monkeypatch.setenv("EXCHANGE_TESTNET", "false")
    monkeypatch.setenv("BRC_EXECUTION_PERMISSION_MAX", "read_only")
    monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "false")
    monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "false")
    monkeypatch.setattr(
        api_brc_console,
        "_bnb_final_gate_read_only_client",
        lambda _api_module: {
            "client": FakeBnbReadOnlyClient(),
            "source": "test_bnb_read_only_client",
            "close_after_read": False,
        },
    )
    monkeypatch.setattr(
        api_brc_console,
        "_bnb_final_gate_pg_reconciliation_counts",
        fake_pg_counts,
    )
    monkeypatch.setattr(
        api_brc_console,
        "_read_active_bnb_scoped_runtime_safety_clearance",
        fake_scoped_clearance,
    )

    async def scenario():
        service, bridge, engine = await _bridge_service()
        try:
            draft = await _create_valid_draft(service)
            await service.activate_live_authorization(
                draft.draft_id,
                _activation_request(),
                operator_id="owner",
            )
            profile = build_bnb_strategy_trial_readiness().strategy_profile
            collector = api_brc_console._strategy_trial_preflight_fact_collector(FakeApiModule())
            snapshot = await collector.collect(profile)
            facts = snapshot.fact_map()

            assert facts["gks"].status == "clear"
            assert facts["gks"].source == "pg_scoped_gks_clearance"
            assert facts["gks"].evidence["active"] is False
            assert facts["gks"].evidence["global_active"] is True
            assert facts["gks"].evidence["scoped_clearance_valid"] is True
            assert facts["startup_guard"].status == "clear"
            assert facts["startup_guard"].source == "pg_scoped_startup_guard_arm"
            assert facts["startup_guard"].evidence["armed"] is True
            assert facts["startup_guard"].evidence["runtime_started"] is False
            assert facts["startup_guard"].evidence["runtime_safety_context_bound"] is True

            result = await bridge.run(fact_snapshot=snapshot)
            assert result.bridge_status == "dry_run_reached_execution_boundary"
            assert result.final_preflight_result == "passed"
            assert result.hard_blockers == []
            assert result.final_gate_read_model.gks.state == "clear"
            assert result.final_gate_read_model.gks.evidence["global_active"] is True
            assert result.final_gate_read_model.startup_guard.state == "clear"
            assert result.final_gate_read_model.startup_guard.evidence["runtime_started"] is False
            assert result.final_gate_read_model.startup_guard.evidence["runtime_safety_context_bound"] is True
            assert result.non_permissions["runtime_started"] is False
            assert result.non_permissions["execution_intent_created"] is False
            assert result.non_permissions["order_created"] is False
            assert result.non_permissions["order_permission_granted"] is False

            session_maker = service._repository._session_maker
            async with session_maker() as session:
                intent_count = await session.scalar(text("SELECT count(*) FROM execution_intents"))
                order_count = await session.scalar(text("SELECT count(*) FROM orders"))
            assert intent_count == 0
            assert order_count == 0
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_bnb_final_gate_missing_scoped_runtime_safety_clearance_blocks(monkeypatch):
    from src.application.strategy_trial_readiness import build_bnb_strategy_trial_readiness
    from src.interfaces import api_brc_console

    class FakeGks:
        def get_state(self):
            return {
                "active": True,
                "source": "test_global_gks_stays_active",
                "reason": "global_fail_closed",
            }

    class FakeApiModule:
        _global_kill_switch_service = FakeGks()
        _startup_trading_guard_service = None
        _startup_reconciliation_summary = None
        _exchange_gateway = None

    class FakeBnbReadOnlyClient:
        async def fetch_balance(self, params=None):
            return {
                "info": {
                    "totalMarginBalance": "100.00",
                    "availableBalance": "80.00",
                },
                "timestamp": int(time.time() * 1000),
            }

        async def fetch_positions(self, symbol=None):
            return []

        async def fetch_open_orders(self, symbol, params=None):
            return []

        async def close(self):
            return None

    async def no_scoped_clearance(_clearance_type, _profile):
        return None

    async def fake_pg_counts(_symbol):
        return {
            "execution_intents": 0,
            "orders": 0,
            "pg_bnb_active_positions": 0,
            "pg_bnb_open_orders": 0,
        }

    monkeypatch.setenv("TRADING_ENV", "live")
    monkeypatch.setenv("EXCHANGE_TESTNET", "false")
    monkeypatch.setenv("BRC_EXECUTION_PERMISSION_MAX", "read_only")
    monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "false")
    monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "false")
    monkeypatch.setattr(
        api_brc_console,
        "_bnb_final_gate_read_only_client",
        lambda _api_module: {
            "client": FakeBnbReadOnlyClient(),
            "source": "test_bnb_read_only_client",
            "close_after_read": False,
        },
    )
    monkeypatch.setattr(
        api_brc_console,
        "_bnb_final_gate_pg_reconciliation_counts",
        fake_pg_counts,
    )
    monkeypatch.setattr(
        api_brc_console,
        "_read_active_bnb_scoped_runtime_safety_clearance",
        no_scoped_clearance,
    )

    async def scenario():
        service, bridge, engine = await _bridge_service()
        try:
            draft = await _create_valid_draft(service)
            await service.activate_live_authorization(
                draft.draft_id,
                _activation_request(),
                operator_id="owner",
            )
            profile = build_bnb_strategy_trial_readiness().strategy_profile
            collector = api_brc_console._strategy_trial_preflight_fact_collector(FakeApiModule())
            snapshot = await collector.collect(profile)
            facts = snapshot.fact_map()

            assert facts["gks"].status == "blocked"
            assert facts["gks"].blocker == "gks_blocked"
            assert facts["startup_guard"].status == "unavailable"
            assert facts["startup_guard"].blocker == "startup_guard_runtime_not_started"

            result = await bridge.run(fact_snapshot=snapshot)
            assert result.bridge_status == "blocked_before_execution_boundary"
            assert "gks_blocked" in result.hard_blockers
            assert "gks_active" in result.hard_blockers
            assert "startup_guard_runtime_not_started" in result.hard_blockers
            assert "startup_guard_not_started" in result.hard_blockers
            assert result.non_permissions["execution_intent_created"] is False
            assert result.non_permissions["order_created"] is False
            assert result.non_permissions["order_permission_granted"] is False
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_bnb_final_gate_live_read_only_env_fail_closed_without_client(monkeypatch):
    from src.application.strategy_trial_readiness import build_bnb_strategy_trial_readiness
    from src.interfaces import api_brc_console

    class FakeGks:
        def get_state(self):
            return {"active": False, "source": "test_gks"}

    class FakeApiModule:
        _global_kill_switch_service = FakeGks()
        _startup_trading_guard_service = None
        _startup_reconciliation_summary = None
        _exchange_gateway = None

    def fail_if_called(_api_module):
        raise AssertionError("live read client must not be created when env is unsafe")

    monkeypatch.setenv("TRADING_ENV", "live")
    monkeypatch.setenv("EXCHANGE_TESTNET", "true")
    monkeypatch.setenv("BRC_EXECUTION_PERMISSION_MAX", "read_only")
    monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "false")
    monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "false")
    monkeypatch.setattr(api_brc_console, "_bnb_final_gate_read_only_client", fail_if_called)

    async def scenario():
        profile = build_bnb_strategy_trial_readiness().strategy_profile
        collector = api_brc_console._strategy_trial_preflight_fact_collector(FakeApiModule())
        snapshot = await collector.collect(profile)
        facts = snapshot.fact_map()

        assert facts["account_facts"].status == "unavailable"
        assert facts["account_facts"].blocker == "account_facts_unavailable"
        assert facts["active_position"].status == "unavailable"
        assert facts["open_order"].status == "unavailable"
        assert facts["gks"].status == "clear"
        assert facts["startup_guard"].evidence["runtime_state"] == "not_started"

    asyncio.run(scenario())
