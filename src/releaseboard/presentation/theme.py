"""Theme management for the HTML dashboard."""

from __future__ import annotations

from releaseboard.domain.enums import ReadinessStatus, Theme

# Status → CSS color mappings (enterprise-grade, desaturated palette)
STATUS_COLORS: dict[ReadinessStatus, dict[str, str]] = {
    ReadinessStatus.READY: {
        "bg": "#0d7c5f", "fg": "#ffffff",
        "light_bg": "#e6f5f0", "light_fg": "#0d5a45",
    },
    ReadinessStatus.MISSING_BRANCH: {
        "bg": "#c52a2a", "fg": "#ffffff",
        "light_bg": "#fce8e8", "light_fg": "#8b1a1a",
    },
    ReadinessStatus.INVALID_NAMING: {
        "bg": "#b8860b", "fg": "#ffffff",
        "light_bg": "#fdf4e3", "light_fg": "#7a5a08",
    },
    ReadinessStatus.STALE: {
        "bg": "#7c3aed", "fg": "#ffffff",
        "light_bg": "#f0ebfe", "light_fg": "#5521b5",
    },
    ReadinessStatus.INACTIVE: {
        "bg": "#64748b", "fg": "#ffffff",
        "light_bg": "#f1f5f9", "light_fg": "#334155",
    },
    ReadinessStatus.WARNING: {
        "bg": "#d49200", "fg": "#000000",
        "light_bg": "#fef8e7", "light_fg": "#6b4a00",
    },
    ReadinessStatus.ERROR: {
        "bg": "#d93636", "fg": "#ffffff",
        "light_bg": "#fce8e8", "light_fg": "#8b1a1a",
    },
    ReadinessStatus.UNKNOWN: {
        "bg": "#64748b", "fg": "#ffffff",
        "light_bg": "#f8fafc", "light_fg": "#475569",
    },
}

# Chart-friendly color palette (slightly muted for professionalism)
CHART_COLORS: dict[ReadinessStatus, str] = {
    ReadinessStatus.READY: "#0d7c5f",
    ReadinessStatus.MISSING_BRANCH: "#c52a2a",
    ReadinessStatus.INVALID_NAMING: "#b8860b",
    ReadinessStatus.STALE: "#7c3aed",
    ReadinessStatus.INACTIVE: "#64748b",
    ReadinessStatus.WARNING: "#d49200",
    ReadinessStatus.ERROR: "#d93636",
    ReadinessStatus.UNKNOWN: "#94a3b8",
}


def get_theme_default(config_theme: str) -> Theme:
    """Resolve configured theme string to Theme enum."""
    try:
        return Theme(config_theme)
    except ValueError:
        return Theme.SYSTEM
