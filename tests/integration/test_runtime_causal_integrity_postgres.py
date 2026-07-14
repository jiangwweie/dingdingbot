from __future__ import annotations

import asyncio
from decimal import Decimal
import multiprocessing

import pytest
from sqlalchemy import text

from src.application.action_time import action_time_ticket as ticket_materializer
from src.application.action_time import finalgate_preflight as finalgate
from src.application.action_time import operation_layer_handoff as handoff
from src.application.action_time import runtime_safety_state as safety
from src.application.action_time.action_time_invocation import (
    load_action_time_invocation,
    start_action_time_invocation,
)
from src.application.action_time.exchange_command_worker import (
    run_one_ticket_bound_exchange_command,
)
from src.application.action_time.exit_protection_materializer import (
    materialize_ticket_bound_exit_protection_set,
)
from src.application.action_time.protected_submit_attempt import (
    record_ticket_bound_protected_submit_result,
)
from src.application.action_time.runner_mutation_command import (
    prepare_ticket_bound_runner_mutation_command,
)
from src.application.action_time.ticket_bound_fill_projector import (
    project_ticket_bound_exchange_fills,
)
from src.application.readmodels import strategy_live_candidate_pool
from src.application.runtime_process_outcome import (
    materialize_runtime_process_outcome,
)
from src.infrastructure.runtime_control_state_repository import (
    PgBackedRuntimeControlStateRepository,
)
from src.application.action_time.ticket_materialization_sequence import (
    materialize_action_time_ticket_sequence,
)
from tests.integration.runtime_causal_integrity_pg_support import (
    FakeExchangeLedgerGateway,
    claim_then_hold_process,
    postgres_certification_engine,
    postgres_certification_template,
    run_fake_exchange_worker_process,
)
from tests.unit.test_action_time_ticket_materialization import NOW_MS
from tests.unit.test_action_time_ticket_materialization_sequence import (
    _bind_fresh_invocation_account_facts,
    _projection_ready,
)
from tests.unit.test_pg_promotion_action_time_lane_materialization import (
    _insert_ready_fresh_signal,
)
from tests.unit.test_ticket_bound_protected_submit_attempt import (
    _prepare_real_submit,
    _submitted_orders,
)
from tests.unit.test_ticket_bound_runtime_safety_state_materialization import (
    _insert_action_time_lane_graph,
)


@pytest.fixture(autouse=True)
def _preserve_release_b_baseline_for_legacy_rci_scenarios(
    request,
    postgres_certification_engine,
):
    """Keep pre-canary causal tests on the disabled Release B contract."""

    release_c_tests = {
        "test_rci_harness_uses_postgresql_revision_123",
        "test_rci_exit_policy_canary_is_exactly_scoped_and_enabled",
    }
    if request.node.name not in release_c_tests:
        with postgres_certification_engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE brc_runtime_capabilities_current "
                    "SET status = 'disabled', "
                    "certification_ref = 'rci:release-b-disabled-baseline' "
                    "WHERE capability_id = 'ticket_exit_policy_v1'"
                )
            )
    yield


def test_rci_harness_uses_postgresql_revision_123(
    postgres_certification_engine,
):
    assert postgres_certification_engine.dialect.name == "postgresql"
    with postgres_certification_engine.connect() as conn:
        revision = conn.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one()
        invocation_table = conn.execute(
            text(
                "SELECT to_regclass('public.brc_action_time_invocations')"
            )
        ).scalar_one()

    assert revision == "123"
    assert invocation_table == "brc_action_time_invocations"


def test_rci_exit_policy_canary_is_exactly_scoped_and_enabled(
    postgres_certification_engine,
):
    with postgres_certification_engine.connect() as conn:
        capability = conn.execute(
            text(
                "SELECT status, certification_ref "
                "FROM brc_runtime_capabilities_current "
                "WHERE capability_id = 'ticket_exit_policy_v1'"
            )
        ).mappings().one()
        current_policies = list(
            conn.execute(
            text(
                "SELECT strategy_group_id, event_spec_id, side, payload_hash "
                "FROM brc_strategy_exit_policies "
                "WHERE status = 'current'"
            )
            ).mappings()
        )

    assert capability["status"] == "enabled"
    assert "migration-123:sor-long-canary" in capability["certification_ref"]
    assert current_policies == [
        {
            "strategy_group_id": "SOR-001",
            "event_spec_id": "event_spec:SOR-001:SOR-LONG:v2",
            "side": "long",
            "payload_hash": (
                "324b2be50b3e1f020837e0f4687e76339a52dd757b272d4336b20de196bef02b"
            ),
        }
    ]


