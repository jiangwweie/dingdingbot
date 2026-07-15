"""Pure immutable payload and deterministic identity for one capacity claim."""

from __future__ import annotations

import json
from decimal import Decimal
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.domain.instrument_risk_identity import (
    InstrumentRiskIdentity,
    InstrumentRuleSnapshotRef,
    RiskClusterMembershipSnapshotRef,
)


class AccountCapacityClaimPayload(BaseModel):
    """All immutable facts that determine one Action-Time capacity reservation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    capacity_claim_schema_version: str = Field(min_length=1, max_length=32)
    reservation_id: str = Field(min_length=1, max_length=192)
    ticket_id: str = Field(min_length=1, max_length=192)
    exposure_episode_id: str = Field(min_length=1, max_length=192)
    action_time_invocation_id: str = Field(min_length=1, max_length=192)
    action_time_lane_input_id: str = Field(min_length=1, max_length=192)
    promotion_candidate_id: str = Field(min_length=1, max_length=192)
    signal_event_id: str = Field(min_length=1, max_length=192)
    account_id: str = Field(min_length=1, max_length=192)
    runtime_profile_id: str = Field(min_length=1, max_length=192)
    strategy_group_id: str = Field(min_length=1, max_length=128)
    side: Literal["long", "short"]
    instrument: InstrumentRiskIdentity
    rule_snapshot: InstrumentRuleSnapshotRef
    cluster_snapshot: RiskClusterMembershipSnapshotRef
    pricing_source_fact_snapshot_id: str = Field(min_length=1, max_length=192)
    account_source_fact_snapshot_id: str = Field(min_length=1, max_length=192)
    account_fact_schema_version: str = Field(min_length=1, max_length=32)
    account_risk_policy_version: str = Field(min_length=1, max_length=192)
    account_risk_policy_event_id: str = Field(min_length=1, max_length=192)
    claimed_budget_projection_version: int = Field(ge=0)
    entry_reference_price: Decimal = Field(gt=0)
    stop_price: Decimal = Field(gt=0)
    intended_qty: Decimal = Field(gt=0)
    target_notional: Decimal = Field(gt=0)
    allowed_risk_budget: Decimal = Field(ge=0)
    planned_stop_risk: Decimal = Field(ge=0)
    reserved_margin: Decimal = Field(ge=0)
    selected_leverage: int = Field(gt=0)
    reserved_at_ms: int = Field(gt=0)
    expires_at_ms: int = Field(gt=0)

    @field_validator("*", mode="before")
    @classmethod
    def _reject_blank_strings(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                raise ValueError("capacity claim string must be nonblank")
            return normalized
        return value


def _canonical(value: object) -> object:
    """Convert Decimal-containing model data into deterministic JSON-safe values."""

    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    if isinstance(value, dict):
        return {key: _canonical(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    return value


def capacity_claim_hash(payload: AccountCapacityClaimPayload) -> str:
    """Hash every immutable semantic fact that describes the claimed capacity."""

    encoded = json.dumps(
        _canonical(payload.model_dump(mode="python")),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def reservation_idempotency_key(payload: AccountCapacityClaimPayload) -> str:
    """Keep retry identity stable across mutable policy or lane semantic changes."""

    parts = (
        payload.account_id,
        payload.runtime_profile_id,
        payload.action_time_invocation_id,
    )
    return "account_capacity:" + sha256("|".join(parts).encode("utf-8")).hexdigest()
