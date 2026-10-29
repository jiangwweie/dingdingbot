"""Certified Owner risk baseline; one Policy owns all effective amounts."""

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MIN_BASELINE = Decimal("0.020")
MAX_BASELINE = Decimal("0.030")
BASELINE_STEP = Decimal("0.001")
DEFAULT_BASELINE = MIN_BASELINE
BUDGET_CONTRACT = {
    "minimum": "0.020",
    "maximum": "0.030",
    "step": "0.001",
    "default": "0.020",
    "gross_multiplier": "3",
    "directional_multiplier": "2",
    "minimum_materialization": "0.50",
}


class RiskBudget(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    baseline: Decimal

    @field_validator("baseline")
    @classmethod
    def valid_baseline(cls, value: Decimal) -> Decimal:
        if (
            not value.is_finite()
            or not MIN_BASELINE <= value <= MAX_BASELINE
            or value % BASELINE_STEP
        ):
            raise ValueError("risk_budget_outside_certified_range")
        return value

    @property
    def gross(self) -> Decimal:
        return self.baseline * 3

    @property
    def directional(self) -> Decimal:
        return self.baseline * 2

    @property
    def minimum(self) -> Decimal:
        return self.baseline / 2


class RiskBudgetChangeRequest(RiskBudget):
    venue_id: str = Field(min_length=1)
    account_id: str = Field(min_length=1)
    owner_policy_id: str = Field(min_length=1)
    expected_policy_version: int = Field(ge=1)
    expected_directional_version: int = Field(ge=1)
    owner_identity: str = Field(min_length=1)
    reason: str = Field(min_length=1, max_length=512)
    idempotency_key: str = Field(min_length=1, max_length=160)
    requested_at_ms: int = Field(gt=0)

    @field_validator(
        "venue_id",
        "account_id",
        "owner_policy_id",
        "owner_identity",
        "reason",
        "idempotency_key",
    )
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("risk_budget_identity_blank")
        return value.strip()


def policy_budget_is_valid(row) -> bool:
    """Validate current linked fields; defaults are not runtime authority."""
    try:
        budget = RiskBudget(baseline=row["max_ticket_stop_risk_fraction"])
        return (
            Decimal(str(row["max_gross_stop_risk_fraction"])) == budget.gross
            and Decimal(str(row["directional_stop_risk_limit_fraction"]))
            == budget.directional
            and Decimal(str(row["min_materialization_ratio"])) == Decimal(".50")
        )
    except (ValueError, KeyError, TypeError):
        return False


class RiskBudgetReceipt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    request_id: str
    status: Literal["pending", "effective", "unchanged"]
    baseline: str
    requested_at_ms: int
    policy_version: int | None = None
    effective_at_ms: int | None = None
