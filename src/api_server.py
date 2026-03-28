"""
Standalone REST API Server (DEPRECATED)

This module is kept as a backup. The API server now runs embedded
within the main application process (src/main.py) to share dependencies.

Current usage: The API server is started in src/main.py Phase 7.5
using uvicorn.Server as a background asyncio task.

To run standalone (not recommended):
    python -m src.api_server
"""
import os
import sys
import signal
import asyncio
import uvicorn

from src.infrastructure.logger import logger


# ============================================================
# DEPRECATED - This module is no longer used
# ============================================================
logger.warning("api_server.py is DEPRECATED. API server now runs embedded in main.py")


def main():
    """Main entry point (deprecated)"""
    logger.error("Cannot run api_server.py standalone - use src/main.py instead")
    sys.exit(1)


if __name__ == "__main__":
    main()
