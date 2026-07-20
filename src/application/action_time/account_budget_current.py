"""Build the single account budget projection from exposure and reservation facts."""

from __future__ import annotations

from decimal import Decimal
from hashlib import sha256

from pydantic import BaseModel, ConfigDict
import sqlalchemy as sa

from src.domain.account_risk import AccountRiskPolicy
from src.infrastructure.binance_usdm_account_risk_snapshot import FullAccountRiskSnapshot
from src.infrastructure.account_capacity_hot_path_repository import (
    load_effective_reservation_rows,
    load_live_exposure_rows,
)


_ZERO = Decimal("0")


class AccountBudgetCurrent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    account_id: str
    runtime_profile_id: str
    risk_policy_version: str
    open_directional_risk: Decimal
    reserved_risk: Decimal
    working_entry_risk: Decimal
    unknown_held_risk: Decimal
    unreflected_pending_margin: Decimal
    portfolio_held_risk: Decimal
    claimed_position_slots: int
    pending_ticket_claims: int
    new_entry_allowed: bool
    first_blocker: str | None
    projection_version: int


def project_account_budget_current(
    conn: sa.Connection,
    *,
    snapshot: FullAccountRiskSnapshot,
    runtime_profile_id: str,
    policy: AccountRiskPolicy,
    now_ms: int,
    projection_version_override: int | None = None,
) -> AccountBudgetCurrent:
    if not snapshot.snapshot_ready or not snapshot.total_wallet_balance or snapshot.available_balance is None or snapshot.exchange_total_initial_margin is None:
        raise ValueError("fresh complete account snapshot is required")
    exposure_result = load_live_exposure_rows(
        conn,
        account_id=snapshot.account_id,
        max_concurrent_positions=policy.max_concurrent_positions,
    )
    reservation_result = load_effective_reservation_rows(
        conn,
        account_id=snapshot.account_id,
        runtime_profile_id=runtime_profile_id,
        max_concurrent_positions=policy.max_concurrent_positions,
    )
    live_exposures = list(exposure_result.rows)
    exposure_ticket_ids = {
        str(row.owner_ticket_id or "")
        for row in live_exposures
        if row.owner_ticket_id
    }
    effective_reservations = [
        row
        for row in reservation_result.rows
        if str(row.ticket_id or "") not in exposure_ticket_ids
    ]
    open_risk = sum(
        (
            row.actual_directional_risk
            for row in live_exposures
            if row.exposure_state
            in {"open_protected", "working_entry", "partially_exited", "runner_active"}
        ),
        _ZERO,
    )
    working_risk = sum(
        (
            row.held_risk
            for row in live_exposures
            if row.exposure_state == "working_entry"
        ),
        _ZERO,
    )
    reserved_risk = sum(
        (row.risk_at_stop for row in effective_reservations), _ZERO
    )
    unknown_risk = sum(
        (
            row.held_risk
            for row in live_exposures
            if row.reconciliation_state in {"unknown", "mismatch"}
        ),
        _ZERO,
    )
    exposure_held_risk = sum(
        (row.held_risk for row in live_exposures), _ZERO
    )
    exposure_pending_margin = sum(
        (row.unreflected_pending_margin for row in live_exposures),
        _ZERO,
    )
    reservation_pending_margin = sum(
        (
            row.reserved_margin
            for row in effective_reservations
            if row.margin_accounting_state == "reserved_unreflected"
        ),
        _ZERO,
    )
    pending_margin = exposure_pending_margin + reservation_pending_margin
    blockers = {
        str(row.first_blocker)
        for row in live_exposures
        if row.first_blocker
    }
    if exposure_result.overflow:
        blockers.add("account_exposure_current_overflow")
    if reservation_result.overflow:
        blockers.add("account_capacity_claim_current_overflow")
    ordered_blockers = sorted(blockers)
    # `held_risk` is the per-exposure max of actual directional risk, remaining
    # working-entry risk, and any known reservation.  Summing the rows once
    # avoids counting a protected partial fill, its working remainder, and its
    # consumed reservation as three independent portfolio risks.
    held = exposure_held_risk + reserved_risk
    claimed_exposure_keys = {
        str(row.owner_ticket_id or row.account_exposure_current_id or "")
        for row in live_exposures
        if row.position_slot_claimed
    }
    pending_ticket_keys = {
        str(row.ticket_id or row.budget_reservation_id or "")
        for row in effective_reservations
    }
    slots = len({key for key in claimed_exposure_keys if key})
    pending = len({key for key in pending_ticket_keys if key})
    limit = snapshot.total_wallet_balance * policy.max_portfolio_open_risk_fraction
    margin_limit = snapshot.total_wallet_balance * policy.max_portfolio_initial_margin_fraction
    claimed_slots = slots + pending
    capacity_blocker: str | None = None
    if claimed_slots >= policy.max_concurrent_positions:
        capacity_blocker = "max_concurrent_positions_reached"
    elif held >= limit:
        capacity_blocker = "portfolio_risk_limit_reached"
    elif snapshot.exchange_total_initial_margin + pending_margin >= margin_limit:
        capacity_blocker = "portfolio_margin_limit_reached"
    entry_blockers = [*ordered_blockers, *([capacity_blocker] if capacity_blocker else [])]
    new_entry_allowed = not entry_blockers
    existing = _existing(conn, snapshot.account_id, runtime_profile_id, policy.risk_policy_version)
    semantic_values = {
        "risk_policy_version": policy.risk_policy_version,
        "total_wallet_balance": snapshot.total_wallet_balance,
        "available_balance": snapshot.available_balance,
        "exchange_total_initial_margin": snapshot.exchange_total_initial_margin,
        "reserved_risk": reserved_risk,
        "working_entry_risk": working_risk,
        "open_directional_risk": open_risk,
        "unknown_held_risk": unknown_risk,
        "portfolio_held_risk": held,
        "unreflected_pending_margin": pending_margin,
        "claimed_position_slots": claimed_slots,
        "pending_ticket_claims": pending,
        "max_concurrent_positions": policy.max_concurrent_positions,
        "new_entry_allowed": new_entry_allowed,
        "first_blocker": entry_blockers[0] if entry_blockers else None,
    }
    if projection_version_override is not None and projection_version_override <= 0:
        raise ValueError("projection_version_override must be positive")
    result = AccountBudgetCurrent(
        account_id=snapshot.account_id, runtime_profile_id=runtime_profile_id,
        risk_policy_version=policy.risk_policy_version, open_directional_risk=open_risk,
        reserved_risk=reserved_risk, working_entry_risk=working_risk,
        unknown_held_risk=unknown_risk, unreflected_pending_margin=pending_margin,
        portfolio_held_risk=held, claimed_position_slots=claimed_slots,
        pending_ticket_claims=pending, new_entry_allowed=new_entry_allowed,
        first_blocker=entry_blockers[0] if entry_blockers else None,
        projection_version=(
            projection_version_override
            if projection_version_override is not None
            else _projection_version(existing, semantic_values)
        ),
    )
    _persist(conn, result, snapshot, policy, margin_limit, limit, now_ms, existing)
    return result


