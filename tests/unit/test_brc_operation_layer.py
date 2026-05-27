from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.application.bounded_risk_campaign_service import BoundedRiskCampaignService
from src.application.brc_operation_layer import (
    BrcOperationService,
    InMemoryOperationRepository,
    OperationLayerError,
    OperationLayerReaders,
)
from tests.unit.test_brc_campaign_service import InMemoryBrcRepo


def _default_runtime_summary() -> dict:
    return {
        "runtime_bound": True,
        "profile": "brc_btc_eth_testnet_runtime",
        "testnet": True,
        "current_runtime_state": "observe",
        "gks_active": True,
        "startup_guard_armed": False,
        "runtime_control_api_enabled": True,
        "runtime_test_signal_injection_enabled": True,
        "live_ready": False,
    }


async def _async_dict(value: dict) -> dict:
    return dict(value)


async def _async_bool(value: bool) -> bool:
    return value


async def _campaign_service(*, create_campaign: bool = True):
    repo = InMemoryBrcRepo()
    service = BoundedRiskCampaignService(repo)
    await service.initialize()
    if create_campaign:
        await service.create_campaign(
            bucket_id="bucket",
            authorized_amount=Decimal("500"),
            max_campaign_loss=Decimal("120"),
            profit_protect_trigger=Decimal("100"),
            reason="test",
        )
    return service, repo


async def _operation_service(
    *,
    market_state: dict | None = None,
    audit_writable: bool = True,
    ttl_ms: int = 300_000,
    runtime_adapter: bool = True,
    runtime_stop_adapter: bool = False,
    runtime_stop_failure: Exception | None = None,
    fixed_rehearsal_adapter: bool = False,
    fixed_rehearsal_failure: Exception | None = None,
    create_campaign: bool = True,
    runtime_state: dict | None = None,
):
    brc, brc_repo = await _campaign_service(create_campaign=create_campaign)
    op_repo = InMemoryOperationRepository()
    market = market_state if market_state is not None else {
        "active_position_count": 0,
        "open_order_count": 0,
        "all_local_flat": True,
        "data_source": "unit",
        "source": "local_pg",
        "truth_level": "summary",
        "reconciliation_status": {"status": "not_available"},
    }
    runtime = _default_runtime_summary()
    runtime.update(runtime_state or {})
    fixed_rehearsal_calls = []
    runtime_stop_calls = []

    async def _runtime_summary():
        return dict(runtime)

    async def _market_summary():
        return dict(market)

    async def _audit_writable():
        return audit_writable

    async def _review_packet(_input):
        return {"packet": "review", "mutation_executed": False, "live_ready": False}

    async def _runtime_transition(target_state, input_params):
        return {
            "status": target_state,
            "operation_id": input_params["operation_id"],
            "preflight_id": input_params["preflight_id"],
            "places_orders": False,
            "live_ready": False,
        }

    async def _runtime_stop(input_params):
        runtime_stop_calls.append(dict(input_params))
        if runtime_stop_failure is not None:
            raise runtime_stop_failure
        runtime["current_runtime_state"] = "hard_locked"
        return {
            "status": "hard_locked",
            "runtime_state": "hard_locked",
            "stopped_by_owner": True,
            "emergency_stop": True,
            "operation_id": input_params["operation_id"],
            "preflight_id": input_params["preflight_id"],
            "authorization_source": input_params["authorization_source"],
            "flatten_executed": False,
            "orders_cancelled": False,
            "places_orders": False,
            "closes_positions": False,
            "cancels_orders": False,
            "live_ready": False,
        }

    async def _fixed_rehearsal(input_params):
        fixed_rehearsal_calls.append(dict(input_params))
        if fixed_rehearsal_failure is not None:
            raise fixed_rehearsal_failure
        return {
            "workflow_run_id": f"op-wf-{input_params['operation_id']}",
            "campaign_id": "brc-rehearsal",
            "mutation_executed": True,
            "withdrawal_executed": False,
            "live_ready": False,
            "final_inventory": {"all_flat": True},
            "review_packet": {"campaign_id": "brc-rehearsal", "ready": True},
            "evidence": {"packet": "fixed-testnet-rehearsal"},
            "readiness": {"mode": "testnet_ready", "live_ready": False},
            "steps": [
                {"name": "campaign_created", "payload": {"campaign_id": "brc-rehearsal"}},
                {"name": "review_decision", "payload": {"review_id": "review-rehearsal"}},
                {"name": "finalized", "payload": {"campaign_id": "brc-rehearsal"}},
            ],
        }

    service = BrcOperationService(
        repository=op_repo,
        brc_campaign_service=brc,
        readers=OperationLayerReaders(
            runtime_summary=_runtime_summary,
            markets_orders_summary=_market_summary,
            audit_writable=_audit_writable,
            review_packet_reader=_review_packet,
            runtime_transition=_runtime_transition if runtime_adapter else None,
            runtime_stop_executor=_runtime_stop if runtime_stop_adapter else None,
            fixed_rehearsal_executor=_fixed_rehearsal if fixed_rehearsal_adapter else None,
        ),
        ttl_ms=ttl_ms,
    )
    await service.initialize()
    market["fixed_rehearsal_calls"] = fixed_rehearsal_calls
    market["runtime_stop_calls"] = runtime_stop_calls
    market["runtime_state"] = runtime
    return service, op_repo, brc_repo, market


async def _switch_preflight(service: BrcOperationService):
    return await service.preflight(
        operation_type="switch_playbook",
        requested_by="owner",
        input_params={
            "target_playbook_id": "PB-004-BRC-CONTROLLED-TESTNET",
            "reason_text": "owner authorized controlled rehearsal",
            "evidence_refs": ["docs/adr/0012-bounded-risk-campaign-system.md"],
        },
        source={"kind": "ui"},
    )


@pytest.mark.asyncio
async def test_operation_capabilities_model_supported_and_forbidden_operations():
    service, _, _, _ = await _operation_service()
    capabilities = {item.operation_type: item for item in service.capabilities()}

    assert capabilities["switch_playbook"].status == "enabled"
    assert capabilities["switch_playbook"].executable_through_operation is True
    for operation_type in [
        "write_review_decision",
        "start_review",
        "enter_observe",
        "enter_pause",
        "enter_strategy_or_monitor",
    ]:
        assert capabilities[operation_type].status == "enabled"
        assert capabilities[operation_type].executable_through_operation is True
    assert capabilities["run_fixed_testnet_rehearsal"].status == "unavailable"
    assert capabilities["run_fixed_testnet_rehearsal"].executable_through_operation is False
    assert capabilities["withdrawal"].status == "forbidden"
    assert capabilities["llm_direct_execution"].status == "forbidden"
    assert capabilities["emergency_flatten"].status == "preflight_dry_run_available"
    assert capabilities["emergency_flatten"].executable_through_operation is False
    assert capabilities["emergency_flatten"].dry_run_only is True
    assert capabilities["emergency_flatten"].confirmation_required is True
    assert capabilities["emergency_stop_runtime"].status == "preflight_planning_available"
    assert capabilities["emergency_stop_runtime"].executable_through_operation is False


