"""Machine semantic-admission projection for every active strategy scope."""

from __future__ import annotations

from hashlib import sha256
from typing import Any

import sqlalchemy as sa


CONCLUSIONS = {
    "trial_grade_capable",
    "observe_only_by_design",
    "semantics_incomplete",
    "facts_incomplete",
    "strategy_quality_blocked",
    "safety_blocked",
}


def materialize_active_strategy_semantic_admissions(
    conn: sa.engine.Connection,
    *,
    now_ms: int,
) -> dict[str, Any]:
    candidates = _rows(conn, "brc_strategy_group_candidate_scope")
    candidates = [row for row in candidates if row.get("status") == "active"]
    bindings = _rows(conn, "brc_candidate_scope_event_bindings")
    events = _rows(conn, "brc_strategy_side_event_specs")
    facts = _rows(conn, "brc_strategy_event_required_facts")
    mappings = _rows(conn, "brc_symbol_instrument_mappings")
    instruments = _rows(conn, "brc_exchange_instruments")
    runtime_scopes = _rows(conn, "brc_runtime_scope_bindings")
    policies = _rows(conn, "brc_owner_policy_current")

    table = _table(conn, "brc_strategy_semantic_admissions")
    result_rows: list[dict[str, Any]] = []
    for candidate in candidates:
        candidate_id = str(candidate.get("candidate_scope_id") or "")
        active_bindings = [
            row
            for row in bindings
            if row.get("status") == "active"
            and row.get("candidate_scope_id") == candidate_id
        ]
        event = {}
        conclusion = "semantics_incomplete"
        first_blocker = "active_event_binding_missing_or_ambiguous"
        if len(active_bindings) == 1:
            event_id = str(active_bindings[0].get("event_spec_id") or "")
            event = next(
                (
                    row
                    for row in events
                    if row.get("event_spec_id") == event_id
                    and row.get("status") == "current"
                ),
                {},
            )
            conclusion, first_blocker = _conclusion(
                candidate=candidate,
                event=event,
                facts=facts,
                mappings=mappings,
                instruments=instruments,
                runtime_scopes=runtime_scopes,
                policies=policies,
            )
        mapping = next(
            (
                row
                for row in mappings
                if row.get("symbol") == candidate.get("symbol")
                and row.get("status") == "active"
            ),
            {},
        )
        exchange_instrument_id = str(
            mapping.get("exchange_instrument_id") or "missing"
        )
        event_spec_id = str(event.get("event_spec_id") or "missing")
        event_spec_version = str(event.get("event_spec_version") or "missing")
        row = {
            "semantic_admission_id": _stable_id(
                "semantic_admission",
                candidate_id,
            ),
            "candidate_scope_id": candidate_id,
            "strategy_group_id": str(candidate.get("strategy_group_id") or ""),
            "strategy_group_version_id": str(
                event.get("strategy_group_version_id") or "missing"
            ),
            "event_spec_id": event_spec_id,
            "event_spec_version_id": f"{event_spec_id}:{event_spec_version}",
            "symbol": str(candidate.get("symbol") or ""),
            "exchange_instrument_id": exchange_instrument_id,
            "asset_class": str(candidate.get("asset_class") or "unknown"),
            "side": str(candidate.get("side") or ""),
            "conclusion": conclusion,
            "first_blocker": first_blocker or None,
            "authority_source_ref": f"event-spec:{event_spec_id}",
            "evaluated_at_ms": now_ms,
        }
        _upsert(conn, table, row)
        result_rows.append(row)
    return {
        "schema": "brc.strategy_semantic_admission.v1",
        "status": "semantic_admissions_materialized",
        "evaluated_count": len(result_rows),
        "conclusion_counts": {
            conclusion: sum(
                1 for row in result_rows if row["conclusion"] == conclusion
            )
            for conclusion in sorted(CONCLUSIONS)
        },
        "grants_submit_authority": False,
        "exchange_write_called": False,
        "rows": result_rows,
    }


