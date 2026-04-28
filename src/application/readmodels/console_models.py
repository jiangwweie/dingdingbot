from __future__ import annotations

from typing import Any, Literal, Optional

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
    active_positions: Optional[int] = None
    active_signals: Optional[int] = None
    pending_intents: Optional[int] = None
    pending_recovery_tasks: Optional[int] = None
    total_equity: Optional[float] = None
    unrealized_pnl: Optional[float] = None


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


# ============================================================
# Console Runtime v1 - Second Batch Models
# ============================================================


class ConsolePositionItem(BaseModel):
    """Console-facing position item for runtime/positions endpoint."""

    symbol: str
    direction: Literal["LONG", "SHORT"]
    quantity: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    leverage: int
    margin: float = Field(default=0.0, description="Margin (if available)")
    exposure: float = Field(default=0.0, description="Notional exposure (if available)")
    updated_at: Optional[str] = None


class ConsolePositionsResponse(BaseModel):
    """Response model for GET /api/runtime/positions."""

    positions: list[ConsolePositionItem] = Field(default_factory=list)


class ConsoleSignalItem(BaseModel):
    """Console-facing signal item for runtime/signals endpoint."""

    signal_id: str
    symbol: str
    timeframe: str
    direction: Literal["LONG", "SHORT"]
    strategy_name: str
    score: float = Field(default=0.0, description="Pattern quality score")
    created_at: str
    status: Optional[str] = None


class ConsoleSignalsResponse(BaseModel):
    """Response model for GET /api/runtime/signals."""

    signals: list[ConsoleSignalItem] = Field(default_factory=list)


class ConsoleAttemptItem(BaseModel):
    """Console-facing attempt item for runtime/attempts endpoint."""

    attempt_id: str
    signal_id: Optional[str] = None
    symbol: str
    timeframe: str
    direction: Optional[str] = None
    strategy_name: Optional[str] = None
    final_result: str
    reject_reason: Optional[str] = None
    filter_reason: Optional[str] = None
    created_at: str


class ConsoleAttemptsResponse(BaseModel):
    """Response model for GET /api/runtime/attempts."""

    attempts: list[ConsoleAttemptItem] = Field(default_factory=list)


class ConsoleOrderItem(BaseModel):
    """Console-facing order item for runtime/execution/orders endpoint."""

    order_id: str
    symbol: str
    order_role: Optional[str] = None
    side: str
    type: str
    status: str
    qty: float
    price: Optional[float] = None
    reduce_only: bool = False
    created_at: str
    updated_at: Optional[str] = None


class ConsoleOrdersResponse(BaseModel):
    """Response model for GET /api/runtime/execution/orders."""

    orders: list[ConsoleOrderItem] = Field(default_factory=list)


class ConsoleEventItem(BaseModel):
    """Console-facing event item for runtime/events endpoint."""

    id: str
    timestamp: str
    category: Literal[
        "STARTUP", "RECONCILIATION", "BREAKER", "RECOVERY",
        "WARNING", "ERROR", "SIGNAL", "EXECUTION",
    ]
    severity: Literal["INFO", "WARN", "ERROR", "SUCCESS"]
    message: str
    related_entities: list[str] = Field(default_factory=list)


class ConsoleEventsResponse(BaseModel):
    """Response model for GET /api/runtime/events."""

    events: list[ConsoleEventItem] = Field(default_factory=list)


class ConsoleExecutionIntentItem(BaseModel):
    """Console-facing execution intent item for runtime/execution/intents endpoint."""

    intent_id: str
    symbol: str
    side: str
    intent_type: str = Field(default="ENTRY", description="Intent type")
    status: str
    quantity: float
    created_at: str
    updated_at: Optional[str] = None
    related_signal_id: Optional[str] = None


class ConsoleExecutionIntentsResponse(BaseModel):
    """Response model for GET /api/runtime/execution/intents."""

    intents: list[ConsoleExecutionIntentItem] = Field(default_factory=list)


# ============================================================
# Console Research v1 - Third Batch Models
# ============================================================


class CandidateTrialItem(BaseModel):
    """A single trial within a candidate (best_trial or top_trials entry)."""

    trial_number: int = Field(default=0)
    objective_value: Optional[float] = None
    sharpe_ratio: Optional[float] = None
    sortino_ratio: Optional[float] = None
    total_return: Optional[float] = None
    max_drawdown: Optional[float] = None
    total_trades: int = Field(default=0)
    win_rate: Optional[float] = None
    params: dict[str, Any] = Field(default_factory=dict)
    completed_at: Optional[str] = None


