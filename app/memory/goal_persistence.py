"""Unified Goal Persistence Layer.

This module provides the single source of truth for goal storage
across the goal_generator and goal_scheduler_bridge systems.

Key principles:
- Single Goal model used by all components
- Single GoalStore with proper persistence
- Backward compatibility with existing code
- Evidence-based goals with provenance
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterator


# ============================================================================
# ENUMS
# ============================================================================

class GoalType(str, Enum):
    """Types of goals the system can generate."""

    # Learning and knowledge
    LEARN_NEW_OPERATOR = "learn_new_operator"
    LEARN_DOC_CONCEPT = "learn_doc_concept"
    DISTILL_TUTORIAL_KNOWLEDGE = "distill_tutorial_knowledge"
    CREATE_RECIPE_KNOWLEDGE = "create_recipe_knowledge"
    IMPROVE_KNOWLEDGE_QUALITY = "improve_knowledge_quality"

    # Error handling and repair
    FIX_REPEATED_ERROR = "fix_repeated_error"
    FORMALIZE_REPAIR_PATTERN = "formalize_repair_pattern"
    INVESTIGATE_ERROR_CLUSTER = "investigate_error_cluster"

    # Memory and retrieval
    IMPROVE_MEMORY_REUSE = "improve_memory_reuse"
    PROMOTE_SUCCESS_PATTERN = "promote_success_pattern"
    CLEAN_STALE_MEMORY = "clean_stale_memory"

    # Bridge and health
    IMPROVE_BRIDGE_RELIABILITY = "improve_bridge_reliability"
    INSTRUMENT_BRIDGE_MONITORING = "instrument_bridge_monitoring"

    # Documentation and knowledge base
    UPDATE_DOCUMENTATION = "update_documentation"
    CREATE_EXAMPLE_RECIPE = "create_example_recipe"

    # System improvement
    OPTIMIZE_EXECUTION_PATH = "optimize_execution_path"
    REDUCE_REDUNDANCY = "reduce_redundancy"
    INVESTIGATE_RUNTIME_DRIFT = "investigate_runtime_drift"
    IMPROVE_VERIFICATION_COVERAGE = "improve_verification_coverage"
    IMPROVE_DATA_COVERAGE = "improve_data_coverage"


class GoalStatus(str, Enum):
    """Lifecycle status of a goal."""

    PROPOSED = "proposed"           # Generated but not yet reviewed
    ACCEPTED = "accepted"           # Approved for action
    ACTIONABLE = "actionable"       # Ready to be converted to tasks
    SCHEDULED = "scheduled"         # Tasks have been created
    IN_PROGRESS = "in_progress"     # Tasks are executing
    COMPLETED = "completed"         # All tasks completed successfully
    PARTIAL = "partial"             # Some tasks succeeded, some failed
    FAILED = "failed"               # All tasks failed
    DEFERRED = "deferred"           # Postponed due to dependencies
    BLOCKED = "blocked"             # Cannot proceed due to blockers
    REJECTED = "rejected"           # Not actionable or not worth pursuing
    CANCELLED = "cancelled"         # Cancelled by user or system
    RESOLVED = "resolved"           # Resolved externally


class GoalPriority(str, Enum):
    """Priority levels for goals."""

    CRITICAL = "critical"    # System stability or blocking issues
    HIGH = "high"            # Important improvements
    MEDIUM = "medium"        # Standard improvements
    LOW = "low"              # Nice-to-have improvements
    BACKGROUND = "background"  # Can run when idle


class ActionabilityStatus(str, Enum):
    """Whether a goal can be converted to tasks."""

    ACTIONABLE_NOW = "actionable_now"
    NEEDS_DEPENDENCIES = "needs_dependencies"
    NEEDS_MORE_EVIDENCE = "needs_more_evidence"
    BLOCKED_BY_HEALTH = "blocked_by_health"
    NOT_ACTIONABLE = "not_actionable"
    DEFERRED_TIMING = "deferred_timing"


class SignalType(str, Enum):
    """Types of signals that can generate goals."""

    # Docs/knowledge signals
    DOCS_DELTA = "docs_delta"
    NEW_OPERATOR = "new_operator"
    NEW_CONCEPT = "new_concept"
    TUTORIAL_RAW = "tutorial_raw"

    # Error/failure signals
    REPEATED_ERROR = "repeated_error"
    REPAIR_FAILURE = "repair_failure"
    NO_PROGRESS_LOOP = "no_progress_loop"
    VERIFICATION_FAILURE = "verification_failure"

    # Memory signals
    WEAK_RETRIEVAL = "weak_retrieval"
    SUCCESS_NOT_REUSED = "success_not_reused"

    # Runtime/bridge signals
    BRIDGE_DEGRADATION = "bridge_degradation"
    COMMAND_REJECTION = "command_rejection"
    BACKEND_INSTABILITY = "backend_instability"

    # Learning/data signals
    WEAK_DATASET_COVERAGE = "weak_dataset_coverage"
    LOW_EXAMPLE_COUNT = "low_example_count"
    WEAK_RECIPE_COVERAGE = "weak_recipe_coverage"


# ============================================================================
# MODELS
# ============================================================================

@dataclass(slots=True)
class GoalEvidence:
    """Evidence supporting a goal's creation."""

    evidence_id: str
    evidence_type: str
    summary: str
    details: dict[str, Any] = field(default_factory=dict)
    source: str = ""
    timestamp: str = ""
    confidence: float = 0.5

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = _now_iso()
        if not self.evidence_id:
            self.evidence_id = f"ev_{int(time.time())}_{uuid.uuid4().hex[:8]}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "evidence_type": self.evidence_type,
            "summary": self.summary,
            "details": self.details,
            "source": self.source,
            "timestamp": self.timestamp,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GoalEvidence":
        return cls(
            evidence_id=data.get("evidence_id", ""),
            evidence_type=data["evidence_type"],
            summary=data["summary"],
            details=data.get("details", {}),
            source=data.get("source", ""),
            timestamp=data.get("timestamp", ""),
            confidence=data.get("confidence", 0.5),
        )


