"""Emit deterministic Owner Console OpenAPI JSON without starting resources."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import cast

from sqlalchemy.ext.asyncio import AsyncEngine

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading_kernel.infrastructure.owner_market_data import OwnerMarketData
from src.trading_kernel.interfaces.owner_console_http.app import (
    create_owner_console_app,
)
from src.trading_kernel.interfaces.owner_console_http.auth import OwnerAuthSettings
from src.trading_kernel.interfaces.owner_console_http.dependencies import (
    OwnerConsoleSettings,
)

_SETTINGS = OwnerConsoleSettings(
    database_dsn="postgresql+asyncpg://openapi:openapi@localhost/openapi",
    account_id="openapi-account",
    auth=OwnerAuthSettings(
        username="openapi-owner",
        password_hash=(
            "$argon2id$v=19$m=65536,t=3,p=1$lMxt0+Hd+L/ssBunZuF9wQ$"
            "fDYQ0aYM1T1UUssc0yd0nvsClUtTkI9JNZpfOCt4C5o"
        ),
        totp_seed="JBSWY3DPEHPK3PXP",
        session_signing_key="openapi-only-signing-key-not-a-production-secret",
    ),
)


class _StubEngine:
    async def dispose(self) -> None:
        return None


class _StubMarketData:
    async def close(self) -> None:
        return None


def main() -> None:
    """Write compact, sorted OpenAPI JSON and nothing else to standard output."""

    app = create_owner_console_app(
        _SETTINGS,
        engine=cast(AsyncEngine, _StubEngine()),
        market_data=cast(OwnerMarketData, _StubMarketData()),
    )
    sys.stdout.write(
        json.dumps(
            app.openapi(),
            sort_keys=True,
            separators=(",", ":"),
        )
    )


if __name__ == "__main__":
    main()
