"""Order-type vocabulary shared by strategy and Ticket semantics."""

from enum import StrEnum


class EntryOrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"
