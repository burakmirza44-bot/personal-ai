"""Generic agent loop types and state machine.

Enhanced with long-horizon planning integration for subgoal-aware execution.

State Machine Flow:
    OBSERVING → INFERRING → PLANNING (if complex) → PROPOSING → EXECUTING → VERIFYING → REPLANNING (if needed) → SUCCEEDED/FAILED

Planning Integration:
    - PLANNING state triggers long-horizon plan decomposition
    - PlanState tracks subgoal progress
    - Subgoal-aware action selection in PROPOSING
    - Progress tracking and replanning triggers in VERIFYING
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from app.agent_core.long_horizon_plan import LongHorizonPlan, PlanConstraints
    from app.agent_core.plan_tracker import PlanTracker, TrackerState
    from app.agent_core.subgoal_models import Subgoal, SubgoalStatus

logger = logging.getLogger(__name__)


class LoopState(str, Enum):
    """Agent loop state machine states."""

    OBSERVING = "observing"
    INFERRING = "inferring"
    PLANNING = "planning"  # New: Decompose into subgoals
    PROPOSING = "proposing"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    REPLANNING = "replanning"  # New: Adjust plan based on failures
    RETRYING = "retrying"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    STOPPED = "stopped"


class ComplexityLevel(str, Enum):
    """Complexity classification for planning decisions."""

    TRIVIAL = "trivial"  # Single-step, no planning needed
    SIMPLE = "simple"  # 2-3 steps, optional planning
    MODERATE = "moderate"  # 4-6 steps, planning recommended
    COMPLEX = "complex"  # 7+ steps, planning required
    UNCERTAIN = "uncertain"  # Unknown scope, planning advisable


@dataclass(slots=True)
class PlanState:
    """Tracks state of long-horizon plan during execution.

    This is the bridge between LongHorizonPlan and AgentLoop execution.
    """

    plan_id: str | None = None
    has_plan: bool = False
    total_subgoals: int = 0
    completed_subgoals: int = 0
    failed_subgoals: int = 0
    current_subgoal_id: str | None = None
    current_subgoal_index: int = 0
    plan_steps_taken: int = 0
    plan_retries_used: int = 0
    last_verification_result: str = ""
    replan_count: int = 0
    max_replans: int = 2

    # Internal references (not serialized)
    _plan: "LongHorizonPlan | None" = field(default=None, repr=False)
    _tracker: "PlanTracker | None" = field(default=None, repr=False)

    def bind_plan(self, plan: "LongHorizonPlan", tracker: "PlanTracker") -> None:
        """Bind a plan and tracker to this state."""
        self._plan = plan
        self._tracker = tracker
        self.plan_id = plan.plan_id
        self.has_plan = True
        self.total_subgoals = len(plan.subgoals)
        self._sync_from_plan()

    def _sync_from_plan(self) -> None:
        """Sync state from bound plan."""
        if self._plan is None:
            return
        self.completed_subgoals = len(self._plan.completed_subgoal_ids())
        self.failed_subgoals = len(self._plan.failed_subgoal_ids())
        self.current_subgoal_id = self._plan.current_subgoal_id
        self.plan_steps_taken = self._plan.total_steps_taken
        self.plan_retries_used = self._plan.total_retries_used

        # Find current subgoal index
        if self.current_subgoal_id:
            for i, s in enumerate(self._plan.subgoals):
                if s.subgoal_id == self.current_subgoal_id:
                    self.current_subgoal_index = i + 1  # 1-indexed for display
                    break

    def current_subgoal(self) -> "Subgoal | None":
        """Get the current subgoal."""
        if self._plan is None:
            return None
        return self._plan.get_current_subgoal()

    def next_subgoal(self) -> "Subgoal | None":
        """Get the next pending subgoal."""
        if self._plan is None:
            return None
        return self._plan.get_next_pending_subgoal()

    def advance_subgoal(self) -> bool:
        """Advance to next subgoal. Returns True if advanced."""
        if self._tracker is None:
            return False

        next_sg = self._tracker.advance_plan()
        if next_sg:
            self._sync_from_plan()
            logger.info(
                f"Advanced to subgoal {next_sg.subgoal_id} "
                f"({self.current_subgoal_index}/{self.total_subgoals})"
            )
            return True
        return False

    def progress_pct(self) -> float:
        """Calculate progress percentage."""
        if self.total_subgoals == 0:
            return 0.0
        return (self.completed_subgoals / self.total_subgoals) * 100

    def progress_report(self) -> str:
        """Generate progress report string."""
        if not self.has_plan:
            return "No active plan"

        current = self.current_subgoal()
        current_title = current.title if current else "None"

        return (
            f"Plan: {self.plan_id} | "
            f"Progress: {self.completed_subgoals}/{self.total_subgoals} ({self.progress_pct():.0f}%) | "
            f"Current: {current_title} | "
            f"Failed: {self.failed_subgoals} | "
            f"Steps: {self.plan_steps_taken} | "
            f"Replans: {self.replan_count}/{self.max_replans}"
        )

    def can_replan(self) -> bool:
        """Check if replanning is still allowed."""
        return self.replan_count < self.max_replans

    def record_replan(self) -> None:
        """Record a replanning event."""
        self.replan_count += 1
        logger.warning(f"Replan triggered ({self.replan_count}/{self.max_replans})")

    def tracker_state(self) -> "TrackerState | None":
        """Get current tracker state snapshot."""
        if self._tracker is None:
            return None
        return self._tracker.current_plan_status()

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for logging/reporting."""
        return {
            "plan_id": self.plan_id,
            "has_plan": self.has_plan,
            "total_subgoals": self.total_subgoals,
            "completed_subgoals": self.completed_subgoals,
            "failed_subgoals": self.failed_subgoals,
            "current_subgoal_id": self.current_subgoal_id,
            "current_subgoal_index": self.current_subgoal_index,
            "plan_steps_taken": self.plan_steps_taken,
            "plan_retries_used": self.plan_retries_used,
            "last_verification_result": self.last_verification_result,
            "replan_count": self.replan_count,
            "progress_pct": round(self.progress_pct(), 1),
        }


