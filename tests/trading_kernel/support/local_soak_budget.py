"""Host-side test safety, never a trading or production configuration source."""

import fcntl
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path


class LocalSoakBudgetError(RuntimeError):
    """The requested local test exceeds the Owner's resource/time boundary."""


@dataclass(frozen=True)
class LocalSoakBudget:
    started_at: float
    total_seconds: int = 600

    def remaining_seconds(self, *, now: float) -> float:
        remaining = self.total_seconds-(now-self.started_at)
        if remaining <= 0:
            raise LocalSoakBudgetError("local soak reached its 600 second total limit")
        return remaining

    def require_local_mode(self, mode: str) -> None:
        if mode == "healthy_24h":
            raise LocalSoakBudgetError("long soak is deferred to separately authorized server validation")
        if mode not in {"consumed_close", "four_processes", "idle_static_four"}:
            raise LocalSoakBudgetError("unknown local soak mode")


@contextmanager
def exclusive_local_soak(path: Path) -> Iterator[None]:
    """Kernel lock: crash-safe, no PID file and no stale-owner guessing."""
    with path.open("a") as handle:
        try:
            fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise LocalSoakBudgetError("another heavy local soak is already running") from exc
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(),fcntl.LOCK_UN)
