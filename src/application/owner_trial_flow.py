"""Owner trial-flow metadata persistence.

This module models Owner risk acknowledgement and bounded live-trial
authorization draft metadata. It is deliberately non-executable: it never
creates execution intents, grants order permission, starts runtime, or calls an
exchange gateway.
"""

from __future__ import annotations

import time
import uuid
from decimal import Decimal
from typing import Protocol, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.application.owner_action_carrier_catalog import (
    BNB_OWNER_ACTION_CARRIER_ID,
    get_owner_action_carrier,
    owner_action_warning_rows,
    required_owner_action_warning_ids,
)
from src.application.strategy_trial_architecture_governance import (
    StrategyTrialCarrierView,
)


SUPPORTED_OWNER_TRIAL_CARRIER_ID = BNB_OWNER_ACTION_CARRIER_ID
OWNER_TRIAL_FLOW_SOURCE = "owner_console"


class OwnerTrialFlowError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class OwnerTrialFlowInfrastructureError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class OwnerRiskAcknowledgementCreateRequest(BaseModel):
    carrier_id: str
    acknowledged_warning_codes: list[str]
    acknowledgement_scope: str = "strategy_trial_warnings"
    owner_id: str | None = None


class OwnerRiskAcknowledgement(BaseModel):
    acknowledgement_id: str
    carrier_id: str
    strategy_family_id: str
    acknowledged_warning_codes: list[str]
    owner_id: str
    acknowledged_at_ms: int
    acknowledgement_scope: str
    source: Literal["owner_console"] = OWNER_TRIAL_FLOW_SOURCE
    non_live_metadata_only: Literal[True] = True


class BoundedLiveTrialAuthorizationDraftCreateRequest(BaseModel):
    carrier_id: str
    linked_acknowledgement_id: str
    symbol: str
    side: Literal["long", "short"]
    max_notional: Decimal = Field(gt=Decimal("0"))
    quantity: Decimal = Field(gt=Decimal("0"))
    leverage: Decimal = Field(gt=Decimal("0"))
    protection_plan_type: Literal["single_tp_plus_sl"]
    owner_id: str | None = None
    expires_at_ms: int | None = None


class BoundedLiveTrialAuthorizationDraft(BaseModel):
    model_config = ConfigDict(frozen=True)

    draft_id: str
    carrier_id: str
    strategy_family_id: str
    symbol: str
    side: Literal["long", "short"]
    max_notional: Decimal = Field(gt=Decimal("0"))
    quantity: Decimal = Field(gt=Decimal("0"))
    leverage: Decimal = Field(gt=Decimal("0"))
    protection_plan_type: Literal["single_tp_plus_sl"]
    single_use: Literal[True] = True
    status: Literal["pending_owner_live_authorization"] = "pending_owner_live_authorization"
    live_ready: Literal[False] = False
    order_permission_granted: Literal[False] = False
    execution_permission_granted: Literal[False] = False
    execution_intent_created: Literal[False] = False
    order_created: Literal[False] = False
    auto_execution_enabled: Literal[False] = False
    consumed: bool = False
    expires_at_ms: int | None = None
    linked_acknowledgement_id: str
    created_at_ms: int
    updated_at_ms: int
    source: Literal["owner_console"] = OWNER_TRIAL_FLOW_SOURCE
    non_live_metadata_only: Literal[True] = True


class OwnerLiveAuthorizationActivationRequest(BaseModel):
    carrier_id: str
    symbol: str
    side: Literal["long", "short"]
    max_notional: Decimal = Field(gt=Decimal("0"))
    quantity: Decimal = Field(gt=Decimal("0"))
    leverage: Decimal = Field(gt=Decimal("0"))
    protection_plan_type: Literal["single_tp_plus_sl"]
    owner_id: str | None = None


class BoundedLiveTrialAuthorization(BaseModel):
    model_config = ConfigDict(frozen=True)

    authorization_id: str
    draft_id: str
    carrier_id: str
    strategy_family_id: str
    symbol: str
    side: Literal["long", "short"]
    max_notional: Decimal = Field(gt=Decimal("0"))
    quantity: Decimal = Field(gt=Decimal("0"))
    leverage: Decimal = Field(gt=Decimal("0"))
    protection_plan_type: Literal["single_tp_plus_sl"]
    single_use: Literal[True] = True
    status: Literal["owner_live_authorized_pending_final_preflight"] = (
        "owner_live_authorized_pending_final_preflight"
    )
    live_authorized: Literal[True] = True
    owner_live_authorized_by: str
    owner_live_authorized_at_ms: int
    live_ready: Literal[False] = False
    order_permission_granted: Literal[False] = False
    execution_permission_granted: Literal[False] = False
    execution_intent_created: Literal[False] = False
    order_created: Literal[False] = False
    auto_execution_enabled: Literal[False] = False
    consumed: bool = False
    expires_at_ms: int | None = None
    linked_acknowledgement_id: str
    source_draft_id: str
    final_preflight_required: Literal[True] = True
    hard_blockers: list[str] = Field(default_factory=list)
    next_executable: Literal[False] = False
    created_at_ms: int
    updated_at_ms: int
    source: Literal["owner_console"] = OWNER_TRIAL_FLOW_SOURCE
    metadata_only: Literal[True] = True


