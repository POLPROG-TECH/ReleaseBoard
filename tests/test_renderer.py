"""Tests for HTML rendering."""

from datetime import UTC, datetime

from releaseboard.analysis.metrics import compute_dashboard_metrics
from releaseboard.domain.enums import ReadinessStatus
from releaseboard.domain.models import BranchInfo, RepositoryAnalysis
from releaseboard.presentation.renderer import DashboardRenderer
from releaseboard.presentation.view_models import build_dashboard_view_model


def _make_analysis(name, layer, status):
    branch = None
    if status == ReadinessStatus.READY:
        branch = BranchInfo(
            name="release/03.2025", exists=True,
            last_commit_date=datetime.now(tz=UTC),
        )
    return RepositoryAnalysis(
        name=name, url=f"https://github.com/acme/{name}.git",
        layer=layer, default_branch="main",
        expected_pattern="release/{MM}.{YYYY}",
        expected_branch_name="release/03.2025",
        status=status, branch=branch,
        naming_valid=status == ReadinessStatus.READY,
    )


class TestDashboardRendering:

    def test_renders_valid_html(self, sample_config):
        # GIVEN some analysis results
        analyses = [
            _make_analysis("web-app", "ui", ReadinessStatus.READY),
            _make_analysis("core-api", "api", ReadinessStatus.MISSING_BRANCH),
        ]
        metrics = compute_dashboard_metrics(
            analyses, {layer.id: layer.label for layer in sample_config.layers}
        )
        vm = build_dashboard_view_model(sample_config, analyses, metrics)

        # WHEN rendered
        renderer = DashboardRenderer()
        html = renderer.render(vm)

        # THEN it's valid HTML with expected content
        assert "<!DOCTYPE html>" in html
        assert "TestBoard" in html
        assert "web-app" in html
        assert "core-api" in html

    def test_renders_to_file(self, sample_config, tmp_path):
        analyses = [_make_analysis("repo1", "ui", ReadinessStatus.READY)]
        metrics = compute_dashboard_metrics(analyses)
        vm = build_dashboard_view_model(sample_config, analyses, metrics)

        renderer = DashboardRenderer()
        output = tmp_path / "output" / "dashboard.html"
        result_path = renderer.render_to_file(vm, output)

        assert result_path.exists()
        content = result_path.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content

    def test_theme_attribute_in_html(self, sample_config):
        analyses = [_make_analysis("r", "ui", ReadinessStatus.READY)]
        metrics = compute_dashboard_metrics(analyses)
        vm = build_dashboard_view_model(sample_config, analyses, metrics)

        renderer = DashboardRenderer()
        html = renderer.render(vm)
        assert 'data-theme="system"' in html

    def test_charts_data_embedded(self, sample_config):
        """Charts were removed — verify metrics are still rendered."""
        analyses = [
            _make_analysis("a", "ui", ReadinessStatus.READY),
            _make_analysis("b", "api", ReadinessStatus.MISSING_BRANCH),
        ]
        metrics = compute_dashboard_metrics(analyses, {"ui": "UI", "api": "API"})
        vm = build_dashboard_view_model(sample_config, analyses, metrics)

        renderer = DashboardRenderer()
        html = renderer.render(vm)

        assert "Ready" in html
        assert "Missing Branch" in html

    def test_attention_items_displayed(self, sample_config):
        analyses = [
            _make_analysis("broken", "ui", ReadinessStatus.ERROR),
        ]
        metrics = compute_dashboard_metrics(analyses)
        vm = build_dashboard_view_model(sample_config, analyses, metrics)

        renderer = DashboardRenderer()
        html = renderer.render(vm)

        assert "Needs Attention" in html
        assert "broken" in html
