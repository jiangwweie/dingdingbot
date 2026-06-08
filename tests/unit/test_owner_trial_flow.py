from __future__ import annotations

import asyncio
import json
import time
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.application.owner_trial_flow import (
    BoundedLiveTrialAuthorizationDraftCreateRequest,
    OwnerLiveAuthorizationActivationRequest,
    OwnerRiskAcknowledgementCreateRequest,
    ScopedRuntimeSafetyClearanceCreateRequest,
    OwnerTrialFlowError,
    OwnerTrialFlowService,
)
from src.application.bnb_live_execution_bridge import (
    BnbLiveExecutionBridgeDryRunRequest,
    BnbLiveExecutionBridgeDryRunService,
)
from src.application.production_strategy_family_admission import GenericActionSpec
from src.application.owner_bounded_execution import (
    ExchangeGatewayBoundedOrderExecutor,
    OwnerBoundedExecutionError,
    OwnerBoundedExecutionResponse,
    OwnerBoundedExecutionService,
    default_owner_bounded_execution_registry,
)
from src.application.protection_price_planner import (
    ProtectionExchangeFilters,
    ProtectionPlannerService,
    StaticProtectionPriceSource,
)
from src.application.strategy_trial_preflight_facts import (
    TrialPreflightFact,
    TrialPreflightFactsSnapshot,
)
from src.infrastructure.owner_trial_flow_repository import PgOwnerTrialFlowRepository
from src.infrastructure.pg_execution_intent_repository import PgExecutionIntentRepository
from src.infrastructure.pg_models import (
    PGBrcBoundedLiveTrialAuthorizationORM,
    PGBrcBoundedLiveTrialAuthorizationDraftORM,
    PGBrcExecutionResultORM,
    PGBrcOwnerRiskAcknowledgementORM,
    PGBrcProtectionPricePlanORM,
    PGBrcScopedRuntimeSafetyClearanceORM,
    PGExecutionIntentORM,
    PGOrderORM,
    PGPositionORM,
)
from src.infrastructure.pg_protection_price_plan_repository import PgProtectionPricePlanRepository
from src.domain.models import Direction, Order, OrderPlacementResult, OrderRole, OrderStatus, OrderType
from src.infrastructure.pg_order_repository import PgOrderRepository


class _RecordingIntentRepository:
    def __init__(self):
        self.items = []
        self.updates = []

    async def save(self, intent):
        self.items.append(intent)

    async def update(self, intent):
        self.updates.append(intent.model_copy(deep=True))


class _RecordingOrderRepository:
    def __init__(self):
        self.items = []

    async def save(self, order):
        self.items.append(order)


@pytest.mark.asyncio
async def test_pg_execution_intent_repository_update_method_is_available(monkeypatch):
    repo = PgExecutionIntentRepository(session_maker=object())
    saved = []

    async def fake_save(intent):
        saved.append(intent)

    monkeypatch.setattr(repo, "save", fake_save)
    intent = SimpleNamespace(id="intent-after-entry-fill")

    await repo.update(intent)

    assert saved == [intent]


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
        await conn.run_sync(PGBrcScopedRuntimeSafetyClearanceORM.__table__.create)
        await conn.run_sync(PGBrcProtectionPricePlanORM.__table__.create)
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
                "status TEXT NOT NULL, authorization_id TEXT, order_id TEXT, "
                "exchange_order_id TEXT, failed_reason TEXT"
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


async def _bridge_service_with_full_execution_tables() -> tuple[
    OwnerTrialFlowService,
    BnbLiveExecutionBridgeDryRunService,
    object,
]:
    service, engine = await _service()
    session_maker = service._repository._session_maker
    async with engine.begin() as conn:
        await conn.run_sync(PGOrderORM.__table__.create)
        await conn.run_sync(PGExecutionIntentORM.__table__.create)
        await conn.run_sync(PGPositionORM.__table__.create)
        await conn.run_sync(PGBrcExecutionResultORM.__table__.create)
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


async def _acknowledge_all_trend(service: OwnerTrialFlowService):
    current = await service.current(carrier_id="TF-001-live-readonly-v0")
    return await service.create_risk_acknowledgement(
        OwnerRiskAcknowledgementCreateRequest(
            carrier_id="TF-001-live-readonly-v0",
            acknowledged_warning_codes=[
                str(item["warning_id"])
                for item in current.strategy_warnings
            ],
        ),
        operator_id="owner",
    )


async def _acknowledge_all_mr_eth(service: OwnerTrialFlowService):
    current = await service.current(carrier_id="MR-001-live-readonly-v0")
    return await service.create_risk_acknowledgement(
        OwnerRiskAcknowledgementCreateRequest(
            carrier_id="MR-001-live-readonly-v0",
            acknowledged_warning_codes=[
                str(item["warning_id"])
                for item in current.strategy_warnings
            ],
        ),
        operator_id="owner",
    )


