"""Add the Owner control-plane authority tables."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0004_owner_control_plane"
down_revision: str | None = "0003_portfolio_admission_observability"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ID = sa.String(160)
SHORT_TEXT = sa.String(96)
LONG_TEXT = sa.String(512)


def upgrade() -> None:
    _assert_flat_source()
    op.create_table(
        "brc_owner_authorizations",
        sa.Column("authorization_id", ID, primary_key=True),
        sa.Column("purpose", SHORT_TEXT, nullable=False),
        sa.Column("owner_identity", SHORT_TEXT, nullable=False),
        sa.Column("authentication_strength", SHORT_TEXT, nullable=False),
        sa.Column("request_digest", LONG_TEXT, nullable=False),
        sa.Column("target_scope", JSONB, nullable=False),
        sa.Column("idempotency_key", ID, nullable=False, unique=True),
        sa.Column("authorized_at_ms", sa.BigInteger(), nullable=False),
        sa.CheckConstraint(
            "purpose IN ('strategy_pause', 'strategy_resume', 'entry_pause', "
            "'entry_resume', 'owner_flatten_all')",
            name="ck_brc_owner_authorizations_purpose_valid",
        ),
        sa.CheckConstraint(
            "authentication_strength IN ('session', 'totp_step_up')",
            name="ck_brc_owner_auth_auth_valid",
        ),
        sa.CheckConstraint(
            "request_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_brc_owner_auth_digest_valid",
        ),
    )
    op.create_table(
        "brc_strategy_entry_control_events",
        sa.Column("strategy_entry_control_event_id", ID, primary_key=True),
        sa.Column("strategy_group_id", ID, nullable=False),
        sa.Column("control_version", sa.BigInteger(), nullable=False),
        sa.Column("operation", SHORT_TEXT, nullable=False),
        sa.Column("target_state", SHORT_TEXT, nullable=False),
        sa.Column("authorization_id", ID, nullable=False),
        sa.Column("reason", LONG_TEXT, nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("created_at_ms", sa.BigInteger(), nullable=False),
        sa.UniqueConstraint("strategy_group_id", "control_version"),
        sa.CheckConstraint("control_version > 0", name="ck_brc_strategy_control_event_ver"),
        sa.CheckConstraint("operation IN ('pause', 'resume')", name="ck_brc_strategy_control_event_op"),
        sa.CheckConstraint("target_state IN ('paused', 'enabled')", name="ck_brc_strategy_control_event_state"),
    )
    op.create_table(
        "brc_strategy_entry_controls_current",
        sa.Column("strategy_group_id", ID, primary_key=True),
        sa.Column("entry_state", SHORT_TEXT, nullable=False),
        sa.Column("control_version", sa.BigInteger(), nullable=False),
        sa.Column("last_event_id", ID, nullable=False),
        sa.Column("reason", LONG_TEXT, nullable=False),
        sa.Column("updated_at_ms", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("entry_state IN ('paused', 'enabled')", name="ck_brc_strategy_control_current_state"),
        sa.CheckConstraint("control_version > 0", name="ck_brc_strategy_control_current_ver"),
    )
    op.create_table(
        "brc_owner_control_operation_events",
        sa.Column("control_operation_event_id", ID, primary_key=True),
        sa.Column("authorization_id", ID, nullable=False),
        sa.Column("operation_version", sa.BigInteger(), nullable=False),
        sa.Column("state", SHORT_TEXT, nullable=False),
        sa.Column("first_blocker", LONG_TEXT, nullable=True),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("created_at_ms", sa.BigInteger(), nullable=False),
        sa.UniqueConstraint("authorization_id", "operation_version"),
        sa.CheckConstraint("operation_version > 0", name="ck_brc_owner_control_event_ver"),
    )
    op.create_table(
        "brc_owner_control_operations_current",
        sa.Column("authorization_id", ID, primary_key=True),
        sa.Column("operation_kind", SHORT_TEXT, nullable=False),
        sa.Column("state", SHORT_TEXT, nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.Column("runtime_profile_id", ID, nullable=False),
        sa.Column("venue_id", SHORT_TEXT, nullable=False),
        sa.Column("account_id", ID, nullable=False),
        sa.Column("target_ticket_ids", JSONB, nullable=False),
        sa.Column("snapshot_digest", LONG_TEXT, nullable=False),
        sa.Column("first_blocker", LONG_TEXT, nullable=True),
        sa.Column("claimed_by", ID, nullable=True),
        sa.Column("lease_until_ms", sa.BigInteger(), nullable=True),
        sa.Column("created_at_ms", sa.BigInteger(), nullable=False),
        sa.Column("updated_at_ms", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("operation_kind = 'flatten_all'", name="ck_brc_owner_control_current_kind"),
        sa.CheckConstraint("version > 0", name="ck_brc_owner_control_current_ver"),
        sa.CheckConstraint("snapshot_digest ~ '^sha256:[0-9a-f]{64}$'", name="ck_brc_owner_control_current_digest"),
    )
    op.create_index(
        "ix_brc_owner_control_operations_actionable",
        "brc_owner_control_operations_current",
        ["state", "updated_at_ms"],
    )
    _seed_strategy_controls()


def downgrade() -> None:
    raise RuntimeError("0004_owner_control_plane is fix-forward only")


def _assert_flat_source() -> None:
    connection = op.get_bind()
    checks = {
        "nonterminal_ticket": "SELECT count(*) FROM brc_trade_aggregates WHERE status NOT IN ('terminal', 'leverage_rejected', 'entry_rejected', 'entry_reconciled_absent')",
        "nonflat_position": "SELECT count(*) FROM brc_positions_current WHERE quantity <> 0",
        "active_reservation": "SELECT count(*) FROM brc_budget_reservations WHERE status = 'active'",
        "unresolved_command": "SELECT count(*) FROM brc_exchange_commands WHERE status IN ('prepared', 'claimed', 'dispatch_started', 'outcome_unknown')",
        "open_incident": "SELECT count(*) FROM brc_runtime_incidents WHERE status = 'open'",
    }
    blockers = [name for name, query in checks.items() if int(connection.scalar(sa.text(query)) or 0) != 0]
    if blockers:
        raise RuntimeError("0004 migration requires exact flat source: " + ",".join(blockers))


def _seed_strategy_controls() -> None:
    connection = op.get_bind()
    now_ms = int(connection.scalar(sa.text("SELECT floor(extract(epoch FROM clock_timestamp()) * 1000)::bigint")))
    groups = tuple(connection.execute(sa.text("SELECT strategy_group_id FROM brc_strategy_groups ORDER BY strategy_group_id")).scalars())
    for strategy_group_id in groups:
        event_id = f"strategy-control-event:seed:{strategy_group_id}"
        authorization_id = f"owner-authorization:seed:{strategy_group_id}"
        connection.execute(sa.text("INSERT INTO brc_owner_authorizations (authorization_id, purpose, owner_identity, authentication_strength, request_digest, target_scope, idempotency_key, authorized_at_ms) VALUES (:authorization_id, 'strategy_resume', 'system-seed', 'session', :digest, CAST(:scope AS jsonb), :idempotency_key, :now_ms)"), {"authorization_id": authorization_id, "digest": "sha256:" + "0" * 64, "scope": '{"seed":true}', "idempotency_key": f"owner-request:seed:{strategy_group_id}", "now_ms": now_ms})
        connection.execute(sa.text("INSERT INTO brc_strategy_entry_control_events (strategy_entry_control_event_id, strategy_group_id, control_version, operation, target_state, authorization_id, reason, payload, created_at_ms) VALUES (:event_id, :strategy_group_id, 1, 'resume', 'enabled', :authorization_id, 'seed_enabled', '{}'::jsonb, :now_ms)"), {"event_id": event_id, "strategy_group_id": strategy_group_id, "authorization_id": authorization_id, "now_ms": now_ms})
        connection.execute(sa.text("INSERT INTO brc_strategy_entry_controls_current (strategy_group_id, entry_state, control_version, last_event_id, reason, updated_at_ms) VALUES (:strategy_group_id, 'enabled', 1, :event_id, 'seed_enabled', :now_ms)"), {"strategy_group_id": strategy_group_id, "event_id": event_id, "now_ms": now_ms})
