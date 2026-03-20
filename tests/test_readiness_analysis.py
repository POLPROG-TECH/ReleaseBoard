"""Tests for readiness analysis — status evaluation, scoring, edge cases."""

from datetime import UTC, datetime

from releaseboard.analysis.readiness import ReadinessAnalyzer
from releaseboard.domain.enums import ReadinessStatus
from releaseboard.domain.models import BranchInfo


class TestReadinessAnalysis:
    """Scenarios for the core readiness evaluation logic."""

    def test_ready_when_branch_exists_and_naming_valid_and_fresh(
        self, sample_config, recent_branch_info
    ):
        """GIVEN a repo with a matching, valid, fresh release branch."""
        repo = sample_config.repositories[0]  # web-app, ui
        branches = ["main", "release/03.2025", "develop"]

        """WHEN analyzed."""
        analyzer = ReadinessAnalyzer(sample_config)
        result = analyzer.analyze(repo, branches, recent_branch_info)

        """THEN status is READY."""
        assert result.status == ReadinessStatus.READY
        assert result.naming_valid is True
        assert result.is_stale is False

    def test_missing_branch_when_no_match(self, sample_config):
        """GIVEN a repo where the release branch does not exist."""
        repo = sample_config.repositories[0]
        branches = ["main", "develop", "feature/login"]

        """WHEN analyzed."""
        analyzer = ReadinessAnalyzer(sample_config)
        result = analyzer.analyze(repo, branches, None)

        """THEN status is MISSING_BRANCH."""
        assert result.status == ReadinessStatus.MISSING_BRANCH
        assert result.branch_exists is False

    def test_stale_when_branch_is_old(self, sample_config, stale_branch_info):
        """GIVEN a repo with a release branch that has not been touched in months."""
        repo = sample_config.repositories[0]
        branches = ["main", "release/03.2025"]

        """WHEN analyzed."""
        analyzer = ReadinessAnalyzer(sample_config)
        result = analyzer.analyze(repo, branches, stale_branch_info)

        """THEN status is STALE."""
        assert result.status == ReadinessStatus.STALE
        assert result.is_stale is True

    def test_invalid_naming_when_pattern_mismatch(self, sample_config):
        """GIVEN a repo in the API layer with a branch matching
        the format but not the exact expected name."""
        repo = sample_config.repositories[2]  # core-api, api
        branches = ["main", "release/2024.03"]
        branch_info = BranchInfo(
            name="release/2024.03",
            exists=True,
            last_commit_date=datetime.now(tz=UTC),
        )

        """WHEN analyzed."""
        analyzer = ReadinessAnalyzer(sample_config)
        result = analyzer.analyze(repo, branches, branch_info)

        """THEN naming is invalid because the branch is not the exact expected name."""
        assert result.status == ReadinessStatus.INVALID_NAMING
        assert result.naming_valid is False

    def test_error_state_on_git_failure(self, sample_config):
        """GIVEN a repo that cannot be accessed."""
        repo = sample_config.repositories[0]

        """WHEN error analysis is created."""
        analyzer = ReadinessAnalyzer(sample_config)
        result = analyzer.analyze_error(repo, "Connection refused")

        """THEN status is ERROR with message."""
        assert result.status == ReadinessStatus.ERROR
        assert result.error_message == "Connection refused"

    def test_layer_pattern_applied_correctly(self, sample_config):
        """GIVEN the API layer uses release/{YYYY}.{MM} pattern."""
        repo = sample_config.repositories[2]  # core-api, api
        branches = ["main", "release/2025.03"]
        branch_info = BranchInfo(
            name="release/2025.03",
            exists=True,
            last_commit_date=datetime.now(tz=UTC),
        )

        """WHEN analyzed."""
        analyzer = ReadinessAnalyzer(sample_config)
        result = analyzer.analyze(repo, branches, branch_info)

        """THEN it is ready and layer pattern matches."""
        assert result.status == ReadinessStatus.READY
        assert result.expected_branch_name == "release/2025.03"

    def test_repo_level_pattern_override(self, sample_config):
        """GIVEN the migrations repo has its own pattern db-release/{MM}.{YYYY}."""
        repo = sample_config.repositories[4]  # migrations, db
        branches = ["main", "db-release/03.2025"]
        branch_info = BranchInfo(
            name="db-release/03.2025",
            exists=True,
            last_commit_date=datetime.now(tz=UTC),
        )

        """WHEN analyzed."""
        analyzer = ReadinessAnalyzer(sample_config)
        result = analyzer.analyze(repo, branches, branch_info)

        """THEN it uses the repo-level pattern."""
        assert result.expected_branch_name == "db-release/03.2025"
        assert result.status == ReadinessStatus.READY

    def test_ready_when_branch_exists_but_no_commit_date(self, sample_config):
        """GIVEN a branch with no commit date info from remote-only inspection."""
        repo = sample_config.repositories[0]
        branches = ["main", "release/03.2025"]
        branch_info = BranchInfo(name="release/03.2025", exists=True)

        """WHEN analyzed."""
        analyzer = ReadinessAnalyzer(sample_config)
        result = analyzer.analyze(repo, branches, branch_info)

        """THEN it is ready because absence of commit metadata does not penalize."""
        assert result.status == ReadinessStatus.READY