async def _acknowledge_all_mr_btc(service: OwnerTrialFlowService):
    current = await service.current(carrier_id="MR-001-BTC-live-readonly-v0")
    return await service.create_risk_acknowledgement(
        OwnerRiskAcknowledgementCreateRequest(
            carrier_id="MR-001-BTC-live-readonly-v0",
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


async def _create_valid_trend_draft(service: OwnerTrialFlowService):
    acknowledgement = await _acknowledge_all_trend(service)
    return await service.create_authorization_draft(
        BoundedLiveTrialAuthorizationDraftCreateRequest(
            carrier_id="TF-001-live-readonly-v0",
            linked_acknowledgement_id=acknowledgement.acknowledgement_id,
            symbol="SOL/USDT:USDT",
            side="long",
            max_notional="20",
            quantity="0.1",
            leverage="1",
            protection_plan_type="single_tp_plus_sl",
        ),
        operator_id="owner",
    )


async def _create_valid_mr_eth_draft(service: OwnerTrialFlowService):
    acknowledgement = await _acknowledge_all_mr_eth(service)
    return await service.create_authorization_draft(
        BoundedLiveTrialAuthorizationDraftCreateRequest(
            carrier_id="MR-001-live-readonly-v0",
            linked_acknowledgement_id=acknowledgement.acknowledgement_id,
            symbol="ETH/USDT:USDT",
            side="long",
            max_notional="20",
            quantity="0.01",
            leverage="1",
            protection_plan_type="single_tp_plus_sl",
        ),
        operator_id="owner",
    )


async def _create_valid_mr_btc_draft(service: OwnerTrialFlowService):
    acknowledgement = await _acknowledge_all_mr_btc(service)
    return await service.create_authorization_draft(
        BoundedLiveTrialAuthorizationDraftCreateRequest(
            carrier_id="MR-001-BTC-live-readonly-v0",
            linked_acknowledgement_id=acknowledgement.acknowledgement_id,
            symbol="BTC/USDT:USDT",
            side="long",
            max_notional="20",
            quantity="0.001",
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


def _trend_activation_request(**patch):
    payload = {
        "carrier_id": "TF-001-live-readonly-v0",
        "symbol": "SOL/USDT:USDT",
        "side": "long",
        "max_notional": "20",
        "quantity": "0.1",
        "leverage": "1",
        "protection_plan_type": "single_tp_plus_sl",
    }
    payload.update(patch)
    return OwnerLiveAuthorizationActivationRequest(**payload)


def _mr_eth_activation_request(**patch):
    payload = {
        "carrier_id": "MR-001-live-readonly-v0",
        "symbol": "ETH/USDT:USDT",
        "side": "long",
        "max_notional": "20",
        "quantity": "0.01",
        "leverage": "1",
        "protection_plan_type": "single_tp_plus_sl",
    }
    payload.update(patch)
    return OwnerLiveAuthorizationActivationRequest(**payload)


def _mr_btc_activation_request(**patch):
    payload = {
        "carrier_id": "MR-001-BTC-live-readonly-v0",
        "symbol": "BTC/USDT:USDT",
        "side": "long",
        "max_notional": "20",
        "quantity": "0.001",
        "leverage": "1",
        "protection_plan_type": "single_tp_plus_sl",
    }
    payload.update(patch)
    return OwnerLiveAuthorizationActivationRequest(**payload)


def _trend_generic_action_spec(**patch):
    payload = {
        "family": "Trend",
        "strategy_family_id": "TF-001-live-readonly-v0",
        "carrier_id": "TF-001-live-readonly-v0",
        "admission_level": "L3",
        "status": "valid_blocked_final_gate",
        "action_registry_supported": True,
        "symbol": "SOL/USDT:USDT",
        "side": "long",
        "quantity": "0.1",
        "max_notional": "20",
        "leverage": "1",
        "max_attempts": 1,
        "protection_mode": "single_tp_plus_sl",
        "review_requirement": "post_action_review_required",
    }
    payload.update(patch)
    return GenericActionSpec(**payload)


def _clear_fact_snapshot(
    *,
    candidate_id: str = "MI-001-BNB-LONG",
    symbol: str = "BNB/USDT:USDT",
    side: str = "long",
    startup_guard_clear: bool = False,
    startup_guard_armed: bool = True,
    active_position_count: int = 0,
    open_order_count: int = 0,
    gks_active: bool = False,
    account_freshness: str = "fresh",
    account_read_only_guarantee: bool = True,
    market_min_notional: str = "5",
    market_min_amount: str = "0.01",
    market_amount_step: str = "0.01",
    market_tick_size: str = "0.1",
    market_price_precision: str = "1",
    market_read_only_guarantee: bool = True,
    protection_tp_ready: bool = True,
    protection_sl_ready: bool = True,
    protection_price_source_ready: bool = True,
    recording_execution_intents_writable: bool = True,
    recording_orders_writable: bool = True,
    recording_review_writable: bool = True,
    recording_audit_writable: bool = True,
    recording_result_envelope_writable: bool = True,
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
        TrialPreflightFact(
            fact_id="market_metadata",
            status="clear",
            source="test_read_only_market_metadata",
            blocking=False,
            observed_at_ms=now,
            evidence={
                "symbol": symbol,
                "min_notional": market_min_notional,
                "min_amount": market_min_amount,
                "amount_step": market_amount_step,
                "tick_size": market_tick_size,
                "price_precision": market_price_precision,
                "read_only_guarantee": market_read_only_guarantee,
            },
        ),
        TrialPreflightFact(
            fact_id="protection_readiness",
            status="clear",
            source="test_read_only_protection_readiness",
            blocking=False,
            observed_at_ms=now,
            evidence={
                "protection_plan_type": "single_tp_plus_sl",
                "tp_ready": protection_tp_ready,
                "sl_ready": protection_sl_ready,
                "price_source_ready": protection_price_source_ready,
                "read_only_guarantee": True,
            },
        ),
        TrialPreflightFact(
            fact_id="recording_readiness",
            status="clear",
            source="test_read_only_recording_readiness",
            blocking=False,
            observed_at_ms=now,
            evidence={
                "execution_intents_writable": recording_execution_intents_writable,
                "orders_writable": recording_orders_writable,
                "review_writable": recording_review_writable,
                "audit_writable": recording_audit_writable,
                "result_envelope_writable": recording_result_envelope_writable,
                "read_only_check": True,
            },
        ),
    ]
    if omit_fact_ids:
        facts = [fact for fact in facts if fact.fact_id not in omit_fact_ids]
    return TrialPreflightFactsSnapshot(
        generated_at_ms=now,
        candidate_id=candidate_id,
        symbol=symbol,
        side=side,
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


def _decode_json_column(value):
    if isinstance(value, (dict, list)):
        return value
    return json.loads(value)


def _assert_success_execution_result_envelope(
    row,
    *,
    payload: dict,
    authorization_id: str,
    carrier_id: str,
    symbol: str,
) -> None:
    recheck_result = _decode_json_column(row["recheck_result"])
    adapter_result = _decode_json_column(row["adapter_result"])
    result_summary = _decode_json_column(row["result_summary"])
    audit_refs = _decode_json_column(row["audit_refs"])
    review_refs = _decode_json_column(row["review_refs"])
    final_state = _decode_json_column(row["final_state_snapshot"])

    assert row["operation_id"] == payload["review_record_id"]
    assert row["status"] == "executed"
    assert row["rechecked"] in {True, 1}
    assert recheck_result["carrier_id"] == carrier_id
    assert recheck_result["symbol"] == symbol
    assert recheck_result["final_preflight_result"] == "passed"
    assert recheck_result["final_gate_input_kind"] == "generic_action_spec"
    assert recheck_result["non_permissions"]["execution_intent_created"] is False
    assert recheck_result["non_permissions"]["order_created"] is False
    assert adapter_result["authorization_id"] == authorization_id
    assert adapter_result["carrier_id"] == carrier_id
    assert adapter_result["status"] == "executed"
    assert adapter_result["final_gate_result"] == "passed"
    assert adapter_result["execution_intent_id"] == payload["execution_intent_id"]
    assert adapter_result["entry_order_id"] == payload["entry_order_id"]
    assert adapter_result["tp_order_ids"] == payload["tp_order_ids"]
    assert adapter_result["sl_order_id"] == payload["sl_order_id"]
    assert result_summary == {
        "authorization_id": authorization_id,
        "execution_intent_id": payload["execution_intent_id"],
        "entry_order_id": payload["entry_order_id"],
        "tp_order_ids": payload["tp_order_ids"],
        "sl_order_id": payload["sl_order_id"],
    }
    assert audit_refs == [authorization_id, payload["execution_intent_id"]]
    assert review_refs == [payload["review_record_id"]]
    assert final_state == {"consumed": True}


def _assert_failure_execution_result_envelope(
    row,
    *,
    authorization_id: str,
    error: OwnerBoundedExecutionError,
    protection_status: str,
) -> None:
    recheck_result = _decode_json_column(row["recheck_result"])
    adapter_result = _decode_json_column(row["adapter_result"])
    result_summary = _decode_json_column(row["result_summary"])
    audit_refs = _decode_json_column(row["audit_refs"])
    review_refs = _decode_json_column(row["review_refs"])
    final_state = _decode_json_column(row["final_state_snapshot"])

    assert row["operation_id"] == f"review-{authorization_id}-{error.execution_intent_id}"
    assert row["status"] == "failed"
    assert row["failed_reason"] == error.code
    assert row["rechecked"] in {True, 1}
    assert recheck_result["final_gate_input_kind"] == "generic_action_spec"
    assert adapter_result["authorization_id"] == authorization_id
    assert adapter_result["status"] == "failed"
    assert adapter_result["code"] == error.code
    assert adapter_result["blockers"] == error.blockers
    assert adapter_result["execution_intent_id"] == error.execution_intent_id
    assert adapter_result["entry_order_id"] == error.entry_order_id
    assert adapter_result["entry_exchange_order_id"] == error.entry_exchange_order_id
    assert adapter_result["tp_order_ids"] == error.tp_order_ids
    assert adapter_result["sl_order_id"] == error.sl_order_id
    assert adapter_result["execution_intent_status"] == error.execution_intent_status
    assert adapter_result["protection_status"] == protection_status
    assert result_summary["authorization_id"] == authorization_id
    assert result_summary["execution_intent_id"] == error.execution_intent_id
    assert result_summary["entry_order_id"] == error.entry_order_id
    assert result_summary["tp_order_ids"] == error.tp_order_ids
    assert result_summary["sl_order_id"] == error.sl_order_id
    assert result_summary["protection_status"] == protection_status
    assert audit_refs == [authorization_id, error.execution_intent_id]
    assert review_refs == [row["operation_id"]]
    assert final_state["consumed"] is False
    assert final_state["manual_review_required"] is True
    assert final_state["protection_status"] == protection_status


def test_trend_carrier_owner_trial_flow_and_final_gate_are_supported_without_order():
    async def scenario():
        service, bridge, engine = await _bridge_service_with_full_execution_tables()
        try:
            current = await service.current(carrier_id="TF-001-live-readonly-v0")
            assert current.selected_carrier_id == "TF-001-live-readonly-v0"
            assert current.carrier["symbol"] == "SOL/USDT:USDT"
            assert current.unacknowledged_warnings

            acknowledgement = await service.create_risk_acknowledgement(
                OwnerRiskAcknowledgementCreateRequest(
                    carrier_id="TF-001-live-readonly-v0",
                    acknowledged_warning_codes=[
                        str(item["warning_id"]) for item in current.strategy_warnings
                    ],
                ),
                operator_id="owner",
            )
            draft = await service.create_authorization_draft(
                BoundedLiveTrialAuthorizationDraftCreateRequest(
                    carrier_id="TF-001-live-readonly-v0",
                    linked_acknowledgement_id=acknowledgement.acknowledgement_id,
                    symbol="SOL/USDT:USDT",
                    side="long",
                    max_notional="20",
                    quantity="0.1",
                    leverage="1",
                    protection_plan_type="single_tp_plus_sl",
                ),
                operator_id="owner",
            )
            authorization = await service.activate_live_authorization(
                draft.draft_id,
                _trend_activation_request(),
                operator_id="owner",
            )

            result = await bridge.run(
                BnbLiveExecutionBridgeDryRunRequest(
                    carrier_id="TF-001-live-readonly-v0",
                    symbol="SOL/USDT:USDT",
                    side="long",
                    max_notional="20",
                    quantity="0.1",
                    leverage="1",
                    protection_plan_type="single_tp_plus_sl",
                ),
                fact_snapshot=_clear_fact_snapshot(
                    candidate_id="TF-001-live-readonly-v0",
                    symbol="SOL/USDT:USDT",
                    side="long",
                    startup_guard_clear=True,
                ),
            )

            assert authorization.carrier_id == "TF-001-live-readonly-v0"
            assert result.final_preflight_result == "passed"
            assert "unsupported_carrier" not in result.hard_blockers
            assert result.execution_plan_preview.symbol == "SOL/USDT:USDT"
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


def test_trend_authorization_draft_rejects_exact_scope_mismatches():
    async def scenario():
        service, _bridge, engine = await _bridge_service()
        try:
            acknowledgement = await _acknowledge_all_trend(service)
            bad_requests = [
                ("symbol_mismatch", {"symbol": "BNB/USDT:USDT"}),
                ("side_mismatch", {"side": "short"}),
                ("cap_violation", {"max_notional": "19"}),
                ("cap_violation", {"quantity": "0.09"}),
                ("cap_violation", {"leverage": "0.5"}),
            ]
            for code, patch in bad_requests:
                payload = {
                    "carrier_id": "TF-001-live-readonly-v0",
                    "linked_acknowledgement_id": acknowledgement.acknowledgement_id,
                    "symbol": "SOL/USDT:USDT",
                    "side": "long",
                    "max_notional": "20",
                    "quantity": "0.1",
                    "leverage": "1",
                    "protection_plan_type": "single_tp_plus_sl",
                }
                payload.update(patch)
                with pytest.raises(OwnerTrialFlowError) as excinfo:
                    await service.create_authorization_draft(
                        BoundedLiveTrialAuthorizationDraftCreateRequest(**payload),
                        operator_id="owner",
                    )
                assert excinfo.value.code == code
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_trend_live_authorization_rejects_exact_scope_mismatches():
    async def scenario():
        service, engine = await _service()
        try:
            draft = await _create_valid_trend_draft(service)
            bad_requests = [
                ("symbol_mismatch", {"symbol": "BNB/USDT:USDT"}),
                ("side_mismatch", {"side": "short"}),
                ("cap_violation", {"max_notional": "19"}),
                ("cap_violation", {"quantity": "0.09"}),
                ("cap_violation", {"leverage": "0.5"}),
            ]
            for code, patch in bad_requests:
                with pytest.raises(OwnerTrialFlowError) as excinfo:
                    await service.activate_live_authorization(
                        draft.draft_id,
                        _trend_activation_request(**patch),
                        operator_id="owner",
                    )
                assert excinfo.value.code == code
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_scoped_runtime_safety_clearance_requires_unused_authorization():
    async def scenario():
        service, _bridge, engine = await _bridge_service()
        try:
            draft = await _create_valid_trend_draft(service)
            authorization = await service.activate_live_authorization(
                draft.draft_id,
                _trend_activation_request(),
                operator_id="owner",
            )
            clearance = await service.create_scoped_runtime_safety_clearance(
                authorization.authorization_id,
                ScopedRuntimeSafetyClearanceCreateRequest(
                    clearance_type="startup_guard",
                    reason="unit_scoped_startup_guard",
                    ttl_ms=60000,
                ),
                operator_id="owner",
            )
            assert clearance.carrier_id == "TF-001-live-readonly-v0"
            assert clearance.clearance_type == "startup_guard"
            assert clearance.symbol == "SOL/USDT:USDT"
            assert clearance.metadata_only is True
            assert clearance.runtime_started is False
            assert clearance.execution_intent_created is False
            assert clearance.order_created is False

            gks_clearance = await service.create_scoped_runtime_safety_clearance(
                authorization.authorization_id,
                ScopedRuntimeSafetyClearanceCreateRequest(
                    clearance_type="gks",
                    reason="unit_scoped_gks",
                    ttl_ms=60000,
                ),
                operator_id="owner",
            )
            assert gks_clearance.clearance_type == "gks"
            assert gks_clearance.carrier_id == "TF-001-live-readonly-v0"
            assert gks_clearance.symbol == "SOL/USDT:USDT"
            assert gks_clearance.metadata_only is True

            await service._repository.mark_live_authorization_consumed(
                authorization.authorization_id,
                occurred_at_ms=int(time.time() * 1000),
            )
            with pytest.raises(OwnerTrialFlowError) as excinfo:
                await service.create_scoped_runtime_safety_clearance(
                    authorization.authorization_id,
                    ScopedRuntimeSafetyClearanceCreateRequest(),
                    operator_id="owner",
                )
            assert excinfo.value.code == "authorization_already_consumed"

            session_maker = service._repository._session_maker
            async with session_maker() as session:
                clearance_count = await session.scalar(
                    text("SELECT count(*) FROM brc_scoped_runtime_safety_clearances")
                )
                intent_count = await session.scalar(text("SELECT count(*) FROM execution_intents"))
                order_count = await session.scalar(text("SELECT count(*) FROM orders"))
            assert clearance_count == 2
            assert intent_count == 0
            assert order_count == 0
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_trend_final_gate_dry_run_blocks_exact_scope_mismatches_without_intent_or_order():
    async def scenario():
        service, bridge, engine = await _bridge_service_with_full_execution_tables()
        try:
            draft = await _create_valid_trend_draft(service)
            await service.activate_live_authorization(
                draft.draft_id,
                _trend_activation_request(),
                operator_id="owner",
            )
            bad_requests = [
                ("symbol_mismatch", {"symbol": "BNB/USDT:USDT"}),
                ("side_mismatch", {"side": "short"}),
                ("cap_mismatch", {"max_notional": "19"}),
                ("quantity_mismatch", {"quantity": "0.09"}),
                ("leverage_mismatch", {"leverage": "0.5"}),
            ]
            for blocker, patch in bad_requests:
                payload = {
                    "carrier_id": "TF-001-live-readonly-v0",
                    "symbol": "SOL/USDT:USDT",
                    "side": "long",
                    "max_notional": "20",
                    "quantity": "0.1",
                    "leverage": "1",
                    "protection_plan_type": "single_tp_plus_sl",
                }
                payload.update(patch)
                result = await bridge.run(
                    BnbLiveExecutionBridgeDryRunRequest(**payload),
                    fact_snapshot=_clear_fact_snapshot(startup_guard_clear=True),
                )

                assert result.final_preflight_result == "blocked"
                assert blocker in result.hard_blockers
                assert blocker in result.execution_plan_preview.exact_blockers
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


def test_trend_bounded_execution_readiness_blocks_tampered_exact_scope():
    async def scenario():
        service, bridge, engine = await _bridge_service_with_full_execution_tables()
        session_maker = service._repository._session_maker
        execute_service = OwnerBoundedExecutionService(
            final_gate_service=bridge,
            session_maker=session_maker,
        )
        try:
            draft = await _create_valid_trend_draft(service)
            authorization = await service.activate_live_authorization(
                draft.draft_id,
                _trend_activation_request(),
                operator_id="owner",
            )
            bad_rows = [
                ("symbol_mismatch", {"symbol": "BNB/USDT:USDT"}),
                ("side_mismatch", {"side": "short"}),
                ("quantity_mismatch", {"quantity": "0.09"}),
                ("cap_mismatch", {"max_notional": "19"}),
                ("leverage_mismatch", {"leverage": "0.5"}),
            ]
            for blocker, patch in bad_rows:
                row = {
                    "carrier_id": "TF-001-live-readonly-v0",
                    "symbol": "SOL/USDT:USDT",
                    "side": "long",
                    "max_notional": "20",
                    "quantity": "0.1",
                    "leverage": "1",
                    "protection_plan_type": "single_tp_plus_sl",
                }
                row.update(patch)
                async with session_maker() as session:
                    await session.execute(
                        text(
                            "UPDATE brc_bounded_live_trial_authorizations "
                            "SET carrier_id = :carrier_id, symbol = :symbol, side = :side, "
                            "max_notional = :max_notional, quantity = :quantity, "
                            "leverage = :leverage, protection_plan_type = :protection_plan_type "
                            "WHERE authorization_id = :authorization_id"
                        ),
                        {
                            **row,
                            "authorization_id": authorization.authorization_id,
                        },
                    )
                    await session.commit()

                readiness = await execute_service.readiness(authorization.authorization_id)

                assert readiness.ready is False
                assert blocker in readiness.blockers
                assert readiness.creates_execution_intent_on_click is False
                assert readiness.creates_order_on_click is False

            async with session_maker() as session:
                intent_count = await session.scalar(text("SELECT count(*) FROM execution_intents"))
                order_count = await session.scalar(text("SELECT count(*) FROM orders"))
            assert intent_count == 0
            assert order_count == 0
        finally:
            await engine.dispose()

    asyncio.run(scenario())


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


def test_consumed_live_authorization_allows_fresh_draft_rehearsal():
    async def scenario():
        service, engine = await _service()
        try:
            first_draft = await _create_valid_draft(service)
            authorization = await service.activate_live_authorization(
                first_draft.draft_id,
                _activation_request(),
                operator_id="owner",
            )
            await service._repository.mark_live_authorization_consumed(
                authorization.authorization_id,
                occurred_at_ms=int(time.time() * 1000),
            )

            current = await service.current()
            assert current.live_authorization is None
            assert current.authorization_draft is None
            assert current.authorization_status == "not_started"

            second_draft = await _create_valid_draft(service)
            assert second_draft.draft_id != first_draft.draft_id
            assert second_draft.consumed is False
            assert second_draft.execution_intent_created is False
            assert second_draft.order_created is False
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_closed_live_trial_intents_do_not_block_fresh_bnb_authorization_draft():
    async def scenario():
        service, bridge, engine = await _bridge_service()
        session_maker = service._repository._session_maker
        try:
            first_draft = await _create_valid_draft(service)
            authorization = await service.activate_live_authorization(
                first_draft.draft_id,
                _activation_request(),
                operator_id="owner",
            )
            await service._repository.mark_live_authorization_consumed(
                authorization.authorization_id,
                occurred_at_ms=int(time.time() * 1000),
            )
            async with session_maker() as session:
                await session.execute(
                    text(
                        "INSERT INTO execution_intents "
                        "(id, signal_id, symbol, status, authorization_id, order_id, "
                        "exchange_order_id, failed_reason) "
                        "VALUES ('intent-closed', 'signal-closed', 'BNB/USDT:USDT', "
                        "'failed', :authorization_id, 'entry-closed', 'x-entry-closed', "
                        "'entry_filled_then_recovered_flat')"
                    ),
                    {"authorization_id": authorization.authorization_id},
                )
                await session.execute(
                    text(
                        "INSERT INTO orders (id, signal_id, symbol) "
                        "VALUES ('entry-closed', 'signal-closed', 'BNB/USDT:USDT')"
                    )
                )
                await session.commit()

            current = await service.current()
            assert current.live_authorization is None
            assert current.authorization_draft is None
            assert current.authorization_status == "not_started"

            second_draft = await _create_valid_draft(service)
            assert second_draft.draft_id != first_draft.draft_id
            assert second_draft.consumed is False
            assert second_draft.execution_intent_created is False
            assert second_draft.order_created is False

            _ = bridge
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

            clearance = client.post(
                f"/api/brc/owner-trial-flow/authorizations/{authorization.json()['authorization_id']}/runtime-safety-clearance",
                json={
                    "clearance_type": "startup_guard",
                    "reason": "unit_scoped_startup_guard",
                    "ttl_ms": 60000,
                },
            )
            assert clearance.status_code == 200
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
    clearance_payload = clearance.json()
    assert clearance_payload["clearance_type"] == "startup_guard"
    assert clearance_payload["authorization_id"] == auth_payload["authorization_id"]
    assert clearance_payload["metadata_only"] is True
    assert clearance_payload["runtime_started"] is False
    assert clearance_payload["execution_intent_created"] is False
    assert clearance_payload["order_created"] is False
    assert clearance_payload["order_permission_granted"] is False
    assert clearance_payload["execution_permission_granted"] is False
    assert clearance_payload["exchange_write_api_called"] is False


def test_trend_owner_trial_flow_api_path_authorizes_and_execute_preflight_blocks_without_order(monkeypatch):
    from src.interfaces import api_brc_console
    from src.interfaces.api import app
    from src.interfaces.operator_auth import OperatorSession, require_operator_session

    seen_profiles = []

    class FakeFactCollector:
        async def collect(self, strategy_profile):
            seen_profiles.append(strategy_profile)
            return _clear_fact_snapshot(
                candidate_id=strategy_profile.candidate_id,
                symbol=strategy_profile.symbol,
                side=strategy_profile.side,
                startup_guard_clear=True,
            )

    async def fake_gateway_binding(_api_module, **_kwargs):
        return {
            "status": "blocked_test_gateway_absent",
            "gateway": None,
            "blockers": ["test_gateway_absent"],
        }

    service, _bridge, engine = asyncio.run(_bridge_service())
    api_brc_console._owner_trial_flow_service = service
    monkeypatch.setenv("TRADING_ENV", "live")
    monkeypatch.setenv("EXCHANGE_TESTNET", "false")
    monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "false")
    monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "false")
    monkeypatch.setenv("BRC_EXECUTION_PERMISSION_MAX", "order_allowed")
    monkeypatch.setattr(
        api_brc_console,
        "_strategy_trial_preflight_fact_collector",
        lambda _api_module, **_kwargs: FakeFactCollector(),
    )
    monkeypatch.setattr(
        api_brc_console,
        "_owner_bounded_exchange_gateway_binding",
        fake_gateway_binding,
    )
    app.dependency_overrides[require_operator_session] = lambda: OperatorSession(
        username="owner",
        expires_at=int(time.time()) + 3600,
    )

    try:
        with TestClient(app) as client:
            current = client.get(
                "/api/brc/owner-trial-flow/current",
                params={"carrier_id": "TF-001-live-readonly-v0"},
            )
            assert current.status_code == 200
            warning_codes = [
                item["warning_id"]
                for item in current.json()["strategy_warnings"]
            ]

            ack = client.post(
                "/api/brc/owner-trial-flow/risk-acknowledgement",
                json={
                    "carrier_id": "TF-001-live-readonly-v0",
                    "acknowledged_warning_codes": warning_codes,
                },
            )
            assert ack.status_code == 200

            draft = client.post(
                "/api/brc/owner-trial-flow/authorization-draft",
                json={
                    "carrier_id": "TF-001-live-readonly-v0",
                    "linked_acknowledgement_id": ack.json()["acknowledgement_id"],
                    "symbol": "SOL/USDT:USDT",
                    "side": "long",
                    "max_notional": "20",
                    "quantity": "0.1",
                    "leverage": "1",
                    "protection_plan_type": "single_tp_plus_sl",
                },
            )
            assert draft.status_code == 200

            authorization = client.post(
                f"/api/brc/owner-trial-flow/authorization-draft/{draft.json()['draft_id']}/activate-live-authorization",
                json={
                    "carrier_id": "TF-001-live-readonly-v0",
                    "symbol": "SOL/USDT:USDT",
                    "side": "long",
                    "max_notional": "20",
                    "quantity": "0.1",
                    "leverage": "1",
                    "protection_plan_type": "single_tp_plus_sl",
                },
            )
            assert authorization.status_code == 200
            authorization_payload = authorization.json()

            execute = client.post(
                f"/api/brc/owner-trial-flow/authorizations/{authorization_payload['authorization_id']}/execute"
            )
            assert execute.status_code == 409

        assert seen_profiles
        assert seen_profiles[0].candidate_id == "TF-001-live-readonly-v0"
        assert seen_profiles[0].symbol == "SOL/USDT:USDT"
        assert seen_profiles[0].side == "long"
        assert authorization_payload["live_authorized"] is True
        assert authorization_payload["execution_intent_created"] is False
        assert authorization_payload["order_created"] is False
        payload = execute.json()
        assert payload["code"] == "owner_bounded_execution_blocked"
        assert payload["error_code"] == "409"
        assert "protection_price_source_missing" in payload["blockers"]
        assert payload["execution_intent_created"] is False
        assert payload["order_created"] is False

        async def counts():
            session_maker = service._repository._session_maker
            async with session_maker() as session:
                return (
                    await session.scalar(text("SELECT count(*) FROM execution_intents")),
                    await session.scalar(text("SELECT count(*) FROM orders")),
                )

        intent_count, order_count = asyncio.run(counts())
        assert intent_count == 0
        assert order_count == 0
    finally:
        app.dependency_overrides.pop(require_operator_session, None)
        api_brc_console._owner_trial_flow_service = None
        asyncio.run(engine.dispose())


def test_trend_owner_trial_flow_api_rejects_wrong_scope_before_authorization_or_order(monkeypatch):
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
            current = client.get(
                "/api/brc/owner-trial-flow/current",
                params={"carrier_id": "TF-001-live-readonly-v0"},
            )
            assert current.status_code == 200
            warning_codes = [
                item["warning_id"]
                for item in current.json()["strategy_warnings"]
            ]
            ack = client.post(
                "/api/brc/owner-trial-flow/risk-acknowledgement",
                json={
                    "carrier_id": "TF-001-live-readonly-v0",
                    "acknowledged_warning_codes": warning_codes,
                },
            )
            assert ack.status_code == 200

            wrong_symbol_draft = client.post(
                "/api/brc/owner-trial-flow/authorization-draft",
                json={
                    "carrier_id": "TF-001-live-readonly-v0",
                    "linked_acknowledgement_id": ack.json()["acknowledgement_id"],
                    "symbol": "BNB/USDT:USDT",
                    "side": "long",
                    "max_notional": "20",
                    "quantity": "0.1",
                    "leverage": "1",
                    "protection_plan_type": "single_tp_plus_sl",
                },
            )
            assert wrong_symbol_draft.status_code == 400
            assert wrong_symbol_draft.json()["code"] == "symbol_mismatch"

            valid_draft = client.post(
                "/api/brc/owner-trial-flow/authorization-draft",
                json={
                    "carrier_id": "TF-001-live-readonly-v0",
                    "linked_acknowledgement_id": ack.json()["acknowledgement_id"],
                    "symbol": "SOL/USDT:USDT",
                    "side": "long",
                    "max_notional": "20",
                    "quantity": "0.1",
                    "leverage": "1",
                    "protection_plan_type": "single_tp_plus_sl",
                },
            )
            assert valid_draft.status_code == 200

            wrong_side_authorization = client.post(
                f"/api/brc/owner-trial-flow/authorization-draft/{valid_draft.json()['draft_id']}/activate-live-authorization",
                json={
                    "carrier_id": "TF-001-live-readonly-v0",
                    "symbol": "SOL/USDT:USDT",
                    "side": "short",
                    "max_notional": "20",
                    "quantity": "0.1",
                    "leverage": "1",
                    "protection_plan_type": "single_tp_plus_sl",
                },
            )
            assert wrong_side_authorization.status_code == 400
            assert wrong_side_authorization.json()["code"] == "side_mismatch"

        async def persisted_metadata_counts():
            session_maker = service._repository._session_maker
            async with session_maker() as session:
                execution_tables = (
                    await session.execute(
                        text(
                            "SELECT name FROM sqlite_master "
                            "WHERE type='table' AND name IN ('orders', 'execution_intents')"
                        )
                    )
                ).all()
                return {
                    "acks": await session.scalar(
                        select(func.count()).select_from(PGBrcOwnerRiskAcknowledgementORM)
                    ),
                    "drafts": await session.scalar(
                        select(func.count()).select_from(PGBrcBoundedLiveTrialAuthorizationDraftORM)
                    ),
                    "authorizations": await session.scalar(
                        select(func.count()).select_from(PGBrcBoundedLiveTrialAuthorizationORM)
                    ),
                    "execution_tables": execution_tables,
                }

        counts = asyncio.run(persisted_metadata_counts())
        assert counts["acks"] == 1
        assert counts["drafts"] == 1
        assert counts["authorizations"] == 0
        assert counts["execution_tables"] == []
    finally:
        app.dependency_overrides.pop(require_operator_session, None)
        api_brc_console._owner_trial_flow_service = None
        asyncio.run(engine.dispose())


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
            assert result.owner_execution_trigger.enabled is True
            assert result.owner_execution_trigger.status == "ready_for_owner_click"
            assert result.owner_execution_trigger.endpoint == (
                f"/api/brc/owner-trial-flow/authorizations/"
                f"{result.execution_plan_preview.authorization_id}/execute"
            )
            assert result.owner_execution_trigger.blockers == []
            assert result.owner_execution_trigger.creates_execution_intent_on_click is True
            assert result.owner_execution_trigger.creates_order_on_click is True
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


def test_owner_bounded_execution_registry_registers_scoped_owner_action_carriers():
    registry = default_owner_bounded_execution_registry()

    assert set(registry.supported_carrier_ids) == {
        "MI-001-BNB-LONG",
        "TF-001-live-readonly-v0",
        "MR-001-live-readonly-v0",
        "MR-001-BTC-live-readonly-v0",
    }
    assert registry.get("MI-001-BNB-LONG") is not None
    assert registry.get("TF-001-live-readonly-v0") is not None
    assert registry.get("MR-001-live-readonly-v0") is not None
    assert registry.get("MR-001-BTC-live-readonly-v0") is not None
    assert registry.get("TB-BTC-SHORT") is None


def test_owner_bounded_execution_blocks_missing_protection_price_source_before_intent_or_order():
    async def scenario():
        service, bridge, engine = await _bridge_service()
        session_maker = service._repository._session_maker
        execute_service = OwnerBoundedExecutionService(
            final_gate_service=bridge,
            session_maker=session_maker,
        )
        try:
            draft = await _create_valid_draft(service)
            authorization = await service.activate_live_authorization(
                draft.draft_id,
                _activation_request(),
                operator_id="owner",
            )
            async with engine.begin() as conn:
                await conn.execute(text("DROP TABLE brc_execution_results"))
                await conn.run_sync(PGBrcExecutionResultORM.__table__.create)

            with pytest.raises(OwnerBoundedExecutionError) as exc_info:
                await execute_service.execute_authorization(
                    authorization.authorization_id,
                    operator_id="owner",
                    fact_snapshot=_clear_fact_snapshot(startup_guard_clear=True),
                )

            assert exc_info.value.code == "owner_bounded_execution_blocked"
            assert "protection_price_source_missing" in exc_info.value.blockers
            async with session_maker() as session:
                intent_count = await session.scalar(text("SELECT count(*) FROM execution_intents"))
                order_count = await session.scalar(text("SELECT count(*) FROM orders"))
            assert intent_count == 0
            assert order_count == 0
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_owner_bounded_execution_valid_price_snapshot_clears_protection_source_blocker():
    async def scenario():
        service, bridge, engine = await _bridge_service()
        session_maker = service._repository._session_maker
        async with engine.begin() as conn:
            await conn.execute(text("DROP TABLE brc_execution_results"))
            await conn.run_sync(lambda sync_conn: PGBrcExecutionResultORM.__table__.create(sync_conn, checkfirst=False))
        protection_repo = PgProtectionPricePlanRepository(session_maker)
        protection_service = ProtectionPlannerService(
            repository=protection_repo,
            price_source=StaticProtectionPriceSource(
                reference_price=Decimal("600.12"),
                filters=ProtectionExchangeFilters(
                    min_amount=Decimal("0.01"),
                    amount_step=Decimal("0.01"),
                    min_notional=Decimal("5"),
                    min_notional_source="test",
                    tick_size=Decimal("0.1"),
                ),
            ),
        )
        execute_service = OwnerBoundedExecutionService(
            final_gate_service=bridge,
            session_maker=session_maker,
            protection_planner_service=protection_service,
        )
        try:
            draft = await _create_valid_draft(service)
            authorization = await service.activate_live_authorization(
                draft.draft_id,
                _activation_request(),
                operator_id="owner",
            )

            with pytest.raises(OwnerBoundedExecutionError) as exc_info:
                await execute_service.execute_authorization(
                    authorization.authorization_id,
                    operator_id="owner",
                    fact_snapshot=_clear_fact_snapshot(startup_guard_clear=True),
                )

            assert "protection_price_source_missing" not in exc_info.value.blockers
            assert "entry_order_executor_not_enabled" in exc_info.value.blockers
            plan = await protection_repo.latest_valid_plan(
                authorization.authorization_id,
                phase="pre_entry_reference",
            )
            assert plan is not None
            assert plan.reference_price.quantize(Decimal("0.01")) == Decimal("600.12")
            assert plan.tp_price.quantize(Decimal("0.1")) == Decimal("606.1")
            assert plan.sl_price.quantize(Decimal("0.1")) == Decimal("594.1")
            assert plan.tp_quantity.quantize(Decimal("0.01")) == Decimal("0.01")
            assert plan.sl_quantity.quantize(Decimal("0.01")) == Decimal("0.01")
            async with session_maker() as session:
                intent_count = await session.scalar(text("SELECT count(*) FROM execution_intents"))
                order_count = await session.scalar(text("SELECT count(*) FROM orders"))
            assert intent_count == 0
            assert order_count == 0
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_owner_bounded_execution_mr_eth_scope_builds_protection_plan_before_entry():
    async def scenario():
        service, bridge, engine = await _bridge_service()
        session_maker = service._repository._session_maker
        async with engine.begin() as conn:
            await conn.execute(text("DROP TABLE brc_execution_results"))
            await conn.run_sync(lambda sync_conn: PGBrcExecutionResultORM.__table__.create(sync_conn, checkfirst=False))
        protection_repo = PgProtectionPricePlanRepository(session_maker)
        protection_service = ProtectionPlannerService(
            repository=protection_repo,
            price_source=StaticProtectionPriceSource(
                reference_price=Decimal("1682.91"),
                filters=ProtectionExchangeFilters(
                    min_amount=Decimal("0.001"),
                    amount_step=Decimal("0.001"),
                    min_notional=Decimal("5"),
                    min_notional_source="test",
                    tick_size=Decimal("0.01"),
                ),
            ),
        )
        execute_service = OwnerBoundedExecutionService(
            final_gate_service=bridge,
            session_maker=session_maker,
            protection_planner_service=protection_service,
        )
        try:
            draft = await _create_valid_mr_eth_draft(service)
            authorization = await service.activate_live_authorization(
                draft.draft_id,
                _mr_eth_activation_request(),
                operator_id="owner",
            )

            with pytest.raises(OwnerBoundedExecutionError) as exc_info:
                await execute_service.execute_authorization(
                    authorization.authorization_id,
                    operator_id="owner",
                    fact_snapshot=_clear_fact_snapshot(
                        candidate_id="MR-001-live-readonly-v0",
                        symbol="ETH/USDT:USDT",
                        startup_guard_clear=True,
                        market_min_amount="0.001",
                        market_amount_step="0.001",
                        market_tick_size="0.01",
                        market_price_precision="2",
                    ),
                )

            assert "protection_planner_config_missing" not in exc_info.value.blockers
            assert "entry_order_executor_not_enabled" in exc_info.value.blockers
            plan = await protection_repo.latest_valid_plan(
                authorization.authorization_id,
                phase="pre_entry_reference",
            )
            assert plan is not None
            assert plan.carrier_id == "MR-001-live-readonly-v0"
            assert plan.symbol == "ETH/USDT:USDT"
            assert plan.tp_price.quantize(Decimal("0.01")) == Decimal("1699.73")
            assert plan.sl_price.quantize(Decimal("0.01")) == Decimal("1666.08")
            assert plan.tp_quantity.quantize(Decimal("0.001")) == Decimal("0.010")
            assert plan.sl_quantity.quantize(Decimal("0.001")) == Decimal("0.010")
            async with session_maker() as session:
                intent_count = await session.scalar(text("SELECT count(*) FROM execution_intents"))
                order_count = await session.scalar(text("SELECT count(*) FROM orders"))
            assert intent_count == 0
            assert order_count == 0
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_owner_bounded_execution_mr_btc_planner_config_stays_blocked_outside_eth_scope():
    async def scenario():
        service, bridge, engine = await _bridge_service()
        session_maker = service._repository._session_maker
        protection_repo = PgProtectionPricePlanRepository(session_maker)
        protection_service = ProtectionPlannerService(
            repository=protection_repo,
            price_source=StaticProtectionPriceSource(
                reference_price=Decimal("105000"),
                filters=ProtectionExchangeFilters(
                    min_amount=Decimal("0.001"),
                    amount_step=Decimal("0.001"),
                    min_notional=Decimal("5"),
                    min_notional_source="test",
                    tick_size=Decimal("0.1"),
                ),
            ),
        )
        execute_service = OwnerBoundedExecutionService(
            final_gate_service=bridge,
            session_maker=session_maker,
            protection_planner_service=protection_service,
        )
        try:
            draft = await _create_valid_mr_btc_draft(service)
            authorization = await service.activate_live_authorization(
                draft.draft_id,
                _mr_btc_activation_request(),
                operator_id="owner",
            )

            with pytest.raises(OwnerBoundedExecutionError) as exc_info:
                await execute_service.execute_authorization(
                    authorization.authorization_id,
                    operator_id="owner",
                    fact_snapshot=_clear_fact_snapshot(
                        candidate_id="MR-001-BTC-live-readonly-v0",
                        symbol="BTC/USDT:USDT",
                        startup_guard_clear=True,
                        market_min_amount="0.001",
                        market_amount_step="0.001",
                        market_tick_size="0.1",
                    ),
                )

            assert "protection_planner_config_missing" in exc_info.value.blockers
            async with session_maker() as session:
                intent_count = await session.scalar(text("SELECT count(*) FROM execution_intents"))
                order_count = await session.scalar(text("SELECT count(*) FROM orders"))
            assert intent_count == 0
            assert order_count == 0
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_owner_bounded_execution_fake_gateway_creates_one_intent_entry_tp_sl_and_consumes():
    class FakeWriteGateway:
        def __init__(self):
            self.calls = []

        async def place_order(self, **kwargs):
            self.calls.append(kwargs)
            order_type = kwargs["order_type"]
            role_index = len(self.calls)
            if order_type == "market":
                return OrderPlacementResult(
                    order_id="entry-order-1",
                    exchange_order_id="x-entry-1",
                    symbol=kwargs["symbol"],
                    order_type=OrderType.MARKET,
                    direction=Direction.LONG,
                    side=kwargs["side"],
                    amount=kwargs["amount"],
                    filled_qty=Decimal("0.01"),
                    average_exec_price=Decimal("600.20"),
                    status=OrderStatus.FILLED,
                    client_order_id=kwargs.get("client_order_id"),
                )
            if order_type == "limit":
                return OrderPlacementResult(
                    order_id=f"tp-order-{role_index}",
                    exchange_order_id=f"x-tp-{role_index}",
                    symbol=kwargs["symbol"],
                    order_type=OrderType.LIMIT,
                    direction=Direction.SHORT,
                    side=kwargs["side"],
                    amount=kwargs["amount"],
                    price=kwargs["price"],
                    reduce_only=kwargs["reduce_only"],
                    status=OrderStatus.OPEN,
                    client_order_id=kwargs.get("client_order_id"),
                )
            return OrderPlacementResult(
                order_id=f"sl-order-{role_index}",
                exchange_order_id=f"x-sl-{role_index}",
                symbol=kwargs["symbol"],
                order_type=OrderType.STOP_MARKET,
                direction=Direction.SHORT,
                side=kwargs["side"],
                amount=kwargs["amount"],
                trigger_price=kwargs["trigger_price"],
                reduce_only=kwargs["reduce_only"],
                status=OrderStatus.OPEN,
                client_order_id=kwargs.get("client_order_id"),
            )

    class FakePositionProjection:
        def __init__(self):
            self.entry_orders = []

        async def project_entry_fill(self, order):
            self.entry_orders.append(order)

    async def scenario():
        service, bridge, engine = await _bridge_service()
        session_maker = service._repository._session_maker
        async with engine.begin() as conn:
            await conn.execute(text("DROP TABLE brc_execution_results"))
            await conn.run_sync(PGBrcExecutionResultORM.__table__.create)
        protection_repo = PgProtectionPricePlanRepository(session_maker)
        protection_service = ProtectionPlannerService(
            repository=protection_repo,
            price_source=StaticProtectionPriceSource(
                reference_price=Decimal("600.12"),
                filters=ProtectionExchangeFilters(
                    min_amount=Decimal("0.01"),
                    amount_step=Decimal("0.01"),
                    min_notional=Decimal("5"),
                    min_notional_source="test",
                    tick_size=Decimal("0.1"),
                ),
            ),
        )
        gateway = FakeWriteGateway()
        intent_repo = _RecordingIntentRepository()
        order_repo = _RecordingOrderRepository()
        projection = FakePositionProjection()
        execute_service = OwnerBoundedExecutionService(
            final_gate_service=bridge,
            session_maker=session_maker,
            protection_planner_service=protection_service,
            order_executor=ExchangeGatewayBoundedOrderExecutor(gateway),
            intent_repository=intent_repo,
            order_repository=order_repo,
            position_projection_service=projection,
        )
        try:
            draft = await _create_valid_draft(service)
            authorization = await service.activate_live_authorization(
                draft.draft_id,
                _activation_request(),
                operator_id="owner",
            )

            result = await execute_service.execute_authorization(
                authorization.authorization_id,
                operator_id="owner",
                fact_snapshot=_clear_fact_snapshot(startup_guard_clear=True),
            )

            assert result.status == "executed"
            assert result.consumed is True
            assert result.execution_intent_status == "completed"
            assert result.protection_status == "protected"
            assert result.tp_order_ids
            assert result.sl_order_id
            assert result.execution_intent_id == intent_repo.items[0].id
            assert len(intent_repo.items) == 1
            assert intent_repo.updates[-1].status == "completed"
            assert len(order_repo.items) == 3
            assert [order.order_role.value for order in order_repo.items] == ["ENTRY", "TP1", "SL"]
            assert projection.entry_orders == [order_repo.items[0]]
            assert len(gateway.calls) == 3
            entry_call, tp_call, sl_call = gateway.calls
            assert entry_call == {
                "symbol": "BNB/USDT:USDT",
                "order_type": "market",
                "side": "buy",
                "amount": Decimal("0.01"),
                "position_side": "LONG",
                "client_order_id": entry_call["client_order_id"],
            }
            assert tp_call["symbol"] == "BNB/USDT:USDT"
            assert tp_call["order_type"] == "limit"
            assert tp_call["side"] == "sell"
            assert tp_call["amount"] == Decimal("0.01")
            assert tp_call["price"] == Decimal("606.2")
            assert tp_call["reduce_only"] is True
            assert tp_call["position_side"] == "LONG"
            assert sl_call["symbol"] == "BNB/USDT:USDT"
            assert sl_call["order_type"] == "stop_market"
            assert sl_call["side"] == "sell"
            assert sl_call["amount"] == Decimal("0.01")
            assert sl_call["trigger_price"] == Decimal("594.1")
            assert sl_call["reduce_only"] is True
            assert sl_call["position_side"] == "LONG"
            fill_plan = await protection_repo.latest_valid_plan(
                authorization.authorization_id,
                phase="post_entry_fill",
            )
            assert fill_plan is not None
            assert fill_plan.fill_price is not None
            assert fill_plan.fill_price.quantize(Decimal("0.01")) == Decimal("600.20")
            current = await service.current()
            assert current.live_authorization is None
            assert current.authorization_draft is None
            assert current.authorization_status == "not_started"
            consumed_authorization = await service._repository.get_live_authorization(
                authorization.authorization_id
            )
            assert consumed_authorization is not None
            assert consumed_authorization.consumed is True
            async with session_maker() as session:
                result_rows = (
                    await session.execute(
                        text("SELECT operation_id, status FROM brc_execution_results")
                    )
                ).all()
            assert result_rows == [(f"review-{authorization.authorization_id}", "executed")]

            with pytest.raises(OwnerBoundedExecutionError) as reuse_exc:
                await execute_service.execute_authorization(
                    authorization.authorization_id,
                    operator_id="owner",
                    fact_snapshot=_clear_fact_snapshot(startup_guard_clear=True),
                )
            assert "authorization_already_consumed" in reuse_exc.value.blockers
            assert len(gateway.calls) == 3
            assert projection.entry_orders == [order_repo.items[0]]
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_owner_bounded_execution_trend_fake_gateway_closes_entry_protection_review_chain():
    class FakeWriteGateway:
        def __init__(self):
            self.calls = []

        async def place_order(self, **kwargs):
            self.calls.append(kwargs)
            role_index = len(self.calls)
            if kwargs["order_type"] == "market":
                return OrderPlacementResult(
                    order_id="trend-entry-order-1",
                    exchange_order_id="x-trend-entry-1",
                    symbol=kwargs["symbol"],
                    order_type=OrderType.MARKET,
                    direction=Direction.LONG,
                    side=kwargs["side"],
                    amount=kwargs["amount"],
                    filled_qty=Decimal("0.1"),
                    average_exec_price=Decimal("100.20"),
                    status=OrderStatus.FILLED,
                    client_order_id=kwargs.get("client_order_id"),
                )
            if kwargs["order_type"] == "limit":
                return OrderPlacementResult(
                    order_id=f"trend-tp-order-{role_index}",
                    exchange_order_id=f"x-trend-tp-{role_index}",
                    symbol=kwargs["symbol"],
                    order_type=OrderType.LIMIT,
                    direction=Direction.SHORT,
                    side=kwargs["side"],
                    amount=kwargs["amount"],
                    price=kwargs["price"],
                    reduce_only=kwargs["reduce_only"],
                    status=OrderStatus.OPEN,
                    client_order_id=kwargs.get("client_order_id"),
                )
            return OrderPlacementResult(
                order_id=f"trend-sl-order-{role_index}",
                exchange_order_id=f"x-trend-sl-{role_index}",
                symbol=kwargs["symbol"],
                order_type=OrderType.STOP_MARKET,
                direction=Direction.SHORT,
                side=kwargs["side"],
                amount=kwargs["amount"],
                trigger_price=kwargs["trigger_price"],
                reduce_only=kwargs["reduce_only"],
                status=OrderStatus.OPEN,
                client_order_id=kwargs.get("client_order_id"),
            )

    async def scenario():
        service, bridge, engine = await _bridge_service()
        session_maker = service._repository._session_maker
        async with engine.begin() as conn:
            await conn.execute(text("DROP TABLE brc_execution_results"))
            await conn.run_sync(PGBrcExecutionResultORM.__table__.create)
        protection_repo = PgProtectionPricePlanRepository(session_maker)
        protection_service = ProtectionPlannerService(
            repository=protection_repo,
            price_source=StaticProtectionPriceSource(
                reference_price=Decimal("100.12"),
                filters=ProtectionExchangeFilters(
                    min_amount=Decimal("0.1"),
                    amount_step=Decimal("0.1"),
                    min_notional=Decimal("5"),
                    min_notional_source="test",
                    tick_size=Decimal("0.01"),
                ),
            ),
        )
        gateway = FakeWriteGateway()
        intent_repo = _RecordingIntentRepository()
        order_repo = _RecordingOrderRepository()
        execute_service = OwnerBoundedExecutionService(
            final_gate_service=bridge,
            session_maker=session_maker,
            protection_planner_service=protection_service,
            order_executor=ExchangeGatewayBoundedOrderExecutor(gateway),
            intent_repository=intent_repo,
            order_repository=order_repo,
        )
        try:
            draft = await _create_valid_trend_draft(service)
            authorization = await service.activate_live_authorization(
                draft.draft_id,
                _trend_activation_request(),
                operator_id="owner",
            )

            result = await execute_service.execute_authorization(
                authorization.authorization_id,
                operator_id="owner",
                fact_snapshot=_clear_fact_snapshot(
                    candidate_id="TF-001-live-readonly-v0",
                    symbol="SOL/USDT:USDT",
                    side="long",
                    startup_guard_clear=True,
                    market_min_amount="0.1",
                    market_amount_step="0.1",
                    market_tick_size="0.01",
                    market_price_precision="2",
                ),
            )

            assert result.status == "executed"
            assert result.carrier_id == "TF-001-live-readonly-v0"
            assert result.consumed is True
            assert result.execution_intent_status == "completed"
            assert result.protection_status == "protected"
            assert result.tp_order_ids
            assert result.sl_order_id
            assert len(intent_repo.items) == 1
            assert intent_repo.items[0].signal.symbol == "SOL/USDT:USDT"
            assert len(order_repo.items) == 3
            assert [order.symbol for order in order_repo.items] == [
                "SOL/USDT:USDT",
                "SOL/USDT:USDT",
                "SOL/USDT:USDT",
            ]
            assert [order.order_role.value for order in order_repo.items] == ["ENTRY", "TP1", "SL"]
            assert len(gateway.calls) == 3
            entry_call, tp_call, sl_call = gateway.calls
            assert entry_call["symbol"] == "SOL/USDT:USDT"
            assert entry_call["amount"] == Decimal("0.1")
            assert entry_call["side"] == "buy"
            assert entry_call["position_side"] == "LONG"
            assert tp_call["symbol"] == "SOL/USDT:USDT"
            assert tp_call["amount"] == Decimal("0.1")
            assert tp_call["side"] == "sell"
            assert tp_call["reduce_only"] is True
            assert sl_call["symbol"] == "SOL/USDT:USDT"
            assert sl_call["amount"] == Decimal("0.1")
            assert sl_call["side"] == "sell"
            assert sl_call["reduce_only"] is True
            fill_plan = await protection_repo.latest_valid_plan(
                authorization.authorization_id,
                phase="post_entry_fill",
            )
            assert fill_plan is not None
            assert fill_plan.fill_price.quantize(Decimal("0.01")) == Decimal("100.20")
            consumed_authorization = await service._repository.get_live_authorization(
                authorization.authorization_id
            )
            assert consumed_authorization is not None
            assert consumed_authorization.consumed is True
            async with session_maker() as session:
                result_rows = (
                    await session.execute(
                        text("SELECT operation_id, status FROM brc_execution_results")
                    )
                ).all()
            assert result_rows == [(f"review-{authorization.authorization_id}", "executed")]
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_owner_bounded_execution_result_audit_records_consumed_final_state():
    class FakeWriteGateway:
        def __init__(self):
            self.calls = []

        async def place_order(self, **kwargs):
            self.calls.append(kwargs)
            if kwargs["order_type"] == "market":
                return OrderPlacementResult(
                    order_id="entry-order-1",
                    exchange_order_id="x-entry-1",
                    symbol=kwargs["symbol"],
                    order_type=OrderType.MARKET,
                    direction=Direction.LONG,
                    side=kwargs["side"],
                    amount=kwargs["amount"],
                    filled_qty=Decimal("0.01"),
                    average_exec_price=Decimal("600.20"),
                    status=OrderStatus.FILLED,
                    client_order_id=kwargs.get("client_order_id"),
                )
            if kwargs["order_type"] == "limit":
                return OrderPlacementResult(
                    order_id="tp-order-1",
                    exchange_order_id="x-tp-1",
                    symbol=kwargs["symbol"],
                    order_type=OrderType.LIMIT,
                    direction=Direction.SHORT,
                    side=kwargs["side"],
                    amount=kwargs["amount"],
                    price=kwargs["price"],
                    reduce_only=kwargs["reduce_only"],
                    status=OrderStatus.OPEN,
                    client_order_id=kwargs.get("client_order_id"),
                )
            return OrderPlacementResult(
                order_id="sl-order-1",
                exchange_order_id="x-sl-1",
                symbol=kwargs["symbol"],
                order_type=OrderType.STOP_MARKET,
                direction=Direction.SHORT,
                side=kwargs["side"],
                amount=kwargs["amount"],
                trigger_price=kwargs["trigger_price"],
                reduce_only=kwargs["reduce_only"],
                status=OrderStatus.OPEN,
                client_order_id=kwargs.get("client_order_id"),
            )

    async def scenario():
        service, bridge, engine = await _bridge_service()
        session_maker = service._repository._session_maker
        async with engine.begin() as conn:
            await conn.execute(text("DROP TABLE brc_execution_results"))
            await conn.run_sync(PGBrcExecutionResultORM.__table__.create)
        protection_repo = PgProtectionPricePlanRepository(session_maker)
        protection_service = ProtectionPlannerService(
            repository=protection_repo,
            price_source=StaticProtectionPriceSource(
                reference_price=Decimal("600.12"),
                filters=ProtectionExchangeFilters(
                    min_amount=Decimal("0.01"),
                    amount_step=Decimal("0.01"),
                    min_notional=Decimal("5"),
                    min_notional_source="test",
                    tick_size=Decimal("0.1"),
                ),
            ),
        )
        execute_service = OwnerBoundedExecutionService(
            final_gate_service=bridge,
            session_maker=session_maker,
            protection_planner_service=protection_service,
            order_executor=ExchangeGatewayBoundedOrderExecutor(FakeWriteGateway()),
            intent_repository=_RecordingIntentRepository(),
            order_repository=_RecordingOrderRepository(),
        )
        try:
            draft = await _create_valid_draft(service)
            authorization = await service.activate_live_authorization(
                draft.draft_id,
                _activation_request(),
                operator_id="owner",
            )

            result = await execute_service.execute_authorization(
                authorization.authorization_id,
                operator_id="owner",
                fact_snapshot=_clear_fact_snapshot(startup_guard_clear=True),
            )

            assert result.consumed is True
            async with session_maker() as session:
                row = (
                    await session.execute(
                        text(
                            "SELECT adapter_result, final_state_snapshot "
                            "FROM brc_execution_results "
                            "WHERE operation_id = :operation_id"
                        ),
                        {"operation_id": f"review-{authorization.authorization_id}"},
                    )
                ).mappings().one()
            adapter_result = row["adapter_result"]
            final_state_snapshot = row["final_state_snapshot"]
            if isinstance(adapter_result, str):
                adapter_result = json.loads(adapter_result)
            if isinstance(final_state_snapshot, str):
                final_state_snapshot = json.loads(final_state_snapshot)
            assert adapter_result["consumed"] is True
            assert final_state_snapshot["consumed"] is True
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_owner_bounded_execution_result_pg_write_failure_is_explicit_blocker():
    async def scenario():
        service, bridge, engine = await _bridge_service()
        session_maker = service._repository._session_maker
        execute_service = OwnerBoundedExecutionService(
            final_gate_service=bridge,
            session_maker=session_maker,
        )
        try:
            draft = await _create_valid_draft(service)
            authorization = await service.activate_live_authorization(
                draft.draft_id,
                _activation_request(),
                operator_id="owner",
            )
            async with engine.begin() as conn:
                await conn.execute(text("DROP TABLE brc_execution_results"))

            with pytest.raises(OwnerBoundedExecutionError) as exc_info:
                await execute_service._record_execution_result(
                    authorization=authorization,
                    result=OwnerBoundedExecutionResponse(
                        authorization_id=authorization.authorization_id,
                        carrier_id=authorization.carrier_id,
                        status="executed",
                        final_gate_result="passed",
                        execution_intent_id="intent-1",
                        entry_order_id="entry-1",
                        entry_exchange_order_id="x-entry-1",
                        tp_order_ids=["tp-1"],
                        sl_order_id="sl-1",
                        review_record_id=f"review-{authorization.authorization_id}",
                        execution_intent_status="completed",
                        protection_status="protected",
                        consumed=True,
                    ),
                    final_gate=await bridge.run(
                        BnbLiveExecutionBridgeDryRunRequest(),
                        fact_snapshot=_clear_fact_snapshot(startup_guard_clear=True),
                    ),
                )

            assert exc_info.value.code == "execution_result_logging_failed"
            assert exc_info.value.blockers == ["execution_result_logging_failed"]
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_owner_bounded_execution_failed_entry_is_recorded_without_consuming_authorization():
    class FakeRejectingGateway:
        def __init__(self):
            self.calls = []

        async def place_order(self, **kwargs):
            self.calls.append(kwargs)
            return OrderPlacementResult(
                order_id="entry-order-rejected",
                exchange_order_id=None,
                symbol=kwargs["symbol"],
                order_type=OrderType.MARKET,
                direction=Direction.LONG,
                side=kwargs["side"],
                amount=kwargs["amount"],
                status=OrderStatus.REJECTED,
                client_order_id=kwargs.get("client_order_id"),
                error_code="F-011",
                error_message="Order's position side does not match user's setting.",
            )

    async def scenario():
        service, bridge, engine = await _bridge_service()
        session_maker = service._repository._session_maker
        async with engine.begin() as conn:
            await conn.execute(text("DROP TABLE brc_execution_results"))
            await conn.run_sync(PGBrcExecutionResultORM.__table__.create)
        protection_repo = PgProtectionPricePlanRepository(session_maker)
        protection_service = ProtectionPlannerService(
            repository=protection_repo,
            price_source=StaticProtectionPriceSource(
                reference_price=Decimal("600.12"),
                filters=ProtectionExchangeFilters(
                    min_amount=Decimal("0.01"),
                    amount_step=Decimal("0.01"),
                    min_notional=Decimal("5"),
                    min_notional_source="test",
                    tick_size=Decimal("0.1"),
                ),
            ),
        )
        gateway = FakeRejectingGateway()
        intent_repo = _RecordingIntentRepository()
        order_repo = _RecordingOrderRepository()
        execute_service = OwnerBoundedExecutionService(
            final_gate_service=bridge,
            session_maker=session_maker,
            protection_planner_service=protection_service,
            order_executor=ExchangeGatewayBoundedOrderExecutor(gateway),
            intent_repository=intent_repo,
            order_repository=order_repo,
        )
        try:
            draft = await _create_valid_draft(service)
            authorization = await service.activate_live_authorization(
                draft.draft_id,
                _activation_request(),
                operator_id="owner",
            )

            with pytest.raises(OwnerBoundedExecutionError) as exc_info:
                await execute_service.execute_authorization(
                    authorization.authorization_id,
                    operator_id="owner",
                    fact_snapshot=_clear_fact_snapshot(startup_guard_clear=True),
                )

            assert exc_info.value.code == "entry_order_failed"
            assert len(gateway.calls) == 1
            assert gateway.calls[0]["position_side"] == "LONG"
            assert len(intent_repo.items) == 1
            assert intent_repo.updates[-1].status == "failed"
            assert intent_repo.updates[-1].failed_reason == "F-011"
            assert len(order_repo.items) == 1
            assert order_repo.items[0].status == OrderStatus.REJECTED
            async with session_maker() as session:
                row = (
                    await session.execute(
                        text(
                            "SELECT operation_id, status, failed_reason, audit_refs, review_refs, result_summary "
                            "FROM brc_execution_results "
                            "WHERE operation_id = :operation_id"
                        ),
                        {
                            "operation_id": (
                                f"review-{authorization.authorization_id}-{exc_info.value.execution_intent_id}"
                            ),
                        },
                    )
                ).mappings().one()
            audit_refs = row["audit_refs"]
            review_refs = row["review_refs"]
            result_summary = row["result_summary"]
            if isinstance(audit_refs, str):
                audit_refs = json.loads(audit_refs)
            if isinstance(review_refs, str):
                review_refs = json.loads(review_refs)
            if isinstance(result_summary, str):
                result_summary = json.loads(result_summary)
            assert row["status"] == "failed"
            assert row["failed_reason"] == "entry_order_failed"
            assert authorization.authorization_id in audit_refs
            assert exc_info.value.execution_intent_id in audit_refs
            assert row["operation_id"] in review_refs
            assert result_summary["protection_status"] == "not_created"
            current = await service.current()
            assert current.live_authorization is not None
            assert current.live_authorization.consumed is False
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_owner_bounded_execution_protection_failure_records_partial_state_without_consuming_authorization():
    class FakeProtectionRejectingGateway:
        def __init__(self):
            self.calls = []

        async def place_order(self, **kwargs):
            self.calls.append(kwargs)
            order_type = kwargs["order_type"]
            role_index = len(self.calls)
            if order_type == "market":
                return OrderPlacementResult(
                    order_id="entry-order-filled",
                    exchange_order_id="x-entry-filled",
                    symbol=kwargs["symbol"],
                    order_type=OrderType.MARKET,
                    direction=Direction.LONG,
                    side=kwargs["side"],
                    amount=kwargs["amount"],
                    filled_qty=Decimal("0.01"),
                    average_exec_price=Decimal("600.20"),
                    status=OrderStatus.FILLED,
                    client_order_id=kwargs.get("client_order_id"),
                )
            if order_type == "limit":
                return OrderPlacementResult(
                    order_id=f"tp-order-{role_index}",
                    exchange_order_id=None,
                    symbol=kwargs["symbol"],
                    order_type=OrderType.LIMIT,
                    direction=Direction.SHORT,
                    side=kwargs["side"],
                    amount=kwargs["amount"],
                    price=kwargs["price"],
                    reduce_only=kwargs["reduce_only"],
                    status=OrderStatus.REJECTED,
                    client_order_id=kwargs.get("client_order_id"),
                    error_code="tp_rejected_by_exchange",
                    error_message="fake TP rejection",
                )
            return OrderPlacementResult(
                order_id=f"sl-order-{role_index}",
                exchange_order_id=f"x-sl-{role_index}",
                symbol=kwargs["symbol"],
                order_type=OrderType.STOP_MARKET,
                direction=Direction.SHORT,
                side=kwargs["side"],
                amount=kwargs["amount"],
                trigger_price=kwargs["trigger_price"],
                reduce_only=kwargs["reduce_only"],
                status=OrderStatus.OPEN,
                client_order_id=kwargs.get("client_order_id"),
            )

    async def scenario():
        service, bridge, engine = await _bridge_service_with_full_execution_tables()
        session_maker = service._repository._session_maker
        protection_repo = PgProtectionPricePlanRepository(session_maker)
        protection_service = ProtectionPlannerService(
            repository=protection_repo,
            price_source=StaticProtectionPriceSource(
                reference_price=Decimal("600.12"),
                filters=ProtectionExchangeFilters(
                    min_amount=Decimal("0.01"),
                    amount_step=Decimal("0.01"),
                    min_notional=Decimal("5"),
                    min_notional_source="test",
                    tick_size=Decimal("0.1"),
                ),
            ),
        )
        gateway = FakeProtectionRejectingGateway()
        intent_repo = _RecordingIntentRepository()
        order_repo = _RecordingOrderRepository()
        execute_service = OwnerBoundedExecutionService(
            final_gate_service=bridge,
            session_maker=session_maker,
            protection_planner_service=protection_service,
            order_executor=ExchangeGatewayBoundedOrderExecutor(gateway),
            intent_repository=intent_repo,
            order_repository=order_repo,
        )
        try:
            draft = await _create_valid_draft(service)
            authorization = await service.activate_live_authorization(
                draft.draft_id,
                _activation_request(),
                operator_id="owner",
            )

            with pytest.raises(OwnerBoundedExecutionError) as exc_info:
                await execute_service.execute_authorization(
                    authorization.authorization_id,
                    operator_id="owner",
                    fact_snapshot=_clear_fact_snapshot(startup_guard_clear=True),
                )

            assert exc_info.value.code == "protection_order_failed"
            assert exc_info.value.execution_intent_created is True
            assert exc_info.value.order_created is True
            assert exc_info.value.order_permission_granted is False
            assert exc_info.value.entry_exchange_order_id == "x-entry-filled"
            assert exc_info.value.execution_intent_status == "partially_protected"
            assert exc_info.value.protection_status == "partial_protection_failed"
            assert exc_info.value.tp_order_ids == ["tp-order-2"]
            assert exc_info.value.sl_order_id == "sl-order-3"
            assert "protection_attach_failed_after_entry_fill" in exc_info.value.blockers
            assert "manual_review_required_before_retry" in exc_info.value.blockers
            assert len(gateway.calls) == 3
            assert gateway.calls[1]["reduce_only"] is True
            assert gateway.calls[1]["position_side"] == "LONG"
            assert gateway.calls[2]["reduce_only"] is True
            assert gateway.calls[2]["position_side"] == "LONG"
            assert [order.order_role for order in order_repo.items] == [
                OrderRole.ENTRY,
                OrderRole.TP1,
                OrderRole.SL,
            ]
            assert order_repo.items[1].status == OrderStatus.REJECTED
            assert order_repo.items[2].status == OrderStatus.OPEN
            assert intent_repo.updates[-1].status.value == "partially_protected"
            assert intent_repo.updates[-1].failed_reason == "tp_rejected_by_exchange"
            current = await service.current()
            assert current.live_authorization is not None
            assert current.live_authorization.consumed is False
            async with session_maker() as session:
                result_rows = (
                    await session.execute(
                        text(
                            "SELECT operation_id, status, failed_reason, rechecked, "
                            "recheck_result, adapter_result, result_summary, audit_refs, "
                            "review_refs, final_state_snapshot FROM brc_execution_results"
                        )
                    )
                ).mappings().all()
            assert len(result_rows) == 1
            assert intent_repo.items[0].id in result_rows[0]["operation_id"]
            _assert_failure_execution_result_envelope(
                result_rows[0],
                authorization_id=authorization.authorization_id,
                error=exc_info.value,
                protection_status="partial_protection_failed",
            )
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_owner_bounded_execution_sl_failure_records_partial_state_without_consuming_authorization():
    class FakeSlRejectingGateway:
        def __init__(self):
            self.calls = []

        async def place_order(self, **kwargs):
            self.calls.append(kwargs)
            order_type = kwargs["order_type"]
            role_index = len(self.calls)
            if order_type == "market":
                return OrderPlacementResult(
                    order_id="entry-order-filled",
                    exchange_order_id="x-entry-filled",
                    symbol=kwargs["symbol"],
                    order_type=OrderType.MARKET,
                    direction=Direction.LONG,
                    side=kwargs["side"],
                    amount=kwargs["amount"],
                    filled_qty=Decimal("0.01"),
                    average_exec_price=Decimal("600.20"),
                    status=OrderStatus.FILLED,
                    client_order_id=kwargs.get("client_order_id"),
                )
            if order_type == "limit":
                return OrderPlacementResult(
                    order_id=f"tp-order-{role_index}",
                    exchange_order_id=f"x-tp-{role_index}",
                    symbol=kwargs["symbol"],
                    order_type=OrderType.LIMIT,
                    direction=Direction.SHORT,
                    side=kwargs["side"],
                    amount=kwargs["amount"],
                    price=kwargs["price"],
                    reduce_only=kwargs["reduce_only"],
                    status=OrderStatus.OPEN,
                    client_order_id=kwargs.get("client_order_id"),
                )
            return OrderPlacementResult(
                order_id=f"sl-order-{role_index}",
                exchange_order_id=None,
                symbol=kwargs["symbol"],
                order_type=OrderType.STOP_MARKET,
                direction=Direction.SHORT,
                side=kwargs["side"],
                amount=kwargs["amount"],
                trigger_price=kwargs["trigger_price"],
                reduce_only=kwargs["reduce_only"],
                status=OrderStatus.REJECTED,
                client_order_id=kwargs.get("client_order_id"),
                error_code="sl_rejected_by_exchange",
                error_message="fake SL rejection",
            )

    async def scenario():
        service, bridge, engine = await _bridge_service_with_full_execution_tables()
        session_maker = service._repository._session_maker
        protection_repo = PgProtectionPricePlanRepository(session_maker)
        protection_service = ProtectionPlannerService(
            repository=protection_repo,
            price_source=StaticProtectionPriceSource(
                reference_price=Decimal("600.12"),
                filters=ProtectionExchangeFilters(
                    min_amount=Decimal("0.01"),
                    amount_step=Decimal("0.01"),
                    min_notional=Decimal("5"),
                    min_notional_source="test",
                    tick_size=Decimal("0.1"),
                ),
            ),
        )
        gateway = FakeSlRejectingGateway()
        intent_repo = _RecordingIntentRepository()
        order_repo = _RecordingOrderRepository()
        execute_service = OwnerBoundedExecutionService(
            final_gate_service=bridge,
            session_maker=session_maker,
            protection_planner_service=protection_service,
            order_executor=ExchangeGatewayBoundedOrderExecutor(gateway),
            intent_repository=intent_repo,
            order_repository=order_repo,
        )
        try:
            draft = await _create_valid_draft(service)
            authorization = await service.activate_live_authorization(
                draft.draft_id,
                _activation_request(),
                operator_id="owner",
            )

            with pytest.raises(OwnerBoundedExecutionError) as exc_info:
                await execute_service.execute_authorization(
                    authorization.authorization_id,
                    operator_id="owner",
                    fact_snapshot=_clear_fact_snapshot(startup_guard_clear=True),
                )

            assert exc_info.value.code == "protection_order_failed"
            assert exc_info.value.execution_intent_status == "partially_protected"
            assert exc_info.value.protection_status == "partial_protection_failed"
            assert "sl_rejected_by_exchange" in exc_info.value.blockers
            assert len(gateway.calls) == 3
            assert gateway.calls[1]["reduce_only"] is True
            assert gateway.calls[1]["position_side"] == "LONG"
            assert gateway.calls[2]["reduce_only"] is True
            assert gateway.calls[2]["position_side"] == "LONG"
            assert [order.order_role for order in order_repo.items] == [
                OrderRole.ENTRY,
                OrderRole.TP1,
                OrderRole.SL,
            ]
            assert order_repo.items[1].status == OrderStatus.OPEN
            assert order_repo.items[2].status == OrderStatus.REJECTED
            assert intent_repo.updates[-1].status.value == "partially_protected"
            assert intent_repo.updates[-1].failed_reason == "sl_rejected_by_exchange"
            current = await service.current()
            assert current.live_authorization is not None
            assert current.live_authorization.consumed is False
            async with session_maker() as session:
                result_rows = (
                    await session.execute(
                        text(
                            "SELECT operation_id, status, failed_reason, rechecked, "
                            "recheck_result, adapter_result, result_summary, audit_refs, "
                            "review_refs, final_state_snapshot FROM brc_execution_results"
                        )
                    )
                ).mappings().all()
            assert len(result_rows) == 1
            _assert_failure_execution_result_envelope(
                result_rows[0],
                authorization_id=authorization.authorization_id,
                error=exc_info.value,
                protection_status="partial_protection_failed",
            )
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_pg_order_chain_keeps_exit_orders_out_of_take_profit_bucket(monkeypatch):
    now = int(time.time() * 1000)
    entry = Order(
        id="entry-1",
        signal_id="signal-1",
        exchange_order_id="x-entry-1",
        symbol="BNB/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        order_role=OrderRole.ENTRY,
        requested_qty=Decimal("0.01"),
        filled_qty=Decimal("0.01"),
        average_exec_price=Decimal("642.81"),
        status=OrderStatus.FILLED,
        created_at=now,
        updated_at=now,
    )
    take_profit = Order(
        id="tp-1",
        signal_id="signal-1",
        exchange_order_id="x-tp-1",
        symbol="BNB/USDT:USDT",
        direction=Direction.SHORT,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP1,
        price=Decimal("649.23"),
        requested_qty=Decimal("0.01"),
        filled_qty=Decimal("0"),
        status=OrderStatus.OPEN,
        created_at=now,
        updated_at=now,
        reduce_only=True,
        parent_order_id="entry-1",
    )
    exit_order = Order(
        id="exit-1",
        signal_id="signal-1",
        exchange_order_id="x-exit-1",
        symbol="BNB/USDT:USDT",
        direction=Direction.SHORT,
        order_type=OrderType.MARKET,
        order_role=OrderRole.EXIT,
        requested_qty=Decimal("0.01"),
        filled_qty=Decimal("0.01"),
        average_exec_price=Decimal("644.27"),
        status=OrderStatus.FILLED,
        created_at=now,
        updated_at=now,
        reduce_only=True,
        parent_order_id="entry-1",
        exit_reason="authorized_recovery_close",
    )
    repo = PgOrderRepository(session_maker=object())

    async def fake_get_orders_by_signal(signal_id):
        assert signal_id == "signal-1"
        return [entry, take_profit, exit_order]

    monkeypatch.setattr(repo, "get_orders_by_signal", fake_get_orders_by_signal)

    chain = asyncio.run(repo.get_order_chain("signal-1"))

    assert chain["entry"] == [entry]
    assert chain["tps"] == [take_profit]
    assert chain["sl"] == []
    assert chain["exits"] == [exit_order]


def test_pg_order_repository_preserves_exchange_reduce_only_audit_fields():
    async def scenario():
        engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        session_maker = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with engine.begin() as conn:
                await conn.run_sync(PGOrderORM.__table__.create)
            repo = PgOrderRepository(session_maker=session_maker)
            now = int(time.time() * 1000)
            order = Order(
                id="tp-audit-1",
                signal_id="intent-audit-1",
                exchange_order_id="x-tp-audit-1",
                symbol="BNB/USDT:USDT",
                direction=Direction.SHORT,
                order_type=OrderType.LIMIT,
                order_role=OrderRole.TP1,
                price=Decimal("649.90"),
                requested_qty=Decimal("0.01"),
                filled_qty=Decimal("0"),
                status=OrderStatus.OPEN,
                created_at=now,
                updated_at=now,
                reduce_only=True,
                exchange_reduce_only_param_sent=False,
                exchange_reduce_only_omit_reason="binance_hedge_mode_position_side",
                parent_order_id="entry-audit-1",
            )

            await repo.save(order)
            loaded = await repo.get_order(order.id)

            assert loaded is not None
            assert loaded.reduce_only is True
            assert loaded.exchange_reduce_only_param_sent is False
            assert (
                loaded.exchange_reduce_only_omit_reason
                == "binance_hedge_mode_position_side"
            )
            response = repo._order_to_response(loaded)
            assert response["local_reduce_only_intent"] is True
            assert response["exchange_reduce_only_param_sent"] is False
            assert (
                response["exchange_reduce_only_omit_reason"]
                == "binance_hedge_mode_position_side"
            )
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_owner_bounded_execution_rejects_unsupported_carrier_before_intent_or_order():
    async def scenario():
        service, bridge, engine = await _bridge_service()
        session_maker = service._repository._session_maker
        execute_service = OwnerBoundedExecutionService(
            final_gate_service=bridge,
            session_maker=session_maker,
        )
        try:
            draft = await _create_valid_draft(service)
            authorization = await service.activate_live_authorization(
                draft.draft_id,
                _activation_request(),
                operator_id="owner",
            )
            async with session_maker() as session:
                await session.execute(
                    text(
                        "UPDATE brc_bounded_live_trial_authorizations "
                        "SET carrier_id = :carrier_id, symbol = :symbol, side = :side "
                        "WHERE authorization_id = :authorization_id"
                    ),
                    {
                        "carrier_id": "TB-BTC-SHORT",
                        "symbol": "BTC/USDT:USDT",
                        "side": "short",
                        "authorization_id": authorization.authorization_id,
                    },
                )
                await session.commit()

            with pytest.raises(OwnerBoundedExecutionError) as exc_info:
                await execute_service.execute_authorization(
                    authorization.authorization_id,
                    operator_id="owner",
                    fact_snapshot=_clear_fact_snapshot(startup_guard_clear=True),
                )

            assert "unsupported_carrier" in exc_info.value.blockers
            async with session_maker() as session:
                intent_count = await session.scalar(text("SELECT count(*) FROM execution_intents"))
                order_count = await session.scalar(text("SELECT count(*) FROM orders"))
            assert intent_count == 0
            assert order_count == 0
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_owner_bounded_execution_rejects_consumed_or_duplicate_authorization():
    async def scenario():
        service, bridge, engine = await _bridge_service()
        session_maker = service._repository._session_maker
        execute_service = OwnerBoundedExecutionService(
            final_gate_service=bridge,
            session_maker=session_maker,
        )
        try:
            draft = await _create_valid_draft(service)
            authorization = await service.activate_live_authorization(
                draft.draft_id,
                _activation_request(),
                operator_id="owner",
            )
            async with session_maker() as session:
                await session.execute(
                    text(
                        "UPDATE brc_bounded_live_trial_authorizations "
                        "SET consumed = 1 WHERE authorization_id = :authorization_id"
                    ),
                    {"authorization_id": authorization.authorization_id},
                )
                await session.commit()

            with pytest.raises(OwnerBoundedExecutionError) as consumed_exc:
                await execute_service.execute_authorization(
                    authorization.authorization_id,
                    operator_id="owner",
                    fact_snapshot=_clear_fact_snapshot(startup_guard_clear=True),
                )
            assert "authorization_already_consumed" in consumed_exc.value.blockers

            async with session_maker() as session:
                await session.execute(
                    text(
                        "UPDATE brc_bounded_live_trial_authorizations "
                        "SET consumed = 0 WHERE authorization_id = :authorization_id"
                    ),
                    {"authorization_id": authorization.authorization_id},
                )
                await session.execute(
                    text(
                        "INSERT INTO execution_intents "
                        "(id, signal_id, symbol, status, authorization_id) "
                        "VALUES ('intent-dup', 'signal-dup', 'BNB/USDT:USDT', 'pending', :authorization_id)"
                    ),
                    {"authorization_id": authorization.authorization_id},
                )
                await session.commit()

            with pytest.raises(OwnerBoundedExecutionError) as duplicate_exc:
                await execute_service.execute_authorization(
                    authorization.authorization_id,
                    operator_id="owner",
                    fact_snapshot=_clear_fact_snapshot(startup_guard_clear=True),
                )
            assert "duplicate_execution_intent_for_authorization" in duplicate_exc.value.blockers
            async with session_maker() as session:
                order_count = await session.scalar(text("SELECT count(*) FROM orders"))
            assert order_count == 0
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_owner_bounded_execution_allows_retryable_failed_pre_order_intent():
    async def scenario():
        service, bridge, engine = await _bridge_service()
        session_maker = service._repository._session_maker
        execute_service = OwnerBoundedExecutionService(
            final_gate_service=bridge,
            session_maker=session_maker,
        )
        try:
            draft = await _create_valid_draft(service)
            authorization = await service.activate_live_authorization(
                draft.draft_id,
                _activation_request(),
                operator_id="owner",
            )
            async with session_maker() as session:
                await session.execute(
                    text(
                        "INSERT INTO execution_intents "
                        "(id, signal_id, symbol, status, authorization_id, failed_reason) "
                        "VALUES ('intent-retryable', 'signal-retryable', 'BNB/USDT:USDT', "
                        "'failed', :authorization_id, "
                        "'entry_order_rejected_binance_position_side_mismatch_before_order_record')"
                    ),
                    {"authorization_id": authorization.authorization_id},
                )
                await session.commit()

            blockers = await execute_service._pre_adapter_blockers(authorization)

            assert "duplicate_execution_intent_for_authorization" not in blockers
            assert blockers == []
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_owner_bounded_execution_blocks_ambiguous_failed_retry_state():
    async def scenario():
        service, bridge, engine = await _bridge_service()
        session_maker = service._repository._session_maker
        execute_service = OwnerBoundedExecutionService(
            final_gate_service=bridge,
            session_maker=session_maker,
        )
        try:
            draft = await _create_valid_draft(service)
            authorization = await service.activate_live_authorization(
                draft.draft_id,
                _activation_request(),
                operator_id="owner",
            )
            async with session_maker() as session:
                await session.execute(
                    text(
                        "INSERT INTO execution_intents "
                        "(id, signal_id, symbol, status, authorization_id, exchange_order_id, failed_reason) "
                        "VALUES ('intent-has-exchange', 'signal-has-exchange', 'BNB/USDT:USDT', "
                        "'failed', :authorization_id, 'x-order-1', 'pre_order_rejected')"
                    ),
                    {"authorization_id": authorization.authorization_id},
                )
                await session.commit()

            blockers = await execute_service._pre_adapter_blockers(authorization)

            assert "duplicate_execution_intent_for_authorization" in blockers
            assert "previous_intent_has_exchange_order_id" in blockers
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_owner_bounded_execution_blocks_failed_intent_with_local_order():
    async def scenario():
        service, bridge, engine = await _bridge_service()
        session_maker = service._repository._session_maker
        execute_service = OwnerBoundedExecutionService(
            final_gate_service=bridge,
            session_maker=session_maker,
        )
        try:
            draft = await _create_valid_draft(service)
            authorization = await service.activate_live_authorization(
                draft.draft_id,
                _activation_request(),
                operator_id="owner",
            )
            async with session_maker() as session:
                await session.execute(
                    text(
                        "INSERT INTO execution_intents "
                        "(id, signal_id, symbol, status, authorization_id, failed_reason) "
                        "VALUES ('intent-has-local-order', 'signal-has-local-order', 'BNB/USDT:USDT', "
                        "'failed', :authorization_id, 'pre_order_rejected')"
                    ),
                    {"authorization_id": authorization.authorization_id},
                )
                await session.execute(
                    text(
                        "INSERT INTO orders (id, signal_id, symbol) "
                        "VALUES ('local-order-1', 'signal-has-local-order', 'BNB/USDT:USDT')"
                    )
                )
                await session.commit()

            blockers = await execute_service._pre_adapter_blockers(authorization)

            assert "duplicate_execution_intent_for_authorization" in blockers
            assert "previous_intent_has_local_order" in blockers
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_owner_bounded_execution_final_gate_failure_blocks_before_intent_or_order():
    async def scenario():
        service, bridge, engine = await _bridge_service()
        session_maker = service._repository._session_maker
        execute_service = OwnerBoundedExecutionService(
            final_gate_service=bridge,
            session_maker=session_maker,
        )
        try:
            draft = await _create_valid_draft(service)
            authorization = await service.activate_live_authorization(
                draft.draft_id,
                _activation_request(),
                operator_id="owner",
            )

            with pytest.raises(OwnerBoundedExecutionError) as exc_info:
                await execute_service.execute_authorization(
                    authorization.authorization_id,
                    operator_id="owner",
                    fact_snapshot=_clear_fact_snapshot(startup_guard_clear=False),
                )

            assert "startup_guard_status_required_before_rehearsal" in exc_info.value.blockers
            async with session_maker() as session:
                intent_count = await session.scalar(text("SELECT count(*) FROM execution_intents"))
                order_count = await session.scalar(text("SELECT count(*) FROM orders"))
            assert intent_count == 0
            assert order_count == 0
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_owner_bounded_execution_api_route_blocks_without_intent_or_order(monkeypatch):
    from src.interfaces import api_brc_console
    from src.interfaces.api import app
    from src.interfaces.operator_auth import OperatorSession, require_operator_session

    class FakeFactCollector:
        async def collect(self, _strategy_profile):
            return _clear_fact_snapshot(startup_guard_clear=True)

    async def setup():
        service, _bridge, engine = await _bridge_service()
        draft = await _create_valid_draft(service)
        authorization = await service.activate_live_authorization(
            draft.draft_id,
            _activation_request(),
            operator_id="owner",
        )
        return service, engine, authorization.authorization_id

    service, engine, authorization_id = asyncio.run(setup())
    api_brc_console._owner_trial_flow_service = service
    monkeypatch.setenv("TRADING_ENV", "live")
    monkeypatch.setenv("EXCHANGE_TESTNET", "false")
    monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "false")
    monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "false")
    monkeypatch.setenv("BRC_EXECUTION_PERMISSION_MAX", "order_allowed")
    monkeypatch.setattr(
        api_brc_console,
        "_strategy_trial_preflight_fact_collector",
        lambda _api_module, **_kwargs: FakeFactCollector(),
    )
    app.dependency_overrides[require_operator_session] = lambda: OperatorSession(
        username="owner",
        expires_at=int(time.time()) + 3600,
    )

    try:
        with TestClient(app) as client:
            response = client.post(
                f"/api/brc/owner-trial-flow/authorizations/{authorization_id}/execute"
        )
        assert response.status_code == 409
        payload = response.json()
        assert payload["error_code"] == "409"
        assert payload["code"] == "owner_bounded_execution_blocked"
        assert "protection_price_source_missing" in payload["blockers"]
        assert payload["execution_intent_created"] is False
        assert payload["order_created"] is False
        assert payload["order_permission_granted"] is False

        async def counts():
            session_maker = service._repository._session_maker
            async with session_maker() as session:
                return (
                    await session.scalar(text("SELECT count(*) FROM execution_intents")),
                    await session.scalar(text("SELECT count(*) FROM orders")),
                )

        intent_count, order_count = asyncio.run(counts())
        assert intent_count == 0
        assert order_count == 0
    finally:
        app.dependency_overrides.pop(require_operator_session, None)
        api_brc_console._owner_trial_flow_service = None
        asyncio.run(engine.dispose())


def test_owner_bounded_execution_api_route_uses_read_only_price_source(monkeypatch):
    from src.interfaces import api_brc_console
    from src.interfaces.api import app
    from src.interfaces.operator_auth import OperatorSession, require_operator_session

    class FakeFactCollector:
        async def collect(self, _strategy_profile):
            return _clear_fact_snapshot(startup_guard_clear=True)

    class FakeReadOnlyGateway:
        async def fetch_ticker_price(self, symbol: str) -> Decimal:
            assert symbol == "BNB/USDT:USDT"
            return Decimal("600.12")

        async def get_market_info(self, symbol: str) -> dict:
            assert symbol == "BNB/USDT:USDT"
            return {
                "min_quantity": Decimal("0.01"),
                "step_size": Decimal("0.01"),
                "min_notional": Decimal("5"),
                "price_precision": 1,
            }

    async def setup():
        service, _bridge, engine = await _bridge_service()
        draft = await _create_valid_draft(service)
        authorization = await service.activate_live_authorization(
            draft.draft_id,
            _activation_request(),
            operator_id="owner",
        )
        return service, engine, authorization.authorization_id

    service, engine, authorization_id = asyncio.run(setup())
    api_brc_console._owner_trial_flow_service = service
    monkeypatch.setenv("TRADING_ENV", "live")
    monkeypatch.setenv("EXCHANGE_TESTNET", "false")
    monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "false")
    monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "false")
    monkeypatch.setenv("BRC_EXECUTION_PERMISSION_MAX", "order_allowed")
    monkeypatch.setattr(
        api_brc_console,
        "_api_module",
        lambda: SimpleNamespace(),
    )
    async def fake_gateway_binding(_api_module, **_kwargs):
        return {
            "status": "ready_for_test_read_source_only",
            "gateway": FakeReadOnlyGateway(),
            "blockers": [],
        }
    monkeypatch.setattr(
        api_brc_console,
        "_owner_bounded_exchange_gateway_binding",
        fake_gateway_binding,
    )
    monkeypatch.setattr(
        api_brc_console,
        "_strategy_trial_preflight_fact_collector",
        lambda _api_module, **_kwargs: FakeFactCollector(),
    )
    app.dependency_overrides[require_operator_session] = lambda: OperatorSession(
        username="owner",
        expires_at=int(time.time()) + 3600,
    )

    try:
        with TestClient(app) as client:
            response = client.post(
                f"/api/brc/owner-trial-flow/authorizations/{authorization_id}/execute"
            )
        assert response.status_code == 409
        payload = response.json()
        assert "protection_price_source_missing" not in payload["blockers"]
        assert "entry_order_executor_not_enabled" in payload["blockers"]

        async def facts():
            session_maker = service._repository._session_maker
            async with session_maker() as session:
                return (
                    await session.scalar(text("SELECT count(*) FROM brc_protection_price_plans")),
                    await session.scalar(text("SELECT count(*) FROM execution_intents")),
                    await session.scalar(text("SELECT count(*) FROM orders")),
                )

        plan_count, intent_count, order_count = asyncio.run(facts())
        assert plan_count == 1
        assert intent_count == 0
        assert order_count == 0
    finally:
        app.dependency_overrides.pop(require_operator_session, None)
        api_brc_console._owner_trial_flow_service = None
        asyncio.run(engine.dispose())


