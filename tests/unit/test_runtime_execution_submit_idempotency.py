from __future__ import annotations

import pytest

from src.domain.execution_intent import ExecutionIntent, ExecutionIntentStatus
from src.domain.runtime_execution_controlled_submit import (
    RuntimeExecutionControlledSubmitPreflightStatus,
)
from src.domain.runtime_execution_intent_adapter import RuntimeExecutionIntentSourceType
from src.domain.runtime_execution_submit_idempotency import (
    RuntimeExecutionSubmitIdempotencySnapshot,
    RuntimeExecutionSubmitIdempotencyStatus,
    build_runtime_execution_submit_idempotency_snapshot,
)
from tests.unit.test_td5_runtime_execution_plan import (
    _planning_service,
    _ready_final_gate_lookup,
)


NOW_MS = 1781000000000


async def _ready_preflight_and_intent():
    draft = await _planning_service(active_positions=[]).intent_draft_for_order_candidate(
        order_candidate_id="candidate-1",
        owner_reviewed=True,
        owner_confirmed_for_intent=True,
    )
    from tests.unit.test_td5_runtime_execution_plan import (
        _DraftLookup,
        _IntentRecorder,
        _SubmitAuthorizationRecorder,
        _RuntimeLookup,
    )
    from src.application.runtime_execution_intent_adapter_service import (
        RuntimeExecutionIntentAdapterService,
    )

    service = RuntimeExecutionIntentAdapterService(
        draft_repository=_DraftLookup({draft.draft_id: draft}),
        intent_repository=_IntentRecorder(),
        submit_authorization_repository=_SubmitAuthorizationRecorder(),
        final_gate_preview_service=_ready_final_gate_lookup(),
        runtime_service=_RuntimeLookup(),
    )
    intent = await service.create_recorded_intent_from_draft(draft.draft_id)
    authorization = await service.create_submit_authorization_for_intent(
        intent.id,
        owner_confirmed_for_submit=True,
    )
    preflight = await service.controlled_submit_preflight_for_authorization(
        authorization.authorization_id
    )
    return preflight, intent


async def test_submit_idempotency_snapshot_defines_replay_key_without_execution():
    preflight, intent = await _ready_preflight_and_intent()

    snapshot = build_runtime_execution_submit_idempotency_snapshot(
        preflight=preflight,
        intent=intent,
        now_ms=NOW_MS,
    )

    assert (
        snapshot.status
        == RuntimeExecutionSubmitIdempotencyStatus.READY_FOR_NON_EXECUTING_POLICY_CONFIRMATION
    )
    assert snapshot.blockers == []
    assert snapshot.authorization_id == preflight.authorization_id
    assert snapshot.stable_submit_key == f"runtime-submit:{preflight.authorization_id}"
    assert snapshot.replay_lock_key == preflight.authorization_id
    assert snapshot.replay_existing_result_on_duplicate is True
    assert snapshot.retry_uses_same_key is True
    assert snapshot.blocks_concurrent_submit_without_lock is True
    assert snapshot.adapter_result_store_required is True
    assert snapshot.adapter_result_store_implemented is False
    assert "adapter_result_store_not_implemented_current_boundary" in (
        snapshot.warnings
    )
    assert "real_submit_adapter_boundary_not_implemented" in snapshot.warnings
    assert snapshot.not_execution_authority is True
    assert snapshot.order_created is False
    assert snapshot.exchange_called is False
    assert snapshot.order_lifecycle_called is False


async def test_submit_idempotency_snapshot_blocks_intent_mismatch():
    preflight, intent = await _ready_preflight_and_intent()
    mismatched_intent = intent.model_copy(update={"id": "intent-other"})

    snapshot = build_runtime_execution_submit_idempotency_snapshot(
        preflight=preflight,
        intent=mismatched_intent,
        now_ms=NOW_MS,
    )

    assert snapshot.status == RuntimeExecutionSubmitIdempotencyStatus.BLOCKED
    assert "preflight_intent_mismatch" in snapshot.blockers


async def test_submit_idempotency_snapshot_blocks_unready_preflight():
    preflight, intent = await _ready_preflight_and_intent()
    blocked_preflight = preflight.model_copy(
        update={
            "status": RuntimeExecutionControlledSubmitPreflightStatus.BLOCKED,
            "blockers": ["runtime_final_gate_execution_check_not_passed"],
        }
    )

    snapshot = build_runtime_execution_submit_idempotency_snapshot(
        preflight=blocked_preflight,
        intent=intent,
        now_ms=NOW_MS,
    )

    assert snapshot.status == RuntimeExecutionSubmitIdempotencyStatus.BLOCKED
    assert "controlled_submit_preflight_not_ready" in snapshot.blockers


def test_submit_idempotency_snapshot_rejects_execution_metadata():
    with pytest.raises(ValueError, match="forbidden execution field"):
        RuntimeExecutionSubmitIdempotencySnapshot(
            submit_idempotency_policy_id="runtime-submit-idempotency-auth-1",
            authorization_id="auth-1",
            execution_intent_id="intent-1",
            semantic_ids=ExecutionIntent(
                id="intent-1",
                symbol="BNB/USDT:USDT",
                status=ExecutionIntentStatus.RECORDED,
                source_type=RuntimeExecutionIntentSourceType.BRC_RUNTIME_ORDER_CANDIDATE.value,
                source_id="candidate-1",
            ).semantic_ids,
            symbol="BNB/USDT:USDT",
            status=RuntimeExecutionSubmitIdempotencyStatus.READY_FOR_NON_EXECUTING_POLICY_CONFIRMATION,
            stable_submit_key="runtime-submit:auth-1",
            replay_lock_key="auth-1",
            created_at_ms=NOW_MS,
            metadata={"exchange_payload": {"symbol": "BNB/USDT:USDT"}},
        )