@dataclass(slots=True)
class AgentStepResult:
    """Result of one agent loop step."""

    step_index: int
    loop_state: LoopState
    action_label: str
    executed: bool
    verified: bool
    passed: bool
    message: str
    state_summary: str = ""
    inferred_action: str = ""
    next_candidates: list[str] = field(default_factory=list)
    subgoal_id: str | None = None  # New: Track which subgoal this step belongs to
    plan_progress: str | None = None  # New: Progress report at this step


@dataclass(slots=True)
class AgentLoopResult:
    """Full result of a bounded agent loop run."""

    run_id: str
    domain: str
    target: str
    max_steps: int
    steps_taken: int
    final_state: LoopState
    succeeded: bool
    stopped_early: bool
    steps: list[AgentStepResult] = field(default_factory=list)
    plan_state: PlanState = field(default_factory=PlanState)  # New: Plan state at end

    def summary(self) -> str:
        plan_info = ""
        if self.plan_state.has_plan:
            plan_info = f" plan_progress={self.plan_state.progress_pct():.0f}%"
        return (
            f"run={self.run_id} domain={self.domain} target={self.target} "
            f"steps={self.steps_taken}/{self.max_steps} "
            f"final={self.final_state.value} succeeded={self.succeeded}{plan_info}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "domain": self.domain,
            "target": self.target,
            "max_steps": self.max_steps,
            "steps_taken": self.steps_taken,
            "final_state": self.final_state.value,
            "succeeded": self.succeeded,
            "stopped_early": self.stopped_early,
            "plan_state": self.plan_state.to_dict(),
            "steps": [
                {
                    "step_index": s.step_index,
                    "loop_state": s.loop_state.value,
                    "action_label": s.action_label,
                    "executed": s.executed,
                    "verified": s.verified,
                    "passed": s.passed,
                    "message": s.message,
                    "state_summary": s.state_summary,
                    "inferred_action": s.inferred_action,
                    "next_candidates": s.next_candidates,
                    "subgoal_id": s.subgoal_id,
                    "plan_progress": s.plan_progress,
                }
                for s in self.steps
            ],
        }