def test_owner_bounded_execution_api_route_collects_facts_from_authorization_scope(monkeypatch):
    from src.interfaces import api_brc_console
    from src.interfaces.api import app
    from src.interfaces.operator_auth import OperatorSession, require_operator_session

    seen_profiles = []

    class FakeFactCollector:
        async def collect(self, strategy_profile):
            seen_profiles.append(strategy_profile)
            return _clear_fact_snapshot(
                candidate_id=strategy_profile.candidate_id,
                symbol=strategy_profile.symbol,
                side=strategy_profile.side,
                startup_guard_clear=True,
            )

    async def setup():
        service, _bridge, engine = await _bridge_service()
        draft = await _create_valid_trend_draft(service)
        authorization = await service.activate_live_authorization(
            draft.draft_id,
            _trend_activation_request(),
            operator_id="owner",
        )
        return service, engine, authorization.authorization_id

    service, engine, authorization_id = asyncio.run(setup())
    api_brc_console._owner_trial_flow_service = service
    monkeypatch.setenv("TRADING_ENV", "live")
    monkeypatch.setenv("EXCHANGE_TESTNET", "false")
    monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "false")
    monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "false")
    monkeypatch.setenv("BRC_EXECUTION_PERMISSION_MAX", "order_allowed")
    monkeypatch.setattr(
        api_brc_console,
        "_strategy_trial_preflight_fact_collector",
        lambda _api_module, **_kwargs: FakeFactCollector(),
    )
    app.dependency_overrides[require_operator_session] = lambda: OperatorSession(
        username="owner",
        expires_at=int(time.time()) + 3600,
    )

    try:
        with TestClient(app) as client:
            response = client.post(
                f"/api/brc/owner-trial-flow/authorizations/{authorization_id}/execute"
            )
        assert response.status_code == 409
        assert seen_profiles
        assert seen_profiles[0].candidate_id == "TF-001-live-readonly-v0"
        assert seen_profiles[0].symbol == "SOL/USDT:USDT"
        assert seen_profiles[0].side == "long"
        payload = response.json()
        assert payload["code"] == "owner_bounded_execution_blocked"
        assert "protection_price_source_missing" in payload["blockers"]
    finally:
        app.dependency_overrides.pop(require_operator_session, None)
        api_brc_console._owner_trial_flow_service = None
        asyncio.run(engine.dispose())


