"""Tests for configuration loading and validation."""

import json

import pytest

from releaseboard.config.loader import load_config
from releaseboard.config.models import AppConfig
from releaseboard.config.schema import (
    ConfigValidationError,
    validate_config,
    validate_config_strict,
    validate_layer_references,
)


class TestSchemaValidation:
    """Tests for JSON Schema validation of config data."""

    def test_valid_config_passes(self, sample_config_dict):
        # GIVEN a valid configuration dict
        # WHEN validated
        errors = validate_config(sample_config_dict)
        # THEN no errors
        assert errors == []

    def test_missing_release_section_fails(self, sample_config_dict):
        # GIVEN config without required 'release' key
        del sample_config_dict["release"]

        # WHEN validated
        errors = validate_config(sample_config_dict)

        # THEN error references missing 'release'
        assert any("release" in e for e in errors)

    def test_missing_repositories_fails(self, sample_config_dict):
        del sample_config_dict["repositories"]
        errors = validate_config(sample_config_dict)
        assert any("repositories" in e for e in errors)

    def test_empty_repositories_valid(self, sample_config_dict):
        """Empty repositories list is valid — config can be a fresh/zeroed draft."""
        sample_config_dict["repositories"] = []
        errors = validate_config(sample_config_dict)
        assert len(errors) == 0

    def test_invalid_month_fails(self, sample_config_dict):
        sample_config_dict["release"]["target_month"] = 13
        errors = validate_config(sample_config_dict)
        assert len(errors) > 0

    def test_invalid_theme_fails(self, sample_config_dict):
        sample_config_dict["settings"] = {"theme": "rainbow"}
        errors = validate_config(sample_config_dict)
        assert len(errors) > 0

    def test_additional_properties_rejected(self, sample_config_dict):
        sample_config_dict["unknown_key"] = "value"
        errors = validate_config(sample_config_dict)
        assert len(errors) > 0

    def test_strict_raises_on_error(self, sample_config_dict):
        del sample_config_dict["release"]
        with pytest.raises(ConfigValidationError):
            validate_config_strict(sample_config_dict)

    def test_layer_with_repository_root_url_valid(self, sample_config_dict):
        """GIVEN a layer with repository_root_url
        WHEN validated
        THEN no errors."""
        sample_config_dict["layers"][0]["repository_root_url"] = "https://git.example.com/frontend"
        errors = validate_config(sample_config_dict)
        assert errors == []


class TestLayerReferenceValidation:

    def test_valid_layer_references_pass(self, sample_config_dict):
        errors = validate_layer_references(sample_config_dict)
        assert errors == []

    def test_invalid_layer_reference_detected(self, sample_config_dict):
        # GIVEN a repo referencing a nonexistent layer
        sample_config_dict["repositories"].append(
            {"name": "bad-repo", "url": "https://x.com/r.git", "layer": "nonexistent"}
        )

        # WHEN validated
        errors = validate_layer_references(sample_config_dict)

        # THEN the invalid reference is reported
        assert any("nonexistent" in e for e in errors)


