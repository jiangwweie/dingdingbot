"""Independent hourly ORB Spec family; flat forward authority extension."""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from src.trading_kernel.infrastructure.generic_selection_source_provenance import (
    count_nonquiescent_source_vacuums,
)

revision: str = '0011_orb_session_1h_v1'
down_revision: str | None = '0010_dynamic_intent_v1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind=op.get_bind()
    if bind.scalar(sa.text('SELECT version_num FROM alembic_version'))!=down_revision:
        raise RuntimeError('0011 requires exact 0010 source')
    predicates={
        'brc_trade_tickets':'active_netting_domain_key IS NOT NULL OR terminal_at_ms IS NULL',
        'brc_trade_aggregates':"status NOT IN ('terminal','leverage_rejected','entry_rejected','entry_reconciled_absent')",
        'brc_positions_current':'quantity<>0','brc_budget_reservations':"status='active'",
        'brc_exchange_commands':"status IN ('prepared','claimed','dispatch_started','outcome_unknown')",
        'brc_runtime_incidents':"status='open'",'brc_strategy_universe_versions':"lifecycle_state IN ('warming','staged')",
        'brc_strategy_universe_materialization_generations':"lifecycle_state IN ('PENDING','DESIRED','DRAINING_ENTRY','MATERIALIZING','STAGED')",
        'brc_owner_control_operations_current':"state NOT IN ('completed','blocked')"}
    bind.execute(sa.text('LOCK TABLE '+','.join(predicates)+',brc_strategy_selection_control_current,brc_owner_authorizations,brc_strategy_entry_vacuums_current IN SHARE ROW EXCLUSIVE MODE'))
    for table,predicate in predicates.items():
        if bind.scalar(sa.text(f'SELECT EXISTS(SELECT 1 FROM {table} WHERE {predicate})')):
            raise RuntimeError(f'0011 requires flat quiescent source: {table}')
    if count_nonquiescent_source_vacuums(bind):
        raise RuntimeError('0011 requires quiescent source Vacuums')
    op.drop_constraint('ck_brc_instrument_selection_specs_kind_valid','brc_instrument_selection_specs',type_='check')
    op.create_check_constraint('ck_brc_instrument_selection_specs_kind_valid','brc_instrument_selection_specs',
        "selection_kind IN ('sor_dynamic_v0','generic_dynamic_v1','orb_session_dynamic_v1')")
    op.create_table('brc_orb_session_selection_specs_v1',
        sa.Column('selection_spec_id',sa.String(200),primary_key=True),
        sa.Column('payload',sa.dialects.postgresql.JSONB(),nullable=False),
        sa.ForeignKeyConstraint(['selection_spec_id'],['brc_instrument_selection_specs.selection_spec_id']),
        sa.CheckConstraint("selection_spec_id='SOR_1H_OR_ATR_DYNAMIC_V1' AND payload->>'strategy_group_id'='SOR-1H-001' "
            "AND payload->>'selection_kind'='orb_session_dynamic_v1' AND payload->>'strategy_version_id'='sgv:SOR-1H-001:v1' "
            "AND (payload->>'selected_count_max')::int=7 AND (payload->>'input_window_bars')::int=96 "
            "AND (payload->>'entry_interval_ms')::bigint=3600000 AND (payload->>'materialization_timeout_ms')::bigint=1800000",
            name='ck_brc_orb_payload_identity'))
    op.execute(sa.text("CREATE TRIGGER trg_brc_orb_session_spec_immutable BEFORE UPDATE OR DELETE ON brc_orb_session_selection_specs_v1 "
        'FOR EACH ROW EXECUTE FUNCTION brc_reject_immutable_selection_fact_mutation()'))
    bind.exec_driver_sql('''CREATE FUNCTION brc_validate_orb_spec_v1() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE sid text; spec brc_instrument_selection_specs%ROWTYPE; p jsonb; members text[]; events text[];
    BEGIN
      sid:=COALESCE(NEW.selection_spec_id,OLD.selection_spec_id);
      SELECT * INTO spec FROM brc_instrument_selection_specs WHERE selection_spec_id=sid;
      IF NOT FOUND THEN RETURN NULL; END IF;
      SELECT payload INTO p FROM brc_orb_session_selection_specs_v1 WHERE selection_spec_id=sid;
      IF spec.selection_kind<>'orb_session_dynamic_v1' THEN
        IF p IS NOT NULL THEN RAISE EXCEPTION 'ORB payload cannot attach to another Spec family'; END IF;
        RETURN NULL;
      END IF;
      SELECT array_agg(exchange_instrument_id ORDER BY exchange_instrument_id COLLATE "C") INTO members
        FROM brc_instrument_selection_spec_members WHERE selection_spec_id=sid;
      SELECT array_agg(e.event_spec_id ORDER BY e.event_spec_id COLLATE "C") INTO events
        FROM brc_instrument_selection_spec_events e WHERE selection_spec_id=sid;
      IF sid<>'SOR_1H_OR_ATR_DYNAMIC_V1' OR spec.strategy_group_id<>'SOR-1H-001'
        OR spec.strategy_version_id<>'sgv:SOR-1H-001:v1' OR spec.selection_version<>1 OR p IS NULL
        OR p IS DISTINCT FROM '{"selection_spec_id":"SOR_1H_OR_ATR_DYNAMIC_V1","strategy_group_id":"SOR-1H-001","strategy_version_id":"sgv:SOR-1H-001:v1","selection_kind":"orb_session_dynamic_v1","event_spec_ids":["event_spec:SOR-1H-001:SOR-1H-LONG:v1","event_spec:SOR-1H-001:SOR-1H-SHORT:v1"],"candidate_ids":["binance-usdm:ADAUSDT:perpetual","binance-usdm:APTUSDT:perpetual","binance-usdm:ARBUSDT:perpetual","binance-usdm:ATOMUSDT:perpetual","binance-usdm:AVAXUSDT:perpetual","binance-usdm:BCHUSDT:perpetual","binance-usdm:BNBUSDT:perpetual","binance-usdm:BTCUSDT:perpetual","binance-usdm:DOGEUSDT:perpetual","binance-usdm:DOTUSDT:perpetual","binance-usdm:ETCUSDT:perpetual","binance-usdm:ETHUSDT:perpetual","binance-usdm:FILUSDT:perpetual","binance-usdm:INJUSDT:perpetual","binance-usdm:LINKUSDT:perpetual","binance-usdm:LTCUSDT:perpetual","binance-usdm:NEARUSDT:perpetual","binance-usdm:OPUSDT:perpetual","binance-usdm:RUNEUSDT:perpetual","binance-usdm:SOLUSDT:perpetual","binance-usdm:SUIUSDT:perpetual","binance-usdm:TRXUSDT:perpetual","binance-usdm:UNIUSDT:perpetual","binance-usdm:XRPUSDT:perpetual"],"selected_count_max":7,"near_count_max":7,"input_window_bars":96,"opening_range_bars":4,"pre_or_atr_bars":14,"activity_floor_quote_usdt":20000000,"decimal_precision":38,"decimal_rounding":"ROUND_HALF_EVEN","entry_interval_ms":3600000,"materialization_timeout_ms":1800000}'::jsonb
        OR spec.algorithm_semantic_digest<>'sha256:1e2ca19aadf543b9381b0f1af6da5ec5be8242f17eea857efd13944bce00355e'
        OR cardinality(members)<>24 OR to_jsonb(members) IS DISTINCT FROM p->'candidate_ids'
        OR events IS DISTINCT FROM ARRAY['event_spec:SOR-1H-001:SOR-1H-LONG:v1','event_spec:SOR-1H-001:SOR-1H-SHORT:v1']::text[]
        OR to_jsonb(events) IS DISTINCT FROM p->'event_spec_ids'
        OR EXISTS(SELECT 1 FROM brc_instrument_selection_spec_events b JOIN brc_event_specs e USING(event_spec_id)
          WHERE b.selection_spec_id=sid AND (e.strategy_version_id<>spec.strategy_version_id OR e.position_side<>b.position_side OR e.timeframe<>'1h'))
      THEN RAISE EXCEPTION 'ORB Spec requires its exact immutable Candidate24 and hourly LONG/SHORT binding'; END IF;
      RETURN NULL;
    END; $$''')
    for table in ('brc_instrument_selection_specs','brc_orb_session_selection_specs_v1','brc_instrument_selection_spec_members','brc_instrument_selection_spec_events'):
        op.execute(sa.text(f'CREATE CONSTRAINT TRIGGER trg_{table}_orb_shape AFTER INSERT OR UPDATE OR DELETE ON {table} '
            'DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION brc_validate_orb_spec_v1()'))
    _snapshot_family()
    _hourly_authority_family()
    _hourly_generation_guard()
    _hourly_owner_resume()
    _hourly_audit_ledger()
    op.execute(sa.text("""CREATE FUNCTION brc_lock_owner_orb_static_source() RETURNS void LANGUAGE plpgsql
      SECURITY DEFINER SET search_path=pg_catalog,public AS $$
    BEGIN
      IF NOT EXISTS(SELECT 1 FROM public.brc_strategy_selection_control_current c
        JOIN public.brc_instrument_selection_specs s ON s.selection_spec_id=c.selection_spec_id
        WHERE c.strategy_group_id='SOR-1H-001' AND c.selection_spec_id='SOR_1H_OR_ATR_DYNAMIC_V1'
          AND c.selection_mode='static_baseline' AND c.pending_selection_mode IS NULL
          AND s.selection_kind='orb_session_dynamic_v1' AND s.status='active') THEN
        RAISE EXCEPTION 'ORB Owner source lock requires exact Static control'; END IF;
      PERFORM 1 FROM public.brc_strategy_universe_current p
        JOIN public.brc_instrument_selection_spec_events e ON e.event_spec_id=p.event_spec_id
        WHERE e.selection_spec_id='SOR_1H_OR_ATR_DYNAMIC_V1' ORDER BY p.event_spec_id FOR UPDATE OF p;
    END; $$"""))
    op.execute(sa.text('REVOKE ALL ON FUNCTION brc_lock_owner_orb_static_source() FROM PUBLIC'))
    _replace_function('brc_enforce_universe_member_limit()',
        "IF spec.selection_kind='sor_dynamic_v0' THEN member_limit:=7;",
        "IF spec.selection_kind IN ('sor_dynamic_v0','orb_session_dynamic_v1') THEN member_limit:=7;")
    _replace_function("brc_validate_rollback_baseline_v1()",
        "IF b.strategy_group_id<>'SOR-001' THEN",
        "IF b.strategy_group_id='SOR-1H-001' AND (b.strategy_version_id<>'sgv:SOR-1H-001:v1' OR NOT EXISTS(SELECT 1 FROM brc_instrument_selection_specs WHERE strategy_group_id=b.strategy_group_id AND selection_kind='orb_session_dynamic_v1')) THEN RAISE EXCEPTION 'ORB baseline installed identity differs'; END IF;\n          IF b.strategy_group_id NOT IN ('SOR-001','SOR-1H-001') THEN")
    _replace_function("brc_validate_selection_job_epoch_v1()",
        "IF kind='sor_dynamic_v0' THEN",
        "IF kind='orb_session_dynamic_v1' THEN\n            IF NEW.selection_epoch_id='sor-v0' OR length(trim(NEW.selection_epoch_id))=0 OR NEW.period_anchor_ms%86400000<>0\n              OR NEW.feature_cutoff_at_ms<>NEW.period_anchor_ms+3600000 OR NEW.scheduled_at_ms<>NEW.feature_cutoff_at_ms\n              OR NEW.selection_spec_id<>'SOR_1H_OR_ATR_DYNAMIC_V1' OR NEW.selection_control_version IS NULL THEN\n              RAISE EXCEPTION 'ORB Job exact epoch/clock/control differs'; END IF;\n            RETURN NEW; END IF;\n          IF kind='sor_dynamic_v0' THEN")
    for role in ('brc_owner_console','brc_owner_control'):
        if bind.scalar(sa.text('SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=:role)'),{'role':role}):
            op.execute(sa.text(f'GRANT SELECT ON brc_orb_session_selection_specs_v1 TO {role}'))
            if role=='brc_owner_control':
                op.execute(sa.text('GRANT EXECUTE ON FUNCTION brc_lock_owner_orb_static_source() TO brc_owner_control'))



