#!/usr/bin/env python3
"""Append one account-risk policy event through the application service."""

from __future__ import annotations

import argparse
from decimal import Decimal
import json
from pathlib import Path
import sys
import time

import sqlalchemy as sa


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.application.action_time.account_risk_policy import (  # noqa: E402
    AccountRiskPolicy,
    append_account_risk_policy_event,
    replace_risk_cluster_memberships,
)
from src.domain.account_risk import RiskClusterMembership  # noqa: E402


DEFAULT_ACCOUNT_ID = "owner-subaccount-runtime-v0"
DEFAULT_RUNTIME_PROFILE_ID = "runtime-order-capable"
DEFAULT_POLICY_VERSION = "account-risk-v0-owner-20260714"


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    policy, event_type = _policy_for_mode(args.mode)
    engine = sa.create_engine(args.database_url)
    with engine.begin() as conn:
        append_account_risk_policy_event(
            conn,
            account_id=args.account_id,
            runtime_profile_id=args.runtime_profile_id,
            event_type=event_type,
            policy=policy,
            created_by=args.created_by,
            now_ms=int(time.time() * 1000),
        )
        if args.mode in {"shadow", "activate"}:
            replace_risk_cluster_memberships(
                conn,
                risk_policy_version=policy.risk_policy_version,
                memberships=_active_crypto_binance_memberships(conn),
                created_by=args.created_by,
                now_ms=int(time.time() * 1000),
            )
    print(
        json.dumps(
            {
                "status": "account_risk_policy_recorded",
                "mode": args.mode,
                "account_id": args.account_id,
                "runtime_profile_id": args.runtime_profile_id,
                "risk_policy_version": policy.risk_policy_version,
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
    parser.add_argument("--account-id", default=DEFAULT_ACCOUNT_ID)
    parser.add_argument("--runtime-profile-id", default=DEFAULT_RUNTIME_PROFILE_ID)
    parser.add_argument("--created-by", default="codex_account_risk_policy_ops")
    return parser.parse_args(argv)


def _policy_for_mode(mode: str) -> tuple[AccountRiskPolicy, str]:
    activation_state = "shadow" if mode == "shadow" else "active"
    max_positions = 1 if mode == "rollback-single-position" else 2
    return (
        AccountRiskPolicy(
            risk_policy_version=DEFAULT_POLICY_VERSION,
            planned_stop_risk_fraction=Decimal("0.025"),
            max_concurrent_positions=max_positions,
            max_portfolio_open_risk_fraction=Decimal("0.06"),
            max_cluster_open_risk_fraction=Decimal("0.04"),
            max_portfolio_initial_margin_fraction=Decimal("0.90"),
            max_leverage=10,
            max_new_action_time_lanes=1,
            automatic_downsize_enabled=True,
            unknown_exposure_policy="global_fail_closed",
            activation_state=activation_state,
        ),
        {
            "shadow": "shadow_dual_position_v0",
            "activate": "activate_dual_position_v0",
            "rollback-single-position": "rollback_single_position",
        }[mode],
    )


def _active_crypto_binance_memberships(
    conn: sa.Connection,
) -> list[RiskClusterMembership]:
    """Read the current PG Registry, never a JSON/MD symbol list."""

    rows = conn.execute(
        sa.text(
            """
            SELECT DISTINCT mapping.exchange_instrument_id
            FROM brc_strategy_group_candidate_scope AS candidate
            JOIN brc_symbol_instrument_mappings AS mapping
              ON mapping.symbol = candidate.symbol
             AND mapping.status = 'active'
            JOIN brc_exchange_instruments AS instrument
              ON instrument.exchange_instrument_id = mapping.exchange_instrument_id
             AND instrument.status = 'active'
            WHERE candidate.status = 'active'
              AND candidate.asset_class = 'crypto'
              AND instrument.exchange_id = 'binance_usdm'
            ORDER BY mapping.exchange_instrument_id
            """
        )
    ).scalars()
    memberships = [
        RiskClusterMembership(
            exchange_instrument_id=str(instrument_id),
            risk_cluster_id="crypto_usd_beta",
        )
        for instrument_id in rows
        if str(instrument_id or "").strip()
    ]
    if not memberships:
        raise ValueError("active_crypto_binance_instrument_registry_empty")
    return memberships


if __name__ == "__main__":
    raise SystemExit(main())
