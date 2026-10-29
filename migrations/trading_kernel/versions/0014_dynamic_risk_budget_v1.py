"""Flat forward-only dynamic risk budgets; initial effective baseline remains 2%."""

import hashlib
import json

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0014_dynamic_risk_budget_v1"
down_revision: str | None = "0013_owner_directional_risk_v1"
branch_labels = None
depends_on = None


def upgrade():
    c = op.get_bind()
    if c.scalar(sa.text("SELECT version_num FROM alembic_version")) != down_revision:
        raise RuntimeError("0014 requires exact 0013 source")
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
        "brc_directional_risk_controls": "pending_view IS NOT NULL",
    }
    c.execute(
        sa.text(
            "LOCK TABLE "
            + ",".join(gates)
            + ",brc_owner_policy_current IN SHARE ROW EXCLUSIVE MODE"
        )
    )
    for table, predicate in gates.items():
        if c.scalar(sa.text(f"SELECT EXISTS(SELECT 1 FROM {table} WHERE {predicate})")):
            raise RuntimeError(f"0014 requires quiescent source: {table}")
    from src.trading_kernel.infrastructure.generic_selection_source_provenance import (
        count_nonquiescent_source_vacuums,
    )

    if count_nonquiescent_source_vacuums(c, allow_paused_failed_generic=True):
        raise RuntimeError("0014 requires quiescent selection Vacuums")
    if c.scalar(
        sa.text("""SELECT EXISTS(SELECT 1 FROM brc_owner_policy_current WHERE
        max_ticket_stop_risk_fraction<>0.02 OR max_gross_stop_risk_fraction<>0.06
        OR directional_stop_risk_limit_fraction<>0.04 OR min_materialization_ratio<>0.50)""")
    ):
        raise RuntimeError("0014 source budget differs from approved default")
    op.add_column(
        "brc_directional_risk_controls",
        sa.Column("pending_baseline", sa.Numeric(38, 18)),
    )
    op.add_column(
        "brc_directional_risk_controls",
        sa.Column("pending_budget_request_id", sa.String(160)),
    )
    op.add_column(
        "brc_directional_risk_controls", sa.Column("pending_policy_version", sa.Integer)
    )
    op.create_check_constraint(
        "budget_pending_valid",
        "brc_directional_risk_controls",
        "COALESCE((pending_baseline IS NULL AND pending_budget_request_id IS NULL AND pending_policy_version IS NULL) OR (pending_baseline BETWEEN 0.02 AND 0.03 AND mod(pending_baseline,0.001)=0 AND pending_budget_request_id IS NOT NULL AND pending_policy_version>0 AND pending_view IS NULL),false)",
    )
    op.create_check_constraint(
        "dynamic_risk_budget_valid",
        "brc_owner_policy_current",
        "max_ticket_stop_risk_fraction BETWEEN 0.02 AND 0.03 AND mod(max_ticket_stop_risk_fraction,0.001)=0 AND max_gross_stop_risk_fraction=3*max_ticket_stop_risk_fraction AND directional_stop_risk_limit_fraction=2*max_ticket_stop_risk_fraction AND min_materialization_ratio=0.5",
    )
    op.add_column(
        "brc_directional_risk_rules", sa.Column("budget_contract", JSONB, nullable=True)
    )
    budget_contract = {
        "minimum": "0.020",
        "maximum": "0.030",
        "step": "0.001",
        "default": "0.020",
        "gross_multiplier": "3",
        "directional_multiplier": "2",
        "minimum_materialization": "0.50",
    }
    limits = {
        "unset": ["1", "1"],
        "bullish": ["1", "0.5"],
        "neutral": ["1", "1"],
        "bearish": ["0.5", "1"],
    }
    ids = c.scalar(
        sa.text(
            "SELECT event_spec_ids FROM brc_directional_risk_rules WHERE rule_id='owner-directional-risk:v1'"
        )
    )
    if ids is None:
        raise RuntimeError("0014 missing source directional rule")
    payload = {
        "rule_id": "owner-directional-risk:v2",
        "limits": limits,
        "event_spec_ids": ids,
        "budget_contract": budget_contract,
    }
    digest = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(
                payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode()
        ).hexdigest()
    )
    c.execute(
        sa.text(
            "INSERT INTO brc_directional_risk_rules(rule_id,rule_digest,limits,event_spec_ids,budget_contract) VALUES(:id,:digest,CAST(:limits AS jsonb),CAST(:events AS jsonb),CAST(:budget AS jsonb))"
        ),
        {
            "id": payload["rule_id"],
            "digest": digest,
            "limits": json.dumps(limits),
            "events": json.dumps(ids),
            "budget": json.dumps(budget_contract),
        },
    )
    c.execute(
        sa.text(
            "UPDATE brc_directional_risk_controls SET rule_id=:id,rule_digest=:digest,version=version+1"
        ),
        {"id": payload["rule_id"], "digest": digest},
    )

    c.exec_driver_sql("""CREATE FUNCTION brc_guard_risk_budget_v1() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE event_row public.brc_owner_policy_events%ROWTYPE; request_payload jsonb; previous_payload jsonb; previous_operation text;
    BEGIN
      IF (NEW.max_ticket_stop_risk_fraction,NEW.max_gross_stop_risk_fraction,NEW.directional_stop_risk_limit_fraction)
         IS NOT DISTINCT FROM (OLD.max_ticket_stop_risk_fraction,OLD.max_gross_stop_risk_fraction,OLD.directional_stop_risk_limit_fraction) THEN RETURN NEW; END IF;
      SELECT * INTO event_row FROM public.brc_owner_policy_events WHERE owner_policy_id=OLD.owner_policy_id AND policy_version=NEW.policy_version;
      SELECT payload INTO request_payload FROM public.brc_directional_risk_events WHERE event_id=event_row.payload->>'request_id' AND event_kind='budget_requested';
      SELECT operation,payload INTO previous_operation,previous_payload FROM public.brc_owner_policy_events WHERE owner_policy_id=OLD.owner_policy_id AND policy_version=OLD.policy_version;
      IF NEW.policy_version<>OLD.policy_version+1 OR NEW.updated_at_ms<OLD.updated_at_ms
        OR event_row.operation IS DISTINCT FROM 'owner_control_risk_budget'
        OR event_row.created_at_ms IS DISTINCT FROM NEW.updated_at_ms
        OR event_row.payload->>'source_policy_version' IS DISTINCT FROM OLD.policy_version::text
        OR (event_row.payload->>'baseline')::numeric IS DISTINCT FROM (request_payload->'request'->>'baseline')::numeric
        OR (request_payload->'request'->>'baseline')::numeric IS DISTINCT FROM NEW.max_ticket_stop_risk_fraction
        OR request_payload->'request'->>'owner_policy_id' IS DISTINCT FROM OLD.owner_policy_id
        OR request_payload->>'authentication_strength' IS DISTINCT FROM 'totp_step_up'
        OR (to_jsonb(NEW)-'policy_version'-'updated_at_ms'-'max_ticket_stop_risk_fraction'-'max_gross_stop_risk_fraction'-'directional_stop_risk_limit_fraction')
           IS DISTINCT FROM (to_jsonb(OLD)-'policy_version'-'updated_at_ms'-'max_ticket_stop_risk_fraction'-'max_gross_stop_risk_fraction'-'directional_stop_risk_limit_fraction')
      THEN RAISE EXCEPTION 'risk budget requires exact authenticated policy transition'; END IF;
      IF event_row.payload->>'resume_authorization_id' IS DISTINCT FROM
        (CASE WHEN NOT OLD.new_entry_submit_enabled THEN NULL WHEN previous_operation='owner_control_entry_resume' THEN previous_payload->>'authorization_id'
        WHEN previous_operation='owner_control_risk_budget' THEN previous_payload->>'resume_authorization_id' ELSE NULL END)
      OR event_row.payload->>'resume_policy_version' IS DISTINCT FROM
        (CASE WHEN NOT OLD.new_entry_submit_enabled THEN NULL WHEN previous_operation='owner_control_entry_resume' THEN OLD.policy_version::text
        WHEN previous_operation='owner_control_risk_budget' THEN previous_payload->>'resume_policy_version' ELSE NULL END)
      THEN RAISE EXCEPTION 'risk budget cannot invent owner resume'; END IF;
      RETURN NEW;
    END $$""")
    c.exec_driver_sql(
        "CREATE TRIGGER trg_risk_budget_v1 BEFORE UPDATE ON brc_owner_policy_current FOR EACH ROW EXECUTE FUNCTION brc_guard_risk_budget_v1()"
    )


def downgrade():
    raise RuntimeError("dynamic risk authority is forward-only; fix-forward required")
