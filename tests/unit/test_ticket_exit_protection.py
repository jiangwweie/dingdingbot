from __future__ import annotations

from src.domain.ticket_exit_protection import (
    ActiveProtectionResolutionState,
    ExitProtectionOrderView,
    resolve_active_exit_protection,
)


NOW_MS = 1_720_000_000_000


def test_resolves_one_active_generation():
    result = _resolve([_order("runner-g1", status="open")])

    assert result.state is ActiveProtectionResolutionState.ACTIVE_ONE
    assert result.active_order is not None
    assert result.active_order.local_order_id == "runner-g1"
    assert result.blockers == ()


def test_ignores_terminal_history_when_one_generation_is_active():
    result = _resolve(
        [
            _order("runner-g1", status="cancelled"),
            _order(
                "runner-g2",
                status="open",
                replaces_exit_protection_order_id="order:runner-g1",
            ),
        ]
    )

    assert result.state is ActiveProtectionResolutionState.ACTIVE_ONE
    assert result.active_order is not None
    assert result.active_order.local_order_id == "runner-g2"


def test_accepts_linked_replacement_overlap_inside_grace_window():
    result = _resolve(
        [
            _order("runner-g1", status="cancel_pending", updated_at_ms=NOW_MS - 1000),
            _order(
                "runner-g2",
                status="open",
                replaces_exit_protection_order_id="order:runner-g1",
                created_at_ms=NOW_MS - 500,
            ),
        ]
    )

    assert result.state is ActiveProtectionResolutionState.REPLACEMENT_OVERLAP
    assert result.active_order is not None
    assert result.active_order.local_order_id == "runner-g2"
    assert result.superseded_order_ids == ("order:runner-g1",)


def test_zero_active_generation_while_position_open_is_missing():
    result = _resolve([_order("runner-g1", status="cancelled")])

    assert result.state is ActiveProtectionResolutionState.MISSING_WHILE_OPEN
    assert result.active_order is None
    assert result.blockers == ("active_runner_sl_protection_missing",)


def test_two_unexplained_active_generations_are_ambiguous():
    result = _resolve(
        [
            _order("runner-g1", status="open"),
            _order("runner-g2", status="open"),
        ]
    )

    assert result.state is ActiveProtectionResolutionState.AMBIGUOUS_ACTIVE
    assert result.active_order is None
    assert result.blockers == ("active_runner_sl_protection_ambiguous",)


def test_broken_replacement_lineage_fails_closed():
    result = _resolve(
        [
            _order(
                "runner-g2",
                status="open",
                replaces_exit_protection_order_id="order:missing",
            )
        ]
    )

    assert result.state is ActiveProtectionResolutionState.BROKEN_LINEAGE
    assert result.active_order is None
    assert result.blockers == ("active_runner_sl_replacement_lineage_broken",)


def test_cross_set_row_fails_closed():
    result = _resolve(
        [
            _order("runner-g1", status="open"),
            _order("runner-g2", status="cancelled", exit_protection_set_id="set-2"),
        ]
    )

    assert result.state is ActiveProtectionResolutionState.CROSS_SET
    assert result.active_order is None
    assert result.blockers == ("active_runner_sl_cross_set_row",)


def test_terminal_position_resolves_lineage_leaf_without_requiring_active_order():
    result = _resolve(
        [
            _order("runner-g1", status="cancelled"),
            _order(
                "runner-g2",
                status="filled",
                replaces_exit_protection_order_id="order:runner-g1",
            ),
        ],
        position_is_open=False,
    )

    assert result.state is ActiveProtectionResolutionState.TERMINAL_POSITION
    assert result.active_order is not None
    assert result.active_order.local_order_id == "runner-g2"
    assert result.blockers == ()


def _resolve(
    orders: list[ExitProtectionOrderView],
    *,
    position_is_open: bool = True,
):
    return resolve_active_exit_protection(
        exit_protection_set_id="set-1",
        role="RUNNER_SL",
        orders=orders,
        position_is_open=position_is_open,
        now_ms=NOW_MS,
        replacement_grace_ms=90_000,
    )


def _order(
    local_order_id: str,
    *,
    status: str,
    exit_protection_set_id: str = "set-1",
    replaces_exit_protection_order_id: str | None = None,
    created_at_ms: int = NOW_MS - 10_000,
    updated_at_ms: int = NOW_MS - 5_000,
) -> ExitProtectionOrderView:
    return ExitProtectionOrderView(
        exit_protection_order_id=f"order:{local_order_id}",
        exit_protection_set_id=exit_protection_set_id,
        role="RUNNER_SL",
        local_order_id=local_order_id,
        exchange_order_id=f"exchange:{local_order_id}",
        status=status,
        replaces_exit_protection_order_id=replaces_exit_protection_order_id,
        created_at_ms=created_at_ms,
        updated_at_ms=updated_at_ms,
    )
