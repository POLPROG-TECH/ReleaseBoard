"""ReleasePilot adapter — thin bridge between ReleaseBoard and ReleasePilot.

All release-notes generation logic lives in the ReleasePilot library.
This adapter only:
  1. Translates ReleaseBoard models → ReleasePilot Settings
  2. Calls ``releasepilot.pipeline.orchestrator.generate()``
  3. Wraps the result into ``ReleasePrepResult`` for the wizard

No rendering, no classification, no git collection is duplicated here.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

try:
    from releasepilot import __version__ as rp_version
    from releasepilot.config.settings import RenderConfig, Settings
    from releasepilot.domain.enums import Audience
    from releasepilot.domain.enums import OutputFormat as RPOutputFormat
    from releasepilot.pipeline.orchestrator import generate

    _RELEASEPILOT_AVAILABLE = True
except ImportError:
    _RELEASEPILOT_AVAILABLE = False
    rp_version = "0.0.0"
    RenderConfig = None  # type: ignore[assignment,misc]
    Settings = None  # type: ignore[assignment,misc]
    Audience = None  # type: ignore[assignment,misc]
    RPOutputFormat = None  # type: ignore[assignment,misc]
    generate = None  # type: ignore[assignment,misc]

from releaseboard.integrations.releasepilot.models import (
    SUPPORTED_LANGUAGES,
    ReleasePrepRequest,
    ReleasePrepResult,
)
from releaseboard.integrations.releasepilot.validation import validate_prep_request

logger = logging.getLogger(__name__)


@dataclass
class ReleasePilotCapabilities:
    """Describes what the integration can do in the current environment."""

    available: bool
    mode: str  # always "library" now
    version: str
    supported_audiences: tuple[str, ...]
    supported_formats: tuple[str, ...]
    export_formats_available: bool = True
    supported_languages: tuple[tuple[str, str], ...] = SUPPORTED_LANGUAGES

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "mode": self.mode,
            "version": self.version,
            "supported_audiences": list(self.supported_audiences),
            "supported_formats": list(self.supported_formats),
            "export_formats_available": self.export_formats_available,
            "supported_languages": [
                {"code": code, "label": label}
                for code, label in self.supported_languages
            ],
        }


def _detect_capabilities() -> ReleasePilotCapabilities:
    """Detect ReleasePilot capabilities from the installed library."""
    if not _RELEASEPILOT_AVAILABLE:
        return ReleasePilotCapabilities(
            available=False,
            mode="not_installed",
            version="0.0.0",
            supported_audiences=(),
            supported_formats=(),
            export_formats_available=False,
        )
    audiences = tuple(a.value for a in Audience)
    formats = tuple(f.value for f in RPOutputFormat)
    return ReleasePilotCapabilities(
        available=True,
        mode="library",
        version=rp_version,
        supported_audiences=audiences,
        supported_formats=formats,
        export_formats_available=True,
    )


def _request_to_settings(request: ReleasePrepRequest) -> Settings:
    """Convert a ReleaseBoard prep request into ReleasePilot Settings."""
    render = RenderConfig(
        show_authors=request.include_authors,
        show_commit_hashes=request.include_hashes,
        show_pr_links=request.show_pr_links,
        show_scope=request.show_scope,
        group_by_scope=request.group_by_scope,
        language=request.language,
        accent_color=request.accent_color,
    )
    return Settings(
        repo_path=request.repo_url,
        from_ref=request.from_ref,
        to_ref=request.to_ref,
        branch=request.branch,
        since_date=request.since_date,
        audience=Audience(str(request.audience)),
        output_format=RPOutputFormat(str(request.output_format)),
        version=request.release_version,
        title=request.release_title,
        app_name=request.app_name or request.repo_name,
        language=request.language,
        render=render,
    )


class ReleasePilotAdapter:
    """Service adapter for ReleasePilot integration.

    Thread-safe.  One instance can be shared across requests.
    """

    def __init__(self) -> None:
        self._capabilities: ReleasePilotCapabilities | None = None

    @property
    def is_available(self) -> bool:
        """Return True if ReleasePilot is installed and usable."""
        return self.capabilities.available

    @property
    def capabilities(self) -> ReleasePilotCapabilities:
        if self._capabilities is None:
            self._capabilities = _detect_capabilities()
        return self._capabilities

    def validate(self, data: dict[str, Any]) -> list[str]:
        return validate_prep_request(data)

    async def prepare_release(self, request: ReleasePrepRequest) -> ReleasePrepResult:
        """Execute a release preparation run via ReleasePilot library."""
        if not self.is_available:
            return ReleasePrepResult(
                success=False,
                repo_name=request.repo_name,
                release_title=request.release_title,
                release_version=request.release_version,
                audience=str(request.audience),
                output_format=str(request.output_format),
                error_message="ReleasePilot is not installed",
                error_code="integration_unavailable",
            )
        try:
            settings = _request_to_settings(request)
            content = await asyncio.to_thread(generate, settings)

            # Derive stats from rendered content
            total = content.count("\n- ") if content else 0

            return ReleasePrepResult(
                success=True,
                repo_name=request.repo_name,
                release_title=request.release_title,
                release_version=request.release_version,
                audience=str(request.audience),
                output_format=str(request.output_format),
                content=content,
                total_changes=total,
                metadata={"mode": "library", "version": rp_version},
            )
        except Exception as exc:
            logger.error("Release preparation failed for %s: %s", request.repo_name, exc)
            return ReleasePrepResult(
                success=False,
                repo_name=request.repo_name,
                release_title=request.release_title,
                release_version=request.release_version,
                audience=str(request.audience),
                output_format=str(request.output_format),
                error_message=str(exc),
                error_code="preparation_failed",
            )

