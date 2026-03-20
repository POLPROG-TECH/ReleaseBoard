"""Staleness detection for branches."""

from __future__ import annotations

from datetime import UTC, datetime


def is_stale(last_commit_date: datetime | None, threshold_days: int) -> bool:
    """Determine whether a branch is stale based on its last commit date.

    Args:
        last_commit_date: Timestamp of the most recent commit on the branch.
        threshold_days: Number of days after which a branch is considered stale.

    Returns:
        True if the branch is stale or has no commit date.
    """
    if last_commit_date is None:
        return True
    now = datetime.now(tz=UTC)
    if last_commit_date.tzinfo is None:
        last_commit_date = last_commit_date.replace(tzinfo=UTC)
    delta = now - last_commit_date
    # Future dates are treated as fresh (not stale) — the caller should
    # handle clock-skew anomalies separately.  Negative deltas must not
    # accidentally evaluate to "stale".
    if delta.days < 0:
        return False
    return delta.days > threshold_days


def freshness_label(
    last_commit_date: datetime | None,
    threshold_days: int,
    locale: str | None = None,
) -> str:
    """Return a human-readable, locale-aware freshness label."""
    from releaseboard.i18n import t

    if last_commit_date is None:
        return t("freshness.unknown", locale=locale)
    now = datetime.now(tz=UTC)
    if last_commit_date.tzinfo is None:
        last_commit_date = last_commit_date.replace(tzinfo=UTC)
    days = (now - last_commit_date).days
    if days < 0:
        return t("freshness.today", locale=locale)
    if days == 0:
        return t("freshness.today", locale=locale)
    if days == 1:
        return t("freshness.yesterday", locale=locale)
    if days <= threshold_days:
        return t("freshness.days_ago", locale=locale, days=days)
    return t("freshness.stale", locale=locale, days=days)