def _replace_function(signature: str, old: str, new: str) -> None:
    bind=op.get_bind()
    definition=bind.scalar(sa.text("SELECT pg_get_functiondef(to_regprocedure(:s))"),{"s":signature})
    if not isinstance(definition,str) or definition.count(old)!=1:
        raise RuntimeError("0011 exact source function differs: "+signature)
    bind.execute(sa.text(definition.replace(old,new)))


def _snapshot_family() -> None:
    bind=op.get_bind()
    for table in ("brc_instrument_selection_snapshots","brc_instrument_selection_member_decisions"):
        op.drop_constraint("ck_"+table+"_family",table,type_="check")
        op.create_check_constraint("ck_"+table+"_family",table,
            "selection_family IN ('sor_dynamic_v0','generic_dynamic_v1','orb_session_dynamic_v1')")
    table="brc_instrument_selection_member_decisions"
    constraints={c["name"]:c["sqltext"] for c in sa.inspect(bind).get_check_constraints(table)}
    name="ck_brc_selection_member_family_payload"
    expression=constraints[name].replace("= 'sor_dynamic_v0'::text", "= ANY (ARRAY['sor_dynamic_v0'::text,'orb_session_dynamic_v1'::text])")
    if expression==constraints[name]:
        raise RuntimeError("0011 member payload source differs")
    op.drop_constraint(name,table,type_="check");op.create_check_constraint(name,table,expression)
    for suffix in ("window_valid","numeric_valid","reason_valid","rank_shape"):
        name="ck_"+table+"_"+suffix
        expression=constraints[name].replace("<> 'sor_dynamic_v0'::text", "<> ALL (ARRAY['sor_dynamic_v0'::text,'orb_session_dynamic_v1'::text])")
        if expression==constraints[name]: raise RuntimeError("0011 member shape source differs")
        op.drop_constraint(name,table,type_="check");op.create_check_constraint(name,table,expression)
    op.execute(sa.text("""CREATE FUNCTION brc_validate_orb_snapshot_v1(sid text) RETURNS void LANGUAGE plpgsql AS $$
    DECLARE s brc_instrument_selection_snapshots%ROWTYPE; n integer; ready integer; selected_n integer;
    BEGIN
      SELECT * INTO s FROM brc_instrument_selection_snapshots WHERE selection_snapshot_id=sid;
      IF NOT FOUND OR s.selection_spec_id<>'SOR_1H_OR_ATR_DYNAMIC_V1' OR s.strategy_group_id<>'SOR-1H-001'
        OR s.strategy_version_id<>'sgv:SOR-1H-001:v1' OR s.selection_family<>'orb_session_dynamic_v1'
        OR s.selection_epoch_id='sor-v0' OR length(trim(s.selection_epoch_id))=0
        OR s.period_anchor_ms<=0 OR s.period_anchor_ms%86400000<>0
        OR s.feature_cutoff_at_ms<>s.period_anchor_ms+3600000 OR s.eligibility_not_before_ms<>s.period_anchor_ms+7200000
        OR s.expires_at_ms<>s.period_anchor_ms+90000000 OR s.decision_at_ms<s.feature_cutoff_at_ms
        OR s.source_observed_at_ms<s.decision_at_ms OR s.created_at_ms<s.source_observed_at_ms OR s.created_at_ms>=s.expires_at_ms
      THEN RAISE EXCEPTION 'ORB Snapshot exact identity/epoch/clock differs'; END IF;
      SELECT count(*),count(*) FILTER(WHERE selection_ready),count(*) FILTER(WHERE selected) INTO n,ready,selected_n
        FROM brc_instrument_selection_member_decisions WHERE selection_snapshot_id=sid;
      IF n<>24 OR s.candidate_count<>24 OR s.ready_count<>ready OR s.selected_count<>selected_n OR selected_n<>least(7,ready)
        OR EXISTS(SELECT 1 FROM brc_instrument_selection_member_decisions m WHERE m.selection_snapshot_id=sid AND (
          m.member_decision_id<>sid||':'||m.exchange_instrument_id OR m.selection_spec_id<>s.selection_spec_id
          OR m.selection_family<>s.selection_family OR m.period_anchor_ms<>s.period_anchor_ms
          OR m.feature_cutoff_at_ms<>s.feature_cutoff_at_ms OR m.input_window_start_ms<>s.period_anchor_ms-82800000
          OR m.input_window_end_ms<>s.feature_cutoff_at_ms OR NOT EXISTS(SELECT 1 FROM brc_instrument_selection_spec_members p
            WHERE p.selection_spec_id=s.selection_spec_id AND p.exchange_instrument_id=m.exchange_instrument_id)))
      THEN RAISE EXCEPTION 'ORB Snapshot requires exact complete Candidate24 decisions'; END IF;
      IF EXISTS(SELECT 1 FROM (SELECT stable_rank,row_number() OVER(ORDER BY pre_or_width_atr14, trailing_24h_quote_volume DESC, exchange_instrument_id COLLATE "C") AS expected
        FROM brc_instrument_selection_member_decisions WHERE selection_snapshot_id=sid AND selection_ready) ranked WHERE stable_rank<>expected)
      THEN RAISE EXCEPTION 'ORB Snapshot rank differs from frozen OR ATR order'; END IF;
    END; $$"""))
    _replace_function("brc_validate_typed_selection_snapshot_v1()",
        "IF s.selection_family='sor_dynamic_v0' THEN RETURN NULL; END IF;",
        "IF s.selection_family='orb_session_dynamic_v1' THEN PERFORM brc_validate_orb_snapshot_v1(s.selection_snapshot_id); RETURN NULL; END IF;\n          IF s.selection_family='sor_dynamic_v0' THEN RETURN NULL; END IF;")