@pytest.mark.asyncio
async def test_emergency_stop_runtime_capability_becomes_executable_when_adapter_available():
    service, _, _, _ = await _operation_service(runtime_stop_adapter=True)
    capabilities = {item.operation_type: item for item in service.capabilities()}

    capability = capabilities["emergency_stop_runtime"]
    assert capability.status == "enabled"
    assert capability.executable_through_operation is True
    assert capability.confirmation_required is True
    assert capability.backend_executor == "brc_operation_runtime_stop"
    assert "does not flatten positions or cancel orders" in capability.current_reason


@pytest.mark.asyncio
async def test_run_fixed_testnet_rehearsal_capability_becomes_executable_when_adapter_available():
    service, _, _, _ = await _operation_service(
        fixed_rehearsal_adapter=True,
        create_campaign=False,
    )
    capabilities = {item.operation_type: item for item in service.capabilities()}

    capability = capabilities["run_fixed_testnet_rehearsal"]
    assert capability.status == "enabled"
    assert capability.executable_through_operation is True
    assert capability.backend_executor == "brc_operation_fixed_testnet_rehearsal"
    assert capability.confirmation_required is True
    assert "Operation-authorized fixed ETH/BTC testnet rehearsal" in capability.current_reason


@pytest.mark.asyncio
async def test_switch_playbook_preflight_confirm_executes_once_and_links_refs():
    service, op_repo, brc_repo, _ = await _operation_service()
    preflight = await _switch_preflight(service)

    assert preflight.decision == "allow"
    assert preflight.status == "awaiting_confirmation"
    assert preflight.confirmation_requirement.phrase == "CONFIRM_SWITCH_PLAYBOOK"

    result = await service.confirm(
        operation_id=preflight.operation_id,
        preflight_id=preflight.preflight_id,
        confirmation_phrase="CONFIRM_SWITCH_PLAYBOOK",
        idempotency_key=preflight.idempotency_key,
    )

    assert result.status == "executed"
    assert result.campaign_refs
    assert result.audit_refs[0]["type"] == "operation"
    assert brc_repo.campaign.current_playbook_id == "PB-004-BRC-CONTROLLED-TESTNET"
    assert len(brc_repo.switches) == 1
    switch_event = next(item for item in brc_repo.events if item["event_type"] == "playbook_switched")
    assert switch_event["metadata"]["operation_id"] == preflight.operation_id
    assert switch_event["metadata"]["preflight_id"] == preflight.preflight_id
    assert f"operation:{preflight.operation_id}" in switch_event["metadata"]["evidence_refs"]

    again = await service.confirm(
        operation_id=preflight.operation_id,
        preflight_id=preflight.preflight_id,
        confirmation_phrase="CONFIRM_SWITCH_PLAYBOOK",
        idempotency_key=preflight.idempotency_key,
    )

    assert again.status == "executed"
    assert len(brc_repo.switches) == 1
    assert (await op_repo.get_operation(preflight.operation_id)).status == "executed"


@pytest.mark.asyncio
async def test_tf001_carrier_playbook_can_be_selected_without_trading_authority():
    service, op_repo, brc_repo, _ = await _operation_service()
    preflight = await service.preflight(
        operation_type="switch_playbook",
        requested_by="owner",
        input_params={
            "target_playbook_id": "TF-001",
            "reason_text": "TF-001 carrier validation selection",
            "evidence_refs": ["docs/ops/brc-r5-001-tf001-carrier-full-chain-validation-plan.md"],
        },
        source={"kind": "unit"},
    )

    assert preflight.decision == "allow"
    assert preflight.playbook_summary["known"] is True
    assert preflight.playbook_summary["target_playbook_id"] == "TF-001"

    result = await service.confirm(
        operation_id=preflight.operation_id,
        preflight_id=preflight.preflight_id,
        confirmation_phrase="CONFIRM_SWITCH_PLAYBOOK",
        idempotency_key=preflight.idempotency_key,
    )

    assert result.status == "executed"
    assert brc_repo.campaign.current_playbook_id == "TF-001"
    assert len(brc_repo.switches) == 1
    assert (await op_repo.get_operation(preflight.operation_id)).status == "executed"
    assert "No orders were placed" in result.result_summary["message"]
    switch_event = next(item for item in brc_repo.events if item["event_type"] == "playbook_switched")
    assert switch_event["metadata"]["preflight_id"] == preflight.preflight_id
    assert f"operation:{preflight.operation_id}" in switch_event["metadata"]["evidence_refs"]


@pytest.mark.asyncio
async def test_unknown_operation_rejected_before_persistence():
    service, op_repo, _, _ = await _operation_service()

    with pytest.raises(OperationLayerError, match="unknown operation_type"):
        await service.preflight(
            operation_type="totally_unknown",
            requested_by="owner",
            input_params={},
        )

    assert await op_repo.list_operations() == []


@pytest.mark.asyncio
async def test_unknown_playbook_persists_blocked_operation_result():
    service, op_repo, brc_repo, _ = await _operation_service()

    preflight = await service.preflight(
        operation_type="switch_playbook",
        requested_by="owner",
        input_params={
            "target_playbook_id": "PB-999-NOT-REAL",
            "evidence_refs": ["evidence"],
        },
    )

    assert preflight.decision == "block"
    assert preflight.status == "blocked"
    result = await op_repo.get_execution_result(preflight.operation_id)
    assert result is not None
    assert result.status == "blocked"
    assert "unknown playbook" in (result.blocked_reason or "")
    assert brc_repo.switches == []


@pytest.mark.asyncio
async def test_wrong_confirmation_phrase_blocks_without_execute():
    service, _, brc_repo, _ = await _operation_service()
    preflight = await _switch_preflight(service)

    result = await service.confirm(
        operation_id=preflight.operation_id,
        preflight_id=preflight.preflight_id,
        confirmation_phrase="WRONG",
        idempotency_key=preflight.idempotency_key,
    )

    assert result.status == "blocked"
    assert "confirmation phrase mismatch" in str(result.result_summary)
    assert brc_repo.switches == []


