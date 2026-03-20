"""Tests for theme handling."""

from releaseboard.domain.enums import ReadinessStatus, Theme
from releaseboard.presentation.theme import (
    CHART_COLORS,
    STATUS_COLORS,
    get_theme_default,
)


class TestTheme:

    def test_valid_theme_strings(self):
        assert get_theme_default("light") == Theme.LIGHT
        assert get_theme_default("dark") == Theme.DARK
        assert get_theme_default("midnight") == Theme.MIDNIGHT
        assert get_theme_default("system") == Theme.SYSTEM

    def test_invalid_theme_falls_back_to_system(self):
        assert get_theme_default("rainbow") == Theme.SYSTEM
        assert get_theme_default("") == Theme.SYSTEM

    def test_all_statuses_have_colors(self):
        for status in ReadinessStatus:
            assert status in STATUS_COLORS, f"Missing color for {status}"
            assert status in CHART_COLORS, f"Missing chart color for {status}"

    def test_status_colors_have_required_keys(self):
        for _status, colors in STATUS_COLORS.items():
            assert "bg" in colors
            assert "fg" in colors
            assert "light_bg" in colors
            assert "light_fg" in colors
