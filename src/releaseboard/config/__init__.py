"""Configuration layer — loading, validation, and config models."""

from releaseboard.config.loader import load_config
from releaseboard.config.models import AppConfig

__all__ = ["AppConfig", "load_config"]
