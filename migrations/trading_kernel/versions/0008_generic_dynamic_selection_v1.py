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
    _trusted_universe_member_limit()
    op.drop_index("uq_brc_strategy_universe_versions_current_digest",table_name="brc_strategy_universe_versions")
    op.execute(sa.text("CREATE UNIQUE INDEX uq_brc_strategy_universe_versions_current_digest "
        "ON brc_strategy_universe_versions(event_spec_id,semantic_digest,(lifecycle_state='active')) "
        "WHERE lifecycle_state IN ('warming','staged','active')"))
    _authority_snapshot_epoch()
    _generic_close_proof_function()
    _generic_normal_binding_guard()
    _generic_static_recovery_proof_function()
    _generic_recovered_activation_proof_function()
    _generic_static_recovery_commit_guard()
    _generic_recovered_activation_commit_guard()
    _grant_existing_owner_read_roles(bind)


def _grant_existing_owner_read_roles(bind: sa.Connection) -> None:
    """Preserve pre-provisioned Owner read surfaces across new 0008 tables."""
    tables = (
        "brc_generic_dynamic_selection_specs_v1",
        "brc_comparison_universe_definitions",
        "brc_comparison_universe_members",
        "brc_comparison_binding_current",
        "brc_selection_authority_event_bindings",
        "brc_materialization_generation_event_baselines",
        "brc_selection_rollback_baseline_events",
    )
    for role in ("brc_owner_console", "brc_owner_control"):
        if bind.scalar(sa.text(
            "SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=:role)"
        ), {"role":role}):
            bind.execute(sa.text(
                f"GRANT SELECT ON TABLE {', '.join(tables)} TO {role}"
            ))


def _generic_static_recovery_commit_guard() -> None:
    op.execute(sa.text("""
      CREATE FUNCTION brc_validate_static_recovery_commit() RETURNS trigger LANGUAGE plpgsql AS $$
      DECLARE a brc_selection_session_authorities%ROWTYPE; p jsonb; b jsonb;
        n integer; actual jsonb; expected jsonb; dynamic_recovery boolean;
      BEGIN
        SELECT * INTO a FROM brc_selection_session_authorities WHERE selection_authority_id=NEW.selection_authority_id;
        IF NOT FOUND OR a.recovery_grant_proof IS NULL OR a.authority_outcome='ACTIVE_NEW' THEN RETURN NULL; END IF;
        p:=a.recovery_grant_proof; b:=p->'event_binding';
        dynamic_recovery := a.selection_mode='dynamic_selection';
        IF NOT EXISTS (SELECT 1 FROM brc_selection_authority_current
          WHERE selection_spec_id=a.selection_spec_id AND selection_authority_id=a.selection_authority_id AND updated_at_ms=a.created_at_ms)
          OR NOT EXISTS (SELECT 1 FROM brc_strategy_selection_control_current
            WHERE strategy_group_id=p->>'strategy_group_id' AND selection_spec_id=a.selection_spec_id
              AND selection_mode=a.selection_mode
              AND selection_epoch_id IS NOT DISTINCT FROM CASE WHEN dynamic_recovery THEN a.selection_epoch_id ELSE NULL END
              AND pending_selection_mode IS NULL AND pending_effective_period_anchor_ms IS NULL AND pending_authorization_id IS NULL
              AND control_version=a.selection_control_version
              AND (dynamic_recovery OR updated_at_ms=a.created_at_ms))
          OR NOT EXISTS (SELECT 1 FROM brc_strategy_entry_controls_current
            WHERE strategy_group_id=p->>'strategy_group_id' AND entry_state='enabled' AND control_version=a.owner_control_version)
          OR NOT EXISTS (SELECT 1 FROM brc_strategy_entry_vacuums_current
            WHERE entry_vacuum_id=p->>'source_entry_vacuum_id' AND source_generation_id=a.materialization_generation_id
              AND state='RESOLVED_FALLBACK' AND fenced_at_ms=(p->>'vacuum_fenced_at_ms')::bigint
              AND drained_at_ms IS NOT NULL AND resolved_at_ms=a.created_at_ms)
          OR NOT EXISTS (SELECT 1 FROM brc_strategy_universe_materialization_generations
            WHERE materialization_generation_id=a.materialization_generation_id AND lifecycle_state='FAILED_CLOSED'
              AND selection_epoch_id=a.selection_epoch_id AND
              selection_control_version=a.selection_control_version-CASE WHEN dynamic_recovery THEN 0 ELSE 1 END)
          THEN
            IF dynamic_recovery THEN RAISE EXCEPTION 'Dynamic recovery requires atomic Control Vacuum Authority'; END IF;
            RAISE EXCEPTION 'Static recovery requires atomic Control Vacuum Authority';
          END IF;
        IF a.comparison_universe_id IS NOT NULL AND NOT EXISTS (
          SELECT 1 FROM brc_comparison_binding_current WHERE event_spec_id=b->>'event_spec_id'
            AND comparison_universe_id=a.comparison_universe_id AND comparison_transition_revision=a.comparison_transition_revision
            AND source_static_universe_version_id=b->>'universe_version_id') THEN
          RAISE EXCEPTION 'Static recovery requires unchanged comparison binding';
        END IF;
        SELECT count(*) INTO n FROM brc_selection_authority_event_bindings WHERE selection_authority_id=a.selection_authority_id;
        IF n<>1 OR NOT EXISTS (SELECT 1 FROM brc_selection_authority_event_bindings x
          JOIN brc_strategy_universe_current u ON u.event_spec_id=x.event_spec_id AND u.universe_version_id=x.universe_version_id
          JOIN brc_strategy_universe_versions v ON v.universe_version_id=x.universe_version_id
          WHERE x.selection_authority_id=a.selection_authority_id AND x.event_spec_id=b->>'event_spec_id'
            AND x.position_side=b->>'position_side' AND x.grant_state='ACTIVE' AND x.universe_version_id=b->>'universe_version_id'
            AND x.member_set_digest=b->>'member_set_digest' AND u.lifecycle_state='active' AND v.lifecycle_state='active') THEN
          RAISE EXCEPTION 'Static recovery requires exact previous Event binding'; END IF;
        SELECT jsonb_agg(jsonb_build_object('key',e.episode_domain_key,'rid',e.authority_recovery_id,
          'revision',e.authority_recovery_revision,'effective',e.authority_recovery_effective_from_ms,
          'first',e.authority_recovery_first_eligible_close_time_ms,'armed',e.authority_recovery_armed_at_ms,
          'observed',e.authority_recovery_last_observed_at_ms,'status',e.authority_recovery_last_detector_status,
          'version',e.authority_recovery_checkpoint_version) ORDER BY e.episode_domain_key COLLATE "C") INTO actual
          FROM jsonb_array_elements(p->'observation_cursors') c JOIN brc_exposure_episode_current e ON e.episode_domain_key=c->>'episode_domain_key';
        SELECT jsonb_agg(jsonb_build_object('key',c->>'episode_domain_key','rid',p->'recovery_close_plan'->>'recovery_id',
          'revision',(p->'recovery_close_plan'->>'recovery_revision')::bigint,'effective',a.created_at_ms,
          'first',a.first_eligible_close_time_ms,'armed',NULL,'observed',c->'last_observed_at_ms','status',NULL,
          'version',(c->>'authority_recovery_checkpoint_version')::bigint+1) ORDER BY c->>'episode_domain_key' COLLATE "C") INTO expected
          FROM jsonb_array_elements(p->'observation_cursors') c;
        IF actual IS DISTINCT FROM expected THEN RAISE EXCEPTION 'Static recovery requires complete pending rebase'; END IF;
        IF NOT EXISTS (SELECT 1 FROM brc_strategy_entry_vacuum_events WHERE entry_vacuum_id=p->>'source_entry_vacuum_id'
          AND event_type='RESOLVED_FALLBACK' AND payload->>'selection_authority_id'=a.selection_authority_id)
          OR NOT EXISTS (SELECT 1 FROM brc_strategy_universe_materialization_events WHERE materialization_generation_id=a.materialization_generation_id
          AND event_type=CASE WHEN dynamic_recovery THEN 'DYNAMIC_RECOVERY_COMMITTED' ELSE 'STATIC_RECOVERY_COMMITTED' END
          AND payload->>'selection_authority_id'=a.selection_authority_id) THEN
          RAISE EXCEPTION 'Generic recovery requires durable commit events'; END IF;
        RETURN NULL;
      END; $$
    """))
    for table in ("brc_selection_session_authorities", "brc_selection_authority_event_bindings"):
        op.execute(sa.text(f"CREATE CONSTRAINT TRIGGER trg_{table}_static_recovery AFTER INSERT ON {table} "
            "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION brc_validate_static_recovery_commit()"))


def _generic_recovered_activation_commit_guard() -> None:
    op.execute(sa.text("""
      CREATE FUNCTION brc_validate_recovered_activation_commit() RETURNS trigger LANGUAGE plpgsql AS $$
      DECLARE a brc_selection_session_authorities%ROWTYPE; p jsonb; b jsonb;
        actual jsonb; expected jsonb; n integer;
      BEGIN
        SELECT * INTO a FROM brc_selection_session_authorities WHERE selection_authority_id=NEW.selection_authority_id;
        IF NOT FOUND OR a.recovery_grant_proof IS NULL OR a.authority_outcome<>'ACTIVE_NEW' THEN RETURN NULL; END IF;
        p:=a.recovery_grant_proof; b:=p->'event_binding';
        IF NOT EXISTS (SELECT 1 FROM brc_selection_authority_current
          WHERE selection_spec_id=a.selection_spec_id AND selection_authority_id=a.selection_authority_id AND updated_at_ms=a.created_at_ms)
          OR NOT EXISTS (SELECT 1 FROM brc_strategy_selection_control_current
            WHERE strategy_group_id=p->>'strategy_group_id' AND selection_spec_id=a.selection_spec_id
              AND selection_mode='dynamic_selection' AND selection_epoch_id=a.selection_epoch_id
              AND pending_selection_mode IS NULL AND control_version=a.selection_control_version)
          OR NOT EXISTS (SELECT 1 FROM brc_strategy_entry_controls_current
            WHERE strategy_group_id=p->>'strategy_group_id' AND entry_state='enabled' AND control_version=a.owner_control_version)
          OR NOT EXISTS (SELECT 1 FROM brc_strategy_universe_materialization_generations g
            JOIN brc_strategy_entry_vacuums_current v ON v.source_generation_id=g.materialization_generation_id
            JOIN brc_strategy_universe_versions u ON u.materialization_generation_id=g.materialization_generation_id
            JOIN brc_strategy_universe_current current_u ON current_u.event_spec_id=u.event_spec_id AND current_u.universe_version_id=u.universe_version_id
            WHERE g.materialization_generation_id=a.materialization_generation_id AND g.lifecycle_state='ACTIVE'
              AND g.selection_snapshot_id=a.selection_snapshot_id AND g.selection_epoch_id=a.selection_epoch_id
              AND g.selection_control_version=a.selection_control_version
              AND g.activated_at_ms=a.created_at_ms AND g.terminal_at_ms=a.created_at_ms
              AND g.fenced_at_ms>v.fenced_at_ms AND v.entry_vacuum_id=p->>'source_entry_vacuum_id'
              AND v.fenced_at_ms=(p->>'vacuum_fenced_at_ms')::bigint
              AND v.state='RESOLVED_ACTIVE' AND v.drained_at_ms IS NOT NULL AND v.resolved_at_ms=a.created_at_ms
              AND u.universe_version_id=b->>'universe_version_id' AND u.lifecycle_state='active'
              AND u.activated_at_ms=a.created_at_ms AND current_u.lifecycle_state='active')
          THEN RAISE EXCEPTION 'Recovered activation requires atomic Generation Universe Vacuum Authority'; END IF;
        IF EXISTS (SELECT 1 FROM brc_materialization_generation_event_baselines prior
          JOIN brc_strategy_universe_versions old_u ON old_u.universe_version_id=prior.universe_version_id
          WHERE prior.materialization_generation_id=a.materialization_generation_id AND prior.grant_state='ACTIVE'
            AND old_u.lifecycle_state<>'retired') THEN
          RAISE EXCEPTION 'Recovered activation must retire previous Universe'; END IF;
        SELECT count(*) INTO n FROM brc_selection_authority_event_bindings WHERE selection_authority_id=a.selection_authority_id;
        IF n<>1 OR NOT EXISTS (SELECT 1 FROM brc_selection_authority_event_bindings x
          WHERE x.selection_authority_id=a.selection_authority_id AND x.event_spec_id=b->>'event_spec_id'
            AND x.position_side=b->>'position_side' AND x.grant_state='ACTIVE'
            AND x.universe_version_id=b->>'universe_version_id' AND x.member_set_digest=b->>'member_set_digest') THEN
          RAISE EXCEPTION 'Recovered activation Event binding differs'; END IF;
        IF a.comparison_universe_id IS NOT NULL AND NOT EXISTS (
          SELECT 1 FROM brc_comparison_binding_current WHERE event_spec_id=b->>'event_spec_id'
            AND comparison_universe_id=a.comparison_universe_id AND comparison_transition_revision=a.comparison_transition_revision
            AND source_static_universe_version_id IS NULL) THEN
          RAISE EXCEPTION 'Recovered activation comparison changed'; END IF;
        SELECT jsonb_agg(jsonb_build_object('key',e.episode_domain_key,'rid',e.authority_recovery_id,
          'revision',e.authority_recovery_revision,'effective',e.authority_recovery_effective_from_ms,
          'first',e.authority_recovery_first_eligible_close_time_ms,'armed',e.authority_recovery_armed_at_ms,
          'observed',e.authority_recovery_last_observed_at_ms,'status',e.authority_recovery_last_detector_status,
          'version',e.authority_recovery_checkpoint_version) ORDER BY e.episode_domain_key COLLATE "C") INTO actual
          FROM jsonb_array_elements(p->'observation_cursors') c JOIN brc_exposure_episode_current e ON e.episode_domain_key=c->>'episode_domain_key';
        SELECT jsonb_agg(jsonb_build_object('key',c->>'episode_domain_key','rid',p->'recovery_close_plan'->>'recovery_id',
          'revision',(p->'recovery_close_plan'->>'recovery_revision')::bigint,'effective',a.created_at_ms,
          'first',a.first_eligible_close_time_ms,'armed',NULL,'observed',c->'last_observed_at_ms','status',NULL,
          'version',(c->>'authority_recovery_checkpoint_version')::bigint+1) ORDER BY c->>'episode_domain_key' COLLATE "C") INTO expected
          FROM jsonb_array_elements(p->'observation_cursors') c;
        IF actual IS DISTINCT FROM expected THEN RAISE EXCEPTION 'Recovered activation requires complete pending rebase'; END IF;
        IF NOT EXISTS (SELECT 1 FROM brc_strategy_entry_vacuum_events
          WHERE entry_vacuum_id=p->>'source_entry_vacuum_id' AND event_type='RESOLVED_ACTIVE'
            AND payload->>'materialization_generation_id'=a.materialization_generation_id)
          OR NOT EXISTS (SELECT 1 FROM brc_strategy_universe_materialization_events
            WHERE materialization_generation_id=a.materialization_generation_id AND event_type='ACTIVE'
              AND payload->>'selection_authority_id'=a.selection_authority_id) THEN
          RAISE EXCEPTION 'Recovered activation requires durable commit events'; END IF;
        RETURN NULL;
      END; $$
    """))
    for table in ("brc_selection_session_authorities", "brc_selection_authority_event_bindings"):
        op.execute(sa.text(f"CREATE CONSTRAINT TRIGGER trg_{table}_recovered_activation AFTER INSERT ON {table} "
            "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION brc_validate_recovered_activation_commit()"))


