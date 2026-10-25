"""Owner risk preference; an additional ceiling, never trading permission."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest


class DirectionalView(StrEnum):
    UNSET = "unset"
    BULLISH = "bullish"
    NEUTRAL = "neutral"
    BEARISH = "bearish"


RULE_ID = "owner-directional-risk:v1"
ENTRY_SEND_WINDOW_MS = 5_000
RULE_LIMITS = {
    "unset": ("0.04", "0.04"),
    "bullish": ("0.04", "0.02"),
    "neutral": ("0.04", "0.04"),
    "bearish": ("0.02", "0.04"),
}
SCOPED_EVENTS = frozenset(
    {
        "event_spec:CPM-RO-001:CPM-LONG:v3",
        "event_spec:MPG-001:MPG-LONG:v3",
        "event_spec:MI-001:MI-LONG:v3",
        "event_spec:BRF2-001:BRF2-SHORT:v3",
        "event_spec:SOR-1H-001:SOR-1H-LONG:v1",
        "event_spec:SOR-1H-001:SOR-1H-SHORT:v1",
    }
)
RULE_DIGEST = canonical_digest(
    {"rule_id": RULE_ID, "limits": RULE_LIMITS, "event_spec_ids": sorted(SCOPED_EVENTS)}
)


class DirectionalControl(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    venue_id: str
    account_id: str
    version: int = Field(ge=1)
    view: DirectionalView
    effective_at_ms: int = Field(gt=0)
    rule_id: str = RULE_ID
    rule_digest: str = RULE_DIGEST
    pending_view: DirectionalView | None = None
    pending_request_id: str | None = None
    requested_at_ms: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def valid(self):
        if not self.venue_id.strip() or not self.account_id.strip():
            raise ValueError("directional_identity_blank")
        if self.rule_id != RULE_ID or self.rule_digest != RULE_DIGEST:
            raise ValueError("directional_rule_mismatch")
        if (self.pending_view is None) != (self.pending_request_id is None):
            raise ValueError("directional_pending_shape")
        if self.pending_view is not None and (
            self.pending_view == DirectionalView.UNSET or not self.requested_at_ms
        ):
            raise ValueError("directional_pending_shape")
        return self


class DirectionalChangeRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    venue_id: str
    account_id: str
    expected_version: int = Field(ge=1)
    view: Literal["bullish", "neutral", "bearish"]
    owner_identity: str
    reason: str = Field(min_length=1, max_length=512)
    idempotency_key: str = Field(min_length=1, max_length=160)
    requested_at_ms: int = Field(gt=0)

    @field_validator(
        "venue_id", "account_id", "owner_identity", "reason", "idempotency_key"
    )
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("directional_identity_blank")
        return value.strip()


def effective_directional_limit(
    control: DirectionalControl | None, side: Literal["long", "short"], base: Decimal
) -> Decimal:
    if control is None:
        raise ValueError("directional_control_missing")
    if control.pending_view is not None:
        raise ValueError("directional_transition_pending")
    return min(base, Decimal(RULE_LIMITS[control.view][0 if side == "long" else 1]))