class OwnerTrialFlowCurrentResponse(BaseModel):
    generated_from: Literal["owner_trial_flow_v1"] = "owner_trial_flow_v1"
    selected_carrier_id: str
    carrier: dict[str, str | bool]
    strategy_warnings: list[dict[str, str | bool]]
    hard_blockers: list[dict[str, str | bool]]
    acknowledged_warnings: list[str] = Field(default_factory=list)
    unacknowledged_warnings: list[str] = Field(default_factory=list)
    latest_acknowledgement: OwnerRiskAcknowledgement | None = None
    authorization_draft: BoundedLiveTrialAuthorizationDraft | None = None
    live_authorization: BoundedLiveTrialAuthorization | None = None
    authorization_status: Literal[
        "not_started",
        "pending_owner_live_authorization",
        "owner_live_authorized_pending_final_preflight",
    ]
    live_ready: Literal[False] = False
    execution_permission_granted: Literal[False] = False
    order_permission_granted: Literal[False] = False
    execution_intent_created: Literal[False] = False
    order_created: Literal[False] = False
    hard_blockers_remain_blocking: Literal[True] = True
    risk_acknowledgement_is_not_live_authorization: Literal[True] = True
    authorization_draft_is_not_executable: Literal[True] = True
    live_authorization_is_not_execution_intent: Literal[True] = True
    live_authorization_does_not_create_order: Literal[True] = True
    source: Literal["backend_metadata"] = "backend_metadata"


class OwnerTrialFlowRepository(Protocol):
    async def create_acknowledgement(
        self,
        acknowledgement: OwnerRiskAcknowledgement,
    ) -> OwnerRiskAcknowledgement:
        ...

    async def get_acknowledgement(
        self,
        acknowledgement_id: str,
    ) -> OwnerRiskAcknowledgement | None:
        ...

    async def latest_acknowledgement(
        self,
        carrier_id: str,
    ) -> OwnerRiskAcknowledgement | None:
        ...

    async def upsert_draft(
        self,
        draft: BoundedLiveTrialAuthorizationDraft,
    ) -> BoundedLiveTrialAuthorizationDraft:
        ...

    async def get_draft(
        self,
        draft_id: str,
    ) -> BoundedLiveTrialAuthorizationDraft | None:
        ...

    async def latest_draft(
        self,
        carrier_id: str,
    ) -> BoundedLiveTrialAuthorizationDraft | None:
        ...

    async def create_live_authorization(
        self,
        authorization: BoundedLiveTrialAuthorization,
    ) -> BoundedLiveTrialAuthorization:
        ...

    async def latest_live_authorization(
        self,
        carrier_id: str,
    ) -> BoundedLiveTrialAuthorization | None:
        ...

    async def live_authorization_for_draft(
        self,
        draft_id: str,
    ) -> BoundedLiveTrialAuthorization | None:
        ...

    async def get_live_authorization(
        self,
        authorization_id: str,
    ) -> BoundedLiveTrialAuthorization | None:
        ...

    async def mark_live_authorization_consumed(
        self,
        authorization_id: str,
        *,
        occurred_at_ms: int,
    ) -> BoundedLiveTrialAuthorization:
        ...


