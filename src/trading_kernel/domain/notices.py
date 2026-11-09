"""Frozen display facts; never grant trading or order authority."""

from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class NoticeKind(StrEnum):
    OPENED = "opened"
    TAKEOVER = "takeover"
    TP1 = "tp1"
    MANUAL_FILL = "manual_fill"
    CLOSED = "closed"
    RESIDUAL = "residual"
    RISK = "risk"
    RECOVERED = "recovered"
    REVIEW = "review"
    REVIEW_CLEARED = "review_cleared"


class StopView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    price: Decimal = Field(gt=0, allow_inf_nan=False)
    quantity: Decimal = Field(ge=0, allow_inf_nan=False)
    full_position: bool

    @field_validator("price", "quantity", mode="before")
    @classmethod
    def exact_number(cls, value: object) -> object:
        if isinstance(value, (float, bool)):
            raise TypeError("financial display facts require exact decimal values")
        return value


class NoticeSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    ticket_id: str
    event_id: str
    state_version: int = Field(ge=1)
    kind: NoticeKind
    severity: Literal["info", "warning", "critical"]
    symbol: str
    side: Literal["long", "short"]
    mode: Literal["AUTO", "MANUAL", "REVIEW_REQUIRED"]
    quantity: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    entry_price: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    fill_role: Literal["TP1", "止损"] | None = None
    fill_quantity: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    fill_price: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    price_tick: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    stops: tuple[StopView, ...] = ()
    protection: Literal["full", "partial", "none", "unknown"]
    protected_quantity: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    strategy: str
    strategy_semantics: str
    event_at_ms: int = Field(ge=0)
    facts_at_ms: int | None = Field(default=None, ge=0)
    residual_order_count: int | None = Field(default=None, ge=0)
    new_entry_restricted: bool = False
    risk_at_stop: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)

    @field_validator(
        "quantity",
        "entry_price",
        "price_tick",
        "fill_quantity",
        "fill_price",
        "protected_quantity",
        "risk_at_stop",
        mode="before",
    )
    @classmethod
    def exact_number(cls, value: object) -> object:
        if isinstance(value, (float, bool)):
            raise TypeError("financial display facts require exact decimal values")
        return value


TEMPLATE_VERSION = "seoul-notice-v1"
