"""Flat, forward-only Owner directional-risk authority; no activation."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0013_owner_directional_risk_v1"
down_revision: str | None = "0012_generic_signal_path_v1"
branch_labels = None
depends_on = None

metadata = sa.MetaData(
    naming_convention={
        "ix": "ix_%(table_name)s_%(column_0_N_name)s",
        "uq": "uq_%(table_name)s_%(column_0_N_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }
)
ID = sa.String(160)
SHORT_TEXT = sa.String(96)
MONEY = sa.Numeric(38, 18)
# Referenced source table is used only to resolve the FK, never created here.
sa.Table(
    "brc_exchange_commands", metadata, sa.Column("command_id", ID, primary_key=True)
)

directional_risk_rules = sa.Table(
    "brc_directional_risk_rules",
    metadata,
    sa.Column("rule_id", ID, primary_key=True),
    sa.Column("rule_digest", ID, nullable=False),
    sa.Column("limits", JSONB, nullable=False),
    sa.Column("event_spec_ids", JSONB, nullable=False),
)
directional_risk_controls = sa.Table(
    "brc_directional_risk_controls",
    metadata,
    sa.Column("venue_id", ID, primary_key=True),
    sa.Column("account_id", ID, primary_key=True),
    sa.Column("version", sa.BigInteger, nullable=False),
    sa.Column("view", SHORT_TEXT, nullable=False),
    sa.Column(
        "rule_id",
        ID,
        sa.ForeignKey("brc_directional_risk_rules.rule_id"),
        nullable=False,
    ),
    sa.Column("rule_digest", ID, nullable=False),
    sa.Column("effective_at_ms", sa.BigInteger, nullable=False),
    sa.Column("pending_view", SHORT_TEXT),
    sa.Column("pending_request_id", ID),
    sa.Column("requested_at_ms", sa.BigInteger),
    sa.CheckConstraint("version>0 AND effective_at_ms>0", name="positive"),
    sa.CheckConstraint(
        "view IN ('unset','bullish','neutral','bearish')", name="view_valid"
    ),
    sa.CheckConstraint(
        "COALESCE((pending_view IS NULL AND pending_request_id IS NULL) OR (pending_view IN ('bullish','neutral','bearish') AND pending_request_id IS NOT NULL AND requested_at_ms>0),false)",
        name="pending_valid",
    ),
)
directional_risk_events = sa.Table(
    "brc_directional_risk_events",
    metadata,
    sa.Column("event_id", ID, primary_key=True),
    sa.Column("venue_id", ID, nullable=False),
    sa.Column("account_id", ID, nullable=False),
    sa.Column("event_kind", SHORT_TEXT, nullable=False),
    sa.Column("payload", JSONB, nullable=False),
    sa.Column("occurred_at_ms", sa.BigInteger, nullable=False),
)
directional_risk_admissions = sa.Table(
    "brc_directional_risk_admissions",
    metadata,
    sa.Column("signal_event_id", ID, primary_key=True),
    sa.Column("ticket_id", ID, nullable=True),
    sa.Column("control", JSONB, nullable=False),
    sa.Column("directional_risk", MONEY, nullable=False),
    sa.Column("effective_limit", MONEY, nullable=False),
    sa.Column("wallet_balance", MONEY, nullable=False),
    sa.Column("outcome", SHORT_TEXT, nullable=False),
    sa.Column("observed_at_ms", sa.BigInteger, nullable=False),
)
entry_send_authorizations = sa.Table(
    "brc_entry_send_authorizations",
    metadata,
    sa.Column(
        "command_id",
        ID,
        sa.ForeignKey("brc_exchange_commands.command_id"),
        primary_key=True,
    ),
    sa.Column("venue_id", ID, nullable=False),
    sa.Column("account_id", ID, nullable=False),
    sa.Column("worker_id", ID, nullable=False),
    sa.Column("authorized_at_ms", sa.BigInteger, nullable=False),
    sa.Column("expires_at_ms", sa.BigInteger, nullable=False),
    sa.Column("control", JSONB, nullable=True),
    sa.Column("completed_at_ms", sa.BigInteger),
    sa.CheckConstraint(
        "authorized_at_ms>0 AND expires_at_ms>authorized_at_ms", name="window_valid"
    ),
)
sa.Index(
    "ix_brc_entry_send_authorizations_pending",
    entry_send_authorizations.c.venue_id,
    entry_send_authorizations.c.account_id,
    postgresql_where=entry_send_authorizations.c.completed_at_ms.is_(None),
)


def upgrade():
    c = op.get_bind()
    if c.scalar(sa.text("SELECT version_num FROM alembic_version")) != down_revision:
        raise RuntimeError("0013 requires exact 0012 source")
    gates = {
        "brc_trade_tickets": "terminal_at_ms IS NULL OR active_netting_domain_key IS NOT NULL",
        "brc_positions_current": "quantity<>0",
        "brc_budget_reservations": "status='active'",
        "brc_exchange_commands": "status IN ('prepared','claimed','outcome_unknown')",
        "brc_runtime_incidents": "status='open'",
        "brc_trade_aggregates": "status NOT IN ('terminal','leverage_rejected','entry_rejected','entry_reconciled_absent')",
        "brc_strategy_universe_versions": "lifecycle_state IN ('warming','staged')",
        "brc_strategy_universe_materialization_generations": "lifecycle_state IN ('PENDING','DESIRED','DRAINING_ENTRY','MATERIALIZING','STAGED')",
        "brc_owner_control_operations_current": "state NOT IN ('completed','blocked')",
        "brc_entry_lane_current": "status<>'idle' OR ticket_id IS NOT NULL OR signal_event_id IS NOT NULL",
    }
    c.execute(sa.text("LOCK TABLE " + ",".join(gates) + " IN SHARE ROW EXCLUSIVE MODE"))
    for table, predicate in gates.items():
        if c.scalar(sa.text(f"SELECT EXISTS(SELECT 1 FROM {table} WHERE {predicate})")):
            raise RuntimeError(f"0013 requires flat quiescent source: {table}")
    from src.trading_kernel.infrastructure.generic_selection_source_provenance import (
        count_nonquiescent_source_vacuums,
    )

    if count_nonquiescent_source_vacuums(c, allow_paused_failed_generic=True):
        raise RuntimeError("0013 requires quiescent selection Vacuums")
    for table in (
        directional_risk_rules,
        directional_risk_controls,
        directional_risk_events,
        directional_risk_admissions,
        entry_send_authorizations,
    ):
        table.create(c)
    op.create_index("ix_brc_capacity_claims_account_latest", "brc_capacity_claims", ["venue_id", "account_id", sa.text("created_at_ms DESC"), "capacity_claim_id"])
    # Installation freezes the rule and explicit unset controls, never an Owner choice.
    import hashlib
    import json

    limits = {
        "unset": ["0.04", "0.04"],
        "bullish": ["0.04", "0.02"],
        "neutral": ["0.04", "0.04"],
        "bearish": ["0.02", "0.04"],
    }
    event_spec_ids = sorted([
        "event_spec:CPM-RO-001:CPM-LONG:v3", "event_spec:MPG-001:MPG-LONG:v3",
        "event_spec:MI-001:MI-LONG:v3", "event_spec:BRF2-001:BRF2-SHORT:v3",
        "event_spec:SOR-1H-001:SOR-1H-LONG:v1", "event_spec:SOR-1H-001:SOR-1H-SHORT:v1",
    ])
    payload = {"rule_id": "owner-directional-risk:v1", "limits": limits, "event_spec_ids": event_spec_ids}
    digest = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(
                payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode()
        ).hexdigest()
    )
    c.execute(
        directional_risk_rules.insert().values(
            rule_id=payload["rule_id"], rule_digest=digest, limits=limits, event_spec_ids=event_spec_ids
        )
    )
    c.execute(
        sa.text(
        "INSERT INTO brc_directional_risk_controls(venue_id,account_id,version,view,rule_id,rule_digest,effective_at_ms) SELECT venue_id,account_id,1,'unset',:rule,:digest,GREATEST(1,(extract(epoch from clock_timestamp())*1000)::bigint) FROM (SELECT DISTINCT venue_id,account_id FROM brc_runtime_profiles) accounts"
        ),
        {"rule": payload["rule_id"], "digest": digest},
    )
    c.exec_driver_sql(
        """CREATE FUNCTION brc_directional_immutable() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'directional risk authority history is immutable'; END $$"""
    )
    for table in (
        directional_risk_rules,
        directional_risk_events,
        directional_risk_admissions,
    ):
        c.exec_driver_sql(
            f"CREATE TRIGGER {table.name}_immutable BEFORE UPDATE OR DELETE ON {table.name} FOR EACH ROW EXECUTE FUNCTION brc_directional_immutable()"
        )
    c.exec_driver_sql("""CREATE FUNCTION brc_entry_send_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP='DELETE' THEN RAISE EXCEPTION 'ENTRY send authority is immutable'; END IF;
      IF (to_jsonb(NEW)-'completed_at_ms') IS DISTINCT FROM (to_jsonb(OLD)-'completed_at_ms')
         OR OLD.completed_at_ms IS NOT NULL OR NEW.completed_at_ms IS NULL
      THEN RAISE EXCEPTION 'ENTRY send authority is immutable'; END IF;
      RETURN NEW;
    END $$""")
    c.exec_driver_sql("CREATE TRIGGER brc_entry_send_authorizations_immutable BEFORE UPDATE OR DELETE ON brc_entry_send_authorizations FOR EACH ROW EXECUTE FUNCTION brc_entry_send_immutable()")


def downgrade():
    raise RuntimeError("directional risk authority is forward-only; fix-forward required")