def _generic_static_recovery_proof_function() -> None:
    """Read-only proof check; this does not remove the closed recovery grant gate."""
    op.execute(sa.text("""
      CREATE FUNCTION brc_generic_static_recovery_proof_matches(p jsonb, checked_at bigint)
      RETURNS boolean LANGUAGE plpgsql STABLE AS $$
      DECLARE g brc_strategy_universe_materialization_generations%ROWTYPE;
        v brc_strategy_entry_vacuums_current%ROWTYPE;
        c brc_strategy_selection_control_current%ROWTYPE;
        o brc_strategy_entry_controls_current%ROWTYPE;
        a brc_owner_authorizations%ROWTYPE;
        b brc_materialization_generation_event_baselines%ROWTYPE;
        source_authority brc_selection_session_authorities%ROWTYPE;
        n integer; cadence integer; rank_limit integer; evaluated bigint; committed bigint;
        missed integer; dynamic_recovery boolean; freshness jsonb; source_id text;
        cutoff bigint; effective bigint; expiry bigint; first_close bigint;
        ids text; members_digest text; cursors jsonb; revision bigint;
        future_cursor boolean; failure jsonb; reason text; expected jsonb;
      BEGIN
        IF p IS NULL OR jsonb_typeof(p)<>'object' OR checked_at IS NULL THEN RETURN false; END IF;
        SELECT * INTO g FROM brc_strategy_universe_materialization_generations
          WHERE materialization_generation_id=p->>'materialization_generation_id';
        IF NOT FOUND OR g.selection_epoch_id='sor-v0' OR g.lifecycle_state<>'FAILED_CLOSED'
          OR g.selection_mode<>'dynamic_selection' OR g.rollback_baseline_id IS NOT NULL
          OR g.activated_at_ms IS NOT NULL OR g.fallback_at_ms IS NOT NULL
          OR g.fenced_at_ms IS NULL OR g.terminal_at_ms IS NULL THEN RETURN false; END IF;
        SELECT * INTO c FROM brc_strategy_selection_control_current WHERE strategy_group_id=g.strategy_group_id;
        IF NOT FOUND OR c.selection_spec_id<>g.selection_spec_id OR c.selection_epoch_id IS DISTINCT FROM g.selection_epoch_id
          OR c.control_version<>g.selection_control_version THEN RETURN false; END IF;
        dynamic_recovery := c.selection_mode='dynamic_selection';
        IF NOT dynamic_recovery AND (c.selection_mode<>'static_baseline'
          OR c.pending_selection_mode IS DISTINCT FROM 'dynamic_selection'
          OR c.pending_effective_period_anchor_ms IS DISTINCT FROM g.period_anchor_ms) THEN RETURN false; END IF;
        IF dynamic_recovery AND (c.pending_selection_mode IS NOT NULL OR c.pending_authorization_id IS NOT NULL
          OR c.pending_effective_period_anchor_ms IS NOT NULL) THEN RETURN false; END IF;
        SELECT * INTO o FROM brc_strategy_entry_controls_current WHERE strategy_group_id=g.strategy_group_id;
        IF NOT FOUND OR o.entry_state<>'enabled' THEN RETURN false; END IF;
        IF NOT dynamic_recovery THEN
          SELECT * INTO a FROM brc_owner_authorizations WHERE authorization_id=c.pending_authorization_id;
          IF NOT FOUND OR a.purpose<>'selection_mode_change' OR a.authentication_strength<>'totp_step_up'
            OR a.authorized_at_ms>g.created_at_ms OR a.target_scope<>jsonb_build_object(
              'strategy_group_id',g.strategy_group_id,'selection_spec_id',g.selection_spec_id,
              'selection_epoch_id',g.selection_epoch_id,'target_selection_mode','dynamic_selection',
              'effective_period_anchor_ms',g.period_anchor_ms) THEN RETURN false; END IF;
        ELSE
          SELECT x.* INTO source_authority FROM brc_selection_authority_current current_auth
            JOIN brc_selection_session_authorities x ON x.selection_authority_id=current_auth.selection_authority_id
            WHERE current_auth.selection_spec_id=g.selection_spec_id;
          IF NOT FOUND OR source_authority.selection_mode<>'dynamic_selection'
            OR source_authority.selection_epoch_id<>g.selection_epoch_id
            OR source_authority.selection_control_version<>c.control_version
            OR source_authority.owner_control_version<>o.control_version
            OR source_authority.membership_freshness IS NULL THEN RETURN false; END IF;
        END IF;
        SELECT * INTO v FROM brc_strategy_entry_vacuums_current WHERE entry_vacuum_id=p->>'source_entry_vacuum_id';
        IF NOT FOUND OR v.source_generation_id IS DISTINCT FROM g.materialization_generation_id
          OR v.strategy_group_id<>g.strategy_group_id OR v.selection_spec_id<>g.selection_spec_id
          OR v.state<>'RECONFIGURING' OR v.fenced_at_ms>g.fenced_at_ms
          OR v.drained_at_ms IS NULL OR v.resolved_at_ms IS NOT NULL THEN RETURN false; END IF;
        SELECT payload INTO failure FROM brc_strategy_entry_vacuum_events
          WHERE entry_vacuum_id=v.entry_vacuum_id AND event_type='RECOVERY_REQUIRED'
          ORDER BY event_sequence DESC LIMIT 1;
        IF failure IS NULL OR failure->>'source_generation_id' IS DISTINCT FROM g.materialization_generation_id
          OR failure->>'reason_code' IS DISTINCT FROM v.first_blocker THEN RETURN false; END IF;
        IF v.first_blocker NOT IN ('MATERIALIZATION_TIMEOUT','MATERIALIZATION_PERIOD_EXPIRED',
          'CERTIFICATION_OWNER_ACTION_REQUIRED','CERTIFICATION_NOT_ELIGIBLE') THEN RETURN false; END IF;
        IF (NOT dynamic_recovery AND EXISTS (SELECT 1 FROM brc_selection_authority_current WHERE selection_spec_id=g.selection_spec_id))
          OR EXISTS (SELECT 1 FROM brc_strategy_universe_versions WHERE materialization_generation_id=g.materialization_generation_id AND lifecycle_state<>'abandoned') THEN RETURN false; END IF;
        SELECT count(*) INTO n FROM brc_materialization_generation_event_baselines WHERE materialization_generation_id=g.materialization_generation_id;
        IF n<>1 THEN RETURN false; END IF;
        SELECT * INTO b FROM brc_materialization_generation_event_baselines WHERE materialization_generation_id=g.materialization_generation_id;
        IF b.grant_state<>'ACTIVE' OR NOT EXISTS (
          SELECT 1 FROM brc_strategy_universe_current u JOIN brc_strategy_universe_versions x USING(universe_version_id)
          WHERE u.event_spec_id=b.event_spec_id AND u.universe_version_id=b.universe_version_id
            AND u.lifecycle_state='active' AND x.lifecycle_state='active' AND u.semantic_digest=x.semantic_digest
            AND x.event_spec_id=b.event_spec_id AND x.strategy_group_id=g.strategy_group_id) THEN RETURN false; END IF;
        IF dynamic_recovery AND NOT EXISTS (SELECT 1 FROM brc_selection_authority_event_bindings sb
          WHERE sb.selection_authority_id=source_authority.selection_authority_id
            AND sb.event_spec_id=b.event_spec_id AND sb.position_side=b.position_side
            AND sb.universe_version_id=b.universe_version_id AND sb.member_set_digest=b.member_set_digest
            AND sb.grant_state='ACTIVE' AND source_authority.comparison_universe_id IS NOT DISTINCT FROM b.comparison_universe_id
            AND source_authority.comparison_transition_revision IS NOT DISTINCT FROM b.comparison_transition_revision) THEN RETURN false; END IF;
        IF NOT EXISTS (SELECT 1 FROM brc_runtime_scopes_current WHERE universe_version_id=b.universe_version_id)
          OR EXISTS (SELECT 1 FROM brc_runtime_scopes_current s JOIN brc_owner_policy_current q USING(owner_policy_id)
            WHERE s.universe_version_id=b.universe_version_id AND (NOT q.enabled OR NOT q.new_entry_submit_enabled)) THEN RETURN false; END IF;
        IF b.comparison_universe_id IS NOT NULL AND NOT EXISTS (
          SELECT 1 FROM brc_comparison_binding_current WHERE event_spec_id=b.event_spec_id
            AND comparison_universe_id=b.comparison_universe_id AND comparison_transition_revision=b.comparison_transition_revision
            AND source_static_universe_version_id=b.universe_version_id) THEN RETURN false; END IF;
        SELECT z.cadence_hours,z.retain_rank INTO cadence,rank_limit FROM brc_generic_dynamic_selection_specs_v1 z
          JOIN brc_instrument_selection_specs s USING(selection_spec_id)
          JOIN brc_instrument_selection_spec_events e USING(selection_spec_id)
          WHERE z.selection_spec_id=g.selection_spec_id AND s.status='active' AND s.selection_kind='generic_dynamic_v1'
            AND s.strategy_group_id=g.strategy_group_id
            AND e.event_spec_id=b.event_spec_id AND e.position_side=b.position_side;
        IF cadence IS NULL THEN RETURN false; END IF;
        evaluated := (p->'recovery_close_plan'->>'evaluated_at_ms')::bigint;
        committed := (p->>'committed_at_ms')::bigint;
        IF evaluated IS NULL OR committed IS NULL OR evaluated<g.terminal_at_ms
          OR evaluated<o.updated_at_ms OR evaluated<c.updated_at_ms
          OR evaluated<v.fenced_at_ms OR committed<evaluated OR checked_at<committed THEN RETURN false; END IF;
        IF EXISTS (SELECT 1 FROM brc_instrument_selection_snapshots s
          WHERE s.selection_spec_id=g.selection_spec_id AND s.selection_epoch_id=g.selection_epoch_id
            AND s.period_anchor_ms>g.period_anchor_ms AND s.created_at_ms<=checked_at
            AND s.eligibility_not_before_ms<=checked_at AND s.expires_at_ms>checked_at) THEN RETURN false; END IF;
        cutoff := ((evaluated-3600000)/(cadence*3600000::bigint))*(cadence*3600000::bigint);
        first_close := (evaluated/3600000+1)*3600000;
        IF first_close>=cutoff+(cadence+1)*3600000::bigint THEN cutoff:=cutoff+cadence*3600000::bigint; END IF;
        effective:=cutoff+3600000; expiry:=effective+cadence*3600000::bigint;
        first_close:=greatest(first_close,effective);
        IF evaluated<cutoff OR checked_at>=first_close OR first_close>=expiry THEN RETURN false; END IF;
        IF dynamic_recovery THEN
          freshness:=source_authority.membership_freshness;
          missed:=(effective-(freshness->>'source_snapshot_effective_at_ms')::bigint)/(cadence*3600000::bigint);
          IF missed NOT IN (0,1) OR freshness->>'source_member_set_digest' IS DISTINCT FROM b.member_set_digest
            OR (freshness->>'membership_valid_until_ms')::bigint<=first_close THEN RETURN false; END IF;
          freshness:=freshness || jsonb_build_object('consecutive_missed_periods',missed,
            'state',CASE WHEN missed=0 THEN 'ACTIVE' ELSE 'GRACE' END);
          source_id:=source_authority.selection_authority_id;
        END IF;
        WITH members AS (
          SELECT exchange_instrument_id,
            'episode-domain:' || encode(sha256(convert_to('{"event_spec_id":' || to_json(b.event_spec_id)::text ||
              ',"exchange_instrument_id":' || to_json(exchange_instrument_id)::text || ',"position_side":' ||
              to_json(b.position_side)::text || '}','UTF8')),'hex') AS domain_key
          FROM brc_strategy_universe_members WHERE universe_version_id=b.universe_version_id
        ) SELECT count(*),string_agg(to_json(m.exchange_instrument_id)::text,',' ORDER BY m.exchange_instrument_id COLLATE "C"),
          jsonb_agg(jsonb_build_object('episode_domain_key',m.domain_key,'exchange_instrument_id',m.exchange_instrument_id,
            'episode_version',coalesce(e.projection_version,0),'comparison_checkpoint_version',coalesce(e.comparison_checkpoint_version,0),
            'authority_recovery_checkpoint_version',coalesce(e.authority_recovery_checkpoint_version,0),
            'last_observed_at_ms',greatest(e.last_observed_at_ms,e.comparison_last_observed_at_ms,e.authority_recovery_last_observed_at_ms)) ORDER BY m.exchange_instrument_id COLLATE "C"),
          coalesce(max(e.authority_recovery_revision),0)+1,
          coalesce(bool_or(greatest(e.last_observed_at_ms,e.comparison_last_observed_at_ms,e.authority_recovery_last_observed_at_ms)>evaluated),false)
          INTO n,ids,cursors,revision,future_cursor FROM members m LEFT JOIN brc_exposure_episode_current e ON e.episode_domain_key=m.domain_key;
        IF n<1 OR n>(CASE WHEN dynamic_recovery THEN rank_limit ELSE 10 END) OR future_cursor THEN RETURN false; END IF;
        members_digest:='sha256:' || encode(sha256(convert_to('{"selected_exchange_instrument_ids":[' || ids || ']}','UTF8')),'hex');
        IF members_digest<>b.member_set_digest THEN RETURN false; END IF;
        reason:=CASE WHEN v.first_blocker IN ('MATERIALIZATION_TIMEOUT','MATERIALIZATION_PERIOD_EXPIRED') THEN 'MATERIALIZATION_TIMEOUT' ELSE 'MATERIALIZATION_FAILURE' END;
        expected:=jsonb_build_object('proof_kind','FUTURE_CLOSE_REBASE_REQUIRED',
          'authority_outcome','FALLBACK_PREVIOUS','target_snapshot_id',NULL,
          'selection_spec_id',g.selection_spec_id,'strategy_group_id',g.strategy_group_id,'selection_epoch_id',g.selection_epoch_id,
          'selection_mode',CASE WHEN dynamic_recovery THEN 'dynamic_selection' ELSE 'static_baseline' END,
          'source_entry_vacuum_id',v.entry_vacuum_id,'vacuum_fenced_at_ms',v.fenced_at_ms,
          'materialization_generation_id',g.materialization_generation_id,'source_selection_authority_id',source_id,
          'failed_activation_authorization_id',CASE WHEN dynamic_recovery THEN NULL ELSE a.authorization_id END,
          'owner_control_version',o.control_version,'selection_control_version',c.control_version+CASE WHEN dynamic_recovery THEN 0 ELSE 1 END,
          'event_binding',jsonb_build_object('event_spec_id',b.event_spec_id,'position_side',b.position_side,'grant_state','ACTIVE','universe_version_id',b.universe_version_id,'member_set_digest',members_digest),
          'recovery_close_plan',jsonb_build_object('recovery_id','recovery:' || encode(sha256(convert_to('{"entry_vacuum_id":' || to_json(v.entry_vacuum_id)::text || '}','UTF8')),'hex'),
            'recovery_revision',revision,'reason',reason,'period',jsonb_build_object('feature_cutoff_at_ms',cutoff,'cadence_hours',cadence,'scheduled_effective_at_ms',effective,'period_expires_at_ms',expiry),
            'evaluated_at_ms',evaluated,'status','FUTURE_CLOSE_REBASE_REQUIRED','first_eligible_close_time_ms',first_close,'episode_rebase_required',true),
          'membership_freshness',freshness,'comparison_universe_id',b.comparison_universe_id,'comparison_transition_revision',b.comparison_transition_revision,
          'observation_cursors',cursors,'committed_at_ms',committed,'episode_rebase_required',true);
        RETURN coalesce(p=expected,false);
      EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range THEN RETURN false;
      END; $$
    """))