@pytest.mark.asyncio
async def test_expired_preflight_persists_expired_result():
    service, _, brc_repo, _ = await _operation_service(ttl_ms=-1)
    preflight = await _switch_preflight(service)

    result = await service.confirm(
        operation_id=preflight.operation_id,
        preflight_id=preflight.preflight_id,
        confirmation_phrase="CONFIRM_SWITCH_PLAYBOOK",
        idempotency_key=preflight.idempotency_key,
    )

    assert result.status == "expired"
    assert brc_repo.switches == []


@pytest.mark.asyncio
async def test_audit_writable_false_blocks_on_confirm_recheck():
    service, _, brc_repo, _ = await _operation_service(audit_writable=False)
    preflight = await _switch_preflight(service)

    result = await service.confirm(
        operation_id=preflight.operation_id,
        preflight_id=preflight.preflight_id,
        confirmation_phrase="CONFIRM_SWITCH_PLAYBOOK",
        idempotency_key=preflight.idempotency_key,
    )

    assert result.status == "blocked"
    assert "audit is not writable" in str(result.result_summary)
    assert brc_repo.switches == []


@pytest.mark.asyncio
async def test_market_drift_blocks_on_confirm_recheck():
    service, _, brc_repo, market = await _operation_service()
    preflight = await _switch_preflight(service)
    market["open_order_count"] = 1
    market["all_local_flat"] = False

    result = await service.confirm(
        operation_id=preflight.operation_id,
        preflight_id=preflight.preflight_id,
        confirmation_phrase="CONFIRM_SWITCH_PLAYBOOK",
        idempotency_key=preflight.idempotency_key,
    )

    assert result.status == "blocked"
    assert "account/order facts changed" in str(result.result_summary)
    assert brc_repo.switches == []


@pytest.mark.asyncio
async def test_operation_preflight_includes_account_facts_source_and_blocks_unavailable_for_medium_risk():
    service, _, _, _ = await _operation_service()
    preflight = await _switch_preflight(service)

    assert preflight.account_order_summary["source"] == "local_pg"
    assert preflight.account_order_summary["truth_level"] == "summary"
    assert preflight.account_order_summary["reconciliation_status"]["status"] == "not_available"

    blocked_service, op_repo, brc_repo, _ = await _operation_service(
        market_state={
            "source": "unavailable",
            "truth_level": "unavailable",
            "active_position_count": 0,
            "open_order_count": 0,
            "all_local_flat": False,
            "blockers": ["local PG position/order repositories are not available"],
        }
    )
    blocked = await _switch_preflight(blocked_service)

    assert blocked.status == "blocked"
    result = await op_repo.get_execution_result(blocked.operation_id)
    assert result is not None
    assert result.status == "blocked"
    assert "account facts unavailable" in (result.blocked_reason or "")
    assert brc_repo.switches == []


@pytest.mark.asyncio
async def test_medium_risk_operation_blocks_on_account_reconciliation_mismatch():
    service, op_repo, brc_repo, _ = await _operation_service(
        market_state={
            "source": "mixed",
            "truth_level": "reconciled",
            "reconciliation_status": {"status": "mismatch"},
            "active_position_count": 0,
            "open_order_count": 1,
            "all_local_flat": False,
            "unknown_or_unmanaged_order_count": 1,
            "unknown_or_unmanaged_position_count": 0,
        }
    )
    preflight = await _switch_preflight(service)

    assert preflight.status == "blocked"
    assert preflight.account_order_summary["reconciliation_status"]["status"] == "mismatch"
    result = await op_repo.get_execution_result(preflight.operation_id)
    assert result is not None
    assert result.status == "blocked"
    assert "account reconciliation mismatch" in (result.blocked_reason or "")
    assert brc_repo.switches == []


@pytest.mark.asyncio
async def test_cancel_get_and_list_operation():
    service, _, _, _ = await _operation_service()
    preflight = await _switch_preflight(service)

    cancelled = await service.cancel(operation_id=preflight.operation_id)
    detail = await service.get(preflight.operation_id)
    listed = await service.list(limit=10)

    assert cancelled.status == "cancelled"
    assert detail.operation.status == "cancelled"
    assert detail.result is not None
    assert listed.operations[0].operation_id == preflight.operation_id


@pytest.mark.asyncio
async def test_forbidden_operation_preflight_is_not_executable():
    service, op_repo, _, _ = await _operation_service()
    preflight = await service.preflight(
        operation_type="withdrawal",
        requested_by="owner",
        input_params={"asset": "USDT", "amount": "1"},
    )

    assert preflight.decision == "block"
    assert preflight.confirmation_requirement.required is False
    result = await op_repo.get_execution_result(preflight.operation_id)
    assert result is not None
    assert result.status == "blocked"


@pytest.mark.asyncio
async def test_write_review_decision_preflight_confirm_executes_once_and_links_refs():
    service, op_repo, brc_repo, _ = await _operation_service()
    preflight = await service.preflight(
        operation_type="write_review_decision",
        requested_by="owner",
        input_params={
            "decision": "accepted",
            "reason_text": "owner reviewed operation layer evidence",
            "next_recommended_task": "continue bounded review",
        },
    )

    assert preflight.status == "awaiting_confirmation"
    assert preflight.confirmation_requirement.phrase == "CONFIRM_WRITE_REVIEW"

    result = await service.confirm(
        operation_id=preflight.operation_id,
        preflight_id=preflight.preflight_id,
        confirmation_phrase="CONFIRM_WRITE_REVIEW",
        idempotency_key=preflight.idempotency_key,
    )

    assert result.status == "executed"
    assert result.review_refs[0]["type"] == "review_decision"
    assert result.audit_refs
    assert len(brc_repo.review_decisions) == 1
    assert brc_repo.review_decisions[0].metadata_json["operation_id"] == preflight.operation_id

    again = await service.confirm(
        operation_id=preflight.operation_id,
        preflight_id=preflight.preflight_id,
        confirmation_phrase="CONFIRM_WRITE_REVIEW",
        idempotency_key=preflight.idempotency_key,
    )
    assert again.status == "executed"
    assert len(brc_repo.review_decisions) == 1
    assert (await op_repo.get_operation(preflight.operation_id)).status == "executed"


