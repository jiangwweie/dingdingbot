from __future__ import annotations

import json
from pathlib import Path

import sqlalchemy as sa
import pytest

from scripts.ops import set_account_risk_policy as subject


def test_shadow_policy_derives_explicit_cluster_memberships_from_pg_registry(
    tmp_path: Path,
    capsys,
) -> None:
    database = tmp_path / "policy.db"
    database_url = f"sqlite:///{database}"
    engine = sa.create_engine(database_url)
    with engine.begin() as conn:
        _create_tables(conn)
        _seed_bound_scope(conn)
        conn.execute(
            sa.text(
                """INSERT INTO brc_symbol_instrument_mappings VALUES
                ('SOLUSDT', 'binance_usdm:SOLUSDT', 'active')"""
            )
        )
        conn.execute(
            sa.text(
                """INSERT INTO brc_exchange_instruments VALUES
                ('binance_usdm:SOLUSDT', 'binance_usdm', 'active')"""
            )
        )

    assert subject.main(_policy_args(database_url, mode="shadow")) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["activation_state"] == "shadow"
    with engine.connect() as conn:
        membership = conn.execute(
            sa.text(
                """SELECT exchange_instrument_id, risk_cluster_id
                FROM brc_risk_cluster_memberships"""
            )
        ).mappings().one()
    assert dict(membership) == {
        "exchange_instrument_id": "binance_usdm:SOLUSDT",
        "risk_cluster_id": "crypto_usd_beta",
    }


def test_rollback_does_not_replace_the_existing_cluster_memberships(
    tmp_path: Path,
) -> None:
    database = tmp_path / "rollback.db"
    database_url = f"sqlite:///{database}"
    engine = sa.create_engine(database_url)
    with engine.begin() as conn:
        _create_tables(conn)
        _seed_bound_scope(conn)
        conn.execute(
            sa.text(
                """INSERT INTO brc_risk_cluster_memberships VALUES
                ('membership-1', 'account-risk-v0-owner-20260714',
                 'binance_usdm:ETHUSDT', 'crypto_usd_beta', 'snapshot-1',
                 'primary', 'active', 1, 'seed')"""
            )
        )

    assert subject.main(
        _policy_args(
            database_url,
            mode="rollback-single-position",
            max_concurrent_positions="1",
        )
    ) == 0
    with engine.connect() as conn:
        count = conn.execute(
            sa.text("SELECT COUNT(*) FROM brc_risk_cluster_memberships")
        ).scalar_one()
        max_positions = conn.execute(
            sa.text("SELECT max_concurrent_positions FROM brc_account_risk_policy_current")
        ).scalar_one()
    assert count == 1
    assert max_positions == 1


def test_policy_command_requires_explicit_risk_values() -> None:
    with pytest.raises(SystemExit):
        subject.main(["--mode", "shadow", "--database-url", "sqlite:///unit.db"])


def test_policy_command_rejects_account_outside_current_runtime_scope(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'mismatch.db'}"
    engine = sa.create_engine(database_url)
    with engine.begin() as conn:
        _create_tables(conn)
        _seed_bound_scope(conn, account_id="other-account")
        conn.execute(
            sa.text(
                """INSERT INTO brc_symbol_instrument_mappings VALUES
                ('SOLUSDT', 'binance_usdm:SOLUSDT', 'active')"""
            )
        )
        conn.execute(
            sa.text(
                """INSERT INTO brc_exchange_instruments VALUES
                ('binance_usdm:SOLUSDT', 'binance_usdm', 'active')"""
            )
        )

    with pytest.raises(
        ValueError,
        match="account_id_not_bound_to_exact_active_runtime_scope",
    ):
        subject.main(_policy_args(database_url, mode="shadow"))

    with engine.connect() as conn:
        assert conn.execute(
            sa.text("SELECT COUNT(*) FROM brc_account_risk_policy_events")
        ).scalar_one() == 0


def _policy_args(
    database_url: str,
    *,
    mode: str,
    max_concurrent_positions: str = "2",
) -> list[str]:
    return [
        "--mode", mode,
        "--database-url", database_url,
        "--account-id", "owner-subaccount-runtime-v0",
        "--runtime-profile-id", "owner-runtime-console-v1",
        "--risk-policy-version", "account-risk-v1-unit",
        "--planned-stop-risk-fraction", "0.025",
        "--max-concurrent-positions", max_concurrent_positions,
        "--max-portfolio-open-risk-fraction", "0.06",
        "--max-cluster-open-risk-fraction", "0.04",
        "--max-portfolio-initial-margin-fraction", "0.90",
        "--max-leverage", "10",
        "--max-new-action-time-lanes", "1",
        "--automatic-downsize-enabled",
        "--unknown-exposure-policy", "global_fail_closed",
    ]


