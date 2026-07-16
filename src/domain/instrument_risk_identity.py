"""Pure immutable identity and versioned facts for one exchange instrument."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _FrozenNonblankModel(BaseModel):
    """Shared pure-domain validation for immutable persisted fact objects."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    @field_validator("*", mode="before")
    @classmethod
    def _reject_blank_strings(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                raise ValueError("identity fact string must be nonblank")
            return normalized
        return value


class InstrumentRiskIdentity(_FrozenNonblankModel):
    """Canonical opaque exchange instrument identity independent of display symbol."""

    exchange_instrument_id: str = Field(min_length=1, max_length=192)
    exchange_id: str = Field(min_length=1, max_length=96)
    exchange_symbol: str = Field(min_length=1, max_length=128)
    asset_class: str = Field(min_length=1, max_length=64)
    instrument_type: str = Field(min_length=1, max_length=64)
    settlement_asset: str = Field(min_length=1, max_length=64)
    margin_asset: str = Field(min_length=1, max_length=64)
    instrument_identity_schema_version: str = Field(min_length=1, max_length=32)


class InstrumentRuleSnapshotRef(_FrozenNonblankModel):
    """Versioned exchange rule facts used when a capacity claim is made."""

    instrument_rule_snapshot_id: str = Field(min_length=1, max_length=192)
    rule_schema_version: str = Field(min_length=1, max_length=32)
    price_tick: Decimal = Field(gt=0)
    quantity_step: Decimal = Field(gt=0)
    min_qty: Decimal = Field(gt=0)
    min_notional: Decimal = Field(gt=0)
    contract_multiplier: Decimal = Field(gt=0)
    exchange_max_leverage_for_claim_notional: int = Field(gt=0)
    source_fact_snapshot_id: str = Field(min_length=1, max_length=192)
    valid_until_ms: int = Field(gt=0)


class RiskClusterMembershipSnapshotRef(_FrozenNonblankModel):
    """Versioned primary-cluster fact; V0 does not enforce secondary clusters."""

    cluster_membership_snapshot_id: str = Field(min_length=1, max_length=192)
    primary_risk_cluster_id: str = Field(min_length=1, max_length=192)
    semantic_hash: str = Field(min_length=1, max_length=128)
