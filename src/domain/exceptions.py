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
# Error Code Reference
# ============================================================
# F-001: API Key has trade permission
# F-002: API Key has withdraw permission
# F-003: Missing required config field
# F-004: Exchange initialization failed
# C-001: WebSocket reconnection limit exceeded
# C-002: REST asset polling consecutive failures
# W-001: K-line data quality issue (high < low, etc.)
# W-002: Data delay exceeds threshold
