"""Refresh account capacity truth from one prefetched full-account snapshot."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
import sqlalchemy as sa

from src.application.action_time.account_budget_current import (
    AccountBudgetCurrent,
    project_account_budget_current,
)
from src.application.action_time.account_exchange_ownership import (
    classify_account_exchange_truth,
)
from src.application.action_time.account_exposure_current import (
    AccountExposureProjectionResult,
    project_account_exposure_current,
)
from src.application.action_time.account_risk_policy import (
    load_account_risk_policy_current,
)
from src.infrastructure.binance_usdm_account_risk_snapshot import (
    FullAccountRiskSnapshot,
)


class AccountRiskReprojectionResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: str
    account_id: str
    runtime_profile_id: str
    source_snapshot_id: str
    projection_version: int | None = None
    semantic_event_count: int = 0
    first_blocker: str | None = None


def reproject_account_risk_current(
    conn: sa.Connection,
    *,
    snapshot: FullAccountRiskSnapshot,
    runtime_profile_id: str,
    now_ms: int,
) -> AccountRiskReprojectionResult:
    """Project one read-only exchange snapshot without creating a Ticket claim."""

    if not snapshot.snapshot_ready:
        return _blocked(
            snapshot,
            runtime_profile_id,
            snapshot.failure_code or "account_risk_snapshot_not_ready",
        )
    if snapshot.can_trade is not True:
        return _blocked(snapshot, runtime_profile_id, "account_trade_permission_not_true")
    policy = load_account_risk_policy_current(
        conn,
        account_id=snapshot.account_id,
        runtime_profile_id=runtime_profile_id,
    )
    if policy is None:
        return _blocked(snapshot, runtime_profile_id, "account_risk_policy_missing_or_changed")
    classification = classify_account_exchange_truth(conn, snapshot=snapshot)
    exposure = project_account_exposure_current(
        conn,
        snapshot=snapshot,
        classification=classification,
        runtime_profile_id=runtime_profile_id,
        max_concurrent_positions=policy.max_concurrent_positions,
        now_ms=now_ms,
    )
    budget = project_account_budget_current(
        conn,
        snapshot=snapshot,
        runtime_profile_id=runtime_profile_id,
        policy=policy,
        now_ms=now_ms,
    )
    blockers = [
        *classification.blockers,
        *exposure.global_blockers,
        *([budget.first_blocker] if budget.first_blocker else []),
    ]
    return AccountRiskReprojectionResult(
        status="blocked" if blockers else "reprojected",
        account_id=snapshot.account_id,
        runtime_profile_id=runtime_profile_id,
        source_snapshot_id=snapshot.source_snapshot_id,
        projection_version=budget.projection_version,
        semantic_event_count=exposure.semantic_event_count,
        first_blocker=blockers[0] if blockers else None,
    )


def _blocked(
    snapshot: FullAccountRiskSnapshot,
    runtime_profile_id: str,
    blocker: str,
) -> AccountRiskReprojectionResult:
    return AccountRiskReprojectionResult(
        status="blocked",
        account_id=snapshot.account_id,
        runtime_profile_id=runtime_profile_id,
        source_snapshot_id=snapshot.source_snapshot_id,
        first_blocker=blocker,
    )
