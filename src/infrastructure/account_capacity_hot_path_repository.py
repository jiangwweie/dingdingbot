"""Bounded explicit-column reads for account-capacity hot paths."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Generic, TypeVar

import sqlalchemy as sa


T = TypeVar("T")


@dataclass(frozen=True)
class AccountExposureCurrentRecord:
    account_exposure_current_id: str
    owner_ticket_id: str | None
    exposure_state: str
    actual_directional_risk: Decimal
    held_risk: Decimal
    unreflected_pending_margin: Decimal
    reconciliation_state: str
    position_slot_claimed: bool
    first_blocker: str | None


@dataclass(frozen=True)
class AccountCapacityClaimRecord:
    budget_reservation_id: str
    ticket_id: str | None
    exchange_instrument_id: str
    exposure_episode_id: str
    logical_symbol: str
    exchange_symbol: str
    asset_class: str
    instrument_type: str
    primary_risk_cluster_id: str
    cluster_membership_snapshot_id: str
    account_source_fact_snapshot_id: str
    account_fact_schema_version: str
    status: str
    risk_at_stop: Decimal
    reserved_margin: Decimal
    margin_accounting_state: str
    contract_multiplier: Decimal


@dataclass(frozen=True)
class AccountCommandEvidenceRecord:
    ticket_id: str
    exchange_instrument_id: str
    exchange_order_id: str | None
    client_order_id: str | None
    parent_order_id: str | None
    order_role: str
    command_state: str


@dataclass(frozen=True)
class BoundedCurrentRows(Generic[T]):
    rows: tuple[T, ...]
    overflow: bool


def load_live_exposure_rows(
    conn: sa.Connection,
    *,
    account_id: str,
    max_concurrent_positions: int,
) -> BoundedCurrentRows[AccountExposureCurrentRecord]:
    limit = _limit_plus_one(max_concurrent_positions)
    rows = conn.execute(
        sa.text(
            """
            SELECT account_exposure_current_id, owner_ticket_id, exposure_state,
                   actual_directional_risk, held_risk,
                   unreflected_pending_margin, reconciliation_state,
                   position_slot_claimed, first_blocker
            FROM brc_account_exposure_current
            WHERE account_id = :account_id
              AND (exposure_state NOT IN ('flat', 'closed')
                   OR first_blocker IS NOT NULL)
            ORDER BY account_exposure_current_id
            LIMIT :policy_limit_plus_one
            """
        ),
        {"account_id": account_id, "policy_limit_plus_one": limit},
    ).mappings().all()
    return BoundedCurrentRows(
        rows=tuple(
            AccountExposureCurrentRecord(
                account_exposure_current_id=str(row["account_exposure_current_id"]),
                owner_ticket_id=_optional_text(row["owner_ticket_id"]),
                exposure_state=str(row["exposure_state"]),
                actual_directional_risk=_decimal(row["actual_directional_risk"]),
                held_risk=_decimal(row["held_risk"]),
                unreflected_pending_margin=_decimal(
                    row["unreflected_pending_margin"]
                ),
                reconciliation_state=str(row["reconciliation_state"]),
                position_slot_claimed=bool(row["position_slot_claimed"]),
                first_blocker=_optional_text(row["first_blocker"]),
            )
            for row in rows[:max_concurrent_positions]
        ),
        overflow=len(rows) > max_concurrent_positions,
    )


def load_effective_reservation_rows(
    conn: sa.Connection,
    *,
    account_id: str,
    runtime_profile_id: str,
    max_concurrent_positions: int,
) -> BoundedCurrentRows[AccountCapacityClaimRecord]:
    limit = _limit_plus_one(max_concurrent_positions)
    rows = conn.execute(
        sa.text(
            """
            SELECT reservation.budget_reservation_id, reservation.ticket_id,
                   reservation.exchange_instrument_id,
                   reservation.exposure_episode_id, reservation.symbol,
                   instrument.exchange_symbol, reservation.asset_class,
                   reservation.instrument_type,
                   reservation.primary_risk_cluster_id,
                   reservation.cluster_membership_snapshot_id,
                   reservation.account_source_fact_snapshot_id,
                   reservation.account_fact_schema_version,
                   reservation.status, reservation.risk_at_stop,
                   reservation.reserved_margin,
                   reservation.margin_accounting_state,
                   rule.contract_multiplier
            FROM brc_budget_reservations AS reservation
            JOIN brc_exchange_instruments AS instrument
              ON instrument.exchange_instrument_id =
                 reservation.exchange_instrument_id
            JOIN brc_instrument_rule_snapshots AS rule
              ON rule.instrument_rule_snapshot_id =
                 reservation.instrument_rule_snapshot_id
            WHERE reservation.account_id = :account_id
              AND reservation.runtime_profile_id = :runtime_profile_id
              AND reservation.status IN ('active', 'consumed')
            ORDER BY reservation.budget_reservation_id
            LIMIT :policy_limit_plus_one
            """
        ),
        {
            "account_id": account_id,
            "runtime_profile_id": runtime_profile_id,
            "policy_limit_plus_one": limit,
        },
    ).mappings().all()
    return BoundedCurrentRows(
        rows=tuple(
            AccountCapacityClaimRecord(
                budget_reservation_id=str(row["budget_reservation_id"]),
                ticket_id=_optional_text(row["ticket_id"]),
                exchange_instrument_id=str(row["exchange_instrument_id"]),
                exposure_episode_id=str(row["exposure_episode_id"]),
                logical_symbol=str(row["symbol"]),
                exchange_symbol=str(row["exchange_symbol"]),
                asset_class=str(row["asset_class"]),
                instrument_type=str(row["instrument_type"]),
                primary_risk_cluster_id=str(row["primary_risk_cluster_id"]),
                cluster_membership_snapshot_id=str(
                    row["cluster_membership_snapshot_id"]
                ),
                account_source_fact_snapshot_id=str(
                    row["account_source_fact_snapshot_id"]
                ),
                account_fact_schema_version=str(row["account_fact_schema_version"]),
                status=str(row["status"]),
                risk_at_stop=_decimal(row["risk_at_stop"]),
                reserved_margin=_decimal(row["reserved_margin"]),
                margin_accounting_state=str(row["margin_accounting_state"]),
                contract_multiplier=_decimal(row["contract_multiplier"]),
            )
            for row in rows[:max_concurrent_positions]
        ),
        overflow=len(rows) > max_concurrent_positions,
    )


def load_current_command_identity_evidence(
    conn: sa.Connection,
    *,
    account_id: str,
    ticket_ids: tuple[str, ...],
) -> tuple[AccountCommandEvidenceRecord, ...]:
    normalized_ids = tuple(sorted({item for item in ticket_ids if item}))
    if not normalized_ids:
        return ()
    statement = sa.text(
        """
        SELECT c.ticket_id, c.exchange_instrument_id, c.exchange_order_id,
               c.client_order_id, c.parent_order_id, c.order_role,
               c.command_state
        FROM brc_ticket_bound_exchange_commands AS c
        WHERE c.account_id = :account_id
          AND c.ticket_id IN :current_ticket_ids
          AND c.command_state NOT IN
              ('confirmed_rejected', 'reconciled_absent')
        ORDER BY c.ticket_id, c.operation_submit_command_id
        """
    ).bindparams(sa.bindparam("current_ticket_ids", expanding=True))
    rows = conn.execute(
        statement,
        {"account_id": account_id, "current_ticket_ids": normalized_ids},
    ).mappings()
    return tuple(
        AccountCommandEvidenceRecord(
            ticket_id=str(row["ticket_id"]),
            exchange_instrument_id=str(row["exchange_instrument_id"]),
            exchange_order_id=_optional_text(row["exchange_order_id"]),
            client_order_id=_optional_text(row["client_order_id"]),
            parent_order_id=_optional_text(row["parent_order_id"]),
            order_role=str(row["order_role"]),
            command_state=str(row["command_state"]),
        )
        for row in rows
    )


def load_current_account_ticket_ids(
    conn: sa.Connection,
    *,
    account_id: str,
) -> tuple[str, ...]:
    rows = conn.execute(
        sa.text(
            """
            SELECT DISTINCT c.ticket_id
            FROM brc_ticket_bound_exchange_commands AS c
            JOIN brc_action_time_tickets AS ticket
              ON ticket.ticket_id = c.ticket_id
            WHERE c.account_id = :account_id
              AND ticket.status NOT IN
                  ('expired', 'finalgate_rejected', 'invalidated',
                   'superseded', 'closed')
            ORDER BY c.ticket_id
            """
        ),
        {"account_id": account_id},
    ).scalars()
    return tuple(str(row) for row in rows)


def _limit_plus_one(max_concurrent_positions: int) -> int:
    if max_concurrent_positions < 1:
        raise ValueError("max_concurrent_positions must be positive")
    return max_concurrent_positions + 1


def _decimal(value: object) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value or "0"))


def _optional_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None
