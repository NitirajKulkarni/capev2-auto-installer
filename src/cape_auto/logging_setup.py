"""
Logging setup for CAPEv2 Automated Installer.

Provides structured logging with secret redaction, file and console handlers,
timestamped log rotation, and category-based log files.
"""
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


# Patterns to redact from logs
_REDACT_PATTERNS = [
    re.compile(r'(password|passwd|pass|secret|token|api_key|apikey|auth)\s*[=:]\s*\S+', re.IGNORECASE),
    re.compile(r'(Authorization|X-API-Key)\s*:\s*\S+', re.IGNORECASE),
    re.compile(r'mongodb://\S+:\S+@', re.IGNORECASE),
    re.compile(r'postgresql://\S+:\S+@', re.IGNORECASE),
]


class RedactingFormatter(logging.Formatter):
    """Formatter that redacts sensitive information from log messages."""

    def __init__(self, fmt: str, redact: bool = True, **kwargs):
        super().__init__(fmt, **kwargs)
        self._redact = redact

    def format(self, record: logging.LogRecord) -> str:
        msg = super().format(record)
        if self._redact:
            for pattern in _REDACT_PATTERNS:
                msg = pattern.sub("[REDACTED]", msg)
        return msg


class CategoryFilter(logging.Filter):
    """Filter log records by category."""
    def __init__(self, categories: list[str]):
        super().__init__()
        self._categories = categories

    def filter(self, record: logging.LogRecord) -> bool:
        return record.name in self._categories or any(
            record.name.startswith(cat + ".") for cat in self._categories
        )


_log_dir: Optional[str] = None
_initialized = False


def setup_logging(log_dir: str, level: str = "INFO", redact: bool = True) -> None:
    """
    Initialize the logging system.

    Creates multiple log files:
      - install.log      All messages
      - commands.log      Command execution only
      - errors.log        Errors only
      - diagnostics.log   Diagnostic messages
      - remediation.log   Remediation actions
      - verification.log  Verification results
    """
    global _log_dir, _initialized
    if _initialized:
        return

    _log_dir = log_dir
    Path(log_dir).mkdir(parents=True, exist_ok=True)

    # Map string level
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    # Root logger
    root_logger = logging.getLogger("cape_auto")
    root_logger.setLevel(logging.DEBUG)  # Capture everything; handlers filter
    root_logger.handlers.clear()

    fmt = "%(asctime)s [%(levelname)-5s] [%(name)s] %(message)s"
    date_fmt = "%Y-%m-%d %H:%M:%S"

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(RedactingFormatter(fmt, redact=redact, datefmt=date_fmt))
    root_logger.addHandler(console_handler)

    # File handlers
    log_files = {
        "install.log": logging.DEBUG,
        "errors.log": logging.ERROR,
    }
    for filename, file_level in log_files.items():
        fh = logging.FileHandler(os.path.join(log_dir, filename), encoding="utf-8")
        fh.setLevel(file_level)
        fh.setFormatter(RedactingFormatter(fmt, redact=redact, datefmt=date_fmt))
        root_logger.addHandler(fh)

    # Category-specific files
    category_files = {
        "commands.log": ["cape_auto.command"],
        "diagnostics.log": ["cape_auto.diagnostics", "cape_auto.health"],
        "remediation.log": ["cape_auto.remediation"],
        "verification.log": ["cape_auto.verification", "cape_auto.health"],
    }
    for filename, categories in category_files.items():
        fh = logging.FileHandler(os.path.join(log_dir, filename), encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(RedactingFormatter(fmt, redact=redact, datefmt=date_fmt))
        fh.addFilter(CategoryFilter(["cape_auto." + c.split(".")[-1] for c in categories]))
        root_logger.addHandler(fh)

    _initialized = True


def get_logger(name: str) -> logging.Logger:
    """Get a named logger under the cape_auto namespace."""
    return logging.getLogger(f"cape_auto.{name}")
