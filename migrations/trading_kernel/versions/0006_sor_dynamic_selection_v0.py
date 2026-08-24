"""Add SOR Dynamic Selection V0 facts and time-bounded ENTRY authority."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0006_sor_dynamic_selection_v0"
down_revision: str | None = "0005_tradfi_instrument_center"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ID = sa.String(160)
SHORT_TEXT = sa.String(96)
LONG_TEXT = sa.String(512)
MONEY = sa.Numeric(38, 18)
SELECTION_DECIMAL = sa.Numeric()

_SELECTION_SPEC_ID = "sor-dynamic-selection-v0"
_SELECTION_SPEC_DIGEST = (
    "sha256:a2c0d5d809a54b90564086f4eab230726a16fdb5524a1ce8f29f48ad659cfb10"
)
_SOR_EVENTS = (
    ("event_spec:SOR-001:SOR-LONG:v4", "long"),
    ("event_spec:SOR-001:SOR-SHORT:v4", "short"),
)
_CANDIDATE_SYMBOLS = (
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "SOLUSDT",
    "XRPUSDT",
    "DOGEUSDT",
    "ADAUSDT",
    "AVAXUSDT",
    "LINKUSDT",
    "LTCUSDT",
    "BCHUSDT",
    "DOTUSDT",
    "NEARUSDT",
    "ATOMUSDT",
    "FILUSDT",
    "ETCUSDT",
    "APTUSDT",
    "OPUSDT",
    "ARBUSDT",
    "INJUSDT",
    "SUIUSDT",
    "TRXUSDT",
    "UNIUSDT",
    "RUNEUSDT",
)


def upgrade() -> None:
    _assert_flat_source()
    _create_selection_spec_tables()
    _create_selection_plane_tables()
    _create_materialization_tables()
    _upgrade_strategy_universe()
    _create_vacuum_and_gap_tables()
    _create_authority_tables()
    _create_suppression_and_release_tables()
    _add_selection_lineage()
    _install_immutability_guards()
    _seed_frozen_sor_v0_if_registry_exists()


def downgrade() -> None:
    raise RuntimeError("0006_sor_dynamic_selection_v0 is fix-forward only")


def _assert_flat_source() -> None:
    connection = op.get_bind()
    checks = {
        "nonterminal_ticket": (
            "SELECT count(*) FROM brc_trade_aggregates "
            "WHERE status NOT IN ('terminal', 'leverage_rejected', "
            "'entry_rejected', 'entry_reconciled_absent')"
        ),
        "nonflat_position": "SELECT count(*) FROM brc_positions_current WHERE quantity <> 0",
        "active_reservation": (
            "SELECT count(*) FROM brc_budget_reservations WHERE status = 'active'"
        ),
        "unresolved_command": (
            "SELECT count(*) FROM brc_exchange_commands "
            "WHERE status IN ('prepared', 'claimed', 'dispatch_started', 'outcome_unknown')"
        ),
        "open_incident": "SELECT count(*) FROM brc_runtime_incidents WHERE status = 'open'",
    }
    blockers = [
        name
        for name, query in checks.items()
        if int(connection.scalar(sa.text(query)) or 0) != 0
    ]
    if blockers:
        raise RuntimeError(
            "0006 migration requires exact flat source: " + ",".join(blockers)
        )


def _create_selection_spec_tables() -> None:
    op.create_table(
        "brc_instrument_selection_specs",
        sa.Column("selection_spec_id", ID, primary_key=True),
        sa.Column("strategy_group_id", ID, nullable=False),
        sa.Column("strategy_version_id", ID, nullable=False),
        sa.Column("selection_version", sa.Integer(), nullable=False),
        sa.Column("selection_kind", SHORT_TEXT, nullable=False),
        sa.Column("algorithm_semantic_digest", LONG_TEXT, nullable=False),
        sa.Column("status", SHORT_TEXT, nullable=False),
        sa.Column("installed_at_ms", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["strategy_group_id"],
            ["brc_strategy_groups.strategy_group_id"],
        ),
        sa.ForeignKeyConstraint(
            ["strategy_version_id"],
            ["brc_strategy_versions.strategy_version_id"],
        ),
        sa.UniqueConstraint(
            "strategy_group_id",
            "selection_version",
            name="uq_brc_instrument_selection_specs_group_version",
        ),
        sa.CheckConstraint(
            "selection_version > 0",
            name="ck_brc_instrument_selection_specs_version_positive",
        ),
        sa.CheckConstraint(
            "selection_kind = 'sor_dynamic_v0'",
            name="ck_brc_instrument_selection_specs_kind_valid",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'retired')",
            name="ck_brc_instrument_selection_specs_status_valid",
        ),
        sa.CheckConstraint(
            "algorithm_semantic_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_brc_instrument_selection_specs_digest_valid",
        ),
    )
    op.create_table(
        "brc_sor_dynamic_selection_specs_v0",
        sa.Column("selection_spec_id", ID, primary_key=True),
        sa.Column("decision_offset_utc_seconds", sa.Integer(), nullable=False),
        sa.Column("feature_cutoff_offset_utc_seconds", sa.Integer(), nullable=False),
        sa.Column(
            "eligibility_not_before_offset_utc_seconds",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "valid_until_next_decision_offset_seconds",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column("candidate_count", sa.Integer(), nullable=False),
        sa.Column("selected_count_max", sa.Integer(), nullable=False),
        sa.Column("near_count_max", sa.Integer(), nullable=False),
        sa.Column("activity_floor_quote_usdt", MONEY, nullable=False),
        sa.Column("materialization_timeout_seconds", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["selection_spec_id"],
            ["brc_instrument_selection_specs.selection_spec_id"],
        ),
        sa.CheckConstraint(
            "decision_offset_utc_seconds = 3600 "
            "AND feature_cutoff_offset_utc_seconds = 3600 "
            "AND eligibility_not_before_offset_utc_seconds = 4500 "
            "AND valid_until_next_decision_offset_seconds = 86400 "
            "AND candidate_count = 24 AND selected_count_max = 7 "
            "AND near_count_max = 7 "
            "AND activity_floor_quote_usdt = 20000000 "
            "AND materialization_timeout_seconds = 1800",
            name="ck_brc_sor_dynamic_selection_specs_v0_frozen",
        ),
    )
    op.create_table(
        "brc_instrument_selection_spec_events",
        sa.Column("selection_spec_id", ID, nullable=False),
        sa.Column("event_spec_id", ID, nullable=False),
        sa.Column("position_side", SHORT_TEXT, nullable=False),
        sa.PrimaryKeyConstraint("selection_spec_id", "event_spec_id"),
        sa.ForeignKeyConstraint(
            ["selection_spec_id"],
            ["brc_instrument_selection_specs.selection_spec_id"],
        ),
        sa.ForeignKeyConstraint(
            ["event_spec_id"],
            ["brc_event_specs.event_spec_id"],
        ),
        sa.UniqueConstraint(
            "selection_spec_id",
            "position_side",
            name="uq_brc_instrument_selection_spec_events_side",
        ),
        sa.CheckConstraint(
            "position_side IN ('long', 'short')",
            name="ck_brc_instrument_selection_spec_events_side_valid",
        ),
    )
    op.create_table(
        "brc_instrument_selection_spec_members",
        sa.Column("selection_spec_id", ID, nullable=False),
        sa.Column("exchange_instrument_id", ID, nullable=False),
        sa.PrimaryKeyConstraint("selection_spec_id", "exchange_instrument_id"),
        sa.ForeignKeyConstraint(
            ["selection_spec_id"],
            ["brc_instrument_selection_specs.selection_spec_id"],
        ),
        sa.ForeignKeyConstraint(
            ["exchange_instrument_id"],
            ["brc_instruments.exchange_instrument_id"],
        ),
    )


def _create_selection_plane_tables() -> None:
    op.create_table(
        "brc_strategy_selection_rollback_baselines",
        sa.Column("rollback_baseline_id", ID, primary_key=True),
        sa.Column("strategy_group_id", ID, nullable=False),
        sa.Column("strategy_version_id", ID, nullable=False),
        sa.Column("source_long_universe_version_id", ID, nullable=False),
        sa.Column("source_short_universe_version_id", ID, nullable=False),
        sa.Column("semantic_digest", LONG_TEXT, nullable=False),
        sa.Column("captured_at_ms", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["strategy_group_id"], ["brc_strategy_groups.strategy_group_id"]
        ),
        sa.ForeignKeyConstraint(
            ["strategy_version_id"], ["brc_strategy_versions.strategy_version_id"]
        ),
        sa.ForeignKeyConstraint(
            ["source_long_universe_version_id"],
            ["brc_strategy_universe_versions.universe_version_id"],
        ),
        sa.ForeignKeyConstraint(
            ["source_short_universe_version_id"],
            ["brc_strategy_universe_versions.universe_version_id"],
        ),
        sa.UniqueConstraint(
            "strategy_group_id",
            "strategy_version_id",
            name="uq_brc_strategy_selection_rollback_baseline_version",
        ),
        sa.CheckConstraint(
            "source_long_universe_version_id <> source_short_universe_version_id",
            name="ck_brc_strategy_selection_rollback_baseline_pair_distinct",
        ),
        sa.CheckConstraint(
            "semantic_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_brc_strategy_selection_rollback_baseline_digest_valid",
        ),
    )
    op.create_table(
        "brc_strategy_selection_control_current",
        sa.Column("strategy_group_id", ID, primary_key=True),
        sa.Column("selection_spec_id", ID, nullable=False),
        sa.Column("selection_mode", SHORT_TEXT, nullable=False),
        sa.Column("pending_selection_mode", SHORT_TEXT, nullable=True),
        sa.Column("pending_effective_session_start_ms", sa.BigInteger(), nullable=True),
        sa.Column("pending_authorization_id", ID, nullable=True),
        sa.Column("control_version", sa.BigInteger(), nullable=False),
        sa.Column("rollback_baseline_id", ID, nullable=True),
        sa.Column("updated_at_ms", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["strategy_group_id"], ["brc_strategy_groups.strategy_group_id"]
        ),
        sa.ForeignKeyConstraint(
            ["selection_spec_id"],
            ["brc_instrument_selection_specs.selection_spec_id"],
        ),
        sa.ForeignKeyConstraint(
            ["pending_authorization_id"],
            ["brc_owner_authorizations.authorization_id"],
        ),
        sa.ForeignKeyConstraint(
            ["rollback_baseline_id"],
            ["brc_strategy_selection_rollback_baselines.rollback_baseline_id"],
        ),
        sa.CheckConstraint(
            "selection_mode IN ('disabled', 'static_baseline', 'dynamic_selection')",
            name="ck_brc_strategy_selection_control_current_mode_valid",
        ),
        sa.CheckConstraint(
            "pending_selection_mode IS NULL OR pending_selection_mode IN "
            "('disabled', 'static_baseline', 'dynamic_selection')",
            name="ck_brc_strategy_selection_control_current_pending_mode_valid",
        ),
        sa.CheckConstraint(
            "(pending_selection_mode IS NULL "
            "AND pending_effective_session_start_ms IS NULL "
            "AND pending_authorization_id IS NULL) OR "
            "(pending_selection_mode IS NOT NULL "
            "AND pending_effective_session_start_ms IS NOT NULL "
            "AND pending_authorization_id IS NOT NULL)",
            name="ck_brc_strategy_selection_control_current_pending_shape",
        ),
        sa.CheckConstraint(
            "control_version > 0",
            name="ck_brc_strategy_selection_control_current_version_positive",
        ),
    )
    op.create_table(
        "brc_instrument_selection_jobs_current",
        sa.Column("selection_job_id", ID, primary_key=True),
        sa.Column("selection_spec_id", ID, nullable=False),
        sa.Column("session_start_ms", sa.BigInteger(), nullable=False),
        sa.Column("scheduled_at_ms", sa.BigInteger(), nullable=False),
        sa.Column("feature_cutoff_at_ms", sa.BigInteger(), nullable=False),
        sa.Column("state", SHORT_TEXT, nullable=False),
        sa.Column("selection_snapshot_id", ID, nullable=True),
        sa.Column("first_blocker", LONG_TEXT, nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("next_retry_at_ms", sa.BigInteger(), nullable=True),
        sa.Column("lease_owner", SHORT_TEXT, nullable=True),
        sa.Column("lease_expires_at_ms", sa.BigInteger(), nullable=True),
        sa.Column("projection_version", sa.BigInteger(), nullable=False),
        sa.Column("updated_at_ms", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["selection_spec_id"],
            ["brc_instrument_selection_specs.selection_spec_id"],
        ),
        sa.UniqueConstraint(
            "selection_spec_id",
            "session_start_ms",
            name="uq_brc_instrument_selection_jobs_current_period",
        ),
        sa.CheckConstraint(
            "state IN ('DUE', 'CLAIMED', 'SNAPSHOT_READY', 'SOURCE_FAILED', "
            "'COMPUTE_FAILED')",
            name="ck_brc_instrument_selection_jobs_current_state_valid",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0 AND projection_version > 0",
            name="ck_brc_instrument_selection_jobs_current_version_valid",
        ),
        sa.CheckConstraint(
            "(state = 'CLAIMED' AND lease_owner IS NOT NULL "
            "AND lease_expires_at_ms IS NOT NULL) OR "
            "(state <> 'CLAIMED' AND lease_owner IS NULL "
            "AND lease_expires_at_ms IS NULL)",
            name="ck_brc_instrument_selection_jobs_current_lease_shape",
        ),
        sa.CheckConstraint(
            "(state = 'SNAPSHOT_READY' AND selection_snapshot_id IS NOT NULL "
            "AND first_blocker IS NULL) OR "
            "(state IN ('SOURCE_FAILED', 'COMPUTE_FAILED') "
            "AND selection_snapshot_id IS NULL AND first_blocker IS NOT NULL) OR "
            "(state IN ('DUE', 'CLAIMED') AND selection_snapshot_id IS NULL)",
            name="ck_brc_instrument_selection_jobs_current_result_shape",
        ),
    )
    op.create_index(
        "ix_brc_instrument_selection_jobs_claim",
        "brc_instrument_selection_jobs_current",
        ["state", "scheduled_at_ms", "next_retry_at_ms", "lease_expires_at_ms"],
        postgresql_where=sa.text(
            "state IN ('DUE', 'CLAIMED', 'SOURCE_FAILED', 'COMPUTE_FAILED')"
        ),
    )
    op.create_table(
        "brc_instrument_selection_attempts",
        sa.Column("selection_attempt_id", ID, primary_key=True),
        sa.Column("selection_job_id", ID, nullable=False),
        sa.Column("selection_spec_id", ID, nullable=False),
        sa.Column("session_start_ms", sa.BigInteger(), nullable=False),
        sa.Column("worker_id", SHORT_TEXT, nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("started_at_ms", sa.BigInteger(), nullable=False),
        sa.Column("completed_at_ms", sa.BigInteger(), nullable=False),
        sa.Column("outcome", SHORT_TEXT, nullable=False),
        sa.Column("reason_code", LONG_TEXT, nullable=True),
        sa.Column("source_member_count", sa.Integer(), nullable=False),
        sa.Column("source_digest", LONG_TEXT, nullable=True),
        sa.ForeignKeyConstraint(
            ["selection_job_id"],
            ["brc_instrument_selection_jobs_current.selection_job_id"],
        ),
        sa.ForeignKeyConstraint(
            ["selection_spec_id"],
            ["brc_instrument_selection_specs.selection_spec_id"],
        ),
        sa.UniqueConstraint(
            "selection_spec_id",
            "session_start_ms",
            "attempt_number",
            name="uq_brc_instrument_selection_attempts_period_number",
        ),
        sa.CheckConstraint(
            "attempt_number > 0 AND completed_at_ms >= started_at_ms",
            name="ck_brc_instrument_selection_attempts_time_valid",
        ),
        sa.CheckConstraint(
            "outcome IN ('SNAPSHOT_READY', 'SOURCE_FAILED', 'COMPUTE_FAILED')",
            name="ck_brc_instrument_selection_attempts_outcome_valid",
        ),
        sa.CheckConstraint(
            "source_member_count BETWEEN 0 AND 24",
            name="ck_brc_instrument_selection_attempts_source_count_valid",
        ),
        sa.CheckConstraint(
            "source_digest IS NULL OR source_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_brc_instrument_selection_attempts_digest_valid",
        ),
    )
    op.create_index(
        "ix_brc_instrument_selection_attempts_period",
        "brc_instrument_selection_attempts",
        ["selection_spec_id", "session_start_ms", "attempt_number"],
    )
    op.create_table(
        "brc_instrument_selection_snapshots",
        sa.Column("selection_snapshot_id", ID, primary_key=True),
        sa.Column("selection_spec_id", ID, nullable=False),
        sa.Column("strategy_group_id", ID, nullable=False),
        sa.Column("strategy_version_id", ID, nullable=False),
        sa.Column("session_start_ms", sa.BigInteger(), nullable=False),
        sa.Column("decision_at_ms", sa.BigInteger(), nullable=False),
        sa.Column("feature_cutoff_at_ms", sa.BigInteger(), nullable=False),
        sa.Column("eligibility_not_before_ms", sa.BigInteger(), nullable=False),
        sa.Column("expires_at_ms", sa.BigInteger(), nullable=False),
        sa.Column("candidate_count", sa.Integer(), nullable=False),
        sa.Column("ready_count", sa.Integer(), nullable=False),
        sa.Column("selected_count", sa.Integer(), nullable=False),
        sa.Column("source_observed_at_ms", sa.BigInteger(), nullable=False),
        sa.Column("source_semantic_digest", LONG_TEXT, nullable=False),
        sa.Column("selection_semantic_digest", LONG_TEXT, nullable=False),
        sa.Column("created_at_ms", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["selection_spec_id"],
            ["brc_instrument_selection_specs.selection_spec_id"],
        ),
        sa.ForeignKeyConstraint(
            ["strategy_group_id"], ["brc_strategy_groups.strategy_group_id"]
        ),
        sa.ForeignKeyConstraint(
            ["strategy_version_id"], ["brc_strategy_versions.strategy_version_id"]
        ),
        sa.UniqueConstraint(
            "selection_spec_id",
            "session_start_ms",
            name="uq_brc_instrument_selection_snapshots_period",
        ),
        sa.UniqueConstraint(
            "selection_snapshot_id",
            "selection_semantic_digest",
            name="uq_brc_instrument_selection_snapshots_identity_digest",
        ),
        sa.CheckConstraint(
            "candidate_count = 24 AND ready_count BETWEEN 0 AND candidate_count "
            "AND selected_count = LEAST(7, ready_count)",
            name="ck_brc_instrument_selection_snapshots_count_valid",
        ),
        sa.CheckConstraint(
            "feature_cutoff_at_ms = session_start_ms + 3600000 "
            "AND eligibility_not_before_ms = session_start_ms + 4500000 "
            "AND expires_at_ms = session_start_ms + 90000000 "
            "AND decision_at_ms >= feature_cutoff_at_ms "
            "AND source_observed_at_ms >= feature_cutoff_at_ms "
            "AND created_at_ms >= decision_at_ms",
            name="ck_brc_instrument_selection_snapshots_time_valid",
        ),
        sa.CheckConstraint(
            "source_semantic_digest ~ '^sha256:[0-9a-f]{64}$' "
            "AND selection_semantic_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_brc_instrument_selection_snapshots_digest_valid",
        ),
    )
    op.create_table(
        "brc_instrument_selection_member_decisions",
        sa.Column("selection_snapshot_id", ID, nullable=False),
        sa.Column("member_decision_id", ID, nullable=False),
        sa.Column("selection_spec_id", ID, nullable=False),
        sa.Column("session_start_ms", sa.BigInteger(), nullable=False),
        sa.Column("feature_cutoff_at_ms", sa.BigInteger(), nullable=False),
        sa.Column("input_window_start_ms", sa.BigInteger(), nullable=False),
        sa.Column("input_window_end_ms", sa.BigInteger(), nullable=False),
        sa.Column("exchange_instrument_id", ID, nullable=False),
        sa.Column("input_window_digest", LONG_TEXT, nullable=False),
        sa.Column("source_status", SHORT_TEXT, nullable=False),
        sa.Column("or_high", SELECTION_DECIMAL, nullable=False),
        sa.Column("or_low", SELECTION_DECIMAL, nullable=False),
        sa.Column("or_width", SELECTION_DECIMAL, nullable=False),
        sa.Column("pre_or_atr14", SELECTION_DECIMAL, nullable=False),
        sa.Column("pre_or_width_atr14", SELECTION_DECIMAL, nullable=False),
        sa.Column("trailing_24h_quote_volume", SELECTION_DECIMAL, nullable=False),
        sa.Column("or_geometry_valid", sa.Boolean(), nullable=False),
        sa.Column("atr_valid", sa.Boolean(), nullable=False),
        sa.Column("activity_valid", sa.Boolean(), nullable=False),
        sa.Column("selection_ready", sa.Boolean(), nullable=False),
        sa.Column("primary_reason", SHORT_TEXT, nullable=True),
        sa.Column("secondary_reasons", JSONB, nullable=False),
        sa.Column("stable_rank", sa.Integer(), nullable=True),
        sa.Column("member_state", SHORT_TEXT, nullable=False),
        sa.Column("selected", sa.Boolean(), nullable=False),
        sa.Column("member_semantic_digest", LONG_TEXT, nullable=False),
        sa.PrimaryKeyConstraint("selection_snapshot_id", "exchange_instrument_id"),
        sa.UniqueConstraint(
            "member_decision_id",
            name="uq_brc_instrument_selection_member_decisions_identity",
        ),
        sa.ForeignKeyConstraint(
            ["selection_snapshot_id"],
            ["brc_instrument_selection_snapshots.selection_snapshot_id"],
        ),
        sa.ForeignKeyConstraint(
            ["selection_spec_id", "exchange_instrument_id"],
            [
                "brc_instrument_selection_spec_members.selection_spec_id",
                "brc_instrument_selection_spec_members.exchange_instrument_id",
            ],
        ),
        sa.CheckConstraint(
            "source_status = 'READY'",
            name="ck_brc_instrument_selection_member_decisions_source_valid",
        ),
        sa.CheckConstraint(
            "input_window_end_ms = feature_cutoff_at_ms "
            "AND input_window_start_ms = session_start_ms - 82800000",
            name="ck_brc_instrument_selection_member_decisions_window_valid",
        ),
        sa.CheckConstraint(
            "or_high > 0 AND or_low > 0 AND or_width >= 0 "
            "AND pre_or_atr14 >= 0 AND pre_or_width_atr14 >= 0 "
            "AND trailing_24h_quote_volume >= 0",
            name="ck_brc_instrument_selection_member_decisions_numeric_valid",
        ),
        sa.CheckConstraint(
            "primary_reason IS NULL OR primary_reason IN "
            "('INVALID_OR_GEOMETRY', 'INVALID_ATR', 'LOW_ACTIVITY')",
            name="ck_brc_instrument_selection_member_decisions_reason_valid",
        ),
        sa.CheckConstraint(
            "member_state IN ('INELIGIBLE', 'SELECTED', 'NEAR_THRESHOLD', "
            "'NOT_SELECTED')",
            name="ck_brc_instrument_selection_member_decisions_state_valid",
        ),
        sa.CheckConstraint(
            "(member_state = 'INELIGIBLE' AND selection_ready = false "
            "AND stable_rank IS NULL AND selected = false "
            "AND primary_reason IS NOT NULL) OR "
            "(member_state = 'SELECTED' AND selection_ready = true "
            "AND stable_rank BETWEEN 1 AND 7 AND selected = true "
            "AND primary_reason IS NULL) OR "
            "(member_state = 'NEAR_THRESHOLD' AND selection_ready = true "
            "AND stable_rank BETWEEN 8 AND 14 AND selected = false "
            "AND primary_reason IS NULL) OR "
            "(member_state = 'NOT_SELECTED' AND selection_ready = true "
            "AND stable_rank BETWEEN 15 AND 24 AND selected = false "
            "AND primary_reason IS NULL)",
            name="ck_brc_instrument_selection_member_decisions_rank_shape",
        ),
        sa.CheckConstraint(
            "input_window_digest ~ '^sha256:[0-9a-f]{64}$' "
            "AND member_semantic_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_brc_instrument_selection_member_decisions_digest_valid",
        ),
    )
    op.create_index(
        "ix_brc_instrument_selection_member_decisions_rank",
        "brc_instrument_selection_member_decisions",
        ["selection_snapshot_id", "stable_rank"],
    )
    op.execute(
        sa.text(
            """
            CREATE FUNCTION brc_validate_selection_snapshot_cardinality()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            DECLARE
                target_snapshot_id text;
                expected_count integer;
                actual_count integer;
            BEGIN
                target_snapshot_id := COALESCE(NEW.selection_snapshot_id, OLD.selection_snapshot_id);
                SELECT candidate_count INTO expected_count
                  FROM brc_instrument_selection_snapshots
                 WHERE selection_snapshot_id = target_snapshot_id;
                IF expected_count IS NULL THEN
                    RETURN NULL;
                END IF;
                SELECT count(*) INTO actual_count
                  FROM brc_instrument_selection_member_decisions
                 WHERE selection_snapshot_id = target_snapshot_id;
                IF actual_count <> expected_count THEN
                    RAISE EXCEPTION 'Selection Snapshot requires exact member cardinality';
                END IF;
                RETURN NULL;
            END;
            $$
            """
        )
    )
    for table in (
        "brc_instrument_selection_snapshots",
        "brc_instrument_selection_member_decisions",
    ):
        op.execute(
            sa.text(
                f"""
                CREATE CONSTRAINT TRIGGER trg_{table}_cardinality
                AFTER INSERT OR UPDATE OR DELETE ON {table}
                DEFERRABLE INITIALLY DEFERRED
                FOR EACH ROW EXECUTE FUNCTION brc_validate_selection_snapshot_cardinality()
                """
            )
        )
    op.create_foreign_key(
        "fk_brc_instrument_selection_jobs_current_snapshot",
        "brc_instrument_selection_jobs_current",
        "brc_instrument_selection_snapshots",
        ["selection_snapshot_id"],
        ["selection_snapshot_id"],
    )


def _create_materialization_tables() -> None:
    op.create_table(
        "brc_strategy_universe_materialization_generations",
        sa.Column("materialization_generation_id", ID, primary_key=True),
        sa.Column("selection_spec_id", ID, nullable=False),
        sa.Column("strategy_group_id", ID, nullable=False),
        sa.Column("strategy_version_id", ID, nullable=False),
        sa.Column("selection_mode", SHORT_TEXT, nullable=False),
        sa.Column("selection_snapshot_id", ID, nullable=True),
        sa.Column("rollback_baseline_id", ID, nullable=True),
        sa.Column("session_start_ms", sa.BigInteger(), nullable=True),
        sa.Column("previous_long_universe_version_id", ID, nullable=False),
        sa.Column("previous_short_universe_version_id", ID, nullable=False),
        sa.Column("desired_member_count", sa.Integer(), nullable=False),
        sa.Column("semantic_digest", LONG_TEXT, nullable=False),
        sa.Column("lifecycle_state", SHORT_TEXT, nullable=False),
        sa.Column("fallback_reason_code", LONG_TEXT, nullable=True),
        sa.Column("lease_owner", SHORT_TEXT, nullable=True),
        sa.Column("lease_expires_at_ms", sa.BigInteger(), nullable=True),
        sa.Column("projection_version", sa.BigInteger(), nullable=False),
        sa.Column("created_at_ms", sa.BigInteger(), nullable=False),
        sa.Column("desired_at_ms", sa.BigInteger(), nullable=True),
        sa.Column("fenced_at_ms", sa.BigInteger(), nullable=True),
        sa.Column("activated_at_ms", sa.BigInteger(), nullable=True),
        sa.Column("fallback_at_ms", sa.BigInteger(), nullable=True),
        sa.Column("terminal_at_ms", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(
            ["selection_spec_id"],
            ["brc_instrument_selection_specs.selection_spec_id"],
        ),
        sa.ForeignKeyConstraint(
            ["selection_snapshot_id"],
            ["brc_instrument_selection_snapshots.selection_snapshot_id"],
        ),
        sa.ForeignKeyConstraint(
            ["rollback_baseline_id"],
            ["brc_strategy_selection_rollback_baselines.rollback_baseline_id"],
        ),
        sa.ForeignKeyConstraint(
            ["previous_long_universe_version_id"],
            ["brc_strategy_universe_versions.universe_version_id"],
        ),
        sa.ForeignKeyConstraint(
            ["previous_short_universe_version_id"],
            ["brc_strategy_universe_versions.universe_version_id"],
        ),
        sa.UniqueConstraint(
            "selection_spec_id",
            "session_start_ms",
            "selection_mode",
            name="uq_brc_strategy_universe_materialization_generation_period",
        ),
        sa.UniqueConstraint(
            "selection_snapshot_id",
            name="uq_brc_strategy_universe_materialization_generation_snapshot",
        ),
        sa.CheckConstraint(
            "selection_mode IN ('dynamic_selection', 'static_baseline')",
            name="ck_brc_strategy_universe_materialization_generation_mode_valid",
        ),
        sa.CheckConstraint(
            "(selection_mode = 'dynamic_selection' "
            "AND selection_snapshot_id IS NOT NULL AND rollback_baseline_id IS NULL "
            "AND session_start_ms IS NOT NULL AND desired_member_count BETWEEN 1 AND 7) "
            "OR (selection_mode = 'static_baseline' "
            "AND selection_snapshot_id IS NULL AND rollback_baseline_id IS NOT NULL "
            "AND session_start_ms IS NULL AND desired_member_count BETWEEN 1 AND 10)",
            name="ck_brc_materialization_generation_source_shape",
        ),
        sa.CheckConstraint(
            "previous_long_universe_version_id <> previous_short_universe_version_id",
            name="ck_brc_materialization_generation_pair_distinct",
        ),
        sa.CheckConstraint(
            "lifecycle_state IN ('PENDING', 'DESIRED', 'DRAINING_ENTRY', "
            "'MATERIALIZING', 'STAGED', 'ACTIVE', 'FALLBACK_PREVIOUS', "
            "'SUPERSEDED', 'ABANDONED', 'FAILED_CLOSED')",
            name="ck_brc_strategy_universe_materialization_generation_state_valid",
        ),
        sa.CheckConstraint(
            "semantic_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_brc_materialization_generation_digest_valid",
        ),
        sa.CheckConstraint(
            "projection_version > 0",
            name="ck_brc_materialization_generation_version_positive",
        ),
        sa.CheckConstraint(
            "(lease_owner IS NULL AND lease_expires_at_ms IS NULL) OR "
            "(lease_owner IS NOT NULL AND lease_expires_at_ms IS NOT NULL)",
            name="ck_brc_strategy_universe_materialization_generation_lease_shape",
        ),
        sa.CheckConstraint(
            "(lifecycle_state = 'FALLBACK_PREVIOUS' AND fallback_reason_code IS NOT NULL "
            "AND fallback_at_ms IS NOT NULL AND terminal_at_ms IS NOT NULL) OR "
            "(lifecycle_state <> 'FALLBACK_PREVIOUS' AND fallback_reason_code IS NULL)",
            name="ck_brc_materialization_generation_fallback_shape",
        ),
    )
    op.create_index(
        "ix_brc_strategy_universe_materialization_generation_claim",
        "brc_strategy_universe_materialization_generations",
        ["lifecycle_state", "lease_expires_at_ms"],
        postgresql_where=sa.text(
            "lifecycle_state IN ('PENDING', 'DESIRED', 'DRAINING_ENTRY', "
            "'MATERIALIZING', 'STAGED')"
        ),
    )
    op.create_table(
        "brc_strategy_universe_materialization_targets",
        sa.Column("materialization_generation_id", ID, nullable=False),
        sa.Column("event_spec_id", ID, nullable=False),
        sa.Column("position_side", SHORT_TEXT, nullable=False),
        sa.Column("expected_member_set_digest", LONG_TEXT, nullable=False),
        sa.Column("materialization_order", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("materialization_generation_id", "event_spec_id"),
        sa.ForeignKeyConstraint(
            ["materialization_generation_id"],
            [
                "brc_strategy_universe_materialization_generations.materialization_generation_id"
            ],
        ),
        sa.ForeignKeyConstraint(
            ["event_spec_id"], ["brc_event_specs.event_spec_id"]
        ),
        sa.UniqueConstraint(
            "materialization_generation_id",
            "position_side",
            name="uq_brc_strategy_universe_materialization_targets_side",
        ),
        sa.UniqueConstraint(
            "materialization_generation_id",
            "materialization_order",
            name="uq_brc_strategy_universe_materialization_targets_order",
        ),
        sa.CheckConstraint(
            "(position_side = 'long' AND materialization_order = 1) OR "
            "(position_side = 'short' AND materialization_order = 2)",
            name="ck_brc_strategy_universe_materialization_targets_order_valid",
        ),
        sa.CheckConstraint(
            "expected_member_set_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_brc_strategy_universe_materialization_targets_digest_valid",
        ),
    )
    op.create_table(
        "brc_strategy_universe_materialization_events",
        sa.Column("materialization_event_id", ID, primary_key=True),
        sa.Column("materialization_generation_id", ID, nullable=False),
        sa.Column("event_sequence", sa.BigInteger(), nullable=False),
        sa.Column("event_type", SHORT_TEXT, nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("occurred_at_ms", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["materialization_generation_id"],
            [
                "brc_strategy_universe_materialization_generations.materialization_generation_id"
            ],
        ),
        sa.UniqueConstraint(
            "materialization_generation_id",
            "event_sequence",
            name="uq_brc_strategy_universe_materialization_events_sequence",
        ),
        sa.CheckConstraint(
            "event_sequence > 0",
            name="ck_brc_materialization_events_sequence_positive",
        ),
    )
    op.execute(
        sa.text(
            """
            CREATE FUNCTION brc_validate_materialization_generation_targets()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            DECLARE
                target_generation_id text;
                expected_selection_spec_id text;
                actual_count integer;
                matching_count integer;
            BEGIN
                target_generation_id := COALESCE(
                    NEW.materialization_generation_id,
                    OLD.materialization_generation_id
                );
                SELECT selection_spec_id INTO expected_selection_spec_id
                  FROM brc_strategy_universe_materialization_generations
                 WHERE materialization_generation_id = target_generation_id;
                IF expected_selection_spec_id IS NULL THEN
                    RETURN NULL;
                END IF;
                SELECT count(*), count(events.event_spec_id)
                  INTO actual_count, matching_count
                  FROM brc_strategy_universe_materialization_targets AS targets
                  LEFT JOIN brc_instrument_selection_spec_events AS events
                    ON events.selection_spec_id = expected_selection_spec_id
                   AND events.event_spec_id = targets.event_spec_id
                   AND events.position_side = targets.position_side
                 WHERE targets.materialization_generation_id = target_generation_id;
                IF actual_count <> 2 OR matching_count <> 2 THEN
                    RAISE EXCEPTION
                        'Materialization Generation requires exact bound LONG/SHORT targets';
                END IF;
                RETURN NULL;
            END;
            $$
            """
        )
    )
    for table in (
        "brc_strategy_universe_materialization_generations",
        "brc_strategy_universe_materialization_targets",
    ):
        op.execute(
            sa.text(
                f"""
                CREATE CONSTRAINT TRIGGER trg_{table}_target_cardinality
                AFTER INSERT OR UPDATE OR DELETE ON {table}
                DEFERRABLE INITIALLY DEFERRED
                FOR EACH ROW EXECUTE FUNCTION
                    brc_validate_materialization_generation_targets()
                """
            )
        )


def _upgrade_strategy_universe() -> None:
    op.add_column(
        "brc_strategy_universe_versions",
        sa.Column("source_kind", SHORT_TEXT, nullable=True),
    )
    op.add_column(
        "brc_strategy_universe_versions",
        sa.Column("materialization_generation_id", ID, nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE brc_strategy_universe_versions SET source_kind = 'manual' "
            "WHERE source_kind IS NULL"
        )
    )
    op.alter_column(
        "brc_strategy_universe_versions",
        "source_kind",
        existing_type=SHORT_TEXT,
        nullable=False,
        server_default=sa.text("'manual'"),
    )
    op.create_foreign_key(
        "fk_brc_strategy_universe_versions_materialization_generation",
        "brc_strategy_universe_versions",
        "brc_strategy_universe_materialization_generations",
        ["materialization_generation_id"],
        ["materialization_generation_id"],
    )
    op.create_unique_constraint(
        "uq_brc_strategy_universe_versions_generation_event",
        "brc_strategy_universe_versions",
        ["materialization_generation_id", "event_spec_id"],
    )
    op.create_check_constraint(
        "ck_brc_strategy_universe_versions_source_kind_valid",
        "brc_strategy_universe_versions",
        "source_kind IN ('manual', 'dynamic_selection', 'static_baseline')",
    )
    op.create_check_constraint(
        "ck_brc_strategy_universe_versions_source_generation_shape",
        "brc_strategy_universe_versions",
        "(source_kind = 'manual' AND materialization_generation_id IS NULL) OR "
        "(source_kind IN ('dynamic_selection', 'static_baseline') "
        "AND materialization_generation_id IS NOT NULL)",
    )
    op.drop_constraint(
        "ck_brc_strategy_universe_versions_lifecycle_state_valid",
        "brc_strategy_universe_versions",
        type_="check",
    )
    op.drop_constraint(
        "ck_brc_strategy_universe_versions_lifecycle_timestamps_valid",
        "brc_strategy_universe_versions",
        type_="check",
    )
    op.create_check_constraint(
        "ck_brc_strategy_universe_versions_lifecycle_state_valid",
        "brc_strategy_universe_versions",
        "lifecycle_state IN ('warming', 'staged', 'active', 'retired', 'abandoned')",
    )
    op.create_check_constraint(
        "ck_brc_strategy_universe_versions_lifecycle_timestamps_valid",
        "brc_strategy_universe_versions",
        "(lifecycle_state IN ('warming', 'staged') "
        "AND activated_at_ms IS NULL AND retired_at_ms IS NULL "
        "AND abandoned_at_ms IS NULL AND abandon_reason_code IS NULL) OR "
        "(lifecycle_state = 'active' AND activated_at_ms IS NOT NULL "
        "AND retired_at_ms IS NULL AND abandoned_at_ms IS NULL "
        "AND abandon_reason_code IS NULL) OR "
        "(lifecycle_state = 'retired' AND activated_at_ms IS NOT NULL "
        "AND retired_at_ms IS NOT NULL AND retired_at_ms >= activated_at_ms "
        "AND abandoned_at_ms IS NULL AND abandon_reason_code IS NULL) OR "
        "(lifecycle_state = 'abandoned' AND activated_at_ms IS NULL "
        "AND retired_at_ms IS NULL AND abandoned_at_ms IS NOT NULL "
        "AND abandon_reason_code IS NOT NULL)",
    )
    op.drop_index(
        "uq_brc_strategy_universe_versions_current_digest",
        table_name="brc_strategy_universe_versions",
    )
    op.create_index(
        "uq_brc_strategy_universe_versions_current_digest",
        "brc_strategy_universe_versions",
        ["event_spec_id", "semantic_digest"],
        unique=True,
        postgresql_where=sa.text("lifecycle_state IN ('warming', 'staged', 'active')"),
    )
    op.create_index(
        "ix_brc_strategy_universe_versions_generation",
        "brc_strategy_universe_versions",
        ["materialization_generation_id", "event_spec_id"],
    )


def _create_vacuum_and_gap_tables() -> None:
    op.create_table(
        "brc_strategy_entry_vacuums_current",
        sa.Column("entry_vacuum_id", ID, primary_key=True),
        sa.Column("strategy_group_id", ID, nullable=False),
        sa.Column("selection_spec_id", ID, nullable=False),
        sa.Column("session_start_ms", sa.BigInteger(), nullable=False),
        sa.Column("source_generation_id", ID, nullable=True),
        sa.Column("state", SHORT_TEXT, nullable=False),
        sa.Column("fenced_at_ms", sa.BigInteger(), nullable=False),
        sa.Column("drained_at_ms", sa.BigInteger(), nullable=True),
        sa.Column("resolved_at_ms", sa.BigInteger(), nullable=True),
        sa.Column("first_blocker", LONG_TEXT, nullable=False),
        sa.Column("projection_version", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["strategy_group_id"], ["brc_strategy_groups.strategy_group_id"]
        ),
        sa.ForeignKeyConstraint(
            ["selection_spec_id"],
            ["brc_instrument_selection_specs.selection_spec_id"],
        ),
        sa.ForeignKeyConstraint(
            ["source_generation_id"],
            [
                "brc_strategy_universe_materialization_generations.materialization_generation_id"
            ],
        ),
        sa.UniqueConstraint(
            "strategy_group_id",
            "selection_spec_id",
            name="uq_brc_strategy_entry_vacuums_current_scope",
        ),
        sa.CheckConstraint(
            "state IN ('OPEN', 'DRAINING_ENTRY', 'RECONFIGURING', "
            "'RESOLVED_ACTIVE', 'RESOLVED_FALLBACK', 'VALID_EMPTY', "
            "'OWNER_PAUSED', 'SUPERSEDED', 'FAILED_CLOSED')",
            name="ck_brc_strategy_entry_vacuums_current_state_valid",
        ),
        sa.CheckConstraint(
            "projection_version > 0 AND fenced_at_ms > 0",
            name="ck_brc_strategy_entry_vacuums_current_version_valid",
        ),
        sa.CheckConstraint(
            "drained_at_ms IS NULL OR drained_at_ms >= fenced_at_ms",
            name="ck_brc_strategy_entry_vacuums_current_drain_time_valid",
        ),
        sa.CheckConstraint(
            "resolved_at_ms IS NULL OR "
            "(drained_at_ms IS NOT NULL AND resolved_at_ms >= drained_at_ms)",
            name="ck_brc_strategy_entry_vacuums_current_resolution_time_valid",
        ),
    )
    op.create_table(
        "brc_strategy_entry_vacuum_events",
        sa.Column("entry_vacuum_event_id", ID, primary_key=True),
        sa.Column("entry_vacuum_id", ID, nullable=False),
        sa.Column("event_sequence", sa.BigInteger(), nullable=False),
        sa.Column("event_type", SHORT_TEXT, nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("occurred_at_ms", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["entry_vacuum_id"],
            ["brc_strategy_entry_vacuums_current.entry_vacuum_id"],
        ),
        sa.UniqueConstraint(
            "entry_vacuum_id",
            "event_sequence",
            name="uq_brc_strategy_entry_vacuum_events_sequence",
        ),
        sa.CheckConstraint(
            "event_sequence > 0",
            name="ck_brc_strategy_entry_vacuum_events_sequence_positive",
        ),
    )
    op.create_table(
        "brc_selection_authority_gap_audits_current",
        sa.Column("authority_gap_audit_id", ID, primary_key=True),
        sa.Column("selection_spec_id", ID, nullable=False),
        sa.Column("session_start_ms", sa.BigInteger(), nullable=False),
        sa.Column("gap_kind", SHORT_TEXT, nullable=False),
        sa.Column("source_entry_vacuum_id", ID, nullable=True),
        sa.Column("source_generation_id", ID, nullable=True),
        sa.Column("proposed_authority_outcome", SHORT_TEXT, nullable=False),
        sa.Column("unauthorized_from_close_time_ms", sa.BigInteger(), nullable=False),
        sa.Column("audited_through_close_time_ms", sa.BigInteger(), nullable=True),
        sa.Column("first_eligible_close_time_ms", sa.BigInteger(), nullable=True),
        sa.Column("audit_scope_digest", LONG_TEXT, nullable=True),
        sa.Column("audit_result_digest", LONG_TEXT, nullable=True),
        sa.Column("detector_semantic_digest", LONG_TEXT, nullable=False),
        sa.Column("state", SHORT_TEXT, nullable=False),
        sa.Column("first_blocker", LONG_TEXT, nullable=True),
        sa.Column("projection_version", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["selection_spec_id"],
            ["brc_instrument_selection_specs.selection_spec_id"],
        ),
        sa.ForeignKeyConstraint(
            ["source_entry_vacuum_id"],
            ["brc_strategy_entry_vacuums_current.entry_vacuum_id"],
        ),
        sa.ForeignKeyConstraint(
            ["source_generation_id"],
            [
                "brc_strategy_universe_materialization_generations.materialization_generation_id"
            ],
        ),
        sa.CheckConstraint(
            "gap_kind IN ('LATE_PRE_FENCE_CONTINUITY', 'LATE_NO_CHANGE', "
            "'ENTRY_VACUUM', 'OWNER_PAUSE')",
            name="ck_brc_selection_authority_gap_audits_current_kind_valid",
        ),
        sa.CheckConstraint(
            "state IN ('PENDING', 'COMPLETE', 'FAILED')",
            name="ck_brc_selection_authority_gap_audits_current_state_valid",
        ),
        sa.CheckConstraint(
            "projection_version > 0",
            name="ck_brc_selection_authority_gap_audits_current_version_positive",
        ),
        sa.CheckConstraint(
            "detector_semantic_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_brc_authority_gap_audits_detector_digest_valid",
        ),
        sa.CheckConstraint(
            "(state = 'PENDING' AND audited_through_close_time_ms IS NULL "
            "AND first_eligible_close_time_ms IS NULL "
            "AND audit_scope_digest IS NULL AND audit_result_digest IS NULL) OR "
            "(state = 'COMPLETE' AND audited_through_close_time_ms IS NOT NULL "
            "AND first_eligible_close_time_ms > audited_through_close_time_ms "
            "AND audit_scope_digest ~ '^sha256:[0-9a-f]{64}$' "
            "AND audit_result_digest ~ '^sha256:[0-9a-f]{64}$' "
            "AND first_blocker IS NULL) OR "
            "(state = 'FAILED' AND first_blocker IS NOT NULL)",
            name="ck_brc_selection_authority_gap_audits_current_result_shape",
        ),
    )
    op.create_table(
        "brc_selection_authority_gap_audit_events",
        sa.Column("authority_gap_audit_event_id", ID, primary_key=True),
        sa.Column("authority_gap_audit_id", ID, nullable=False),
        sa.Column("event_sequence", sa.BigInteger(), nullable=False),
        sa.Column("event_type", SHORT_TEXT, nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("occurred_at_ms", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["authority_gap_audit_id"],
            ["brc_selection_authority_gap_audits_current.authority_gap_audit_id"],
        ),
        sa.UniqueConstraint(
            "authority_gap_audit_id",
            "event_sequence",
            name="uq_brc_selection_authority_gap_audit_events_sequence",
        ),
        sa.CheckConstraint(
            "event_sequence > 0",
            name="ck_brc_selection_authority_gap_audit_events_sequence_positive",
        ),
    )


def _create_authority_tables() -> None:
    op.create_table(
        "brc_selection_session_authorities",
        sa.Column("selection_authority_id", ID, primary_key=True),
        sa.Column("selection_spec_id", ID, nullable=False),
        sa.Column("session_start_ms", sa.BigInteger(), nullable=False),
        sa.Column("decision_boundary_ms", sa.BigInteger(), nullable=False),
        sa.Column("authority_sequence", sa.BigInteger(), nullable=False),
        sa.Column("selection_mode", SHORT_TEXT, nullable=False),
        sa.Column("selection_job_id", ID, nullable=True),
        sa.Column("selection_attempt_id", ID, nullable=True),
        sa.Column("selection_snapshot_id", ID, nullable=True),
        sa.Column("continued_from_selection_authority_id", ID, nullable=True),
        sa.Column("continuity_source_kind", SHORT_TEXT, nullable=False),
        sa.Column("authority_gap_audit_id", ID, nullable=True),
        sa.Column("materialization_generation_id", ID, nullable=True),
        sa.Column("owner_control_version", sa.BigInteger(), nullable=False),
        sa.Column("authority_outcome", SHORT_TEXT, nullable=False),
        sa.Column("authorized_long_universe_version_id", ID, nullable=True),
        sa.Column("authorized_short_universe_version_id", ID, nullable=True),
        sa.Column("grant_proof_kind", SHORT_TEXT, nullable=True),
        sa.Column("grant_predecessor_authority_id", ID, nullable=True),
        sa.Column("effective_from_ms", sa.BigInteger(), nullable=False),
        sa.Column("first_eligible_close_time_ms", sa.BigInteger(), nullable=True),
        sa.Column("expires_at_ms", sa.BigInteger(), nullable=False),
        sa.Column("reason_code", LONG_TEXT, nullable=False),
        sa.Column("semantic_digest", LONG_TEXT, nullable=False),
        sa.Column("created_at_ms", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["selection_spec_id"],
            ["brc_instrument_selection_specs.selection_spec_id"],
        ),
        sa.ForeignKeyConstraint(
            ["selection_job_id"],
            ["brc_instrument_selection_jobs_current.selection_job_id"],
        ),
        sa.ForeignKeyConstraint(
            ["selection_attempt_id"],
            ["brc_instrument_selection_attempts.selection_attempt_id"],
        ),
        sa.ForeignKeyConstraint(
            ["selection_snapshot_id"],
            ["brc_instrument_selection_snapshots.selection_snapshot_id"],
        ),
        sa.ForeignKeyConstraint(
            ["continued_from_selection_authority_id"],
            ["brc_selection_session_authorities.selection_authority_id"],
        ),
        sa.ForeignKeyConstraint(
            ["authority_gap_audit_id"],
            ["brc_selection_authority_gap_audits_current.authority_gap_audit_id"],
        ),
        sa.ForeignKeyConstraint(
            ["materialization_generation_id"],
            [
                "brc_strategy_universe_materialization_generations.materialization_generation_id"
            ],
        ),
        sa.ForeignKeyConstraint(
            ["authorized_long_universe_version_id"],
            ["brc_strategy_universe_versions.universe_version_id"],
        ),
        sa.ForeignKeyConstraint(
            ["authorized_short_universe_version_id"],
            ["brc_strategy_universe_versions.universe_version_id"],
        ),
        sa.UniqueConstraint(
            "selection_spec_id",
            "session_start_ms",
            "authority_sequence",
            name="uq_brc_selection_session_authorities_sequence",
        ),
        sa.CheckConstraint(
            "selection_mode IN ('disabled', 'static_baseline', 'dynamic_selection')",
            name="ck_brc_selection_session_authorities_mode_valid",
        ),
        sa.CheckConstraint(
            "continuity_source_kind IN ('SELECTION_AUTHORITY', 'STATIC_BASELINE', "
            "'AUTHORITY_GAP_AUDIT', 'NONE')",
            name="ck_brc_selection_session_authorities_continuity_source_valid",
        ),
        sa.CheckConstraint(
            "authority_outcome IN ('PRE_FENCE_CONTINUITY', 'ACTIVE_NEW', "
            "'NO_CHANGE', 'FALLBACK_PREVIOUS', 'VALID_EMPTY', "
            "'OWNER_PAUSED_NOT_MATERIALIZED')",
            name="ck_brc_selection_session_authorities_outcome_valid",
        ),
        sa.CheckConstraint(
            "grant_proof_kind IS NULL OR grant_proof_kind IN "
            "('CONTINUOUS_ELIGIBLE_CLOSES', 'AUDITED_AUTHORITY_GAP')",
            name="ck_brc_selection_session_authorities_proof_kind_valid",
        ),
        sa.CheckConstraint(
            "authority_sequence > 0 AND owner_control_version > 0 "
            "AND decision_boundary_ms = session_start_ms + 3600000 "
            "AND effective_from_ms >= decision_boundary_ms "
            "AND expires_at_ms = session_start_ms + 90000000 "
            "AND created_at_ms >= effective_from_ms AND created_at_ms < expires_at_ms",
            name="ck_brc_selection_session_authorities_time_valid",
        ),
        sa.CheckConstraint(
            "semantic_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_brc_selection_session_authorities_digest_valid",
        ),
        sa.CheckConstraint(
            "(authority_outcome IN ('PRE_FENCE_CONTINUITY', 'ACTIVE_NEW', "
            "'NO_CHANGE', 'FALLBACK_PREVIOUS') "
            "AND authorized_long_universe_version_id IS NOT NULL "
            "AND authorized_short_universe_version_id IS NOT NULL "
            "AND authorized_long_universe_version_id <> authorized_short_universe_version_id "
            "AND first_eligible_close_time_ms IS NOT NULL "
            "AND first_eligible_close_time_ms % 900000 = 0 "
            "AND first_eligible_close_time_ms > created_at_ms "
            "AND first_eligible_close_time_ms < expires_at_ms "
            "AND grant_proof_kind IS NOT NULL) OR "
            "(authority_outcome IN ('VALID_EMPTY', 'OWNER_PAUSED_NOT_MATERIALIZED') "
            "AND authorized_long_universe_version_id IS NULL "
            "AND authorized_short_universe_version_id IS NULL "
            "AND first_eligible_close_time_ms IS NULL "
            "AND grant_proof_kind IS NULL "
            "AND grant_predecessor_authority_id IS NULL)",
            name="ck_brc_selection_session_authorities_grant_shape",
        ),
        sa.CheckConstraint(
            "(grant_proof_kind = 'CONTINUOUS_ELIGIBLE_CLOSES' "
            "AND grant_predecessor_authority_id IS NOT NULL "
            "AND authority_gap_audit_id IS NULL "
            "AND continuity_source_kind IN ('SELECTION_AUTHORITY', 'STATIC_BASELINE')) OR "
            "(grant_proof_kind = 'AUDITED_AUTHORITY_GAP' "
            "AND grant_predecessor_authority_id IS NULL "
            "AND authority_gap_audit_id IS NOT NULL "
            "AND continuity_source_kind IN ('AUTHORITY_GAP_AUDIT', 'STATIC_BASELINE')) OR "
            "grant_proof_kind IS NULL",
            name="ck_brc_selection_session_authorities_proof_shape",
        ),
        sa.CheckConstraint(
            "(authority_outcome = 'ACTIVE_NEW' AND selection_mode = 'dynamic_selection' "
            "AND selection_snapshot_id IS NOT NULL "
            "AND materialization_generation_id IS NOT NULL "
            "AND grant_proof_kind = 'AUDITED_AUTHORITY_GAP') OR "
            "authority_outcome <> 'ACTIVE_NEW'",
            name="ck_brc_selection_session_authorities_active_new_shape",
        ),
        sa.CheckConstraint(
            "(authority_outcome = 'FALLBACK_PREVIOUS' "
            "AND selection_snapshot_id IS NOT NULL "
            "AND materialization_generation_id IS NOT NULL "
            "AND authority_gap_audit_id IS NOT NULL "
            "AND grant_proof_kind = 'AUDITED_AUTHORITY_GAP') OR "
            "authority_outcome <> 'FALLBACK_PREVIOUS'",
            name="ck_brc_selection_session_authorities_fallback_shape",
        ),
        sa.CheckConstraint(
            "(authority_outcome = 'VALID_EMPTY' "
            "AND selection_mode = 'dynamic_selection' "
            "AND selection_snapshot_id IS NOT NULL "
            "AND materialization_generation_id IS NULL "
            "AND continuity_source_kind = 'NONE') OR "
            "authority_outcome <> 'VALID_EMPTY'",
            name="ck_brc_selection_session_authorities_valid_empty_shape",
        ),
    )
    op.create_index(
        "ix_brc_selection_session_authorities_period",
        "brc_selection_session_authorities",
        ["selection_spec_id", "session_start_ms", "authority_sequence"],
    )
    op.create_table(
        "brc_selection_authority_current",
        sa.Column("selection_spec_id", ID, primary_key=True),
        sa.Column("selection_authority_id", ID, nullable=False),
        sa.Column("projection_version", sa.BigInteger(), nullable=False),
        sa.Column("updated_at_ms", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["selection_spec_id"],
            ["brc_instrument_selection_specs.selection_spec_id"],
        ),
        sa.ForeignKeyConstraint(
            ["selection_authority_id"],
            ["brc_selection_session_authorities.selection_authority_id"],
        ),
        sa.CheckConstraint(
            "projection_version > 0",
            name="ck_brc_selection_authority_current_version_positive",
        ),
    )


def _create_suppression_and_release_tables() -> None:
    op.create_table(
        "brc_strategy_trigger_suppressions",
        sa.Column("trigger_suppression_id", ID, primary_key=True),
        sa.Column("authority_gap_audit_id", ID, nullable=False),
        sa.Column("entry_vacuum_id", ID, nullable=True),
        sa.Column("materialization_generation_id", ID, nullable=True),
        sa.Column("event_spec_id", ID, nullable=False),
        sa.Column("exchange_instrument_id", ID, nullable=False),
        sa.Column("session_reference", LONG_TEXT, nullable=False),
        sa.Column("first_natural_trigger_at_ms", sa.BigInteger(), nullable=False),
        sa.Column("reason_code", SHORT_TEXT, nullable=False),
        sa.Column("detector_semantic_digest", LONG_TEXT, nullable=False),
        sa.Column("created_at_ms", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["authority_gap_audit_id"],
            ["brc_selection_authority_gap_audits_current.authority_gap_audit_id"],
        ),
        sa.ForeignKeyConstraint(
            ["entry_vacuum_id"],
            ["brc_strategy_entry_vacuums_current.entry_vacuum_id"],
        ),
        sa.ForeignKeyConstraint(
            ["materialization_generation_id"],
            [
                "brc_strategy_universe_materialization_generations.materialization_generation_id"
            ],
        ),
        sa.ForeignKeyConstraint(["event_spec_id"], ["brc_event_specs.event_spec_id"]),
        sa.ForeignKeyConstraint(
            ["exchange_instrument_id"], ["brc_instruments.exchange_instrument_id"]
        ),
        sa.UniqueConstraint(
            "event_spec_id",
            "exchange_instrument_id",
            "session_reference",
            name="uq_brc_strategy_trigger_suppressions_episode",
        ),
        sa.CheckConstraint(
            "reason_code = 'TRIGGER_DURING_AUTHORITY_GAP'",
            name="ck_brc_strategy_trigger_suppressions_reason_valid",
        ),
        sa.CheckConstraint(
            "detector_semantic_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_brc_strategy_trigger_suppressions_digest_valid",
        ),
    )
    op.create_table(
        "brc_runtime_release_compatibility_facts",
        sa.Column("release_compatibility_id", ID, primary_key=True),
        sa.Column("from_commit", SHORT_TEXT, nullable=False),
        sa.Column("to_commit", SHORT_TEXT, nullable=False),
        sa.Column("from_schema_revision", SHORT_TEXT, nullable=False),
        sa.Column("to_schema_revision", SHORT_TEXT, nullable=False),
        sa.Column("classification", SHORT_TEXT, nullable=False),
        sa.Column("compatibility_basis_digest", LONG_TEXT, nullable=False),
        sa.Column("reason_codes", JSONB, nullable=False),
        sa.Column("certification_manifest_digest", LONG_TEXT, nullable=False),
        sa.Column("created_at_ms", sa.BigInteger(), nullable=False),
        sa.UniqueConstraint(
            "from_commit",
            "to_commit",
            "from_schema_revision",
            "to_schema_revision",
            name="uq_brc_runtime_release_compatibility_facts_transition",
        ),
        sa.CheckConstraint(
            "from_commit ~ '^[0-9a-f]{40}$' AND to_commit ~ '^[0-9a-f]{40}$'",
            name="ck_brc_runtime_release_compatibility_facts_commit_valid",
        ),
        sa.CheckConstraint(
            "classification IN ('COMPATIBLE_RESTART', "
            "'REQUIRES_RUNTIME_REMATERIALIZATION')",
            name="ck_brc_runtime_release_compatibility_facts_classification_valid",
        ),
        sa.CheckConstraint(
            "compatibility_basis_digest ~ '^sha256:[0-9a-f]{64}$' "
            "AND certification_manifest_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_brc_runtime_release_compatibility_facts_digest_valid",
        ),
    )


def _add_selection_lineage() -> None:
    for table in (
        "brc_signal_events",
        "brc_capacity_claims",
        "brc_admission_decisions",
        "brc_trade_tickets",
    ):
        op.add_column(table, sa.Column("selection_authority_id", ID, nullable=True))
        op.create_foreign_key(
            f"fk_{table}_selection_authority",
            table,
            "brc_selection_session_authorities",
            ["selection_authority_id"],
            ["selection_authority_id"],
        )
        op.create_index(
            f"ix_{table}_selection_authority_id",
            table,
            ["selection_authority_id"],
        )


def _install_immutability_guards() -> None:
    op.execute(
        sa.text(
            """
            CREATE FUNCTION brc_reject_immutable_selection_fact_mutation()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                RAISE EXCEPTION 'immutable Selection fact cannot be updated or deleted';
            END;
            $$
            """
        )
    )
    immutable_tables = (
        "brc_instrument_selection_specs",
        "brc_sor_dynamic_selection_specs_v0",
        "brc_instrument_selection_spec_events",
        "brc_instrument_selection_spec_members",
        "brc_strategy_selection_rollback_baselines",
        "brc_instrument_selection_attempts",
        "brc_instrument_selection_snapshots",
        "brc_instrument_selection_member_decisions",
        "brc_strategy_universe_materialization_targets",
        "brc_strategy_universe_materialization_events",
        "brc_selection_session_authorities",
        "brc_strategy_entry_vacuum_events",
        "brc_selection_authority_gap_audit_events",
        "brc_strategy_trigger_suppressions",
        "brc_runtime_release_compatibility_facts",
    )
    for table in immutable_tables:
        op.execute(
            sa.text(
                f"""
                CREATE TRIGGER trg_{table}_immutable
                BEFORE UPDATE OR DELETE ON {table}
                FOR EACH ROW EXECUTE FUNCTION brc_reject_immutable_selection_fact_mutation()
                """
            )
        )


def _seed_frozen_sor_v0_if_registry_exists() -> None:
    connection = op.get_bind()
    registry_ready = bool(
        connection.scalar(
            sa.text(
                "SELECT count(*) = 2 FROM brc_event_specs "
                "WHERE event_spec_id IN "
                "('event_spec:SOR-001:SOR-LONG:v4', "
                "'event_spec:SOR-001:SOR-SHORT:v4') "
                "AND strategy_version_id = 'sgv:SOR-001:v4'"
            )
        )
    )
    if not registry_ready:
        return
    now_ms = int(
        connection.scalar(
            sa.text("SELECT floor(extract(epoch FROM clock_timestamp()) * 1000)::bigint")
        )
    )
    for symbol in _CANDIDATE_SYMBOLS:
        instrument_id = f"binance-usdm:{symbol}:perpetual"
        connection.execute(
            sa.text(
                """
                INSERT INTO brc_instruments (
                    exchange_instrument_id, venue_id, asset_class, venue_symbol,
                    contract_kind, status
                ) VALUES (:instrument_id, 'binance-usdm', 'crypto', :symbol,
                          'perpetual', 'pending_certification')
                ON CONFLICT (exchange_instrument_id) DO NOTHING
                """
            ),
            {"instrument_id": instrument_id, "symbol": symbol},
        )
        profile_payload = {
            "asset_class": "crypto",
            "contract_type": "perpetual",
            "entry_session_policy": "continuous",
            "margin_asset": "USDT",
            "product_family": "crypto_perpetual",
            "status": "candidate",
            "underlying_type": "crypto_asset",
        }
        profile_digest = "sha256:" + hashlib.sha256(
            json.dumps(
                profile_payload,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        connection.execute(
            sa.text(
                """
                INSERT INTO brc_instrument_product_profiles (
                    exchange_instrument_id, product_family, asset_class,
                    contract_type, underlying_type, margin_asset,
                    entry_session_policy, status, max_entry_spread_bps,
                    max_mark_index_deviation_bps, semantic_digest, updated_at_ms
                ) VALUES (
                    :instrument_id, 'crypto_perpetual', 'crypto', 'perpetual',
                    'crypto_asset', 'USDT', 'continuous', 'candidate', NULL,
                    NULL, :semantic_digest, :updated_at_ms
                )
                ON CONFLICT (exchange_instrument_id) DO NOTHING
                """
            ),
            {
                "instrument_id": instrument_id,
                "semantic_digest": profile_digest,
                "updated_at_ms": now_ms,
            },
        )
    connection.execute(
        sa.text(
            """
            INSERT INTO brc_instrument_selection_specs (
                selection_spec_id, strategy_group_id, strategy_version_id,
                selection_version, selection_kind, algorithm_semantic_digest,
                status, installed_at_ms
            ) VALUES (
                :selection_spec_id, 'SOR-001', 'sgv:SOR-001:v4', 1,
                'sor_dynamic_v0', :algorithm_digest, 'active', :installed_at_ms
            )
            """
        ),
        {
            "selection_spec_id": _SELECTION_SPEC_ID,
            "algorithm_digest": _SELECTION_SPEC_DIGEST,
            "installed_at_ms": now_ms,
        },
    )
    connection.execute(
        sa.text(
            """
            INSERT INTO brc_sor_dynamic_selection_specs_v0 (
                selection_spec_id, decision_offset_utc_seconds,
                feature_cutoff_offset_utc_seconds,
                eligibility_not_before_offset_utc_seconds,
                valid_until_next_decision_offset_seconds, candidate_count,
                selected_count_max, near_count_max, activity_floor_quote_usdt,
                materialization_timeout_seconds
            ) VALUES (
                :selection_spec_id, 3600, 3600, 4500, 86400, 24, 7, 7,
                20000000, 1800
            )
            """
        ),
        {"selection_spec_id": _SELECTION_SPEC_ID},
    )
    connection.execute(
        sa.text(
            """
            INSERT INTO brc_instrument_selection_spec_events (
                selection_spec_id, event_spec_id, position_side
            ) VALUES (:selection_spec_id, :event_spec_id, :position_side)
            """
        ),
        [
            {
                "selection_spec_id": _SELECTION_SPEC_ID,
                "event_spec_id": event_spec_id,
                "position_side": side,
            }
            for event_spec_id, side in _SOR_EVENTS
        ],
    )
    connection.execute(
        sa.text(
            """
            INSERT INTO brc_instrument_selection_spec_members (
                selection_spec_id, exchange_instrument_id
            ) VALUES (:selection_spec_id, :exchange_instrument_id)
            """
        ),
        [
            {
                "selection_spec_id": _SELECTION_SPEC_ID,
                "exchange_instrument_id": f"binance-usdm:{symbol}:perpetual",
            }
            for symbol in sorted(_CANDIDATE_SYMBOLS)
        ],
    )
    rollback_baseline_id = _capture_rollback_baseline(connection, now_ms=now_ms)
    connection.execute(
        sa.text(
            """
            INSERT INTO brc_strategy_selection_control_current (
                strategy_group_id, selection_spec_id, selection_mode,
                pending_selection_mode, pending_effective_session_start_ms,
                pending_authorization_id, control_version, rollback_baseline_id,
                updated_at_ms
            ) VALUES (
                'SOR-001', :selection_spec_id, 'static_baseline', NULL, NULL,
                NULL, 1, :rollback_baseline_id, :updated_at_ms
            )
            """
        ),
        {
            "selection_spec_id": _SELECTION_SPEC_ID,
            "rollback_baseline_id": rollback_baseline_id,
            "updated_at_ms": now_ms,
        },
    )


def _capture_rollback_baseline(
    connection: sa.Connection,
    *,
    now_ms: int,
) -> str | None:
    pair = connection.execute(
        sa.text(
            """
            SELECT current.event_spec_id, current.universe_version_id,
                   current.semantic_digest
              FROM brc_strategy_universe_current AS current
             WHERE current.event_spec_id IN (
                 'event_spec:SOR-001:SOR-LONG:v4',
                 'event_spec:SOR-001:SOR-SHORT:v4'
             )
             ORDER BY current.event_spec_id
            """
        )
    ).all()
    if len(pair) != 2:
        return None
    by_event = {str(row[0]): (str(row[1]), str(row[2])) for row in pair}
    long_identity = by_event.get("event_spec:SOR-001:SOR-LONG:v4")
    short_identity = by_event.get("event_spec:SOR-001:SOR-SHORT:v4")
    if long_identity is None or short_identity is None:
        return None
    rollback_baseline_id = "rollback-baseline:SOR-001:pre-dynamic-v0"
    semantic_digest = "sha256:" + hashlib.sha256(
        json.dumps(
            {
                "long_universe_version_id": long_identity[0],
                "long_universe_semantic_digest": long_identity[1],
                "short_universe_version_id": short_identity[0],
                "short_universe_semantic_digest": short_identity[1],
                "strategy_group_id": "SOR-001",
                "strategy_version_id": "sgv:SOR-001:v4",
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    connection.execute(
        sa.text(
            """
            INSERT INTO brc_strategy_selection_rollback_baselines (
                rollback_baseline_id, strategy_group_id, strategy_version_id,
                source_long_universe_version_id,
                source_short_universe_version_id, semantic_digest,
                captured_at_ms
            ) VALUES (
                :rollback_baseline_id, 'SOR-001', 'sgv:SOR-001:v4',
                :long_universe_version_id, :short_universe_version_id,
                :semantic_digest, :captured_at_ms
            )
            """
        ),
        {
            "rollback_baseline_id": rollback_baseline_id,
            "long_universe_version_id": long_identity[0],
            "short_universe_version_id": short_identity[0],
            "semantic_digest": semantic_digest,
            "captured_at_ms": now_ms,
        },
    )
    return rollback_baseline_id