def _generic_recovered_activation_proof_function() -> None:
    """Independently derive one staged target's future-close recovery proof."""
    op.execute(sa.text("""
      CREATE FUNCTION brc_generic_recovered_activation_proof_matches(p jsonb, checked_at bigint)
      RETURNS boolean LANGUAGE plpgsql STABLE AS $$
      DECLARE g brc_strategy_universe_materialization_generations%ROWTYPE;
        v brc_strategy_entry_vacuums_current%ROWTYPE;
        c brc_strategy_selection_control_current%ROWTYPE;
        o brc_strategy_entry_controls_current%ROWTYPE;
        s brc_instrument_selection_snapshots%ROWTYPE;
        t brc_strategy_universe_versions%ROWTYPE;
        oldg brc_strategy_universe_materialization_generations%ROWTYPE;
        src brc_selection_session_authorities%ROWTYPE;
        b brc_materialization_generation_event_baselines%ROWTYPE;
        cb brc_comparison_binding_current%ROWTYPE;
        old_event jsonb; failure jsonb; expected jsonb; cursors jsonb; freshness jsonb;
        cadence integer; n integer; missed integer; comparison_revision bigint; revision bigint;
        evaluated bigint; committed bigint; cutoff bigint; effective bigint; expiry bigint;
        first_close bigint; cadence_ms bigint; future_cursor boolean;
        target_digest text; comparison_id text; member_ids text; selected_ids text; comparison_ids text; reason text;
      BEGIN
        IF p IS NULL OR jsonb_typeof(p)<>'object' OR checked_at IS NULL
          OR p->>'authority_outcome'<>'ACTIVE_NEW' OR p->>'selection_mode'<>'dynamic_selection' THEN RETURN false; END IF;
        SELECT * INTO g FROM brc_strategy_universe_materialization_generations
          WHERE materialization_generation_id=p->>'materialization_generation_id';
        IF NOT FOUND OR g.selection_epoch_id='sor-v0' OR g.lifecycle_state<>'STAGED'
          OR g.fenced_at_ms IS NULL OR g.rollback_baseline_id IS NOT NULL THEN RETURN false; END IF;
        SELECT * INTO s FROM brc_instrument_selection_snapshots WHERE selection_snapshot_id=g.selection_snapshot_id;
        SELECT * INTO c FROM brc_strategy_selection_control_current WHERE strategy_group_id=g.strategy_group_id;
        SELECT * INTO o FROM brc_strategy_entry_controls_current WHERE strategy_group_id=g.strategy_group_id;
        SELECT z.cadence_hours INTO cadence FROM brc_generic_dynamic_selection_specs_v1 z
          JOIN brc_instrument_selection_specs spec USING(selection_spec_id)
          WHERE z.selection_spec_id=g.selection_spec_id AND spec.status='active' AND spec.selection_kind='generic_dynamic_v1';
        IF s.selection_snapshot_id IS NULL OR cadence IS NULL OR c.strategy_group_id IS NULL OR o.strategy_group_id IS NULL
          OR c.selection_mode<>'dynamic_selection' OR c.pending_selection_mode IS NOT NULL
          OR c.selection_spec_id<>g.selection_spec_id OR c.selection_epoch_id<>g.selection_epoch_id
          OR c.control_version<>g.selection_control_version OR o.entry_state<>'enabled'
          OR s.selection_epoch_id<>g.selection_epoch_id OR s.period_anchor_ms<>g.period_anchor_ms
          OR s.selected_count<>g.desired_member_count OR p->>'target_snapshot_id' IS DISTINCT FROM s.selection_snapshot_id
          THEN RETURN false; END IF;
        SELECT * INTO v FROM brc_strategy_entry_vacuums_current WHERE entry_vacuum_id=p->>'source_entry_vacuum_id';
        IF NOT FOUND OR v.source_generation_id<>g.materialization_generation_id OR v.state<>'RECONFIGURING'
          OR v.strategy_group_id<>g.strategy_group_id OR v.selection_spec_id<>g.selection_spec_id
          OR v.period_anchor_ms<>g.period_anchor_ms OR v.fenced_at_ms>=g.fenced_at_ms
          OR v.drained_at_ms IS NULL OR v.resolved_at_ms IS NOT NULL THEN RETURN false; END IF;
        SELECT payload INTO old_event FROM brc_strategy_entry_vacuum_events
          WHERE entry_vacuum_id=v.entry_vacuum_id AND event_type='SUPERSEDED'
          ORDER BY event_sequence DESC LIMIT 1;
        IF old_event IS NULL OR old_event->>'replacement_generation_id' IS DISTINCT FROM g.materialization_generation_id
          THEN RETURN false; END IF;
        SELECT * INTO oldg FROM brc_strategy_universe_materialization_generations
          WHERE materialization_generation_id=old_event->>'previous_generation_id';
        IF NOT FOUND OR oldg.lifecycle_state<>'FAILED_CLOSED' OR oldg.fenced_at_ms<>v.fenced_at_ms
          OR oldg.terminal_at_ms>g.created_at_ms OR oldg.selection_epoch_id<>g.selection_epoch_id THEN RETURN false; END IF;
        SELECT payload INTO failure FROM brc_strategy_universe_materialization_events
          WHERE materialization_generation_id=oldg.materialization_generation_id AND event_type='FAILED_CLOSED'
          ORDER BY event_sequence DESC LIMIT 1;
        IF failure IS NULL OR failure->>'entry_vacuum_id' IS DISTINCT FROM v.entry_vacuum_id
          OR failure->>'reason_code' IS NULL OR failure->>'reason_code' NOT IN ('MATERIALIZATION_TIMEOUT','MATERIALIZATION_PERIOD_EXPIRED',
            'CERTIFICATION_OWNER_ACTION_REQUIRED','CERTIFICATION_NOT_ELIGIBLE') THEN RETURN false; END IF;
        reason:=CASE WHEN failure->>'reason_code' IN ('MATERIALIZATION_TIMEOUT','MATERIALIZATION_PERIOD_EXPIRED')
          THEN 'MATERIALIZATION_TIMEOUT' ELSE 'MATERIALIZATION_FAILURE' END;
        SELECT * INTO b FROM brc_materialization_generation_event_baselines
          WHERE materialization_generation_id=g.materialization_generation_id;
        IF NOT FOUND OR (SELECT count(*) FROM brc_materialization_generation_event_baselines
          WHERE materialization_generation_id=g.materialization_generation_id)<>1 OR b.grant_state<>'ACTIVE'
          OR NOT EXISTS (SELECT 1 FROM brc_materialization_generation_event_baselines oldb
            WHERE oldb.materialization_generation_id=oldg.materialization_generation_id
              AND oldb.event_spec_id=b.event_spec_id AND oldb.position_side=b.position_side
              AND oldb.universe_version_id=b.universe_version_id AND oldb.member_set_digest=b.member_set_digest
              AND oldb.comparison_universe_id IS NOT DISTINCT FROM b.comparison_universe_id
              AND oldb.comparison_transition_revision IS NOT DISTINCT FROM b.comparison_transition_revision)
          THEN RETURN false; END IF;
        SELECT a.* INTO src FROM brc_selection_authority_current current_a
          JOIN brc_selection_session_authorities a ON a.selection_authority_id=current_a.selection_authority_id
          WHERE current_a.selection_spec_id=g.selection_spec_id;
        IF NOT FOUND OR src.selection_authority_id IS DISTINCT FROM p->>'source_selection_authority_id'
          OR src.selection_epoch_id<>g.selection_epoch_id OR src.selection_control_version<>c.control_version
          OR src.owner_control_version<>o.control_version OR src.comparison_universe_id IS DISTINCT FROM b.comparison_universe_id
          OR src.comparison_transition_revision IS DISTINCT FROM b.comparison_transition_revision
          OR NOT EXISTS (SELECT 1 FROM brc_selection_authority_event_bindings sb
            WHERE sb.selection_authority_id=src.selection_authority_id AND sb.event_spec_id=b.event_spec_id
              AND sb.position_side=b.position_side AND sb.universe_version_id=b.universe_version_id
              AND sb.member_set_digest=b.member_set_digest AND sb.grant_state='ACTIVE') THEN RETURN false; END IF;
        IF NOT EXISTS (SELECT 1 FROM brc_strategy_universe_current u
          JOIN brc_strategy_universe_versions x ON x.universe_version_id=u.universe_version_id
          WHERE u.event_spec_id=b.event_spec_id AND u.universe_version_id=b.universe_version_id
            AND u.lifecycle_state='active' AND x.lifecycle_state='active') THEN RETURN false; END IF;
        SELECT x.* INTO t FROM brc_strategy_universe_versions x WHERE x.materialization_generation_id=g.materialization_generation_id;
        IF NOT FOUND OR (SELECT count(*) FROM brc_strategy_universe_versions x
          WHERE x.materialization_generation_id=g.materialization_generation_id)<>1
          OR t.lifecycle_state<>'staged' OR t.event_spec_id<>b.event_spec_id OR t.strategy_group_id<>g.strategy_group_id
          THEN RETURN false; END IF;
        IF NOT EXISTS (SELECT 1 FROM brc_runtime_scopes_current scope
          JOIN brc_owner_policy_current policy USING(owner_policy_id)
          WHERE scope.universe_version_id=t.universe_version_id AND policy.enabled AND policy.new_entry_submit_enabled)
          OR EXISTS (SELECT 1 FROM brc_runtime_scopes_current scope
            JOIN brc_owner_policy_current policy USING(owner_policy_id)
            WHERE scope.universe_version_id=t.universe_version_id AND (NOT policy.enabled OR NOT policy.new_entry_submit_enabled))
          THEN RETURN false; END IF;
        SELECT count(*),string_agg(to_json(m.exchange_instrument_id)::text,',' ORDER BY m.exchange_instrument_id COLLATE "C")
          INTO n,member_ids FROM brc_strategy_universe_members m WHERE m.universe_version_id=t.universe_version_id;
        IF n<>s.selected_count OR n<1 OR n>16 THEN RETURN false; END IF;
        target_digest:='sha256:' || encode(sha256(convert_to('{"selected_exchange_instrument_ids":[' || member_ids || ']}','UTF8')),'hex');
        SELECT string_agg(to_json(exchange_instrument_id)::text,',' ORDER BY exchange_instrument_id COLLATE "C")
          INTO selected_ids FROM brc_instrument_selection_member_decisions
          WHERE selection_snapshot_id=s.selection_snapshot_id AND selected;
        IF selected_ids IS DISTINCT FROM member_ids THEN RETURN false; END IF;
        comparison_id:=NULL; comparison_revision:=NULL;
        IF g.strategy_group_id IN ('MPG-001','MI-001') THEN
          SELECT * INTO cb FROM brc_comparison_binding_current WHERE event_spec_id=b.event_spec_id;
          IF NOT FOUND OR cb.comparison_universe_id IS DISTINCT FROM b.comparison_universe_id
            OR cb.comparison_transition_revision IS DISTINCT FROM b.comparison_transition_revision THEN RETURN false; END IF;
          SELECT string_agg(to_json(exchange_instrument_id)::text,',' ORDER BY exchange_instrument_id COLLATE "C")
            INTO comparison_ids FROM brc_instrument_selection_spec_members WHERE selection_spec_id=g.selection_spec_id;
          comparison_id:='comparison:' || encode(sha256(convert_to('{"exchange_instrument_ids":[' || comparison_ids || ']}','UTF8')),'hex');
          comparison_revision:=cb.comparison_transition_revision+CASE WHEN cb.comparison_universe_id=comparison_id THEN 0 ELSE 1 END;
        ELSIF b.comparison_universe_id IS NOT NULL THEN RETURN false; END IF;
        evaluated:=(p->'recovery_close_plan'->>'evaluated_at_ms')::bigint;
        committed:=(p->>'committed_at_ms')::bigint;
        cadence_ms:=cadence*3600000::bigint;
        IF evaluated IS NULL OR committed IS NULL OR evaluated<g.fenced_at_ms OR evaluated<o.updated_at_ms
          OR evaluated<c.updated_at_ms OR committed<evaluated OR checked_at<committed OR committed>=g.fenced_at_ms+1800000
          OR NOT (s.eligibility_not_before_ms<=committed AND committed<s.expires_at_ms) THEN RETURN false; END IF;
        cutoff:=g.period_anchor_ms;
        effective:=cutoff+3600000; expiry:=effective+cadence_ms;
        first_close:=greatest(effective,(evaluated/3600000+1)*3600000);
        IF first_close>=expiry THEN
          cutoff:=cutoff+cadence_ms; effective:=cutoff+3600000; expiry:=effective+cadence_ms;
          first_close:=greatest(effective,(evaluated/3600000+1)*3600000);
        END IF;
        missed:=(effective-s.eligibility_not_before_ms)/cadence_ms;
        IF evaluated<cutoff OR checked_at>=first_close OR first_close>=expiry OR missed NOT IN (0,1)
          OR first_close>=s.eligibility_not_before_ms+2*cadence_ms THEN RETURN false; END IF;
        WITH members AS (SELECT exchange_instrument_id,
          'episode-domain:' || encode(sha256(convert_to('{"event_spec_id":' || to_json(b.event_spec_id)::text ||
            ',"exchange_instrument_id":' || to_json(exchange_instrument_id)::text || ',"position_side":' ||
            to_json(b.position_side)::text || '}','UTF8')),'hex') AS domain_key
          FROM brc_strategy_universe_members WHERE universe_version_id=t.universe_version_id)
        SELECT jsonb_agg(jsonb_build_object('episode_domain_key',m.domain_key,'exchange_instrument_id',m.exchange_instrument_id,
            'episode_version',coalesce(e.projection_version,0),'comparison_checkpoint_version',coalesce(e.comparison_checkpoint_version,0),
            'authority_recovery_checkpoint_version',coalesce(e.authority_recovery_checkpoint_version,0),
            'last_observed_at_ms',greatest(e.last_observed_at_ms,e.comparison_last_observed_at_ms,e.authority_recovery_last_observed_at_ms))
            ORDER BY m.exchange_instrument_id COLLATE "C"),
          coalesce(max(e.authority_recovery_revision),0)+1,
          coalesce(bool_or(greatest(e.last_observed_at_ms,e.comparison_last_observed_at_ms,e.authority_recovery_last_observed_at_ms)>evaluated),false)
          INTO cursors,revision,future_cursor FROM members m LEFT JOIN brc_exposure_episode_current e ON e.episode_domain_key=m.domain_key;
        IF future_cursor THEN RETURN false; END IF;
        freshness:=jsonb_build_object('source_snapshot_id',s.selection_snapshot_id,'source_member_set_digest',target_digest,
          'source_snapshot_cutoff_at_ms',s.period_anchor_ms,'source_snapshot_effective_at_ms',s.eligibility_not_before_ms,
          'cadence_hours',cadence,'membership_valid_until_ms',s.eligibility_not_before_ms+2*cadence_ms,
          'consecutive_missed_periods',missed,'state',CASE WHEN missed=0 THEN 'ACTIVE' ELSE 'GRACE' END);
        expected:=jsonb_build_object('proof_kind','FUTURE_CLOSE_REBASE_REQUIRED','authority_outcome','ACTIVE_NEW',
          'target_snapshot_id',s.selection_snapshot_id,'selection_spec_id',g.selection_spec_id,'strategy_group_id',g.strategy_group_id,
          'selection_epoch_id',g.selection_epoch_id,'selection_mode','dynamic_selection','source_entry_vacuum_id',v.entry_vacuum_id,
          'vacuum_fenced_at_ms',v.fenced_at_ms,'materialization_generation_id',g.materialization_generation_id,
          'source_selection_authority_id',src.selection_authority_id,'failed_activation_authorization_id',NULL,
          'owner_control_version',o.control_version,'selection_control_version',c.control_version,
          'event_binding',jsonb_build_object('event_spec_id',b.event_spec_id,'position_side',b.position_side,'grant_state','ACTIVE',
            'universe_version_id',t.universe_version_id,'member_set_digest',target_digest),
          'recovery_close_plan',jsonb_build_object('recovery_id','recovery:' || encode(sha256(convert_to(
              '{"entry_vacuum_id":' || to_json(v.entry_vacuum_id)::text || ',"materialization_generation_id":' ||
              to_json(g.materialization_generation_id)::text || '}','UTF8')),'hex'),
            'recovery_revision',revision,'reason',reason,'period',jsonb_build_object('feature_cutoff_at_ms',cutoff,
              'cadence_hours',cadence,'scheduled_effective_at_ms',effective,'period_expires_at_ms',expiry),
            'evaluated_at_ms',evaluated,'status','FUTURE_CLOSE_REBASE_REQUIRED','first_eligible_close_time_ms',first_close,
            'episode_rebase_required',true),
          'membership_freshness',freshness,'comparison_universe_id',comparison_id,'comparison_transition_revision',comparison_revision,
          'observation_cursors',cursors,'committed_at_ms',committed,'episode_rebase_required',true);
        RETURN coalesce(p=expected,false);
      EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range THEN RETURN false;
      END; $$
    """))


