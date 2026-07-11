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
    "brc_ticket_bound_lifecycle_events",
    "brc_ticket_bound_runner_mutation_commands",
    "brc_ticket_bound_exchange_commands",
    "brc_ticket_bound_scope_freezes",
    "brc_ticket_bound_reconciliation_ticks",
    "brc_ticket_bound_post_submit_closures",
    "brc_live_outcome_ledger",
    "brc_goal_status_current",
    "brc_server_monitor_runs",
)
EXCHANGE_COMMAND_HEALTH_COLUMNS = (
    "exchange_command_id",
    "ticket_id",
    "command_kind",
    "command_source",
    "command_state",
    "outcome_class",
    "exchange_result",
    "netting_domain_key",
    "claim_owner",
    "claim_expires_at_ms",
    "updated_at_ms",
)
DOMAIN_HOLD_HEALTH_COLUMNS = (
    "scope_freeze_id",
    "strategy_group_id",
    "symbol",
    "side",
    "source_ticket_id",
    "source_kind",
    "source_id",
    "netting_domain_key",
    "first_blocker",
    "blockers",
    "updated_at_ms",
)
PG_RECENT_WINDOW_MS = 10 * 60 * 1000
LIFECYCLE_ATTENTION_STATUSES = (
    "submit_failed",
    "entry_unknown",
    "entry_orphaned",
    "entry_partial_fill_unhandled",
    "protection_missing",
    "protection_submit_failed",
    "protection_reconciliation_mismatch",
    "tp1_or_sl_orphaned",
    "runner_mutation_pending",
    "runner_mutation_failed",
    "runner_reconciliation_mismatch",
    "position_closed_protection_live",
    "final_exit_unknown",
    "settlement_blocked",
    "review_blocked",
)

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
    (
        "lifecycle_timer_status",
        ("systemctl", "is-active", "brc-ticket-lifecycle-maintenance.timer"),
    ),
    (
        "lifecycle_service_enabled",
        ("systemctl", "is-enabled", "brc-ticket-lifecycle-maintenance.service"),
    ),
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
    if "critical" in statuses:
        status = "critical"
    elif "warn" in statuses or "missing_binary" in statuses:
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
        "status": summary["status"],
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
            "runner_mutation_commands": "brc_ticket_bound_runner_mutation_commands",
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
    submitted_attempts_with_invalid_order_semantics = list(
        conn.execute(
            sa.text(
                """
                WITH submitted_attempts AS (
                  SELECT
                    a.protected_submit_attempt_id,
                    a.ticket_id,
                    a.strategy_group_id,
                    a.symbol,
                    a.side,
                    a.updated_at_ms,
                    a.submit_request,
                    a.submit_result
                  FROM brc_ticket_bound_protected_submit_attempts AS a
                  WHERE a.status = 'submitted'
                    AND a.submit_result->>'status' = 'exchange_submit_orders_submitted'
                ),
                required_roles(role) AS (
                  VALUES ('ENTRY'), ('SL'), ('TP1')
                ),
                role_rows AS (
                  SELECT
                    a.protected_submit_attempt_id,
                    a.ticket_id,
                    a.strategy_group_id,
                    a.symbol,
                    a.side,
                    a.updated_at_ms,
                    rr.role,
                    req.order_json AS request_order,
                    submitted.order_json AS submitted_order,
                    COALESCE(
                      NULLIF(submitted.order_json->>'amount', ''),
                      NULLIF(req.order_json->>'amount', ''),
                      ''
                    ) AS amount_text
                  FROM submitted_attempts AS a
                  CROSS JOIN required_roles AS rr
                  LEFT JOIN LATERAL (
                    SELECT value AS order_json
                    FROM jsonb_array_elements(
                      CASE
                        WHEN jsonb_typeof(a.submit_request->'orders') = 'array'
                        THEN a.submit_request->'orders'
                        ELSE '[]'::jsonb
                      END
                    ) AS value
                    WHERE upper(value->>'order_role') = rr.role
                    LIMIT 1
                  ) AS req ON true
                  LEFT JOIN LATERAL (
                    SELECT value AS order_json
                    FROM jsonb_array_elements(
                      CASE
                        WHEN jsonb_typeof(a.submit_result->'submitted_orders') = 'array'
                        THEN a.submit_result->'submitted_orders'
                        ELSE '[]'::jsonb
                      END
                    ) AS value
                    WHERE upper(value->>'order_role') = rr.role
                    LIMIT 1
                  ) AS submitted ON true
                ),
                issue_rows AS (
                  SELECT
                    protected_submit_attempt_id,
                    ticket_id,
                    strategy_group_id,
                    symbol,
                    side,
                    updated_at_ms,
                    role,
                    array_remove(ARRAY[
                      CASE
                        WHEN request_order IS NULL
                        THEN 'submit_request_' || lower(role) || '_order_missing'
                      END,
                      CASE
                        WHEN submitted_order IS NULL
                        THEN 'submit_result_' || lower(role) || '_order_missing'
                      END,
                      CASE
                        WHEN submitted_order IS NOT NULL
                         AND request_order IS NOT NULL
                         AND COALESCE(submitted_order->>'local_order_id', '')
                             <> COALESCE(request_order->>'local_order_id', '')
                        THEN 'submit_result_' || lower(role) || '_local_order_id_mismatch'
                      END,
                      CASE
                        WHEN submitted_order IS NOT NULL
                         AND COALESCE(submitted_order->>'exchange_order_id', '') = ''
                        THEN 'submit_result_' || lower(role) || '_exchange_order_id_missing'
                      END,
                      CASE
                        WHEN submitted_order IS NOT NULL
                         AND (
                           amount_text = ''
                           OR CASE
                             WHEN amount_text ~ '^[0-9]+(\\.[0-9]+)?$'
                             THEN amount_text::numeric <= 0
                             ELSE true
                           END
                         )
                        THEN 'submit_result_' || lower(role) || '_amount_missing'
                      END,
                      CASE
                        WHEN submitted_order IS NOT NULL
                         AND role = 'ENTRY'
                         AND COALESCE(submitted_order->>'reduce_only', '') <> 'false'
                        THEN 'submit_result_entry_reduce_only_invalid'
                      END,
                      CASE
                        WHEN submitted_order IS NOT NULL
                         AND role = 'ENTRY'
                         AND lower(COALESCE(submitted_order->>'status', '')) IN (
                           'canceled', 'cancelled', 'rejected', 'expired', 'failed'
                         )
                        THEN 'submit_result_entry_terminal_status'
                      END,
                      CASE
                        WHEN submitted_order IS NOT NULL
                         AND role IN ('SL', 'TP1')
                         AND COALESCE(submitted_order->>'reduce_only', '') <> 'true'
                        THEN 'submit_result_' || lower(role) || '_reduce_only_required'
                      END,
                      CASE
                        WHEN submitted_order IS NOT NULL
                         AND role IN ('SL', 'TP1')
                         AND lower(COALESCE(submitted_order->>'status', '')) IN (
                           'canceled', 'cancelled', 'rejected', 'expired', 'failed'
                         )
                        THEN 'submit_result_' || lower(role) || '_terminal_status'
                      END,
                      CASE
                        WHEN submitted_order IS NOT NULL
                         AND role = 'SL'
                         AND COALESCE(
                           NULLIF(submitted_order->>'trigger_price', ''),
                           NULLIF(request_order->>'trigger_price', ''),
                           ''
                         ) = ''
                        THEN 'submit_result_sl_trigger_price_missing'
                      END,
                      CASE
                        WHEN submitted_order IS NOT NULL
                         AND role = 'TP1'
                         AND COALESCE(
                           NULLIF(submitted_order->>'price', ''),
                           NULLIF(request_order->>'price', ''),
                           ''
                         ) = ''
                        THEN 'submit_result_tp1_price_missing'
                      END
                    ], NULL) AS issues
                  FROM role_rows
                )
                SELECT
                  protected_submit_attempt_id,
                  ticket_id,
                  strategy_group_id,
                  symbol,
                  side,
                  updated_at_ms,
                  jsonb_object_agg(role, issues) AS semantic_issues
                FROM issue_rows
                WHERE cardinality(issues) > 0
                GROUP BY
                  protected_submit_attempt_id,
                  ticket_id,
                  strategy_group_id,
                  symbol,
                  side,
                  updated_at_ms
                ORDER BY updated_at_ms DESC
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
    closed_protection_sets_with_live_orders = list(
        conn.execute(
            sa.text(
                """
                SELECT
                  s.exit_protection_set_id,
                  s.ticket_id,
                  s.protected_submit_attempt_id,
                  s.strategy_group_id,
                  s.symbol,
                  s.side,
                  s.updated_at_ms,
                  count(*) AS live_order_count
                FROM brc_ticket_bound_exit_protection_sets AS s
                JOIN brc_ticket_bound_exit_protection_orders AS o
                  ON o.exit_protection_set_id = s.exit_protection_set_id
                 AND o.status IN (
                   'planned', 'submitted', 'open', 'partially_filled',
                   'cancel_pending', 'replace_pending'
                 )
                WHERE s.status = 'closed'
                GROUP BY
                  s.exit_protection_set_id,
                  s.ticket_id,
                  s.protected_submit_attempt_id,
                  s.strategy_group_id,
                  s.symbol,
                  s.side,
                  s.updated_at_ms
                ORDER BY s.updated_at_ms DESC
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
    post_submit_closed_without_lifecycle_evidence_events = list(
        conn.execute(
            sa.text(
                """
                SELECT
                  c.post_submit_closure_id,
                  c.ticket_id,
                  c.protected_submit_attempt_id,
                  c.strategy_group_id,
                  c.symbol,
                  c.side,
                  c.updated_at_ms
                FROM brc_ticket_bound_post_submit_closures AS c
                JOIN brc_ticket_bound_order_lifecycle_runs AS l
                  ON l.protected_submit_attempt_id = c.protected_submit_attempt_id
                WHERE c.status = 'closed'
                  AND (
                    NOT EXISTS (
                      SELECT 1
                      FROM brc_ticket_bound_lifecycle_events AS e
                      WHERE e.lifecycle_run_id = l.lifecycle_run_id
                        AND e.ticket_id = l.ticket_id
                        AND e.protected_submit_attempt_id = l.protected_submit_attempt_id
                        AND e.event_type = 'reconciliation_matched'
                        AND e.event_payload @> '{"final_position_flat_confirmed": true}'::jsonb
                    )
                    OR NOT EXISTS (
                      SELECT 1
                      FROM brc_ticket_bound_lifecycle_events AS e
                      WHERE e.lifecycle_run_id = l.lifecycle_run_id
                        AND e.ticket_id = l.ticket_id
                        AND e.protected_submit_attempt_id = l.protected_submit_attempt_id
                        AND e.event_type = 'budget_settled'
                    )
                    OR NOT EXISTS (
                      SELECT 1
                      FROM brc_ticket_bound_lifecycle_events AS e
                      WHERE e.lifecycle_run_id = l.lifecycle_run_id
                        AND e.ticket_id = l.ticket_id
                        AND e.protected_submit_attempt_id = l.protected_submit_attempt_id
                        AND e.event_type = 'review_recorded'
                    )
                  )
                ORDER BY c.updated_at_ms DESC
                LIMIT 20
                """
            )
        ).mappings()
    )
    runner_mutation_commands_without_runner_proof = list(
        conn.execute(
            sa.text(
                """
                SELECT cmd.runner_mutation_command_id, cmd.ticket_id,
                       cmd.exit_protection_set_id, cmd.protected_submit_attempt_id,
                       cmd.strategy_group_id, cmd.symbol, cmd.side, cmd.status,
                       cmd.updated_at_ms
                FROM brc_ticket_bound_runner_mutation_commands AS cmd
                LEFT JOIN brc_ticket_bound_exit_protection_orders AS runner_sl
                  ON runner_sl.exit_protection_set_id = cmd.exit_protection_set_id
                 AND runner_sl.role = 'RUNNER_SL'
                 AND runner_sl.status IN ('submitted', 'open', 'filled')
                WHERE cmd.status IN ('prepared', 'result_recorded')
                  AND runner_sl.exit_protection_order_id IS NULL
                ORDER BY cmd.updated_at_ms DESC
                LIMIT 20
                """
            )
        ).mappings()
    )
    lifecycle_attention_rows = list(
        conn.execute(
            sa.text(
                """
                SELECT lifecycle_run_id, ticket_id, protected_submit_attempt_id,
                       strategy_group_id, symbol, side, status, first_blocker,
                       blockers, updated_at_ms
                FROM brc_ticket_bound_order_lifecycle_runs
                WHERE status IN :attention_statuses
                ORDER BY updated_at_ms DESC
                LIMIT 20
                """
            ).bindparams(
                sa.bindparam(
                    "attention_statuses",
                    expanding=True,
                )
            ),
            {"attention_statuses": LIFECYCLE_ATTENTION_STATUSES},
        ).mappings()
    )
    exchange_command_critical_rows = _read_exchange_command_critical_rows(
        conn,
        now_ms=now_ms,
    )
    active_domain_holds = _read_active_domain_holds(conn)
    lifecycle_closed_without_live_outcome = list(
        conn.execute(
            sa.text(
                """
                SELECT l.lifecycle_run_id, l.ticket_id,
                       l.protected_submit_attempt_id, l.updated_at_ms
                FROM brc_ticket_bound_order_lifecycle_runs AS l
                LEFT JOIN brc_live_outcome_ledger AS o
                  ON o.ticket_id = l.ticket_id
                WHERE l.status = 'lifecycle_closed'
                  AND o.live_outcome_id IS NULL
                ORDER BY l.updated_at_ms DESC
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
        "submitted_attempts_with_invalid_order_semantics": [
            dict(row) for row in submitted_attempts_with_invalid_order_semantics
        ],
        "incomplete_protection_sets": [dict(row) for row in incomplete_protection_sets],
        "closed_protection_sets_with_live_orders": [
            dict(row) for row in closed_protection_sets_with_live_orders
        ],
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
        "post_submit_closed_without_lifecycle_evidence_events": [
            dict(row) for row in post_submit_closed_without_lifecycle_evidence_events
        ],
        "runner_mutation_commands_without_runner_proof": [
            dict(row) for row in runner_mutation_commands_without_runner_proof
        ],
        "lifecycle_attention_rows": [dict(row) for row in lifecycle_attention_rows],
        "exchange_command_critical_rows": [
            dict(row) for row in exchange_command_critical_rows
        ],
        "active_domain_holds": [dict(row) for row in active_domain_holds],
        "lifecycle_closed_without_live_outcome": [
            dict(row) for row in lifecycle_closed_without_live_outcome
        ],
        "goal": dict(goal or {}),
        "monitor": dict(monitor or {}),
        "unadvanced_fresh_signals": [dict(row) for row in unadvanced_fresh_signals],
        "recent_duplicate_lanes": [dict(row) for row in recent_duplicate_lanes],
    }


def _read_exchange_command_critical_rows(
    conn: sa.engine.Connection,
    *,
    now_ms: int,
) -> list[dict[str, Any]]:
    """Read critical command truth from fields defined by migration 114."""

    columns = ", ".join(EXCHANGE_COMMAND_HEALTH_COLUMNS)
    rows = conn.execute(
        sa.text(
            f"""
            SELECT {columns}
            FROM brc_ticket_bound_exchange_commands
            WHERE command_state IN ('outcome_unknown', 'hard_stopped')
               OR (command_state = 'dispatching'
                   AND claim_expires_at_ms IS NOT NULL
                   AND claim_expires_at_ms <= :now_ms)
            ORDER BY updated_at_ms DESC
            LIMIT 20
            """
        ),
        {"now_ms": now_ms},
    ).mappings()
    results: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        exchange_result = row.get("exchange_result")
        if isinstance(exchange_result, str):
            try:
                exchange_result = json.loads(exchange_result)
            except json.JSONDecodeError:
                exchange_result = {}
        if not isinstance(exchange_result, dict):
            exchange_result = {}
        row["first_blocker"] = str(
            exchange_result.get("error_code")
            or row.get("outcome_class")
            or row.get("command_state")
            or "ticket_bound_exchange_command_critical_state"
        )
        results.append(row)
    return results


def _read_active_domain_holds(
    conn: sa.engine.Connection,
) -> list[dict[str, Any]]:
    """Read source-owned holds from the exact migration 101 + 113 shape."""

    columns = ", ".join(DOMAIN_HOLD_HEALTH_COLUMNS)
    rows = conn.execute(
        sa.text(
            f"""
            SELECT {columns}
            FROM brc_ticket_bound_scope_freezes
            WHERE status = 'active'
            ORDER BY updated_at_ms DESC
            LIMIT 20
            """
        )
    ).mappings()
    return [dict(row) for row in rows]


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
    if snapshot.get("submitted_attempts_with_invalid_order_semantics"):
        issues.append("submitted_attempt_invalid_order_semantics")
    if snapshot.get("incomplete_protection_sets"):
        issues.append("incomplete_ticket_bound_exit_protection_set")
    if snapshot.get("closed_protection_sets_with_live_orders"):
        issues.append("closed_exit_protection_set_with_live_orders")
    if snapshot.get("tp1_filled_without_runner_sl"):
        issues.append("tp1_filled_without_runner_sl")
    if snapshot.get("runner_protected_without_runner_sl"):
        issues.append("runner_protected_without_runner_sl")
    if snapshot.get("lifecycle_closed_without_post_submit_closed"):
        issues.append("lifecycle_closed_without_post_submit_closed")
    if snapshot.get("post_submit_closed_without_lifecycle_closed"):
        issues.append("post_submit_closed_without_lifecycle_closed")
    if snapshot.get("post_submit_closed_without_lifecycle_evidence_events"):
        issues.append("post_submit_closed_without_lifecycle_evidence_events")
    if snapshot.get("runner_mutation_commands_without_runner_proof"):
        issues.append("runner_mutation_command_without_runner_proof")
    if snapshot.get("lifecycle_attention_rows"):
        issues.append("ticket_bound_lifecycle_attention_state")
    if snapshot.get("exchange_command_critical_rows"):
        issues.append("ticket_bound_exchange_command_critical_state")
    if snapshot.get("active_domain_holds"):
        issues.append("active_netting_domain_hold")
    if snapshot.get("lifecycle_closed_without_live_outcome"):
        issues.append("lifecycle_closed_without_live_outcome")

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
    if monitor and monitor.get("status") not in {
        "quiet",
        "notify",
        "notify_sent",
        "notify_suppressed",
    }:
        issues.append("server_monitor_status_not_classified")
    monitor_blocker_classes = _current_monitor_blocker_classes(
        monitor=monitor,
        goal=goal,
        open_counts=snapshot.get("open_counts") or {},
        issues=issues,
    )

    critical_issue_names = {
        "submitted_attempt_without_exit_protection_set",
        "closed_exit_protection_set_with_live_orders",
        "ticket_bound_exchange_command_critical_state",
        "active_netting_domain_hold",
        "lifecycle_closed_without_live_outcome",
    }
    status = (
        "critical"
        if any(issue in critical_issue_names for issue in issues)
        else ("warn" if issues else "ok")
    )
    return {
        "schema": "brc.ops.l2_l7_chain_health_summary.v1",
        "status": status,
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
        "server_monitor_blocker_classes": monitor_blocker_classes,
        "server_monitor_raw_blocker_classes": monitor.get("blocker_classes") or [],
        "unadvanced_fresh_signal_count": len(snapshot.get("unadvanced_fresh_signals") or []),
        "recent_duplicate_lane_count": len(snapshot.get("recent_duplicate_lanes") or []),
        "submitted_attempt_without_protection_count": len(
            snapshot.get("submitted_attempts_without_protection") or []
        ),
        "submitted_attempt_invalid_order_semantics_count": len(
            snapshot.get("submitted_attempts_with_invalid_order_semantics") or []
        ),
        "incomplete_protection_set_count": len(
            snapshot.get("incomplete_protection_sets") or []
        ),
        "closed_protection_set_with_live_order_count": len(
            snapshot.get("closed_protection_sets_with_live_orders") or []
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
        "post_submit_closed_without_lifecycle_evidence_event_count": len(
            snapshot.get("post_submit_closed_without_lifecycle_evidence_events") or []
        ),
        "runner_mutation_command_without_runner_proof_count": len(
            snapshot.get("runner_mutation_commands_without_runner_proof") or []
        ),
        "lifecycle_attention_state_count": len(
            snapshot.get("lifecycle_attention_rows") or []
        ),
        "lifecycle_attention_statuses": sorted(
            {
                str(row.get("status") or "")
                for row in snapshot.get("lifecycle_attention_rows") or []
                if row.get("status")
            }
        ),
        "exchange_command_critical_count": len(
            snapshot.get("exchange_command_critical_rows") or []
        ),
        "active_netting_domain_hold_count": len(
            snapshot.get("active_domain_holds") or []
        ),
        "lifecycle_closed_without_live_outcome_count": len(
            snapshot.get("lifecycle_closed_without_live_outcome") or []
        ),
        "authority_boundary": {
            "readonly_check": True,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "mutates_live_profile_or_sizing": False,
        },
    }


def _current_monitor_blocker_classes(
    *,
    monitor: dict[str, Any],
    goal: dict[str, Any],
    open_counts: dict[str, Any],
    issues: list[str],
) -> list[Any]:
    raw = monitor.get("blocker_classes") or []
    if not raw:
        return []
    if monitor.get("status") == "quiet":
        return []
    has_open_chain_object = any(int(value or 0) for value in open_counts.values())
    chain_issues = [
        issue
        for issue in issues
        if issue
        not in {
            "server_monitor_status_not_classified",
            "server_monitor_forbidden_effect_detected",
        }
    ]
    if (
        monitor.get("status") == "notify"
        and not has_open_chain_object
        and not chain_issues
        and goal.get("status")
        in {"waiting_for_signal", "protected_submit_rehearsal_completed"}
    ):
        return []
    return raw


def _missing_tables(
    conn: sa.engine.Connection, table_names: tuple[str, ...]
) -> list[str]:
    existing = set(sa.inspect(conn).get_table_names())
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
