"""Extend exact hourly ORB validators for independently controlled directions."""

import json
import re

import sqlalchemy as sa
from alembic import op

revision: str = "0025_directional_sor"
down_revision: str | None = "0024_owner_cooperation"
branch_labels = None
depends_on = None

_LEGACY = "SOR_1H_OR_ATR_DYNAMIC_V1"
_DIRECTIONS = (
    (
        "SOR_1H_LONG_OR_ATR_DYNAMIC_V1",
        "SOR-1H-LONG-001",
        "event_spec:SOR-1H-LONG-001:SOR-1H-LONG:v1",
        "sha256:512a95428c62c45f19299ae5d25b9974fdede62bd366ab9355f1394d1a24dfdd",
        "sha256:3e48b25aa7ef437a54a34a7cdc3455a1cc51422a688723416535bf5fe9ec6b93",
    ),
    (
        "SOR_1H_SHORT_OR_ATR_DYNAMIC_V1",
        "SOR-1H-SHORT-001",
        "event_spec:SOR-1H-SHORT-001:SOR-1H-SHORT:v1",
        "sha256:ad729c21ae839cf7a0f5c61b1a54cf3b204d1adeffb9b4e88767ae560e235b58",
        "sha256:ed98ec5939bcc35778cf9ae38bf5a5d0764cb0101b1b5e11a175adb3b589dcc4",
    ),
)
_SPECS_SQL = f"'{_LEGACY}'," + ",".join(f"'{row[0]}'" for row in _DIRECTIONS)


def _definition(signature: str) -> str:
    result = op.get_bind().scalar(
        sa.text("SELECT pg_get_functiondef(to_regprocedure(:signature))"),
        {"signature": signature},
    )
    if not isinstance(result, str):
        raise TypeError(f"0025 expected exact source function {signature}")
    return result


def _amend(signature: str, *changes: tuple[str, str, int]) -> None:
    definition = _definition(signature)
    for old, new, count in changes:
        if definition.count(old) != count:
            raise RuntimeError(f"0025 source signature differs for {signature}: {old}")
        definition = definition.replace(old, new)
    op.get_bind().exec_driver_sql(definition)


def _amend_spec_comparison(
    field: str, *, negated: bool = False
) -> tuple[str, str, int]:
    operator = "<>" if negated else "="
    old = f"{field}{operator}'{_LEGACY}'"
    new = f"{field} {'NOT IN' if negated else 'IN'} ({_SPECS_SQL})"
    return old, new, 1


def _check_constraint(table: str, name: str) -> str:
    for constraint in sa.inspect(op.get_bind()).get_check_constraints(table):
        if constraint["name"] == name:
            return constraint["sqltext"]
    raise RuntimeError(f"0025 expected exact source constraint {name}")


def _extend_clock_constraint(table: str, name: str) -> None:
    source = _check_constraint(table, name)
    old = f"'{_LEGACY}'::text"
    if old not in source:
        raise RuntimeError(f"0025 expected hourly identity in {name}")
    # Each directional check retains all the old terms with only its Spec identity replaced.
    target = source
    for spec_id, *_ in reversed(_DIRECTIONS):
        target = f"CASE WHEN selection_spec_id='{spec_id}' THEN ({source.replace(old, repr(spec_id) + '::text')}) ELSE ({target}) END"
    op.drop_constraint(name, table, type_="check")
    op.create_check_constraint(name, table, target)