def _generic_normal_binding_guard() -> None:
    op.execute(sa.text("""
      CREATE FUNCTION brc_validate_generic_normal_binding() RETURNS trigger LANGUAGE plpgsql AS $$
      DECLARE a brc_selection_session_authorities%ROWTYPE; matches integer;
      BEGIN
        SELECT * INTO a FROM brc_selection_session_authorities WHERE selection_authority_id=NEW.selection_authority_id;
        IF NOT FOUND OR a.selection_epoch_id='sor-v0' THEN RETURN NULL; END IF;
        IF a.activation_authorization_id IS NOT NULL AND NOT EXISTS (
          SELECT 1 FROM brc_owner_authorizations o
            JOIN brc_instrument_selection_specs s ON s.selection_spec_id=a.selection_spec_id
            JOIN brc_strategy_selection_control_current c ON c.strategy_group_id=s.strategy_group_id
            JOIN brc_selection_authority_current p ON p.selection_spec_id=a.selection_spec_id
              AND p.selection_authority_id=a.selection_authority_id
          WHERE o.authorization_id=a.activation_authorization_id AND o.purpose='selection_mode_change'
            AND o.authentication_strength='totp_step_up' AND o.authorized_at_ms<=a.created_at_ms
            AND o.target_scope=jsonb_build_object('strategy_group_id',s.strategy_group_id,
              'selection_spec_id',a.selection_spec_id,'selection_epoch_id',a.selection_epoch_id,
              'target_selection_mode','dynamic_selection','effective_period_anchor_ms',a.period_anchor_ms)
            AND c.selection_spec_id=a.selection_spec_id AND c.selection_epoch_id=a.selection_epoch_id
            AND c.selection_mode='dynamic_selection' AND c.control_version=a.selection_control_version
            AND c.pending_selection_mode IS NULL AND c.pending_authorization_id IS NULL
            AND c.pending_effective_period_anchor_ms IS NULL AND c.updated_at_ms=a.effective_from_ms) THEN
          RAISE EXCEPTION 'Generic first activation requires atomic authorized mode transition';
        END IF;
        IF a.recovery_grant_proof IS NOT NULL OR a.authority_outcome NOT IN ('NO_CHANGE','ACTIVE_NEW') THEN RETURN NULL; END IF;
        SELECT count(*) INTO matches FROM brc_selection_authority_event_bindings b
          JOIN brc_strategy_universe_versions u ON u.universe_version_id=b.universe_version_id
          JOIN brc_strategy_universe_current c ON c.event_spec_id=b.event_spec_id AND c.universe_version_id=b.universe_version_id
          WHERE b.selection_authority_id=a.selection_authority_id AND b.grant_state='ACTIVE' AND u.lifecycle_state='active'
            AND c.lifecycle_state='active' AND c.semantic_digest=u.semantic_digest
            AND b.member_set_digest=a.membership_freshness->>'source_member_set_digest';
        IF matches<>1 THEN RAISE EXCEPTION 'Generic NO_CHANGE requires exact current active membership'; END IF;
        IF a.comparison_universe_id IS NOT NULL AND NOT EXISTS (
          SELECT 1 FROM brc_comparison_binding_current b JOIN brc_instrument_selection_spec_events e USING(event_spec_id)
          WHERE e.selection_spec_id=a.selection_spec_id AND b.comparison_universe_id=a.comparison_universe_id
            AND b.comparison_transition_revision=a.comparison_transition_revision) THEN
          RAISE EXCEPTION 'Generic normal Authority comparison changed before commit';
        END IF;
        IF a.authority_outcome='ACTIVE_NEW' THEN
          SELECT count(*) INTO matches FROM brc_strategy_universe_materialization_generations g
            JOIN brc_strategy_universe_versions u ON u.materialization_generation_id=g.materialization_generation_id
            JOIN brc_selection_authority_event_bindings b ON b.selection_authority_id=a.selection_authority_id AND b.universe_version_id=u.universe_version_id
            JOIN brc_strategy_entry_vacuums_current v ON v.source_generation_id=g.materialization_generation_id
            JOIN brc_selection_authority_current c ON c.selection_spec_id=a.selection_spec_id AND c.selection_authority_id=a.selection_authority_id
            WHERE g.materialization_generation_id=a.materialization_generation_id AND g.lifecycle_state='ACTIVE'
              AND g.selection_spec_id=a.selection_spec_id AND g.selection_snapshot_id=a.selection_snapshot_id
              AND g.selection_epoch_id=a.selection_epoch_id
              AND g.selection_control_version + CASE WHEN a.activation_authorization_id IS NULL THEN 0 ELSE 1 END = a.selection_control_version
              AND g.activated_at_ms=a.effective_from_ms AND g.terminal_at_ms=a.effective_from_ms
              AND u.lifecycle_state='active' AND u.activated_at_ms=a.effective_from_ms
              AND v.state='RESOLVED_ACTIVE' AND v.resolved_at_ms=a.effective_from_ms
              AND v.selection_spec_id=a.selection_spec_id AND v.strategy_group_id=g.strategy_group_id AND v.period_anchor_ms=a.period_anchor_ms
              AND g.fenced_at_ms=v.fenced_at_ms AND g.fenced_at_ms IS NOT NULL
              AND v.drained_at_ms IS NOT NULL AND v.drained_at_ms<=a.effective_from_ms;
          IF matches<>1 THEN RAISE EXCEPTION 'Generic ACTIVE_NEW requires atomic Generation Vacuum and current activation'; END IF;
          IF EXISTS (SELECT 1 FROM brc_materialization_generation_event_baselines b
            JOIN brc_strategy_universe_versions u ON u.universe_version_id=b.universe_version_id
            WHERE b.materialization_generation_id=a.materialization_generation_id AND b.grant_state='ACTIVE'
              AND u.lifecycle_state<>'retired') THEN
            RAISE EXCEPTION 'Generic ACTIVE_NEW previous baseline must be retired atomically';
          END IF;
        END IF;
        RETURN NULL;
      END; $$
    """))
    for table in ("brc_selection_session_authorities", "brc_selection_authority_event_bindings"):
        op.execute(sa.text(f"CREATE CONSTRAINT TRIGGER trg_{table}_generic_normal AFTER INSERT ON {table} "
            "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION brc_validate_generic_normal_binding()"))