def test_owner_bounded_execution_api_route_trend_fake_gateway_executes_full_chain(monkeypatch):
    from src.interfaces import api_brc_console
    from src.interfaces.api import app
    from src.interfaces.operator_auth import OperatorSession, require_operator_session

    class FakeFactCollector:
        async def collect(self, strategy_profile):
            return _clear_fact_snapshot(
                candidate_id=strategy_profile.candidate_id,
                symbol=strategy_profile.symbol,
                side=strategy_profile.side,
                startup_guard_clear=True,
                market_min_amount="0.1",
                market_amount_step="0.1",
                market_tick_size="0.01",
                market_price_precision="2",
            )

    class FakeGateway:
        def __init__(self):
            self.calls = []

        async def fetch_ticker_price(self, symbol: str) -> Decimal:
            assert symbol == "SOL/USDT:USDT"
            return Decimal("100.12")

        async def get_market_info(self, symbol: str) -> dict:
            assert symbol == "SOL/USDT:USDT"
            return {
                "min_quantity": Decimal("0.1"),
                "step_size": Decimal("0.1"),
                "min_notional": Decimal("5"),
                "price_precision": 2,
            }

        async def place_order(self, **kwargs):
            self.calls.append(kwargs)
            index = len(self.calls)
            if kwargs["order_type"] == "market":
                return OrderPlacementResult(
                    order_id="api-trend-entry-order-1",
                    exchange_order_id="x-api-trend-entry-1",
                    symbol=kwargs["symbol"],
                    order_type=OrderType.MARKET,
                    direction=Direction.LONG,
                    side=kwargs["side"],
                    amount=kwargs["amount"],
                    filled_qty=Decimal("0.1"),
                    average_exec_price=Decimal("100.20"),
                    status=OrderStatus.FILLED,
                    client_order_id=kwargs.get("client_order_id"),
                )
            if kwargs["order_type"] == "limit":
                return OrderPlacementResult(
                    order_id=f"api-trend-tp-order-{index}",
                    exchange_order_id=f"x-api-trend-tp-{index}",
                    symbol=kwargs["symbol"],
                    order_type=OrderType.LIMIT,
                    direction=Direction.SHORT,
                    side=kwargs["side"],
                    amount=kwargs["amount"],
                    price=kwargs["price"],
                    reduce_only=kwargs["reduce_only"],
                    status=OrderStatus.OPEN,
                    client_order_id=kwargs.get("client_order_id"),
                )
            return OrderPlacementResult(
                order_id=f"api-trend-sl-order-{index}",
                exchange_order_id=f"x-api-trend-sl-{index}",
                symbol=kwargs["symbol"],
                order_type=OrderType.STOP_MARKET,
                direction=Direction.SHORT,
                side=kwargs["side"],
                amount=kwargs["amount"],
                trigger_price=kwargs["trigger_price"],
                reduce_only=kwargs["reduce_only"],
                status=OrderStatus.OPEN,
                client_order_id=kwargs.get("client_order_id"),
            )

    async def setup():
        service, _bridge, engine = await _bridge_service_with_full_execution_tables()
        draft = await _create_valid_trend_draft(service)
        authorization = await service.activate_live_authorization(
            draft.draft_id,
            _trend_activation_request(),
            operator_id="owner",
        )
        return service, engine, authorization.authorization_id

    gateway = FakeGateway()
    service, engine, authorization_id = asyncio.run(setup())
    api_brc_console._owner_trial_flow_service = service
    monkeypatch.setenv("TRADING_ENV", "live")
    monkeypatch.setenv("EXCHANGE_TESTNET", "false")
    monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "false")
    monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "false")
    monkeypatch.setenv("BRC_EXECUTION_PERMISSION_MAX", "order_allowed")

    async def fake_gateway_binding(_api_module, **_kwargs):
        return {
            "status": "ready_for_test_full_chain",
            "gateway": gateway,
            "blockers": [],
        }

    monkeypatch.setattr(
        api_brc_console,
        "_owner_bounded_exchange_gateway_binding",
        fake_gateway_binding,
    )
    monkeypatch.setattr(
        api_brc_console,
        "_strategy_trial_preflight_fact_collector",
        lambda _api_module, **_kwargs: FakeFactCollector(),
    )
    app.dependency_overrides[require_operator_session] = lambda: OperatorSession(
        username="owner",
        expires_at=int(time.time()) + 3600,
    )

    try:
        with TestClient(app) as client:
            response = client.post(
                f"/api/brc/owner-trial-flow/authorizations/{authorization_id}/execute"
            )
        assert response.status_code == 200
        payload = response.json()
        assert payload["carrier_id"] == "TF-001-live-readonly-v0"
        assert payload["status"] == "executed"
        assert payload["final_gate_result"] == "passed"
        assert payload["execution_intent_status"] == "completed"
        assert payload["protection_status"] == "protected"
        assert payload["consumed"] is True
        assert payload["no_permission_granted"] is True
        assert payload["auto_execution_enabled"] is False
        assert payload["entry_exchange_order_id"] == "x-api-trend-entry-1"
        assert len(payload["tp_order_ids"]) == 1
        assert payload["sl_order_id"]
        assert [call["symbol"] for call in gateway.calls] == [
            "SOL/USDT:USDT",
            "SOL/USDT:USDT",
            "SOL/USDT:USDT",
        ]
        assert [call["amount"] for call in gateway.calls] == [
            Decimal("0.1"),
            Decimal("0.1"),
            Decimal("0.1"),
        ]

        async def persisted_state():
            session_maker = service._repository._session_maker
            async with session_maker() as session:
                return {
                    "intent_rows": (
                        await session.execute(
                            text(
                                "SELECT symbol, status, authorization_id, order_id, exchange_order_id "
                                "FROM execution_intents"
                            )
                        )
                    ).all(),
                    "order_rows": (
                        await session.execute(
                            text(
                                "SELECT symbol, order_role, status, requested_qty, reduce_only "
                                "FROM orders ORDER BY created_at ASC"
                            )
                        )
                    ).all(),
                    "position_rows": (
                        await session.execute(
                            text("SELECT symbol, direction, current_qty, is_closed FROM positions")
                        )
                    ).all(),
                    "result_rows": (
                        await session.execute(
                            text(
                                "SELECT operation_id, status, rechecked, recheck_result, "
                                "adapter_result, result_summary, audit_refs, review_refs, "
                                "final_state_snapshot FROM brc_execution_results"
                            )
                        )
                    ).mappings().all(),
                }

        state = asyncio.run(persisted_state())
        assert state["intent_rows"] == [
            (
                "SOL/USDT:USDT",
                "completed",
                authorization_id,
                "api-trend-entry-order-1",
                "x-api-trend-entry-1",
            )
        ]
        assert [
            (row[0], row[1], row[2], Decimal(str(row[3])), bool(row[4]))
            for row in state["order_rows"]
        ] == [
            ("SOL/USDT:USDT", "ENTRY", "FILLED", Decimal("0.1"), False),
            ("SOL/USDT:USDT", "TP1", "OPEN", Decimal("0.1"), True),
            ("SOL/USDT:USDT", "SL", "OPEN", Decimal("0.1"), True),
        ]
        assert [
            (row[0], row[1], Decimal(str(row[2])), row[3])
            for row in state["position_rows"]
        ] == [("SOL/USDT:USDT", "LONG", Decimal("0.1"), 0)]
        assert len(state["result_rows"]) == 1
        _assert_success_execution_result_envelope(
            state["result_rows"][0],
            payload=payload,
            authorization_id=authorization_id,
            carrier_id="TF-001-live-readonly-v0",
            symbol="SOL/USDT:USDT",
        )
    finally:
        app.dependency_overrides.pop(require_operator_session, None)
        api_brc_console._owner_trial_flow_service = None
        asyncio.run(engine.dispose())


