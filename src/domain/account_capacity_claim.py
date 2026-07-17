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
    InstrumentRuleSnapshotRefV2,
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
    event_spec_id: str = Field(min_length=1, max_length=192)
    account_id: str = Field(min_length=1, max_length=192)
    runtime_profile_id: str = Field(min_length=1, max_length=192)
    strategy_group_id: str = Field(min_length=1, max_length=128)
    symbol: str = Field(min_length=1, max_length=128)
    side: Literal["long", "short"]
    instrument: InstrumentRiskIdentity
    rule_snapshot: InstrumentRuleSnapshotRef
    cluster_snapshot: RiskClusterMembershipSnapshotRef
    pricing_source_fact_snapshot_id: str = Field(min_length=1, max_length=192)
    account_source_fact_snapshot_id: str = Field(min_length=1, max_length=192)
    account_fact_schema_version: str = Field(min_length=1, max_length=32)
    account_risk_policy_version: str = Field(min_length=1, max_length=192)
    account_risk_policy_event_id: str = Field(min_length=1, max_length=192)
    owner_policy_version: str = Field(min_length=1, max_length=192)
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


class AccountCapacityClaimPayloadV2(AccountCapacityClaimPayload):
    """New immutable Claim authority for linear quote-settled instruments."""

    capacity_claim_schema_version: Literal["v2"]
    rule_snapshot: InstrumentRuleSnapshotRefV2


def load_capacity_claim_payload(
    value: object,
) -> AccountCapacityClaimPayload | AccountCapacityClaimPayloadV2:
    """Dispatch persisted Claims without upgrading an opaque V1 in memory."""

    if isinstance(value, (AccountCapacityClaimPayload, AccountCapacityClaimPayloadV2)):
        return value
    if not isinstance(value, dict):
        raise ValueError("account_capacity_claim_payload_invalid")
    version = str(value.get("capacity_claim_schema_version") or "")
    if version == "v1":
        return AccountCapacityClaimPayload.model_validate(value)
    if version == "v2":
        return AccountCapacityClaimPayloadV2.model_validate(value)
    raise ValueError("account_capacity_claim_schema_version_unknown")


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


def revalidate_capacity_totals(
    *,
    current_portfolio_held_risk: Decimal,
    current_primary_cluster_held_risk: Decimal,
    current_pending_margin: Decimal,
    current_claimed_position_slots: int,
    available_balance: Decimal,
    claim_risk: Decimal,
    claim_margin: Decimal,
    portfolio_limit: Decimal,
    cluster_limit: Decimal,
    margin_limit: Decimal,
    max_concurrent_positions: int,
) -> tuple[str, ...]:
    """Recheck one already-counted immutable claim against current capacity."""

    decimal_values = (
        current_portfolio_held_risk,
        current_primary_cluster_held_risk,
        current_pending_margin,
        available_balance,
        claim_risk,
        claim_margin,
        portfolio_limit,
        cluster_limit,
        margin_limit,
    )
    if (
        not all(value.is_finite() and value >= 0 for value in decimal_values)
        or current_claimed_position_slots < 0
        or max_concurrent_positions < 1
    ):
        return ("account_capacity_revalidation_input_invalid",)

    other_risk = max(
        Decimal("0"), current_portfolio_held_risk - claim_risk
    )
    other_cluster = max(
        Decimal("0"), current_primary_cluster_held_risk - claim_risk
    )
    other_margin = max(
        Decimal("0"), current_pending_margin - claim_margin
    )
    blockers: list[str] = []
    if other_risk + claim_risk > portfolio_limit:
        blockers.append("portfolio_open_risk_capacity_exhausted")
    if other_cluster + claim_risk > cluster_limit:
        blockers.append("risk_cluster_open_risk_capacity_exhausted")
    if other_margin + claim_margin > margin_limit:
        blockers.append("portfolio_initial_margin_capacity_exhausted")
    if other_margin + claim_margin > available_balance:
        blockers.append("available_balance_capacity_exhausted")
    if current_claimed_position_slots > max_concurrent_positions:
        blockers.append("max_concurrent_positions_reached")
    return tuple(blockers)