def _generic_close_proof_function() -> None:
    op.execute(sa.text("""
      CREATE FUNCTION brc_generic_freshness_matches(snapshot_id text, freshness jsonb)
      RETURNS boolean LANGUAGE plpgsql STABLE AS $$
      DECLARE s brc_instrument_selection_snapshots%ROWTYPE; cadence integer; member_digest text; actual_count integer;
      BEGIN
        SELECT * INTO s FROM brc_instrument_selection_snapshots WHERE selection_snapshot_id=snapshot_id;
        IF NOT FOUND OR s.selection_family<>'generic_dynamic_v1' OR s.selected_count<=0 THEN RETURN false; END IF;
        SELECT cadence_hours INTO cadence FROM brc_generic_dynamic_selection_specs_v1 WHERE selection_spec_id=s.selection_spec_id;
        IF cadence IS NULL THEN RETURN false; END IF;
        SELECT count(*), 'sha256:' || encode(sha256(convert_to(
          '{"selected_exchange_instrument_ids":[' || coalesce(string_agg(to_json(exchange_instrument_id)::text,',' ORDER BY exchange_instrument_id COLLATE "C"),'') || ']}','UTF8')),'hex')
          INTO actual_count,member_digest FROM brc_instrument_selection_member_decisions
          WHERE selection_snapshot_id=snapshot_id AND selected;
        IF actual_count<>s.selected_count THEN RETURN false; END IF;
        RETURN coalesce(freshness=jsonb_build_object(
          'source_snapshot_id',snapshot_id,'source_member_set_digest',member_digest,
          'source_snapshot_cutoff_at_ms',s.feature_cutoff_at_ms,'source_snapshot_effective_at_ms',s.eligibility_not_before_ms,
          'cadence_hours',cadence,'membership_valid_until_ms',s.eligibility_not_before_ms+2*cadence*3600000::bigint,
          'consecutive_missed_periods',0,'state','ACTIVE'),false);
      END; $$
    """))
    op.execute(sa.text("""
      CREATE FUNCTION brc_generic_close_proof_matches(snapshot_id text, proof jsonb, granted_at bigint)
      RETURNS boolean LANGUAGE plpgsql STABLE AS $$
      DECLARE s brc_instrument_selection_snapshots%ROWTYPE; cadence integer;
        evt text; side text; c bigint; cursors jsonb; actual_count integer; consumed boolean;
      BEGIN
        SELECT * INTO s FROM brc_instrument_selection_snapshots WHERE selection_snapshot_id=snapshot_id;
        IF NOT FOUND OR s.selection_family<>'generic_dynamic_v1' OR s.selected_count<=0 OR granted_at IS NULL THEN RETURN false; END IF;
        SELECT g.cadence_hours,e.event_spec_id,e.position_side INTO cadence,evt,side
          FROM brc_generic_dynamic_selection_specs_v1 g JOIN brc_instrument_selection_spec_events e USING(selection_spec_id)
          WHERE g.selection_spec_id=s.selection_spec_id;
        IF cadence IS NULL OR evt IS NULL THEN RETURN false; END IF;
        c := granted_at/3600000*3600000;
        IF granted_at<=c OR c<s.eligibility_not_before_ms OR granted_at>=s.expires_at_ms OR s.created_at_ms>=c THEN RETURN false; END IF;
        WITH selected AS (
          SELECT m.exchange_instrument_id,
            'episode-domain:' || encode(sha256(convert_to(
              '{"event_spec_id":' || to_json(evt)::text || ',"exchange_instrument_id":' || to_json(m.exchange_instrument_id)::text ||
              ',"position_side":' || to_json(side)::text || '}','UTF8')),'hex') AS domain_key
          FROM brc_instrument_selection_member_decisions m
          WHERE m.selection_snapshot_id=snapshot_id AND m.selected
        )
        SELECT count(*), jsonb_agg(jsonb_build_object(
            'episode_domain_key',m.domain_key,'exchange_instrument_id',m.exchange_instrument_id,
            'episode_version',coalesce(e.projection_version,0),
            'comparison_checkpoint_version',coalesce(e.comparison_checkpoint_version,0),
            'authority_recovery_checkpoint_version',coalesce(e.authority_recovery_checkpoint_version,0),
            'last_observed_at_ms',greatest(e.last_observed_at_ms,e.comparison_last_observed_at_ms,e.authority_recovery_last_observed_at_ms)) ORDER BY m.exchange_instrument_id COLLATE "C"),
            coalesce(bool_or(greatest(e.last_observed_at_ms,e.comparison_last_observed_at_ms,e.authority_recovery_last_observed_at_ms)>=c),false)
          INTO actual_count,cursors,consumed FROM selected m LEFT JOIN brc_exposure_episode_current e ON e.episode_domain_key=m.domain_key;
        IF actual_count<>s.selected_count OR consumed THEN RETURN false; END IF;
        RETURN coalesce(proof=jsonb_build_object(
          'selection_snapshot_id',snapshot_id,'selection_committed_at_ms',s.created_at_ms,
          'source_snapshot_cutoff_at_ms',s.feature_cutoff_at_ms,
          'period',jsonb_build_object('feature_cutoff_at_ms',s.feature_cutoff_at_ms,'cadence_hours',cadence,
            'scheduled_effective_at_ms',s.eligibility_not_before_ms,'period_expires_at_ms',s.expires_at_ms),
          'current_final_close_time_ms',c,'authority_granted_at_ms',granted_at,'observation_cursors',cursors),false);
      END; $$
    """))


