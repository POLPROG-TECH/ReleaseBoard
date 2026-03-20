"""Shared test fixtures for ReleaseBoard."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from releaseboard.config.models import (
    AppConfig,
    BrandingConfig,
    LayerConfig,
    ReleaseConfig,
    RepositoryConfig,
    SettingsConfig,
)
from releaseboard.domain.models import BranchInfo

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def sample_release() -> ReleaseConfig:
    return ReleaseConfig(
        name="March 2025 Release",
        target_month=3,
        target_year=2025,
        branch_pattern="release/{MM}.{YYYY}",
    )


@pytest.fixture
def sample_layers() -> list[LayerConfig]:
    return [
        LayerConfig(
            id="ui", label="UI", color="#3B82F6", order=0,
        ),
        LayerConfig(
            id="api", label="API",
            branch_pattern="release/{YYYY}.{MM}",
            color="#10B981", order=1,
        ),
        LayerConfig(
            id="db", label="Database",
            branch_pattern="rel/{MM}-{YYYY}",
            color="#F59E0B", order=2,
        ),
    ]


@pytest.fixture
def sample_repositories() -> list[RepositoryConfig]:
    return [
        RepositoryConfig(
            name="web-app",
            url="https://github.com/acme/web-app.git",
            layer="ui",
        ),
        RepositoryConfig(
            name="admin-panel",
            url="https://github.com/acme/admin-panel.git",
            layer="ui",
        ),
        RepositoryConfig(
            name="core-api",
            url="https://github.com/acme/core-api.git",
            layer="api",
        ),
        RepositoryConfig(
            name="auth-service",
            url="https://github.com/acme/auth-service.git",
            layer="api",
        ),
        RepositoryConfig(
            name="migrations",
            url="https://github.com/acme/migrations.git",
            layer="db",
            branch_pattern="db-release/{MM}.{YYYY}",
        ),
    ]


@pytest.fixture
def sample_config(sample_release, sample_layers, sample_repositories) -> AppConfig:
    return AppConfig(
        release=sample_release,
        layers=sample_layers,
        repositories=sample_repositories,
        branding=BrandingConfig(title="TestBoard", subtitle="Test Dashboard"),
        settings=SettingsConfig(stale_threshold_days=14),
    )


@pytest.fixture
def sample_config_dict() -> dict:
    """Raw JSON-compatible config dict for schema validation tests."""
    return {
        "release": {
            "name": "March 2025 Release",
            "target_month": 3,
            "target_year": 2025,
            "branch_pattern": "release/{MM}.{YYYY}",
        },
        "layers": [
            {"id": "ui", "label": "UI", "color": "#3B82F6", "order": 0},
            {"id": "api", "label": "API",
             "branch_pattern": "release/{YYYY}.{MM}",
             "color": "#10B981", "order": 1},
        ],
        "repositories": [
            {"name": "web-app", "url": "https://github.com/acme/web-app.git", "layer": "ui"},
            {"name": "core-api", "url": "https://github.com/acme/core-api.git", "layer": "api"},
        ],
        "branding": {
            "title": "TestBoard",
            "primary_color": "#4F46E5",
        },
        "settings": {
            "stale_threshold_days": 14,
            "theme": "system",
        },
    }


@pytest.fixture
def recent_branch_info() -> BranchInfo:
    return BranchInfo(
        name="release/03.2025",
        exists=True,
        last_commit_date=datetime.now(tz=UTC),
        last_commit_author="dev@acme.com",
        last_commit_message="Fix build",
        commit_count=42,
    )


@pytest.fixture
def stale_branch_info() -> BranchInfo:
    return BranchInfo(
        name="release/03.2025",
        exists=True,
        last_commit_date=datetime(2025, 1, 1, tzinfo=UTC),
        last_commit_author="dev@acme.com",
        last_commit_message="Old commit",
        commit_count=10,
    )


@pytest.fixture
def tmp_config_file(tmp_path: Path, sample_config_dict: dict) -> Path:
    config_path = tmp_path / "releaseboard.json"
    config_path.write_text(json.dumps(sample_config_dict), encoding="utf-8")
    return config_path
