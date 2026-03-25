"""
Unified logging configuration with secret masking.
All modules must use this logger - no bare print() allowed.
"""
import logging
import sys
from typing import List


# ============================================================
# Secret Masking
# ============================================================
def mask_secret(value: str, visible_chars: int = 4) -> str:
    """
    Mask sensitive data: keep first 4 and last 4 characters, replace middle with ****.

    Example: "abcdefghijklmnop" -> "abcd****mnop"

    Args:
        value: The sensitive string to mask
        visible_chars: Number of characters to show at start and end

    Returns:
        Masked string
    """
    if len(value) <= visible_chars * 2:
        return "****"
    return f"{value[:visible_chars]}****{value[-visible_chars:]}"


def mask_sensitive_data(text: str, secrets: List[str]) -> str:
    """
    Mask all sensitive data in text.

    Args:
        text: The text that may contain sensitive data
        secrets: List of secret strings to mask

    Returns:
        Text with all secrets masked
    """
    result = text
    for secret in secrets:
        if secret:
            result = result.replace(secret, mask_secret(secret))
    return result


# ============================================================
# Logger Configuration
# ============================================================
LOG_FORMAT = "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class SecretMaskingFormatter(logging.Formatter):
    """
    Custom formatter that automatically masks sensitive data in log messages.
    """

    def __init__(self, fmt=None, datefmt=None):
        super().__init__(fmt, datefmt)
        self._secrets: List[str] = []

    def add_secret(self, secret: str):
        """Add a secret to be masked in log messages."""
        if secret and secret not in self._secrets:
            self._secrets.append(secret)

    def clear_secrets(self):
        """Clear all registered secrets."""
        self._secrets.clear()

    def format(self, record: logging.LogRecord) -> str:
        """Format the record and mask any sensitive data."""
        formatted = super().format(record)
        return mask_sensitive_data(formatted, self._secrets)


# Global formatter instance
_formatter = SecretMaskingFormatter(fmt=LOG_FORMAT, datefmt=DATE_FORMAT)


def setup_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """
    Set up a logger with secret masking capability.

    Args:
        name: Logger name (typically __name__)
        level: Logging level (default: INFO)

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Avoid adding duplicate handlers
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_formatter)
        logger.addHandler(handler)

    return logger


def register_secret(secret: str):
    """
    Register a secret value to be masked in all log output.

    Args:
        secret: The secret string to mask (API key, webhook URL, etc.)
    """
    if secret:
        _formatter.add_secret(secret)


def clear_secrets():
    """Clear all registered secrets."""
    _formatter.clear_secrets()


# Default logger for module-level use
logger = setup_logger(__name__)
