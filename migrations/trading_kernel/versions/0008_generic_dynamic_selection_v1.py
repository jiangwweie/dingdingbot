"""Generic Selection comparison provenance and normalized Event grants.

Unreleased capability revision. Runtime materialization is never run by this
migration. Static provenance must be certified before the first schema write.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from src.trading_kernel.infrastructure.generic_selection_source_provenance import (
    certify_0007_static_comparison_sources_sync,
)

revision: str = "0008_generic_dynamic_selection_v1"
down_revision: str | None = "0007_exit_profile_authority_v1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ID = sa.String(160)
DIGEST = sa.String(71)


def upgrade() -> None:
    bind = op.get_bind()
    _require_flat_quiescent_source(bind)
    _require_legacy_event_baseline_source(bind)
    proofs = certify_0007_static_comparison_sources_sync(bind)
    _rename_period_storage()
    _comparison_tables()
    _episode_provenance()
    _bind_static_comparison(bind)
    for proof in proofs:
        bind.execute(sa.text(
            "UPDATE brc_exposure_episode_current SET comparison_source_evidence_digest=:digest, "
            "comparison_binding_digest=:members, comparison_transition_revision=0 "
            "WHERE episode_domain_key=:key AND projection_version=:version"
        ), {"digest": proof.source_evidence_digest, "members": proof.comparison_member_digest,
            "key": proof.episode_domain_key, "version": proof.episode_projection_version})
    _authority_event_bindings(bind)
    _generic_spec_payload_table()
    _selection_epoch_lineage()
    _typed_selection_snapshots(bind)
    _selection_job_epochs()
    _materialization_event_baselines(bind)


def downgrade() -> None:
    raise RuntimeError("0008_generic_dynamic_selection_v1 is fix-forward only")


def _rename_period_storage() -> None:
    """Rename the shared clock without changing any frozen SOR values or hashes."""
    for table in (
        "brc_instrument_selection_jobs_current", "brc_instrument_selection_attempts",
        "brc_instrument_selection_snapshots", "brc_instrument_selection_member_decisions",
        "brc_strategy_universe_materialization_generations", "brc_strategy_entry_vacuums_current",
        "brc_selection_authority_gap_audits_current", "brc_selection_session_authorities",
    ):
        op.alter_column(table, "session_start_ms", new_column_name="period_anchor_ms")
    op.alter_column("brc_strategy_selection_control_current", "pending_effective_session_start_ms",
        new_column_name="pending_effective_period_anchor_ms")


def _require_legacy_event_baseline_source(bind: sa.Connection) -> None:
    """Certify the only source pair family before any target DDL; never guess comparison provenance."""
    for table, prefix in (("brc_strategy_universe_materialization_generations", "previous"),
                          ("brc_strategy_selection_rollback_baselines", "source")):
        invalid = bind.scalar(sa.text(f"""
            SELECT EXISTS(SELECT 1 FROM {table} p
              CROSS JOIN LATERAL (VALUES('long',p.{prefix}_long_universe_version_id),('short',p.{prefix}_short_universe_version_id)) r(side,uid)
              LEFT JOIN brc_strategy_universe_versions u ON u.universe_version_id=r.uid
              LEFT JOIN brc_event_specs e ON e.event_spec_id=u.event_spec_id
              WHERE p.strategy_group_id<>'SOR-001' OR u.universe_version_id IS NULL
                OR e.position_side IS DISTINCT FROM r.side OR u.strategy_group_id IS DISTINCT FROM p.strategy_group_id
                OR e.strategy_version_id IS DISTINCT FROM p.strategy_version_id)
        """))
        if invalid:
            raise RuntimeError(f"BASELINE_SOURCE_MISMATCH:{table}")


def _materialization_event_baselines(bind: sa.Connection) -> None:
    generations = "brc_strategy_universe_materialization_generations"
    baselines = "brc_strategy_selection_rollback_baselines"
    previous = "brc_materialization_generation_event_baselines"
    rollback = "brc_selection_rollback_baseline_events"
    empty = "sha256:" + hashlib.sha256(b'{"selected_exchange_instrument_ids":[]}').hexdigest()
    op.execute(sa.text("""
        CREATE FUNCTION brc_selected_universe_member_digest_v1(target text) RETURNS text LANGUAGE SQL STABLE AS $$
          SELECT 'sha256:' || encode(sha256(convert_to('{"selected_exchange_instrument_ids":[' ||
            coalesce(string_agg(to_json(exchange_instrument_id)::text,',' ORDER BY exchange_instrument_id COLLATE "C"),'') || ']}','UTF8')),'hex')
          FROM brc_strategy_universe_members WHERE universe_version_id=target
        $$
    """))
    op.create_table(previous,
        sa.Column("materialization_generation_id", ID, nullable=False),
        sa.Column("event_spec_id", ID, nullable=False),
        sa.Column("position_side", sa.String(16), nullable=False),
        sa.Column("grant_state", sa.String(16), nullable=False),
        sa.Column("universe_version_id", ID, nullable=True),
        sa.Column("member_set_digest", DIGEST, nullable=False),
        sa.Column("comparison_universe_id", ID, nullable=True),
        sa.PrimaryKeyConstraint("materialization_generation_id", "event_spec_id"),
        sa.UniqueConstraint("materialization_generation_id", "position_side", name="uq_brc_generation_baseline_side"),
        sa.ForeignKeyConstraint(["materialization_generation_id"], [f"{generations}.materialization_generation_id"]),
        sa.ForeignKeyConstraint(["event_spec_id"], ["brc_event_specs.event_spec_id"]),
        sa.ForeignKeyConstraint(["universe_version_id"], ["brc_strategy_universe_versions.universe_version_id"]),
        sa.ForeignKeyConstraint(["comparison_universe_id"], ["brc_comparison_universe_definitions.comparison_universe_id"]),
        sa.CheckConstraint("position_side IN ('long','short')", name="ck_brc_generation_baseline_side"),
        sa.CheckConstraint("member_set_digest ~ '^sha256:[0-9a-f]{64}$'", name="ck_brc_generation_baseline_digest"),
        sa.CheckConstraint(f"(grant_state='ACTIVE' AND universe_version_id IS NOT NULL AND member_set_digest<>'{empty}') OR "
            f"(grant_state='EMPTY' AND universe_version_id IS NULL AND member_set_digest='{empty}')", name="ck_brc_generation_baseline_grant"),
    )
    op.create_table(rollback,
        sa.Column("rollback_baseline_id", ID, nullable=False),
        sa.Column("event_spec_id", ID, nullable=False),
        sa.Column("position_side", sa.String(16), nullable=False),
        sa.Column("universe_version_id", ID, nullable=False),
        sa.Column("comparison_universe_id", ID, nullable=True),
        sa.PrimaryKeyConstraint("rollback_baseline_id", "event_spec_id"),
        sa.UniqueConstraint("rollback_baseline_id", "position_side", name="uq_brc_rollback_baseline_side"),
        sa.ForeignKeyConstraint(["rollback_baseline_id"], [f"{baselines}.rollback_baseline_id"]),
        sa.ForeignKeyConstraint(["event_spec_id"], ["brc_event_specs.event_spec_id"]),
        sa.ForeignKeyConstraint(["universe_version_id"], ["brc_strategy_universe_versions.universe_version_id"]),
        sa.ForeignKeyConstraint(["comparison_universe_id"], ["brc_comparison_universe_definitions.comparison_universe_id"]),
        sa.CheckConstraint("position_side IN ('long','short')", name="ck_brc_rollback_baseline_side"),
    )
    for suffix, side in (("long", "long"), ("short", "short")):
        bind.execute(sa.text(f"""
            INSERT INTO {previous} SELECT g.materialization_generation_id,u.event_spec_id,:side,'ACTIVE',u.universe_version_id,
              brc_selected_universe_member_digest_v1(u.universe_version_id),NULL
            FROM {generations} g JOIN brc_strategy_universe_versions u ON u.universe_version_id=g.previous_{suffix}_universe_version_id
        """), {"side": side})
        bind.execute(sa.text(f"""
            INSERT INTO {rollback} SELECT b.rollback_baseline_id,u.event_spec_id,:side,u.universe_version_id,NULL
            FROM {baselines} b JOIN brc_strategy_universe_versions u ON u.universe_version_id=b.source_{suffix}_universe_version_id
        """), {"side": side})
    op.drop_column(generations, "previous_long_universe_version_id")
    op.drop_column(generations, "previous_short_universe_version_id")
    op.drop_column(baselines, "source_long_universe_version_id")
    op.drop_column(baselines, "source_short_universe_version_id")
    op.drop_constraint("ck_brc_materialization_generation_source_shape", generations, type_="check")
    op.create_check_constraint("ck_brc_materialization_generation_source_shape", generations,
        "(selection_mode='dynamic_selection' AND selection_snapshot_id IS NOT NULL AND rollback_baseline_id IS NULL "
        "AND period_anchor_ms IS NOT NULL AND desired_member_count BETWEEN 1 AND 16) OR "
        "(selection_mode='static_baseline' AND selection_snapshot_id IS NULL AND rollback_baseline_id IS NOT NULL "
        "AND period_anchor_ms IS NULL AND desired_member_count BETWEEN 1 AND 10)")
    op.execute(sa.text("""
        CREATE OR REPLACE FUNCTION brc_validate_materialization_generation_targets() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE gid text; sid text; expected integer; actual integer; matching integer;
        BEGIN
          gid := COALESCE(NEW.materialization_generation_id,OLD.materialization_generation_id);
          SELECT selection_spec_id INTO sid FROM brc_strategy_universe_materialization_generations WHERE materialization_generation_id=gid;
          IF NOT FOUND THEN RETURN NULL; END IF;
          SELECT count(*) INTO expected FROM brc_instrument_selection_spec_events WHERE selection_spec_id=sid;
          SELECT count(*),count(e.event_spec_id) INTO actual,matching FROM brc_strategy_universe_materialization_targets t
            LEFT JOIN brc_instrument_selection_spec_events e ON e.selection_spec_id=sid AND e.event_spec_id=t.event_spec_id AND e.position_side=t.position_side
            WHERE t.materialization_generation_id=gid;
          IF expected NOT IN (1,2) OR actual<>expected OR matching<>expected THEN
            RAISE EXCEPTION 'Materialization Generation requires exact bound Event targets';
          END IF;
          RETURN NULL;
        END; $$
    """))
    op.execute(sa.text("""
        CREATE FUNCTION brc_validate_generation_baseline_v1() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE gid text; g brc_strategy_universe_materialization_generations%ROWTYPE;
                spec brc_instrument_selection_specs%ROWTYPE; expected integer; actual integer; matching integer; states integer;
        BEGIN
          gid := NEW.materialization_generation_id;
          SELECT * INTO g FROM brc_strategy_universe_materialization_generations WHERE materialization_generation_id=gid;
          SELECT * INTO spec FROM brc_instrument_selection_specs WHERE selection_spec_id=g.selection_spec_id;
          IF g.strategy_group_id<>spec.strategy_group_id OR g.strategy_version_id<>spec.strategy_version_id
             OR (spec.selection_kind='sor_dynamic_v0' AND g.selection_mode='dynamic_selection' AND g.desired_member_count>7) THEN
            RAISE EXCEPTION 'Generation Spec identity or member limit mismatch';
          END IF;
          SELECT count(*) INTO expected FROM brc_instrument_selection_spec_events WHERE selection_spec_id=g.selection_spec_id;
          SELECT count(*),count(e.event_spec_id),count(DISTINCT b.grant_state) INTO actual,matching,states
            FROM brc_materialization_generation_event_baselines b LEFT JOIN brc_instrument_selection_spec_events e
              ON e.selection_spec_id=g.selection_spec_id AND e.event_spec_id=b.event_spec_id AND e.position_side=b.position_side
            WHERE b.materialization_generation_id=gid;
          IF expected NOT IN (1,2) OR actual<>expected OR matching<>expected OR states<>1 THEN
            RAISE EXCEPTION 'Generation requires exact previous Event set';
          END IF;
          IF EXISTS (SELECT 1 FROM brc_materialization_generation_event_baselines b
            LEFT JOIN brc_strategy_universe_versions u ON u.universe_version_id=b.universe_version_id
            LEFT JOIN brc_event_specs e ON e.event_spec_id=u.event_spec_id
            WHERE b.materialization_generation_id=gid AND (
              (b.grant_state='ACTIVE' AND (u.event_spec_id IS DISTINCT FROM b.event_spec_id OR u.strategy_group_id<>g.strategy_group_id
                OR e.strategy_version_id<>g.strategy_version_id OR b.member_set_digest<>brc_selected_universe_member_digest_v1(b.universe_version_id)))
              OR ((g.strategy_group_id IN ('MPG-001','MI-001')) <> (b.comparison_universe_id IS NOT NULL)))) THEN
            RAISE EXCEPTION 'Generation previous Universe/digest/comparison mismatch';
          END IF;
          RETURN NULL;
        END; $$
    """))
    op.execute(sa.text("""
        CREATE FUNCTION brc_validate_rollback_baseline_v1() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE bid text; b brc_strategy_selection_rollback_baselines%ROWTYPE; expected integer; actual integer; matching integer;
        BEGIN
          bid := NEW.rollback_baseline_id;
          SELECT * INTO b FROM brc_strategy_selection_rollback_baselines WHERE rollback_baseline_id=bid;
          SELECT count(*) INTO expected FROM brc_event_specs WHERE strategy_version_id=b.strategy_version_id;
          SELECT count(*),count(e.event_spec_id) INTO actual,matching FROM brc_selection_rollback_baseline_events r
            LEFT JOIN brc_event_specs e ON e.strategy_version_id=b.strategy_version_id AND e.event_spec_id=r.event_spec_id AND e.position_side=r.position_side
            WHERE r.rollback_baseline_id=bid;
          IF expected NOT IN (1,2) OR actual<>expected OR matching<>expected THEN RAISE EXCEPTION 'Static baseline requires exact Event set'; END IF;
          IF EXISTS (SELECT 1 FROM brc_selection_rollback_baseline_events r JOIN brc_strategy_universe_versions u ON u.universe_version_id=r.universe_version_id
            JOIN brc_event_specs e ON e.event_spec_id=u.event_spec_id
            WHERE r.rollback_baseline_id=bid AND (u.event_spec_id<>r.event_spec_id OR u.strategy_group_id<>b.strategy_group_id OR e.strategy_version_id<>b.strategy_version_id
              OR ((b.strategy_group_id IN ('MPG-001','MI-001'))<>(r.comparison_universe_id IS NOT NULL)))) THEN
            RAISE EXCEPTION 'Static baseline Universe/comparison mismatch';
          END IF;
          RETURN NULL;
        END; $$
    """))
    for table in (generations, previous):
        op.execute(sa.text(f"CREATE CONSTRAINT TRIGGER trg_{table}_baseline_v1 AFTER INSERT OR UPDATE ON {table} "
            "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION brc_validate_generation_baseline_v1()"))
    for table in (baselines, rollback):
        op.execute(sa.text(f"CREATE CONSTRAINT TRIGGER trg_{table}_events_v1 AFTER INSERT ON {table} "
            "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION brc_validate_rollback_baseline_v1()"))
    for table in (previous, rollback):
        op.execute(sa.text(f"CREATE TRIGGER trg_{table}_immutable BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION brc_reject_immutable_selection_fact_mutation()"))
    op.execute(sa.text("""
        CREATE FUNCTION brc_preserve_generation_source_identity_v1() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF ROW(NEW.materialization_generation_id,NEW.selection_spec_id,NEW.strategy_group_id,NEW.strategy_version_id,
              NEW.selection_mode,NEW.selection_snapshot_id,NEW.rollback_baseline_id,NEW.period_anchor_ms,
              NEW.desired_member_count,NEW.semantic_digest,NEW.created_at_ms)
             IS DISTINCT FROM ROW(OLD.materialization_generation_id,OLD.selection_spec_id,OLD.strategy_group_id,OLD.strategy_version_id,
              OLD.selection_mode,OLD.selection_snapshot_id,OLD.rollback_baseline_id,OLD.period_anchor_ms,
              OLD.desired_member_count,OLD.semantic_digest,OLD.created_at_ms) THEN
            RAISE EXCEPTION 'Generation source identity is immutable';
          END IF;
          RETURN NEW;
        END; $$
    """))
    op.execute(sa.text(f"CREATE TRIGGER trg_generation_source_identity_v1 BEFORE UPDATE ON {generations} "
        "FOR EACH ROW EXECUTE FUNCTION brc_preserve_generation_source_identity_v1()"))


def _selection_job_epochs() -> None:
    control = "brc_strategy_selection_control_current"
    jobs = "brc_instrument_selection_jobs_current"
    attempts = "brc_instrument_selection_attempts"
    snapshots = "brc_instrument_selection_snapshots"
    op.add_column(control, sa.Column("selection_epoch_id", ID, nullable=True))
    for table in (jobs, attempts):
        op.add_column(table, sa.Column("selection_epoch_id", ID, nullable=False, server_default="sor-v0"))
        op.add_column(table, sa.Column("selection_control_version", sa.BigInteger(), nullable=True))
        op.add_column(table, sa.Column("predecessor_snapshot_id", ID, nullable=True))
        op.add_column(table, sa.Column("predecessor_member_digest", DIGEST, nullable=True))
        op.create_foreign_key(f"fk_{table}_predecessor", table, snapshots,
            ["predecessor_snapshot_id"], ["selection_snapshot_id"])
        op.create_check_constraint(f"ck_{table}_epoch_shape", table,
            "(selection_epoch_id='sor-v0' AND selection_control_version IS NULL AND predecessor_snapshot_id IS NULL AND predecessor_member_digest IS NULL) OR "
            "(selection_epoch_id<>'sor-v0' AND length(trim(selection_epoch_id))>0 AND selection_control_version IS NOT NULL AND selection_control_version>0 AND "
            "((predecessor_snapshot_id IS NULL AND predecessor_member_digest IS NULL) OR "
            "(predecessor_snapshot_id IS NOT NULL AND predecessor_member_digest IS NOT NULL AND predecessor_member_digest ~ '^sha256:[0-9a-f]{64}$')))")
    op.drop_constraint("uq_brc_instrument_selection_jobs_current_period", jobs, type_="unique")
    op.create_unique_constraint("uq_brc_instrument_selection_jobs_current_period", jobs,
        ["selection_spec_id", "selection_epoch_id", "period_anchor_ms"])
    op.drop_constraint("uq_brc_instrument_selection_attempts_period_number", attempts, type_="unique")
    op.create_unique_constraint("uq_brc_instrument_selection_attempts_period_number", attempts,
        ["selection_spec_id", "selection_epoch_id", "period_anchor_ms", "attempt_number"])
    op.create_unique_constraint("uq_brc_selection_job_epoch_identity", jobs,
        ["selection_job_id", "selection_spec_id", "selection_epoch_id", "period_anchor_ms"])
    op.create_foreign_key("fk_brc_selection_attempt_job_epoch", attempts, jobs,
        ["selection_job_id", "selection_spec_id", "selection_epoch_id", "period_anchor_ms"],
        ["selection_job_id", "selection_spec_id", "selection_epoch_id", "period_anchor_ms"])
    op.create_unique_constraint("uq_brc_selection_snapshot_job_identity", snapshots,
        ["selection_snapshot_id", "selection_spec_id", "selection_epoch_id", "period_anchor_ms"])
    op.create_foreign_key("fk_brc_selection_job_snapshot_epoch", jobs, snapshots,
        ["selection_snapshot_id", "selection_spec_id", "selection_epoch_id", "period_anchor_ms"],
        ["selection_snapshot_id", "selection_spec_id", "selection_epoch_id", "period_anchor_ms"])
    op.execute(sa.text("""
        CREATE FUNCTION brc_validate_selection_control_epoch_v1() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE kind text; spec_group text; cadence integer; needs_epoch boolean;
        BEGIN
          SELECT selection_kind,strategy_group_id INTO kind,spec_group FROM brc_instrument_selection_specs WHERE selection_spec_id=NEW.selection_spec_id;
          IF spec_group IS DISTINCT FROM NEW.strategy_group_id THEN RAISE EXCEPTION 'Selection Control parent Spec mismatch'; END IF;
          IF kind='sor_dynamic_v0' THEN
            IF NEW.selection_epoch_id IS NOT NULL THEN RAISE EXCEPTION 'SOR Control cannot carry Generic epoch'; END IF;
            RETURN NEW;
          END IF;
          needs_epoch := NEW.selection_mode='dynamic_selection' OR coalesce(NEW.pending_selection_mode='dynamic_selection',false);
          IF needs_epoch THEN
            IF NEW.selection_epoch_id IS NULL OR NEW.selection_epoch_id='sor-v0' OR length(trim(NEW.selection_epoch_id))=0 THEN
              RAISE EXCEPTION 'Generic Dynamic Control requires epoch';
            END IF;
          ELSIF NEW.selection_epoch_id IS NOT NULL THEN RAISE EXCEPTION 'Static Generic Control cannot retain epoch'; END IF;
          SELECT cadence_hours INTO cadence FROM brc_generic_dynamic_selection_specs_v1 WHERE selection_spec_id=NEW.selection_spec_id;
          IF NEW.pending_effective_period_anchor_ms IS NOT NULL AND NEW.pending_effective_period_anchor_ms % (cadence*3600000::bigint)<>0 THEN
            RAISE EXCEPTION 'Generic pending Control requires exact period';
          END IF;
          RETURN NEW;
        END; $$
    """))
    op.execute(sa.text(f"CREATE TRIGGER trg_selection_control_epoch_v1 BEFORE INSERT OR UPDATE ON {control} "
        "FOR EACH ROW EXECUTE FUNCTION brc_validate_selection_control_epoch_v1()"))
    op.execute(sa.text("""
        CREATE FUNCTION brc_validate_selection_job_epoch_v1() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE kind text; cadence integer;
        BEGIN
          SELECT selection_kind INTO kind FROM brc_instrument_selection_specs WHERE selection_spec_id=NEW.selection_spec_id;
          IF TG_OP='UPDATE' AND (NEW.selection_job_id<>OLD.selection_job_id OR NEW.selection_spec_id<>OLD.selection_spec_id
             OR NEW.selection_epoch_id<>OLD.selection_epoch_id OR NEW.period_anchor_ms<>OLD.period_anchor_ms
             OR NEW.feature_cutoff_at_ms<>OLD.feature_cutoff_at_ms OR NEW.scheduled_at_ms<>OLD.scheduled_at_ms) THEN
            RAISE EXCEPTION 'Selection Job period identity is immutable';
          END IF;
          IF kind='sor_dynamic_v0' THEN
            IF NEW.selection_epoch_id<>'sor-v0' THEN RAISE EXCEPTION 'SOR Job cannot carry Generic epoch'; END IF;
            RETURN NEW;
          END IF;
          SELECT cadence_hours INTO cadence FROM brc_generic_dynamic_selection_specs_v1 WHERE selection_spec_id=NEW.selection_spec_id;
          IF NEW.selection_epoch_id='sor-v0' OR NEW.feature_cutoff_at_ms<>NEW.period_anchor_ms
             OR NEW.scheduled_at_ms<>NEW.period_anchor_ms OR NEW.period_anchor_ms<=0
             OR NEW.period_anchor_ms % (cadence*3600000::bigint)<>0 THEN
            RAISE EXCEPTION 'Generic Job requires exact epoch/period';
          END IF;
          RETURN NEW;
        END; $$
    """))
    op.execute(sa.text(f"CREATE TRIGGER trg_selection_job_epoch_v1 BEFORE INSERT OR UPDATE ON {jobs} "
        "FOR EACH ROW EXECUTE FUNCTION brc_validate_selection_job_epoch_v1()"))


def _typed_selection_snapshots(bind: sa.Connection) -> None:
    """One fact chain, with explicit family-specific validation, not fake ORs."""
    snapshots = "brc_instrument_selection_snapshots"
    members = "brc_instrument_selection_member_decisions"
    geometry = ("or_high", "or_low", "or_width", "pre_or_atr14", "pre_or_width_atr14",
                "trailing_24h_quote_volume", "or_geometry_valid", "atr_valid", "activity_valid")
    for table, suffixes in ((snapshots, ("count_valid", "time_valid")),
                            (members, ("window_valid", "numeric_valid", "reason_valid", "rank_shape"))):
        op.add_column(table, sa.Column("selection_family", sa.String(40), nullable=False, server_default="sor_dynamic_v0"))
        op.create_check_constraint(f"ck_{table}_family", table,
                                   "selection_family IN ('sor_dynamic_v0','generic_dynamic_v1')")
        existing = {c["name"]: c["sqltext"] for c in sa.inspect(bind).get_check_constraints(table)}
        for suffix in suffixes:
            name = f"ck_{table}_{suffix}"
            expression = existing[name]
            op.drop_constraint(name, table, type_="check")
            op.create_check_constraint(name, table,
                f"selection_family <> 'sor_dynamic_v0' OR COALESCE(({expression}),false)")
    for column in geometry:
        op.alter_column(members, column, nullable=True)
    op.add_column(members, sa.Column("feature_value", sa.Numeric(), nullable=True))
    op.add_column(members, sa.Column("retained", sa.Boolean(), nullable=True))
    op.add_column(members, sa.Column("qualification_fact", sa.dialects.postgresql.JSONB(), nullable=True))
    op.add_column(members, sa.Column("qualification_semantic_digest", DIGEST, nullable=True))
    sor_shape = " AND ".join(f"{column} IS NOT NULL" for column in geometry)
    generic_shape = " AND ".join(f"{column} IS NULL" for column in geometry)
    op.create_check_constraint("ck_brc_selection_member_family_payload", members,
        f"(selection_family='sor_dynamic_v0' AND {sor_shape} AND feature_value IS NULL AND retained IS NULL AND qualification_fact IS NULL AND qualification_semantic_digest IS NULL) OR "
        f"(selection_family='generic_dynamic_v1' AND {generic_shape} AND feature_value IS NOT NULL "
        "AND feature_value NOT IN ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric) "
        "AND retained IS NOT NULL AND stable_rank IS NOT NULL AND stable_rank BETWEEN 1 AND 24 "
        "AND qualification_fact IS NOT NULL AND jsonb_typeof(qualification_fact)='object' "
        "AND qualification_semantic_digest IS NOT NULL AND qualification_semantic_digest ~ '^sha256:[0-9a-f]{64}$' "
        "AND ((selection_ready AND primary_reason IS NULL) OR (NOT selection_ready AND primary_reason IS NOT NULL AND primary_reason IN "
        "('PRODUCT_PROFILE_INCOMPATIBLE','VENUE_PRODUCT_INCOMPATIBLE','VENUE_NOT_TRADING'))) AND secondary_reasons='[]'::jsonb "
        "AND (NOT selected OR selection_ready) AND (NOT retained OR selected) "
        "AND member_state=CASE WHEN selected THEN 'SELECTED' WHEN selection_ready THEN 'NOT_SELECTED' ELSE 'INELIGIBLE' END)")
    op.create_unique_constraint("uq_brc_selection_snapshot_family", snapshots,
        ["selection_snapshot_id", "selection_spec_id", "selection_family", "period_anchor_ms", "feature_cutoff_at_ms"])
    op.create_foreign_key("fk_brc_selection_member_parent_identity", members, snapshots,
        ["selection_snapshot_id", "selection_spec_id", "selection_family", "period_anchor_ms", "feature_cutoff_at_ms"],
        ["selection_snapshot_id", "selection_spec_id", "selection_family", "period_anchor_ms", "feature_cutoff_at_ms"])
    op.drop_constraint("uq_brc_instrument_selection_snapshots_period", snapshots, type_="unique")
    op.create_unique_constraint("uq_brc_instrument_selection_snapshots_period", snapshots,
        ["selection_spec_id", "selection_epoch_id", "period_anchor_ms"])
    op.create_index("ix_brc_selection_snapshot_epoch_latest", snapshots,
        ["selection_spec_id", "selection_epoch_id", "feature_cutoff_at_ms"])
    op.execute(sa.text("""
        CREATE FUNCTION brc_validate_typed_selection_snapshot_v1() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE s brc_instrument_selection_snapshots%ROWTYPE;
                spec brc_instrument_selection_specs%ROWTYPE;
                payload brc_generic_dynamic_selection_specs_v1%ROWTYPE;
                actual_ready integer; actual_selected integer; prior_id text;
        BEGIN
          SELECT * INTO s FROM brc_instrument_selection_snapshots WHERE selection_snapshot_id=NEW.selection_snapshot_id;
          SELECT * INTO spec FROM brc_instrument_selection_specs WHERE selection_spec_id=s.selection_spec_id;
          IF s.selection_family<>spec.selection_kind OR s.strategy_group_id<>spec.strategy_group_id
             OR s.strategy_version_id<>spec.strategy_version_id THEN
            RAISE EXCEPTION 'Selection Snapshot parent Spec identity mismatch';
          END IF;
          IF s.selection_family='sor_dynamic_v0' THEN RETURN NULL; END IF;
          SELECT * INTO payload FROM brc_generic_dynamic_selection_specs_v1 WHERE selection_spec_id=s.selection_spec_id;
          IF NOT FOUND THEN RAISE EXCEPTION 'Generic Spec not installed'; END IF;
          IF s.feature_cutoff_at_ms<>s.period_anchor_ms OR s.period_anchor_ms<=0
             OR s.period_anchor_ms % (payload.cadence_hours*3600000::bigint)<>0
             OR s.eligibility_not_before_ms<>s.feature_cutoff_at_ms+3600000
             OR s.expires_at_ms<>s.eligibility_not_before_ms+payload.cadence_hours*3600000::bigint
             OR s.decision_at_ms<s.feature_cutoff_at_ms OR s.source_observed_at_ms<s.decision_at_ms
             OR s.created_at_ms<s.source_observed_at_ms THEN
            RAISE EXCEPTION 'Generic Snapshot time mismatch';
          END IF;
          SELECT count(*) FILTER (WHERE selection_ready),count(*) FILTER (WHERE selected)
          INTO actual_ready,actual_selected FROM brc_instrument_selection_member_decisions WHERE selection_snapshot_id=s.selection_snapshot_id;
          IF s.candidate_count<>24 OR s.ready_count<>actual_ready OR s.selected_count<>actual_selected
             OR s.selected_count>payload.retain_rank THEN RAISE EXCEPTION 'Generic Snapshot count mismatch'; END IF;
          SELECT selection_snapshot_id INTO prior_id FROM brc_instrument_selection_snapshots
          WHERE selection_spec_id=s.selection_spec_id AND selection_epoch_id=s.selection_epoch_id
            AND feature_cutoff_at_ms<s.feature_cutoff_at_ms
          ORDER BY feature_cutoff_at_ms DESC LIMIT 1;
          IF prior_id IS DISTINCT FROM s.predecessor_snapshot_id THEN
            RAISE EXCEPTION 'Selection predecessor is not latest Desired Snapshot';
          END IF;
          IF EXISTS (
            SELECT 1 FROM (
              SELECT m.*,row_number() OVER (ORDER BY feature_value DESC,exchange_instrument_id COLLATE "C") AS expected_rank
              FROM brc_instrument_selection_member_decisions m WHERE selection_snapshot_id=s.selection_snapshot_id
            ) ranked WHERE stable_rank<>expected_rank
              OR input_window_end_ms<>s.feature_cutoff_at_ms
              OR input_window_start_ms<>s.feature_cutoff_at_ms-payload.window_bars*3600000::bigint
              OR retained IS DISTINCT FROM (selection_ready AND stable_rank<=payload.retain_rank AND EXISTS (
                SELECT 1 FROM brc_instrument_selection_member_decisions p
                WHERE p.selection_snapshot_id=s.predecessor_snapshot_id AND p.exchange_instrument_id=ranked.exchange_instrument_id AND p.selected))
              OR selected IS DISTINCT FROM (selection_ready AND (stable_rank<=payload.entry_rank OR retained))
          ) THEN RAISE EXCEPTION 'Generic Snapshot ranking/retention/window mismatch'; END IF;
          RETURN NULL;
        END; $$
    """))
    for table in (snapshots, members):
        op.execute(sa.text(f"CREATE CONSTRAINT TRIGGER trg_{table}_typed_v1 AFTER INSERT ON {table} "
            "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION brc_validate_typed_selection_snapshot_v1()"))


def _selection_epoch_lineage() -> None:
    """Selection memory belongs to Snapshot lineage, never the Active Universe."""
    table = "brc_instrument_selection_snapshots"
    op.add_column(table, sa.Column("selection_epoch_id", ID, nullable=False, server_default="sor-v0"))
    op.add_column(table, sa.Column("predecessor_snapshot_id", ID, nullable=True))
    op.add_column(table, sa.Column("predecessor_member_digest", DIGEST, nullable=True))
    op.create_foreign_key("fk_brc_selection_snapshot_predecessor", table, table,
                          ["predecessor_snapshot_id"], ["selection_snapshot_id"])
    op.create_check_constraint("ck_brc_selection_snapshot_predecessor_shape", table,
        "(predecessor_snapshot_id IS NULL AND predecessor_member_digest IS NULL) OR "
        "(predecessor_snapshot_id IS NOT NULL AND predecessor_snapshot_id <> selection_snapshot_id "
        "AND predecessor_member_digest IS NOT NULL AND predecessor_member_digest ~ '^sha256:[0-9a-f]{64}$')")
    op.execute(sa.text("""
        CREATE FUNCTION brc_validate_selection_predecessor_v1() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE kind text; prior brc_instrument_selection_snapshots%ROWTYPE; expected_digest text;
        BEGIN
          SELECT selection_kind INTO kind FROM brc_instrument_selection_specs WHERE selection_spec_id=NEW.selection_spec_id;
          IF kind='sor_dynamic_v0' THEN
            IF NEW.selection_epoch_id<>'sor-v0' OR NEW.predecessor_snapshot_id IS NOT NULL THEN
              RAISE EXCEPTION 'SOR Snapshot must retain its frozen non-hysteretic identity';
            END IF;
            RETURN NULL;
          END IF;
          IF NEW.selection_epoch_id='sor-v0' OR length(trim(NEW.selection_epoch_id))=0 THEN
            RAISE EXCEPTION 'Generic Snapshot requires an explicit Selection epoch';
          END IF;
          IF NEW.predecessor_snapshot_id IS NULL THEN RETURN NULL; END IF;
          SELECT * INTO prior FROM brc_instrument_selection_snapshots WHERE selection_snapshot_id=NEW.predecessor_snapshot_id;
          IF NOT FOUND OR prior.selection_spec_id<>NEW.selection_spec_id
             OR prior.selection_epoch_id<>NEW.selection_epoch_id
             OR prior.feature_cutoff_at_ms>=NEW.feature_cutoff_at_ms
             OR prior.created_at_ms>NEW.created_at_ms THEN
            RAISE EXCEPTION 'Selection predecessor Spec/epoch/time mismatch';
          END IF;
          SELECT 'sha256:' || encode(sha256(convert_to(
            '{"selected_exchange_instrument_ids":[' || coalesce(string_agg(to_json(exchange_instrument_id)::text,',' ORDER BY exchange_instrument_id),'') || ']}', 'UTF8')),'hex')
          INTO expected_digest FROM brc_instrument_selection_member_decisions
          WHERE selection_snapshot_id=NEW.predecessor_snapshot_id AND selected;
          IF expected_digest<>NEW.predecessor_member_digest THEN
            RAISE EXCEPTION 'Selection predecessor member digest mismatch';
          END IF;
          RETURN NULL;
        END; $$
    """))
    op.execute(sa.text(f"CREATE CONSTRAINT TRIGGER trg_selection_predecessor_v1 AFTER INSERT ON {table} "
                       "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION brc_validate_selection_predecessor_v1()"))


def _generic_spec_payload_table() -> None:
    op.drop_constraint("ck_brc_instrument_selection_specs_kind_valid", "brc_instrument_selection_specs", type_="check")
    op.create_check_constraint("ck_brc_instrument_selection_specs_kind_valid", "brc_instrument_selection_specs",
                               "selection_kind IN ('sor_dynamic_v0','generic_dynamic_v1')")
    op.create_table(
        "brc_generic_dynamic_selection_specs_v1",
        sa.Column("selection_spec_id", ID, primary_key=True),
        sa.Column("cadence_hours", sa.Integer(), nullable=False),
        sa.Column("entry_rank", sa.Integer(), nullable=False),
        sa.Column("retain_rank", sa.Integer(), nullable=False),
        sa.Column("window_bars", sa.Integer(), nullable=False),
        sa.Column("delay_ms", sa.BigInteger(), nullable=False),
        sa.Column("decimal_precision", sa.Integer(), nullable=False),
        sa.Column("decimal_rounding", sa.String(32), nullable=False),
        sa.Column("max_consecutive_selection_miss", sa.Integer(), nullable=False),
        sa.Column("materialization_timeout_ms", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["selection_spec_id"], ["brc_instrument_selection_specs.selection_spec_id"]),
        sa.CheckConstraint("delay_ms=3600000 AND decimal_precision=38 AND decimal_rounding='ROUND_HALF_EVEN' "
            "AND max_consecutive_selection_miss=1 AND materialization_timeout_ms=1800000 AND retain_rank=16"),
        sa.CheckConstraint("(selection_spec_id='CPM_ABSOLUTE_DIRECTIONAL_EFFICIENCY_V1' AND cadence_hours=4 AND entry_rank=16 AND window_bars=25) OR "
            "(selection_spec_id='MPG_PERSISTENT_LEADERSHIP_SCORE_V1' AND cadence_hours=1 AND entry_rank=12 AND window_bars=14) OR "
            "(selection_spec_id='MI_POSITIVE_IMPULSE_RECENCY_V0' AND cadence_hours=1 AND entry_rank=16 AND window_bars=13) OR "
            "(selection_spec_id='BRF2_RESIDUAL_EXTENSION_V0' AND cadence_hours=4 AND entry_rank=16 AND window_bars=73)"),
    )
    op.execute(sa.text("CREATE TRIGGER trg_brc_generic_dynamic_selection_specs_v1_immutable BEFORE UPDATE OR DELETE "
        "ON brc_generic_dynamic_selection_specs_v1 FOR EACH ROW EXECUTE FUNCTION brc_reject_immutable_selection_fact_mutation()"))
    op.execute(sa.text("""
        CREATE FUNCTION brc_validate_generic_spec_v1() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE sid text; kind text; version_id text; group_id text; payload_count integer; member_count integer; event_count integer; bad_count integer;
        BEGIN
          sid := COALESCE(NEW.selection_spec_id,OLD.selection_spec_id);
          SELECT selection_kind,strategy_version_id,strategy_group_id INTO kind,version_id,group_id
          FROM brc_instrument_selection_specs WHERE selection_spec_id=sid;
          IF NOT FOUND THEN RETURN NULL; END IF;
          SELECT count(*) INTO payload_count FROM brc_generic_dynamic_selection_specs_v1 WHERE selection_spec_id=sid;
          IF kind<>'generic_dynamic_v1' THEN
            IF payload_count<>0 THEN RAISE EXCEPTION 'Spec family/payload mismatch'; END IF;
            RETURN NULL;
          END IF;
          SELECT count(*) INTO member_count FROM brc_instrument_selection_spec_members WHERE selection_spec_id=sid;
          SELECT count(*),count(*) FILTER (WHERE e.strategy_version_id IS DISTINCT FROM version_id OR e.position_side IS DISTINCT FROM b.position_side)
          INTO event_count,bad_count FROM brc_instrument_selection_spec_events b
          LEFT JOIN brc_event_specs e ON e.event_spec_id=b.event_spec_id WHERE b.selection_spec_id=sid;
          IF payload_count<>1 OR member_count<>24 OR event_count<>1 OR bad_count<>0 THEN
            RAISE EXCEPTION 'Generic Spec requires exact payload, Candidate24 and bound Event';
          END IF;
          RETURN NULL;
        END; $$
    """))
    for table in ("brc_instrument_selection_specs", "brc_generic_dynamic_selection_specs_v1",
                  "brc_instrument_selection_spec_members", "brc_instrument_selection_spec_events"):
        op.execute(sa.text(f"CREATE CONSTRAINT TRIGGER trg_{table}_generic_shape AFTER INSERT OR UPDATE OR DELETE ON {table} "
                           "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION brc_validate_generic_spec_v1()"))


def _require_flat_quiescent_source(bind: sa.Connection) -> None:
    revision_in_db = bind.scalar(sa.text("SELECT version_num FROM alembic_version"))
    if revision_in_db != down_revision:
        raise RuntimeError("0008 requires exact 0007 source")
    bind.execute(sa.text(
        "LOCK TABLE brc_trade_tickets, brc_trade_aggregates, brc_positions_current, "
        "brc_budget_reservations, brc_exchange_commands, brc_runtime_incidents, "
        "brc_strategy_universe_versions, brc_strategy_universe_current, "
        "brc_runtime_scopes_current, brc_exposure_episode_current, "
        "brc_comparative_projection_current, brc_facts_current, brc_readiness_current, "
        "brc_strategy_selection_control_current, brc_strategy_universe_materialization_generations, brc_strategy_selection_rollback_baselines, "
        "brc_strategy_entry_vacuums_current IN SHARE ROW EXCLUSIVE MODE"
    ))
    predicates = {
        "brc_trade_aggregates": "status NOT IN ('terminal','leverage_rejected','entry_rejected','entry_reconciled_absent')",
        "brc_positions_current": "quantity <> 0",
        "brc_budget_reservations": "status='active'",
        "brc_trade_tickets": "active_netting_domain_key IS NOT NULL",
        "brc_exchange_commands": "status IN ('prepared','claimed','dispatch_started','outcome_unknown')",
        "brc_runtime_incidents": "status='open'",
        "brc_strategy_universe_versions": "lifecycle_state IN ('warming','staged')",
        "brc_strategy_universe_materialization_generations": "lifecycle_state IN ('PENDING','DESIRED','DRAINING_ENTRY','MATERIALIZING','STAGED')",
        "brc_strategy_entry_vacuums_current": "resolved_at_ms IS NULL",
    }
    for table, predicate in predicates.items():
        if bind.scalar(sa.text(f"SELECT EXISTS(SELECT 1 FROM {table} WHERE {predicate})")):
            raise RuntimeError(f"0008 requires flat quiescent source: {table}")


def _comparison_tables() -> None:
    op.create_table(
        "brc_comparison_universe_definitions",
        sa.Column("comparison_universe_id", ID, primary_key=True),
        sa.Column("member_set_digest", DIGEST, nullable=False, unique=True),
        sa.Column("member_count", sa.Integer(), nullable=False),
        sa.CheckConstraint("member_count BETWEEN 1 AND 24"),
        sa.CheckConstraint("member_set_digest ~ '^sha256:[0-9a-f]{64}$'"),
    )
    op.create_table(
        "brc_comparison_universe_members",
        sa.Column("comparison_universe_id", ID, nullable=False),
        sa.Column("exchange_instrument_id", ID, nullable=False),
        sa.PrimaryKeyConstraint("comparison_universe_id", "exchange_instrument_id"),
        sa.ForeignKeyConstraint(["comparison_universe_id"], ["brc_comparison_universe_definitions.comparison_universe_id"]),
        sa.ForeignKeyConstraint(["exchange_instrument_id"], ["brc_instruments.exchange_instrument_id"]),
    )
    op.create_table(
        "brc_comparison_binding_current",
        sa.Column("event_spec_id", ID, primary_key=True),
        sa.Column("comparison_universe_id", ID, nullable=False),
        sa.Column("comparison_transition_revision", sa.BigInteger(), nullable=False),
        sa.Column("source_static_universe_version_id", ID, nullable=True),
        sa.ForeignKeyConstraint(["event_spec_id"], ["brc_event_specs.event_spec_id"]),
        sa.ForeignKeyConstraint(["comparison_universe_id"], ["brc_comparison_universe_definitions.comparison_universe_id"]),
        sa.ForeignKeyConstraint(["source_static_universe_version_id"], ["brc_strategy_universe_versions.universe_version_id"]),
        sa.CheckConstraint("comparison_transition_revision >= 0"),
    )
    for table in ("brc_comparison_universe_definitions", "brc_comparison_universe_members"):
        op.execute(sa.text(f"CREATE TRIGGER trg_{table}_immutable BEFORE UPDATE OR DELETE ON {table} "
                           "FOR EACH ROW EXECUTE FUNCTION brc_reject_immutable_selection_fact_mutation()"))
    op.execute(sa.text("""
        CREATE FUNCTION brc_validate_comparison_members_v1() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE cid text; expected integer; actual integer; stored text; actual_digest text;
        BEGIN
          cid := COALESCE(NEW.comparison_universe_id,OLD.comparison_universe_id);
          SELECT member_count,member_set_digest INTO expected,stored FROM brc_comparison_universe_definitions WHERE comparison_universe_id=cid;
          IF NOT FOUND THEN RETURN NULL; END IF;
          SELECT count(*), 'sha256:' || encode(sha256(convert_to(
            '{"exchange_instrument_ids":[' || coalesce(string_agg(to_json(exchange_instrument_id)::text,',' ORDER BY exchange_instrument_id),'') || ']}','UTF8')),'hex')
          INTO actual,actual_digest FROM brc_comparison_universe_members WHERE comparison_universe_id=cid;
          IF expected<>actual OR stored<>actual_digest THEN RAISE EXCEPTION 'Comparison member count/digest mismatch'; END IF;
          RETURN NULL;
        END; $$
    """))
    for table in ("brc_comparison_universe_definitions", "brc_comparison_universe_members"):
        op.execute(sa.text(f"CREATE CONSTRAINT TRIGGER trg_{table}_shape AFTER INSERT OR UPDATE OR DELETE ON {table} "
                           "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION brc_validate_comparison_members_v1()"))


def _episode_provenance() -> None:
    for column in (
        sa.Column("comparison_binding_digest", DIGEST, nullable=True),
        sa.Column("comparison_transition_revision", sa.BigInteger(), nullable=True),
        sa.Column("comparison_source_evidence_digest", DIGEST, nullable=True),
        sa.Column("comparison_armed_at_ms", sa.BigInteger(), nullable=True),
        sa.Column("comparison_last_observed_at_ms", sa.BigInteger(), nullable=True),
        sa.Column("comparison_last_detector_status", sa.String(32), nullable=True),
    ):
        op.add_column("brc_exposure_episode_current", column)
    op.create_check_constraint("ck_brc_episode_comparison_provenance_shape", "brc_exposure_episode_current",
        "COALESCE((comparison_binding_digest IS NULL AND comparison_transition_revision IS NULL "
        "AND comparison_source_evidence_digest IS NULL AND comparison_armed_at_ms IS NULL "
        "AND comparison_last_observed_at_ms IS NULL AND comparison_last_detector_status IS NULL) OR "
        "(comparison_binding_digest ~ '^sha256:[0-9a-f]{64}$' AND comparison_transition_revision >= 0 "
        "AND (comparison_transition_revision > 0 OR comparison_source_evidence_digest ~ '^sha256:[0-9a-f]{64}$')), false)")


def _bind_static_comparison(bind: sa.Connection) -> None:
    currents = bind.execute(sa.text("SELECT event_spec_id, universe_version_id FROM brc_strategy_universe_current "
        "WHERE event_spec_id IN ('event_spec:MPG-001:MPG-LONG:v3','event_spec:MI-001:MI-LONG:v3') "
        "ORDER BY event_spec_id")).mappings().all()
    for current in currents:
        members = tuple(bind.execute(sa.text("SELECT exchange_instrument_id FROM brc_strategy_universe_members "
            "WHERE universe_version_id=:id ORDER BY exchange_instrument_id"), {"id": current["universe_version_id"]}).scalars())
        payload = json.dumps({"exchange_instrument_ids": members}, sort_keys=True, separators=(",", ":")).encode()
        digest = "sha256:" + hashlib.sha256(payload).hexdigest()
        identity = "comparison:" + digest[7:]
        bind.execute(sa.text("INSERT INTO brc_comparison_universe_definitions VALUES(:id,:digest,:count) ON CONFLICT DO NOTHING"),
            {"id": identity, "digest": digest, "count": len(members)})
        for member in members:
            bind.execute(sa.text("INSERT INTO brc_comparison_universe_members VALUES(:id,:member) ON CONFLICT DO NOTHING"), {"id": identity,"member": member})
        bind.execute(sa.text("INSERT INTO brc_comparison_binding_current VALUES(:event,:id,0,:source)"),
            {"event": current["event_spec_id"],"id": identity,"source": current["universe_version_id"]})


def _authority_event_bindings(bind: sa.Connection) -> None:
    empty_payload = b'{"selected_exchange_instrument_ids":[]}'
    empty_digest = "sha256:" + hashlib.sha256(empty_payload).hexdigest()
    op.create_table(
        "brc_selection_authority_event_bindings",
        sa.Column("selection_authority_id", ID, nullable=False),
        sa.Column("event_spec_id", ID, nullable=False),
        sa.Column("position_side", sa.String(16), nullable=False),
        sa.Column("grant_state", sa.String(16), nullable=False),
        sa.Column("universe_version_id", ID, nullable=True),
        sa.Column("member_set_digest", DIGEST, nullable=False),
        sa.PrimaryKeyConstraint("selection_authority_id", "event_spec_id"),
        sa.ForeignKeyConstraint(["selection_authority_id"], ["brc_selection_session_authorities.selection_authority_id"]),
        sa.ForeignKeyConstraint(["event_spec_id"], ["brc_event_specs.event_spec_id"]),
        sa.ForeignKeyConstraint(["universe_version_id"], ["brc_strategy_universe_versions.universe_version_id"]),
        sa.CheckConstraint("position_side IN ('long','short')"),
        sa.CheckConstraint("member_set_digest ~ '^sha256:[0-9a-f]{64}$'"),
        sa.CheckConstraint("(grant_state='ACTIVE' AND universe_version_id IS NOT NULL "
            f"AND member_set_digest <> '{empty_digest}') OR (grant_state='EMPTY' AND universe_version_id IS NULL "
            f"AND member_set_digest = '{empty_digest}')"),
    )
    authorities = bind.execute(sa.text("SELECT * FROM brc_selection_session_authorities ORDER BY selection_authority_id")).mappings().all()
    for authority in authorities:
        events = bind.execute(sa.text("SELECT event_spec_id,position_side FROM brc_instrument_selection_spec_events "
            "WHERE selection_spec_id=:spec ORDER BY position_side"), {"spec": authority["selection_spec_id"]}).mappings().all()
        for event in events:
            universe = authority[f"authorized_{event['position_side']}_universe_version_id"]
            members = tuple(bind.execute(sa.text("SELECT exchange_instrument_id FROM brc_strategy_universe_members "
                "WHERE universe_version_id=:id ORDER BY exchange_instrument_id"), {"id": universe}).scalars()) if universe else ()
            digest = "sha256:" + hashlib.sha256(json.dumps({"selected_exchange_instrument_ids":members},sort_keys=True,separators=(",", ":")).encode()).hexdigest()
            bind.execute(sa.text("INSERT INTO brc_selection_authority_event_bindings VALUES(:aid,:event,:side,:state,:uid,:digest)"),
                {"aid":authority["selection_authority_id"],"event":event["event_spec_id"],"side":event["position_side"],
                 "state":"ACTIVE" if universe else "EMPTY","uid":universe,"digest":digest})
    op.drop_constraint("ck_brc_selection_session_authorities_grant_shape", "brc_selection_session_authorities", type_="check")
    op.drop_column("brc_selection_session_authorities", "authorized_long_universe_version_id")
    op.drop_column("brc_selection_session_authorities", "authorized_short_universe_version_id")
    op.create_check_constraint("ck_brc_selection_session_authorities_grant_shape", "brc_selection_session_authorities",
        "(authority_outcome IN ('PRE_FENCE_CONTINUITY','ACTIVE_NEW','NO_CHANGE','FALLBACK_PREVIOUS') "
        "AND first_eligible_close_time_ms IS NOT NULL AND first_eligible_close_time_ms % 900000=0 "
        "AND first_eligible_close_time_ms>created_at_ms AND first_eligible_close_time_ms<expires_at_ms "
        "AND grant_proof_kind IS NOT NULL) OR (authority_outcome IN ('VALID_EMPTY','OWNER_PAUSED_NOT_MATERIALIZED') "
        "AND first_eligible_close_time_ms IS NULL AND grant_proof_kind IS NULL AND grant_predecessor_authority_id IS NULL)")
    op.execute(sa.text("""
        CREATE FUNCTION brc_validate_authority_event_bindings_v1() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE aid text; spec text; expected_count integer; actual_count integer; bad_count integer; trading boolean;
        BEGIN
          aid := COALESCE(NEW.selection_authority_id,OLD.selection_authority_id);
          SELECT selection_spec_id,authority_outcome IN ('PRE_FENCE_CONTINUITY','ACTIVE_NEW','NO_CHANGE','FALLBACK_PREVIOUS')
          INTO spec,trading FROM brc_selection_session_authorities WHERE selection_authority_id=aid;
          IF NOT FOUND THEN RETURN NULL; END IF;
          SELECT count(*) INTO expected_count FROM brc_instrument_selection_spec_events WHERE selection_spec_id=spec;
          SELECT count(*),count(*) FILTER (WHERE e.event_spec_id IS NULL OR
            (trading AND b.grant_state<>'ACTIVE') OR (NOT trading AND b.grant_state<>'EMPTY') OR
            (b.grant_state='ACTIVE' AND (u.event_spec_id IS DISTINCT FROM b.event_spec_id OR u.universe_version_id IS NULL
            OR b.member_set_digest <> (SELECT 'sha256:' || encode(sha256(convert_to(
              '{"selected_exchange_instrument_ids":[' || coalesce(string_agg(to_json(m.exchange_instrument_id)::text,',' ORDER BY m.exchange_instrument_id),'') || ']}','UTF8')),'hex')
              FROM brc_strategy_universe_members m WHERE m.universe_version_id=b.universe_version_id))))
          INTO actual_count,bad_count
          FROM brc_selection_authority_event_bindings b
          LEFT JOIN brc_instrument_selection_spec_events e ON e.selection_spec_id=spec AND e.event_spec_id=b.event_spec_id AND e.position_side=b.position_side
          LEFT JOIN brc_strategy_universe_versions u ON u.universe_version_id=b.universe_version_id
          WHERE b.selection_authority_id=aid;
          IF expected_count NOT BETWEEN 1 AND 2 OR expected_count<>actual_count OR bad_count<>0 THEN
            RAISE EXCEPTION 'Authority requires exact homogeneous Spec Event binding shape';
          END IF;
          RETURN NULL;
        END; $$
    """))
    for table in ("brc_selection_session_authorities", "brc_selection_authority_event_bindings"):
        op.execute(sa.text(f"CREATE CONSTRAINT TRIGGER trg_{table}_event_shape AFTER INSERT OR UPDATE OR DELETE ON {table} "
                           "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION brc_validate_authority_event_bindings_v1()"))
    op.execute(sa.text("CREATE TRIGGER trg_brc_selection_authority_event_bindings_immutable BEFORE UPDATE OR DELETE "
                       "ON brc_selection_authority_event_bindings FOR EACH ROW EXECUTE FUNCTION brc_reject_immutable_selection_fact_mutation()"))
