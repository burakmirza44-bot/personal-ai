"""Execution-Based Self-Improvement Module.

Implements autonomous self-improvement based on execution analysis:
- Execution analysis to identify improvement opportunities
- Risk-based approval logic (autonomous vs human review)
- Automatic application of low-risk improvements
- Human review queue for high-risk changes
- Performance tracking and metrics

This enables the system to learn from execution patterns without
requiring human approval for every improvement.

Complements the existing self_improvement_loop.py which handles
code patches and sandbox validation.
"""

from __future__ import annotations

__all__ = [
    # Enums
    "ImprovementOpportunity",
    "RiskLevel",
    "ImprovementStatus",
    # Dataclasses
    "ExecutionAnalysis",
    "ImprovementApproval",
    "PendingImprovement",
    "ImprovementMetrics",
    # Core classes
    "ExecutionAnalyzer",
    "ImprovementRiskAssessor",
    "AutonomousImprover",
    "SelfImprovingExecutionAgent",
    "HumanReviewQueue",
]

import statistics
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Optional

if TYPE_CHECKING:
    from app.core.memory_store import MemoryStore


# ============================================================================
# ENUMS
# ============================================================================

class ImprovementOpportunity(str, Enum):
    """Types of improvement opportunities."""

    PARAMETER_OPTIMIZATION = "parameter_optimization"
    STEP_REORDERING = "step_reordering"
    FALLBACK_STRATEGY = "fallback_strategy"
    ERROR_PREVENTION = "error_prevention"
    PERFORMANCE_IMPROVEMENT = "performance_improvement"
    CONFIDENCE_BOOSTING = "confidence_boosting"
    RECIPE_SIMPLIFICATION = "recipe_simplification"
    RETRY_STRATEGY_UPDATE = "retry_strategy_update"


class RiskLevel(str, Enum):
    """Risk level for improvements."""

    LOW = "low"        # Safe, can approve autonomously
    MEDIUM = "medium"  # Requires validation
    HIGH = "high"      # Requires human approval


class ImprovementStatus(str, Enum):
    """Status of an improvement."""

    PENDING = "pending"
    APPLIED = "applied"
    REJECTED = "rejected"
    ROLLED_BACK = "rolled_back"


# ============================================================================
# DATACLASSES
# ============================================================================

@dataclass
class ExecutionAnalysis:
    """Analysis of a single execution."""

    execution_id: str
    goal: str
    success: bool
    duration_ms: float

    # Metrics
    steps_completed: int = 0
    steps_failed: int = 0
    retries_needed: int = 0
    errors_encountered: list[str] = field(default_factory=list)

    # Knowledge usage
    recipes_used: list[str] = field(default_factory=list)
    avg_recipe_confidence: float = 0.0
    knowledge_retrieved: list[str] = field(default_factory=list)

    # Opportunities identified
    opportunities: list[tuple[ImprovementOpportunity, str]] = field(default_factory=list)

    # Context
    domain: str = ""
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")

    @property
    def success_rate(self) -> float:
        """Success rate of steps."""
        total = self.steps_completed + self.steps_failed
        return self.steps_completed / total if total > 0 else 0.0

    @property
    def retry_ratio(self) -> float:
        """Ratio of retries to successful steps."""
        return self.retries_needed / self.steps_completed if self.steps_completed > 0 else 0.0

    @property
    def error_rate(self) -> float:
        """Rate of errors per step."""
        total = self.steps_completed + self.steps_failed
        return len(self.errors_encountered) / total if total > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "execution_id": self.execution_id,
            "goal": self.goal,
            "success": self.success,
            "duration_ms": self.duration_ms,
            "steps_completed": self.steps_completed,
            "steps_failed": self.steps_failed,
            "retries_needed": self.retries_needed,
            "errors_encountered": self.errors_encountered,
            "recipes_used": self.recipes_used,
            "avg_recipe_confidence": self.avg_recipe_confidence,
            "opportunities": [(o.value, d) for o, d in self.opportunities],
            "domain": self.domain,
            "timestamp": self.timestamp,
            "success_rate": self.success_rate,
            "retry_ratio": self.retry_ratio,
        }


@dataclass
class ImprovementApproval:
    """Approval decision for an improvement."""

    opportunity: ImprovementOpportunity
    description: str
    risk_level: RiskLevel
    requires_human_approval: bool
    confidence: float  # 0.0-1.0

    reason: str = ""
    suggested_action: str = ""
    applied: bool = False
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "opportunity": self.opportunity.value,
            "description": self.description,
            "risk_level": self.risk_level.value,
            "requires_human_approval": self.requires_human_approval,
            "confidence": self.confidence,
            "reason": self.reason,
            "suggested_action": self.suggested_action,
            "applied": self.applied,
            "timestamp": self.timestamp,
        }