def _hourly_authority_family() -> None:
    bind = op.get_bind()
    table = 'brc_selection_session_authorities'
    constraints = {c['name']: c['sqltext'] for c in sa.inspect(bind).get_check_constraints(table)}
    name = 'ck_brc_generic_normal_grant_shape'
    op.drop_constraint(name, table, type_='check')
    # The independent branch has its own fail-closed deferred validator below.
    op.create_check_constraint(name, table,
        "selection_spec_id='SOR_1H_OR_ATR_DYNAMIC_V1' OR ("+constraints[name]+")")
    op.create_check_constraint('ck_brc_orb_authority_clock', table,
        "selection_spec_id<>'SOR_1H_OR_ATR_DYNAMIC_V1' OR COALESCE(("
        "selection_epoch_id<>'sor-v0' AND period_anchor_ms%86400000=0 "
        "AND expires_at_ms=period_anchor_ms+86400000 AND effective_from_ms=created_at_ms "
        "AND current_close_proof IS NULL AND membership_freshness IS NULL "
        "AND recovery_grant_proof IS NULL AND comparison_universe_id IS NULL "
        "AND comparison_transition_revision IS NULL AND ("
        "(authority_outcome IN ('VALID_EMPTY','OWNER_PAUSED_NOT_MATERIALIZED') "
        "AND first_eligible_close_time_ms IS NULL AND grant_proof_kind IS NULL) OR "
        "(authority_outcome IN ('PRE_FENCE_CONTINUITY','ACTIVE_NEW','NO_CHANGE','FALLBACK_PREVIOUS') "
        "AND first_eligible_close_time_ms%3600000=0 AND first_eligible_close_time_ms>=period_anchor_ms+7200000 "
        "AND first_eligible_close_time_ms>created_at_ms AND first_eligible_close_time_ms<expires_at_ms "
        "AND grant_proof_kind IN ('CONTINUOUS_ELIGIBLE_CLOSES','AUDITED_AUTHORITY_GAP')))),false)")
    for signature in ('brc_validate_generic_normal_binding()', 'brc_validate_generic_continuity_commit()'):
        _replace_function(signature,
            "IF NOT FOUND OR a.selection_epoch_id='sor-v0'",
            "IF NOT FOUND OR a.selection_spec_id='SOR_1H_OR_ATR_DYNAMIC_V1' OR a.selection_epoch_id='sor-v0'")
    op.execute(sa.text("""CREATE FUNCTION brc_validate_orb_authority_commit() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE a brc_selection_session_authorities%ROWTYPE; c brc_strategy_selection_control_current%ROWTYPE;
      o brc_owner_authorizations%ROWTYPE; s brc_instrument_selection_snapshots%ROWTYPE; n integer;
    BEGIN
      SELECT * INTO a FROM brc_selection_session_authorities WHERE selection_authority_id=NEW.selection_authority_id;
      IF NOT FOUND OR a.selection_spec_id<>'SOR_1H_OR_ATR_DYNAMIC_V1' THEN RETURN NULL; END IF;
      SELECT * INTO c FROM brc_strategy_selection_control_current WHERE strategy_group_id='SOR-1H-001';
      IF NOT FOUND OR c.selection_spec_id<>a.selection_spec_id OR c.selection_epoch_id IS DISTINCT FROM a.selection_epoch_id
        OR c.control_version IS DISTINCT FROM a.selection_control_version THEN
        RAISE EXCEPTION 'ORB Authority requires exact current epoch/control'; END IF;
      IF NOT EXISTS(SELECT 1 FROM brc_selection_authority_current p WHERE p.selection_spec_id=a.selection_spec_id
        AND p.selection_authority_id=a.selection_authority_id AND p.updated_at_ms=a.created_at_ms) THEN
        RAISE EXCEPTION 'ORB Authority requires atomic current pointer'; END IF;
      IF NOT EXISTS(SELECT 1 FROM brc_strategy_entry_controls_current e WHERE e.strategy_group_id='SOR-1H-001'
        AND e.control_version=a.owner_control_version AND e.entry_state=CASE
          WHEN a.authority_outcome='OWNER_PAUSED_NOT_MATERIALIZED' THEN 'paused' ELSE 'enabled' END) THEN
        RAISE EXCEPTION 'ORB Authority Owner control differs'; END IF;
      IF a.activation_authorization_id IS NOT NULL THEN
        SELECT * INTO o FROM brc_owner_authorizations WHERE authorization_id=a.activation_authorization_id;
        IF NOT FOUND OR o.purpose<>'selection_mode_change' OR o.authentication_strength<>'totp_step_up'
          OR o.authorized_at_ms>a.created_at_ms OR o.target_scope->>'strategy_group_id'<>'SOR-1H-001'
          OR o.target_scope->>'selection_spec_id' IS DISTINCT FROM a.selection_spec_id
          OR o.target_scope->>'selection_epoch_id' IS DISTINCT FROM a.selection_epoch_id
          OR o.target_scope->>'target_selection_mode'<>'dynamic_selection'
          OR (o.target_scope->>'effective_period_anchor_ms')::bigint>a.period_anchor_ms
          OR c.selection_mode<>'dynamic_selection' OR c.pending_selection_mode IS NOT NULL
          OR c.pending_authorization_id IS NOT NULL OR c.pending_effective_period_anchor_ms IS NOT NULL
          OR c.updated_at_ms<>a.created_at_ms THEN
          RAISE EXCEPTION 'ORB first activation requires original Owner proof and atomic mode transition'; END IF;
      END IF;
      IF a.selection_snapshot_id IS NOT NULL THEN
        SELECT * INTO s FROM brc_instrument_selection_snapshots WHERE selection_snapshot_id=a.selection_snapshot_id;
        IF NOT FOUND OR s.selection_spec_id<>a.selection_spec_id OR s.selection_epoch_id<>a.selection_epoch_id
          OR s.period_anchor_ms<>a.period_anchor_ms OR s.created_at_ms>a.created_at_ms THEN
          RAISE EXCEPTION 'ORB Authority Snapshot source differs'; END IF;
      END IF;
      IF a.authority_outcome='NO_CHANGE' THEN
        IF a.selection_snapshot_id IS NULL OR s.selected_count=0 OR a.materialization_generation_id IS NOT NULL THEN
          RAISE EXCEPTION 'ORB NO_CHANGE requires nonempty Snapshot'; END IF;
        SELECT count(*) INTO n FROM brc_selection_authority_event_bindings b
          JOIN brc_strategy_universe_current p ON p.event_spec_id=b.event_spec_id AND p.universe_version_id=b.universe_version_id
          JOIN brc_strategy_universe_versions u ON u.universe_version_id=b.universe_version_id
          WHERE b.selection_authority_id=a.selection_authority_id AND b.grant_state='ACTIVE'
            AND p.lifecycle_state='active' AND u.lifecycle_state='active' AND p.semantic_digest=u.semantic_digest
            AND NOT EXISTS((SELECT exchange_instrument_id FROM brc_strategy_universe_members WHERE universe_version_id=b.universe_version_id)
              EXCEPT (SELECT exchange_instrument_id FROM brc_instrument_selection_member_decisions WHERE selection_snapshot_id=s.selection_snapshot_id AND selected))
            AND NOT EXISTS((SELECT exchange_instrument_id FROM brc_instrument_selection_member_decisions WHERE selection_snapshot_id=s.selection_snapshot_id AND selected)
              EXCEPT (SELECT exchange_instrument_id FROM brc_strategy_universe_members WHERE universe_version_id=b.universe_version_id));
        IF n<>2 THEN RAISE EXCEPTION 'ORB NO_CHANGE requires exact active hourly pair'; END IF;
        IF a.continuity_source_kind='STATIC_BASELINE' AND (a.activation_authorization_id IS NULL
          OR a.grant_proof_kind<>'CONTINUOUS_ELIGIBLE_CLOSES' OR a.authority_gap_audit_id IS NOT NULL) THEN
          RAISE EXCEPTION 'ORB Static NO_CHANGE requires activation proof'; END IF;
      ELSIF a.authority_outcome='ACTIVE_NEW' THEN
        IF a.selection_snapshot_id IS NULL OR s.selected_count=0 OR a.grant_proof_kind<>'AUDITED_AUTHORITY_GAP'
          OR a.continuity_source_kind<>'AUTHORITY_GAP_AUDIT' OR a.selection_mode<>'dynamic_selection' THEN
          RAISE EXCEPTION 'ORB ACTIVE_NEW requires audited nonempty Snapshot'; END IF;
        IF NOT EXISTS(SELECT 1 FROM brc_strategy_universe_materialization_generations g
          JOIN brc_strategy_entry_vacuums_current v ON v.source_generation_id=g.materialization_generation_id
          JOIN brc_selection_authority_gap_audits_current audit ON audit.source_generation_id=g.materialization_generation_id
            AND audit.source_entry_vacuum_id=v.entry_vacuum_id
          WHERE g.materialization_generation_id=a.materialization_generation_id
            AND g.selection_spec_id=a.selection_spec_id AND g.selection_epoch_id=a.selection_epoch_id
            AND g.selection_snapshot_id=a.selection_snapshot_id AND g.period_anchor_ms=a.period_anchor_ms
            AND g.lifecycle_state='ACTIVE' AND g.activated_at_ms=a.created_at_ms
            AND g.terminal_at_ms=a.created_at_ms AND g.desired_member_count=s.selected_count
            AND g.selection_control_version IN (a.selection_control_version,a.selection_control_version-1)
            AND v.state='RESOLVED_ACTIVE' AND v.drained_at_ms IS NOT NULL AND v.resolved_at_ms=a.created_at_ms
            AND audit.authority_gap_audit_id=a.authority_gap_audit_id AND audit.state='COMPLETE'
            AND audit.selection_spec_id=a.selection_spec_id AND audit.period_anchor_ms=a.period_anchor_ms
            AND audit.proposed_authority_outcome='ACTIVE_NEW' AND audit.gap_kind='ENTRY_VACUUM'
            AND audit.first_eligible_close_time_ms=a.first_eligible_close_time_ms
            AND audit.audited_through_close_time_ms+3600000=a.first_eligible_close_time_ms) THEN
          RAISE EXCEPTION 'ORB ACTIVE_NEW requires atomic Generation Vacuum and hourly audit'; END IF;
        SELECT count(*) INTO n FROM brc_selection_authority_event_bindings b
          JOIN brc_strategy_universe_current p ON p.event_spec_id=b.event_spec_id AND p.universe_version_id=b.universe_version_id
          JOIN brc_strategy_universe_versions u ON u.universe_version_id=b.universe_version_id
          WHERE b.selection_authority_id=a.selection_authority_id AND b.grant_state='ACTIVE'
            AND p.lifecycle_state='active' AND u.lifecycle_state='active' AND p.semantic_digest=u.semantic_digest
            AND u.materialization_generation_id=a.materialization_generation_id AND u.source_kind='dynamic_selection'
            AND u.activated_at_ms=a.created_at_ms
            AND NOT EXISTS((SELECT exchange_instrument_id FROM brc_strategy_universe_members WHERE universe_version_id=b.universe_version_id)
              EXCEPT (SELECT exchange_instrument_id FROM brc_instrument_selection_member_decisions WHERE selection_snapshot_id=s.selection_snapshot_id AND selected))
            AND NOT EXISTS((SELECT exchange_instrument_id FROM brc_instrument_selection_member_decisions WHERE selection_snapshot_id=s.selection_snapshot_id AND selected)
              EXCEPT (SELECT exchange_instrument_id FROM brc_strategy_universe_members WHERE universe_version_id=b.universe_version_id));
        IF n<>2 THEN RAISE EXCEPTION 'ORB ACTIVE_NEW requires exact activated hourly pair'; END IF;
        IF EXISTS(SELECT 1 FROM brc_materialization_generation_event_baselines b
          JOIN brc_strategy_universe_versions u ON u.universe_version_id=b.universe_version_id
          JOIN brc_runtime_scopes_current r ON r.universe_version_id=u.universe_version_id
          WHERE b.materialization_generation_id=a.materialization_generation_id
            AND (u.lifecycle_state<>'retired' OR r.lifecycle_state<>'retired'
              OR r.entry_enabled OR r.observation_enabled)) THEN
          RAISE EXCEPTION 'ORB ACTIVE_NEW retains previous writer'; END IF;
      ELSIF a.authority_outcome='FALLBACK_PREVIOUS' THEN
        IF a.selection_snapshot_id IS NULL OR a.grant_proof_kind<>'AUDITED_AUTHORITY_GAP'
          OR a.activation_authorization_id IS NOT NULL OR c.selection_mode<>a.selection_mode THEN
          RAISE EXCEPTION 'ORB fallback requires exact unchanged Owner intent'; END IF;
        IF NOT EXISTS(SELECT 1 FROM brc_strategy_universe_materialization_generations g
          JOIN brc_strategy_entry_vacuums_current v ON v.source_generation_id=g.materialization_generation_id
          JOIN brc_selection_authority_gap_audits_current audit ON audit.source_generation_id=g.materialization_generation_id
            AND audit.source_entry_vacuum_id=v.entry_vacuum_id
          WHERE g.materialization_generation_id=a.materialization_generation_id
            AND g.selection_spec_id=a.selection_spec_id AND g.selection_epoch_id=a.selection_epoch_id
            AND g.selection_snapshot_id=a.selection_snapshot_id AND g.period_anchor_ms=a.period_anchor_ms
            AND g.selection_control_version=a.selection_control_version AND g.lifecycle_state='FALLBACK_PREVIOUS'
            AND g.fallback_at_ms=a.created_at_ms AND g.terminal_at_ms=a.created_at_ms
            AND v.state='RESOLVED_FALLBACK' AND v.drained_at_ms IS NOT NULL AND v.resolved_at_ms=a.created_at_ms
            AND audit.authority_gap_audit_id=a.authority_gap_audit_id AND audit.state='COMPLETE'
            AND audit.selection_spec_id=a.selection_spec_id AND audit.period_anchor_ms=a.period_anchor_ms
            AND audit.proposed_authority_outcome='FALLBACK_PREVIOUS' AND audit.gap_kind='ENTRY_VACUUM'
            AND audit.first_eligible_close_time_ms=a.first_eligible_close_time_ms
            AND audit.audited_through_close_time_ms+3600000=a.first_eligible_close_time_ms) THEN
          RAISE EXCEPTION 'ORB fallback requires atomic previous recovery and hourly audit'; END IF;
        SELECT count(*) INTO n FROM brc_selection_authority_event_bindings b
          JOIN brc_materialization_generation_event_baselines baseline ON baseline.materialization_generation_id=a.materialization_generation_id
            AND baseline.event_spec_id=b.event_spec_id AND baseline.universe_version_id=b.universe_version_id
            AND baseline.member_set_digest=b.member_set_digest
          JOIN brc_strategy_universe_current p ON p.event_spec_id=b.event_spec_id AND p.universe_version_id=b.universe_version_id
          JOIN brc_strategy_universe_versions u ON u.universe_version_id=b.universe_version_id
          WHERE b.selection_authority_id=a.selection_authority_id AND b.grant_state='ACTIVE'
            AND p.lifecycle_state='active' AND u.lifecycle_state='active';
        IF n<>2 OR EXISTS(SELECT 1 FROM brc_strategy_universe_versions WHERE materialization_generation_id=a.materialization_generation_id
          AND lifecycle_state<>'abandoned') THEN RAISE EXCEPTION 'ORB fallback must restore actual previous pair and abandon targets'; END IF;
        IF a.selection_mode='static_baseline' AND (c.pending_selection_mode IS DISTINCT FROM 'dynamic_selection'
          OR c.pending_authorization_id IS NULL OR c.pending_effective_period_anchor_ms>a.period_anchor_ms
          OR a.continuity_source_kind<>'STATIC_BASELINE') THEN
          RAISE EXCEPTION 'ORB first failure must preserve pending Owner intent'; END IF;
      ELSIF a.authority_outcome='VALID_EMPTY' THEN
        IF a.selection_snapshot_id IS NULL OR s.selected_count<>0 OR a.first_eligible_close_time_ms IS NOT NULL
          OR a.materialization_generation_id IS NOT NULL OR a.grant_proof_kind IS NOT NULL
          OR a.continuity_source_kind<>'NONE' OR c.selection_mode<>'dynamic_selection' THEN
          RAISE EXCEPTION 'ORB VALID_EMPTY requires exact empty Snapshot and Dynamic mode'; END IF;
        IF NOT EXISTS(SELECT 1 FROM brc_strategy_entry_vacuums_current v WHERE v.selection_spec_id=a.selection_spec_id
          AND v.period_anchor_ms=a.period_anchor_ms AND v.state='VALID_EMPTY'
          AND v.drained_at_ms IS NOT NULL AND v.resolved_at_ms=a.created_at_ms) THEN
          RAISE EXCEPTION 'ORB VALID_EMPTY requires completed ENTRY drain'; END IF;
      ELSIF a.authority_outcome='PRE_FENCE_CONTINUITY' THEN
        IF c.selection_mode<>'dynamic_selection' OR a.selection_mode<>'dynamic_selection'
          OR a.activation_authorization_id IS NOT NULL OR a.materialization_generation_id IS NOT NULL
          OR a.selection_snapshot_id IS NOT NULL OR a.grant_proof_kind<>'AUDITED_AUTHORITY_GAP'
          OR a.continuity_source_kind<>'AUTHORITY_GAP_AUDIT' THEN
          RAISE EXCEPTION 'ORB continuity requires exact Dynamic hourly audit'; END IF;
        IF NOT EXISTS(SELECT 1 FROM brc_selection_authority_gap_audits_current audit
          WHERE audit.authority_gap_audit_id=a.authority_gap_audit_id AND audit.state='COMPLETE'
            AND audit.selection_spec_id=a.selection_spec_id AND audit.period_anchor_ms=a.period_anchor_ms
            AND audit.source_generation_id IS NULL AND audit.proposed_authority_outcome='PRE_FENCE_CONTINUITY'
            AND audit.first_eligible_close_time_ms=a.first_eligible_close_time_ms
            AND audit.audited_through_close_time_ms+3600000=a.first_eligible_close_time_ms) THEN
          RAISE EXCEPTION 'ORB continuity audit differs'; END IF;
        SELECT count(*) INTO n FROM brc_selection_authority_event_bindings b
          JOIN brc_strategy_universe_current p ON p.event_spec_id=b.event_spec_id AND p.universe_version_id=b.universe_version_id
          JOIN brc_strategy_universe_versions u ON u.universe_version_id=b.universe_version_id
          JOIN brc_selection_authority_event_bindings prior ON prior.selection_authority_id=a.continued_from_selection_authority_id
            AND prior.event_spec_id=b.event_spec_id AND prior.universe_version_id=b.universe_version_id
            AND prior.member_set_digest=b.member_set_digest
          JOIN brc_selection_session_authorities source ON source.selection_authority_id=prior.selection_authority_id
          WHERE b.selection_authority_id=a.selection_authority_id AND b.grant_state='ACTIVE'
            AND p.lifecycle_state='active' AND u.lifecycle_state='active'
            AND source.selection_spec_id=a.selection_spec_id AND source.selection_epoch_id=a.selection_epoch_id
            AND source.selection_control_version=a.selection_control_version AND (source.owner_control_version=a.owner_control_version
              OR EXISTS(SELECT 1 FROM brc_selection_authority_gap_audits_current audit
                JOIN brc_strategy_entry_vacuums_current v ON v.entry_vacuum_id=audit.source_entry_vacuum_id
                WHERE audit.authority_gap_audit_id=a.authority_gap_audit_id AND audit.gap_kind='OWNER_PAUSE'
                  AND v.state='RESOLVED_CONTINUITY' AND v.resolved_at_ms=a.created_at_ms
                  AND brc_orb_owner_resume_matches(v.entry_vacuum_id,a.created_at_ms)))
            AND source.authority_outcome IN ('ACTIVE_NEW','NO_CHANGE','PRE_FENCE_CONTINUITY','FALLBACK_PREVIOUS');
        IF n<>2 THEN RAISE EXCEPTION 'ORB continuity must retain actual authorized pair'; END IF;
      ELSIF a.authority_outcome='OWNER_PAUSED_NOT_MATERIALIZED' THEN
        IF a.first_eligible_close_time_ms IS NOT NULL OR a.grant_proof_kind IS NOT NULL
          OR a.activation_authorization_id IS NOT NULL OR a.continuity_source_kind<>'NONE'
          OR a.materialization_generation_id IS NOT NULL THEN
          RAISE EXCEPTION 'ORB paused outcome cannot grant ENTRY'; END IF;
        IF NOT EXISTS(SELECT 1 FROM brc_strategy_entry_vacuums_current v WHERE v.selection_spec_id=a.selection_spec_id
          AND v.strategy_group_id='SOR-1H-001' AND v.state IN ('OPEN','DRAINING_ENTRY','OWNER_PAUSED')
          AND v.first_blocker='OWNER_PAUSED') THEN RAISE EXCEPTION 'ORB pause requires negative fence'; END IF;
      ELSE
        RAISE EXCEPTION 'ORB Authority outcome is unsupported';
      END IF;
      RETURN NULL;
    END; $$"""))
    for target in (table, 'brc_selection_authority_event_bindings'):
        op.execute(sa.text(f'CREATE CONSTRAINT TRIGGER trg_{target}_orb_commit AFTER INSERT ON {target} '
            'DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION brc_validate_orb_authority_commit()'))