def test_owner_bounded_execution_api_route_bnb_fake_gateway_regression_full_chain(monkeypatch):
    from src.interfaces import api_brc_console
    from src.interfaces.api import app
    from src.interfaces.operator_auth import OperatorSession, require_operator_session

    class FakeFactCollector:
        async def collect(self, strategy_profile):
            return _clear_fact_snapshot(
                candidate_id=strategy_profile.candidate_id,
                symbol=strategy_profile.symbol,
                side=strategy_profile.side,
                startup_guard_clear=True,
            )

    class FakeGateway:
        def __init__(self):
            self.calls = []

        async def fetch_ticker_price(self, symbol: str) -> Decimal:
            assert symbol == "BNB/USDT:USDT"
            return Decimal("600.12")

        async def get_market_info(self, symbol: str) -> dict:
            assert symbol == "BNB/USDT:USDT"
            return {
                "min_quantity": Decimal("0.01"),
                "step_size": Decimal("0.01"),
                "min_notional": Decimal("5"),
                "price_precision": 1,
            }

        async def place_order(self, **kwargs):
            self.calls.append(kwargs)
            index = len(self.calls)
            if kwargs["order_type"] == "market":
                return OrderPlacementResult(
                    order_id="api-bnb-entry-order-1",
                    exchange_order_id="x-api-bnb-entry-1",
                    symbol=kwargs["symbol"],
                    order_type=OrderType.MARKET,
                    direction=Direction.LONG,
                    side=kwargs["side"],
                    amount=kwargs["amount"],
                    filled_qty=Decimal("0.01"),
                    average_exec_price=Decimal("600.20"),
                    status=OrderStatus.FILLED,
                    client_order_id=kwargs.get("client_order_id"),
                )
            if kwargs["order_type"] == "limit":
                return OrderPlacementResult(
                    order_id=f"api-bnb-tp-order-{index}",
                    exchange_order_id=f"x-api-bnb-tp-{index}",
                    symbol=kwargs["symbol"],
                    order_type=OrderType.LIMIT,
                    direction=Direction.SHORT,
                    side=kwargs["side"],
                    amount=kwargs["amount"],
                    price=kwargs["price"],
                    reduce_only=kwargs["reduce_only"],
                    status=OrderStatus.OPEN,
                    client_order_id=kwargs.get("client_order_id"),
                )
            return OrderPlacementResult(
                order_id=f"api-bnb-sl-order-{index}",
                exchange_order_id=f"x-api-bnb-sl-{index}",
                symbol=kwargs["symbol"],
                order_type=OrderType.STOP_MARKET,
                direction=Direction.SHORT,
                side=kwargs["side"],
                amount=kwargs["amount"],
                trigger_price=kwargs["trigger_price"],
                reduce_only=kwargs["reduce_only"],
                status=OrderStatus.OPEN,
                client_order_id=kwargs.get("client_order_id"),
            )

    async def setup():
        service, _bridge, engine = await _bridge_service_with_full_execution_tables()
        draft = await _create_valid_draft(service)
        authorization = await service.activate_live_authorization(
            draft.draft_id,
            _activation_request(),
            operator_id="owner",
        )
        return service, engine, authorization.authorization_id

    gateway = FakeGateway()
    service, engine, authorization_id = asyncio.run(setup())
    api_brc_console._owner_trial_flow_service = service
    monkeypatch.setenv("TRADING_ENV", "live")
    monkeypatch.setenv("EXCHANGE_TESTNET", "false")
    monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "false")
    monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "false")
    monkeypatch.setenv("BRC_EXECUTION_PERMISSION_MAX", "order_allowed")

    async def fake_gateway_binding(_api_module, **_kwargs):
        return {
            "status": "ready_for_test_bnb_regression",
            "gateway": gateway,
            "blockers": [],
        }

    monkeypatch.setattr(
        api_brc_console,
        "_owner_bounded_exchange_gateway_binding",
        fake_gateway_binding,
    )
    monkeypatch.setattr(
        api_brc_console,
        "_strategy_trial_preflight_fact_collector",
        lambda _api_module, **_kwargs: FakeFactCollector(),
    )
    app.dependency_overrides[require_operator_session] = lambda: OperatorSession(
        username="owner",
        expires_at=int(time.time()) + 3600,
    )

    try:
        with TestClient(app) as client:
            response = client.post(
                f"/api/brc/owner-trial-flow/authorizations/{authorization_id}/execute"
            )
        assert response.status_code == 200
        payload = response.json()
        assert payload["carrier_id"] == "MI-001-BNB-LONG"
        assert payload["status"] == "executed"
        assert payload["final_gate_result"] == "passed"
        assert payload["execution_intent_status"] == "completed"
        assert payload["protection_status"] == "protected"
        assert payload["consumed"] is True
        assert payload["no_permission_granted"] is True
        assert payload["auto_execution_enabled"] is False
        assert payload["entry_exchange_order_id"] == "x-api-bnb-entry-1"
        assert len(payload["tp_order_ids"]) == 1
        assert payload["sl_order_id"]
        assert [call["symbol"] for call in gateway.calls] == [
            "BNB/USDT:USDT",
            "BNB/USDT:USDT",
            "BNB/USDT:USDT",
        ]
        assert [call["amount"] for call in gateway.calls] == [
            Decimal("0.01"),
            Decimal("0.01"),
            Decimal("0.01"),
        ]

        async def persisted_state():
            session_maker = service._repository._session_maker
            async with session_maker() as session:
                return {
                    "intent_rows": (
                        await session.execute(
                            text(
                                "SELECT symbol, status, authorization_id, order_id, exchange_order_id "
                                "FROM execution_intents"
                            )
                        )
                    ).all(),
                    "order_rows": (
                        await session.execute(
                            text(
                                "SELECT symbol, order_role, status, requested_qty, reduce_only "
                                "FROM orders ORDER BY created_at ASC"
                            )
                        )
                    ).all(),
                    "position_rows": (
                        await session.execute(
                            text("SELECT symbol, direction, current_qty, is_closed FROM positions")
                        )
                    ).all(),
                    "result_rows": (
                        await session.execute(
                            text(
                                "SELECT operation_id, status, rechecked, recheck_result, "
                                "adapter_result, result_summary, audit_refs, review_refs, "
                                "final_state_snapshot FROM brc_execution_results"
                            )
                        )
                    ).mappings().all(),
                }

        state = asyncio.run(persisted_state())
        assert state["intent_rows"] == [
            (
                "BNB/USDT:USDT",
                "completed",
                authorization_id,
                "api-bnb-entry-order-1",
                "x-api-bnb-entry-1",
            )
        ]
        assert [
            (row[0], row[1], row[2], Decimal(str(row[3])), bool(row[4]))
            for row in state["order_rows"]
        ] == [
            ("BNB/USDT:USDT", "ENTRY", "FILLED", Decimal("0.01"), False),
            ("BNB/USDT:USDT", "TP1", "OPEN", Decimal("0.01"), True),
            ("BNB/USDT:USDT", "SL", "OPEN", Decimal("0.01"), True),
        ]
        assert [
            (row[0], row[1], Decimal(str(row[2])), row[3])
            for row in state["position_rows"]
        ] == [("BNB/USDT:USDT", "LONG", Decimal("0.01"), 0)]
        assert len(state["result_rows"]) == 1
        _assert_success_execution_result_envelope(
            state["result_rows"][0],
            payload=payload,
            authorization_id=authorization_id,
            carrier_id="MI-001-BNB-LONG",
            symbol="BNB/USDT:USDT",
        )
    finally:
        app.dependency_overrides.pop(require_operator_session, None)
        api_brc_console._owner_trial_flow_service = None
        asyncio.run(engine.dispose())


