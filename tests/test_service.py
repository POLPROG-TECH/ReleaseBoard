"""Tests for the AnalysisService — shared analysis pipeline."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from releaseboard.application.service import (
    AnalysisPhase,
    AnalysisProgress,
    AnalysisResult,
    AnalysisService,
    RepoProgress,
)
from releaseboard.config.models import (
    AppConfig,
    BrandingConfig,
    LayerConfig,
    ReleaseConfig,
    RepositoryConfig,
    SettingsConfig,
)
from releaseboard.domain.enums import ReadinessStatus
from releaseboard.domain.models import BranchInfo
from releaseboard.git.provider import GitAccessError, GitProvider

# ── Fixtures ──


@pytest.fixture
def two_repo_config() -> AppConfig:
    return AppConfig(
        release=ReleaseConfig(
            name="March 2025",
            target_month=3,
            target_year=2025,
            branch_pattern="release/{MM}.{YYYY}",
        ),
        layers=[LayerConfig(id="api", label="API", order=0)],
        repositories=[
            RepositoryConfig(name="svc-alpha", url="https://git.local/svc-alpha.git", layer="api"),
            RepositoryConfig(name="svc-beta", url="https://git.local/svc-beta.git", layer="api"),
        ],
        branding=BrandingConfig(),
        settings=SettingsConfig(),
    )


class StubGitProvider(GitProvider):
    """Configurable stub for testing without real git."""

    def __init__(
        self,
        branches: dict[str, list[str]] | None = None,
        branch_info: dict[str, BranchInfo | None] | None = None,
        errors: dict[str, Exception] | None = None,
    ) -> None:
        self._branches = branches or {}
        self._branch_info = branch_info or {}
        self._errors = errors or {}

    def list_remote_branches(self, url: str, timeout: int = 30) -> list[str]:
        if url in self._errors:
            raise self._errors[url]
        return self._branches.get(url, [])

    def get_branch_info(self, url: str, branch: str, timeout: int = 30) -> BranchInfo | None:
        if url in self._errors:
            raise self._errors[url]
        return self._branch_info.get(url)


# ── AnalysisProgress unit tests ──


class TestAnalysisProgress:
    def test_progress_pct_empty(self):
        # GIVEN no repos
        p = AnalysisProgress(total=0, completed=0)
        # THEN percentage is 0
        assert p.progress_pct == 0.0

    def test_progress_pct_partial(self):
        # GIVEN 3/10 completed
        p = AnalysisProgress(total=10, completed=3)
        # THEN percentage is 30%
        assert p.progress_pct == 30.0

    def test_to_dict_contains_required_keys(self):
        p = AnalysisProgress(
            phase=AnalysisPhase.ANALYZING,
            total=5,
            completed=2,
            current_repo="my-repo",
            repos=[RepoProgress(name="my-repo", status="analyzing")],
        )
        d = p.to_dict()
        assert d["phase"] == "analyzing"
        assert d["total"] == 5
        assert d["completed"] == 2
        assert d["current_repo"] == "my-repo"
        assert len(d["repos"]) == 1
        assert d["repos"][0]["name"] == "my-repo"


# ── AnalysisService tests ──


class TestAnalysisService:
    @pytest.mark.asyncio
    async def test_successful_analysis_of_all_repos(self, two_repo_config: AppConfig):
        """GIVEN two repos with matching release branches
        WHEN analysis completes
        THEN both repos are analyzed and metrics computed."""
        provider = StubGitProvider(
            branches={
                "https://git.local/svc-alpha.git": ["main", "release/03.2025"],
                "https://git.local/svc-beta.git": ["main", "release/03.2025"],
            },
            branch_info={
                "https://git.local/svc-alpha.git": BranchInfo(
                    exists=True,
                    name="release/03.2025",
                    last_commit_date=datetime.now(tz=UTC),
                    last_commit_author="dev",
                    last_commit_message="feat: ready",
                ),
                "https://git.local/svc-beta.git": BranchInfo(
                    exists=True,
                    name="release/03.2025",
                    last_commit_date=datetime.now(tz=UTC),
                    last_commit_author="dev",
                    last_commit_message="fix: done",
                ),
            },
        )
        service = AnalysisService(provider)
        result = await service.analyze_async(two_repo_config)

        assert isinstance(result, AnalysisResult)
        assert len(result.analyses) == 2
        assert result.progress.phase == AnalysisPhase.COMPLETED
        assert result.progress.completed == 2
        assert result.progress.error_count == 0
        assert result.metrics.total == 2
        assert result.metrics.ready == 2

    @pytest.mark.asyncio
    async def test_git_error_produces_partial_failure(self, two_repo_config: AppConfig):
        """GIVEN one repo that errors
        WHEN analysis completes
        THEN result shows partial failure."""
        provider = StubGitProvider(
            branches={"https://git.local/svc-alpha.git": ["main", "release/03.2025"]},
            branch_info={
                "https://git.local/svc-alpha.git": BranchInfo(
                    exists=True,
                    name="release/03.2025",
                    last_commit_date=datetime.now(tz=UTC),
                    last_commit_author="dev",
                    last_commit_message="ok",
                ),
            },
            errors={
                "https://git.local/svc-beta.git":
                    GitAccessError(
                        "https://git.local/svc-beta.git",
                        "timeout",
                    ),
            },
        )
        service = AnalysisService(provider)
        result = await service.analyze_async(two_repo_config)

        assert result.progress.phase == AnalysisPhase.PARTIAL_FAILURE
        assert result.progress.error_count == 1
        assert any(a.status == ReadinessStatus.ERROR for a in result.analyses)

    @pytest.mark.asyncio
    async def test_all_errors_produces_failed(self, two_repo_config: AppConfig):
        """GIVEN all repos that error
        WHEN analysis completes
        THEN result shows failed."""
        provider = StubGitProvider(
            errors={
                "https://git.local/svc-alpha.git": GitAccessError("repo", "fail"),
                "https://git.local/svc-beta.git": GitAccessError("repo", "fail"),
            },
        )
        service = AnalysisService(provider)
        result = await service.analyze_async(two_repo_config)

        assert result.progress.phase == AnalysisPhase.FAILED
        assert result.progress.error_count == 2

    @pytest.mark.asyncio
    async def test_progress_callback_receives_events(self, two_repo_config: AppConfig):
        """GIVEN a progress callback
        WHEN analysis runs
        THEN callback receives start, per-repo, and completion events."""
        provider = StubGitProvider(
            branches={
                "https://git.local/svc-alpha.git": ["release/03.2025"],
                "https://git.local/svc-beta.git": ["release/03.2025"],
            },
            branch_info={
                "https://git.local/svc-alpha.git": BranchInfo(
                    exists=True,
                    name="release/03.2025",
                    last_commit_date=datetime.now(tz=UTC),
                    last_commit_author="dev",
                    last_commit_message="ok",
                ),
                "https://git.local/svc-beta.git": BranchInfo(
                    exists=True,
                    name="release/03.2025",
                    last_commit_date=datetime.now(tz=UTC),
                    last_commit_author="dev",
                    last_commit_message="ok",
                ),
            },
        )
        events: list[tuple[str, dict]] = []

        def on_progress(event_type: str, progress: AnalysisProgress):
            events.append((event_type, progress.to_dict()))

        service = AnalysisService(provider)
        await service.analyze_async(two_repo_config, on_progress=on_progress)

        event_types = [e[0] for e in events]
        assert "analysis_start" in event_types
        assert "repo_start" in event_types
        assert "repo_complete" in event_types
        assert "analysis_complete" in event_types
        assert event_types[-1] == "analysis_complete"

    @pytest.mark.asyncio
    async def test_missing_branch_detected(self, two_repo_config: AppConfig):
        """GIVEN a repo without the expected branch
        WHEN analysis runs
        THEN status is MISSING_BRANCH."""
        provider = StubGitProvider(
            branches={
                "https://git.local/svc-alpha.git": ["main"],
                "https://git.local/svc-beta.git": ["main", "release/03.2025"],
            },
            branch_info={
                "https://git.local/svc-beta.git": BranchInfo(
                    exists=True,
                    name="release/03.2025",
                    last_commit_date=datetime.now(tz=UTC),
                    last_commit_author="dev",
                    last_commit_message="ok",
                ),
            },
        )
        service = AnalysisService(provider)
        result = await service.analyze_async(two_repo_config)

        statuses = {a.name: a.status for a in result.analyses}
        assert statuses["svc-alpha"] == ReadinessStatus.MISSING_BRANCH
        assert statuses["svc-beta"] == ReadinessStatus.READY

    @pytest.mark.asyncio
    async def test_cancellation_stops_after_current_repo(self, two_repo_config: AppConfig):
        """GIVEN a cancel request during analysis
        WHEN analysis is running with max_concurrent=1 (sequential)
        THEN remaining repos are skipped and phase is CANCELLED."""
        from dataclasses import replace
        # Force sequential analysis so cancellation between repos is deterministic
        seq_config = replace(
            two_repo_config,
            settings=replace(two_repo_config.settings, max_concurrent=1),
        )
        call_count = 0

        class SlowProvider(GitProvider):
            def list_remote_branches(self, url: str, timeout: int = 30) -> list[str]:
                nonlocal call_count
                call_count += 1
                return ["main", "release/03.2025"]

            def get_branch_info(
                self, url: str, branch: str, timeout: int = 30,
            ) -> BranchInfo | None:
                return BranchInfo(
                    exists=True,
                    name="release/03.2025",
                    last_commit_date=datetime.now(tz=UTC),
                    last_commit_author="dev",
                    last_commit_message="ok",
                )

        service = AnalysisService(SlowProvider())

        events: list[str] = []

        async def on_progress(event_type: str, progress: AnalysisProgress):
            events.append(event_type)
            # Cancel after first repo completes
            if event_type == "repo_complete" and progress.completed == 1:
                service.request_cancel()

        result = await service.analyze_async(seq_config, on_progress=on_progress)

        assert result.progress.phase == AnalysisPhase.CANCELLED
        assert len(result.analyses) == 1  # Only first repo analyzed
        assert result.progress.repos[1].status == "skipped"
        assert "analysis_stopping" in events

    @pytest.mark.asyncio
    async def test_cancel_when_not_running_is_safe(self):
        """GIVEN no active analysis
        WHEN request_cancel is called
        THEN nothing happens (no error)."""
        service = AnalysisService(StubGitProvider())
        service.request_cancel()  # Should not raise
