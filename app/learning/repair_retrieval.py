"""Repair-Time Knowledge Retrieval Module.

Provides intelligent error recovery by retrieving knowledge from:
1. Error memory (past similar errors + how fixed)
2. Tutorial memory (best practices + safety checks)

This module enhances the existing error handling system with
retrieval-informed repair decisions.
"""

from __future__ import annotations

__all__ = [
    "ErrorRepairRetriever",
    "RepairKnowledge",
    "ErrorRepairStrategy",
    "TutorialRepairHint",
    "ErrorRecoveryManager",
    "ErrorRecoveryState",
    "RepairActionGenerator",
    "RepairMetrics",
    "ErrorClassification",
    "classify_error",
    "compute_adaptive_backoff",
]

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional
import re
import time


class ErrorClassification(str, Enum):
    """Classification of error types for repair routing."""

    EXECUTION = "execution"           # Node not found, invalid parameter
    VALIDATION = "validation"         # Output doesn't match expected format
    TIMEOUT = "timeout"               # Operation took too long
    RESOURCE = "resource"             # Out of memory, connection issues
    DOMAIN = "domain"                 # Tool-specific limitation
    LOGIC = "logic"                   # Subgoal partially completed
    PERMISSION = "permission"         # Access denied, not authorized
    STATE = "state"                   # Invalid state, unexpected state


@dataclass(slots=True)
class ErrorRepairStrategy:
    """A repair strategy extracted from past error fixes."""

    error_pattern: str               # Pattern that matches the error
    successful_action: str           # What action fixed it
    success_rate: float              # How often this works
    domain: str                      # Domain where this applies
    source_error_id: str             # Original error ID
    last_used: str                   # ISO timestamp
    use_count: int = 0               # How many times used

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_pattern": self.error_pattern,
            "successful_action": self.successful_action,
            "success_rate": self.success_rate,
            "domain": self.domain,
            "source_error_id": self.source_error_id,
            "last_used": self.last_used,
            "use_count": self.use_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ErrorRepairStrategy":
        return cls(
            error_pattern=data["error_pattern"],
            successful_action=data["successful_action"],
            success_rate=data["success_rate"],
            domain=data["domain"],
            source_error_id=data["source_error_id"],
            last_used=data["last_used"],
            use_count=data.get("use_count", 0),
        )


@dataclass(slots=True)
class TutorialRepairHint:
    """Repair hint extracted from tutorial knowledge."""

    source_tutorial: str              # Tutorial ID/name
    repair_suggestion: str            # What to do
    reasoning: str                    # Why this works
    applicability: float              # 0.0-1.0, how relevant to this error
    confidence: float                 # Based on tutorial confidence
    prerequisites: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_tutorial": self.source_tutorial,
            "repair_suggestion": self.repair_suggestion,
            "reasoning": self.reasoning,
            "applicability": self.applicability,
            "confidence": self.confidence,
            "prerequisites": self.prerequisites,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TutorialRepairHint":
        return cls(
            source_tutorial=data["source_tutorial"],
            repair_suggestion=data["repair_suggestion"],
            reasoning=data["reasoning"],
            applicability=data["applicability"],
            confidence=data["confidence"],
            prerequisites=data.get("prerequisites", []),
        )


@dataclass(slots=True)
class RepairKnowledge:
    """Aggregated repair knowledge for an error."""

    error_classification: ErrorClassification
    similar_error_repairs: list[ErrorRepairStrategy] = field(default_factory=list)
    tutorial_hints: list[TutorialRepairHint] = field(default_factory=list)
    confidence_in_repair: float = 0.0
    retrieval_timestamp: str = ""

    def __post_init__(self):
        if not self.retrieval_timestamp:
            self.retrieval_timestamp = datetime.utcnow().isoformat() + "Z"

    def get_best_repair(self) -> ErrorRepairStrategy | TutorialRepairHint | None:
        """Return highest-confidence repair option."""
        all_repairs: list[tuple[float, ErrorRepairStrategy | TutorialRepairHint]] = []

        for r in self.similar_error_repairs:
            all_repairs.append((r.success_rate, r))

        for h in self.tutorial_hints:
            all_repairs.append((h.confidence * h.applicability, h))

        if not all_repairs:
            return None

        return max(all_repairs, key=lambda x: x[0])[1]

    @property
    def has_repairs(self) -> bool:
        return len(self.similar_error_repairs) > 0 or len(self.tutorial_hints) > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_classification": self.error_classification.value,
            "similar_error_repairs": [r.to_dict() for r in self.similar_error_repairs],
            "tutorial_hints": [h.to_dict() for h in self.tutorial_hints],
            "confidence_in_repair": self.confidence_in_repair,
            "retrieval_timestamp": self.retrieval_timestamp,
        }


