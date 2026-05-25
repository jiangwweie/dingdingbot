from __future__ import annotations

import asyncio

import pytest

from src.application.startup_trading_guard import StartupTradingGuardService
import src.main as main_module


@pytest.fixture(autouse=True)
def _reset_main_task_globals():
    original_ws_task = main_module._ws_task
    original_api_task = main_module._api_task
    original_snapshot_update_task = main_module._snapshot_update_task
    original_order_watch_tasks = list(main_module._order_watch_tasks)
    original_periodic_reconciliation_task = main_module._periodic_reconciliation_task
    original_startup_trading_guard_service = main_module._startup_trading_guard_service
    yield
    main_module._ws_task = original_ws_task
    main_module._api_task = original_api_task
    main_module._snapshot_update_task = original_snapshot_update_task
    main_module._order_watch_tasks = original_order_watch_tasks
    main_module._periodic_reconciliation_task = original_periodic_reconciliation_task
    main_module._startup_trading_guard_service = original_startup_trading_guard_service


async def _running_forever() -> None:
    await asyncio.sleep(60)


async def _returns_done() -> str:
    return "done"


async def _raises_error() -> None:
    raise RuntimeError("task failed")


@pytest.mark.asyncio
async def test_cancel_ws_task_handles_none_task():
    main_module._ws_task = None

    await main_module._cancel_ws_task()

    assert main_module._ws_task is None


@pytest.mark.asyncio
async def test_cancel_ws_task_handles_completed_task_and_clears_handle():
    main_module._ws_task = asyncio.create_task(_returns_done())
    await asyncio.sleep(0)

    await main_module._cancel_ws_task()

    assert main_module._ws_task is None


@pytest.mark.asyncio
async def test_cancel_ws_task_cancels_running_task_and_clears_handle():
    task = asyncio.create_task(_running_forever())
    main_module._ws_task = task

    await main_module._cancel_ws_task()

    assert main_module._ws_task is None
    assert task.cancelled()


@pytest.mark.asyncio
async def test_cancel_api_task_handles_none_task():
    main_module._api_task = None

    await main_module._cancel_api_task()

    assert main_module._api_task is None


@pytest.mark.asyncio
async def test_cancel_api_task_handles_completed_task_and_clears_handle():
    main_module._api_task = asyncio.create_task(_returns_done())
    await asyncio.sleep(0)

    await main_module._cancel_api_task()

    assert main_module._api_task is None


@pytest.mark.asyncio
async def test_cancel_api_task_cancels_running_task_and_clears_handle():
    task = asyncio.create_task(_running_forever())
    main_module._api_task = task

    await main_module._cancel_api_task()

    assert main_module._api_task is None
    assert task.cancelled()


@pytest.mark.asyncio
async def test_cancel_helpers_are_idempotent():
    ws_task = asyncio.create_task(_running_forever())
    api_task = asyncio.create_task(_running_forever())
    main_module._ws_task = ws_task
    main_module._api_task = api_task

    await main_module._cancel_ws_task()
    await main_module._cancel_ws_task()
    await main_module._cancel_api_task()
    await main_module._cancel_api_task()

    assert main_module._ws_task is None
    assert main_module._api_task is None
    assert ws_task.cancelled()
    assert api_task.cancelled()


@pytest.mark.asyncio
async def test_cancel_helpers_do_not_touch_other_runtime_task_handles():
    snapshot_task = asyncio.create_task(_returns_done())
    periodic_task = asyncio.create_task(_returns_done())
    order_watch_task = asyncio.create_task(_returns_done())
    await asyncio.gather(snapshot_task, periodic_task, order_watch_task)
    main_module._snapshot_update_task = snapshot_task
    main_module._periodic_reconciliation_task = periodic_task
    main_module._order_watch_tasks = [order_watch_task]
    main_module._ws_task = asyncio.create_task(_running_forever())
    main_module._api_task = asyncio.create_task(_running_forever())

    await main_module._cancel_ws_task()
    await main_module._cancel_api_task()

    assert main_module._snapshot_update_task is snapshot_task
    assert main_module._periodic_reconciliation_task is periodic_task
    assert main_module._order_watch_tasks == [order_watch_task]


@pytest.mark.asyncio
async def test_cancel_ws_task_logs_non_cancel_exception_and_clears_handle(caplog):
    caplog.set_level("WARNING")
    main_module._ws_task = asyncio.create_task(_raises_error())
    await asyncio.sleep(0)

    await main_module._cancel_ws_task()

    assert main_module._ws_task is None
    assert "WebSocket task shutdown error" in caplog.text


@pytest.mark.asyncio
async def test_cancel_api_task_logs_non_cancel_exception_and_clears_handle(caplog):
    caplog.set_level("WARNING")
    main_module._api_task = asyncio.create_task(_raises_error())
    await asyncio.sleep(0)

    await main_module._cancel_api_task()

    assert main_module._api_task is None
    assert "API server task shutdown error" in caplog.text


def test_shutdown_guard_reset_blocks_previously_armed_runtime():
    guard = StartupTradingGuardService()
    guard.manual_arm(updated_by="owner", reason="startup checked")
    main_module._startup_trading_guard_service = guard

    main_module._block_startup_guard_for_shutdown("unit_shutdown")

    state = guard.get_state()
    assert state.armed is False
    assert state.reason == "RUNTIME_SHUTDOWN_RESET"
    assert state.source == "unit_shutdown"
