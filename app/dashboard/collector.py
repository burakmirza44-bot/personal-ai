"""Dashboard Collector - Gather metrics from all system components.

Collects metrics from:
- System resources (CPU, memory, disk, GPU)
- Memory store
- Bridge connectivity (TD/Houdini)
- RAG index
- Execution history
- Error memory
- Planning/goals
- Knowledge base
- Training data
- Feedback loop
"""

from __future__ import annotations

import json
import logging
import os
import platform
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app.dashboard.metrics import (
    BridgeConnectivityMetrics,
    ComprehensiveHealthReport,
    ErrorMetrics,
    ExecutionHistoryMetrics,
    FeedbackLoopMetrics,
    KnowledgeQualityMetrics,
    MemoryStoreMetrics,
    PlanningMetrics,
    RAGIndexMetrics,
    SystemMetrics,
    TrainingMetrics,
)

logger = logging.getLogger(__name__)


class DashboardCollector:
    """Collect comprehensive system metrics.

    Usage:
        collector = DashboardCollector(repo_root=Path("."))
        report = collector.collect_all()
        print(report.overall_health_score())
    """

    def __init__(
        self,
        repo_root: Path | None = None,
        data_dir: Path | None = None,
    ) -> None:
        """Initialize collector.

        Args:
            repo_root: Repository root path
            data_dir: Data directory path
        """
        self.repo_root = repo_root or Path.cwd()
        self.data_dir = data_dir or self.repo_root / "data"
        self._start_time = time.time()

    def collect_all(self) -> ComprehensiveHealthReport:
        """Collect all metrics into a comprehensive report."""
        report = ComprehensiveHealthReport()
        report.uptime_seconds = time.time() - self._start_time

        # Collect each metric type
        report.system = self.collect_system_metrics()
        report.memory_store = self.collect_memory_store_metrics()
        report.bridges = self.collect_bridge_metrics()
        report.rag_index = self.collect_rag_metrics()
        report.execution = self.collect_execution_metrics()
        report.errors = self.collect_error_metrics()
        report.planning = self.collect_planning_metrics()
        report.knowledge = self.collect_knowledge_metrics()
        report.training = self.collect_training_metrics()
        report.feedback_loop = self.collect_feedback_loop_metrics()

        return report

    def collect_system_metrics(self) -> SystemMetrics:
        """Collect system resource metrics."""
        metrics = SystemMetrics()

        try:
            import psutil

            metrics.cpu_percent = psutil.cpu_percent(interval=0.1) or 0.0

            mem = psutil.virtual_memory()
            metrics.memory_percent = mem.percent
            metrics.memory_used_gb = mem.used / (1024**3)
            metrics.memory_total_gb = mem.total / (1024**3)

            disk = psutil.disk_usage(str(self.repo_root))
            metrics.disk_percent = disk.percent
            metrics.disk_used_gb = disk.used / (1024**3)
            metrics.disk_total_gb = disk.total / (1024**3)

        except ImportError:
            # psutil not available, use basic metrics
            metrics.cpu_percent = 0.0
            metrics.memory_percent = 0.0
        except Exception as e:
            logger.debug(f"Failed to collect system metrics: {e}")

        # GPU metrics
        try:
            import subprocess

            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.used,memory.total,utilization.gpu", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                parts = result.stdout.strip().split(", ")
                if len(parts) >= 4:
                    metrics.gpu_available = True
                    metrics.gpu_name = parts[0].strip()
                    metrics.gpu_memory_used_gb = float(parts[1]) / 1024
                    metrics.gpu_memory_total_gb = float(parts[2]) / 1024
                    metrics.gpu_utilization = float(parts[3])
        except Exception:
            metrics.gpu_available = False

        # Platform info
        metrics.python_version = sys.version.split()[0]
        metrics.platform = f"{platform.system()} {platform.release()}"

        return metrics

    def collect_memory_store_metrics(self) -> MemoryStoreMetrics:
        """Collect memory store statistics."""
        metrics = MemoryStoreMetrics()

        try:
            from app.core.memory_store import build_default_memory_store

            store = build_default_memory_store(self.repo_root)
            long_term = store.list_long_term(limit=10000)
            short_term = store.list_short_term(limit=10000)

            metrics.long_term_count = len(long_term)
            metrics.short_term_count = len(short_term)
            metrics.total_memories = metrics.long_term_count + metrics.short_term_count

            # Extract domains
            domains = set()
            for item in long_term + short_term:
                domain = item.get("domain", "general")
                if domain:
                    domains.add(domain)
            metrics.domains = list(domains)

            # Storage size
            memory_path = self.repo_root / "memory" / "memory_store.json"
            if memory_path.exists():
                metrics.storage_size_kb = memory_path.stat().st_size / 1024

        except Exception as e:
            logger.debug(f"Failed to collect memory store metrics: {e}")

        return metrics

    def collect_bridge_metrics(self) -> BridgeConnectivityMetrics:
        """Collect bridge connectivity status."""
        metrics = BridgeConnectivityMetrics()

        # Check TouchDesigner bridge
        try:
            from app.domains.touchdesigner.td_live_client import TDLiveClient

            # Try to get config
            config_path = self.repo_root / "config" / "td_bridge.json"
            if config_path.exists():
                config = json.loads(config_path.read_text(encoding="utf-8"))
                metrics.touchdesigner_host = config.get("host", "localhost")
                metrics.touchdesigner_port = config.get("port", 9980)

                # Try ping
                client = TDLiveClient(
                    host=metrics.touchdesigner_host,
                    port=metrics.touchdesigner_port,
                )
                metrics.touchdesigner_connected = client.ping(timeout=2)
                metrics.touchdesigner_last_ping = datetime.utcnow().isoformat()

        except Exception as e:
            logger.debug(f"TD bridge check failed: {e}")
            metrics.touchdesigner_connected = False

        # Check Houdini bridge
        try:
            from app.domains.houdini.houdini_live_client import HoudiniLiveFileClient

            config_path = self.repo_root / "config" / "houdini_bridge.json"
            if config_path.exists():
                config = json.loads(config_path.read_text(encoding="utf-8"))
                metrics.houdini_host = config.get("host", "localhost")
                metrics.houdini_port = config.get("port", 9876)

                client = HoudiniLiveFileClient()
                metrics.houdini_connected = client.ping(timeout=2)
                metrics.houdini_last_ping = datetime.utcnow().isoformat()

        except Exception as e:
            logger.debug(f"Houdini bridge check failed: {e}")
            metrics.houdini_connected = False

        return metrics

    def collect_rag_metrics(self) -> RAGIndexMetrics:
        """Collect RAG index statistics."""
        metrics = RAGIndexMetrics()

        try:
            # Check for RAG index files
            rag_dir = self.repo_root / "data" / "rag"
            if rag_dir.exists():
                # Count chunks
                chunks_file = rag_dir / "chunks.jsonl"
                if chunks_file.exists():
                    with open(chunks_file, "r", encoding="utf-8") as f:
                        metrics.total_chunks = sum(1 for _ in f)

                # Index size
                for f in rag_dir.glob("*"):
                    if f.is_file():
                        metrics.index_size_mb += f.stat().st_size / (1024**2)

                # Last indexed
                meta_file = rag_dir / "metadata.json"
                if meta_file.exists():
                    meta = json.loads(meta_file.read_text(encoding="utf-8"))
                    metrics.last_indexed = meta.get("last_indexed", "")
                    metrics.total_documents = meta.get("total_documents", 0)
                    metrics.domains = meta.get("domains", [])

        except Exception as e:
            logger.debug(f"Failed to collect RAG metrics: {e}")

        return metrics

    def collect_execution_metrics(self) -> ExecutionHistoryMetrics:
        """Collect execution history statistics."""
        metrics = ExecutionHistoryMetrics()

        try:
            # Check execution log
            exec_log = self.repo_root / "logs" / "execution_history.jsonl"
            if exec_log.exists():
                executions = []
                with open(exec_log, "r", encoding="utf-8") as f:
                    for line in f:
                        try:
                            executions.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue

                metrics.total_executions = len(executions)

                # Count successes and failures
                for exec_item in executions[-1000:]:  # Last 1000
                    if exec_item.get("success"):
                        metrics.successful_executions += 1
                    else:
                        metrics.failed_executions += 1

                    domain = exec_item.get("domain", "")
                    if domain and domain not in metrics.recent_domains:
                        metrics.recent_domains.append(domain)

                if metrics.total_executions > 0:
                    metrics.success_rate = metrics.successful_executions / metrics.total_executions

                if executions:
                    metrics.last_execution = executions[-1].get("timestamp", "")

        except Exception as e:
            logger.debug(f"Failed to collect execution metrics: {e}")

        return metrics

    def collect_error_metrics(self) -> ErrorMetrics:
        """Collect error statistics."""
        metrics = ErrorMetrics()

        try:
            from app.learning.error_memory import build_default_error_memory_store

            store = build_default_error_memory_store(self.repo_root)
            store.load()

            errors = store._items
            metrics.total_errors = len(errors)

            # Recent errors (last 24h)
            now = datetime.utcnow()
            cutoff = now - timedelta(hours=24)

            error_types: dict[str, int] = {}
            for err in errors:
                # Check if recent
                try:
                    err_time = datetime.fromisoformat(err.created_at.replace("Z", ""))
                    if err_time > cutoff:
                        metrics.recent_errors_24h += 1
                except Exception:
                    pass

                # Count error types
                etype = err.error_type or "unknown"
                error_types[etype] = error_types.get(etype, 0) + 1

            metrics.unique_error_types = len(error_types)

            # Most common error
            if error_types:
                metrics.most_common_error = max(error_types, key=error_types.get)
                metrics.top_error_types = [
                    {"type": k, "count": v}
                    for k, v in sorted(error_types.items(), key=lambda x: -x[1])[:5]
                ]

            # Error rate
            if metrics.total_errors > 0:
                hours_running = max(1, time.time() - self._start_time) / 3600
                metrics.error_rate_per_hour = metrics.recent_errors_24h / min(24, hours_running)

        except Exception as e:
            logger.debug(f"Failed to collect error metrics: {e}")

        return metrics

    def collect_planning_metrics(self) -> PlanningMetrics:
        """Collect planning and goal statistics."""
        metrics = PlanningMetrics()

        try:
            # Check goal store
            goal_file = self.repo_root / "data" / "goals" / "active_goals.json"
            if goal_file.exists():
                goals = json.loads(goal_file.read_text(encoding="utf-8"))

                for goal in goals:
                    status = goal.get("status", "")
                    if status == "active":
                        metrics.active_goals += 1
                    elif status == "completed":
                        metrics.completed_goals += 1
                    elif status == "abandoned":
                        metrics.abandoned_goals += 1

                total = metrics.active_goals + metrics.completed_goals + metrics.abandoned_goals
                if total > 0:
                    metrics.goal_success_rate = metrics.completed_goals / total

            # Check plans
            plans_file = self.repo_root / "data" / "plans" / "active_plans.json"
            if plans_file.exists():
                plans = json.loads(plans_file.read_text(encoding="utf-8"))
                metrics.plans_in_progress = len([p for p in plans if p.get("status") == "in_progress"])

                # Average plan completion
                completions = [p.get("completion", 0) for p in plans if "completion" in p]
                if completions:
                    metrics.avg_plan_completion = sum(completions) / len(completions)

        except Exception as e:
            logger.debug(f"Failed to collect planning metrics: {e}")

        return metrics

    def collect_knowledge_metrics(self) -> KnowledgeQualityMetrics:
        """Collect knowledge base statistics."""
        metrics = KnowledgeQualityMetrics()

        try:
            from app.learning.success_patterns import build_default_success_pattern_store

            store = build_default_success_pattern_store(self.repo_root)
            store.load()

            patterns = store._patterns
            metrics.total_patterns = len(patterns)

            # Domain coverage
            domain_counts: dict[str, int] = {}
            total_usage = 0
            verified = 0

            for pattern in patterns:
                domain = pattern.domain or "general"
                domain_counts[domain] = domain_counts.get(domain, 0) + 1
                total_usage += pattern.usage_count
                if pattern.success_rate > 0.5:
                    verified += 1

            metrics.domain_coverage = domain_counts
            metrics.verified_patterns = verified
            metrics.pattern_success_rate = sum(p.success_rate for p in patterns) / len(patterns) if patterns else 0

            if metrics.total_patterns > 0:
                metrics.avg_pattern_usage = total_usage / metrics.total_patterns

            # Top patterns
            sorted_patterns = sorted(patterns, key=lambda p: p.success_rate, reverse=True)[:5]
            metrics.top_patterns = [
                {
                    "id": p.pattern_id,
                    "domain": p.domain,
                    "success_rate": p.success_rate,
                    "description": p.fix_description[:50],
                }
                for p in sorted_patterns
            ]

        except Exception as e:
            logger.debug(f"Failed to collect knowledge metrics: {e}")

        return metrics

    def collect_training_metrics(self) -> TrainingMetrics:
        """Collect training data statistics."""
        metrics = TrainingMetrics()

        try:
            from app.learning.model_registry import ModelRegistry

            # Check registry
            registry_path = self.repo_root / "models" / "registry.json"
            if registry_path.exists():
                registry = ModelRegistry(registry_path)
                data = registry.load()

                metrics.active_model_id = data.get("active_model_id", "")
                metrics.models_trained = len(data.get("entries", []))

                # Best eval score
                entries = data.get("entries", [])
                if entries:
                    scores = [e.get("eval_score", 0) for e in entries]
                    metrics.best_eval_score = max(scores) if scores else 0

            # Count training examples
            train_dir = self.repo_root / "data" / "training"
            if train_dir.exists():
                total = 0
                domain_counts: dict[str, int] = {}

                for f in train_dir.glob("**/*.jsonl"):
                    domain = f.parent.name
                    count = 0
                    with open(f, "r", encoding="utf-8") as fp:
                        count = sum(1 for _ in fp)
                    total += count
                    domain_counts[domain] = domain_counts.get(domain, 0) + count

                metrics.training_examples_total = total
                metrics.training_examples_domain = domain_counts

            # Check finetune manifest
            manifest_path = self.repo_root / "data" / "finetune_manifest.json"
            if manifest_path.exists():
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                metrics.last_training = manifest.get("last_training", "")
                metrics.training_pending = manifest.get("pending", False)

        except Exception as e:
            logger.debug(f"Failed to collect training metrics: {e}")

        return metrics

    def collect_feedback_loop_metrics(self) -> FeedbackLoopMetrics:
        """Collect feedback loop statistics."""
        metrics = FeedbackLoopMetrics()

        try:
            from feedback.memory.feedback_store import FeedbackStore

            store = FeedbackStore(db_path=self.repo_root / "data" / "feedback" / "feedback.db")
            summary = store.get_summary()

            metrics.iterations_total = summary.get("total_records", 0)
            metrics.avg_score = summary.get("average_score", 0.0)
            metrics.positive_count = summary.get("positive_count", 0)
            metrics.correction_count = summary.get("correction_count", 0)
            metrics.negative_count = summary.get("negative_count", 0)
            metrics.sessions_total = 1  # Placeholder

            # Determine trend
            recent = store.get_recent(limit=50)
            if len(recent) >= 10:
                recent_scores = [r.score for r in recent]
                early_avg = sum(recent_scores[:10]) / 10
                late_avg = sum(recent_scores[-10:]) / 10
                if late_avg > early_avg + 0.05:
                    metrics.score_trend = "improving"
                elif late_avg < early_avg - 0.05:
                    metrics.score_trend = "declining"
                else:
                    metrics.score_trend = "stable"

            # Check for collected examples
            collected_path = self.repo_root / "data" / "feedback_collected"
            if collected_path.exists():
                metrics.examples_collected = sum(1 for _ in collected_path.glob("*.jsonl"))

        except Exception as e:
            logger.debug(f"Failed to collect feedback loop metrics: {e}")

        return metrics

    def export_json(self, output_path: Path | str) -> int:
        """Export metrics to JSON file.

        Args:
            output_path: Output file path

        Returns:
            Number of bytes written
        """
        report = self.collect_all()
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        content = json.dumps(report.to_dict(), indent=2, ensure_ascii=False)
        output.write_text(content, encoding="utf-8")

        return len(content)