class OwnerTrialFlowService:
    def __init__(self, repository: OwnerTrialFlowRepository) -> None:
        self._repository = repository

    async def current(self, *, carrier_id: str = SUPPORTED_OWNER_TRIAL_CARRIER_ID) -> OwnerTrialFlowCurrentResponse:
        carrier = _supported_carrier(carrier_id)
        acknowledgement = await self._repository.latest_acknowledgement(carrier.carrier_id)
        draft = await self._repository.latest_draft(carrier.carrier_id)
        authorization = await self._repository.latest_live_authorization(carrier.carrier_id)
        if draft is not None:
            draft_authorization = await self._repository.live_authorization_for_draft(draft.draft_id)
            if draft_authorization is not None and (
                authorization is None
                or draft_authorization.authorization_id != authorization.authorization_id
            ):
                draft = None
        warnings = _warning_rows(carrier.carrier_id)
        warning_ids = [str(row["warning_id"]) for row in warnings]
        acknowledged = [
            code
            for code in (acknowledgement.acknowledged_warning_codes if acknowledgement else [])
            if code in warning_ids
        ]
        unacknowledged = [code for code in warning_ids if code not in acknowledged]
        return OwnerTrialFlowCurrentResponse(
            selected_carrier_id=carrier.carrier_id,
            carrier=_carrier_summary(carrier),
            strategy_warnings=warnings,
            hard_blockers=_hard_blocker_rows(live_authorization=authorization),
            acknowledged_warnings=acknowledged,
            unacknowledged_warnings=unacknowledged,
            latest_acknowledgement=acknowledgement,
            authorization_draft=draft,
            live_authorization=authorization,
            authorization_status=(
                "owner_live_authorized_pending_final_preflight"
                if authorization
                else "pending_owner_live_authorization" if draft else "not_started"
            ),
        )

    async def create_risk_acknowledgement(
        self,
        request: OwnerRiskAcknowledgementCreateRequest,
        *,
        operator_id: str = "owner",
    ) -> OwnerRiskAcknowledgement:
        carrier = _supported_carrier(request.carrier_id)
        requested = _dedupe(request.acknowledged_warning_codes)
        known = set(_required_warning_ids(carrier.carrier_id))
        unknown = [code for code in requested if code not in known]
        if unknown:
            raise OwnerTrialFlowError(
                "unsupported_warning_code",
                f"Unsupported strategy warning code(s): {', '.join(unknown)}",
            )
        if not requested:
            raise OwnerTrialFlowError(
                "empty_risk_acknowledgement",
                "At least one strategy warning code must be acknowledged.",
            )
        now = _now_ms()
        acknowledgement = OwnerRiskAcknowledgement(
            acknowledgement_id=f"ack-{uuid.uuid4().hex}",
            carrier_id=carrier.carrier_id,
            strategy_family_id=carrier.strategy_id,
            acknowledged_warning_codes=requested,
            owner_id=request.owner_id or operator_id,
            acknowledged_at_ms=now,
            acknowledgement_scope=request.acknowledgement_scope,
        )
        return await self._repository.create_acknowledgement(acknowledgement)

    async def create_authorization_draft(
        self,
        request: BoundedLiveTrialAuthorizationDraftCreateRequest,
        *,
        operator_id: str = "owner",
    ) -> BoundedLiveTrialAuthorizationDraft:
        carrier = _supported_carrier(request.carrier_id)
        acknowledgement = await self._repository.get_acknowledgement(
            request.linked_acknowledgement_id
        )
        if acknowledgement is None:
            raise OwnerTrialFlowError(
                "linked_acknowledgement_missing",
                "Authorization draft requires a backend-recorded risk acknowledgement.",
            )
        if acknowledgement.carrier_id != carrier.carrier_id:
            raise OwnerTrialFlowError(
                "acknowledgement_carrier_mismatch",
                "Linked acknowledgement belongs to a different carrier.",
            )
        missing = [
            code
            for code in _required_warning_ids(carrier.carrier_id)
            if code not in acknowledgement.acknowledged_warning_codes
        ]
        if missing:
            raise OwnerTrialFlowError(
                "strategy_warning_acknowledgement_incomplete",
                f"Required strategy warning(s) are not acknowledged: {', '.join(missing)}",
            )
        _validate_draft_scope(request, carrier)
        now = _now_ms()
        existing = await self._repository.latest_draft(carrier.carrier_id)
        if existing is not None and await self._repository.live_authorization_for_draft(existing.draft_id):
            existing = None
        draft = BoundedLiveTrialAuthorizationDraft(
            draft_id=existing.draft_id if existing else f"draft-{uuid.uuid4().hex}",
            carrier_id=carrier.carrier_id,
            strategy_family_id=carrier.strategy_id,
            symbol=carrier.runtime_symbol,
            side=carrier.side,
            max_notional=request.max_notional,
            quantity=request.quantity,
            leverage=request.leverage,
            protection_plan_type=request.protection_plan_type,
            expires_at_ms=request.expires_at_ms,
            linked_acknowledgement_id=acknowledgement.acknowledgement_id,
            created_at_ms=existing.created_at_ms if existing else now,
            updated_at_ms=now,
        )
        _ = operator_id  # Retained for future audit expansion; draft remains non-live metadata.
        return await self._repository.upsert_draft(draft)

    async def get_draft(self, draft_id: str) -> BoundedLiveTrialAuthorizationDraft:
        draft = await self._repository.get_draft(draft_id)
        if draft is None:
            raise OwnerTrialFlowError("draft_not_found", "Authorization draft not found.")
        return draft

    async def activate_live_authorization(
        self,
        draft_id: str,
        request: OwnerLiveAuthorizationActivationRequest,
        *,
        operator_id: str = "owner",
    ) -> BoundedLiveTrialAuthorization:
        draft = await self.get_draft(draft_id)
        if draft.status != "pending_owner_live_authorization":
            raise OwnerTrialFlowError(
                "draft_not_pending_owner_live_authorization",
                "Only a pending Owner live authorization draft can be activated.",
            )
        if draft.consumed:
            raise OwnerTrialFlowError("draft_already_consumed", "Authorization draft is already consumed.")
        if draft.expires_at_ms is not None and draft.expires_at_ms <= _now_ms():
            raise OwnerTrialFlowError("draft_expired", "Authorization draft has expired.")
        if (
            draft.live_ready
            or draft.order_permission_granted
            or draft.execution_permission_granted
            or draft.execution_intent_created
            or draft.order_created
            or draft.auto_execution_enabled
        ):
            raise OwnerTrialFlowError(
                "draft_has_executable_state",
                "Authorization draft contains executable state and cannot be activated.",
            )
        existing = await self._repository.live_authorization_for_draft(draft.draft_id)
        if existing is not None:
            raise OwnerTrialFlowError(
                "live_authorization_already_exists",
                "This authorization draft has already been explicitly authorized.",
            )
        carrier = _supported_carrier(request.carrier_id)
        if draft.carrier_id != carrier.carrier_id:
            raise OwnerTrialFlowError("draft_carrier_mismatch", "Draft carrier does not match activation request.")
        _validate_activation_scope(request, draft, carrier)
        acknowledgement = await self._repository.get_acknowledgement(draft.linked_acknowledgement_id)
        if acknowledgement is None:
            raise OwnerTrialFlowError(
                "linked_acknowledgement_missing",
                "Explicit live authorization requires a backend-recorded risk acknowledgement.",
            )
        if acknowledgement.carrier_id != draft.carrier_id:
            raise OwnerTrialFlowError(
                "acknowledgement_carrier_mismatch",
                "Linked acknowledgement belongs to a different carrier.",
            )
        missing = [
            code
            for code in _required_warning_ids(carrier.carrier_id)
            if code not in acknowledgement.acknowledged_warning_codes
        ]
        if missing:
            raise OwnerTrialFlowError(
                "strategy_warning_acknowledgement_incomplete",
                f"Required strategy warning(s) are not acknowledged: {', '.join(missing)}",
            )
        now = _now_ms()
        authorization = BoundedLiveTrialAuthorization(
            authorization_id=f"auth-{uuid.uuid4().hex}",
            draft_id=draft.draft_id,
            carrier_id=draft.carrier_id,
            strategy_family_id=draft.strategy_family_id,
            symbol=draft.symbol,
            side=draft.side,
            max_notional=draft.max_notional,
            quantity=draft.quantity,
            leverage=draft.leverage,
            protection_plan_type=draft.protection_plan_type,
            owner_live_authorized_by=request.owner_id or operator_id,
            owner_live_authorized_at_ms=now,
            expires_at_ms=draft.expires_at_ms,
            linked_acknowledgement_id=draft.linked_acknowledgement_id,
            source_draft_id=draft.draft_id,
            hard_blockers=["startup_guard_status_unavailable_runtime_not_started"],
            created_at_ms=now,
            updated_at_ms=now,
        )
        return await self._repository.create_live_authorization(authorization)


