"""Pattern Tracker - Track recurring error patterns.

Identifies and tracks patterns in feedback data for targeted improvement.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ErrorPattern:
    """A recurring error pattern."""

    pattern_id: str
    pattern_type: str
    description: str
    frequency: int = 0
    last_seen: str = ""
    affected_domains: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern_id": self.pattern_id,
            "pattern_type": self.pattern_type,
            "description": self.description,
            "frequency": self.frequency,
            "last_seen": self.last_seen,
            "affected_domains": self.affected_domains,
            "example_count": len(self.examples),
        }


@dataclass(slots=True)
class WeakArea:
    """A weak area identified from patterns."""

    area_name: str
    severity: str  # critical, high, medium, low
    occurrence_count: int = 0
    trend: str = "stable"  # improving, declining, stable
    suggestions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "area_name": self.area_name,
            "severity": self.severity,
            "occurrence_count": self.occurrence_count,
            "trend": self.trend,
            "suggestions": self.suggestions,
        }


class PatternTracker:
    """Track and identify recurring error patterns.

    Analyzes feedback records to identify:
    - Repeated error types
    - Weak areas by domain
    - Trending issues
    - Improvement opportunities

    Usage:
        tracker = PatternTracker()
        tracker.record_error("houdini", "Merge SOP connection failed")
        patterns = tracker.get_patterns()
    """

    def __init__(self) -> None:
        """Initialize pattern tracker."""
        self._error_counts: Counter = Counter()
        self._domain_errors: dict[str, Counter] = {}
        self._recent_errors: list[tuple[str, str, str]] = []  # domain, error, timestamp
        self._patterns: dict[str, ErrorPattern] = {}

    def record_error(
        self,
        domain: str,
        error: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Record an error for pattern tracking.

        Args:
            domain: Domain where error occurred
            error: Error message or description
            context: Optional additional context
        """
        timestamp = datetime.utcnow().isoformat()

        # Normalize error
        normalized = self._normalize_error(error)

        # Track counts
        self._error_counts[normalized] += 1

        if domain not in self._domain_errors:
            self._domain_errors[domain] = Counter()
        self._domain_errors[domain][normalized] += 1

        # Track recent
        self._recent_errors.append((domain, normalized, timestamp))

        # Keep only last 1000
        if len(self._recent_errors) > 1000:
            self._recent_errors = self._recent_errors[-1000:]

    def _normalize_error(
        self,
        error: str,
    ) -> str:
        """Normalize error message for pattern matching."""
        # Remove specific values
        normalized = re.sub(r'\b\d+\.\d+\b', '[NUM]', error)
        normalized = re.sub(r'\b\d+\b', '[NUM]', normalized)

        # Remove paths
        normalized = re.sub(r'[A-Z]:\\[^\s]+', '[PATH]', normalized)
        normalized = re.sub(r'/[^\s]+', '[PATH]', normalized)

        # Truncate
        return normalized[:100]

    def get_patterns(
        self,
        min_frequency: int = 3,
    ) -> list[ErrorPattern]:
        """Get identified error patterns.

        Args:
            min_frequency: Minimum frequency to consider

        Returns:
            List of error patterns
        """
        patterns = []

        for error, count in self._error_counts.most_common(50):
            if count < min_frequency:
                continue

            # Find affected domains
            domains = []
            for domain, counter in self._domain_errors.items():
                if counter.get(error, 0) > 0:
                    domains.append(domain)

            # Determine pattern type
            pattern_type = self._classify_pattern(error)

            # Get last seen
            last_seen = ""
            for d, e, t in reversed(self._recent_errors):
                if e == error:
                    last_seen = t
                    break

            pattern = ErrorPattern(
                pattern_id=f"pattern_{abs(hash(error)) % 10000:04d}",
                pattern_type=pattern_type,
                description=error,
                frequency=count,
                last_seen=last_seen,
                affected_domains=domains,
            )

            patterns.append(pattern)

        return patterns

    def _classify_pattern(
        self,
        error: str,
    ) -> str:
        """Classify error pattern type."""
        error_lower = error.lower()

        if "node" in error_lower:
            return "node_error"
        elif "connection" in error_lower:
            return "connection_error"
        elif "parameter" in error_lower:
            return "parameter_error"
        elif "vex" in error_lower:
            return "vex_error"
        elif "python" in error_lower:
            return "python_error"
        elif "render" in error_lower:
            return "render_error"
        else:
            return "general_error"

    def get_weak_areas(
        self,
        domain: str | None = None,
    ) -> list[WeakArea]:
        """Get weak areas from pattern analysis.

        Args:
            domain: Optional domain filter

        Returns:
            List of weak areas
        """
        weak_areas: list[WeakArea] = []

        # Analyze domain-specific errors
        domain_counter = self._domain_errors.get(domain, {}) if domain else self._error_counts

        for error, count in domain_counter.most_common(10):
            if count < 2:
                continue

            area_name = self._extract_area_name(error)
            severity = self._determine_severity(count)

            area = WeakArea(
                area_name=area_name,
                severity=severity,
                occurrence_count=count,
                trend=self._get_trend(area_name),
                suggestions=self._generate_suggestions(area_name),
            )

            weak_areas.append(area)

        return weak_areas

    def _extract_area_name(
        self,
        error: str,
    ) -> str:
        """Extract area name from error."""
        error_lower = error.lower()

        if "merge" in error_lower:
            return "merge_operations"
        elif "scatter" in error_lower:
            return "scatter_setup"
        elif "connection" in error_lower:
            return "node_connections"
        elif "parameter" in error_lower:
            return "parameter_settings"
        elif "vex" in error_lower or "wrangle" in error_lower:
            return "vex_code"
        else:
            return "general_operations"

    def _determine_severity(
        self,
        count: int,
    ) -> str:
        """Determine severity from count."""
        if count >= 10:
            return "critical"
        elif count >= 5:
            return "high"
        elif count >= 3:
            return "medium"
        else:
            return "low"

    def _get_trend(
        self,
        area_name: str,
    ) -> str:
        """Get trend for an area."""
        # Simple trend based on recent errors
        recent_count = sum(
            1 for _, e, _ in self._recent_errors[-100:]
            if area_name in self._extract_area_name(e).lower()
        )
        older_count = sum(
            1 for _, e, _ in self._recent_errors[:100]
            if area_name in self._extract_area_name(e).lower()
        )

        if recent_count > older_count * 1.5:
            return "declining"
        elif recent_count < older_count * 0.7:
            return "improving"
        else:
            return "stable"

    def _generate_suggestions(
        self,
        area_name: str,
    ) -> list[str]:
        """Generate improvement suggestions."""
        suggestions = {
            "merge_operations": [
                "Review merge SOP input ordering",
                "Check for null node requirements",
                "Verify upstream connections",
            ],
            "scatter_setup": [
                "Verify input geometry bounds",
                "Check point count settings",
                "Review seed parameter usage",
            ],
            "node_connections": [
                "Verify node names in connections",
                "Check output indices",
                "Review connection order",
            ],
            "parameter_settings": [
                "Validate parameter ranges",
                "Check for required parameters",
                "Review expression syntax",
            ],
            "vex_code": [
                "Review VEX syntax",
                "Check attribute names",
                "Verify function signatures",
            ],
        }

        return suggestions.get(area_name, ["Review documentation for this area"])

    def get_summary(self) -> dict[str, Any]:
        """Get pattern tracking summary."""
        return {
            "total_unique_errors": len(self._error_counts),
            "total_error_count": sum(self._error_counts.values()),
            "domains_tracked": list(self._domain_errors.keys()),
            "recent_errors": len(self._recent_errors),
            "top_patterns": [
                {"error": e, "count": c}
                for e, c in self._error_counts.most_common(5)
            ],
        }

    def clear(self) -> None:
        """Clear all tracked patterns."""
        self._error_counts = Counter()
        self._domain_errors = {}
        self._recent_errors = []