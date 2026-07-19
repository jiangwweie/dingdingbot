"""Pure immutable identity and versioned facts for one exchange instrument."""

from __future__ import annotations

from decimal import Decimal
from hashlib import sha256
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


CANONICAL_INSTRUMENT_IDENTITY_SCHEMA_VERSION = "v2"


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


def build_canonical_exchange_instrument_id(
    *,
    exchange_id: str,
    exchange_symbol: str,
    asset_class: str,
    instrument_type: str,
    settlement_asset: str,
    margin_asset: str,
    instrument_identity_schema_version: str = (
        CANONICAL_INSTRUMENT_IDENTITY_SCHEMA_VERSION
    ),
) -> str:
    """Build one stable opaque ID from immutable instrument semantics.

    The digest is deliberately opaque. Runtime consumers must load the typed
    registry row and must never recover business meaning by parsing this ID.
    """

    payload = {
        "exchange_id": _canonical_identity_text(exchange_id),
        "exchange_symbol": _canonical_identity_text(exchange_symbol),
        "asset_class": _canonical_identity_text(asset_class),
        "instrument_type": _canonical_identity_text(instrument_type),
        "settlement_asset": _canonical_identity_text(settlement_asset),
        "margin_asset": _canonical_identity_text(margin_asset),
        "instrument_identity_schema_version": _canonical_identity_text(
            instrument_identity_schema_version
        ),
    }
    digest = sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return f"exchange_instrument:{instrument_identity_schema_version}:{digest[:40]}"


def _canonical_identity_text(value: object) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError("canonical instrument identity fields must be nonblank")
    return normalized


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


class InstrumentRuleSnapshotRefV2(_FrozenNonblankModel):
    """Current linear quote-settled rule facts with explicit economics."""

    instrument_rule_snapshot_id: str = Field(min_length=1, max_length=192)
    rule_schema_version: Literal["v2"]
    price_tick: Decimal = Field(gt=0)
    quantity_step: Decimal = Field(gt=0)
    min_qty: Decimal = Field(gt=0)
    min_notional: Decimal = Field(gt=0)
    contract_multiplier: Decimal = Field(gt=0)
    exchange_max_leverage_for_claim_notional: int = Field(gt=0)
    source_fact_snapshot_id: str = Field(min_length=1, max_length=192)
    valid_until_ms: int = Field(gt=0)
    risk_calculation_kind: Literal["linear_quote_settled"]
    semantic_hash: str = Field(min_length=64, max_length=64)

    @field_validator("semantic_hash")
    @classmethod
    def _verify_semantic_hash(cls, value: str, info: object) -> str:
        data = getattr(info, "data", {})
        required = {
            "instrument_rule_snapshot_id",
            "rule_schema_version",
            "price_tick",
            "quantity_step",
            "min_qty",
            "min_notional",
            "contract_multiplier",
            "exchange_max_leverage_for_claim_notional",
            "source_fact_snapshot_id",
            "valid_until_ms",
            "risk_calculation_kind",
        }
        if not required <= set(data):
            return value
        expected = instrument_rule_snapshot_v2_semantic_hash(data)
        if value != expected:
            raise ValueError("instrument rule v2 semantic hash mismatch")
        return value


def instrument_rule_snapshot_v2_semantic_hash(value: object) -> str:
    """Canonical immutable hash for the complete V2 linear-risk rule."""

    data = value.model_dump(mode="python") if hasattr(value, "model_dump") else dict(value)
    fields = (
        "instrument_rule_snapshot_id",
        "rule_schema_version",
        "price_tick",
        "quantity_step",
        "min_qty",
        "min_notional",
        "contract_multiplier",
        "exchange_max_leverage_for_claim_notional",
        "source_fact_snapshot_id",
        "valid_until_ms",
        "risk_calculation_kind",
    )
    payload = {
        field: format(data[field].normalize(), "f")
        if isinstance(data[field], Decimal)
        else data[field]
        for field in fields
    }
    return sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


class RiskClusterMembershipSnapshotRef(_FrozenNonblankModel):
    """Versioned primary-cluster fact; V0 does not enforce secondary clusters."""

    cluster_membership_snapshot_id: str = Field(min_length=1, max_length=192)
    primary_risk_cluster_id: str = Field(min_length=1, max_length=192)
    semantic_hash: str = Field(min_length=1, max_length=128)