def _extend_spec() -> None:
    signature = "brc_validate_orb_spec_v1()"
    definition = _definition(signature)
    payload_match = re.search(r"OR p IS DISTINCT FROM '({[^']+})'::jsonb", definition)
    if payload_match is None:
        raise RuntimeError("0025 expected frozen source payload")
    payload = json.loads(payload_match.group(1))
    cases = []
    for spec_id, group, event, digest, _ in _DIRECTIONS:
        version = f"sgv:{group}:v1"
        expected = json.dumps(
            {
                **payload,
                "selection_spec_id": spec_id,
                "strategy_group_id": group,
                "strategy_version_id": version,
                "event_spec_ids": [event],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        cases.append(
            f"""IF sid='{spec_id}' THEN
            IF spec.strategy_group_id<>'{group}' OR spec.strategy_version_id<>'{version}'
              OR spec.selection_version<>1 OR spec.algorithm_semantic_digest<>'{digest}'
              OR p IS DISTINCT FROM '{expected}'::jsonb
              OR members IS NULL OR to_jsonb(members) IS DISTINCT FROM p->'candidate_ids'
              OR events IS DISTINCT FROM ARRAY['{event}']::text[]
              OR EXISTS(SELECT 1 FROM brc_instrument_selection_spec_events b JOIN brc_event_specs e USING(event_spec_id)
                WHERE b.selection_spec_id=sid AND (e.strategy_version_id<>spec.strategy_version_id
                  OR e.position_side<>b.position_side OR e.timeframe<>'1h'))
            THEN RAISE EXCEPTION 'ORB Spec requires exact directional payload, Candidate24 and Event'; END IF;
            RETURN NULL;
            END IF;"""
        )
    anchor = f"IF sid<>'{_LEGACY}'"
    _amend(signature, (anchor, "\n".join(cases) + "\n      " + anchor, 1))
    table, name = "brc_orb_session_selection_specs_v1", "ck_brc_orb_payload_identity"
    old = _check_constraint(table, name)
    op.drop_constraint(name, table, type_="check")
    op.create_check_constraint(
        name,
        table,
        f"selection_spec_id IN ({_SPECS_SQL}) AND "
        f"(selection_spec_id<>'{_LEGACY}' OR ({old}))",
    )


def _extend_selection_functions() -> None:
    identity = "EXISTS(SELECT 1 FROM brc_instrument_selection_specs source WHERE "
    snapshot = "brc_validate_orb_snapshot_v1(text)"
    _amend(
        snapshot,
        (
            (
                f"s.selection_spec_id<>'{_LEGACY}' OR s.strategy_group_id<>'SOR-1H-001'\n"
                "        OR s.strategy_version_id<>'sgv:SOR-1H-001:v1'"
            ),
            (
                f"s.selection_spec_id NOT IN ({_SPECS_SQL}) OR NOT {identity}"
                "source.selection_spec_id=s.selection_spec_id AND source.strategy_group_id=s.strategy_group_id "
                "AND source.strategy_version_id=s.strategy_version_id)"
            ),
            1,
        ),
        (
            f',"selection_spec_id":"{_LEGACY}","session_start_ms":',
            ',"selection_spec_id":\'||to_json(s.selection_spec_id)::text||\',"session_start_ms":',
            1,
        ),
    )
    job = "brc_validate_selection_job_epoch_v1()"
    _amend(job, _amend_spec_comparison("NEW.selection_spec_id", negated=True))
    generation = "brc_validate_orb_generation(text)"
    _amend(
        generation,
        (
            (
                f"g.selection_spec_id<>'{_LEGACY}' OR g.strategy_group_id<>'SOR-1H-001'\n"
                "        OR g.strategy_version_id<>'sgv:SOR-1H-001:v1'"
            ),
            (
                f"g.selection_spec_id NOT IN ({_SPECS_SQL}) OR NOT {identity}"
                "source.selection_spec_id=g.selection_spec_id AND source.strategy_group_id=g.strategy_group_id "
                "AND source.strategy_version_id=g.strategy_version_id)"
            ),
            1,
        ),
    )
    for function, field, negated in (
        ("brc_validate_orb_previous_authority()", "g.selection_spec_id", True),
        ("brc_preserve_generation_source_identity_v1()", "OLD.selection_spec_id", True),
        ("brc_validate_generic_normal_binding()", "a.selection_spec_id", False),
        ("brc_validate_generic_continuity_commit()", "a.selection_spec_id", False),
        ("brc_guard_orb_owner_resume_vacuum()", "NEW.selection_spec_id", False),
        ("brc_validate_orb_owner_resume_commit()", "NEW.selection_spec_id", False),
    ):
        _amend(function, _amend_spec_comparison(field, negated=negated))

    for function, field, group, count in (
        (
            "brc_validate_orb_authority_commit()",
            "a.selection_spec_id",
            "(SELECT source.strategy_group_id FROM brc_instrument_selection_specs source WHERE source.selection_spec_id=a.selection_spec_id)",
            4,
        ),
        (
            "brc_validate_orb_static_authority(text)",
            "a.selection_spec_id",
            "g.strategy_group_id",
            3,
        ),
        (
            "brc_validate_orb_static_generation(text)",
            "g.selection_spec_id",
            "g.strategy_group_id",
            1,
        ),
        (
            "brc_orb_owner_resume_matches(text,bigint)",
            "v.selection_spec_id",
            "v.strategy_group_id",
            2,
        ),
    ):
        changes = [
            _amend_spec_comparison(
                field,
                negated=function != "brc_orb_owner_resume_matches(text,bigint)",
            ),
            ("'SOR-1H-001'", group, count),
        ]
        if function in {
            "brc_validate_orb_authority_commit()",
            "brc_validate_orb_static_authority(text)",
        }:
            changes.append(
                (
                    "n<>2",
                    f"n<>(SELECT count(*) FROM brc_instrument_selection_spec_events WHERE selection_spec_id={field})",
                    4 if function == "brc_validate_orb_authority_commit()" else 1,
                )
            )
        _amend(function, *changes)

    audit = "brc_validate_orb_audit_ledger()"
    cases = " ".join(
        f"WHEN '{spec}' THEN '{digest}'" for spec, _, _, _, digest in _DIRECTIONS
    )
    _amend(
        audit,
        _amend_spec_comparison("audit.selection_spec_id", negated=True),
        (
            "audit.detector_semantic_digest<>'sha256:4138d607eebadd1fe4885eb6940e726448cb21c863c93c90993dea39b4f23730'",
            (
                "audit.detector_semantic_digest IS DISTINCT FROM (CASE audit.selection_spec_id "
                f"{cases} ELSE 'sha256:4138d607eebadd1fe4885eb6940e726448cb21c863c93c90993dea39b4f23730' END)"
            ),
            1,
        ),
        (
            "expected_count NOT BETWEEN 2 AND 28",
            (
                "expected_count NOT BETWEEN "
                "(SELECT count(*) FROM brc_instrument_selection_spec_events WHERE selection_spec_id=audit.selection_spec_id) "
                "AND 14*(SELECT count(*) FROM brc_instrument_selection_spec_events WHERE selection_spec_id=audit.selection_spec_id)"
            ),
            1,
        ),
        (
            "NOT IN ('event_spec:SOR-1H-001:SOR-1H-LONG:v1','event_spec:SOR-1H-001:SOR-1H-SHORT:v1')",
            "NOT IN (SELECT event_spec_id FROM brc_instrument_selection_spec_events WHERE selection_spec_id=audit.selection_spec_id)",
            1,
        ),
    )


def _extend_static_source() -> None:
    bind = op.get_bind()
    spec_ids = ",".join(f"'{row[0]}'" for row in _DIRECTIONS)
    group_ids = ",".join(f"'{row[1]}'" for row in _DIRECTIONS)
    bind.exec_driver_sql(f"""
      CREATE FUNCTION brc_lock_owner_directional_orb_static_source(sid text) RETURNS void
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
      BEGIN
        IF sid NOT IN ({spec_ids}) OR NOT EXISTS(
          SELECT 1 FROM public.brc_strategy_selection_control_current c
          JOIN public.brc_instrument_selection_specs s ON s.selection_spec_id=c.selection_spec_id
          WHERE c.selection_spec_id=sid AND c.strategy_group_id=s.strategy_group_id
            AND c.selection_mode='static_baseline' AND c.pending_selection_mode IS NULL
            AND s.selection_kind='orb_session_dynamic_v1' AND s.status='active'
        ) THEN RAISE EXCEPTION 'ORB Owner source lock requires exact directional Static control'; END IF;
        PERFORM 1 FROM public.brc_strategy_universe_current p
          JOIN public.brc_instrument_selection_spec_events e ON e.event_spec_id=p.event_spec_id
          WHERE e.selection_spec_id=sid ORDER BY p.event_spec_id FOR UPDATE OF p;
      END; $$
    """)
    bind.exec_driver_sql(
        "REVOKE ALL ON FUNCTION brc_lock_owner_directional_orb_static_source(text) FROM PUBLIC"
    )
    if bind.scalar(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='brc_owner_control')"
        )
    ):
        bind.exec_driver_sql(
            "GRANT EXECUTE ON FUNCTION brc_lock_owner_directional_orb_static_source(text) TO brc_owner_control"
        )
    _amend(
        "brc_validate_rollback_baseline_v1()",
        (
            "IF b.strategy_group_id NOT IN ('SOR-001','SOR-1H-001') THEN",
            f"""IF b.strategy_group_id IN ({group_ids}) THEN
              SELECT * INTO spec FROM brc_instrument_selection_specs
                WHERE strategy_group_id=b.strategy_group_id AND strategy_version_id=b.strategy_version_id
                  AND selection_spec_id IN ({spec_ids}) AND selection_kind='orb_session_dynamic_v1';
              IF NOT FOUND OR spec.installed_at_ms>b.captured_at_ms THEN
                RAISE EXCEPTION 'Directional ORB baseline requires installed Spec'; END IF;
              SELECT * INTO baseline_event FROM brc_selection_rollback_baseline_events WHERE rollback_baseline_id=bid;
              SELECT * INTO source_universe FROM brc_strategy_universe_versions WHERE universe_version_id=baseline_event.universe_version_id;
              SELECT * INTO source_current FROM brc_strategy_universe_current WHERE event_spec_id=baseline_event.event_spec_id;
              IF NOT FOUND OR source_current.universe_version_id<>source_universe.universe_version_id
                OR source_current.semantic_digest<>source_universe.semantic_digest
                OR source_current.lifecycle_state<>'active' OR source_universe.lifecycle_state<>'active'
                OR source_current.activated_at_ms>b.captured_at_ms
                OR (SELECT array_agg(exchange_instrument_id::text ORDER BY exchange_instrument_id COLLATE "C")
                    FROM brc_strategy_universe_members WHERE universe_version_id=source_universe.universe_version_id)
                  IS DISTINCT FROM ARRAY[
                    'binance-usdm:ADAUSDT:perpetual','binance-usdm:BNBUSDT:perpetual','binance-usdm:BTCUSDT:perpetual',
                    'binance-usdm:DOGEUSDT:perpetual','binance-usdm:ETHUSDT:perpetual','binance-usdm:SOLUSDT:perpetual',
                    'binance-usdm:XRPUSDT:perpetual']::text[] THEN
                RAISE EXCEPTION 'Directional ORB baseline requires exact current Static source'; END IF;
              member_digest:=brc_selected_universe_member_digest_v1(source_universe.universe_version_id);
              source_json:='{{"event_spec_id":'||to_json(baseline_event.event_spec_id)::text||
                ',"member_set_digest":'||to_json(member_digest)::text||
                ',"position_side":'||to_json(baseline_event.position_side)::text||
                ',"universe_semantic_digest":'||to_json(source_universe.semantic_digest)::text||
                ',"universe_version_id":'||to_json(source_universe.universe_version_id)::text||'}}';
              expected_digest:='sha256:'||encode(sha256(convert_to(
                '{{"captured_at_ms":'||b.captured_at_ms::text||',"selection_spec_id":'||to_json(spec.selection_spec_id)::text||
                ',"source_events":['||source_json||'],"strategy_group_id":'||to_json(b.strategy_group_id)::text||
                ',"strategy_version_id":'||to_json(b.strategy_version_id)::text||'}}','UTF8')),'hex');
              IF b.semantic_digest IS DISTINCT FROM expected_digest
                OR bid IS DISTINCT FROM 'rollback:orb:'||substring(expected_digest from 8) THEN
                RAISE EXCEPTION 'Directional ORB baseline digest differs'; END IF;
              IF NOT EXISTS(
                SELECT 1 FROM brc_strategy_selection_control_current sc
                JOIN brc_owner_authorizations owner ON owner.authorization_id=sc.pending_authorization_id
                WHERE sc.strategy_group_id=b.strategy_group_id AND sc.selection_spec_id=spec.selection_spec_id
                  AND sc.selection_mode='static_baseline' AND sc.pending_selection_mode='dynamic_selection'
                  AND sc.rollback_baseline_id=bid AND sc.updated_at_ms=b.captured_at_ms
                  AND owner.purpose='selection_mode_change' AND owner.authentication_strength='totp_step_up'
                  AND owner.authorized_at_ms=b.captured_at_ms
                  AND owner.target_scope->>'strategy_group_id'=b.strategy_group_id
                  AND owner.target_scope->>'selection_spec_id'=spec.selection_spec_id
                  AND owner.target_scope->>'selection_epoch_id'=sc.selection_epoch_id
              ) THEN RAISE EXCEPTION 'Directional ORB baseline requires atomic Owner capture'; END IF;
              RETURN NULL;
            END IF;
            IF b.strategy_group_id NOT IN ('SOR-001','SOR-1H-001') THEN""",
            1,
        ),
    )


