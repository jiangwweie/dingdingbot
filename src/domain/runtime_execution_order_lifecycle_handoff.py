"""Runtime OrderLifecycle handoff draft.

This freezes the facts a future runtime submit adapter would hand to
OrderLifecycle. It does not create Order objects, call OrderLifecycle, or build
exchange payloads.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
import hashlib
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.brc_audit_ids import BrcSemanticIds
from src.domain.execution_intent import ExecutionIntent, ExecutionIntentStatus
from src.domain.models import Direction, OrderRole, OrderStatus, OrderType
from src.domain.runtime_execution_attempt_mutation import (
    RuntimeExecutionAttemptMutation,
    RuntimeExecutionAttemptMutationStatus,
)
from src.domain.runtime_execution_controlled_submit import (
    RuntimeExecutionControlledSubmitPreflight,
    RuntimeExecutionControlledSubmitPreflightStatus,
)
from src.domain.runtime_execution_intent_adapter import RuntimeExecutionIntentSourceType
from src.domain.runtime_execution_protection_plan import (
    RuntimeExecutionProtectionPlan,
    RuntimeExecutionProtectionPlanStatus,
)


class RuntimeExecutionOrderLifecycleHandoffModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuntimeExecutionOrderLifecycleHandoffStatus(str, Enum):
    BLOCKED = "blocked"
    READY_FOR_ORDER_LIFECYCLE_ADAPTER = "ready_for_order_lifecycle_adapter"


class RuntimeExecutionOrderLifecycleHandoffDraft(RuntimeExecutionOrderLifecycleHandoffModel):
    handoff_draft_id: str = Field(min_length=1, max_length=360)
    preflight_id: str = Field(min_length=1, max_length=260)
    authorization_id: str = Field(min_length=1, max_length=220)
    execution_intent_id: str = Field(min_length=1, max_length=64)
    attempt_mutation_id: str = Field(min_length=1, max_length=320)
    protection_plan_id: str = Field(min_length=1, max_length=260)
    runtime_instance_id: str = Field(min_length=1, max_length=128)
    source_type: Optional[str] = Field(default=None, max_length=64)
    source_id: Optional[str] = Field(default=None, max_length=128)
    semantic_ids: BrcSemanticIds
    status: RuntimeExecutionOrderLifecycleHandoffStatus
    symbol: str = Field(min_length=1, max_length=128)
    side: str = Field(min_length=1, max_length=32)
    direction: Direction
    entry_order_type: OrderType
    entry_order_role: OrderRole = OrderRole.ENTRY
    requested_qty: Decimal = Field(gt=Decimal("0"))
    intended_notional: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    entry_price_reference: Optional[Decimal] = None
    stop_price_reference: Optional[Decimal] = None
    take_profit_references: list[dict[str, Any]] = Field(default_factory=list)
    entry_order_draft: dict[str, Any] = Field(default_factory=dict)
    protection_order_drafts: list[dict[str, Any]] = Field(default_factory=list)
    order_model_drafts: list[dict[str, Any]] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    preflight_status: RuntimeExecutionControlledSubmitPreflightStatus
    attempt_mutation_status: RuntimeExecutionAttemptMutationStatus
    protection_plan_status: RuntimeExecutionProtectionPlanStatus
    order_lifecycle_method: str = Field(default="register_created_order", max_length=128)
    handoff_draft_recorded: Literal[True] = True
    requires_order_lifecycle_adapter: Literal[True] = True
    order_lifecycle_adapter_implemented: Literal[False] = False
    execution_intent_status_changed: Literal[False] = False
    order_created: Literal[False] = False
    exchange_called: Literal[False] = False
    owner_bounded_execution_called: Literal[False] = False
    order_lifecycle_called: Literal[False] = False
    created_at_ms: int = Field(ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _reject_execution_fields(self) -> "RuntimeExecutionOrderLifecycleHandoffDraft":
        forbidden = {
            "client_order_id",
            "exchange_order_id",
            "exchange_payload",
            "order_id",
            "place_order",
            "submit_order",
        }
        for key in _walk_keys({"metadata": self.metadata}):
            if key.lower() in forbidden:
                raise ValueError(f"order lifecycle handoff draft contains forbidden execution field: {key}")
        if (
            self.status
            == RuntimeExecutionOrderLifecycleHandoffStatus.READY_FOR_ORDER_LIFECYCLE_ADAPTER
            and self.blockers
        ):
            raise ValueError("ready order lifecycle handoff draft cannot have blockers")
        return self


def build_runtime_execution_order_lifecycle_handoff_draft(
    *,
    preflight: RuntimeExecutionControlledSubmitPreflight,
    intent: ExecutionIntent,
    attempt_mutation: RuntimeExecutionAttemptMutation,
    protection_plan: RuntimeExecutionProtectionPlan,
    now_ms: int,
) -> RuntimeExecutionOrderLifecycleHandoffDraft:
    blockers = list(preflight.blockers)
    warnings = list(preflight.warnings)
    blockers.extend(attempt_mutation.blockers)
    warnings.extend(attempt_mutation.warnings)
    blockers.extend(protection_plan.blockers)
    warnings.extend(protection_plan.warnings)

    if preflight.status != RuntimeExecutionControlledSubmitPreflightStatus.READY_FOR_CONTROLLED_SUBMIT_ADAPTER:
        blockers.append("controlled_submit_preflight_not_ready")
    if intent.status != ExecutionIntentStatus.RECORDED:
        blockers.append("execution_intent_not_recorded")
    if intent.source_type != RuntimeExecutionIntentSourceType.BRC_RUNTIME_ORDER_CANDIDATE.value:
        blockers.append("execution_intent_source_not_runtime_order_candidate")
    if preflight.execution_intent_id != intent.id:
        blockers.append("preflight_intent_mismatch")
    if attempt_mutation.execution_intent_id != intent.id:
        blockers.append("attempt_mutation_intent_mismatch")
    if protection_plan.execution_intent_id != intent.id:
        blockers.append("protection_plan_intent_mismatch")
    if attempt_mutation.runtime_instance_id != intent.runtime_instance_id:
        blockers.append("attempt_mutation_runtime_mismatch")
    if intent.runtime_instance_id and protection_plan.semantic_ids.runtime_instance_id:
        if protection_plan.semantic_ids.runtime_instance_id != intent.runtime_instance_id:
            blockers.append("protection_plan_runtime_mismatch")
    if attempt_mutation.status != RuntimeExecutionAttemptMutationStatus.APPLIED:
        blockers.append("attempt_mutation_not_applied")
    if protection_plan.status != RuntimeExecutionProtectionPlanStatus.READY_FOR_SUBMIT_ADAPTER:
        blockers.append("runtime_protection_plan_not_ready")
    if not attempt_mutation.attempt_consumed or not attempt_mutation.runtime_budget_mutated:
        blockers.append("runtime_attempt_budget_not_mutated")

    payload = intent.source_payload or {}
    side = _required_str(payload.get("side") or protection_plan.side or attempt_mutation.side)
    direction = _direction_for_side(side)
    requested_qty = protection_plan.proposed_quantity or attempt_mutation.proposed_quantity
    if requested_qty is None or requested_qty <= Decimal("0"):
        blockers.append("requested_quantity_missing")
        requested_qty = Decimal("0.00000001")
    entry_order_type = _order_type_for_candidate(payload.get("candidate_order_type"))
    if entry_order_type is None:
        blockers.append("candidate_order_type_unsupported")
        entry_order_type = OrderType.MARKET
    if protection_plan.stop_price_reference is None and protection_plan.requires_protection:
        blockers.append("stop_price_reference_missing")

    entry_order_draft = {
        "symbol": intent.symbol or preflight.final_gate_preview.symbol,
        "direction": direction.value,
        "order_type": entry_order_type.value,
        "order_role": OrderRole.ENTRY.value,
        "requested_qty": str(requested_qty),
        "price": str(protection_plan.entry_price_reference)
        if entry_order_type == OrderType.LIMIT and protection_plan.entry_price_reference is not None
        else None,
        "runtime_instance_id": intent.runtime_instance_id,
        "trial_binding_id": intent.trial_binding_id,
        "strategy_family_id": intent.strategy_family_id,
        "strategy_family_version_id": intent.strategy_family_version_id,
        "signal_evaluation_id": intent.signal_evaluation_id,
        "order_candidate_id": intent.order_candidate_id,
    }
    protection_order_drafts = _protection_order_drafts(
        symbol=intent.symbol or preflight.final_gate_preview.symbol,
        direction=direction,
        requested_qty=requested_qty,
        protection_plan=protection_plan,
    )
    order_model_drafts = _order_model_drafts(
        authorization_id=preflight.authorization_id,
        semantic_ids=intent.semantic_ids,
        symbol=intent.symbol or preflight.final_gate_preview.symbol,
        direction=direction,
        entry_order_type=entry_order_type,
        requested_qty=requested_qty,
        entry_price_reference=protection_plan.entry_price_reference,
        protection_order_drafts=protection_order_drafts,
        now_ms=now_ms,
    )

    status = (
        RuntimeExecutionOrderLifecycleHandoffStatus.BLOCKED
        if blockers
        else RuntimeExecutionOrderLifecycleHandoffStatus.READY_FOR_ORDER_LIFECYCLE_ADAPTER
    )
    return RuntimeExecutionOrderLifecycleHandoffDraft(
        handoff_draft_id=f"runtime-order-lifecycle-handoff-{preflight.authorization_id}",
        preflight_id=preflight.preflight_id,
        authorization_id=preflight.authorization_id,
        execution_intent_id=intent.id,
        attempt_mutation_id=attempt_mutation.mutation_id,
        protection_plan_id=protection_plan.protection_plan_id,
        runtime_instance_id=intent.runtime_instance_id or attempt_mutation.runtime_instance_id,
        source_type=intent.source_type,
        source_id=intent.source_id,
        semantic_ids=intent.semantic_ids,
        status=status,
        symbol=intent.symbol or preflight.final_gate_preview.symbol,
        side=side,
        direction=direction,
        entry_order_type=entry_order_type,
        requested_qty=requested_qty,
        intended_notional=protection_plan.intended_notional,
        entry_price_reference=protection_plan.entry_price_reference,
        stop_price_reference=protection_plan.stop_price_reference,
        take_profit_references=list(protection_plan.take_profit_references),
        entry_order_draft=entry_order_draft,
        protection_order_drafts=protection_order_drafts,
        order_model_drafts=order_model_drafts,
        blockers=_dedupe(blockers),
        warnings=_dedupe(warnings),
        preflight_status=preflight.status,
        attempt_mutation_status=attempt_mutation.status,
        protection_plan_status=protection_plan.status,
        created_at_ms=now_ms,
        metadata={
            "scope": "runtime_execution_order_lifecycle_handoff_draft",
            "target_order_lifecycle_method": "register_created_order",
            "order_lifecycle_adapter_implemented": False,
            "does_not_create_order": True,
            "does_not_change_execution_intent_status": True,
            "does_not_call_owner_bounded_execution": True,
            "does_not_call_order_lifecycle": True,
            "does_not_call_exchange": True,
        },
    )


def _direction_for_side(side: str) -> Direction:
    if side.lower() == "long":
        return Direction.LONG
    if side.lower() == "short":
        return Direction.SHORT
    raise ValueError(f"unsupported handoff side: {side}")


def _order_type_for_candidate(value: Any) -> Optional[OrderType]:
    text = str(value or "").strip().lower()
    if text == "market":
        return OrderType.MARKET
    if text == "limit":
        return OrderType.LIMIT
    return None


def _required_str(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("required handoff string is missing")
    return text


def _protection_order_drafts(
    *,
    symbol: str,
    direction: Direction,
    requested_qty: Decimal,
    protection_plan: RuntimeExecutionProtectionPlan,
) -> list[dict[str, Any]]:
    drafts: list[dict[str, Any]] = []
    if protection_plan.stop_price_reference is not None:
        drafts.append(
            {
                "symbol": symbol,
                "direction": direction.value,
                "order_type": OrderType.STOP_MARKET.value,
                "order_role": OrderRole.SL.value,
                "requested_qty": str(requested_qty),
                "trigger_price": str(protection_plan.stop_price_reference),
                "reduce_only": True,
                "source": "runtime_protection_plan",
            }
        )
    for index, take_profit in enumerate(protection_plan.take_profit_references, start=1):
        price = take_profit.get("price")
        if price is None:
            continue
        role = f"TP{min(index, 5)}"
        ratio = Decimal(str(take_profit.get("position_ratio") or "1"))
        drafts.append(
            {
                "symbol": symbol,
                "direction": direction.value,
                "order_type": OrderType.LIMIT.value,
                "order_role": role,
                "requested_qty": str(requested_qty * ratio),
                "price": str(price),
                "reduce_only": True,
                "source": "runtime_protection_plan",
            }
        )
    return drafts


def _order_model_drafts(
    *,
    authorization_id: str,
    semantic_ids: BrcSemanticIds,
    symbol: str,
    direction: Direction,
    entry_order_type: OrderType,
    requested_qty: Decimal,
    entry_price_reference: Optional[Decimal],
    protection_order_drafts: list[dict[str, Any]],
    now_ms: int,
) -> list[dict[str, Any]]:
    """Build Order-shaped draft facts without constructing or saving Orders."""
    signal_id = (
        semantic_ids.signal_evaluation_id
        or semantic_ids.order_candidate_id
        or f"runtime-signal-{authorization_id}"
    )
    draft_prefix = _order_draft_id_prefix(authorization_id)
    entry_draft_id = f"{draft_prefix}-entry"
    drafts = [
        {
            "local_order_draft_id": entry_draft_id,
            "signal_id": signal_id,
            "symbol": symbol,
            "direction": direction.value,
            "order_type": entry_order_type.value,
            "order_role": OrderRole.ENTRY.value,
            "price": str(entry_price_reference)
            if entry_order_type == OrderType.LIMIT and entry_price_reference is not None
            else None,
            "trigger_price": None,
            "requested_qty": str(requested_qty),
            "status": OrderStatus.CREATED.value,
            "created_at": now_ms,
            "updated_at": now_ms,
            "reduce_only": False,
            "parent_local_order_draft_id": None,
            "runtime_instance_id": semantic_ids.runtime_instance_id,
            "trial_binding_id": semantic_ids.trial_binding_id,
            "strategy_family_id": semantic_ids.strategy_family_id,
            "strategy_family_version_id": semantic_ids.strategy_family_version_id,
            "signal_evaluation_id": semantic_ids.signal_evaluation_id,
            "order_candidate_id": semantic_ids.order_candidate_id,
            "persisted": False,
            "order_lifecycle_called": False,
            "exchange_called": False,
        }
    ]
    for index, protection_draft in enumerate(protection_order_drafts, start=1):
        role = str(protection_draft.get("order_role") or f"EXIT{index}").lower()
        draft_id = f"{draft_prefix}-{role}"
        drafts.append(
            {
                "local_order_draft_id": draft_id,
                "signal_id": signal_id,
                "symbol": symbol,
                "direction": direction.value,
                "order_type": protection_draft.get("order_type"),
                "order_role": protection_draft.get("order_role"),
                "price": protection_draft.get("price"),
                "trigger_price": protection_draft.get("trigger_price"),
                "requested_qty": protection_draft.get("requested_qty"),
                "status": OrderStatus.CREATED.value,
                "created_at": now_ms,
                "updated_at": now_ms,
                "reduce_only": True,
                "parent_local_order_draft_id": entry_draft_id,
                "runtime_instance_id": semantic_ids.runtime_instance_id,
                "trial_binding_id": semantic_ids.trial_binding_id,
                "strategy_family_id": semantic_ids.strategy_family_id,
                "strategy_family_version_id": semantic_ids.strategy_family_version_id,
                "signal_evaluation_id": semantic_ids.signal_evaluation_id,
                "order_candidate_id": semantic_ids.order_candidate_id,
                "persisted": False,
                "order_lifecycle_called": False,
                "exchange_called": False,
            }
        )
    return drafts


def _order_draft_id_prefix(authorization_id: str) -> str:
    digest = hashlib.sha256(authorization_id.encode("utf-8")).hexdigest()[:18]
    return f"rtod-{digest}"


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _walk_keys(value: Any) -> list[str]:
    keys: list[str] = []
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="python")
    if isinstance(value, dict):
        for key, nested in value.items():
            keys.append(str(key))
            keys.extend(_walk_keys(nested))
    elif isinstance(value, list):
        for item in value:
            keys.extend(_walk_keys(item))
    return keys