# ============================================================================
# ERROR CLASSIFICATION
# ============================================================================

# Patterns for error classification
ERROR_PATTERNS = {
    ErrorClassification.EXECUTION: [
        r"not found",
        r"does not exist",
        r"invalid parameter",
        r"invalid argument",
        r"unknown node",
        r"unknown operator",
        r"missing",
        r"undefined",
    ],
    ErrorClassification.VALIDATION: [
        r"does not match",
        r"expected",
        r"validation failed",
        r"invalid format",
        r"schema violation",
        r"type mismatch",
    ],
    ErrorClassification.TIMEOUT: [
        r"timeout",
        r"timed out",
        r"took too long",
        r"deadline exceeded",
        r"operation cancelled",
    ],
    ErrorClassification.RESOURCE: [
        r"out of memory",
        r"memory allocation",
        r"connection refused",
        r"connection reset",
        r"network",
        r"socket",
        r"disk full",
    ],
    ErrorClassification.DOMAIN: [
        r"houdini:",
        r"touchdesigner:",
        r"sop:",
        r"dop:",
        r"top:",
        r"chop:",
        r"vex",
        r"python error",
    ],
    ErrorClassification.LOGIC: [
        r"partial",
        r"incomplete",
        r"unexpected state",
        r"precondition",
        r"postcondition",
    ],
    ErrorClassification.PERMISSION: [
        r"permission denied",
        r"access denied",
        r"unauthorized",
        r"forbidden",
        r"not allowed",
    ],
    ErrorClassification.STATE: [
        r"invalid state",
        r"already exists",
        r"not initialized",
        r"closed",
        r"disposed",
    ],
}


def classify_error(error_message: str, error_context: dict[str, Any] | None = None) -> ErrorClassification:
    """Classify an error message into a category.

    Args:
        error_message: The error message text
        error_context: Optional context for additional classification hints

    Returns:
        ErrorClassification enum value
    """
    message_lower = error_message.lower()

    # Check each classification's patterns
    scores: dict[ErrorClassification, int] = {ec: 0 for ec in ErrorClassification}

    for classification, patterns in ERROR_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, message_lower):
                scores[classification] += 1

    # Check context hints
    if error_context:
        # Timeout hints
        if error_context.get("duration_ms", 0) > 30000:
            scores[ErrorClassification.TIMEOUT] += 2

        # Domain hints
        domain = error_context.get("domain", "").lower()
        if domain in ("houdini", "touchdesigner"):
            scores[ErrorClassification.DOMAIN] += 1

    # Find best classification
    best = max(scores.items(), key=lambda x: x[1])

    # Default to EXECUTION if no patterns match
    if best[1] == 0:
        return ErrorClassification.EXECUTION

    return best[0]


def extract_concepts(text: str) -> list[str]:
    """Extract key concepts from error message for matching.

    Args:
        text: Error message or context

    Returns:
        List of concept keywords
    """
    # Remove common words
    stop_words = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been",
        "being", "have", "has", "had", "do", "does", "did", "will",
        "would", "could", "should", "may", "might", "must", "shall",
        "can", "need", "to", "of", "in", "for", "on", "with", "at",
        "by", "from", "as", "into", "through", "during", "before",
        "after", "above", "below", "between", "under", "again",
        "further", "then", "once", "here", "there", "when", "where",
        "why", "how", "all", "each", "few", "more", "most", "other",
        "some", "such", "no", "nor", "not", "only", "own", "same",
        "so", "than", "too", "very", "just", "and", "but", "if",
        "or", "because", "until", "while", "error", "failed", "exception",
    }

    # Tokenize and filter
    words = re.findall(r"\b[a-z]{3,}\b", text.lower())
    concepts = [w for w in words if w not in stop_words]

    # Remove duplicates while preserving order
    seen = set()
    unique = []
    for c in concepts:
        if c not in seen:
            seen.add(c)
            unique.append(c)

    return unique[:10]  # Top 10 concepts


def matches_error_pattern(hint_text: str, error_message: str) -> bool:
    """Check if hint text is relevant to error.

    Args:
        hint_text: Hint or prevention text
        error_message: Error message to match against

    Returns:
        True if there's meaningful overlap
    """
    hint_terms = set(hint_text.lower().split())
    error_terms = set(error_message.lower().split())

    if not hint_terms:
        return False

    overlap = len(hint_terms & error_terms)
    return overlap / len(hint_terms) > 0.3