def _hourly_generation_guard() -> None:
    op.execute(sa.text("""CREATE FUNCTION brc_validate_orb_generation(gid text) RETURNS void LANGUAGE plpgsql AS $$
    DECLARE g brc_strategy_universe_materialization_generations%ROWTYPE;
      s brc_instrument_selection_snapshots%ROWTYPE; c brc_strategy_selection_control_current%ROWTYPE;
    BEGIN
      SELECT * INTO g FROM brc_strategy_universe_materialization_generations WHERE materialization_generation_id=gid;
      SELECT * INTO s FROM brc_instrument_selection_snapshots WHERE selection_snapshot_id=g.selection_snapshot_id;
      IF NOT FOUND OR g.selection_spec_id<>'SOR_1H_OR_ATR_DYNAMIC_V1' OR g.strategy_group_id<>'SOR-1H-001'
        OR g.strategy_version_id<>'sgv:SOR-1H-001:v1' OR g.selection_mode<>'dynamic_selection'
        OR g.selection_epoch_id='sor-v0' OR g.selection_control_version IS NULL
        OR s.selection_spec_id<>g.selection_spec_id OR s.selection_epoch_id<>g.selection_epoch_id
        OR s.period_anchor_ms<>g.period_anchor_ms OR s.selected_count<>g.desired_member_count
        OR g.desired_member_count NOT BETWEEN 1 AND 7 OR g.created_at_ms<s.created_at_ms
        OR g.created_at_ms<s.feature_cutoff_at_ms OR g.created_at_ms>=s.period_anchor_ms+82800000
        OR NOT EXISTS(SELECT 1 FROM brc_instrument_selection_jobs_current j
          JOIN brc_instrument_selection_attempts a ON a.selection_job_id=j.selection_job_id
          WHERE j.selection_snapshot_id=s.selection_snapshot_id AND j.state='SNAPSHOT_READY'
            AND j.selection_epoch_id=g.selection_epoch_id AND j.selection_control_version=g.selection_control_version
            AND a.outcome='SNAPSHOT_READY' AND a.source_member_count=24)
      THEN RAISE EXCEPTION 'ORB Generation requires exact committed Job Snapshot epoch and hourly source'; END IF;
      SELECT * INTO c FROM brc_strategy_selection_control_current WHERE strategy_group_id=g.strategy_group_id;
      IF NOT FOUND OR c.selection_spec_id<>g.selection_spec_id OR c.selection_epoch_id<>g.selection_epoch_id
        OR (c.control_version<>g.selection_control_version AND NOT (g.lifecycle_state='ACTIVE'
          AND c.control_version=g.selection_control_version+1 AND EXISTS(SELECT 1 FROM brc_selection_session_authorities a
            WHERE a.materialization_generation_id=gid AND a.activation_authorization_id IS NOT NULL
              AND a.selection_control_version=c.control_version))) THEN
        RAISE EXCEPTION 'ORB Generation current Owner epoch differs'; END IF;
      IF EXISTS(SELECT 1 FROM brc_strategy_universe_materialization_targets t WHERE t.materialization_generation_id=gid
        AND t.expected_member_set_digest<>(SELECT 'sha256:'||encode(sha256(convert_to(
          '{"selected_exchange_instrument_ids":['||coalesce(string_agg(to_json(m.exchange_instrument_id)::text,',' ORDER BY m.exchange_instrument_id COLLATE "C"),'')||']}','UTF8')),'hex')
          FROM brc_instrument_selection_member_decisions m WHERE m.selection_snapshot_id=s.selection_snapshot_id AND selected)) THEN
        RAISE EXCEPTION 'ORB Generation targets differ from Snapshot'; END IF;
    END; $$"""))
    _replace_function('brc_validate_generation_baseline_v1()',
        "IF spec.selection_kind='generic_dynamic_v1' AND g.selection_mode='dynamic_selection' THEN",
        "IF spec.selection_kind='orb_session_dynamic_v1' THEN PERFORM brc_validate_orb_generation(gid); END IF;\n          IF spec.selection_kind='generic_dynamic_v1' AND g.selection_mode='dynamic_selection' THEN")