# ------------------------------------------------------------------
# Complexity Estimation
# ------------------------------------------------------------------


def estimate_complexity(
    goal: str,
    context: dict[str, Any] | None = None,
    known_patterns: list[str] | None = None,
) -> ComplexityLevel:
    """Estimate task complexity for planning decisions.

    Uses heuristics based on:
    - Goal text length and structure
    - Known complexity patterns
    - Context indicators

    Args:
        goal: The task goal description
        context: Optional context with hints about complexity
        known_patterns: List of known complexity patterns to match

    Returns:
        ComplexityLevel indicating estimated complexity
    """
    if not goal:
        return ComplexityLevel.TRIVIAL

    context = context or {}
    known_patterns = known_patterns or []

    goal_lower = goal.lower()
    word_count = len(goal.split())

    # Check for explicit complexity hints in context
    if "complexity_hint" in context:
        hint = context["complexity_hint"]
        if hint in ("trivial", "simple", "moderate", "complex", "uncertain"):
            return ComplexityLevel(hint)

    # Pattern-based detection
    complex_patterns = [
        "multi-step",
        "pipeline",
        "workflow",
        "sequence",
        "chain",
        "then",
        "after that",
        "followed by",
        "integrate",
        "combine",
        "merge",
        "synchronize",
        "orchestrate",
    ]

    moderate_patterns = [
        "create",
        "build",
        "setup",
        "configure",
        "implement",
        "design",
        "refactor",
        "optimize",
        "connect",
    ]

    simple_patterns = [
        "get",
        "fetch",
        "read",
        "write",
        "update",
        "delete",
        "remove",
        "list",
        "show",
        "check",
    ]

    # Count pattern matches
    complex_matches = sum(1 for p in complex_patterns if p in goal_lower)
    moderate_matches = sum(1 for p in moderate_patterns if p in goal_lower)
    simple_matches = sum(1 for p in simple_patterns if p in goal_lower)

    # Check for known complex patterns
    for pattern in known_patterns:
        if pattern.lower() in goal_lower:
            complex_matches += 1

    # Check for conjunctions indicating multiple steps
    conjunctions = ["and", "then", "also", "plus", "additionally"]
    conjunction_count = sum(1 for c in conjunctions if f" {c} " in f" {goal_lower} ")

    # Check for scope indicators
    scope_indicators = ["all", "multiple", "several", "many", "various"]
    scope_count = sum(1 for s in scope_indicators if s in goal_lower)

    # Decision logic
    total_complexity_score = (
        complex_matches * 3
        + moderate_matches * 2
        + conjunction_count * 2
        + scope_count * 1
        - simple_matches * 1
    )

    # Word count heuristic
    if word_count < 5:
        return ComplexityLevel.TRIVIAL
    elif word_count < 10 and total_complexity_score < 2:
        return ComplexityLevel.SIMPLE

    # Score-based decision
    if total_complexity_score >= 6:
        return ComplexityLevel.COMPLEX
    elif total_complexity_score >= 3:
        return ComplexityLevel.MODERATE
    elif total_complexity_score >= 1:
        return ComplexityLevel.SIMPLE
    else:
        return ComplexityLevel.TRIVIAL


def should_use_long_horizon_plan(
    goal: str,
    context: dict[str, Any] | None = None,
    complexity_threshold: ComplexityLevel = ComplexityLevel.MODERATE,
    force_planning: bool = False,
) -> tuple[bool, ComplexityLevel]:
    """Decide whether to use long-horizon planning.

    Args:
        goal: The task goal description
        context: Optional context for decision
        complexity_threshold: Minimum complexity to trigger planning
        force_planning: Override heuristics and force planning

    Returns:
        Tuple of (should_plan, estimated_complexity)
    """
    if force_planning:
        return True, ComplexityLevel.COMPLEX

    complexity = estimate_complexity(goal, context)

    # Threshold hierarchy
    thresholds = {
        ComplexityLevel.TRIVIAL: 0,
        ComplexityLevel.SIMPLE: 1,
        ComplexityLevel.MODERATE: 2,
        ComplexityLevel.COMPLEX: 3,
        ComplexityLevel.UNCERTAIN: 2,  # Default to planning for uncertain
    }

    should_plan = thresholds.get(complexity, 0) >= thresholds.get(complexity_threshold, 2)

    if should_plan:
        logger.info(f"Planning triggered for complexity={complexity.value}: {goal[:50]}...")

    return should_plan, complexity


