"""Task-local transport guard after CCXT loading/throttling, with no blind retry."""

from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass


@dataclass
class MutationSendContext:
    before_send: Callable[[], Awaitable[None]]
    attempted: bool = False


current_mutation_guard: ContextVar[MutationSendContext | None] = ContextVar(
    "kernel_mutation_guard", default=None
)
