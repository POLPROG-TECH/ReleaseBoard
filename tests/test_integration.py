"""Integration test — end-to-end config → analysis → rendering pipeline."""

import json
from datetime import UTC, datetime
from pathlib import Path

from releaseboard.analysis.metrics import compute_dashboard_metrics
from releaseboard.analysis.readiness import ReadinessAnalyzer
from releaseboard.config.loader import load_config
from releaseboard.domain.enums import ReadinessStatus
from releaseboard.domain.models import BranchInfo
from releaseboard.presentation.renderer import DashboardRenderer
from releaseboard.presentation.view_models import build_dashboard_view_model


class TestEndToEnd:

    def test_full_pipeline_produces_valid_dashboard(self, tmp_path: Path):
        """GIVEN a valid config file and simulated branch data
        WHEN the full pipeline runs
        THEN a valid HTML dashboard is produced with correct metrics."""

        # GIVEN — write config file
        config_data = {
            "release": {
                "name": "March 2025 Release",
                "target_month": 3,
                "target_year": 2025,
                "branch_pattern": "release/{MM}.{YYYY}",
            },
            "layers": [
                {"id": "ui", "label": "Frontend", "color": "#3B82F6"},
                {"id": "api", "label": "Backend", "color": "#10B981"},
            ],
            "repositories": [
                {"name": "web-app", "url": "https://github.com/acme/web-app.git", "layer": "ui"},
                {"name": "mobile-app", "url": "https://github.com/acme/mobile.git", "layer": "ui"},
                {"name": "core-api", "url": "https://github.com/acme/core-api.git", "layer": "api"},
            ],
            "branding": {
                "title": "ReleaseBoard",
                "subtitle": "Release Readiness",
                "company": "Acme Inc",
                "primary_color": "#6366F1",
            },
            "settings": {
                "stale_threshold_days": 14,
                "output_path": str(tmp_path / "dashboard.html"),
                "theme": "dark",
            },
        }
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(config_data), encoding="utf-8")

        # Load config
        config = load_config(config_path)
        assert config.release.name == "March 2025 Release"
        assert len(config.repositories) == 3

        # Simulate analysis (no real git access)
        analyzer = ReadinessAnalyzer(config)
        now = datetime.now(tz=UTC)

        analyses = [
            # web-app: ready
            analyzer.analyze(
                config.repositories[0],
                ["main", "release/03.2025"],
                BranchInfo(name="release/03.2025", exists=True, last_commit_date=now),
            ),
            # mobile-app: missing branch
            analyzer.analyze(config.repositories[1], ["main", "develop"], None),
            # core-api: ready
            analyzer.analyze(
                config.repositories[2],
                ["main", "release/03.2025"],
                BranchInfo(name="release/03.2025", exists=True, last_commit_date=now),
            ),
        ]

        # Verify statuses
        assert analyses[0].status == ReadinessStatus.READY
        assert analyses[1].status == ReadinessStatus.MISSING_BRANCH
        assert analyses[2].status == ReadinessStatus.READY

        # Compute metrics
        layer_labels = {layer.id: layer.label for layer in config.layers}
        metrics = compute_dashboard_metrics(analyses, layer_labels)
        assert metrics.total == 3
        assert metrics.ready == 2
        assert metrics.missing == 1
        assert abs(metrics.readiness_pct - 66.7) < 1

        # Build view model and render
        vm = build_dashboard_view_model(config, analyses, metrics)
        assert vm.title == "ReleaseBoard"
        assert vm.theme == "dark"

        renderer = DashboardRenderer()
        output_path = renderer.render_to_file(vm, config.settings.output_path)

        # THEN dashboard file exists and has expected content
        assert output_path.exists()
        html = output_path.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in html
        assert "ReleaseBoard" in html
        assert "March 2025 Release" in html
        assert "web-app" in html
        assert "mobile-app" in html
        assert "Missing Branch" in html
        assert 'data-theme="dark"' in html
        assert "Frontend" in html
        assert "Backend" in html
