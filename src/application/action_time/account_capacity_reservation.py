"""Locked, account-scoped capacity reservation for one pending Ticket."""

from __future__ import annotations

from decimal import Decimal
from pydantic import BaseModel, ConfigDict
import sqlalchemy as sa

from src.application.action_time.account_risk_policy import (
    load_account_risk_policy_current_projection,
)
from src.application.action_time.instrument_risk_facts import InstrumentRiskFacts
from src.domain.account_risk import decide_account_capacity
from src.domain.execution_sizing import ExecutionSizingDecision


class AccountCapacityCandidate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    account_id: str
    runtime_profile_id: str
    instrument_facts: InstrumentRiskFacts
    per_unit_stop_risk: Decimal
    entry_reference_price: Decimal


class AccountCapacityReservationResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    allowed: bool; allocated_risk: Decimal = Decimal("0"); intended_qty: Decimal = Decimal("0")
    selected_leverage: int | None = None; reserved_margin: Decimal = Decimal("0")
    claimed_projection_version: int | None = None; first_blocker: str | None = None
    account_risk_policy_version: str | None = None
    account_risk_policy_event_id: str | None = None
    risk_cluster_id: str | None = None
    exchange_instrument_id: str | None = None
    instrument_rule_snapshot_id: str | None = None
    cluster_membership_snapshot_id: str | None = None


def reserve_account_capacity_for_candidate(conn: sa.Connection, *, candidate: AccountCapacityCandidate, expected_source_snapshot_id: str, expected_projection_version: int, now_ms: int) -> AccountCapacityReservationResult:
    identity = candidate.instrument_facts.identity
    rule = candidate.instrument_facts.rule_snapshot
    cluster = candidate.instrument_facts.cluster_snapshot
    budget_table = sa.Table("brc_account_budget_current", sa.MetaData(), autoload_with=conn)
    budget = conn.execute(sa.select(budget_table).where(budget_table.c.account_id == candidate.account_id).where(budget_table.c.runtime_profile_id == candidate.runtime_profile_id).with_for_update()).mappings().one_or_none()
    if not budget: return _blocked("account_budget_current_missing")
    if str(budget["source_snapshot_id"]) != expected_source_snapshot_id: return _blocked("account_budget_source_snapshot_changed")
    if int(budget["projection_version"]) != expected_projection_version: return _blocked("account_budget_projection_version_changed")
    if int(budget["valid_until_ms"]) <= now_ms: return _blocked("account_budget_current_stale")
    if not bool(budget["new_entry_allowed"]): return _blocked(str(budget["first_blocker"] or "account_budget_new_entry_not_allowed"))
    policy_current = load_account_risk_policy_current_projection(
        conn,
        account_id=candidate.account_id,
        runtime_profile_id=candidate.runtime_profile_id,
    )
    if policy_current is None or policy_current.policy.risk_policy_version != str(budget["risk_policy_version"]): return _blocked("account_risk_policy_missing_or_changed")
    policy = policy_current.policy
    if not policy_current.source_event_id:
        return _blocked("account_risk_policy_event_missing")
    if policy.activation_state != "active": return _blocked("account_risk_policy_not_active")
    facts_blocker = _validate_instrument_facts_current(
        conn,
        facts=candidate.instrument_facts,
        risk_policy_version=policy.risk_policy_version,
        now_ms=now_ms,
    )
    if facts_blocker:
        return _blocked(facts_blocker)
    if _instrument_claimed(conn, candidate.account_id, identity.exchange_instrument_id): return _blocked("account_instrument_already_claimed")
    decision = decide_account_capacity(wallet_balance=_d(budget["total_wallet_balance"]), available_balance=_d(budget["available_balance"]), exchange_initial_margin=_d(budget["exchange_total_initial_margin"]), unreflected_pending_margin=_d(budget["unreflected_pending_margin"]), existing_portfolio_held_risk=_d(budget["portfolio_held_risk"]), existing_cluster_held_risk=_cluster_held_risk(conn, candidate.account_id, policy.risk_policy_version, cluster.primary_risk_cluster_id, fallback=_d(budget["portfolio_held_risk"])), claimed_position_slots=int(budget["claimed_position_slots"]), instrument_already_claimed=False, per_unit_stop_risk=candidate.per_unit_stop_risk, entry_reference_price=candidate.entry_reference_price, min_qty=rule.min_qty, qty_step=rule.quantity_step, min_notional=rule.min_notional, exchange_max_leverage=rule.exchange_max_leverage_for_claim_notional, policy=policy)
    if decision.blockers: return _blocked(decision.blockers[0])
    claimed_version = expected_projection_version + 1
    claimed = conn.execute(budget_table.update().where(budget_table.c.account_budget_current_id == budget["account_budget_current_id"]).where(budget_table.c.projection_version == expected_projection_version).values(projection_version=claimed_version))
    if int(claimed.rowcount or 0) != 1: return _blocked("account_budget_projection_version_changed")
    return AccountCapacityReservationResult(allowed=True, allocated_risk=decision.allowed_risk, intended_qty=decision.intended_qty, selected_leverage=decision.selected_leverage, reserved_margin=decision.reserved_margin, claimed_projection_version=claimed_version, account_risk_policy_version=policy.risk_policy_version, account_risk_policy_event_id=policy_current.source_event_id, risk_cluster_id=cluster.primary_risk_cluster_id, exchange_instrument_id=identity.exchange_instrument_id, instrument_rule_snapshot_id=rule.instrument_rule_snapshot_id, cluster_membership_snapshot_id=cluster.cluster_membership_snapshot_id)


