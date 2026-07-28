"""Add forward-only PostgreSQL authority for crypto StrategyUniverses.

Revision ID: 0002_crypto_strategy_universe
Revises: 0001_initial
Create Date: 2026-07-28

The upgrade is intentionally flat-only. It rejects populated runtime or trade
tables before executing DDL and provides no downgrade compatibility path.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0002_crypto_strategy_universe"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ID = sa.String(160)
SHORT_TEXT = sa.String(96)
LONG_TEXT = sa.String(512)


def _id(name: str, *, primary_key: bool = False, nullable: bool = False) -> sa.Column:
    return sa.Column(name, ID, primary_key=primary_key, nullable=nullable)


def _time(name: str, *, nullable: bool = False) -> sa.Column:
    return sa.Column(name, sa.BigInteger, nullable=nullable)


def _json(name: str, *, nullable: bool = False) -> sa.Column:
    return sa.Column(name, postgresql.JSONB, nullable=nullable)


def upgrade() -> None:
    _assert_flat_runtime_before_ddl()

    op.drop_index(
        "ix_brc_runtime_scopes_current_observation_due",
        table_name="brc_runtime_scopes_current",
    )
    op.drop_table("brc_strategy_candidate_scopes")

    op.create_check_constraint(
        "ck_brc_instruments_status_valid",
        "brc_instruments",
        "status IN ('pending_certification', 'active')",
    )

    op.create_table(
        "brc_strategy_universe_versions",
        _id("universe_version_id", primary_key=True),
        _id("strategy_group_id"),
        _id("event_spec_id"),
        sa.Column("universe_version", sa.Integer, nullable=False),
        sa.Column("semantic_digest", LONG_TEXT, nullable=False),
        sa.Column("lifecycle_state", SHORT_TEXT, nullable=False),
        _time("installed_at_ms"),
        _time("activated_at_ms", nullable=True),
        _time("retired_at_ms", nullable=True),
        sa.UniqueConstraint(
            "event_spec_id",
            "universe_version",
            name="uq_brc_strategy_universe_versions_event_version",
        ),
        sa.UniqueConstraint(
            "universe_version_id",
            "event_spec_id",
            "semantic_digest",
            name="uq_brc_universe_versions_identity_digest",
        ),
        sa.UniqueConstraint(
            "universe_version_id",
            "event_spec_id",
            "semantic_digest",
            "lifecycle_state",
            name="uq_brc_universe_versions_identity_lifecycle",
        ),
        sa.CheckConstraint(
            "universe_version > 0",
            name="ck_brc_strategy_universe_versions_version_positive",
        ),
        sa.CheckConstraint(
            "semantic_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_brc_strategy_universe_versions_digest_valid",
        ),
        sa.CheckConstraint(
            "lifecycle_state IN ('warming', 'active', 'retired')",
            name="ck_brc_strategy_universe_versions_state_valid",
        ),
        sa.CheckConstraint(
            "(lifecycle_state = 'warming' "
            "AND activated_at_ms IS NULL AND retired_at_ms IS NULL) OR "
            "(lifecycle_state = 'active' "
            "AND activated_at_ms IS NOT NULL AND retired_at_ms IS NULL) OR "
            "(lifecycle_state = 'retired' "
            "AND activated_at_ms IS NOT NULL AND retired_at_ms IS NOT NULL "
            "AND retired_at_ms >= activated_at_ms)",
            name="ck_brc_strategy_universe_versions_timestamps_valid",
        ),
    )
    op.create_index(
        "uq_brc_strategy_universe_versions_current_digest",
        "brc_strategy_universe_versions",
        ["event_spec_id", "semantic_digest"],
        unique=True,
        postgresql_where=sa.text(
            "lifecycle_state IN ('warming', 'active')"
        ),
    )
    op.create_index(
        "uq_brc_strategy_universe_versions_global_warming",
        "brc_strategy_universe_versions",
        ["lifecycle_state"],
        unique=True,
        postgresql_where=sa.text("lifecycle_state = 'warming'"),
    )

    op.create_table(
        "brc_strategy_universe_members",
        _id("universe_version_id"),
        _id("exchange_instrument_id"),
        sa.PrimaryKeyConstraint(
            "universe_version_id",
            "exchange_instrument_id",
            name="pk_brc_strategy_universe_members",
        ),
        sa.ForeignKeyConstraint(
            ["universe_version_id"],
            ["brc_strategy_universe_versions.universe_version_id"],
            name="fk_brc_universe_members_universe_version",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["exchange_instrument_id"],
            ["brc_instruments.exchange_instrument_id"],
            name="fk_brc_universe_members_instrument",
        ),
    )
    _create_member_cardinality_guard()

    op.create_table(
        "brc_strategy_universe_current",
        _id("event_spec_id", primary_key=True),
        _id("universe_version_id"),
        sa.Column("semantic_digest", LONG_TEXT, nullable=False),
        sa.Column(
            "lifecycle_state",
            SHORT_TEXT,
            nullable=False,
            server_default=sa.text("'active'"),
        ),
        sa.Column("activation_generation", sa.BigInteger, nullable=False),
        _time("activated_at_ms"),
        sa.ForeignKeyConstraint(
            [
                "universe_version_id",
                "event_spec_id",
                "semantic_digest",
                "lifecycle_state",
            ],
            [
                "brc_strategy_universe_versions.universe_version_id",
                "brc_strategy_universe_versions.event_spec_id",
                "brc_strategy_universe_versions.semantic_digest",
                "brc_strategy_universe_versions.lifecycle_state",
            ],
            name="fk_brc_universe_current_active_identity",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.UniqueConstraint(
            "universe_version_id",
            name="uq_brc_strategy_universe_current_version",
        ),
        sa.CheckConstraint(
            "semantic_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_brc_strategy_universe_current_digest_valid",
        ),
        sa.CheckConstraint(
            "activation_generation > 0",
            name="ck_brc_strategy_universe_current_generation_positive",
        ),
        sa.CheckConstraint(
            "lifecycle_state = 'active'",
            name="ck_brc_strategy_universe_current_active_only",
        ),
    )
    _create_universe_activation_entry_fence()

    op.create_table(
        "brc_instrument_certification_current",
        _id("runtime_profile_id"),
        _id("exchange_instrument_id"),
        sa.Column("status", SHORT_TEXT, nullable=False),
        sa.Column("blocker_code", SHORT_TEXT, nullable=True),
        sa.Column("facts_digest", LONG_TEXT, nullable=False),
        sa.Column("product_rules_digest", LONG_TEXT, nullable=True),
        sa.Column("configured_leverage", sa.Integer, nullable=True),
        sa.Column("margin_mode", SHORT_TEXT, nullable=True),
        sa.Column("position_mode", SHORT_TEXT, nullable=True),
        _time("observed_at_ms"),
        _time("valid_until_ms"),
        _time("next_check_at_ms"),
        sa.Column("lease_owner", SHORT_TEXT, nullable=True),
        _time("lease_expires_at_ms", nullable=True),
        sa.Column("projection_version", sa.BigInteger, nullable=False),
        sa.PrimaryKeyConstraint(
            "runtime_profile_id",
            "exchange_instrument_id",
            name="pk_brc_instrument_certification_current",
        ),
        sa.ForeignKeyConstraint(
            ["runtime_profile_id"],
            ["brc_runtime_profiles.runtime_profile_id"],
            name="fk_brc_instrument_certification_profile",
        ),
        sa.ForeignKeyConstraint(
            ["exchange_instrument_id"],
            ["brc_instruments.exchange_instrument_id"],
            name="fk_brc_instrument_certification_instrument",
        ),
        sa.CheckConstraint(
            "status IN ('eligible', 'owner_action_required', "
            "'temporarily_unavailable')",
            name="ck_brc_instrument_certification_status_valid",
        ),
        sa.CheckConstraint(
            "facts_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_brc_instrument_certification_facts_digest_valid",
        ),
        sa.CheckConstraint(
            "product_rules_digest IS NULL "
            "OR product_rules_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_brc_instrument_certification_rules_digest_valid",
        ),
        sa.CheckConstraint(
            "valid_until_ms > observed_at_ms",
            name="ck_brc_instrument_certification_validity_window",
        ),
        sa.CheckConstraint(
            "next_check_at_ms >= observed_at_ms",
            name="ck_brc_instrument_certification_next_check_valid",
        ),
        sa.CheckConstraint(
            "(lease_owner IS NULL AND lease_expires_at_ms IS NULL) OR "
            "(lease_owner IS NOT NULL AND lease_expires_at_ms IS NOT NULL)",
            name="ck_brc_instrument_certification_lease_shape",
        ),
        sa.CheckConstraint(
            "projection_version > 0",
            name="ck_brc_instrument_certification_projection_positive",
        ),
    )
    op.create_index(
        "ix_brc_instrument_certification_current_due",
        "brc_instrument_certification_current",
        ["status", "next_check_at_ms", "lease_expires_at_ms"],
    )

    op.create_table(
        "brc_comparative_projection_current",
        _id("event_spec_id"),
        _id("universe_version_id"),
        _time("closed_bar_time_ms"),
        sa.Column("member_set_digest", LONG_TEXT, nullable=False),
        _json("projection"),
        _time("observed_at_ms"),
        _time("valid_until_ms"),
        sa.Column("projection_version", sa.BigInteger, nullable=False),
        sa.PrimaryKeyConstraint(
            "event_spec_id",
            "universe_version_id",
            name="pk_brc_comparative_projection_current",
        ),
        sa.ForeignKeyConstraint(
            ["universe_version_id"],
            ["brc_strategy_universe_versions.universe_version_id"],
            name="fk_brc_comparative_projection_universe_version",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "member_set_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_brc_comparative_projection_member_digest_valid",
        ),
        sa.CheckConstraint(
            "valid_until_ms > observed_at_ms",
            name="ck_brc_comparative_projection_validity_window",
        ),
        sa.CheckConstraint(
            "projection_version > 0",
            name="ck_brc_comparative_projection_version_positive",
        ),
    )
    op.create_index(
        "ix_brc_comparative_projection_current_lookup",
        "brc_comparative_projection_current",
        ["event_spec_id", "universe_version_id", "closed_bar_time_ms"],
    )

    _replace_runtime_scope_authority()
    _add_trade_chain_universe_lineage()


def downgrade() -> None:
    raise RuntimeError("0002_crypto_strategy_universe is forward-only")


def _assert_flat_runtime_before_ddl() -> None:
    populated_tables = tuple(sorted((
        "brc_strategy_candidate_scopes",
        "brc_instrument_rules_current",
        "brc_owner_policy_events",
        "brc_owner_policy_current",
        "brc_runtime_profiles",
        "brc_runtime_scopes_current",
        "brc_facts_current",
        "brc_signal_events",
        "brc_signal_fact_snapshots",
        "brc_readiness_current",
        "brc_entry_lane_current",
        "brc_runtime_capabilities_current",
        "brc_capacity_claims",
        "brc_trade_tickets",
        "brc_trade_aggregates",
        "brc_trade_events",
        "brc_exchange_commands",
        "brc_positions_current",
        "brc_budget_reservations",
        "brc_account_exposure_current",
        "brc_runtime_incidents",
        "brc_trade_reviews",
        "brc_monitor_current",
        "brc_monitor_events",
        "brc_retention_runs",
        "brc_schema_metadata",
    )))
    locked_tables = ", ".join(f'"{table_name}"' for table_name in populated_tables)
    op.execute(
        sa.text(
            f"LOCK TABLE {locked_tables} IN ACCESS EXCLUSIVE MODE"
        )
    )
    predicates = " OR ".join(
        f'EXISTS (SELECT 1 FROM "{table_name}" LIMIT 1)'
        for table_name in populated_tables
    )
    op.execute(
        sa.text(
            f"""
            DO $$
            BEGIN
                IF {predicates} THEN
                    RAISE EXCEPTION
                        'runtime/trade tables must be empty before '
                        '0002_crypto_strategy_universe'
                        USING ERRCODE = '55000';
                END IF;
            END
            $$;
            """
        )
    )


def _create_member_cardinality_guard() -> None:
    op.execute(
        sa.text(
            """
            CREATE FUNCTION brc_enforce_universe_member_limit()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            DECLARE
                instrument_exists boolean;
                instrument_is_crypto_usdt_perpetual boolean;
            BEGIN
                SELECT
                    true,
                    venue_id = 'binance-usdm'
                    AND asset_class = 'crypto'
                    AND venue_symbol ~ '^[A-Z0-9]+USDT$'
                    AND contract_kind = 'perpetual'
                    AND exchange_instrument_id =
                        'binance-usdm' || chr(58) || venue_symbol
                        || chr(58) || 'perpetual'
                INTO
                    instrument_exists,
                    instrument_is_crypto_usdt_perpetual
                FROM brc_instruments
                WHERE exchange_instrument_id = NEW.exchange_instrument_id;

                IF instrument_exists
                   AND NOT instrument_is_crypto_usdt_perpetual THEN
                    RAISE EXCEPTION
                        'strategy universe member must be a canonical '
                        'Binance USD-M USDT perpetual'
                        USING ERRCODE = '23514',
                              CONSTRAINT = 'ck_brc_universe_member_crypto';
                END IF;

                PERFORM 1
                FROM brc_strategy_universe_versions
                WHERE universe_version_id = NEW.universe_version_id
                FOR UPDATE;

                IF (
                    SELECT count(*)
                    FROM brc_strategy_universe_members
                    WHERE universe_version_id = NEW.universe_version_id
                ) >= 10 THEN
                    RAISE EXCEPTION
                        'strategy universe cardinality cannot exceed 10'
                        USING ERRCODE = '23514',
                              CONSTRAINT = 'ck_brc_universe_members_max_ten';
                END IF;
                RETURN NEW;
            END
            $$;
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_brc_universe_members_max_ten
            BEFORE INSERT ON brc_strategy_universe_members
            FOR EACH ROW
            EXECUTE FUNCTION brc_enforce_universe_member_limit();
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE FUNCTION brc_reject_universe_member_mutation()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                RAISE EXCEPTION
                    'strategy universe members are immutable'
                    USING ERRCODE = '23514',
                          CONSTRAINT = 'ck_brc_universe_member_immutable';
            END
            $$;
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_brc_universe_member_immutable
            BEFORE UPDATE OR DELETE ON brc_strategy_universe_members
            FOR EACH ROW
            EXECUTE FUNCTION brc_reject_universe_member_mutation();
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE FUNCTION brc_reject_instrument_identity_mutation()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                RAISE EXCEPTION
                    'instrument identity fields are immutable'
                    USING ERRCODE = '23514',
                          CONSTRAINT = 'ck_brc_instrument_identity_immutable';
            END
            $$;
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_brc_instrument_identity_immutable
            BEFORE UPDATE OF
                exchange_instrument_id,
                venue_id,
                asset_class,
                venue_symbol,
                contract_kind
            ON brc_instruments
            FOR EACH ROW
            EXECUTE FUNCTION brc_reject_instrument_identity_mutation();
            """
        )
    )


def _create_universe_activation_entry_fence() -> None:
    op.execute(
        sa.text(
            """
            CREATE FUNCTION brc_fence_universe_pointer_during_entry()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            DECLARE
                lane_status text;
                blocking_ticket_id text;
            BEGIN
                INSERT INTO brc_entry_lane_current (
                    lane_id,
                    ticket_id,
                    signal_event_id,
                    status,
                    claimed_at_ms,
                    lease_until_ms,
                    claim_owner,
                    version
                )
                VALUES (
                    'global-entry',
                    NULL,
                    NULL,
                    'idle',
                    NULL,
                    NULL,
                    NULL,
                    0
                )
                ON CONFLICT (lane_id) DO NOTHING;

                SELECT status, ticket_id
                INTO lane_status, blocking_ticket_id
                FROM brc_entry_lane_current
                WHERE lane_id = 'global-entry'
                FOR UPDATE;

                IF lane_status <> 'idle' THEN
                    RAISE EXCEPTION
                        'strategy universe activation is fenced by '
                        'global ENTRY lane ticket %',
                        blocking_ticket_id
                        USING ERRCODE = '55000',
                              CONSTRAINT =
                                  'ck_brc_universe_activation_entry_lane_idle';
                END IF;

                RETURN NULL;
            END
            $$;
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_brc_universe_activation_entry_lane
            BEFORE INSERT OR UPDATE OR DELETE
            ON brc_strategy_universe_current
            FOR EACH STATEMENT
            EXECUTE FUNCTION brc_fence_universe_pointer_during_entry();
            """
        )
    )


def _replace_runtime_scope_authority() -> None:
    op.drop_constraint(
        "uq_brc_runtime_scopes_current_identity",
        "brc_runtime_scopes_current",
        type_="unique",
    )
    op.drop_column("brc_runtime_scopes_current", "enabled")
    op.drop_column("brc_runtime_scopes_current", "observation_due_at_ms")
    op.drop_column("brc_runtime_scopes_current", "observation_lease_until_ms")
    op.drop_column("brc_runtime_scopes_current", "observation_claim_owner")

    op.add_column(
        "brc_runtime_scopes_current",
        _id("universe_version_id"),
    )
    op.add_column(
        "brc_runtime_scopes_current",
        sa.Column("universe_semantic_digest", LONG_TEXT, nullable=False),
    )
    op.add_column(
        "brc_runtime_scopes_current",
        sa.Column("lifecycle_state", SHORT_TEXT, nullable=False),
    )
    op.add_column(
        "brc_runtime_scopes_current",
        sa.Column("observation_enabled", sa.Boolean, nullable=False),
    )
    op.add_column(
        "brc_runtime_scopes_current",
        sa.Column("entry_enabled", sa.Boolean, nullable=False),
    )
    op.add_column(
        "brc_runtime_scopes_current",
        _time("warm_ready_at_ms", nullable=True),
    )
    op.add_column(
        "brc_runtime_scopes_current",
        sa.Column("warm_readiness_digest", LONG_TEXT, nullable=True),
    )
    op.add_column(
        "brc_runtime_scopes_current",
        _time("warm_valid_until_ms", nullable=True),
    )
    op.add_column(
        "brc_runtime_scopes_current",
        _time("next_observation_due_at_ms", nullable=True),
    )
    op.add_column(
        "brc_runtime_scopes_current",
        _time("lease_expires_at_ms", nullable=True),
    )
    op.add_column(
        "brc_runtime_scopes_current",
        _id("lease_owner", nullable=True),
    )
    op.create_unique_constraint(
        "uq_brc_runtime_scopes_current_universe_identity",
        "brc_runtime_scopes_current",
        [
            "universe_version_id",
            "runtime_profile_id",
            "exchange_instrument_id",
            "position_side",
        ],
    )
    op.create_foreign_key(
        "fk_brc_runtime_scope_universe_member",
        "brc_runtime_scopes_current",
        "brc_strategy_universe_members",
        ["universe_version_id", "exchange_instrument_id"],
        ["universe_version_id", "exchange_instrument_id"],
    )
    op.create_foreign_key(
        "fk_brc_runtime_scope_universe_lifecycle",
        "brc_runtime_scopes_current",
        "brc_strategy_universe_versions",
        [
            "universe_version_id",
            "event_spec_id",
            "universe_semantic_digest",
            "lifecycle_state",
        ],
        [
            "universe_version_id",
            "event_spec_id",
            "semantic_digest",
            "lifecycle_state",
        ],
        deferrable=True,
        initially="DEFERRED",
    )
    op.create_check_constraint(
        "ck_brc_runtime_scope_lifecycle_permissions",
        "brc_runtime_scopes_current",
        "(lifecycle_state = 'warming' "
        "AND observation_enabled AND NOT entry_enabled) OR "
        "(lifecycle_state = 'active' "
        "AND observation_enabled AND entry_enabled) OR "
        "(lifecycle_state = 'retired' "
        "AND NOT observation_enabled AND NOT entry_enabled)",
    )
    op.create_check_constraint(
        "ck_brc_runtime_scope_warm_readiness_shape",
        "brc_runtime_scopes_current",
        "(warm_ready_at_ms IS NULL AND warm_readiness_digest IS NULL "
        "AND warm_valid_until_ms IS NULL) OR "
        "(warm_ready_at_ms IS NOT NULL AND warm_readiness_digest IS NOT NULL "
        "AND warm_valid_until_ms IS NOT NULL "
        "AND warm_valid_until_ms > warm_ready_at_ms)",
    )
    op.create_check_constraint(
        "ck_brc_runtime_scope_active_requires_warm",
        "brc_runtime_scopes_current",
        "lifecycle_state <> 'active' OR warm_ready_at_ms IS NOT NULL",
    )
    op.create_check_constraint(
        "ck_brc_runtime_scope_warm_digest_valid",
        "brc_runtime_scopes_current",
        "warm_readiness_digest IS NULL "
        "OR warm_readiness_digest ~ '^sha256:[0-9a-f]{64}$'",
    )
    op.create_check_constraint(
        "ck_brc_runtime_scope_universe_digest_valid",
        "brc_runtime_scopes_current",
        "universe_semantic_digest ~ '^sha256:[0-9a-f]{64}$'",
    )
    op.create_index(
        "ix_brc_runtime_scopes_current_observation_due",
        "brc_runtime_scopes_current",
        [
            "observation_enabled",
            "next_observation_due_at_ms",
            "lease_expires_at_ms",
        ],
    )


def _add_trade_chain_universe_lineage() -> None:
    for table_name in (
        "brc_signal_events",
        "brc_capacity_claims",
        "brc_trade_tickets",
    ):
        op.add_column(table_name, _id("universe_version_id"))
        op.add_column(
            table_name,
            sa.Column("universe_semantic_digest", LONG_TEXT, nullable=False),
        )
        op.create_foreign_key(
            f"fk_{table_name}_universe_identity",
            table_name,
            "brc_strategy_universe_versions",
            [
                "universe_version_id",
                "event_spec_id",
                "universe_semantic_digest",
            ],
            [
                "universe_version_id",
                "event_spec_id",
                "semantic_digest",
            ],
        )
        op.create_check_constraint(
            f"ck_{table_name}_universe_digest_valid",
            table_name,
            "universe_semantic_digest ~ '^sha256:[0-9a-f]{64}$'",
        )
