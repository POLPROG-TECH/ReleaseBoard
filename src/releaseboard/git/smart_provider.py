"""Smart git provider — dispatches to GitHub API with git CLI fallback."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from releaseboard.git.github_provider import GitHubProvider, parse_github_url
from releaseboard.git.local_provider import LocalGitProvider
from releaseboard.git.provider import GitAccessError, GitErrorKind, GitProvider

if TYPE_CHECKING:
    from releaseboard.domain.models import BranchInfo

logger = logging.getLogger(__name__)

# Error kinds that indicate API-level failure (not repository-specific)
_API_FAILURE_KINDS = frozenset({
    GitErrorKind.RATE_LIMITED,
    GitErrorKind.NETWORK_ERROR,
    GitErrorKind.PROVIDER_UNAVAILABLE,
    GitErrorKind.DNS_RESOLUTION,
    GitErrorKind.TIMEOUT,
})


class SmartGitProvider(GitProvider):
    """Routes requests to GitHubProvider for GitHub URLs, else LocalGitProvider.

    When the GitHub REST API is unavailable (rate-limited, network error, etc.),
    automatically falls back to direct git CLI inspection (``git ls-remote``)
    for public repositories. This ensures public repos remain analyzable even
    without API access.

    After ``_API_RETRY_TTL`` seconds, the provider re-attempts the GitHub API
    instead of staying permanently degraded.
    """

    _API_RETRY_TTL = 300  # Re-check GitHub API availability after 5 minutes

    def __init__(self, github_token: str | None = None) -> None:
        self._github = GitHubProvider(token=github_token)
        self._local = LocalGitProvider()
        self._github_api_available = True
        self._api_unavailable_since: float | None = None

    def _check_api_available(self) -> bool:
        """Check if GitHub API should be attempted (with TTL-based reset)."""
        if self._github_api_available:
            return True
        if self._api_unavailable_since is not None:
            elapsed = time.monotonic() - self._api_unavailable_since
            if elapsed >= self._API_RETRY_TTL:
                self._github_api_available = True
                self._api_unavailable_since = None
                logger.info(
                    "Re-enabling GitHub API after %.0fs cooldown", elapsed,
                )
                return True
        return False

    def _mark_api_unavailable(self) -> None:
        """Record that GitHub API is temporarily unavailable."""
        self._github_api_available = False
        self._api_unavailable_since = time.monotonic()

    def _is_github(self, repo_url: str) -> bool:
        return parse_github_url(repo_url) is not None

    def list_remote_branches(self, repo_url: str, timeout: int = 30) -> list[str]:
        if not self._is_github(repo_url):
            return self._local.list_remote_branches(repo_url, timeout)

        api_error: GitAccessError | None = None
        if self._check_api_available():
            try:
                return self._github.list_remote_branches(repo_url, timeout)
            except GitAccessError as exc:
                if exc.kind not in _API_FAILURE_KINDS:
                    raise  # Repo-specific error — don't fall back
                api_error = exc
                self._mark_api_unavailable()
                logger.info(
                    "GitHub API unavailable (%s) for %s, falling back to git CLI",
                    exc.kind.value, repo_url,
                )

        # Fallback to git CLI (git ls-remote)
        try:
            return self._local.list_remote_branches(repo_url, timeout)
        except GitAccessError as local_exc:
            # Both strategies failed — combine context
            api_detail = api_error.detail if api_error else "skipped (previously failed)"
            msg = f"GitHub API: {api_detail}; Git CLI: {local_exc.detail}"
            raise GitAccessError(repo_url, msg, kind=local_exc.kind) from local_exc

    def get_branch_info(
        self, repo_url: str, branch_name: str, timeout: int = 30
    ) -> BranchInfo | None:
        if not self._is_github(repo_url):
            return self._local.get_branch_info(repo_url, branch_name, timeout)

        if self._check_api_available():
            try:
                return self._github.get_branch_info(repo_url, branch_name, timeout)
            except GitAccessError as exc:
                if exc.kind not in _API_FAILURE_KINDS:
                    raise
                self._mark_api_unavailable()
                logger.info(
                    "GitHub API unavailable (%s) for branch info, using git CLI",
                    exc.kind.value,
                )

        return self._local.get_branch_info(repo_url, branch_name, timeout)

    def get_default_branch_info(
        self, repo_url: str, timeout: int = 30
    ) -> BranchInfo | None:
        """Get default branch info — tries GitHub API, then git CLI fallback."""
        if not self._is_github(repo_url):
            return self._local.get_default_branch_info(repo_url, timeout)

        if self._check_api_available():
            try:
                return self._github.get_default_branch_info(repo_url, timeout)
            except GitAccessError as exc:
                if exc.kind not in _API_FAILURE_KINDS:
                    raise
                self._mark_api_unavailable()
                logger.info(
                    "GitHub API unavailable (%s) for default branch, using git CLI",
                    exc.kind.value,
                )

        return self._local.get_default_branch_info(repo_url, timeout)
