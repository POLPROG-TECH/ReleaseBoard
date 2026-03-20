"""Centralized logging configuration."""

import logging
import sys


class StructuredFormatter(logging.Formatter):
    """Formatter that outputs structured log fields for easier parsing."""

    def format(self, record: logging.LogRecord) -> str:
        # Add extra context fields if present
        extras = ""
        for key in ("request_path", "config_path", "repo_name", "duration_ms"):
            val = getattr(record, key, None)
            if val is not None:
                extras += f" {key}={val}"

        base = super().format(record)
        if extras:
            return f"{base}{extras}"
        return base


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(f"releaseboard.{name}")
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(
            StructuredFormatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
        )
        logger.addHandler(handler)
    return logger


def configure_root_logger(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    root = logging.getLogger("releaseboard")
    root.setLevel(level)
    # Ensure root logger also uses structured formatter
    if not root.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(
            StructuredFormatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
        )
        root.addHandler(handler)
