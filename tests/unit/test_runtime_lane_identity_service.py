from __future__ import annotations

import pytest
import sqlalchemy as sa


def _create_schema(conn: sa.engine.Connection) -> None:
    conn.execute(
        sa.text(
            """
            CREATE TABLE strategy_runtime_instances (
              runtime_instance_id TEXT PRIMARY KEY,
              strategy_family_id TEXT NOT NULL,
              strategy_family_version_id TEXT NOT NULL,
              symbol TEXT NOT NULL,
              side TEXT NOT NULL,
              status TEXT NOT NULL
            )
            """
        )
    )
    conn.execute(
        sa.text(
            """
            CREATE TABLE brc_strategy_group_candidate_scope (
              candidate_scope_id TEXT PRIMARY KEY,
              strategy_group_id TEXT NOT NULL,
              symbol TEXT NOT NULL,
              exchange_instrument_id TEXT NOT NULL,
              asset_class TEXT NOT NULL,
              side TEXT NOT NULL,
              timeframe TEXT NOT NULL,
              policy_current_id TEXT,
              status TEXT NOT NULL
            )
            """
        )
    )
    conn.execute(
        sa.text(
            """
            CREATE TABLE brc_candidate_scope_event_bindings (
              binding_id TEXT PRIMARY KEY,
              candidate_scope_id TEXT NOT NULL,
              event_spec_id TEXT NOT NULL,
              strategy_group_id TEXT NOT NULL,
              symbol TEXT NOT NULL,
              side TEXT NOT NULL,
              status TEXT NOT NULL
            )
            """
        )
    )
    conn.execute(
        sa.text(
            """
            CREATE TABLE brc_strategy_side_event_specs (
              event_spec_id TEXT PRIMARY KEY,
              strategy_group_id TEXT NOT NULL,
              strategy_group_version_id TEXT NOT NULL,
              event_id TEXT NOT NULL,
              side TEXT NOT NULL,
              timeframe TEXT,
              event_spec_version TEXT NOT NULL,
              time_authority TEXT NOT NULL,
              freshness_window_ms INTEGER NOT NULL,
              status TEXT NOT NULL
            )
            """
        )
    )
    conn.execute(
        sa.text(
            """
            CREATE TABLE brc_runtime_scope_bindings (
              runtime_scope_binding_id TEXT PRIMARY KEY,
              candidate_scope_id TEXT NOT NULL,
              strategy_group_id TEXT NOT NULL,
              symbol TEXT NOT NULL,
              side TEXT NOT NULL,
              runtime_profile_id TEXT NOT NULL,
              policy_current_id TEXT NOT NULL,
              status TEXT NOT NULL
            )
            """
        )
    )
    conn.execute(
        sa.text(
            """
            CREATE TABLE brc_owner_policy_current (
              policy_current_id TEXT PRIMARY KEY,
              strategy_group_id TEXT NOT NULL,
              symbol TEXT NOT NULL,
              side TEXT NOT NULL,
              runtime_profile_id TEXT NOT NULL
            )
            """
        )
    )


def _seed(conn: sa.engine.Connection) -> None:
    conn.execute(
        sa.text(
            """
            INSERT INTO strategy_runtime_instances VALUES (
              'runtime-cpm-sol-long', 'CPM-RO-001', 'CPM-RO-001-v0',
              'SOL/USDT:USDT', 'long', 'active'
            )
            """
        )
    )
    conn.execute(
        sa.text(
            """
            INSERT INTO brc_strategy_group_candidate_scope VALUES (
              'scope:CPM-RO-001:SOLUSDT:long', 'CPM-RO-001', 'SOLUSDT',
              'opaque-instrument-sol-perp', 'crypto', 'long', '1h',
              'policy:CPM-RO-001:SOLUSDT:long', 'active'
            )
            """
        )
    )
    conn.execute(
        sa.text(
            """
            INSERT INTO brc_candidate_scope_event_bindings VALUES (
              'binding:CPM-RO-001:SOLUSDT:long:CPM-LONG',
              'scope:CPM-RO-001:SOLUSDT:long',
              'event_spec:CPM-RO-001:CPM-LONG:v2', 'CPM-RO-001', 'SOLUSDT',
              'long', 'active'
            )
            """
        )
    )
    conn.execute(
        sa.text(
            """
            INSERT INTO brc_strategy_side_event_specs VALUES (
              'event_spec:CPM-RO-001:CPM-LONG:v2', 'CPM-RO-001',
              'sgv:CPM-RO-001:v2', 'CPM-LONG', 'long', '1h', 'v2',
              'trigger_candle_close_time_ms', 3600000, 'current'
            )
            """
        )
    )
    conn.execute(
        sa.text(
            """
            INSERT INTO brc_runtime_scope_bindings VALUES (
              'runtime_scope:CPM-RO-001:SOLUSDT:long',
              'scope:CPM-RO-001:SOLUSDT:long', 'CPM-RO-001', 'SOLUSDT', 'long',
              'runtime-profile:pilot', 'policy:CPM-RO-001:SOLUSDT:long', 'active'
            )
            """
        )
    )
    conn.execute(
        sa.text(
            """
            INSERT INTO brc_owner_policy_current VALUES (
              'policy:CPM-RO-001:SOLUSDT:long', 'CPM-RO-001', 'SOLUSDT', 'long',
              'runtime-profile:pilot'
            )
            """
        )
    )


