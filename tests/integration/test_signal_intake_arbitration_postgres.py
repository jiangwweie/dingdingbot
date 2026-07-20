"""Real PostgreSQL certification for concurrent fresh-signal intake."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import text

from src.application.action_time.signal_arbitration import ArbitrationDisposition
from src.application.action_time.signal_intake import (
    conserve_and_arbitrate_fresh_signals,
)
from tests.integration.runtime_causal_integrity_pg_support import (
    postgres_certification_engine,
    postgres_certification_template,
)
from tests.unit.test_pg_promotion_action_time_lane_materialization import (
    NOW_MS,
    _insert_ready_fresh_signal,
)


def test_two_workers_conserve_two_signals_with_one_stable_winner(
    postgres_certification_engine,
) -> None:
    with postgres_certification_engine.begin() as conn:
        _insert_ready_fresh_signal(
            conn,
            "SOR-001",
            "ETHUSDT",
            "long",
            insert_action_time_fact=False,
        )
        _insert_ready_fresh_signal(
            conn,
            "SOR-001",
            "SOLUSDT",
            "long",
            insert_action_time_fact=False,
        )

    def intake_once() -> list[tuple[str, ArbitrationDisposition]]:
        with postgres_certification_engine.begin() as conn:
            return [
                (item.decision.signal_event_id, item.decision.disposition)
                for item in conserve_and_arbitrate_fresh_signals(conn, now_ms=NOW_MS)
            ]

    with ThreadPoolExecutor(max_workers=2) as workers:
        outcomes = list(workers.map(lambda _unused: intake_once(), range(2)))

    assert outcomes[0] == outcomes[1]
    assert outcomes[0] == [
        ("signal:SOR-001:ETHUSDT:long:unit", ArbitrationDisposition.SELECTED),
        (
            "signal:SOR-001:SOLUSDT:long:unit",
            ArbitrationDisposition.NOT_SELECTED_THIS_ROUND,
        ),
    ]
    with postgres_certification_engine.connect() as conn:
        invocations = conn.execute(
            text(
                """
                SELECT signal_event_id, terminal_kind, winner_signal_event_id
                FROM brc_action_time_invocations
                ORDER BY signal_event_id
                """
            )
        ).mappings().all()
        outcomes_count = conn.execute(
            text(
                """
                SELECT count(*)
                FROM brc_runtime_process_outcomes
                WHERE process_name = 'action_time_signal_arbitration'
                """
            )
        ).scalar_one()

    assert [row["signal_event_id"] for row in invocations] == [
        "signal:SOR-001:ETHUSDT:long:unit",
        "signal:SOR-001:SOLUSDT:long:unit",
    ]
    assert invocations[0]["terminal_kind"] is None
    assert invocations[1]["terminal_kind"] == "not_selected"
    assert invocations[1]["winner_signal_event_id"] == invocations[0]["signal_event_id"]
    assert outcomes_count == 2
