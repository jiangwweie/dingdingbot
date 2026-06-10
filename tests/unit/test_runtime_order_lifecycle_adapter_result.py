from __future__ import annotations

from decimal import Decimal

import pytest

from src.application.runtime_execution_intent_adapter_service import (
    RuntimeExecutionIntentAdapterService,
)
from src.domain.brc_audit_ids import BrcSemanticIds
from src.domain.models import Direction, OrderRole, OrderStatus, OrderType
from src.domain.runtime_execution_order_lifecycle_adapter_result import (
    RuntimeExecutionOrderLifecycleAdapterResultStatus,
    build_runtime_execution_orders_for_registration,
)
from src.domain.runtime_execution_order_registration_draft import (
    RuntimeExecutionLocalOrderRegistrationDraft,
    RuntimeExecutionOrderRegistrationDraftPreview,
    RuntimeExecutionOrderRegistrationDraftPreviewStatus,
)


NOW_MS = 1781090000000


class _DraftRepo:
    async def get(self, draft_id: str):
        raise AssertionError("draft repository should not be used in this test")


class _Lifecycle:
    def __init__(self) -> None:
        self.calls = []

    async def register_created_order(self, order, *, metadata=None):
        self.calls.append({"order": order, "metadata": metadata or {}})
        return order


def _registration_preview() -> RuntimeExecutionOrderRegistrationDraftPreview:
    semantic_ids = BrcSemanticIds(
        runtime_instance_id="runtime-1",
        trial_binding_id="binding-1",
        strategy_family_id="CPM-001",
        strategy_family_version_id="CPM-001-v0",
        signal_evaluation_id="signal-eval-1",
        order_candidate_id="candidate-1",
    )
    entry_id = "runtime-order-draft-auth-1-entry"
    return RuntimeExecutionOrderRegistrationDraftPreview(
        registration_preview_id="registration-preview-1",
        adapter_preview_id="adapter-preview-1",
        handoff_draft_id="handoff-1",
        preflight_id="preflight-1",
        authorization_id="auth-1",
        execution_intent_id="intent-1",
        runtime_instance_id="runtime-1",
        source_type="brc_runtime_order_candidate",
        source_id="candidate-1",
        semantic_ids=semantic_ids,
        status=(
            RuntimeExecutionOrderRegistrationDraftPreviewStatus
            .INPUTS_READY_REGISTRATION_DRAFT_ONLY
        ),
        symbol="BNB/USDT:USDT",
        side="long",
        local_order_registration_drafts=[
            RuntimeExecutionLocalOrderRegistrationDraft(
                local_order_draft_id=entry_id,
                signal_id="signal-eval-1",
                symbol="BNB/USDT:USDT",
                direction=Direction.LONG,
                order_type=OrderType.MARKET,
                order_role=OrderRole.ENTRY,
                requested_qty=Decimal("0.016"),
                status=OrderStatus.CREATED,
                created_at=NOW_MS,
                updated_at=NOW_MS,
                reduce_only=False,
                runtime_instance_id="runtime-1",
                trial_binding_id="binding-1",
                strategy_family_id="CPM-001",
                strategy_family_version_id="CPM-001-v0",
                signal_evaluation_id="signal-eval-1",
                order_candidate_id="candidate-1",
            ),
            RuntimeExecutionLocalOrderRegistrationDraft(
                local_order_draft_id="runtime-order-draft-auth-1-sl",
                signal_id="signal-eval-1",
                symbol="BNB/USDT:USDT",
                direction=Direction.LONG,
                order_type=OrderType.STOP_MARKET,
                order_role=OrderRole.SL,
                trigger_price=Decimal("587.50"),
                requested_qty=Decimal("0.016"),
                status=OrderStatus.CREATED,
                created_at=NOW_MS,
                updated_at=NOW_MS,
                reduce_only=True,
                parent_local_order_draft_id=entry_id,
                runtime_instance_id="runtime-1",
                trial_binding_id="binding-1",
                strategy_family_id="CPM-001",
                strategy_family_version_id="CPM-001-v0",
                signal_evaluation_id="signal-eval-1",
                order_candidate_id="candidate-1",
            ),
        ],
        registration_draft_count=2,
        entry_registration_draft_count=1,
        protection_registration_draft_count=1,
        created_at_ms=NOW_MS,
    )


