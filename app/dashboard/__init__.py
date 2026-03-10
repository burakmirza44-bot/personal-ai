"""Dashboard Module - Progress & Health Dashboard.

Comprehensive metrics collection and visualization for the personal-ai system.

Components:
- metrics: Data models for all metric types
- collector: Gather metrics from system components
- renderer: Beautiful terminal display

Usage:
    from app.dashboard import DashboardCollector, DashboardRenderer

    collector = DashboardCollector(repo_root=Path("."))
    report = collector.collect_all()

    renderer = DashboardRenderer()
    print(renderer.render(report))

CLI:
    personal-ai status-dashboard
    personal-ai status-dashboard --refresh  # Live refresh
    personal-ai status-dashboard --json      # Export to JSON
"""

from app.dashboard.metrics import (
    # Core metrics
    SystemMetrics,
    MemoryStoreMetrics,
    BridgeConnectivityMetrics,
    RAGIndexMetrics,
    ExecutionHistoryMetrics,
    ErrorMetrics,
    PlanningMetrics,
    KnowledgeQualityMetrics,
    TrainingMetrics,
    FeedbackLoopMetrics,
    # Report
    ComprehensiveHealthReport,
    HealthStatus,
)
from app.dashboard.collector import DashboardCollector
from app.dashboard.renderer import DashboardRenderer

__all__ = [
    # Metrics
    "SystemMetrics",
    "MemoryStoreMetrics",
    "BridgeConnectivityMetrics",
    "RAGIndexMetrics",
    "ExecutionHistoryMetrics",
    "ErrorMetrics",
    "PlanningMetrics",
    "KnowledgeQualityMetrics",
    "TrainingMetrics",
    "FeedbackLoopMetrics",
    # Report
    "ComprehensiveHealthReport",
    "HealthStatus",
    # Collector & Renderer
    "DashboardCollector",
    "DashboardRenderer",
]