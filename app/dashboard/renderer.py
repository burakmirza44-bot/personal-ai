"""Dashboard Renderer - Beautiful terminal display for metrics.

Renders comprehensive health reports with:
- Color-coded status indicators
- Progress bars
- Sparklines
- Formatted tables
"""

from __future__ import annotations

import sys
from datetime import datetime
from typing import Any

from app.dashboard.metrics import (
    ComprehensiveHealthReport,
    HealthStatus,
)


class DashboardRenderer:
    """Render dashboard metrics to terminal.

    Usage:
        renderer = DashboardRenderer()
        report = collector.collect_all()
        renderer.render(report)
    """

    # ANSI color codes
    COLORS = {
        "reset": "\033[0m",
        "bold": "\033[1m",
        "dim": "\033[2m",
        "red": "\033[91m",
        "green": "\033[92m",
        "yellow": "\033[93m",
        "blue": "\033[94m",
        "magenta": "\033[95m",
        "cyan": "\033[96m",
        "white": "\033[97m",
        "bg_red": "\033[41m",
        "bg_green": "\033[42m",
        "bg_yellow": "\033[43m",
    }

    # Unicode symbols (ASCII-safe alternatives)
    SYMBOLS = {
        "ok": "[OK]",
        "warn": "[!!]",
        "error": "[XX]",
        "info": "[--]",
        "arrow": "->",
        "bullet": "*",
        "corner": "+",
        "horizontal": "-",
        "vertical": "|",
        "block": "#",
        "empty": ".",
    }

    def __init__(self, use_color: bool = True, width: int = 80) -> None:
        """Initialize renderer.

        Args:
            use_color: Whether to use ANSI colors
            width: Terminal width
        """
        self.use_color = use_color and self._supports_color()
        self.width = min(width, 120)

    def _supports_color(self) -> bool:
        """Check if terminal supports color."""
        # Check for Windows
        if sys.platform == "win32":
            return os.environ.get("ANSICON") is not None or "WT_SESSION" in os.environ
        # Check for TTY
        return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

    def _color(self, text: str, color: str) -> str:
        """Apply color to text."""
        if not self.use_color:
            return text
        code = self.COLORS.get(color, "")
        reset = self.COLORS["reset"]
        return f"{code}{text}{reset}"

    def _status_color(self, status: HealthStatus) -> str:
        """Get color for health status."""
        return {
            "healthy": "green",
            "degraded": "yellow",
            "critical": "red",
            "unknown": "dim",
        }.get(status, "white")

    def _status_symbol(self, status: HealthStatus) -> str:
        """Get symbol for health status."""
        return {
            "healthy": self.SYMBOLS["ok"],
            "degraded": self.SYMBOLS["warn"],
            "critical": self.SYMBOLS["error"],
            "unknown": self.SYMBOLS["info"],
        }.get(status, self.SYMBOLS["info"])

    def _progress_bar(self, value: float, max_value: float = 100, width: int = 20) -> str:
        """Create a progress bar."""
        if max_value <= 0:
            return self.SYMBOLS["empty"] * width

        ratio = min(1.0, max(0.0, value / max_value))
        filled = int(ratio * width)
        empty = width - filled

        bar = self.SYMBOLS["block"] * filled + self.SYMBOLS["empty"] * empty
        return bar

    def _sparkline(self, values: list[float], width: int = 10) -> str:
        """Create a simple sparkline."""
        if not values:
            return "." * width

        # Normalize values
        min_v, max_v = min(values), max(values)
        if max_v == min_v:
            normalized = [0.5] * len(values)
        else:
            normalized = [(v - min_v) / (max_v - min_v) for v in values]

        # Sample to width
        step = max(1, len(normalized) // width)
        sampled = normalized[::step][:width]

        # Convert to bars
        chars = ["_", "-", "="]
        return "".join(chars[min(2, int(v * 3))] for v in sampled)

    def _format_bytes(self, value: float, unit: str = "GB") -> str:
        """Format bytes with unit."""
        if value < 0.1:
            return f"{value * 1000:.0f} MB"
        return f"{value:.1f} {unit}"

    def _format_duration(self, seconds: float) -> str:
        """Format duration in human readable form."""
        if seconds < 60:
            return f"{seconds:.0f}s"
        elif seconds < 3600:
            return f"{seconds / 60:.1f}m"
        elif seconds < 86400:
            return f"{seconds / 3600:.1f}h"
        return f"{seconds / 86400:.1f}d"

    def render(self, report: ComprehensiveHealthReport) -> str:
        """Render complete dashboard."""
        lines: list[str] = []

        # Header
        lines.append(self._render_header(report))

        # Overall health
        lines.append(self._render_overall_health(report))

        # System metrics
        lines.append(self._render_system_metrics(report))

        # Memory and storage
        lines.append(self._render_memory_metrics(report))

        # Bridges
        lines.append(self._render_bridge_metrics(report))

        # Execution
        lines.append(self._render_execution_metrics(report))

        # Errors
        lines.append(self._render_error_metrics(report))

        # Knowledge and training
        lines.append(self._render_knowledge_metrics(report))

        # Feedback loop
        lines.append(self._render_feedback_metrics(report))

        # Footer
        lines.append(self._render_footer(report))

        return "\n".join(lines)

    def _render_header(self, report: ComprehensiveHealthReport) -> str:
        """Render header section."""
        lines = []
        lines.append("")
        lines.append("=" * self.width)
        lines.append(self._color("  PERSONAL-AI DASHBOARD", "bold") + " " + self._color("Health Monitor", "cyan"))
        lines.append("=" * self.width)

        timestamp = datetime.fromisoformat(report.timestamp).strftime("%Y-%m-%d %H:%M:%S UTC")
        lines.append(f"  Timestamp: {timestamp}")
        lines.append(f"  Uptime: {self._format_duration(report.uptime_seconds)}")
        lines.append("")

        return "\n".join(lines)

    def _render_overall_health(self, report: ComprehensiveHealthReport) -> str:
        """Render overall health section."""
        lines = []
        lines.append(self._horizontal_line())

        score = report.overall_health_score()
        status = report.health_status()
        color = self._status_color(status)
        symbol = self._status_symbol(status)

        lines.append(f"  {self._color('OVERALL HEALTH', 'bold')}")
        lines.append("")
        lines.append(f"    Score: {self._color(f'{score:.1f}/100', color)}  {self._color(symbol, color)}")
        lines.append(f"    Status: {self._color(status.upper(), color)}")
        lines.append(f"    {self._progress_bar(score)}")
        lines.append("")

        return "\n".join(lines)

    def _horizontal_line(self) -> str:
        """Create horizontal separator."""
        return self.SYMBOLS["horizontal"] * self.width

    def _render_system_metrics(self, report: ComprehensiveHealthReport) -> str:
        """Render system metrics section."""
        lines = []
        lines.append(self._horizontal_line())
        lines.append(f"  {self._color('SYSTEM RESOURCES', 'bold')}")
        lines.append("")

        sys_metrics = report.system

        # CPU
        cpu_color = "green" if sys_metrics.cpu_percent < 70 else "yellow" if sys_metrics.cpu_percent < 90 else "red"
        lines.append(f"    CPU:      {self._color(f'{sys_metrics.cpu_percent:.1f}%', cpu_color)}  {self._progress_bar(sys_metrics.cpu_percent)}")

        # Memory
        mem_color = "green" if sys_metrics.memory_percent < 70 else "yellow" if sys_metrics.memory_percent < 90 else "red"
        mem_used = self._format_bytes(sys_metrics.memory_used_gb)
        mem_total = self._format_bytes(sys_metrics.memory_total_gb)
        lines.append(f"    Memory:   {self._color(f'{sys_metrics.memory_percent:.1f}%', mem_color)}  {self._progress_bar(sys_metrics.memory_percent)} ({mem_used}/{mem_total})")

        # Disk
        disk_color = "green" if sys_metrics.disk_percent < 70 else "yellow" if sys_metrics.disk_percent < 90 else "red"
        disk_used = self._format_bytes(sys_metrics.disk_used_gb)
        disk_total = self._format_bytes(sys_metrics.disk_total_gb)
        lines.append(f"    Disk:     {self._color(f'{sys_metrics.disk_percent:.1f}%', disk_color)}  {self._progress_bar(sys_metrics.disk_percent)} ({disk_used}/{disk_total})")

        # GPU
        if sys_metrics.gpu_available:
            gpu_color = "green" if sys_metrics.gpu_utilization < 70 else "yellow" if sys_metrics.gpu_utilization < 90 else "red"
            gpu_mem = f"{sys_metrics.gpu_memory_used_gb:.1f}/{sys_metrics.gpu_memory_total_gb:.1f} GB"
            lines.append(f"    GPU:      {self._color(f'{sys_metrics.gpu_utilization:.1f}%', gpu_color)}  {self._progress_bar(sys_metrics.gpu_utilization)} ({sys_metrics.gpu_name})")
            lines.append(f"    GPU Mem:  {gpu_mem}")
        else:
            lines.append(f"    GPU:      {self._color('Not available', 'dim')}")

        lines.append("")

        return "\n".join(lines)

    def _render_memory_metrics(self, report: ComprehensiveHealthReport) -> str:
        """Render memory store metrics."""
        lines = []
        lines.append(self._horizontal_line())
        lines.append(f"  {self._color('MEMORY & STORAGE', 'bold')}")
        lines.append("")

        mem = report.memory_store
        rag = report.rag_index

        # Memory store
        lines.append(f"    Memory Store:")
        lines.append(f"      Long-term:  {mem.long_term_count} memories")
        lines.append(f"      Short-term: {mem.short_term_count} memories")
        if mem.domains:
            lines.append(f"      Domains:    {', '.join(mem.domains[:5])}")

        # RAG Index
        lines.append(f"    RAG Index:")
        lines.append(f"      Chunks:     {rag.total_chunks}")
        lines.append(f"      Documents:  {rag.total_documents}")
        if rag.index_size_mb > 0:
            lines.append(f"      Size:       {rag.index_size_mb:.2f} MB")

        lines.append("")

        return "\n".join(lines)

    def _render_bridge_metrics(self, report: ComprehensiveHealthReport) -> str:
        """Render bridge connectivity metrics."""
        lines = []
        lines.append(self._horizontal_line())
        lines.append(f"  {self._color('BRIDGE CONNECTIVITY', 'bold')}")
        lines.append("")

        bridges = report.bridges

        # TouchDesigner
        td_status = self.SYMBOLS["ok"] if bridges.touchdesigner_connected else self.SYMBOLS["error"]
        td_color = "green" if bridges.touchdesigner_connected else "red"
        lines.append(f"    TouchDesigner: {self._color(td_status, td_color)}")
        if bridges.touchdesigner_host:
            lines.append(f"      {bridges.touchdesigner_host}:{bridges.touchdesigner_port}")

        # Houdini
        h_status = self.SYMBOLS["ok"] if bridges.houdini_connected else self.SYMBOLS["error"]
        h_color = "green" if bridges.houdini_connected else "red"
        lines.append(f"    Houdini:       {self._color(h_status, h_color)}")
        if bridges.houdini_host:
            lines.append(f"      {bridges.houdini_host}:{bridges.houdini_port}")

        lines.append("")

        return "\n".join(lines)

    def _render_execution_metrics(self, report: ComprehensiveHealthReport) -> str:
        """Render execution history metrics."""
        lines = []
        lines.append(self._horizontal_line())
        lines.append(f"  {self._color('EXECUTION HISTORY', 'bold')}")
        lines.append("")

        exec_metrics = report.execution

        # Success rate
        sr_color = "green" if exec_metrics.success_rate > 0.8 else "yellow" if exec_metrics.success_rate > 0.5 else "red"
        lines.append(f"    Total:         {exec_metrics.total_executions}")
        lines.append(f"    Success Rate:  {self._color(f'{exec_metrics.success_rate * 100:.1f}%', sr_color)}")
        lines.append(f"      Successes:   {exec_metrics.successful_executions}")
        lines.append(f"      Failures:    {exec_metrics.failed_executions}")

        if exec_metrics.recent_domains:
            lines.append(f"    Recent Domains: {', '.join(exec_metrics.recent_domains[:3])}")

        lines.append("")

        return "\n".join(lines)

    def _render_error_metrics(self, report: ComprehensiveHealthReport) -> str:
        """Render error metrics."""
        lines = []
        lines.append(self._horizontal_line())
        lines.append(f"  {self._color('ERROR TRACKING', 'bold')}")
        lines.append("")

        errors = report.errors

        # Error count
        if errors.total_errors == 0:
            lines.append(f"    {self._color('No errors recorded', 'green')}")
        else:
            err_color = "green" if errors.recent_errors_24h == 0 else "yellow" if errors.recent_errors_24h < 5 else "red"
            lines.append(f"    Total Errors:     {errors.total_errors}")
            lines.append(f"    Recent (24h):     {self._color(str(errors.recent_errors_24h), err_color)}")
            lines.append(f"    Unique Types:     {errors.unique_error_types}")

            if errors.most_common_error:
                lines.append(f"    Most Common:      {errors.most_common_error}")

            if errors.top_error_types:
                lines.append("    Top Error Types:")
                for et in errors.top_error_types[:3]:
                    lines.append(f"      - {et['type']}: {et['count']}")

        lines.append("")

        return "\n".join(lines)

    def _render_knowledge_metrics(self, report: ComprehensiveHealthReport) -> str:
        """Render knowledge and training metrics."""
        lines = []
        lines.append(self._horizontal_line())
        lines.append(f"  {self._color('KNOWLEDGE & TRAINING', 'bold')}")
        lines.append("")

        knowledge = report.knowledge
        training = report.training

        # Knowledge patterns
        lines.append(f"    Success Patterns:")
        lines.append(f"      Total:       {knowledge.total_patterns}")
        lines.append(f"      Verified:    {knowledge.verified_patterns}")
        if knowledge.pattern_success_rate > 0:
            lines.append(f"      Success Rt:  {knowledge.pattern_success_rate * 100:.1f}%")

        # Training
        lines.append(f"    Training Data:")
        lines.append(f"      Examples:    {training.training_examples_total}")
        if training.training_examples_domain:
            for domain, count in list(training.training_examples_domain.items())[:3]:
                lines.append(f"        {domain}: {count}")

        if training.active_model_id:
            lines.append(f"      Active Model: {training.active_model_id}")

        lines.append("")

        return "\n".join(lines)

    def _render_feedback_metrics(self, report: ComprehensiveHealthReport) -> str:
        """Render feedback loop metrics."""
        lines = []
        lines.append(self._horizontal_line())
        lines.append(f"  {self._color('FEEDBACK LOOP', 'bold')}")
        lines.append("")

        fb = report.feedback_loop

        if fb.iterations_total == 0:
            lines.append(f"    {self._color('No feedback iterations yet', 'dim')}")
        else:
            trend_color = "green" if fb.score_trend == "improving" else "red" if fb.score_trend == "declining" else "yellow"
            lines.append(f"    Iterations:   {fb.iterations_total}")
            lines.append(f"    Avg Score:    {fb.avg_score:.2f}")
            lines.append(f"    Trend:        {self._color(fb.score_trend, trend_color)}")
            lines.append(f"    Positive:     {fb.positive_count}")
            lines.append(f"    Correction:   {fb.correction_count}")
            lines.append(f"    Negative:     {fb.negative_count}")

            if fb.examples_collected > 0:
                lines.append(f"    Collected:    {fb.examples_collected} examples")

        lines.append("")

        return "\n".join(lines)

    def _render_footer(self, report: ComprehensiveHealthReport) -> str:
        """Render footer section."""
        lines = []
        lines.append("=" * self.width)

        # Quick status
        status = report.health_status()
        color = self._status_color(status)
        symbol = self._status_symbol(status)

        lines.append(f"  Status: {self._color(symbol + ' ' + status.upper(), color)}")
        lines.append(f"  Health: {self._color(f'{report.overall_health_score():.1f}%', color)}")
        lines.append("")
        lines.append("  Commands: status-dashboard --refresh  # Live refresh")
        lines.append("            status-dashboard --json    # Export to JSON")
        lines.append("")
        lines.append("=" * self.width)

        return "\n".join(lines)

    def render_compact(self, report: ComprehensiveHealthReport) -> str:
        """Render compact single-line status."""
        score = report.overall_health_score()
        status = report.health_status()
        color = self._status_color(status)
        symbol = self._status_symbol(status)

        parts = [
            self._color(f"{symbol} {score:.0f}%", color),
            f"CPU:{report.system.cpu_percent:.0f}%",
            f"MEM:{report.system.memory_percent:.0f}%",
            f"ERR:{report.errors.recent_errors_24h}",
        ]

        if report.system.gpu_available:
            parts.append(f"GPU:{report.system.gpu_utilization:.0f}%")

        return " | ".join(parts)

    def render_json(self, report: ComprehensiveHealthReport) -> str:
        """Render as JSON string."""
        import json
        return json.dumps(report.to_dict(), indent=2, ensure_ascii=False)


# Import os for color detection
import os