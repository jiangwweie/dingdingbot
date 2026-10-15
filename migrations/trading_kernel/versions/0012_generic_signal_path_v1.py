"""Forward-only, flat addition of disabled Signal-owned price-path research."""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from src.trading_kernel.infrastructure.generic_selection_source_provenance import (
    count_nonquiescent_source_vacuums,
)

revision: str = "0012_generic_signal_path_v1"
down_revision: str | None = "0011_orb_session_1h_v1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT version_num FROM alembic_version")) != down_revision:
        raise RuntimeError("0012 requires exact 0011 source")
    flat = {
        "brc_trade_tickets": "terminal_at_ms IS NULL OR active_netting_domain_key IS NOT NULL",
        "brc_positions_current": "quantity<>0",
        "brc_budget_reservations": "status='active'",
        "brc_exchange_commands": "status IN ('prepared','claimed','dispatch_started','outcome_unknown')",
        "brc_runtime_incidents": "status='open'",
        "brc_trade_aggregates": "status NOT IN ('terminal','leverage_rejected','entry_rejected','entry_reconciled_absent')",
        "brc_strategy_universe_versions": "lifecycle_state IN ('warming','staged')",
        "brc_strategy_universe_materialization_generations": "lifecycle_state IN ('PENDING','DESIRED','DRAINING_ENTRY','MATERIALIZING','STAGED')",
        "brc_owner_control_operations_current": "state NOT IN ('completed','blocked')",
        "brc_entry_lane_current": "status<>'idle' OR ticket_id IS NOT NULL OR signal_event_id IS NOT NULL",
    }
    connection.execute(sa.text("LOCK TABLE " + ",".join((*flat, "brc_shadow_outcomes_current")) + " IN SHARE ROW EXCLUSIVE MODE"))
    for table, predicate in flat.items():
        if connection.scalar(sa.text(f"SELECT EXISTS(SELECT 1 FROM {table} WHERE {predicate})")):
            raise RuntimeError(f"0012 requires flat source: {table}")
    if count_nonquiescent_source_vacuums(connection, allow_paused_failed_generic=True):
        raise RuntimeError("0012 requires quiescent selection Vacuums")
    table = "brc_shadow_outcomes_current"
    op.add_column(table, sa.Column("reference_at_ms", sa.BigInteger(), nullable=True))
    op.add_column(table, sa.Column("price_basis", sa.String(96), nullable=True))
    op.add_column(table, sa.Column("path_spec_digest", sa.String(160), nullable=True))
    op.add_column(table, sa.Column("source_runtime_commit", sa.String(160), nullable=True))
    op.add_column(table, sa.Column("path_metrics", JSONB(), nullable=True))
    op.add_column(table, sa.Column("last_attempted_at_ms", sa.BigInteger(), nullable=True))
    op.add_column(table, sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column(table, sa.Column("next_attempt_at_ms", sa.BigInteger(), nullable=True))
    op.add_column(table, sa.Column("retry_deadline_ms", sa.BigInteger(), nullable=True))
    op.drop_constraint("ck_brc_shadow_outcomes_current_evaluation_kind_valid", table, type_="check")
    op.create_check_constraint("ck_brc_shadow_outcomes_current_evaluation_kind_valid", table,
        "evaluation_kind IN ('fixed_horizon_excursion_v1','sor_path_observation_v1','generic_signal_path_v1')")
    op.drop_constraint("ck_brc_shadow_outcomes_current_source_kind_valid", table, type_="check")
    op.create_check_constraint("ck_brc_shadow_outcomes_current_source_kind_valid", table,
        "COALESCE(((source_kind='portfolio_rejection' AND admission_decision_id IS NOT NULL AND evaluation_kind='fixed_horizon_excursion_v1') OR "
        "(source_kind='strategy_observation' AND admission_decision_id IS NULL AND evaluation_kind='sor_path_observation_v1') OR "
        "(source_kind='signal_path' AND admission_decision_id IS NULL AND evaluation_kind='generic_signal_path_v1' "
        "AND timeframe='1h' AND price_basis='signal_closed_bar' AND reference_at_ms=horizon_start_ms "
        "AND path_spec_digest ~ '^sha256:[0-9a-f]{64}$' AND source_runtime_commit IS NOT NULL "
        "AND retry_deadline_ms>horizon_end_ms "
        "AND next_attempt_at_ms>=horizon_end_ms AND next_attempt_at_ms<=retry_deadline_ms)),false)")
    op.drop_constraint("ck_brc_shadow_outcomes_current_projection_shape_valid", table, type_="check")
    op.create_check_constraint("ck_brc_shadow_outcomes_current_projection_shape_valid", table,
        "(status='claimed' AND claim_owner IS NOT NULL AND claim_token IS NOT NULL AND lease_until_ms IS NOT NULL "
        "AND completed_at_ms IS NULL AND max_favorable_price IS NULL AND max_adverse_price IS NULL AND mfe_r IS NULL "
        "AND mae_r IS NULL AND observed_through_ms IS NULL AND completion_reason IS NULL AND first_path IS NULL "
        "AND first_path_at_ms IS NULL AND observed_bar_count IS NULL AND path_metrics IS NULL) OR "
        "(status='pending' AND claim_owner IS NULL AND claim_token IS NULL AND lease_until_ms IS NULL "
        "AND completed_at_ms IS NULL AND max_favorable_price IS NULL AND max_adverse_price IS NULL AND mfe_r IS NULL "
        "AND mae_r IS NULL AND observed_through_ms IS NULL AND completion_reason IS NULL AND first_path IS NULL "
        "AND first_path_at_ms IS NULL AND observed_bar_count IS NULL AND path_metrics IS NULL) OR "
        "(status='completed' AND claim_owner IS NULL AND claim_token IS NULL AND lease_until_ms IS NULL "
        "AND completed_at_ms IS NOT NULL AND max_favorable_price IS NOT NULL AND max_adverse_price IS NOT NULL "
        "AND mfe_r IS NOT NULL AND mae_r IS NOT NULL AND observed_through_ms IS NOT NULL AND completion_reason IS NOT NULL "
        "AND ((evaluation_kind='fixed_horizon_excursion_v1' AND first_path IS NULL AND first_path_at_ms IS NULL "
        "AND observed_bar_count IS NULL AND path_metrics IS NULL) OR "
        "(evaluation_kind='sor_path_observation_v1' AND first_path IS NOT NULL AND first_path_at_ms IS NOT NULL "
        "AND observed_bar_count>0 AND path_metrics IS NULL) OR "
        "(evaluation_kind='generic_signal_path_v1' AND first_path IS NULL AND first_path_at_ms IS NULL "
        "AND observed_bar_count IS NOT NULL AND observed_bar_count>0 AND path_metrics IS NOT NULL AND jsonb_typeof(path_metrics)='object' AND octet_length(path_metrics::text)<=4096 "
        "AND COALESCE(path_metrics ?& ARRAY['levels','initial_stop_first_touch_at_ms','max_favorable_at_ms','max_adverse_at_ms'],false) "
        "AND COALESCE((path_metrics->'levels') ?& ARRAY['1R','3R','5R'],false)))) OR "
        "(status='unavailable' AND claim_owner IS NULL AND claim_token IS NULL AND lease_until_ms IS NULL "
        "AND completed_at_ms IS NOT NULL AND max_favorable_price IS NULL AND max_adverse_price IS NULL AND mfe_r IS NULL "
        "AND mae_r IS NULL AND observed_through_ms IS NULL AND completion_reason IS NOT NULL "
        "AND first_path IS NULL AND first_path_at_ms IS NULL AND observed_bar_count IS NULL AND path_metrics IS NULL)")
    op.create_check_constraint("ck_brc_shadow_outcomes_current_retry_bounds", table,
        "attempt_count>=0 AND attempt_count<=4 AND (source_kind='signal_path' OR "
        "(attempt_count=0 AND next_attempt_at_ms IS NULL AND retry_deadline_ms IS NULL AND reference_at_ms IS NULL "
        "AND price_basis IS NULL AND path_spec_digest IS NULL AND source_runtime_commit IS NULL "
        "AND path_metrics IS NULL))")
    connection.exec_driver_sql("""CREATE FUNCTION brc_guard_signal_path_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF OLD.source_kind='signal_path' THEN
        IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Signal path identity is immutable'; END IF;
        IF ROW(NEW.shadow_outcome_id,NEW.signal_event_id,NEW.admission_decision_id,NEW.source_kind,
          NEW.evaluation_kind,NEW.exchange_instrument_id,NEW.position_side,NEW.timeframe,
          NEW.entry_reference_price,NEW.initial_stop_price,NEW.initial_risk_per_unit,
          NEW.horizon_start_ms,NEW.horizon_end_ms,NEW.created_at_ms,NEW.reference_at_ms,
          NEW.price_basis,NEW.path_spec_digest,NEW.source_runtime_commit,NEW.retry_deadline_ms)
          IS DISTINCT FROM
          ROW(OLD.shadow_outcome_id,OLD.signal_event_id,OLD.admission_decision_id,OLD.source_kind,
          OLD.evaluation_kind,OLD.exchange_instrument_id,OLD.position_side,OLD.timeframe,
          OLD.entry_reference_price,OLD.initial_stop_price,OLD.initial_risk_per_unit,
          OLD.horizon_start_ms,OLD.horizon_end_ms,OLD.created_at_ms,OLD.reference_at_ms,
          OLD.price_basis,OLD.path_spec_digest,OLD.source_runtime_commit,OLD.retry_deadline_ms)
        THEN RAISE EXCEPTION 'Signal path frozen inputs are immutable'; END IF;
        IF OLD.status IN ('completed','unavailable') AND NEW IS DISTINCT FROM OLD
        THEN RAISE EXCEPTION 'Signal path terminal evidence is immutable'; END IF;
      END IF;
      IF TG_OP='DELETE' THEN RETURN OLD; END IF;
      RETURN NEW;
    END; $$""")
    connection.execute(sa.text("CREATE TRIGGER trg_brc_signal_path_immutable BEFORE UPDATE OR DELETE "
        "ON brc_shadow_outcomes_current FOR EACH ROW EXECUTE FUNCTION brc_guard_signal_path_immutable()"))
    op.create_index("ix_brc_shadow_signal_path_due",table,["status","last_attempted_at_ms","next_attempt_at_ms","horizon_end_ms"])
    op.create_table("brc_research_collection_control",
        sa.Column("control_id",sa.String(160),primary_key=True),
        sa.Column("enabled",sa.Boolean(),nullable=False),
        sa.Column("daily_limit",sa.Integer(),nullable=False),
        sa.Column("control_version",sa.Integer(),nullable=False),
        sa.CheckConstraint("control_id='generic_signal_path_v1' AND daily_limit BETWEEN 0 AND 1000 AND control_version>0 AND (NOT enabled OR daily_limit>0)",name="ck_brc_research_collection_control_bounds"))
    op.create_table("brc_research_collection_events",
        sa.Column("event_id",sa.String(160),primary_key=True),
        sa.Column("control_version",sa.Integer(),nullable=False),
        sa.Column("enabled",sa.Boolean(),nullable=False),
        sa.Column("daily_limit",sa.Integer(),nullable=False),
        sa.Column("owner_identity",sa.String(160),nullable=False),
        sa.Column("reason",sa.String(512),nullable=False),
        sa.Column("occurred_at_ms",sa.BigInteger(),nullable=False),
        sa.UniqueConstraint("control_version"),
        sa.CheckConstraint("control_version>1 AND daily_limit BETWEEN 0 AND 1000 AND length(trim(reason))>0",name="ck_brc_research_collection_events_bounds"))
    connection.execute(sa.text("CREATE TRIGGER trg_brc_research_collection_events_immutable "
        "BEFORE UPDATE OR DELETE ON brc_research_collection_events "
        "FOR EACH ROW EXECUTE FUNCTION brc_reject_immutable_selection_fact_mutation()"))
    op.create_table("brc_research_collection_daily",
        sa.Column("day_start_ms",sa.BigInteger(),primary_key=True),
        sa.Column("admitted_count",sa.Integer(),nullable=False),
        sa.Column("skipped_count",sa.Integer(),nullable=False),
        sa.Column("coverage_counts",JSONB(),nullable=False,server_default=sa.text("'{}'::jsonb")),
        sa.CheckConstraint("jsonb_typeof(coverage_counts)='object'",name="ck_brc_research_collection_daily_coverage_shape"),
        sa.CheckConstraint("day_start_ms>=0 AND day_start_ms%86400000=0 AND admitted_count>=0 AND skipped_count>=0",name="ck_brc_research_collection_daily_counts"))
    connection.execute(sa.text("INSERT INTO brc_research_collection_control(control_id,enabled,daily_limit,control_version) VALUES ('generic_signal_path_v1',false,0,1)"))


def downgrade() -> None:
    raise RuntimeError("Trading Kernel schema is forward-only; use fix-forward")
