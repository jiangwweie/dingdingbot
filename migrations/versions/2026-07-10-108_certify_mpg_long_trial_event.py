"""Certify MPG-LONG v2 as a trial-grade event.

Revision ID: 108
Revises: 107
Create Date: 2026-07-10
"""

from __future__ import annotations

import json
from typing import Any, Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "108"
down_revision: Union[str, None] = "107"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


MPG_GROUP_ID = "MPG-001"
MPG_V1 = "sgv:MPG-001:v1"
MPG_V2 = "sgv:MPG-001:v2"
EVENT_V1 = "event_spec:MPG-001:MPG-LONG:v1"
EVENT_V2 = "event_spec:MPG-001:MPG-LONG:v2"
MIGRATION_AT_MS = 1783645200000


def upgrade() -> None:
    conn = op.get_bind()
    groups = _table(conn, "brc_strategy_groups")
    versions = _table(conn, "brc_strategy_group_versions")
    contracts = _table(conn, "brc_required_fact_contracts")
    events = _table(conn, "brc_strategy_side_event_specs")
    facts = _table(conn, "brc_strategy_event_required_facts")
    policies = _table(conn, "brc_execution_policies")
    bindings = _table(conn, "brc_candidate_scope_event_bindings")

    version_v1 = _one(conn, versions, versions.c.strategy_group_version_id == MPG_V1)
    event_v1 = _one(conn, events, events.c.event_spec_id == EVENT_V1)
    if not version_v1 or not event_v1:
        raise RuntimeError("MPG-LONG v1 authority rows are required before migration 108")

    version_v2 = dict(version_v1)
    version_v2.update(
        {
            "strategy_group_version_id": MPG_V2,
            "version": 2,
            "status": "draft",
            "evidence_refs": _append_unique(
                version_v2.get("evidence_refs"),
                "migration:108:MPG-LONG-v2-comparative-strength-contract",
            ),
            "created_at_ms": MIGRATION_AT_MS,
            "created_by": "migration_108",
        }
    )
    _insert_if_missing(conn, versions, "strategy_group_version_id", version_v2)

    old_contracts = _rows(
        conn,
        contracts,
        contracts.c.strategy_group_version_id == MPG_V1,
    )
    if not old_contracts:
        raise RuntimeError("MPG v1 RequiredFact contracts are required before migration 108")
    for old_contract in old_contracts:
        fact_key = str(old_contract["fact_key"])
        new_contract = dict(old_contract)
        payload = _json_dict(new_contract.get("definition_payload"))
        if fact_key == "leader_strength_confirmed":
            payload["comparative_strength"] = {
                "timeframe": "1h",
                "lookback_bars": 8,
                "max_rank": 1,
                "require_positive_return": True,
            }
        new_contract.update(
            {
                "fact_contract_id": f"fact_contract:{MPG_V2}:{fact_key}:finalgate",
                "strategy_group_version_id": MPG_V2,
                "definition_payload": payload,
                "created_at_ms": MIGRATION_AT_MS,
            }
        )
        _insert_if_missing(conn, contracts, "fact_contract_id", new_contract)

    event_v2 = dict(event_v1)
    event_v2.update(
        {
            "event_spec_id": EVENT_V2,
            "strategy_group_version_id": MPG_V2,
            "event_spec_version": "v2",
            "status": "disabled",
            "created_at_ms": MIGRATION_AT_MS,
            "created_by": "migration_108",
            "declared_signal_grade": "trial_grade_signal",
            "declared_required_execution_mode": "trial_live",
            "execution_eligibility_enabled": True,
        }
    )
    _insert_if_missing(conn, events, "event_spec_id", event_v2)

    old_facts = _rows(conn, facts, facts.c.event_spec_id == EVENT_V1)
    if len(old_facts) != 3:
        raise RuntimeError("MPG-LONG v1 requires exactly three RequiredFacts")
    for old_fact in old_facts:
        fact_key = str(old_fact["fact_key"])
        new_fact = dict(old_fact)
        new_fact.update(
            {
                "event_required_fact_id": f"event_fact:{EVENT_V2}:{fact_key}",
                "event_spec_id": EVENT_V2,
                "required_facts_version_id": f"rf:{EVENT_V2}:v2",
                "created_at_ms": MIGRATION_AT_MS,
            }
        )
        _insert_if_missing(conn, facts, "event_required_fact_id", new_fact)

    old_policy = _one(
        conn,
        policies,
        sa.and_(
            policies.c.strategy_group_id == MPG_GROUP_ID,
            policies.c.event_spec_id == EVENT_V1,
            policies.c.status == "current",
        ),
    )
    if not old_policy:
        raise RuntimeError("MPG-LONG v1 execution policy is required before migration 108")
    new_policy = dict(old_policy)
    new_policy.update(
        {
            "execution_policy_id": f"exec_policy:{EVENT_V2}",
            "execution_policy_version": "exec-v2",
            "event_spec_id": EVENT_V2,
            "created_at_ms": MIGRATION_AT_MS,
            "created_by": "migration_108",
        }
    )
    _insert_if_missing(conn, policies, "execution_policy_id", new_policy)

    old_bindings = _rows(
        conn,
        bindings,
        sa.and_(
            bindings.c.strategy_group_id == MPG_GROUP_ID,
            bindings.c.event_spec_id == EVENT_V1,
            bindings.c.status == "active",
        ),
    )
    if len(old_bindings) != 4:
        raise RuntimeError("MPG-LONG v1 requires exactly four active candidate bindings")
    for old_binding in old_bindings:
        new_binding = dict(old_binding)
        new_binding.update(
            {
                "binding_id": f"binding:{old_binding['candidate_scope_id']}:{EVENT_V2}",
                "event_spec_id": EVENT_V2,
                "status": "paused",
                "valid_from_ms": MIGRATION_AT_MS,
                "valid_until_ms": None,
                "created_at_ms": MIGRATION_AT_MS,
            }
        )
        _insert_if_missing(conn, bindings, "binding_id", new_binding)

    conn.execute(
        versions.update()
        .where(versions.c.strategy_group_version_id == MPG_V1)
        .values(status="superseded")
    )
    conn.execute(
        events.update().where(events.c.event_spec_id == EVENT_V1).values(status="retired")
    )
    conn.execute(
        bindings.update()
        .where(
            sa.and_(
                bindings.c.strategy_group_id == MPG_GROUP_ID,
                bindings.c.event_spec_id == EVENT_V1,
                bindings.c.status == "active",
            )
        )
        .values(status="revoked", valid_until_ms=MIGRATION_AT_MS)
    )
    conn.execute(
        versions.update()
        .where(versions.c.strategy_group_version_id == MPG_V2)
        .values(status="current")
    )
    conn.execute(
        events.update().where(events.c.event_spec_id == EVENT_V2).values(status="current")
    )
    conn.execute(
        bindings.update()
        .where(
            sa.and_(
                bindings.c.strategy_group_id == MPG_GROUP_ID,
                bindings.c.event_spec_id == EVENT_V2,
                bindings.c.status == "paused",
            )
        )
        .values(status="active")
    )
    conn.execute(
        groups.update()
        .where(groups.c.strategy_group_id == MPG_GROUP_ID)
        .values(current_version_id=MPG_V2, updated_at_ms=MIGRATION_AT_MS)
    )


