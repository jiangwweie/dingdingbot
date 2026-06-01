"""PG-backed multi-carrier budget authorization foundation.

This module stores non-live budget metadata only. It never creates execution
intents, grants order permission, starts runtime, or calls exchange APIs.
"""

from __future__ import annotations

import time
import uuid
from decimal import Decimal
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.application.strategy_trial_carrier_expansion import (
    FIRST_CARRIER_ID,
    budget_eligible_carrier_ids,
    carrier_by_id,
)


BUDGET_AUTHORIZATION_SOURCE = "owner_console"


class MultiCarrierBudgetAuthorizationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class MultiCarrierBudgetAuthorizationInfrastructureError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class CarrierBudgetScope(BaseModel):
    model_config = ConfigDict(frozen=True)

    carrier_id: str
    strategy_family_id: str
    symbol: str
    side: Literal["long", "short"]
    per_carrier_cap: Decimal = Field(gt=Decimal("0"))
    risk_cap_profile_id: str
    protection_plan_type: Literal["single_tp_plus_sl"]
    status: Literal["allowed_metadata_only"] = "allowed_metadata_only"
    live_ready: Literal[False] = False
    auto_execution_enabled: Literal[False] = False
    order_permission_granted: Literal[False] = False
    execution_intent_created: Literal[False] = False
    order_created: Literal[False] = False


class MultiCarrierBudgetAuthorizationCreateRequest(BaseModel):
    allowed_carrier_ids: list[str]
    per_carrier_caps: dict[str, Decimal]
    global_budget: Decimal = Field(gt=Decimal("0"))
    max_attempts: int = Field(gt=0)
    daily_loss_limit: Decimal = Field(gt=Decimal("0"))
    max_concurrent_positions: int = Field(gt=0)
    cooldown_seconds: int = Field(ge=0)
    valid_from_ms: int | None = None
    valid_until_ms: int | None = None
    linked_acknowledgement_id: str | None = None
    linked_authorization_id: str | None = None

    @model_validator(mode="after")
    def _validate_window(self) -> "MultiCarrierBudgetAuthorizationCreateRequest":
        if (
            self.valid_from_ms is not None
            and self.valid_until_ms is not None
            and self.valid_until_ms <= self.valid_from_ms
        ):
            raise ValueError("valid_until_ms must be greater than valid_from_ms")
        return self


class MultiCarrierBudgetAuthorization(BaseModel):
    model_config = ConfigDict(frozen=True)

    budget_authorization_id: str
    allowed_carriers: list[CarrierBudgetScope]
    global_budget: Decimal = Field(gt=Decimal("0"))
    max_attempts: int = Field(gt=0)
    daily_loss_limit: Decimal = Field(gt=Decimal("0"))
    max_concurrent_positions: int = Field(gt=0)
    cooldown_seconds: int = Field(ge=0)
    valid_from_ms: int | None = None
    valid_until_ms: int | None = None
    status: Literal["draft_disabled_pending_owner_authorization"] = (
        "draft_disabled_pending_owner_authorization"
    )
    linked_acknowledgement_id: str | None = None
    linked_authorization_id: str | None = None
    live_ready: Literal[False] = False
    auto_execution_enabled: Literal[False] = False
    order_permission_granted: Literal[False] = False
    execution_permission_granted: Literal[False] = False
    execution_intent_created: Literal[False] = False
    order_created: Literal[False] = False
    source: Literal["owner_console"] = BUDGET_AUTHORIZATION_SOURCE
    metadata_only: Literal[True] = True
    created_at_ms: int
    updated_at_ms: int


class MultiCarrierBudgetAuthorizationCurrentResponse(BaseModel):
    generated_from: Literal["multi_carrier_budget_authorization_foundation_v1"] = (
        "multi_carrier_budget_authorization_foundation_v1"
    )
    latest_budget_authorization: MultiCarrierBudgetAuthorization | None
    eligible_carrier_ids: list[str]
    disabled_execution_state: dict[str, bool]
    budget_scope_source: Literal["pg_metadata"] = "pg_metadata"


class MultiCarrierBudgetAuthorizationRepository(Protocol):
    async def create(
        self,
        authorization: MultiCarrierBudgetAuthorization,
    ) -> MultiCarrierBudgetAuthorization:
        ...

    async def latest(self) -> MultiCarrierBudgetAuthorization | None:
        ...