def _existing(conn: sa.Connection, account_id: str, profile: str, policy: str) -> dict[str, object] | None:
    row = conn.execute(sa.text("""
      SELECT account_budget_current_id, risk_policy_version,
             total_wallet_balance, available_balance,
             exchange_total_initial_margin, reserved_risk,
             working_entry_risk, open_directional_risk, unknown_held_risk,
             portfolio_held_risk, unreflected_pending_margin,
             claimed_position_slots, pending_ticket_claims,
             max_concurrent_positions, new_entry_allowed, first_blocker,
             projection_version
      FROM brc_account_budget_current
      WHERE account_id = :account_id
        AND runtime_profile_id = :runtime_profile_id
        AND risk_policy_version = :risk_policy_version
      LIMIT 2
    """), {
        "account_id": account_id,
        "runtime_profile_id": profile,
        "risk_policy_version": policy,
    }).mappings().one_or_none()
    return dict(row) if row else None


def _persist(conn: sa.Connection, result: AccountBudgetCurrent, snapshot: FullAccountRiskSnapshot, policy: AccountRiskPolicy, margin_limit: Decimal, risk_limit: Decimal, now_ms: int, existing: dict[str, object] | None) -> None:
    margin_used = snapshot.exchange_total_initial_margin
    values = {
        "account_budget_current_id": existing["account_budget_current_id"] if existing else _stable_id("account_budget", result.account_id, result.runtime_profile_id, result.risk_policy_version),
        **result.model_dump(), "total_wallet_balance": snapshot.total_wallet_balance, "available_balance": snapshot.available_balance,
        "exchange_total_initial_margin": snapshot.exchange_total_initial_margin,
        "working_entry_risk": result.working_entry_risk,
        "unknown_held_risk": result.unknown_held_risk,
        "unreflected_pending_margin": result.unreflected_pending_margin,
        "portfolio_margin_used": margin_used + result.unreflected_pending_margin,
        "ticket_risk_limit": snapshot.total_wallet_balance * policy.planned_stop_risk_fraction,
        "portfolio_risk_limit": risk_limit, "portfolio_risk_remaining": max(_ZERO, risk_limit - result.portfolio_held_risk),
        "portfolio_margin_limit": margin_limit,
        "portfolio_margin_remaining": max(
            _ZERO, margin_limit - margin_used - result.unreflected_pending_margin
        ),
        "pending_ticket_claims": result.pending_ticket_claims,
        "max_concurrent_positions": policy.max_concurrent_positions,
        # Capacity exhaustion is a normal matched account fact, not a failed
        # reconciliation.  Only truth/safety blockers make Current mismatched.
        "reconciliation_state": "matched" if not _truth_blocked(result.first_blocker) else "mismatch", "source_snapshot_id": snapshot.source_snapshot_id,
        "source_watermark": snapshot.source_snapshot_id, "valid_until_ms": snapshot.valid_until_ms, "updated_at_ms": now_ms,
    }
    columns = tuple(values)
    if existing:
        assignments = ", ".join(
            f"{column} = :{column}"
            for column in columns
            if column != "account_budget_current_id"
        )
        conn.execute(
            sa.text(
                "UPDATE brc_account_budget_current SET " + assignments
                + " WHERE account_budget_current_id = :account_budget_current_id"
            ),
            _driver_params(values),
        )
    else:
        conn.execute(
            sa.text(
                "INSERT INTO brc_account_budget_current ("
                + ", ".join(columns)
                + ") VALUES ("
                + ", ".join(f":{column}" for column in columns)
                + ")"
            ),
            _driver_params(values),
        )


def _decimal(value: object) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value or "0"))


def _truth_blocked(first_blocker: str | None) -> bool:
    return bool(first_blocker) and first_blocker not in {
        "max_concurrent_positions_reached",
        "portfolio_risk_limit_reached",
        "portfolio_margin_limit_reached",
    }


def _driver_params(values: dict[str, object]) -> dict[str, object]:
    return {
        key: format(value, "f") if isinstance(value, Decimal) else value
        for key, value in values.items()
    }


def _stable_id(prefix: str, *parts: str) -> str:
    return f"{prefix}:{sha256('|'.join(parts).encode()).hexdigest()[:32]}"


def _projection_version(
    existing: dict[str, object] | None,
    semantic_values: dict[str, object],
) -> int:
    """Advance the CAS version only when capacity semantics actually change."""

    if existing is None:
        return 1
    if all(existing.get(key) == value for key, value in semantic_values.items()):
        return int(existing.get("projection_version") or 0)
    return int(existing.get("projection_version") or 0) + 1
