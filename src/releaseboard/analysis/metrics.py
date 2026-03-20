"""Metrics computation — aggregates analysis results into dashboard metrics."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from releaseboard.domain.enums import ReadinessStatus

if TYPE_CHECKING:
    from releaseboard.domain.models import RepositoryAnalysis


@dataclass
class LayerMetrics:
    """Metrics for a single layer."""

    layer_id: str
    layer_label: str
    total: int = 0
    ready: int = 0
    missing: int = 0
    invalid_naming: int = 0
    stale: int = 0
    error: int = 0
    warning: int = 0
    inactive: int = 0

    @property
    def readiness_pct(self) -> float:
        return (self.ready / self.total * 100) if self.total > 0 else 0.0

    @property
    def problem_count(self) -> int:
        return self.missing + self.invalid_naming + self.stale + self.error + self.warning


@dataclass
class DashboardMetrics:
    """Aggregated metrics for the entire dashboard."""

    total: int = 0
    ready: int = 0
    missing: int = 0
    invalid_naming: int = 0
    stale: int = 0
    error: int = 0
    warning: int = 0
    inactive: int = 0
    unknown: int = 0
    status_counts: dict[str, int] = field(default_factory=dict)
    layer_metrics: dict[str, LayerMetrics] = field(default_factory=dict)
    attention_items: list[RepositoryAnalysis] = field(default_factory=list)

    @property
    def readiness_pct(self) -> float:
        return (self.ready / self.total * 100) if self.total > 0 else 0.0


def compute_dashboard_metrics(
    analyses: list[RepositoryAnalysis],
    layer_labels: dict[str, str] | None = None,
) -> DashboardMetrics:
    """Compute aggregated dashboard metrics from analysis results.

    Args:
        analyses: List of per-repository analysis results.
        layer_labels: Optional mapping of layer_id → display label.

    Returns:
        DashboardMetrics with global and per-layer aggregations.
    """
    if layer_labels is None:
        layer_labels = {}

    metrics = DashboardMetrics()
    metrics.total = len(analyses)

    status_counter: Counter[str] = Counter()
    layer_map: dict[str, LayerMetrics] = {}

    for analysis in analyses:
        status = analysis.status
        status_counter[status.value] += 1

        # Global counters
        match status:
            case ReadinessStatus.READY:
                metrics.ready += 1
            case ReadinessStatus.MISSING_BRANCH:
                metrics.missing += 1
            case ReadinessStatus.INVALID_NAMING:
                metrics.invalid_naming += 1
            case ReadinessStatus.STALE:
                metrics.stale += 1
            case ReadinessStatus.ERROR:
                metrics.error += 1
            case ReadinessStatus.WARNING:
                metrics.warning += 1
            case ReadinessStatus.INACTIVE:
                metrics.inactive += 1
            case ReadinessStatus.UNKNOWN:
                metrics.unknown += 1

        # Per-layer
        layer_id = analysis.layer
        if layer_id not in layer_map:
            layer_map[layer_id] = LayerMetrics(
                layer_id=layer_id,
                layer_label=layer_labels.get(layer_id, layer_id),
            )
        lm = layer_map[layer_id]
        lm.total += 1
        match status:
            case ReadinessStatus.READY:
                lm.ready += 1
            case ReadinessStatus.MISSING_BRANCH:
                lm.missing += 1
            case ReadinessStatus.INVALID_NAMING:
                lm.invalid_naming += 1
            case ReadinessStatus.STALE:
                lm.stale += 1
            case ReadinessStatus.ERROR:
                lm.error += 1
            case ReadinessStatus.WARNING:
                lm.warning += 1
            case ReadinessStatus.INACTIVE:
                lm.inactive += 1

        # Attention items — repos with problems, sorted by severity
        if status.is_problem:
            metrics.attention_items.append(analysis)

    metrics.status_counts = dict(status_counter)
    metrics.layer_metrics = layer_map
    metrics.attention_items.sort(key=lambda a: a.status.severity)

    return metrics
