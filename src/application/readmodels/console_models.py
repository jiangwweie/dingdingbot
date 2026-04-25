from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


FreshnessStatus = Literal["Fresh", "Stale", "Possibly Dead"]
HealthStatus = Literal["OK", "DEGRADED", "DOWN"]
ReviewStatus = Literal[
    "PASS_STRICT",
    "PASS_STRICT_WITH_WARNINGS",
    "PASS_LOOSE",
    "REJECT",
    "PENDING",
]


class RuntimeOverviewResponse(BaseModel):
    profile: str
    version: str
    hash: str
    frozen: bool
    symbol: str
    timeframe: str
    mode: str
    backend_summary: str
    exchange_health: HealthStatus
    pg_health: HealthStatus
    webhook_health: HealthStatus
    breaker_count: int
    reconciliation_summary: str
    server_time: str
    last_runtime_update_at: str
    last_heartbeat_at: str
    freshness_status: FreshnessStatus


class PortfolioPositionItem(BaseModel):
    symbol: str
    direction: Literal["LONG", "SHORT"]
    quantity: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    pnl_percent: float
    leverage: int


class RuntimePortfolioResponse(BaseModel):
    total_equity: float
    available_balance: float
    unrealized_pnl: float
    total_exposure: float
    daily_loss_used: float
    daily_loss_limit: float
    max_total_exposure: float
    leverage_usage: float
    positions: list[PortfolioPositionItem] = Field(default_factory=list)


class BreakerSummaryResponse(BaseModel):
    total_tripped: int
    active_breakers: list[str] = Field(default_factory=list)
    last_trip_time: Optional[str] = None


class RecoverySummaryResponse(BaseModel):
    pending_tasks: int
    completed_tasks: int
    last_recovery_time: Optional[str] = None


class RuntimeHealthResponse(BaseModel):
    pg_status: HealthStatus
    exchange_status: HealthStatus
    notification_status: HealthStatus
    recent_warnings: list[str] = Field(default_factory=list)
    recent_errors: list[str] = Field(default_factory=list)
    startup_markers: dict[str, Literal["PASSED", "FAILED", "PENDING"]] = Field(default_factory=dict)
    breaker_summary: BreakerSummaryResponse
    recovery_summary: RecoverySummaryResponse


class CandidateListItem(BaseModel):
    candidate_name: str
    generated_at: str
    source_profile: str
    git_commit: str
    objective: str
    review_status: ReviewStatus
    strict_gate_result: Literal["PASSED", "FAILED"]
    warnings: list[str] = Field(default_factory=list)