@pytest.fixture
def pg_connection():
    engine = sa.create_engine("sqlite://")
    try:
        with engine.begin() as conn:
            _create_schema(conn)
            _seed(conn)
        with engine.connect() as conn:
            yield conn
    finally:
        engine.dispose()


def _service_module():
    from src.application import runtime_lane_identity_service

    return runtime_lane_identity_service


def _resolve(conn: sa.engine.Connection):
    return _service_module().RuntimeLaneIdentityService().resolve(
        conn,
        runtime_instance_id="runtime-cpm-sol-long",
    )


def test_resolve_exact_active_runtime_lane_identity(pg_connection) -> None:
    resolution = _resolve(pg_connection)

    assert resolution.identity.model_dump() == {
        "candidate_scope_id": "scope:CPM-RO-001:SOLUSDT:long",
        "candidate_scope_event_binding_id": "binding:CPM-RO-001:SOLUSDT:long:CPM-LONG",
        "runtime_scope_binding_id": "runtime_scope:CPM-RO-001:SOLUSDT:long",
        "runtime_instance_id": "runtime-cpm-sol-long",
        "runtime_profile_id": "runtime-profile:pilot",
        "policy_current_id": "policy:CPM-RO-001:SOLUSDT:long",
        "strategy_group_id": "CPM-RO-001",
        "strategy_group_version_id": "sgv:CPM-RO-001:v2",
        "symbol": "SOLUSDT",
        "exchange_instrument_id": "opaque-instrument-sol-perp",
        "asset_class": "crypto",
        "side": "long",
        "event_spec_id": "event_spec:CPM-RO-001:CPM-LONG:v2",
        "event_spec_version": "v2",
        "event_id": "CPM-LONG",
        "timeframe": "1h",
        "time_authority": "trigger_candle_close_time_ms",
    }
    assert resolution.evaluator_version_id == "CPM-RO-001-v0"
    assert resolution.freshness_window_ms == 3_600_000


@pytest.mark.parametrize(
    ("sql", "params", "expected_blocker"),
    [
        (
            "DELETE FROM brc_strategy_group_candidate_scope",
            {},
            "candidate_scope_missing",
        ),
        (
            """
            INSERT INTO brc_candidate_scope_event_bindings VALUES (
              'binding:CPM-RO-001:SOLUSDT:long:extra',
              'scope:CPM-RO-001:SOLUSDT:long',
              'event_spec:CPM-RO-001:CPM-LONG:v2', 'CPM-RO-001', 'SOLUSDT',
              'long', 'active'
            )
            """,
            {},
            "candidate_scope_event_binding_ambiguous",
        ),
        (
            "UPDATE brc_runtime_scope_bindings SET side = 'short'",
            {},
            "runtime_lane_identity_mismatch",
        ),
        (
            "UPDATE strategy_runtime_instances SET symbol = 'AVAX/USDT:USDT'",
            {},
            "runtime_instance_not_selected",
        ),
        (
            "UPDATE brc_strategy_side_event_specs SET side = 'short'",
            {},
            "runtime_lane_identity_mismatch",
        ),
        (
            "UPDATE brc_strategy_side_event_specs SET timeframe = ''",
            {},
            "event_spec_timeframe_missing",
        ),
    ],
)
def test_resolver_fails_closed_for_scope_identity_breaks(
    pg_connection,
    sql: str,
    params: dict[str, object],
    expected_blocker: str,
) -> None:
    pg_connection.execute(sa.text(sql), params)
    module = _service_module()

    with pytest.raises(module.RuntimeLaneIdentityResolutionError) as error:
        _resolve(pg_connection)

    assert error.value.blocker == expected_blocker


def test_monitor_revalidation_rejects_identity_changed_after_evaluation(
    pg_connection,
) -> None:
    from scripts import runtime_active_observation_monitor

    identity = _resolve(pg_connection).identity
    candidate = {
        "runtime_instance_id": identity.runtime_instance_id,
        "strategy_group_id": identity.strategy_group_id,
        "symbol": identity.symbol,
        "side": identity.side,
        "lane_identity": identity.model_dump(),
    }

    assert (
        runtime_active_observation_monitor._revalidate_candidate_runtime_lane_identity(
            pg_connection,
            candidate=candidate,
        )
        is None
    )

    pg_connection.execute(
        sa.text("UPDATE brc_runtime_scope_bindings SET runtime_profile_id = 'changed'")
    )

    assert (
        runtime_active_observation_monitor._revalidate_candidate_runtime_lane_identity(
            pg_connection,
            candidate=candidate,
        )
        == "runtime_lane_identity_mismatch"
    )


def test_same_symbol_two_instruments_do_not_cross_candidate_scope(
    pg_connection,
) -> None:
    pg_connection.execute(
        sa.text(
            """
            INSERT INTO brc_strategy_group_candidate_scope VALUES (
              'scope:CPM-RO-001:SOLUSDT:long:quarterly', 'CPM-RO-001',
              'SOLUSDT', 'opaque-instrument-sol-quarterly', 'crypto', 'long',
              '1h', 'policy:CPM-RO-001:SOLUSDT:long', 'active'
            )
            """
        )
    )
    module = _service_module()

    with pytest.raises(module.RuntimeLaneIdentityResolutionError) as error:
        _resolve(pg_connection)

    assert error.value.blocker == "candidate_scope_ambiguous"