def downgrade() -> None:
    conn = op.get_bind()
    signals = _table(conn, "brc_live_signal_events")
    if conn.execute(
        sa.select(sa.func.count())
        .select_from(signals)
        .where(signals.c.event_spec_id == EVENT_V2)
    ).scalar_one():
        raise RuntimeError("cannot downgrade migration 108 while MPG-LONG v2 signals exist")

    groups = _table(conn, "brc_strategy_groups")
    versions = _table(conn, "brc_strategy_group_versions")
    contracts = _table(conn, "brc_required_fact_contracts")
    events = _table(conn, "brc_strategy_side_event_specs")
    facts = _table(conn, "brc_strategy_event_required_facts")
    policies = _table(conn, "brc_execution_policies")
    bindings = _table(conn, "brc_candidate_scope_event_bindings")

    conn.execute(bindings.delete().where(bindings.c.event_spec_id == EVENT_V2))
    conn.execute(facts.delete().where(facts.c.event_spec_id == EVENT_V2))
    conn.execute(policies.delete().where(policies.c.event_spec_id == EVENT_V2))
    conn.execute(events.delete().where(events.c.event_spec_id == EVENT_V2))
    conn.execute(
        contracts.delete().where(contracts.c.strategy_group_version_id == MPG_V2)
    )
    conn.execute(versions.delete().where(versions.c.strategy_group_version_id == MPG_V2))
    conn.execute(
        versions.update()
        .where(versions.c.strategy_group_version_id == MPG_V1)
        .values(status="current")
    )
    conn.execute(
        events.update().where(events.c.event_spec_id == EVENT_V1).values(status="current")
    )
    conn.execute(
        bindings.update()
        .where(
            sa.and_(
                bindings.c.strategy_group_id == MPG_GROUP_ID,
                bindings.c.event_spec_id == EVENT_V1,
            )
        )
        .values(status="active", valid_until_ms=None)
    )
    conn.execute(
        groups.update()
        .where(groups.c.strategy_group_id == MPG_GROUP_ID)
        .values(current_version_id=MPG_V1, updated_at_ms=MIGRATION_AT_MS)
    )


def _table(conn: sa.Connection, table_name: str) -> sa.Table:
    return sa.Table(table_name, sa.MetaData(), autoload_with=conn)


def _one(
    conn: sa.Connection,
    table: sa.Table,
    condition: sa.ColumnElement[bool],
) -> dict[str, Any]:
    row = conn.execute(sa.select(table).where(condition).limit(1)).mappings().first()
    return dict(row) if row else {}


def _rows(
    conn: sa.Connection,
    table: sa.Table,
    condition: sa.ColumnElement[bool],
) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(sa.select(table).where(condition)).mappings()]


def _insert_if_missing(
    conn: sa.Connection,
    table: sa.Table,
    pk_name: str,
    row: dict[str, Any],
) -> None:
    pk = table.c[pk_name]
    if conn.execute(
        sa.select(pk).where(pk == row[pk_name]).limit(1)
    ).scalar_one_or_none() is None:
        conn.execute(table.insert().values(**row))


def _append_unique(value: Any, item: str) -> list[str]:
    rows = list(value) if isinstance(value, list) else []
    if item not in rows:
        rows.append(item)
    return rows


def _json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}