def _service_with_preview(preview, lifecycle=None) -> RuntimeExecutionIntentAdapterService:
    service = RuntimeExecutionIntentAdapterService(
        draft_repository=_DraftRepo(),
        order_lifecycle_service=lifecycle,
    )

    async def _preview_for_authorization(authorization_id: str):
        assert authorization_id == preview.authorization_id
        return preview

    service.order_registration_draft_preview_for_authorization = (  # type: ignore[method-assign]
        _preview_for_authorization
    )
    return service


def test_registration_preview_maps_to_order_objects_with_runtime_semantics():
    preview = _registration_preview()

    orders = build_runtime_execution_orders_for_registration(
        registration_preview=preview
    )

    assert [order.id for order in orders] == [
        "runtime-order-draft-auth-1-entry",
        "runtime-order-draft-auth-1-sl",
    ]
    assert orders[0].status == OrderStatus.CREATED
    assert orders[0].exchange_order_id is None
    assert orders[0].runtime_instance_id == "runtime-1"
    assert orders[0].strategy_family_version_id == "CPM-001-v0"
    assert orders[0].order_candidate_id == "candidate-1"
    assert orders[1].order_role == OrderRole.SL
    assert orders[1].reduce_only is True
    assert orders[1].parent_order_id == "runtime-order-draft-auth-1-entry"


@pytest.mark.asyncio
async def test_adapter_result_default_disabled_does_not_call_lifecycle():
    preview = _registration_preview()
    lifecycle = _Lifecycle()
    service = _service_with_preview(preview, lifecycle=lifecycle)

    result = await service.order_lifecycle_adapter_result_for_authorization(
        "auth-1"
    )

    assert (
        result.status
        == RuntimeExecutionOrderLifecycleAdapterResultStatus
        .ORDER_LIFECYCLE_ADAPTER_DISABLED
    )
    assert result.blockers == ["order_lifecycle_adapter_disabled"]
    assert result.order_objects_constructed is False
    assert result.local_order_registration_executed is False
    assert result.order_lifecycle_called is False
    assert result.exchange_called is False
    assert lifecycle.calls == []


@pytest.mark.asyncio
async def test_adapter_result_requires_duplicate_submit_lock_before_registration():
    preview = _registration_preview()
    lifecycle = _Lifecycle()
    service = _service_with_preview(preview, lifecycle=lifecycle)

    result = await service.order_lifecycle_adapter_result_for_authorization(
        "auth-1",
        order_lifecycle_adapter_enabled=True,
        local_order_registration_enabled=True,
        duplicate_submit_lock_acquired=False,
    )

    assert (
        result.status
        == RuntimeExecutionOrderLifecycleAdapterResultStatus
        .DUPLICATE_SUBMIT_LOCK_REQUIRED
    )
    assert result.blockers == ["persistent_duplicate_submit_lock_required"]
    assert lifecycle.calls == []
    assert result.exchange_called is False


@pytest.mark.asyncio
async def test_adapter_result_registers_created_local_orders_when_explicitly_enabled():
    preview = _registration_preview()
    lifecycle = _Lifecycle()
    service = _service_with_preview(preview, lifecycle=lifecycle)

    result = await service.order_lifecycle_adapter_result_for_authorization(
        "auth-1",
        order_lifecycle_adapter_enabled=True,
        local_order_registration_enabled=True,
        duplicate_submit_lock_acquired=True,
    )

    assert (
        result.status
        == RuntimeExecutionOrderLifecycleAdapterResultStatus
        .REGISTERED_CREATED_LOCAL_ORDERS
    )
    assert result.blockers == []
    assert result.order_objects_constructed is True
    assert result.local_order_registration_executed is True
    assert result.order_lifecycle_called is True
    assert result.exchange_called is False
    assert result.execution_intent_status_changed is False
    assert result.entry_order_ids == ["runtime-order-draft-auth-1-entry"]
    assert result.protection_order_ids == ["runtime-order-draft-auth-1-sl"]
    assert [call["order"].id for call in lifecycle.calls] == result.local_order_ids
    assert all(
        call["metadata"]["exchange_called"] is False for call in lifecycle.calls
    )
