"""Bounded PG loader for exact, versioned instrument risk facts."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict
import sqlalchemy as sa

from src.domain.instrument_risk_identity import (
    InstrumentRiskIdentity,
    InstrumentRuleSnapshotRef,
    RiskClusterMembershipSnapshotRef,
)


class InstrumentRiskFacts(BaseModel):
    """Immutable facts consumed by one account-capacity decision."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    identity: InstrumentRiskIdentity
    rule_snapshot: InstrumentRuleSnapshotRef
    cluster_snapshot: RiskClusterMembershipSnapshotRef


class InstrumentRiskFactsError(RuntimeError):
    """Fail-closed classification for missing, ambiguous or stale facts."""


def load_instrument_risk_facts(
    conn: sa.Connection,
    *,
    exchange_instrument_id: str,
    risk_policy_version: str,
    planned_notional: Decimal,
    now_ms: int,
) -> InstrumentRiskFacts:
    if not planned_notional.is_finite() or planned_notional <= 0:
        raise InstrumentRiskFactsError("instrument_rule_planned_notional_invalid")
    return InstrumentRiskFacts(
        identity=_load_exact_instrument_identity(conn, exchange_instrument_id),
        rule_snapshot=_load_one_current_rule_snapshot(
            conn,
            exchange_instrument_id=exchange_instrument_id,
            planned_notional=planned_notional,
            now_ms=now_ms,
        ),
        cluster_snapshot=_load_one_primary_cluster_snapshot(
            conn,
            exchange_instrument_id=exchange_instrument_id,
            risk_policy_version=risk_policy_version,
        ),
    )


def _load_exact_instrument_identity(
    conn: sa.Connection,
    exchange_instrument_id: str,
) -> InstrumentRiskIdentity:
    rows = conn.execute(
        sa.text(
            """
            SELECT exchange_instrument_id, exchange_id, exchange_symbol,
                   asset_class, instrument_type, settlement_asset, margin_asset,
                   instrument_identity_schema_version
            FROM brc_exchange_instruments
            WHERE exchange_instrument_id = :exchange_instrument_id
              AND status = 'active'
            ORDER BY exchange_instrument_id
            LIMIT 2
            """
        ),
        {"exchange_instrument_id": exchange_instrument_id},
    ).mappings().all()
    if len(rows) != 1:
        raise InstrumentRiskFactsError("instrument_identity_missing")
    try:
        return InstrumentRiskIdentity.model_validate(dict(rows[0]))
    except (TypeError, ValueError) as exc:
        raise InstrumentRiskFactsError("instrument_identity_schema_invalid") from exc


def _load_one_current_rule_snapshot(
    conn: sa.Connection,
    *,
    exchange_instrument_id: str,
    planned_notional: Decimal,
    now_ms: int,
) -> InstrumentRuleSnapshotRef:
    del planned_notional  # V0 stores the already selected notional-specific leverage fact.
    rows = conn.execute(
        sa.text(
            """
            SELECT instrument_rule_snapshot_id, rule_schema_version, price_tick,
                   quantity_step, min_qty, min_notional, contract_multiplier,
                   exchange_max_leverage_for_claim_notional,
                   source_fact_snapshot_id, valid_until_ms
            FROM brc_instrument_rule_snapshots
            WHERE exchange_instrument_id = :exchange_instrument_id
              AND status = 'current'
            ORDER BY instrument_rule_snapshot_id
            LIMIT 2
            """
        ),
        {"exchange_instrument_id": exchange_instrument_id},
    ).mappings().all()
    if len(rows) != 1:
        raise InstrumentRiskFactsError("instrument_rule_snapshot_invalid")
    if int(rows[0]["valid_until_ms"] or 0) <= now_ms:
        raise InstrumentRiskFactsError("instrument_rule_snapshot_stale")
    try:
        return InstrumentRuleSnapshotRef.model_validate(dict(rows[0]))
    except (TypeError, ValueError) as exc:
        raise InstrumentRiskFactsError("instrument_rule_snapshot_schema_invalid") from exc


def _load_one_primary_cluster_snapshot(
    conn: sa.Connection,
    *,
    exchange_instrument_id: str,
    risk_policy_version: str,
) -> RiskClusterMembershipSnapshotRef:
    rows = conn.execute(
        sa.text(
            """
            SELECT snapshot.cluster_membership_snapshot_id,
                   snapshot.primary_risk_cluster_id,
                   snapshot.semantic_hash,
                   membership.risk_cluster_id AS member_primary_risk_cluster_id
            FROM brc_risk_cluster_membership_snapshots AS snapshot
            JOIN brc_risk_cluster_memberships AS membership
              ON membership.cluster_membership_snapshot_id =
                 snapshot.cluster_membership_snapshot_id
             AND membership.membership_role = 'primary'
             AND membership.status = 'active'
            WHERE snapshot.risk_policy_version = :risk_policy_version
              AND snapshot.status = 'current'
              AND membership.risk_policy_version = :risk_policy_version
              AND membership.exchange_instrument_id = :exchange_instrument_id
            ORDER BY snapshot.cluster_membership_snapshot_id
            LIMIT 2
            """
        ),
        {
            "exchange_instrument_id": exchange_instrument_id,
            "risk_policy_version": risk_policy_version,
        },
    ).mappings().all()
    if len(rows) != 1:
        raise InstrumentRiskFactsError(
            "primary_risk_cluster_membership_invalid"
        )
    row = dict(rows[0])
    if row.pop("member_primary_risk_cluster_id") != row["primary_risk_cluster_id"]:
        raise InstrumentRiskFactsError(
            "primary_risk_cluster_membership_invalid"
        )
    try:
        return RiskClusterMembershipSnapshotRef.model_validate(row)
    except (TypeError, ValueError) as exc:
        raise InstrumentRiskFactsError(
            "primary_risk_cluster_membership_invalid"
        ) from exc