def _supported_carrier(carrier_id: str) -> StrategyTrialCarrierView:
    carrier = get_owner_action_carrier(carrier_id)
    if carrier is None:
        raise OwnerTrialFlowError(
            "unsupported_carrier",
            f"Unsupported owner trial carrier: {carrier_id}",
        )
    return carrier


def _validate_draft_scope(
    request: BoundedLiveTrialAuthorizationDraftCreateRequest,
    carrier: StrategyTrialCarrierView,
) -> None:
    if request.symbol not in {carrier.symbol, carrier.runtime_symbol}:
        raise OwnerTrialFlowError("symbol_mismatch", "Draft symbol does not match carrier.")
    if request.side != carrier.side:
        raise OwnerTrialFlowError("side_mismatch", "Draft side does not match carrier.")
    if request.max_notional > carrier.max_notional:
        raise OwnerTrialFlowError("cap_violation", "Draft max notional exceeds carrier cap.")
    if request.quantity > carrier.quantity:
        raise OwnerTrialFlowError("cap_violation", "Draft quantity exceeds carrier cap.")
    if request.leverage > carrier.max_leverage_allowed:
        raise OwnerTrialFlowError("cap_violation", "Draft leverage exceeds carrier cap.")
    if request.protection_plan_type != carrier.protection_plan_type:
        raise OwnerTrialFlowError(
            "protection_not_executable",
            "Draft protection plan does not match carrier protection plan.",
        )