def _prepare_exchange_commands_on_connection(conn) -> tuple[dict, dict]:
    lane_id = _insert_action_time_lane_graph(conn)
    ticket = ticket_materializer.materialize_action_time_ticket(
        conn,
        now_ms=NOW_MS,
    )
    assert ticket["status"] == "action_time_ticket_created", ticket
    ticket_id = str(ticket["ticket_id"])
    preflight = finalgate.materialize_action_time_finalgate_preflight(
        conn,
        ticket_id=ticket_id,
        now_ms=NOW_MS + 1_000,
    )
    assert preflight["status"] == "finalgate_ready", preflight
    operation_handoff = handoff.materialize_action_time_operation_layer_handoff(
        conn,
        ticket_id=ticket_id,
        finalgate_pass_id=str(preflight["finalgate_pass_id"]),
        now_ms=NOW_MS + 2_000,
    )
    assert operation_handoff["status"] == "operation_layer_handoff_ready", (
        operation_handoff
    )
    conn.execute(
        text(
            "UPDATE brc_runtime_capabilities_current "
            "SET status = 'enabled', "
            "certification_ref = 'rci-test:ticket-lifecycle', "
            "updated_at_ms = :now_ms "
            "WHERE capability_id = 'ticket_lifecycle_durable_mutation'"
        ),
        {"now_ms": NOW_MS + 2_500},
    )
    runtime_safety = safety.materialize_ticket_bound_runtime_safety_state(
        conn,
        ticket_id=ticket_id,
        operation_layer_handoff_id=str(
            operation_handoff["operation_layer_handoff_id"]
        ),
        now_ms=NOW_MS + 3_000,
    )
    assert runtime_safety["submit_allowed"] is True, runtime_safety
    ids = {
        "lane_id": lane_id,
        "ticket_id": ticket_id,
        "finalgate_pass_id": str(preflight["finalgate_pass_id"]),
        "operation_layer_handoff_id": str(
            operation_handoff["operation_layer_handoff_id"]
        ),
        "operation_submit_command_id": str(
            operation_handoff["operation_submit_command_id"]
        ),
    }
    prepared = _prepare_real_submit(conn, ids)
    return ids, prepared


def _prepare_exchange_commands(engine) -> None:
    with engine.connect() as conn:
        _prepare_exchange_commands_on_connection(conn)
        conn.commit()


def _materialize_protection(
    conn,
    *,
    partial: bool = False,
) -> tuple[dict, dict, dict]:
    ids, prepared = _prepare_exchange_commands_on_connection(conn)
    orders = _submitted_orders(prepared)
    if partial:
        entry = next(row for row in orders if row["order_role"] == "ENTRY")
        sl = next(row for row in orders if row["order_role"] == "SL")
        tp1 = next(row for row in orders if row["order_role"] == "TP1")
        actual = Decimal(str(entry["filled_qty"])) / Decimal("2")
        entry["status"] = "PARTIALLY_FILLED"
        entry["filled_qty"] = str(actual)
        sl["amount"] = str(actual)
        tp1["amount"] = str(actual / Decimal("2"))
    recorded = record_ticket_bound_protected_submit_result(
        conn,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        submit_result={
            "status": "exchange_submit_orders_submitted",
            "ticket_id": ids["ticket_id"],
            "operation_submit_command_id": ids["operation_submit_command_id"],
            "strategy_group_id": "SOR-001",
            "symbol": "ETHUSDT",
            "side": "long",
            "exchange_write_called": True,
            "order_created": True,
            "order_lifecycle_called": True,
            "withdrawal_or_transfer_created": False,
            "live_profile_changed": False,
            "order_sizing_changed": False,
            "submitted_orders": orders,
        },
        now_ms=NOW_MS + 5_000,
    )
    assert recorded["status"] == "submitted", recorded
    protection = materialize_ticket_bound_exit_protection_set(
        conn,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        now_ms=NOW_MS + 6_000,
    )
    assert protection["status"] == "position_protected", protection
    return ids, prepared, protection


