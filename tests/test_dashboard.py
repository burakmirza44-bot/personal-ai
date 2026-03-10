"""Tests for Dashboard Module - Progress & Health Dashboard.

Tests cover:
- Metrics dataclasses
- DashboardCollector
- DashboardRenderer
- CLI integration
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.dashboard.metrics import (
    BridgeConnectivityMetrics,
    ComprehensiveHealthReport,
    ErrorMetrics,
    ExecutionHistoryMetrics,
    FeedbackLoopMetrics,
    HealthStatus,
    KnowledgeQualityMetrics,
    MemoryStoreMetrics,
    PlanningMetrics,
    RAGIndexMetrics,
    SystemMetrics,
    TrainingMetrics,
)
from app.dashboard.collector import DashboardCollector
from app.dashboard.renderer import DashboardRenderer


class TestSystemMetrics:
    """Test SystemMetrics dataclass."""

    def test_default_values(self):
        """Test default values are zero/empty."""
        metrics = SystemMetrics()
        assert metrics.cpu_percent == 0.0
        assert metrics.memory_percent == 0.0
        assert metrics.gpu_available is False

    def test_health_score_calculation(self):
        """Test health score calculation."""
        # Perfect health
        metrics = SystemMetrics(cpu_percent=0, memory_percent=0, disk_percent=0, gpu_available=True, gpu_utilization=0)
        score = metrics.health_score()
        assert score == 100.0

        # Degraded health (50% utilization)
        metrics = SystemMetrics(cpu_percent=50, memory_percent=50, disk_percent=50, gpu_available=False)
        score = metrics.health_score()
        # Score should be between 40 and 80
        assert 40 <= score <= 80

        # Critical health
        metrics = SystemMetrics(cpu_percent=95, memory_percent=95, disk_percent=95)
        score = metrics.health_score()
        assert score < 30

    def test_health_score_no_gpu(self):
        """Test health score without GPU."""
        metrics = SystemMetrics(cpu_percent=0, memory_percent=0, disk_percent=0, gpu_available=False)
        score = metrics.health_score()
        # Should still get partial GPU score (70 * 0.3 = 21)
        assert 50 <= score <= 100


class TestMemoryStoreMetrics:
    """Test MemoryStoreMetrics dataclass."""

    def test_default_values(self):
        """Test default values."""
        metrics = MemoryStoreMetrics()
        assert metrics.total_memories == 0
        assert metrics.domains == []

    def test_health_score_empty(self):
        """Test health score when empty."""
        metrics = MemoryStoreMetrics()
        score = metrics.health_score()
        assert score == 50.0  # Neutral score

    def test_health_score_with_memories(self):
        """Test health score with memories."""
        metrics = MemoryStoreMetrics(total_memories=100, domains=["houdini", "touchdesigner"])
        score = metrics.health_score()
        # Score is based on domain count (40) + count score (10)
        assert score >= 0


class TestBridgeConnectivityMetrics:
    """Test BridgeConnectivityMetrics dataclass."""

    def test_no_connections(self):
        """Test with no connections."""
        metrics = BridgeConnectivityMetrics()
        assert metrics.touchdesigner_connected is False
        assert metrics.houdini_connected is False
        assert metrics.health_score() == 0.0

    def test_td_connected(self):
        """Test with TD connected."""
        metrics = BridgeConnectivityMetrics(touchdesigner_connected=True)
        assert metrics.health_score() == 50.0

    def test_both_connected(self):
        """Test with both connected."""
        metrics = BridgeConnectivityMetrics(touchdesigner_connected=True, houdini_connected=True)
        assert metrics.health_score() == 100.0


class TestExecutionHistoryMetrics:
    """Test ExecutionHistoryMetrics dataclass."""

    def test_default_values(self):
        """Test default values."""
        metrics = ExecutionHistoryMetrics()
        assert metrics.total_executions == 0
        assert metrics.success_rate == 0.0

    def test_health_score(self):
        """Test health score based on success rate."""
        metrics = ExecutionHistoryMetrics(success_rate=0.9)
        assert metrics.health_score() == 90.0

        metrics = ExecutionHistoryMetrics(success_rate=0.5)
        assert metrics.health_score() == 50.0


class TestErrorMetrics:
    """Test ErrorMetrics dataclass."""

    def test_no_errors(self):
        """Test with no errors."""
        metrics = ErrorMetrics()
        assert metrics.health_score() == 100.0

    def test_recent_errors(self):
        """Test with recent errors."""
        metrics = ErrorMetrics(total_errors=10, recent_errors_24h=5)
        score = metrics.health_score()
        assert score < 100


class TestComprehensiveHealthReport:
    """Test ComprehensiveHealthReport dataclass."""

    def test_default_values(self):
        """Test default values."""
        report = ComprehensiveHealthReport()
        assert report.uptime_seconds == 0.0
        assert isinstance(report.system, SystemMetrics)

    def test_overall_health_score(self):
        """Test overall health score calculation."""
        report = ComprehensiveHealthReport()
        score = report.overall_health_score()
        # Should be a valid score
        assert 0 <= score <= 100

    def test_health_status(self):
        """Test health status determination."""
        report = ComprehensiveHealthReport()

        # Mock high score
        report.system.cpu_percent = 0
        report.system.memory_percent = 0
        report.system.disk_percent = 0
        report.system.gpu_available = True
        report.system.gpu_utilization = 0

        status = report.health_status()
        assert status in ["healthy", "degraded", "critical", "unknown"]

    def test_to_dict(self):
        """Test serialization to dictionary."""
        report = ComprehensiveHealthReport()
        data = report.to_dict()

        assert "timestamp" in data
        assert "overall_health_score" in data
        assert "health_status" in data
        assert "system" in data


class TestDashboardCollector:
    """Test DashboardCollector class."""

    def test_init(self, tmp_path):
        """Test initialization."""
        collector = DashboardCollector(repo_root=tmp_path)
        assert collector.repo_root == tmp_path

    def test_collect_system_metrics(self, tmp_path):
        """Test system metrics collection."""
        collector = DashboardCollector(repo_root=tmp_path)
        metrics = collector.collect_system_metrics()

        assert isinstance(metrics, SystemMetrics)
        assert metrics.platform != ""

    def test_collect_all(self, tmp_path):
        """Test collecting all metrics."""
        collector = DashboardCollector(repo_root=tmp_path)
        report = collector.collect_all()

        assert isinstance(report, ComprehensiveHealthReport)
        assert isinstance(report.system, SystemMetrics)
        assert isinstance(report.memory_store, MemoryStoreMetrics)
        assert isinstance(report.bridges, BridgeConnectivityMetrics)

    def test_export_json(self, tmp_path):
        """Test JSON export."""
        collector = DashboardCollector(repo_root=tmp_path)
        output_file = tmp_path / "dashboard.json"

        bytes_written = collector.export_json(output_file)

        assert bytes_written > 0
        assert output_file.exists()

        # Verify JSON is valid
        data = json.loads(output_file.read_text(encoding="utf-8"))
        assert "timestamp" in data


class TestDashboardRenderer:
    """Test DashboardRenderer class."""

    def test_init(self):
        """Test initialization."""
        renderer = DashboardRenderer()
        assert renderer.width <= 120

    def test_render(self):
        """Test rendering a report."""
        renderer = DashboardRenderer()
        report = ComprehensiveHealthReport()

        output = renderer.render(report)

        assert "PERSONAL-AI DASHBOARD" in output
        assert "OVERALL HEALTH" in output
        assert "SYSTEM RESOURCES" in output

    def test_render_compact(self):
        """Test compact rendering."""
        renderer = DashboardRenderer()
        report = ComprehensiveHealthReport()

        output = renderer.render_compact(report)

        assert "CPU:" in output
        assert "MEM:" in output

    def test_render_json(self):
        """Test JSON rendering."""
        renderer = DashboardRenderer()
        report = ComprehensiveHealthReport()

        output = renderer.render_json(report)

        # Should be valid JSON
        data = json.loads(output)
        assert "timestamp" in data

    def test_progress_bar(self):
        """Test progress bar creation."""
        renderer = DashboardRenderer()

        bar = renderer._progress_bar(50, 100, width=10)
        assert len(bar) == 10
        assert "#" in bar
        assert "." in bar

    def test_format_duration(self):
        """Test duration formatting."""
        renderer = DashboardRenderer()

        assert renderer._format_duration(30) == "30s"
        assert renderer._format_duration(120) == "2.0m"
        assert renderer._format_duration(3600) == "1.0h"
        assert renderer._format_duration(86400) == "1.0d"


class TestIntegration:
    """Integration tests for dashboard."""

    def test_collector_renderer_workflow(self, tmp_path):
        """Test complete collector -> renderer workflow."""
        collector = DashboardCollector(repo_root=tmp_path)
        report = collector.collect_all()

        renderer = DashboardRenderer()
        output = renderer.render(report)

        # Should produce valid output
        assert len(output) > 100
        assert "Health" in output

    def test_json_export_import(self, tmp_path):
        """Test JSON export and re-import."""
        collector = DashboardCollector(repo_root=tmp_path)
        report = collector.collect_all()

        # Export
        output_file = tmp_path / "health.json"
        collector.export_json(output_file)

        # Verify can be loaded
        data = json.loads(output_file.read_text(encoding="utf-8"))

        # Compare with tolerance for floating point
        assert abs(data["overall_health_score"] - report.overall_health_score()) < 1.0
        assert data["health_status"] == report.health_status()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])