@dataclass
class PendingImprovement:
    """Pending improvement awaiting human review."""

    improvement_id: str
    opportunity: ImprovementOpportunity
    description: str
    risk_level: RiskLevel
    confidence: float
    analysis: ExecutionAnalysis

    suggested_action: str = ""
    rationale: str = ""
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "improvement_id": self.improvement_id,
            "opportunity": self.opportunity.value,
            "description": self.description,
            "risk_level": self.risk_level.value,
            "confidence": self.confidence,
            "suggested_action": self.suggested_action,
            "rationale": self.rationale,
            "created_at": self.created_at,
            "analysis": self.analysis.to_dict(),
        }


@dataclass
class ImprovementMetrics:
    """Metrics for self-improvement system."""

    total_executions_analyzed: int = 0
    total_opportunities_found: int = 0
    autonomous_improvements_applied: int = 0
    improvements_pending_review: int = 0
    improvements_rejected: int = 0
    improvements_rolled_back: int = 0

    # By opportunity type
    by_opportunity: dict[str, int] = field(default_factory=dict)
    by_risk_level: dict[str, int] = field(default_factory=dict)

    # Success tracking
    improvement_success_rate: float = 0.0
    avg_confidence: float = 0.0

    # Timestamps
    last_analysis: str = ""
    last_improvement: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_executions_analyzed": self.total_executions_analyzed,
            "total_opportunities_found": self.total_opportunities_found,
            "autonomous_improvements_applied": self.autonomous_improvements_applied,
            "improvements_pending_review": self.improvements_pending_review,
            "improvements_rejected": self.improvements_rejected,
            "improvements_rolled_back": self.improvements_rolled_back,
            "by_opportunity": self.by_opportunity,
            "by_risk_level": self.by_risk_level,
            "improvement_success_rate": self.improvement_success_rate,
            "avg_confidence": self.avg_confidence,
            "last_analysis": self.last_analysis,
            "last_improvement": self.last_improvement,
        }

    @property
    def pending_ratio(self) -> float:
        """Ratio of pending to total opportunities."""
        if self.total_opportunities_found == 0:
            return 0.0
        return self.improvements_pending_review / self.total_opportunities_found

    @property
    def autonomous_ratio(self) -> float:
        """Ratio of autonomous to total improvements."""
        if self.total_opportunities_found == 0:
            return 0.0
        return self.autonomous_improvements_applied / self.total_opportunities_found


# ============================================================================
# EXECUTION ANALYZER
# ============================================================================

