"""Serialize effective Ticket exit-policy adoption authority.

Revision ID: 135
Revises: 134
Create Date: 2026-07-17
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "135"
down_revision: Union[str, None] = "134"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ADOPTION_TABLE = "brc_ticket_exit_policy_adoption_events"
CURRENT_TABLE = "brc_ticket_exit_policy_current"
LIFETIME_ACCEPTED_INDEX = "uq_brc_ticket_exit_policy_one_accepted_adoption"
ADOPTION_STATE_CHECK = "ck_brc_ticket_exit_policy_adoption_state"
ADOPTION_MUTATION_CHECK = "ck_brc_ticket_exit_policy_adoption_mutation_allowed"


def upgrade() -> None:
    bind = op.get_bind()
    _require_tables(bind)
    _assert_current_binding_backfill_is_unambiguous(bind)
    _drop_lifetime_accepted_index(bind)
    _extend_current_projection(bind)
    _backfill_current_projection(bind)


def downgrade() -> None:
    bind = op.get_bind()
    _require_tables(bind)
    _assert_lifetime_uniqueness_restorable(bind)
    _contract_current_projection(bind)
    _create_lifetime_accepted_index(bind)


def _require_tables(bind: sa.Connection) -> None:
    inspector = sa.inspect(bind)
    missing = [
        table_name
        for table_name in (ADOPTION_TABLE, CURRENT_TABLE)
        if not inspector.has_table(table_name)
    ]
    if missing:
        raise RuntimeError(
            "exit_policy_adoption_authority_missing:" + ",".join(missing)
        )


def _assert_current_binding_backfill_is_unambiguous(bind: sa.Connection) -> None:
    current = _table(bind, CURRENT_TABLE)
    events = _table(bind, ADOPTION_TABLE)
    for row in bind.execute(sa.select(current)).mappings():
        source = str(row.get("binding_source") or "ticket")
        event_id = str(row.get("adoption_event_id") or "").strip()
        if source == "ticket" and not event_id:
            continue
        if source != "adoption_event" or not event_id:
            raise RuntimeError("exit_policy_adoption_backfill_binding_ambiguous")
        accepted = list(
            bind.execute(
                sa.select(events.c.adoption_event_id).where(
                    events.c.ticket_id == row["ticket_id"],
                    events.c.adoption_event_id == event_id,
                    events.c.decision == "accepted",
                )
            )
        )
        revoked = bind.execute(
            sa.select(events.c.adoption_event_id).where(
                events.c.ticket_id == row["ticket_id"],
                events.c.decision == "revoked",
                events.c.supersedes_adoption_event_id == event_id,
            )
        ).first()
        if len(accepted) != 1 or revoked is not None:
            raise RuntimeError("exit_policy_adoption_backfill_binding_ambiguous")


def _drop_lifetime_accepted_index(bind: sa.Connection) -> None:
    names = {
        str(index.get("name") or "")
        for index in sa.inspect(bind).get_indexes(ADOPTION_TABLE)
    }
    if LIFETIME_ACCEPTED_INDEX in names:
        op.drop_index(LIFETIME_ACCEPTED_INDEX, table_name=ADOPTION_TABLE)


def _extend_current_projection(bind: sa.Connection) -> None:
    additions = (
        sa.Column(
            "adoption_state",
            sa.String(32),
            nullable=False,
            server_default="ticket_bound",
        ),
        sa.Column(
            "mutation_allowed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "adoption_projection_version",
            sa.BIGINT(),
            nullable=False,
            server_default="1",
        ),
    )
    existing_constraints = _constraint_names(bind, CURRENT_TABLE)
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table(CURRENT_TABLE, recreate="always") as batch:
            existing_columns = _column_names(bind, CURRENT_TABLE)
            for column in additions:
                if column.name not in existing_columns:
                    batch.add_column(column)
            if ADOPTION_STATE_CHECK not in existing_constraints:
                batch.create_check_constraint(
                    ADOPTION_STATE_CHECK,
                    "adoption_state IN ('ticket_bound', 'accepted', 'revoked')",
                )
            if ADOPTION_MUTATION_CHECK not in existing_constraints:
                batch.create_check_constraint(
                    ADOPTION_MUTATION_CHECK,
                    "(adoption_state = 'revoked' AND mutation_allowed = 0) OR "
                    "(adoption_state IN ('ticket_bound', 'accepted') AND mutation_allowed = 1)",
                )
        return
    for column in additions:
        if column.name not in _column_names(bind, CURRENT_TABLE):
            op.add_column(CURRENT_TABLE, column)
    if ADOPTION_STATE_CHECK not in existing_constraints:
        op.create_check_constraint(
            ADOPTION_STATE_CHECK,
            CURRENT_TABLE,
            "adoption_state IN ('ticket_bound', 'accepted', 'revoked')",
        )
    if ADOPTION_MUTATION_CHECK not in existing_constraints:
        op.create_check_constraint(
            ADOPTION_MUTATION_CHECK,
            CURRENT_TABLE,
            "(adoption_state = 'revoked' AND mutation_allowed = false) OR "
            "(adoption_state IN ('ticket_bound', 'accepted') AND mutation_allowed = true)",
        )


def _backfill_current_projection(bind: sa.Connection) -> None:
    current = _table(bind, CURRENT_TABLE)
    for row in bind.execute(sa.select(current)).mappings():
        source = str(row.get("binding_source") or "ticket")
        values = {
            "adoption_state": "ticket_bound",
            "mutation_allowed": True,
            "adoption_projection_version": 1,
        }
        if source == "adoption_event":
            values.update({"adoption_state": "accepted", "mutation_allowed": True})
        bind.execute(
            current.update()
            .where(current.c.ticket_id == row["ticket_id"])
            .values(**values)
        )


def _assert_lifetime_uniqueness_restorable(bind: sa.Connection) -> None:
    events = _table(bind, ADOPTION_TABLE)
    duplicate = bind.execute(
        sa.select(events.c.ticket_id)
        .where(events.c.decision == "accepted")
        .group_by(events.c.ticket_id)
        .having(sa.func.count() > 1)
        .limit(1)
    ).first()
    if duplicate is not None:
        raise RuntimeError("cannot_downgrade_multiple_accepted_adoption_history")


def _contract_current_projection(bind: sa.Connection) -> None:
    constraints = _constraint_names(bind, CURRENT_TABLE)
    columns = _column_names(bind, CURRENT_TABLE)
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table(CURRENT_TABLE, recreate="always") as batch:
            for name in (ADOPTION_MUTATION_CHECK, ADOPTION_STATE_CHECK):
                if name in constraints:
                    batch.drop_constraint(name, type_="check")
            for name in (
                "adoption_projection_version",
                "mutation_allowed",
                "adoption_state",
            ):
                if name in columns:
                    batch.drop_column(name)
        return
    for name in (ADOPTION_MUTATION_CHECK, ADOPTION_STATE_CHECK):
        if name in constraints:
            op.drop_constraint(name, CURRENT_TABLE, type_="check")
    for name in (
        "adoption_projection_version",
        "mutation_allowed",
        "adoption_state",
    ):
        if name in columns:
            op.drop_column(CURRENT_TABLE, name)


def _create_lifetime_accepted_index(bind: sa.Connection) -> None:
    names = {
        str(index.get("name") or "")
        for index in sa.inspect(bind).get_indexes(ADOPTION_TABLE)
    }
    if LIFETIME_ACCEPTED_INDEX not in names:
        op.create_index(
            LIFETIME_ACCEPTED_INDEX,
            ADOPTION_TABLE,
            ["ticket_id"],
            unique=True,
            postgresql_where=sa.text("decision = 'accepted'"),
            sqlite_where=sa.text("decision = 'accepted'"),
        )


def _table(bind: sa.Connection, table_name: str) -> sa.Table:
    return sa.Table(table_name, sa.MetaData(), autoload_with=bind)


def _column_names(bind: sa.Connection, table_name: str) -> set[str]:
    return {
        str(column["name"])
        for column in sa.inspect(bind).get_columns(table_name)
    }


def _constraint_names(bind: sa.Connection, table_name: str) -> set[str]:
    return {
        str(constraint.get("name") or "")
        for constraint in sa.inspect(bind).get_check_constraints(table_name)
    }
