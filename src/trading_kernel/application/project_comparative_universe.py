"""Build one shared, typed comparative market projection per Universe close."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from decimal import Decimal
from threading import Lock
from typing import Sequence

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.trading_kernel.application.market_ports import (
    ClosedCandleRequest,
    PublicMarketSource,
)
from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
from src.trading_kernel.domain.market import (
    ClosedCandle,
    ComparativeStrengthMember,
    ComparativeStrengthSnapshot,
)


@dataclass
class _ProjectionLockState:
    lock: asyncio.Lock
    users: int = 0


_PROJECTION_LOCKS_GUARD = Lock()
_PROJECTION_LOCKS: dict[
    tuple[str, str, int, str],
    _ProjectionLockState,
] = {}


class ComparativeMemberWindow(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exchange_instrument_id: str
    candles_1h: tuple[ClosedCandle, ...]

    @field_validator("exchange_instrument_id", mode="before")
    @classmethod
    def _require_instrument(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("comparative member instrument must be non-blank")
        return normalized

    @model_validator(mode="after")
    def _validate_window(self) -> "ComparativeMemberWindow":
        if not self.candles_1h:
            raise ValueError("comparative member window must not be empty")
        close_times = tuple(item.close_time_ms for item in self.candles_1h)
        if close_times != tuple(sorted(close_times)) or len(close_times) != len(
            set(close_times)
        ):
            raise ValueError(
                "comparative member candles must have unique increasing closes"
            )
        return self


class ComparativeUniverseProjection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_spec_id: str
    universe_version_id: str
    member_set_digest: str
    closed_bar_time_ms: int
    member_windows: tuple[ComparativeMemberWindow, ...]
    comparative_strength: ComparativeStrengthSnapshot
    observed_at_ms: int
    valid_until_ms: int
    projection_version: int = 1

    @field_validator(
        "event_spec_id",
        "universe_version_id",
        "member_set_digest",
        mode="before",
    )
    @classmethod
    def _require_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("comparative projection identity must be non-blank")
        return normalized

    @model_validator(mode="after")
    def _validate_projection(self) -> "ComparativeUniverseProjection":
        if (
            self.closed_bar_time_ms <= 0
            or self.observed_at_ms != self.closed_bar_time_ms
            or self.valid_until_ms <= self.observed_at_ms
            or self.projection_version <= 0
        ):
            raise ValueError("comparative projection timing is invalid")
        window_members = tuple(
            item.exchange_instrument_id for item in self.member_windows
        )
        if (
            not window_members
            or window_members != tuple(sorted(window_members))
            or len(window_members) != len(set(window_members))
        ):
            raise ValueError(
                "comparative projection members must be unique and sorted"
            )
        if self.member_set_digest != comparative_member_set_digest(
            window_members
        ):
            raise ValueError("comparative projection member digest is invalid")
        strength = self.comparative_strength
        if (
            strength.trigger_candle_close_time_ms != self.closed_bar_time_ms
            or strength.observed_at_ms != self.observed_at_ms
            or strength.valid_until_ms != self.valid_until_ms
            or {item.exchange_instrument_id for item in strength.members}
            != set(window_members)
        ):
            raise ValueError(
                "comparative strength differs from projection identity"
            )
        if any(
            window.candles_1h[-1].close_time_ms != self.closed_bar_time_ms
            or any(
                candle.close_time_ms > self.closed_bar_time_ms
                for candle in window.candles_1h
            )
            for window in self.member_windows
        ):
            raise ValueError(
                "comparative member windows must share the exact closed bar"
            )
        return self

    def candles_for(
        self,
        exchange_instrument_id: str,
    ) -> tuple[ClosedCandle, ...]:
        for window in self.member_windows:
            if window.exchange_instrument_id == exchange_instrument_id:
                return window.candles_1h
        raise KeyError(exchange_instrument_id)


def comparative_member_set_digest(
    exchange_instrument_ids: Sequence[str],
) -> str:
    canonical_members = tuple(sorted(exchange_instrument_ids))
    if not canonical_members or len(canonical_members) != len(
        set(canonical_members)
    ):
        raise ValueError("comparative projection requires unique members")
    return canonical_digest(
        {"exchange_instrument_ids": canonical_members}
    )


@asynccontextmanager
async def serialize_comparative_projection(
    *,
    event_spec_id: str,
    universe_version_id: str,
    closed_bar_time_ms: int,
    member_set_digest: str,
) -> AsyncIterator[None]:
    """Coalesce same-process projector work; PostgreSQL remains authority."""

    key = (
        event_spec_id,
        universe_version_id,
        closed_bar_time_ms,
        member_set_digest,
    )
    with _PROJECTION_LOCKS_GUARD:
        state = _PROJECTION_LOCKS.get(key)
        if state is None:
            state = _ProjectionLockState(lock=asyncio.Lock())
            _PROJECTION_LOCKS[key] = state
        state.users += 1
    acquired = False
    try:
        await state.lock.acquire()
        acquired = True
        yield
    finally:
        if acquired:
            state.lock.release()
        with _PROJECTION_LOCKS_GUARD:
            state.users -= 1
            if state.users == 0:
                _PROJECTION_LOCKS.pop(key, None)


def build_comparative_universe_projection(
    *,
    event_spec_id: str,
    universe_version_id: str,
    strategy_group_id: str,
    exchange_instrument_ids: Sequence[str],
    closed_bar_time_ms: int,
    lookback_bars: int,
    freshness_window_ms: int,
    member_windows: tuple[ComparativeMemberWindow, ...],
) -> ComparativeUniverseProjection:
    if (
        closed_bar_time_ms <= 0
        or lookback_bars <= 0
        or freshness_window_ms <= 0
    ):
        raise ValueError("comparative projection window must be positive")
    expected_members = tuple(sorted(exchange_instrument_ids))
    windows = tuple(
        sorted(
            member_windows,
            key=lambda item: item.exchange_instrument_id,
        )
    )
    if (
        tuple(item.exchange_instrument_id for item in windows)
        != expected_members
    ):
        raise ValueError("comparative projection requires the exact member set")

    returns: list[tuple[str, Decimal]] = []
    minimum_candles = lookback_bars + 1
    for window in windows:
        if (
            len(window.candles_1h) < minimum_candles
            or window.candles_1h[-1].close_time_ms != closed_bar_time_ms
        ):
            raise ValueError(
                "comparative projection requires complete same-close windows"
            )
        sample = window.candles_1h[-minimum_candles:]
        return_pct = (
            (sample[-1].close - sample[0].close) / sample[0].close
        ) * Decimal("100")
        returns.append((window.exchange_instrument_id, return_pct))

    ranked = tuple(sorted(returns, key=lambda item: (-item[1], item[0])))
    valid_until_ms = closed_bar_time_ms + freshness_window_ms
    comparative_strength = ComparativeStrengthSnapshot(
        strategy_group_id=strategy_group_id,
        timeframe="1h",
        lookback_bars=lookback_bars,
        trigger_candle_close_time_ms=closed_bar_time_ms,
        members=tuple(
            ComparativeStrengthMember(
                exchange_instrument_id=instrument_id,
                return_pct=return_pct,
                rank=rank,
            )
            for rank, (instrument_id, return_pct) in enumerate(
                ranked,
                start=1,
            )
        ),
        observed_at_ms=closed_bar_time_ms,
        valid_until_ms=valid_until_ms,
        source_ref=(
            f"public_closed_ohlcv:{strategy_group_id}:"
            f"{closed_bar_time_ms}:comparative"
        ),
    )
    return ComparativeUniverseProjection(
        event_spec_id=event_spec_id,
        universe_version_id=universe_version_id,
        member_set_digest=comparative_member_set_digest(expected_members),
        closed_bar_time_ms=closed_bar_time_ms,
        member_windows=windows,
        comparative_strength=comparative_strength,
        observed_at_ms=closed_bar_time_ms,
        valid_until_ms=valid_until_ms,
    )


async def project_comparative_universe(
    market_source: PublicMarketSource,
    *,
    event_spec_id: str,
    universe_version_id: str,
    strategy_group_id: str,
    exchange_instrument_ids: tuple[str, ...],
    closed_bar_time_ms: int,
    lookback_bars: int,
    freshness_window_ms: int,
) -> ComparativeUniverseProjection:
    async def load_member(
        exchange_instrument_id: str,
    ) -> ComparativeMemberWindow:
        candles = await market_source.fetch_closed_candles(
            ClosedCandleRequest(
                exchange_instrument_id=exchange_instrument_id,
                timeframe="1h",
                limit=25,
                closed_at_ms=closed_bar_time_ms,
            )
        )
        closed = tuple(
            item
            for item in candles
            if item.close_time_ms <= closed_bar_time_ms
        )[-25:]
        return ComparativeMemberWindow(
            exchange_instrument_id=exchange_instrument_id,
            candles_1h=closed,
        )

    windows = await asyncio.gather(
        *(load_member(member) for member in exchange_instrument_ids)
    )
    return build_comparative_universe_projection(
        event_spec_id=event_spec_id,
        universe_version_id=universe_version_id,
        strategy_group_id=strategy_group_id,
        exchange_instrument_ids=exchange_instrument_ids,
        closed_bar_time_ms=closed_bar_time_ms,
        lookback_bars=lookback_bars,
        freshness_window_ms=freshness_window_ms,
        member_windows=tuple(windows),
    )
