"""Readonly current-state evidence for the existing operational Entry promotion.

This projection grants no authority and writes no rows. Owner Resume remains
the sole policy-changing operation; historical bootstrap batches are not inputs.
"""

from __future__ import annotations

import json
from hashlib import sha256

import sqlalchemy as sa
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncConnection

from src.trading_kernel.domain.owner_policy import OwnerPolicyScope
from src.trading_kernel.infrastructure.pg_models import (
    owner_policy_current,
    runtime_capabilities_current,
    runtime_profiles,
    schema_metadata,
    strategy_entry_controls_current,
)


class EntryRestorationState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ready: bool
    owner_resume_authorized: bool
    account_id: str
    member_ids: tuple[str, ...]
    basis_digest: str
    valid_until_ms: int


async def read_entry_restoration_state(
    connection: AsyncConnection, *, now_ms: int,
) -> EntryRestorationState:
    """Read bounded current pointers, exact member certifications and Owner proof."""
    identity = {str(key): str(value) for key, value in (await connection.execute(sa.select(
        schema_metadata.c.metadata_key, schema_metadata.c.metadata_value,
    ).where(schema_metadata.c.metadata_key.in_(
        ("runtime_commit", "schema_revision", "seed_identity"),
    )))).all()}
    policy = (await connection.execute(sa.select(owner_policy_current))).mappings().one_or_none()
    if policy is None:
        return _unready_state()
    try:
        scope = OwnerPolicyScope.model_validate(policy["scope"])
    except ValueError:
        return _unready_state()
    profiles = (await connection.execute(sa.select(runtime_profiles).where(
        runtime_profiles.c.runtime_profile_id.in_(
            tuple({item.runtime_profile_id for item in scope.event_runtime_profiles}),
        ),
    ))).mappings().all()
    accounts = {str(row["account_id"]) for row in profiles}
    account_id = next(iter(accounts)) if len(accounts) == 1 else ""
    capability = (await connection.execute(sa.select(runtime_capabilities_current).where(
        runtime_capabilities_current.c.capability_key == "exchange_commands",
    ))).mappings().one_or_none()
    rows = (await connection.execute(sa.text("""
        SELECT p.event_spec_id,p.universe_version_id,p.semantic_digest,
               p.activation_generation,s.runtime_profile_id,s.exchange_instrument_id,
               s.universe_semantic_digest,s.lifecycle_state,
               s.warm_completed_at_ms,s.warm_readiness_digest,
               cert.status AS certification_status,cert.blocker_code,
               cert.configured_leverage,cert.margin_mode,cert.position_mode,
               cert.facts_digest,cert.product_rules_digest,
               cert.observed_at_ms,cert.valid_until_ms
          FROM brc_strategy_universe_current p
          JOIN brc_strategy_universe_versions v
            ON v.universe_version_id=p.universe_version_id
           AND v.lifecycle_state='active' AND p.lifecycle_state='active'
          JOIN brc_strategy_universe_members m
            ON m.universe_version_id=p.universe_version_id
          LEFT JOIN brc_runtime_scopes_current s
            ON s.universe_version_id=p.universe_version_id
           AND s.exchange_instrument_id=m.exchange_instrument_id
          LEFT JOIN brc_instrument_certification_current cert
            ON cert.runtime_profile_id=s.runtime_profile_id
           AND cert.exchange_instrument_id=s.exchange_instrument_id
         ORDER BY p.event_spec_id,m.exchange_instrument_id
         LIMIT 1025
    """))).mappings().all()
    controls = (await connection.execute(sa.select(strategy_entry_controls_current)
        .order_by(strategy_entry_controls_current.c.strategy_group_id))).mappings().all()
    authorization = (await connection.execute(sa.text("""
        SELECT a.authorization_id,a.purpose,a.authentication_strength,
               a.target_scope,a.authorized_at_ms,e.created_at_ms
          FROM brc_owner_policy_events e
          JOIN brc_owner_authorizations a
            ON a.authorization_id=e.payload->>'authorization_id'
         WHERE e.owner_policy_id=:policy AND e.policy_version=:version
           AND e.operation='owner_control_entry_resume'
           AND e.payload->>'new_entry_submit_enabled'='true'
    """), {"policy": policy["owner_policy_id"], "version": policy["policy_version"]}
    )).mappings().one_or_none()
    owner_resume = bool(
        authorization is not None
        and authorization["purpose"] == "entry_resume"
        and authorization["authentication_strength"] == "totp_step_up"
        and authorization["target_scope"] == {"owner_policy_id": policy["owner_policy_id"]}
        and 0 < authorization["authorized_at_ms"] == authorization["created_at_ms"]
        == policy["updated_at_ms"] <= now_ms
        and policy["enabled"] and policy["new_entry_submit_enabled"]
    )
    event_ids = {str(row["event_spec_id"]) for row in rows}
    expected_events = {item.event_spec_id for item in scope.event_runtime_profiles}
    members = tuple(sorted({str(row["exchange_instrument_id"]) for row in rows
                            if row["exchange_instrument_id"] is not None}))
    ready = bool(
        now_ms > 0 and 0 < len(rows) <= 1024 and members and event_ids == expected_events
        and len(profiles) == len({item.runtime_profile_id for item in scope.event_runtime_profiles})
        and account_id
        and all(row["status"] == "active" and row["venue_id"] == "binance-usdm"
                and row["environment"] == "live" and row["position_mode"] == "independent_sides"
                for row in profiles)
        and capability is not None and capability["enabled"]
        and capability["certified_commit"] == identity.get("runtime_commit")
        and capability["schema_revision"] == identity.get("schema_revision")
        and all(
            scope.runtime_profile_for(str(row["event_spec_id"])) == row["runtime_profile_id"]
            and row["lifecycle_state"] == "active"
            and row["universe_semantic_digest"] == row["semantic_digest"]
            and row["warm_completed_at_ms"] is not None
            and 0 < row["warm_completed_at_ms"] <= now_ms
            and row["warm_readiness_digest"] is not None
            and row["certification_status"] == "eligible" and row["blocker_code"] is None
            and row["configured_leverage"] == 5 and row["margin_mode"] == "cross"
            and row["position_mode"] == "independent_sides"
            and row["product_rules_digest"] is not None and row["facts_digest"] is not None
            and row["observed_at_ms"] is not None and 0 < row["observed_at_ms"] <= now_ms
            and row["valid_until_ms"] is not None and row["valid_until_ms"] > now_ms
            for row in rows
        )
    )
    basis = {"runtime_identity": identity, "policy": dict(policy),
             "controls": [dict(row) for row in controls],
             "current_members": [{key: row[key] for key in (
                 "event_spec_id", "universe_version_id", "semantic_digest",
                 "activation_generation", "runtime_profile_id", "exchange_instrument_id",
             )} for row in rows], "account_id": account_id,
             "owner_authorization_id": None if authorization is None else authorization["authorization_id"]}
    return EntryRestorationState(
        ready=ready, owner_resume_authorized=owner_resume, account_id=account_id,
        member_ids=members, basis_digest="sha256:" + sha256(json.dumps(
            basis, sort_keys=True, separators=(",", ":"), default=str,
        ).encode()).hexdigest(),
        valid_until_ms=min((int(row["valid_until_ms"]) for row in rows
                            if row["valid_until_ms"] is not None), default=0),
    )


def _unready_state() -> EntryRestorationState:
    return EntryRestorationState(
        ready=False, owner_resume_authorized=False, account_id="", member_ids=(),
        basis_digest="sha256:" + sha256(b"entry-restoration-unready").hexdigest(),
        valid_until_ms=0,
    )
