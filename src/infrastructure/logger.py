"""
Unified logging configuration with secret masking.
All modules must use this logger - no bare print() allowed.
"""
import gzip
import logging
import os
import sys
from datetime import datetime, timedelta
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import List, Optional


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


# ============================================================
# Log Rotation and Cleanup
# ============================================================
def extract_date_from_filename(filename: str) -> Optional[str]:
    """
    Extract date string from log filename.

    Args:
        filename: Log filename like 'dingdingbot-2026-03-29.log' or 'dingdingbot-2026-03-29.log.gz'

    Returns:
        Date string in YYYY-MM-DD format, or None if not found
    """
    # Remove .gz suffix if present
    if filename.endswith('.gz'):
        filename = filename[:-3]

    # Pattern: dingdingbot-YYYY-MM-DD.log
    prefix = 'dingdingbot-'
    suffix = '.log'

    if filename.startswith(prefix) and filename.endswith(suffix):
        date_str = filename[len(prefix):-len(suffix)]
        # Validate date format
        try:
            datetime.strptime(date_str, '%Y-%m-%d')
            return date_str
        except ValueError:
            return None
    return None


def compress_old_logs(logs_dir: str, days_threshold: int = 7) -> None:
    """
    Compress .log files older than N days into .gz format.

    Args:
        logs_dir: Path to the logs directory
        days_threshold: Compress logs older than this many days
    """
    logs_path = Path(logs_dir)
    if not logs_path.exists():
        return

    cutoff = datetime.now() - timedelta(days=days_threshold)

    for filename in os.listdir(logs_path):
        # Only process .log files (not .gz)
        if not filename.endswith('.log'):
            continue
        if filename.endswith('.gz'):
            continue

        file_path = logs_path / filename
        file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)

        if file_mtime < cutoff:
            gz_path = file_path.with_suffix(file_path.suffix + '.gz')

            try:
                # Compress the file
                with open(file_path, 'rb') as f_in, gzip.open(gz_path, 'wb') as f_out:
                    f_out.writelines(f_in)

                # Remove original file
                os.remove(file_path)

                # Use existing logger if available, otherwise skip
                _logger = logging.getLogger(__name__)
                _logger.info(f"已压缩旧日志：{filename} -> {filename}.gz")
            except Exception as e:
                _logger = logging.getLogger(__name__)
                _logger.error(f"压缩日志失败 {filename}: {e}")


def cleanup_old_logs(logs_dir: str, retention_days: int = 30) -> None:
    """
    Delete log files older than N days.

    Args:
        logs_dir: Path to the logs directory
        retention_days: Delete logs older than this many days
    """
    logs_path = Path(logs_dir)
    if not logs_path.exists():
        return

    cutoff = datetime.now() - timedelta(days=retention_days)

    for filename in os.listdir(logs_path):
        if not (filename.endswith('.log') or filename.endswith('.log.gz')):
            continue

        # Extract date from filename
        date_str = extract_date_from_filename(filename)
        if not date_str:
            # If can't parse date, use file modification time
            file_path = logs_path / filename
            file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
            if file_mtime < cutoff:
                try:
                    os.remove(file_path)
                    _logger = logging.getLogger(__name__)
                    _logger.info(f"已删除过期日志：{filename}")
                except Exception as e:
                    _logger = logging.getLogger(__name__)
                    _logger.error(f"删除日志失败 {filename}: {e}")
            continue

        file_date = datetime.strptime(date_str, '%Y-%m-%d')

        if file_date < cutoff:
            file_path = logs_path / filename
            try:
                os.remove(file_path)
                _logger = logging.getLogger(__name__)
                _logger.info(f"已删除过期日志：{filename}")
            except Exception as e:
                _logger = logging.getLogger(__name__)
                _logger.error(f"删除日志失败 {filename}: {e}")


def setup_logger(name: str, level: int = logging.INFO, logs_dir: str = "logs") -> logging.Logger:
    """
    Set up a logger with secret masking capability and file persistence.

    Args:
        name: Logger name (typically __name__)
        level: Logging level (default: INFO)
        logs_dir: Directory for log files (default: "logs")

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)  # Set logger to DEBUG to allow all levels to handlers

    # Avoid adding duplicate handlers
    if not logger.handlers:
        # Handler 1: StreamHandler (console output)
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setLevel(level)  # Use parameter for console level
        stream_handler.setFormatter(_formatter)
        logger.addHandler(stream_handler)

        # Handler 2: FileHandler (file persistence with rotation)
        logs_path = Path(logs_dir)
        logs_path.mkdir(parents=True, exist_ok=True)

        # Perform log compression and cleanup on startup
        compress_old_logs(logs_dir, days_threshold=7)
        cleanup_old_logs(logs_dir, retention_days=30)

        # TimedRotatingFileHandler for daily rotation
        log_file = logs_path / "dingdingbot.log"
        file_handler = TimedRotatingFileHandler(
            filename=log_file,
            when='D',           # Daily rotation
            interval=1,         # Every 1 day
            backupCount=30,     # Keep 30 backups
            encoding='utf-8',
            delay=False
        )
        file_handler.suffix = "%Y-%m-%d.log"  # Filename suffix after rotation
        file_handler.setLevel(logging.DEBUG)  # File logs more detailed
        file_handler.setFormatter(_formatter)
        logger.addHandler(file_handler)

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