def _validate_instrument_facts_current(
    conn: sa.Connection,
    *,
    facts: InstrumentRiskFacts,
    risk_policy_version: str,
    now_ms: int,
) -> str | None:
    identity = facts.identity
    rule = facts.rule_snapshot
    cluster = facts.cluster_snapshot
    if rule.valid_until_ms <= now_ms:
        return "instrument_rule_snapshot_stale"
    rule_rows = conn.execute(
        sa.text(
            """
            SELECT instrument_rule_snapshot_id
            FROM brc_instrument_rule_snapshots
            WHERE instrument_rule_snapshot_id = :instrument_rule_snapshot_id
              AND exchange_instrument_id = :exchange_instrument_id
              AND status = 'current'
            LIMIT 2
            """
        ),
        {
            "instrument_rule_snapshot_id": rule.instrument_rule_snapshot_id,
            "exchange_instrument_id": identity.exchange_instrument_id,
        },
    ).all()
    if len(rule_rows) != 1:
        return "instrument_rule_snapshot_missing_or_changed"
    cluster_rows = conn.execute(
        sa.text(
            """
            SELECT membership.risk_cluster_membership_id
            FROM brc_risk_cluster_membership_snapshots AS snapshot
            JOIN brc_risk_cluster_memberships AS membership
              ON membership.cluster_membership_snapshot_id =
                 snapshot.cluster_membership_snapshot_id
             AND membership.membership_role = 'primary'
             AND membership.status = 'active'
            WHERE snapshot.cluster_membership_snapshot_id =
                  :cluster_membership_snapshot_id
              AND snapshot.risk_policy_version = :risk_policy_version
              AND snapshot.primary_risk_cluster_id = :primary_risk_cluster_id
              AND snapshot.status = 'current'
              AND membership.risk_policy_version = :risk_policy_version
              AND membership.exchange_instrument_id = :exchange_instrument_id
              AND membership.risk_cluster_id = :primary_risk_cluster_id
            LIMIT 2
            """
        ),
        {
            "cluster_membership_snapshot_id": cluster.cluster_membership_snapshot_id,
            "risk_policy_version": risk_policy_version,
            "primary_risk_cluster_id": cluster.primary_risk_cluster_id,
            "exchange_instrument_id": identity.exchange_instrument_id,
        },
    ).all()
    if len(cluster_rows) != 1:
        return "risk_cluster_membership_missing_or_changed"
    return None
def _d(value: object) -> Decimal: return value if isinstance(value, Decimal) else Decimal(str(value))
def _blocked(blocker: str) -> AccountCapacityReservationResult: return AccountCapacityReservationResult(allowed=False, first_blocker=blocker)

def apply_account_capacity_to_sizing(base: ExecutionSizingDecision, capacity: AccountCapacityReservationResult) -> ExecutionSizingDecision:
    """Narrow an existing sizing decision; account capacity can never widen it."""
    if not capacity.allowed or capacity.selected_leverage is None:
        raise ValueError("account capacity must be allowed before sizing adaptation")
    if capacity.intended_qty > base.intended_qty or capacity.allocated_risk > base.planned_stop_risk:
        raise ValueError("account capacity must not expand existing ticket sizing")
    actual_stop_risk = (
        abs(base.entry_reference_price - base.protective_stop_price)
        * capacity.intended_qty
    )
    if actual_stop_risk <= 0 or actual_stop_risk > capacity.allocated_risk:
        raise ValueError("account capacity stop risk must fit the allocated ceiling")
    return base.model_copy(update={
        "intended_qty": capacity.intended_qty,
        "effective_notional": capacity.intended_qty * base.entry_reference_price,
        "selected_leverage": capacity.selected_leverage,
        "reserved_margin": capacity.reserved_margin,
        "planned_stop_risk_budget": capacity.allocated_risk,
        "planned_stop_risk": actual_stop_risk,
        "risk_reservation_basis": base.risk_reservation_basis,
    })