# ------------------------------------------------------------------
# Agent Loop Monitor
# ------------------------------------------------------------------


@dataclass
class AgentLoopMonitor:
    """Monitors agent loop execution for progress tracking and logging.

    Provides:
    - Subgoal transition logging
    - Progress snapshots
    - Performance metrics
    """

    run_id: str
    domain: str
    start_time: str = ""
    _step_times: list[float] = field(default_factory=list, repr=False)
    _subgoal_transitions: list[dict[str, Any]] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        if not self.start_time:
            self.start_time = datetime.utcnow().isoformat(timespec="seconds") + "Z"

    def record_step(self, step_index: int, state: LoopState, duration_ms: float = 0) -> None:
        """Record a step execution."""
        self._step_times.append(duration_ms)
        logger.debug(f"[{self.run_id}] Step {step_index}: {state.value} ({duration_ms:.0f}ms)")

    def record_subgoal_transition(
        self,
        from_subgoal: str | None,
        to_subgoal: str | None,
        reason: str = "",
    ) -> None:
        """Record a subgoal transition."""
        transition = {
            "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "from": from_subgoal,
            "to": to_subgoal,
            "reason": reason,
        }
        self._subgoal_transitions.append(transition)
        logger.info(
            f"[{self.run_id}] Subgoal transition: {from_subgoal} → {to_subgoal} ({reason})"
        )

    def record_replan(
        self,
        trigger: str,
        old_plan_id: str | None,
        new_plan_id: str | None,
    ) -> None:
        """Record a replanning event."""
        logger.warning(
            f"[{self.run_id}] Replan triggered: {trigger} "
            f"(old={old_plan_id} new={new_plan_id})"
        )

    def get_metrics(self) -> dict[str, Any]:
        """Get performance metrics."""
        avg_step_time = (
            sum(self._step_times) / len(self._step_times)
            if self._step_times
            else 0
        )
        return {
            "run_id": self.run_id,
            "domain": self.domain,
            "start_time": self.start_time,
            "total_steps": len(self._step_times),
            "avg_step_time_ms": round(avg_step_time, 2),
            "subgoal_transitions": len(self._subgoal_transitions),
            "transitions": self._subgoal_transitions,
        }


# ------------------------------------------------------------------
# Subgoal-aware Action Selection
# ------------------------------------------------------------------


def propose_for_subgoal(
    subgoal: "Subgoal",
    context: dict[str, Any] | None = None,
    action_candidates: list[str] | None = None,
) -> tuple[str, list[str]]:
    """Select action based on current subgoal.

    Args:
        subgoal: Current subgoal being executed
        context: Execution context
        action_candidates: Available actions to choose from

    Returns:
        Tuple of (selected_action, remaining_candidates)
    """
    context = context or {}
    action_candidates = action_candidates or []

    # Stage-specific action preferences
    stage_preferences: dict[str, list[str]] = {
        "inspect": ["observe", "query", "list", "check"],
        "source": ["create", "add", "load", "import"],
        "control": ["configure", "set", "connect", "route"],
        "process": ["transform", "modify", "apply", "execute"],
        "bridge": ["connect", "bridge", "send", "sync"],
        "output": ["export", "save", "write", "render"],
        "verify": ["check", "validate", "test", "confirm"],
        "repair": ["fix", "repair", "adjust", "correct"],
        "cleanup": ["delete", "remove", "clear", "reset"],
        "custom": ["execute", "run", "perform"],
    }

    stage_type = subgoal.stage_type
    preferences = stage_preferences.get(stage_type, ["execute"])

    # Find matching action from candidates
    selected = "execute"  # Default
    for pref in preferences:
        for candidate in action_candidates:
            if pref in candidate.lower():
                selected = candidate
                break
        else:
            continue
        break

    # Build remaining candidates
    remaining = [a for a in action_candidates if a != selected]

    logger.debug(
        f"Proposed action '{selected}' for subgoal {subgoal.subgoal_id} "
        f"(stage={stage_type})"
    )

    return selected, remaining