@dataclass(slots=True)
class Goal:
    """A structured goal derived from system state analysis.

    Goals represent desired outcomes that the system should pursue.
    They are transformed into scheduled tasks by the bridge layer.
    """

    goal_id: str
    goal_type: GoalType
    title: str
    description: str
    domain: str

    status: GoalStatus = GoalStatus.PROPOSED
    priority: GoalPriority = GoalPriority.MEDIUM
    actionability: ActionabilityStatus = ActionabilityStatus.ACTIONABLE_NOW

    evidence: list[GoalEvidence] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    blocks: list[str] = field(default_factory=list)

    confidence: float = 0.5
    impact_score: float = 0.5
    effort_estimate: str = "medium"

    created_at: str = ""
    updated_at: str = ""
    resolved_at: str = ""
    source_analysis_id: str = ""

    derived_task_ids: list[str] = field(default_factory=list)
    recommended_action: str = ""
    resolution_notes: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = _now_iso()
        if not self.updated_at:
            self.updated_at = self.created_at
        if not self.goal_id:
            self.goal_id = generate_goal_id(self.goal_type, self.domain)

    def is_actionable(self) -> bool:
        """Check if goal is actionable for task derivation."""
        return self.actionability == ActionabilityStatus.ACTIONABLE_NOW

    def can_derive_tasks(self) -> bool:
        """Check if tasks can be derived from this goal."""
        return (
            self.status in (GoalStatus.PROPOSED, GoalStatus.ACTIONABLE, GoalStatus.ACCEPTED)
            and self.is_actionable()
            and self.confidence >= 0.3
        )

    def get_effective_priority(self) -> float:
        """Calculate effective priority score."""
        priority_weights = {
            GoalPriority.CRITICAL: 1.0,
            GoalPriority.HIGH: 0.8,
            GoalPriority.MEDIUM: 0.5,
            GoalPriority.LOW: 0.3,
            GoalPriority.BACKGROUND: 0.1,
        }
        base = priority_weights.get(self.priority, 0.5)
        return base * self.confidence * self.impact_score

    def mark_scheduled(self, task_ids: list[str]) -> None:
        """Mark goal as scheduled with derived tasks."""
        self.status = GoalStatus.SCHEDULED
        self.derived_task_ids = task_ids
        self.updated_at = _now_iso()

    def mark_in_progress(self) -> None:
        """Mark goal as in progress."""
        self.status = GoalStatus.IN_PROGRESS
        self.updated_at = _now_iso()

    def mark_completed(self, notes: str = "") -> None:
        """Mark goal as completed."""
        self.status = GoalStatus.COMPLETED
        self.updated_at = _now_iso()
        self.resolved_at = self.updated_at
        if notes:
            self.resolution_notes = notes

    def mark_failed(self, reason: str = "") -> None:
        """Mark goal as failed."""
        self.status = GoalStatus.FAILED
        self.updated_at = _now_iso()
        self.resolved_at = self.updated_at
        if reason:
            self.resolution_notes = reason

    def mark_deferred(self, reason: str = "") -> None:
        """Mark goal as deferred."""
        self.status = GoalStatus.DEFERRED
        self.updated_at = _now_iso()
        if reason:
            self.metadata["deferral_reason"] = reason

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal_id": self.goal_id,
            "goal_type": self.goal_type.value,
            "title": self.title,
            "description": self.description,
            "domain": self.domain,
            "status": self.status.value,
            "priority": self.priority.value,
            "actionability": self.actionability.value,
            "evidence": [e.to_dict() for e in self.evidence],
            "dependencies": self.dependencies,
            "blocks": self.blocks,
            "confidence": self.confidence,
            "impact_score": self.impact_score,
            "effort_estimate": self.effort_estimate,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "resolved_at": self.resolved_at,
            "source_analysis_id": self.source_analysis_id,
            "derived_task_ids": self.derived_task_ids,
            "recommended_action": self.recommended_action,
            "resolution_notes": self.resolution_notes,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Goal":
        return cls(
            goal_id=data["goal_id"],
            goal_type=GoalType(data["goal_type"]),
            title=data["title"],
            description=data["description"],
            domain=data["domain"],
            status=GoalStatus(data.get("status", "proposed")),
            priority=GoalPriority(data.get("priority", "medium")),
            actionability=ActionabilityStatus(data.get("actionability", "actionable_now")),
            evidence=[GoalEvidence.from_dict(e) for e in data.get("evidence", [])],
            dependencies=data.get("dependencies", []),
            blocks=data.get("blocks", []),
            confidence=data.get("confidence", 0.5),
            impact_score=data.get("impact_score", 0.5),
            effort_estimate=data.get("effort_estimate", "medium"),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            resolved_at=data.get("resolved_at", ""),
            source_analysis_id=data.get("source_analysis_id", ""),
            derived_task_ids=data.get("derived_task_ids", []),
            recommended_action=data.get("recommended_action", ""),
            resolution_notes=data.get("resolution_notes", ""),
            metadata=data.get("metadata", {}),
        )


