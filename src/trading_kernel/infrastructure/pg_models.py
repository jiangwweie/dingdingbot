"""Clean PostgreSQL authority model for the replacement trading kernel."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
metadata = sa.MetaData(naming_convention=NAMING_CONVENTION)

ID = sa.String(160)
SHORT_TEXT = sa.String(96)
LONG_TEXT = sa.String(512)
MONEY = sa.Numeric(38, 18)
SELECTION_DECIMAL = sa.Numeric()


def _id(name: str, *, primary_key: bool = False, nullable: bool = False) -> sa.Column:
    return sa.Column(name, ID, primary_key=primary_key, nullable=nullable)


def _time(name: str, *, nullable: bool = False) -> sa.Column:
    return sa.Column(name, sa.BigInteger, nullable=nullable)


def _json(name: str, *, nullable: bool = False) -> sa.Column:
    return sa.Column(name, JSONB, nullable=nullable)


strategy_groups = sa.Table(
    "brc_strategy_groups",
    metadata,
    _id("strategy_group_id", primary_key=True),
    sa.Column("display_name", LONG_TEXT, nullable=False),
    _id("active_version_id", nullable=True),
    sa.Column("status", SHORT_TEXT, nullable=False),
    _time("updated_at_ms"),
)

strategy_versions = sa.Table(
    "brc_strategy_versions",
    metadata,
    _id("strategy_version_id", primary_key=True),
    _id("strategy_group_id"),
    sa.Column("version", sa.Integer, nullable=False),
    _json("semantics"),
    sa.Column("status", SHORT_TEXT, nullable=False),
    _time("created_at_ms"),
    sa.UniqueConstraint("strategy_group_id", "version"),
)

event_specs = sa.Table(
    "brc_event_specs",
    metadata,
    _id("event_spec_id", primary_key=True),
    _id("strategy_version_id"),
    sa.Column("event_id", SHORT_TEXT, nullable=False),
    sa.Column("position_side", SHORT_TEXT, nullable=False),
    sa.Column("timeframe", SHORT_TEXT, nullable=False),
    sa.Column("freshness_window_ms", sa.BigInteger, nullable=False),
    sa.Column("event_time_authority", SHORT_TEXT, nullable=False),
    sa.Column("entry_order_type", SHORT_TEXT, nullable=False),
    _id("protection_reference_fact_definition_id"),
    _id("exit_policy_id"),
    _json("execution_semantics"),
    sa.Column("status", SHORT_TEXT, nullable=False),
    _time("created_at_ms"),
    sa.UniqueConstraint("strategy_version_id", "event_id"),
)

exit_policies = sa.Table(
    "brc_exit_policies",
    metadata,
    _id("exit_policy_id", primary_key=True),
    sa.Column("exit_policy_version", SHORT_TEXT, nullable=False),
    _id("event_spec_id", nullable=True),
    sa.Column("profile_schema_version", SHORT_TEXT, nullable=True),
    sa.Column("position_side", SHORT_TEXT, nullable=False),
    _json("policy"),
    sa.Column("semantic_hash", LONG_TEXT, nullable=False),
    sa.Column("status", SHORT_TEXT, nullable=False),
    _time("created_at_ms"),
    sa.UniqueConstraint("semantic_hash"),
    sa.UniqueConstraint("exit_policy_id", "semantic_hash"),
    sa.CheckConstraint(
        "position_side IN ('long', 'short')",
        name="position_side_valid",
    ),
    sa.CheckConstraint(
        "(event_spec_id IS NOT NULL AND profile_schema_version IS NULL) OR "
        "(event_spec_id IS NULL AND profile_schema_version = 'exit_profile_v1')",
        name="profile_schema_shape_valid",
    ),
)

event_exit_profile_bindings = sa.Table(
    "brc_event_exit_profile_bindings",
    metadata,
    _id("exit_binding_id", primary_key=True),
    sa.Column("binding_version", sa.BigInteger, nullable=False),
    _id("event_spec_id"),
    _id("exit_profile_id"),
    sa.Column("exit_profile_semantic_hash", LONG_TEXT, nullable=False),
    sa.Column("binding_semantic_hash", LONG_TEXT, nullable=False),
    sa.Column("activation_reason", LONG_TEXT, nullable=False),
    _time("created_at_ms"),
    sa.UniqueConstraint("event_spec_id", "binding_version"),
    sa.UniqueConstraint("exit_binding_id", "binding_semantic_hash"),
    sa.ForeignKeyConstraint(
        ["event_spec_id"],
        ["brc_event_specs.event_spec_id"],
    ),
    sa.ForeignKeyConstraint(
        ["exit_profile_id", "exit_profile_semantic_hash"],
        ["brc_exit_policies.exit_policy_id", "brc_exit_policies.semantic_hash"],
        match="FULL",
    ),
    sa.CheckConstraint("binding_version > 0", name="binding_version_positive"),
    sa.CheckConstraint(
        "exit_profile_semantic_hash ~ '^sha256:[0-9a-f]{64}$' "
        "AND binding_semantic_hash ~ '^sha256:[0-9a-f]{64}$'",
        name="binding_hashes_valid",
    ),
)

event_exit_profile_binding_current = sa.Table(
    "brc_event_exit_profile_binding_current",
    metadata,
    _id("event_spec_id", primary_key=True),
    _id("exit_binding_id"),
    sa.Column("binding_semantic_hash", LONG_TEXT, nullable=False),
    sa.Column("projection_version", sa.BigInteger, nullable=False),
    _time("activated_at_ms"),
    sa.UniqueConstraint("exit_binding_id"),
    sa.ForeignKeyConstraint(
        ["event_spec_id"],
        ["brc_event_specs.event_spec_id"],
    ),
    sa.ForeignKeyConstraint(
        ["exit_binding_id", "binding_semantic_hash"],
        [
            "brc_event_exit_profile_bindings.exit_binding_id",
            "brc_event_exit_profile_bindings.binding_semantic_hash",
        ],
        match="FULL",
    ),
    sa.CheckConstraint("projection_version > 0", name="projection_version_positive"),
    sa.CheckConstraint(
        "binding_semantic_hash ~ '^sha256:[0-9a-f]{64}$'",
        name="binding_semantic_hash_valid",
    ),
)

event_exit_profile_binding_events = sa.Table(
    "brc_event_exit_profile_binding_events",
    metadata,
    _id("binding_event_id", primary_key=True),
    _id("event_spec_id"),
    _id("exit_binding_id"),
    sa.Column("binding_version", sa.BigInteger, nullable=False),
    sa.Column("operation", SHORT_TEXT, nullable=False),
    sa.Column("authorization_source", SHORT_TEXT, nullable=False),
    _id("owner_authorization_id", nullable=True),
    sa.Column("reason", LONG_TEXT, nullable=False),
    _time("created_at_ms"),
    sa.UniqueConstraint("exit_binding_id", "operation"),
    sa.ForeignKeyConstraint(
        ["event_spec_id"],
        ["brc_event_specs.event_spec_id"],
    ),
    sa.ForeignKeyConstraint(
        ["exit_binding_id"],
        ["brc_event_exit_profile_bindings.exit_binding_id"],
    ),
    sa.ForeignKeyConstraint(
        ["owner_authorization_id"],
        ["brc_owner_authorizations.authorization_id"],
    ),
    sa.CheckConstraint("binding_version > 0", name="binding_version_positive"),
    sa.CheckConstraint(
        "operation IN ('ACTIVATED', 'RETIRED')",
        name="operation_valid",
    ),
    sa.CheckConstraint(
        "authorization_source IN ('system_migration', 'owner_control')",
        name="authorization_source_valid",
    ),
    sa.CheckConstraint(
        "(authorization_source = 'system_migration' "
        "AND owner_authorization_id IS NULL) OR "
        "(authorization_source = 'owner_control' "
        "AND owner_authorization_id IS NOT NULL)",
        name="authorization_shape_valid",
    ),
)

fact_definitions = sa.Table(
    "brc_fact_definitions",
    metadata,
    _id("fact_definition_id", primary_key=True),
    sa.Column("fact_name", SHORT_TEXT, nullable=False, unique=True),
    sa.Column("value_type", SHORT_TEXT, nullable=False),
    sa.Column("freshness_ms", sa.BigInteger, nullable=False),
    _json("validation"),
)

event_required_facts = sa.Table(
    "brc_event_required_facts",
    metadata,
    _id("event_spec_id"),
    _id("fact_definition_id"),
    sa.Column("role", SHORT_TEXT, nullable=False),
    sa.Column("required", sa.Boolean, nullable=False, server_default=sa.true()),
    sa.PrimaryKeyConstraint("event_spec_id", "fact_definition_id"),
)

instruments = sa.Table(
    "brc_instruments",
    metadata,
    _id("exchange_instrument_id", primary_key=True),
    sa.Column("venue_id", SHORT_TEXT, nullable=False),
    sa.Column("asset_class", SHORT_TEXT, nullable=False),
    sa.Column("venue_symbol", SHORT_TEXT, nullable=False),
    sa.Column("contract_kind", SHORT_TEXT, nullable=False),
    sa.Column("status", SHORT_TEXT, nullable=False),
    sa.UniqueConstraint("venue_id", "venue_symbol"),
    sa.CheckConstraint(
        "status IN ('pending_certification', 'active')",
        name="status_valid",
    ),
)

event_product_compatibility = sa.Table(
    "brc_event_product_compatibility",
    metadata,
    _id("event_spec_id", primary_key=True),
    sa.Column("product_family", SHORT_TEXT, nullable=False),
    sa.Column("asset_class", SHORT_TEXT, nullable=False),
    sa.Column("contract_type", SHORT_TEXT, nullable=False),
    sa.Column("underlying_type", SHORT_TEXT, nullable=False),
    sa.Column("margin_asset", SHORT_TEXT, nullable=False),
    sa.Column("semantic_digest", LONG_TEXT, nullable=False),
    _time("created_at_ms"),
    sa.ForeignKeyConstraint(
        ["event_spec_id"],
        ["brc_event_specs.event_spec_id"],
    ),
    sa.CheckConstraint(
        "product_family IN ('crypto_perpetual', 'tradfi_equity_perpetual')",
        name="product_family_valid",
    ),
    sa.CheckConstraint(
        "asset_class IN ('crypto', 'equity')",
        name="asset_class_valid",
    ),
    sa.CheckConstraint(
        "semantic_digest ~ '^sha256:[0-9a-f]{64}$'",
        name="semantic_digest_valid",
    ),
)

instrument_product_profiles = sa.Table(
    "brc_instrument_product_profiles",
    metadata,
    _id("exchange_instrument_id", primary_key=True),
    sa.Column("product_family", SHORT_TEXT, nullable=False),
    sa.Column("asset_class", SHORT_TEXT, nullable=False),
    sa.Column("contract_type", SHORT_TEXT, nullable=False),
    sa.Column("underlying_type", SHORT_TEXT, nullable=False),
    sa.Column("margin_asset", SHORT_TEXT, nullable=False),
    sa.Column("entry_session_policy", SHORT_TEXT, nullable=False),
    sa.Column("status", SHORT_TEXT, nullable=False),
    sa.Column("max_entry_spread_bps", MONEY, nullable=True),
    sa.Column("max_mark_index_deviation_bps", MONEY, nullable=True),
    sa.Column("semantic_digest", LONG_TEXT, nullable=False),
    _time("updated_at_ms"),
    sa.CheckConstraint(
        "product_family IN ('crypto_perpetual', 'tradfi_equity_perpetual')",
        name="product_family_valid",
    ),
    sa.CheckConstraint(
        "asset_class IN ('crypto', 'equity')",
        name="asset_class_valid",
    ),
    sa.CheckConstraint(
        "entry_session_policy IN ('continuous', 'regular_only', 'reference_only')",
        name="entry_session_policy_valid",
    ),
    sa.CheckConstraint(
        "status IN ('candidate', 'reference', 'active', 'retired')",
        name="status_valid",
    ),
    sa.CheckConstraint(
        "max_entry_spread_bps IS NULL OR max_entry_spread_bps > 0",
        name="max_entry_spread_bps_positive",
    ),
    sa.CheckConstraint(
        "max_mark_index_deviation_bps IS NULL OR "
        "max_mark_index_deviation_bps > 0",
        name="max_mark_index_deviation_bps_positive",
    ),
    sa.CheckConstraint(
        "semantic_digest ~ '^sha256:[0-9a-f]{64}$'",
        name="semantic_digest_valid",
    ),
)

instrument_product_current = sa.Table(
    "brc_instrument_product_current",
    metadata,
    _id("exchange_instrument_id", primary_key=True),
    sa.Column("product_status", SHORT_TEXT, nullable=False),
    sa.Column("session_state", SHORT_TEXT, nullable=False),
    _time("regular_session_open_ms", nullable=True),
    _time("regular_session_close_ms", nullable=True),
    sa.Column("mark_price", MONEY, nullable=True),
    sa.Column("index_price", MONEY, nullable=True),
    sa.Column("funding_rate", MONEY, nullable=True),
    sa.Column("best_bid", MONEY, nullable=True),
    sa.Column("best_ask", MONEY, nullable=True),
    sa.Column("best_bid_quantity", MONEY, nullable=True),
    sa.Column("best_ask_quantity", MONEY, nullable=True),
    sa.Column("corporate_event_status", SHORT_TEXT, nullable=False),
    _time("observed_at_ms"),
    _time("valid_until_ms"),
    sa.Column("source_ref", LONG_TEXT, nullable=False),
    sa.Column("projection_version", sa.BigInteger, nullable=False),
    sa.ForeignKeyConstraint(
        ["exchange_instrument_id"],
        ["brc_instrument_product_profiles.exchange_instrument_id"],
    ),
    sa.CheckConstraint(
        "product_status IN ('active', 'inactive', 'temporarily_unavailable')",
        name="product_status_valid",
    ),
    sa.CheckConstraint(
        "session_state IN ('pre_market', 'regular', 'after_market', 'overnight', 'no_trading', 'unavailable')",
        name="session_state_valid",
    ),
    sa.CheckConstraint(
        "corporate_event_status IN ('clear', 'blocked', 'unavailable')",
        name="corporate_event_status_valid",
    ),
    sa.CheckConstraint(
        "valid_until_ms > observed_at_ms",
        name="validity_window_valid",
    ),
    sa.CheckConstraint(
        "(regular_session_open_ms IS NULL AND regular_session_close_ms IS NULL) OR "
        "(regular_session_open_ms IS NOT NULL AND regular_session_close_ms > regular_session_open_ms)",
        name="regular_session_window_valid",
    ),
    sa.CheckConstraint("projection_version > 0", name="projection_version_positive"),
)

strategy_universe_versions = sa.Table(
    "brc_strategy_universe_versions",
    metadata,
    _id("universe_version_id", primary_key=True),
    _id("strategy_group_id"),
    _id("event_spec_id"),
    sa.Column("universe_version", sa.Integer, nullable=False),
    sa.Column("semantic_digest", LONG_TEXT, nullable=False),
    sa.Column("lifecycle_state", SHORT_TEXT, nullable=False),
    sa.Column(
        "source_kind",
        SHORT_TEXT,
        nullable=False,
        server_default=sa.text("'manual'"),
    ),
    _id("materialization_generation_id", nullable=True),
    _time("installed_at_ms"),
    _time("activated_at_ms", nullable=True),
    _time("retired_at_ms", nullable=True),
    _time("abandoned_at_ms", nullable=True),
    sa.Column("abandon_reason_code", SHORT_TEXT, nullable=True),
    sa.UniqueConstraint("event_spec_id", "universe_version"),
    sa.UniqueConstraint(
        "universe_version_id",
        "event_spec_id",
        "semantic_digest",
    ),
    sa.UniqueConstraint(
        "universe_version_id",
        "event_spec_id",
        "semantic_digest",
        "lifecycle_state",
    ),
    sa.CheckConstraint("universe_version > 0", name="version_positive"),
    sa.CheckConstraint(
        "semantic_digest ~ '^sha256:[0-9a-f]{64}$'",
        name="semantic_digest_valid",
    ),
    sa.CheckConstraint(
        "lifecycle_state IN ('warming', 'staged', 'active', 'retired', 'abandoned')",
        name="lifecycle_state_valid",
    ),
    sa.CheckConstraint(
        "source_kind IN ('manual', 'dynamic_selection', 'static_baseline')",
        name="source_kind_valid",
    ),
    sa.CheckConstraint(
        "(source_kind = 'manual' AND materialization_generation_id IS NULL) OR "
        "(source_kind IN ('dynamic_selection', 'static_baseline') "
        "AND materialization_generation_id IS NOT NULL)",
        name="source_generation_shape_valid",
    ),
    sa.CheckConstraint(
        "(lifecycle_state IN ('warming', 'staged') "
        "AND activated_at_ms IS NULL AND retired_at_ms IS NULL "
        "AND abandoned_at_ms IS NULL AND abandon_reason_code IS NULL) OR "
        "(lifecycle_state = 'active' "
        "AND activated_at_ms IS NOT NULL AND retired_at_ms IS NULL "
        "AND abandoned_at_ms IS NULL AND abandon_reason_code IS NULL) OR "
        "(lifecycle_state = 'retired' "
        "AND activated_at_ms IS NOT NULL AND retired_at_ms IS NOT NULL "
        "AND retired_at_ms >= activated_at_ms "
        "AND abandoned_at_ms IS NULL AND abandon_reason_code IS NULL) OR "
        "(lifecycle_state = 'abandoned' "
        "AND activated_at_ms IS NULL AND retired_at_ms IS NULL "
        "AND abandoned_at_ms IS NOT NULL AND abandon_reason_code IS NOT NULL)",
        name="lifecycle_timestamps_valid",
    ),
    sa.ForeignKeyConstraint(
        ["materialization_generation_id"],
        [
            "brc_strategy_universe_materialization_generations.materialization_generation_id"
        ],
    ),
    sa.UniqueConstraint(
        "materialization_generation_id",
        "event_spec_id",
        name="generation_event",
    ),
)

sa.Index(
    "uq_brc_strategy_universe_versions_current_digest",
    strategy_universe_versions.c.event_spec_id,
    strategy_universe_versions.c.semantic_digest,
    unique=True,
    postgresql_where=strategy_universe_versions.c.lifecycle_state.in_(
        ("warming", "staged", "active")
    ),
)
sa.Index(
    "uq_brc_strategy_universe_versions_global_warming",
    strategy_universe_versions.c.lifecycle_state,
    unique=True,
    postgresql_where=strategy_universe_versions.c.lifecycle_state == "warming",
)
sa.Index(
    "ix_brc_strategy_universe_versions_generation",
    strategy_universe_versions.c.materialization_generation_id,
    strategy_universe_versions.c.event_spec_id,
)

strategy_universe_members = sa.Table(
    "brc_strategy_universe_members",
    metadata,
    _id("universe_version_id"),
    _id("exchange_instrument_id"),
    sa.PrimaryKeyConstraint("universe_version_id", "exchange_instrument_id"),
    sa.ForeignKeyConstraint(
        ["universe_version_id"],
        ["brc_strategy_universe_versions.universe_version_id"],
        ondelete="CASCADE",
    ),
    sa.ForeignKeyConstraint(
        ["exchange_instrument_id"],
        ["brc_instruments.exchange_instrument_id"],
    ),
)

strategy_universe_current = sa.Table(
    "brc_strategy_universe_current",
    metadata,
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
        deferrable=True,
        initially="DEFERRED",
    ),
    sa.UniqueConstraint("universe_version_id"),
    sa.CheckConstraint(
        "semantic_digest ~ '^sha256:[0-9a-f]{64}$'",
        name="semantic_digest_valid",
    ),
    sa.CheckConstraint(
        "activation_generation > 0",
        name="activation_generation_positive",
    ),
    sa.CheckConstraint(
        "lifecycle_state = 'active'",
        name="active_only",
    ),
)

instrument_selection_specs = sa.Table(
    "brc_instrument_selection_specs",
    metadata,
    _id("selection_spec_id", primary_key=True),
    _id("strategy_group_id"),
    _id("strategy_version_id"),
    sa.Column("selection_version", sa.Integer, nullable=False),
    sa.Column("selection_kind", SHORT_TEXT, nullable=False),
    sa.Column("algorithm_semantic_digest", LONG_TEXT, nullable=False),
    sa.Column("status", SHORT_TEXT, nullable=False),
    _time("installed_at_ms"),
    sa.ForeignKeyConstraint(
        ["strategy_group_id"], ["brc_strategy_groups.strategy_group_id"]
    ),
    sa.ForeignKeyConstraint(
        ["strategy_version_id"], ["brc_strategy_versions.strategy_version_id"]
    ),
    sa.UniqueConstraint("strategy_group_id", "selection_version"),
    sa.CheckConstraint("selection_version > 0", name="selection_version_positive"),
    sa.CheckConstraint("selection_kind = 'sor_dynamic_v0'", name="selection_kind_valid"),
    sa.CheckConstraint("status IN ('active', 'retired')", name="status_valid"),
    sa.CheckConstraint(
        "algorithm_semantic_digest ~ '^sha256:[0-9a-f]{64}$'",
        name="algorithm_digest_valid",
    ),
)

sor_dynamic_selection_specs_v0 = sa.Table(
    "brc_sor_dynamic_selection_specs_v0",
    metadata,
    _id("selection_spec_id", primary_key=True),
    sa.Column("decision_offset_utc_seconds", sa.Integer, nullable=False),
    sa.Column("feature_cutoff_offset_utc_seconds", sa.Integer, nullable=False),
    sa.Column("eligibility_not_before_offset_utc_seconds", sa.Integer, nullable=False),
    sa.Column("valid_until_next_decision_offset_seconds", sa.Integer, nullable=False),
    sa.Column("candidate_count", sa.Integer, nullable=False),
    sa.Column("selected_count_max", sa.Integer, nullable=False),
    sa.Column("near_count_max", sa.Integer, nullable=False),
    sa.Column("activity_floor_quote_usdt", MONEY, nullable=False),
    sa.Column("materialization_timeout_seconds", sa.Integer, nullable=False),
    sa.ForeignKeyConstraint(
        ["selection_spec_id"], ["brc_instrument_selection_specs.selection_spec_id"]
    ),
    sa.CheckConstraint(
        "decision_offset_utc_seconds = 3600 "
        "AND feature_cutoff_offset_utc_seconds = 3600 "
        "AND eligibility_not_before_offset_utc_seconds = 4500 "
        "AND valid_until_next_decision_offset_seconds = 86400 "
        "AND candidate_count = 24 AND selected_count_max = 7 "
        "AND near_count_max = 7 AND activity_floor_quote_usdt = 20000000 "
        "AND materialization_timeout_seconds = 1800",
        name="frozen_v0",
    ),
)

instrument_selection_spec_events = sa.Table(
    "brc_instrument_selection_spec_events",
    metadata,
    _id("selection_spec_id"),
    _id("event_spec_id"),
    sa.Column("position_side", SHORT_TEXT, nullable=False),
    sa.PrimaryKeyConstraint("selection_spec_id", "event_spec_id"),
    sa.ForeignKeyConstraint(
        ["selection_spec_id"], ["brc_instrument_selection_specs.selection_spec_id"]
    ),
    sa.ForeignKeyConstraint(["event_spec_id"], ["brc_event_specs.event_spec_id"]),
    sa.UniqueConstraint("selection_spec_id", "position_side"),
    sa.CheckConstraint("position_side IN ('long', 'short')", name="side_valid"),
)

instrument_selection_spec_members = sa.Table(
    "brc_instrument_selection_spec_members",
    metadata,
    _id("selection_spec_id"),
    _id("exchange_instrument_id"),
    sa.PrimaryKeyConstraint("selection_spec_id", "exchange_instrument_id"),
    sa.ForeignKeyConstraint(
        ["selection_spec_id"], ["brc_instrument_selection_specs.selection_spec_id"]
    ),
    sa.ForeignKeyConstraint(
        ["exchange_instrument_id"], ["brc_instruments.exchange_instrument_id"]
    ),
)

strategy_selection_rollback_baselines = sa.Table(
    "brc_strategy_selection_rollback_baselines",
    metadata,
    _id("rollback_baseline_id", primary_key=True),
    _id("strategy_group_id"),
    _id("strategy_version_id"),
    _id("source_long_universe_version_id"),
    _id("source_short_universe_version_id"),
    sa.Column("semantic_digest", LONG_TEXT, nullable=False),
    _time("captured_at_ms"),
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
    sa.UniqueConstraint("strategy_group_id", "strategy_version_id"),
    sa.CheckConstraint(
        "source_long_universe_version_id <> source_short_universe_version_id",
        name="pair_distinct",
    ),
    sa.CheckConstraint(
        "semantic_digest ~ '^sha256:[0-9a-f]{64}$'", name="semantic_digest_valid"
    ),
)

strategy_selection_control_current = sa.Table(
    "brc_strategy_selection_control_current",
    metadata,
    _id("strategy_group_id", primary_key=True),
    _id("selection_spec_id"),
    sa.Column("selection_mode", SHORT_TEXT, nullable=False),
    sa.Column("pending_selection_mode", SHORT_TEXT, nullable=True),
    _time("pending_effective_session_start_ms", nullable=True),
    _id("pending_authorization_id", nullable=True),
    sa.Column("control_version", sa.BigInteger, nullable=False),
    _id("rollback_baseline_id", nullable=True),
    _time("updated_at_ms"),
    sa.ForeignKeyConstraint(
        ["strategy_group_id"], ["brc_strategy_groups.strategy_group_id"]
    ),
    sa.ForeignKeyConstraint(
        ["selection_spec_id"], ["brc_instrument_selection_specs.selection_spec_id"]
    ),
    sa.ForeignKeyConstraint(
        ["pending_authorization_id"], ["brc_owner_authorizations.authorization_id"]
    ),
    sa.ForeignKeyConstraint(
        ["rollback_baseline_id"],
        ["brc_strategy_selection_rollback_baselines.rollback_baseline_id"],
    ),
    sa.CheckConstraint(
        "selection_mode IN ('disabled', 'static_baseline', 'dynamic_selection')",
        name="mode_valid",
    ),
    sa.CheckConstraint("control_version > 0", name="version_positive"),
)

instrument_selection_jobs_current = sa.Table(
    "brc_instrument_selection_jobs_current",
    metadata,
    _id("selection_job_id", primary_key=True),
    _id("selection_spec_id"),
    _time("session_start_ms"),
    _time("scheduled_at_ms"),
    _time("feature_cutoff_at_ms"),
    sa.Column("state", SHORT_TEXT, nullable=False),
    _id("selection_snapshot_id", nullable=True),
    sa.Column("first_blocker", LONG_TEXT, nullable=True),
    sa.Column("attempt_count", sa.Integer, nullable=False),
    _time("next_retry_at_ms", nullable=True),
    sa.Column("lease_owner", SHORT_TEXT, nullable=True),
    _time("lease_expires_at_ms", nullable=True),
    sa.Column("projection_version", sa.BigInteger, nullable=False),
    _time("updated_at_ms"),
    sa.ForeignKeyConstraint(
        ["selection_spec_id"], ["brc_instrument_selection_specs.selection_spec_id"]
    ),
    sa.ForeignKeyConstraint(
        ["selection_snapshot_id"],
        ["brc_instrument_selection_snapshots.selection_snapshot_id"],
    ),
    sa.UniqueConstraint("selection_spec_id", "session_start_ms"),
    sa.CheckConstraint(
        "state IN ('DUE', 'CLAIMED', 'SNAPSHOT_READY', 'SOURCE_FAILED', "
        "'COMPUTE_FAILED')",
        name="state_valid",
    ),
)
sa.Index(
    "ix_brc_instrument_selection_jobs_claim",
    instrument_selection_jobs_current.c.state,
    instrument_selection_jobs_current.c.scheduled_at_ms,
    instrument_selection_jobs_current.c.next_retry_at_ms,
    instrument_selection_jobs_current.c.lease_expires_at_ms,
    postgresql_where=instrument_selection_jobs_current.c.state.in_(
        ("DUE", "CLAIMED", "SOURCE_FAILED", "COMPUTE_FAILED")
    ),
)

instrument_selection_attempts = sa.Table(
    "brc_instrument_selection_attempts",
    metadata,
    _id("selection_attempt_id", primary_key=True),
    _id("selection_job_id"),
    _id("selection_spec_id"),
    _time("session_start_ms"),
    sa.Column("worker_id", SHORT_TEXT, nullable=False),
    sa.Column("attempt_number", sa.Integer, nullable=False),
    _time("started_at_ms"),
    _time("completed_at_ms"),
    sa.Column("outcome", SHORT_TEXT, nullable=False),
    sa.Column("reason_code", LONG_TEXT, nullable=True),
    sa.Column("source_member_count", sa.Integer, nullable=False),
    sa.Column("source_digest", LONG_TEXT, nullable=True),
    sa.ForeignKeyConstraint(
        ["selection_job_id"], ["brc_instrument_selection_jobs_current.selection_job_id"]
    ),
    sa.ForeignKeyConstraint(
        ["selection_spec_id"], ["brc_instrument_selection_specs.selection_spec_id"]
    ),
    sa.UniqueConstraint("selection_spec_id", "session_start_ms", "attempt_number"),
)

instrument_selection_snapshots = sa.Table(
    "brc_instrument_selection_snapshots",
    metadata,
    _id("selection_snapshot_id", primary_key=True),
    _id("selection_spec_id"),
    _id("strategy_group_id"),
    _id("strategy_version_id"),
    _time("session_start_ms"),
    _time("decision_at_ms"),
    _time("feature_cutoff_at_ms"),
    _time("eligibility_not_before_ms"),
    _time("expires_at_ms"),
    sa.Column("candidate_count", sa.Integer, nullable=False),
    sa.Column("ready_count", sa.Integer, nullable=False),
    sa.Column("selected_count", sa.Integer, nullable=False),
    _time("source_observed_at_ms"),
    sa.Column("source_semantic_digest", LONG_TEXT, nullable=False),
    sa.Column("selection_semantic_digest", LONG_TEXT, nullable=False),
    _time("created_at_ms"),
    sa.ForeignKeyConstraint(
        ["selection_spec_id"], ["brc_instrument_selection_specs.selection_spec_id"]
    ),
    sa.ForeignKeyConstraint(
        ["strategy_group_id"], ["brc_strategy_groups.strategy_group_id"]
    ),
    sa.ForeignKeyConstraint(
        ["strategy_version_id"], ["brc_strategy_versions.strategy_version_id"]
    ),
    sa.UniqueConstraint("selection_spec_id", "session_start_ms"),
    sa.UniqueConstraint("selection_snapshot_id", "selection_semantic_digest"),
)

instrument_selection_member_decisions = sa.Table(
    "brc_instrument_selection_member_decisions",
    metadata,
    _id("selection_snapshot_id"),
    _id("member_decision_id"),
    _id("selection_spec_id"),
    _time("session_start_ms"),
    _time("feature_cutoff_at_ms"),
    _time("input_window_start_ms"),
    _time("input_window_end_ms"),
    _id("exchange_instrument_id"),
    sa.Column("input_window_digest", LONG_TEXT, nullable=False),
    sa.Column("source_status", SHORT_TEXT, nullable=False),
    sa.Column("or_high", SELECTION_DECIMAL, nullable=False),
    sa.Column("or_low", SELECTION_DECIMAL, nullable=False),
    sa.Column("or_width", SELECTION_DECIMAL, nullable=False),
    sa.Column("pre_or_atr14", SELECTION_DECIMAL, nullable=False),
    sa.Column("pre_or_width_atr14", SELECTION_DECIMAL, nullable=False),
    sa.Column("trailing_24h_quote_volume", SELECTION_DECIMAL, nullable=False),
    sa.Column("or_geometry_valid", sa.Boolean, nullable=False),
    sa.Column("atr_valid", sa.Boolean, nullable=False),
    sa.Column("activity_valid", sa.Boolean, nullable=False),
    sa.Column("selection_ready", sa.Boolean, nullable=False),
    sa.Column("primary_reason", SHORT_TEXT, nullable=True),
    _json("secondary_reasons"),
    sa.Column("stable_rank", sa.Integer, nullable=True),
    sa.Column("member_state", SHORT_TEXT, nullable=False),
    sa.Column("selected", sa.Boolean, nullable=False),
    sa.Column("member_semantic_digest", LONG_TEXT, nullable=False),
    sa.PrimaryKeyConstraint("selection_snapshot_id", "exchange_instrument_id"),
    sa.UniqueConstraint("member_decision_id"),
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
)
sa.Index(
    "ix_brc_instrument_selection_member_decisions_rank",
    instrument_selection_member_decisions.c.selection_snapshot_id,
    instrument_selection_member_decisions.c.stable_rank,
)

strategy_universe_materialization_generations = sa.Table(
    "brc_strategy_universe_materialization_generations",
    metadata,
    _id("materialization_generation_id", primary_key=True),
    _id("selection_spec_id"),
    _id("strategy_group_id"),
    _id("strategy_version_id"),
    sa.Column("selection_mode", SHORT_TEXT, nullable=False),
    _id("selection_snapshot_id", nullable=True),
    _id("rollback_baseline_id", nullable=True),
    _time("session_start_ms", nullable=True),
    _id("previous_long_universe_version_id"),
    _id("previous_short_universe_version_id"),
    sa.Column("desired_member_count", sa.Integer, nullable=False),
    sa.Column("semantic_digest", LONG_TEXT, nullable=False),
    sa.Column("lifecycle_state", SHORT_TEXT, nullable=False),
    sa.Column("fallback_reason_code", LONG_TEXT, nullable=True),
    sa.Column("lease_owner", SHORT_TEXT, nullable=True),
    _time("lease_expires_at_ms", nullable=True),
    sa.Column("projection_version", sa.BigInteger, nullable=False),
    _time("created_at_ms"),
    _time("desired_at_ms", nullable=True),
    _time("fenced_at_ms", nullable=True),
    _time("activated_at_ms", nullable=True),
    _time("fallback_at_ms", nullable=True),
    _time("terminal_at_ms", nullable=True),
    sa.ForeignKeyConstraint(
        ["selection_spec_id"], ["brc_instrument_selection_specs.selection_spec_id"]
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
    sa.UniqueConstraint("selection_spec_id", "session_start_ms", "selection_mode"),
    sa.UniqueConstraint("selection_snapshot_id"),
)
sa.Index(
    "ix_brc_strategy_universe_materialization_generation_claim",
    strategy_universe_materialization_generations.c.lifecycle_state,
    strategy_universe_materialization_generations.c.lease_expires_at_ms,
    postgresql_where=strategy_universe_materialization_generations.c.lifecycle_state.in_(
        ("PENDING", "DESIRED", "DRAINING_ENTRY", "MATERIALIZING", "STAGED")
    ),
)

strategy_universe_materialization_targets = sa.Table(
    "brc_strategy_universe_materialization_targets",
    metadata,
    _id("materialization_generation_id"),
    _id("event_spec_id"),
    sa.Column("position_side", SHORT_TEXT, nullable=False),
    sa.Column("expected_member_set_digest", LONG_TEXT, nullable=False),
    sa.Column("materialization_order", sa.Integer, nullable=False),
    sa.PrimaryKeyConstraint("materialization_generation_id", "event_spec_id"),
    sa.ForeignKeyConstraint(
        ["materialization_generation_id"],
        ["brc_strategy_universe_materialization_generations.materialization_generation_id"],
    ),
    sa.ForeignKeyConstraint(["event_spec_id"], ["brc_event_specs.event_spec_id"]),
    sa.UniqueConstraint("materialization_generation_id", "position_side"),
    sa.UniqueConstraint("materialization_generation_id", "materialization_order"),
)

strategy_universe_materialization_events = sa.Table(
    "brc_strategy_universe_materialization_events",
    metadata,
    _id("materialization_event_id", primary_key=True),
    _id("materialization_generation_id"),
    sa.Column("event_sequence", sa.BigInteger, nullable=False),
    sa.Column("event_type", SHORT_TEXT, nullable=False),
    _json("payload"),
    _time("occurred_at_ms"),
    sa.ForeignKeyConstraint(
        ["materialization_generation_id"],
        ["brc_strategy_universe_materialization_generations.materialization_generation_id"],
    ),
    sa.UniqueConstraint("materialization_generation_id", "event_sequence"),
)

strategy_entry_vacuums_current = sa.Table(
    "brc_strategy_entry_vacuums_current",
    metadata,
    _id("entry_vacuum_id", primary_key=True),
    _id("strategy_group_id"),
    _id("selection_spec_id"),
    _time("session_start_ms"),
    _id("source_generation_id", nullable=True),
    sa.Column("state", SHORT_TEXT, nullable=False),
    _time("fenced_at_ms"),
    _time("drained_at_ms", nullable=True),
    _time("resolved_at_ms", nullable=True),
    sa.Column("first_blocker", LONG_TEXT, nullable=False),
    sa.Column("projection_version", sa.BigInteger, nullable=False),
    sa.ForeignKeyConstraint(
        ["strategy_group_id"], ["brc_strategy_groups.strategy_group_id"]
    ),
    sa.ForeignKeyConstraint(
        ["selection_spec_id"], ["brc_instrument_selection_specs.selection_spec_id"]
    ),
    sa.ForeignKeyConstraint(
        ["source_generation_id"],
        ["brc_strategy_universe_materialization_generations.materialization_generation_id"],
    ),
)
sa.Index(
    "uq_brc_strategy_entry_vacuums_current_open_scope",
    strategy_entry_vacuums_current.c.strategy_group_id,
    strategy_entry_vacuums_current.c.selection_spec_id,
    unique=True,
    postgresql_where=strategy_entry_vacuums_current.c.state.in_(
        (
            "OPEN",
            "DRAINING_ENTRY",
            "RECONFIGURING",
            "OWNER_PAUSED",
            "SUPERSEDED",
            "FAILED_CLOSED",
        )
    ),
)

strategy_entry_vacuum_events = sa.Table(
    "brc_strategy_entry_vacuum_events",
    metadata,
    _id("entry_vacuum_event_id", primary_key=True),
    _id("entry_vacuum_id"),
    sa.Column("event_sequence", sa.BigInteger, nullable=False),
    sa.Column("event_type", SHORT_TEXT, nullable=False),
    _json("payload"),
    _time("occurred_at_ms"),
    sa.ForeignKeyConstraint(
        ["entry_vacuum_id"], ["brc_strategy_entry_vacuums_current.entry_vacuum_id"]
    ),
    sa.UniqueConstraint("entry_vacuum_id", "event_sequence"),
)

selection_authority_gap_audits_current = sa.Table(
    "brc_selection_authority_gap_audits_current",
    metadata,
    _id("authority_gap_audit_id", primary_key=True),
    _id("selection_spec_id"),
    _time("session_start_ms"),
    sa.Column("gap_kind", SHORT_TEXT, nullable=False),
    _id("source_entry_vacuum_id", nullable=True),
    _id("source_generation_id", nullable=True),
    sa.Column("proposed_authority_outcome", SHORT_TEXT, nullable=False),
    _time("unauthorized_from_close_time_ms"),
    _time("audited_through_close_time_ms", nullable=True),
    _time("first_eligible_close_time_ms", nullable=True),
    sa.Column("audit_scope_digest", LONG_TEXT, nullable=True),
    sa.Column("audit_result_digest", LONG_TEXT, nullable=True),
    sa.Column("detector_semantic_digest", LONG_TEXT, nullable=False),
    sa.Column("state", SHORT_TEXT, nullable=False),
    sa.Column("first_blocker", LONG_TEXT, nullable=True),
    sa.Column("projection_version", sa.BigInteger, nullable=False),
    sa.ForeignKeyConstraint(
        ["selection_spec_id"], ["brc_instrument_selection_specs.selection_spec_id"]
    ),
    sa.ForeignKeyConstraint(
        ["source_entry_vacuum_id"],
        ["brc_strategy_entry_vacuums_current.entry_vacuum_id"],
    ),
    sa.ForeignKeyConstraint(
        ["source_generation_id"],
        ["brc_strategy_universe_materialization_generations.materialization_generation_id"],
    ),
)

selection_authority_gap_audit_events = sa.Table(
    "brc_selection_authority_gap_audit_events",
    metadata,
    _id("authority_gap_audit_event_id", primary_key=True),
    _id("authority_gap_audit_id"),
    sa.Column("event_sequence", sa.BigInteger, nullable=False),
    sa.Column("event_type", SHORT_TEXT, nullable=False),
    _json("payload"),
    _time("occurred_at_ms"),
    sa.ForeignKeyConstraint(
        ["authority_gap_audit_id"],
        ["brc_selection_authority_gap_audits_current.authority_gap_audit_id"],
    ),
    sa.UniqueConstraint("authority_gap_audit_id", "event_sequence"),
)

selection_session_authorities = sa.Table(
    "brc_selection_session_authorities",
    metadata,
    _id("selection_authority_id", primary_key=True),
    _id("selection_spec_id"),
    _time("session_start_ms"),
    _time("decision_boundary_ms"),
    sa.Column("authority_sequence", sa.BigInteger, nullable=False),
    sa.Column("selection_mode", SHORT_TEXT, nullable=False),
    _id("selection_job_id", nullable=True),
    _id("selection_attempt_id", nullable=True),
    _id("selection_snapshot_id", nullable=True),
    _id("continued_from_selection_authority_id", nullable=True),
    sa.Column("continuity_source_kind", SHORT_TEXT, nullable=False),
    _id("authority_gap_audit_id", nullable=True),
    _id("materialization_generation_id", nullable=True),
    sa.Column("owner_control_version", sa.BigInteger, nullable=False),
    sa.Column("authority_outcome", SHORT_TEXT, nullable=False),
    _id("authorized_long_universe_version_id", nullable=True),
    _id("authorized_short_universe_version_id", nullable=True),
    sa.Column("grant_proof_kind", SHORT_TEXT, nullable=True),
    _id("grant_predecessor_authority_id", nullable=True),
    _time("effective_from_ms"),
    _time("first_eligible_close_time_ms", nullable=True),
    _time("expires_at_ms"),
    sa.Column("reason_code", LONG_TEXT, nullable=False),
    sa.Column("semantic_digest", LONG_TEXT, nullable=False),
    _time("created_at_ms"),
    sa.ForeignKeyConstraint(
        ["selection_spec_id"], ["brc_instrument_selection_specs.selection_spec_id"]
    ),
    sa.ForeignKeyConstraint(
        ["selection_job_id"], ["brc_instrument_selection_jobs_current.selection_job_id"]
    ),
    sa.ForeignKeyConstraint(
        ["selection_attempt_id"], ["brc_instrument_selection_attempts.selection_attempt_id"]
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
        ["brc_strategy_universe_materialization_generations.materialization_generation_id"],
    ),
    sa.ForeignKeyConstraint(
        ["authorized_long_universe_version_id"],
        ["brc_strategy_universe_versions.universe_version_id"],
    ),
    sa.ForeignKeyConstraint(
        ["authorized_short_universe_version_id"],
        ["brc_strategy_universe_versions.universe_version_id"],
    ),
    sa.UniqueConstraint("selection_spec_id", "session_start_ms", "authority_sequence"),
)
sa.Index(
    "ix_brc_selection_session_authorities_period",
    selection_session_authorities.c.selection_spec_id,
    selection_session_authorities.c.session_start_ms,
    selection_session_authorities.c.authority_sequence,
)

selection_authority_current = sa.Table(
    "brc_selection_authority_current",
    metadata,
    _id("selection_spec_id", primary_key=True),
    _id("selection_authority_id"),
    sa.Column("projection_version", sa.BigInteger, nullable=False),
    _time("updated_at_ms"),
    sa.ForeignKeyConstraint(
        ["selection_spec_id"], ["brc_instrument_selection_specs.selection_spec_id"]
    ),
    sa.ForeignKeyConstraint(
        ["selection_authority_id"],
        ["brc_selection_session_authorities.selection_authority_id"],
    ),
)

strategy_trigger_suppressions = sa.Table(
    "brc_strategy_trigger_suppressions",
    metadata,
    _id("trigger_suppression_id", primary_key=True),
    _id("authority_gap_audit_id"),
    _id("entry_vacuum_id", nullable=True),
    _id("materialization_generation_id", nullable=True),
    _id("event_spec_id"),
    _id("exchange_instrument_id"),
    sa.Column("session_reference", LONG_TEXT, nullable=False),
    _time("first_natural_trigger_at_ms"),
    sa.Column("reason_code", SHORT_TEXT, nullable=False),
    sa.Column("detector_semantic_digest", LONG_TEXT, nullable=False),
    _time("created_at_ms"),
    sa.ForeignKeyConstraint(
        ["authority_gap_audit_id"],
        ["brc_selection_authority_gap_audits_current.authority_gap_audit_id"],
    ),
    sa.ForeignKeyConstraint(
        ["entry_vacuum_id"], ["brc_strategy_entry_vacuums_current.entry_vacuum_id"]
    ),
    sa.ForeignKeyConstraint(
        ["materialization_generation_id"],
        ["brc_strategy_universe_materialization_generations.materialization_generation_id"],
    ),
    sa.ForeignKeyConstraint(["event_spec_id"], ["brc_event_specs.event_spec_id"]),
    sa.ForeignKeyConstraint(
        ["exchange_instrument_id"], ["brc_instruments.exchange_instrument_id"]
    ),
    sa.UniqueConstraint("event_spec_id", "exchange_instrument_id", "session_reference"),
)

runtime_release_compatibility_facts = sa.Table(
    "brc_runtime_release_compatibility_facts",
    metadata,
    _id("release_compatibility_id", primary_key=True),
    sa.Column("from_commit", SHORT_TEXT, nullable=False),
    sa.Column("to_commit", SHORT_TEXT, nullable=False),
    sa.Column("from_schema_revision", SHORT_TEXT, nullable=False),
    sa.Column("to_schema_revision", SHORT_TEXT, nullable=False),
    sa.Column("classification", SHORT_TEXT, nullable=False),
    sa.Column("compatibility_basis_digest", LONG_TEXT, nullable=False),
    _json("reason_codes"),
    sa.Column("certification_manifest_digest", LONG_TEXT, nullable=False),
    _time("created_at_ms"),
    sa.UniqueConstraint(
        "from_commit", "to_commit", "from_schema_revision", "to_schema_revision"
    ),
)

instrument_certification_current = sa.Table(
    "brc_instrument_certification_current",
    metadata,
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
    _id("lease_universe_version_id", nullable=True),
    sa.Column("projection_version", sa.BigInteger, nullable=False),
    sa.PrimaryKeyConstraint("runtime_profile_id", "exchange_instrument_id"),
    sa.ForeignKeyConstraint(
        ["runtime_profile_id"],
        ["brc_runtime_profiles.runtime_profile_id"],
    ),
    sa.ForeignKeyConstraint(
        ["exchange_instrument_id"],
        ["brc_instruments.exchange_instrument_id"],
    ),
    sa.CheckConstraint(
        "status IN ('eligible', 'owner_action_required', "
        "'temporarily_unavailable')",
        name="status_valid",
    ),
    sa.CheckConstraint(
        "facts_digest ~ '^sha256:[0-9a-f]{64}$'",
        name="facts_digest_valid",
    ),
    sa.CheckConstraint(
        "product_rules_digest IS NULL "
        "OR product_rules_digest ~ '^sha256:[0-9a-f]{64}$'",
        name="product_rules_digest_valid",
    ),
    sa.CheckConstraint(
        "valid_until_ms > observed_at_ms",
        name="validity_window_valid",
    ),
    sa.CheckConstraint(
        "next_check_at_ms >= observed_at_ms",
        name="next_check_not_before_observation",
    ),
    sa.CheckConstraint(
        "(lease_owner IS NULL AND lease_expires_at_ms IS NULL "
        "AND lease_universe_version_id IS NULL) OR "
        "(lease_owner IS NOT NULL AND lease_expires_at_ms IS NOT NULL "
        "AND lease_universe_version_id IS NOT NULL)",
        name="lease_shape_valid",
    ),
    sa.CheckConstraint(
        "projection_version > 0",
        name="projection_version_positive",
    ),
)

sa.Index(
    "ix_brc_instrument_certification_current_due",
    instrument_certification_current.c.status,
    instrument_certification_current.c.next_check_at_ms,
    instrument_certification_current.c.lease_expires_at_ms,
)

instrument_certification_batches = sa.Table(
    "brc_instrument_certification_batches",
    metadata,
    _id("certification_batch_id", primary_key=True),
    _id("runtime_profile_id"),
    sa.Column("target_commit", SHORT_TEXT, nullable=False),
    sa.Column("target_schema_revision", SHORT_TEXT, nullable=False),
    sa.Column("target_seed_identity", LONG_TEXT, nullable=False),
    _id("owner_policy_id"),
    sa.Column("owner_policy_version", sa.Integer, nullable=False),
    sa.Column("manifest_digest", LONG_TEXT, nullable=False),
    sa.Column("status", SHORT_TEXT, nullable=False),
    _time("started_at_ms"),
    _time("minimum_valid_until_ms"),
    _time("completed_at_ms", nullable=True),
    _time("valid_until_ms", nullable=True),
    sa.Column("blocker_code", SHORT_TEXT, nullable=True),
    sa.ForeignKeyConstraint(
        ["runtime_profile_id"],
        ["brc_runtime_profiles.runtime_profile_id"],
    ),
    sa.ForeignKeyConstraint(
        ["owner_policy_id"],
        ["brc_owner_policy_current.owner_policy_id"],
    ),
    sa.CheckConstraint(
        "status IN ('pending', 'completed', 'blocked')",
        name="status_valid",
    ),
    sa.CheckConstraint(
        "target_seed_identity ~ '^sha256:[0-9a-f]{64}$'",
        name="seed_identity_valid",
    ),
    sa.CheckConstraint(
        "manifest_digest ~ '^sha256:[0-9a-f]{64}$'",
        name="manifest_digest_valid",
    ),
    sa.CheckConstraint(
        "minimum_valid_until_ms > started_at_ms",
        name="promotion_window_valid",
    ),
    sa.CheckConstraint(
        "(status = 'pending' AND completed_at_ms IS NULL "
        "AND valid_until_ms IS NULL AND blocker_code IS NULL) OR "
        "(status = 'completed' AND completed_at_ms IS NOT NULL "
        "AND valid_until_ms >= minimum_valid_until_ms "
        "AND blocker_code IS NULL) OR "
        "(status = 'blocked' AND completed_at_ms IS NOT NULL "
        "AND valid_until_ms IS NULL AND blocker_code IS NOT NULL)",
        name="terminal_shape_valid",
    ),
)

sa.Index(
    "uq_brc_instrument_certification_batches_pending_profile",
    instrument_certification_batches.c.runtime_profile_id,
    unique=True,
    postgresql_where=instrument_certification_batches.c.status == "pending",
)

instrument_certification_batch_members = sa.Table(
    "brc_instrument_certification_batch_members",
    metadata,
    _id("certification_batch_id"),
    _id("exchange_instrument_id"),
    sa.Column("status", SHORT_TEXT, nullable=False),
    sa.Column("blocker_code", SHORT_TEXT, nullable=True),
    sa.Column("facts_digest", LONG_TEXT, nullable=True),
    sa.Column("product_rules_digest", LONG_TEXT, nullable=True),
    _time("observed_at_ms", nullable=True),
    _time("valid_until_ms", nullable=True),
    sa.PrimaryKeyConstraint(
        "certification_batch_id",
        "exchange_instrument_id",
    ),
    sa.ForeignKeyConstraint(
        ["certification_batch_id"],
        ["brc_instrument_certification_batches.certification_batch_id"],
        ondelete="CASCADE",
    ),
    sa.ForeignKeyConstraint(
        ["exchange_instrument_id"],
        ["brc_instruments.exchange_instrument_id"],
    ),
    sa.CheckConstraint(
        "status IN ('pending', 'eligible', 'owner_action_required')",
        name="status_valid",
    ),
    sa.CheckConstraint(
        "facts_digest IS NULL OR facts_digest ~ '^sha256:[0-9a-f]{64}$'",
        name="facts_digest_valid",
    ),
    sa.CheckConstraint(
        "product_rules_digest IS NULL "
        "OR product_rules_digest ~ '^sha256:[0-9a-f]{64}$'",
        name="product_rules_digest_valid",
    ),
    sa.CheckConstraint(
        "(status = 'pending' AND blocker_code IS NULL "
        "AND facts_digest IS NULL AND product_rules_digest IS NULL "
        "AND observed_at_ms IS NULL AND valid_until_ms IS NULL) OR "
        "(status = 'eligible' AND blocker_code IS NULL "
        "AND facts_digest IS NOT NULL AND product_rules_digest IS NOT NULL "
        "AND observed_at_ms IS NOT NULL "
        "AND valid_until_ms > observed_at_ms) OR "
        "(status = 'owner_action_required' AND blocker_code IS NOT NULL "
        "AND facts_digest IS NOT NULL "
        "AND observed_at_ms IS NOT NULL "
        "AND valid_until_ms > observed_at_ms)",
        name="result_shape_valid",
    ),
)

comparative_projection_current = sa.Table(
    "brc_comparative_projection_current",
    metadata,
    _id("event_spec_id"),
    _id("universe_version_id"),
    _time("closed_bar_time_ms"),
    sa.Column("member_set_digest", LONG_TEXT, nullable=False),
    sa.Column("projection_status", SHORT_TEXT, nullable=False),
    sa.Column("failure_reason", SHORT_TEXT, nullable=True),
    _json("projection"),
    _time("observed_at_ms"),
    _time("valid_until_ms"),
    sa.Column("projection_version", sa.BigInteger, nullable=False),
    sa.PrimaryKeyConstraint("event_spec_id", "universe_version_id"),
    sa.ForeignKeyConstraint(
        ["universe_version_id"],
        ["brc_strategy_universe_versions.universe_version_id"],
        ondelete="CASCADE",
    ),
    sa.CheckConstraint(
        "member_set_digest ~ '^sha256:[0-9a-f]{64}$'",
        name="member_set_digest_valid",
    ),
    sa.CheckConstraint(
        "(projection_status = 'ready' AND failure_reason IS NULL) OR "
        "(projection_status = 'unavailable' AND "
        "failure_reason IN ('comparative_projection_incomplete', "
        "'comparative_market_temporarily_unavailable'))",
        name="projection_status_shape_valid",
    ),
    sa.CheckConstraint(
        "valid_until_ms > observed_at_ms",
        name="validity_window_valid",
    ),
    sa.CheckConstraint(
        "projection_version > 0",
        name="projection_version_positive",
    ),
)

sa.Index(
    "ix_brc_comparative_projection_current_lookup",
    comparative_projection_current.c.event_spec_id,
    comparative_projection_current.c.universe_version_id,
    comparative_projection_current.c.closed_bar_time_ms,
)

instrument_rules_current = sa.Table(
    "brc_instrument_rules_current",
    metadata,
    sa.Column("venue_id", SHORT_TEXT, primary_key=True),
    _id("exchange_instrument_id", primary_key=True),
    sa.Column("quantity_step", MONEY, nullable=False),
    sa.Column("price_tick", MONEY, nullable=False),
    sa.Column("min_quantity", MONEY, nullable=False),
    sa.Column("min_notional", MONEY, nullable=False),
    sa.Column("exchange_max_leverage", sa.Integer, nullable=False),
    _json("maintenance_margin_brackets"),
    sa.Column("maintenance_margin_brackets_digest", LONG_TEXT, nullable=False),
    sa.Column("notional_coefficient", MONEY, nullable=False),
    sa.Column("notional_coefficient_certified", sa.Boolean, nullable=False),
    _json("session_and_settlement"),
    _time("observed_at_ms"),
    _time("valid_until_ms"),
    sa.Column("projection_version", sa.BigInteger, nullable=False),
    sa.CheckConstraint(
        "exchange_max_leverage > 0",
        name="exchange_max_leverage_positive",
    ),
    sa.CheckConstraint(
        "maintenance_margin_brackets_digest ~ '^sha256:[0-9a-f]{64}$'",
        name="brackets_digest_valid",
    ),
    sa.CheckConstraint(
        "notional_coefficient > 0",
        name="notional_coefficient_positive",
    ),
)

owner_policy_events = sa.Table(
    "brc_owner_policy_events",
    metadata,
    _id("owner_policy_event_id", primary_key=True),
    _id("owner_policy_id"),
    sa.Column("policy_version", sa.Integer, nullable=False),
    sa.Column("operation", SHORT_TEXT, nullable=False),
    _json("payload"),
    _time("created_at_ms"),
    sa.UniqueConstraint("owner_policy_id", "policy_version"),
)

owner_policy_current = sa.Table(
    "brc_owner_policy_current",
    metadata,
    _id("owner_policy_id", primary_key=True),
    sa.Column("policy_version", sa.Integer, nullable=False),
    sa.Column("enabled", sa.Boolean, nullable=False),
    sa.Column("new_entry_submit_enabled", sa.Boolean, nullable=False),
    sa.Column(
        "priority_rank",
        sa.Integer,
        nullable=False,
        server_default=sa.text("100"),
    ),
    sa.Column("max_concurrent_tickets", sa.Integer, nullable=False),
    # Retained only for historical v3 rows; current projections ignore it.
    sa.Column(
        "max_strategy_group_concurrent_tickets",
        sa.Integer,
        nullable=True,
    ),
    _json("family_ticket_limits"),
    sa.Column("max_ticket_stop_risk_fraction", MONEY, nullable=False),
    sa.Column("max_gross_stop_risk_fraction", MONEY, nullable=False),
    sa.Column("max_ticket_initial_margin_fraction", MONEY, nullable=False),
    sa.Column("max_gross_initial_margin_utilization", MONEY, nullable=False),
    sa.Column("directional_stop_risk_limit_fraction", MONEY, nullable=False),
    sa.Column("min_materialization_ratio", MONEY, nullable=False),
    sa.Column("max_leverage", sa.Integer, nullable=False),
    sa.Column("supported_margin_mode", SHORT_TEXT, nullable=False),
    sa.Column("post_stop_stress_multiple", MONEY, nullable=False),
    sa.Column("max_post_fill_stop_risk_overrun_fraction", MONEY, nullable=False),
    _json("scope"),
    _time("updated_at_ms"),
    sa.CheckConstraint("priority_rank > 0", name="priority_positive"),
    sa.CheckConstraint(
        "max_concurrent_tickets > 0",
        name="max_concurrent_tickets_positive",
    ),
    sa.CheckConstraint(
        "max_ticket_stop_risk_fraction > 0 "
        "AND max_ticket_stop_risk_fraction < 1",
        name="ticket_stop_risk_fraction_valid",
    ),
    sa.CheckConstraint(
        "max_gross_stop_risk_fraction > 0 "
        "AND max_gross_stop_risk_fraction <= 1 "
        "AND max_ticket_stop_risk_fraction <= max_gross_stop_risk_fraction",
        name="gross_stop_risk_fraction_valid",
    ),
    sa.CheckConstraint(
        "max_ticket_initial_margin_fraction > 0 "
        "AND max_ticket_initial_margin_fraction <= 1",
        name="ticket_margin_fraction_valid",
    ),
    sa.CheckConstraint(
        "max_gross_initial_margin_utilization > 0 "
        "AND max_gross_initial_margin_utilization <= 1 "
        "AND max_ticket_initial_margin_fraction "
        "<= max_gross_initial_margin_utilization",
        name="gross_margin_utilization_valid",
    ),
    sa.CheckConstraint(
        "max_leverage >= 1 AND max_leverage <= 10",
        name="max_leverage_valid",
    ),
    sa.CheckConstraint(
        "supported_margin_mode = 'cross'",
        name="supported_margin_mode_cross_only",
    ),
    sa.CheckConstraint(
        "post_stop_stress_multiple > 0",
        name="post_stop_stress_multiple_positive",
    ),
    sa.CheckConstraint(
        "max_post_fill_stop_risk_overrun_fraction >= 0 "
        "AND max_post_fill_stop_risk_overrun_fraction < 1",
        name="post_fill_overrun_valid",
    ),
)

runtime_profiles = sa.Table(
    "brc_runtime_profiles",
    metadata,
    _id("runtime_profile_id", primary_key=True),
    sa.Column("venue_id", SHORT_TEXT, nullable=False),
    _id("account_id"),
    sa.Column("environment", SHORT_TEXT, nullable=False),
    sa.Column("position_mode", SHORT_TEXT, nullable=False),
    sa.Column("status", SHORT_TEXT, nullable=False),
    _time("updated_at_ms"),
)

runtime_scopes_current = sa.Table(
    "brc_runtime_scopes_current",
    metadata,
    _id("runtime_scope_id", primary_key=True),
    _id("strategy_group_id"),
    _id("strategy_version_id"),
    _id("event_spec_id"),
    _id("runtime_profile_id"),
    _id("owner_policy_id"),
    _id("exchange_instrument_id"),
    sa.Column("position_side", SHORT_TEXT, nullable=False),
    _id("universe_version_id"),
    sa.Column("universe_semantic_digest", LONG_TEXT, nullable=False),
    sa.Column("lifecycle_state", SHORT_TEXT, nullable=False),
    sa.Column("observation_enabled", sa.Boolean, nullable=False),
    sa.Column("entry_enabled", sa.Boolean, nullable=False),
    sa.Column("scope_version", sa.Integer, nullable=False),
    _time("warm_closed_bar_time_ms", nullable=True),
    _time("warm_completed_at_ms", nullable=True),
    sa.Column("warm_readiness_digest", LONG_TEXT, nullable=True),
    _time("warm_valid_until_ms", nullable=True),
    _time("next_observation_due_at_ms", nullable=True),
    _time("lease_expires_at_ms", nullable=True),
    _id("lease_owner", nullable=True),
    sa.Column(
        "observation_generation",
        sa.BigInteger,
        nullable=False,
        server_default="0",
    ),
    _time("updated_at_ms"),
    sa.UniqueConstraint(
        "universe_version_id",
        "runtime_profile_id",
        "exchange_instrument_id",
        "position_side",
    ),
    sa.ForeignKeyConstraint(
        ["universe_version_id", "exchange_instrument_id"],
        [
            "brc_strategy_universe_members.universe_version_id",
            "brc_strategy_universe_members.exchange_instrument_id",
        ],
    ),
    sa.ForeignKeyConstraint(
        [
            "universe_version_id",
            "event_spec_id",
            "universe_semantic_digest",
            "lifecycle_state",
        ],
        [
            "brc_strategy_universe_versions.universe_version_id",
            "brc_strategy_universe_versions.event_spec_id",
            "brc_strategy_universe_versions.semantic_digest",
            "brc_strategy_universe_versions.lifecycle_state",
        ],
        deferrable=True,
        initially="DEFERRED",
    ),
    sa.CheckConstraint(
        "(lifecycle_state = 'warming' "
        "AND observation_enabled AND NOT entry_enabled) OR "
        "(lifecycle_state = 'staged' "
        "AND NOT observation_enabled AND NOT entry_enabled) OR "
        "(lifecycle_state = 'active' "
        "AND observation_enabled AND entry_enabled) OR "
        "(lifecycle_state = 'retired' "
        "AND NOT observation_enabled AND NOT entry_enabled) OR "
        "(lifecycle_state = 'abandoned' "
        "AND NOT observation_enabled AND NOT entry_enabled)",
        name="lifecycle_permissions_valid",
    ),
    sa.CheckConstraint(
        "(warm_closed_bar_time_ms IS NULL AND warm_completed_at_ms IS NULL "
        "AND warm_readiness_digest IS NULL "
        "AND warm_valid_until_ms IS NULL) OR "
        "(warm_closed_bar_time_ms IS NOT NULL AND warm_completed_at_ms IS NOT NULL "
        "AND warm_readiness_digest IS NOT NULL "
        "AND warm_valid_until_ms IS NOT NULL "
        "AND warm_completed_at_ms >= warm_closed_bar_time_ms "
        "AND warm_valid_until_ms > warm_completed_at_ms)",
        name="warm_readiness_shape_valid",
    ),
    sa.CheckConstraint(
        "lifecycle_state <> 'active' OR warm_closed_bar_time_ms IS NOT NULL",
        name="active_requires_warm_readiness",
    ),
    sa.CheckConstraint(
        "warm_readiness_digest IS NULL "
        "OR warm_readiness_digest ~ '^sha256:[0-9a-f]{64}$'",
        name="warm_readiness_digest_valid",
    ),
    sa.CheckConstraint(
        "universe_semantic_digest ~ '^sha256:[0-9a-f]{64}$'",
        name="universe_semantic_digest_valid",
    ),
    sa.CheckConstraint(
        "observation_generation >= 0",
        name="observation_generation_nonnegative",
    ),
)

sa.Index(
    "ix_brc_runtime_scopes_current_observation_due",
    runtime_scopes_current.c.observation_enabled,
    runtime_scopes_current.c.next_observation_due_at_ms,
    runtime_scopes_current.c.lease_expires_at_ms,
)

facts_current = sa.Table(
    "brc_facts_current",
    metadata,
    _id("fact_current_id", primary_key=True),
    _id("runtime_scope_id"),
    _id("fact_definition_id"),
    _json("value"),
    sa.Column("satisfied", sa.Boolean, nullable=False),
    _time("observed_at_ms"),
    _time("valid_until_ms"),
    sa.Column("projection_version", sa.BigInteger, nullable=False),
    sa.UniqueConstraint("runtime_scope_id", "fact_definition_id"),
)

exposure_episode_current = sa.Table(
    "brc_exposure_episode_current",
    metadata,
    _id("episode_domain_key", primary_key=True),
    _id("event_spec_id"),
    _id("exchange_instrument_id"),
    sa.Column("position_side", SHORT_TEXT, nullable=False),
    sa.Column("episode_policy", SHORT_TEXT, nullable=False),
    sa.Column("state", SHORT_TEXT, nullable=False),
    _id("exposure_episode_id", nullable=True),
    _time("triggered_at_ms", nullable=True),
    _time("rearmed_at_ms", nullable=True),
    _time("last_observed_at_ms"),
    sa.Column("projection_version", sa.BigInteger, nullable=False),
    sa.CheckConstraint(
        "position_side IN ('long', 'short')",
        name="position_side_valid",
    ),
    sa.CheckConstraint(
        "episode_policy = 'rising_edge'",
        name="episode_policy_valid",
    ),
    sa.CheckConstraint(
        "state IN ('armed', 'triggered')",
        name="state_valid",
    ),
    sa.CheckConstraint(
        "projection_version > 0 AND last_observed_at_ms > 0",
        name="version_and_observation_positive",
    ),
    sa.CheckConstraint(
        "rearmed_at_ms IS NULL OR rearmed_at_ms > 0",
        name="rearmed_time_valid",
    ),
    sa.CheckConstraint(
        "(state = 'triggered' AND exposure_episode_id IS NOT NULL "
        "AND triggered_at_ms IS NOT NULL AND triggered_at_ms > 0) OR "
        "(state = 'armed' AND exposure_episode_id IS NULL "
        "AND triggered_at_ms IS NULL)",
        name="state_shape_valid",
    ),
    sa.ForeignKeyConstraint(
        ["event_spec_id"],
        ["brc_event_specs.event_spec_id"],
    ),
    sa.ForeignKeyConstraint(
        ["exchange_instrument_id"],
        ["brc_instruments.exchange_instrument_id"],
    ),
)

signal_events = sa.Table(
    "brc_signal_events",
    metadata,
    _id("signal_event_id", primary_key=True),
    _id("exposure_episode_id"),
    _id("runtime_scope_id"),
    sa.Column("runtime_scope_version", sa.Integer, nullable=False),
    _id("strategy_group_id"),
    _id("strategy_version_id"),
    _id("event_spec_id"),
    _id("universe_version_id"),
    _id("selection_authority_id", nullable=True),
    sa.Column("universe_semantic_digest", LONG_TEXT, nullable=False),
    _id("exchange_instrument_id"),
    sa.Column("position_side", SHORT_TEXT, nullable=False),
    sa.Column("fact_digest", LONG_TEXT, nullable=False),
    _time("occurred_at_ms"),
    _time("observed_at_ms"),
    _time("expires_at_ms"),
    sa.UniqueConstraint("exposure_episode_id"),
    sa.CheckConstraint(
        "position_side IN ('long', 'short')",
        name="position_side_valid",
    ),
    sa.CheckConstraint(
        "expires_at_ms > occurred_at_ms",
        name="time_window_valid",
    ),
    sa.CheckConstraint(
        "observed_at_ms >= occurred_at_ms AND expires_at_ms > observed_at_ms",
        name="observation_window_valid",
    ),
    sa.CheckConstraint(
        "fact_digest ~ '^sha256:[0-9a-f]{64}$'",
        name="fact_digest_valid",
    ),
    sa.CheckConstraint(
        "universe_semantic_digest ~ '^sha256:[0-9a-f]{64}$'",
        name="universe_semantic_digest_valid",
    ),
    sa.ForeignKeyConstraint(
        [
            "universe_version_id",
            "event_spec_id",
            "universe_semantic_digest",
        ],
        [
            "brc_strategy_universe_versions.universe_version_id",
            "brc_strategy_universe_versions.event_spec_id",
            "brc_strategy_universe_versions.semantic_digest",
        ],
    ),
    sa.ForeignKeyConstraint(
        ["selection_authority_id"],
        ["brc_selection_session_authorities.selection_authority_id"],
    ),
)
sa.Index(
    "ix_brc_signal_events_selection_authority_id",
    signal_events.c.selection_authority_id,
)

signal_fact_snapshots = sa.Table(
    "brc_signal_fact_snapshots",
    metadata,
    _id("signal_event_id"),
    _id("fact_definition_id"),
    sa.Column("role", SHORT_TEXT, nullable=False),
    _json("value"),
    sa.Column("satisfied", sa.Boolean, nullable=False),
    _time("observed_at_ms"),
    _time("valid_until_ms"),
    sa.Column("projection_version", sa.BigInteger, nullable=False),
    sa.PrimaryKeyConstraint("signal_event_id", "fact_definition_id"),
    sa.CheckConstraint(
        "role IN ('condition', 'protection_reference', 'identity_reference', "
        "'lifecycle_reference', 'disable')",
        name="role_valid",
    ),
    sa.CheckConstraint(
        "valid_until_ms > observed_at_ms",
        name="time_window_valid",
    ),
    sa.CheckConstraint(
        "projection_version > 0",
        name="projection_version_positive",
    ),
)

readiness_current = sa.Table(
    "brc_readiness_current",
    metadata,
    _id("runtime_scope_id", primary_key=True),
    sa.Column("readiness_state", SHORT_TEXT, nullable=False),
    sa.Column("first_blocker", LONG_TEXT, nullable=True),
    _id("signal_event_id", nullable=True),
    _json("fact_summary"),
    _time("updated_at_ms"),
    sa.Column("projection_version", sa.BigInteger, nullable=False),
)

admission_decisions = sa.Table(
    "brc_admission_decisions",
    metadata,
    _id("admission_decision_id", primary_key=True),
    _id("signal_event_id"),
    _id("exposure_episode_id"),
    _id("strategy_group_id"),
    _id("strategy_version_id"),
    _id("event_spec_id"),
    _id("universe_version_id"),
    _id("selection_authority_id", nullable=True),
    sa.Column("universe_semantic_digest", LONG_TEXT, nullable=False),
    _id("runtime_profile_id"),
    _id("runtime_scope_id"),
    sa.Column("runtime_scope_version", sa.BigInteger, nullable=False),
    _id("owner_policy_id"),
    sa.Column("owner_policy_version", sa.BigInteger, nullable=False),
    _id("venue_id"),
    _id("account_id"),
    _id("exchange_instrument_id"),
    sa.Column("position_side", SHORT_TEXT, nullable=False),
    sa.Column("exposure_family", SHORT_TEXT, nullable=False),
    sa.Column("candidate_rank", sa.Integer, nullable=False),
    sa.Column("candidate_count", sa.Integer, nullable=False),
    sa.Column("candidate_set_digest", LONG_TEXT, nullable=False),
    _json("candidate_set_summary"),
    _json("portfolio_usage"),
    sa.Column("decision_status", SHORT_TEXT, nullable=False),
    sa.Column("first_blocker", LONG_TEXT, nullable=True),
    sa.Column("binding_constraint", LONG_TEXT, nullable=True),
    _id("capacity_claim_id", nullable=True),
    _id("ticket_id", nullable=True),
    sa.Column("entry_admission_snapshot_digest", LONG_TEXT, nullable=True),
    sa.Column("decision_digest", LONG_TEXT, nullable=False),
    _time("decided_at_ms"),
    sa.UniqueConstraint("signal_event_id"),
    sa.CheckConstraint(
        "position_side IN ('long', 'short')",
        name="position_side_valid",
    ),
    sa.CheckConstraint(
        "exposure_family IN ('long_continuation', 'opening_range', "
        "'rally_failure_short')",
        name="exposure_family_valid",
    ),
    sa.CheckConstraint(
        "candidate_rank > 0 AND candidate_count BETWEEN 1 AND 64 "
        "AND candidate_rank <= candidate_count",
        name="candidate_shape_valid",
    ),
    sa.CheckConstraint(
        "decision_status IN ('admitted', 'rejected')",
        name="decision_status_valid",
    ),
    sa.CheckConstraint(
        "(decision_status = 'admitted' AND first_blocker IS NULL "
        "AND capacity_claim_id IS NOT NULL AND ticket_id IS NOT NULL "
        "AND entry_admission_snapshot_digest IS NOT NULL) OR "
        "(decision_status = 'rejected' AND first_blocker IS NOT NULL "
        "AND capacity_claim_id IS NULL AND ticket_id IS NULL)",
        name="decision_shape_valid",
    ),
    sa.CheckConstraint(
        "candidate_set_digest ~ '^sha256:[0-9a-f]{64}$' "
        "AND decision_digest ~ '^sha256:[0-9a-f]{64}$' "
        "AND universe_semantic_digest ~ '^sha256:[0-9a-f]{64}$' "
        "AND (entry_admission_snapshot_digest IS NULL OR "
        "entry_admission_snapshot_digest ~ '^sha256:[0-9a-f]{64}$')",
        name="digest_shape_valid",
    ),
    sa.ForeignKeyConstraint(
        ["signal_event_id"],
        ["brc_signal_events.signal_event_id"],
    ),
    sa.ForeignKeyConstraint(
        ["capacity_claim_id"],
        ["brc_capacity_claims.capacity_claim_id"],
    ),
    sa.ForeignKeyConstraint(
        ["ticket_id"],
        ["brc_trade_tickets.ticket_id"],
    ),
    sa.ForeignKeyConstraint(
        ["selection_authority_id"],
        ["brc_selection_session_authorities.selection_authority_id"],
    ),
)
sa.Index(
    "ix_brc_admission_decisions_selection_authority_id",
    admission_decisions.c.selection_authority_id,
)

shadow_outcomes_current = sa.Table(
    "brc_shadow_outcomes_current",
    metadata,
    _id("shadow_outcome_id", primary_key=True),
    _id("signal_event_id"),
    _id("admission_decision_id", nullable=True),
    sa.Column("source_kind", SHORT_TEXT, nullable=False),
    sa.Column("status", SHORT_TEXT, nullable=False),
    sa.Column("evaluation_kind", SHORT_TEXT, nullable=False),
    _id("exchange_instrument_id"),
    sa.Column("position_side", SHORT_TEXT, nullable=False),
    sa.Column("timeframe", SHORT_TEXT, nullable=False),
    sa.Column("entry_reference_price", MONEY, nullable=True),
    sa.Column("initial_stop_price", MONEY, nullable=True),
    sa.Column("initial_risk_per_unit", MONEY, nullable=True),
    sa.Column("take_profit_price", MONEY, nullable=True),
    sa.Column("opening_range_boundary_price", MONEY, nullable=True),
    _time("session_exit_deadline_ms", nullable=True),
    sa.Column("mark_price", MONEY, nullable=True),
    sa.Column("index_price", MONEY, nullable=True),
    sa.Column("funding_rate", MONEY, nullable=True),
    sa.Column("best_bid_price", MONEY, nullable=True),
    sa.Column("best_ask_price", MONEY, nullable=True),
    sa.Column("best_bid_quantity", MONEY, nullable=True),
    sa.Column("best_ask_quantity", MONEY, nullable=True),
    sa.Column("spread_bps", MONEY, nullable=True),
    sa.Column("mark_index_deviation_bps", MONEY, nullable=True),
    _time("horizon_start_ms"),
    _time("horizon_end_ms"),
    _id("claim_owner", nullable=True),
    _id("claim_token", nullable=True),
    _time("lease_until_ms", nullable=True),
    sa.Column("max_favorable_price", MONEY, nullable=True),
    sa.Column("max_adverse_price", MONEY, nullable=True),
    sa.Column("mfe_r", MONEY, nullable=True),
    sa.Column("mae_r", MONEY, nullable=True),
    _time("observed_through_ms", nullable=True),
    sa.Column("completion_reason", LONG_TEXT, nullable=True),
    sa.Column("first_path", SHORT_TEXT, nullable=True),
    _time("first_path_at_ms", nullable=True),
    sa.Column("observed_bar_count", sa.BigInteger, nullable=True),
    sa.Column("projection_version", sa.BigInteger, nullable=False),
    _time("created_at_ms"),
    _time("completed_at_ms", nullable=True),
    sa.UniqueConstraint("signal_event_id"),
    sa.UniqueConstraint("admission_decision_id"),
    sa.CheckConstraint(
        "status IN ('pending', 'claimed', 'completed', 'unavailable')",
        name="status_valid",
    ),
    sa.CheckConstraint(
        "evaluation_kind IN ('fixed_horizon_excursion_v1', "
        "'sor_path_observation_v1')",
        name="evaluation_kind_valid",
    ),
    sa.CheckConstraint("position_side IN ('long', 'short')", name="side_valid"),
    sa.CheckConstraint("timeframe IN ('15m', '1h')", name="timeframe_valid"),
    sa.CheckConstraint(
        "(initial_risk_per_unit IS NULL OR initial_risk_per_unit >= 0) "
        "AND horizon_end_ms > horizon_start_ms "
        "AND (session_exit_deadline_ms IS NULL "
        "OR session_exit_deadline_ms > horizon_start_ms)",
        name="risk_horizon_valid",
    ),
    sa.CheckConstraint(
        "(source_kind = 'portfolio_rejection' "
        "AND admission_decision_id IS NOT NULL "
        "AND evaluation_kind = 'fixed_horizon_excursion_v1') OR "
        "(source_kind = 'strategy_observation' "
        "AND admission_decision_id IS NULL "
        "AND evaluation_kind = 'sor_path_observation_v1')",
        name="source_kind_valid",
    ),
    sa.CheckConstraint(
        "first_path IS NULL OR first_path IN ("
        "'tp1_first', 'initial_stop_first', 'ambiguous_same_bar', "
        "'opening_range_failure', 'time_stop', 'session_exit', "
        "'horizon_complete')",
        name="path_valid",
    ),
    sa.CheckConstraint(
        "(status IN ('pending', 'claimed', 'completed') "
        "AND entry_reference_price IS NOT NULL "
        "AND initial_stop_price IS NOT NULL "
        "AND initial_risk_per_unit IS NOT NULL) OR status = 'unavailable'",
        name="lease_shape_valid",
    ),
    sa.CheckConstraint(
        "(status = 'claimed' AND claim_owner IS NOT NULL "
        "AND claim_token IS NOT NULL AND lease_until_ms IS NOT NULL "
        "AND completed_at_ms IS NULL AND max_favorable_price IS NULL "
        "AND max_adverse_price IS NULL AND mfe_r IS NULL AND mae_r IS NULL "
        "AND observed_through_ms IS NULL AND completion_reason IS NULL "
        "AND first_path IS NULL AND first_path_at_ms IS NULL "
        "AND observed_bar_count IS NULL) OR "
        "(status = 'pending' AND claim_owner IS NULL "
        "AND claim_token IS NULL AND lease_until_ms IS NULL "
        "AND completed_at_ms IS NULL AND max_favorable_price IS NULL "
        "AND max_adverse_price IS NULL AND mfe_r IS NULL AND mae_r IS NULL "
        "AND observed_through_ms IS NULL AND completion_reason IS NULL "
        "AND first_path IS NULL AND first_path_at_ms IS NULL "
        "AND observed_bar_count IS NULL) OR "
        "(status = 'completed' AND claim_owner IS NULL "
        "AND claim_token IS NULL AND lease_until_ms IS NULL "
        "AND completed_at_ms IS NOT NULL AND max_favorable_price IS NOT NULL "
        "AND max_adverse_price IS NOT NULL AND mfe_r IS NOT NULL "
        "AND mae_r IS NOT NULL AND observed_through_ms IS NOT NULL "
        "AND completion_reason IS NOT NULL "
        "AND ((evaluation_kind = 'fixed_horizon_excursion_v1' "
        "AND first_path IS NULL AND first_path_at_ms IS NULL "
        "AND observed_bar_count IS NULL) OR "
        "(evaluation_kind = 'sor_path_observation_v1' "
        "AND first_path IS NOT NULL AND first_path_at_ms IS NOT NULL "
        "AND observed_bar_count > 0))) OR "
        "(status = 'unavailable' AND claim_owner IS NULL "
        "AND claim_token IS NULL AND lease_until_ms IS NULL "
        "AND completed_at_ms IS NOT NULL AND max_favorable_price IS NULL "
        "AND max_adverse_price IS NULL AND mfe_r IS NULL AND mae_r IS NULL "
        "AND observed_through_ms IS NULL AND completion_reason IS NOT NULL "
        "AND first_path IS NULL AND first_path_at_ms IS NULL "
        "AND observed_bar_count IS NULL)",
        name="projection_shape_valid",
    ),
)

sa.Index(
    "ix_brc_shadow_outcomes_current_due",
    shadow_outcomes_current.c.status,
    shadow_outcomes_current.c.horizon_end_ms,
    shadow_outcomes_current.c.lease_until_ms,
)

sa.Index(
    "ix_brc_admission_decisions_decided_at_ms",
    admission_decisions.c.decided_at_ms,
)
sa.Index(
    "ix_brc_admission_decisions_first_blocker_decided_at_ms",
    admission_decisions.c.first_blocker,
    admission_decisions.c.decided_at_ms,
)
sa.Index(
    "ix_brc_admission_decisions_strategy_event_decided",
    admission_decisions.c.strategy_group_id,
    admission_decisions.c.event_spec_id,
    admission_decisions.c.decided_at_ms,
)

sa.Index(
    "ix_brc_readiness_current_readiness_state_signal_event_id",
    readiness_current.c.readiness_state,
    readiness_current.c.signal_event_id,
)
sa.Index(
    "ix_brc_signal_events_candidate_order",
    signal_events.c.expires_at_ms,
    signal_events.c.occurred_at_ms,
    signal_events.c.observed_at_ms,
    signal_events.c.signal_event_id,
)

entry_lane_current = sa.Table(
    "brc_entry_lane_current",
    metadata,
    sa.Column("lane_id", SHORT_TEXT, primary_key=True),
    _id("ticket_id", nullable=True),
    _id("signal_event_id", nullable=True),
    sa.Column("status", SHORT_TEXT, nullable=False),
    _time("claimed_at_ms", nullable=True),
    _time("lease_until_ms", nullable=True),
    sa.Column("claim_owner", SHORT_TEXT, nullable=True),
    sa.Column("version", sa.BigInteger, nullable=False),
)

runtime_capabilities_current = sa.Table(
    "brc_runtime_capabilities_current",
    metadata,
    sa.Column("capability_key", SHORT_TEXT, primary_key=True),
    sa.Column("enabled", sa.Boolean, nullable=False),
    sa.Column("certified_commit", SHORT_TEXT, nullable=False),
    sa.Column("schema_revision", SHORT_TEXT, nullable=False),
    _json("certification"),
    _time("updated_at_ms"),
)

capacity_claims = sa.Table(
    "brc_capacity_claims",
    metadata,
    _id("capacity_claim_id", primary_key=True),
    _id("ticket_id"),
    _id("signal_event_id"),
    _id("exposure_episode_id"),
    _id("strategy_group_id"),
    _id("strategy_version_id"),
    _id("event_spec_id"),
    _id("universe_version_id"),
    _id("selection_authority_id", nullable=True),
    sa.Column("universe_semantic_digest", LONG_TEXT, nullable=False),
    _id("runtime_profile_id"),
    _id("owner_policy_id"),
    sa.Column("owner_policy_version", sa.Integer, nullable=False),
    _id("runtime_scope_id"),
    sa.Column("runtime_scope_version", sa.Integer, nullable=False),
    _id("account_id"),
    sa.Column("venue_id", SHORT_TEXT, nullable=False),
    _id("exchange_instrument_id"),
    sa.Column("position_side", SHORT_TEXT, nullable=False),
    sa.Column("netting_domain_key", LONG_TEXT, nullable=False),
    sa.Column("fact_digest", LONG_TEXT, nullable=False),
    _id("exit_policy_id"),
    sa.Column("exit_policy_semantic_hash", LONG_TEXT, nullable=False),
    _id("exit_binding_id", nullable=True),
    sa.Column("exit_binding_semantic_hash", LONG_TEXT, nullable=True),
    sa.Column("exit_binding_authority_version", sa.BigInteger, nullable=True),
    sa.Column("entry_admission_snapshot_digest", LONG_TEXT, nullable=False),
    sa.Column("account_entry_health_digest", LONG_TEXT, nullable=False),
    sa.Column("instrument_entry_health_digest", LONG_TEXT, nullable=False),
    sa.Column("instrument_rules_projection_version", sa.BigInteger, nullable=False),
    sa.Column("account_capacity_domain_key", LONG_TEXT, nullable=False),
    sa.Column("leverage_domain_key", LONG_TEXT, nullable=False),
    sa.Column("total_wallet_balance_at_claim", MONEY, nullable=False),
    sa.Column("total_margin_balance_at_claim", MONEY, nullable=False),
    sa.Column("total_initial_margin_at_claim", MONEY, nullable=False),
    sa.Column("total_maintenance_margin_at_claim", MONEY, nullable=False),
    sa.Column("available_margin_at_claim", MONEY, nullable=False),
    sa.Column("mark_price_at_claim", MONEY, nullable=False),
    sa.Column("position_mode_at_claim", SHORT_TEXT, nullable=False),
    sa.Column("margin_mode_at_claim", SHORT_TEXT, nullable=False),
    sa.Column("active_ticket_count_at_claim", sa.Integer, nullable=False),
    sa.Column("remaining_slots_at_claim", sa.Integer, nullable=False),
    # These nullable columns preserve pre-v4 Claim rows and receive no new writes.
    sa.Column(
        "active_strategy_group_ticket_count_at_claim",
        sa.Integer,
        nullable=True,
    ),
    sa.Column(
        "max_strategy_group_concurrent_tickets",
        sa.Integer,
        nullable=True,
    ),
    sa.Column(
        "remaining_strategy_group_slots_at_claim",
        sa.Integer,
        nullable=True,
    ),
    sa.Column("exposure_family", SHORT_TEXT, nullable=False),
    sa.Column("active_family_ticket_count_at_claim", sa.Integer, nullable=False),
    sa.Column("family_ticket_limit", sa.Integer, nullable=False),
    sa.Column("gross_risk_at_stop_at_claim", MONEY, nullable=False),
    sa.Column("directional_risk_at_stop_at_claim", MONEY, nullable=False),
    sa.Column("current_reserved_margin_at_claim", MONEY, nullable=False),
    sa.Column("max_ticket_stop_risk_fraction", MONEY, nullable=False),
    sa.Column("max_gross_stop_risk_fraction", MONEY, nullable=False),
    sa.Column("directional_stop_risk_limit_fraction", MONEY, nullable=False),
    sa.Column("max_ticket_initial_margin_fraction", MONEY, nullable=False),
    sa.Column("max_gross_initial_margin_utilization", MONEY, nullable=False),
    sa.Column("min_materialization_ratio", MONEY, nullable=False),
    sa.Column("minimum_stop_risk_budget", MONEY, nullable=False),
    sa.Column("planned_stop_risk_budget", MONEY, nullable=False),
    sa.Column("max_post_fill_stop_risk_overrun_fraction", MONEY, nullable=False),
    sa.Column("post_fill_stop_risk_limit", MONEY, nullable=False),
    sa.Column("post_stop_stress_multiple", MONEY, nullable=False),
    sa.Column("ticket_margin_budget", MONEY, nullable=False),
    sa.Column("required_leverage", sa.Integer, nullable=False),
    sa.Column("selected_leverage", sa.Integer, nullable=False),
    sa.Column("configured_leverage_at_claim", sa.Integer, nullable=False),
    sa.Column("leverage_change_required", sa.Boolean, nullable=False),
    sa.Column("exchange_max_leverage", sa.Integer, nullable=False),
    sa.Column("reserved_margin", MONEY, nullable=False),
    _json("cross_margin_stress_evidence"),
    sa.Column("entry_reference_price", MONEY, nullable=False),
    sa.Column("quantity", MONEY, nullable=False),
    sa.Column("notional", MONEY, nullable=False),
    sa.Column("risk_at_stop", MONEY, nullable=False),
    sa.Column("entry_order_type", SHORT_TEXT, nullable=False),
    sa.Column("entry_limit_price", MONEY, nullable=True),
    sa.Column("initial_stop_price", MONEY, nullable=False),
    sa.Column("pre_tp1_reclaim_price", MONEY, nullable=True),
    _time("exposure_session_end_ms", nullable=True),
    _json("take_profit_prices"),
    _json("take_profit_quantities"),
    sa.Column("decision_digest", LONG_TEXT, nullable=False),
    _time("created_at_ms"),
    _time("expires_at_ms"),
    sa.UniqueConstraint("ticket_id"),
    sa.UniqueConstraint("signal_event_id"),
    sa.UniqueConstraint("decision_digest"),
    sa.CheckConstraint("quantity > 0", name="quantity_positive"),
    sa.CheckConstraint("notional > 0", name="notional_positive"),
    sa.CheckConstraint("selected_leverage > 0", name="selected_leverage_positive"),
    sa.CheckConstraint(
        "selected_leverage <= exchange_max_leverage",
        name="selected_leverage_within_exchange_maximum",
    ),
    sa.CheckConstraint("risk_at_stop >= 0", name="risk_nonnegative"),
    sa.CheckConstraint(
        "risk_at_stop <= planned_stop_risk_budget",
        name="risk_within_planned_stop_budget",
    ),
    sa.CheckConstraint(
        "post_fill_stop_risk_limit >= planned_stop_risk_budget",
        name="post_fill_limit_not_below_planned_budget",
    ),
    sa.CheckConstraint("expires_at_ms > created_at_ms", name="time_window_valid"),
    sa.CheckConstraint(
        "universe_semantic_digest ~ '^sha256:[0-9a-f]{64}$'",
        name="universe_semantic_digest_valid",
    ),
    sa.ForeignKeyConstraint(
        [
            "universe_version_id",
            "event_spec_id",
            "universe_semantic_digest",
        ],
        [
            "brc_strategy_universe_versions.universe_version_id",
            "brc_strategy_universe_versions.event_spec_id",
            "brc_strategy_universe_versions.semantic_digest",
        ],
    ),
    sa.ForeignKeyConstraint(
        ["selection_authority_id"],
        ["brc_selection_session_authorities.selection_authority_id"],
    ),
    sa.ForeignKeyConstraint(
        ["exit_binding_id", "exit_binding_semantic_hash"],
        [
            "brc_event_exit_profile_bindings.exit_binding_id",
            "brc_event_exit_profile_bindings.binding_semantic_hash",
        ],
        match="FULL",
    ),
    sa.CheckConstraint(
        "(exit_binding_id IS NULL "
        "AND exit_binding_semantic_hash IS NULL "
        "AND exit_binding_authority_version IS NULL) OR "
        "(exit_binding_id IS NOT NULL "
        "AND exit_binding_semantic_hash IS NOT NULL "
        "AND exit_binding_authority_version > 0)",
        name="exit_binding_lineage_shape_valid",
    ),
)
sa.Index(
    "ix_brc_capacity_claims_selection_authority_id",
    capacity_claims.c.selection_authority_id,
)

trade_tickets = sa.Table(
    "brc_trade_tickets",
    metadata,
    _id("ticket_id", primary_key=True),
    _id("exposure_episode_id"),
    _id("signal_event_id"),
    _id("strategy_group_id"),
    _id("strategy_version_id"),
    _id("event_spec_id"),
    _id("universe_version_id"),
    _id("selection_authority_id", nullable=True),
    sa.Column("universe_semantic_digest", LONG_TEXT, nullable=False),
    _id("runtime_profile_id"),
    _id("owner_policy_id"),
    sa.Column("owner_policy_version", sa.Integer, nullable=False),
    _id("runtime_scope_id"),
    sa.Column("runtime_scope_version", sa.Integer, nullable=False),
    _id("account_id"),
    sa.Column("venue_id", SHORT_TEXT, nullable=False),
    _id("exchange_instrument_id"),
    sa.Column("position_side", SHORT_TEXT, nullable=False),
    sa.Column("netting_domain_key", LONG_TEXT, nullable=False),
    sa.Column("active_netting_domain_key", LONG_TEXT, nullable=True),
    sa.Column("exposure_family", SHORT_TEXT, nullable=False),
    sa.Column("active_family_ticket_count_at_claim", sa.Integer, nullable=False),
    sa.Column("family_ticket_limit", sa.Integer, nullable=False),
    sa.Column("directional_risk_at_stop_at_claim", MONEY, nullable=False),
    sa.Column("directional_stop_risk_limit_fraction", MONEY, nullable=False),
    sa.Column("min_materialization_ratio", MONEY, nullable=False),
    sa.Column("minimum_stop_risk_budget", MONEY, nullable=False),
    _id("exit_policy_id"),
    sa.Column("exit_policy_semantic_hash", LONG_TEXT, nullable=False),
    _id("exit_binding_id", nullable=True),
    sa.Column("exit_binding_semantic_hash", LONG_TEXT, nullable=True),
    sa.Column("exit_binding_authority_version", sa.BigInteger, nullable=True),
    sa.Column("entry_reference_price", MONEY, nullable=False),
    sa.Column("quantity", MONEY, nullable=False),
    sa.Column("notional", MONEY, nullable=False),
    _id("capacity_claim_id"),
    sa.Column("planned_stop_risk_budget", MONEY, nullable=False),
    sa.Column("post_fill_stop_risk_limit", MONEY, nullable=False),
    sa.Column("selected_leverage", sa.Integer, nullable=False),
    sa.Column("leverage_change_required", sa.Boolean, nullable=False),
    sa.Column("reserved_margin", MONEY, nullable=False),
    sa.Column("risk_reservation_basis", SHORT_TEXT, nullable=False),
    sa.Column("margin_mode", SHORT_TEXT, nullable=False),
    sa.Column("cross_margin_stress_model_id", SHORT_TEXT, nullable=False),
    sa.Column("post_stop_stress_multiple", MONEY, nullable=False),
    sa.Column("claim_stress_proof_digest", LONG_TEXT, nullable=False),
    sa.Column("risk_at_stop", MONEY, nullable=False),
    sa.Column("entry_order_type", SHORT_TEXT, nullable=False),
    sa.Column("entry_limit_price", MONEY, nullable=True),
    sa.Column("initial_stop_price", MONEY, nullable=False),
    sa.Column("pre_tp1_reclaim_price", MONEY, nullable=True),
    _time("exposure_session_end_ms", nullable=True),
    _json("take_profit_prices"),
    _json("take_profit_quantities"),
    sa.Column("fact_digest", LONG_TEXT, nullable=False),
    sa.Column("decision_digest", LONG_TEXT, nullable=False),
    sa.Column("status", SHORT_TEXT, nullable=False),
    _time("created_at_ms"),
    _time("expires_at_ms"),
    _time("terminal_at_ms", nullable=True),
    sa.UniqueConstraint("signal_event_id"),
    sa.UniqueConstraint("active_netting_domain_key"),
    sa.CheckConstraint("quantity > 0", name="quantity_positive"),
    sa.CheckConstraint("notional > 0", name="notional_positive"),
    sa.CheckConstraint("selected_leverage > 0", name="selected_leverage_positive"),
    sa.CheckConstraint("risk_at_stop >= 0", name="risk_nonnegative"),
    sa.CheckConstraint(
        "universe_semantic_digest ~ '^sha256:[0-9a-f]{64}$'",
        name="universe_semantic_digest_valid",
    ),
    sa.ForeignKeyConstraint(
        [
            "universe_version_id",
            "event_spec_id",
            "universe_semantic_digest",
        ],
        [
            "brc_strategy_universe_versions.universe_version_id",
            "brc_strategy_universe_versions.event_spec_id",
            "brc_strategy_universe_versions.semantic_digest",
        ],
    ),
    sa.ForeignKeyConstraint(
        ["selection_authority_id"],
        ["brc_selection_session_authorities.selection_authority_id"],
    ),
    sa.ForeignKeyConstraint(
        ["exit_binding_id", "exit_binding_semantic_hash"],
        [
            "brc_event_exit_profile_bindings.exit_binding_id",
            "brc_event_exit_profile_bindings.binding_semantic_hash",
        ],
        match="FULL",
    ),
    sa.CheckConstraint(
        "(exit_binding_id IS NULL "
        "AND exit_binding_semantic_hash IS NULL "
        "AND exit_binding_authority_version IS NULL) OR "
        "(exit_binding_id IS NOT NULL "
        "AND exit_binding_semantic_hash IS NOT NULL "
        "AND exit_binding_authority_version > 0)",
        name="exit_binding_lineage_shape_valid",
    ),
)
sa.Index(
    "ix_brc_trade_tickets_selection_authority_id",
    trade_tickets.c.selection_authority_id,
)
sa.Index(
    "ix_brc_trade_tickets_instrument_window",
    trade_tickets.c.venue_id,
    trade_tickets.c.account_id,
    trade_tickets.c.exchange_instrument_id,
    trade_tickets.c.created_at_ms,
    trade_tickets.c.terminal_at_ms,
)
sa.Index(
    "ix_brc_trade_tickets_active_family",
    trade_tickets.c.venue_id,
    trade_tickets.c.account_id,
    trade_tickets.c.exposure_family,
    trade_tickets.c.terminal_at_ms,
)
sa.Index(
    "ix_brc_trade_tickets_active_directional_risk",
    trade_tickets.c.venue_id,
    trade_tickets.c.account_id,
    trade_tickets.c.position_side,
    trade_tickets.c.terminal_at_ms,
)

trade_aggregates = sa.Table(
    "brc_trade_aggregates",
    metadata,
    _id("ticket_id", primary_key=True),
    sa.Column("status", SHORT_TEXT, nullable=False),
    sa.Column("version", sa.BigInteger, nullable=False),
    sa.Column("last_event_sequence", sa.BigInteger, nullable=False),
    sa.Column("entry_lane_held", sa.Boolean, nullable=False),
    sa.Column("position_qty", MONEY, nullable=False),
    sa.Column("average_fill_price", MONEY, nullable=True),
    sa.Column("actual_stop_risk", MONEY, nullable=True),
    sa.Column("venue_reported_liquidation_price", MONEY, nullable=True),
    sa.Column("post_fill_risk_status", SHORT_TEXT, nullable=True),
    sa.Column("post_fill_disposition", SHORT_TEXT, nullable=True),
    sa.Column("post_fill_stress_status", SHORT_TEXT, nullable=True),
    sa.Column("post_fill_stress_proof_digest", LONG_TEXT, nullable=True),
    sa.Column("protected_qty", MONEY, nullable=False),
    _id("entry_exchange_order_id", nullable=True),
    _id("initial_stop_exchange_order_id", nullable=True),
    _id("active_stop_exchange_order_id", nullable=True),
    sa.Column("active_stop_price", MONEY, nullable=True),
    _id("tp1_exchange_order_id", nullable=True),
    sa.Column("tp1_target_qty", MONEY, nullable=False),
    sa.Column("tp1_filled_qty", MONEY, nullable=False),
    sa.Column("break_even_floor_price", MONEY, nullable=True),
    _id("pending_replaced_stop_exchange_order_id", nullable=True),
    sa.Column("pending_stop_price", MONEY, nullable=True),
    _time("pending_stop_watermark_ms", nullable=True),
    _time("runner_stop_watermark_ms", nullable=True),
    _id("pending_cancel_exchange_order_id", nullable=True),
    _id("entry_vacuum_id", nullable=True),
    sa.Column("entry_materialization_kind", SHORT_TEXT, nullable=True),
    _id("exit_exchange_order_id", nullable=True),
    _id("review_id", nullable=True),
    _time("lifecycle_due_at_ms", nullable=True),
    _time("reconciliation_due_at_ms", nullable=True),
    _time("updated_at_ms"),
    sa.ForeignKeyConstraint(
        ["entry_vacuum_id"],
        ["brc_strategy_entry_vacuums_current.entry_vacuum_id"],
    ),
    sa.CheckConstraint("version > 0", name="version_positive"),
    sa.CheckConstraint("last_event_sequence > 0", name="sequence_positive"),
    sa.CheckConstraint("position_qty >= 0", name="position_nonnegative"),
    sa.CheckConstraint("protected_qty >= 0", name="protection_nonnegative"),
    sa.CheckConstraint("tp1_target_qty >= 0", name="tp1_target_nonnegative"),
    sa.CheckConstraint("tp1_filled_qty >= 0", name="tp1_filled_nonnegative"),
    sa.CheckConstraint(
        "entry_materialization_kind IS NULL OR "
        "entry_materialization_kind = 'VACUUM_PARTIAL_RETAINED'",
        name="entry_materialization_kind_valid",
    ),
)
sa.Index(
    "ix_brc_trade_aggregates_lifecycle_due",
    trade_aggregates.c.status,
    trade_aggregates.c.lifecycle_due_at_ms,
)
sa.Index(
    "ix_brc_trade_aggregates_reconciliation_due",
    trade_aggregates.c.status,
    trade_aggregates.c.reconciliation_due_at_ms,
)

trade_events = sa.Table(
    "brc_trade_events",
    metadata,
    _id("event_id", primary_key=True),
    _id("ticket_id"),
    sa.Column("sequence", sa.BigInteger, nullable=False),
    sa.Column("event_type", SHORT_TEXT, nullable=False),
    _json("payload"),
    _time("occurred_at_ms"),
    sa.UniqueConstraint("ticket_id", "sequence"),
)

exchange_commands = sa.Table(
    "brc_exchange_commands",
    metadata,
    _id("command_id", primary_key=True),
    _id("ticket_id"),
    sa.Column("command_kind", SHORT_TEXT, nullable=False),
    sa.Column("generation", sa.Integer, nullable=False),
    sa.Column("idempotency_key", LONG_TEXT, nullable=False),
    sa.Column("venue_client_order_id", SHORT_TEXT, nullable=True),
    sa.Column("status", SHORT_TEXT, nullable=False),
    sa.Column("quantity", MONEY, nullable=True),
    _json("request_payload"),
    _json("result_payload", nullable=True),
    sa.Column("claim_owner", SHORT_TEXT, nullable=True),
    _time("lease_until_ms", nullable=True),
    _time("created_at_ms"),
    _time("deadline_at_ms"),
    _time("completed_at_ms", nullable=True),
    sa.UniqueConstraint("idempotency_key"),
    sa.UniqueConstraint("venue_client_order_id"),
    sa.UniqueConstraint("ticket_id", "command_kind", "generation"),
    sa.CheckConstraint(
        "(command_kind = 'set_leverage' AND venue_client_order_id IS NULL) "
        "OR (command_kind <> 'set_leverage' AND venue_client_order_id IS NOT NULL)",
        name="command_order_identity_shape",
    ),
    sa.CheckConstraint("generation > 0", name="generation_positive"),
    sa.CheckConstraint(
        "quantity IS NULL OR quantity > 0",
        name="quantity_positive",
    ),
)

positions_current = sa.Table(
    "brc_positions_current",
    metadata,
    sa.Column("netting_domain_key", LONG_TEXT, primary_key=True),
    _id("ticket_id", nullable=True),
    sa.Column("venue_id", SHORT_TEXT, nullable=False),
    _id("account_id"),
    _id("exchange_instrument_id"),
    sa.Column("position_side", SHORT_TEXT, nullable=False),
    sa.Column("quantity", MONEY, nullable=False),
    sa.Column("average_entry_price", MONEY, nullable=True),
    sa.Column("venue_reported_liquidation_price", MONEY, nullable=True),
    sa.Column(
        "venue_reported_liquidation_observation_status",
        SHORT_TEXT,
        nullable=False,
    ),
    _time("observed_at_ms"),
    sa.Column("projection_version", sa.BigInteger, nullable=False),
    sa.CheckConstraint("quantity >= 0", name="quantity_nonnegative"),
)

budget_reservations = sa.Table(
    "brc_budget_reservations",
    metadata,
    _id("budget_reservation_id", primary_key=True),
    _id("ticket_id"),
    _id("owner_policy_id"),
    sa.Column("venue_id", SHORT_TEXT, nullable=False),
    _id("account_id"),
    sa.Column("reserved_notional", MONEY, nullable=False),
    sa.Column("reserved_risk", MONEY, nullable=False),
    sa.Column("reserved_margin", MONEY, nullable=False),
    sa.Column("planned_stop_risk_budget", MONEY, nullable=False),
    sa.Column("risk_reservation_basis", SHORT_TEXT, nullable=False),
    sa.Column("status", SHORT_TEXT, nullable=False),
    _time("created_at_ms"),
    _time("released_at_ms", nullable=True),
    sa.UniqueConstraint("ticket_id"),
    sa.CheckConstraint("reserved_notional > 0", name="notional_positive"),
    sa.CheckConstraint("reserved_risk >= 0", name="risk_nonnegative"),
    sa.CheckConstraint("reserved_margin > 0", name="margin_positive"),
)

account_exposure_current = sa.Table(
    "brc_account_exposure_current",
    metadata,
    sa.Column("venue_id", SHORT_TEXT, primary_key=True),
    _id("account_id", primary_key=True),
    sa.Column("gross_notional", MONEY, nullable=False),
    sa.Column("gross_risk_at_stop", MONEY, nullable=False),
    sa.Column("current_reserved_margin", MONEY, nullable=False),
    sa.Column("active_ticket_count", sa.Integer, nullable=False),
    sa.Column("projection_version", sa.BigInteger, nullable=False),
    _time("updated_at_ms"),
    sa.CheckConstraint("gross_notional >= 0", name="notional_nonnegative"),
    sa.CheckConstraint("gross_risk_at_stop >= 0", name="risk_nonnegative"),
    sa.CheckConstraint(
        "current_reserved_margin >= 0",
        name="reserved_margin_nonnegative",
    ),
    sa.CheckConstraint("active_ticket_count >= 0", name="ticket_count_nonnegative"),
)

runtime_incidents = sa.Table(
    "brc_runtime_incidents",
    metadata,
    _id("incident_id", primary_key=True),
    _id("ticket_id", nullable=True),
    sa.Column("incident_kind", SHORT_TEXT, nullable=False),
    sa.Column("status", SHORT_TEXT, nullable=False),
    sa.Column("first_blocker", LONG_TEXT, nullable=False),
    sa.Column("entry_block_scope", SHORT_TEXT, nullable=False),
    sa.Column("entry_block_key", LONG_TEXT, nullable=True),
    _json("details"),
    _time("opened_at_ms"),
    _time("resolved_at_ms", nullable=True),
    sa.CheckConstraint(
        "entry_block_scope IN ('runtime', 'account_capacity', 'leverage_domain', 'none')",
        name="incident_entry_block_scope_valid",
    ),
    sa.CheckConstraint(
        "(entry_block_scope = 'runtime' AND entry_block_key = 'global') OR "
        "(entry_block_scope = 'account_capacity' AND entry_block_key ~ '^[^:]+:[^:]+$') OR "
        "(entry_block_scope = 'leverage_domain' AND entry_block_key ~ '^[^:]+:[^:]+:[^:]+$') OR "
        "(entry_block_scope = 'none' AND entry_block_key IS NULL)",
        name="incident_entry_block_key_canonical",
    ),
)

trade_reviews = sa.Table(
    "brc_trade_reviews",
    metadata,
    _id("review_id", primary_key=True),
    _id("ticket_id"),
    sa.Column("revision", sa.BigInteger, nullable=False),
    sa.Column("supersedes_review_id", ID, nullable=True),
    sa.Column("outcome", SHORT_TEXT, nullable=False),
    _json("metrics"),
    _json("decision_impact"),
    _time("created_at_ms"),
    sa.UniqueConstraint("ticket_id", "review_id"),
    sa.UniqueConstraint("ticket_id", "revision"),
    sa.UniqueConstraint("supersedes_review_id"),
    sa.ForeignKeyConstraint(
        ("ticket_id", "supersedes_review_id"),
        ("brc_trade_reviews.ticket_id", "brc_trade_reviews.review_id"),
    ),
    sa.CheckConstraint(
        "(revision = 1 AND supersedes_review_id IS NULL) OR "
        "(revision > 1 AND supersedes_review_id IS NOT NULL)",
        name="review_revision_chain_valid",
    ),
    sa.CheckConstraint("revision > 0", name="review_revision_positive"),
)
sa.Index(
    "ix_brc_trade_reviews_ticket_revision",
    trade_reviews.c.ticket_id,
    trade_reviews.c.revision.desc(),
)

monitor_current = sa.Table(
    "brc_monitor_current",
    metadata,
    sa.Column("monitor_key", SHORT_TEXT, primary_key=True),
    sa.Column("owner_status", SHORT_TEXT, nullable=False),
    sa.Column("summary", LONG_TEXT, nullable=False),
    sa.Column("intervention", LONG_TEXT, nullable=False),
    _id("ticket_id", nullable=True),
    _id("incident_id", nullable=True),
    _time("updated_at_ms"),
    sa.Column("projection_version", sa.BigInteger, nullable=False),
)

monitor_events = sa.Table(
    "brc_monitor_events",
    metadata,
    _id("monitor_event_id", primary_key=True),
    sa.Column("monitor_key", SHORT_TEXT, nullable=False),
    sa.Column("event_type", SHORT_TEXT, nullable=False),
    _json("payload"),
    _time("created_at_ms"),
)

retention_runs = sa.Table(
    "brc_retention_runs",
    metadata,
    _id("retention_run_id", primary_key=True),
    sa.Column("scope", SHORT_TEXT, nullable=False),
    sa.Column("deleted_rows", sa.BigInteger, nullable=False),
    _time("started_at_ms"),
    _time("completed_at_ms"),
)

schema_metadata = sa.Table(
    "brc_schema_metadata",
    metadata,
    sa.Column("metadata_key", SHORT_TEXT, primary_key=True),
    sa.Column("metadata_value", LONG_TEXT, nullable=False),
    _time("updated_at_ms"),
)

strategy_entry_control_events = sa.Table(
    "brc_strategy_entry_control_events",
    metadata,
    _id("strategy_entry_control_event_id", primary_key=True),
    _id("strategy_group_id"),
    sa.Column("control_version", sa.BigInteger, nullable=False),
    sa.Column("operation", SHORT_TEXT, nullable=False),
    sa.Column("target_state", SHORT_TEXT, nullable=False),
    _id("authorization_id"),
    sa.Column("reason", LONG_TEXT, nullable=False),
    _json("payload"),
    _time("created_at_ms"),
    sa.UniqueConstraint("strategy_group_id", "control_version"),
    sa.CheckConstraint("control_version > 0", name="ver_pos"),
    sa.CheckConstraint("operation IN ('pause', 'resume')", name="op_valid"),
    sa.CheckConstraint("target_state IN ('paused', 'enabled')", name="state_valid"),
)

strategy_entry_controls_current = sa.Table(
    "brc_strategy_entry_controls_current",
    metadata,
    _id("strategy_group_id", primary_key=True),
    sa.Column("entry_state", SHORT_TEXT, nullable=False),
    sa.Column("control_version", sa.BigInteger, nullable=False),
    _id("last_event_id"),
    sa.Column("reason", LONG_TEXT, nullable=False),
    _time("updated_at_ms"),
    sa.CheckConstraint("entry_state IN ('paused', 'enabled')", name="state_valid"),
    sa.CheckConstraint("control_version > 0", name="ver_pos"),
)

owner_authorizations = sa.Table(
    "brc_owner_authorizations",
    metadata,
    _id("authorization_id", primary_key=True),
    sa.Column("purpose", SHORT_TEXT, nullable=False),
    sa.Column("owner_identity", SHORT_TEXT, nullable=False),
    sa.Column("authentication_strength", SHORT_TEXT, nullable=False),
    sa.Column("request_digest", LONG_TEXT, nullable=False),
    _json("target_scope"),
    _id("idempotency_key"),
    _time("authorized_at_ms"),
    sa.UniqueConstraint("idempotency_key"),
    sa.CheckConstraint(
        "purpose IN ('strategy_pause', 'strategy_resume', 'entry_pause', "
        "'entry_resume', 'owner_flatten_all', 'universe_configure', "
        "'selection_mode_change', 'exit_profile_bind', "
        "'exit_profile_retire')",
        name="purpose_valid",
    ),
    sa.CheckConstraint(
        "authentication_strength IN ('session', 'totp_step_up')",
        name="auth_valid",
    ),
    sa.CheckConstraint("request_digest ~ '^sha256:[0-9a-f]{64}$'", name="digest_valid"),
)

owner_control_operation_events = sa.Table(
    "brc_owner_control_operation_events",
    metadata,
    _id("control_operation_event_id", primary_key=True),
    _id("authorization_id"),
    sa.Column("operation_version", sa.BigInteger, nullable=False),
    sa.Column("state", SHORT_TEXT, nullable=False),
    sa.Column("first_blocker", LONG_TEXT, nullable=True),
    _json("payload"),
    _time("created_at_ms"),
    sa.UniqueConstraint("authorization_id", "operation_version"),
    sa.CheckConstraint("operation_version > 0", name="ver_pos"),
)

owner_control_operations_current = sa.Table(
    "brc_owner_control_operations_current",
    metadata,
    _id("authorization_id", primary_key=True),
    sa.Column("operation_kind", SHORT_TEXT, nullable=False),
    sa.Column("state", SHORT_TEXT, nullable=False),
    sa.Column("version", sa.BigInteger, nullable=False),
    _id("runtime_profile_id"),
    sa.Column("venue_id", SHORT_TEXT, nullable=False),
    _id("account_id"),
    _json("target_ticket_ids"),
    sa.Column("snapshot_digest", LONG_TEXT, nullable=False),
    sa.Column("first_blocker", LONG_TEXT, nullable=True),
    _id("claimed_by", nullable=True),
    _time("lease_until_ms", nullable=True),
    _time("created_at_ms"),
    _time("updated_at_ms"),
    sa.CheckConstraint("operation_kind = 'flatten_all'", name="kind_valid"),
    sa.CheckConstraint("version > 0", name="ver_pos"),
    sa.CheckConstraint("snapshot_digest ~ '^sha256:[0-9a-f]{64}$'", name="digest_valid"),
)
sa.Index(
    "ix_brc_owner_control_operations_actionable",
    owner_control_operations_current.c.state,
    owner_control_operations_current.c.updated_at_ms,
)
