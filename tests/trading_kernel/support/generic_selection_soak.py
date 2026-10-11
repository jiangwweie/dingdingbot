"""Frozen synthetic engineering tape and metrics; never production authority.

One immutable close has one value across all four strategies and overlapping
windows. The 4/5 rotation rate is workload, not a Selection parameter. Numeric
installation evidence, activation, warming and Entry gates remain independent.
"""

from dataclasses import dataclass
from decimal import Decimal, localcontext

from src.trading_kernel.domain.dynamic_selection_numeric import (
    DYNAMIC_SELECTION_DECIMAL_CONTEXT,
)
from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
from src.trading_kernel.domain.generic_selection_core import (
    GenericSelectionInput,
    GenericSelectionSnapshotV1,
)
from src.trading_kernel.domain.generic_selection_source import GenericSelectionCandle
from src.trading_kernel.domain.generic_selection_spec import GenericSelectionSpecV1
from tests.trading_kernel.support.generic_selection import HOUR, inputs

SOAK_GROUPS = ("CPM-RO-001", "MPG-001", "MI-001", "BRF2-001")
SOAK_CUTOFF = 600*HOUR


class SoakWorkload:
    """Deterministic 24h tape with warm-up history and actual rank hysteresis."""

    def __init__(self) -> None:
        self._sources = {group: inputs(group) for group in SOAK_GROUPS}
        self._tape: dict[str, dict[int, GenericSelectionCandle]] = {}
        with localcontext(DYNAMIC_SELECTION_DECIMAL_CONTEXT):
            for index, member in enumerate(self._sources[SOAK_GROUPS[0]].spec.candidate_ids):
                price = Decimal(100)
                candles = {}
                for hour in range(-100, 26):
                    rank_index = (index-hour*4//5) % 24
                    rate = Decimal(24-rank_index)/Decimal(10000)
                    if rank_index >= 20 and hour % 2:
                        rate = -rate
                    if hour >= -96:
                        price *= 1+rate
                    close_ms = SOAK_CUTOFF+hour*HOUR
                    candles[close_ms] = GenericSelectionCandle(
                        open_time_ms=close_ms-HOUR, close_time_ms=close_ms,
                        open=price, close=price, high=price*Decimal("1.01"), low=price*Decimal("0.99"),
                        base_volume=Decimal(10), quote_volume=price*10,
                    )
                self._tape[member] = candles

    def spec(self, group: str) -> GenericSelectionSpecV1:
        return self._sources[group].spec

    def candles(self, member: str, *, close_ms: int, count: int) -> tuple[GenericSelectionCandle, ...]:
        return tuple(self._tape[member][close_ms-(count-1-index)*HOUR] for index in range(count))

    def selection_input(self, group: str, *, cutoff_ms: int,
                        predecessor: GenericSelectionSnapshotV1 | None = None,
                        epoch: str = "epoch:gs12-frozen-tape") -> GenericSelectionInput:
        source = self._sources[group]
        return source.model_copy(update={
            "selection_epoch_id": epoch, "feature_cutoff_at_ms": cutoff_ms,
            "decision_at_ms": cutoff_ms, "source_observed_at_ms": cutoff_ms+10,
            "committed_at_ms": cutoff_ms+20, "predecessor_snapshot": predecessor,
            "member_windows": tuple(window.model_copy(update={
                "candles": self.candles(window.exchange_instrument_id, close_ms=cutoff_ms, count=source.spec.window_bars),
                "qualification": window.qualification.model_copy(update={"observed_at_ms": cutoff_ms+10}),
            }) for window in source.member_windows),
        })

    @property
    def semantic_digest(self) -> str:
        return canonical_digest({"version": "gs12-rotating-common-tape-v1", "groups": SOAK_GROUPS,
                                 "tape": {member: tuple(c.model_dump(mode="python") for c in rows.values())
                                          for member, rows in self._tape.items()}})


@dataclass(frozen=True)
class SoakResourceFacts:
    cpu_cores: Decimal
    memory_limit_bytes: int

    @classmethod
    def from_cgroup(cls, *, cpu_max: str, memory_max: str) -> "SoakResourceFacts":
        try:
            quota, period = cpu_max.split()
            cores = Decimal(quota)/Decimal(period)
            memory = int(memory_max)
        except (ValueError, ArithmeticError) as exc:
            raise ValueError("soak resource limits are absent or invalid") from exc
        if cores != 1 or memory != 1024**3:
            raise ValueError("soak resource limits differ from 1CPU/1GiB")
        return cls(cpu_cores=cores, memory_limit_bytes=memory)


def percentile95(values: tuple[int, ...]) -> int | None:
    """Nearest-rank empirical p95, with sample count reported separately."""
    if not values:
        return None
    return sorted(values)[(95*len(values)+99)//100-1]


def vacuum_time_union_ms(intervals: tuple[tuple[int, int], ...], *, start_ms: int, end_ms: int) -> int:
    if end_ms < start_ms or any(right < left for left, right in intervals):
        raise ValueError("invalid vacuum observation interval")
    merged_end = start_ms
    total = 0
    for left, right in sorted(intervals):
        left, right = max(left, start_ms, merged_end), min(right, end_ms)
        if right > left:
            total += right-left
            merged_end = right
    return total