class ExecutionAnalyzer:
    """
    Analyze executions to identify improvement opportunities.

    Tracks execution history and identifies patterns that suggest
    opportunities for improvement.
    """

    def __init__(self, history_window: int = 100):
        """
        Initialize analyzer.

        Args:
            history_window: Maximum number of executions to keep in history
        """
        self.history_window = history_window
        self.execution_history: list[ExecutionAnalysis] = []

    def analyze_execution(
        self,
        execution_data: dict[str, Any],
    ) -> ExecutionAnalysis:
        """
        Analyze a single execution.

        Args:
            execution_data: Dictionary containing execution details

        Returns:
            ExecutionAnalysis with identified opportunities
        """
        analysis = ExecutionAnalysis(
            execution_id=str(execution_data.get("execution_id", "")),
            goal=str(execution_data.get("goal", "")),
            success=bool(execution_data.get("success", False)),
            duration_ms=float(execution_data.get("duration_ms", 0)),
            steps_completed=int(execution_data.get("steps_completed", 0)),
            steps_failed=int(execution_data.get("steps_failed", 0)),
            retries_needed=int(execution_data.get("retries_needed", 0)),
            errors_encountered=list(execution_data.get("errors", [])),
            recipes_used=list(execution_data.get("recipes_used", [])),
            avg_recipe_confidence=float(execution_data.get("avg_confidence", 0.0)),
            knowledge_retrieved=list(execution_data.get("knowledge_retrieved", [])),
            domain=str(execution_data.get("domain", "")),
        )

        # Identify opportunities
        analysis.opportunities = self._identify_opportunities(analysis, execution_data)

        # Store in history
        self.execution_history.append(analysis)

        # Trim history if needed
        if len(self.execution_history) > self.history_window:
            self.execution_history = self.execution_history[-self.history_window:]

        return analysis

    def _identify_opportunities(
        self,
        analysis: ExecutionAnalysis,
        execution_data: dict[str, Any],
    ) -> list[tuple[ImprovementOpportunity, str]]:
        """
        Identify improvement opportunities from execution.

        Args:
            analysis: The execution analysis
            execution_data: Raw execution data

        Returns:
            List of (opportunity_type, description) tuples
        """
        opportunities = []

        # Opportunity 1: High retry ratio → parameter optimization
        if analysis.retry_ratio > 0.2:
            opportunities.append((
                ImprovementOpportunity.PARAMETER_OPTIMIZATION,
                f"High retry ratio ({analysis.retry_ratio:.0%}): Parameters may need tuning"
            ))

        # Opportunity 2: Low recipe confidence → try different approach
        if analysis.avg_recipe_confidence < 0.6 and analysis.recipes_used:
            opportunities.append((
                ImprovementOpportunity.FALLBACK_STRATEGY,
                f"Low recipe confidence ({analysis.avg_recipe_confidence:.0%}): Consider alternative approach"
            ))

        # Opportunity 3: Specific errors recurring → add repair hint
        errors = execution_data.get("errors", [])
        if errors:
            error_counts: dict[str, int] = {}
            for error in errors:
                error_type = str(error).split(":")[0] if isinstance(error, str) else str(error)
                error_counts[error_type] = error_counts.get(error_type, 0) + 1

            for error_type, count in error_counts.items():
                if count > 1:
                    opportunities.append((
                        ImprovementOpportunity.ERROR_PREVENTION,
                        f"Error '{error_type}' occurred {count}x: Add prevention hint"
                    ))

        # Opportunity 4: Slow execution → optimize
        recent_times = [
            e.duration_ms for e in self.execution_history[-10:]
            if e.goal == analysis.goal
        ]

        if recent_times and len(recent_times) >= 3:
            avg_time = statistics.mean(recent_times)
            if analysis.duration_ms > avg_time * 1.5:
                opportunities.append((
                    ImprovementOpportunity.PERFORMANCE_IMPROVEMENT,
                    f"Slow execution ({analysis.duration_ms:.0f}ms vs avg {avg_time:.0f}ms)"
                ))

        # Opportunity 5: Success but low confidence → boost confidence
        if analysis.success and analysis.avg_recipe_confidence < 0.7 and analysis.recipes_used:
            opportunities.append((
                ImprovementOpportunity.CONFIDENCE_BOOSTING,
                f"Successful despite low confidence ({analysis.avg_recipe_confidence:.0%}): Update recipe confidence"
            ))

        # Opportunity 6: Many steps → simplification opportunity
        if analysis.steps_completed > 10 and analysis.success:
            opportunities.append((
                ImprovementOpportunity.RECIPE_SIMPLIFICATION,
                f"Recipe has {analysis.steps_completed} steps: Consider simplification"
            ))

        # Opportunity 7: High retry count with success → update retry strategy
        if analysis.retries_needed > 3 and analysis.success:
            opportunities.append((
                ImprovementOpportunity.RETRY_STRATEGY_UPDATE,
                f"Success after {analysis.retries_needed} retries: Adjust retry strategy"
            ))

        return opportunities

    def get_execution_trends(
        self,
        goal: str,
        window: int = 20,
    ) -> dict[str, Any]:
        """
        Get trends for a specific goal.

        Args:
            goal: Goal to analyze
            window: Number of recent executions to consider

        Returns:
            Dictionary with trend statistics
        """
        goal_executions = [
            e for e in self.execution_history[-window:]
            if e.goal == goal
        ]

        if not goal_executions:
            return {
                "total_executions": 0,
                "success_rate": 0.0,
                "avg_duration_ms": 0.0,
                "trend": "no_data",
            }

        successes = sum(1 for e in goal_executions if e.success)
        durations = [e.duration_ms for e in goal_executions if e.duration_ms > 0]

        # Calculate trend
        if len(goal_executions) >= 5:
            first_half = goal_executions[:len(goal_executions)//2]
            second_half = goal_executions[len(goal_executions)//2:]

            first_success = sum(1 for e in first_half if e.success) / len(first_half)
            second_success = sum(1 for e in second_half if e.success) / len(second_half)

            if second_success > first_success + 0.1:
                trend = "improving"
            elif second_success < first_success - 0.1:
                trend = "declining"
            else:
                trend = "stable"
        else:
            trend = "insufficient_data"

        return {
            "total_executions": len(goal_executions),
            "success_rate": successes / len(goal_executions),
            "avg_duration_ms": statistics.mean(durations) if durations else 0.0,
            "min_duration_ms": min(durations) if durations else 0.0,
            "max_duration_ms": max(durations) if durations else 0.0,
            "avg_retry_ratio": statistics.mean([e.retry_ratio for e in goal_executions]),
            "trend": trend,
        }

    def get_all_goals(self) -> list[str]:
        """Get all unique goals in history."""
        return list(set(e.goal for e in self.execution_history if e.goal))

    def get_summary(self) -> dict[str, Any]:
        """Get summary statistics of all executions."""
        if not self.execution_history:
            return {
                "total_executions": 0,
                "overall_success_rate": 0.0,
            }

        successes = sum(1 for e in self.execution_history if e.success)

        return {
            "total_executions": len(self.execution_history),
            "overall_success_rate": successes / len(self.execution_history),
            "unique_goals": len(self.get_all_goals()),
            "avg_duration_ms": statistics.mean([e.duration_ms for e in self.execution_history]),
        }


# ============================================================================
# RISK ASSESSOR
# ============================================================================

class ImprovementRiskAssessor:
    """
    Assess risk level of improvements.

    Determines if autonomous approval is safe based on execution
    history and improvement type.
    """

    # Risk profiles for different improvement types
    RISK_PROFILES: dict[ImprovementOpportunity, dict[str, Any]] = {
        ImprovementOpportunity.PARAMETER_OPTIMIZATION: {
            "base_risk": RiskLevel.LOW,
            "conditions": {
                "retry_ratio_threshold": 0.3,
                "history_size_threshold": 5,
                "min_success_rate": 0.5,
            }
        },
        ImprovementOpportunity.CONFIDENCE_BOOSTING: {
            "base_risk": RiskLevel.LOW,
            "conditions": {
                "success_required": True,
                "min_success_count": 3,
            }
        },
        ImprovementOpportunity.ERROR_PREVENTION: {
            "base_risk": RiskLevel.MEDIUM,
            "conditions": {
                "min_error_count": 2,
                "validation_required": True,
            }
        },
        ImprovementOpportunity.FALLBACK_STRATEGY: {
            "base_risk": RiskLevel.HIGH,
            "conditions": {
                "human_approval_required": True,
            }
        },
        ImprovementOpportunity.STEP_REORDERING: {
            "base_risk": RiskLevel.HIGH,
            "conditions": {
                "human_approval_required": True,
            }
        },
        ImprovementOpportunity.PERFORMANCE_IMPROVEMENT: {
            "base_risk": RiskLevel.MEDIUM,
            "conditions": {
                "validation_required": True,
                "rollback_available": True,
            }
        },
        ImprovementOpportunity.RECIPE_SIMPLIFICATION: {
            "base_risk": RiskLevel.MEDIUM,
            "conditions": {
                "validation_required": True,
            }
        },
        ImprovementOpportunity.RETRY_STRATEGY_UPDATE: {
            "base_risk": RiskLevel.LOW,
            "conditions": {
                "success_required": True,
                "min_success_count": 3,
            }
        },
    }

    def assess_improvement(
        self,
        opportunity: ImprovementOpportunity,
        analyzer: ExecutionAnalyzer,
        goal: str,
        execution_data: dict[str, Any],
    ) -> tuple[RiskLevel, bool]:
        """
        Assess risk level and determine if autonomous approval is safe.

        Args:
            opportunity: The improvement opportunity type
            analyzer: Execution analyzer with history
            goal: Goal being improved
            execution_data: Current execution data

        Returns:
            Tuple of (risk_level, can_approve_autonomously)
        """
        profile = self.RISK_PROFILES.get(
            opportunity,
            {"base_risk": RiskLevel.HIGH}
        )

        base_risk = profile.get("base_risk", RiskLevel.HIGH)
        conditions = profile.get("conditions", {})

        # Check conditions
        can_approve = self._check_conditions(
            opportunity,
            analyzer,
            goal,
            execution_data,
            conditions,
        )

        # Determine final risk and approval
        if can_approve and base_risk == RiskLevel.LOW:
            return RiskLevel.LOW, True
        elif can_approve and base_risk == RiskLevel.MEDIUM:
            return RiskLevel.MEDIUM, True  # Can auto-approve with validation
        else:
            return base_risk, False  # Requires human approval

    def _check_conditions(
        self,
        opportunity: ImprovementOpportunity,
        analyzer: ExecutionAnalyzer,
        goal: str,
        execution_data: dict[str, Any],
        conditions: dict[str, Any],
    ) -> bool:
        """Check if conditions allow autonomous approval."""
        # Check basic conditions
        if conditions.get("human_approval_required"):
            return False

        # Check success requirement
        if conditions.get("success_required"):
            if not execution_data.get("success"):
                return False

        # Check minimum success rate
        min_success = conditions.get("min_success_rate")
        if min_success:
            trends = analyzer.get_execution_trends(goal)
            if trends.get("success_rate", 0) < min_success:
                return False

        # Check minimum success count
        min_count = conditions.get("min_success_count")
        if min_count:
            trends = analyzer.get_execution_trends(goal)
            successful = int(trends.get("total_executions", 0) * trends.get("success_rate", 0))
            if successful < min_count:
                return False

        # Check history size
        history_threshold = conditions.get("history_size_threshold")
        if history_threshold:
            recent = [
                e for e in analyzer.execution_history[-20:]
                if e.goal == goal
            ]
            if len(recent) < history_threshold:
                return False

        # Check minimum error count for error prevention
        min_error_count = conditions.get("min_error_count")
        if min_error_count:
            errors = execution_data.get("errors", [])
            if len(errors) < min_error_count:
                return False

        return True

    def get_risk_description(self, risk_level: RiskLevel) -> str:
        """Get description for risk level."""
        descriptions = {
            RiskLevel.LOW: "Safe to apply autonomously. Changes are reversible and low impact.",
            RiskLevel.MEDIUM: "Requires validation. Changes may affect behavior but are recoverable.",
            RiskLevel.HIGH: "Requires human approval. Changes have significant impact or are hard to reverse.",
        }
        return descriptions.get(risk_level, "Unknown risk level")


# ============================================================================
# AUTONOMOUS IMPROVER
# ============================================================================

class AutonomousImprover:
    """
    Apply autonomous improvements without human approval.

    Only applies low-risk, well-validated improvements that meet
    the risk assessor's conditions.
    """

    def __init__(
        self,
        memory_store: Optional["MemoryStore"] = None,
        recipe_updater: Optional[Callable] = None,
    ):
        """
        Initialize improver.

        Args:
            memory_store: Memory store for recipe updates
            recipe_updater: Optional callback for recipe updates
        """
        self.memory_store = memory_store
        self.recipe_updater = recipe_updater
        self.improvement_history: list[dict[str, Any]] = []

    def apply_improvements(
        self,
        analysis: ExecutionAnalysis,
        analyzer: ExecutionAnalyzer,
        risk_assessor: ImprovementRiskAssessor,
    ) -> list[ImprovementApproval]:
        """
        Apply autonomous improvements for low-risk opportunities.

        Args:
            analysis: Execution analysis with opportunities
            analyzer: Execution analyzer for context
            risk_assessor: Risk assessor for approval decisions

        Returns:
            List of applied improvements
        """
        applied: list[ImprovementApproval] = []

        for opportunity, description in analysis.opportunities:
            # Assess risk
            risk, can_approve = risk_assessor.assess_improvement(
                opportunity,
                analyzer,
                analysis.goal,
                {
                    "success": analysis.success,
                    "errors": analysis.errors_encountered,
                }
            )

            confidence = self._calculate_confidence(opportunity, analyzer, analysis)

            approval = ImprovementApproval(
                opportunity=opportunity,
                description=description,
                risk_level=risk,
                requires_human_approval=not can_approve,
                confidence=confidence,
                reason=risk_assessor.get_risk_description(risk),
                suggested_action=self._get_suggested_action(opportunity, analysis),
            )

            # If low-risk and safe, apply
            if risk == RiskLevel.LOW and can_approve:
                success = self._apply_improvement(opportunity, analysis, analyzer)

                if success:
                    approval.applied = True
                    applied.append(approval)

                    self.improvement_history.append({
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                        "opportunity": opportunity.value,
                        "description": description,
                        "applied": True,
                        "confidence": confidence,
                    })

        return applied

    def _apply_improvement(
        self,
        opportunity: ImprovementOpportunity,
        analysis: ExecutionAnalysis,
        analyzer: ExecutionAnalyzer,
    ) -> bool:
        """
        Apply a specific improvement.

        Args:
            opportunity: Type of improvement
            analysis: Execution analysis
            analyzer: Execution analyzer

        Returns:
            True if improvement was applied successfully
        """
        if opportunity == ImprovementOpportunity.PARAMETER_OPTIMIZATION:
            return self._optimize_parameters(analysis, analyzer)

        elif opportunity == ImprovementOpportunity.CONFIDENCE_BOOSTING:
            return self._boost_confidence(analysis)

        elif opportunity == ImprovementOpportunity.ERROR_PREVENTION:
            return self._add_error_prevention(analysis)

        elif opportunity == ImprovementOpportunity.PERFORMANCE_IMPROVEMENT:
            return self._optimize_performance(analysis, analyzer)

        elif opportunity == ImprovementOpportunity.RETRY_STRATEGY_UPDATE:
            return self._update_retry_strategy(analysis)

        else:
            return False

    def _optimize_parameters(
        self,
        analysis: ExecutionAnalysis,
        analyzer: ExecutionAnalyzer,
    ) -> bool:
        """Optimize recipe parameters based on retry patterns."""
        if not self.memory_store or not analysis.recipes_used:
            return False

        for recipe_id in analysis.recipes_used:
            try:
                recipe = self.memory_store.get_recipe(recipe_id)
                if not recipe:
                    continue

                # Adjust parameters based on errors
                for error in analysis.errors_encountered:
                    if "timeout" in str(error).lower():
                        # Increase timeout
                        current_timeout = recipe.get("timeout", 30)
                        recipe["timeout"] = int(current_timeout * 1.5)

                    elif "memory" in str(error).lower():
                        # Reduce memory usage
                        recipe["reduce_memory"] = True

                # Update recipe
                if self.recipe_updater:
                    self.recipe_updater(recipe_id, recipe)
                else:
                    self.memory_store.update_recipe(recipe_id, recipe)

            except Exception:
                continue

        return True

    def _boost_confidence(self, analysis: ExecutionAnalysis) -> bool:
        """Increase confidence of recipes that succeeded."""
        if not self.memory_store or not analysis.recipes_used:
            return False

        for recipe_id in analysis.recipes_used:
            try:
                recipe = self.memory_store.get_recipe(recipe_id)
                if recipe and analysis.success:
                    # Increase confidence slightly
                    old_conf = recipe.get("confidence", 0.5)
                    new_conf = min(old_conf + 0.05, 0.99)  # Cap at 0.99
                    recipe["confidence"] = new_conf

                    if self.recipe_updater:
                        self.recipe_updater(recipe_id, recipe)
                    else:
                        self.memory_store.update_recipe(recipe_id, recipe)

            except Exception:
                continue

        return True

    def _add_error_prevention(self, analysis: ExecutionAnalysis) -> bool:
        """Add prevention hints for recurring errors."""
        if not self.memory_store or not analysis.recipes_used:
            return False

        for recipe_id in analysis.recipes_used:
            try:
                recipe = self.memory_store.get_recipe(recipe_id)
                if not recipe:
                    continue

                # Add hints for encountered errors
                hints = recipe.get("prevention_hints", [])

                for error in analysis.errors_encountered:
                    hint = f"Avoid: {str(error)[:100]}"
                    if hint not in hints:
                        hints.append(hint)

                recipe["prevention_hints"] = hints

                if self.recipe_updater:
                    self.recipe_updater(recipe_id, recipe)
                else:
                    self.memory_store.update_recipe(recipe_id, recipe)

            except Exception:
                continue

        return True

    def _optimize_performance(
        self,
        analysis: ExecutionAnalysis,
        analyzer: ExecutionAnalyzer,
    ) -> bool:
        """Optimize performance of slow-running recipes."""
        if not self.memory_store or not analysis.recipes_used:
            return False

        trends = analyzer.get_execution_trends(analysis.goal)

        if trends.get("trend") == "declining":
            for recipe_id in analysis.recipes_used:
                try:
                    recipe = self.memory_store.get_recipe(recipe_id)

                    if recipe:
                        recipe["parallelize"] = True
                        recipe["optimize"] = True

                        if self.recipe_updater:
                            self.recipe_updater(recipe_id, recipe)
                        else:
                            self.memory_store.update_recipe(recipe_id, recipe)

                except Exception:
                    continue

        return True

    def _update_retry_strategy(self, analysis: ExecutionAnalysis) -> bool:
        """Update retry strategy based on successful retries."""
        if not self.memory_store or not analysis.recipes_used:
            return False

        for recipe_id in analysis.recipes_used:
            try:
                recipe = self.memory_store.get_recipe(recipe_id)
                if recipe:
                    # Increase max retries if we succeeded after retries
                    current_max = recipe.get("max_retries", 3)
                    if analysis.retries_needed > current_max:
                        recipe["max_retries"] = analysis.retries_needed + 1

                    if self.recipe_updater:
                        self.recipe_updater(recipe_id, recipe)
                    else:
                        self.memory_store.update_recipe(recipe_id, recipe)

            except Exception:
                continue

        return True

    def _calculate_confidence(
        self,
        opportunity: ImprovementOpportunity,
        analyzer: ExecutionAnalyzer,
        analysis: ExecutionAnalysis,
    ) -> float:
        """
        Calculate confidence in improvement.

        Higher confidence = safer to apply autonomously.
        """
        base_confidence = 0.5

        # Factor 1: Execution success (0.0-0.2)
        if analysis.success:
            base_confidence += 0.2

        # Factor 2: History size (0.0-0.2)
        if len(analyzer.execution_history) > 20:
            base_confidence += 0.2
        elif len(analyzer.execution_history) > 10:
            base_confidence += 0.1

        # Factor 3: Success rate (0.0-0.2)
        trends = analyzer.get_execution_trends(analysis.goal)
        success_rate = trends.get("success_rate", 0)
        base_confidence += success_rate * 0.2

        # Factor 4: Opportunity type (0.0-0.1)
        if opportunity in (
            ImprovementOpportunity.CONFIDENCE_BOOSTING,
            ImprovementOpportunity.PARAMETER_OPTIMIZATION,
        ):
            base_confidence += 0.1

        return min(base_confidence, 1.0)

    def _get_suggested_action(
        self,
        opportunity: ImprovementOpportunity,
        analysis: ExecutionAnalysis,
    ) -> str:
        """Get suggested action for improvement type."""
        actions = {
            ImprovementOpportunity.PARAMETER_OPTIMIZATION: "Adjust parameters based on error patterns",
            ImprovementOpportunity.STEP_REORDERING: "Reorder steps for better success rate",
            ImprovementOpportunity.FALLBACK_STRATEGY: "Use alternative recipe approach",
            ImprovementOpportunity.ERROR_PREVENTION: "Add validation before error-prone step",
            ImprovementOpportunity.PERFORMANCE_IMPROVEMENT: "Enable parallel step execution",
            ImprovementOpportunity.CONFIDENCE_BOOSTING: "Increase recipe confidence score",
            ImprovementOpportunity.RECIPE_SIMPLIFICATION: "Simplify recipe steps",
            ImprovementOpportunity.RETRY_STRATEGY_UPDATE: "Adjust retry count based on history",
        }
        return actions.get(opportunity, "Review and apply improvement")

    def get_improvement_history(self, limit: int = 50) -> list[dict[str, Any]]:
        """Get recent improvement history."""
        return self.improvement_history[-limit:]


# ============================================================================
# HUMAN REVIEW QUEUE
# ============================================================================

class HumanReviewQueue:
    """
    Queue of improvements pending human review.

    Manages improvements that require human approval before
    being applied.
    """

    def __init__(self):
        """Initialize the review queue."""
        self.pending: list[PendingImprovement] = []
        self.reviewed: list[dict[str, Any]] = []

    def add_for_review(
        self,
        opportunity: ImprovementOpportunity,
        description: str,
        risk_level: RiskLevel,
        confidence: float,
        analysis: ExecutionAnalysis,
    ) -> str:
        """
        Add improvement for human review.

        Args:
            opportunity: The improvement opportunity
            description: Description of the improvement
            risk_level: Risk level assessment
            confidence: Confidence in the improvement
            analysis: Related execution analysis

        Returns:
            Improvement ID for tracking
        """
        improvement_id = f"imp_{int(time.time() * 1000)}"

        pending = PendingImprovement(
            improvement_id=improvement_id,
            opportunity=opportunity,
            description=description,
            risk_level=risk_level,
            confidence=confidence,
            analysis=analysis,
            suggested_action=self._get_suggested_action(opportunity, analysis),
            rationale=self._get_rationale(opportunity, analysis),
        )

        self.pending.append(pending)

        return improvement_id

    def review_improvement(
        self,
        improvement_id: str,
        approved: bool,
        human_notes: str = "",
        apply_callback: Optional[Callable] = None,
    ) -> bool:
        """
        Review a pending improvement.

        Args:
            improvement_id: ID of improvement to review
            approved: Whether to approve the improvement
            human_notes: Notes from human reviewer
            apply_callback: Optional callback to apply improvement

        Returns:
            True if review was processed
        """
        improvement = next(
            (i for i in self.pending if i.improvement_id == improvement_id),
            None
        )

        if not improvement:
            return False

        # Apply if approved
        success = False
        if approved and apply_callback:
            success = apply_callback(improvement)

        # Record decision
        self.reviewed.append({
            "improvement_id": improvement_id,
            "opportunity": improvement.opportunity.value,
            "approved": approved,
            "success": success,
            "human_notes": human_notes,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        })

        # Remove from pending
        self.pending = [i for i in self.pending if i.improvement_id != improvement_id]

        return True

    def get_pending_improvements(self, limit: int = 10) -> list[PendingImprovement]:
        """
        Get pending improvements for review.

        Args:
            limit: Maximum number to return

        Returns:
            List of pending improvements sorted by priority
        """
        # Sort by risk level (HIGH first) and confidence (highest first)
        risk_order = {RiskLevel.HIGH: 0, RiskLevel.MEDIUM: 1, RiskLevel.LOW: 2}

        sorted_pending = sorted(
            self.pending,
            key=lambda x: (risk_order.get(x.risk_level, 99), -x.confidence)
        )

        return sorted_pending[:limit]

    def get_reviewed_improvements(self, limit: int = 50) -> list[dict[str, Any]]:
        """Get recently reviewed improvements."""
        return self.reviewed[-limit:]

    def clear_pending(self) -> int:
        """Clear all pending improvements. Returns count cleared."""
        count = len(self.pending)
        self.pending.clear()
        return count

    def _get_suggested_action(
        self,
        opportunity: ImprovementOpportunity,
        analysis: ExecutionAnalysis,
    ) -> str:
        """Get suggested action for improvement type."""
        actions = {
            ImprovementOpportunity.PARAMETER_OPTIMIZATION: f"Increase timeout or adjust parameters based on {analysis.retries_needed} retries",
            ImprovementOpportunity.STEP_REORDERING: "Move error-prone step earlier in sequence",
            ImprovementOpportunity.FALLBACK_STRATEGY: "Use alternative recipe approach",
            ImprovementOpportunity.ERROR_PREVENTION: f"Add validation before step that causes: {', '.join(analysis.errors_encountered[:3])}",
            ImprovementOpportunity.PERFORMANCE_IMPROVEMENT: "Enable parallel step execution",
            ImprovementOpportunity.CONFIDENCE_BOOSTING: f"Increase recipe confidence from {analysis.avg_recipe_confidence:.0%}",
            ImprovementOpportunity.RECIPE_SIMPLIFICATION: f"Reduce from {analysis.steps_completed} steps",
            ImprovementOpportunity.RETRY_STRATEGY_UPDATE: f"Increase max retries beyond {analysis.retries_needed}",
        }
        return actions.get(opportunity, "Review and approve")

    def _get_rationale(
        self,
        opportunity: ImprovementOpportunity,
        analysis: ExecutionAnalysis,
    ) -> str:
        """Get rationale for improvement."""
        if opportunity == ImprovementOpportunity.PARAMETER_OPTIMIZATION:
            return f"Step failed {analysis.retries_needed}x with current parameters"

        elif opportunity == ImprovementOpportunity.STEP_REORDERING:
            if analysis.errors_encountered:
                return f"Error '{analysis.errors_encountered[0][:50]}' occurred during execution"

        elif opportunity == ImprovementOpportunity.CONFIDENCE_BOOSTING:
            return f"Successful execution with {analysis.avg_recipe_confidence:.0%} confidence"

        return "Improvement has potential to increase success rate"


# ============================================================================
# SELF-IMPROVING EXECUTION AGENT
# ============================================================================

class SelfImprovingExecutionAgent:
    """
    Agent with autonomous self-improvement capability.

    Integrates execution analysis, risk assessment, and improvement
    application into the execution loop.
    """

    def __init__(
        self,
        agent: Any = None,
        memory_store: Optional["MemoryStore"] = None,
        recipe_executor: Optional[Any] = None,
        history_window: int = 100,
    ):
        """
        Initialize self-improving agent.

        Args:
            agent: The underlying agent to wrap
            memory_store: Memory store for recipe updates
            recipe_executor: Recipe executor for improvements
            history_window: Maximum execution history size
        """
        self.agent = agent
        self.memory_store = memory_store
        self.recipe_executor = recipe_executor

        self.analyzer = ExecutionAnalyzer(history_window=history_window)
        self.risk_assessor = ImprovementRiskAssessor()
        self.improver = AutonomousImprover(memory_store=memory_store)
        self.review_queue = HumanReviewQueue()

        self.metrics = ImprovementMetrics()

    def execute_with_improvement(
        self,
        goal: str,
        domain: str,
        execution_callback: Optional[Callable] = None,
    ) -> tuple[Any, list[ImprovementApproval]]:
        """
        Execute goal and apply improvements.

        Args:
            goal: Goal to execute
            domain: Execution domain
            execution_callback: Optional callback for execution

        Returns:
            Tuple of (execution_result, applied_improvements)
        """
        # Step 1: Execute
        execution_data: dict[str, Any] = {
            "execution_id": f"exec_{int(time.time() * 1000)}",
            "goal": goal,
            "domain": domain,
        }

        if execution_callback:
            result = execution_callback(goal, domain)
            if isinstance(result, dict):
                execution_data.update(result)
        elif self.agent and hasattr(self.agent, "run"):
            result = self.agent.run(goal, domain)
            if isinstance(result, dict):
                execution_data.update(result)

        # Step 2: Analyze
        analysis = self.analyzer.analyze_execution(execution_data)

        # Update metrics
        self.metrics.total_executions_analyzed += 1
        self.metrics.total_opportunities_found += len(analysis.opportunities)
        self.metrics.last_analysis = datetime.utcnow().isoformat() + "Z"

        # Step 3: Identify improvements
        applied: list[ImprovementApproval] = []
        pending_for_review: list[tuple[ImprovementOpportunity, str]] = []

        for opportunity, description in analysis.opportunities:
            risk, can_approve = self.risk_assessor.assess_improvement(
                opportunity,
                self.analyzer,
                goal,
                {"success": analysis.success, "errors": analysis.errors_encountered},
            )

            # Track by opportunity type
            self.metrics.by_opportunity[opportunity.value] = (
                self.metrics.by_opportunity.get(opportunity.value, 0) + 1
            )
            self.metrics.by_risk_level[risk.value] = (
                self.metrics.by_risk_level.get(risk.value, 0) + 1
            )

            if risk == RiskLevel.LOW and can_approve:
                # Auto-apply low risk improvements
                pass  # Will be handled by improver.apply_improvements
            elif not can_approve:
                pending_for_review.append((opportunity, description))

        # Step 4: Apply autonomous improvements
        applied = self.improver.apply_improvements(
            analysis,
            self.analyzer,
            self.risk_assessor,
        )

        self.metrics.autonomous_improvements_applied += len(applied)

        if applied:
            self.metrics.last_improvement = datetime.utcnow().isoformat() + "Z"

        # Step 5: Queue high-risk for review
        for opportunity, description in pending_for_review:
            risk, _ = self.risk_assessor.assess_improvement(
                opportunity,
                self.analyzer,
                goal,
                {"success": analysis.success, "errors": analysis.errors_encountered},
            )

            confidence = self.improver._calculate_confidence(
                opportunity,
                self.analyzer,
                analysis,
            )

            self.review_queue.add_for_review(
                opportunity=opportunity,
                description=description,
                risk_level=risk,
                confidence=confidence,
                analysis=analysis,
            )

            self.metrics.improvements_pending_review += 1

        return execution_data, applied

    def review_pending(
        self,
        improvement_id: str,
        approved: bool,
        human_notes: str = "",
    ) -> bool:
        """
        Review a pending improvement.

        Args:
            improvement_id: ID of improvement to review
            approved: Whether to approve
            human_notes: Notes from reviewer

        Returns:
            True if review was processed
        """
        def apply_callback(improvement: PendingImprovement) -> bool:
            return self.improver._apply_improvement(
                improvement.opportunity,
                improvement.analysis,
                self.analyzer,
            )

        result = self.review_queue.review_improvement(
            improvement_id,
            approved,
            human_notes,
            apply_callback,
        )

        if result:
            if approved:
                self.metrics.autonomous_improvements_applied += 1
                self.metrics.improvements_pending_review -= 1
            else:
                self.metrics.improvements_rejected += 1
                self.metrics.improvements_pending_review -= 1

        return result

    def get_improvement_report(self) -> dict[str, Any]:
        """
        Get self-improvement report.

        Returns:
            Dictionary with improvement metrics and trends
        """
        recent_goals = list(set(
            e.goal for e in self.analyzer.execution_history[-20:]
            if e.goal
        ))

        return {
            "metrics": self.metrics.to_dict(),
            "pending_improvements": len(self.review_queue.pending),
            "execution_summary": self.analyzer.get_summary(),
            "recent_trends": {
                goal: self.analyzer.get_execution_trends(goal)
                for goal in recent_goals[:5]
            },
            "improvement_history": self.improver.get_improvement_history(limit=10),
        }

    def get_pending_for_review(self, limit: int = 10) -> list[PendingImprovement]:
        """Get pending improvements for human review."""
        return self.review_queue.get_pending_improvements(limit)