@pytest.mark.asyncio
async def test_write_review_decision_wrong_phrase_expired_and_audit_recheck_block():
    service, _, brc_repo, _ = await _operation_service()
    preflight = await service.preflight(
        operation_type="write_review_decision",
        requested_by="owner",
        input_params={
            "decision": "accepted",
            "reason_text": "review",
            "next_recommended_task": "next",
        },
    )
    wrong = await service.confirm(
        operation_id=preflight.operation_id,
        preflight_id=preflight.preflight_id,
        confirmation_phrase="WRONG",
        idempotency_key=preflight.idempotency_key,
    )
    assert wrong.status == "blocked"
    assert brc_repo.review_decisions == []

    expired_service, _, expired_repo, _ = await _operation_service(ttl_ms=-1)
    expired_preflight = await expired_service.preflight(
        operation_type="write_review_decision",
        requested_by="owner",
        input_params={
            "decision": "accepted",
            "reason_text": "review",
            "next_recommended_task": "next",
        },
    )
    expired = await expired_service.confirm(
        operation_id=expired_preflight.operation_id,
        preflight_id=expired_preflight.preflight_id,
        confirmation_phrase="CONFIRM_WRITE_REVIEW",
        idempotency_key=expired_preflight.idempotency_key,
    )
    assert expired.status == "expired"
    assert expired_repo.review_decisions == []

    blocked_service, _, blocked_repo, _ = await _operation_service(audit_writable=False)
    blocked_preflight = await blocked_service.preflight(
        operation_type="write_review_decision",
        requested_by="owner",
        input_params={
            "decision": "accepted",
            "reason_text": "review",
            "next_recommended_task": "next",
        },
    )
    blocked = await blocked_service.confirm(
        operation_id=blocked_preflight.operation_id,
        preflight_id=blocked_preflight.preflight_id,
        confirmation_phrase="CONFIRM_WRITE_REVIEW",
        idempotency_key=blocked_preflight.idempotency_key,
    )
    assert blocked.status == "blocked"
    assert blocked_repo.review_decisions == []


@pytest.mark.asyncio
async def test_start_review_reads_packet_without_mutation():
    service, _, _, _ = await _operation_service()
    preflight = await service.preflight(
        operation_type="start_review",
        requested_by="owner",
        input_params={},
    )
    result = await service.confirm(
        operation_id=preflight.operation_id,
        preflight_id=preflight.preflight_id,
        confirmation_phrase="CONFIRM_START_REVIEW",
        idempotency_key=preflight.idempotency_key,
    )

    assert result.status == "executed"
    assert result.review_refs[0]["type"] == "review_packet"
    assert result.result_summary["mutation_executed"] is False


@pytest.mark.asyncio
async def test_run_fixed_testnet_rehearsal_is_explicitly_unavailable_without_authorized_operation_adapter():
    service, op_repo, _, _ = await _operation_service()
    preflight = await service.preflight(
        operation_type="run_fixed_testnet_rehearsal",
        requested_by="owner",
        input_params={"source": "fixed_rehearsal_page"},
    )

    assert preflight.status == "blocked"
    assert preflight.decision == "unavailable"
    assert preflight.confirmation_requirement.required is False
    result = await op_repo.get_execution_result(preflight.operation_id)
    assert result is not None
    assert result.status == "blocked"
    assert "fixed rehearsal executor is not wired" in (result.blocked_reason or "").lower()


@pytest.mark.asyncio
async def test_run_fixed_testnet_rehearsal_preflight_confirm_executes_once_and_links_refs():
    service, op_repo, _, market = await _operation_service(
        fixed_rehearsal_adapter=True,
        create_campaign=False,
    )
    preflight = await service.preflight(
        operation_type="run_fixed_testnet_rehearsal",
        requested_by="owner",
        input_params={"source": "fixed_rehearsal_page"},
    )

    assert preflight.status == "awaiting_confirmation"
    assert preflight.decision == "allow"
    assert preflight.confirmation_requirement.phrase == "CONFIRM_FIXED_TESTNET_REHEARSAL"
    assert preflight.after["symbols"] == ["ETH/USDT:USDT", "BTC/USDT:USDT"]
    assert preflight.after["workflow_carrier"] == "internal_ref_only"

    result = await service.confirm(
        operation_id=preflight.operation_id,
        preflight_id=preflight.preflight_id,
        confirmation_phrase="CONFIRM_FIXED_TESTNET_REHEARSAL",
        idempotency_key=preflight.idempotency_key,
    )

    assert result.status == "executed"
    assert result.result_summary["workflow_run_id"] == f"op-wf-{preflight.operation_id}"
    assert result.result_summary["campaign_id"] == "brc-rehearsal"
    assert result.result_summary["live_ready"] is False
    assert result.audit_refs[0]["type"] == "workflow_run"
    assert any(item["type"] == "evidence_packet" for item in result.audit_refs)
    assert any(item["type"] == "review_decision" for item in result.review_refs)
    assert any(item["type"] == "campaign" for item in result.campaign_refs)
    assert market["fixed_rehearsal_calls"][0]["authorization_source"] == "brc_operation_layer"
    assert market["fixed_rehearsal_calls"][0]["workflow_carrier_role"] == "internal_ref_only"
    assert market["fixed_rehearsal_calls"][0]["allowed_symbols"] == ["ETH/USDT:USDT", "BTC/USDT:USDT"]

    again = await service.confirm(
        operation_id=preflight.operation_id,
        preflight_id=preflight.preflight_id,
        confirmation_phrase="CONFIRM_FIXED_TESTNET_REHEARSAL",
        idempotency_key=preflight.idempotency_key,
    )

    assert again.status == "executed"
    assert len(market["fixed_rehearsal_calls"]) == 1
    assert (await op_repo.get_operation(preflight.operation_id)).status == "executed"


