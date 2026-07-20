"""Monotonic deadline conservation for one bounded Action-Time attempt."""

from __future__ import annotations

from dataclasses import dataclass


SYSTEM_ACTION_TIME_BUDGET_MS = 30_000


@dataclass(frozen=True)
class ActionTimeDeadline:
    """The deadline can shrink as new facts arrive, but can never extend."""

    opened_wall_ms: int
    opened_monotonic_ms: int
    global_deadline_ms: int
    monotonic_deadline_ms: int

    @classmethod
    def start(
        cls,
        *,
        opened_wall_ms: int,
        opened_monotonic_ms: int,
        expiry_candidates_ms: tuple[int, ...] = (),
        system_budget_ms: int = SYSTEM_ACTION_TIME_BUDGET_MS,
    ) -> "ActionTimeDeadline":
        if system_budget_ms <= 0:
            raise ValueError("action_time_deadline_budget_invalid")
        valid_expiries = tuple(
            int(value) for value in expiry_candidates_ms if int(value) > opened_wall_ms
        )
        global_deadline_ms = min(
            (opened_wall_ms + int(system_budget_ms), *valid_expiries)
        )
        return cls(
            opened_wall_ms=int(opened_wall_ms),
            opened_monotonic_ms=int(opened_monotonic_ms),
            global_deadline_ms=global_deadline_ms,
            monotonic_deadline_ms=(
                int(opened_monotonic_ms) + global_deadline_ms - int(opened_wall_ms)
            ),
        )

    def shorten(self, *, expiry_candidates_ms: tuple[int, ...]) -> "ActionTimeDeadline":
        valid_expiries = tuple(
            int(value)
            for value in expiry_candidates_ms
            if int(value) > self.opened_wall_ms
        )
        if not valid_expiries:
            return self
        global_deadline_ms = min(self.global_deadline_ms, *valid_expiries)
        return ActionTimeDeadline(
            opened_wall_ms=self.opened_wall_ms,
            opened_monotonic_ms=self.opened_monotonic_ms,
            global_deadline_ms=global_deadline_ms,
            monotonic_deadline_ms=(
                self.opened_monotonic_ms + global_deadline_ms - self.opened_wall_ms
            ),
        )

    def remaining_ms(self, *, monotonic_now_ms: int) -> int:
        return max(0, self.monotonic_deadline_ms - int(monotonic_now_ms))