def test_owner_bounded_execution_readiness_api_blocks_existing_failed_order_without_mutation(monkeypatch):
    from src.interfaces import api_brc_console
    from src.interfaces.api import app
    from src.interfaces.operator_auth import OperatorSession, require_operator_session

    async def setup():
        service, _bridge, engine = await _bridge_service()
        draft = await _create_valid_draft(service)
        authorization = await service.activate_live_authorization(
            draft.draft_id,
            _activation_request(),
            operator_id="owner",
        )
        session_maker = service._repository._session_maker
        async with session_maker() as session:
            await session.execute(
                text(
                    "INSERT INTO execution_intents "
                    "(id, signal_id, symbol, status, authorization_id, order_id, failed_reason) "
                    "VALUES ('intent-failed-with-order', 'signal-failed-with-order', "
                    "'BNB/USDT:USDT', 'failed', :authorization_id, "
                    "'local-rejected-order', 'exchange_rejected_after_local_order_record')"
                ),
                {"authorization_id": authorization.authorization_id},
            )
            await session.execute(
                text(
                    "INSERT INTO orders (id, signal_id, symbol) "
                    "VALUES ('local-rejected-order', 'signal-failed-with-order', 'BNB/USDT:USDT')"
                )
            )
            await session.commit()
        return service, engine, authorization.authorization_id

    service, engine, authorization_id = asyncio.run(setup())
    api_brc_console._owner_trial_flow_service = service
    app.dependency_overrides[require_operator_session] = lambda: OperatorSession(
        username="owner",
        expires_at=int(time.time()) + 3600,
    )

    try:
        with TestClient(app) as client:
            response = client.get(
                f"/api/brc/owner-trial-flow/authorizations/{authorization_id}/execute-readiness"
            )
        assert response.status_code == 200
        payload = response.json()
        assert payload["authorization_id"] == authorization_id
        assert payload["ready"] is False
        assert payload["creates_execution_intent_on_click"] is False
        assert payload["creates_order_on_click"] is False
        assert payload["order_permission_granted"] is False
        assert "duplicate_execution_intent_for_authorization" in payload["blockers"]
        assert "previous_intent_has_order_id" in payload["blockers"]

        async def counts():
            session_maker = service._repository._session_maker
            async with session_maker() as session:
                return (
                    await session.scalar(text("SELECT count(*) FROM execution_intents")),
                    await session.scalar(text("SELECT count(*) FROM orders")),
                )

        intent_count, order_count = asyncio.run(counts())
        assert intent_count == 1
        assert order_count == 1
    finally:
        app.dependency_overrides.pop(require_operator_session, None)
        api_brc_console._owner_trial_flow_service = None
        asyncio.run(engine.dispose())


def test_owner_bounded_execution_state_api_surfaces_failed_attempt_evidence(monkeypatch):
    from src.interfaces import api_brc_console
    from src.interfaces.api import app
    from src.interfaces.operator_auth import OperatorSession, require_operator_session

    async def setup():
        service, _bridge, engine = await _bridge_service()
        draft = await _create_valid_draft(service)
        authorization = await service.activate_live_authorization(
            draft.draft_id,
            _activation_request(),
            operator_id="owner",
        )
        session_maker = service._repository._session_maker
        async with session_maker() as session:
            await session.execute(
                text(
                    "INSERT INTO execution_intents "
                    "(id, signal_id, symbol, status, authorization_id, order_id, failed_reason) "
                    "VALUES ('intent-failed-with-order', 'signal-failed-with-order', "
                    "'BNB/USDT:USDT', 'failed', :authorization_id, "
                    "'local-rejected-order', 'exchange_rejected_after_local_order_record')"
                ),
                {"authorization_id": authorization.authorization_id},
            )
            await session.execute(
                text(
                    "INSERT INTO orders (id, signal_id, symbol) "
                    "VALUES ('local-rejected-order', 'signal-failed-with-order', 'BNB/USDT:USDT')"
                )
            )
            await session.execute(
                text(
                    "INSERT INTO brc_execution_results (operation_id, status) "
                    "VALUES (:operation_id, 'failed')"
                ),
                {"operation_id": f"review-{authorization.authorization_id}-intent-failed-with-order"},
            )
            await session.commit()
        return service, engine, authorization.authorization_id

    service, engine, authorization_id = asyncio.run(setup())
    api_brc_console._owner_trial_flow_service = service
    app.dependency_overrides[require_operator_session] = lambda: OperatorSession(
        username="owner",
        expires_at=int(time.time()) + 3600,
    )

    try:
        with TestClient(app) as client:
            response = client.get(
                f"/api/brc/owner-trial-flow/authorizations/{authorization_id}/execution-state"
            )
        assert response.status_code == 200
        payload = response.json()
        assert payload["authorization_id"] == authorization_id
        assert payload["retry_allowed"] is False
        assert "duplicate_execution_intent_for_authorization" in payload["retry_blockers"]
        assert "previous_intent_has_order_id" in payload["retry_blockers"]
        assert payload["execution_intent_count"] == 1
        assert payload["local_order_count"] == 1
        assert payload["result_count"] == 1
        assert payload["execution_intents"][0]["id"] == "intent-failed-with-order"
        assert payload["execution_intents"][0]["order_id"] == "local-rejected-order"
        assert payload["execution_intents"][0]["local_order_count_for_signal"] == 1
        assert payload["local_orders"][0]["id"] == "local-rejected-order"
        assert payload["execution_results"][0]["status"] == "failed"
        assert payload["safety"] == {
            "creates_authorization": False,
            "creates_execution_intent": False,
            "creates_order": False,
            "starts_runtime": False,
            "calls_exchange": False,
            "mutates_pg": False,
        }

        async def counts():
            session_maker = service._repository._session_maker
            async with session_maker() as session:
                return (
                    await session.scalar(text("SELECT count(*) FROM execution_intents")),
                    await session.scalar(text("SELECT count(*) FROM orders")),
                    await session.scalar(text("SELECT count(*) FROM brc_execution_results")),
                )

        intent_count, order_count, result_count = asyncio.run(counts())
        assert (intent_count, order_count, result_count) == (1, 1, 1)
    finally:
        app.dependency_overrides.pop(require_operator_session, None)
        api_brc_console._owner_trial_flow_service = None
        asyncio.run(engine.dispose())


def test_owner_bounded_execution_final_gate_dry_run_api_plan_without_fact_collection(monkeypatch):
    from src.interfaces import api_brc_console
    from src.interfaces.api import app
    from src.interfaces.operator_auth import OperatorSession, require_operator_session

    async def setup():
        service, _bridge, engine = await _bridge_service()
        draft = await _create_valid_trend_draft(service)
        authorization = await service.activate_live_authorization(
            draft.draft_id,
            _trend_activation_request(),
            operator_id="owner",
        )
        return service, engine, authorization.authorization_id

    service, engine, authorization_id = asyncio.run(setup())
    api_brc_console._owner_trial_flow_service = service
    app.dependency_overrides[require_operator_session] = lambda: OperatorSession(
        username="owner",
        expires_at=int(time.time()) + 3600,
    )

    def fact_collector_must_not_run(*_args, **_kwargs):
        raise AssertionError("fact collector must not run in dry-run plan mode")

    monkeypatch.setattr(
        api_brc_console,
        "_strategy_trial_preflight_fact_collector",
        fact_collector_must_not_run,
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                f"/api/brc/owner-trial-flow/authorizations/{authorization_id}/final-gate-dry-run"
            )
        assert response.status_code == 200
        payload = response.json()
        assert payload["mode"] == "dry_run"
        assert payload["result"] == "dry_run"
        assert payload["authorization_id"] == authorization_id
        assert payload["carrier_id"] == "TF-001-live-readonly-v0"
        assert payload["symbol"] == "SOL/USDT:USDT"
        assert payload["quantity"] == "0.1"
        assert payload["safety"]["creates_execution_intent"] is False
        assert payload["safety"]["creates_order"] is False
    finally:
        app.dependency_overrides.pop(require_operator_session, None)
        api_brc_console._owner_trial_flow_service = None
        asyncio.run(engine.dispose())


def test_owner_bounded_execution_final_gate_dry_run_blocks_stale_authorization_before_facts(monkeypatch):
    from src.interfaces import api_brc_console
    from src.interfaces.api import app
    from src.interfaces.operator_auth import OperatorSession, require_operator_session

    async def setup():
        service, _bridge, engine = await _bridge_service()
        first_draft = await _create_valid_trend_draft(service)
        first_authorization = await service.activate_live_authorization(
            first_draft.draft_id,
            _trend_activation_request(),
            operator_id="owner",
        )
        second_draft = await _create_valid_trend_draft(service)
        second_authorization = await service.activate_live_authorization(
            second_draft.draft_id,
            _trend_activation_request(),
            operator_id="owner",
        )
        return (
            service,
            engine,
            first_authorization.authorization_id,
            second_authorization.authorization_id,
        )

    service, engine, stale_authorization_id, current_authorization_id = asyncio.run(setup())
    api_brc_console._owner_trial_flow_service = service
    app.dependency_overrides[require_operator_session] = lambda: OperatorSession(
        username="owner",
        expires_at=int(time.time()) + 3600,
    )

    def fact_collector_must_not_run(*_args, **_kwargs):
        raise AssertionError("fact collector must not run for stale authorization")

    monkeypatch.setattr(
        api_brc_console,
        "_strategy_trial_preflight_fact_collector",
        fact_collector_must_not_run,
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                f"/api/brc/owner-trial-flow/authorizations/{stale_authorization_id}/final-gate-dry-run?run=true"
            )
        assert response.status_code == 200
        payload = response.json()
        assert payload["mode"] == "run"
        assert payload["result"] == "blocked"
        assert payload["authorization_id"] == stale_authorization_id
        assert payload["current_authorization_id"] == current_authorization_id
        assert payload["blockers"] == ["authorization_not_current_for_carrier"]
        assert payload["safety"]["creates_execution_intent"] is False
        assert payload["safety"]["creates_order"] is False
        assert payload["safety"]["exchange_write_api_called"] is False
    finally:
        app.dependency_overrides.pop(require_operator_session, None)
        api_brc_console._owner_trial_flow_service = None
        asyncio.run(engine.dispose())


def test_owner_bounded_execution_final_gate_dry_run_api_run_with_fake_facts(monkeypatch):
    from src.interfaces import api_brc_console
    from src.interfaces.api import app
    from src.interfaces.operator_auth import OperatorSession, require_operator_session

    class FakeFactCollector:
        async def collect(self, _strategy_profile):
            return _clear_fact_snapshot(
                candidate_id="TF-001-live-readonly-v0",
                symbol="SOL/USDT:USDT",
                startup_guard_clear=True,
            )

    async def fake_gateway_binding(_api_module, **_kwargs):
        return {
            "status": "ready_for_test",
            "gateway": object(),
            "blockers": [],
            "gateway_type": "FakeGateway",
        }

    async def setup():
        service, _bridge, engine = await _bridge_service_with_full_execution_tables()
        draft = await _create_valid_trend_draft(service)
        authorization = await service.activate_live_authorization(
            draft.draft_id,
            _trend_activation_request(),
            operator_id="owner",
        )
        return service, engine, authorization.authorization_id

    service, engine, authorization_id = asyncio.run(setup())
    api_brc_console._owner_trial_flow_service = service
    monkeypatch.setenv("TRADING_ENV", "live")
    monkeypatch.setenv("EXCHANGE_TESTNET", "false")
    monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "false")
    monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "false")
    monkeypatch.setenv("BRC_EXECUTION_PERMISSION_MAX", "order_allowed")
    monkeypatch.setattr(
        api_brc_console,
        "_owner_bounded_exchange_gateway_binding",
        fake_gateway_binding,
    )
    monkeypatch.setattr(
        api_brc_console,
        "_strategy_trial_preflight_fact_collector",
        lambda _api_module, **_kwargs: FakeFactCollector(),
    )
    app.dependency_overrides[require_operator_session] = lambda: OperatorSession(
        username="owner",
        expires_at=int(time.time()) + 3600,
    )

    try:
        with TestClient(app) as client:
            response = client.get(
                f"/api/brc/owner-trial-flow/authorizations/{authorization_id}/final-gate-dry-run?run=true"
            )
        assert response.status_code == 200
        payload = response.json()
        assert payload["mode"] == "run"
        assert payload["result"] == "passed"
        assert payload["gateway_binding"]["status"] == "ready_for_test"
        assert payload["final_gate"]["carrier_id"] == "TF-001-live-readonly-v0"
        assert payload["final_gate"]["final_preflight_result"] == "passed"
        assert payload["final_gate"]["non_permissions"]["execution_intent_created"] is False
        assert payload["final_gate"]["non_permissions"]["order_created"] is False

        async def counts():
            session_maker = service._repository._session_maker
            async with session_maker() as session:
                return (
                    await session.scalar(text("SELECT count(*) FROM execution_intents")),
                    await session.scalar(text("SELECT count(*) FROM orders")),
                    await session.scalar(text("SELECT count(*) FROM brc_execution_results")),
                )

        assert asyncio.run(counts()) == (0, 0, 0)
    finally:
        app.dependency_overrides.pop(require_operator_session, None)
        api_brc_console._owner_trial_flow_service = None
        asyncio.run(engine.dispose())


def test_owner_bounded_execution_api_route_converts_unhandled_exception_to_business_status(monkeypatch):
    from src.interfaces import api_brc_console
    from src.interfaces.api import app
    from src.interfaces.operator_auth import OperatorSession, require_operator_session

    class FakeFactCollector:
        async def collect(self, _strategy_profile):
            return _clear_fact_snapshot(startup_guard_clear=True)

    class FakeExecuteService:
        def __init__(self, **_kwargs):
            pass

        async def execute_authorization(self, *_args, **_kwargs):
            raise RuntimeError("simulated recording failure")

    async def setup():
        service, _bridge, engine = await _bridge_service()
        draft = await _create_valid_draft(service)
        authorization = await service.activate_live_authorization(
            draft.draft_id,
            _activation_request(),
            operator_id="owner",
        )
        return service, engine, authorization.authorization_id

    service, engine, authorization_id = asyncio.run(setup())
    api_brc_console._owner_trial_flow_service = service
    monkeypatch.setenv("TRADING_ENV", "live")
    monkeypatch.setenv("EXCHANGE_TESTNET", "false")
    monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "false")
    monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "false")
    monkeypatch.setenv("BRC_EXECUTION_PERMISSION_MAX", "order_allowed")

    async def fake_gateway_binding(_api_module, **_kwargs):
        return {
            "status": "ready_for_test",
            "gateway": object(),
            "blockers": [],
        }

    monkeypatch.setattr(
        api_brc_console,
        "_owner_bounded_exchange_gateway_binding",
        fake_gateway_binding,
    )
    monkeypatch.setattr(
        api_brc_console,
        "_strategy_trial_preflight_fact_collector",
        lambda _api_module, **_kwargs: FakeFactCollector(),
    )
    monkeypatch.setattr(api_brc_console, "OwnerBoundedExecutionService", FakeExecuteService)
    app.dependency_overrides[require_operator_session] = lambda: OperatorSession(
        username="owner",
        expires_at=int(time.time()) + 3600,
    )

    try:
        with TestClient(app) as client:
            response = client.post(
                f"/api/brc/owner-trial-flow/authorizations/{authorization_id}/execute"
            )
        assert response.status_code == 409
        payload = response.json()
        assert payload["error_code"] == "409"
        assert payload["code"] == "owner_bounded_execution_unhandled_exception"
        assert "manual_review_required_before_retry" in payload["blockers"]

        async def counts():
            session_maker = service._repository._session_maker
            async with session_maker() as session:
                return (
                    await session.scalar(text("SELECT count(*) FROM execution_intents")),
                    await session.scalar(text("SELECT count(*) FROM orders")),
                )

        intent_count, order_count = asyncio.run(counts())
        assert intent_count == 0
        assert order_count == 0
    finally:
        app.dependency_overrides.pop(require_operator_session, None)
        api_brc_console._owner_trial_flow_service = None
        asyncio.run(engine.dispose())


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


