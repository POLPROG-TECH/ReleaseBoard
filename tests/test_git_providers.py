"""Tests for git providers — URL parsing, name derivation, author config, smart routing."""

from __future__ import annotations

from datetime import UTC, datetime

from releaseboard.config.models import (
    AuthorConfig,
    derive_name_from_url,
)
from releaseboard.domain.models import BranchInfo
from releaseboard.git.github_provider import parse_github_url
from releaseboard.git.smart_provider import SmartGitProvider

# ──────────────────────────────────────────────────────────────────────────────
# URL → name derivation
# ──────────────────────────────────────────────────────────────────────────────


class TestDeriveNameFromUrl:
    """Scenarios for URL-to-name derivation."""

    def test_https_github_url(self):
        """GIVEN a standard HTTPS GitHub URL."""
        url = "https://github.com/acme/payment-gateway"

        """WHEN deriving the name."""
        result = derive_name_from_url(url)

        """THEN the repository name is extracted."""
        assert result == "payment-gateway"

    def test_https_with_git_suffix(self):
        """GIVEN an HTTPS URL with .git suffix."""
        url = "https://github.com/acme/payment-gateway.git"

        """WHEN deriving the name."""
        result = derive_name_from_url(url)

        """THEN .git is stripped from the name."""
        assert result == "payment-gateway"

    def test_ssh_git_at_syntax(self):
        """GIVEN an SSH git@ URL with .git suffix."""
        url = "git@github.com:team/customer-api.git"

        """WHEN deriving the name."""
        result = derive_name_from_url(url)

        """THEN the repository name is extracted."""
        assert result == "customer-api"

    def test_ssh_scheme(self):
        """GIVEN an SSH scheme URL."""
        url = "ssh://git@git.example.com/team/customer-api.git"

        """WHEN deriving the name."""
        result = derive_name_from_url(url)

        """THEN the repository name is extracted."""
        assert result == "customer-api"

    def test_custom_host(self):
        """GIVEN a URL with a custom host."""
        url = "https://git.example.com/platform/admin-portal.git"

        """WHEN deriving the name."""
        result = derive_name_from_url(url)

        """THEN the repository name is extracted."""
        assert result == "admin-portal"

    def test_trailing_slash(self):
        """GIVEN a URL with a trailing slash."""
        url = "https://github.com/acme/repo/"

        """WHEN deriving the name."""
        result = derive_name_from_url(url)

        """THEN the trailing slash is ignored."""
        assert result == "repo"

    def test_bare_slug(self):
        """GIVEN a bare slug without path separators."""
        slug = "my-service"

        """WHEN deriving the name."""
        result = derive_name_from_url(slug)

        """THEN the slug is returned as-is."""
        assert result == "my-service"

    def test_local_path(self):
        """GIVEN a local filesystem path."""
        path = "/home/user/repos/my-tool"

        """WHEN deriving the name."""
        result = derive_name_from_url(path)

        """THEN the last path component is returned."""
        assert result == "my-tool"

    def test_local_path_with_git_suffix(self):
        """GIVEN a local path with .git suffix."""
        path = "/home/user/repos/my-tool.git"

        """WHEN deriving the name."""
        result = derive_name_from_url(path)

        """THEN .git is stripped from the name."""
        assert result == "my-tool"

    def test_empty_string(self):
        """GIVEN an empty string."""
        url = ""

        """WHEN deriving the name."""
        result = derive_name_from_url(url)

        """THEN an empty string is returned."""
        assert result == ""


# ──────────────────────────────────────────────────────────────────────────────
# GitHub URL parsing
# ──────────────────────────────────────────────────────────────────────────────


class TestParseGitHubUrl:
    """Scenarios for GitHub URL parsing."""

    def test_https_url(self):
        """GIVEN a standard HTTPS GitHub URL."""
        url = "https://github.com/acme/repo"

        """WHEN parsing the URL."""
        result = parse_github_url(url)

        """THEN owner and repo are extracted."""
        assert result == ("acme", "repo")

    def test_https_with_git_suffix(self):
        """GIVEN an HTTPS GitHub URL with .git suffix."""
        url = "https://github.com/acme/repo.git"

        """WHEN parsing the URL."""
        result = parse_github_url(url)

        """THEN owner and repo are extracted without .git."""
        assert result == ("acme", "repo")

    def test_ssh_url(self):
        """GIVEN an SSH GitHub URL."""
        url = "git@github.com:acme/repo.git"

        """WHEN parsing the URL."""
        result = parse_github_url(url)

        """THEN owner and repo are extracted."""
        assert result == ("acme", "repo")

    def test_non_github_returns_none(self):
        """GIVEN a non-GitHub URL."""
        url = "https://gitlab.com/acme/repo"

        """WHEN parsing the URL."""
        result = parse_github_url(url)

        """THEN None is returned."""
        assert result is None

    def test_local_path_returns_none(self):
        """GIVEN a local filesystem path."""
        path = "/home/user/repo"

        """WHEN parsing the URL."""
        result = parse_github_url(path)

        """THEN None is returned."""
        assert result is None


