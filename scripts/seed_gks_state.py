"""Seed the single Global Kill Switch row in PG.

Default behavior is fail-safe: seed the row as active=True so deployment setup
does not accidentally allow new entries. Operators can explicitly pass
--inactive for controlled non-live/testnet smoke setup after Owner approval.
"""

from __future__ import annotations

import argparse
import asyncio
import time

from src.infrastructure.pg_global_kill_switch_repository import (
    PgGlobalKillSwitchRepository,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed PG Global Kill Switch state row.")
    state = parser.add_mutually_exclusive_group()
    state.add_argument(
        "--active",
        action="store_true",
        help="Seed the row as active=True. This is also the default.",
    )
    state.add_argument(
        "--inactive",
        action="store_true",
        help="Seed the row as active=False. Use only after explicit Owner approval.",
    )
    parser.add_argument(
        "--reason",
        default="GKS_SEEDED_ACTIVE",
        help="Operator-visible reason stored with the row.",
    )
    parser.add_argument(
        "--updated-by",
        default="ops_seed_gks_state",
        help="Operator or automation name stored with the row.",
    )
    return parser.parse_args()


async def _main() -> None:
    args = _parse_args()
    active = not args.inactive
    reason = args.reason
    if args.inactive and reason == "GKS_SEEDED_ACTIVE":
        reason = "GKS_SEEDED_INACTIVE_OWNER_APPROVED"

    repository = PgGlobalKillSwitchRepository()
    await repository.initialize()
    snapshot = await repository.set_state(
        active=active,
        reason=reason,
        updated_by=args.updated_by,
        updated_at_ms=int(time.time() * 1000),
    )
    print(
        "GKS row seeded: "
        f"active={snapshot.active}, reason={snapshot.reason}, "
        f"updated_by={snapshot.updated_by}, source={snapshot.source}"
    )


if __name__ == "__main__":
    asyncio.run(_main())
