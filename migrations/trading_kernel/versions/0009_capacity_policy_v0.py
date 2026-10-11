"""Install explicit strategy-side capacity without changing any Owner Policy."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from src.trading_kernel.infrastructure.generic_selection_source_provenance import (
    count_nonquiescent_source_vacuums,
)

revision: str = "0009_capacity_policy_v0"
down_revision: str | None = "0008_generic_dynamic_selection_v1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.scalar(sa.text("SELECT version_num FROM alembic_version")) != down_revision:
        raise RuntimeError("0009 requires exact 0008 source")
    predicates = {
        "brc_trade_tickets": "active_netting_domain_key IS NOT NULL OR terminal_at_ms IS NULL",
        "brc_trade_aggregates": "status NOT IN ('terminal','leverage_rejected','entry_rejected','entry_reconciled_absent')",
        "brc_positions_current": "quantity <> 0",
        "brc_budget_reservations": "status='active'",
        "brc_exchange_commands": "status IN ('prepared','claimed','dispatch_started','outcome_unknown')",
        "brc_runtime_incidents": "status='open'",
        "brc_strategy_universe_versions": "lifecycle_state IN ('warming','staged')",
        "brc_strategy_universe_materialization_generations": "lifecycle_state IN ('PENDING','DESIRED','DRAINING_ENTRY','MATERIALIZING','STAGED')",
        "brc_owner_control_operations_current": "state NOT IN ('completed','blocked')",
    }
    bind.execute(
        sa.text(
            "LOCK TABLE "
            + ",".join(predicates)
            + ",brc_owner_policy_current,brc_owner_policy_events,brc_capacity_claims,"
            "brc_strategy_entry_vacuums_current,brc_strategy_entry_vacuum_events,"
            "brc_strategy_entry_controls_current,brc_strategy_entry_control_events,"
            "brc_strategy_selection_control_current IN SHARE ROW EXCLUSIVE MODE"
        )
    )
    for table, predicate in predicates.items():
        if bind.scalar(
            sa.text(f"SELECT EXISTS(SELECT 1 FROM {table} WHERE {predicate})")
        ):
            raise RuntimeError(f"0009 requires flat quiescent source: {table}")
    if count_nonquiescent_source_vacuums(bind):
        raise RuntimeError("0009 requires flat quiescent source: brc_strategy_entry_vacuums_current")
    # NULL is explicit absence of an extra gate, not a fabricated old limit.
    # No UPDATE, revision, strategy resume or capacity activation occurs here.
    op.add_column(
        "brc_owner_policy_current",
        sa.Column("max_same_strategy_side", sa.Integer(), nullable=True),
    )
    op.create_check_constraint(
        "strategy_side_limit_positive",
        "brc_owner_policy_current",
        "max_same_strategy_side IS NULL OR max_same_strategy_side > 0",
    )
    op.add_column(
        "brc_capacity_claims",
        sa.Column("max_same_strategy_side", sa.Integer(), nullable=True),
    )
    op.add_column(
        "brc_capacity_claims",
        sa.Column(
            "active_strategy_side_ticket_count_at_claim", sa.Integer(), nullable=True
        ),
    )
    op.create_check_constraint(
        "strategy_side_evidence_valid",
        "brc_capacity_claims",
        "(max_same_strategy_side IS NULL AND active_strategy_side_ticket_count_at_claim IS NULL) OR "
        "(max_same_strategy_side IS NOT NULL AND active_strategy_side_ticket_count_at_claim IS NOT NULL "
        "AND max_same_strategy_side > 0 AND active_strategy_side_ticket_count_at_claim >= 0 "
        "AND active_strategy_side_ticket_count_at_claim < max_same_strategy_side)",
    )
    op.create_index(
        "ix_brc_trade_tickets_active_strategy_side",
        "brc_trade_tickets",
        ["venue_id", "account_id", "strategy_group_id", "position_side"],
        postgresql_where=sa.text("terminal_at_ms IS NULL"),
    )
    op.execute(sa.text("""
        CREATE FUNCTION brc_guard_capacity_release_v0() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE release_event public.brc_owner_policy_events%ROWTYPE; actual_commit text;
        BEGIN
          IF NEW.max_same_strategy_side IS NOT DISTINCT FROM OLD.max_same_strategy_side THEN
            RETURN NEW;
          END IF;
          SELECT * INTO release_event FROM public.brc_owner_policy_events
            WHERE owner_policy_id=OLD.owner_policy_id AND policy_version=NEW.policy_version;
          SELECT metadata_value INTO actual_commit FROM public.brc_schema_metadata
            WHERE metadata_key='runtime_commit';
          IF OLD.max_same_strategy_side IS NOT NULL OR NEW.max_same_strategy_side IS DISTINCT FROM 2
            OR (OLD.family_ticket_limits->'long_continuation') IS DISTINCT FROM '1'::jsonb
            OR NEW.family_ticket_limits IS DISTINCT FROM jsonb_build_object('long_continuation',2,'opening_range',2,'rally_failure_short',1)
            OR NEW.policy_version <> OLD.policy_version+1 OR NEW.new_entry_submit_enabled
            OR NEW.updated_at_ms < OLD.updated_at_ms
            OR (to_jsonb(NEW)-'max_same_strategy_side'-'family_ticket_limits'-'policy_version'-'updated_at_ms')
              IS DISTINCT FROM (to_jsonb(OLD)-'max_same_strategy_side'-'family_ticket_limits'-'policy_version'-'updated_at_ms')
            OR release_event.operation IS DISTINCT FROM 'compatible_capacity_policy_v0'
            OR release_event.created_at_ms IS DISTINCT FROM NEW.updated_at_ms
            OR release_event.payload->'source_policy_version' IS DISTINCT FROM to_jsonb(OLD.policy_version)
            OR release_event.payload->'policy_version' IS DISTINCT FROM to_jsonb(NEW.policy_version)
            OR release_event.payload->'max_same_strategy_side' IS DISTINCT FROM '2'::jsonb
            OR release_event.payload->'family_ticket_limits' IS DISTINCT FROM NEW.family_ticket_limits
            OR release_event.payload->>'target_commit' IS DISTINCT FROM actual_commit
            OR release_event.payload->>'target_schema_revision' IS DISTINCT FROM '0009_capacity_policy_v0'
            OR NOT EXISTS(SELECT 1 FROM public.brc_schema_metadata WHERE metadata_key='schema_revision'
              AND metadata_value='0009_capacity_policy_v0' AND updated_at_ms=NEW.updated_at_ms)
            OR NOT EXISTS(SELECT 1 FROM public.alembic_version WHERE version_num='0009_capacity_policy_v0')
            OR NOT EXISTS(SELECT 1 FROM public.brc_strategy_entry_controls_current
              WHERE strategy_group_id='SOR-001' AND entry_state='paused')
            OR EXISTS(SELECT 1 FROM public.brc_trade_tickets WHERE terminal_at_ms IS NULL OR active_netting_domain_key IS NOT NULL)
            OR EXISTS(SELECT 1 FROM public.brc_budget_reservations WHERE status='active')
            OR EXISTS(SELECT 1 FROM public.brc_positions_current WHERE quantity<>0)
            OR EXISTS(SELECT 1 FROM public.brc_exchange_commands WHERE status IN ('prepared','claimed','dispatch_started','outcome_unknown'))
            OR EXISTS(SELECT 1 FROM public.brc_runtime_incidents WHERE status='open') THEN
            RAISE EXCEPTION 'Capacity release authority does not match exact fenced flat transition';
          END IF;
          RETURN NEW;
        END; $$
    """))
    op.execute(sa.text("CREATE TRIGGER trg_capacity_release_v0 BEFORE UPDATE ON brc_owner_policy_current FOR EACH ROW EXECUTE FUNCTION brc_guard_capacity_release_v0()"))
    op.create_index("ix_brc_budget_reservations_active_account", "brc_budget_reservations",
        ["venue_id", "account_id", "ticket_id"], postgresql_where=sa.text("status='active'"))
    op.create_index("ix_brc_exchange_commands_unresolved_ticket", "brc_exchange_commands",
        ["ticket_id"], postgresql_where=sa.text("status IN ('prepared','claimed','dispatch_started','outcome_unknown')"))


def downgrade() -> None:
    raise RuntimeError("0009_capacity_policy_v0 is fix-forward only")
