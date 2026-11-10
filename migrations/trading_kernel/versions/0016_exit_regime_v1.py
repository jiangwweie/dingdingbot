"""Actual-fill exit plans and versioned strategy experiment controls.

Revision ID: 0016_exit_regime_v1
Revises: 0015_generic_owner_recovery_v1
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0016_exit_regime_v1"
down_revision: str | None = "0015_generic_owner_recovery_v1"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    if (
        connection.scalar(sa.text("SELECT version_num FROM alembic_version"))
        != down_revision
    ):
        raise RuntimeError("0016 requires exact 0015 source")
    gates = {
        "brc_trade_tickets": "terminal_at_ms IS NULL OR active_netting_domain_key IS NOT NULL",
        "brc_positions_current": "quantity<>0",
        "brc_budget_reservations": "status='active'",
        "brc_exchange_commands": "status IN ('prepared','claimed','dispatch_started','outcome_unknown')",
        "brc_runtime_incidents": "status='open'",
        "brc_entry_lane_current": "status<>'idle' OR ticket_id IS NOT NULL",
        "brc_entry_send_authorizations": "completed_at_ms IS NULL",
        "brc_trade_aggregates": "status NOT IN ('terminal','leverage_rejected','entry_rejected','entry_reconciled_absent')",
        "brc_owner_control_operations_current": "state NOT IN ('completed','blocked')",
        "brc_strategy_universe_versions": "lifecycle_state IN ('warming','staged')",
        "brc_strategy_universe_materialization_generations": "lifecycle_state IN ('PENDING','DESIRED','DRAINING_ENTRY','MATERIALIZING','STAGED')",
        "brc_directional_risk_controls": "pending_view IS NOT NULL OR pending_baseline IS NOT NULL",
    }
    connection.execute(
        sa.text(
            "LOCK TABLE "
            + ",".join(gates)
            + ",brc_owner_policy_current IN SHARE ROW EXCLUSIVE MODE"
        )
    )
    for table, predicate in gates.items():
        if connection.scalar(
            sa.text(f"SELECT EXISTS(SELECT 1 FROM {table} WHERE {predicate})")
        ):
            raise RuntimeError(f"0016 requires stopped flat source: {table}")
    from src.trading_kernel.infrastructure.generic_selection_source_provenance import (
        count_nonquiescent_source_vacuums,
    )

    if count_nonquiescent_source_vacuums(connection, allow_paused_failed_generic=True):
        raise RuntimeError("0016 requires quiescent selection Vacuums")
    op.add_column(
        "brc_trade_aggregates", sa.Column("post_fill_exit_plan", JSONB, nullable=True)
    )
    op.add_column(
        "brc_trade_aggregates",
        sa.Column(
            "initial_stop_closes_position",
            sa.Boolean,
            nullable=False,
            server_default=sa.false(),
        ),
    )
    connection.exec_driver_sql("""
        CREATE FUNCTION brc_guard_post_fill_exit_plan() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF OLD.post_fill_exit_plan IS NOT NULL AND NEW.post_fill_exit_plan IS DISTINCT FROM OLD.post_fill_exit_plan THEN
            RAISE EXCEPTION 'Post-fill exit plan is immutable';
          END IF;
          IF NEW.post_fill_exit_plan IS NOT NULL AND (NEW.post_fill_exit_plan->'request'->>'ticket_id') IS DISTINCT FROM NEW.ticket_id THEN
            RAISE EXCEPTION 'Post-fill exit plan Ticket mismatch';
          END IF;
          RETURN NEW;
        END; $$;
    """)
    connection.exec_driver_sql("""
        CREATE TRIGGER brc_post_fill_exit_plan_immutable BEFORE UPDATE ON brc_trade_aggregates
        FOR EACH ROW EXECUTE FUNCTION brc_guard_post_fill_exit_plan();
    """)

    op.create_table(
        "brc_entry_regime_revisions",
        sa.Column("event_spec_id", sa.String(160), primary_key=True),
        sa.Column("revision", sa.BigInteger, primary_key=True),
        sa.Column("enabled", sa.Boolean, nullable=False),
        sa.Column("rule_id", sa.String(160), nullable=False),
        sa.Column("authorization_id", sa.String(160), nullable=True),
        sa.Column("created_at_ms", sa.BigInteger, nullable=False),
        sa.CheckConstraint("revision>0", name="revision_positive"),
    )
    op.create_table(
        "brc_entry_regime_current",
        sa.Column("event_spec_id", sa.String(160), primary_key=True),
        sa.Column("revision", sa.BigInteger, nullable=False),
        sa.ForeignKeyConstraint(
            ["event_spec_id", "revision"],
            [
                "brc_entry_regime_revisions.event_spec_id",
                "brc_entry_regime_revisions.revision",
            ],
        ),
    )
    op.create_table(
        "brc_btc_ma50_current",
        sa.Column("exchange_instrument_id", sa.String(160), primary_key=True),
        sa.Column("latest_close_ms", sa.BigInteger, nullable=False),
        sa.Column("snapshot", JSONB, nullable=True),
        sa.Column("retry_not_before_ms", sa.BigInteger, nullable=False, server_default="0"),
    )
    op.create_table(
        "brc_entry_regime_evidence",
        sa.Column("phase", sa.String(160), primary_key=True),
        sa.Column("identity_key", sa.String(160), primary_key=True),
        sa.Column("ticket_id", sa.String(160), nullable=True),
        sa.Column("evidence", JSONB, nullable=False),
    )
    for event in (
        "event_spec:CPM-RO-001:CPM-LONG:v3",
        "event_spec:MI-001:MI-LONG:v3",
        "event_spec:MPG-001:MPG-LONG:v3",
    ):
        connection.execute(
            sa.text(
                "INSERT INTO brc_entry_regime_revisions VALUES(:event,1,false,'btc4h_ma50_long_v1',NULL,1)"
            ),
            {"event": event},
        )
        connection.execute(
            sa.text("INSERT INTO brc_entry_regime_current VALUES(:event,1)"),
            {"event": event},
        )
    connection.exec_driver_sql("""CREATE FUNCTION brc_guard_entry_regime_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'Entry regime lineage is immutable'; END; $$""")
    for table in ("brc_entry_regime_revisions", "brc_entry_regime_evidence"):
        connection.exec_driver_sql(
            f"CREATE TRIGGER entry_regime_immutable BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION brc_guard_entry_regime_immutable()"
        )


def downgrade():
    raise RuntimeError("Exit experiment schema is forward-only; fix-forward required")
