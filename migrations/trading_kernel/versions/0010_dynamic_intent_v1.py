"""Preserve first Dynamic intent across missed periods; no row or scope changes."""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from src.trading_kernel.infrastructure.generic_selection_source_provenance import (
    count_nonquiescent_source_vacuums,
)

revision: str = "0010_dynamic_intent_v1"
down_revision: str | None = "0009_capacity_policy_v0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _replace_function(signature: str, replacements: tuple[tuple[str, str], ...]) -> None:
    bind = op.get_bind()
    definition = bind.scalar(sa.text("SELECT pg_get_functiondef(to_regprocedure(:signature))"), {"signature": signature})
    if not isinstance(definition, str):
        raise TypeError(f"0010 source function missing: {signature}")
    for old, new in replacements:
        if definition.count(old) != 1:
            raise RuntimeError(f"0010 source function differs: {signature}")
        definition = definition.replace(old, new)
    bind.execute(sa.text(definition))


def upgrade() -> None:
    bind = op.get_bind()
    if bind.scalar(sa.text("SELECT version_num FROM alembic_version")) != down_revision:
        raise RuntimeError("0010 requires exact 0009 source")
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
    bind.execute(sa.text("LOCK TABLE " + ",".join(predicates) + ",brc_strategy_selection_control_current,brc_owner_authorizations,brc_strategy_entry_vacuums_current IN SHARE ROW EXCLUSIVE MODE"))
    for table, predicate in predicates.items():
        if bind.scalar(sa.text(f"SELECT EXISTS(SELECT 1 FROM {table} WHERE {predicate})")):
            raise RuntimeError(f"0010 requires flat quiescent source: {table}")
    if count_nonquiescent_source_vacuums(bind):
        raise RuntimeError("0010 requires quiescent source Vacuums")
    # All original authorization/epoch/version/atomic activation checks remain.
    # The frozen authorized period is an earliest boundary, never moved forward.
    _replace_function("brc_validate_generic_normal_binding()", (
        ("'effective_period_anchor_ms',a.period_anchor_ms)",
         "'effective_period_anchor_ms',(o.target_scope->>'effective_period_anchor_ms')::bigint)\n            AND (o.target_scope->>'effective_period_anchor_ms')::bigint <= a.period_anchor_ms"),
    ))
    _replace_function("brc_generic_first_pause_recovery_matches(text,text,bigint)", (
        ("c.pending_effective_period_anchor_ms=g.period_anchor_ms", "c.pending_effective_period_anchor_ms<=g.period_anchor_ms"),
    ))
    _replace_function("brc_generic_static_recovery_proof_matches(jsonb,bigint)", (
        ("c.pending_effective_period_anchor_ms IS DISTINCT FROM g.period_anchor_ms", "c.pending_effective_period_anchor_ms IS NULL OR c.pending_effective_period_anchor_ms>g.period_anchor_ms"),
        ("'effective_period_anchor_ms',g.period_anchor_ms)", "'effective_period_anchor_ms',c.pending_effective_period_anchor_ms)"),
    ))

    _replace_function("brc_validate_static_recovery_commit()", (
        ("AND selection_epoch_id IS NOT DISTINCT FROM CASE WHEN dynamic_recovery THEN a.selection_epoch_id ELSE NULL END\n              AND pending_selection_mode IS NULL AND pending_effective_period_anchor_ms IS NULL AND pending_authorization_id IS NULL",
         "AND selection_epoch_id=a.selection_epoch_id\n              AND ((dynamic_recovery AND pending_selection_mode IS NULL AND pending_effective_period_anchor_ms IS NULL AND pending_authorization_id IS NULL) OR (NOT dynamic_recovery AND pending_selection_mode='dynamic_selection' AND pending_authorization_id=p->>'failed_activation_authorization_id' AND pending_effective_period_anchor_ms<=a.period_anchor_ms))"),
    ))
    _replace_function("brc_generic_static_recovery_proof_matches(jsonb,bigint)", (
        ("OR source_authority.recovery_grant_proof IS NULL OR source_authority.selection_epoch_id=g.selection_epoch_id\n              OR source_authority.selection_control_version+1<>c.control_version",
         "OR source_authority.recovery_grant_proof IS NULL OR NOT ((source_authority.selection_epoch_id=g.selection_epoch_id AND source_authority.selection_control_version=c.control_version AND source_authority.recovery_grant_proof->>'failed_activation_authorization_id'=a.authorization_id) OR (source_authority.selection_epoch_id<>g.selection_epoch_id AND source_authority.selection_control_version+1=c.control_version AND source_authority.recovery_grant_proof->>'failed_activation_authorization_id'<>a.authorization_id))"),
        ("OR source_authority.recovery_grant_proof->>'failed_activation_authorization_id'=a.authorization_id", ""),
    ))
    _replace_function("brc_validate_authority_epoch_v1()", (
        ("OR source_authority_row.selection_epoch_id=NEW.selection_epoch_id\n                        OR source_authority_row.selection_control_version+2<>NEW.selection_control_version",
         "OR NOT ((source_authority_row.selection_epoch_id=NEW.selection_epoch_id AND source_authority_row.selection_control_version+1=NEW.selection_control_version AND source_authority_row.recovery_grant_proof->>'failed_activation_authorization_id'=NEW.activation_authorization_id) OR (source_authority_row.selection_epoch_id<>NEW.selection_epoch_id AND source_authority_row.selection_control_version+2=NEW.selection_control_version AND source_authority_row.recovery_grant_proof->>'failed_activation_authorization_id'<>NEW.activation_authorization_id))"),
        ("OR source_authority_row.recovery_grant_proof->>'failed_activation_authorization_id'=NEW.activation_authorization_id", ""),
    ))


def downgrade() -> None:
    raise RuntimeError("Dynamic intent migration requires fix-forward; downgrade is forbidden")
