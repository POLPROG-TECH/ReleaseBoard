"""Tests for metrics aggregation."""

from datetime import UTC, datetime

from releaseboard.analysis.metrics import compute_dashboard_metrics
from releaseboard.domain.enums import ReadinessStatus
from releaseboard.domain.models import BranchInfo, RepositoryAnalysis


def _make_analysis(name: str, layer: str, status: ReadinessStatus) -> RepositoryAnalysis:
    branch = None
    if status == ReadinessStatus.READY:
        branch = BranchInfo(
            name="release/03.2025",
            exists=True,
            last_commit_date=datetime.now(tz=UTC),
        )
    return RepositoryAnalysis(
        name=name,
        url=f"https://github.com/acme/{name}.git",
        layer=layer,
        default_branch="main",
        expected_pattern="release/{MM}.{YYYY}",
        expected_branch_name="release/03.2025",
        status=status,
        branch=branch,
        naming_valid=status == ReadinessStatus.READY,
    )


class TestMetricsComputation:

    def test_all_ready(self):
        # GIVEN all repos are ready
        analyses = [
            _make_analysis("a", "ui", ReadinessStatus.READY),
            _make_analysis("b", "api", ReadinessStatus.READY),
        ]

        # WHEN metrics are computed
        metrics = compute_dashboard_metrics(analyses)

        # THEN 100% readiness
        assert metrics.total == 2
        assert metrics.ready == 2
        assert metrics.readiness_pct == 100.0
        assert metrics.missing == 0
        assert len(metrics.attention_items) == 0

    def test_mixed_statuses(self):
        analyses = [
            _make_analysis("a", "ui", ReadinessStatus.READY),
            _make_analysis("b", "ui", ReadinessStatus.MISSING_BRANCH),
            _make_analysis("c", "api", ReadinessStatus.STALE),
            _make_analysis("d", "api", ReadinessStatus.READY),
        ]

        metrics = compute_dashboard_metrics(analyses, {"ui": "UI", "api": "API"})

        assert metrics.total == 4
        assert metrics.ready == 2
        assert metrics.missing == 1
        assert metrics.stale == 1
        assert metrics.readiness_pct == 50.0
        assert len(metrics.attention_items) == 2

    def test_layer_metrics(self):
        analyses = [
            _make_analysis("a", "ui", ReadinessStatus.READY),
            _make_analysis("b", "ui", ReadinessStatus.READY),
            _make_analysis("c", "api", ReadinessStatus.MISSING_BRANCH),
        ]

        metrics = compute_dashboard_metrics(analyses, {"ui": "UI", "api": "API"})

        # THEN UI layer is 100%, API is 0%
        assert metrics.layer_metrics["ui"].readiness_pct == 100.0
        assert metrics.layer_metrics["api"].readiness_pct == 0.0
        assert metrics.layer_metrics["api"].missing == 1

    def test_empty_list(self):
        metrics = compute_dashboard_metrics([])
        assert metrics.total == 0
        assert metrics.readiness_pct == 0.0

    def test_attention_items_sorted_by_severity(self):
        analyses = [
            _make_analysis("warning-repo", "ui", ReadinessStatus.WARNING),
            _make_analysis("error-repo", "ui", ReadinessStatus.ERROR),
            _make_analysis("missing-repo", "api", ReadinessStatus.MISSING_BRANCH),
        ]

        metrics = compute_dashboard_metrics(analyses)

        # THEN sorted by severity (ERROR first)
        assert metrics.attention_items[0].status == ReadinessStatus.ERROR
        assert metrics.attention_items[1].status == ReadinessStatus.MISSING_BRANCH