def _install_directional_risk_rule() -> None:
    bind = op.get_bind()
    old_event_ids = (
        "event_spec:SOR-1H-001:SOR-1H-LONG:v1",
        "event_spec:SOR-1H-001:SOR-1H-SHORT:v1",
    )
    bind.execute(
        sa.text("""
            INSERT INTO brc_directional_risk_rules(rule_id,rule_digest,limits,event_spec_ids,budget_contract)
            SELECT 'owner-directional-risk:v3', :target_digest, limits,
                   (SELECT jsonb_agg(event_id ORDER BY event_id COLLATE "C") FROM (
                        SELECT jsonb_array_elements_text(event_spec_ids - CAST(:removed AS text[])) AS event_id
                        UNION ALL SELECT unnest(CAST(:added AS text[]))
                   ) events), budget_contract
              FROM brc_directional_risk_rules
             WHERE rule_id='owner-directional-risk:v2' AND rule_digest=:source_digest
        """),
        {
            "removed": list(old_event_ids),
            "added": [item[2] for item in _DIRECTIONS],
            "source_digest": "sha256:54563b9f46a0370f2efda893fd6b4acc18ed6933f75961818ae7003b0f1a1406",
            "target_digest": "sha256:b02127c5038db37b471d2b538dab2c93fb08065302ae68df8552dfdc9cacf9df",
        },
    )
    if not bind.scalar(sa.text("SELECT EXISTS(SELECT 1 FROM brc_directional_risk_rules WHERE rule_id='owner-directional-risk:v3')")):
        raise RuntimeError("0025 missing canonical v2 directional risk source")