def _fake_exchange_counts(engine) -> tuple[int, int]:
    with engine.connect() as conn:
        attempts = conn.execute(
            text("SELECT count(*) FROM brc_rci_fake_exchange_attempts")
        ).scalar_one()
        orders = conn.execute(
            text("SELECT count(*) FROM brc_rci_fake_exchange_orders")
        ).scalar_one()
    return int(attempts), int(orders)


def _database_url(engine) -> str:
    return engine.url.render_as_string(hide_password=False)


def test_rci_s1_two_ready_signals_keep_exact_invocation_ticket_identity(
    postgres_certification_engine,
):
    with postgres_certification_engine.connect() as conn:
        _insert_ready_fresh_signal(
            conn,
            "SOR-001",
            "ETHUSDT",
            "long",
            insert_action_time_fact=False,
        )
        signal_a = "signal:SOR-001:ETHUSDT:long:unit"
        invocation = start_action_time_invocation(
            conn,
            signal_event_id=signal_a,
            opened_at_ms=NOW_MS,
        )
        _bind_fresh_invocation_account_facts(
            conn,
            action_time_invocation_id=invocation.action_time_invocation_id,
            observed_at_ms=NOW_MS + 1,
        )
        _insert_ready_fresh_signal(
            conn,
            "BRF2-001",
            "BTCUSDT",
            "short",
            insert_action_time_fact=False,
        )

        report = materialize_action_time_ticket_sequence(
            conn,
            action_time_invocation_id=invocation.action_time_invocation_id,
            stage_at_ms=NOW_MS + 1,
            completion_clock_ms=lambda: NOW_MS + 2,
        )

        assert report["status"] == "action_time_ticket_sequence_committed", report
        ticket = conn.execute(
            text(
                "SELECT signal_event_id, action_time_invocation_id, "
                "lane_identity_key, source_watermark "
                "FROM brc_action_time_tickets"
            )
        ).mappings().one()
        assert ticket["signal_event_id"] == signal_a
        assert ticket["action_time_invocation_id"] == (
            invocation.action_time_invocation_id
        )
        assert ticket["lane_identity_key"] == invocation.lane_identity.identity_key
        assert ticket["source_watermark"] == invocation.source_watermark
        assert conn.execute(
            text(
                "SELECT count(*) FROM brc_promotion_candidates "
                "WHERE signal_event_id = "
                "'signal:BRF2-001:BTCUSDT:short:unit'"
            )
        ).scalar_one() == 0
        reloaded = load_action_time_invocation(
            conn,
            action_time_invocation_id=invocation.action_time_invocation_id,
        )
        assert reloaded.ticket_id == report["ticket"]["ticket_id"]


def test_rci_s2_ticket_blocker_rolls_back_all_action_authority_rows(
    postgres_certification_engine,
):
    with postgres_certification_engine.connect() as conn:
        _insert_ready_fresh_signal(
            conn,
            "SOR-001",
            "ETHUSDT",
            "long",
            insert_action_time_fact=False,
        )
        report = materialize_action_time_ticket_sequence(
            conn,
            now_ms=NOW_MS,
            projection_publisher=_projection_ready,
            ticket_materializer=lambda inner_conn, now_ms: {
                "status": "blocked",
                "blockers": ["rci_forced_ticket_blocker"],
                "strategy_group_id": "SOR-001",
                "symbol": "ETHUSDT",
                "side": "long",
            },
            completion_clock_ms=lambda: NOW_MS + 1,
        )

        assert report["status"] == "action_time_ticket_sequence_rolled_back"
        for table_name in (
            "brc_promotion_candidates",
            "brc_budget_reservations",
            "brc_action_time_lane_inputs",
            "brc_action_time_tickets",
        ):
            count = conn.execute(
                text(f"SELECT count(*) FROM {table_name}")
            ).scalar_one()
            assert count == 0, table_name
        outcome = conn.execute(
            text(
                "SELECT scope_key, first_blocker, process_state "
                "FROM brc_runtime_process_outcomes "
                "WHERE process_name = 'action_time_ticket_sequence'"
            )
        ).mappings().one()
        assert outcome["scope_key"] == "lane:SOR-001:ETHUSDT:long"
        assert outcome["first_blocker"] == "rci_forced_ticket_blocker"
        assert outcome["process_state"] == "business_blocked"