def _validate_activation_scope(
    request: OwnerLiveAuthorizationActivationRequest,
    draft: BoundedLiveTrialAuthorizationDraft,
    carrier: StrategyTrialCarrierView,
) -> None:
    _validate_draft_scope(
        BoundedLiveTrialAuthorizationDraftCreateRequest(
            carrier_id=request.carrier_id,
            linked_acknowledgement_id=draft.linked_acknowledgement_id,
            symbol=request.symbol,
            side=request.side,
            max_notional=request.max_notional,
            quantity=request.quantity,
            leverage=request.leverage,
            protection_plan_type=request.protection_plan_type,
            expires_at_ms=draft.expires_at_ms,
        ),
        carrier,
    )
    if request.symbol not in {draft.symbol, carrier.symbol, carrier.runtime_symbol}:
        raise OwnerTrialFlowError("symbol_mismatch", "Activation symbol does not match draft.")
    if request.side != draft.side:
        raise OwnerTrialFlowError("side_mismatch", "Activation side does not match draft.")
    if not _decimal_scope_equal(request.max_notional, draft.max_notional):
        raise OwnerTrialFlowError("cap_violation", "Activation max notional does not match draft.")
    if not _decimal_scope_equal(request.quantity, draft.quantity):
        raise OwnerTrialFlowError("cap_violation", "Activation quantity does not match draft.")
    if not _decimal_scope_equal(request.leverage, draft.leverage):
        raise OwnerTrialFlowError("cap_violation", "Activation leverage does not match draft.")
    if request.protection_plan_type != draft.protection_plan_type:
        raise OwnerTrialFlowError(
            "protection_not_executable",
            "Activation protection plan does not match draft.",
        )


def _required_warning_ids(carrier_id: str) -> list[str]:
    return required_owner_action_warning_ids(carrier_id)


def _warning_rows(carrier_id: str) -> list[dict[str, str | bool]]:
    return owner_action_warning_rows(carrier_id)


def _decimal_scope_equal(left: Decimal, right: Decimal) -> bool:
    return abs(Decimal(str(left)) - Decimal(str(right))) <= Decimal("0.000000000001")


def _hard_blocker_rows(
    *,
    live_authorization: BoundedLiveTrialAuthorization | None = None,
) -> list[dict[str, str | bool]]:
    if live_authorization is not None:
        return [
            {
                "blocker_id": "startup_guard_status_unavailable_runtime_not_started",
                "active": True,
                "blocks_after_ack": True,
                "description": "Owner live authorization is recorded; final startup guard preflight is still required before any execution intent or order.",
                "source": "owner_trial_flow",
                "classification": "hard_safety_blocker",
            }
        ]
    return [
        {
            "blocker_id": "missing_explicit_live_authorization",
            "active": True,
            "blocks_after_ack": True,
            "description": "Real live / real-funds authorization has not been explicitly granted.",
            "source": "owner_trial_flow",
            "classification": "hard_safety_blocker",
        }
    ]


def _carrier_summary(carrier: StrategyTrialCarrierView) -> dict[str, str | bool]:
    return {
        "carrier_id": carrier.carrier_id,
        "strategy_family_id": carrier.strategy_id,
        "strategy_id": carrier.strategy_id,
        "candidate_id": carrier.candidate_id,
        "symbol": carrier.symbol,
        "runtime_symbol": carrier.runtime_symbol,
        "side": carrier.side,
        "execution_mode": carrier.execution_mode,
        "max_notional": str(carrier.max_notional),
        "quantity": str(carrier.quantity),
        "leverage": str(carrier.leverage),
        "protection_plan_type": carrier.protection_plan_type,
        "live_ready": False,
        "order_permission_granted": False,
    }


def _dedupe(values: list[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        if value not in deduped:
            deduped.append(value)
    return deduped


def _now_ms() -> int:
    return int(time.time() * 1000)