@pytest.mark.asyncio
async def test_run_fixed_testnet_rehearsal_wrong_phrase_expired_and_audit_recheck_block():
    service, _, _, market = await _operation_service(
        fixed_rehearsal_adapter=True,
        create_campaign=False,
    )
    preflight = await service.preflight(
        operation_type="run_fixed_testnet_rehearsal",
        requested_by="owner",
        input_params={},
    )
    wrong = await service.confirm(
        operation_id=preflight.operation_id,
        preflight_id=preflight.preflight_id,
        confirmation_phrase="WRONG",
        idempotency_key=preflight.idempotency_key,
    )
    assert wrong.status == "blocked"
    assert market["fixed_rehearsal_calls"] == []

    expired_service, _, _, expired_market = await _operation_service(
        ttl_ms=-1,
        fixed_rehearsal_adapter=True,
        create_campaign=False,
    )
    expired_preflight = await expired_service.preflight(
        operation_type="run_fixed_testnet_rehearsal",
        requested_by="owner",
        input_params={},
    )
    expired = await expired_service.confirm(
        operation_id=expired_preflight.operation_id,
        preflight_id=expired_preflight.preflight_id,
        confirmation_phrase="CONFIRM_FIXED_TESTNET_REHEARSAL",
        idempotency_key=expired_preflight.idempotency_key,
    )
    assert expired.status == "expired"
    assert expired_market["fixed_rehearsal_calls"] == []

    blocked_service, _, _, blocked_market = await _operation_service(
        audit_writable=False,
        fixed_rehearsal_adapter=True,
        create_campaign=False,
    )
    blocked_preflight = await blocked_service.preflight(
        operation_type="run_fixed_testnet_rehearsal",
        requested_by="owner",
        input_params={},
    )
    blocked = await blocked_service.confirm(
        operation_id=blocked_preflight.operation_id,
        preflight_id=blocked_preflight.preflight_id,
        confirmation_phrase="CONFIRM_FIXED_TESTNET_REHEARSAL",
        idempotency_key=blocked_preflight.idempotency_key,
    )
    assert blocked.status == "blocked"
    assert "audit is not writable" in str(blocked.result_summary)
    assert blocked_market["fixed_rehearsal_calls"] == []


@pytest.mark.asyncio
async def test_run_fixed_testnet_rehearsal_blocks_mutation_gates_guards_live_and_campaign_state():
    cases = [
        ({"runtime_control_api_enabled": False}, "runtime mutation gate is not enabled"),
        ({"runtime_test_signal_injection_enabled": False}, "controlled test signal gate is not enabled"),
        ({"gks_active": False}, "global kill switch must be active"),
        ({"startup_guard_armed": True}, "startup guard must not already be armed"),
        ({"testnet": False}, "exchange testnet is not confirmed"),
        ({"profile": "live"}, "runtime profile is not brc_btc_eth_testnet_runtime"),
        ({"live_ready": True}, "live/mainnet readiness is forbidden"),
    ]
    for runtime_state, expected in cases:
        service, op_repo, _, market = await _operation_service(
            fixed_rehearsal_adapter=True,
            create_campaign=False,
            runtime_state=runtime_state,
        )
        preflight = await service.preflight(
            operation_type="run_fixed_testnet_rehearsal",
            requested_by="owner",
            input_params={},
        )
        assert preflight.status == "blocked"
        result = await op_repo.get_execution_result(preflight.operation_id)
        assert result is not None
        assert result.status == "blocked"
        assert expected in (result.blocked_reason or "")
        assert market["fixed_rehearsal_calls"] == []

    active_campaign_service, active_campaign_repo, _, active_campaign_market = await _operation_service(
        fixed_rehearsal_adapter=True,
        create_campaign=True,
    )
    active_campaign_preflight = await active_campaign_service.preflight(
        operation_type="run_fixed_testnet_rehearsal",
        requested_by="owner",
        input_params={},
    )
    active_campaign_result = await active_campaign_repo.get_execution_result(
        active_campaign_preflight.operation_id
    )
    assert active_campaign_result is not None
    assert active_campaign_result.status == "blocked"
    assert "active BRC campaign already exists" in (active_campaign_result.blocked_reason or "")
    assert active_campaign_market["fixed_rehearsal_calls"] == []


@pytest.mark.asyncio
async def test_run_fixed_testnet_rehearsal_blocks_open_orders_and_market_drift_on_recheck():
    open_order_service, open_order_repo, _, open_order_market = await _operation_service(
        fixed_rehearsal_adapter=True,
        create_campaign=False,
        market_state={
            "active_position_count": 0,
            "open_order_count": 1,
            "all_local_flat": True,
            "data_source": "unit",
        },
    )
    open_order_preflight = await open_order_service.preflight(
        operation_type="run_fixed_testnet_rehearsal",
        requested_by="owner",
        input_params={},
    )
    open_order_result = await open_order_repo.get_execution_result(open_order_preflight.operation_id)
    assert open_order_result is not None
    assert open_order_result.status == "blocked"
    assert "local open orders exist" in (open_order_result.blocked_reason or "")
    assert open_order_market["fixed_rehearsal_calls"] == []

    service, _, _, market = await _operation_service(
        fixed_rehearsal_adapter=True,
        create_campaign=False,
    )
    preflight = await service.preflight(
        operation_type="run_fixed_testnet_rehearsal",
        requested_by="owner",
        input_params={},
    )
    market["open_order_count"] = 1
    market["all_local_flat"] = False
    result = await service.confirm(
        operation_id=preflight.operation_id,
        preflight_id=preflight.preflight_id,
        confirmation_phrase="CONFIRM_FIXED_TESTNET_REHEARSAL",
        idempotency_key=preflight.idempotency_key,
    )
    assert result.status == "blocked"
    assert "local open orders exist" in str(result.result_summary)
    assert market["fixed_rehearsal_calls"] == []


@pytest.mark.asyncio
async def test_run_fixed_testnet_rehearsal_runner_failure_and_forbidden_flags_persist_failed():
    service, op_repo, _, market = await _operation_service(
        fixed_rehearsal_adapter=True,
        fixed_rehearsal_failure=RuntimeError("runner failed"),
        create_campaign=False,
    )
    preflight = await service.preflight(
        operation_type="run_fixed_testnet_rehearsal",
        requested_by="owner",
        input_params={},
    )
    failed = await service.confirm(
        operation_id=preflight.operation_id,
        preflight_id=preflight.preflight_id,
        confirmation_phrase="CONFIRM_FIXED_TESTNET_REHEARSAL",
        idempotency_key=preflight.idempotency_key,
    )
    assert failed.status == "failed"
    stored_failed = await op_repo.get_execution_result(preflight.operation_id)
    assert stored_failed is not None
    assert stored_failed.failed_reason == "runner failed"
    assert len(market["fixed_rehearsal_calls"]) == 1

    async def _unsafe_executor(_input):
        return {"workflow_run_id": "wf-unsafe", "live_ready": True, "withdrawal_executed": False}

    unsafe_repo = InMemoryOperationRepository()
    runtime = _default_runtime_summary()
    unsafe_service = BrcOperationService(
        repository=unsafe_repo,
        brc_campaign_service=(await _campaign_service(create_campaign=False))[0],
        readers=OperationLayerReaders(
            runtime_summary=lambda: _async_dict(runtime),
            markets_orders_summary=lambda: _async_dict({
                "active_position_count": 0,
                "open_order_count": 0,
                "all_local_flat": True,
            }),
            audit_writable=lambda: _async_bool(True),
            fixed_rehearsal_executor=_unsafe_executor,
        ),
    )
    await unsafe_service.initialize()
    unsafe_preflight = await unsafe_service.preflight(
        operation_type="run_fixed_testnet_rehearsal",
        requested_by="owner",
        input_params={},
    )
    unsafe = await unsafe_service.confirm(
        operation_id=unsafe_preflight.operation_id,
        preflight_id=unsafe_preflight.preflight_id,
        confirmation_phrase="CONFIRM_FIXED_TESTNET_REHEARSAL",
        idempotency_key=unsafe_preflight.idempotency_key,
    )
    assert unsafe.status == "failed"
    assert "forbidden live/withdrawal flags" in str(unsafe.result_summary)