def _hourly_owner_resume() -> None:
    table='brc_strategy_entry_vacuums_current'
    constraints={c['name']:c['sqltext'] for c in sa.inspect(op.get_bind()).get_check_constraints(table)}
    name='ck_brc_strategy_entry_vacuums_current_gap_continuity_shape'
    op.drop_constraint(name,table,type_='check')
    op.create_check_constraint(name,table,
        "(selection_spec_id='SOR_1H_OR_ATR_DYNAMIC_V1' AND state='RESOLVED_CONTINUITY' "
        "AND source_generation_id IS NULL AND first_blocker='OWNER_PAUSED' "
        "AND drained_at_ms IS NOT NULL AND resolved_at_ms IS NOT NULL) OR ("+constraints[name]+")")
    op.execute(sa.text("""CREATE FUNCTION brc_orb_owner_resume_matches(vid text, checked_at bigint)
    RETURNS boolean LANGUAGE sql STABLE AS $$
      SELECT EXISTS(SELECT 1 FROM brc_strategy_entry_vacuums_current v
        JOIN brc_strategy_entry_controls_current c ON c.strategy_group_id=v.strategy_group_id
        JOIN brc_strategy_entry_control_events r ON r.strategy_entry_control_event_id=c.last_event_id
        JOIN brc_strategy_entry_control_events p ON p.strategy_group_id=c.strategy_group_id AND p.control_version=r.control_version-1
        JOIN brc_owner_authorizations a ON a.authorization_id=r.authorization_id
        JOIN brc_owner_authorizations pa ON pa.authorization_id=p.authorization_id
        WHERE v.entry_vacuum_id=vid AND v.selection_spec_id='SOR_1H_OR_ATR_DYNAMIC_V1'
          AND v.source_generation_id IS NULL AND v.first_blocker='OWNER_PAUSED'
          AND v.drained_at_ms IS NOT NULL AND v.drained_at_ms<=r.created_at_ms AND r.created_at_ms<=checked_at
          AND p.created_at_ms<=v.fenced_at_ms AND p.operation='pause' AND p.target_state='paused'
          AND r.operation='resume' AND r.target_state='enabled' AND c.entry_state='enabled' AND c.control_version=r.control_version
          AND a.purpose='strategy_resume' AND a.authentication_strength='totp_step_up'
          AND a.target_scope=jsonb_build_object('strategy_group_id','SOR-1H-001') AND a.authorized_at_ms=r.created_at_ms
          AND pa.purpose='strategy_pause' AND pa.target_scope=jsonb_build_object('strategy_group_id','SOR-1H-001')
          AND pa.authorized_at_ms=p.created_at_ms
          AND EXISTS(SELECT 1 FROM brc_strategy_entry_vacuum_events e WHERE e.entry_vacuum_id=vid
            AND e.event_type='OWNER_PAUSED' AND e.occurred_at_ms=v.drained_at_ms AND e.payload->'entry_drain_complete'='true'::jsonb))
    $$"""))
    op.execute(sa.text("""CREATE FUNCTION brc_guard_orb_owner_resume_vacuum() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF NEW.selection_spec_id='SOR_1H_OR_ATR_DYNAMIC_V1' AND NEW.state='RESOLVED_CONTINUITY' THEN
        IF OLD.state<>'OWNER_PAUSED' OR NEW.projection_version<>OLD.projection_version+1
          OR NEW.source_generation_id IS NOT NULL OR NEW.fenced_at_ms<>OLD.fenced_at_ms
          OR NEW.drained_at_ms IS DISTINCT FROM OLD.drained_at_ms OR NEW.first_blocker<>OLD.first_blocker
          OR NOT brc_orb_owner_resume_matches(OLD.entry_vacuum_id,NEW.resolved_at_ms) THEN
          RAISE EXCEPTION 'ORB Owner pause cannot bypass resumed hourly audit'; END IF;
      END IF;
      RETURN NEW;
    END; $$"""))
    op.execute(sa.text('CREATE TRIGGER trg_orb_owner_resume_vacuum BEFORE UPDATE ON brc_strategy_entry_vacuums_current '
        'FOR EACH ROW EXECUTE FUNCTION brc_guard_orb_owner_resume_vacuum()'))
    op.execute(sa.text("""CREATE FUNCTION brc_validate_orb_owner_resume_commit() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF NEW.selection_spec_id='SOR_1H_OR_ATR_DYNAMIC_V1' AND NEW.state='RESOLVED_CONTINUITY'
        AND NOT EXISTS(SELECT 1 FROM brc_selection_authority_current p
          JOIN brc_selection_session_authorities a ON a.selection_authority_id=p.selection_authority_id
          JOIN brc_selection_authority_gap_audits_current audit ON audit.authority_gap_audit_id=a.authority_gap_audit_id
          JOIN brc_strategy_entry_vacuum_events e ON e.entry_vacuum_id=NEW.entry_vacuum_id
          WHERE p.selection_spec_id=NEW.selection_spec_id AND a.authority_outcome='PRE_FENCE_CONTINUITY'
            AND a.created_at_ms=NEW.resolved_at_ms AND audit.state='COMPLETE'
            AND audit.gap_kind='OWNER_PAUSE' AND audit.source_entry_vacuum_id=NEW.entry_vacuum_id
            AND e.event_sequence=NEW.projection_version AND e.event_type='RESOLVED_CONTINUITY'
            AND e.payload->>'selection_authority_id'=a.selection_authority_id
            AND e.payload->>'authority_gap_audit_id'=audit.authority_gap_audit_id
            AND e.occurred_at_ms=a.created_at_ms) THEN
        RAISE EXCEPTION 'ORB Owner resume requires atomic complete hourly audit';
      END IF;
      RETURN NULL;
    END; $$"""))
    op.execute(sa.text('CREATE CONSTRAINT TRIGGER trg_orb_owner_resume_commit AFTER UPDATE ON brc_strategy_entry_vacuums_current '
        'DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION brc_validate_orb_owner_resume_commit()'))