def build_subgoal_context(
    subgoal: "Subgoal",
    plan_state: PlanState,
    execution_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build execution context for a subgoal.

    Combines:
    - Subgoal details
    - Plan progress
    - Execution history
    """
    execution_context = execution_context or {}

    return {
        "subgoal_id": subgoal.subgoal_id,
        "subgoal_title": subgoal.title,
        "subgoal_description": subgoal.description,
        "stage_type": subgoal.stage_type,
        "step_budget": subgoal.bounded_step_budget,
        "retry_budget": subgoal.bounded_retry_budget,
        "steps_taken": subgoal.steps_taken,
        "retries_used": subgoal.retries_used,
        "dependencies": subgoal.dependencies,
        "expected_outputs": subgoal.expected_outputs,
        "plan_progress": plan_state.progress_report(),
        "plan_completed": plan_state.completed_subgoals,
        "plan_total": plan_state.total_subgoals,
        **execution_context,
    }


# ------------------------------------------------------------------
# Replanning Logic
# ------------------------------------------------------------------


def should_trigger_replan(
    plan_state: PlanState,
    verification_result: str,
    failure_count: int = 0,
    consecutive_failures: int = 0,
    context: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    """Determine if replanning should be triggered.

    Args:
        plan_state: Current plan state
        verification_result: Result of last verification
        failure_count: Total failures in plan
        consecutive_failures: Consecutive failures without success
        context: Additional context

    Returns:
        Tuple of (should_replan, reason)
    """
    context = context or {}

    # Check replan budget
    if not plan_state.can_replan():
        return False, "Replan budget exhausted"

    # Consecutive failures trigger replan
    if consecutive_failures >= 3:
        return True, f"Consecutive failures ({consecutive_failures})"

    # Critical subgoal failure
    current = plan_state.current_subgoal()
    if current and current.priority == "critical" and verification_result == "failed":
        return True, "Critical subgoal failed"

    # High failure rate
    if plan_state.total_subgoals > 0:
        failure_rate = plan_state.failed_subgoals / plan_state.total_subgoals
        if failure_rate > 0.5:
            return True, f"High failure rate ({failure_rate:.0%})"

    # Blocked subgoal
    if current and hasattr(current, "status"):
        from app.agent_core.subgoal_models import SubgoalStatus

        if current.status == SubgoalStatus.BLOCKED:
            return True, "Current subgoal blocked"

    # Context-based triggers
    if context.get("force_replan"):
        return True, "Forced replan"

    if context.get("scope_changed"):
        return True, "Scope changed"

    return False, ""


def build_replan_context(
    plan_state: PlanState,
    trigger_reason: str,
    execution_history: list[AgentStepResult] | None = None,
) -> dict[str, Any]:
    """Build context for replanning decision.

    Includes:
    - What went wrong
    - What succeeded
    - Current progress
    - Constraints
    """
    execution_history = execution_history or []

    # Analyze failures
    failed_steps = [s for s in execution_history if not s.passed]
    successful_steps = [s for s in execution_history if s.passed]

    return {
        "trigger_reason": trigger_reason,
        "plan_id": plan_state.plan_id,
        "completed_subgoals": plan_state.completed_subgoals,
        "failed_subgoals": plan_state.failed_subgoals,
        "total_subgoals": plan_state.total_subgoals,
        "progress_pct": plan_state.progress_pct(),
        "replan_count": plan_state.replan_count,
        "failed_step_count": len(failed_steps),
        "successful_step_count": len(successful_steps),
        "last_verification": plan_state.last_verification_result,
        "recent_failures": [
            {"step": s.step_index, "action": s.action_label, "message": s.message}
            for s in failed_steps[-5:]  # Last 5 failures
        ],
    }