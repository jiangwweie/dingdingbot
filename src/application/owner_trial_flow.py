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

from src.application.strategy_trial_architecture_governance import (
    StrategyTrialCarrierView,
    build_bnb_strategy_trial_architecture_governance,
)


SUPPORTED_OWNER_TRIAL_CARRIER_ID = "MI-001-BNB-LONG"
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
    consumed: Literal[False] = False
    expires_at_ms: int | None = None
    linked_acknowledgement_id: str
    created_at_ms: int
    updated_at_ms: int
    source: Literal["owner_console"] = OWNER_TRIAL_FLOW_SOURCE
    non_live_metadata_only: Literal[True] = True


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
    authorization_status: Literal["not_started", "pending_owner_live_authorization"]
    live_ready: Literal[False] = False
    execution_permission_granted: Literal[False] = False
    order_permission_granted: Literal[False] = False
    execution_intent_created: Literal[False] = False
    order_created: Literal[False] = False
    hard_blockers_remain_blocking: Literal[True] = True
    risk_acknowledgement_is_not_live_authorization: Literal[True] = True
    authorization_draft_is_not_executable: Literal[True] = True
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


class OwnerTrialFlowService:
    def __init__(self, repository: OwnerTrialFlowRepository) -> None:
        self._repository = repository

    async def current(self, *, carrier_id: str = SUPPORTED_OWNER_TRIAL_CARRIER_ID) -> OwnerTrialFlowCurrentResponse:
        carrier = _supported_carrier(carrier_id)
        acknowledgement = await self._repository.latest_acknowledgement(carrier.carrier_id)
        draft = await self._repository.latest_draft(carrier.carrier_id)
        warnings = _warning_rows()
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
            hard_blockers=_hard_blocker_rows(),
            acknowledged_warnings=acknowledged,
            unacknowledged_warnings=unacknowledged,
            latest_acknowledgement=acknowledgement,
            authorization_draft=draft,
            authorization_status=(
                "pending_owner_live_authorization" if draft else "not_started"
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
        known = set(_required_warning_ids())
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
            for code in _required_warning_ids()
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


def _supported_carrier(carrier_id: str) -> StrategyTrialCarrierView:
    if carrier_id != SUPPORTED_OWNER_TRIAL_CARRIER_ID:
        raise OwnerTrialFlowError(
            "unsupported_carrier",
            f"Unsupported owner trial carrier: {carrier_id}",
        )
    return build_bnb_strategy_trial_architecture_governance().owner_review_packet.carrier


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


def _required_warning_ids() -> list[str]:
    return [
        warning.warning_id
        for warning in build_bnb_strategy_trial_architecture_governance().owner_review_packet.strategy_warnings
        if warning.owner_ack_required
    ]


def _warning_rows() -> list[dict[str, str | bool]]:
    return [
        {
            "warning_id": warning.warning_id,
            "severity": warning.severity,
            "description": warning.description,
            "owner_ack_required": warning.owner_ack_required,
            "blocks_after_ack": warning.blocks_after_ack,
            "classification": "strategy_warning",
        }
        for warning in build_bnb_strategy_trial_architecture_governance().owner_review_packet.strategy_warnings
    ]


def _hard_blocker_rows() -> list[dict[str, str | bool]]:
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