def _seed_bound_scope(
    conn: sa.Connection,
    *,
    account_id: str = "owner-subaccount-runtime-v0",
) -> None:
    conn.execute(
        sa.text(
            """INSERT INTO brc_strategy_group_candidate_scope
            (candidate_scope_id, symbol, asset_class, status, strategy_group_id,
             scope_state)
            VALUES ('scope-1', 'SOLUSDT', 'crypto', 'active', 'SOR-001',
                    'live_submit_allowed')"""
        )
    )
    conn.execute(
        sa.text(
            """INSERT INTO brc_strategy_groups VALUES ('SOR-001', 'SOR-001-v1')"""
        )
    )
    conn.execute(
        sa.text(
            """INSERT INTO brc_strategy_group_versions VALUES
            ('SOR-001-v1', :risk_envelope)"""
        ),
        {"risk_envelope": json.dumps({"account_id": account_id})},
    )
    conn.execute(
        sa.text(
            """INSERT INTO brc_runtime_scope_bindings VALUES
            ('scope-1', 'owner-runtime-console-v1', 'active')"""
        )
    )


def _create_tables(conn: sa.Connection) -> None:
    for statement in (
        """CREATE TABLE brc_account_risk_policy_events (
            account_risk_policy_event_id TEXT PRIMARY KEY, account_id TEXT,
            runtime_profile_id TEXT, event_type TEXT, risk_policy_version TEXT,
            payload JSON, created_at_ms BIGINT, created_by TEXT
        )""",
        """CREATE TABLE brc_account_risk_policy_current (
            account_risk_policy_current_id TEXT PRIMARY KEY, account_id TEXT,
            runtime_profile_id TEXT, risk_policy_version TEXT,
            planned_stop_risk_fraction NUMERIC, max_concurrent_positions INTEGER,
            max_portfolio_open_risk_fraction NUMERIC,
            max_cluster_open_risk_fraction NUMERIC,
            max_portfolio_initial_margin_fraction NUMERIC, max_leverage INTEGER,
            max_new_action_time_lanes INTEGER, automatic_downsize_enabled BOOLEAN,
            unknown_exposure_policy TEXT, activation_state TEXT,
            source_event_id TEXT, updated_at_ms BIGINT
        )""",
        """CREATE TABLE brc_risk_cluster_memberships (
            risk_cluster_membership_id TEXT PRIMARY KEY, risk_policy_version TEXT,
            exchange_instrument_id TEXT, risk_cluster_id TEXT,
            cluster_membership_snapshot_id TEXT, membership_role TEXT, status TEXT,
            created_at_ms BIGINT, created_by TEXT
        )""",
        """CREATE TABLE brc_risk_cluster_membership_snapshots (
            cluster_membership_snapshot_id TEXT PRIMARY KEY,
            risk_policy_version TEXT, primary_risk_cluster_id TEXT,
            semantic_hash TEXT, status TEXT, created_at_ms BIGINT
        )""",
        """CREATE TABLE brc_strategy_group_candidate_scope (
            candidate_scope_id TEXT, symbol TEXT, asset_class TEXT, status TEXT,
            strategy_group_id TEXT, scope_state TEXT
        )""",
        """CREATE TABLE brc_strategy_groups (
            strategy_group_id TEXT, current_version_id TEXT
        )""",
        """CREATE TABLE brc_strategy_group_versions (
            strategy_group_version_id TEXT, risk_envelope JSON
        )""",
        """CREATE TABLE brc_runtime_scope_bindings (
            candidate_scope_id TEXT, runtime_profile_id TEXT, status TEXT
        )""",
        """CREATE TABLE brc_symbol_instrument_mappings (
            symbol TEXT, exchange_instrument_id TEXT, status TEXT
        )""",
        """CREATE TABLE brc_exchange_instruments (
            exchange_instrument_id TEXT, exchange_id TEXT, status TEXT
        )""",
    ):
        conn.execute(sa.text(statement))
