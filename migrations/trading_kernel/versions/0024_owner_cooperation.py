"""Add persistent Owner device sessions and serialized position intents.

Frozen additive schema; stopped/flat source and historical row preservation.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


def _define_frozen_tables(metadata: sa.MetaData) -> tuple[sa.Table, ...]:
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
            "result_kind", sa.String(24), nullable=False, server_default="pending"
        ),
        sa.Column("result_payload", JSONB(none_as_null=True)),
        sa.CheckConstraint(
            "(result_kind='pending' AND authorization_id IS NULL AND result_payload IS NULL) OR (result_kind='authorized' AND authorization_id IS NOT NULL) OR (result_kind='no_change' AND authorization_id IS NULL AND result_payload IS NOT NULL)",
            name="result_valid",
        ),
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
    binding_limits = sa.Table(
        "brc_owner_binding_limits",
        metadata,
        sa.Column("bucket_key", sa.String(80), primary_key=True),
        sa.Column("failures", JSONB, nullable=False),
        sa.Column("expires_at_ms", time, nullable=False),
        sa.CheckConstraint(
            "jsonb_typeof(failures)='array' AND jsonb_array_length(failures)<=5 AND expires_at_ms>0",
            name="valid",
        ),
    )
    sa.Index("ix_brc_owner_binding_limits_expiry", binding_limits.c.expires_at_ms)
    receive_epochs = sa.Table(
        "brc_management_receive_epochs",
        metadata,
        sa.Column("scope_key", ids, primary_key=True),
        sa.Column("epoch_id", ids, primary_key=True),
        sa.Column("ordinal", time, nullable=False),
        sa.Column("persisted_watermark", time, nullable=False),
        sa.Column("connected_at_ms", time),
        sa.Column("gap_reason", sa.String(256)),
        sa.Column("backlog_pending", sa.Boolean, nullable=False),
        sa.Column("updated_at_ms", time, nullable=False),
        sa.Column("completed_at_ms", time),
        sa.UniqueConstraint(
            "scope_key", "ordinal", name="uq_brc_management_receive_ordinal"
        ),
        sa.CheckConstraint(
            "ordinal>0 AND persisted_watermark>=0 AND updated_at_ms>0", name="valid"
        ),
    )
    sa.Index(
        "ix_brc_management_receive_pending",
        receive_epochs.c.scope_key,
        receive_epochs.c.ordinal,
        postgresql_where=receive_epochs.c.completed_at_ms.is_(None),
    )
    return (
        devices,
        sessions,
        grants,
        nonces,
        operations,
        events,
        writes,
        binding_limits,
        receive_epochs,
    )


revision: str = "0024_owner_cooperation"
down_revision: str = "0023_management_recovery"
branch_labels = None
depends_on = None


def upgrade():
    c = op.get_bind()
    c.exec_driver_sql(
        "LOCK TABLE brc_trade_tickets, brc_exchange_commands, brc_positions_current, brc_owner_policy_current IN SHARE ROW EXCLUSIVE MODE"
    )
    for table, predicate in {
        "brc_trade_tickets": "terminal_at_ms IS NULL",
        "brc_positions_current": "quantity<>0",
        "brc_exchange_commands": "status IN ('prepared','claimed','dispatch_started','outcome_unknown')",
        "brc_owner_policy_current": "new_entry_submit_enabled",
        "brc_budget_reservations": "status='active'",
        "brc_entry_lane_current": "status<>'idle'",
        "brc_runtime_incidents": "status='open'",
        "brc_account_exposure_current": "active_ticket_count<>0 OR gross_notional<>0 OR gross_risk_at_stop<>0 OR current_reserved_margin<>0",
    }.items():
        if c.scalar(sa.text(f"SELECT EXISTS(SELECT 1 FROM {table} WHERE {predicate})")):
            raise RuntimeError(
                "0024 requires stopped flat terminal-clean paused source"
            )
    op.drop_constraint(
        "ck_brc_owner_auth_auth_valid",
        "brc_owner_authorizations",
        type_="check",
    )
    op.create_check_constraint(
        "ck_brc_owner_authorizations_auth_valid",
        "brc_owner_authorizations",
        "authentication_strength IN ('session','totp_step_up','trusted_device_session')",
    )
    op.drop_constraint(
        "ck_brc_owner_authorizations_purpose_valid",
        "brc_owner_authorizations",
        type_="check",
    )
    op.create_check_constraint(
        "ck_brc_owner_authorizations_purpose_valid",
        "brc_owner_authorizations",
        "purpose IN ('strategy_pause','strategy_resume','entry_pause','entry_resume','owner_flatten_all',"
        "'universe_configure','selection_mode_change','exit_profile_bind','exit_profile_retire','review_revise',"
        "'position_reduce','position_close','protection_tighten','manual_tp_set','manual_tp_cancel')",
    )
    op.add_column(
        "brc_trade_aggregates",
        sa.Column("owner_reduction_context", JSONB(none_as_null=True), nullable=True),
    )
    m = sa.MetaData()
    sa.Table(
        "brc_trade_tickets", m, sa.Column("ticket_id", sa.String(160), primary_key=True)
    )
    sa.Table(
        "brc_owner_authorizations",
        m,
        sa.Column("authorization_id", sa.String(160), primary_key=True),
    )
    for table in _define_frozen_tables(m):
        table.create(c)
    c.exec_driver_sql(
        """CREATE FUNCTION brc_owner_operation_event_immutable() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Owner operation events are append-only'; END; $$"""
    )
    c.exec_driver_sql(
        "CREATE TRIGGER trg_owner_operation_event_immutable BEFORE UPDATE OR DELETE ON brc_owner_position_operation_events FOR EACH ROW EXECUTE FUNCTION brc_owner_operation_event_immutable()"
    )
    c.exec_driver_sql("""CREATE FUNCTION brc_owner_device_source_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Owner device source immutable'; END IF;
      IF TG_TABLE_NAME='brc_owner_device_registrations' THEN
        IF (to_jsonb(NEW)-'revoked_at_ms') IS DISTINCT FROM (to_jsonb(OLD)-'revoked_at_ms')
          OR OLD.revoked_at_ms IS NOT NULL OR NEW.revoked_at_ms IS NULL OR NEW.revoked_at_ms<OLD.registered_at_ms
          THEN RAISE EXCEPTION 'Owner device registration immutable'; END IF;
      ELSE
        IF (to_jsonb(NEW)-ARRAY['authorization_id','result_kind','result_payload']) IS DISTINCT FROM
           (to_jsonb(OLD)-ARRAY['authorization_id','result_kind','result_payload'])
          OR OLD.result_kind<>'pending' OR NEW.result_kind NOT IN ('authorized','no_change')
          THEN RAISE EXCEPTION 'Owner write evidence immutable'; END IF;
      END IF;
      RETURN NEW;
    END; $$""")
    for table in ["brc_owner_device_registrations", "brc_owner_device_write_evidence"]:
        c.exec_driver_sql(
            f"CREATE TRIGGER trg_{table}_source_immutable BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION brc_owner_device_source_immutable()"
        )
    c.exec_driver_sql("""CREATE FUNCTION brc_owner_device_authorization_valid(aid text, expected_purpose text, checked_at bigint)
    RETURNS boolean LANGUAGE sql STABLE AS $$
      SELECT EXISTS(SELECT 1 FROM brc_owner_authorizations a
        JOIN brc_owner_device_write_evidence e USING(authorization_id)
        JOIN brc_owner_device_registrations d ON d.device_id=e.device_id
        WHERE a.authorization_id=aid AND a.purpose=expected_purpose
          AND expected_purpose IN ('entry_pause','entry_resume','strategy_pause','strategy_resume','position_reduce','position_close','protection_tighten','manual_tp_set','manual_tp_cancel')
          AND a.authentication_strength='trusted_device_session' AND e.result_kind='authorized' AND e.purpose=a.purpose
          AND e.owner_identity=a.owner_identity AND d.owner_identity=a.owner_identity
          AND e.device_epoch=d.epoch AND e.authorized_at_ms=a.authorized_at_ms
          AND d.registered_at_ms<=a.authorized_at_ms AND a.authorized_at_ms<=checked_at
          AND (d.revoked_at_ms IS NULL OR d.revoked_at_ms>a.authorized_at_ms)
          AND (e.proof->>'issued_at_ms')::bigint<=a.authorized_at_ms
          AND (e.proof->>'expires_at_ms')::bigint>a.authorized_at_ms
          AND e.proof->>'device_id'=e.device_id AND e.proof->>'body_digest'=e.body_digest
          AND length(e.signature)>=80)
    $$""")
    # Narrowly extend only strategy Resume proofs, not Selection/configuration
    # or risk-budget authority. Original historical TOTP branches remain.
    for signature, alias in [
        ("brc_static_owner_resume_authorization(text,bigint)", "a"),
        ("brc_orb_owner_resume_matches(text,bigint)", "a"),
        ("brc_generic_vacuum_owner_resume_matches(text,text,bigint)", "resume_auth"),
    ]:
        definition = c.scalar(
            sa.text("SELECT pg_get_functiondef(to_regprocedure(:signature))"),
            {"signature": signature},
        )
        if not definition:
            raise RuntimeError("Owner Resume authority function missing")
        marker = alias + ".authentication_strength='totp_step_up'"
        if marker not in definition:
            raise RuntimeError("Owner Resume authority predicate changed")
        c.exec_driver_sql(
            definition.replace(
                marker,
                "("
                + marker
                + " OR brc_owner_device_authorization_valid("
                + alias
                + ".authorization_id,'strategy_resume',"
                + alias
                + ".authorized_at_ms))",
            )
        )

    for role in ["brc_kernel", "brc_owner_console", "brc_owner_control"]:
        exists = c.scalar(
            sa.text("SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=:role)"),
            {"role": role},
        )
        if not exists:
            continue
        names = ", ".join(t.name for t in _define_frozen_tables(sa.MetaData()))
        c.exec_driver_sql("GRANT SELECT ON " + names + " TO " + role)
        if role == "brc_kernel":
            c.exec_driver_sql("GRANT INSERT, UPDATE ON " + names + " TO " + role)
        if role == "brc_owner_control":
            c.exec_driver_sql(
                "GRANT INSERT, UPDATE ON brc_owner_device_sessions, brc_owner_request_nonces, brc_owner_position_operations, brc_owner_binding_limits TO "
                + role
            )
            c.exec_driver_sql("GRANT DELETE ON brc_owner_binding_limits TO " + role)
            c.exec_driver_sql(
                "GRANT INSERT ON brc_owner_device_registrations, brc_owner_device_write_evidence TO "
                + role
            )
            c.exec_driver_sql(
                "REVOKE UPDATE ON brc_owner_device_registrations, brc_owner_device_write_evidence FROM "
                + role
            )
            c.exec_driver_sql(
                "GRANT UPDATE (revoked_at_ms) ON brc_owner_device_registrations TO "
                + role
            )
            c.exec_driver_sql(
                "GRANT UPDATE (authorization_id,result_kind,result_payload) ON brc_owner_device_write_evidence TO "
                + role
            )
            c.exec_driver_sql(
                "GRANT UPDATE (consumed_at_ms) ON brc_owner_binding_grants TO " + role
            )
            c.exec_driver_sql(
                "GRANT INSERT ON brc_owner_position_operation_events TO " + role
            )


def downgrade():
    raise RuntimeError("owner cooperation requires forward-only evolution")
