"""Additive persistent Owner device and position-operation authority."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


def define_owner_cooperation_tables(metadata: sa.MetaData) -> tuple[sa.Table, ...]:
    ids = sa.String(160)
    text = sa.String(512)
    time = sa.BigInteger
    devices = sa.Table(
        "brc_owner_device_registrations",
        metadata,
        sa.Column("device_id", ids, primary_key=True),
        sa.Column("owner_identity", sa.String(96), nullable=False),
        sa.Column("epoch", time, nullable=False),
        sa.Column("public_key", JSONB, nullable=False),
        sa.Column("key_digest", sa.String(71), nullable=False),
        sa.Column("registered_at_ms", time, nullable=False),
        sa.Column("revoked_at_ms", time),
        sa.CheckConstraint("epoch>0 AND registered_at_ms>0", name="valid"),
    )
    sa.Index(
        "uq_brc_owner_one_active_device",
        devices.c.owner_identity,
        unique=True,
        postgresql_where=devices.c.revoked_at_ms.is_(None),
    )
    sessions = sa.Table(
        "brc_owner_device_sessions",
        metadata,
        sa.Column("session_id", ids, primary_key=True),
        sa.Column("device_id", ids, sa.ForeignKey(devices.c.device_id), nullable=False),
        sa.Column("device_epoch", time, nullable=False),
        sa.Column("token_digest", sa.String(71), nullable=False, unique=True),
        sa.Column("issued_at_ms", time, nullable=False),
        sa.Column("last_seen_at_ms", time, nullable=False),
        sa.Column("expires_at_ms", time, nullable=False),
        sa.Column("revoked_at_ms", time),
        sa.CheckConstraint(
            "device_epoch>0 AND issued_at_ms<=last_seen_at_ms AND last_seen_at_ms<expires_at_ms",
            name="valid",
        ),
    )
    grants = sa.Table(
        "brc_owner_binding_grants",
        metadata,
        sa.Column("grant_id", ids, primary_key=True),
        sa.Column("token_digest", sa.String(71), nullable=False, unique=True),
        sa.Column("owner_identity", sa.String(96), nullable=False),
        sa.Column("replace_device", sa.Boolean, nullable=False),
        sa.Column("issued_at_ms", time, nullable=False),
        sa.Column("expires_at_ms", time, nullable=False),
        sa.Column("consumed_at_ms", time),
        sa.CheckConstraint(
            "issued_at_ms>0 AND expires_at_ms>issued_at_ms", name="valid"
        ),
    )
    nonces = sa.Table(
        "brc_owner_request_nonces",
        metadata,
        sa.Column("nonce_id", ids, primary_key=True),
        sa.Column(
            "session_id", ids, sa.ForeignKey(sessions.c.session_id), nullable=False
        ),
        sa.Column("issued_at_ms", time, nullable=False),
        sa.Column("expires_at_ms", time, nullable=False),
        sa.Column("consumed_at_ms", time),
        sa.Column("request_digest", sa.String(71)),
        sa.Column("idempotency_key", ids),
        sa.CheckConstraint(
            "issued_at_ms>0 AND expires_at_ms>issued_at_ms AND expires_at_ms-issued_at_ms<=60000",
            name="valid",
        ),
    )
    operations = sa.Table(
        "brc_owner_position_operations",
        metadata,
        sa.Column("operation_id", ids, primary_key=True),
        sa.Column(
            "ticket_id",
            ids,
            sa.ForeignKey("brc_trade_tickets.ticket_id"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("owner_identity", sa.String(96), nullable=False),
        sa.Column("device_id", ids, sa.ForeignKey(devices.c.device_id), nullable=False),
        sa.Column("device_epoch", time, nullable=False),
        sa.Column(
            "authorization_id",
            ids,
            sa.ForeignKey("brc_owner_authorizations.authorization_id"),
        ),
        sa.Column("idempotency_key", ids, nullable=False),
        sa.Column("request_digest", sa.String(71), nullable=False),
        sa.Column("version", time, nullable=False),
        sa.Column("state", sa.String(48), nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("first_blocker", text),
        sa.Column("created_at_ms", time, nullable=False),
        sa.Column("updated_at_ms", time, nullable=False),
        sa.Column("due_at_ms", time, nullable=False),
        sa.Column("completed_at_ms", time),
        sa.UniqueConstraint(
            "owner_identity",
            "idempotency_key",
            name="uq_brc_owner_position_idempotency",
        ),
        sa.CheckConstraint(
            "version>0 AND device_epoch>0 AND updated_at_ms>=created_at_ms",
            name="valid",
        ),
        sa.CheckConstraint(
            "kind IN ('position_reduce','position_close','protection_tighten','manual_tp_set','manual_tp_cancel')",
            name="kind_valid",
        ),
    )
    sa.Index(
        "uq_brc_owner_one_active_adjustment",
        operations.c.ticket_id,
        unique=True,
        postgresql_where=sa.and_(
            operations.c.completed_at_ms.is_(None), operations.c.state != "previewed"
        ),
    )
    sa.Index(
        "ix_brc_owner_operation_due",
        operations.c.due_at_ms,
        operations.c.operation_id,
        postgresql_where=operations.c.completed_at_ms.is_(None),
    )
    events = sa.Table(
        "brc_owner_position_operation_events",
        metadata,
        sa.Column(
            "operation_id",
            ids,
            sa.ForeignKey(operations.c.operation_id),
            primary_key=True,
        ),
        sa.Column("version", time, primary_key=True),
        sa.Column("state", sa.String(48), nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("occurred_at_ms", time, nullable=False),
        sa.CheckConstraint("version>0 AND occurred_at_ms>0", name="valid"),
    )
    writes = sa.Table(
        "brc_owner_device_write_evidence",
        metadata,
        sa.Column("evidence_id", sa.String(71), primary_key=True),
        sa.Column(
            "authorization_id",
            ids,
            sa.ForeignKey("brc_owner_authorizations.authorization_id"),
            unique=True,
        ),
        sa.Column("device_id", ids, sa.ForeignKey(devices.c.device_id), nullable=False),
        sa.Column("device_epoch", time, nullable=False),
        sa.Column("owner_identity", sa.String(96), nullable=False),
        sa.Column("purpose", sa.String(48), nullable=False),
        sa.Column("idempotency_key", ids, nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("proof", JSONB, nullable=False),
        sa.Column("signature", sa.String(128), nullable=False),
        sa.Column("body_digest", sa.String(71), nullable=False),
        sa.Column("authorized_at_ms", time, nullable=False),
        sa.UniqueConstraint(
            "owner_identity",
            "idempotency_key",
            name="uq_brc_owner_device_write_request",
        ),
    )
    return devices, sessions, grants, nonces, operations, events, writes