def test_rci_s3_ttl_expiry_survives_reconnect_without_ticket(
    postgres_certification_engine,
):
    with postgres_certification_engine.connect() as conn:
        _insert_ready_fresh_signal(
            conn,
            "SOR-001",
            "ETHUSDT",
            "short",
            insert_action_time_fact=False,
        )
        report = materialize_action_time_ticket_sequence(
            conn,
            now_ms=NOW_MS,
            projection_publisher=_projection_ready,
            completion_clock_ms=lambda: NOW_MS + 600_000,
        )
        assert report["status"] == "action_time_ticket_sequence_rolled_back"
        assert report["blockers"] == [
            "action_time_sequence_ttl_expired_before_ticket_commit"
        ]
        conn.commit()

    postgres_certification_engine.dispose()
    with postgres_certification_engine.connect() as restarted:
        assert restarted.execute(
            text("SELECT count(*) FROM brc_action_time_tickets")
        ).scalar_one() == 0
        outcome = restarted.execute(
            text(
                "SELECT first_blocker, process_state "
                "FROM brc_runtime_process_outcomes "
                "WHERE process_name = 'action_time_ticket_sequence' "
                "AND scope_key = 'lane:SOR-001:ETHUSDT:short'"
            )
        ).mappings().one()
        assert outcome["first_blocker"] == (
            "action_time_sequence_ttl_expired_before_ticket_commit"
        )
        assert outcome["process_state"] == "business_blocked"


def test_rci_l1_partial_entry_protection_uses_actual_fill_quantity(
    postgres_certification_engine,
):
    with postgres_certification_engine.connect() as conn:
        ids, _, _ = _materialize_protection(conn, partial=True)
        lifecycle_qty = Decimal(
            str(
                conn.execute(
                    text(
                        "SELECT entry_filled_qty "
                        "FROM brc_ticket_bound_order_lifecycle_runs "
                        "WHERE ticket_id = :ticket_id"
                    ),
                    {"ticket_id": ids["ticket_id"]},
                ).scalar_one()
            )
        )
        sl_qty = Decimal(
            str(
                conn.execute(
                    text(
                        "SELECT qty "
                        "FROM brc_ticket_bound_exit_protection_orders "
                        "WHERE ticket_id = :ticket_id AND role = 'SL'"
                    ),
                    {"ticket_id": ids["ticket_id"]},
                ).scalar_one()
            )
        )
        requested_entry_qty = Decimal(
            str(
                conn.execute(
                    text(
                        "SELECT amount "
                        "FROM brc_ticket_bound_exchange_commands "
                        "WHERE ticket_id = :ticket_id AND order_role = 'ENTRY'"
                    ),
                    {"ticket_id": ids["ticket_id"]},
                ).scalar_one()
            )
        )

        assert lifecycle_qty == sl_qty
        assert Decimal("0") < sl_qty < requested_entry_qty


def test_rci_l2_duplicate_fill_is_idempotent_and_contradiction_hard_stops(
    postgres_certification_engine,
):
    with postgres_certification_engine.connect() as conn:
        ids, _, protection = _materialize_protection(conn)
        tp1 = conn.execute(
            text(
                "SELECT exchange_order_id, qty, price "
                "FROM brc_ticket_bound_exit_protection_orders "
                "WHERE ticket_id = :ticket_id AND role = 'TP1'"
            ),
            {"ticket_id": ids["ticket_id"]},
        ).mappings().one()
        fill = {
            "exchange_order_id": tp1["exchange_order_id"],
            "qty": str(tp1["qty"]),
            "price": str(tp1["price"]),
            "timestamp_ms": NOW_MS + 7_000,
        }
        first = project_ticket_bound_exchange_fills(
            conn,
            ticket_id=ids["ticket_id"],
            exchange_snapshot={"recent_fills": [fill]},
            now_ms=NOW_MS + 7_000,
        )
        duplicate = project_ticket_bound_exchange_fills(
            conn,
            ticket_id=ids["ticket_id"],
            exchange_snapshot={"recent_fills": [fill]},
            now_ms=NOW_MS + 7_100,
        )
        contradictory_fill = {
            **fill,
            "qty": str(Decimal(str(fill["qty"])) + Decimal("0.001")),
        }
        contradiction = project_ticket_bound_exchange_fills(
            conn,
            ticket_id=ids["ticket_id"],
            exchange_snapshot={"recent_fills": [contradictory_fill]},
            now_ms=NOW_MS + 7_200,
        )

        assert first["status"] == "fills_projected"
        assert duplicate["status"] == "no_new_fills"
        assert contradiction["status"] == "fill_truth_contradiction"
        assert contradiction["first_blocker"].startswith(
            "contradictory_fill_truth:TP1:"
        )
        lifecycle = conn.execute(
            text(
                "SELECT status, first_blocker "
                "FROM brc_ticket_bound_order_lifecycle_runs "
                "WHERE ticket_id = :ticket_id"
            ),
            {"ticket_id": ids["ticket_id"]},
        ).mappings().one()
        assert lifecycle["status"] == "blocked"
        assert lifecycle["first_blocker"] == contradiction["first_blocker"]
        assert protection["exit_protection_set_id"]


