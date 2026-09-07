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
    proofs = certify_0007_static_comparison_sources_sync(bind)
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


def downgrade() -> None:
    raise RuntimeError("0008_generic_dynamic_selection_v1 is fix-forward only")


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
        "brc_strategy_selection_control_current, brc_strategy_universe_materialization_generations, "
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
