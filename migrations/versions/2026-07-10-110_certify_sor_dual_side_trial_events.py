"""Certify both SOR v2 side events as trial-grade.

Revision ID: 110
Revises: 109
Create Date: 2026-07-10
"""

from __future__ import annotations

from typing import Any, Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "110"
down_revision: Union[str, None] = "109"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

GROUP_ID = "SOR-001"
VERSION_V1 = "sgv:SOR-001:v1"
VERSION_V2 = "sgv:SOR-001:v2"
EVENTS = (
    ("event_spec:SOR-001:SOR-LONG:v1", "event_spec:SOR-001:SOR-LONG:v2"),
    ("event_spec:SOR-001:SOR-SHORT:v1", "event_spec:SOR-001:SOR-SHORT:v2"),
)
MIGRATION_AT_MS = 1783652400000


def upgrade() -> None:
    conn = op.get_bind()
    groups = _table(conn, "brc_strategy_groups")
    versions = _table(conn, "brc_strategy_group_versions")
    contracts = _table(conn, "brc_required_fact_contracts")
    events = _table(conn, "brc_strategy_side_event_specs")
    facts = _table(conn, "brc_strategy_event_required_facts")
    policies = _table(conn, "brc_execution_policies")
    bindings = _table(conn, "brc_candidate_scope_event_bindings")

    version_v1 = _one(conn, versions, versions.c.strategy_group_version_id == VERSION_V1)
    old_events = {
        old_id: _one(conn, events, events.c.event_spec_id == old_id)
        for old_id, _ in EVENTS
    }
    if not version_v1 or any(not row for row in old_events.values()):
        raise RuntimeError("both SOR v1 side events are required before migration 110")

    version_v2 = dict(version_v1)
    version_v2.update(
        {
            "strategy_group_version_id": VERSION_V2,
            "version": 2,
            "status": "draft",
            "evidence_refs": _append_unique(
                version_v2.get("evidence_refs"),
                "migration:110:SOR-dual-side-v2-event-contract",
            ),
            "created_at_ms": MIGRATION_AT_MS,
            "created_by": "migration_110",
        }
    )
    _insert_if_missing(conn, versions, "strategy_group_version_id", version_v2)

    old_contracts = _rows(
        conn,
        contracts,
        contracts.c.strategy_group_version_id == VERSION_V1,
    )
    if len(old_contracts) != 5:
        raise RuntimeError("SOR v1 requires exactly five distinct RequiredFact contracts")
    for old_contract in old_contracts:
        fact_key = str(old_contract["fact_key"])
        new_contract = dict(old_contract)
        new_contract.update(
            {
                "fact_contract_id": f"fact_contract:{VERSION_V2}:{fact_key}:finalgate",
                "strategy_group_version_id": VERSION_V2,
                "created_at_ms": MIGRATION_AT_MS,
            }
        )
        _insert_if_missing(conn, contracts, "fact_contract_id", new_contract)

    for old_id, new_id in EVENTS:
        event_v2 = dict(old_events[old_id])
        event_v2.update(
            {
                "event_spec_id": new_id,
                "strategy_group_version_id": VERSION_V2,
                "event_spec_version": "v2",
                "status": "disabled",
                "created_at_ms": MIGRATION_AT_MS,
                "created_by": "migration_110",
                "declared_signal_grade": "trial_grade_signal",
                "declared_required_execution_mode": "trial_live",
                "execution_eligibility_enabled": True,
            }
        )
        _insert_if_missing(conn, events, "event_spec_id", event_v2)

        old_facts = _rows(conn, facts, facts.c.event_spec_id == old_id)
        if len(old_facts) != 3:
            raise RuntimeError(f"{old_id} requires exactly three RequiredFacts")
        for old_fact in old_facts:
            fact_key = str(old_fact["fact_key"])
            new_fact = dict(old_fact)
            new_fact.update(
                {
                    "event_required_fact_id": f"event_fact:{new_id}:{fact_key}",
                    "event_spec_id": new_id,
                    "required_facts_version_id": f"rf:{new_id}:v2",
                    "created_at_ms": MIGRATION_AT_MS,
                }
            )
            _insert_if_missing(conn, facts, "event_required_fact_id", new_fact)

        old_policy = _one(
            conn,
            policies,
            sa.and_(
                policies.c.strategy_group_id == GROUP_ID,
                policies.c.event_spec_id == old_id,
                policies.c.status == "current",
            ),
        )
        if not old_policy:
            raise RuntimeError(f"{old_id} execution policy is required")
        new_policy = dict(old_policy)
        new_policy.update(
            {
                "execution_policy_id": f"exec_policy:{new_id}",
                "execution_policy_version": "exec-v2",
                "event_spec_id": new_id,
                "created_at_ms": MIGRATION_AT_MS,
                "created_by": "migration_110",
            }
        )
        _insert_if_missing(conn, policies, "execution_policy_id", new_policy)

        old_bindings = _rows(
            conn,
            bindings,
            sa.and_(
                bindings.c.strategy_group_id == GROUP_ID,
                bindings.c.event_spec_id == old_id,
                bindings.c.status == "active",
            ),
        )
        if len(old_bindings) != 4:
            raise RuntimeError(f"{old_id} requires exactly four active bindings")
        for old_binding in old_bindings:
            new_binding = dict(old_binding)
            new_binding.update(
                {
                    "binding_id": f"binding:{old_binding['candidate_scope_id']}:{new_id}",
                    "event_spec_id": new_id,
                    "status": "paused",
                    "valid_from_ms": MIGRATION_AT_MS,
                    "valid_until_ms": None,
                    "created_at_ms": MIGRATION_AT_MS,
                }
            )
            _insert_if_missing(conn, bindings, "binding_id", new_binding)

    old_ids = [old_id for old_id, _ in EVENTS]
    new_ids = [new_id for _, new_id in EVENTS]
    conn.execute(
        versions.update()
        .where(versions.c.strategy_group_version_id == VERSION_V1)
        .values(status="superseded")
    )
    conn.execute(events.update().where(events.c.event_spec_id.in_(old_ids)).values(status="retired"))
    conn.execute(
        bindings.update()
        .where(
            sa.and_(
                bindings.c.strategy_group_id == GROUP_ID,
                bindings.c.event_spec_id.in_(old_ids),
                bindings.c.status == "active",
            )
        )
        .values(status="revoked", valid_until_ms=MIGRATION_AT_MS)
    )
    conn.execute(
        versions.update()
        .where(versions.c.strategy_group_version_id == VERSION_V2)
        .values(status="current")
    )
    conn.execute(events.update().where(events.c.event_spec_id.in_(new_ids)).values(status="current"))
    conn.execute(
        bindings.update()
        .where(
            sa.and_(
                bindings.c.strategy_group_id == GROUP_ID,
                bindings.c.event_spec_id.in_(new_ids),
                bindings.c.status == "paused",
            )
        )
        .values(status="active")
    )
    conn.execute(
        groups.update()
        .where(groups.c.strategy_group_id == GROUP_ID)
        .values(current_version_id=VERSION_V2, updated_at_ms=MIGRATION_AT_MS)
    )


