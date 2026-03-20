"""Tests for staleness detection."""

from datetime import UTC, datetime, timedelta

from releaseboard.analysis.staleness import freshness_label, is_stale


class TestStaleness:

    def test_none_date_is_stale(self):
        assert is_stale(None, threshold_days=14) is True

    def test_recent_commit_is_not_stale(self):
        # GIVEN a commit from 1 day ago
        recent = datetime.now(tz=UTC) - timedelta(days=1)

        # THEN it's not stale
        assert is_stale(recent, threshold_days=14) is False

    def test_old_commit_is_stale(self):
        # GIVEN a commit from 30 days ago
        old = datetime.now(tz=UTC) - timedelta(days=30)

        # THEN it's stale with a 14-day threshold
        assert is_stale(old, threshold_days=14) is True

    def test_exactly_at_threshold_is_not_stale(self):
        # GIVEN a commit exactly at the threshold boundary
        at_threshold = datetime.now(tz=UTC) - timedelta(days=14)

        # THEN it is NOT stale (strictly > threshold, not >=)
        # A branch is stale only after the threshold has fully elapsed.
        assert is_stale(at_threshold, threshold_days=14) is False

    def test_just_before_threshold_is_fresh(self):
        just_before = datetime.now(tz=UTC) - timedelta(days=13, hours=23)
        assert is_stale(just_before, threshold_days=14) is False

    def test_naive_datetime_handled(self):
        # GIVEN a naive datetime (no timezone)
        old = datetime.now() - timedelta(days=30)
        # Should not crash
        assert is_stale(old, threshold_days=14) is True


class TestFreshnessLabel:

    def test_none_returns_unknown(self):
        assert freshness_label(None, 14) == "Unknown"

    def test_today(self):
        now = datetime.now(tz=UTC)
        assert freshness_label(now, 14) == "Today"

    def test_yesterday(self):
        yesterday = datetime.now(tz=UTC) - timedelta(days=1)
        assert freshness_label(yesterday, 14) == "Yesterday"

    def test_days_ago(self):
        five_days = datetime.now(tz=UTC) - timedelta(days=5)
        assert "5 days ago" in freshness_label(five_days, 14)

    def test_stale_label(self):
        old = datetime.now(tz=UTC) - timedelta(days=30)
        label = freshness_label(old, 14)
        assert "Stale" in label
        assert "30" in label
