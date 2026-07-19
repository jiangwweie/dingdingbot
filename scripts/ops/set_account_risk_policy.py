#!/usr/bin/env python3
"""Append one account-risk policy event through the application service."""

from __future__ import annotations

import argparse
from decimal import Decimal
import json
from pathlib import Path
import sys
import time
from uuid import uuid4

import sqlalchemy as sa


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.application.action_time.account_risk_policy import (  # noqa: E402
    AccountRiskPolicy,
    append_account_risk_policy_event,
    load_account_risk_policy_current_projection,
    replace_risk_cluster_memberships,
)
from src.application.action_time.risk_cluster_membership import (  # noqa: E402
    build_runtime_scope_primary_cluster_memberships,
)
from scripts.pg_dsn import normalize_sync_postgres_dsn  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    policy, event_type = _policy_from_args(args)
    engine = sa.create_engine(normalize_sync_postgres_dsn(args.database_url))
    with engine.begin() as conn:
        now_ms = int(time.time() * 1000)
        _require_exact_active_runtime_scope(
            conn,
            account_id=args.account_id,
            runtime_profile_id=args.runtime_profile_id,
        )
        memberships = None
        if args.mode in {"shadow", "activate"}:
            memberships = build_runtime_scope_primary_cluster_memberships(
                conn,
                runtime_profile_id=args.runtime_profile_id,
                risk_policy_version=policy.risk_policy_version,
                now_ms=now_ms,
                expected_instrument_count=6,
            )
        append_account_risk_policy_event(
            conn,
            account_id=args.account_id,
            runtime_profile_id=args.runtime_profile_id,
            event_type=event_type,
            policy=policy,
            created_by=args.created_by,
            now_ms=now_ms,
            operation_id=args.operation_id,
        )
        if args.mode in {"shadow", "activate"}:
            assert memberships is not None
            replace_risk_cluster_memberships(
                conn,
                risk_policy_version=policy.risk_policy_version,
                memberships=memberships,
                created_by=args.created_by,
                now_ms=now_ms,
            )
        current = load_account_risk_policy_current_projection(
            conn,
            account_id=args.account_id,
            runtime_profile_id=args.runtime_profile_id,
        )
    print(
        json.dumps(
            {
                "status": "account_risk_policy_recorded",
                "mode": args.mode,
                "account_id": args.account_id,
                "runtime_profile_id": args.runtime_profile_id,
                "risk_policy_version": policy.risk_policy_version,
                "account_risk_policy_event_id": (
                    current.source_event_id if current is not None else None
                ),
                "activation_state": policy.activation_state,
                "max_concurrent_positions": policy.max_concurrent_positions,
            },
            sort_keys=True,
        )
    )
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        required=True,
        choices=("shadow", "activate", "rollback-single-position"),
    )
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--runtime-profile-id", required=True)
    parser.add_argument("--risk-policy-version", required=True)
    parser.add_argument("--planned-stop-risk-fraction", type=Decimal, required=True)
    parser.add_argument("--max-concurrent-positions", type=int, choices=(1, 2), required=True)
    parser.add_argument("--max-portfolio-open-risk-fraction", type=Decimal, required=True)
    parser.add_argument("--max-cluster-open-risk-fraction", type=Decimal, required=True)
    parser.add_argument(
        "--max-portfolio-initial-margin-fraction",
        type=Decimal,
        required=True,
    )
    parser.add_argument("--max-leverage", type=int, required=True)
    parser.add_argument("--max-new-action-time-lanes", type=int, choices=(1,), required=True)
    downsize = parser.add_mutually_exclusive_group(required=True)
    downsize.add_argument(
        "--automatic-downsize-enabled",
        dest="automatic_downsize_enabled",
        action="store_true",
    )
    downsize.add_argument(
        "--no-automatic-downsize",
        dest="automatic_downsize_enabled",
        action="store_false",
    )
    parser.add_argument(
        "--unknown-exposure-policy",
        choices=("global_fail_closed",),
        required=True,
    )
    parser.add_argument("--created-by", default="codex_account_risk_policy_ops")
    parser.add_argument("--operation-id", default=uuid4().hex)
    return parser.parse_args(argv)


def _policy_from_args(args: argparse.Namespace) -> tuple[AccountRiskPolicy, str]:
    activation_state = "shadow" if args.mode == "shadow" else "active"
    if args.mode == "rollback-single-position" and args.max_concurrent_positions != 1:
        raise ValueError("rollback-single-position requires max_concurrent_positions=1")
    return (
        AccountRiskPolicy(
            risk_policy_version=args.risk_policy_version,
            planned_stop_risk_fraction=args.planned_stop_risk_fraction,
            max_concurrent_positions=args.max_concurrent_positions,
            max_portfolio_open_risk_fraction=args.max_portfolio_open_risk_fraction,
            max_cluster_open_risk_fraction=args.max_cluster_open_risk_fraction,
            max_portfolio_initial_margin_fraction=(
                args.max_portfolio_initial_margin_fraction
            ),
            max_leverage=args.max_leverage,
            max_new_action_time_lanes=args.max_new_action_time_lanes,
            automatic_downsize_enabled=args.automatic_downsize_enabled,
            unknown_exposure_policy=args.unknown_exposure_policy,
            activation_state=activation_state,
        ),
        {
            "shadow": "shadow_dual_position_v0",
            "activate": "activate_dual_position_v0",
            "rollback-single-position": "rollback_single_position",
        }[args.mode],
    )


def _require_exact_active_runtime_scope(
    conn: sa.Connection,
    *,
    account_id: str,
    runtime_profile_id: str,
) -> None:
    """Reject policy writes that do not match the current runtime authority."""

    rows = conn.execute(
        sa.text(
            """
            SELECT DISTINCT version.risk_envelope
            FROM brc_runtime_scope_bindings AS runtime
            JOIN brc_strategy_group_candidate_scope AS candidate
              ON candidate.candidate_scope_id = runtime.candidate_scope_id
            JOIN brc_strategy_groups AS strategy_group
              ON strategy_group.strategy_group_id = candidate.strategy_group_id
            JOIN brc_strategy_group_versions AS version
              ON version.strategy_group_version_id = strategy_group.current_version_id
            WHERE runtime.status = 'active'
              AND candidate.status = 'active'
              AND candidate.scope_state = 'live_submit_allowed'
              AND runtime.runtime_profile_id = :runtime_profile_id
            """
        ),
        {"runtime_profile_id": runtime_profile_id},
    ).scalars()
    scope_account_ids = {
        str(_json_object(value).get("account_id") or "").strip()
        for value in rows
    }
    if scope_account_ids != {account_id}:
        raise ValueError("account_id_not_bound_to_exact_active_runtime_scope")


def _json_object(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(str(value or ""))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


if __name__ == "__main__":
    raise SystemExit(main())
