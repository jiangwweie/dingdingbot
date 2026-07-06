#!/usr/bin/env python3
"""Publish PG-backed current read-model projections.

This projector is non-authority from a trading perspective. It converts the
current PG control state into durable current projections and read-model
snapshots so generated JSON exports are no longer the only place where the
current Candidate Pool, Daily Table, and Goal Status are visible.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from typing import Any

import sqlalchemy as sa


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.build_daily_live_enablement_table import (  # noqa: E402
    build_daily_live_enablement_table_from_control_state,
)
from scripts.build_strategy_live_candidate_pool import (  # noqa: E402
    build_strategy_live_candidate_pool_from_control_state,
)
from scripts.build_strategygroup_runtime_goal_status import (  # noqa: E402
    build_goal_status_artifact_from_control_state,
)
from scripts.pg_dsn import normalize_sync_postgres_dsn  # noqa: E402
from src.infrastructure.runtime_control_state_repository import (  # noqa: E402
    PgBackedRuntimeControlStateRepository,
)


DEFAULT_REPORT_DIR = Path("/home/ubuntu/brc-deploy/reports/runtime-signal-watcher")
DEFAULT_RUNTIME_MONITOR_DIR = Path("/home/ubuntu/brc-deploy/reports/runtime-monitor")
DEFAULT_RELEASE_MANIFEST = Path("/home/ubuntu/brc-deploy/app/current/.brc-release-manifest.json")
DEFAULT_OUTPUT_JSON = (
    DEFAULT_REPORT_DIR / "runtime-control-current-projection-publish.json"
)
PROJECTOR_NAME = "pg_current_projection_publisher"
SCHEMA = "brc.runtime_control_current_projection_publish.v1"


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    database_url = _normalized_database_url(args.database_url)
    if not database_url:
        print(
            "ERROR: PG_DATABASE_URL is required for current projection publishing",
            file=sys.stderr,
        )
        return 2
    if not database_url.startswith(
        ("postgresql://", "postgresql+psycopg://")
    ) and not args.allow_non_postgres_for_test:
        print(
            "ERROR: current projection publishing requires PostgreSQL DSN",
            file=sys.stderr,
        )
        return 2

    engine = sa.create_engine(database_url)
    try:
        with engine.begin() as conn:
            report = publish_runtime_control_current_projections(
                conn,
                report_dir=args.report_dir,
                runtime_monitor_dir=args.runtime_monitor_dir,
                release_manifest=args.release_manifest,
                expected_head=args.expected_head,
                output_paths={
                    "candidate_pool": args.candidate_pool_json,
                    "daily_live_enablement_table": args.daily_table_json,
                    "goal_status": args.goal_status_json,
                },
            )
            _write_json(args.output_json, report)
    finally:
        engine.dispose()

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["status"] == "current_projections_published" else 1


def publish_runtime_control_current_projections(
    conn: sa.engine.Connection,
    *,
    report_dir: Path = DEFAULT_REPORT_DIR,
    runtime_monitor_dir: Path = DEFAULT_RUNTIME_MONITOR_DIR,
    release_manifest: Path | None = DEFAULT_RELEASE_MANIFEST,
    expected_head: str | None = None,
    output_paths: dict[str, Path | None] | None = None,
) -> dict[str, Any]:
    started_ms = int(time.time() * 1000)
    generated = datetime.now(timezone.utc).isoformat()
    repository = PgBackedRuntimeControlStateRepository(conn)
    control_state = repository.read_control_state()
    projection_control_state = {
        **control_state,
        # Build the new current readiness projection from base facts/scope,
        # not from the previous current projection row set.
        "pretrade_readiness_rows": [],
    }

    candidate_pool = build_strategy_live_candidate_pool_from_control_state(
        projection_control_state,
        generated_at_utc=generated,
    )
    daily_table = build_daily_live_enablement_table_from_control_state(
        projection_control_state,
        generated_at_utc=generated,
    )
    goal_status = build_goal_status_artifact_from_control_state(
        control_state={
            **projection_control_state,
            "pretrade_readiness_rows": _readiness_rows_for_control_state(
                candidate_pool,
                control_state=control_state,
                computed_at_ms=started_ms,
            ),
        },
        report_dir=report_dir,
        release_manifest=release_manifest,
        expected_head=expected_head,
    )

    output_paths = output_paths or {}
    projector_runs = [
        _projection_run(
            model_type="candidate_pool",
            owner_projector="pg_candidate_pool_projector",
            started_ms=started_ms,
            input_watermark=_input_watermark(control_state, candidate_pool),
        ),
        _projection_run(
            model_type="daily_live_enablement_table",
            owner_projector="pg_daily_table_projector",
            started_ms=started_ms,
            input_watermark=_input_watermark(control_state, daily_table),
        ),
        _projection_run(
            model_type="goal_status",
            owner_projector="pg_goal_status_projector",
            started_ms=started_ms,
            input_watermark=_input_watermark(control_state, goal_status),
        ),
    ]
    readiness_rows = _readiness_rows_for_control_state(
        candidate_pool,
        control_state=control_state,
        computed_at_ms=started_ms,
    )
    snapshots = [
        _snapshot_row(
            model_type="candidate_pool",
            payload=candidate_pool,
            source_watermark=_source_watermark(candidate_pool),
            input_watermark=_input_watermark(control_state, candidate_pool),
            output_path=output_paths.get("candidate_pool"),
            generated_at_ms=started_ms,
        ),
        _snapshot_row(
            model_type="daily_live_enablement_table",
            payload=daily_table,
            source_watermark=_source_watermark(daily_table),
            input_watermark=_input_watermark(control_state, daily_table),
            output_path=output_paths.get("daily_live_enablement_table"),
            generated_at_ms=started_ms,
        ),
        _snapshot_row(
            model_type="goal_status",
            payload=goal_status,
            source_watermark=_source_watermark(goal_status),
            input_watermark=_input_watermark(control_state, goal_status),
            output_path=output_paths.get("goal_status"),
            generated_at_ms=started_ms,
        ),
    ]

    _replace_pretrade_readiness_rows(conn, readiness_rows)
    for run in projector_runs:
        _upsert_by_pk(conn, "brc_projection_runs", run)
    _upsert_goal_status_current(
        conn,
        goal_status=goal_status,
        projection_run_id=projector_runs[-1]["projection_run_id"],
        updated_at_ms=started_ms,
    )
    _insert_current_snapshots(conn, snapshots)

    return {
        "schema": SCHEMA,
        "status": "current_projections_published",
        "generated_at_utc": generated,
        "published_tables": {
            "brc_pretrade_readiness_rows": len(readiness_rows),
            "brc_goal_status_current": 1,
            "brc_control_read_model_snapshots_current": len(snapshots),
            "brc_projection_runs": len(projector_runs),
        },
        "model_types": [snapshot["model_type"] for snapshot in snapshots],
        "candidate_pool": {
            "status": candidate_pool.get("status"),
            "symbol_readiness_count": len(candidate_pool.get("symbol_readiness_rows") or []),
            "action_time_lane_input_count": len(candidate_pool.get("action_time_lane_inputs") or []),
        },
        "goal_status": {
            "status": goal_status.get("status"),
            "ready_for_real_order_action": goal_status.get("ready_for_real_order_action")
            is True,
        },
        "authority_boundary": (
            "current_projection_publish_only; no_finalgate_no_operation_layer_"
            "no_exchange_write_no_order_lifecycle_no_live_profile_or_sizing_change"
        ),
        "safety_invariants": {
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "live_profile_changed": False,
            "order_sizing_changed": False,
        },
    }


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("PG_DATABASE_URL", ""))
    parser.add_argument(
        "--require-database-url",
        action="store_true",
        help="Accepted for command consistency; this projector is always PG-backed.",
    )
    parser.add_argument(
        "--allow-non-postgres-for-test",
        action="store_true",
        help="Allow SQLite/non-PG DSNs only in tests.",
    )
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--runtime-monitor-dir", type=Path, default=DEFAULT_RUNTIME_MONITOR_DIR)
    parser.add_argument("--release-manifest", type=Path, default=DEFAULT_RELEASE_MANIFEST)
    parser.add_argument("--expected-head")
    parser.add_argument(
        "--candidate-pool-json",
        type=Path,
        default=DEFAULT_RUNTIME_MONITOR_DIR / "latest-strategy-live-candidate-pool.json",
    )
    parser.add_argument(
        "--daily-table-json",
        type=Path,
        default=DEFAULT_RUNTIME_MONITOR_DIR / "latest-daily-live-enablement-table.json",
    )
    parser.add_argument(
        "--goal-status-json",
        type=Path,
        default=DEFAULT_REPORT_DIR / "strategygroup-runtime-goal-status.json",
    )
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def _normalized_database_url(database_url: str) -> str:
    return normalize_sync_postgres_dsn(database_url)


def _readiness_rows_for_control_state(
    candidate_pool: dict[str, Any],
    *,
    control_state: dict[str, Any],
    computed_at_ms: int,
) -> list[dict[str, Any]]:
    candidate_scope_by_lane = {
        _lane_key(row): str(row.get("candidate_scope_id") or "")
        for row in _dict_rows(control_state.get("candidate_scope"))
        if row.get("status") == "active"
    }
    watermark = _stable_watermark(candidate_pool)
    return [
        _readiness_row(
            row,
            candidate_scope_id=candidate_scope_by_lane.get(_lane_key(row), ""),
            computed_at_ms=computed_at_ms,
            source_watermark=watermark,
        )
        for row in _dict_rows(candidate_pool.get("symbol_readiness_rows"))
    ]


def _readiness_row(
    row: dict[str, Any],
    *,
    candidate_scope_id: str,
    computed_at_ms: int,
    source_watermark: str,
) -> dict[str, Any]:
    strategy_group_id = str(row.get("strategy_group_id") or "")
    symbol = str(row.get("symbol") or "")
    side = str(row.get("side") or "")
    public_facts = _dict(row.get("public_facts_state"))
    return {
        "readiness_row_id": f"readiness:{strategy_group_id}:{symbol}:{side}",
        "candidate_scope_id": candidate_scope_id or None,
        "strategy_group_id": strategy_group_id,
        "symbol": symbol,
        "side": side,
        "readiness_state": _readiness_state(row),
        "detector_state": str(row.get("detector_state") or "unknown"),
        "watcher_state": str(row.get("watcher_state") or "unknown"),
        "public_facts_state": str(public_facts.get("state") or "unknown"),
        "signal_lifecycle_status": str(row.get("signal_state") or "unknown"),
        "signal_freshness_state": (
            "fresh" if str(row.get("signal_state") or "") == "fresh" else "absent"
        ),
        "risk_state": str(row.get("risk_state") or "unknown"),
        "scope_state": str(row.get("scope_state") or "unknown"),
        "promotion_state": str(row.get("promotion_state") or "idle"),
        "first_blocker_class": str(row.get("first_blocker") or "unknown"),
        "first_blocker_detail": _first_blocker_detail(row),
        "next_action": str(row.get("next_action") or ""),
        "stop_condition": str(row.get("stop_condition") or ""),
        "evidence_ref": str(row.get("evidence_ref") or "") or None,
        "source_watermark": source_watermark,
        "computed_at_ms": computed_at_ms,
        "valid_until_ms": None,
    }


def _readiness_state(row: dict[str, Any]) -> str:
    promotion_state = str(row.get("promotion_state") or "")
    signal_state = str(row.get("signal_state") or "")
    first_blocker = str(row.get("first_blocker") or "")
    if promotion_state == "action_time_lane":
        return "action_time_lane_ready"
    if promotion_state == "promotion_candidate":
        return "promotion_candidate"
    if first_blocker == "action_time_preflight_ready":
        return "preflight_ready"
    if signal_state == "fresh":
        return "fresh_signal_blocked"
    if first_blocker in {"computed_not_satisfied", "market_wait_validated"}:
        return "market_wait"
    return "blocked"


def _first_blocker_detail(row: dict[str, Any]) -> str:
    public_facts = _dict(row.get("public_facts_state"))
    failed = public_facts.get("computed_not_satisfied") or []
    failed_text = ",".join(str(item) for item in failed if str(item or ""))
    if failed_text:
        return f"{row.get('first_blocker')}: {failed_text}"
    return str(row.get("first_blocker") or "")


def _projection_run(
    *,
    model_type: str,
    owner_projector: str,
    started_ms: int,
    input_watermark: dict[str, Any],
) -> dict[str, Any]:
    return {
        "projection_run_id": f"projection:{model_type}:{started_ms}",
        "model_type": model_type,
        "owner_projector": owner_projector,
        "code_version": "current",
        "source_mode": "db_backed",
        "projection_target": "production_current",
        "input_watermark": input_watermark,
        "source_priority": ["pg"],
        "legacy_diagnostics_read": False,
        "legacy_diagnostics_affected_current": False,
        "started_at_ms": started_ms,
        "finished_at_ms": int(time.time() * 1000),
        "status": "succeeded",
        "error_detail": None,
    }


def _snapshot_row(
    *,
    model_type: str,
    payload: dict[str, Any],
    source_watermark: dict[str, Any],
    input_watermark: dict[str, Any],
    output_path: Path | None,
    generated_at_ms: int,
) -> dict[str, Any]:
    return {
        "snapshot_id": f"snapshot:{model_type}:{generated_at_ms}",
        "model_type": model_type,
        "payload": payload,
        "source_watermark": source_watermark,
        "owner_projector": _snapshot_owner_projector(model_type),
        "input_watermark": input_watermark,
        "output_path": str(output_path) if output_path else None,
        "is_current": True,
        "generated_at_ms": generated_at_ms,
        "generated_by": PROJECTOR_NAME,
    }


def _snapshot_owner_projector(model_type: str) -> str:
    return {
        "candidate_pool": "pg_candidate_pool_projector",
        "daily_live_enablement_table": "pg_daily_table_projector",
        "goal_status": "pg_goal_status_projector",
    }[model_type]


def _upsert_goal_status_current(
    conn: sa.engine.Connection,
    *,
    goal_status: dict[str, Any],
    projection_run_id: str,
    updated_at_ms: int,
) -> None:
    checks = _dict(goal_status.get("checks"))
    row = {
        "goal_status_current_id": "strategygroup-runtime-goal-status",
        "status": str(goal_status.get("status") or ""),
        "fresh_signal_present": checks.get("fresh_signal_present") is True,
        "ready_for_real_order_action": goal_status.get("ready_for_real_order_action")
        is True,
        "owner_action_required": _owner_action_required(goal_status),
        "blockers": list(goal_status.get("blockers") or []),
        "input_watermark": _source_watermark(goal_status),
        "projection_run_id": projection_run_id,
        "updated_at_ms": updated_at_ms,
    }
    _upsert_by_pk(conn, "brc_goal_status_current", row)


def _owner_action_required(goal_status: dict[str, Any]) -> bool:
    owner_state = _dict(goal_status.get("owner_state"))
    label = str(owner_state.get("label") or "")
    return label == "需要介入" or str(goal_status.get("status") or "") in {
        "hard_safety_stop",
        "deployment_issue",
    }


def _replace_pretrade_readiness_rows(
    conn: sa.engine.Connection,
    rows: list[dict[str, Any]],
) -> None:
    table = _table(conn, "brc_pretrade_readiness_rows")
    conn.execute(table.delete())
    if rows:
        conn.execute(table.insert(), rows)


def _insert_current_snapshots(
    conn: sa.engine.Connection,
    snapshots: list[dict[str, Any]],
) -> None:
    table = _table(conn, "brc_control_read_model_snapshots")
    model_types = sorted({row["model_type"] for row in snapshots})
    for model_type in model_types:
        conn.execute(
            table.update()
            .where(table.c.model_type == model_type)
            .where(table.c.is_current.is_(True))
            .values(is_current=False)
        )
    if snapshots:
        conn.execute(table.insert(), snapshots)


def _upsert_by_pk(
    conn: sa.engine.Connection,
    table_name: str,
    row: dict[str, Any],
) -> None:
    table = _table(conn, table_name)
    pk_columns = list(table.primary_key.columns)
    if len(pk_columns) != 1:
        raise RuntimeError(f"{table_name} must have exactly one primary key")
    pk = pk_columns[0]
    existing = conn.execute(
        sa.select(pk).where(pk == row[pk.name]).limit(1)
    ).scalar_one_or_none()
    if existing is None:
        conn.execute(table.insert().values(**row))
    else:
        conn.execute(table.update().where(pk == row[pk.name]).values(**row))


def _table(conn: sa.engine.Connection, table_name: str) -> sa.Table:
    metadata = sa.MetaData()
    return sa.Table(table_name, metadata, autoload_with=conn)


def _input_watermark(
    control_state: dict[str, Any],
    artifact: dict[str, Any],
) -> dict[str, Any]:
    return {
        "control_state_schema": str(control_state.get("schema") or ""),
        "table_counts": _dict(control_state.get("table_counts")),
        "artifact_schema": str(artifact.get("schema") or ""),
        "artifact_status": str(artifact.get("status") or ""),
        "artifact_generated_at_utc": str(artifact.get("generated_at_utc") or ""),
    }


def _source_watermark(artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": str(artifact.get("schema") or ""),
        "status": str(artifact.get("status") or ""),
        "generated_at_utc": str(artifact.get("generated_at_utc") or ""),
        "payload_hash": _stable_watermark(artifact),
    }


def _stable_watermark(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def _lane_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("strategy_group_id") or ""),
        str(row.get("symbol") or row.get("symbol_or_basket") or ""),
        str(row.get("side") or ""),
    )


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )
    tmp_path.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
