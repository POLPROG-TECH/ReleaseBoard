"""Dashboard renderer — generates the HTML dashboard file."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import TYPE_CHECKING

import jinja2

from releaseboard import __version__
from releaseboard.shared.logging import get_logger

if TYPE_CHECKING:
    from releaseboard.presentation.view_models import DashboardViewModel

logger = get_logger("renderer")

_TEMPLATE_DIR = Path(__file__).parent / "templates"


def _js_string(value: str) -> str:
    """Escape a string for safe embedding inside a JS string literal.

    Returns a JSON-encoded string (with surrounding quotes).
    """
    return json.dumps(str(value) if value else "")


def _snake_to_camel(name: str) -> str:
    """Convert snake_case to camelCase: 'last_activity' -> 'lastActivity'."""
    parts = name.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def _repo_data_json(repos: list) -> str:
    """Serialize all repos to a JSON object keyed by name.

    Produces a safe JavaScript object literal — all values are properly
    JSON-encoded so special characters (backslash, backtick, newlines,
    quotes) in commit messages, descriptions, etc. cannot break the parser.
    Keys are converted from snake_case to camelCase to match existing JS code.
    """
    data = {}
    for repo in repos:
        d = dataclasses.asdict(repo)
        camel = {_snake_to_camel(k): v for k, v in d.items()}
        data[d["name"]] = camel
    return json.dumps(data, ensure_ascii=False, default=str)


class DashboardRenderer:
    """Renders the HTML dashboard from a DashboardViewModel."""

    def __init__(self) -> None:
        self.env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(_TEMPLATE_DIR)),
            autoescape=jinja2.select_autoescape(["html"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.env.filters["js_string"] = _js_string
        self.env.globals["repo_data_json"] = _repo_data_json

    def render(self, view_model: DashboardViewModel) -> str:
        """Render the dashboard to an HTML string.

        Returns a fallback error page if template rendering fails.
        """
        try:
            template = self.env.get_template("dashboard.html.j2")
            return template.render(vm=view_model)
        except Exception as exc:
            logger.error("Template rendering failed: %s", exc)
            from releaseboard.i18n import get_locale, t

            _loc = get_locale()
            _title = t("error.page_title", locale=_loc) or "ReleaseBoard Error"
            _heading = t("error.dashboard_rendering", locale=_loc) or "Dashboard Rendering Error"
            _body = (
                t("error.check_logs", locale=_loc)
                or "The dashboard template could not be rendered."
                " Please check the server logs for details."
            )
            return (
                f"<!DOCTYPE html><html><head><title>{_title}</title></head>"
                f"<body><h1>{_heading}</h1>"
                f"<p>{_body}</p></body></html>"
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
