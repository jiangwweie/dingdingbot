"""Persist exact external observation and conservative manual risk evidence."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0017_app_management_observation"
down_revision: str | None = "0016_app_manual_takeover_v1"
branch_labels = None
depends_on = None


def upgrade():
    c = op.get_bind()
    if c.scalar(sa.text("SELECT version_num FROM alembic_version")) != down_revision:
        raise RuntimeError("0017 exact source required")
    c.execute(
        sa.text(
            "LOCK TABLE brc_trade_tickets,brc_exchange_commands,brc_positions_current,brc_owner_policy_current IN SHARE ROW EXCLUSIVE MODE"
        )
    )
    for table, where in {
        "brc_trade_tickets": "terminal_at_ms IS NULL",
        "brc_positions_current": "quantity<>0",
        "brc_exchange_commands": "status IN ('prepared','claimed','dispatch_started','outcome_unknown')",
        "brc_owner_policy_current": "new_entry_submit_enabled",
    }.items():
        if c.scalar(sa.text(f"SELECT EXISTS(SELECT 1 FROM {table} WHERE {where})")):
            raise RuntimeError("0017 requires flat paused source")
    for name, typ, nullable, default in [
        ("management_observed_at_ms", sa.BigInteger(), True, None),
        ("manual_risk_at_stop", sa.Numeric(38, 18), True, None),
        ("manual_risk_reason", sa.String(512), True, None),
        ("management_orders", JSONB(), False, sa.text("'[]'::jsonb")),
    ]:
        op.add_column(
            "brc_trade_aggregates",
            sa.Column(name, typ, nullable=nullable, server_default=default),
        )
    op.create_table(
        "brc_management_order_evidence",
        sa.Column("evidence_id", sa.String(160), primary_key=True),
        sa.Column(
            "ticket_id",
            sa.String(160),
            sa.ForeignKey("brc_trade_tickets.ticket_id"),
            nullable=False,
        ),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("observed_at_ms", sa.BigInteger(), nullable=False),
    )
    op.create_index(
        "ix_brc_management_order_evidence_ticket_id_observed_at_ms",
        "brc_management_order_evidence",
        ["ticket_id", "observed_at_ms"],
    )
    op.create_table(
        "brc_management_observation_current",
        sa.Column(
            "ticket_id",
            sa.String(160),
            sa.ForeignKey("brc_trade_tickets.ticket_id"),
            primary_key=True,
        ),
        sa.Column("covered_until_ms", sa.BigInteger(), nullable=False),
        sa.Column("facts_complete", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.String(512)),
        sa.Column("updated_at_ms", sa.BigInteger(), nullable=False),
    )
    # The same instrument cannot own two nonterminal directions in this product.
    op.create_index(
        "uq_brc_app_active_instrument",
        "brc_trade_tickets",
        ["venue_id", "account_id", "exchange_instrument_id"],
        unique=True,
        postgresql_where=sa.text("terminal_at_ms IS NULL"),
    )
    c.exec_driver_sql(
        """CREATE FUNCTION brc_management_evidence_immutable() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'management evidence is append-only'; END; $$"""
    )
    c.exec_driver_sql(
        "CREATE TRIGGER trg_management_evidence_immutable BEFORE UPDATE OR DELETE ON brc_management_order_evidence FOR EACH ROW EXECUTE FUNCTION brc_management_evidence_immutable()"
    )

    # Clearing REVIEW is distinct from irreversible MANUAL and needs full-history evidence.
    c.exec_driver_sql("""CREATE OR REPLACE FUNCTION brc_validate_management_event() RETURNS trigger LANGUAGE plpgsql AS $$
 BEGIN
 IF NEW.management_revision=OLD.management_revision THEN RETURN NULL; END IF;
 IF NEW.management_mode='AUTO' AND OLD.management_mode='REVIEW_REQUIRED' AND OLD.management_reason IN ('collector_gap','order_history_incomplete_or_command_unknown','kernel_order_not_matched_to_command','known_order_creation_time_or_terms_drift') AND EXISTS (
 SELECT 1 FROM brc_trade_events e JOIN brc_trade_tickets t USING(ticket_id)
 WHERE e.ticket_id=NEW.ticket_id AND e.sequence=NEW.last_event_sequence AND e.event_type='ManagementReviewCleared'
 AND (e.payload->>'coverage_from_ms')::bigint<=t.created_at_ms AND (e.payload->>'coverage_until_ms')::bigint<=e.occurred_at_ms)
 THEN RETURN NULL; END IF;
 IF NEW.management_mode NOT IN ('MANUAL','REVIEW_REQUIRED') OR NOT EXISTS (
 SELECT 1 FROM brc_trade_events e WHERE e.ticket_id=NEW.ticket_id AND e.sequence=NEW.last_event_sequence
 AND e.event_type=CASE WHEN NEW.management_mode='MANUAL' THEN 'ManualTakeoverConfirmed' ELSE 'ManagementReviewRequired' END
 AND e.payload->>'evidence_id'=NEW.management_evidence_id AND e.payload->>'reason'=NEW.management_reason
 AND (NEW.management_mode<>'MANUAL' OR e.occurred_at_ms=NEW.manual_takeover_at_ms))
 THEN RAISE EXCEPTION 'management requires atomic evidence event'; END IF;
 RETURN NULL; END; $$""")


def downgrade():
    raise RuntimeError("management observations are forward-only")