def _conclusion(
    *,
    candidate: dict[str, Any],
    event: dict[str, Any],
    facts: list[dict[str, Any]],
    mappings: list[dict[str, Any]],
    instruments: list[dict[str, Any]],
    runtime_scopes: list[dict[str, Any]],
    policies: list[dict[str, Any]],
) -> tuple[str, str]:
    if not event:
        return "semantics_incomplete", "current_event_spec_missing"
    side = str(candidate.get("side") or "")
    event_id = str(event.get("event_id") or "")
    if event.get("side") != side or not event_id.endswith(side.upper()):
        return "semantics_incomplete", "unsupported_side_event_mirroring"
    if (
        event.get("time_authority") != "trigger_candle_close_time_ms"
        or not event.get("strategy_group_version_id")
        or not event.get("event_spec_version")
        or not event.get("protection_ref_type")
    ):
        return "semantics_incomplete", "event_semantics_contract_incomplete"
    current_facts = [
        row
        for row in facts
        if row.get("event_spec_id") == event.get("event_spec_id")
        and row.get("status") == "current"
    ]
    if not current_facts:
        return "facts_incomplete", "required_facts_missing"
    mapping = next(
        (
            row
            for row in mappings
            if row.get("symbol") == candidate.get("symbol")
            and row.get("status") == "active"
        ),
        {},
    )
    instrument = next(
        (
            row
            for row in instruments
            if row.get("exchange_instrument_id")
            == mapping.get("exchange_instrument_id")
        ),
        {},
    )
    if not mapping or not instrument:
        return "semantics_incomplete", "canonical_instrument_mapping_missing"
    if instrument.get("status") != "active":
        return "safety_blocked", "exchange_instrument_not_active"
    runtime = next(
        (
            row
            for row in runtime_scopes
            if row.get("candidate_scope_id") == candidate.get("candidate_scope_id")
            and row.get("status") == "active"
        ),
        {},
    )
    policy = next(
        (
            row
            for row in policies
            if row.get("policy_current_id")
            == (runtime.get("policy_current_id") if runtime else None)
        ),
        {},
    )
    if not runtime or not policy:
        return "safety_blocked", "runtime_or_owner_policy_missing"
    grade = str(event.get("declared_signal_grade") or "")
    mode = str(event.get("declared_required_execution_mode") or "")
    enabled = event.get("execution_eligibility_enabled") is True
    if enabled and grade in {"trial_grade_signal", "production_grade_signal"} and mode in {
        "trial_live",
        "production_live",
    }:
        return "trial_grade_capable", ""
    if not enabled and grade == "observe_only_signal" and mode == "observe_only":
        return "observe_only_by_design", "execution_eligibility_not_declared"
    return "semantics_incomplete", "execution_eligibility_semantics_inconsistent"


def _rows(conn: sa.engine.Connection, table_name: str) -> list[dict[str, Any]]:
    table = _table(conn, table_name)
    return [dict(row) for row in conn.execute(sa.select(table)).mappings()]


def _table(conn: sa.engine.Connection, table_name: str) -> sa.Table:
    return sa.Table(table_name, sa.MetaData(), autoload_with=conn)


def _upsert(
    conn: sa.engine.Connection,
    table: sa.Table,
    row: dict[str, Any],
) -> None:
    pk = row["semantic_admission_id"]
    exists = conn.execute(
        sa.select(table.c.semantic_admission_id).where(
            table.c.semantic_admission_id == pk
        )
    ).first()
    if exists:
        conn.execute(
            table.update()
            .where(table.c.semantic_admission_id == pk)
            .values(**row)
        )
    else:
        conn.execute(table.insert().values(**row))


def _stable_id(prefix: str, value: str) -> str:
    return f"{prefix}:{sha256(value.encode('utf-8')).hexdigest()[:32]}"
