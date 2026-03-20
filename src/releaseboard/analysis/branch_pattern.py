"""Branch pattern matching — resolves and validates release branch names."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ResolvedPattern:
    """A branch pattern resolved to a concrete branch name."""

    template: str
    resolved_name: str
    regex: re.Pattern[str]


class BranchPatternMatcher:
    """Resolves branch name templates and validates actual branch names.

    Supported template variables:
        {YYYY} — 4-digit year (e.g. 2025)
        {YY}   — 2-digit year (e.g. 25)
        {MM}   — zero-padded month (e.g. 03)
        {M}    — month without padding (e.g. 3)
    """

    VARIABLE_MAP = {
        "{YYYY}": (lambda m, y: f"{y:04d}"),
        "{YY}": (lambda m, y: f"{y % 100:02d}"),
        "{MM}": (lambda m, y: f"{m:02d}"),
        "{M}": (lambda m, y: str(m)),
    }

    REGEX_MAP = {
        "{YYYY}": r"\d{4}",
        "{YY}": r"\d{2}",
        "{MM}": r"\d{2}",
        "{M}": r"\d{1,2}",
    }

    def resolve(self, template: str, month: int, year: int) -> ResolvedPattern:
        """Resolve a template to a concrete branch name for the given release.

        Args:
            template: Branch pattern template, e.g. "release/{MM}.{YYYY}"
            month: Release target month (1–12).
            year: Release target year.

        Returns:
            ResolvedPattern with the concrete name and validation regex.

        Raises:
            ValueError: If month or year is out of valid range.
        """
        if not (1 <= month <= 12):
            raise ValueError(f"Invalid release month: {month} (must be 1–12)")
        if year < 2000 or year > 2099:
            raise ValueError(f"Invalid release year: {year} (must be 2000–2099)")

        name = template
        regex_str = re.escape(template)

        for var, resolver in self.VARIABLE_MAP.items():
            name = name.replace(var, resolver(month, year))

        for var, pattern in self.REGEX_MAP.items():
            regex_str = regex_str.replace(re.escape(var), pattern)

        return ResolvedPattern(
            template=template,
            resolved_name=name,
            regex=re.compile(f"^{regex_str}$"),
        )

    def matches(self, branch_name: str, resolved: ResolvedPattern) -> bool:
        """Check if a branch name matches the resolved pattern."""
        return resolved.regex.match(branch_name) is not None

    def exact_match(self, branch_name: str, resolved: ResolvedPattern) -> bool:
        """Check if a branch name is the exact expected name."""
        return branch_name == resolved.resolved_name

    def find_matching(
        self, branch_names: list[str], resolved: ResolvedPattern
    ) -> list[str]:
        """Find all branch names matching the resolved pattern."""
        return [b for b in branch_names if self.matches(b, resolved)]

    @staticmethod
    def validate_template(template: str) -> list[str]:
        """Validate that a template string is well-formed.

        Returns a list of errors (empty if valid).
        """
        errors: list[str] = []
        known_vars = {"{YYYY}", "{YY}", "{MM}", "{M}"}
        found_vars = set(re.findall(r"\{[^}]+}", template))
        unknown = found_vars - known_vars
        if unknown:
            errors.append(f"Unknown variables in template: {unknown}")
        if not found_vars:
            errors.append("Template contains no variables — branch name is static")
        return errors
