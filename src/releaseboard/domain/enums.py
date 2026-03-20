"""Domain enumerations."""

from __future__ import annotations

from enum import StrEnum


class ReadinessStatus(StrEnum):
    """Release readiness status for a repository."""

    READY = "ready"
    MISSING_BRANCH = "missing_branch"
    INVALID_NAMING = "invalid_naming"
    STALE = "stale"
    INACTIVE = "inactive"
    WARNING = "warning"
    ERROR = "error"
    UNKNOWN = "unknown"

    @property
    def label(self) -> str:
        """English fallback label (used by tests and non-localized paths)."""
        return self.localized_label()

    def localized_label(self, locale: str | None = None) -> str:
        """Return a locale-aware label via the i18n catalog."""
        from releaseboard.i18n import t

        return t(f"status.{self.value}", locale=locale)

    @property
    def severity(self) -> int:
        """Lower is better. Used for sorting — worst problems surface first."""
        _severity_map = {
            self.ERROR: 0,
            self.MISSING_BRANCH: 1,
            self.INVALID_NAMING: 2,
            self.STALE: 3,
            self.WARNING: 4,
            self.INACTIVE: 5,
            self.UNKNOWN: 6,
            self.READY: 10,
        }
        return _severity_map.get(self, 100)

    @property
    def is_problem(self) -> bool:
        return self in {
            self.ERROR,
            self.MISSING_BRANCH,
            self.INVALID_NAMING,
            self.STALE,
            self.WARNING,
        }


class Theme(StrEnum):
    LIGHT = "light"
    DARK = "dark"
    MIDNIGHT = "midnight"
    SYSTEM = "system"
