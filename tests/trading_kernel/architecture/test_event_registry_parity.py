from __future__ import annotations

from typing import get_args

from src.trading_kernel.domain.events import TradeEvent
from src.trading_kernel.infrastructure.pg_repositories import _EVENT_MODELS


def test_every_trade_event_is_registered_for_postgres_reload() -> None:
    domain_event_names = {event_type.__name__ for event_type in get_args(TradeEvent)}
    persisted_event_names = set(_EVENT_MODELS)

    assert persisted_event_names == domain_event_names
    assert len(_EVENT_MODELS) == len(domain_event_names)
