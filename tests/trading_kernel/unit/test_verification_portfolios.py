from __future__ import annotations

from scripts.trading_kernel.verification_portfolios import (
    FAST_KERNEL_COMMANDS,
    PERIODIC_AUDIT_COMMANDS,
    R1_STATIC_COMMANDS,
    R2_OWNER_API_COMMANDS,
    R3_SAME_SCHEMA_KERNEL_COMMANDS,
    R4_SCHEMA_AUTHORITY_COMMANDS,
    command_set_digest,
    validate_command_set,
)


def test_every_tracked_portfolio_is_nonempty_unique_and_digest_stable() -> None:
    portfolios = (
        FAST_KERNEL_COMMANDS,
        R1_STATIC_COMMANDS,
        R2_OWNER_API_COMMANDS,
        R3_SAME_SCHEMA_KERNEL_COMMANDS,
        R4_SCHEMA_AUTHORITY_COMMANDS,
        PERIODIC_AUDIT_COMMANDS,
    )

    for commands in portfolios:
        validate_command_set(commands)
        assert command_set_digest(commands) == command_set_digest(commands)


def test_schema_and_periodic_portfolios_extend_their_lower_boundaries() -> None:
    assert R4_SCHEMA_AUTHORITY_COMMANDS[: len(R3_SAME_SCHEMA_KERNEL_COMMANDS)] == (
        R3_SAME_SCHEMA_KERNEL_COMMANDS
    )
    assert PERIODIC_AUDIT_COMMANDS[: len(R4_SCHEMA_AUTHORITY_COMMANDS)] == (
        R4_SCHEMA_AUTHORITY_COMMANDS
    )
