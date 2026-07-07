#!/usr/bin/env python3
"""One-shot Tokyo runtime ops health command plan/check helper.

By default this prints the readonly commands an operator should run on Tokyo.
It can execute locally with --execute-local, which is intended for tests and for
running directly on the server. It never mutates runtime state.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

import sqlalchemy as sa


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.pg_dsn import is_sync_postgres_dsn, normalize_sync_postgres_dsn  # noqa: E402


SCHEMA = "brc.ops.tokyo_runtime_ops_health_once.v1"
LOW_PRIORITY_PREFIX = ("timeout", "3s", "ionice", "-c3", "nice", "-n", "19")
PG_ROW_COUNT_TABLES = (
    "brc_runtime_fact_snapshots",
    "brc_watcher_runtime_coverage",
    "brc_server_monitor_runs",
)
L2_L7_CHAIN_TABLES = (
    "brc_strategy_group_candidate_scope",
    "brc_watcher_runtime_coverage",
    "brc_runtime_fact_snapshots",
    "brc_live_signal_events",
    "brc_promotion_candidates",
    "brc_action_time_lane_inputs",
    "brc_action_time_tickets",
    "brc_ticket_bound_protected_submit_attempts",
    "brc_ticket_bound_order_lifecycle_runs",
    "brc_ticket_bound_exit_protection_sets",
    "brc_ticket_bound_exit_protection_orders",
    "brc_ticket_bound_post_submit_closures",
    "brc_goal_status_current",
    "brc_server_monitor_runs",
)
PG_RECENT_WINDOW_MS = 10 * 60 * 1000

COMMANDS = (
    ("disk_df", ("df", "-h")),
    ("inode_df", ("df", "-ih", "/")),
    (
        "reports_du",
        LOW_PRIORITY_PREFIX + ("du", "-sh", "/home/ubuntu/brc-deploy/reports"),
    ),
    (
        "releases_du",
        LOW_PRIORITY_PREFIX + ("du", "-sh", "/home/ubuntu/brc-deploy/releases"),
    ),
    (
        "backups_du",
        LOW_PRIORITY_PREFIX + ("du", "-sh", "/home/ubuntu/brc-deploy/backups"),
    ),
    ("journald_usage", ("journalctl", "--disk-usage")),
    ("backend_status", ("systemctl", "is-active", "brc-owner-console-backend.service")),
    ("watcher_timer_status", ("systemctl", "is-active", "brc-runtime-signal-watcher.timer")),
    ("monitor_timer_status", ("systemctl", "is-active", "brc-runtime-monitor.timer")),
    ("pg_listener", ("ss", "-ltnp")),
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    payload = build_payload(execute_local=args.execute_local)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["status"] != "critical" else 2


def build_payload(*, execute_local: bool) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for name, command in COMMANDS:
        if not execute_local:
            results.append({"name": name, "command": list(command), "status": "planned"})
            continue
        executable = shutil.which(command[0])
        if not executable:
            results.append({"name": name, "command": list(command), "status": "missing_binary"})
            continue
        completed = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=8,
        )
        status = "ok" if completed.returncode == 0 else "warn"
        if completed.returncode == 124 and command[: len(LOW_PRIORITY_PREFIX)] == LOW_PRIORITY_PREFIX:
            status = "skipped_timeout"
        results.append(
            {
                "name": name,
                "command": list(command),
                "status": status,
                "returncode": completed.returncode,
                "stdout_tail": completed.stdout[-2000:],
                "stderr_tail": completed.stderr[-2000:],
            }
        )
    results.append(_pg_runtime_row_counts_result(execute_local=execute_local))
    results.append(_pg_l2_l7_chain_health_result(execute_local=execute_local))
    statuses = {row["status"] for row in results}
    status = "ok"
    if "warn" in statuses or "missing_binary" in statuses:
        status = "warn"
    return {
        "schema": SCHEMA,
        "status": status,
        "mode": "execute_local" if execute_local else "plan_only",
        "results": results,
        "checks": {
            "no_pg_runtime_truth_write": True,
            "no_trade_runtime_mutation": True,
            "pg_row_count_check_is_readonly": True,
            "pg_retention_apply_not_run": True,
            "readonly_commands_only": True,
        },
    }


def _pg_runtime_row_counts_result(*, execute_local: bool) -> dict[str, Any]:
    base = {
        "name": "pg_runtime_row_counts",
        "command": ["internal_sqlalchemy_readonly_row_counts"],
    }
    if not execute_local:
        return {**base, "status": "planned"}
    raw_dsn = os.environ.get("PG_DATABASE_URL") or os.environ.get("DATABASE_URL") or ""
    if not raw_dsn:
        return {**base, "status": "warn", "stderr_tail": "PG_DATABASE_URL missing"}
    database_url = normalize_sync_postgres_dsn(raw_dsn)
    if not is_sync_postgres_dsn(database_url):
        return {**base, "status": "warn", "stderr_tail": "PG DSN is not sync PostgreSQL"}
    engine = sa.create_engine(database_url)
    try:
        with engine.connect() as conn:
            counts = {
                table_name: int(
                    conn.execute(sa.text(f"SELECT count(*) FROM {table_name}")).scalar_one()
                )
                for table_name in PG_ROW_COUNT_TABLES
            }
    except Exception as exc:
        return {
            **base,
            "status": "warn",
            "stderr_tail": f"{type(exc).__name__}: {exc}",
        }
    finally:
        engine.dispose()
    return {
        **base,
        "status": "ok",
        "stdout_tail": "\n".join(
            f"{table_name}={count}" for table_name, count in counts.items()
        ),
        "stderr_tail": "",
    }


def _pg_l2_l7_chain_health_result(*, execute_local: bool) -> dict[str, Any]:
    base = {
        "name": "pg_l2_l7_chain_health",
        "command": ["internal_sqlalchemy_readonly_l2_l7_chain_health"],
    }
    if not execute_local:
        return {**base, "status": "planned"}
    raw_dsn = os.environ.get("PG_DATABASE_URL") or os.environ.get("DATABASE_URL") or ""
    if not raw_dsn:
        return {**base, "status": "warn", "stderr_tail": "PG_DATABASE_URL missing"}
    database_url = normalize_sync_postgres_dsn(raw_dsn)
    if not is_sync_postgres_dsn(database_url):
        return {**base, "status": "warn", "stderr_tail": "PG DSN is not sync PostgreSQL"}
    engine = sa.create_engine(database_url)
    try:
        with engine.connect() as conn:
            snapshot = _read_l2_l7_chain_snapshot(conn)
    except Exception as exc:
        return {
            **base,
            "status": "warn",
            "stderr_tail": f"{type(exc).__name__}: {exc}",
        }
    finally:
        engine.dispose()
    summary = summarize_l2_l7_chain_snapshot(snapshot)
    return {
        **base,
        "status": "ok" if not summary["issues"] else "warn",
        "stdout_tail": json.dumps(summary, ensure_ascii=False, sort_keys=True)[-4000:],
        "stderr_tail": "",
    }


def _read_l2_l7_chain_snapshot(conn: sa.engine.Connection) -> dict[str, Any]:
    now_ms = int(os.environ.get("BRC_OPS_HEALTH_NOW_MS") or 0) or _now_ms()
    since_ms = now_ms - PG_RECENT_WINDOW_MS
    missing_tables = _missing_tables(conn, L2_L7_CHAIN_TABLES)
    if missing_tables:
        return {
            "now_ms": now_ms,
            "since_ms": since_ms,
            "missing_tables": missing_tables,
        }

    missing_coverage = list(
        conn.execute(
            sa.text(
                """
                SELECT
                  c.candidate_scope_id,
                  c.strategy_group_id,
                  c.symbol,
                  c.side,
                  c.scope_state,
                  c.observation_scope
                FROM brc_strategy_group_candidate_scope AS c
                LEFT JOIN brc_watcher_runtime_coverage AS w
                  ON w.strategy_group_id = c.strategy_group_id
                 AND w.symbol = c.symbol
                 AND w.side = c.side
                 AND w.is_current = true
                 AND w.coverage_state = 'covered'
                 AND w.liveness_state = 'active'
                 AND w.valid_until_ms > :now_ms
                WHERE c.status = 'active'
                  AND (c.valid_until_ms IS NULL OR c.valid_until_ms > :now_ms)
                  AND c.observation_scope <> 'none'
                  AND w.runtime_coverage_id IS NULL
                ORDER BY c.strategy_group_id, c.symbol, c.side
                """
            ),
            {"now_ms": now_ms},
        ).mappings()
    )
    coverage_by_group = list(
        conn.execute(
            sa.text(
                """
                SELECT
                  strategy_group_id,
                  count(*) AS current_count,
                  min(valid_until_ms) AS min_valid_until_ms,
                  max(last_tick_at_ms) AS max_last_tick_at_ms
                FROM brc_watcher_runtime_coverage
                WHERE is_current = true
                  AND coverage_state = 'covered'
                  AND liveness_state = 'active'
                GROUP BY strategy_group_id
                ORDER BY strategy_group_id
                """
            )
        ).mappings()
    )
    recent_counts = {
        name: int(
            conn.execute(
                sa.text(f"SELECT count(*) FROM {table_name} WHERE created_at_ms >= :since_ms"),
                {"since_ms": since_ms},
            ).scalar_one()
        )
        for name, table_name in {
            "facts": "brc_runtime_fact_snapshots",
            "signals": "brc_live_signal_events",
            "promotions": "brc_promotion_candidates",
            "lanes": "brc_action_time_lane_inputs",
            "tickets": "brc_action_time_tickets",
            "attempts": "brc_ticket_bound_protected_submit_attempts",
            "lifecycle_runs": "brc_ticket_bound_order_lifecycle_runs",
            "protection_sets": "brc_ticket_bound_exit_protection_sets",
            "protection_orders": "brc_ticket_bound_exit_protection_orders",
            "post_submit_closures": "brc_ticket_bound_post_submit_closures",
            "monitor": "brc_server_monitor_runs",
        }.items()
    }
    open_counts = {
        "promotions": int(
            conn.execute(
                sa.text(
                    """
                    SELECT count(*)
                    FROM brc_promotion_candidates
                    WHERE status NOT IN (
                      'closed', 'expired', 'superseded', 'rejected',
                      'arbitration_lost', 'blocked'
                    )
                    """
                )
            ).scalar_one()
        ),
        "lanes": int(
            conn.execute(
                sa.text(
                    """
                    SELECT count(*)
                    FROM brc_action_time_lane_inputs
                    WHERE status NOT IN ('closed', 'expired', 'superseded', 'rejected')
                    """
                )
            ).scalar_one()
        ),
        "tickets": int(
            conn.execute(
                sa.text(
                    """
                    SELECT count(*)
                    FROM brc_action_time_tickets
                    WHERE status NOT IN ('closed', 'expired', 'superseded', 'rejected')
                    """
                )
            ).scalar_one()
        ),
        "attempts": int(
            conn.execute(
                sa.text(
                    """
                    SELECT count(*)
                    FROM brc_ticket_bound_protected_submit_attempts
                    WHERE status NOT IN (
                      'disabled_smoke_passed', 'blocked', 'failed',
                      'submitted', 'expired'
                    )
                    """
                )
            ).scalar_one()
        ),
    }
    submitted_attempts_without_protection = list(
        conn.execute(
            sa.text(
                """
                SELECT a.protected_submit_attempt_id, a.ticket_id,
                       a.strategy_group_id, a.symbol, a.side, a.updated_at_ms
                FROM brc_ticket_bound_protected_submit_attempts AS a
                LEFT JOIN brc_ticket_bound_exit_protection_sets AS s
                  ON s.protected_submit_attempt_id = a.protected_submit_attempt_id
                 AND s.protection_complete = true
                WHERE a.status = 'submitted'
                  AND s.exit_protection_set_id IS NULL
                ORDER BY a.updated_at_ms DESC
                LIMIT 20
                """
            )
        ).mappings()
    )
    incomplete_protection_sets = list(
        conn.execute(
            sa.text(
                """
                SELECT exit_protection_set_id, ticket_id, protected_submit_attempt_id,
                       strategy_group_id, symbol, side, status, protection_complete,
                       first_blocker, updated_at_ms
                FROM brc_ticket_bound_exit_protection_sets
                WHERE protection_complete = false
                   OR status NOT IN ('submitted', 'reconciled', 'runner_protected', 'closed')
                ORDER BY updated_at_ms DESC
                LIMIT 20
                """
            )
        ).mappings()
    )
    tp1_filled_without_runner_sl = list(
        conn.execute(
            sa.text(
                """
                SELECT s.exit_protection_set_id, s.ticket_id,
                       s.protected_submit_attempt_id, s.strategy_group_id,
                       s.symbol, s.side, s.status AS set_status,
                       tp1.status AS tp1_status, tp1.updated_at_ms AS tp1_updated_at_ms
                FROM brc_ticket_bound_exit_protection_sets AS s
                JOIN brc_ticket_bound_exit_protection_orders AS tp1
                  ON tp1.exit_protection_set_id = s.exit_protection_set_id
                 AND tp1.role = 'TP1'
                 AND tp1.status = 'filled'
                LEFT JOIN brc_ticket_bound_exit_protection_orders AS runner_sl
                  ON runner_sl.exit_protection_set_id = s.exit_protection_set_id
                 AND runner_sl.role = 'RUNNER_SL'
                 AND runner_sl.status IN ('submitted', 'open', 'filled')
                WHERE s.status NOT IN ('runner_protected', 'closed')
                  AND runner_sl.exit_protection_order_id IS NULL
                ORDER BY tp1.updated_at_ms DESC
                LIMIT 20
                """
            )
        ).mappings()
    )
    runner_protected_without_runner_sl = list(
        conn.execute(
            sa.text(
                """
                SELECT s.exit_protection_set_id, s.ticket_id,
                       s.protected_submit_attempt_id, s.strategy_group_id,
                       s.symbol, s.side, s.status AS set_status, s.updated_at_ms
                FROM brc_ticket_bound_exit_protection_sets AS s
                LEFT JOIN brc_ticket_bound_exit_protection_orders AS runner_sl
                  ON runner_sl.exit_protection_set_id = s.exit_protection_set_id
                 AND runner_sl.role = 'RUNNER_SL'
                 AND runner_sl.status IN ('submitted', 'open', 'filled')
                WHERE s.status = 'runner_protected'
                  AND runner_sl.exit_protection_order_id IS NULL
                ORDER BY s.updated_at_ms DESC
                LIMIT 20
                """
            )
        ).mappings()
    )
    lifecycle_closed_without_post_submit_closed = list(
        conn.execute(
            sa.text(
                """
                SELECT l.lifecycle_run_id, l.ticket_id, l.protected_submit_attempt_id,
                       l.strategy_group_id, l.symbol, l.side, l.updated_at_ms
                FROM brc_ticket_bound_order_lifecycle_runs AS l
                LEFT JOIN brc_ticket_bound_post_submit_closures AS c
                  ON c.protected_submit_attempt_id = l.protected_submit_attempt_id
                 AND c.status = 'closed'
                WHERE l.status = 'lifecycle_closed'
                  AND c.post_submit_closure_id IS NULL
                ORDER BY l.updated_at_ms DESC
                LIMIT 20
                """
            )
        ).mappings()
    )
    post_submit_closed_without_lifecycle_closed = list(
        conn.execute(
            sa.text(
                """
                SELECT c.post_submit_closure_id, c.ticket_id,
                       c.protected_submit_attempt_id, c.strategy_group_id,
                       c.symbol, c.side, c.updated_at_ms,
                       l.status AS lifecycle_status
                FROM brc_ticket_bound_post_submit_closures AS c
                LEFT JOIN brc_ticket_bound_order_lifecycle_runs AS l
                  ON l.protected_submit_attempt_id = c.protected_submit_attempt_id
                WHERE c.status = 'closed'
                  AND COALESCE(l.status, '') <> 'lifecycle_closed'
                ORDER BY c.updated_at_ms DESC
                LIMIT 20
                """
            )
        ).mappings()
    )
    goal = conn.execute(
        sa.text(
            """
            SELECT status, fresh_signal_present, ready_for_real_order_action,
                   owner_action_required, blockers, updated_at_ms
            FROM brc_goal_status_current
            ORDER BY updated_at_ms DESC
            LIMIT 1
            """
        )
    ).mappings().first()
    monitor = conn.execute(
        sa.text(
            """
            SELECT status, quiet_reason, notify_reason, blocker_classes,
                   forbidden_effects, created_at_ms
            FROM brc_server_monitor_runs
            ORDER BY created_at_ms DESC
            LIMIT 1
            """
        )
    ).mappings().first()
    unadvanced_fresh_signals = list(
        conn.execute(
            sa.text(
                """
                SELECT e.signal_event_id, e.strategy_group_id, e.symbol, e.side,
                       e.status, e.freshness_state, e.event_time_ms, e.expires_at_ms
                FROM brc_live_signal_events AS e
                LEFT JOIN brc_promotion_candidates AS p
                  ON p.signal_event_id = e.signal_event_id
                LEFT JOIN brc_action_time_lane_inputs AS l
                  ON l.signal_event_id = e.signal_event_id
                LEFT JOIN brc_action_time_tickets AS t
                  ON t.signal_event_id = e.signal_event_id
                WHERE e.status = 'facts_validated'
                  AND e.freshness_state = 'fresh'
                  AND e.expires_at_ms > :now_ms
                  AND p.promotion_candidate_id IS NULL
                  AND l.action_time_lane_input_id IS NULL
                  AND t.ticket_id IS NULL
                ORDER BY e.created_at_ms DESC
                LIMIT 20
                """
            ),
            {"now_ms": now_ms},
        ).mappings()
    )
    recent_duplicate_lanes = list(
        conn.execute(
            sa.text(
                """
                SELECT signal_event_id, count(*) AS lane_count, max(created_at_ms) AS latest_lane_ms
                FROM brc_action_time_lane_inputs
                GROUP BY signal_event_id
                HAVING count(*) > 1
                   AND max(created_at_ms) >= :since_ms
                ORDER BY latest_lane_ms DESC
                LIMIT 20
                """
            ),
            {"since_ms": since_ms},
        ).mappings()
    )
    return {
        "now_ms": now_ms,
        "since_ms": since_ms,
        "missing_tables": [],
        "missing_coverage": [dict(row) for row in missing_coverage],
        "coverage_by_group": [dict(row) for row in coverage_by_group],
        "recent_counts": recent_counts,
        "open_counts": open_counts,
        "submitted_attempts_without_protection": [
            dict(row) for row in submitted_attempts_without_protection
        ],
        "incomplete_protection_sets": [dict(row) for row in incomplete_protection_sets],
        "tp1_filled_without_runner_sl": [
            dict(row) for row in tp1_filled_without_runner_sl
        ],
        "runner_protected_without_runner_sl": [
            dict(row) for row in runner_protected_without_runner_sl
        ],
        "lifecycle_closed_without_post_submit_closed": [
            dict(row) for row in lifecycle_closed_without_post_submit_closed
        ],
        "post_submit_closed_without_lifecycle_closed": [
            dict(row) for row in post_submit_closed_without_lifecycle_closed
        ],
        "goal": dict(goal or {}),
        "monitor": dict(monitor or {}),
        "unadvanced_fresh_signals": [dict(row) for row in unadvanced_fresh_signals],
        "recent_duplicate_lanes": [dict(row) for row in recent_duplicate_lanes],
    }


def summarize_l2_l7_chain_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    issues: list[str] = []
    if snapshot.get("missing_tables"):
        issues.append("missing_pg_tables")
    if snapshot.get("missing_coverage"):
        issues.append("active_candidate_scope_without_current_coverage")
    if snapshot.get("unadvanced_fresh_signals"):
        issues.append("fresh_signal_without_promotion_lane_or_ticket")
    if snapshot.get("recent_duplicate_lanes"):
        issues.append("recent_duplicate_action_time_lane_for_same_signal")
    if snapshot.get("submitted_attempts_without_protection"):
        issues.append("submitted_attempt_without_exit_protection_set")
    if snapshot.get("incomplete_protection_sets"):
        issues.append("incomplete_ticket_bound_exit_protection_set")
    if snapshot.get("tp1_filled_without_runner_sl"):
        issues.append("tp1_filled_without_runner_sl")
    if snapshot.get("runner_protected_without_runner_sl"):
        issues.append("runner_protected_without_runner_sl")
    if snapshot.get("lifecycle_closed_without_post_submit_closed"):
        issues.append("lifecycle_closed_without_post_submit_closed")
    if snapshot.get("post_submit_closed_without_lifecycle_closed"):
        issues.append("post_submit_closed_without_lifecycle_closed")

    goal = snapshot.get("goal") or {}
    blockers = goal.get("blockers") or []
    blocker_text = json.dumps(blockers, ensure_ascii=False, sort_keys=True)
    if "action_time_preflight_ready" in blocker_text:
        issues.append("goal_status_ready_pseudo_blocker")
    if goal.get("status") == "protected_submit_rehearsal_completed" and any(
        int(value or 0) for value in (snapshot.get("open_counts") or {}).values()
    ):
        issues.append("terminal_goal_status_with_open_l2_l7_objects")

    monitor = snapshot.get("monitor") or {}
    forbidden_effects = monitor.get("forbidden_effects") or {}
    if any(bool(value) for value in forbidden_effects.values()):
        issues.append("server_monitor_forbidden_effect_detected")
    if monitor and monitor.get("status") not in {"quiet", "notify_sent", "notify_suppressed"}:
        issues.append("server_monitor_status_not_classified")

    return {
        "schema": "brc.ops.l2_l7_chain_health_summary.v1",
        "status": "ok" if not issues else "warn",
        "issues": issues,
        "now_ms": snapshot.get("now_ms"),
        "since_ms": snapshot.get("since_ms"),
        "coverage_by_group": snapshot.get("coverage_by_group", []),
        "missing_coverage_count": len(snapshot.get("missing_coverage") or []),
        "recent_counts": snapshot.get("recent_counts", {}),
        "open_counts": snapshot.get("open_counts", {}),
        "goal_status": goal.get("status"),
        "goal_blockers": blockers,
        "server_monitor_status": monitor.get("status"),
        "server_monitor_blocker_classes": monitor.get("blocker_classes") or [],
        "unadvanced_fresh_signal_count": len(snapshot.get("unadvanced_fresh_signals") or []),
        "recent_duplicate_lane_count": len(snapshot.get("recent_duplicate_lanes") or []),
        "submitted_attempt_without_protection_count": len(
            snapshot.get("submitted_attempts_without_protection") or []
        ),
        "incomplete_protection_set_count": len(
            snapshot.get("incomplete_protection_sets") or []
        ),
        "tp1_filled_without_runner_sl_count": len(
            snapshot.get("tp1_filled_without_runner_sl") or []
        ),
        "runner_protected_without_runner_sl_count": len(
            snapshot.get("runner_protected_without_runner_sl") or []
        ),
        "lifecycle_closed_without_post_submit_closed_count": len(
            snapshot.get("lifecycle_closed_without_post_submit_closed") or []
        ),
        "post_submit_closed_without_lifecycle_closed_count": len(
            snapshot.get("post_submit_closed_without_lifecycle_closed") or []
        ),
        "authority_boundary": {
            "readonly_check": True,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "mutates_live_profile_or_sizing": False,
        },
    }


def _missing_tables(
    conn: sa.engine.Connection, table_names: tuple[str, ...]
) -> list[str]:
    existing = set(
        conn.execute(
            sa.text(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = :schema
                  AND table_name LIKE :pattern
                """
            ),
            {"schema": "public", "pattern": "brc_%"},
        ).scalars()
    )
    return [table_name for table_name in table_names if table_name not in existing]


def _now_ms() -> int:
    import time

    return int(time.time() * 1000)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-local", action="store_true")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
