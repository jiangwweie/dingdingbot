"""Consume a prefetched full-account snapshot inside the short PG transaction."""

from __future__ import annotations

import sqlalchemy as sa

from src.application.action_time.account_capacity_reservation import (
    AccountCapacityCandidate,
    AccountCapacityReservationResult,
    reserve_account_capacity_for_candidate,
)
from src.application.action_time.account_exchange_ownership import (
    classify_account_exchange_truth,
)
from src.application.action_time.account_exposure_current import (
    project_account_exposure_current,
)
from src.application.action_time.account_budget_current import (
    project_account_budget_current,
)
from src.application.action_time.account_risk_policy import (
    AccountRiskPolicyCurrentProjection,
    load_account_risk_policy_current_projection,
)
from src.infrastructure.binance_usdm_account_risk_snapshot import FullAccountRiskSnapshot


def materialize_account_capacity_from_snapshot(
    conn: sa.Connection,
    *,
    snapshot: FullAccountRiskSnapshot,
    runtime_profile_id: str,
    candidate: AccountCapacityCandidate,
    now_ms: int,
) -> AccountCapacityReservationResult:
    """Classify, project, and atomically claim capacity from a prefetched snapshot."""
    if not snapshot.snapshot_ready:
        return _blocked(snapshot.failure_code or "account_risk_snapshot_not_ready")
    if snapshot.can_trade is not True:
        return _blocked("account_trade_permission_not_true")
    if snapshot.position_mode not in {"one_way", "hedge"}:
        return _blocked("account_position_mode_not_safe")
    if snapshot.account_id != candidate.account_id or runtime_profile_id != candidate.runtime_profile_id:
        return _blocked("account_capacity_scope_mismatch")
    classification = classify_account_exchange_truth(conn, snapshot=snapshot)
    if classification.blockers:
        return _blocked(classification.blockers[0])
    policy_projection = lock_account_risk_policy_current(
        conn,
        account_id=candidate.account_id,
        runtime_profile_id=runtime_profile_id,
    )
    if policy_projection is None:
        return _blocked("account_risk_policy_missing_or_changed")
    policy = policy_projection.policy
    exposure = project_account_exposure_current(
        conn,
        snapshot=snapshot,
        classification=classification,
        runtime_profile_id=runtime_profile_id,
        max_concurrent_positions=policy.max_concurrent_positions,
        now_ms=now_ms,
    )
    if exposure.global_blockers:
        return _blocked(exposure.global_blockers[0])
    budget = project_account_budget_current(
        conn, snapshot=snapshot, runtime_profile_id=runtime_profile_id,
        policy=policy, now_ms=now_ms
    )
    if not lock_account_budget_current(
        conn,
        account_id=candidate.account_id,
        runtime_profile_id=runtime_profile_id,
    ):
        return _blocked("account_budget_current_missing")
    return reserve_account_capacity_for_candidate(
        conn, candidate=candidate,
        expected_source_snapshot_id=snapshot.source_snapshot_id,
        expected_projection_version=budget.projection_version,
        now_ms=now_ms,
    )


def _blocked(blocker: str) -> AccountCapacityReservationResult:
    return AccountCapacityReservationResult(allowed=False, first_blocker=blocker)


def lock_account_budget_current(
    conn: sa.Connection,
    *,
    account_id: str,
    runtime_profile_id: str,
) -> bool:
    """Lock the exact bootstrapped Budget Current row before capacity calculation."""

    if not sa.inspect(conn).has_table("brc_account_budget_current"):
        return False
    budgets = sa.Table("brc_account_budget_current", sa.MetaData(), autoload_with=conn)
    row = conn.execute(
        sa.select(budgets.c.account_budget_current_id)
        .where(budgets.c.account_id == account_id)
        .where(budgets.c.runtime_profile_id == runtime_profile_id)
        .with_for_update()
    ).first()
    return row is not None


def lock_account_risk_policy_current(
    conn: sa.Connection,
    *,
    account_id: str,
    runtime_profile_id: str,
) -> AccountRiskPolicyCurrentProjection | None:
    """Lock current policy first and verify its immutable source event when present."""

    if not sa.inspect(conn).has_table("brc_account_risk_policy_current"):
        return None
    policies = sa.Table(
        "brc_account_risk_policy_current", sa.MetaData(), autoload_with=conn
    )
    row = conn.execute(
        sa.select(policies.c.source_event_id)
        .where(policies.c.account_id == account_id)
        .where(policies.c.runtime_profile_id == runtime_profile_id)
        .with_for_update()
    ).mappings().one_or_none()
    if row is None or not str(row.get("source_event_id") or "").strip():
        return None
    projection = load_account_risk_policy_current_projection(
        conn,
        account_id=account_id,
        runtime_profile_id=runtime_profile_id,
    )
    if projection is None:
        return None
    if sa.inspect(conn).has_table("brc_account_risk_policy_events"):
        events = sa.Table(
            "brc_account_risk_policy_events", sa.MetaData(), autoload_with=conn
        )
        matching = conn.execute(
            sa.select(events.c.account_risk_policy_event_id)
            .where(
                events.c.account_risk_policy_event_id
                == projection.source_event_id
            )
            .where(events.c.account_id == account_id)
            .where(events.c.runtime_profile_id == runtime_profile_id)
            .where(
                events.c.risk_policy_version
                == projection.policy.risk_policy_version
            )
            .limit(2)
        ).all()
        if len(matching) != 1:
            return None
    return projection
