"""Stable, non-sensitive HTTP error responses for the Owner Console."""

from __future__ import annotations

from fastapi.responses import JSONResponse


class UnauthorizedError(Exception):
    """Raised when the sole active Owner Session is absent or invalid."""


class PublicMarketFailure(Exception):
    """Raised when bounded credential-free market data cannot be read."""


def error_response(
    *,
    status_code: int,
    code: str,
    message: str,
) -> JSONResponse:
    """Return the one public error-envelope shape without internal details."""

    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )


def unauthorized_response() -> JSONResponse:
    """Return the stable unauthenticated response used by all protected routes."""

    return error_response(
        status_code=401,
        code="unauthorized",
        message="Authentication required",
    )