def _authority_snapshot_epoch() -> None:
    table = "brc_selection_session_authorities"
    op.add_column(table, sa.Column("selection_epoch_id", ID, nullable=False, server_default="sor-v0"))
    op.add_column(table, sa.Column("selection_control_version", sa.BigInteger(), nullable=True))
    op.add_column(table, sa.Column("activation_authorization_id", ID, nullable=True))
    op.create_foreign_key("fk_brc_authority_activation_owner", table, "brc_owner_authorizations", ["activation_authorization_id"], ["authorization_id"])
    op.create_unique_constraint("uq_brc_authority_activation_owner", table, ["activation_authorization_id"])
    op.create_check_constraint("ck_brc_authority_activation_shape", table,
        "activation_authorization_id IS NULL OR (selection_epoch_id<>'sor-v0' AND authority_outcome IN ('ACTIVE_NEW','NO_CHANGE','VALID_EMPTY'))")
    op.add_column(table, sa.Column("current_close_proof", sa.dialects.postgresql.JSONB(), nullable=True))
    op.add_column(table, sa.Column("recovery_grant_proof", sa.dialects.postgresql.JSONB(), nullable=True))
    op.create_check_constraint("ck_brc_recovery_grant_shape",table,
        "recovery_grant_proof IS NULL OR (jsonb_typeof(recovery_grant_proof)='object' AND "
        "selection_epoch_id<>'sor-v0' AND ((authority_outcome='FALLBACK_PREVIOUS' AND selection_mode IN ('static_baseline','dynamic_selection')) "
        "OR (authority_outcome='ACTIVE_NEW' AND selection_mode='dynamic_selection')))")
    op.add_column(table, sa.Column("membership_freshness", sa.dialects.postgresql.JSONB(), nullable=True))
    op.add_column(table, sa.Column("comparison_universe_id", ID, nullable=True))
    op.add_column(table, sa.Column("comparison_transition_revision", sa.BigInteger(), nullable=True))
    op.create_foreign_key("fk_brc_authority_comparison", table, "brc_comparison_universe_definitions",
        ["comparison_universe_id"], ["comparison_universe_id"])
    op.create_check_constraint("ck_brc_authority_generic_proof_shape", table,
        "(current_close_proof IS NULL OR jsonb_typeof(current_close_proof)='object') AND "
        "(membership_freshness IS NULL OR jsonb_typeof(membership_freshness)='object') AND "
        "((comparison_universe_id IS NULL AND comparison_transition_revision IS NULL) OR "
        "(comparison_universe_id IS NOT NULL AND comparison_transition_revision IS NOT NULL AND comparison_transition_revision>=0))")
    op.create_unique_constraint("uq_brc_snapshot_spec_epoch", "brc_instrument_selection_snapshots",
        ["selection_snapshot_id", "selection_spec_id", "selection_epoch_id"])
    op.create_foreign_key("fk_brc_authority_snapshot_epoch", table, "brc_instrument_selection_snapshots",
        ["selection_snapshot_id", "selection_spec_id", "selection_epoch_id"],
        ["selection_snapshot_id", "selection_spec_id", "selection_epoch_id"])
    op.create_check_constraint("ck_brc_authority_epoch_shape", table,
        "(selection_epoch_id='sor-v0' AND selection_control_version IS NULL) OR "
        "(selection_epoch_id<>'sor-v0' AND length(trim(selection_epoch_id))>0 "
        "AND selection_control_version IS NOT NULL AND selection_control_version>0)")
    old_time = next(c["sqltext"] for c in sa.inspect(op.get_bind()).get_check_constraints(table)
        if c["name"] == "ck_brc_selection_session_authorities_time_valid")
    op.drop_constraint("ck_brc_selection_session_authorities_time_valid",table,type_="check")
    op.create_check_constraint("ck_brc_selection_session_authorities_time_valid",table,
        f"(selection_epoch_id='sor-v0' AND ({old_time})) OR "
        "(selection_epoch_id<>'sor-v0' AND authority_sequence>0 AND owner_control_version>0 "
        "AND period_anchor_ms>0 AND decision_boundary_ms=period_anchor_ms+3600000 "
        "AND effective_from_ms>=decision_boundary_ms AND created_at_ms<expires_at_ms "
        "AND ((recovery_grant_proof IS NULL AND created_at_ms=effective_from_ms) OR "
        "(recovery_grant_proof IS NOT NULL AND created_at_ms<=effective_from_ms AND created_at_ms>0)))")
    constraints = {c["name"]:c["sqltext"] for c in sa.inspect(op.get_bind()).get_check_constraints(table)}
    for suffix in ("proof_kind_valid","proof_shape","grant_shape","active_new_shape","fallback_shape"):
        name = "ck_brc_selection_session_authorities_"+suffix
        op.drop_constraint(name,table,type_="check")
        op.create_check_constraint(name,table,f"selection_epoch_id<>'sor-v0' OR COALESCE(({constraints[name]}),false)")
    op.create_check_constraint("ck_brc_generic_normal_grant_shape",table,
        "selection_epoch_id='sor-v0' OR recovery_grant_proof IS NOT NULL OR COALESCE(( "
        "(authority_outcome='VALID_EMPTY' AND first_eligible_close_time_ms IS NULL AND grant_proof_kind IS NULL "
        "AND grant_predecessor_authority_id IS NULL) OR "
        "(authority_outcome IN ('NO_CHANGE','ACTIVE_NEW') AND selection_mode='dynamic_selection' AND selection_snapshot_id IS NOT NULL "
        "AND ((authority_outcome='NO_CHANGE' AND materialization_generation_id IS NULL) OR "
        "(authority_outcome='ACTIVE_NEW' AND materialization_generation_id IS NOT NULL)) "
        "AND authority_gap_audit_id IS NULL "
        "AND ((continued_from_selection_authority_id IS NULL AND continuity_source_kind='NONE') OR "
        "(authority_outcome='NO_CHANGE' AND continued_from_selection_authority_id IS NOT NULL "
        "AND continuity_source_kind='SELECTION_AUTHORITY')) "
        "AND grant_predecessor_authority_id IS NULL "
        "AND grant_proof_kind='PRECOMMITTED_SELECTION_CURRENT_CLOSE' AND first_eligible_close_time_ms IS NOT NULL "
        "AND first_eligible_close_time_ms % 3600000=0 AND first_eligible_close_time_ms=created_at_ms/3600000*3600000 "
        "AND first_eligible_close_time_ms>=decision_boundary_ms AND first_eligible_close_time_ms<created_at_ms "
        "AND current_close_proof IS NOT NULL AND membership_freshness IS NOT NULL)),false)")
    op.execute(sa.text("""
        CREATE FUNCTION brc_validate_authority_epoch_v1() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE kind text; cadence integer; snapshot brc_instrument_selection_snapshots%ROWTYPE; p jsonb;
        BEGIN
          SELECT selection_kind INTO kind FROM brc_instrument_selection_specs WHERE selection_spec_id=NEW.selection_spec_id;
          IF kind='sor_dynamic_v0' AND (NEW.current_close_proof IS NOT NULL OR NEW.membership_freshness IS NOT NULL
              OR NEW.comparison_universe_id IS NOT NULL OR NEW.comparison_transition_revision IS NOT NULL) THEN
            RAISE EXCEPTION 'SOR Authority forbids Generic proof';
          END IF;
          IF kind='sor_dynamic_v0' AND NEW.selection_epoch_id<>'sor-v0' THEN
            RAISE EXCEPTION 'SOR Authority cannot carry Generic epoch';
          ELSIF kind='generic_dynamic_v1' AND NEW.selection_epoch_id='sor-v0' THEN
            RAISE EXCEPTION 'Generic Authority requires explicit epoch';
          END IF;
          IF kind='generic_dynamic_v1' THEN
            IF NEW.recovery_grant_proof IS NOT NULL THEN
              p:=NEW.recovery_grant_proof;
              IF p->>'authority_outcome'='ACTIVE_NEW' THEN
                IF NOT brc_generic_recovered_activation_proof_matches(p,NEW.created_at_ms)
                  OR NEW.selection_spec_id IS DISTINCT FROM p->>'selection_spec_id'
                  OR NEW.selection_epoch_id IS DISTINCT FROM p->>'selection_epoch_id'
                  OR NEW.selection_control_version IS DISTINCT FROM (p->>'selection_control_version')::bigint
                  OR NEW.owner_control_version IS DISTINCT FROM (p->>'owner_control_version')::bigint
                  OR NEW.created_at_ms IS DISTINCT FROM (p->>'committed_at_ms')::bigint
                  OR NEW.period_anchor_ms IS DISTINCT FROM (p->'recovery_close_plan'->'period'->>'feature_cutoff_at_ms')::bigint
                  OR NEW.decision_boundary_ms IS DISTINCT FROM (p->'recovery_close_plan'->'period'->>'scheduled_effective_at_ms')::bigint
                  OR NEW.effective_from_ms IS DISTINCT FROM greatest(NEW.created_at_ms,NEW.decision_boundary_ms)
                  OR NEW.expires_at_ms IS DISTINCT FROM least(
                    (p->'recovery_close_plan'->'period'->>'period_expires_at_ms')::bigint,
                    (p->'membership_freshness'->>'membership_valid_until_ms')::bigint)
                  OR NEW.first_eligible_close_time_ms IS DISTINCT FROM (p->'recovery_close_plan'->>'first_eligible_close_time_ms')::bigint
                  OR NEW.materialization_generation_id IS DISTINCT FROM p->>'materialization_generation_id'
                  OR NEW.comparison_universe_id IS DISTINCT FROM p->>'comparison_universe_id'
                  OR NEW.comparison_transition_revision IS DISTINCT FROM (p->>'comparison_transition_revision')::bigint
                  OR NEW.reason_code IS DISTINCT FROM p->'recovery_close_plan'->>'reason'
                  OR NEW.selection_mode<>'dynamic_selection' OR NEW.authority_outcome<>'ACTIVE_NEW'
                  OR NEW.continuity_source_kind<>'SELECTION_AUTHORITY'
                  OR NEW.grant_proof_kind<>'FUTURE_CLOSE_REBASE_REQUIRED'
                  OR NEW.selection_snapshot_id IS DISTINCT FROM p->>'target_snapshot_id'
                  OR NEW.selection_job_id IS NOT NULL OR NEW.selection_attempt_id IS NOT NULL
                  OR NEW.current_close_proof IS NOT NULL
                  OR NEW.membership_freshness IS DISTINCT FROM p->'membership_freshness'
                  OR NEW.activation_authorization_id IS NOT NULL OR NEW.authority_gap_audit_id IS NOT NULL
                  OR NEW.continued_from_selection_authority_id IS DISTINCT FROM p->>'source_selection_authority_id'
                  OR NEW.grant_predecessor_authority_id IS NOT NULL THEN
                  RAISE EXCEPTION 'Recovered activation proof differs from locked source facts';
                END IF;
                RETURN NEW;
              END IF;
              IF NOT brc_generic_static_recovery_proof_matches(p,NEW.created_at_ms) OR
                NEW.selection_spec_id IS DISTINCT FROM p->>'selection_spec_id' OR
                NEW.selection_epoch_id IS DISTINCT FROM p->>'selection_epoch_id' OR
                NEW.selection_control_version IS DISTINCT FROM (p->>'selection_control_version')::bigint OR
                NEW.owner_control_version IS DISTINCT FROM (p->>'owner_control_version')::bigint OR
                NEW.created_at_ms IS DISTINCT FROM (p->>'committed_at_ms')::bigint OR
                NEW.period_anchor_ms IS DISTINCT FROM (p->'recovery_close_plan'->'period'->>'feature_cutoff_at_ms')::bigint OR
                NEW.decision_boundary_ms IS DISTINCT FROM (p->'recovery_close_plan'->'period'->>'scheduled_effective_at_ms')::bigint OR
                NEW.effective_from_ms IS DISTINCT FROM greatest(NEW.created_at_ms,NEW.decision_boundary_ms) OR
                NEW.expires_at_ms IS DISTINCT FROM (p->'recovery_close_plan'->'period'->>'period_expires_at_ms')::bigint OR
                NEW.first_eligible_close_time_ms IS DISTINCT FROM (p->'recovery_close_plan'->>'first_eligible_close_time_ms')::bigint OR
                NEW.materialization_generation_id IS DISTINCT FROM p->>'materialization_generation_id' OR
                NEW.comparison_universe_id IS DISTINCT FROM p->>'comparison_universe_id' OR
                NEW.comparison_transition_revision IS DISTINCT FROM (p->>'comparison_transition_revision')::bigint OR
                NEW.reason_code IS DISTINCT FROM p->'recovery_close_plan'->>'reason' OR
                NEW.selection_mode IS DISTINCT FROM p->>'selection_mode' OR NEW.authority_outcome<>'FALLBACK_PREVIOUS' OR
                NEW.continuity_source_kind IS DISTINCT FROM (CASE WHEN NEW.selection_mode='static_baseline' THEN 'STATIC_BASELINE' ELSE 'SELECTION_AUTHORITY' END) OR
                NEW.grant_proof_kind IS DISTINCT FROM 'FUTURE_CLOSE_REBASE_REQUIRED' OR
                NEW.selection_snapshot_id IS DISTINCT FROM p->'membership_freshness'->>'source_snapshot_id' OR
                NEW.selection_job_id IS NOT NULL OR NEW.selection_attempt_id IS NOT NULL OR
                NEW.current_close_proof IS NOT NULL OR NEW.membership_freshness IS DISTINCT FROM nullif(p->'membership_freshness','null'::jsonb) OR
                NEW.activation_authorization_id IS NOT NULL OR NEW.authority_gap_audit_id IS NOT NULL OR
                NEW.continued_from_selection_authority_id IS DISTINCT FROM p->>'source_selection_authority_id'
                OR NEW.grant_predecessor_authority_id IS NOT NULL THEN
                IF NEW.selection_mode='static_baseline' THEN
                  RAISE EXCEPTION 'Static recovery proof differs from locked source facts';
                END IF;
                RAISE EXCEPTION 'Dynamic recovery proof differs from locked source facts';
              END IF;
              RETURN NEW;
            END IF;
            IF NEW.authority_outcome NOT IN ('VALID_EMPTY','NO_CHANGE','ACTIVE_NEW') THEN
              RAISE EXCEPTION 'Generic trading Authority proof contract is not installed';
            END IF;
            SELECT cadence_hours INTO cadence FROM brc_generic_dynamic_selection_specs_v1 WHERE selection_spec_id=NEW.selection_spec_id;
            IF cadence IS NULL OR NEW.period_anchor_ms % (cadence*3600000::bigint)<>0
                OR NEW.expires_at_ms<>NEW.decision_boundary_ms+cadence*3600000::bigint THEN
              RAISE EXCEPTION 'Generic Authority period differs from Spec';
            END IF;
            IF NEW.authority_outcome='VALID_EMPTY' THEN
              SELECT * INTO snapshot FROM brc_instrument_selection_snapshots WHERE selection_snapshot_id=NEW.selection_snapshot_id;
              IF NOT FOUND OR snapshot.selection_spec_id<>NEW.selection_spec_id OR snapshot.selection_epoch_id<>NEW.selection_epoch_id
                  OR snapshot.selected_count<>0 OR snapshot.period_anchor_ms<>NEW.period_anchor_ms OR snapshot.created_at_ms>NEW.created_at_ms
                  OR NEW.current_close_proof IS NOT NULL OR NEW.membership_freshness IS NOT NULL THEN
                RAISE EXCEPTION 'Generic VALID_EMPTY requires exact zero-member Snapshot and no trading proof';
              END IF;
            ELSE
              IF NEW.continued_from_selection_authority_id IS NOT NULL AND (
                NEW.authority_outcome<>'NO_CHANGE' OR NOT EXISTS (
                  SELECT 1 FROM brc_selection_session_authorities origin
                    JOIN brc_selection_authority_event_bindings origin_binding
                      ON origin_binding.selection_authority_id=origin.selection_authority_id
                    JOIN brc_selection_authority_current current_auth
                      ON current_auth.selection_spec_id=NEW.selection_spec_id
                    JOIN brc_selection_session_authorities source_auth
                      ON source_auth.selection_authority_id=current_auth.selection_authority_id
                  WHERE origin.selection_authority_id=NEW.continued_from_selection_authority_id
                    AND origin.recovery_grant_proof IS NOT NULL AND origin.selection_spec_id=NEW.selection_spec_id
                    AND origin.selection_epoch_id=NEW.selection_epoch_id
                    AND (source_auth.selection_authority_id=origin.selection_authority_id
                      OR source_auth.continued_from_selection_authority_id=origin.selection_authority_id)
                    AND source_auth.owner_control_version=NEW.owner_control_version
                    AND source_auth.comparison_universe_id IS NOT DISTINCT FROM NEW.comparison_universe_id
                    AND source_auth.comparison_transition_revision IS NOT DISTINCT FROM NEW.comparison_transition_revision
                    AND origin_binding.member_set_digest=NEW.membership_freshness->>'source_member_set_digest'
                    AND origin_binding.event_spec_id IN (
                      SELECT event_spec_id FROM brc_instrument_selection_spec_events WHERE selection_spec_id=NEW.selection_spec_id)
                )) THEN RAISE EXCEPTION 'Generic recovery successor origin differs'; END IF;
              SELECT * INTO snapshot FROM brc_instrument_selection_snapshots WHERE selection_snapshot_id=NEW.selection_snapshot_id;
              IF NOT FOUND OR snapshot.selection_spec_id<>NEW.selection_spec_id OR snapshot.selection_epoch_id<>NEW.selection_epoch_id
                  OR snapshot.period_anchor_ms<>NEW.period_anchor_ms
                  OR NOT brc_generic_close_proof_matches(NEW.selection_snapshot_id,NEW.current_close_proof,NEW.created_at_ms)
                  OR NOT brc_generic_freshness_matches(NEW.selection_snapshot_id,NEW.membership_freshness) THEN
                RAISE EXCEPTION 'Generic normal Authority proof differs from Snapshot';
              END IF;
              IF snapshot.strategy_group_id IN ('MPG-001','MI-001') THEN
                IF NOT EXISTS (SELECT 1 FROM brc_comparison_binding_current b
                    JOIN brc_comparison_universe_definitions d USING(comparison_universe_id)
                    JOIN brc_instrument_selection_spec_events e ON e.event_spec_id=b.event_spec_id
                    WHERE e.selection_spec_id=NEW.selection_spec_id AND b.comparison_universe_id=NEW.comparison_universe_id
                    AND b.comparison_transition_revision=NEW.comparison_transition_revision
                    AND b.comparison_transition_revision>0 AND b.source_static_universe_version_id IS NULL AND d.member_count=24) THEN
                  RAISE EXCEPTION 'Generic normal Authority comparison differs';
                END IF;
              ELSIF NEW.comparison_universe_id IS NOT NULL OR NEW.comparison_transition_revision IS NOT NULL THEN
                RAISE EXCEPTION 'Generic non-comparative Authority forbids comparison';
              END IF;
            END IF;
          END IF;
          RETURN NEW;
        END; $$
    """))
    op.execute(sa.text("CREATE TRIGGER trg_authority_epoch_v1 BEFORE INSERT ON brc_selection_session_authorities "
        "FOR EACH ROW EXECUTE FUNCTION brc_validate_authority_epoch_v1()"))