def test_owner_bounded_gateway_env_modes_separate_read_only_probe_from_execute(monkeypatch):
    from src.interfaces import api_brc_console

    monkeypatch.setenv("TRADING_ENV", "live")
    monkeypatch.setenv("EXCHANGE_TESTNET", "false")
    monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "false")
    monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "false")

    monkeypatch.setenv("BRC_EXECUTION_PERMISSION_MAX", "read_only")
    assert api_brc_console._owner_bounded_gateway_env_blockers() == []
    assert api_brc_console._owner_bounded_gateway_env_blockers(permission_max="order_allowed") == [
        "brc_execution_permission_max_not_order_allowed"
    ]

    monkeypatch.setenv("BRC_EXECUTION_PERMISSION_MAX", "order_allowed")
    assert api_brc_console._owner_bounded_gateway_env_blockers() == [
        "brc_execution_permission_max_not_read_only"
    ]
    assert api_brc_console._owner_bounded_gateway_env_blockers(permission_max="order_allowed") == []


def test_bnb_final_gate_live_read_env_status_can_be_allowed_for_official_execute(monkeypatch):
    from src.interfaces import api_brc_console

    monkeypatch.setenv("TRADING_ENV", "live")
    monkeypatch.setenv("EXCHANGE_TESTNET", "false")
    monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "false")
    monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "false")

    monkeypatch.setenv("BRC_EXECUTION_PERMISSION_MAX", "read_only")
    assert api_brc_console._bnb_final_gate_live_read_env_status()["safe"] is True

    monkeypatch.setenv("BRC_EXECUTION_PERMISSION_MAX", "order_allowed")
    assert api_brc_console._bnb_final_gate_live_read_env_status()["safe"] is False
    execute_status = api_brc_console._bnb_final_gate_live_read_env_status(
        allow_order_permission=True,
    )
    assert execute_status["safe"] is True
    assert execute_status["permission_order_allowed_for_read_only_facts"] is True


def test_owner_bounded_gateway_binding_reports_initialization_error_code(monkeypatch):
    from src.domain.exceptions import FatalStartupError
    from src.interfaces import api_brc_console

    class FailingGateway:
        def __init__(self, **_kwargs):
            self.closed = False

        async def initialize(self):
            raise FatalStartupError("unit gateway init failure", "F-004")

        async def close(self):
            self.closed = True

    monkeypatch.setenv("TRADING_ENV", "live")
    monkeypatch.setenv("EXCHANGE_TESTNET", "false")
    monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "false")
    monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "false")
    monkeypatch.setenv("BRC_EXECUTION_PERMISSION_MAX", "order_allowed")
    monkeypatch.setenv("EXCHANGE_NAME", "binance")
    monkeypatch.setenv("EXCHANGE_API_KEY", "unit-key")
    monkeypatch.setenv("EXCHANGE_API_SECRET", "unit-secret")
    monkeypatch.setattr(api_brc_console, "ExchangeGateway", FailingGateway)

    async def scenario():
        result = await api_brc_console._owner_bounded_exchange_gateway_binding(
            SimpleNamespace(_owner_bounded_exchange_gateway=None),
            permission_max="order_allowed",
        )

        assert result["status"] == "blocked_gateway_initialization_failed"
        assert result["gateway"] is None
        assert "exchange_gateway_initialization_failed:FatalStartupError" in result["blockers"]
        assert "exchange_gateway_initialization_failed:F-004" in result["blockers"]
        assert result["error_code"] == "F-004"
        assert result["error_type"] == "FatalStartupError"

    asyncio.run(scenario())


def test_owner_bounded_gateway_binding_requires_canonical_exchange_credentials(monkeypatch):
    from src.interfaces import api_brc_console

    class GatewayMustNotConstruct:
        def __init__(self, **_kwargs):
            raise AssertionError("gateway must not use BINANCE_* alias credentials")

    monkeypatch.setenv("TRADING_ENV", "live")
    monkeypatch.setenv("EXCHANGE_TESTNET", "false")
    monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "false")
    monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "false")
    monkeypatch.setenv("BRC_EXECUTION_PERMISSION_MAX", "order_allowed")
    monkeypatch.setenv("EXCHANGE_NAME", "binance")
    monkeypatch.delenv("EXCHANGE_API_KEY", raising=False)
    monkeypatch.delenv("EXCHANGE_API_SECRET", raising=False)
    monkeypatch.setenv("BINANCE_API_KEY", "alias-key")
    monkeypatch.setenv("BINANCE_SECRET_KEY", "alias-secret")
    monkeypatch.setattr(api_brc_console, "ExchangeGateway", GatewayMustNotConstruct)

    async def scenario():
        result = await api_brc_console._owner_bounded_exchange_gateway_binding(
            SimpleNamespace(_owner_bounded_exchange_gateway=None),
            permission_max="order_allowed",
        )

        assert result == {
            "status": "blocked_credentials_missing",
            "gateway": None,
            "blockers": ["exchange_credentials_missing"],
        }

    asyncio.run(scenario())


def test_bnb_live_execution_bridge_official_execute_mode_allows_order_permission_env():
    async def scenario():
        service, _bridge, engine = await _bridge_service()
        try:
            draft = await _create_valid_draft(service)
            await service.activate_live_authorization(
                draft.draft_id,
                _activation_request(),
                operator_id="owner",
            )
            bridge = BnbLiveExecutionBridgeDryRunService(
                owner_trial_flow_service=service,
                session_maker=service._repository._session_maker,
                env={
                    "TRADING_ENV": "live",
                    "EXCHANGE_TESTNET": "false",
                    "RUNTIME_CONTROL_API_ENABLED": "false",
                    "RUNTIME_TEST_SIGNAL_INJECTION_ENABLED": "false",
                    "BRC_EXECUTION_PERMISSION_MAX": "order_allowed",
                },
                permission_mode="official_execute",
            )

            result = await bridge.run(
                fact_snapshot=_clear_fact_snapshot(startup_guard_clear=True),
            )

            assert result.final_preflight_result == "passed"
            assert result.final_gate_input_kind == "legacy_request"
            assert result.generic_action_spec_status is None
            assert result.generic_action_spec_action_registry_supported is None
            assert "global_permission_not_order_allowed" not in result.hard_blockers
            assert result.environment_checks["permission_mode"] == "official_execute"
            assert result.non_permissions["execution_intent_created"] is False
            assert result.non_permissions["order_created"] is False
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_generic_action_spec_final_gate_consumes_trend_exact_scope_without_order():
    async def scenario():
        service, bridge, engine = await _bridge_service()
        try:
            draft = await _create_valid_trend_draft(service)
            await service.activate_live_authorization(
                draft.draft_id,
                _trend_activation_request(),
                operator_id="owner",
            )

            result = await bridge.run_action_spec(
                _trend_generic_action_spec(),
                fact_snapshot=_clear_fact_snapshot(
                    candidate_id="TF-001-live-readonly-v0",
                    symbol="SOL/USDT:USDT",
                    side="long",
                    startup_guard_clear=True,
                ),
            )

            assert result.final_preflight_result == "passed"
            assert result.final_gate_input_kind == "generic_action_spec"
            assert result.generic_action_spec_status == "valid_blocked_final_gate"
            assert result.generic_action_spec_action_registry_supported is True
            assert result.carrier_id == "TF-001-live-readonly-v0"
            assert result.symbol == "SOL/USDT:USDT"
            assert result.execution_plan_preview.quantity == Decimal("0.1")
            assert result.execution_plan_preview.max_notional == Decimal("20")
            assert result.final_gate_read_model.market_metadata.state == "clear"
            assert result.final_gate_read_model.protection_readiness.state == "clear"
            assert result.final_gate_read_model.recording_readiness.state == "clear"
            assert result.final_gate_read_model.active_position == result.final_gate_read_model.bnb_position
            assert result.final_gate_read_model.open_order == result.final_gate_read_model.bnb_open_order
            assert "BNB entry" not in result.execution_plan_preview.entry_order.intended_behavior
            assert "real BNB" not in result.owner_execution_trigger.reason
            assert "TF-001-live-readonly-v0 entry" in result.execution_plan_preview.entry_order.intended_behavior
            assert "SOL/USDT:USDT" in result.owner_execution_trigger.reason
            assert result.non_permissions["execution_intent_created"] is False
            assert result.non_permissions["order_created"] is False
            async with service._repository._session_maker() as session:
                intent_count = await session.scalar(text("SELECT count(*) FROM execution_intents"))
                order_count = await session.scalar(text("SELECT count(*) FROM orders"))
            assert intent_count == 0
            assert order_count == 0
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_generic_action_spec_final_gate_consumes_mr_btc_exact_scope_without_order():
    async def scenario():
        service, bridge, engine = await _bridge_service()
        try:
            draft = await _create_valid_mr_btc_draft(service)
            await service.activate_live_authorization(
                draft.draft_id,
                _mr_btc_activation_request(),
                operator_id="owner",
            )

            result = await bridge.run_action_spec(
                _trend_generic_action_spec(
                    family="Mean reversion",
                    strategy_family_id="MR-001-live-readonly-v0",
                    carrier_id="MR-001-BTC-live-readonly-v0",
                    admission_level="L2",
                    status="valid_blocked_final_gate",
                    action_registry_supported=True,
                    symbol="BTC/USDT:USDT",
                    quantity="0.001",
                    max_notional="20",
                    leverage="1",
                ),
                fact_snapshot=_clear_fact_snapshot(
                    candidate_id="MR-001-BTC-live-readonly-v0",
                    symbol="BTC/USDT:USDT",
                    side="long",
                    startup_guard_clear=True,
                    market_min_amount="0.001",
                    market_amount_step="0.001",
                ),
            )

            assert result.final_preflight_result == "passed"
            assert result.final_gate_input_kind == "generic_action_spec"
            assert result.generic_action_spec_status == "valid_blocked_final_gate"
            assert result.generic_action_spec_action_registry_supported is True
            assert result.carrier_id == "MR-001-BTC-live-readonly-v0"
            assert result.symbol == "BTC/USDT:USDT"
            assert result.execution_plan_preview.quantity == Decimal("0.001")
            assert result.execution_plan_preview.max_notional == Decimal("20")
            assert result.non_permissions["execution_intent_created"] is False
            assert result.non_permissions["order_created"] is False
            async with service._repository._session_maker() as session:
                intent_count = await session.scalar(text("SELECT count(*) FROM execution_intents"))
                order_count = await session.scalar(text("SELECT count(*) FROM orders"))
            assert intent_count == 0
            assert order_count == 0
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_generic_action_spec_final_gate_requires_market_metadata_fact():
    async def scenario():
        service, bridge, engine = await _bridge_service()
        try:
            draft = await _create_valid_trend_draft(service)
            await service.activate_live_authorization(
                draft.draft_id,
                _trend_activation_request(),
                operator_id="owner",
            )

            result = await bridge.run_action_spec(
                _trend_generic_action_spec(),
                fact_snapshot=_clear_fact_snapshot(
                    candidate_id="TF-001-live-readonly-v0",
                    symbol="SOL/USDT:USDT",
                    side="long",
                    startup_guard_clear=True,
                    omit_fact_ids={"market_metadata"},
                ),
            )

            assert result.final_preflight_result == "blocked"
            assert "market_metadata_fact_missing" in result.hard_blockers
            assert result.final_gate_read_model.market_metadata.state == "missing"
            assert result.execution_plan_preview.status == "preview_unavailable_invalid_scope"
            assert result.non_permissions["execution_intent_created"] is False
            assert result.non_permissions["order_created"] is False
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_generic_action_spec_final_gate_checks_market_min_notional_and_precision():
    async def scenario():
        service, bridge, engine = await _bridge_service()
        try:
            draft = await _create_valid_trend_draft(service)
            await service.activate_live_authorization(
                draft.draft_id,
                _trend_activation_request(),
                operator_id="owner",
            )

            below_min_notional = await bridge.run_action_spec(
                _trend_generic_action_spec(),
                fact_snapshot=_clear_fact_snapshot(
                    candidate_id="TF-001-live-readonly-v0",
                    symbol="SOL/USDT:USDT",
                    side="long",
                    startup_guard_clear=True,
                    market_min_notional="25",
                ),
            )
            assert below_min_notional.final_preflight_result == "blocked"
            assert "generic_action_spec_below_min_notional" in below_min_notional.hard_blockers
            assert below_min_notional.non_permissions["execution_intent_created"] is False
            assert below_min_notional.non_permissions["order_created"] is False

            step_mismatch = await bridge.run_action_spec(
                _trend_generic_action_spec(),
                fact_snapshot=_clear_fact_snapshot(
                    candidate_id="TF-001-live-readonly-v0",
                    symbol="SOL/USDT:USDT",
                    side="long",
                    startup_guard_clear=True,
                    market_amount_step="0.03",
                ),
            )
            assert step_mismatch.final_preflight_result == "blocked"
            assert "generic_action_spec_quantity_step_mismatch" in step_mismatch.hard_blockers
            assert step_mismatch.non_permissions["execution_intent_created"] is False
            assert step_mismatch.non_permissions["order_created"] is False
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_generic_action_spec_final_gate_requires_reconciliation_protection_and_recording_readiness():
    async def scenario():
        service, bridge, engine = await _bridge_service()
        try:
            draft = await _create_valid_trend_draft(service)
            await service.activate_live_authorization(
                draft.draft_id,
                _trend_activation_request(),
                operator_id="owner",
            )

            missing_reconciliation = await bridge.run_action_spec(
                _trend_generic_action_spec(),
                fact_snapshot=_clear_fact_snapshot(
                    candidate_id="TF-001-live-readonly-v0",
                    symbol="SOL/USDT:USDT",
                    side="long",
                    startup_guard_clear=True,
                    omit_fact_ids={"reconciliation"},
                ),
            )
            assert missing_reconciliation.final_preflight_result == "blocked"
            assert "reconciliation_fact_missing" in missing_reconciliation.hard_blockers
            assert missing_reconciliation.non_permissions["execution_intent_created"] is False
            assert missing_reconciliation.non_permissions["order_created"] is False

            blocked_reconciliation = await bridge.run_action_spec(
                _trend_generic_action_spec(),
                fact_snapshot=_replace_fact(
                    _clear_fact_snapshot(
                        candidate_id="TF-001-live-readonly-v0",
                        symbol="SOL/USDT:USDT",
                        side="long",
                        startup_guard_clear=True,
                    ),
                    TrialPreflightFact(
                        fact_id="reconciliation",
                        status="blocked",
                        source="test_reconciliation",
                        blocking=True,
                        blocker="reconciliation_not_clean",
                        blockers=["reconciliation_not_clean"],
                        observed_at_ms=int(time.time() * 1000),
                        evidence={"status": "mismatch"},
                    ),
                ),
            )
            assert blocked_reconciliation.final_preflight_result == "blocked"
            assert "reconciliation_not_clean" in blocked_reconciliation.hard_blockers
            assert blocked_reconciliation.non_permissions["execution_intent_created"] is False
            assert blocked_reconciliation.non_permissions["order_created"] is False

            missing_protection = await bridge.run_action_spec(
                _trend_generic_action_spec(),
                fact_snapshot=_clear_fact_snapshot(
                    candidate_id="TF-001-live-readonly-v0",
                    symbol="SOL/USDT:USDT",
                    side="long",
                    startup_guard_clear=True,
                    omit_fact_ids={"protection_readiness"},
                ),
            )
            assert missing_protection.final_preflight_result == "blocked"
            assert "protection_readiness_fact_missing" in missing_protection.hard_blockers
            assert missing_protection.non_permissions["execution_intent_created"] is False
            assert missing_protection.non_permissions["order_created"] is False

            missing_recording = await bridge.run_action_spec(
                _trend_generic_action_spec(),
                fact_snapshot=_clear_fact_snapshot(
                    candidate_id="TF-001-live-readonly-v0",
                    symbol="SOL/USDT:USDT",
                    side="long",
                    startup_guard_clear=True,
                    omit_fact_ids={"recording_readiness"},
                ),
            )
            assert missing_recording.final_preflight_result == "blocked"
            assert "recording_readiness_fact_missing" in missing_recording.hard_blockers
            assert missing_recording.non_permissions["execution_intent_created"] is False
            assert missing_recording.non_permissions["order_created"] is False

            not_ready = await bridge.run_action_spec(
                _trend_generic_action_spec(),
                fact_snapshot=_clear_fact_snapshot(
                    candidate_id="TF-001-live-readonly-v0",
                    symbol="SOL/USDT:USDT",
                    side="long",
                    startup_guard_clear=True,
                    protection_price_source_ready=False,
                    recording_audit_writable=False,
                    recording_result_envelope_writable=False,
                ),
            )
            assert not_ready.final_preflight_result == "blocked"
            assert "protection_price_source_missing" in not_ready.hard_blockers
            assert "audit_write_unavailable" in not_ready.hard_blockers
            assert "execution_result_envelope_write_unavailable" in not_ready.hard_blockers
            assert not_ready.non_permissions["execution_intent_created"] is False
            assert not_ready.non_permissions["order_created"] is False
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_generic_action_spec_final_gate_fails_closed_for_wrong_scope_and_fact_binding():
    async def scenario():
        service, bridge, engine = await _bridge_service()
        try:
            draft = await _create_valid_trend_draft(service)
            await service.activate_live_authorization(
                draft.draft_id,
                _trend_activation_request(),
                operator_id="owner",
            )

            wrong_specs = [
                ("symbol_mismatch", _trend_generic_action_spec(symbol="BNB/USDT:USDT")),
                ("side_mismatch", _trend_generic_action_spec(side="short")),
                ("quantity_mismatch", _trend_generic_action_spec(quantity="0.2")),
                ("cap_mismatch", _trend_generic_action_spec(max_notional="21")),
                ("leverage_mismatch", _trend_generic_action_spec(leverage="2")),
                (
                    "generic_action_spec_max_attempts_mismatch",
                    _trend_generic_action_spec(max_attempts=2),
                ),
                (
                    "generic_action_spec_protection_plan_mismatch",
                    _trend_generic_action_spec(protection_mode="none"),
                ),
                (
                    "generic_action_spec_review_requirement_mismatch",
                    _trend_generic_action_spec(review_requirement="optional_review"),
                ),
            ]
            for expected_blocker, spec in wrong_specs:
                result = await bridge.run_action_spec(
                    spec,
                    fact_snapshot=_clear_fact_snapshot(
                        candidate_id="TF-001-live-readonly-v0",
                        symbol="SOL/USDT:USDT",
                        side="long",
                        startup_guard_clear=True,
                    ),
                )
                assert result.final_preflight_result == "blocked"
                assert expected_blocker in result.hard_blockers
                assert result.non_permissions["execution_intent_created"] is False
                assert result.non_permissions["order_created"] is False

            wrong_fact_result = await bridge.run_action_spec(
                _trend_generic_action_spec(),
                fact_snapshot=_clear_fact_snapshot(startup_guard_clear=True),
            )
            assert wrong_fact_result.final_preflight_result == "blocked"
            assert "preflight_fact_symbol_mismatch" in wrong_fact_result.hard_blockers
            assert "preflight_fact_candidate_mismatch" in wrong_fact_result.hard_blockers
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_generic_action_spec_final_gate_fails_closed_for_non_catalog_carrier():
    async def scenario():
        service, bridge, engine = await _bridge_service()
        try:
            result = await bridge.run_action_spec(
                _trend_generic_action_spec(
                    carrier_id="VE-001-live-readonly-v0",
                    strategy_family_id="VE-001-live-readonly-v0",
                    action_registry_supported=True,
                ),
                fact_snapshot=_clear_fact_snapshot(
                    candidate_id="VE-001-live-readonly-v0",
                    symbol="SOL/USDT:USDT",
                    side="long",
                    startup_guard_clear=True,
                ),
            )

            assert result.final_preflight_result == "blocked"
            assert "unsupported_carrier" in result.hard_blockers
            assert result.non_permissions["execution_intent_created"] is False
            assert result.non_permissions["order_created"] is False
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_generic_action_spec_final_gate_keeps_volatility_non_action_and_mr_wrong_scope_blocked():
    async def scenario():
        service, bridge, engine = await _bridge_service()
        try:
            volatility = await bridge.run_action_spec(
                _trend_generic_action_spec(
                    family="Volatility expansion",
                    strategy_family_id="VB-001-live-readonly-v0",
                    carrier_id="VB-001-live-readonly-v0",
                    admission_level="L2",
                    status="proposal_non_action",
                    action_registry_supported=False,
                ),
                fact_snapshot=_clear_fact_snapshot(
                    candidate_id="VB-001-live-readonly-v0",
                    symbol="SOL/USDT:USDT",
                    side="long",
                    startup_guard_clear=True,
                ),
            )

            assert volatility.final_preflight_result == "blocked"
            assert "generic_action_spec_status_not_final_gate_ready" in volatility.hard_blockers
            assert "generic_action_spec_not_action_registry_supported" in volatility.hard_blockers
            assert "unsupported_carrier" in volatility.hard_blockers
            assert volatility.non_permissions["execution_intent_created"] is False
            assert volatility.non_permissions["order_created"] is False
            assert volatility.owner_execution_trigger.enabled is False

            mr_wrong_scope = await bridge.run_action_spec(
                _trend_generic_action_spec(
                    family="Mean reversion",
                    strategy_family_id="MR-001-live-readonly-v0",
                    carrier_id="MR-001-live-readonly-v0",
                    admission_level="L2",
                    status="valid_blocked_final_gate",
                    action_registry_supported=True,
                    symbol="SOL/USDT:USDT",
                    quantity="0.1",
                ),
                fact_snapshot=_clear_fact_snapshot(
                    candidate_id="MR-001-live-readonly-v0",
                    symbol="SOL/USDT:USDT",
                    side="long",
                    startup_guard_clear=True,
                ),
            )

            assert mr_wrong_scope.final_preflight_result == "blocked"
            assert "symbol_mismatch" in mr_wrong_scope.hard_blockers
            assert "quantity_mismatch" in mr_wrong_scope.hard_blockers
            assert "missing_explicit_owner_live_authorization" in mr_wrong_scope.hard_blockers
            assert mr_wrong_scope.non_permissions["execution_intent_created"] is False
            assert mr_wrong_scope.non_permissions["order_created"] is False
            assert mr_wrong_scope.owner_execution_trigger.enabled is False
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
        lambda _api_module, **_kwargs: FakeCollector(),
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


