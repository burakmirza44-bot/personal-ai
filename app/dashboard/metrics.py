"""Dashboard Metrics - Data models for comprehensive system metrics."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal


@dataclass(slots=True)
class SystemMetrics:
    """System-level resource metrics."""

    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    memory_used_gb: float = 0.0
    memory_total_gb: float = 0.0
    disk_percent: float = 0.0
    disk_used_gb: float = 0.0
    disk_total_gb: float = 0.0
    gpu_available: bool = False
    gpu_name: str = ""
    gpu_memory_used_gb: float = 0.0
    gpu_memory_total_gb: float = 0.0
    gpu_utilization: float = 0.0
    uptime_seconds: float = 0.0
    python_version: str = ""
    platform: str = ""

    def health_score(self) -> float:
        """Calculate overall health score (0-100)."""
        # Weight: CPU 20%, Memory 30%, Disk 20%, GPU 30%
        cpu_score = max(0, 100 - self.cpu_percent)
        mem_score = max(0, 100 - self.memory_percent)
        disk_score = max(0, 100 - self.disk_percent)

        base = (cpu_score * 0.2 + mem_score * 0.3 + disk_score * 0.2)

        if self.gpu_available:
            gpu_score = max(0, 100 - self.gpu_utilization)
            base += gpu_score * 0.3
        else:
            base += 70 * 0.3  # Partial score if no GPU

        return round(base, 1)


@dataclass(slots=True)
class MemoryStoreMetrics:
    """Memory store statistics."""

    long_term_count: int = 0
    short_term_count: int = 0
    total_memories: int = 0
    domains: list[str] = field(default_factory=list)
    oldest_memory_age_days: float = 0.0
    newest_memory_age_days: float = 0.0
    storage_size_kb: float = 0.0

    def health_score(self) -> float:
        """Health based on memory utilization."""
        if self.total_memories == 0:
            return 50.0  # Neutral if empty
        # Good if we have memories distributed
        domain_score = min(100, len(self.domains) * 20)
        count_score = min(100, self.total_memories / 10)
        return round((domain_score + count_score) / 2, 1)


@dataclass(slots=True)
class BridgeConnectivityMetrics:
    """Bridge connectivity status for TD/Houdini."""

    touchdesigner_connected: bool = False
    touchdesigner_host: str = ""
    touchdesigner_port: int = 0
    touchdesigner_last_ping: str = ""

    houdini_connected: bool = False
    houdini_host: str = ""
    houdini_port: int = 0
    houdini_last_ping: str = ""

    def health_score(self) -> float:
        """Health based on connectivity."""
        score = 0.0
        if self.touchdesigner_connected:
            score += 50
        if self.houdini_connected:
            score += 50
        return score


@dataclass(slots=True)
class RAGIndexMetrics:
    """RAG index statistics."""

    total_chunks: int = 0
    total_documents: int = 0
    index_size_mb: float = 0.0
    last_indexed: str = ""
    domains: list[str] = field(default_factory=list)
    chunk_avg_chars: float = 0.0

    def health_score(self) -> float:
        """Health based on index utilization."""
        if self.total_chunks == 0:
            return 30.0
        chunk_score = min(100, self.total_chunks / 2000)
        doc_score = min(100, self.total_documents / 100)
        return round((chunk_score + doc_score) / 2, 1)


@dataclass(slots=True)
class ExecutionHistoryMetrics:
    """Execution history statistics."""

    total_executions: int = 0
    successful_executions: int = 0
    failed_executions: int = 0
    success_rate: float = 0.0
    avg_execution_time_ms: float = 0.0
    last_execution: str = ""
    recent_domains: list[str] = field(default_factory=list)

    def health_score(self) -> float:
        """Health based on success rate."""
        return round(self.success_rate * 100, 1)


@dataclass(slots=True)
class ErrorMetrics:
    """Error tracking metrics."""

    total_errors: int = 0
    recent_errors_24h: int = 0
    unique_error_types: int = 0
    most_common_error: str = ""
    error_rate_per_hour: float = 0.0
    resolved_errors: int = 0
    pending_errors: int = 0
    top_error_types: list[dict[str, Any]] = field(default_factory=list)

    def health_score(self) -> float:
        """Health inverse to error rate."""
        if self.total_errors == 0:
            return 100.0
        # Penalize for recent errors
        penalty = min(100, self.recent_errors_24h * 10)
        return max(0, 100 - penalty)


@dataclass(slots=True)
class PlanningMetrics:
    """Planning and goal tracking metrics."""

    active_goals: int = 0
    completed_goals: int = 0
    abandoned_goals: int = 0
    goal_success_rate: float = 0.0
    avg_plan_steps: float = 0.0
    plans_in_progress: int = 0
    avg_plan_completion: float = 0.0

    def health_score(self) -> float:
        """Health based on goal success."""
        return round(self.goal_success_rate * 100, 1)


@dataclass(slots=True)
class KnowledgeQualityMetrics:
    """Knowledge base quality metrics."""

    total_patterns: int = 0
    verified_patterns: int = 0
    pattern_success_rate: float = 0.0
    domain_coverage: dict[str, int] = field(default_factory=dict)
    avg_pattern_usage: float = 0.0
    top_patterns: list[dict[str, Any]] = field(default_factory=list)

    def health_score(self) -> float:
        """Health based on knowledge quality."""
        if self.total_patterns == 0:
            return 40.0
        verification_rate = self.verified_patterns / self.total_patterns
        return round((verification_rate * 50 + self.pattern_success_rate * 50), 1)


@dataclass(slots=True)
class TrainingMetrics:
    """Training and fine-tuning metrics."""

    training_examples_total: int = 0
    training_examples_domain: dict[str, int] = field(default_factory=dict)
    models_trained: int = 0
    active_model_id: str = ""
    best_eval_score: float = 0.0
    last_training: str = ""
    training_pending: bool = False

    def health_score(self) -> float:
        """Health based on training data availability."""
        if self.training_examples_total == 0:
            return 30.0
        data_score = min(100, self.training_examples_total / 1000)
        model_score = 50 if self.active_model_id else 0
        return round((data_score + model_score) / 2, 1)


@dataclass(slots=True)
class FeedbackLoopMetrics:
    """Feedback loop metrics."""

    sessions_total: int = 0
    iterations_total: int = 0
    avg_score: float = 0.0
    positive_count: int = 0
    correction_count: int = 0
    negative_count: int = 0
    score_trend: str = "stable"  # improving, declining, stable
    last_session: str = ""
    examples_collected: int = 0

    def health_score(self) -> float:
        """Health based on feedback quality."""
        if self.iterations_total == 0:
            return 50.0
        quality_score = self.avg_score * 100
        trend_bonus = 10 if self.score_trend == "improving" else 0
        return min(100, round(quality_score + trend_bonus, 1))


HealthStatus = Literal["healthy", "degraded", "critical", "unknown"]


@dataclass(slots=True)
class ComprehensiveHealthReport:
    """Comprehensive health report combining all metrics."""

    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    uptime_seconds: float = 0.0

    # Individual metrics
    system: SystemMetrics = field(default_factory=SystemMetrics)
    memory_store: MemoryStoreMetrics = field(default_factory=MemoryStoreMetrics)
    bridges: BridgeConnectivityMetrics = field(default_factory=BridgeConnectivityMetrics)
    rag_index: RAGIndexMetrics = field(default_factory=RAGIndexMetrics)
    execution: ExecutionHistoryMetrics = field(default_factory=ExecutionHistoryMetrics)
    errors: ErrorMetrics = field(default_factory=ErrorMetrics)
    planning: PlanningMetrics = field(default_factory=PlanningMetrics)
    knowledge: KnowledgeQualityMetrics = field(default_factory=KnowledgeQualityMetrics)
    training: TrainingMetrics = field(default_factory=TrainingMetrics)
    feedback_loop: FeedbackLoopMetrics = field(default_factory=FeedbackLoopMetrics)

    def overall_health_score(self) -> float:
        """Calculate weighted overall health score."""
        weights = {
            "system": 0.15,
            "memory_store": 0.10,
            "bridges": 0.15,
            "rag_index": 0.10,
            "execution": 0.15,
            "errors": 0.10,
            "planning": 0.05,
            "knowledge": 0.10,
            "training": 0.05,
            "feedback_loop": 0.05,
        }

        total = 0.0
        for name, weight in weights.items():
            metric = getattr(self, name)
            if hasattr(metric, "health_score"):
                total += metric.health_score() * weight

        return round(total, 1)

    def health_status(self) -> HealthStatus:
        """Determine overall health status."""
        score = self.overall_health_score()
        if score >= 80:
            return "healthy"
        elif score >= 50:
            return "degraded"
        elif score > 0:
            return "critical"
        return "unknown"

    def status_emoji(self) -> str:
        """Return emoji for current status."""
        status = self.health_status()
        return {
            "healthy": "[OK]",
            "degraded": "[!!]",
            "critical": "[XX]",
            "unknown": "[??]",
        }.get(status, "[??]")

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "timestamp": self.timestamp,
            "uptime_seconds": self.uptime_seconds,
            "overall_health_score": self.overall_health_score(),
            "health_status": self.health_status(),
            "system": {
                "cpu_percent": self.system.cpu_percent,
                "memory_percent": self.system.memory_percent,
                "disk_percent": self.system.disk_percent,
                "gpu_available": self.system.gpu_available,
                "health_score": self.system.health_score(),
            },
            "memory_store": {
                "total_memories": self.memory_store.total_memories,
                "health_score": self.memory_store.health_score(),
            },
            "bridges": {
                "touchdesigner_connected": self.bridges.touchdesigner_connected,
                "houdini_connected": self.bridges.houdini_connected,
                "health_score": self.bridges.health_score(),
            },
            "rag_index": {
                "total_chunks": self.rag_index.total_chunks,
                "health_score": self.rag_index.health_score(),
            },
            "execution": {
                "total_executions": self.execution.total_executions,
                "success_rate": self.execution.success_rate,
                "health_score": self.execution.health_score(),
            },
            "errors": {
                "total_errors": self.errors.total_errors,
                "recent_errors_24h": self.errors.recent_errors_24h,
                "health_score": self.errors.health_score(),
            },
            "planning": {
                "active_goals": self.planning.active_goals,
                "goal_success_rate": self.planning.goal_success_rate,
                "health_score": self.planning.health_score(),
            },
            "knowledge": {
                "total_patterns": self.knowledge.total_patterns,
                "health_score": self.knowledge.health_score(),
            },
            "training": {
                "training_examples_total": self.training.training_examples_total,
                "active_model_id": self.training.active_model_id,
                "health_score": self.training.health_score(),
            },
            "feedback_loop": {
                "sessions_total": self.feedback_loop.sessions_total,
                "avg_score": self.feedback_loop.avg_score,
                "health_score": self.feedback_loop.health_score(),
            },
        }