"""Immutable, idempotent persistence for one account-capacity claim."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict
import sqlalchemy as sa

from src.domain.account_capacity_claim import (
    AccountCapacityClaimPayload,
    capacity_claim_hash,
    load_capacity_claim_payload,
    reservation_idempotency_key,
)


class PersistedAccountCapacityClaim(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    payload: AccountCapacityClaimPayload
    capacity_claim_hash: str
    reservation_idempotency_key: str


class AccountCapacityClaimConflict(RuntimeError):
    """The Invocation already owns a different immutable claim."""


def insert_or_get_account_capacity_claim(
    conn: sa.Connection,
    *,
    payload: AccountCapacityClaimPayload,
) -> PersistedAccountCapacityClaim:
    claim_hash = capacity_claim_hash(payload)
    idempotency_key = reservation_idempotency_key(payload)
    existing = _claim_by_invocation_id(conn, payload.action_time_invocation_id)
    if existing is not None:
        return _verify_existing_claim(
            existing,
            claim_hash=claim_hash,
            idempotency_key=idempotency_key,
        )
    try:
        # PostgreSQL marks a transaction failed after a unique-key race.  Keep
        # the speculative insert inside a savepoint so the outer atomic
        # Claim/Ticket transaction remains usable when another worker wins.
        with conn.begin_nested():
            _insert_claim_row(
                conn,
                payload=payload,
                capacity_claim_hash=claim_hash,
                reservation_idempotency_key=idempotency_key,
            )
    except sa.exc.IntegrityError:
        existing = _claim_by_invocation_id(conn, payload.action_time_invocation_id)
        if existing is None:
            raise AccountCapacityClaimConflict(
                "account_capacity_claim_unique_conflict_without_existing_claim"
            ) from None
        return _verify_existing_claim(
            existing,
            claim_hash=claim_hash,
            idempotency_key=idempotency_key,
        )
    persisted = _claim_by_invocation_id(conn, payload.action_time_invocation_id)
    if persisted is None:
        raise AccountCapacityClaimConflict("account_capacity_claim_insert_missing")
    if persisted.payload != payload:
        drifted_fields: list[str] = []
        for field_name in set(persisted.payload.model_fields) | set(payload.model_fields):
            persisted_value = getattr(persisted.payload, field_name, object())
            requested_value = getattr(payload, field_name, object())
            if persisted_value == requested_value:
                continue
            if isinstance(persisted_value, BaseModel) and isinstance(
                requested_value, BaseModel
            ):
                drifted_fields.extend(
                    f"{field_name}.{nested_name}"
                    for nested_name in type(persisted_value).model_fields
                    if getattr(persisted_value, nested_name)
                    != getattr(requested_value, nested_name)
                )
            else:
                drifted_fields.append(field_name)
        raise AccountCapacityClaimConflict(
            "account_capacity_claim_roundtrip_mismatch:" + ",".join(drifted_fields)
        )
    if capacity_claim_hash(persisted.payload) != claim_hash:
        raise AccountCapacityClaimConflict("account_capacity_claim_hash_mismatch")
    return persisted


def _verify_existing_claim(
    existing: PersistedAccountCapacityClaim,
    *,
    claim_hash: str,
    idempotency_key: str,
) -> PersistedAccountCapacityClaim:
    if existing.reservation_idempotency_key != idempotency_key:
        raise AccountCapacityClaimConflict(
            "account_capacity_claim_invocation_identity_conflict"
        )
    if existing.capacity_claim_hash != claim_hash:
        raise AccountCapacityClaimConflict(
            "account_capacity_claim_idempotency_conflict"
        )
    return existing


def load_account_capacity_claim_by_invocation(
    conn: sa.Connection,
    *,
    action_time_invocation_id: str,
) -> PersistedAccountCapacityClaim | None:
    return _claim_by_invocation_id(conn, action_time_invocation_id)


def _claim_by_invocation_id(
    conn: sa.Connection,
    action_time_invocation_id: str,
) -> PersistedAccountCapacityClaim | None:
    rows = conn.execute(
        sa.text(
            """
            SELECT reservation.budget_reservation_id,
                   reservation.promotion_candidate_id,
                   reservation.action_time_lane_input_id,
                   reservation.ticket_id,
                   reservation.signal_event_id,
                   reservation.event_spec_id,
                   reservation.runtime_profile_id,
                   reservation.account_id,
                   reservation.strategy_group_id,
                   reservation.symbol,
                   reservation.side,
                   reservation.target_notional,
                   reservation.selected_leverage,
                   reservation.reserved_margin,
                   reservation.entry_reference_price,
                   reservation.stop_price,
                   reservation.intended_qty,
                   reservation.risk_at_stop,
                   reservation.reserved_at_ms,
                   reservation.expires_at_ms,
                   reservation.policy_version,
                   reservation.exchange_instrument_id,
                   reservation.exposure_episode_id,
                   reservation.action_time_invocation_id,
                   reservation.asset_class,
                   reservation.instrument_type,
                   reservation.settlement_asset,
                   reservation.margin_asset,
                   reservation.instrument_rule_snapshot_id,
                   reservation.instrument_rule_schema_version,
                   reservation.pricing_source_fact_snapshot_id,
                   reservation.account_source_fact_snapshot_id,
                   reservation.account_fact_schema_version,
                   reservation.primary_risk_cluster_id,
                   reservation.cluster_membership_snapshot_id,
                   reservation.capacity_claim_schema_version,
                   reservation.capacity_claim_hash,
                   reservation.reservation_idempotency_key,
                   reservation.account_risk_policy_version,
                   reservation.account_risk_policy_event_id,
                   reservation.allowed_risk_budget,
                   reservation.account_capacity_projection_version,
                   instrument.exchange_id, instrument.exchange_symbol,
                   instrument.instrument_identity_schema_version,
                   rule.price_tick, rule.quantity_step, rule.min_qty,
                   rule.min_notional, rule.contract_multiplier,
                   rule.exchange_max_leverage_for_claim_notional,
                   rule.source_fact_snapshot_id AS rule_source_fact_snapshot_id,
                   rule.valid_until_ms AS rule_valid_until_ms,
                   rule.risk_calculation_kind AS rule_risk_calculation_kind,
                   rule.semantic_hash AS rule_semantic_hash,
                   cluster.semantic_hash AS cluster_semantic_hash
            FROM brc_budget_reservations AS reservation
            JOIN brc_exchange_instruments AS instrument
              ON instrument.exchange_instrument_id = reservation.exchange_instrument_id
            JOIN brc_instrument_rule_snapshots AS rule
              ON rule.instrument_rule_snapshot_id = reservation.instrument_rule_snapshot_id
            JOIN brc_risk_cluster_membership_snapshots AS cluster
              ON cluster.cluster_membership_snapshot_id =
                 reservation.cluster_membership_snapshot_id
            WHERE reservation.action_time_invocation_id = :action_time_invocation_id
            LIMIT 2
            """
        ),
        {"action_time_invocation_id": action_time_invocation_id},
    ).mappings().all()
    if not rows:
        return None
    if len(rows) != 1:
        raise AccountCapacityClaimConflict(
            "account_capacity_claim_invocation_identity_conflict"
        )
    row = rows[0]
    rule_snapshot = {
        "instrument_rule_snapshot_id": row["instrument_rule_snapshot_id"],
        "rule_schema_version": row["instrument_rule_schema_version"],
        "price_tick": row["price_tick"],
        "quantity_step": row["quantity_step"],
        "min_qty": row["min_qty"],
        "min_notional": row["min_notional"],
        "contract_multiplier": row["contract_multiplier"],
        "exchange_max_leverage_for_claim_notional": row[
            "exchange_max_leverage_for_claim_notional"
        ],
        "source_fact_snapshot_id": row["rule_source_fact_snapshot_id"],
        "valid_until_ms": row["rule_valid_until_ms"],
    }
    if str(row["capacity_claim_schema_version"]) == "v2":
        rule_snapshot.update({
            "risk_calculation_kind": row["rule_risk_calculation_kind"],
            "semantic_hash": row["rule_semantic_hash"],
        })
    payload = load_capacity_claim_payload({
        "capacity_claim_schema_version": str(row["capacity_claim_schema_version"]),
        "reservation_id": str(row["budget_reservation_id"]),
        "ticket_id": str(row["ticket_id"]),
        "exposure_episode_id": str(row["exposure_episode_id"]),
        "action_time_invocation_id": str(row["action_time_invocation_id"]),
        "action_time_lane_input_id": str(row["action_time_lane_input_id"]),
        "promotion_candidate_id": str(row["promotion_candidate_id"]),
        "signal_event_id": str(row["signal_event_id"]),
        "event_spec_id": str(row["event_spec_id"]),
        "account_id": str(row["account_id"]),
        "runtime_profile_id": str(row["runtime_profile_id"]),
        "strategy_group_id": str(row["strategy_group_id"]),
        "symbol": str(row["symbol"]),
        "side": str(row["side"]),
        "instrument": {
            "exchange_instrument_id": row["exchange_instrument_id"],
            "exchange_id": row["exchange_id"],
            "exchange_symbol": row["exchange_symbol"],
            "asset_class": row["asset_class"],
            "instrument_type": row["instrument_type"],
            "settlement_asset": row["settlement_asset"],
            "margin_asset": row["margin_asset"],
            "instrument_identity_schema_version": row[
                "instrument_identity_schema_version"
            ],
        },
        "rule_snapshot": rule_snapshot,
        "cluster_snapshot": {
            "cluster_membership_snapshot_id": row[
                "cluster_membership_snapshot_id"
            ],
            "primary_risk_cluster_id": row["primary_risk_cluster_id"],
            "semantic_hash": row["cluster_semantic_hash"],
        },
        "pricing_source_fact_snapshot_id": str(row["pricing_source_fact_snapshot_id"]),
        "account_source_fact_snapshot_id": str(row["account_source_fact_snapshot_id"]),
        "account_fact_schema_version": str(row["account_fact_schema_version"]),
        "account_risk_policy_version": str(row["account_risk_policy_version"]),
        "account_risk_policy_event_id": str(row["account_risk_policy_event_id"]),
        "owner_policy_version": str(row["policy_version"]),
        "claimed_budget_projection_version": int(
            row["account_capacity_projection_version"]
        ),
        "entry_reference_price": row["entry_reference_price"],
        "stop_price": row["stop_price"],
        "intended_qty": row["intended_qty"],
        "target_notional": row["target_notional"],
        "allowed_risk_budget": row["allowed_risk_budget"],
        "planned_stop_risk": row["risk_at_stop"],
        "reserved_margin": row["reserved_margin"],
        "selected_leverage": int(row["selected_leverage"]),
        "reserved_at_ms": int(row["reserved_at_ms"]),
        "expires_at_ms": int(row["expires_at_ms"]),
    })
    return PersistedAccountCapacityClaim(
        payload=payload,
        capacity_claim_hash=str(row["capacity_claim_hash"]),
        reservation_idempotency_key=str(row["reservation_idempotency_key"]),
    )


def _insert_claim_row(
    conn: sa.Connection,
    *,
    payload: AccountCapacityClaimPayload,
    capacity_claim_hash: str,
    reservation_idempotency_key: str,
) -> None:
    conn.execute(
        sa.text(
            """
            INSERT INTO brc_budget_reservations (
              budget_reservation_id, promotion_candidate_id,
              action_time_lane_input_id, ticket_id, signal_event_id, event_spec_id,
              runtime_profile_id, account_id, strategy_group_id, symbol, side,
              target_notional, leverage, selected_leverage, reserved_margin,
              entry_reference_price, stop_price, intended_qty, risk_at_stop,
              effective_notional, planned_stop_risk_budget, planned_stop_risk,
              risk_reservation_basis,
              reserved_at_ms, expires_at_ms, status, policy_version,
              exchange_instrument_id, exposure_episode_id, action_time_invocation_id,
              asset_class, instrument_type, settlement_asset, margin_asset,
              instrument_rule_snapshot_id, instrument_rule_schema_version,
              pricing_source_fact_snapshot_id, account_source_fact_snapshot_id,
              account_fact_schema_version, primary_risk_cluster_id,
              cluster_membership_snapshot_id, capacity_claim_schema_version,
              capacity_claim_hash, reservation_idempotency_key,
              account_risk_policy_version, account_risk_policy_event_id,
              allowed_risk_budget, margin_accounting_state,
              account_capacity_projection_version, reconciliation_state
            ) VALUES (
              :reservation_id, :promotion_candidate_id, :action_time_lane_input_id,
              :ticket_id, :signal_event_id, :event_spec_id, :runtime_profile_id,
              :account_id, :strategy_group_id, :symbol, :side,
              :target_notional, :selected_leverage, :selected_leverage,
              :reserved_margin, :entry_reference_price, :stop_price, :intended_qty,
              :planned_stop_risk, :target_notional, :allowed_risk_budget,
              :planned_stop_risk, 'entry_reference_stop_distance_v0',
              :reserved_at_ms, :expires_at_ms, 'active',
              :owner_policy_version, :exchange_instrument_id, :exposure_episode_id,
              :action_time_invocation_id, :asset_class, :instrument_type,
              :settlement_asset, :margin_asset, :instrument_rule_snapshot_id,
              :instrument_rule_schema_version, :pricing_source_fact_snapshot_id,
              :account_source_fact_snapshot_id, :account_fact_schema_version,
              :primary_risk_cluster_id, :cluster_membership_snapshot_id,
              :capacity_claim_schema_version, :capacity_claim_hash,
              :reservation_idempotency_key, :account_risk_policy_version,
              :account_risk_policy_event_id, :allowed_risk_budget,
              'reserved_unreflected', :claimed_budget_projection_version, 'matched'
            )
            """
        ),
        _driver_params({
            **payload.model_dump(mode="python", exclude={"instrument", "rule_snapshot", "cluster_snapshot"}),
            "exchange_instrument_id": payload.instrument.exchange_instrument_id,
            "asset_class": payload.instrument.asset_class,
            "instrument_type": payload.instrument.instrument_type,
            "settlement_asset": payload.instrument.settlement_asset,
            "margin_asset": payload.instrument.margin_asset,
            "instrument_rule_snapshot_id": payload.rule_snapshot.instrument_rule_snapshot_id,
            "instrument_rule_schema_version": payload.rule_snapshot.rule_schema_version,
            "primary_risk_cluster_id": payload.cluster_snapshot.primary_risk_cluster_id,
            "cluster_membership_snapshot_id": payload.cluster_snapshot.cluster_membership_snapshot_id,
            "capacity_claim_hash": capacity_claim_hash,
            "reservation_idempotency_key": reservation_idempotency_key,
        }),
    )


def _driver_params(values: dict[str, object]) -> dict[str, object]:
    return {
        key: format(value, "f") if isinstance(value, Decimal) else value
        for key, value in values.items()
    }
