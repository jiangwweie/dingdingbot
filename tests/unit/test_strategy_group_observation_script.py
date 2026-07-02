from __future__ import annotations

import argparse
import builtins
import importlib.util
from pathlib import Path

import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "run_strategy_group_readonly_observation_once.py"
)


def _load_script_module():
    spec = importlib.util.spec_from_file_location(
        "run_strategy_group_readonly_observation_once_test",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_observation_script_load_env_ignores_missing_dotenv(monkeypatch):
    module = _load_script_module()
    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "dotenv":
            raise ModuleNotFoundError("No module named 'dotenv'")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    module._load_env()


def test_observation_script_load_env_surfaces_dotenv_import_error(monkeypatch):
    module = _load_script_module()
    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "dotenv":
            raise RuntimeError("dotenv import failed")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(RuntimeError, match="dotenv import failed"):
        module._load_env()


class _FakeResult:
    market_source = "unit_test_market_source"
    sink = "unit_test_sink"
    inserted_count = 1
    skipped_duplicate_count = 0
    failed_count = 0
    candidate_results = []

    def model_dump(self, *, mode: str):
        assert mode == "json"
        return {
            "market_source": self.market_source,
            "inserted_count": self.inserted_count,
            "failed_count": self.failed_count,
        }


def _args(**overrides):
    values = {
        "source": "local_sqlite_read_only",
        "json": True,
        "shadow_plan": False,
        "allow_shadow_candidate_creation": False,
        "account_facts_source": "none",
        "public_market_facts": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


@pytest.mark.asyncio
async def test_observation_script_defaults_to_observation_only(monkeypatch, capsys):
    module = _load_script_module()
    import src.application.strategy_group_readonly_observation_scheduler as scheduler

    captured: dict = {}

    async def fake_run_scheduled_readonly_observation_once(**kwargs):
        captured.update(kwargs)
        return _FakeResult()

    async def fail_builder(args):
        raise AssertionError("shadow planner dependencies must not be built")

    monkeypatch.setattr(
        scheduler,
        "run_scheduled_readonly_observation_once",
        fake_run_scheduled_readonly_observation_once,
    )
    monkeypatch.setattr(module, "_build_shadow_planning_dependencies", fail_builder)

    code = await module._run(_args())

    assert code == 0
    assert captured == {"source_name": "local_sqlite_read_only"}
    assert '"inserted_count": 1' in capsys.readouterr().out


@pytest.mark.asyncio
async def test_observation_script_rejects_candidate_creation_without_shadow_plan(
    monkeypatch,
    capsys,
):
    module = _load_script_module()
    import src.application.strategy_group_readonly_observation_scheduler as scheduler

    async def fail_run(**kwargs):
        raise AssertionError("scheduler must not run for invalid flags")

    monkeypatch.setattr(
        scheduler,
        "run_scheduled_readonly_observation_once",
        fail_run,
    )

    code = await module._run(
        _args(allow_shadow_candidate_creation=True, shadow_plan=False)
    )

    assert code == 2
    assert "requires --shadow-plan" in capsys.readouterr().err


@pytest.mark.asyncio
async def test_observation_script_shadow_plan_injects_resolver_and_planner(
    monkeypatch,
):
    module = _load_script_module()
    import src.application.strategy_group_readonly_observation_scheduler as scheduler

    captured: dict = {}

    class _Closeable:
        closed = False

        async def close(self):
            self.closed = True

    closeable = _Closeable()

    async def fake_builder(args):
        assert args.shadow_plan is True
        return "runtime-resolver", "scheduler-planning-service", [closeable]

    async def fake_run_scheduled_readonly_observation_once(**kwargs):
        captured.update(kwargs)
        return _FakeResult()

    monkeypatch.setattr(module, "_build_shadow_planning_dependencies", fake_builder)
    monkeypatch.setattr(
        scheduler,
        "run_scheduled_readonly_observation_once",
        fake_run_scheduled_readonly_observation_once,
    )

    code = await module._run(
        _args(shadow_plan=True, allow_shadow_candidate_creation=True)
    )

    assert code == 0
    assert captured["source_name"] == "local_sqlite_read_only"
    assert captured["runtime_resolver"] == "runtime-resolver"
    assert captured["runtime_signal_planning_service"] == "scheduler-planning-service"
    assert captured["allow_shadow_candidate_creation"] is True
    assert closeable.closed is True