class MultiCarrierBudgetAuthorizationService:
    def __init__(self, repository: MultiCarrierBudgetAuthorizationRepository) -> None:
        self._repository = repository

    async def current(self) -> MultiCarrierBudgetAuthorizationCurrentResponse:
        return MultiCarrierBudgetAuthorizationCurrentResponse(
            latest_budget_authorization=await self._repository.latest(),
            eligible_carrier_ids=sorted(budget_eligible_carrier_ids()),
            disabled_execution_state=_disabled_execution_state(),
        )

    async def create_foundation(
        self,
        request: MultiCarrierBudgetAuthorizationCreateRequest,
    ) -> MultiCarrierBudgetAuthorization:
        allowed_ids = _dedupe(request.allowed_carrier_ids)
        scopes = _validate_and_build_scopes(allowed_ids, request)
        now = _now_ms()
        authorization = MultiCarrierBudgetAuthorization(
            budget_authorization_id=f"budget-{uuid.uuid4().hex}",
            allowed_carriers=scopes,
            global_budget=request.global_budget,
            max_attempts=request.max_attempts,
            daily_loss_limit=request.daily_loss_limit,
            max_concurrent_positions=request.max_concurrent_positions,
            cooldown_seconds=request.cooldown_seconds,
            valid_from_ms=request.valid_from_ms,
            valid_until_ms=request.valid_until_ms,
            linked_acknowledgement_id=request.linked_acknowledgement_id,
            linked_authorization_id=request.linked_authorization_id,
            created_at_ms=now,
            updated_at_ms=now,
        )
        return await self._repository.create(authorization)


def _validate_and_build_scopes(
    allowed_ids: list[str],
    request: MultiCarrierBudgetAuthorizationCreateRequest,
) -> list[CarrierBudgetScope]:
    if len(allowed_ids) < 2:
        raise MultiCarrierBudgetAuthorizationError(
            "budget_scope_too_narrow",
            "Budget authorization foundation must reference at least two carriers.",
        )
    if all(carrier_id == FIRST_CARRIER_ID for carrier_id in allowed_ids):
        raise MultiCarrierBudgetAuthorizationError(
            "bnb_only_budget_scope_rejected",
            "Budget authorization foundation cannot be BNB-only.",
        )
    eligible = budget_eligible_carrier_ids()
    unsupported = [carrier_id for carrier_id in allowed_ids if carrier_id not in eligible]
    if unsupported:
        raise MultiCarrierBudgetAuthorizationError(
            "unsupported_or_unsafe_carrier_scope",
            f"Unsupported or unsafe budget carrier scope: {', '.join(unsupported)}",
        )
    missing_caps = [carrier_id for carrier_id in allowed_ids if carrier_id not in request.per_carrier_caps]
    if missing_caps:
        raise MultiCarrierBudgetAuthorizationError(
            "missing_per_carrier_cap",
            f"Missing per-carrier cap(s): {', '.join(missing_caps)}",
        )
    if request.daily_loss_limit > request.global_budget:
        raise MultiCarrierBudgetAuthorizationError(
            "daily_loss_limit_exceeds_global_budget",
            "Daily loss limit cannot exceed global budget.",
        )
    if request.max_concurrent_positions > len(allowed_ids):
        raise MultiCarrierBudgetAuthorizationError(
            "max_concurrent_positions_exceeds_scope",
            "Max concurrent positions cannot exceed allowed carrier count.",
        )

    scopes: list[CarrierBudgetScope] = []
    for carrier_id in allowed_ids:
        carrier = carrier_by_id(carrier_id)
        if carrier is None or not carrier.budget_foundation_eligible:
            raise MultiCarrierBudgetAuthorizationError(
                "unsupported_or_unsafe_carrier_scope",
                f"Unsupported or unsafe budget carrier scope: {carrier_id}",
            )
        cap = request.per_carrier_caps[carrier_id]
        if cap <= Decimal("0"):
            raise MultiCarrierBudgetAuthorizationError(
                "invalid_per_carrier_cap",
                f"Per-carrier cap must be positive: {carrier_id}",
            )
        if cap > request.global_budget:
            raise MultiCarrierBudgetAuthorizationError(
                "per_carrier_cap_exceeds_global_budget",
                f"Per-carrier cap exceeds global budget: {carrier_id}",
            )
        if cap > carrier.risk_cap_draft.per_carrier_cap:
            raise MultiCarrierBudgetAuthorizationError(
                "per_carrier_cap_exceeds_carrier_draft",
                f"Per-carrier cap exceeds carrier draft cap: {carrier_id}",
            )
        scopes.append(
            CarrierBudgetScope(
                carrier_id=carrier.carrier_id,
                strategy_family_id=carrier.strategy_family,
                symbol=carrier.runtime_symbol,
                side=carrier.side,
                per_carrier_cap=cap,
                risk_cap_profile_id=carrier.risk_cap_draft.cap_profile_id,
                protection_plan_type=carrier.protection_feasibility.protection_plan_type,
            )
        )
    return scopes


def _disabled_execution_state() -> dict[str, bool]:
    return {
        "live_ready": False,
        "auto_execution_enabled": False,
        "order_permission_granted": False,
        "execution_permission_granted": False,
        "execution_intent_created": False,
        "order_created": False,
    }


def _dedupe(values: list[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        if value not in deduped:
            deduped.append(value)
    return deduped


def _now_ms() -> int:
    return int(time.time() * 1000)
