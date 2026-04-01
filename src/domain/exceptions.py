"""
Unified exception classes with error codes.
All modules must use these exceptions - do not define custom exceptions.
"""


class CryptoMonitorError(Exception):
    """Base class for all business exceptions"""
    def __init__(self, message: str, error_code: str):
        self.error_code = error_code
        super().__init__(f"[{error_code}] {message}")


# ============================================================
# FATAL - System cannot start or must stop immediately
# ============================================================
class FatalStartupError(CryptoMonitorError):
    """
    Critical errors that prevent system startup.
    System must refuse to start and exit immediately.
    """
    pass


# ============================================================
# CRITICAL - Connection lost, system in degraded mode
# ============================================================
class ConnectionLostError(CryptoMonitorError):
    """
    Critical connection failures.
    System should send alerts via webhook and enter degraded mode.
    """
    pass


# ============================================================
# WARNING - Data quality issues, skip current calculation
# ============================================================
class DataQualityWarning(CryptoMonitorError):
    """
    Data quality warnings.
    Log the issue and skip current calculation, continue processing other data.
    """
    pass


# ============================================================
# Trading Errors - Phase 5 (Real Exchange Integration)
# ============================================================
class InsufficientMarginError(FatalStartupError):
    """
    Insufficient margin to place order.
    Order rejected by exchange due to insufficient funds.
    """
    pass


class InvalidOrderError(FatalStartupError):
    """
    Invalid order parameters.
    Order rejected by exchange due to parameter validation failure.
    """
    pass


class OrderNotFoundError(FatalStartupError):
    """
    Order not found.
    Raised when attempting to cancel or query a non-existent order.
    """
    pass


class OrderAlreadyFilledError(FatalStartupError):
    """
    Order already filled.
    Raised when attempting to cancel an order that has been executed.
    """
    pass


# ============================================================
# Order Validation Errors (P0-004)
# ============================================================
class InvalidOrderAmountError(InvalidOrderError):
    """
    Invalid order amount.
    Order rejected due to minimum notional value violation.
    """
    pass


class InvalidOrderPriceError(InvalidOrderError):
    """
    Invalid order price.
    Order rejected due to price deviation from market price.
    """
    pass


class RateLimitError(ConnectionLostError):
    """
    Rate limit exceeded.
    Exchange API rate limit hit, must back off and retry.
    """
    pass


# ============================================================
# Error Code Reference
# ============================================================
# F-001: API Key has trade permission
# F-002: API Key has withdraw permission
# F-003: Missing required config field
# F-004: Exchange initialization failed
# F-010: Insufficient margin
# F-011: Invalid order parameters
# F-012: Order not found
# F-013: Order already filled
# C-001: WebSocket reconnection limit exceeded
# C-002: REST asset polling consecutive failures
# C-010: Rate limit exceeded
# W-001: K-line data quality issue (high < low, etc.)
# W-002: Data delay exceeds threshold
