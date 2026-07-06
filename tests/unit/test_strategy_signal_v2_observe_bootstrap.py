from __future__ import annotations

import src.main as main_module


def test_observe_bootstrap_disabled_when_env_unset(caplog):
    caplog.set_level("INFO")

    writer = main_module._build_strategy_signal_v2_observe_writer(env={})

    assert writer is None
    assert "StrategySignalV2 observe disabled" in caplog.text


def test_observe_bootstrap_enabled_does_not_construct_file_sidecar(caplog):
    caplog.set_level("WARNING")

    writer = main_module._build_strategy_signal_v2_observe_writer(
        env={"STRATEGY_SIGNAL_V2_OBSERVE_ENABLED": "true"}
    )

    assert writer is None
    assert "file-backed observe sidecar has been removed" in caplog.text


def test_observe_bootstrap_path_override_is_ignored(caplog):
    caplog.set_level("WARNING")

    writer = main_module._build_strategy_signal_v2_observe_writer(
        env={
            "STRATEGY_SIGNAL_V2_OBSERVE_ENABLED": "true",
            "STRATEGY_SIGNAL_V2_OBSERVE_PATH": "tmp/observe.jsonl",
        }
    )

    assert writer is None
    assert "tmp/observe.jsonl" not in caplog.text


def test_observe_bootstrap_non_true_values_are_disabled():
    writer = main_module._build_strategy_signal_v2_observe_writer(
        env={"STRATEGY_SIGNAL_V2_OBSERVE_ENABLED": "1"}
    )

    assert writer is None


def test_observe_bootstrap_does_not_read_or_mutate_runtime_profile(caplog):
    caplog.set_level("WARNING")
    env = {
        "RUNTIME_PROFILE": "live_profile_must_not_be_used_here",
        "STRATEGY_SIGNAL_V2_OBSERVE_ENABLED": "true",
    }

    writer = main_module._build_strategy_signal_v2_observe_writer(env=env)

    assert writer is None
    assert env["RUNTIME_PROFILE"] == "live_profile_must_not_be_used_here"