# ============================================================================
# ADAPTIVE BACKOFF
# ============================================================================

def compute_adaptive_backoff(
    attempt_count: int,
    confidence: float,
    base_backoff: float = 0.5,
    max_backoff: float = 10.0,
) -> float:
    """Compute backoff time based on attempts and confidence.

    Low confidence -> longer backoff (give more time)
    High confidence -> shorter backoff (retry quickly)

    Args:
        attempt_count: Number of attempts so far (1-indexed)
        confidence: Confidence in repair (0.0-1.0)
        base_backoff: Base backoff time in seconds
        max_backoff: Maximum backoff time

    Returns:
        Backoff time in seconds
    """
    # Exponential backoff: 0.5s, 1s, 2s, 4s
    exponential = base_backoff * (2 ** (attempt_count - 1))

    # Confidence adjustment: 0.5 (low) to 1.0 (high)
    # Low confidence: wait longer
    confidence_factor = 2.0 - confidence  # 1.0 (conf=1.0) to 1.5 (conf=0.5)

    backoff = exponential * confidence_factor

    return min(backoff, max_backoff)


# ============================================================================
# REPAIR METRICS
# ============================================================================

@dataclass
class RepairMetrics:
    """Track repair effectiveness metrics."""

    total_errors: int = 0
    errors_repaired: int = 0
    errors_requiring_replan: int = 0
    total_repair_time: float = 0.0
    tutorial_hints_used: int = 0
    tutorial_hints_successful: int = 0
    prior_solution_used: int = 0
    prior_solution_successful: int = 0
    generic_recovery_used: int = 0

    # By error type
    repair_attempts_by_type: dict[str, int] = field(default_factory=dict)
    repair_success_by_type: dict[str, int] = field(default_factory=dict)

    @property
    def repair_success_rate(self) -> float:
        if self.total_errors == 0:
            return 0.0
        return self.errors_repaired / self.total_errors

    @property
    def avg_repair_time(self) -> float:
        if self.errors_repaired == 0:
            return 0.0
        return self.total_repair_time / self.errors_repaired

    @property
    def tutorial_effectiveness(self) -> float:
        if self.tutorial_hints_used == 0:
            return 0.0
        return self.tutorial_hints_successful / self.tutorial_hints_used

    @property
    def prior_solution_effectiveness(self) -> float:
        if self.prior_solution_used == 0:
            return 0.0
        return self.prior_solution_successful / self.prior_solution_used

    def record_error(self, error_type: str) -> None:
        """Record an error occurrence."""
        self.total_errors += 1
        self.repair_attempts_by_type[error_type] = (
            self.repair_attempts_by_type.get(error_type, 0) + 1
        )

    def record_repair_success(
        self,
        error_type: str,
        repair_time: float,
        used_tutorial: bool = False,
        used_prior: bool = False,
    ) -> None:
        """Record a successful repair."""
        self.errors_repaired += 1
        self.total_repair_time += repair_time
        self.repair_success_by_type[error_type] = (
            self.repair_success_by_type.get(error_type, 0) + 1
        )

        if used_tutorial:
            self.tutorial_hints_used += 1
            self.tutorial_hints_successful += 1

        if used_prior:
            self.prior_solution_used += 1
            self.prior_solution_successful += 1

    def record_replan_needed(self) -> None:
        """Record that replanning was needed."""
        self.errors_requiring_replan += 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_errors": self.total_errors,
            "errors_repaired": self.errors_repaired,
            "errors_requiring_replan": self.errors_requiring_replan,
            "repair_success_rate": self.repair_success_rate,
            "avg_repair_time": self.avg_repair_time,
            "tutorial_effectiveness": self.tutorial_effectiveness,
            "prior_solution_effectiveness": self.prior_solution_effectiveness,
            "tutorial_hints_used": self.tutorial_hints_used,
            "prior_solution_used": self.prior_solution_used,
            "generic_recovery_used": self.generic_recovery_used,
            "repair_attempts_by_type": self.repair_attempts_by_type,
            "repair_success_by_type": self.repair_success_by_type,
        }

    def summary(self) -> str:
        """Return a summary string."""
        return f"""Repair Metrics:
- Total errors: {self.total_errors}
- Repair success rate: {self.repair_success_rate:.0%}
- Avg repair time: {self.avg_repair_time:.1f}s
- Tutorial effectiveness: {self.tutorial_effectiveness:.0%}
- Prior solution effectiveness: {self.prior_solution_effectiveness:.0%}
- Required replan: {self.errors_requiring_replan}
"""