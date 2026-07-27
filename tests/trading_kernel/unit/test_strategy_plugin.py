from __future__ import annotations

import pytest

from src.trading_kernel.domain.strategy_plugin import (
    UniverseKind,
    strategy_plugin_for,
    strategy_plugins,
)


def test_static_plugin_registry_has_all_seven_events() -> None:
    plugins = strategy_plugins()

    assert len(plugins) == 7
    assert {plugin.event_id for plugin in plugins} == {
        "CPM-LONG",
        "MPG-LONG",
        "MI-LONG",
        "SOR-LONG",
        "SOR-SHORT",
        "BRF2-SHORT",
        "RSRVCB-LONG-15M",
    }
    assert (
        strategy_plugin_for(
            "event_spec:RSRVCB-001:RSRVCB-LONG-15M:v1"
        ).universe_kind
        is UniverseKind.RANKED
    )


def test_plugin_lookup_is_exact_and_fail_closed() -> None:
    first = strategy_plugins()[0]

    assert strategy_plugin_for(first.event_spec_id) is first
    with pytest.raises(KeyError, match="unknown Event Spec plugin"):
        strategy_plugin_for("event_spec:unknown")
