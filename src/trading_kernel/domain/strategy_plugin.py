"""Static strategy plugin registration; never a dynamic code-loading boundary."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache

from src.trading_kernel.domain.detector import StrategyDetector
from src.trading_kernel.domain.strategy_registry import RegisteredStrategyContract


class UniverseKind(StrEnum):
    DIRECT = "direct"
    COMPARATIVE = "comparative"
    RANKED = "ranked"


DetectorFactory = Callable[[RegisteredStrategyContract], StrategyDetector]


@dataclass(frozen=True)
class StrategyPlugin:
    event_spec_id: str
    event_id: str
    universe_kind: UniverseKind
    detector_factory: DetectorFactory

    def detector(self, contract: RegisteredStrategyContract) -> StrategyDetector:
        if contract.event_spec_id != self.event_spec_id:
            raise ValueError("plugin and Event contract identities differ")
        return self.detector_factory(contract)


@lru_cache(maxsize=1)
def strategy_plugins() -> tuple[StrategyPlugin, ...]:
    from src.trading_kernel.domain.detectors.brf2 import BRF2ShortDetector
    from src.trading_kernel.domain.detectors.cpm import CPMLongDetector
    from src.trading_kernel.domain.detectors.mi import MILongDetector
    from src.trading_kernel.domain.detectors.mpg import MPGLongDetector
    from src.trading_kernel.domain.detectors.rsr_vcb import RSRVCBDetector
    from src.trading_kernel.domain.detectors.sor import SORDetector

    specifications: tuple[
        tuple[str, str, UniverseKind, DetectorFactory],
        ...,
    ] = (
        (
            "event_spec:CPM-RO-001:CPM-LONG:v2",
            "CPM-LONG",
            UniverseKind.DIRECT,
            CPMLongDetector,
        ),
        (
            "event_spec:MPG-001:MPG-LONG:v2",
            "MPG-LONG",
            UniverseKind.COMPARATIVE,
            MPGLongDetector,
        ),
        (
            "event_spec:MI-001:MI-LONG:v2",
            "MI-LONG",
            UniverseKind.COMPARATIVE,
            MILongDetector,
        ),
        (
            "event_spec:SOR-001:SOR-LONG:v2",
            "SOR-LONG",
            UniverseKind.DIRECT,
            SORDetector,
        ),
        (
            "event_spec:SOR-001:SOR-SHORT:v2",
            "SOR-SHORT",
            UniverseKind.DIRECT,
            SORDetector,
        ),
        (
            "event_spec:BRF2-001:BRF2-SHORT:v2",
            "BRF2-SHORT",
            UniverseKind.DIRECT,
            BRF2ShortDetector,
        ),
        (
            "event_spec:RSRVCB-001:RSRVCB-LONG-15M:v1",
            "RSRVCB-LONG-15M",
            UniverseKind.RANKED,
            RSRVCBDetector,
        ),
    )
    return tuple(
        StrategyPlugin(
            event_spec_id=event_spec_id,
            event_id=event_id,
            universe_kind=universe_kind,
            detector_factory=factory,
        )
        for event_spec_id, event_id, universe_kind, factory in specifications
    )


def strategy_plugin_for(event_spec_id: str) -> StrategyPlugin:
    for plugin in strategy_plugins():
        if plugin.event_spec_id == event_spec_id:
            return plugin
    raise KeyError(f"unknown Event Spec plugin: {event_spec_id}")