@dataclass(slots=True)
class GoalSignal:
    """A signal that contributes to goal generation."""

    signal_id: str
    signal_type: SignalType
    domain: str
    source: str
    evidence: dict[str, Any] = field(default_factory=dict)
    recurrence_count: int = 1
    first_seen: str = ""
    last_seen: str = ""

    def __post_init__(self) -> None:
        if not self.signal_id:
            self.signal_id = f"sig_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        if not self.first_seen:
            self.first_seen = _now_iso()
        if not self.last_seen:
            self.last_seen = self.first_seen

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "signal_type": self.signal_type.value,
            "domain": self.domain,
            "source": self.source,
            "evidence": self.evidence,
            "recurrence_count": self.recurrence_count,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GoalSignal":
        return cls(
            signal_id=data["signal_id"],
            signal_type=SignalType(data["signal_type"]),
            domain=data["domain"],
            source=data.get("source", ""),
            evidence=data.get("evidence", {}),
            recurrence_count=data.get("recurrence_count", 1),
            first_seen=data.get("first_seen", ""),
            last_seen=data.get("last_seen", ""),
        )


# ============================================================================
# GOAL STORE
# ============================================================================

class GoalStore:
    """Persistent store for goals and signals.

    Provides a single source of truth for goal persistence with:
    - JSONL-based append-only storage
    - Efficient in-memory indexes
    - Query and filter capabilities
    - Statistics and reporting
    """

    def __init__(
        self,
        repo_root: Path | None = None,
        storage_dir: Path | None = None,
    ) -> None:
        """Initialize the goal store.

        Args:
            repo_root: Repository root path
            storage_dir: Optional custom storage directory
        """
        self._repo_root = Path(repo_root) if repo_root else Path.cwd()

        if storage_dir:
            self._goals_path = storage_dir / "goals.jsonl"
            self._signals_path = storage_dir / "signals.jsonl"
        else:
            self._goals_path = self._repo_root / "data" / "goals" / "goals.jsonl"
            self._signals_path = self._repo_root / "data" / "goals" / "signals.jsonl"

        self._goals: list[Goal] = []
        self._signals: list[GoalSignal] = []
        self._loaded: bool = False
        self._goal_index: dict[str, Goal] = {}
        self._signal_index: dict[str, GoalSignal] = {}

    # ------------------------------------------------------------------
    # Loading and Saving
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Load goals and signals from storage."""
        if self._loaded:
            return

        self._goals = self._load_jsonl(self._goals_path, Goal.from_dict)
        self._signals = self._load_jsonl(self._signals_path, GoalSignal.from_dict)

        # Build indexes
        self._goal_index = {g.goal_id: g for g in self._goals}
        self._signal_index = {s.signal_id: s for s in self._signals}

        self._loaded = True

    def _load_jsonl(self, path: Path, from_dict) -> list:
        """Load items from a JSONL file."""
        if not path.exists():
            return []
        items = []
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    items.append(from_dict(json.loads(line)))
        except (OSError, json.JSONDecodeError) as e:
            pass
        return items

    def _ensure_dir(self) -> None:
        """Ensure storage directory exists."""
        self._goals_path.parent.mkdir(parents=True, exist_ok=True)

    def _append_jsonl(self, path: Path, item: Any) -> None:
        """Append an item to a JSONL file."""
        self._ensure_dir()
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(item.to_dict(), ensure_ascii=False) + "\n")

    def save(self) -> None:
        """Save all goals and signals to storage."""
        self._ensure_dir()
        self._save_jsonl(self._goals_path, self._goals)
        self._save_jsonl(self._signals_path, self._signals)

    def _save_jsonl(self, path: Path, items: list) -> None:
        """Save items to a JSONL file."""
        lines = [json.dumps(item.to_dict(), ensure_ascii=False) for item in items]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # ------------------------------------------------------------------
    # Goal Operations
    # ------------------------------------------------------------------

    def add_goal(self, goal: Goal) -> Goal:
        """Add a new goal."""
        self.load()
        self._goals.append(goal)
        self._goal_index[goal.goal_id] = goal
        self._append_jsonl(self._goals_path, goal)
        return goal

    def get_goal(self, goal_id: str) -> Goal | None:
        """Get a goal by ID."""
        self.load()
        return self._goal_index.get(goal_id)

    def update_goal(self, goal: Goal) -> bool:
        """Update an existing goal."""
        self.load()
        if goal.goal_id not in self._goal_index:
            return False

        # Find and update in list
        for i, g in enumerate(self._goals):
            if g.goal_id == goal.goal_id:
                self._goals[i] = goal
                self._goal_index[goal.goal_id] = goal
                break

        # Rewrite file (could optimize with append-only)
        self._save_jsonl(self._goals_path, self._goals)
        return True

    def update_goal_status(
        self,
        goal_id: str,
        status: GoalStatus,
        notes: str = "",
    ) -> Goal | None:
        """Update a goal's status."""
        goal = self.get_goal(goal_id)
        if not goal:
            return None

        goal.status = status
        goal.updated_at = _now_iso()

        if status in (GoalStatus.COMPLETED, GoalStatus.FAILED, GoalStatus.RESOLVED, GoalStatus.REJECTED):
            goal.resolved_at = goal.updated_at

        if notes:
            goal.resolution_notes = notes

        self._save_jsonl(self._goals_path, self._goals)
        return goal

    def list_goals(
        self,
        domain: str | None = None,
        goal_type: GoalType | None = None,
        status: GoalStatus | None = None,
        priority: GoalPriority | None = None,
        limit: int = 100,
    ) -> list[Goal]:
        """List goals with optional filters."""
        self.load()
        results = []

        for goal in reversed(self._goals):
            if domain and goal.domain != domain:
                continue
            if goal_type and goal.goal_type != goal_type:
                continue
            if status and goal.status != status:
                continue
            if priority and goal.priority != priority:
                continue
            results.append(goal)
            if len(results) >= limit:
                break

        return results

    def get_active_goals(self) -> list[Goal]:
        """Get all active (proposed, accepted, or actionable) goals."""
        self.load()
        return [
            g for g in self._goals
            if g.status in (GoalStatus.PROPOSED, GoalStatus.ACCEPTED, GoalStatus.ACTIONABLE)
        ]

    def get_actionable_goals(self) -> list[Goal]:
        """Get all goals ready for task derivation."""
        self.load()
        return [g for g in self._goals if g.can_derive_tasks()]

    def find_similar_goal(
        self,
        domain: str,
        goal_type: GoalType,
        title_keywords: list[str],
        status_exclude: list[GoalStatus] | None = None,
    ) -> Goal | None:
        """Find a similar existing goal for deduplication."""
        self.load()
        exclude = status_exclude or [
            GoalStatus.COMPLETED,
            GoalStatus.FAILED,
            GoalStatus.RESOLVED,
            GoalStatus.REJECTED,
            GoalStatus.CANCELLED,
        ]

        for goal in self._goals:
            if goal.status in exclude:
                continue
            if goal.domain != domain:
                continue
            if goal.goal_type != goal_type:
                continue

            # Check title similarity
            goal_title_lower = goal.title.lower()
            matches = sum(1 for kw in title_keywords if kw.lower() in goal_title_lower)
            if matches >= len(title_keywords) * 0.6:
                return goal

        return None

    # ------------------------------------------------------------------
    # Signal Operations
    # ------------------------------------------------------------------

    def add_signal(self, signal: GoalSignal) -> GoalSignal:
        """Add a new signal."""
        self.load()
        self._signals.append(signal)
        self._signal_index[signal.signal_id] = signal
        self._append_jsonl(self._signals_path, signal)
        return signal

    def get_signal(self, signal_id: str) -> GoalSignal | None:
        """Get a signal by ID."""
        self.load()
        return self._signal_index.get(signal_id)

    def list_signals(
        self,
        domain: str | None = None,
        signal_type: SignalType | None = None,
        min_recurrence: int = 1,
        limit: int = 100,
    ) -> list[GoalSignal]:
        """List signals with optional filters."""
        self.load()
        results = []

        for signal in reversed(self._signals):
            if domain and signal.domain != domain:
                continue
            if signal_type and signal.signal_type != signal_type:
                continue
            if signal.recurrence_count < min_recurrence:
                continue
            results.append(signal)
            if len(results) >= limit:
                break

        return results

    def find_similar_signal(
        self,
        signal_type: SignalType,
        domain: str,
        evidence_key: str,
    ) -> GoalSignal | None:
        """Find a similar signal for aggregation."""
        self.load()

        for signal in self._signals:
            if signal.signal_type != signal_type:
                continue
            if signal.domain != domain:
                continue
            # Check if evidence matches
            for ev_value in signal.evidence.values():
                if isinstance(ev_value, str) and evidence_key in ev_value:
                    return signal

        return None

    def update_signal_recurrence(
        self,
        signal_id: str,
        increment: int = 1,
    ) -> GoalSignal | None:
        """Update a signal's recurrence count."""
        signal = self.get_signal(signal_id)
        if not signal:
            return None

        signal.recurrence_count += increment
        signal.last_seen = _now_iso()

        self._save_jsonl(self._signals_path, self._signals)
        return signal

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def get_stats(self) -> dict[str, Any]:
        """Get goal statistics."""
        self.load()

        stats = {
            "total_goals": len(self._goals),
            "total_signals": len(self._signals),
            "by_status": {},
            "by_domain": {},
            "by_type": {},
            "by_priority": {},
        }

        for goal in self._goals:
            stats["by_status"][goal.status.value] = stats["by_status"].get(goal.status.value, 0) + 1
            stats["by_domain"][goal.domain] = stats["by_domain"].get(goal.domain, 0) + 1
            stats["by_type"][goal.goal_type.value] = stats["by_type"].get(goal.goal_type.value, 0) + 1
            stats["by_priority"][goal.priority.value] = stats["by_priority"].get(goal.priority.value, 0) + 1

        return stats

    def clear(self) -> None:
        """Clear all goals and signals from memory (not disk)."""
        self._goals = []
        self._signals = []
        self._goal_index = {}
        self._signal_index = {}
        self._loaded = True


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _now_iso() -> str:
    """Return current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds") + "Z"


def generate_goal_id(goal_type: GoalType, domain: str) -> str:
    """Generate a unique goal ID."""
    timestamp = int(time.time())
    unique = uuid.uuid4().hex[:8]
    return f"goal_{goal_type.value}_{domain}_{timestamp}_{unique}"


def build_goal_store(repo_root: Path | None = None, storage_dir: Path | None = None) -> GoalStore:
    """Build a GoalStore instance.

    Args:
        repo_root: Repository root path
        storage_dir: Optional custom storage directory

    Returns:
        GoalStore instance
    """
    return GoalStore(repo_root=repo_root, storage_dir=storage_dir)


# ============================================================================
# FACTORY FUNCTIONS
# ============================================================================

def create_goal(
    goal_type: GoalType,
    title: str,
    description: str,
    domain: str,
    priority: GoalPriority = GoalPriority.MEDIUM,
    confidence: float = 0.5,
    impact_score: float = 0.5,
    evidence: list[GoalEvidence] | None = None,
    recommended_action: str = "",
) -> Goal:
    """Create a new goal with defaults."""
    return Goal(
        goal_id=generate_goal_id(goal_type, domain),
        goal_type=goal_type,
        title=title,
        description=description,
        domain=domain,
        priority=priority,
        confidence=confidence,
        impact_score=impact_score,
        evidence=evidence or [],
        recommended_action=recommended_action,
    )


def create_signal(
    signal_type: SignalType,
    domain: str,
    source: str,
    evidence: dict[str, Any] | None = None,
) -> GoalSignal:
    """Create a new signal with defaults."""
    signal_id = f"sig_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    return GoalSignal(
        signal_id=signal_id,
        signal_type=signal_type,
        domain=domain,
        source=source,
        evidence=evidence or {},
    )