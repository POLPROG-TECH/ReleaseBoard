"""Domain models — pure data, no side effects."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True)
class BranchInfo:
    """Metadata about a single branch in a repository."""

    name: str
    exists: bool
    last_commit_date: datetime | None = None
    last_commit_author: str | None = None
    last_commit_message: str | None = None
    last_commit_sha: str | None = None
    estimated_creation_date: datetime | None = None
    commit_count: int | None = None
    repo_description: str | None = None
    repo_default_branch: str | None = None
    repo_visibility: str | None = None
    repo_owner: str | None = None
    repo_archived: bool | None = None
    repo_web_url: str | None = None
    provider_updated_at: datetime | None = None
    data_source: str | None = None  # "github_api", "git_cli", "local"

    @property
    def age_days(self) -> int | None:
        if self.last_commit_date is None:
            return None
        now = datetime.now(tz=UTC)
        lcd = self.last_commit_date
        if lcd.tzinfo is None:
            lcd = lcd.replace(tzinfo=UTC)
        delta = now - lcd
        return delta.days


@dataclass(frozen=True)
class TagInfo:
    """Metadata about a Git tag relevant to a branch.

    Tags in Git are repository-level objects — they are not scoped to branches.
    ReleaseBoard derives the "latest relevant tag" for an analyzed branch by
    checking which tags have their target commit reachable from the branch head.

    Determination rules:
    - Tags are fetched from the provider API sorted by commit date (newest first).
    - For each candidate tag, the provider checks whether the tag's target commit
      is reachable from the analyzed branch (i.e., the commit exists in the
      branch's ancestry).
    - The first tag that passes the reachability check is chosen as the latest
      relevant tag.
    - "Latest" is determined by the tagged commit's date (committed_date), not
      the tag creation date, since commit date is universally available for both
      lightweight and annotated tags.
    """

    name: str
    target_sha: str
    committed_date: datetime | None = None
    message: str | None = None  # Annotated tag message, None for lightweight tags


@dataclass(frozen=True)
class LayerDefinition:
    """Definition of a repository layer/category."""

    id: str
    label: str
    branch_pattern: str | None = None
    color: str | None = None
    order: int = 0


@dataclass
class RepositoryAnalysis:
    """Complete analysis result for a single repository."""

    name: str
    url: str
    layer: str
    default_branch: str
    expected_pattern: str
    expected_branch_name: str
    status: ReadinessStatus  # noqa: F821 — forward ref resolved at runtime
    branch: BranchInfo | None = None
    naming_valid: bool = False
    is_stale: bool = False
    last_activity: datetime | None = None
    first_activity: datetime | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)
    notes: tuple[str, ...] = field(default_factory=tuple)
    error_message: str | None = None
    error_kind: str | None = None
    error_detail: str | None = None
    latest_tag: TagInfo | None = None

    @property
    def branch_exists(self) -> bool:
        return self.branch is not None and self.branch.exists