def test_rci_l3_restart_after_tp1_creates_one_runner_command_generation(
    postgres_certification_engine,
):
    with postgres_certification_engine.connect() as conn:
        _, _, protection = _materialize_protection(conn)
        set_id = str(protection["exit_protection_set_id"])
        conn.execute(
            text(
                "UPDATE brc_ticket_bound_exit_protection_orders "
                "SET status = 'filled', updated_at_ms = :now_ms "
                "WHERE exit_protection_set_id = :set_id AND role = 'TP1'"
            ),
            {"now_ms": NOW_MS + 6_500, "set_id": set_id},
        )
        first = prepare_ticket_bound_runner_mutation_command(
            conn,
            exit_protection_set_id=set_id,
            now_ms=NOW_MS + 7_000,
        )
        assert first["status"] == "prepared", first
        conn.commit()

    postgres_certification_engine.dispose()
    with postgres_certification_engine.connect() as restarted:
        second = prepare_ticket_bound_runner_mutation_command(
            restarted,
            exit_protection_set_id=set_id,
            now_ms=NOW_MS + 8_000,
        )
        assert second["status"] == "prepared"
        assert second["runner_mutation_command_id"] == (
            first["runner_mutation_command_id"]
        )
        assert second["idempotent_existing_runner_mutation_command"] is True
        assert restarted.execute(
            text(
                "SELECT count(*) "
                "FROM brc_ticket_bound_runner_mutation_commands "
                "WHERE exit_protection_set_id = :set_id"
            ),
            {"set_id": set_id},
        ).scalar_one() == 1


def _owner_projection_row(conn, *, strategy_group_id: str, symbol: str, side: str):
    control_state = PgBackedRuntimeControlStateRepository(
        conn,
        now_ms=NOW_MS + 10_000,
    ).read_control_state()
    build_inputs = (
        strategy_live_candidate_pool
        .build_strategy_live_candidate_pool_inputs_from_control_state
    )
    inputs = build_inputs(
        control_state,
        generated_at_utc="2026-02-02T03:16:50+00:00",
    )
    return next(
        row
        for row in inputs["daily_table"]["rows"]
        if row["strategy_group_id"] == strategy_group_id
        and row["symbol"] == symbol
        and row["side"] == side
    )


def _sor_long_invocation(conn):
    _insert_ready_fresh_signal(
        conn,
        "SOR-001",
        "ETHUSDT",
        "long",
        insert_action_time_fact=False,
    )
    return start_action_time_invocation(
        conn,
        signal_event_id="signal:SOR-001:ETHUSDT:long:unit",
        opened_at_ms=NOW_MS,
    )


