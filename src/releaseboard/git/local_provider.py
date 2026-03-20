"""Local git provider — uses git CLI subprocess calls."""

from __future__ import annotations

import contextlib
import subprocess
from datetime import datetime

from releaseboard.domain.models import BranchInfo
from releaseboard.git.provider import GitAccessError, GitProvider
from releaseboard.shared.logging import get_logger

logger = get_logger("git.local")


class LocalGitProvider(GitProvider):
    """Git provider that uses the local `git` CLI.

    Supports both remote URLs (via `git ls-remote`) and local clones.
    For branch metadata, clones or fetches as needed.
    """

    def list_remote_branches(self, repo_url: str, timeout: int = 30) -> list[str]:
        """List branches using `git ls-remote --heads`."""
        try:
            result = subprocess.run(
                ["git", "ls-remote", "--heads", repo_url],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if result.returncode != 0:
                raise GitAccessError(repo_url, result.stderr.strip())

            branches: list[str] = []
            for line in result.stdout.strip().splitlines():
                if not line:
                    continue
                parts = line.split("\t")
                if len(parts) == 2:
                    ref = parts[1]
                    branch_name = ref.removeprefix("refs/heads/")
                    branches.append(branch_name)
            return branches

        except subprocess.TimeoutExpired as exc:
            raise GitAccessError(repo_url, f"Timeout after {timeout}s") from exc
        except FileNotFoundError as exc:
            raise GitAccessError(repo_url, "git CLI not found") from exc

    def get_branch_info(
        self, repo_url: str, branch_name: str, timeout: int = 30
    ) -> BranchInfo | None:
        """Get branch info using `git ls-remote` and, for local repos, `git log`.

        For remote URLs, metadata is limited to existence confirmation.
        For local paths, full metadata is available.
        """
        import os

        # Check if this is a local repo path
        is_local = os.path.isdir(os.path.join(repo_url, ".git")) or (
            os.path.isdir(repo_url) and os.path.isfile(os.path.join(repo_url, "HEAD"))
        )

        if is_local:
            return self._get_local_branch_info(repo_url, branch_name, timeout)
        return self._get_remote_branch_info(repo_url, branch_name, timeout)

    def _get_remote_branch_info(
        self, repo_url: str, branch_name: str, timeout: int
    ) -> BranchInfo | None:
        """Get limited branch info from a remote repository."""
        try:
            result = subprocess.run(
                ["git", "ls-remote", "--heads", repo_url, f"refs/heads/{branch_name}"],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if result.returncode != 0 or not result.stdout.strip():
                return None

            return BranchInfo(
                name=branch_name,
                exists=True,
                data_source="git_cli",
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return None

    def get_default_branch_info(
        self, repo_url: str, timeout: int = 30
    ) -> BranchInfo | None:
        """Detect the default branch via `git ls-remote --symref HEAD`.

        Works for any public remote without cloning.
        """
        try:
            result = subprocess.run(
                ["git", "ls-remote", "--symref", repo_url, "HEAD"],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if result.returncode != 0:
                return None

            default_branch = None
            for line in result.stdout.splitlines():
                if line.startswith("ref:"):
                    parts = line.split()
                    if len(parts) >= 2:
                        default_branch = parts[1].removeprefix("refs/heads/")
                    break

            if default_branch:
                return BranchInfo(
                    name=default_branch,
                    exists=True,
                    repo_default_branch=default_branch,
                    repo_visibility="public",
                    data_source="git_cli",
                )
            return None
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return None

    def _get_local_branch_info(
        self, repo_path: str, branch_name: str, timeout: int
    ) -> BranchInfo | None:
        """Get full branch info from a local repository clone."""
        try:
            # Check if branch exists
            result = subprocess.run(
                ["git", "-C", repo_path, "rev-parse", "--verify", f"refs/heads/{branch_name}"],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if result.returncode != 0:
                # Also check remote tracking branches
                result = subprocess.run(
                    [
                        "git", "-C", repo_path, "rev-parse", "--verify",
                        f"refs/remotes/origin/{branch_name}",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
                if result.returncode != 0:
                    return None
                ref = f"refs/remotes/origin/{branch_name}"
            else:
                ref = f"refs/heads/{branch_name}"

            # Get last commit info
            log_result = subprocess.run(
                [
                    "git", "-C", repo_path, "log", "-1",
                    "--format=%aI%n%an%n%s", ref,
                ],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            last_date = None
            last_author = None
            last_message = None
            if log_result.returncode == 0 and log_result.stdout.strip():
                lines = log_result.stdout.strip().splitlines()
                if len(lines) >= 1:
                    last_date = _parse_iso_datetime(lines[0])
                if len(lines) >= 2:
                    last_author = lines[1]
                if len(lines) >= 3:
                    last_message = lines[2]

            # Estimate creation date heuristically:
            # Use the first commit that is on this branch but not on the default branch.
            # This is a best-effort approximation.
            estimated_creation = self._estimate_branch_creation(
                repo_path, branch_name, ref, timeout
            )

            # Count commits on branch
            count_result = subprocess.run(
                ["git", "-C", repo_path, "rev-list", "--count", ref],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            commit_count = None
            if count_result.returncode == 0:
                with contextlib.suppress(ValueError):
                    commit_count = int(count_result.stdout.strip())

            return BranchInfo(
                name=branch_name,
                exists=True,
                last_commit_date=last_date,
                last_commit_author=last_author,
                last_commit_message=last_message,
                estimated_creation_date=estimated_creation,
                commit_count=commit_count,
                data_source="local",
            )
        except subprocess.TimeoutExpired:
            logger.warning("Timeout getting branch info for %s in %s", branch_name, repo_path)
            return None

    def _estimate_branch_creation(
        self, repo_path: str, branch_name: str, ref: str, timeout: int
    ) -> datetime | None:
        """Estimate when a branch was created by finding the merge-base with main/master.

        This is heuristic — the "first divergent commit" date is used as a proxy.
        Git does not store branch creation times natively.
        """
        for default in ("main", "master"):
            try:
                merge_base = subprocess.run(
                    ["git", "-C", repo_path, "merge-base", default, ref],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
                if merge_base.returncode != 0:
                    continue
                base_sha = merge_base.stdout.strip()
                if not base_sha:
                    continue

                # Get date of the first commit after the merge-base
                first_result = subprocess.run(
                    [
                        "git", "-C", repo_path, "log", "--format=%aI",
                        "--reverse", f"{base_sha}..{ref}",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
                if first_result.returncode == 0 and first_result.stdout.strip():
                    lines = first_result.stdout.strip().splitlines()
                    if lines:
                        return _parse_iso_datetime(lines[0])
            except subprocess.TimeoutExpired:
                continue
        return None


def _parse_iso_datetime(raw: str) -> datetime | None:
    """Parse an ISO 8601 datetime string from git."""
    try:
        return datetime.fromisoformat(raw)
    except (ValueError, TypeError):
        try:
            # Fallback for older formats
            return datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S%z")
        except (ValueError, TypeError):
            return None
