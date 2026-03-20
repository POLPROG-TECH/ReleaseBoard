"""Dashboard renderer — generates the HTML dashboard file."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import jinja2

from releaseboard import __version__
from releaseboard.shared.logging import get_logger

if TYPE_CHECKING:
    from releaseboard.presentation.view_models import DashboardViewModel

logger = get_logger("renderer")

_TEMPLATE_DIR = Path(__file__).parent / "templates"


class DashboardRenderer:
    """Renders the HTML dashboard from a DashboardViewModel."""

    def __init__(self) -> None:
        self.env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(_TEMPLATE_DIR)),
            autoescape=jinja2.select_autoescape(["html"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def render(self, view_model: DashboardViewModel) -> str:
        """Render the dashboard to an HTML string.

        Returns a fallback error page if template rendering fails.
        """
        try:
            template = self.env.get_template("dashboard.html.j2")
            return template.render(vm=view_model)
        except Exception as exc:
            logger.error("Template rendering failed: %s", exc)
            return (
                "<!DOCTYPE html><html><head><title>ReleaseBoard Error</title></head>"
                "<body><h1>Dashboard Rendering Error</h1>"
                "<p>The dashboard template could not be rendered. "
                "Please check the server logs for details.</p></body></html>"
            )

    def render_first_run(self, locale: str = "en", config_path: str = "releaseboard.json") -> str:
        """Render the first-run setup wizard page."""
        from datetime import datetime as _dt

        from releaseboard.integrations.releasepilot.adapter import _detect_capabilities

        rp_caps = _detect_capabilities()
        template = self.env.get_template("first_run.html.j2")
        return template.render(
            locale=locale,
            config_path=config_path,
            version=__version__,
            year=_dt.now().year,
            rp_version=rp_caps.version,
        )

    def render_to_file(self, view_model: DashboardViewModel, output_path: str | Path) -> Path:
        """Render the dashboard and write to a file.

        Creates parent directories if needed.

        Returns:
            The absolute path of the written file.
        """
        html = self.render(view_model)
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html, encoding="utf-8")
        logger.info("Dashboard written to %s", path.absolute())
        return path.absolute()
