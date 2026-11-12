"""Freeze wallet-based initial allocation; preserve all old terminal evidence."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0022_wallet_margin_allocation"
down_revision: str = "0021_manual_operational_closure"
branch_labels = None
depends_on = None


def upgrade():
    c = op.get_bind()
    c.exec_driver_sql(
        "LOCK TABLE brc_trade_tickets, brc_capacity_claims, brc_exchange_commands, brc_positions_current, brc_owner_policy_current IN SHARE ROW EXCLUSIVE MODE"
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
                "0022 requires stopped flat terminal-clean paused source"
            )
    op.add_column(
        "brc_owner_policy_current",
        sa.Column(
            "margin_allocation_contract",
            sa.String(96),
            nullable=False,
            server_default="wallet_allocation_v1",
        ),
    )
    op.create_check_constraint(
        "ck_brc_policy_margin_contract",
        "brc_owner_policy_current",
        "margin_allocation_contract='wallet_allocation_v1'",
    )
    # NULL identifies preserved terminal history; never invent an allocation for it.
    op.add_column(
        "brc_capacity_claims", sa.Column("margin_allocation", JSONB, nullable=True)
    )
    op.create_check_constraint(
        "ck_brc_claim_allocation_contract",
        "brc_capacity_claims",
        "margin_allocation IS NULL OR (jsonb_typeof(margin_allocation)='object' AND margin_allocation->>'contract'='wallet_allocation_v1')",
    )
    c.exec_driver_sql("""CREATE FUNCTION brc_require_wallet_allocation() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF NEW.margin_allocation IS NULL OR NEW.margin_allocation->>'contract' IS DISTINCT FROM 'wallet_allocation_v1' THEN
            RAISE EXCEPTION 'new CapacityClaim requires wallet allocation evidence';
        END IF;
        RETURN NEW;
    END; $$""")
    c.exec_driver_sql(
        "CREATE TRIGGER trg_brc_require_wallet_allocation BEFORE INSERT ON brc_capacity_claims FOR EACH ROW EXECUTE FUNCTION brc_require_wallet_allocation()"
    )

    c.exec_driver_sql("""CREATE FUNCTION brc_wallet_allocation_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF NEW.margin_allocation IS DISTINCT FROM OLD.margin_allocation THEN
            RAISE EXCEPTION 'allocation evidence immutable';
        END IF;
        RETURN NEW;
    END; $$""")
    c.exec_driver_sql(
        "CREATE TRIGGER trg_brc_wallet_allocation_immutable BEFORE UPDATE OF margin_allocation ON brc_capacity_claims FOR EACH ROW EXECUTE FUNCTION brc_wallet_allocation_immutable()"
    )


def downgrade():
    raise RuntimeError("wallet margin allocation is forward-only")