class CandidateMetadata(BaseModel):
    """Candidate metadata block shared by detail and replay endpoints."""

    candidate_name: str
    generated_at: str
    source_profile: dict[str, Any] = Field(default_factory=dict)
    git: dict[str, Any] = Field(default_factory=dict)
    objective: str = "unknown"
    status: str = "unknown"


class CandidateDetailResponse(BaseModel):
    """Response model for GET /api/research/candidates/{candidate_name}."""

    candidate_name: str
    metadata: CandidateMetadata
    best_trial: Optional[CandidateTrialItem] = None
    top_trials: list[CandidateTrialItem] = Field(default_factory=list)
    fixed_params: dict[str, Any] = Field(default_factory=dict)
    runtime_overrides: dict[str, Any] = Field(default_factory=dict)
    constraints: dict[str, Any] = Field(default_factory=dict)
    resolved_request: dict[str, Any] = Field(default_factory=dict)
    reproduce_cmd: str = ""
    # Legacy top-level fields kept for backward compat
    generated_at: str = ""
    source_profile: dict[str, Any] = Field(default_factory=dict)
    git: dict[str, Any] = Field(default_factory=dict)
    objective: str = "unknown"
    status: str = "unknown"


class ReplayContextResponse(BaseModel):
    """Response model for GET /api/research/replay/{candidate_name}."""

    candidate_name: str
    metadata: CandidateMetadata
    reproduce_cmd: str
    resolved_request: dict[str, Any] = Field(default_factory=dict)
    runtime_overrides: dict[str, Any] = Field(default_factory=dict)
    # Legacy top-level field kept for backward compat
    generated_at: str = ""


class StrictGateCheckItem(BaseModel):
    """A single gate check in the strict_v1 checklist."""

    gate: str
    threshold: str
    actual: Optional[str] = None
    passed: bool = False


class ReviewSummaryResponse(BaseModel):
    """Response model for GET /api/research/candidates/{candidate_name}/review-summary."""

    candidate_name: str
    review_status: ReviewStatus
    strict_gate_result: Literal["PASSED", "FAILED"]
    strict_v1_checklist: list[StrictGateCheckItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    params_at_boundary: list[str] = Field(default_factory=list)
    summary: str = ""


class ConsoleBacktestMetrics(BaseModel):
    """Metrics summary for a single backtest record."""

    total_return: Optional[float] = None
    sharpe: Optional[float] = None
    max_drawdown: Optional[float] = None
    win_rate: Optional[float] = None
    trades: Optional[int] = None


class ConsoleBacktestItem(BaseModel):
    """Console-facing backtest record for research/backtests endpoint."""

    id: str
    candidate_ref: str = ""
    symbol: str
    timeframe: str
    start_date: str = ""
    end_date: str = ""
    status: Literal["COMPLETED", "RUNNING", "FAILED"] = "COMPLETED"
    metrics: ConsoleBacktestMetrics = Field(default_factory=ConsoleBacktestMetrics)


class ConsoleBacktestsResponse(BaseModel):
    """Response model for GET /api/research/backtests."""

    backtests: list[ConsoleBacktestItem] = Field(default_factory=list)


class CompareRow(BaseModel):
    """A single metric row in the compare response."""

    metric: str
    baseline: Optional[float] = None
    candidate_a: Optional[float] = None
    candidate_b: Optional[float] = None
    diff_a: Optional[float] = None
    diff_b: Optional[float] = None


class CompareResponse(BaseModel):
    """Response model for GET /api/research/compare/candidates."""

    baseline_label: str = ""
    candidate_a_label: str = ""
    candidate_b_label: Optional[str] = None
    rows: list[CompareRow] = Field(default_factory=list)


class ConfigIdentity(BaseModel):
    """Identity block for config/snapshot."""

    profile: str
    version: int
    hash: str


class ConfigSnapshotResponse(BaseModel):
    """Response model for GET /api/config/snapshot."""

    identity: ConfigIdentity
    market: dict[str, Any] = Field(default_factory=dict)
    strategy: dict[str, Any] = Field(default_factory=dict)
    risk: dict[str, Any] = Field(default_factory=dict)
    execution: dict[str, Any] = Field(default_factory=dict)
    backend: dict[str, Any] = Field(default_factory=dict)
    source_of_truth_hints: list[str] = Field(default_factory=list)
    # Legacy top-level fields kept for backward compat
    profile: str = ""
    version: int = 0
    hash: str = ""
    environment: dict[str, Any] = Field(default_factory=dict)
