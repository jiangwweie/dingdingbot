"""Add immutable ExitProfile catalog and EventExitBinding authority."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_exit_profile_authority_v1"
down_revision: str | None = "0006_sor_dynamic_selection_v0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ID = sa.String(160)
SHORT_TEXT = sa.String(96)
LONG_TEXT = sa.String(512)


def upgrade() -> None:
    _assert_flat_source()
    _upgrade_owner_authorization_purposes()
    _upgrade_profile_store()
    _create_binding_authority()
    _add_claim_ticket_binding_lineage()
    _install_immutability_guards()


def downgrade() -> None:
    raise RuntimeError("0007_exit_profile_authority_v1 is fix-forward only")


def _assert_flat_source() -> None:
    connection = op.get_bind()
    checks = {
        "nonterminal_ticket": (
            "SELECT count(*) FROM brc_trade_aggregates "
            "WHERE status NOT IN ('terminal', 'leverage_rejected', "
            "'entry_rejected', 'entry_reconciled_absent')"
        ),
        "nonflat_position": (
            "SELECT count(*) FROM brc_positions_current WHERE quantity <> 0"
        ),
        "active_reservation": (
            "SELECT count(*) FROM brc_budget_reservations WHERE status = 'active'"
        ),
        "active_domain": (
            "SELECT count(*) FROM brc_trade_tickets "
            "WHERE active_netting_domain_key IS NOT NULL"
        ),
        "unresolved_command": (
            "SELECT count(*) FROM brc_exchange_commands "
            "WHERE status IN ('prepared', 'claimed', 'dispatch_started', "
            "'outcome_unknown')"
        ),
        "open_incident": (
            "SELECT count(*) FROM brc_runtime_incidents WHERE status = 'open'"
        ),
    }
    blockers = [
        name
        for name, query in checks.items()
        if int(connection.scalar(sa.text(query)) or 0) != 0
    ]
    if blockers:
        raise RuntimeError(
            "0007 migration requires exact flat source: " + ",".join(blockers)
        )


def _upgrade_profile_store() -> None:
    op.drop_constraint(
        "uq_brc_exit_policies_event_spec_id",
        "brc_exit_policies",
        type_="unique",
    )
    op.alter_column("brc_exit_policies", "event_spec_id", nullable=True)
    op.add_column(
        "brc_exit_policies",
        sa.Column("profile_schema_version", SHORT_TEXT, nullable=True),
    )
    op.create_unique_constraint(
        "uq_brc_exit_policies_exit_policy_id_semantic_hash",
        "brc_exit_policies",
        ["exit_policy_id", "semantic_hash"],
    )
    op.create_check_constraint(
        "ck_brc_exit_policies_profile_schema_shape_valid",
        "brc_exit_policies",
        "(event_spec_id IS NOT NULL AND profile_schema_version IS NULL) OR "
        "(event_spec_id IS NULL AND profile_schema_version = 'exit_profile_v1')",
    )


def _upgrade_owner_authorization_purposes() -> None:
    op.drop_constraint(
        "ck_brc_owner_authorizations_purpose_valid",
        "brc_owner_authorizations",
        type_="check",
    )
    op.create_check_constraint(
        "ck_brc_owner_authorizations_purpose_valid",
        "brc_owner_authorizations",
        "purpose IN ('strategy_pause', 'strategy_resume', 'entry_pause', "
        "'entry_resume', 'owner_flatten_all', 'universe_configure', "
        "'selection_mode_change', 'exit_profile_bind', "
        "'exit_profile_retire')",
    )


def _create_binding_authority() -> None:
    op.create_table(
        "brc_event_exit_profile_bindings",
        sa.Column("exit_binding_id", ID, primary_key=True),
        sa.Column("binding_version", sa.BigInteger(), nullable=False),
        sa.Column("event_spec_id", ID, nullable=False),
        sa.Column("exit_profile_id", ID, nullable=False),
        sa.Column("exit_profile_semantic_hash", LONG_TEXT, nullable=False),
        sa.Column("binding_semantic_hash", LONG_TEXT, nullable=False),
        sa.Column("activation_reason", LONG_TEXT, nullable=False),
        sa.Column("created_at_ms", sa.BigInteger(), nullable=False),
        sa.UniqueConstraint(
            "event_spec_id",
            "binding_version",
            name="uq_brc_event_exit_profile_bindings_event_version",
        ),
        sa.UniqueConstraint(
            "exit_binding_id",
            "binding_semantic_hash",
            name="uq_brc_event_exit_profile_bindings_identity_hash",
        ),
        sa.ForeignKeyConstraint(
            ["event_spec_id"],
            ["brc_event_specs.event_spec_id"],
            name="fk_brc_event_exit_profile_bindings_event",
        ),
        sa.ForeignKeyConstraint(
            ["exit_profile_id", "exit_profile_semantic_hash"],
            ["brc_exit_policies.exit_policy_id", "brc_exit_policies.semantic_hash"],
            name="fk_brc_event_exit_profile_bindings_profile",
            match="FULL",
        ),
        sa.CheckConstraint(
            "binding_version > 0",
            name="ck_brc_event_exit_profile_bindings_version_positive",
        ),
        sa.CheckConstraint(
            "exit_profile_semantic_hash ~ '^sha256:[0-9a-f]{64}$' "
            "AND binding_semantic_hash ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_brc_event_exit_profile_bindings_hashes_valid",
        ),
    )
    op.create_table(
        "brc_event_exit_profile_binding_current",
        sa.Column("event_spec_id", ID, primary_key=True),
        sa.Column("exit_binding_id", ID, nullable=False, unique=True),
        sa.Column("binding_semantic_hash", LONG_TEXT, nullable=False),
        sa.Column("projection_version", sa.BigInteger(), nullable=False),
        sa.Column("activated_at_ms", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["event_spec_id"],
            ["brc_event_specs.event_spec_id"],
            name="fk_brc_event_exit_profile_binding_current_event",
        ),
        sa.ForeignKeyConstraint(
            ["exit_binding_id", "binding_semantic_hash"],
            [
                "brc_event_exit_profile_bindings.exit_binding_id",
                "brc_event_exit_profile_bindings.binding_semantic_hash",
            ],
            name="fk_brc_event_exit_profile_binding_current_binding",
            match="FULL",
        ),
        sa.CheckConstraint(
            "projection_version > 0",
            name="ck_brc_event_exit_profile_binding_current_version_positive",
        ),
        sa.CheckConstraint(
            "binding_semantic_hash ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_brc_event_exit_profile_binding_current_hash_valid",
        ),
    )
    op.create_table(
        "brc_event_exit_profile_binding_events",
        sa.Column("binding_event_id", ID, primary_key=True),
        sa.Column("event_spec_id", ID, nullable=False),
        sa.Column("exit_binding_id", ID, nullable=False),
        sa.Column("binding_version", sa.BigInteger(), nullable=False),
        sa.Column("operation", SHORT_TEXT, nullable=False),
        sa.Column("authorization_source", SHORT_TEXT, nullable=False),
        sa.Column("owner_authorization_id", ID, nullable=True),
        sa.Column("reason", LONG_TEXT, nullable=False),
        sa.Column("created_at_ms", sa.BigInteger(), nullable=False),
        sa.UniqueConstraint(
            "exit_binding_id",
            "operation",
            name="uq_brc_event_exit_profile_binding_events_lifecycle",
        ),
        sa.ForeignKeyConstraint(
            ["event_spec_id"],
            ["brc_event_specs.event_spec_id"],
            name="fk_brc_event_exit_profile_binding_events_event",
        ),
        sa.ForeignKeyConstraint(
            ["exit_binding_id"],
            ["brc_event_exit_profile_bindings.exit_binding_id"],
            name="fk_brc_event_exit_profile_binding_events_binding",
        ),
        sa.ForeignKeyConstraint(
            ["owner_authorization_id"],
            ["brc_owner_authorizations.authorization_id"],
            name="fk_brc_event_exit_profile_binding_events_owner_authorization",
        ),
        sa.CheckConstraint(
            "binding_version > 0",
            name="ck_brc_event_exit_profile_binding_events_version_positive",
        ),
        sa.CheckConstraint(
            "operation IN ('ACTIVATED', 'RETIRED')",
            name="ck_brc_event_exit_profile_binding_events_operation_valid",
        ),
        sa.CheckConstraint(
            "authorization_source IN ('system_migration', 'owner_control')",
            name="ck_brc_event_exit_profile_binding_events_source_valid",
        ),
        sa.CheckConstraint(
            "(authorization_source = 'system_migration' "
            "AND owner_authorization_id IS NULL) OR "
            "(authorization_source = 'owner_control' "
            "AND owner_authorization_id IS NOT NULL)",
            name="ck_brc_event_exit_profile_binding_events_authorization_shape",
        ),
    )


def _add_claim_ticket_binding_lineage() -> None:
    for table in ("brc_capacity_claims", "brc_trade_tickets"):
        op.add_column(table, sa.Column("exit_binding_id", ID, nullable=True))
        op.add_column(
            table,
            sa.Column("exit_binding_semantic_hash", LONG_TEXT, nullable=True),
        )
        op.add_column(
            table,
            sa.Column("exit_binding_authority_version", sa.BigInteger(), nullable=True),
        )
        op.create_check_constraint(
            f"ck_{table}_exit_binding_lineage_shape_valid",
            table,
            "(exit_binding_id IS NULL "
            "AND exit_binding_semantic_hash IS NULL "
            "AND exit_binding_authority_version IS NULL) OR "
            "(exit_binding_id IS NOT NULL "
            "AND exit_binding_semantic_hash IS NOT NULL "
            "AND exit_binding_authority_version > 0)",
        )
        op.create_foreign_key(
            f"fk_{table}_exit_binding",
            table,
            "brc_event_exit_profile_bindings",
            ["exit_binding_id", "exit_binding_semantic_hash"],
            ["exit_binding_id", "binding_semantic_hash"],
            match="FULL",
        )


def _install_immutability_guards() -> None:
    op.execute(
        sa.text(
            """
            CREATE FUNCTION brc_protect_exit_profile_v1()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                IF TG_OP = 'DELETE' AND OLD.event_spec_id IS NULL THEN
                    RAISE EXCEPTION 'immutable ExitProfile cannot be deleted';
                END IF;
                IF TG_OP = 'UPDATE' AND OLD.event_spec_id IS NULL THEN
                    IF NEW.exit_policy_id IS DISTINCT FROM OLD.exit_policy_id
                       OR NEW.exit_policy_version IS DISTINCT FROM OLD.exit_policy_version
                       OR NEW.event_spec_id IS DISTINCT FROM OLD.event_spec_id
                       OR NEW.profile_schema_version IS DISTINCT FROM OLD.profile_schema_version
                       OR NEW.position_side IS DISTINCT FROM OLD.position_side
                       OR NEW.policy IS DISTINCT FROM OLD.policy
                       OR NEW.semantic_hash IS DISTINCT FROM OLD.semantic_hash
                       OR NEW.created_at_ms IS DISTINCT FROM OLD.created_at_ms THEN
                        RAISE EXCEPTION 'immutable ExitProfile content changed';
                    END IF;
                    IF NEW.status IS DISTINCT FROM OLD.status
                       AND NOT (OLD.status = 'active' AND NEW.status = 'retired') THEN
                        RAISE EXCEPTION 'illegal ExitProfile status transition';
                    END IF;
                END IF;
                RETURN COALESCE(NEW, OLD);
            END;
            $$
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_brc_exit_policies_profile_v1_immutable
            BEFORE UPDATE OR DELETE ON brc_exit_policies
            FOR EACH ROW EXECUTE FUNCTION brc_protect_exit_profile_v1()
            """
        )
    )
    for table, label in (
        ("brc_event_exit_profile_bindings", "EventExitBinding"),
        ("brc_event_exit_profile_binding_events", "EventExitBinding event"),
    ):
        function_name = f"brc_protect_{table}_immutable"
        trigger_name = f"trg_{table}_immutable"
        op.execute(
            sa.text(
                f"""
                CREATE FUNCTION {function_name}()
                RETURNS trigger
                LANGUAGE plpgsql
                AS $$
                BEGIN
                    RAISE EXCEPTION 'immutable {label} cannot change';
                END;
                $$
                """
            )
        )
        op.execute(
            sa.text(
                f"""
                CREATE TRIGGER {trigger_name}
                BEFORE UPDATE OR DELETE ON {table}
                FOR EACH ROW EXECUTE FUNCTION {function_name}()
                """
            )
        )
