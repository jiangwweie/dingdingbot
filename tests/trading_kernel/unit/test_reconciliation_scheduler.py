from __future__ import annotations

from src.trading_kernel.application.reconciliation_scheduler import (
    ReconciliationActionCandidate,
    ReconciliationActionKind,
    ReconciliationScheduleInput,
    select_reconciliation_schedule,
)


def test_housekeeping_selects_earliest_deadline_then_stable_identity() -> None:
    """Catches fixed-if ordering that can starve a tighter housekeeping deadline."""

    decision = select_reconciliation_schedule(
        ReconciliationScheduleInput(
            now_ms=125_000,
            safety_action=ReconciliationActionCandidate(
                kind=ReconciliationActionKind.POSITION_SAFETY,
                stable_identity="ticket:safety",
                due_at_ms=123_000,
                max_wait_ms=0,
            ),
            housekeeping_candidates=(
                ReconciliationActionCandidate(
                    kind=ReconciliationActionKind.CERTIFICATION,
                    stable_identity="instrument:z",
                    due_at_ms=5_000,
                    max_wait_ms=120_000,
                ),
                ReconciliationActionCandidate(
                    kind=ReconciliationActionKind.SETTLEMENT,
                    stable_identity="ticket:b",
                    due_at_ms=64_000,
                    max_wait_ms=60_000,
                ),
                ReconciliationActionCandidate(
                    kind=ReconciliationActionKind.SETTLEMENT,
                    stable_identity="ticket:a",
                    due_at_ms=64_000,
                    max_wait_ms=60_000,
                ),
                ReconciliationActionCandidate(
                    kind=ReconciliationActionKind.FEE_MONITOR,
                    stable_identity="account:fee",
                    due_at_ms=0,
                    max_wait_ms=600_000,
                ),
            ),
        )
    )

    assert decision.safety_action is not None
    assert decision.safety_action.stable_identity == "ticket:safety"
    assert decision.housekeeping_action is not None
    assert decision.housekeeping_action.stable_identity == "ticket:a"
    assert decision.next_due_at_ms == 0
    assert decision.deadline_breach is True


def test_housekeeping_ignores_future_work_and_reports_next_due() -> None:
    """Catches executing not-yet-due work merely because the lane is idle."""

    decision = select_reconciliation_schedule(
        ReconciliationScheduleInput(
            now_ms=100_000,
            housekeeping_candidates=(
                ReconciliationActionCandidate(
                    kind=ReconciliationActionKind.CERTIFICATION,
                    stable_identity="instrument:btc",
                    due_at_ms=105_000,
                    max_wait_ms=120_000,
                ),
                ReconciliationActionCandidate(
                    kind=ReconciliationActionKind.FEE_MONITOR,
                    stable_identity="account:fee",
                    due_at_ms=110_000,
                    max_wait_ms=600_000,
                ),
            ),
        )
    )

    assert decision.housekeeping_action is None
    assert decision.next_due_at_ms == 105_000
    assert decision.deadline_breach is False


def test_fifteen_minute_production_cadence_bounds_all_housekeeping_waits() -> None:
    """Catches starvation with 5s polls and continuously re-due position safety."""

    safety_due = {
        "ticket:btc": 0,
        "ticket:eth": 0,
        "ticket:sol": 0,
    }
    housekeeping = {
        "settlement:ticket:closed": (
            ReconciliationActionKind.SETTLEMENT,
            0,
            60_000,
        ),
        "review:ticket:closed": (
            ReconciliationActionKind.REVIEW,
            0,
            60_000,
        ),
        **{
            f"certification:{symbol}": (
                ReconciliationActionKind.CERTIFICATION,
                0,
                120_000,
            )
            for symbol in ("BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA")
        },
        "fee:account": (ReconciliationActionKind.FEE_MONITOR, 0, 600_000),
    }
    maximum_wait: dict[str, int] = {identity: 0 for identity in housekeeping}
    execution_count: dict[str, int] = {identity: 0 for identity in housekeeping}
    safety_count = {identity: 0 for identity in safety_due}

    for now_ms in range(5_000, 900_001, 5_000):
        safety_identity = min(
            safety_due,
            key=lambda identity: (safety_due[identity], identity),
        )
        safety_action = ReconciliationActionCandidate(
            kind=ReconciliationActionKind.POSITION_SAFETY,
            stable_identity=safety_identity,
            due_at_ms=safety_due[safety_identity],
            max_wait_ms=0,
        )
        candidates = tuple(
            ReconciliationActionCandidate(
                kind=kind,
                stable_identity=identity,
                due_at_ms=due_at_ms,
                max_wait_ms=max_wait_ms,
            )
            for identity, (kind, due_at_ms, max_wait_ms) in housekeeping.items()
        )
        decision = select_reconciliation_schedule(
            ReconciliationScheduleInput(
                now_ms=now_ms,
                safety_action=safety_action,
                housekeeping_candidates=candidates,
            )
        )

        safety_count[safety_identity] += 1
        safety_due[safety_identity] = now_ms + 2_000
        selected = decision.housekeeping_action
        if selected is None:
            continue
        waited_ms = now_ms - selected.due_at_ms
        maximum_wait[selected.stable_identity] = max(
            maximum_wait[selected.stable_identity],
            waited_ms,
        )
        execution_count[selected.stable_identity] += 1
        next_interval_ms = (
            30_000
            if selected.kind
            in {
                ReconciliationActionKind.SETTLEMENT,
                ReconciliationActionKind.REVIEW,
            }
            else 300_000
        )
        housekeeping[selected.stable_identity] = (
            selected.kind,
            now_ms + next_interval_ms,
            selected.max_wait_ms,
        )

    assert all(count > 0 for count in safety_count.values())
    assert all(count > 0 for count in execution_count.values())
    assert maximum_wait["settlement:ticket:closed"] <= 60_000
    assert maximum_wait["review:ticket:closed"] <= 60_000
    assert all(
        maximum_wait[f"certification:{symbol}"] <= 120_000
        for symbol in ("BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA")
    )
    assert maximum_wait["fee:account"] <= 600_000
