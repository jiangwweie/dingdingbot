"""Research control plane domain models.

These models describe research jobs and candidates only. They must not become
runtime configuration or execution state models.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from src.domain.models import BacktestRuntimeOverrides


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ResearchJobStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"


class CandidateStatus(str, Enum):
    DRAFT = "DRAFT"
    REVIEWED = "REVIEWED"
    REJECTED = "REJECTED"
    RECOMMENDED = "RECOMMENDED"


class ResearchEngineCostSpec(BaseModel):
    initial_balance: Decimal = Decimal("10000")
    slippage_rate: Decimal = Decimal("0.0001")
    tp_slippage_rate: Decimal = Decimal("0")
    fee_rate: Decimal = Decimal("0.000405")


class ResearchSpec(BaseModel):
    """Serializable research input. It is not a runtime profile update."""

    kind: Literal["backtest"] = "backtest"
    name: str = Field(..., min_length=1, max_length=120)
    profile_name: str = Field(default="backtest_eth_baseline", min_length=1, max_length=120)
    symbol: str = Field(default="ETH/USDT:USDT", min_length=1, max_length=80)
    timeframe: str = Field(default="1h", min_length=1, max_length=16)
    start_time_ms: int = Field(..., ge=0)
    end_time_ms: int = Field(..., ge=0)
    limit: int = Field(default=9000, ge=10, le=30000)
    mode: Literal["v3_pms"] = "v3_pms"
    costs: ResearchEngineCostSpec = Field(default_factory=ResearchEngineCostSpec)
    runtime_overrides: Optional[BacktestRuntimeOverrides] = None
    notes: Optional[str] = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def validate_window(self) -> "ResearchSpec":
        if self.end_time_ms <= self.start_time_ms:
            raise ValueError("end_time_ms must be greater than start_time_ms")
        return self


class ResearchJob(BaseModel):
    id: str
    kind: Literal["backtest"] = "backtest"
    name: str
    spec_ref: str
    status: ResearchJobStatus
    run_result_id: Optional[str] = None
    created_at: str = Field(default_factory=utc_now_iso)
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    requested_by: str = "local"
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    progress_pct: Optional[int] = Field(default=None, ge=0, le=100)
    spec: ResearchSpec


class ResearchRunResult(BaseModel):
    id: str
    job_id: str
    kind: Literal["backtest"] = "backtest"
    spec_snapshot: dict[str, Any]
    summary_metrics: dict[str, Any]
    artifact_index: dict[str, str]
    source_profile: Optional[str] = None
    generated_at: str = Field(default_factory=utc_now_iso)


class CandidateRecord(BaseModel):
    id: str
    run_result_id: str
    candidate_name: str = Field(..., min_length=1, max_length=160)
    status: CandidateStatus = CandidateStatus.DRAFT
    review_notes: str = Field(default="", max_length=10000)
    applicable_market: Optional[str] = Field(default=None, max_length=500)
    risks: list[str] = Field(default_factory=list)
    recommendation: Optional[str] = Field(default=None, max_length=5000)
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


class CandidateReviewRequest(BaseModel):
    status: CandidateStatus
    review_notes: str = Field(default="", max_length=10000)
    applicable_market: Optional[str] = Field(default=None, max_length=500)
    risks: list[str] = Field(default_factory=list)
    recommendation: Optional[str] = Field(default=None, max_length=5000)


class CreateCandidateRequest(BaseModel):
    run_result_id: str
    candidate_name: str = Field(..., min_length=1, max_length=160)
    review_notes: str = Field(default="", max_length=10000)


class ResearchJobAccepted(BaseModel):
    status: Literal["accepted"] = "accepted"
    job_id: str
    job_status: ResearchJobStatus


class ResearchJobListResponse(BaseModel):
    jobs: list[ResearchJob]
    total: int
    limit: int
    offset: int


class ResearchRunListResponse(BaseModel):
    runs: list[ResearchRunResult]
    total: int
    limit: int
    offset: int
