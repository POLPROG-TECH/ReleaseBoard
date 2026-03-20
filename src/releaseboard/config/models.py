"""Typed configuration models."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse


def derive_name_from_url(url: str) -> str:
    """Derive a clean application name from a repository URL.

    Handles HTTPS, SSH (git@), local paths, and bare slugs.
    Strips ``.git`` suffix and trailing slashes.

    Examples::

        https://github.com/acme/payment-gateway.git  → payment-gateway
        git@github.com:org/admin-portal.git           → admin-portal
        ssh://git@host/team/customer-api.git          → customer-api
        /opt/repos/my-service                         → my-service
        my-repo                                       → my-repo
    """
    cleaned = url.strip().rstrip("/")
    if not cleaned:
        return ""

    # SSH shorthand: git@host:org/repo.git
    ssh_match = re.match(r"^[\w.-]+@[\w.-]+:(.+)$", cleaned)
    if ssh_match:
        path = ssh_match.group(1)
    else:
        try:
            parsed = urlparse(cleaned)
            path = parsed.path if parsed.scheme else cleaned
        except (ValueError, AttributeError, TypeError):
            path = cleaned

    # Take the last path segment
    segment = path.rstrip("/").rsplit("/", 1)[-1]
    # Strip .git suffix
    if segment.endswith(".git"):
        segment = segment[:-4]
    return segment or ""


@dataclass(frozen=True)
class AuthorConfig:
    """Author/creator metadata for branding and credits."""

    name: str = ""
    role: str = ""
    url: str = ""
    tagline: str = ""
    copyright: str = ""


@dataclass(frozen=True)
class RepositoryConfig:
    """Configuration for a single repository."""

    name: str
    url: str
    layer: str
    branch_pattern: str | None = None
    default_branch: str = "main"
    notes: str | None = None


@dataclass(frozen=True)
class LayerConfig:
    """Configuration for a repository layer."""

    id: str
    label: str
    branch_pattern: str | None = None
    color: str | None = None
    order: int = 0
    repository_root_url: str | None = None


@dataclass(frozen=True)
class ReleaseConfig:
    """Release target configuration."""

    name: str
    target_month: int
    target_year: int
    branch_pattern: str = "release/{YYYY}.{MM}"


@dataclass(frozen=True)
class BrandingConfig:
    """Dashboard branding settings."""

    title: str = "ReleaseBoard"
    subtitle: str = "Release Readiness Dashboard"
    company: str = ""
    primary_color: str = "#fb6400"
    secondary_color: str = "#002754e6"
    tertiary_color: str = "#10b981"
    logo_path: str | None = None


@dataclass(frozen=True)
class SettingsConfig:
    """Application settings."""

    stale_threshold_days: int = 14
    output_path: str = "output/dashboard.html"
    theme: str = "system"
    verbose: bool = False
    timeout_seconds: int = 30
    max_concurrent: int = 5
    repository_root_url: str = ""


@dataclass(frozen=True)
class LayoutConfig:
    """Dashboard layout preferences."""

    default_template: str = "default"
    section_order: tuple[str, ...] = (
        "score", "metrics", "charts", "filters", "attention", "layer-*", "summary"
    )
    enable_drag_drop: bool = True


@dataclass(frozen=True)
class AppConfig:
    """Root application configuration."""

    release: ReleaseConfig
    layers: list[LayerConfig] = field(default_factory=list)
    repositories: list[RepositoryConfig] = field(default_factory=list)
    branding: BrandingConfig = field(default_factory=BrandingConfig)
    settings: SettingsConfig = field(default_factory=SettingsConfig)
    author: AuthorConfig = field(default_factory=AuthorConfig)
    layout: LayoutConfig = field(default_factory=LayoutConfig)

    def get_layer(self, layer_id: str) -> LayerConfig | None:
        return next((layer for layer in self.layers if layer.id == layer_id), None)

    def get_repos_for_layer(self, layer_id: str) -> list[RepositoryConfig]:
        return [r for r in self.repositories if r.layer == layer_id]

    def resolve_branch_pattern(self, repo: RepositoryConfig) -> str:
        """Resolve branch pattern with three-tier override: repo → layer → global."""
        if repo.branch_pattern:
            return repo.branch_pattern
        layer = self.get_layer(repo.layer)
        if layer and layer.branch_pattern:
            return layer.branch_pattern
        return self.release.branch_pattern

    def resolve_repo_url(self, repo: RepositoryConfig) -> str:
        """Resolve repository URL.

        Precedence:
        1. Absolute repo URL → used as-is
        2. Layer ``repository_root_url`` + slug
        3. Global ``repository_root_url`` + slug
        4. Bare slug returned as-is
        """
        url = repo.url.strip()

        # If the URL already looks absolute, use it directly
        if url.startswith(("http://", "https://", "git@", "ssh://", "/")):
            return url

        # Try layer root URL first
        layer = self.get_layer(repo.layer)
        if layer and layer.repository_root_url:
            root = layer.repository_root_url.strip().rstrip("/")
            if root:
                return f"{root}/{url}"

        # Fall back to global root URL
        root = self.settings.repository_root_url.strip().rstrip("/")
        if root:
            return f"{root}/{url}"

        return url

    @property
    def layer_ids(self) -> list[str]:
        return [layer.id for layer in sorted(self.layers, key=lambda layer: layer.order)]
