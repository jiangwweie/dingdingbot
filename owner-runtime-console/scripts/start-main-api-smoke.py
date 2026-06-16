#!/usr/bin/env python3
"""Start the main FastAPI app for Owner Console smoke tests.

The main composition root loads local dotenv files during import. This helper
imports the app first, then reapplies the smoke-test auth environment so the
browser smoke can log in without reading or mutating real operator secrets.
"""

from __future__ import annotations

import os
import sys

import uvicorn

from src.interfaces import api as api_module


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8028
    for name in (
        "BRC_OPERATOR_USERNAME",
        "BRC_OPERATOR_PASSWORD_HASH",
        "BRC_OPERATOR_TOTP_SECRET",
        "BRC_OPERATOR_SESSION_SECRET",
        "BRC_OPERATOR_SESSION_TTL_SECONDS",
    ):
        value = os.environ.get(f"SMOKE_{name}")
        if value:
            os.environ[name] = value
    uvicorn.run(api_module.app, host="127.0.0.1", port=port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