def upgrade() -> None:
    bind = op.get_bind()
    if bind.scalar(sa.text("SELECT version_num FROM alembic_version")) != down_revision:
        raise RuntimeError("0025 requires exact 0024 source")
    predicates = {
        "brc_trade_tickets": "terminal_at_ms IS NULL",
        "brc_positions_current": "quantity<>0",
        "brc_exchange_commands": "status IN ('prepared','claimed','dispatch_started','outcome_unknown')",
        "brc_owner_policy_current": "new_entry_submit_enabled",
        "brc_budget_reservations": "status='active'",
        "brc_entry_lane_current": "status<>'idle'",
        "brc_runtime_incidents": "status='open'",
        "brc_strategy_universe_versions": "lifecycle_state IN ('warming','staged')",
        "brc_strategy_universe_materialization_generations": "lifecycle_state IN ('PENDING','DESIRED','DRAINING_ENTRY','MATERIALIZING','STAGED')",
    }
    bind.exec_driver_sql(
        f"LOCK TABLE {','.join(predicates)} IN SHARE ROW EXCLUSIVE MODE"
    )
    for table, predicate in predicates.items():
        if bind.scalar(
            sa.text(f"SELECT EXISTS(SELECT 1 FROM {table} WHERE {predicate})")
        ):
            raise RuntimeError(f"0025 requires stopped flat and paused source: {table}")
    _extend_spec()
    _extend_selection_functions()
    _extend_static_source()
    _install_directional_risk_rule()
    for table, name in (
        ("brc_selection_session_authorities", "ck_brc_generic_normal_grant_shape"),
        ("brc_selection_session_authorities", "ck_brc_orb_authority_clock"),
        (
            "brc_strategy_universe_materialization_generations",
            "ck_brc_materialization_generation_source_shape",
        ),
        (
            "brc_strategy_entry_vacuums_current",
            "ck_brc_strategy_entry_vacuums_current_gap_continuity_shape",
        ),
    ):
        _extend_clock_constraint(table, name)


def downgrade() -> None:
    raise RuntimeError("0025 is forward-only")