@pytest.mark.asyncio
async def test_runtime_state_operations_execute_or_degrade_safely():
    service, _, _, _ = await _operation_service()
    observe_preflight = await service.preflight(
        operation_type="enter_observe",
        requested_by="owner",
        input_params={"reason": "owner observe"},
    )
    observe = await service.confirm(
        operation_id=observe_preflight.operation_id,
        preflight_id=observe_preflight.preflight_id,
        confirmation_phrase="CONFIRM_ENTER_OBSERVE",
        idempotency_key=observe_preflight.idempotency_key,
    )
    assert observe.status == "noop"
    assert observe.next_state["runtime_transition"]["status"] == "observe"

    pause_preflight = await service.preflight(
        operation_type="enter_pause",
        requested_by="owner",
        input_params={"reason": "owner pause"},
    )
    pause = await service.confirm(
        operation_id=pause_preflight.operation_id,
        preflight_id=pause_preflight.preflight_id,
        confirmation_phrase="CONFIRM_ENTER_PAUSE",
        idempotency_key=pause_preflight.idempotency_key,
    )
    assert pause.status == "executed"
    assert pause.next_state["runtime_transition"]["status"] == "paused"
    assert pause.result_summary["live_ready"] is False

    monitor_preflight = await service.preflight(
        operation_type="enter_strategy_or_monitor",
        requested_by="owner",
        input_params={},
    )
    monitor = await service.confirm(
        operation_id=monitor_preflight.operation_id,
        preflight_id=monitor_preflight.preflight_id,
        confirmation_phrase="CONFIRM_ENTER_MONITOR",
        idempotency_key=monitor_preflight.idempotency_key,
    )
    assert monitor.status == "noop"
    assert monitor.next_state["carrier"] == "monitor"
    assert "unrestricted auto trading" in monitor.result_summary["message"]


@pytest.mark.asyncio
async def test_runtime_transition_unavailable_when_adapter_missing():
    service, op_repo, _, _ = await _operation_service(runtime_adapter=False)
    preflight = await service.preflight(
        operation_type="enter_pause",
        requested_by="owner",
        input_params={},
    )

    assert preflight.status == "blocked"
    result = await op_repo.get_execution_result(preflight.operation_id)
    assert result is not None
    assert result.status == "blocked"
    assert "runtime transition adapter unavailable" in (result.blocked_reason or "")


@pytest.mark.asyncio
async def test_emergency_flatten_dry_run_no_exposure_persists_noop_without_trading():
    service, op_repo, _, _ = await _operation_service()

    preflight = await service.preflight(
        operation_type="emergency_flatten",
        requested_by="owner",
        input_params={"reason": "owner dry-run"},
    )

    assert preflight.decision == "warn"
    assert preflight.status == "awaiting_confirmation"
    assert preflight.confirmation_requirement.phrase == "CONFIRM_FLATTEN_DRY_RUN"
    assert preflight.after["dry_run_only"] is True
    assert preflight.after["actual_execution_available"] is False
    assert preflight.after["actual_execution"] is False
    assert preflight.after["dry_run_plan"]["estimated_actions_count"] == 0
    assert preflight.after["dry_run_plan"]["plan_status"] == "noop"
    assert preflight.after["estimated_flatten_impact"]["planned_result_status"] == "noop"
    assert any("no positions and no open orders" in item for item in preflight.risk_summary["warnings"])
    assert preflight.risk_summary["blockers"] == []

    confirm = await service.confirm(
        operation_id=preflight.operation_id,
        preflight_id=preflight.preflight_id,
        confirmation_phrase="CONFIRM_FLATTEN_DRY_RUN",
        idempotency_key=preflight.idempotency_key,
    )
    stored = await op_repo.get_execution_result(preflight.operation_id)
    assert confirm.status == "noop"
    assert stored is not None
    assert stored.status == "noop"
    assert stored.result_summary["dry_run_only"] is True
    assert stored.result_summary["actual_execution"] is False
    assert stored.result_summary["orders_cancelled"] is False
    assert stored.result_summary["positions_closed"] is False
    assert stored.audit_refs[0]["type"] == "flatten_dry_run"


@pytest.mark.asyncio
async def test_emergency_flatten_dry_run_with_clean_exposure_returns_candidates_and_confirms_once():
    service, op_repo, _, _ = await _operation_service(
        market_state={
            "active_position_count": 1,
            "open_order_count": 1,
            "all_local_flat": False,
            "source": "mixed",
            "truth_level": "reconciled",
            "reconciliation_status": {"status": "clean"},
            "positions": [{"position_id": "pos-1", "symbol": "ETH/USDT:USDT", "side": "long", "size": "0.01"}],
            "open_orders": [{"order_id": "ord-1", "symbol": "ETH/USDT:USDT", "side": "sell", "order_type": "STOP_MARKET"}],
        }
    )
    preflight = await service.preflight(
        operation_type="emergency_flatten",
        requested_by="owner",
        input_params={},
    )

    assert preflight.decision == "allow"
    assert preflight.status == "awaiting_confirmation"
    plan = preflight.after["dry_run_plan"]
    assert plan["dry_run_only"] is True
    assert plan["actual_execution"] is False
    assert plan["estimated_actions_count"] == 2
    assert plan["cancel_order_candidates"][0]["candidate_only"] is True
    assert plan["cancel_order_candidates"][0]["executable_order_request"] is False
    assert plan["close_position_candidates"][0]["candidate_only"] is True
    assert plan["close_position_candidates"][0]["executable_order_request"] is False

    result = await service.confirm(
        operation_id=preflight.operation_id,
        preflight_id=preflight.preflight_id,
        confirmation_phrase="CONFIRM_FLATTEN_DRY_RUN",
        idempotency_key=preflight.idempotency_key,
    )
    assert result.status == "executed"
    assert result.result_summary["estimated_actions_count"] == 2
    assert result.result_summary["orders_cancelled"] is False
    assert result.result_summary["positions_closed"] is False
    assert (await op_repo.get_operation(preflight.operation_id)).status == "executed"

    again = await service.confirm(
        operation_id=preflight.operation_id,
        preflight_id=preflight.preflight_id,
        confirmation_phrase="CONFIRM_FLATTEN_DRY_RUN",
        idempotency_key=preflight.idempotency_key,
    )
    assert again.status == "executed"


