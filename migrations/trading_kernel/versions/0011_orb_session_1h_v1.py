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
    _replace_function("brc_validate_selection_job_epoch_v1()",
        "IF kind='sor_dynamic_v0' THEN",
        "IF kind='orb_session_dynamic_v1' THEN\n            IF NEW.selection_epoch_id='sor-v0' OR length(trim(NEW.selection_epoch_id))=0 OR NEW.period_anchor_ms%86400000<>0\n              OR NEW.feature_cutoff_at_ms<>NEW.period_anchor_ms+3600000 OR NEW.scheduled_at_ms<>NEW.feature_cutoff_at_ms\n              OR NEW.selection_spec_id<>'SOR_1H_OR_ATR_DYNAMIC_V1' OR NEW.selection_control_version IS NULL THEN\n              RAISE EXCEPTION 'ORB Job exact epoch/clock/control differs'; END IF;\n            RETURN NEW; END IF;\n          IF kind='sor_dynamic_v0' THEN")
    for role in ('brc_owner_console','brc_owner_control'):
        if bind.scalar(sa.text('SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=:role)'),{'role':role}):
            op.execute(sa.text(f'GRANT SELECT ON brc_orb_session_selection_specs_v1 TO {role}'))



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

def downgrade() -> None:
    raise RuntimeError('Hourly ORB authority migration is fix-forward only')
