"""Certified manual-product Entry timing; independent of the send-authority window."""

ENTRY_TIMEOUT_SECONDS = 10
ENTRY_ACTION_FACT_VALIDITY_MS = 30_000


def require_entry_runtime_contract(*, timeout_seconds: float, validity_ms: int) -> None:
    if (timeout_seconds, validity_ms) != (
        ENTRY_TIMEOUT_SECONDS,
        ENTRY_ACTION_FACT_VALIDITY_MS,
    ):
        raise ValueError("Entry runtime timing differs from the certified product contract")