@pytest.mark.asyncio
async def test_emergency_flatten_diagnostic_dry_run_on_mismatch_or_unmanaged_exposure():
    mismatch_service, _, _, _ = await _operation_service(
        market_state={
            "active_position_count": 0,
            "open_order_count": 0,
            "all_local_flat": True,
            "source": "mixed",
            "truth_level": "reconciled",
            "reconciliation_status": {"status": "mismatch"},
        }
    )
    mismatch = await mismatch_service.preflight(
        operation_type="emergency_flatten",
        requested_by="owner",
        input_params={},
    )
    assert mismatch.decision == "warn"
    assert mismatch.status == "awaiting_confirmation"
    assert mismatch.after["actual_execution"] is False
    assert mismatch.after["dry_run_plan"]["exposure_summary"]["reconciliation_status"] == "mismatch"
    assert any("reconciliation mismatch" in item for item in mismatch.risk_summary["warnings"])

    unmanaged_service, _, _, _ = await _operation_service(
        market_state={
            "active_position_count": 0,
            "open_order_count": 1,
            "all_local_flat": False,
            "source": "mixed",
            "truth_level": "reconciled",
            "reconciliation_status": {"status": "clean"},
            "unknown_or_unmanaged_orders": [{"id": "exchange-orphan"}],
        }
    )
    unmanaged = await unmanaged_service.preflight(
        operation_type="emergency_flatten",
        requested_by="owner",
        input_params={},
    )
    assert unmanaged.decision == "warn"
    assert unmanaged.status == "awaiting_confirmation"
    assert unmanaged.after["unknown_or_unmanaged_orders"][0]["id"] == "exchange-orphan"
    assert any("unknown or unmanaged" in item for item in unmanaged.risk_summary["warnings"])


@pytest.mark.asyncio
async def test_emergency_flatten_account_unavailable_and_live_are_blocked_without_confirm():
    unavailable_service, unavailable_repo, _, _ = await _operation_service(
        market_state={
            "source": "unavailable",
            "truth_level": "unavailable",
            "active_position_count": 0,
            "open_order_count": 0,
            "all_local_flat": False,
        }
    )
    unavailable = await unavailable_service.preflight(
        operation_type="emergency_flatten",
        requested_by="owner",
        input_params={},
    )
    assert unavailable.status == "blocked"
    unavailable_result = await unavailable_repo.get_execution_result(unavailable.operation_id)
    assert unavailable_result is not None
    assert "account facts unavailable" in (unavailable_result.blocked_reason or "")

    live_service, live_repo, _, _ = await _operation_service(
        runtime_state={"testnet": False, "live_ready": True},
    )
    live = await live_service.preflight(
        operation_type="emergency_flatten",
        requested_by="owner",
        input_params={},
    )
    assert live.status == "blocked"
    live_result = await live_repo.get_execution_result(live.operation_id)
    assert live_result is not None
    assert "live/mainnet flatten execution is forbidden" in (live_result.blocked_reason or "")


@pytest.mark.asyncio
async def test_emergency_stop_runtime_preflight_planning_unavailable_without_executor():
    service, op_repo, _, _ = await _operation_service()

    preflight = await service.preflight(
        operation_type="emergency_stop_runtime",
        requested_by="owner",
        input_params={"reason": "owner planning only"},
    )

    assert preflight.decision == "unavailable"
    assert preflight.status == "blocked"
    assert preflight.after["planning_only"] is True
    assert preflight.after["actual_execution_available"] is False
    assert preflight.after["expected_stop_behavior"]["does_not_flatten"] is True
    assert preflight.after["expected_stop_behavior"]["does_not_cancel_orders"] is True
    assert any("executor unavailable" in item for item in preflight.risk_summary["blockers"])

    confirm = await service.confirm(
        operation_id=preflight.operation_id,
        preflight_id=preflight.preflight_id,
        confirmation_phrase="",
        idempotency_key=preflight.idempotency_key,
    )
    assert confirm.status == "blocked"
    assert (await op_repo.get_execution_result(preflight.operation_id)).status == "blocked"


@pytest.mark.asyncio
async def test_emergency_stop_runtime_preflight_confirm_executes_once_and_links_runtime_refs():
    service, op_repo, _, market = await _operation_service(runtime_stop_adapter=True)

    preflight = await service.preflight(
        operation_type="emergency_stop_runtime",
        requested_by="owner",
        input_params={"reason": "owner emergency stop"},
    )

    assert preflight.decision == "allow"
    assert preflight.status == "awaiting_confirmation"
    assert preflight.confirmation_requirement.phrase == "CONFIRM_STOP_RUNTIME"
    assert preflight.after["actual_execution_available"] is True
    assert preflight.after["planning_only"] is False
    assert preflight.after["does_not_flatten"] is True
    assert preflight.after["does_not_cancel_orders"] is True
    assert preflight.after["expected_stop_behavior"]["does_not_flatten"] is True
    assert preflight.after["expected_stop_behavior"]["does_not_cancel_orders"] is True

    result = await service.confirm(
        operation_id=preflight.operation_id,
        preflight_id=preflight.preflight_id,
        confirmation_phrase="CONFIRM_STOP_RUNTIME",
        idempotency_key=preflight.idempotency_key,
    )

    assert result.status == "executed"
    assert result.result_summary["runtime_state"] == "hard_locked"
    assert result.result_summary["does_not_flatten"] is True
    assert result.result_summary["does_not_cancel_orders"] is True
    assert result.audit_refs[0]["type"] == "runtime_stop"
    assert result.next_state["runtime_state"] == "hard_locked"
    assert market["runtime_stop_calls"][0]["authorization_source"] == "brc_operation_layer"
    assert market["runtime_stop_calls"][0]["does_not_flatten"] is True
    assert market["runtime_stop_calls"][0]["does_not_cancel_orders"] is True

    again = await service.confirm(
        operation_id=preflight.operation_id,
        preflight_id=preflight.preflight_id,
        confirmation_phrase="CONFIRM_STOP_RUNTIME",
        idempotency_key=preflight.idempotency_key,
    )

    assert again.status == "executed"
    assert len(market["runtime_stop_calls"]) == 1
    assert (await op_repo.get_operation(preflight.operation_id)).status == "executed"