def test_rci_p1_newer_success_clears_current_blocker_and_keeps_history(
    postgres_certification_engine,
):
    with postgres_certification_engine.connect() as conn:
        invocation = _sor_long_invocation(conn)
        failure = materialize_runtime_process_outcome(
            conn,
            process_name="action_time_ticket_sequence",
            scope_key=None,
            lane_identity=invocation.lane_identity,
            action_time_invocation_id=invocation.action_time_invocation_id,
            run_id="rci-p1-failure",
            result_status="action_time_ticket_sequence_rolled_back",
            blockers=["rci_projection_engineering_blocker"],
            started_at_ms=NOW_MS + 100,
            completed_at_ms=NOW_MS + 110,
            runtime_head="rci-head",
            source_watermark="rci-p1-failure-watermark",
        )
        success = materialize_runtime_process_outcome(
            conn,
            process_name="action_time_ticket_sequence",
            scope_key=None,
            lane_identity=invocation.lane_identity,
            action_time_invocation_id=invocation.action_time_invocation_id,
            run_id="rci-p1-success",
            result_status="action_time_ticket_sequence_committed",
            blockers=[],
            started_at_ms=NOW_MS + 200,
            completed_at_ms=NOW_MS + 210,
            runtime_head="rci-head",
            source_watermark="rci-p1-success-watermark",
        )

        rows = list(
            conn.execute(
                text(
                    "SELECT process_outcome_id, process_state, first_blocker "
                    "FROM brc_runtime_process_outcomes "
                    "WHERE process_name = 'action_time_ticket_sequence' "
                    "AND lane_identity_key = :lane_identity_key "
                    "ORDER BY updated_at_ms"
                ),
                {"lane_identity_key": invocation.lane_identity.identity_key},
            ).mappings()
        )
        current = _owner_projection_row(
            conn,
            strategy_group_id="SOR-001",
            symbol="ETHUSDT",
            side="long",
        )

        assert [row["process_outcome_id"] for row in rows] == [
            failure["process_outcome_id"],
            success["process_outcome_id"],
        ]
        assert rows[0]["first_blocker"] == "rci_projection_engineering_blocker"
        assert rows[1]["process_state"] == "succeeded"
        assert current["first_blocker"] != "action_time_boundary_not_reproduced"


def test_rci_p2_no_signal_projection_cannot_erase_engineering_blocker(
    postgres_certification_engine,
):
    with postgres_certification_engine.connect() as conn:
        invocation = _sor_long_invocation(conn)
        materialize_runtime_process_outcome(
            conn,
            process_name="action_time_ticket_sequence",
            scope_key=None,
            lane_identity=invocation.lane_identity,
            action_time_invocation_id=invocation.action_time_invocation_id,
            run_id="rci-p2-failure",
            result_status="action_time_ticket_sequence_rolled_back",
            blockers=["rci_persistent_engineering_blocker"],
            started_at_ms=NOW_MS + 100,
            completed_at_ms=NOW_MS + 110,
            runtime_head="rci-head",
            source_watermark="rci-p2-failure-watermark",
        )
        conn.execute(
            text(
                "UPDATE brc_live_signal_events "
                "SET status = 'superseded', freshness_state = 'expired', "
                "expires_at_ms = :expired_at_ms "
                "WHERE signal_event_id = :signal_event_id"
            ),
            {
                "expired_at_ms": NOW_MS - 1,
                "signal_event_id": invocation.signal_event_id,
            },
        )

        current = _owner_projection_row(
            conn,
            strategy_group_id="SOR-001",
            symbol="ETHUSDT",
            side="long",
        )

        assert current["first_blocker"] == "action_time_boundary_not_reproduced"


def test_rci_e1_claim_crash_before_exchange_never_redispatches(
    postgres_certification_engine,
):
    _prepare_exchange_commands(postgres_certification_engine)
    context = multiprocessing.get_context("spawn")
    claimed_event = context.Event()
    hold_event = context.Event()
    lease_ms = 100
    process = context.Process(
        target=claim_then_hold_process,
        kwargs={
            "database_url": _database_url(postgres_certification_engine),
            "claimed_event": claimed_event,
            "hold_event": hold_event,
            "now_ms": NOW_MS + 5_000,
            "lease_ms": lease_ms,
        },
    )
    process.start()
    assert claimed_event.wait(10)
    process.terminate()
    process.join(10)
    assert not process.is_alive()

    gateway = FakeExchangeLedgerGateway(
        _database_url(postgres_certification_engine),
        caller_label="rci-e1-recovery",
    )
    result = asyncio.run(
        run_one_ticket_bound_exchange_command(
            postgres_certification_engine,
            gateway=gateway,
            worker_id="rci-e1-recovery-worker",
            now_ms=NOW_MS + 5_000 + lease_ms + 1,
            command_sources=("protected_submit",),
        )
    )

    assert result["status"] == "outcome_unknown_persisted"
    assert _fake_exchange_counts(postgres_certification_engine) == (0, 0)


