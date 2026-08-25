"""Tracked, explicit verification portfolios for the R0-R4 release model.

P2.1 defines these portfolios only.  Candidate classification and deployment
selection remain owned by ``scripts/classify_release.py`` and later P2.2 work;
the Kernel certification continues to use the complete current portfolio.
"""

from __future__ import annotations

import json
from hashlib import sha256
from typing import Final

Command = tuple[str, ...]
CommandSet = tuple[Command, ...]

FAST_KERNEL_COMMANDS: Final[CommandSet] = (
    (
        ".venv/bin/python",
        "-m",
        "pytest",
        "tests/trading_kernel/unit",
        "tests/trading_kernel/architecture",
        "-q",
    ),
    (
        ".venv/bin/ruff",
        "check",
        "src/trading_kernel",
        "scripts/trading_kernel",
        "tests/trading_kernel",
        "migrations/trading_kernel",
    ),
    (".venv/bin/mypy", "src/trading_kernel", "scripts/trading_kernel"),
    ("git", "diff", "--check"),
)

R1_STATIC_COMMANDS: Final[CommandSet] = (
    ("pnpm", "--dir", "frontend/owner-console", "run", "typecheck"),
    ("pnpm", "--dir", "frontend/owner-console", "run", "build"),
)

R2_OWNER_API_COMMANDS: Final[CommandSet] = (
    (
        ".venv/bin/python",
        "-m",
        "pytest",
        "tests/trading_kernel/unit/owner_console",
        "tests/trading_kernel/unit/test_owner_control.py",
        "tests/trading_kernel/interfaces/test_owner_console_http.py",
        "tests/trading_kernel/architecture/test_owner_console_deployment.py",
        "-q",
    ),
    (
        ".venv/bin/ruff",
        "check",
        "scripts/owner_console",
        "src/trading_kernel/application/owner_console",
        "src/trading_kernel/interfaces/owner_console_http",
        "src/trading_kernel/infrastructure/owner_market_data.py",
        "src/trading_kernel/infrastructure/pg_owner_control.py",
        "src/trading_kernel/infrastructure/pg_owner_read_repository.py",
        "tests/trading_kernel/unit/owner_console",
        "tests/trading_kernel/unit/test_owner_control.py",
        "tests/trading_kernel/interfaces/test_owner_console_http.py",
        "tests/trading_kernel/architecture/test_owner_console_deployment.py",
    ),
    ("git", "diff", "--check"),
)

# Until P2.2 binds a classified candidate to a narrower same-schema slice,
# this remains the complete current Kernel Release Certification portfolio.
R3_SAME_SCHEMA_KERNEL_COMMANDS: Final[CommandSet] = (
    (
        ".venv/bin/python",
        "-m",
        "pytest",
        "tests/trading_kernel/unit",
        "tests/trading_kernel/architecture",
        "-q",
    ),
    (".venv/bin/python", "-m", "pytest", "tests/trading_kernel/integration", "-q"),
    (".venv/bin/python", "-m", "pytest", "tests/trading_kernel/full_chain", "-q"),
    (
        ".venv/bin/ruff",
        "check",
        "src/trading_kernel",
        "scripts/trading_kernel",
        "tests/trading_kernel",
        "migrations/trading_kernel",
    ),
    (".venv/bin/mypy", "src/trading_kernel", "scripts/trading_kernel"),
    ("git", "diff", "--check"),
)

R4_SCHEMA_AUTHORITY_COMMANDS: Final[CommandSet] = (
    *R3_SAME_SCHEMA_KERNEL_COMMANDS,
    (
        ".venv/bin/python",
        "scripts/trading_kernel/verify_sor_dynamic_selection_golden.py",
        "verify",
        "--artifact-dir",
        "tests/trading_kernel/fixtures/sor_dynamic_selection_v0",
    ),
    (
        ".venv/bin/python",
        "scripts/trading_kernel/verify_sor_dynamic_selection_core_parity.py",
    ),
    (
        ".venv/bin/python",
        "-m",
        "pytest",
        "tests/trading_kernel/integration/test_sor_v3_compatible_migration.py",
        "tests/trading_kernel/integration/test_portfolio_admission_observability_migration.py",
        "tests/trading_kernel/integration/test_portfolio_admission_flat_compatible_deployment.py",
        "tests/trading_kernel/integration/test_tradfi_instrument_center_upgrade.py",
        "tests/trading_kernel/integration/test_clean_baseline_rebuild.py",
        "-q",
    ),
)

PERIODIC_AUDIT_COMMANDS: Final[CommandSet] = (
    *R4_SCHEMA_AUTHORITY_COMMANDS,
    (
        ".venv/bin/python",
        "-m",
        "pytest",
        "tests/trading_kernel/integration/test_bootstrap_schema.py",
        "tests/trading_kernel/integration/test_strategy_universe_local_release_rehearsal.py",
        "tests/trading_kernel/full_chain/test_portfolio_admission_observability.py",
        "-q",
    ),
)


def command_set_digest(commands: CommandSet) -> str:
    payload = json.dumps(commands, separators=(",", ":"), ensure_ascii=True)
    return f"sha256:{sha256(payload.encode()).hexdigest()}"


def validate_command_set(commands: CommandSet) -> None:
    if not commands:
        raise ValueError("verification portfolio cannot be empty")
    if len(set(commands)) != len(commands):
        raise ValueError("verification portfolio repeats a command")
    if any(not command or any(not part for part in command) for command in commands):
        raise ValueError("verification command must contain nonempty arguments")
