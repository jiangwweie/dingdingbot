"""Add physical capacity-fact references for account-risk authority.

Revision ID: 134
Revises: 133
Create Date: 2026-07-17
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import hashlib
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "134"
down_revision: Union[str, None] = "133"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# This is deliberately duplicated from the pre-134 Ticket contract rather
# than imported from application code.  Migration validation must remain tied
# to the historical V1 canonical tuple even after future runtime code changes.
_FROZEN_TICKET_HASH_V1_FIELDS = (
    "ticket_id", "action_time_invocation_id", "action_time_lane_input_id",
    "promotion_candidate_id", "signal_event_id", "event_spec_id",
    "event_spec_version_id", "candidate_scope_id", "runtime_scope_binding_id",
    "strategy_group_id", "strategy_group_version_id", "symbol",
    "exchange_instrument_id", "side", "event_id", "event_time_ms",
    "trigger_candle_close_time_ms", "runtime_profile_id",
    "public_fact_snapshot_id", "action_time_fact_snapshot_id",
    "account_safe_fact_snapshot_id", "account_mode_snapshot_id",
    "budget_reservation_id", "protection_ref_id", "execution_policy_id",
    "execution_policy_version", "owner_policy_version", "sizing_policy_version",
    "protection_policy_version", "exit_policy_id", "exit_policy_version",
    "exit_policy_hash", "target_notional", "leverage", "effective_notional",
    "selected_leverage", "planned_stop_risk_budget", "planned_stop_risk",
    "expires_at_ms", "authority_boundary", "created_under_versions_hash",
    "signal_grade", "required_execution_mode", "execution_eligible",
    "authority_source_ref", "lane_identity_key", "source_watermark",
)
_FROZEN_TICKET_DECIMAL_FIELDS = {
    "target_notional", "leverage", "effective_notional",
    "planned_stop_risk_budget", "planned_stop_risk",
}
_FROZEN_TICKET_INTEGER_FIELDS = {
    "event_time_ms", "trigger_candle_close_time_ms", "expires_at_ms",
}
_LEGACY_TERMINAL_HASH_SCHEMA = (
    "action_time_ticket_hash.legacy_terminal_unverifiable"
)
_TERMINAL_TICKET_STATUSES = frozenset(
    {"expired", "closed", "invalidated", "rejected", "cancelled"}
)


def upgrade() -> None:
    bind = op.get_bind()
    _make_ticket_legacy_account_fact_nullable(bind)
    _add_column_if_missing(
        bind,
        "brc_action_time_invocations",
        "account_capacity_base_fact_snapshot_id",
        sa.String(256),
    )
    _add_column_if_missing(
        bind,
        "brc_action_time_lane_inputs",
        "account_capacity_base_fact_snapshot_id",
        sa.String(256),
    )
    _add_column_if_missing(
        bind,
        "brc_action_time_tickets",
        "account_capacity_base_fact_snapshot_id",
        sa.String(256),
    )
    _add_column_if_missing(
        bind,
        "brc_action_time_tickets",
        "ticket_hash_schema_version",
        sa.String(64),
    )
    if sa.inspect(bind).has_table("brc_action_time_tickets"):
        _classify_historical_ticket_hashes(bind)
    for column_name, column_type in (
        ("trusted_fact_refs_schema_version", sa.String(64)),
        ("account_capacity_fact_surface", sa.String(64)),
        ("account_capacity_fact_snapshot_id", sa.String(256)),
    ):
        _add_column_if_missing(
            bind,
            "brc_runtime_safety_state_snapshots",
            column_name,
            column_type,
        )
    if sa.inspect(bind).has_table("brc_runtime_safety_state_snapshots"):
        bind.execute(
            sa.text(
                "UPDATE brc_runtime_safety_state_snapshots "
                "SET trusted_fact_refs_schema_version = "
                "'runtime_safety_trusted_refs.v1' "
                "WHERE trusted_fact_refs_schema_version IS NULL"
            )
        )
    _create_index_if_missing(
        bind,
        "brc_action_time_invocations",
        "idx_brc_invocation_capacity_base_fact",
        ["account_capacity_base_fact_snapshot_id"],
    )
    _create_index_if_missing(
        bind,
        "brc_action_time_lane_inputs",
        "idx_brc_lane_capacity_base_fact",
        ["account_capacity_base_fact_snapshot_id"],
    )
    _create_index_if_missing(
        bind,
        "brc_action_time_tickets",
        "idx_brc_ticket_capacity_base_fact",
        ["account_capacity_base_fact_snapshot_id"],
    )
    _create_index_if_missing(
        bind,
        "brc_runtime_safety_state_snapshots",
        "idx_brc_runtime_safety_capacity_fact",
        ["account_capacity_fact_surface", "account_capacity_fact_snapshot_id"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    _assert_no_v2_history(bind)
    for table_name, index_name in (
        ("brc_action_time_invocations", "idx_brc_invocation_capacity_base_fact"),
        ("brc_action_time_lane_inputs", "idx_brc_lane_capacity_base_fact"),
        ("brc_action_time_tickets", "idx_brc_ticket_capacity_base_fact"),
        ("brc_runtime_safety_state_snapshots", "idx_brc_runtime_safety_capacity_fact"),
    ):
        if sa.inspect(bind).has_table(table_name):
            bind.execute(sa.text(f"DROP INDEX IF EXISTS {index_name}"))


def _assert_no_v2_history(bind: sa.Connection) -> None:
    checks = (
        (
            "brc_action_time_tickets",
            "ticket_hash_schema_version",
            "action_time_ticket_hash.v2",
        ),
        (
            "brc_runtime_safety_state_snapshots",
            "trusted_fact_refs_schema_version",
            "runtime_safety_trusted_refs.v2",
        ),
    )
    for table_name, column_name, v2_value in checks:
        if not sa.inspect(bind).has_table(table_name):
            continue
        columns = {column["name"] for column in sa.inspect(bind).get_columns(table_name)}
        if column_name not in columns:
            continue
        count = bind.execute(
            sa.text(
                f"SELECT count(*) FROM {table_name} "
                f"WHERE {column_name} = :v2_value"
            ),
            {"v2_value": v2_value},
        ).scalar_one()
        if int(count or 0):
            raise RuntimeError("capacity_fact_history_not_legacy_compatible")


def _classify_historical_ticket_hashes(bind: sa.Connection) -> None:
    """Label only proven V1 rows; quarantine terminal snapshot drift.

    The scan is deliberately keyset-batched to avoid materializing Ticket
    history in application memory.  A nonterminal hash mismatch remains a
    hard failure.  An already terminal row whose mutable lifecycle projection
    drifted after its immutable Ticket hash was issued is retained as history
    under an explicitly non-authoritative schema label; it is never rehashed
    or upgraded into V1/V2 execution authority.
    """

    tickets = sa.Table("brc_action_time_tickets", sa.MetaData(), autoload_with=bind)
    columns = set(tickets.c.keys())
    if not {"ticket_id", "ticket_hash"} <= columns:
        return
    last_ticket_id = ""
    while True:
        rows = bind.execute(
            sa.select(tickets)
            .where(tickets.c.ticket_id > last_ticket_id)
            .order_by(tickets.c.ticket_id)
            .limit(500)
        ).mappings().all()
        if not rows:
            return
        v1_ticket_ids: list[str] = []
        legacy_terminal_ticket_ids: list[str] = []
        for row in rows:
            expected = _frozen_ticket_hash_v1(row)
            if str(row.get("ticket_hash") or "") == expected:
                v1_ticket_ids.append(str(row["ticket_id"]))
            elif str(row.get("status") or "") in _TERMINAL_TICKET_STATUSES:
                legacy_terminal_ticket_ids.append(str(row["ticket_id"]))
            else:
                raise RuntimeError("ticket_hash_v1_preflight_invalid")
        _label_ticket_hash_schema_batch(
            bind,
            ticket_ids=v1_ticket_ids,
            schema_version="action_time_ticket_hash.v1",
        )
        _label_ticket_hash_schema_batch(
            bind,
            ticket_ids=legacy_terminal_ticket_ids,
            schema_version=_LEGACY_TERMINAL_HASH_SCHEMA,
        )
        last_ticket_id = str(rows[-1]["ticket_id"])


def _label_ticket_hash_schema_batch(
    bind: sa.Connection,
    *,
    ticket_ids: list[str],
    schema_version: str,
) -> None:
    if not ticket_ids:
        return
    bind.execute(
        sa.text(
            "UPDATE brc_action_time_tickets "
            "SET ticket_hash_schema_version = :schema_version "
            "WHERE ticket_hash_schema_version IS NULL "
            "AND ticket_id IN :ticket_ids"
        ).bindparams(sa.bindparam("ticket_ids", expanding=True)),
        {"schema_version": schema_version, "ticket_ids": ticket_ids},
    )


def _frozen_ticket_hash_v1(row: sa.RowMapping) -> str:
    payload = {
        field: _frozen_ticket_hash_value(field, row.get(field))
        for field in _FROZEN_TICKET_HASH_V1_FIELDS
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _frozen_ticket_hash_value(field: str, value: object) -> object:
    if field in _FROZEN_TICKET_DECIMAL_FIELDS:
        return _frozen_decimal_string(value)
    if field in _FROZEN_TICKET_INTEGER_FIELDS:
        try:
            return int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return value
    return value


def _frozen_decimal_string(value: object) -> str:
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return str(value)
    if decimal_value == 0:
        return "0"
    canonical = decimal_value.quantize(Decimal("0.000000000001"))
    return format(canonical.normalize(), "f")


def _add_column_if_missing(
    bind: sa.Connection,
    table_name: str,
    column_name: str,
    column_type: sa.types.TypeEngine[object],
) -> None:
    if not sa.inspect(bind).has_table(table_name):
        return
    columns = {column["name"] for column in sa.inspect(bind).get_columns(table_name)}
    if column_name not in columns:
        op.add_column(table_name, sa.Column(column_name, column_type, nullable=True))


def _make_ticket_legacy_account_fact_nullable(bind: sa.Connection) -> None:
    table_name = "brc_action_time_tickets"
    if not sa.inspect(bind).has_table(table_name):
        return
    columns = {
        column["name"]: column
        for column in sa.inspect(bind).get_columns(table_name)
    }
    column = columns.get("account_safe_fact_snapshot_id")
    if column is None or column.get("nullable") is True:
        return
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table(table_name) as batch:
            batch.alter_column(
                "account_safe_fact_snapshot_id",
                existing_type=column["type"],
                nullable=True,
            )
    else:
        op.alter_column(
            table_name,
            "account_safe_fact_snapshot_id",
            existing_type=column["type"],
            nullable=True,
        )


def _create_index_if_missing(
    bind: sa.Connection,
    table_name: str,
    index_name: str,
    columns: list[str],
) -> None:
    if not sa.inspect(bind).has_table(table_name):
        return
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes(table_name)}
    if index_name not in indexes:
        op.create_index(index_name, table_name, columns)
