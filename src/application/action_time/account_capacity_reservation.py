"""Locked, account-scoped capacity reservation for one pending Ticket."""

from __future__ import annotations

from decimal import Decimal
from pydantic import BaseModel, ConfigDict
import sqlalchemy as sa

from src.application.action_time.account_risk_policy import load_account_risk_policy_current
from src.domain.account_risk import decide_account_capacity


class AccountCapacityCandidate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    account_id: str; runtime_profile_id: str; exchange_instrument_id: str; risk_cluster_id: str
    per_unit_stop_risk: Decimal; entry_reference_price: Decimal; min_qty: Decimal; qty_step: Decimal
    min_notional: Decimal; exchange_max_leverage: int


class AccountCapacityReservationResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    allowed: bool; allocated_risk: Decimal = Decimal("0"); intended_qty: Decimal = Decimal("0")
    selected_leverage: int | None = None; reserved_margin: Decimal = Decimal("0")
    claimed_projection_version: int | None = None; first_blocker: str | None = None


def reserve_account_capacity_for_candidate(conn: sa.Connection, *, candidate: AccountCapacityCandidate, expected_source_snapshot_id: str, expected_projection_version: int, now_ms: int) -> AccountCapacityReservationResult:
    budget_table = sa.Table("brc_account_budget_current", sa.MetaData(), autoload_with=conn)
    budget = conn.execute(sa.select(budget_table).where(budget_table.c.account_id == candidate.account_id).where(budget_table.c.runtime_profile_id == candidate.runtime_profile_id).with_for_update()).mappings().one_or_none()
    if not budget: return _blocked("account_budget_current_missing")
    if str(budget["source_snapshot_id"]) != expected_source_snapshot_id: return _blocked("account_budget_source_snapshot_changed")
    if int(budget["projection_version"]) != expected_projection_version: return _blocked("account_budget_projection_version_changed")
    if int(budget["valid_until_ms"]) <= now_ms: return _blocked("account_budget_current_stale")
    if not bool(budget["new_entry_allowed"]): return _blocked(str(budget["first_blocker"] or "account_budget_new_entry_not_allowed"))
    policy = load_account_risk_policy_current(conn, account_id=candidate.account_id, runtime_profile_id=candidate.runtime_profile_id)
    if policy is None or policy.risk_policy_version != str(budget["risk_policy_version"]): return _blocked("account_risk_policy_missing_or_changed")
    if _cluster(conn, policy.risk_policy_version, candidate.exchange_instrument_id) != candidate.risk_cluster_id: return _blocked("risk_cluster_membership_missing_or_changed")
    if _instrument_claimed(conn, candidate.account_id, candidate.exchange_instrument_id): return _blocked("account_instrument_already_claimed")
    decision = decide_account_capacity(wallet_balance=_d(budget["total_wallet_balance"]), available_balance=_d(budget["available_balance"]), exchange_initial_margin=_d(budget["exchange_total_initial_margin"]), unreflected_pending_margin=_d(budget["unreflected_pending_margin"]), existing_portfolio_held_risk=_d(budget["portfolio_held_risk"]), existing_cluster_held_risk=_cluster_held_risk(conn, candidate.account_id, policy.risk_policy_version, candidate.risk_cluster_id, fallback=_d(budget["portfolio_held_risk"])), claimed_position_slots=int(budget["claimed_position_slots"]), instrument_already_claimed=False, per_unit_stop_risk=candidate.per_unit_stop_risk, entry_reference_price=candidate.entry_reference_price, min_qty=candidate.min_qty, qty_step=candidate.qty_step, min_notional=candidate.min_notional, exchange_max_leverage=candidate.exchange_max_leverage, policy=policy)
    if decision.blockers: return _blocked(decision.blockers[0])
    claimed_version = expected_projection_version + 1
    claimed = conn.execute(budget_table.update().where(budget_table.c.account_budget_current_id == budget["account_budget_current_id"]).where(budget_table.c.projection_version == expected_projection_version).values(projection_version=claimed_version))
    if int(claimed.rowcount or 0) != 1: return _blocked("account_budget_projection_version_changed")
    return AccountCapacityReservationResult(allowed=True, allocated_risk=decision.allowed_risk, intended_qty=decision.intended_qty, selected_leverage=decision.selected_leverage, reserved_margin=decision.reserved_margin, claimed_projection_version=claimed_version)


def _cluster(conn: sa.Connection, version: str, instrument: str) -> str | None:
    table = sa.Table("brc_risk_cluster_memberships", sa.MetaData(), autoload_with=conn)
    return conn.execute(sa.select(table.c.risk_cluster_id).where(table.c.risk_policy_version == version).where(table.c.exchange_instrument_id == instrument)).scalar_one_or_none()
def _d(value: object) -> Decimal: return value if isinstance(value, Decimal) else Decimal(str(value))
def _blocked(blocker: str) -> AccountCapacityReservationResult: return AccountCapacityReservationResult(allowed=False, first_blocker=blocker)

def _instrument_claimed(conn: sa.Connection, account_id: str, instrument: str) -> bool:
    if not sa.inspect(conn).has_table("brc_account_exposure_current"): return False
    table = sa.Table("brc_account_exposure_current", sa.MetaData(), autoload_with=conn)
    return conn.execute(sa.select(table.c.account_id).where(table.c.account_id == account_id).where(table.c.exchange_instrument_id == instrument).where(table.c.position_slot_claimed.is_(True)).limit(1)).first() is not None

def _cluster_held_risk(conn: sa.Connection, account_id: str, version: str, cluster: str, *, fallback: Decimal) -> Decimal:
    if not sa.inspect(conn).has_table("brc_account_exposure_current"): return fallback
    exposures = sa.Table("brc_account_exposure_current", sa.MetaData(), autoload_with=conn); memberships = sa.Table("brc_risk_cluster_memberships", sa.MetaData(), autoload_with=conn)
    return sum((_d(value) for value in conn.execute(sa.select(exposures.c.held_risk).join(memberships, memberships.c.exchange_instrument_id == exposures.c.exchange_instrument_id).where(exposures.c.account_id == account_id).where(memberships.c.risk_policy_version == version).where(memberships.c.risk_cluster_id == cluster)).scalars()), Decimal("0"))