def _hourly_audit_ledger() -> None:
    op.execute(sa.text("""CREATE FUNCTION brc_validate_orb_audit_ledger() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE audit brc_selection_authority_gap_audits_current%ROWTYPE;
      aid text; expected_count integer; actual_count integer; scope_json text; result_json text;
    BEGIN
      aid:=NEW.authority_gap_audit_id;
      SELECT * INTO audit FROM brc_selection_authority_gap_audits_current WHERE authority_gap_audit_id=aid;
      IF NOT FOUND OR audit.selection_spec_id<>'SOR_1H_OR_ATR_DYNAMIC_V1' OR audit.state<>'COMPLETE' THEN RETURN NULL; END IF;
      IF audit.detector_semantic_digest<>'sha256:4138d607eebadd1fe4885eb6940e726448cb21c863c93c90993dea39b4f23730'
        OR audit.period_anchor_ms%86400000<>0 OR audit.unauthorized_from_close_time_ms%3600000<>0
        OR audit.unauthorized_from_close_time_ms<audit.period_anchor_ms+7200000
        OR audit.first_eligible_close_time_ms%3600000<>0
        OR audit.first_eligible_close_time_ms<>audit.audited_through_close_time_ms+3600000
        OR audit.first_eligible_close_time_ms>=audit.period_anchor_ms+86400000
        OR (audit.audited_through_close_time_ms<audit.unauthorized_from_close_time_ms
          AND NOT (audit.audited_through_close_time_ms=audit.period_anchor_ms+3600000
            AND audit.unauthorized_from_close_time_ms=audit.first_eligible_close_time_ms)) THEN
        RAISE EXCEPTION 'ORB audit hourly window differs'; END IF;
      WITH expected AS (
        SELECT e.event_spec_id,m.exchange_instrument_id FROM brc_instrument_selection_spec_events e
          JOIN brc_strategy_universe_current p ON p.event_spec_id=e.event_spec_id
          JOIN brc_strategy_universe_members m ON m.universe_version_id=p.universe_version_id
          WHERE e.selection_spec_id=audit.selection_spec_id AND audit.source_generation_id IS NULL
        UNION
        SELECT b.event_spec_id,m.exchange_instrument_id FROM brc_materialization_generation_event_baselines b
          JOIN brc_strategy_universe_members m ON m.universe_version_id=b.universe_version_id
          WHERE b.materialization_generation_id=audit.source_generation_id
        UNION
        SELECT e.event_spec_id,m.exchange_instrument_id FROM brc_strategy_universe_materialization_generations g
          JOIN brc_instrument_selection_spec_events e ON e.selection_spec_id=g.selection_spec_id
          JOIN brc_instrument_selection_member_decisions m ON m.selection_snapshot_id=g.selection_snapshot_id AND m.selected
          WHERE g.materialization_generation_id=audit.source_generation_id
      ) SELECT count(*) INTO expected_count FROM expected;
      SELECT count(*), '['||string_agg('{"event_spec_id":'||to_json(e.payload->'scope'->>'event_spec_id')::text||
        ',"exchange_instrument_id":'||to_json(e.payload->'scope'->>'exchange_instrument_id')::text||'}',','
        ORDER BY e.payload->'scope'->>'event_spec_id' COLLATE "C",e.payload->'scope'->>'exchange_instrument_id' COLLATE "C")||']',
        '['||string_agg('{"first_natural_trigger_at_ms":'||coalesce(e.payload->>'first_natural_trigger_at_ms','null')||
          ',"scope":{"event_spec_id":'||to_json(e.payload->'scope'->>'event_spec_id')::text||
          ',"exchange_instrument_id":'||to_json(e.payload->'scope'->>'exchange_instrument_id')::text||
          '},"session_reference":'||to_json(e.payload->>'session_reference')::text||'}',','
          ORDER BY e.payload->'scope'->>'event_spec_id' COLLATE "C",e.payload->'scope'->>'exchange_instrument_id' COLLATE "C")||']'
        INTO actual_count,scope_json,result_json FROM brc_selection_authority_gap_audit_events e
        WHERE e.authority_gap_audit_id=aid AND e.event_type IN ('CHECKED_NEGATIVE','TRIGGER_SUPPRESSED');
      IF expected_count NOT BETWEEN 2 AND 28 OR actual_count<>expected_count
        OR audit.audit_scope_digest IS DISTINCT FROM 'sha256:'||encode(sha256(convert_to(scope_json,'UTF8')),'hex')
        OR audit.audit_result_digest IS DISTINCT FROM 'sha256:'||encode(sha256(convert_to(result_json,'UTF8')),'hex')
        OR (SELECT count(DISTINCT (e.payload->'scope'->>'event_spec_id',e.payload->'scope'->>'exchange_instrument_id'))
          FROM brc_selection_authority_gap_audit_events e WHERE e.authority_gap_audit_id=aid
          AND e.event_type IN ('CHECKED_NEGATIVE','TRIGGER_SUPPRESSED'))<>expected_count
        OR NOT EXISTS(SELECT 1 FROM brc_selection_authority_gap_audit_events e WHERE e.authority_gap_audit_id=aid
          AND e.event_type='COMPLETE' AND e.payload->>'audit_scope_digest'=audit.audit_scope_digest
          AND e.payload->>'audit_result_digest'=audit.audit_result_digest
          AND (e.payload->>'first_eligible_close_time_ms')::bigint=audit.first_eligible_close_time_ms
          AND e.occurred_at_ms<audit.first_eligible_close_time_ms) THEN
        RAISE EXCEPTION 'ORB audit requires exact complete positive and negative ledger'; END IF;
      IF EXISTS(SELECT 1 FROM brc_selection_authority_gap_audit_events e WHERE e.authority_gap_audit_id=aid
        AND e.event_type IN ('CHECKED_NEGATIVE','TRIGGER_SUPPRESSED') AND (
          e.payload->>'session_reference' IS DISTINCT FROM audit.period_anchor_ms::text
          OR e.payload->'scope'->>'event_spec_id' NOT IN ('event_spec:SOR-1H-001:SOR-1H-LONG:v1','event_spec:SOR-1H-001:SOR-1H-SHORT:v1')
          OR NOT (EXISTS(SELECT 1 FROM brc_strategy_universe_current p JOIN brc_strategy_universe_members m USING(universe_version_id)
            WHERE audit.source_generation_id IS NULL AND p.event_spec_id=e.payload->'scope'->>'event_spec_id'
              AND m.exchange_instrument_id=e.payload->'scope'->>'exchange_instrument_id')
            OR EXISTS(SELECT 1 FROM brc_materialization_generation_event_baselines b JOIN brc_strategy_universe_members m USING(universe_version_id)
              WHERE b.materialization_generation_id=audit.source_generation_id AND b.event_spec_id=e.payload->'scope'->>'event_spec_id'
                AND m.exchange_instrument_id=e.payload->'scope'->>'exchange_instrument_id')
            OR EXISTS(SELECT 1 FROM brc_strategy_universe_materialization_generations g JOIN brc_instrument_selection_member_decisions m
              ON m.selection_snapshot_id=g.selection_snapshot_id AND m.selected WHERE g.materialization_generation_id=audit.source_generation_id
                AND m.exchange_instrument_id=e.payload->'scope'->>'exchange_instrument_id'))
          OR (e.event_type='CHECKED_NEGATIVE' AND e.payload->'first_natural_trigger_at_ms' IS DISTINCT FROM 'null'::jsonb)
          OR (e.event_type='TRIGGER_SUPPRESSED' AND ((e.payload->>'first_natural_trigger_at_ms')::bigint%3600000<>0
            OR (e.payload->>'first_natural_trigger_at_ms')::bigint<audit.unauthorized_from_close_time_ms
            OR (e.payload->>'first_natural_trigger_at_ms')::bigint>audit.audited_through_close_time_ms
            OR NOT EXISTS(SELECT 1 FROM brc_strategy_trigger_suppressions s WHERE s.event_spec_id=e.payload->'scope'->>'event_spec_id'
              AND s.exchange_instrument_id=e.payload->'scope'->>'exchange_instrument_id'
              AND s.session_reference=audit.period_anchor_ms::text AND s.detector_semantic_digest=audit.detector_semantic_digest
              AND s.first_natural_trigger_at_ms=(e.payload->>'first_natural_trigger_at_ms')::bigint))))) THEN
        RAISE EXCEPTION 'ORB audit result or suppression differs'; END IF;
      RETURN NULL;
    END; $$"""))
    for table in ('brc_selection_authority_gap_audits_current','brc_selection_authority_gap_audit_events'):
        op.execute(sa.text(f'CREATE CONSTRAINT TRIGGER trg_{table}_orb_ledger AFTER INSERT OR UPDATE ON {table} '
            'DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION brc_validate_orb_audit_ledger()'))


def downgrade() -> None:
    raise RuntimeError('Hourly ORB authority migration is fix-forward only')