# ──────────────────────────────────────────────────────────────────────────────
# AuthorConfig
# ──────────────────────────────────────────────────────────────────────────────


class TestAuthorConfig:
    """Scenarios for AuthorConfig defaults and custom values."""

    def test_defaults(self):
        """GIVEN a default AuthorConfig with no arguments."""
        a = AuthorConfig()

        """WHEN checking field values."""
        name = a.name

        """THEN all fields are empty strings."""
        assert name == ""
        assert a.role == ""
        assert a.url == ""
        assert a.tagline == ""
        assert a.copyright == ""

    def test_custom_values(self):
        """GIVEN an AuthorConfig with custom values."""
        a = AuthorConfig(
            name="Jane Doe",
            role="Release Manager",
            url="https://github.com/janedoe",
            tagline="Delivering quality releases",
            copyright="© 2025 Jane Doe",
        )

        """WHEN checking field values."""
        name = a.name
        copyright_ = a.copyright

        """THEN the fields reflect the provided values."""
        assert name == "Jane Doe"
        assert copyright_ == "© 2025 Jane Doe"


# ──────────────────────────────────────────────────────────────────────────────
# Readiness status ordering
# ──────────────────────────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
# SmartGitProvider routing
# ──────────────────────────────────────────────────────────────────────────────


class TestSmartGitProvider:
    """Scenarios for SmartGitProvider routing."""

    def test_github_url_uses_github_provider(self):
        """GIVEN a GitHub HTTPS URL."""
        provider = SmartGitProvider()

        """WHEN checking provider routing."""
        result = provider._is_github("https://github.com/acme/repo")

        """THEN it is identified as GitHub."""
        assert result is True

    def test_local_path_uses_local_provider(self):
        """GIVEN a local filesystem path."""
        provider = SmartGitProvider()

        """WHEN checking provider routing."""
        result = provider._is_github("/home/user/repos/my-app")

        """THEN it is not identified as GitHub."""
        assert result is False

    def test_non_github_remote_uses_local_provider(self):
        """GIVEN a non-GitHub remote URL."""
        provider = SmartGitProvider()

        """WHEN checking provider routing."""
        result = provider._is_github("https://gitlab.com/acme/repo.git")

        """THEN it is not identified as GitHub."""
        assert result is False


# ──────────────────────────────────────────────────────────────────────────────
# BranchInfo enriched fields
# ──────────────────────────────────────────────────────────────────────────────


class TestBranchInfoEnrichedFields:
    """Scenarios for BranchInfo enriched metadata fields."""

    def test_new_fields_default_to_none(self):
        """GIVEN a BranchInfo with only required fields."""
        info = BranchInfo(name="main", exists=True)

        """WHEN checking enriched metadata fields."""
        last_commit_sha = info.last_commit_sha
        repo_description = info.repo_description

        """THEN all enriched fields default to None."""
        assert last_commit_sha is None
        assert repo_description is None
        assert info.repo_default_branch is None
        assert info.repo_visibility is None
        assert info.repo_owner is None
        assert info.repo_archived is None
        assert info.repo_web_url is None
        assert info.provider_updated_at is None

    def test_new_fields_can_be_set(self):
        """GIVEN a BranchInfo with all enriched fields set."""
        info = BranchInfo(
            name="release/2025.03",
            exists=True,
            last_commit_sha="abc123",
            repo_description="My service",
            repo_default_branch="main",
            repo_visibility="private",
            repo_owner="acme",
            repo_archived=False,
            repo_web_url="https://github.com/acme/my-service",
            provider_updated_at=datetime(2025, 3, 1, tzinfo=UTC),
        )

        """WHEN checking the field values."""
        last_commit_sha = info.last_commit_sha
        repo_owner = info.repo_owner
        repo_archived = info.repo_archived

        """THEN the fields reflect the provided values."""
        assert last_commit_sha == "abc123"
        assert repo_owner == "acme"
        assert repo_archived is False


# ──────────────────────────────────────────────────────────────────────────────
# Schema validation with author section
# ──────────────────────────────────────────────────────────────────────────────