def test_preflight_collector_uses_owner_bounded_gateway_for_market_and_protection_readiness(monkeypatch):
    from src.interfaces import api_brc_console

    class CleanLocalPositionRepo:
        async def list_active(self, *, symbol=None, limit=20):
            return []

    class CleanLocalOrderRepo:
        async def get_open_orders(self, symbol=None):
            return []

    class ClearGks:
        def get_state(self):
            return {"active": False, "source": "test_gks"}

    class ClearStartupGuard:
        def get_state(self):
            return {
                "armed": True,
                "runtime_started": False,
                "runtime_safety_context_bound": True,
                "runtime_state": "scoped_safety_context_bound",
                "source": "test_startup_guard",
            }

    class OwnerBoundedReadOnlyGateway:
        def __init__(self):
            self.market_info_symbols = []
            self.place_order_called = False

        async def get_market_info(self, symbol: str):
            self.market_info_symbols.append(symbol)
            return {
                "symbol": symbol,
                "min_quantity": "0.01",
                "step_size": Decimal("0"),
                "quantity_precision": "0.01",
                "min_notional": "5",
                "price_precision": "1",
            }

        async def fetch_ticker_price(self, symbol: str):
            return Decimal("100")

        async def place_order(self, *_args, **_kwargs):
            self.place_order_called = True
            raise AssertionError("preflight collector must not place orders")

    gateway = OwnerBoundedReadOnlyGateway()

    class FakeApiModule:
        _position_repo = CleanLocalPositionRepo()
        _order_repo = CleanLocalOrderRepo()
        _global_kill_switch_service = ClearGks()
        _startup_trading_guard_service = ClearStartupGuard()
        _startup_reconciliation_summary = {
            "status": "clean",
            "reconciliation_status": "clean",
            "source": "test_reconciliation",
        }
        _owner_bounded_exchange_gateway = gateway

        @staticmethod
        def _account_getter():
            return SimpleNamespace(
                total_balance=Decimal("30.00"),
                available_balance=Decimal("30.00"),
                timestamp=int(time.time() * 1000),
            )

    monkeypatch.setenv("TRADING_ENV", "live")
    monkeypatch.setenv("EXCHANGE_TESTNET", "true")
    monkeypatch.setenv("BRC_EXECUTION_PERMISSION_MAX", "read_only")
    monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "false")
    monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "false")

    async def scenario():
        service, _bridge, engine = await _bridge_service_with_full_execution_tables()
        try:
            profile = api_brc_console._strategy_profile_for_owner_action_scope(
                carrier_id="TF-001-live-readonly-v0",
                symbol="SOL/USDT:USDT",
                side="long",
            )
            collector = api_brc_console._strategy_trial_preflight_fact_collector(
                FakeApiModule(),
                session_maker=service._repository._session_maker,
            )
            snapshot = await collector.collect(profile)
            facts = snapshot.fact_map()

            assert facts["market_metadata"].status == "clear"
            assert facts["market_metadata"].source == "bound_exchange_gateway_market_info"
            assert facts["market_metadata"].evidence["symbol"] == "SOL/USDT:USDT"
            assert facts["protection_readiness"].status == "clear"
            assert facts["protection_readiness"].evidence["tp_ready"] is True
            assert facts["protection_readiness"].evidence["sl_ready"] is True
            assert facts["protection_readiness"].evidence["price_source_ready"] is True
            assert facts["recording_readiness"].status == "clear"
            assert gateway.market_info_symbols == ["SOL/USDT:USDT"]
            assert gateway.place_order_called is False
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_preflight_recording_readiness_requires_full_result_envelope(monkeypatch):
    from src.interfaces import api_brc_console

    class CleanLocalPositionRepo:
        async def list_active(self, *, symbol=None, limit=20):
            return []

    class CleanLocalOrderRepo:
        async def get_open_orders(self, symbol=None):
            return []

    class ClearGks:
        def get_state(self):
            return {"active": False, "source": "test_gks"}

    class ClearStartupGuard:
        def get_state(self):
            return {
                "armed": True,
                "runtime_started": False,
                "runtime_safety_context_bound": True,
                "runtime_state": "scoped_safety_context_bound",
                "source": "test_startup_guard",
            }

    class OwnerBoundedReadOnlyGateway:
        async def get_market_info(self, symbol: str):
            return {
                "symbol": symbol,
                "min_quantity": "0.01",
                "step_size": "0.01",
                "min_notional": "5",
                "price_precision": "1",
            }

        async def fetch_ticker_price(self, symbol: str):
            return Decimal("100")

    class FakeApiModule:
        _position_repo = CleanLocalPositionRepo()
        _order_repo = CleanLocalOrderRepo()
        _global_kill_switch_service = ClearGks()
        _startup_trading_guard_service = ClearStartupGuard()
        _startup_reconciliation_summary = {
            "status": "clean",
            "reconciliation_status": "clean",
            "source": "test_reconciliation",
        }
        _owner_bounded_exchange_gateway = OwnerBoundedReadOnlyGateway()

        @staticmethod
        def _account_getter():
            return SimpleNamespace(
                total_balance=Decimal("30.00"),
                available_balance=Decimal("30.00"),
                timestamp=int(time.time() * 1000),
            )

    monkeypatch.setenv("TRADING_ENV", "live")
    monkeypatch.setenv("EXCHANGE_TESTNET", "true")
    monkeypatch.setenv("BRC_EXECUTION_PERMISSION_MAX", "read_only")
    monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "false")
    monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "false")

    async def scenario():
        service, _bridge, engine = await _bridge_service()
        try:
            profile = api_brc_console._strategy_profile_for_owner_action_scope(
                carrier_id="TF-001-live-readonly-v0",
                symbol="SOL/USDT:USDT",
                side="long",
            )
            collector = api_brc_console._strategy_trial_preflight_fact_collector(
                FakeApiModule(),
                session_maker=service._repository._session_maker,
            )
            snapshot = await collector.collect(profile)
            recording = snapshot.fact_map()["recording_readiness"]

            assert recording.status == "unavailable"
            assert "execution_intents_write_unavailable" in recording.blockers
            assert "orders_write_unavailable" in recording.blockers
            assert "review_write_unavailable" in recording.blockers
            assert "audit_write_unavailable" in recording.blockers
            assert "execution_result_envelope_write_unavailable" in recording.blockers
            assert recording.evidence["execution_intents_writable"] is False
            assert recording.evidence["orders_writable"] is False
            assert recording.evidence["result_envelope_writable"] is False
            assert snapshot.execution_intent_created is False
            assert snapshot.order_created is False
        finally:
            await engine.dispose()

    asyncio.run(scenario())


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
        assert facts["reconciliation"].evidence["pg_active_position_count"] == 0
        assert facts["reconciliation"].evidence["pg_open_order_count"] == 0
        assert facts["reconciliation"].evidence["exchange_active_position_count"] == 0
        assert facts["reconciliation"].evidence["exchange_open_order_count"] == 0
        assert facts["reconciliation"].evidence["scoped_symbol"] in {
            "BNBUSDT",
            "BNB/USDT:USDT",
        }
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
        assert fact.evidence["exchange_open_order_count"] == 1
        assert fact.evidence["exchange_bnb_open_order_count"] == 1

    asyncio.run(scenario())


def test_bnb_final_gate_reconciliation_allows_retryable_failed_pre_order_intent(monkeypatch):
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
            return []

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
            "retryable_failed_execution_intents": 1,
            "blocking_execution_intents": 0,
            "retry_classification": "retryable_failed_intent_present",
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

        assert fact.status == "clear"
        assert fact.blocker is None
        assert fact.evidence["status"] == "clean_for_retry"
        assert fact.evidence["pg_execution_intents_count"] == 1
        assert fact.evidence["pg_blocking_execution_intents_count"] == 0
        assert fact.evidence["retryable_failed_execution_intents_count"] == 1
        assert fact.evidence["retry_classification"] == "retryable_failed_intent_present"

    asyncio.run(scenario())


def test_bnb_final_gate_reconciliation_ignores_closed_consumed_owner_trial(monkeypatch):
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
            return []

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
            "execution_intents": 3,
            "retryable_failed_execution_intents": 0,
            "blocking_execution_intents": 0,
            "closed_execution_intents": 3,
            "retry_classification": "closed_owner_trial_intent_present",
            "orders": 0,
            "historical_closed_orders": 2,
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

        assert fact.status == "clear"
        assert fact.blocker is None
        assert fact.evidence["status"] == "clean"
        assert fact.evidence["pg_execution_intents_count"] == 3
        assert fact.evidence["pg_blocking_execution_intents_count"] == 0
        assert fact.evidence["pg_closed_execution_intents_count"] == 3
        assert fact.evidence["pg_orders_count"] == 0
        assert fact.evidence["pg_historical_closed_orders_count"] == 2
        assert fact.evidence["retry_classification"] == "closed_owner_trial_intent_present"

    asyncio.run(scenario())


def test_bnb_final_gate_closed_owner_trial_intent_classifier_requires_consumed_closeout():
    from src.interfaces import api_brc_console

    completed_consumed = {
        "status": "completed",
        "authorization_consumed": True,
        "authorization_metadata": {},
    }
    assert api_brc_console._is_closed_owner_trial_intent_row(completed_consumed) is True

    completed_not_consumed = dict(completed_consumed)
    completed_not_consumed["authorization_consumed"] = False
    assert api_brc_console._is_closed_owner_trial_intent_row(completed_not_consumed) is False

    closed_row = {
        "status": "failed",
        "authorization_consumed": True,
        "authorization_metadata": {
            "trial_final_state": "completed_with_recovery_flat",
            "next_trade_requires_new_owner_authorization": True,
        },
    }
    assert api_brc_console._is_closed_owner_trial_intent_row(closed_row) is True

    not_consumed = dict(closed_row)
    not_consumed["authorization_consumed"] = False
    assert api_brc_console._is_closed_owner_trial_intent_row(not_consumed) is False

    ambiguous = {
        "authorization_consumed": True,
        "authorization_metadata": {
            "trial_final_state": "entry_filled_protection_unknown",
            "next_trade_requires_new_owner_authorization": True,
        },
    }
    assert api_brc_console._is_closed_owner_trial_intent_row(ambiguous) is False


def test_bnb_final_gate_pg_order_status_blocking_classifier():
    from src.interfaces import api_brc_console

    assert api_brc_console._is_blocking_pg_order_status("OPEN") is True
    assert api_brc_console._is_blocking_pg_order_status("PARTIALLY_FILLED") is True
    assert api_brc_console._is_blocking_pg_order_status("FILLED") is False
    assert api_brc_console._is_blocking_pg_order_status("CANCELED") is False


def test_bnb_final_gate_symbol_variants_cover_profile_and_runtime_symbols():
    from src.interfaces import api_brc_console

    assert api_brc_console._bnb_final_gate_symbol_variants("BNBUSDT") == [
        "BNB/USDT:USDT",
        "BNBUSDT",
    ]
    assert api_brc_console._bnb_final_gate_symbol_variants("BNB/USDT:USDT") == [
        "BNB/USDT:USDT",
        "BNBUSDT",
    ]


def test_owner_action_scoped_clearance_resolver_supports_exact_trend_scope():
    from src.interfaces import api_brc_console

    profile = SimpleNamespace(
        candidate_id="TF-001-live-readonly-v0",
        symbol="SOL/USDT:USDT",
        side="long",
    )

    carrier = api_brc_console._owner_action_scoped_clearance_carrier(profile)

    assert carrier is not None
    assert carrier.carrier_id == "TF-001-live-readonly-v0"
    assert carrier.symbol == "SOL/USDT:USDT"


def test_owner_action_scoped_clearance_resolver_fails_closed_for_non_catalog_or_wrong_scope():
    from src.interfaces import api_brc_console

    assert (
        api_brc_console._owner_action_scoped_clearance_carrier(
            SimpleNamespace(
                candidate_id="VE-001-live-readonly-v0",
                symbol="SOL/USDT:USDT",
                side="long",
            )
        )
        is None
    )
    assert (
        api_brc_console._owner_action_scoped_clearance_carrier(
            SimpleNamespace(
                candidate_id="TF-001-live-readonly-v0",
                symbol="ETH/USDT:USDT",
                side="long",
            )
        )
        is None
    )
    assert (
        api_brc_console._owner_action_scoped_clearance_carrier(
            SimpleNamespace(
                candidate_id="TF-001-live-readonly-v0",
                symbol="SOL/USDT:USDT",
                side="short",
            )
        )
        is None
    )


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


def test_bnb_final_gate_scoped_startup_guard_overlays_runtime_guard(monkeypatch):
    from src.application.strategy_trial_readiness import build_bnb_strategy_trial_readiness
    from src.interfaces import api_brc_console

    now_ms = int(time.time() * 1000)

    class FakeGks:
        def get_state(self):
            return {"active": False, "source": "test_gks_clear"}

    class FakeStartupGuard:
        def get_state(self):
            return {
                "armed": False,
                "source": "startup_default_block",
                "reason": "STARTUP_TRADING_GUARD_NOT_ARMED",
            }

    class FakeApiModule:
        _global_kill_switch_service = FakeGks()
        _startup_trading_guard_service = FakeStartupGuard()
        _startup_reconciliation_summary = {
            "status": "unavailable",
            "source": "unavailable",
            "reason": "startup_reconciliation_summary_unavailable",
        }
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
        if clearance_type != "startup_guard":
            return None
        return {
            "clearance_id": "startup_guard-auth-scoped",
            "authorization_id": "auth-scoped",
            "expires_at_ms": now_ms + 60_000,
            "updated_at_ms": now_ms,
            "reason": "test_scoped_startup_guard",
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
        profile = build_bnb_strategy_trial_readiness().strategy_profile
        collector = api_brc_console._strategy_trial_preflight_fact_collector(FakeApiModule())
        snapshot = await collector.collect(profile)
        facts = snapshot.fact_map()

        assert facts["startup_guard"].status == "clear"
        assert facts["startup_guard"].source == "pg_scoped_startup_guard_arm"
        assert facts["startup_guard"].evidence["armed"] is True
        assert facts["startup_guard"].evidence["runtime_started"] is True
        assert facts["startup_guard"].evidence["runtime_safety_context_bound"] is True
        assert facts["startup_guard"].evidence["authorization_id"] == "auth-scoped"
        assert facts["reconciliation"].status == "clear"
        assert facts["reconciliation"].source == "bnb_final_gate_read_only_reconciliation"

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


def test_bnb_final_gate_live_read_only_exchange_error_fails_closed_and_closes(monkeypatch):
    from src.application.strategy_trial_readiness import build_bnb_strategy_trial_readiness
    from src.interfaces import api_brc_console

    class FakeApiModule:
        _exchange_gateway = None

    class FailingReadOnlyClient:
        def __init__(self):
            self.closed = False

        async def fetch_balance(self, params=None):
            raise RuntimeError('binance {"code":-2008,"msg":"Invalid Api-Key ID."}')

        async def fetch_positions(self, symbol=None):
            raise AssertionError("positions must not be read after balance failure")

        async def fetch_open_orders(self, symbol, params=None):
            raise AssertionError("orders must not be read after balance failure")

        async def close(self):
            self.closed = True

    client = FailingReadOnlyClient()
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
            "close_after_read": True,
        },
    )

    async def scenario():
        profile = build_bnb_strategy_trial_readiness().strategy_profile
        facts_reader = api_brc_console._BnbFinalGateLiveReadOnlyFacts(FakeApiModule())
        facts = await facts_reader.read(profile)

        assert facts["available"] is False
        assert facts["reason"] == "exchange_read_failed:RuntimeError:exchange_error_code:-2008"
        assert facts["errors"] == [facts["reason"]]
        assert facts["account_facts"]["external_call_performed"] is False
        assert facts["positions"] == []
        assert facts["open_orders"] == []
        assert "Invalid Api-Key ID" not in repr(facts)
        assert client.closed is True

    asyncio.run(scenario())


def test_bnb_final_gate_collector_preserves_sanitized_exchange_error_reason(monkeypatch):
    from src.application.strategy_trial_readiness import build_bnb_strategy_trial_readiness
    from src.interfaces import api_brc_console

    class FakeGks:
        def get_state(self):
            return {"active": False, "source": "test_gks"}

    class FakeStartupGuard:
        def get_state(self):
            return {
                "armed": True,
                "runtime_started": False,
                "runtime_safety_context_bound": True,
                "runtime_state": "scoped_safety_context_bound",
                "source": "test_startup_guard",
            }

    class FakeApiModule:
        _global_kill_switch_service = FakeGks()
        _startup_trading_guard_service = FakeStartupGuard()
        _startup_reconciliation_summary = {
            "status": "clean",
            "source": "test_reconciliation",
        }
        _exchange_gateway = None

    class FailingReadOnlyClient:
        async def fetch_balance(self, params=None):
            raise RuntimeError('binance {"code":-2008,"msg":"Invalid Api-Key ID."}')

        async def fetch_positions(self, symbol=None):
            raise AssertionError("positions must not be read after balance failure")

        async def fetch_open_orders(self, symbol, params=None):
            raise AssertionError("orders must not be read after balance failure")

        async def get_market_info(self, symbol):
            raise RuntimeError("market_info_unavailable")

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
            "client": FailingReadOnlyClient(),
            "source": "test_bnb_read_only_client",
            "close_after_read": True,
        },
    )

    async def scenario():
        profile = build_bnb_strategy_trial_readiness().strategy_profile
        collector = api_brc_console._strategy_trial_preflight_fact_collector(FakeApiModule())
        snapshot = await collector.collect(profile)
        facts = snapshot.fact_map()

        assert snapshot.execution_intent_created is False
        assert snapshot.order_created is False
        assert "account_facts_unavailable" in snapshot.blockers
        assert "active_position_check_required_before_rehearsal" in snapshot.blockers
        assert "open_order_check_required_before_rehearsal" in snapshot.blockers
        assert facts["account_facts"].evidence["reason"] == (
            "exchange_read_failed:RuntimeError:exchange_error_code:-2008"
        )
        assert facts["active_position"].evidence["reason"] == (
            "active position read failed: RuntimeError"
        )
        assert "Invalid Api-Key ID" not in repr(snapshot.to_response_dict())

    asyncio.run(scenario())


def test_bnb_final_gate_fallback_facts_do_not_bypass_unsafe_live_environment(monkeypatch):
    from src.application.strategy_trial_readiness import build_bnb_strategy_trial_readiness
    from src.interfaces import api_brc_console

    class CleanLocalPositionRepo:
        async def list_active(self, *, symbol=None, limit=20):
            return []

    class CleanLocalOrderRepo:
        async def get_open_orders(self, symbol=None):
            return []

    class ClearGks:
        def get_state(self):
            return {"active": False, "source": "test_gks"}

    class ClearStartupGuard:
        def get_state(self):
            return {
                "armed": True,
                "runtime_started": False,
                "runtime_safety_context_bound": True,
                "runtime_state": "scoped_safety_context_bound",
                "source": "test_startup_guard",
            }

    class FakeApiModule:
        _position_repo = CleanLocalPositionRepo()
        _order_repo = CleanLocalOrderRepo()
        _global_kill_switch_service = ClearGks()
        _startup_trading_guard_service = ClearStartupGuard()
        _startup_reconciliation_summary = {
            "status": "clean",
            "reconciliation_status": "clean",
            "source": "test_reconciliation",
        }
        _exchange_gateway = None

        @staticmethod
        def _account_getter():
            return SimpleNamespace(
                total_balance=Decimal("30.00"),
                available_balance=Decimal("30.00"),
                timestamp=int(time.time() * 1000),
            )

    def fail_if_called(_api_module):
        raise AssertionError("unsafe env fallback must not create a live read client")

    monkeypatch.setenv("TRADING_ENV", "live")
    monkeypatch.setenv("EXCHANGE_TESTNET", "true")
    monkeypatch.setenv("BRC_EXECUTION_PERMISSION_MAX", "read_only")
    monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "false")
    monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "false")
    monkeypatch.setattr(api_brc_console, "_bnb_final_gate_read_only_client", fail_if_called)

    async def scenario():
        service, bridge, engine = await _bridge_service()
        try:
            draft = await _create_valid_draft(service)
            await service.activate_live_authorization(
                draft.draft_id,
                _activation_request(),
                operator_id="owner",
            )
            bridge._env = {
                "TRADING_ENV": "live",
                "EXCHANGE_TESTNET": "true",
                "RUNTIME_CONTROL_API_ENABLED": "false",
                "RUNTIME_TEST_SIGNAL_INJECTION_ENABLED": "false",
                "BRC_EXECUTION_PERMISSION_MAX": "read_only",
            }

            profile = build_bnb_strategy_trial_readiness().strategy_profile
            collector = api_brc_console._strategy_trial_preflight_fact_collector(FakeApiModule())
            snapshot = await collector.collect(profile)
            result = await bridge.run(fact_snapshot=snapshot)

            assert result.final_preflight_result == "blocked"
            assert result.bridge_status == "blocked_before_execution_boundary"
            assert "exchange_testnet_false" in result.hard_blockers
            assert result.environment_checks["exchange_testnet_false"] is False
            assert result.non_permissions["execution_intent_created"] is False
            assert result.non_permissions["order_created"] is False
            assert result.non_permissions["order_permission_granted"] is False
        finally:
            await engine.dispose()

    asyncio.run(scenario())