class TestConfigLoader:

    def test_loads_valid_config_file(self, tmp_config_file):
        # GIVEN a valid config file on disk
        # WHEN loaded
        config = load_config(tmp_config_file)

        # THEN it returns a correct AppConfig
        assert isinstance(config, AppConfig)
        assert config.release.name == "March 2025 Release"
        assert config.release.target_month == 3
        assert len(config.repositories) == 2
        assert len(config.layers) == 2

    def test_nonexistent_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_config(tmp_path / "does_not_exist.json")

    def test_invalid_json_raises(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{invalid json", encoding="utf-8")
        with pytest.raises((json.JSONDecodeError, ValueError)):
            load_config(bad)

    def test_env_var_resolution(self, tmp_path, monkeypatch):
        # GIVEN config with ${TOKEN} placeholder
        monkeypatch.setenv("MY_TOKEN", "secret123")
        config_data = {
            "release": {"name": "Test", "target_month": 1, "target_year": 2025},
            "repositories": [
                {"name": "repo", "url": "https://${MY_TOKEN}@github.com/r.git", "layer": "ui"}
            ],
        }
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(config_data), encoding="utf-8")

        # WHEN loaded
        config = load_config(config_path)

        # THEN the env var is resolved
        assert "secret123" in config.repositories[0].url
        assert "${MY_TOKEN}" not in config.repositories[0].url


class TestBranchPatternOverrides:
    """Tests for the three-tier branch pattern resolution."""

    def test_global_pattern_used_when_no_overrides(self, sample_config):
        # GIVEN a repo in the UI layer (no layer or repo override for branch_pattern)
        repo = sample_config.repositories[0]  # web-app, ui layer
        # UI layer has no branch_pattern override

        # WHEN resolving
        pattern = sample_config.resolve_branch_pattern(repo)

        # THEN the global pattern is used
        assert pattern == "release/{MM}.{YYYY}"

    def test_layer_override_takes_precedence(self, sample_config):
        # GIVEN a repo in the API layer (which has a branch_pattern override)
        repo = sample_config.repositories[2]  # core-api, api layer

        # WHEN resolving
        pattern = sample_config.resolve_branch_pattern(repo)

        # THEN the layer pattern is used
        assert pattern == "release/{YYYY}.{MM}"

    def test_repo_override_takes_highest_precedence(self, sample_config):
        # GIVEN the migrations repo which has its own branch_pattern
        repo = sample_config.repositories[4]  # migrations, db layer

        # WHEN resolving
        pattern = sample_config.resolve_branch_pattern(repo)

        # THEN the repo-level pattern wins over layer and global
        assert pattern == "db-release/{MM}.{YYYY}"


class TestRepoUrlResolution:
    """Tests for repository URL composition with root URL."""

    def test_absolute_url_not_modified(self):
        """GIVEN a repo with a full HTTPS URL and a root URL
        WHEN resolving
        THEN the absolute URL is returned as-is."""
        from releaseboard.config.models import (
            AppConfig,
            ReleaseConfig,
            RepositoryConfig,
            SettingsConfig,
        )
        config = AppConfig(
            release=ReleaseConfig(name="Test", target_month=3, target_year=2025),
            repositories=[
                RepositoryConfig(
                    name="r",
                    url="https://github.com/acme/repo.git",
                    layer="api",
                ),
            ],
            settings=SettingsConfig(
                repository_root_url="https://gitlab.com/org",
            ),
        )
        assert config.resolve_repo_url(config.repositories[0]) == "https://github.com/acme/repo.git"

    def test_slug_composed_with_root(self):
        """GIVEN a repo with a slug and a root URL
        WHEN resolving
        THEN root + slug is returned."""
        from releaseboard.config.models import (
            AppConfig,
            ReleaseConfig,
            RepositoryConfig,
            SettingsConfig,
        )
        config = AppConfig(
            release=ReleaseConfig(name="Test", target_month=3, target_year=2025),
            repositories=[RepositoryConfig(name="r", url="payment-gateway", layer="api")],
            settings=SettingsConfig(repository_root_url="https://github.com/acme"),
        )
        assert config.resolve_repo_url(config.repositories[0]) == "https://github.com/acme/payment-gateway"

    def test_slug_without_root_returns_slug(self):
        """GIVEN a repo with a slug but no root URL
        WHEN resolving
        THEN the slug is returned as-is."""
        from releaseboard.config.models import (
            AppConfig,
            ReleaseConfig,
            RepositoryConfig,
            SettingsConfig,
        )
        config = AppConfig(
            release=ReleaseConfig(name="Test", target_month=3, target_year=2025),
            repositories=[RepositoryConfig(name="r", url="payment-gateway", layer="api")],
            settings=SettingsConfig(repository_root_url=""),
        )
        assert config.resolve_repo_url(config.repositories[0]) == "payment-gateway"

    def test_root_trailing_slash_stripped(self):
        """GIVEN a root URL with trailing slash
        WHEN composing with slug
        THEN no double slash."""
        from releaseboard.config.models import (
            AppConfig,
            ReleaseConfig,
            RepositoryConfig,
            SettingsConfig,
        )
        config = AppConfig(
            release=ReleaseConfig(name="Test", target_month=3, target_year=2025),
            repositories=[RepositoryConfig(name="r", url="my-repo", layer="api")],
            settings=SettingsConfig(repository_root_url="https://github.com/acme/"),
        )
        resolved = config.resolve_repo_url(config.repositories[0])
        assert resolved == "https://github.com/acme/my-repo"
        assert "//" not in resolved.split("://")[1]

    def test_ssh_url_not_modified(self):
        """GIVEN a repo with SSH URL
        WHEN resolving
        THEN it's returned as-is."""
        from releaseboard.config.models import (
            AppConfig,
            ReleaseConfig,
            RepositoryConfig,
            SettingsConfig,
        )
        config = AppConfig(
            release=ReleaseConfig(name="Test", target_month=3, target_year=2025),
            repositories=[
                RepositoryConfig(
                    name="r",
                    url="git@github.com:acme/repo.git",
                    layer="api",
                ),
            ],
            settings=SettingsConfig(repository_root_url="https://github.com/other"),
        )
        assert config.resolve_repo_url(config.repositories[0]) == "git@github.com:acme/repo.git"

    def test_local_path_not_modified(self):
        """GIVEN a repo with an absolute local path
        WHEN resolving
        THEN it's returned as-is."""
        from releaseboard.config.models import (
            AppConfig,
            ReleaseConfig,
            RepositoryConfig,
            SettingsConfig,
        )
        config = AppConfig(
            release=ReleaseConfig(name="Test", target_month=3, target_year=2025),
            repositories=[RepositoryConfig(name="r", url="/opt/repos/my-repo", layer="api")],
            settings=SettingsConfig(repository_root_url="https://github.com/acme"),
        )
        assert config.resolve_repo_url(config.repositories[0]) == "/opt/repos/my-repo"

    def test_layer_root_url_overrides_global(self):
        """GIVEN a layer with repository_root_url and a global root URL
        WHEN resolving a slug repo in that layer
        THEN the layer root URL is used."""
        from releaseboard.config.models import (
            AppConfig,
            LayerConfig,
            ReleaseConfig,
            RepositoryConfig,
            SettingsConfig,
        )
        config = AppConfig(
            release=ReleaseConfig(name="Test", target_month=3, target_year=2025),
            layers=[LayerConfig(id="api", label="API", repository_root_url="https://git.example.com/backend")],
            repositories=[RepositoryConfig(name="svc", url="payment-svc", layer="api")],
            settings=SettingsConfig(repository_root_url="https://git.example.com/global"),
        )
        assert config.resolve_repo_url(config.repositories[0]) == "https://git.example.com/backend/payment-svc"

    def test_global_root_used_when_layer_has_no_root(self):
        """GIVEN a layer without repository_root_url
        WHEN resolving a slug repo
        THEN global root URL is used."""
        from releaseboard.config.models import (
            AppConfig,
            LayerConfig,
            ReleaseConfig,
            RepositoryConfig,
            SettingsConfig,
        )
        config = AppConfig(
            release=ReleaseConfig(name="Test", target_month=3, target_year=2025),
            layers=[LayerConfig(id="ui", label="UI")],
            repositories=[RepositoryConfig(name="portal", url="web-portal", layer="ui")],
            settings=SettingsConfig(repository_root_url="https://git.example.com/platform"),
        )
        assert config.resolve_repo_url(config.repositories[0]) == "https://git.example.com/platform/web-portal"

    def test_absolute_url_ignores_layer_root(self):
        """GIVEN a repo with an absolute URL and a layer with root URL
        WHEN resolving
        THEN the absolute URL is returned as-is."""
        from releaseboard.config.models import (
            AppConfig,
            LayerConfig,
            ReleaseConfig,
            RepositoryConfig,
            SettingsConfig,
        )
        config = AppConfig(
            release=ReleaseConfig(name="Test", target_month=3, target_year=2025),
            layers=[LayerConfig(id="db", label="DB", repository_root_url="https://git.example.com/database")],
            repositories=[
                RepositoryConfig(
                    name="core",
                    url="https://other.host/db-core.git",
                    layer="db",
                ),
            ],
            settings=SettingsConfig(repository_root_url="https://git.example.com/global"),
        )
        assert config.resolve_repo_url(config.repositories[0]) == "https://other.host/db-core.git"

    def test_layer_root_trailing_slash_stripped(self):
        """GIVEN a layer root URL with trailing slash
        WHEN composing with slug
        THEN no double slash."""
        from releaseboard.config.models import (
            AppConfig,
            LayerConfig,
            ReleaseConfig,
            RepositoryConfig,
            SettingsConfig,
        )
        config = AppConfig(
            release=ReleaseConfig(name="Test", target_month=3, target_year=2025),
            layers=[LayerConfig(id="api", label="API", repository_root_url="https://git.example.com/backend/")],
            repositories=[RepositoryConfig(name="svc", url="my-svc", layer="api")],
            settings=SettingsConfig(),
        )
        resolved = config.resolve_repo_url(config.repositories[0])
        assert resolved == "https://git.example.com/backend/my-svc"
        assert "//" not in resolved.split("://")[1]
