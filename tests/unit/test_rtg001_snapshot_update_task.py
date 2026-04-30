from __future__ import annotations

import asyncio

import pytest

import src.main as main_module


class _FakeGateway:
    def __init__(self, snapshots):
        self._snapshots = list(snapshots)

    def get_account_snapshot(self):
        item = self._snapshots.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class _FakePipeline:
    def __init__(self, shutdown_event: asyncio.Event | None = None) -> None:
        self.shutdown_event = shutdown_event
        self.snapshots = []

    def update_account_snapshot(self, snapshot) -> None:
        self.snapshots.append(snapshot)
        if self.shutdown_event is not None:
            self.shutdown_event.set()


@pytest.fixture(autouse=True)
def _reset_main_globals():
    original_shutdown_event = main_module._shutdown_event
    original_exchange_gateway = main_module._exchange_gateway
    original_signal_pipeline = main_module._signal_pipeline
    original_snapshot_update_task = main_module._snapshot_update_task
    yield
    main_module._shutdown_event = original_shutdown_event
    main_module._exchange_gateway = original_exchange_gateway
    main_module._signal_pipeline = original_signal_pipeline
    main_module._snapshot_update_task = original_snapshot_update_task


@pytest.mark.asyncio
async def test_snapshot_update_loop_updates_signal_pipeline_snapshot():
    shutdown_event = asyncio.Event()
    pipeline = _FakePipeline(shutdown_event)
    main_module._shutdown_event = shutdown_event
    main_module._exchange_gateway = _FakeGateway(["snapshot-1"])
    main_module._signal_pipeline = pipeline

    await asyncio.wait_for(
        main_module._run_snapshot_update_loop(polling_interval=60),
        timeout=0.2,
    )

    assert pipeline.snapshots == ["snapshot-1"]


@pytest.mark.asyncio
async def test_snapshot_update_loop_logs_exception_and_continues(caplog):
    shutdown_event = asyncio.Event()
    pipeline = _FakePipeline(shutdown_event)
    main_module._shutdown_event = shutdown_event
    main_module._exchange_gateway = _FakeGateway([RuntimeError("snapshot failed"), "snapshot-2"])
    main_module._signal_pipeline = pipeline
    caplog.set_level("ERROR")

    await asyncio.wait_for(
        main_module._run_snapshot_update_loop(polling_interval=0.01),
        timeout=0.5,
    )

    assert "Snapshot update loop failed" in caplog.text
    assert pipeline.snapshots == ["snapshot-2"]


@pytest.mark.asyncio
async def test_snapshot_update_loop_shutdown_event_exits_during_interval_wait():
    shutdown_event = asyncio.Event()
    main_module._shutdown_event = shutdown_event
    main_module._exchange_gateway = _FakeGateway([None])
    main_module._signal_pipeline = _FakePipeline()

    task = asyncio.create_task(main_module._run_snapshot_update_loop(polling_interval=60))
    await asyncio.sleep(0)
    shutdown_event.set()

    await asyncio.wait_for(task, timeout=0.2)


@pytest.mark.asyncio
async def test_snapshot_update_loop_cancellation_is_not_swallowed():
    shutdown_event = asyncio.Event()
    main_module._shutdown_event = shutdown_event
    main_module._exchange_gateway = _FakeGateway([None])
    main_module._signal_pipeline = _FakePipeline()

    task = asyncio.create_task(main_module._run_snapshot_update_loop(polling_interval=60))
    await asyncio.sleep(0)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_cancel_snapshot_update_task_cancels_awaits_and_clears_handle():
    shutdown_event = asyncio.Event()
    main_module._shutdown_event = shutdown_event
    main_module._exchange_gateway = _FakeGateway([None])
    main_module._signal_pipeline = _FakePipeline()
    main_module._snapshot_update_task = main_module._start_snapshot_update_task(60)

    await asyncio.sleep(0)
    await main_module._cancel_snapshot_update_task()

    assert main_module._snapshot_update_task is None


@pytest.mark.asyncio
async def test_cancel_snapshot_update_task_handles_none_task():
    main_module._snapshot_update_task = None

    await main_module._cancel_snapshot_update_task()

    assert main_module._snapshot_update_task is None


@pytest.mark.asyncio
async def test_cancel_snapshot_update_task_logs_done_task_exception(caplog):
    async def _failed_task():
        raise RuntimeError("already failed")

    caplog.set_level("WARNING")
    main_module._snapshot_update_task = asyncio.create_task(_failed_task())
    await asyncio.sleep(0)

    await main_module._cancel_snapshot_update_task()

    assert main_module._snapshot_update_task is None
    assert "Snapshot update task shutdown error" in caplog.text
