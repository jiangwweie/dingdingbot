from __future__ import annotations

import src.main as main_module
from src.infrastructure.strategy_signal_v2_observe_sink import (
    DEFAULT_STRATEGY_SIGNAL_V2_OBSERVE_PATH,
)


class _FakeSink:
    constructed_paths = []

    def __init__(self, path):
        self.path = path
        self.__class__.constructed_paths.append(path)


class _FailingSink:
    def __init__(self, path):
        raise RuntimeError("sink unavailable")


class _FakeWriter:
    constructed_sinks = []

    def __init__(self, *, sink):
        self.sink = sink
        self.__class__.constructed_sinks.append(sink)


def _install_fakes(monkeypatch, *, sink_cls=_FakeSink, writer_cls=_FakeWriter):
    _FakeSink.constructed_paths = []
    _FakeWriter.constructed_sinks = []
    monkeypatch.setattr(main_module, "StrategySignalV2ObserveSink", sink_cls)
    monkeypatch.setattr(main_module, "PatternStrategySignalObserveWriter", writer_cls)


def test_observe_bootstrap_disabled_when_env_unset(monkeypatch, caplog):
    _install_fakes(monkeypatch, sink_cls=_FailingSink)
    caplog.set_level("INFO")

    writer = main_module._build_strategy_signal_v2_observe_writer(env={})

    assert writer is None
    assert "StrategySignalV2 observe disabled" in caplog.text


def test_observe_bootstrap_enabled_constructs_writer_with_default_path(monkeypatch, caplog):
    _install_fakes(monkeypatch)
    caplog.set_level("INFO")

    writer = main_module._build_strategy_signal_v2_observe_writer(
        env={"STRATEGY_SIGNAL_V2_OBSERVE_ENABLED": "true"}
    )

    assert isinstance(writer, _FakeWriter)
    assert _FakeSink.constructed_paths == [DEFAULT_STRATEGY_SIGNAL_V2_OBSERVE_PATH]
    assert writer.sink.path == DEFAULT_STRATEGY_SIGNAL_V2_OBSERVE_PATH
    assert "StrategySignalV2 observe enabled" in caplog.text


def test_observe_bootstrap_path_override(monkeypatch):
    _install_fakes(monkeypatch)

    writer = main_module._build_strategy_signal_v2_observe_writer(
        env={
            "STRATEGY_SIGNAL_V2_OBSERVE_ENABLED": "true",
            "STRATEGY_SIGNAL_V2_OBSERVE_PATH": "tmp/observe.jsonl",
        }
    )

    assert isinstance(writer, _FakeWriter)
    assert _FakeSink.constructed_paths == ["tmp/observe.jsonl"]
    assert writer.sink.path == "tmp/observe.jsonl"


def test_observe_bootstrap_init_failure_disables_observe(monkeypatch, caplog):
    _install_fakes(monkeypatch, sink_cls=_FailingSink)
    caplog.set_level("WARNING")

    writer = main_module._build_strategy_signal_v2_observe_writer(
        env={"STRATEGY_SIGNAL_V2_OBSERVE_ENABLED": "true"}
    )

    assert writer is None
    assert "StrategySignalV2 observe init failed; observe disabled" in caplog.text


def test_observe_bootstrap_non_true_values_are_disabled(monkeypatch):
    _install_fakes(monkeypatch, sink_cls=_FailingSink)

    writer = main_module._build_strategy_signal_v2_observe_writer(
        env={"STRATEGY_SIGNAL_V2_OBSERVE_ENABLED": "1"}
    )

    assert writer is None


def test_observe_bootstrap_does_not_read_or_mutate_runtime_profile(monkeypatch):
    _install_fakes(monkeypatch)

    env = {
        "RUNTIME_PROFILE": "live_profile_must_not_be_used_here",
        "STRATEGY_SIGNAL_V2_OBSERVE_ENABLED": "true",
    }
    writer = main_module._build_strategy_signal_v2_observe_writer(env=env)

    assert isinstance(writer, _FakeWriter)
    assert env["RUNTIME_PROFILE"] == "live_profile_must_not_be_used_here"
