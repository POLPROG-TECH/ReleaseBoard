"""Configuration loader — reads JSON, validates, and builds AppConfig."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from releaseboard.config.models import (
    AppConfig,
    AuthorConfig,
    BrandingConfig,
    LayerConfig,
    LayoutConfig,
    ReleaseConfig,
    RepositoryConfig,
    SettingsConfig,
)
from releaseboard.config.schema import (
    ConfigValidationError,
    validate_config_strict,
    validate_layer_references,
)
from releaseboard.shared.logging import get_logger

logger = get_logger("config")


def _resolve_env_vars(value: str) -> str:
    """Replace ${ENV_VAR} placeholders with environment variable values.

    Logs a warning for each unresolved variable and returns the placeholder
    as-is so downstream code can detect unresolved refs.
    """
    import re

    def _replace(match: re.Match[str]) -> str:
        var_name = match.group(1)
        env_val = os.environ.get(var_name)
        if env_val is None:
            logger.warning(
                "Environment variable '%s' is not set — "
                "placeholder '${%s}' left unresolved",
                var_name, var_name,
            )
            return match.group(0)
        return env_val

    return re.sub(r"\$\{(\w+)}", _replace, value)


def _walk_resolve_env(obj: Any) -> Any:
    """Recursively resolve environment variable placeholders in strings."""
    if isinstance(obj, str):
        return _resolve_env_vars(obj)
    if isinstance(obj, dict):
        return {k: _walk_resolve_env(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_walk_resolve_env(item) for item in obj]
    return obj


def _build_release(data: dict[str, Any]) -> ReleaseConfig:
    return ReleaseConfig(
        name=data["name"],
        target_month=int(data["target_month"]),
        target_year=int(data["target_year"]),
        branch_pattern=data.get("branch_pattern", "release/{YYYY}.{MM}"),
    )


def _build_layers(data: list[dict[str, Any]] | None) -> list[LayerConfig]:
    if not data:
        return []
    return [
        LayerConfig(
            id=item["id"],
            label=item["label"],
            branch_pattern=item.get("branch_pattern"),
            color=item.get("color"),
            order=item.get("order", i),
            repository_root_url=item.get("repository_root_url"),
        )
        for i, item in enumerate(data)
    ]


def _build_repositories(data: list[dict[str, Any]]) -> list[RepositoryConfig]:
    return [
        RepositoryConfig(
            name=item["name"],
            url=item["url"],
            layer=item["layer"],
            branch_pattern=item.get("branch_pattern"),
            default_branch=item.get("default_branch", "main"),
            notes=item.get("notes"),
        )
        for item in data
    ]


def _build_branding(data: dict[str, Any] | None) -> BrandingConfig:
    if not data:
        return BrandingConfig()
    return BrandingConfig(
        title=data.get("title", "ReleaseBoard"),
        subtitle=data.get("subtitle", "Release Readiness Dashboard"),
        company=data.get("company", ""),
        primary_color=data.get("primary_color", data.get("accent_color", "#fb6400")),
        secondary_color=data.get("secondary_color", "#002754e6"),
        tertiary_color=data.get("tertiary_color", "#10b981"),
        logo_path=data.get("logo_path"),
    )


def _build_settings(data: dict[str, Any] | None) -> SettingsConfig:
    if not data:
        return SettingsConfig()

    def _safe_int(val: Any, default: int) -> int:
        try:
            return int(val)
        except (TypeError, ValueError):
            if val is not None:
                logger.warning("Invalid integer value %r, using default %d", val, default)
            return default

    return SettingsConfig(
        stale_threshold_days=_safe_int(data.get("stale_threshold_days", 14), 14),
        output_path=data.get("output_path", "output/dashboard.html"),
        theme=data.get("theme", "system"),
        verbose=data.get("verbose", False),
        timeout_seconds=_safe_int(data.get("timeout_seconds", 30), 30),
        max_concurrent=_safe_int(data.get("max_concurrent", 5), 5),
        repository_root_url=data.get("repository_root_url", ""),
    )


def _build_author(data: dict[str, Any] | None) -> AuthorConfig:
    if not data:
        return AuthorConfig()
    return AuthorConfig(
        name=data.get("name", ""),
        role=data.get("role", ""),
        url=data.get("url", ""),
        tagline=data.get("tagline", ""),
        copyright=data.get("copyright", ""),
    )


def _build_layout(data: dict[str, Any] | None) -> LayoutConfig:
    if not data:
        return LayoutConfig()
    section_order = data.get("section_order")
    return LayoutConfig(
        default_template=data.get("default_template", "default"),
        section_order=tuple(section_order)
        if isinstance(section_order, list)
        else LayoutConfig.section_order,
        enable_drag_drop=data.get("enable_drag_drop", True),
    )


def load_config(path: str | Path) -> AppConfig:
    """Load, validate, and parse a ReleaseBoard configuration file.

    Args:
        path: Path to the JSON configuration file.

    Returns:
        Fully validated AppConfig instance.

    Raises:
        FileNotFoundError: If the config file does not exist.
        ConfigValidationError: If the config fails schema or semantic validation.
    """
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    raw_text = config_path.read_text(encoding="utf-8")
    raw_data: dict[str, Any] = json.loads(raw_text)

    # Resolve environment variable placeholders
    data = _walk_resolve_env(raw_data)

    # Schema validation
    validate_config_strict(data)

    # Semantic validation
    ref_errors = validate_layer_references(data)
    if ref_errors:
        raise ConfigValidationError(ref_errors)

    logger.info("Configuration loaded from %s", config_path)

    return AppConfig(
        release=_build_release(data["release"]),
        layers=_build_layers(data.get("layers")),
        repositories=_build_repositories(data["repositories"]),
        branding=_build_branding(data.get("branding")),
        settings=_build_settings(data.get("settings")),
        author=_build_author(data.get("author")),
        layout=_build_layout(data.get("layout")),
    )