@pytest.mark.asyncio
async def test_emergency_stop_runtime_already_stopped_records_noop_without_calling_adapter():
    service, _, _, market = await _operation_service(
        runtime_stop_adapter=True,
        runtime_state={"current_runtime_state": "hard_locked"},
    )

    preflight = await service.preflight(
        operation_type="emergency_stop_runtime",
        requested_by="owner",
        input_params={},
    )
    assert preflight.decision == "warn"
    assert preflight.after["already_stopped"] is True
    assert preflight.after["planned_result_status"] == "noop"

    result = await service.confirm(
        operation_id=preflight.operation_id,
        preflight_id=preflight.preflight_id,
        confirmation_phrase="CONFIRM_STOP_RUNTIME",
        idempotency_key=preflight.idempotency_key,
    )

    assert result.status == "noop"
    assert result.result_summary["runtime_state"] == "hard_locked"
    assert market["runtime_stop_calls"] == []


@pytest.mark.asyncio
async def test_emergency_stop_runtime_wrong_phrase_expired_audit_and_failure_paths():
    service, _, _, market = await _operation_service(runtime_stop_adapter=True)
    preflight = await service.preflight(
        operation_type="emergency_stop_runtime",
        requested_by="owner",
        input_params={},
    )
    wrong = await service.confirm(
        operation_id=preflight.operation_id,
        preflight_id=preflight.preflight_id,
        confirmation_phrase="WRONG",
        idempotency_key=preflight.idempotency_key,
    )
    assert wrong.status == "blocked"
    assert market["runtime_stop_calls"] == []

    expired_service, _, _, expired_market = await _operation_service(
        ttl_ms=-1,
        runtime_stop_adapter=True,
    )
    expired_preflight = await expired_service.preflight(
        operation_type="emergency_stop_runtime",
        requested_by="owner",
        input_params={},
    )
    expired = await expired_service.confirm(
        operation_id=expired_preflight.operation_id,
        preflight_id=expired_preflight.preflight_id,
        confirmation_phrase="CONFIRM_STOP_RUNTIME",
        idempotency_key=expired_preflight.idempotency_key,
    )
    assert expired.status == "expired"
    assert expired_market["runtime_stop_calls"] == []

    audit_block_service, audit_block_repo, _, audit_block_market = await _operation_service(
        audit_writable=False,
        runtime_stop_adapter=True,
    )
    audit_block_preflight = await audit_block_service.preflight(
        operation_type="emergency_stop_runtime",
        requested_by="owner",
        input_params={},
    )
    assert audit_block_preflight.status == "blocked"
    audit_block_result = await audit_block_repo.get_execution_result(audit_block_preflight.operation_id)
    assert audit_block_result is not None
    assert audit_block_result.status == "blocked"
    assert "audit is not writable" in (audit_block_result.blocked_reason or "")
    assert audit_block_market["runtime_stop_calls"] == []

    failed_service, failed_repo, _, failed_market = await _operation_service(
        runtime_stop_adapter=True,
        runtime_stop_failure=RuntimeError("stop adapter failed"),
    )
    failed_preflight = await failed_service.preflight(
        operation_type="emergency_stop_runtime",
        requested_by="owner",
        input_params={},
    )
    failed = await failed_service.confirm(
        operation_id=failed_preflight.operation_id,
        preflight_id=failed_preflight.preflight_id,
        confirmation_phrase="CONFIRM_STOP_RUNTIME",
        idempotency_key=failed_preflight.idempotency_key,
    )
    assert failed.status == "failed"
    stored_failed = await failed_repo.get_execution_result(failed_preflight.operation_id)
    assert stored_failed is not None
    assert stored_failed.failed_reason == "stop adapter failed"
    assert len(failed_market["runtime_stop_calls"]) == 1


@pytest.mark.asyncio
async def test_emergency_stop_runtime_blocks_live_and_unmanaged_account_facts_without_claiming_cleanup():
    live_service, live_repo, _, live_market = await _operation_service(
        runtime_stop_adapter=True,
        runtime_state={"live_ready": True},
    )
    live_preflight = await live_service.preflight(
        operation_type="emergency_stop_runtime",
        requested_by="owner",
        input_params={},
    )
    assert live_preflight.status == "blocked"
    live_result = await live_repo.get_execution_result(live_preflight.operation_id)
    assert live_result is not None
    assert "live/mainnet runtime stop execution is forbidden" in (live_result.blocked_reason or "")
    assert live_market["runtime_stop_calls"] == []

    unmanaged_service, unmanaged_repo, _, unmanaged_market = await _operation_service(
        runtime_stop_adapter=True,
        market_state={
            "source": "mixed",
            "truth_level": "reconciled",
            "reconciliation_status": {"status": "clean"},
            "active_position_count": 0,
            "open_order_count": 1,
            "all_local_flat": False,
            "unknown_or_unmanaged_orders": [{"id": "orphan-order"}],
        },
    )
    unmanaged = await unmanaged_service.preflight(
        operation_type="emergency_stop_runtime",
        requested_by="owner",
        input_params={},
    )
    assert unmanaged.status == "blocked"
    assert unmanaged.after["does_not_flatten"] is True
    assert unmanaged.after["does_not_cancel_orders"] is True
    unmanaged_result = await unmanaged_repo.get_execution_result(unmanaged.operation_id)
    assert unmanaged_result is not None
    assert "unknown or unmanaged exchange exposure" in (unmanaged_result.blocked_reason or "")
    assert unmanaged_market["runtime_stop_calls"] == []


@pytest.mark.asyncio
async def test_no_live_withdrawal_or_arbitrary_trading_paths_are_executable():
    service, _, _, _ = await _operation_service()
    capabilities = {item.operation_type: item for item in service.capabilities()}

    for operation_type in [
        "live_execution",
        "withdrawal",
        "transfer",
        "unrestricted_order_execution",
        "arbitrary_symbol_order",
        "arbitrary_side_size_order",
        "llm_direct_execution",
    ]:
        assert capabilities[operation_type].status == "forbidden"
        assert capabilities[operation_type].executable_through_operation is False


@pytest.mark.asyncio
async def test_pg_operation_repository_initialize_fails_when_migration_missing():
    from src.infrastructure.pg_brc_operation_repository import PgBrcOperationRepository

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        repository = PgBrcOperationRepository(async_sessionmaker(engine, expire_on_commit=False))
        with pytest.raises(RuntimeError, match="migration is not applied"):
            await repository.initialize()
    finally:
        await engine.dispose()
