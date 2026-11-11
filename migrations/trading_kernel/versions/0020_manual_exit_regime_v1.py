"""Actual-fill exit plans and supported Owner configuration authority, flat-only."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0020_manual_exit_regime_v1"
down_revision: str = "0019_management_evidence_v2"
branch_labels = None
depends_on = None


def upgrade():
    c = op.get_bind()
    if c.scalar(sa.text("SELECT version_num FROM alembic_version")) != down_revision:
        raise RuntimeError("0020 requires exact manual source")
    c.exec_driver_sql(
        "LOCK TABLE brc_trade_tickets, brc_exchange_commands, brc_positions_current, brc_owner_policy_current IN SHARE ROW EXCLUSIVE MODE"
    )
    for table, where in {
        "brc_trade_tickets": "terminal_at_ms IS NULL",
        "brc_positions_current": "quantity<>0",
        "brc_exchange_commands": "status IN ('prepared','claimed','dispatch_started','outcome_unknown')",
        "brc_owner_policy_current": "new_entry_submit_enabled",
        "brc_runtime_incidents": "status='open'",
        "brc_budget_reservations": "status='active'",
        "brc_entry_lane_current": "status<>'idle'",
        "brc_account_exposure_current": "active_ticket_count<>0 OR gross_notional<>0 OR gross_risk_at_stop<>0 OR current_reserved_margin<>0",
    }.items():
        if c.scalar(sa.text(f"SELECT EXISTS(SELECT 1 FROM {table} WHERE {where})")):
            raise RuntimeError(
                "0020 requires stopped flat terminal-clean paused source"
            )
    op.drop_constraint(
        "ck_brc_exit_policies_profile_schema_shape_valid",
        "brc_exit_policies",
        type_="check",
    )
    op.create_check_constraint(
        "ck_brc_exit_policies_profile_schema_shape_valid",
        "brc_exit_policies",
        "(event_spec_id IS NOT NULL AND profile_schema_version IS NULL) OR (event_spec_id IS NULL AND profile_schema_version IN ('exit_profile_v1','exit_profile_v2'))",
    )
    op.add_column(
        "brc_exchange_commands",
        sa.Column("management_revision", sa.BigInteger, nullable=True),
    )
    op.add_column(
        "brc_trade_tickets", sa.Column("regime_admission", JSONB, nullable=True)
    )
    op.add_column(
        "brc_capacity_claims", sa.Column("regime_admission", JSONB, nullable=True)
    )
    op.add_column(
        "brc_instrument_rules_current",
        sa.Column("exit_order_rules", JSONB, nullable=True),
    )
    op.add_column(
        "brc_trade_aggregates", sa.Column("post_fill_exit_plan", JSONB, nullable=True)
    )
    op.add_column(
        "brc_trade_aggregates",
        sa.Column(
            "partial_tp_protection",
            sa.Boolean,
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_table(
        "brc_post_fill_exit_plans",
        sa.Column(
            "ticket_id",
            sa.String(160),
            sa.ForeignKey("brc_trade_tickets.ticket_id"),
            primary_key=True,
        ),
        sa.Column(
            "source_event_id",
            sa.String(160),
            sa.ForeignKey("brc_trade_events.event_id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("plan", JSONB, nullable=False),
        sa.Column("created_at_ms", sa.BigInteger, nullable=False),
    )
    c.exec_driver_sql(
        "CREATE FUNCTION brc_exit_plan_immutable() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'exit plan immutable'; END; $$"
    )
    c.exec_driver_sql(
        "CREATE TRIGGER trg_brc_post_fill_exit_plans_immutable BEFORE UPDATE OR DELETE ON brc_post_fill_exit_plans FOR EACH ROW EXECUTE FUNCTION brc_exit_plan_immutable()"
    )
    c.exec_driver_sql("""CREATE FUNCTION brc_exit_plan_projection_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN IF OLD.post_fill_exit_plan IS NOT NULL AND NEW.post_fill_exit_plan IS DISTINCT FROM OLD.post_fill_exit_plan THEN
        RAISE EXCEPTION 'exit plan projection immutable'; END IF; RETURN NEW; END; $$""")
    c.exec_driver_sql(
        "CREATE TRIGGER trg_brc_exit_plan_projection_immutable BEFORE UPDATE ON brc_trade_aggregates FOR EACH ROW EXECUTE FUNCTION brc_exit_plan_projection_immutable()"
    )
    op.create_table(
        "brc_exit_configurations",
        sa.Column("configuration_id", sa.String(160), primary_key=True),
        sa.Column("product_id", sa.String(96), nullable=False),
        sa.Column("venue_id", sa.String(96), nullable=False),
        sa.Column("account_id", sa.String(160), nullable=False),
        sa.Column("revision", sa.BigInteger, nullable=False),
        sa.Column(
            "owner_authorization_id",
            sa.String(160),
            sa.ForeignKey("brc_owner_authorizations.authorization_id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("record", JSONB, nullable=False),
        sa.Column("created_at_ms", sa.BigInteger, nullable=False),
        sa.UniqueConstraint("product_id", "venue_id", "account_id", "revision"),
    )
    op.create_table(
        "brc_exit_configuration_current",
        sa.Column("product_id", sa.String(96), primary_key=True),
        sa.Column("venue_id", sa.String(96), primary_key=True),
        sa.Column("account_id", sa.String(160), primary_key=True),
        sa.Column(
            "configuration_id",
            sa.String(160),
            sa.ForeignKey("brc_exit_configurations.configuration_id"),
            nullable=False,
        ),
        sa.Column("revision", sa.BigInteger, nullable=False),
    )
    op.create_table(
        "brc_btc_ma50_current",
        sa.Column("venue_id", sa.String(96), primary_key=True),
        sa.Column("blocked_window_close_ms", sa.BigInteger, nullable=True),
        sa.Column("snapshot", JSONB, nullable=False),
        sa.Column("latest_close_time_ms", sa.BigInteger, nullable=False),
        sa.Column("observed_at_ms", sa.BigInteger, nullable=False),
    )
    c.exec_driver_sql(
        "CREATE TRIGGER trg_brc_exit_configurations_immutable BEFORE UPDATE OR DELETE ON brc_exit_configurations FOR EACH ROW EXECUTE FUNCTION brc_exit_plan_immutable()"
    )
    op.create_table(
        "brc_btc_ma50_snapshots",
        sa.Column("window_digest", sa.String(71), primary_key=True),
        sa.Column("venue_id", sa.String(96), nullable=False),
        sa.Column("latest_close_time_ms", sa.BigInteger, nullable=False),
        sa.Column("snapshot", JSONB, nullable=False),
        sa.Column("observed_at_ms", sa.BigInteger, nullable=False),
    )
    op.create_index(
        "ix_brc_btc_ma50_snapshot_window",
        "brc_btc_ma50_snapshots",
        ["venue_id", "latest_close_time_ms", "observed_at_ms"],
    )
    c.exec_driver_sql(
        "CREATE TRIGGER trg_brc_btc_ma50_snapshots_immutable BEFORE UPDATE OR DELETE ON brc_btc_ma50_snapshots FOR EACH ROW EXECUTE FUNCTION brc_exit_plan_immutable()"
    )
    for role, grant in [
        ("brc_kernel", "SELECT,INSERT"),
        ("brc_owner_console", "SELECT"),
    ]:
        if c.scalar(
            sa.text("SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=:role)"),
            {"role": role},
        ):
            c.exec_driver_sql(
                f"GRANT {grant} ON brc_post_fill_exit_plans, brc_exit_configurations, brc_btc_ma50_snapshots TO {role}"
            )
            c.exec_driver_sql(
                f"GRANT {'SELECT,INSERT,UPDATE' if role == 'brc_kernel' else 'SELECT'} ON brc_exit_configuration_current, brc_btc_ma50_current TO {role}"
            )
    if c.scalar(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='brc_owner_control')"
        )
    ):
        c.exec_driver_sql(
            "GRANT SELECT,INSERT ON brc_exit_policies,brc_exit_configurations TO brc_owner_control"
        )
        c.exec_driver_sql(
            "GRANT SELECT,INSERT,UPDATE ON brc_exit_configuration_current TO brc_owner_control"
        )


def downgrade():
    raise RuntimeError("manual exit regime is forward-only")
