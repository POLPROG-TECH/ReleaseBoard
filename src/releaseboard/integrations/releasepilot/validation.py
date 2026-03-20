"""Validation logic for ReleasePilot integration inputs.

All validation functions return a list of i18n error keys (empty = valid).
Validation is safe, non-destructive, and locale-aware.
"""

from __future__ import annotations

import re
from typing import Any

from releaseboard.integrations.releasepilot.models import AudienceMode, OutputFormat

# Reasonable limits
_MAX_TITLE_LENGTH = 200
_MAX_VERSION_LENGTH = 50
_MAX_REF_LENGTH = 256
_MAX_NOTES_LENGTH = 5000

# Semver-ish pattern: allows v1.0.0, 1.0, 2025.03, etc.
_VERSION_PATTERN = re.compile(r"^v?\d+(\.\d+){0,3}(-[\w.]+)?(\+[\w.]+)?$")

# Git ref pattern: allows branch names, tags, SHAs
_REF_PATTERN = re.compile(r"^[\w./-]+$")


def validate_release_title(title: str) -> list[str]:
    """Validate the release title field."""
    errors: list[str] = []
    stripped = title.strip()
    if not stripped:
        errors.append("rp.validation.title_required")
    elif len(stripped) > _MAX_TITLE_LENGTH:
        errors.append("rp.validation.title_too_long")
    return errors


def validate_release_version(version: str) -> list[str]:
    """Validate the release version field."""
    errors: list[str] = []
    stripped = version.strip()
    if not stripped:
        errors.append("rp.validation.version_required")
    elif len(stripped) > _MAX_VERSION_LENGTH:
        errors.append("rp.validation.version_too_long")
    elif not _VERSION_PATTERN.match(stripped):
        errors.append("rp.validation.version_invalid_format")
    return errors


def validate_git_ref(ref: str, field_name: str) -> list[str]:
    """Validate a git ref (from_ref or to_ref). Empty is allowed (auto-detect)."""
    errors: list[str] = []
    stripped = ref.strip()
    if not stripped:
        return []  # Optional — RP auto-detects from tags
    if len(stripped) > _MAX_REF_LENGTH:
        errors.append(f"rp.validation.{field_name}_too_long")
    elif not _REF_PATTERN.match(stripped):
        errors.append(f"rp.validation.{field_name}_invalid")
    return errors


def validate_audience(audience: str) -> list[str]:
    """Validate the audience mode."""
    try:
        AudienceMode(audience)
        return []
    except ValueError:
        return ["rp.validation.audience_invalid"]


def validate_output_format(fmt: str) -> list[str]:
    """Validate the output format."""
    try:
        OutputFormat(fmt)
        return []
    except ValueError:
        return ["rp.validation.format_invalid"]


def validate_additional_notes(notes: str) -> list[str]:
    """Validate optional additional notes."""
    if len(notes) > _MAX_NOTES_LENGTH:
        return ["rp.validation.notes_too_long"]
    return []


def validate_repo_context(repo_name: str, repo_url: str) -> list[str]:
    """Validate repository context fields."""
    errors: list[str] = []
    if not repo_name or not repo_name.strip():
        errors.append("rp.validation.repo_name_required")
    if not repo_url or not repo_url.strip():
        errors.append("rp.validation.repo_url_required")
    return errors


def validate_prep_request(data: dict[str, Any]) -> list[str]:
    """Validate a complete release preparation request payload.

    Returns a list of i18n error keys. Empty list means valid.
    """
    errors: list[str] = []

    errors.extend(validate_repo_context(
        data.get("repo_name", ""),
        data.get("repo_url", ""),
    ))
    errors.extend(validate_release_title(data.get("release_title", "")))
    errors.extend(validate_release_version(data.get("release_version", "")))
    errors.extend(validate_git_ref(data.get("from_ref", ""), "from_ref"))
    errors.extend(validate_git_ref(data.get("to_ref", ""), "to_ref"))
    errors.extend(validate_audience(data.get("audience", "changelog")))
    errors.extend(validate_output_format(data.get("output_format", "markdown")))
    errors.extend(validate_additional_notes(data.get("additional_notes", "")))

    return errors
