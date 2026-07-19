"""Build exact-scope primary risk-cluster memberships from PG current facts."""

from __future__ import annotations

from decimal import Decimal

import sqlalchemy as sa

from src.application.action_time.instrument_risk_facts import (
    InstrumentRiskFactsError,
    load_current_instrument_rule_snapshot,
    load_exact_instrument_identity,
)
from src.domain.account_risk import RiskClusterMembership


PRIMARY_CRYPTO_USD_CLUSTER = "crypto_usd_beta"


class RuntimeScopeMembershipError(RuntimeError):
    """Fail-closed error for incomplete or ambiguous current membership scope."""


def build_runtime_scope_primary_cluster_memberships(
    conn: sa.Connection,
    *,
    runtime_profile_id: str,
    risk_policy_version: str,
    now_ms: int,
    expected_instrument_count: int | None = None,
) -> tuple[RiskClusterMembership, ...]:
    """Resolve exact active candidate identities and verify their current rules."""

    if not str(runtime_profile_id or "").strip():
        raise RuntimeScopeMembershipError("runtime_profile_id_missing")
    if not str(risk_policy_version or "").strip():
        raise RuntimeScopeMembershipError("risk_policy_version_missing")
    if now_ms <= 0:
        raise RuntimeScopeMembershipError("membership_observation_time_invalid")

    rows = tuple(
        conn.execute(
            sa.text(
                """
                SELECT DISTINCT candidate.exchange_instrument_id
                FROM brc_strategy_group_candidate_scope AS candidate
                JOIN brc_runtime_scope_bindings AS runtime
                  ON runtime.candidate_scope_id = candidate.candidate_scope_id
                 AND runtime.status = 'active'
                 AND runtime.runtime_profile_id = :runtime_profile_id
                WHERE candidate.status = 'active'
                  AND candidate.scope_state = 'live_submit_allowed'
                  AND candidate.exchange_instrument_id IS NOT NULL
                  AND trim(candidate.exchange_instrument_id) <> ''
                ORDER BY candidate.exchange_instrument_id
                """
            ),
            {"runtime_profile_id": runtime_profile_id},
        ).scalars()
    )
    instrument_ids = tuple(str(value).strip() for value in rows if str(value or "").strip())
    if not instrument_ids:
        raise RuntimeScopeMembershipError("active_runtime_scope_instrument_set_empty")
    if len(set(instrument_ids)) != len(instrument_ids):
        raise RuntimeScopeMembershipError("active_runtime_scope_instrument_set_ambiguous")
    if (
        expected_instrument_count is not None
        and len(instrument_ids) != expected_instrument_count
    ):
        raise RuntimeScopeMembershipError(
            "active_runtime_scope_instrument_count_invalid"
        )

    memberships: list[RiskClusterMembership] = []
    for instrument_id in instrument_ids:
        try:
            identity = load_exact_instrument_identity(conn, instrument_id)
            load_current_instrument_rule_snapshot(
                conn,
                exchange_instrument_id=instrument_id,
                planned_notional=Decimal("1"),
                now_ms=now_ms,
            )
        except InstrumentRiskFactsError as exc:
            raise RuntimeScopeMembershipError(str(exc)) from exc
        if (
            identity.exchange_id != "binance_usdm"
            or identity.asset_class != "crypto"
            or identity.instrument_type != "perpetual"
            or identity.settlement_asset != "USDT"
            or identity.margin_asset != "USDT"
            or identity.instrument_identity_schema_version != "v2"
        ):
            raise RuntimeScopeMembershipError("instrument_identity_schema_invalid")
        memberships.append(
            RiskClusterMembership(
                exchange_instrument_id=instrument_id,
                risk_cluster_id=PRIMARY_CRYPTO_USD_CLUSTER,
            )
        )
    return tuple(memberships)
