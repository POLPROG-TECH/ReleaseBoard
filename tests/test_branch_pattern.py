"""Tests for branch pattern matching."""


from releaseboard.analysis.branch_pattern import BranchPatternMatcher


class TestBranchPatternResolver:
    """Tests for resolving branch name templates to concrete names."""

    def test_standard_pattern_resolves_correctly(self):
        # GIVEN a standard release pattern
        matcher = BranchPatternMatcher()

        # WHEN resolved for March 2025
        resolved = matcher.resolve("release/{MM}.{YYYY}", month=3, year=2025)

        # THEN the concrete name is correct
        assert resolved.resolved_name == "release/03.2025"

    def test_reversed_year_month_pattern(self):
        matcher = BranchPatternMatcher()
        resolved = matcher.resolve("release/{YYYY}.{MM}", month=3, year=2025)
        assert resolved.resolved_name == "release/2025.03"

    def test_short_year_pattern(self):
        matcher = BranchPatternMatcher()
        resolved = matcher.resolve("rel/{YY}-{MM}", month=12, year=2025)
        assert resolved.resolved_name == "rel/25-12"

    def test_unpadded_month(self):
        matcher = BranchPatternMatcher()
        resolved = matcher.resolve("release/{M}.{YYYY}", month=3, year=2025)
        assert resolved.resolved_name == "release/3.2025"

    def test_padded_month_for_december(self):
        matcher = BranchPatternMatcher()
        resolved = matcher.resolve("release/{MM}.{YYYY}", month=12, year=2025)
        assert resolved.resolved_name == "release/12.2025"

    def test_custom_prefix(self):
        matcher = BranchPatternMatcher()
        resolved = matcher.resolve("hotfix/{MM}-{YYYY}", month=1, year=2026)
        assert resolved.resolved_name == "hotfix/01-2026"


class TestBranchPatternMatching:
    """Tests for validating actual branch names against patterns."""

    def test_exact_match_returns_true(self):
        # GIVEN a resolved pattern for release/03.2025
        matcher = BranchPatternMatcher()
        resolved = matcher.resolve("release/{MM}.{YYYY}", month=3, year=2025)

        # WHEN checking exact match
        # THEN it matches
        assert matcher.exact_match("release/03.2025", resolved)

    def test_wrong_name_does_not_match(self):
        matcher = BranchPatternMatcher()
        resolved = matcher.resolve("release/{MM}.{YYYY}", month=3, year=2025)
        assert not matcher.exact_match("release/04.2025", resolved)

    def test_regex_match_accepts_valid_format(self):
        matcher = BranchPatternMatcher()
        resolved = matcher.resolve("release/{MM}.{YYYY}", month=3, year=2025)
        # Pattern-level match (any month/year in correct format)
        assert matcher.matches("release/03.2025", resolved)
        assert matcher.matches("release/12.9999", resolved)

    def test_regex_rejects_invalid_format(self):
        matcher = BranchPatternMatcher()
        resolved = matcher.resolve("release/{MM}.{YYYY}", month=3, year=2025)
        assert not matcher.matches("release/3.2025", resolved)  # not zero-padded
        assert not matcher.matches("feature/03.2025", resolved)

    def test_find_matching_filters_branch_list(self):
        # GIVEN a list of branches with some matching
        matcher = BranchPatternMatcher()
        resolved = matcher.resolve("release/{MM}.{YYYY}", month=3, year=2025)
        branches = [
            "main",
            "develop",
            "release/03.2025",
            "release/02.2025",
            "feature/login",
        ]

        # WHEN finding matching branches
        matching = matcher.find_matching(branches, resolved)

        # THEN both release branches match the pattern format
        assert "release/03.2025" in matching
        assert "release/02.2025" in matching
        assert "main" not in matching


class TestTemplateValidation:

    def test_valid_template_has_no_errors(self):
        errors = BranchPatternMatcher.validate_template("release/{MM}.{YYYY}")
        assert errors == []

    def test_unknown_variable_detected(self):
        errors = BranchPatternMatcher.validate_template("release/{VERSION}")
        assert any("Unknown" in e for e in errors)

    def test_no_variables_detected(self):
        errors = BranchPatternMatcher.validate_template("release/static-name")
        assert any("no variables" in e for e in errors)