def _instrument_claimed(conn: sa.Connection, account_id: str, instrument: str) -> bool:
    if sa.inspect(conn).has_table("brc_account_exposure_current"):
        exposures = sa.Table(
            "brc_account_exposure_current", sa.MetaData(), autoload_with=conn
        )
        exposure_claim = conn.execute(
            sa.select(exposures.c.account_id)
            .where(exposures.c.account_id == account_id)
            .where(exposures.c.exchange_instrument_id == instrument)
            .where(exposures.c.position_slot_claimed.is_(True))
            .limit(1)
        ).first()
        if exposure_claim is not None:
            return True
    if not sa.inspect(conn).has_table("brc_budget_reservations"):
        return False
    reservations = sa.Table(
        "brc_budget_reservations", sa.MetaData(), autoload_with=conn
    )
    if "exchange_instrument_id" not in reservations.c:
        return False
    return conn.execute(
        sa.select(reservations.c.budget_reservation_id)
        .where(reservations.c.account_id == account_id)
        .where(reservations.c.exchange_instrument_id == instrument)
        .where(reservations.c.status.in_(("active", "consumed")))
        .limit(1)
    ).first() is not None

def _cluster_held_risk(conn: sa.Connection, account_id: str, version: str, cluster: str, *, fallback: Decimal) -> Decimal:
    if not sa.inspect(conn).has_table("brc_account_exposure_current"): return fallback
    exposures = sa.Table("brc_account_exposure_current", sa.MetaData(), autoload_with=conn); memberships = sa.Table("brc_risk_cluster_memberships", sa.MetaData(), autoload_with=conn)
    exposure_query = (
        sa.select(exposures)
        .join(
            memberships,
            memberships.c.exchange_instrument_id == exposures.c.exchange_instrument_id,
        )
        .where(exposures.c.account_id == account_id)
        .where(memberships.c.risk_policy_version == version)
        .where(memberships.c.risk_cluster_id == cluster)
        .where(memberships.c.membership_role == "primary")
        .where(memberships.c.status == "active")
    )
    exposure_rows = [dict(row) for row in conn.execute(exposure_query).mappings()]
    exposure_held = sum(
        (_d(row.get("held_risk")) for row in exposure_rows), Decimal("0")
    )
    consumed_tickets_represented_by_exposure = {
        str(row.get("owner_ticket_id") or "")
        for row in exposure_rows
        if (
            str(row.get("owner_ticket_id") or "")
            and _exposure_still_holds_capacity(row)
        )
    }
    if not sa.inspect(conn).has_table("brc_budget_reservations"):
        return exposure_held
    reservations = sa.Table("brc_budget_reservations", sa.MetaData(), autoload_with=conn)
    required_columns = {"account_risk_policy_version", "risk_cluster_id", "risk_at_stop", "status"}
    if not required_columns.issubset(reservations.c.keys()):
        return exposure_held
    reservation_query = (
        sa.select(reservations.c.risk_at_stop)
        .where(reservations.c.account_id == account_id)
        .where(reservations.c.account_risk_policy_version == version)
        .where(reservations.c.risk_cluster_id == cluster)
    )
    if consumed_tickets_represented_by_exposure:
        reservation_query = reservation_query.where(
            sa.or_(
                reservations.c.status == "active",
                sa.and_(
                    reservations.c.status == "consumed",
                    ~reservations.c.ticket_id.in_(
                        tuple(consumed_tickets_represented_by_exposure)
                    ),
                ),
            )
        )
    else:
        reservation_query = reservation_query.where(
            reservations.c.status.in_(("active", "consumed"))
        )
    reservation_held = sum(
        (
            _d(value)
            for value in conn.execute(reservation_query).scalars()
        ),
        Decimal("0"),
    )
    return exposure_held + reservation_held


def _exposure_still_holds_capacity(row: dict[str, object]) -> bool:
    """A flat/closed projection cannot suppress its still-consumed reservation."""

    return str(row.get("exposure_state") or "").strip() not in {"flat", "closed"}