def downgrade() -> None:
    raise RuntimeError("0008_generic_dynamic_selection_v1 is fix-forward only")


def _trusted_universe_member_limit() -> None:
    op.execute(sa.text("""
      CREATE OR REPLACE FUNCTION brc_enforce_universe_member_limit() RETURNS trigger LANGUAGE plpgsql AS $$
      DECLARE identity_compatible boolean; u brc_strategy_universe_versions%ROWTYPE;
        g brc_strategy_universe_materialization_generations%ROWTYPE;
        spec brc_instrument_selection_specs%ROWTYPE; member_limit integer := 10;
      BEGIN
        SELECT * INTO u FROM brc_strategy_universe_versions WHERE universe_version_id=NEW.universe_version_id FOR UPDATE;
        SELECT i.venue_id='binance-usdm' AND i.asset_class IN ('crypto','equity')
          AND i.venue_symbol ~ '^[A-Z0-9]+USDT$' AND i.contract_kind='perpetual'
          AND i.exchange_instrument_id='binance-usdm'||chr(58)||i.venue_symbol||chr(58)||'perpetual'
          AND p.asset_class=i.asset_class AND p.status IN ('candidate','active')
          AND p.entry_session_policy<>'reference_only' AND p.product_family=c.product_family
          AND p.asset_class=c.asset_class AND p.contract_type=c.contract_type
          AND p.underlying_type=c.underlying_type AND p.margin_asset=c.margin_asset
        INTO identity_compatible FROM brc_instruments i JOIN brc_instrument_product_profiles p USING(exchange_instrument_id)
          JOIN brc_event_product_compatibility c ON c.event_spec_id=u.event_spec_id
          WHERE i.exchange_instrument_id=NEW.exchange_instrument_id;
        IF identity_compatible IS DISTINCT FROM true THEN
          RAISE EXCEPTION 'strategy universe member product compatibility mismatch' USING ERRCODE='23514',CONSTRAINT='ck_brc_universe_member_product';
        END IF;
        IF u.source_kind='dynamic_selection' THEN
          SELECT * INTO g FROM brc_strategy_universe_materialization_generations WHERE materialization_generation_id=u.materialization_generation_id;
          IF NOT FOUND OR g.selection_mode<>'dynamic_selection' OR g.strategy_group_id<>u.strategy_group_id THEN
            RAISE EXCEPTION 'Universe trusted Generation identity mismatch';
          END IF;
          SELECT s.* INTO spec FROM brc_instrument_selection_specs s JOIN brc_instrument_selection_spec_events e USING(selection_spec_id)
            WHERE s.selection_spec_id=g.selection_spec_id AND e.event_spec_id=u.event_spec_id AND s.status='active';
          IF NOT FOUND THEN RAISE EXCEPTION 'Universe trusted Spec identity mismatch'; END IF;
          IF spec.selection_kind='sor_dynamic_v0' THEN member_limit:=7;
          ELSIF spec.selection_kind='generic_dynamic_v1' THEN
            SELECT retain_rank INTO member_limit FROM brc_generic_dynamic_selection_specs_v1 WHERE selection_spec_id=spec.selection_spec_id;
          ELSE RAISE EXCEPTION 'Universe trusted Spec kind mismatch'; END IF;
          IF member_limit IS NULL OR member_limit>16 THEN RAISE EXCEPTION 'Universe trusted member limit unavailable'; END IF;
        END IF;
        IF (SELECT count(*) FROM brc_strategy_universe_members WHERE universe_version_id=NEW.universe_version_id)>=member_limit THEN
          RAISE EXCEPTION 'Universe trusted member limit exceeded: %',member_limit USING ERRCODE='23514',CONSTRAINT='ck_brc_universe_members_trusted_limit';
        END IF;
        RETURN NEW;
      END; $$
    """))


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
    op.add_column(generations, sa.Column("selection_epoch_id", ID, nullable=False, server_default="sor-v0"))
    op.add_column(generations, sa.Column("selection_control_version", sa.BigInteger(), nullable=True))
    op.add_column(generations, sa.Column("lease_epoch", sa.BigInteger(), nullable=False, server_default="0"))
    op.drop_constraint("uq_brc_strategy_universe_materialization_generation_period", generations, type_="unique")
    op.create_unique_constraint("uq_brc_strategy_universe_materialization_generation_period", generations,
        ["selection_spec_id", "selection_epoch_id", "period_anchor_ms", "selection_mode"])
    op.create_foreign_key("fk_brc_generation_snapshot_epoch", generations, "brc_instrument_selection_snapshots",
        ["selection_snapshot_id", "selection_spec_id", "selection_epoch_id", "period_anchor_ms"],
        ["selection_snapshot_id", "selection_spec_id", "selection_epoch_id", "period_anchor_ms"])
    op.create_check_constraint("ck_brc_generation_epoch_shape", generations,
        "lease_epoch>=0 AND ((selection_epoch_id='sor-v0' AND selection_control_version IS NULL) OR "
        "(selection_epoch_id<>'sor-v0' AND length(trim(selection_epoch_id))>0 AND selection_control_version IS NOT NULL AND selection_control_version>0))")
    op.create_index("uq_brc_generic_generation_actionable_group", generations, ["strategy_group_id"], unique=True,
        postgresql_where=sa.text("selection_epoch_id<>'sor-v0' AND lifecycle_state IN ('PENDING','DESIRED','DRAINING_ENTRY','MATERIALIZING','STAGED')"))
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
        sa.Column("comparison_transition_revision", sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint("materialization_generation_id", "event_spec_id"),
        sa.UniqueConstraint("materialization_generation_id", "position_side", name="uq_brc_generation_baseline_side"),
        sa.ForeignKeyConstraint(["materialization_generation_id"], [f"{generations}.materialization_generation_id"]),
        sa.ForeignKeyConstraint(["event_spec_id"], ["brc_event_specs.event_spec_id"]),
        sa.ForeignKeyConstraint(["universe_version_id"], ["brc_strategy_universe_versions.universe_version_id"]),
        sa.ForeignKeyConstraint(["comparison_universe_id"], ["brc_comparison_universe_definitions.comparison_universe_id"]),
        sa.CheckConstraint("position_side IN ('long','short')", name="ck_brc_generation_baseline_side"),
        sa.CheckConstraint("member_set_digest ~ '^sha256:[0-9a-f]{64}$'", name="ck_brc_generation_baseline_digest"),
        sa.CheckConstraint("(comparison_universe_id IS NULL AND comparison_transition_revision IS NULL) OR "
            "(comparison_universe_id IS NOT NULL AND comparison_transition_revision IS NOT NULL AND comparison_transition_revision>=0)",
            name="ck_brc_generation_baseline_comparison"),
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
              brc_selected_universe_member_digest_v1(u.universe_version_id),NULL,NULL
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
                spec brc_instrument_selection_specs%ROWTYPE; s brc_instrument_selection_snapshots%ROWTYPE;
                expected integer; actual integer; matching integer; states integer; target_digest text;
        BEGIN
          gid := NEW.materialization_generation_id;
          SELECT * INTO g FROM brc_strategy_universe_materialization_generations WHERE materialization_generation_id=gid;
          SELECT * INTO spec FROM brc_instrument_selection_specs WHERE selection_spec_id=g.selection_spec_id;
          IF g.strategy_group_id<>spec.strategy_group_id OR g.strategy_version_id<>spec.strategy_version_id
             OR (spec.selection_kind='sor_dynamic_v0' AND (g.selection_epoch_id<>'sor-v0' OR (g.selection_mode='dynamic_selection' AND g.desired_member_count>7)))
             OR (spec.selection_kind='generic_dynamic_v1' AND g.selection_epoch_id='sor-v0') THEN
            RAISE EXCEPTION 'Generation Spec identity or member limit mismatch';
          END IF;
          IF spec.selection_kind='generic_dynamic_v1' AND g.selection_mode='dynamic_selection' THEN
            SELECT * INTO s FROM brc_instrument_selection_snapshots WHERE selection_snapshot_id=g.selection_snapshot_id;
            IF NOT FOUND OR s.selection_spec_id<>g.selection_spec_id OR s.selection_epoch_id<>g.selection_epoch_id
               OR s.period_anchor_ms<>g.period_anchor_ms OR s.selected_count<>g.desired_member_count
               OR g.created_at_ms<s.eligibility_not_before_ms OR g.created_at_ms>=s.expires_at_ms THEN
              RAISE EXCEPTION 'Generation Snapshot epoch/period/count/time mismatch';
            END IF;
            SELECT 'sha256:' || encode(sha256(convert_to('{"selected_exchange_instrument_ids":[' ||
              coalesce(string_agg(to_json(exchange_instrument_id)::text,',' ORDER BY exchange_instrument_id COLLATE "C"),'') || ']}','UTF8')),'hex')
            INTO target_digest FROM brc_instrument_selection_member_decisions WHERE selection_snapshot_id=s.selection_snapshot_id AND selected;
            IF EXISTS(SELECT 1 FROM brc_strategy_universe_materialization_targets WHERE materialization_generation_id=gid AND expected_member_set_digest<>target_digest) THEN
              RAISE EXCEPTION 'Generation target digest differs from Snapshot';
            END IF;
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
              NEW.desired_member_count,NEW.semantic_digest,NEW.created_at_ms,NEW.selection_epoch_id,NEW.selection_control_version)
             IS DISTINCT FROM ROW(OLD.materialization_generation_id,OLD.selection_spec_id,OLD.strategy_group_id,OLD.strategy_version_id,
              OLD.selection_mode,OLD.selection_snapshot_id,OLD.rollback_baseline_id,OLD.period_anchor_ms,
              OLD.desired_member_count,OLD.semantic_digest,OLD.created_at_ms,OLD.selection_epoch_id,OLD.selection_control_version) THEN
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
    op.drop_constraint("ck_brc_instrument_selection_jobs_current_state_valid", jobs, type_="check")
    op.drop_constraint("ck_brc_instrument_selection_jobs_current_result_shape", jobs, type_="check")
    op.create_check_constraint("ck_brc_instrument_selection_jobs_current_state_valid", jobs,
        "state IN ('DUE', 'CLAIMED', 'SNAPSHOT_READY', 'SOURCE_FAILED', 'COMPUTE_FAILED', 'EXPIRED', 'SUPERSEDED')")
    op.create_check_constraint("ck_brc_instrument_selection_jobs_current_result_shape", jobs,
        "(state = 'SNAPSHOT_READY' AND selection_snapshot_id IS NOT NULL AND first_blocker IS NULL) OR "
        "(state IN ('SOURCE_FAILED', 'COMPUTE_FAILED', 'EXPIRED', 'SUPERSEDED') "
        "AND selection_snapshot_id IS NULL AND first_blocker IS NOT NULL) OR "
        "(state IN ('DUE', 'CLAIMED') AND selection_snapshot_id IS NULL)")
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
    op.create_check_constraint("ck_brc_instrument_selection_jobs_current_generic_terminal_state", jobs,
        "state NOT IN ('EXPIRED', 'SUPERSEDED') OR selection_epoch_id <> 'sor-v0'")
    op.create_unique_constraint("uq_brc_instrument_selection_jobs_current_period", jobs,
        ["selection_spec_id", "selection_epoch_id", "period_anchor_ms"])
    op.create_index("uq_brc_generic_selection_jobs_one_actionable_epoch", jobs,
        ["selection_spec_id", "selection_epoch_id"], unique=True,
        postgresql_where=sa.text("selection_epoch_id <> 'sor-v0' AND state IN ('DUE', 'CLAIMED')"))
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
          owner_proof brc_owner_authorizations%ROWTYPE;
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
          IF NEW.pending_selection_mode='dynamic_selection' THEN
            SELECT * INTO owner_proof FROM brc_owner_authorizations
              WHERE authorization_id=NEW.pending_authorization_id;
            IF NOT FOUND OR owner_proof.purpose<>'selection_mode_change'
               OR owner_proof.authentication_strength<>'totp_step_up'
               OR owner_proof.target_scope->>'strategy_group_id' IS DISTINCT FROM NEW.strategy_group_id
               OR owner_proof.target_scope->>'selection_spec_id' IS DISTINCT FROM NEW.selection_spec_id
               OR owner_proof.target_scope->>'target_selection_mode' IS DISTINCT FROM 'dynamic_selection'
               OR owner_proof.target_scope->>'effective_period_anchor_ms' IS DISTINCT FROM NEW.pending_effective_period_anchor_ms::text
               OR owner_proof.target_scope->>'selection_epoch_id' IS DISTINCT FROM NEW.selection_epoch_id THEN
              RAISE EXCEPTION 'Generic pending Owner epoch proof mismatch';
            END IF;
          END IF;
          IF TG_OP='UPDATE' AND OLD.selection_mode='static_baseline'
             AND NEW.selection_mode='dynamic_selection' THEN
            IF OLD.pending_selection_mode IS DISTINCT FROM 'dynamic_selection'
               OR OLD.pending_authorization_id IS NULL
               OR OLD.selection_epoch_id IS DISTINCT FROM NEW.selection_epoch_id
               OR NEW.pending_selection_mode IS NOT NULL
               OR NEW.pending_authorization_id IS NOT NULL
               OR NEW.pending_effective_period_anchor_ms IS NOT NULL
               OR NEW.control_version<>OLD.control_version+1 THEN
              RAISE EXCEPTION 'Generic activation requires pending Owner epoch';
            END IF;
          END IF;
          IF TG_OP='UPDATE' AND OLD.selection_mode='dynamic_selection'
             AND NEW.selection_mode='dynamic_selection'
             AND OLD.selection_epoch_id IS DISTINCT FROM NEW.selection_epoch_id THEN
            RAISE EXCEPTION 'Generic epoch rotation requires Static transition';
          END IF;
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
    op.add_column("brc_comparative_projection_current", sa.Column(
        "comparison_transition_revision", sa.BigInteger(), nullable=False, server_default="0",
    ))
    op.create_check_constraint("comparison_revision_valid", "brc_comparative_projection_current",
        "comparison_transition_revision >= 0")
    op.drop_index("ix_brc_comparative_projection_current_lookup", table_name="brc_comparative_projection_current")
    op.execute(sa.text("CREATE INDEX ix_brc_comparative_projection_current_lookup "
        "ON brc_comparative_projection_current(event_spec_id, member_set_digest, "
        "comparison_transition_revision, closed_bar_time_ms, projection_status, "
        "projection_version DESC, universe_version_id)"))
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
    columns: Sequence[sa.Column] = (
        sa.Column("comparison_binding_digest", DIGEST, nullable=True),
        sa.Column("comparison_transition_revision", sa.BigInteger(), nullable=True),
        sa.Column("comparison_source_evidence_digest", DIGEST, nullable=True),
        sa.Column("comparison_armed_at_ms", sa.BigInteger(), nullable=True),
        sa.Column("comparison_last_observed_at_ms", sa.BigInteger(), nullable=True),
        sa.Column("comparison_last_detector_status", sa.String(32), nullable=True),
        sa.Column("comparison_checkpoint_version", sa.BigInteger(), nullable=True),
        sa.Column("authority_recovery_id", ID, nullable=True),
        sa.Column("authority_recovery_revision", sa.BigInteger(), nullable=True),
        sa.Column("authority_recovery_effective_from_ms", sa.BigInteger(), nullable=True),
        sa.Column("authority_recovery_first_eligible_close_time_ms", sa.BigInteger(), nullable=True),
        sa.Column("authority_recovery_armed_at_ms", sa.BigInteger(), nullable=True),
        sa.Column("authority_recovery_last_observed_at_ms", sa.BigInteger(), nullable=True),
        sa.Column("authority_recovery_last_detector_status", sa.String(32), nullable=True),
        sa.Column("authority_recovery_checkpoint_version", sa.BigInteger(), nullable=True),
    )
    for column in columns:
        op.add_column("brc_exposure_episode_current", column)
    op.alter_column("brc_exposure_episode_current","last_observed_at_ms",existing_type=sa.BigInteger(),nullable=True)
    op.drop_constraint("ck_brc_episode_version_time","brc_exposure_episode_current",type_="check")
    op.create_check_constraint("version_and_observation_positive","brc_exposure_episode_current",
        "projection_version > 0 AND ((last_observed_at_ms IS NOT NULL AND last_observed_at_ms>0) OR "
        "(last_observed_at_ms IS NULL AND state='authority_rebase_required' AND authority_recovery_checkpoint_version IS NOT NULL "
        "AND authority_recovery_last_observed_at_ms IS NULL AND authority_recovery_last_detector_status IS NULL))")
    op.drop_constraint("ck_brc_episode_state", "brc_exposure_episode_current", type_="check")
    op.drop_constraint("ck_brc_episode_state_shape", "brc_exposure_episode_current", type_="check")
    op.create_check_constraint("state_valid", "brc_exposure_episode_current",
        "state IN ('armed', 'triggered', 'comparison_rebase_required', 'authority_rebase_required')")
    op.create_check_constraint("state_shape_valid", "brc_exposure_episode_current",
        "(state = 'triggered' AND exposure_episode_id IS NOT NULL AND triggered_at_ms IS NOT NULL AND triggered_at_ms > 0) OR "
        "(state = 'armed' AND exposure_episode_id IS NULL AND triggered_at_ms IS NULL) OR "
        "(state = 'comparison_rebase_required' AND exposure_episode_id IS NULL AND triggered_at_ms IS NULL "
        "AND rearmed_at_ms IS NULL AND comparison_checkpoint_version IS NOT NULL) OR "
        "(state = 'authority_rebase_required' AND exposure_episode_id IS NULL AND triggered_at_ms IS NULL "
        "AND rearmed_at_ms IS NULL AND authority_recovery_checkpoint_version IS NOT NULL AND authority_recovery_armed_at_ms IS NULL)")
    op.create_check_constraint("authority_recovery_checkpoint_shape", "brc_exposure_episode_current",
        "(authority_recovery_id IS NULL AND authority_recovery_revision IS NULL AND authority_recovery_effective_from_ms IS NULL "
        "AND authority_recovery_first_eligible_close_time_ms IS NULL AND authority_recovery_armed_at_ms IS NULL "
        "AND authority_recovery_last_observed_at_ms IS NULL AND authority_recovery_last_detector_status IS NULL "
        "AND authority_recovery_checkpoint_version IS NULL) OR COALESCE(("
        "length(trim(authority_recovery_id))>0 AND authority_recovery_id=trim(authority_recovery_id) "
        "AND authority_recovery_revision>0 AND authority_recovery_checkpoint_version>0 "
        "AND authority_recovery_effective_from_ms>0 AND authority_recovery_effective_from_ms<authority_recovery_first_eligible_close_time_ms "
        "AND authority_recovery_first_eligible_close_time_ms%3600000=0 "
        "AND event_spec_id IN ('event_spec:CPM-RO-001:CPM-LONG:v3','event_spec:MPG-001:MPG-LONG:v3',"
        "'event_spec:MI-001:MI-LONG:v3','event_spec:BRF2-001:BRF2-SHORT:v3') "
        "AND ((authority_recovery_armed_at_ms IS NULL AND authority_recovery_last_detector_status IS NULL AND "
        "(authority_recovery_last_observed_at_ms IS NULL OR (authority_recovery_last_observed_at_ms>0 AND "
        "authority_recovery_last_observed_at_ms<=authority_recovery_effective_from_ms AND authority_recovery_last_observed_at_ms%3600000=0))) OR "
        "(authority_recovery_first_eligible_close_time_ms<=authority_recovery_last_observed_at_ms AND authority_recovery_last_observed_at_ms%3600000=0 "
        "AND authority_recovery_last_detector_status IN ('triggered','not_triggered') AND "
        "((authority_recovery_armed_at_ms IS NULL AND authority_recovery_last_detector_status='triggered') OR "
        "(authority_recovery_armed_at_ms>=authority_recovery_first_eligible_close_time_ms "
        "AND authority_recovery_armed_at_ms<=authority_recovery_last_observed_at_ms AND authority_recovery_armed_at_ms%3600000=0 "
        "AND NOT (authority_recovery_last_detector_status='triggered' AND authority_recovery_armed_at_ms=authority_recovery_last_observed_at_ms)))))),false)")
    op.create_check_constraint("comparison_checkpoint_shape", "brc_exposure_episode_current",
        "comparison_checkpoint_version IS NULL OR COALESCE((comparison_checkpoint_version > 0 "
        "AND comparison_transition_revision > 0 AND comparison_last_observed_at_ms > 0 "
        "AND comparison_last_detector_status IN ('triggered', 'not_triggered') "
        "AND event_spec_id IN ('event_spec:MPG-001:MPG-LONG:v3','event_spec:MI-001:MI-LONG:v3') "
        "AND ((comparison_armed_at_ms IS NULL AND comparison_last_detector_status='triggered') OR "
        "(comparison_armed_at_ms > 0 AND comparison_armed_at_ms <= comparison_last_observed_at_ms))), false)")
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
