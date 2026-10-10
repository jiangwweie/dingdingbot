from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest


@pytest.mark.asyncio
async def test_real_process_sigterm_cancels_slow_component_without_starving_other_ticks(tmp_path: Path) -> None:
    """Exercise actual OS signals, not a substituted shutdown Event."""
    repo=Path(__file__).resolve().parents[3]
    program="""
import asyncio
from pydantic import BaseModel
from src.trading_kernel.interfaces.worker_process import WorkerProcessLoop,run_worker_process_group
class Result(BaseModel):
    status: str='heartbeat'
async def slow():
    print('slow_started',flush=True)
    try:
        await asyncio.Event().wait()
    finally:
        print('slow_cancelled',flush=True)
async def safety():
    return Result()
asyncio.run(run_worker_process_group((
    WorkerProcessLoop('selection:slow',slow,10,frozenset()),
    WorkerProcessLoop('observation:safety',safety,10,frozenset()),
),run_forever=True,idle_log_interval_ms=1000))
"""
    for _ in range(2):
        process=await asyncio.create_subprocess_exec(sys.executable,"-c",program,cwd=tmp_path,
            env={**os.environ,"PYTHONPATH":str(repo),"PYTHONDONTWRITEBYTECODE":"1"},
            stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        try:
            assert process.stdout is not None
            assert (await asyncio.wait_for(process.stdout.readline(),timeout=5)).decode().strip()=="slow_started"
            for _ in range(3):
                heartbeat=json.loads(await asyncio.wait_for(process.stdout.readline(),timeout=2))
                assert heartbeat["component_id"]=="observation:safety"
            process.terminate()
            stdout,stderr=await asyncio.wait_for(process.communicate(),timeout=2)
            assert process.returncode==0,stderr.decode()
            assert b"slow_cancelled" in stdout
            assert b"tick_failed" not in stdout
        finally:
            if process.returncode is None:
                process.kill()
                await process.communicate()
    assert tuple(tmp_path.iterdir())==()