def downgrade() -> None:
    conn = op.get_bind()
    old_ids = [old_id for old_id, _ in EVENTS]
    new_ids = [new_id for _, new_id in EVENTS]
    signals = _table(conn, "brc_live_signal_events")
    if conn.execute(
        sa.select(sa.func.count()).select_from(signals).where(signals.c.event_spec_id.in_(new_ids))
    ).scalar_one():
        raise RuntimeError("cannot downgrade migration 110 while SOR v2 signals exist")

    groups = _table(conn, "brc_strategy_groups")
    versions = _table(conn, "brc_strategy_group_versions")
    contracts = _table(conn, "brc_required_fact_contracts")
    events = _table(conn, "brc_strategy_side_event_specs")
    facts = _table(conn, "brc_strategy_event_required_facts")
    policies = _table(conn, "brc_execution_policies")
    bindings = _table(conn, "brc_candidate_scope_event_bindings")

    conn.execute(bindings.delete().where(bindings.c.event_spec_id.in_(new_ids)))
    conn.execute(facts.delete().where(facts.c.event_spec_id.in_(new_ids)))
    conn.execute(policies.delete().where(policies.c.event_spec_id.in_(new_ids)))
    conn.execute(events.delete().where(events.c.event_spec_id.in_(new_ids)))
    conn.execute(contracts.delete().where(contracts.c.strategy_group_version_id == VERSION_V2))
    conn.execute(versions.delete().where(versions.c.strategy_group_version_id == VERSION_V2))
    conn.execute(versions.update().where(versions.c.strategy_group_version_id == VERSION_V1).values(status="current"))
    conn.execute(events.update().where(events.c.event_spec_id.in_(old_ids)).values(status="current"))
    conn.execute(
        bindings.update()
        .where(sa.and_(bindings.c.strategy_group_id == GROUP_ID, bindings.c.event_spec_id.in_(old_ids)))
        .values(status="active", valid_until_ms=None)
    )
    conn.execute(
        groups.update().where(groups.c.strategy_group_id == GROUP_ID).values(
            current_version_id=VERSION_V1,
            updated_at_ms=MIGRATION_AT_MS,
        )
    )


def _table(conn: sa.Connection, table_name: str) -> sa.Table:
    return sa.Table(table_name, sa.MetaData(), autoload_with=conn)


def _one(conn: sa.Connection, table: sa.Table, condition: sa.ColumnElement[bool]) -> dict[str, Any]:
    row = conn.execute(sa.select(table).where(condition).limit(1)).mappings().first()
    return dict(row) if row else {}


def _rows(conn: sa.Connection, table: sa.Table, condition: sa.ColumnElement[bool]) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(sa.select(table).where(condition)).mappings()]


def _insert_if_missing(conn: sa.Connection, table: sa.Table, pk_name: str, row: dict[str, Any]) -> None:
    pk = table.c[pk_name]
    if conn.execute(sa.select(pk).where(pk == row[pk_name]).limit(1)).scalar_one_or_none() is None:
        conn.execute(table.insert().values(**row))


def _append_unique(value: Any, item: str) -> list[str]:
    rows = list(value) if isinstance(value, list) else []
    if item not in rows:
        rows.append(item)
    return rows
