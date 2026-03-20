"""Readiness analysis — evaluates release readiness for each repository."""

from __future__ import annotations

from typing import TYPE_CHECKING

from releaseboard.analysis.branch_pattern import BranchPatternMatcher
from releaseboard.analysis.staleness import is_stale
from releaseboard.domain.enums import ReadinessStatus
from releaseboard.domain.models import BranchInfo, RepositoryAnalysis
from releaseboard.shared.logging import get_logger

if TYPE_CHECKING:
    from releaseboard.config.models import AppConfig, RepositoryConfig

logger = get_logger("readiness")


class ReadinessAnalyzer:
    """Evaluates release readiness for repositories."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.matcher = BranchPatternMatcher()

    def analyze(
        self,
        repo_config: RepositoryConfig,
        remote_branches: list[str],
        branch_info: BranchInfo | None,
        default_branch_info: BranchInfo | None = None,
    ) -> RepositoryAnalysis:
        """Analyze a single repository's release readiness.

        Args:
            repo_config: Repository configuration.
            remote_branches: List of all branch names in the repo.
            branch_info: Metadata for the expected release branch (if found).
            default_branch_info: Optional metadata for the repo's default branch,
                used as a fallback intelligence source when the release branch
                is missing but the repository is reachable.

        Returns:
            Complete RepositoryAnalysis.
        """
        pattern_template = self.config.resolve_branch_pattern(repo_config)
        resolved = self.matcher.resolve(
            pattern_template,
            self.config.release.target_month,
            self.config.release.target_year,
        )

        warnings: list[str] = []
        notes: list[str] = []

        # Check if any branch matches the pattern
        matching = self.matcher.find_matching(remote_branches, resolved)

        if not matching:
            # Determine intelligence source for repo metadata
            metadata_source = branch_info or default_branch_info
            repo_notes = list(notes)
            last_activity = None

            if metadata_source and metadata_source.repo_default_branch:
                repo_notes.append(
                    f"Repository reachable. Default branch: {metadata_source.repo_default_branch}"
                )
            if metadata_source and metadata_source.repo_visibility:
                repo_notes.append(
                    f"Repository visibility: {metadata_source.repo_visibility}"
                )
            if metadata_source and metadata_source.data_source:
                ds = metadata_source.data_source
                ds_label = {
                    "github_api": "GitHub API",
                    "git_cli": "Public git inspection",
                    "local": "Local clone",
                }.get(ds, ds)
                repo_notes.append(f"Data source: {ds_label}")
            if default_branch_info and default_branch_info.last_commit_date:
                last_activity = default_branch_info.last_commit_date
                repo_notes.append(
                    "Last activity from default branch (release branch not found)"
                )

            return RepositoryAnalysis(
                name=repo_config.name,
                url=repo_config.url,
                layer=repo_config.layer,
                default_branch=repo_config.default_branch,
                expected_pattern=pattern_template,
                expected_branch_name=resolved.resolved_name,
                status=ReadinessStatus.MISSING_BRANCH,
                branch=metadata_source,
                naming_valid=False,
                is_stale=False,
                last_activity=last_activity,
                warnings=tuple(["Release branch not found"]),
                notes=tuple(repo_notes),
            )

        # Branch exists — check naming
        exact = resolved.resolved_name in matching
        naming_valid = exact

        if not exact:
            warnings.append(
                f"Branch matches pattern but is not the exact expected name "
                f"'{resolved.resolved_name}'; found: {matching}"
            )

        # Use provided branch_info or build a minimal one
        if branch_info is None:
            branch_info = BranchInfo(
                name=matching[0],
                exists=True,
            )

        # Staleness check
        stale = is_stale(
            branch_info.last_commit_date,
            self.config.settings.stale_threshold_days,
        )

        # Determine status
        status = self._compute_status(naming_valid, stale, branch_info, warnings)

        # Notes about estimated creation date
        if branch_info.estimated_creation_date is not None:
            notes.append(
                "⚠ Branch creation date is estimated heuristically from the first "
                "divergent commit. This is an approximation, not a guaranteed value."
            )

        return RepositoryAnalysis(
            name=repo_config.name,
            url=repo_config.url,
            layer=repo_config.layer,
            default_branch=repo_config.default_branch,
            expected_pattern=pattern_template,
            expected_branch_name=resolved.resolved_name,
            status=status,
            branch=branch_info,
            naming_valid=naming_valid,
            is_stale=stale,
            last_activity=branch_info.last_commit_date,
            first_activity=branch_info.estimated_creation_date,
            warnings=tuple(warnings),
            notes=tuple(notes),
        )

    def _compute_status(
        self,
        naming_valid: bool,
        stale: bool,
        branch_info: BranchInfo,
        warnings: list[str],
    ) -> ReadinessStatus:
        if not naming_valid:
            return ReadinessStatus.INVALID_NAMING

        if stale:
            # No commit metadata → branch exists but we have no freshness data
            # (typical for remote-only inspection). Not truly stale/inactive.
            if branch_info.last_commit_date is None:
                if warnings:
                    return ReadinessStatus.WARNING
                return ReadinessStatus.READY

            return ReadinessStatus.STALE

        if warnings:
            return ReadinessStatus.WARNING

        return ReadinessStatus.READY

    def analyze_error(
        self,
        repo_config: RepositoryConfig,
        error_message: str,
    ) -> RepositoryAnalysis:
        """Create an error-state analysis when git access fails."""
        pattern_template = self.config.resolve_branch_pattern(repo_config)
        resolved = self.matcher.resolve(
            pattern_template,
            self.config.release.target_month,
            self.config.release.target_year,
        )
        return RepositoryAnalysis(
            name=repo_config.name,
            url=repo_config.url,
            layer=repo_config.layer,
            default_branch=repo_config.default_branch,
            expected_pattern=pattern_template,
            expected_branch_name=resolved.resolved_name,
            status=ReadinessStatus.ERROR,
            error_message=error_message,
        )