def test_rci_e2_exchange_accept_crash_before_pg_result_never_duplicates(
    postgres_certification_engine,
):
    _prepare_exchange_commands(postgres_certification_engine)
    context = multiprocessing.get_context("spawn")
    accepted_event = context.Event()
    hold_event = context.Event()
    lease_ms = 100
    process = context.Process(
        target=run_fake_exchange_worker_process,
        kwargs={
            "database_url": _database_url(postgres_certification_engine),
            "worker_id": "rci-e2-crash-worker",
            "caller_label": "rci-e2-crash-worker",
            "now_ms": NOW_MS + 5_000,
            "lease_ms": lease_ms,
            "accepted_event": accepted_event,
            "hold_event": hold_event,
        },
    )
    process.start()
    assert accepted_event.wait(10)
    process.terminate()
    process.join(10)
    assert not process.is_alive()

    recovery_gateway = FakeExchangeLedgerGateway(
        _database_url(postgres_certification_engine),
        caller_label="rci-e2-recovery",
    )
    result = asyncio.run(
        run_one_ticket_bound_exchange_command(
            postgres_certification_engine,
            gateway=recovery_gateway,
            worker_id="rci-e2-recovery-worker",
            now_ms=NOW_MS + 5_000 + lease_ms + 1,
            command_sources=("protected_submit",),
        )
    )

    assert result["status"] == "outcome_unknown_persisted"
    assert _fake_exchange_counts(postgres_certification_engine) == (1, 1)


def test_rci_e3_two_process_workers_produce_one_external_attempt(
    postgres_certification_engine,
):
    _prepare_exchange_commands(postgres_certification_engine)
    context = multiprocessing.get_context("spawn")
    start_event = context.Event()
    processes = [
        context.Process(
            target=run_fake_exchange_worker_process,
            kwargs={
                "database_url": _database_url(postgres_certification_engine),
                "worker_id": f"rci-e3-worker-{index}",
                "caller_label": f"rci-e3-worker-{index}",
                "now_ms": NOW_MS + 5_000,
                "lease_ms": 15_000,
                "start_event": start_event,
            },
        )
        for index in (1, 2)
    ]
    for process in processes:
        process.start()
    start_event.set()
    for process in processes:
        process.join(15)
        assert process.exitcode == 0

    assert _fake_exchange_counts(postgres_certification_engine) == (1, 1)
    with postgres_certification_engine.connect() as conn:
        states = conn.execute(
            text(
                "SELECT command_state "
                "FROM brc_ticket_bound_exchange_commands "
                "WHERE order_role = 'ENTRY'"
            )
        ).scalars().all()
    assert states == ["confirmed_submitted"]


def test_rci_e4_ambiguous_gateway_timeout_blocks_later_dispatch(
    postgres_certification_engine,
):
    _prepare_exchange_commands(postgres_certification_engine)

    class TimeoutAfterAcceptanceGateway(FakeExchangeLedgerGateway):
        async def place_order(self, **kwargs):
            await super().place_order(**kwargs)
            raise TimeoutError("rci_ambiguous_exchange_timeout")

    first_gateway = TimeoutAfterAcceptanceGateway(
        _database_url(postgres_certification_engine),
        caller_label="rci-e4-timeout",
    )
    first = asyncio.run(
        run_one_ticket_bound_exchange_command(
            postgres_certification_engine,
            gateway=first_gateway,
            worker_id="rci-e4-worker",
            now_ms=NOW_MS + 5_000,
            command_sources=("protected_submit",),
        )
    )
    second_gateway = FakeExchangeLedgerGateway(
        _database_url(postgres_certification_engine),
        caller_label="rci-e4-later-worker",
    )
    second = asyncio.run(
        run_one_ticket_bound_exchange_command(
            postgres_certification_engine,
            gateway=second_gateway,
            worker_id="rci-e4-later-worker",
            now_ms=NOW_MS + 6_000,
            command_sources=("protected_submit",),
        )
    )

    assert first["status"] == "command_outcome_unknown"
    assert second["status"] == "no_prepared_command"
    assert _fake_exchange_counts(postgres_certification_engine) == (1, 1)
    with postgres_certification_engine.connect() as conn:
        hold_status = conn.execute(
            text(
                "SELECT status FROM brc_ticket_bound_scope_freezes "
                "WHERE source_kind = 'exchange_command'"
            )
        ).scalar_one()
    assert hold_status == "active"
