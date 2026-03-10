"""Integrated Runtime Loop Module.

Provides unified runtime orchestration with integrated error handling,
memory management, bridge health monitoring, and checkpoint/resume support.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.bridge_health import BridgeHealthReport, check_bridge_health
from app.core.checkpoint import Checkpoint, StepStatus
from app.core.checkpoint_lifecycle import CheckpointLifecycle, CheckpointBoundaryDetector
from app.core.checkpoint_resume import ResumeManager, ResumeResult, ResumeContext
from app.core.memory_runtime import (
    RuntimeMemoryContext,
    build_runtime_memory_context,
    build_enhanced_memory_context,
    get_memory_influence_summary,
    get_memory_reuse_summary,
    save_execution_result,
)
from app.learning.error_normalizer import NormalizedError, normalize_error, SourceLayer
from app.learning.error_loop_manager import (
    ErrorLoopManager,
    ErrorLoopResult,
    ErrorLoopState,
    create_error_loop_manager,
)
from app.learning.recipe_rag_bridge import (
    RecipeRAGBridge,
    RecipeKnowledge,
    RAGContext,
    MergedContext,
    build_recipe_knowledge_from_steps,
    build_rag_context_from_bundle,
)


@dataclass
class RuntimeLoopStep:
    """A single step in a runtime loop execution.

    Tracks action, verification, and retry information for each step.
    """

    step_index: int = 0
    action_label: str = ""
    target_context: str = ""
    provider: str = ""
    verification_status: str = ""
    retry_reason: str = ""
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "step_index": self.step_index,
            "action_label": self.action_label,
            "target_context": self.target_context,
            "provider": self.provider,
            "verification_status": self.verification_status,
            "retry_reason": self.retry_reason,
            "message": self.message,
        }


@dataclass
class RuntimeLoopResult:
    """Result of a runtime loop execution.

    Provides visibility into memory usage, bridge health, execution status,
    and checkpoint/resume metadata.
    """

    run_id: str = ""
    domain: str = ""
    task_id: str = ""
    bridge_reachable: bool = True
    provider: str = ""
    memory_items: list[str] = field(default_factory=list)
    error_memory_items: list[str] = field(default_factory=list)
    final_status: str = ""
    verification_status: str = ""
    steps: list[RuntimeLoopStep] = field(default_factory=list)
    retries_attempted: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    # Legacy fields for backward compatibility
    success: bool = False
    memory_retrieved: bool = False
    memory_items_used: int = 0
    success_patterns_used: int = 0
    failure_patterns_used: int = 0
    repair_patterns_used: int = 0
    memory_writeback_done: bool = False
    bridge_health_summary: dict[str, Any] = field(default_factory=dict)
    error_count: int = 0
    normalized_errors: list[dict] = field(default_factory=list)
    execution_time_ms: float = 0.0
    # Enhanced memory reuse metadata
    memory_influence_weight: str = "none"
    retrieval_confidence: float = 0.0
    retrieval_reasoning: str = ""
    bridge_patterns_used: int = 0
    backend_patterns_used: int = 0
    memory_influenced_decision: bool = False
    memory_reuse_helped: bool = False
    success_hints_applied: int = 0
    failure_warnings_applied: int = 0
    repair_strategies_applied: int = 0
    # Checkpoint/resume metadata
    checkpoint_created: bool = False
    checkpoint_id: str | None = None
    checkpoint_saved: bool = False
    resumed_from_checkpoint: bool = False
    resume_checkpoint_id: str | None = None
    resume_success: bool = False
    resume_context: dict[str, Any] | None = None
    replayed_steps: list[str] = field(default_factory=list)
    recovery_mode: str = ""

    # Error loop metadata
    error_loop_id: str = ""
    normalized_error_recorded: bool = False
    normalized_error_count: int = 0
    normalized_error_summary: dict[str, Any] = field(default_factory=dict)
    retry_decision_summary: dict[str, Any] = field(default_factory=dict)
    repair_attempted: bool = False
    repair_summary: dict[str, Any] = field(default_factory=dict)
    fix_pattern_candidate_generated: bool = False
    fix_pattern_promoted: bool = False
    fix_pattern_id: str = ""
    promoted_fix_pattern_count: int = 0
    no_progress_detected: bool = False
    retry_exhausted: bool = False
    final_error_loop_status: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "success": self.success,
            "memory_retrieved": self.memory_retrieved,
            "memory_items_used": self.memory_items_used,
            "success_patterns_used": self.success_patterns_used,
            "failure_patterns_used": self.failure_patterns_used,
            "repair_patterns_used": self.repair_patterns_used,
            "memory_writeback_done": self.memory_writeback_done,
            "bridge_health_summary": self.bridge_health_summary,
            "error_count": self.error_count,
            "normalized_errors": self.normalized_errors,
            "execution_time_ms": self.execution_time_ms,
            "domain": self.domain,
            "task_id": self.task_id,
            # Enhanced memory reuse metadata
            "memory_influence_weight": self.memory_influence_weight,
            "retrieval_confidence": self.retrieval_confidence,
            "retrieval_reasoning": self.retrieval_reasoning,
            "bridge_patterns_used": self.bridge_patterns_used,
            "backend_patterns_used": self.backend_patterns_used,
            "memory_influenced_decision": self.memory_influenced_decision,
            "memory_reuse_helped": self.memory_reuse_helped,
            "success_hints_applied": self.success_hints_applied,
            "failure_warnings_applied": self.failure_warnings_applied,
            "repair_strategies_applied": self.repair_strategies_applied,
            # Checkpoint/resume metadata
            "checkpoint_created": self.checkpoint_created,
            "checkpoint_id": self.checkpoint_id,
            "checkpoint_saved": self.checkpoint_saved,
            "resumed_from_checkpoint": self.resumed_from_checkpoint,
            "resume_checkpoint_id": self.resume_checkpoint_id,
            "resume_success": self.resume_success,
            "resume_context": self.resume_context,
            "replayed_steps": self.replayed_steps,
            "recovery_mode": self.recovery_mode,
            # Error loop metadata
            "error_loop_id": self.error_loop_id,
            "normalized_error_recorded": self.normalized_error_recorded,
            "normalized_error_count": self.normalized_error_count,
            "normalized_error_summary": self.normalized_error_summary,
            "retry_decision_summary": self.retry_decision_summary,
            "repair_attempted": self.repair_attempted,
            "repair_summary": self.repair_summary,
            "fix_pattern_candidate_generated": self.fix_pattern_candidate_generated,
            "fix_pattern_promoted": self.fix_pattern_promoted,
            "fix_pattern_id": self.fix_pattern_id,
            "promoted_fix_pattern_count": self.promoted_fix_pattern_count,
            "no_progress_detected": self.no_progress_detected,
            "retry_exhausted": self.retry_exhausted,
            "final_error_loop_status": self.final_error_loop_status,
        }


class IntegratedRuntimeLoop:
    """Unified runtime loop with integrated error, memory, bridge, and checkpoint systems.

    This class provides a single entry point for task execution that:
    1. Attempts to resume from checkpoint if available
    2. Checks bridge health before execution
    3. Retrieves memory context before execution
    4. Creates checkpoints at safe boundaries
    5. Normalizes all errors into the error loop
    6. Saves results to memory after execution
    7. Provides visibility into all systems via RuntimeLoopResult
    """

    def __init__(
        self,
        domain: str,
        repo_root: str = ".",
        enable_memory: bool = True,
        enable_bridge_health: bool = True,
        enable_checkpoints: bool = True,
        task_id: str = "",
        session_id: str = "",
        plan_id: str = "",
    ):
        """Initialize the integrated runtime loop.

        Args:
            domain: Execution domain ("touchdesigner" or "houdini")
            repo_root: Repository root for memory stores
            enable_memory: Whether to enable memory retrieval/writeback
            enable_bridge_health: Whether to enable bridge health checks
            enable_checkpoints: Whether to enable checkpoint/resume
            task_id: Task ID for checkpoint tracking
            session_id: Session ID for checkpoint tracking
            plan_id: Plan ID for checkpoint tracking
        """
        self._domain = domain
        self._repo_root = repo_root
        self._enable_memory = enable_memory
        self._enable_bridge_health = enable_bridge_health
        self._enable_checkpoints = enable_checkpoints
        self._task_id = task_id
        self._session_id = session_id or f"session_{int(time.time())}"
        self._plan_id = plan_id
        self._error_memory: list[NormalizedError] = []

        # Initialize error loop manager
        self._error_loop_manager: ErrorLoopManager | None = None

        # Initialize checkpoint systems
        self._checkpoint_lifecycle: CheckpointLifecycle | None = None
        self._resume_manager: ResumeManager | None = None
        self._boundary_detector: CheckpointBoundaryDetector | None = None
        self._current_checkpoint: Checkpoint | None = None
        self._resume_result: ResumeResult | None = None

        if self._enable_checkpoints:
            self._checkpoint_lifecycle = CheckpointLifecycle(repo_root=repo_root)
            self._resume_manager = ResumeManager(
                lifecycle=self._checkpoint_lifecycle,
                repo_root=repo_root,
            )
            self._boundary_detector = CheckpointBoundaryDetector()

    def _get_error_loop_manager(self) -> ErrorLoopManager:
        """Get or create the error loop manager."""
        if self._error_loop_manager is None:
            self._error_loop_manager = create_error_loop_manager(
                domain=self._domain,
                task_id=self._task_id,
                session_id=self._session_id,
                repo_root=Path(self._repo_root),
            )
        return self._error_loop_manager

    @property
    def domain(self) -> str:
        """Get the execution domain."""
        return self._domain

    @property
    def current_checkpoint(self) -> Checkpoint | None:
        """Get the current checkpoint."""
        return self._current_checkpoint

    def process_error(
        self,
        error: str | Exception | NormalizedError,
        source_layer: SourceLayer = SourceLayer.UNKNOWN,
        context: dict[str, Any] | None = None,
    ) -> ErrorLoopResult:
        """Process an error through the error loop.

        This is the unified entry point for error handling in the runtime loop.
        Errors are normalized, retry/repair decisions are evaluated, and
        fix patterns are looked up.

        Args:
            error: Error to process
            source_layer: Where the error originated
            context: Additional context

        Returns:
            ErrorLoopResult with processing outcome
        """
        manager = self._get_error_loop_manager()
        return manager.process_error(
            raw_error=error,
            source_layer=source_layer,
            context=context,
        )

    def get_error_loop_summary(self) -> dict[str, Any]:
        """Get summary of error loop state.

        Returns:
            Dictionary with error loop statistics
        """
        if self._error_loop_manager is None:
            return {"error_loop_enabled": False}

        state = self._error_loop_manager.state
        return {
            "error_loop_enabled": True,
            "loop_id": state.loop_id,
            "error_count": state.error_count,
            "retry_count": state.retry_count,
            "repair_attempted": state.repair_attempted,
            "fix_pattern_found": state.fix_pattern_found,
            "final_outcome": state.final_outcome,
        }

    def _update_result_with_error_loop(
        self,
        result: RuntimeLoopResult,
        error_loop_result: ErrorLoopResult | None = None,
    ) -> None:
        """Update a RuntimeLoopResult with error loop metadata.

        Args:
            result: Result to update
            error_loop_result: Optional error loop result to include
        """
        if self._error_loop_manager is None:
            return

        state = self._error_loop_manager.state
        result.error_loop_id = state.loop_id
        result.normalized_error_count = state.error_count
        result.repair_attempted = state.repair_attempted
        result.fix_pattern_promoted = state.fix_pattern_promoted
        result.no_progress_detected = state.current_error.no_progress_related if state.current_error else False
        result.retry_exhausted = state.retry_count >= state.max_retries
        result.final_error_loop_status = state.final_outcome

        if state.current_error:
            result.normalized_error_summary = {
                "error_id": state.current_error.error_id,
                "error_type": state.current_error.normalized_error_type.value,
                "error_category": state.current_error.error_category.value,
                "recoverable": state.current_error.recoverable,
                "fix_hint": state.current_error.fix_hint,
            }

        if self._error_loop_manager.retry_strategy:
            result.retry_decision_summary = {
                "strategy_type": self._error_loop_manager.retry_strategy.strategy_type.value,
                "rationale": self._error_loop_manager.retry_strategy.rationale,
                "confidence": self._error_loop_manager.retry_strategy.confidence,
            }

        if error_loop_result:
            result.normalized_error_recorded = error_loop_result.normalized_error_count > 0
            result.fix_pattern_candidate_generated = error_loop_result.fix_pattern_candidate_generated
            result.fix_pattern_id = error_loop_result.fix_pattern_id

    def attempt_resume(
        self,
        force_checkpoint_id: str | None = None,
    ) -> ResumeResult | None:
        """Attempt to resume from a checkpoint.

        Args:
            force_checkpoint_id: Optional specific checkpoint ID to use

        Returns:
            ResumeResult if resume was attempted, None if checkpoints disabled
        """
        if not self._enable_checkpoints or not self._resume_manager:
            return None

        if not self._task_id:
            return None

        result = self._resume_manager.attempt_resume(
            task_id=self._task_id,
            plan_id=self._plan_id,
            session_id=self._session_id,
            force_checkpoint_id=force_checkpoint_id,
        )

        self._resume_result = result

        if result.success and result.resume_context:
            self._current_checkpoint = result.resume_context.checkpoint

        return result

    def create_checkpoint(
        self,
        current_goal: str,
        steps: list[dict[str, Any]] | None = None,
        reason: str = "manual",
    ) -> Checkpoint | None:
        """Create a checkpoint for the current execution.

        Args:
            current_goal: Current goal being pursued
            steps: Optional list of step definitions
            reason: Reason for creating checkpoint

        Returns:
            Checkpoint or None if checkpoints disabled
        """
        if not self._enable_checkpoints or not self._checkpoint_lifecycle:
            return None

        if not self._task_id:
            return None

        # Get bridge health if enabled
        bridge_health = None
        if self._enable_bridge_health:
            bridge_health = self.check_bridge_health()

        # Get memory context if enabled
        memory_context = None
        if self._enable_memory:
            memory_context = self.retrieve_memory(current_goal)

        checkpoint = self._checkpoint_lifecycle.create_checkpoint(
            task_id=self._task_id,
            session_id=self._session_id,
            plan_id=self._plan_id or f"plan_{self._task_id}",
            domain=self._domain,
            current_goal=current_goal,
            steps=steps,
            bridge_health=bridge_health,
            memory_context=memory_context,
            checkpoint_reason=reason,
        )

        self._current_checkpoint = checkpoint
        return checkpoint

    def save_checkpoint(self) -> bool:
        """Save the current checkpoint to disk.

        Returns:
            True if checkpoint was saved
        """
        if not self._enable_checkpoints or not self._checkpoint_lifecycle:
            return False

        if not self._current_checkpoint:
            return False

        try:
            self._checkpoint_lifecycle.save_checkpoint(self._current_checkpoint)
            return True
        except Exception:
            return False

    def update_checkpoint_for_step(
        self,
        step_id: str,
        status: StepStatus,
        result: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
        verified: bool = False,
    ) -> bool:
        """Update the checkpoint for a step completion.

        Args:
            step_id: Step ID
            status: New step status
            result: Optional step result
            error: Optional error information
            verified: Whether step was verified

        Returns:
            True if checkpoint was updated
        """
        if not self._enable_checkpoints or not self._checkpoint_lifecycle:
            return False

        if not self._current_checkpoint:
            return False

        try:
            self._checkpoint_lifecycle.update_checkpoint(
                checkpoint=self._current_checkpoint,
                step_id=step_id,
                step_status=status,
                step_result=result,
                error=error,
                verified=verified,
            )
            return True
        except Exception:
            return False

    def check_bridge_health(
        self,
        host: str = "127.0.0.1",
        port: int | None = None,
    ) -> BridgeHealthReport | None:
        """Check bridge health if enabled.

        Args:
            host: Bridge host address
            port: Bridge port (defaults based on domain)

        Returns:
            BridgeHealthReport or None if disabled
        """
        if not self._enable_bridge_health:
            return None

        if port is None:
            port = 9988 if self._domain == "touchdesigner" else 9989

        return check_bridge_health(
            domain=self._domain,
            host=host,
            port=port,
        )

    def retrieve_memory(
        self,
        query: str,
        max_success: int = 3,
        max_failure: int = 3,
        retrieval_mode: str = "pre_execution",
        action_type: str = "",
        failure_context: dict[str, Any] | None = None,
    ) -> RuntimeMemoryContext:
        """Retrieve memory context if enabled.

        Uses the enhanced MemoryReuseAdapter for consistent retrieval
        across all runtime paths with ranking and influence tracking.

        Args:
            query: Query string to match patterns
            max_success: Maximum success patterns to retrieve
            max_failure: Maximum failure patterns to retrieve
            retrieval_mode: Mode of retrieval (pre_execution, pre_retry, etc.)
            action_type: Type of action being considered
            failure_context: Context for retry/repair scenarios

        Returns:
            RuntimeMemoryContext with retrieved patterns and influence metadata
        """
        if not self._enable_memory:
            return RuntimeMemoryContext(
                domain=self._domain,
                query=query,
                memory_influenced=False,
            )

        # Use enhanced retrieval with MemoryReuseAdapter
        return build_enhanced_memory_context(
            domain=self._domain,
            task_id=self._task_id,
            query=query,
            retrieval_mode=retrieval_mode,
            repo_root=self._repo_root,
            session_id=self._session_id,
            action_type=action_type,
            failure_context=failure_context,
        )

    def execute_step_with_retry(
        self,
        step: dict[str, Any],
        max_retries: int = 3,
        task_id: str = "",
        step_id: str | None = None,
    ) -> RuntimeLoopResult:
        """Execute a single step with retry, error normalization, and checkpoint support.

        Routes execution to domain-specific bridge executors when available.
        For "touchdesigner" domain, uses TDBridgeExecutor for live bridge calls.
        For other domains, uses stub execution.

        Args:
            step: Step definition to execute
            max_retries: Maximum retry attempts
            task_id: Task ID for tracking
            step_id: Optional step ID for checkpoint tracking

        Returns:
            RuntimeLoopResult with execution status
        """
        start_time = time.perf_counter()
        result = RuntimeLoopResult(
            domain=self._domain,
            task_id=task_id or self._task_id,
        )

        # Track checkpoint metadata
        if self._current_checkpoint:
            result.checkpoint_id = self._current_checkpoint.checkpoint_id

        if self._resume_result:
            result.resumed_from_checkpoint = self._resume_result.success
            result.resume_checkpoint_id = self._resume_result.checkpoint_id
            result.resume_success = self._resume_result.success
            result.recovery_mode = self._resume_result.recovery_mode
            result.replayed_steps = self._resume_result.replayed_steps

        # Retrieve memory before execution
        query = step.get("description", step.get("action", ""))
        action_type = step.get("action", "")
        runtime_memory = self.retrieve_memory(
            query=query,
            action_type=action_type,
            retrieval_mode="pre_execution",
        )
        result.memory_retrieved = runtime_memory.memory_influenced
        result.memory_items_used = runtime_memory.total_patterns
        result.success_patterns_used = runtime_memory.success_pattern_count
        result.failure_patterns_used = runtime_memory.failure_pattern_count
        result.repair_patterns_used = runtime_memory.repair_pattern_count
        # Populate enhanced memory metadata
        result.memory_influence_weight = runtime_memory.memory_influence_weight
        result.retrieval_confidence = runtime_memory.retrieval_confidence
        result.retrieval_reasoning = runtime_memory.retrieval_reasoning
        result.bridge_patterns_used = runtime_memory.bridge_patterns_used
        result.backend_patterns_used = runtime_memory.backend_patterns_used
        result.memory_influenced_decision = runtime_memory.memory_influenced
        result.success_hints_applied = len(runtime_memory.success_hints)
        result.failure_warnings_applied = len(runtime_memory.failure_warnings)
        result.repair_strategies_applied = len(runtime_memory.repair_strategies)

        # Check bridge health if needed
        if step.get("requires_bridge", False):
            bridge_health = self.check_bridge_health()
            if bridge_health:
                result.bridge_health_summary = bridge_health.to_dict()

                if not bridge_health.is_healthy:
                    # Normalize bridge failure
                    normalized = normalize_error(
                        Exception(f"Bridge unhealthy: {bridge_health.last_error_message}"),
                        context={
                            "domain": self._domain,
                            "task_id": task_id or self._task_id,
                            "bridge_health": bridge_health.to_dict(),
                        },
                    )
                    self._error_memory.append(normalized)
                    result.normalized_errors.append(normalized.to_dict())
                    result.error_count = 1
                    result.execution_time_ms = (time.perf_counter() - start_time) * 1000
                    return result

        # Mark step as started in checkpoint
        if step_id and self._enable_checkpoints:
            self.update_checkpoint_for_step(
                step_id=step_id,
                status=StepStatus.IN_PROGRESS,
            )

        # Execute with retry using ErrorLoopManager
        last_error: Exception | None = None
        verified = False
        error_loop_result: ErrorLoopResult | None = None

        for attempt in range(max_retries):
            try:
                # Domain-specific execution routing
                if self._domain == "touchdesigner":
                    # Use TDBridgeExecutor for TouchDesigner domain
                    execution_result = self._execute_step_touchdesigner(step, attempt)
                    result.success = execution_result["success"]
                    verified = execution_result.get("verified", False)
                    result.metadata["bridge_response"] = execution_result.get("bridge_response", {})
                else:
                    # Stub execution for other domains
                    result.success = True
                    verified = step.get("verify", False)

                result.execution_time_ms = (time.perf_counter() - start_time) * 1000

                # Record recovery success if we had previous errors
                if attempt > 0 and self._error_loop_manager and last_error:
                    self._error_loop_manager.record_recovery_success(
                        verification_result={"verified": verified, "attempt": attempt + 1},
                        fix_summary=f"Retry succeeded after {attempt} attempts",
                    )

                # Mark step as completed in checkpoint
                if step_id and self._enable_checkpoints:
                    self.update_checkpoint_for_step(
                        step_id=step_id,
                        status=StepStatus.COMPLETED_VERIFIED if verified else StepStatus.COMPLETED,
                        result={"success": True, "attempts": attempt + 1},
                        verified=verified,
                    )
                    self.save_checkpoint()

                # Save success to memory
                if self._enable_memory:
                    save_execution_result(
                        domain=self._domain,
                        query=query,
                        success=True,
                        result_data={
                            "description": f"Executed step: {step.get('action', 'unknown')}",
                            "attempts": attempt + 1,
                            "checkpoint_id": self._current_checkpoint.checkpoint_id if self._current_checkpoint else None,
                        },
                        repo_root=self._repo_root,
                    )
                    result.memory_writeback_done = True

                # Update result with error loop metadata
                if self._error_loop_manager:
                    self._update_result_with_error_loop(result, error_loop_result)

                return result

            except Exception as e:
                last_error = e

                # Process error through ErrorLoopManager
                if self._error_loop_manager:
                    error_loop_result = self.process_error(
                        error=e,
                        source_layer=SourceLayer.EXECUTION,
                        context={
                            "domain": self._domain,
                            "task_id": task_id or self._task_id,
                            "attempt": attempt + 1,
                            "step": step,
                            "max_retries": max_retries,
                        },
                    )
                    # Get normalized error for legacy tracking
                    if self._error_loop_manager.current_error:
                        normalized = self._error_loop_manager.current_error
                        self._error_memory.append(normalized)
                        result.normalized_errors.append(normalized.to_dict())
                else:
                    # Fallback to basic normalization
                    normalized = normalize_error(
                        e,
                        context={
                            "domain": self._domain,
                            "task_id": task_id or self._task_id,
                            "attempt": attempt + 1,
                            "step": step,
                        },
                    )
                    self._error_memory.append(normalized)
                    result.normalized_errors.append(normalized.to_dict())

                result.error_count += 1

                # Check if we should retry using ErrorLoopManager
                should_retry = attempt < max_retries - 1
                if self._error_loop_manager and error_loop_result:
                    should_retry = not error_loop_result.no_progress_detected and attempt < max_retries - 1

                # Mark step as failed in checkpoint
                is_recoverable = should_retry
                if step_id and self._enable_checkpoints:
                    self.update_checkpoint_for_step(
                        step_id=step_id,
                        status=StepStatus.FAILED_RECOVERABLE if is_recoverable else StepStatus.FAILED,
                        error={"message": str(e), "type": type(e).__name__},
                    )
                    self.save_checkpoint()

                # Get retry strategy from ErrorLoopManager
                if should_retry and self._error_loop_manager:
                    retry_strategy = self._error_loop_manager.get_retry_strategy(
                        state_summary={"step": step, "attempt": attempt + 1},
                        recent_actions=[{"action": step.get("action", ""), "success": False}],
                    )
                    if retry_strategy:
                        result.retry_decision_summary = {
                            "strategy_type": retry_strategy.strategy_type.value,
                            "rationale": retry_strategy.rationale,
                            "expected_fix": retry_strategy.expected_fix,
                        }

                # Retrieve repair patterns for retry context
                if should_retry and self._enable_memory:
                    normalized_error_type = "unknown"
                    if self._error_loop_manager and self._error_loop_manager.current_error:
                        normalized_error_type = self._error_loop_manager.current_error.normalized_error_type.value

                    repair_memory = self.retrieve_memory(
                        query=f"{query} error: {str(e)}",
                        retrieval_mode="pre_retry",
                        failure_context={
                            "error_type": normalized_error_type,
                            "error_message": str(e),
                            "attempt": attempt + 1,
                        },
                    )
                    if repair_memory.repair_patterns:
                        result.repair_patterns_used = len(repair_memory.repair_patterns)
                        result.memory_reuse_helped = True
                    if repair_memory.repair_strategies:
                        result.repair_strategies_applied = len(repair_memory.repair_strategies)

                    # Look up fix pattern from ErrorLoopManager
                    if self._error_loop_manager:
                        fix_pattern = self._error_loop_manager.get_fix_pattern()
                        if fix_pattern:
                            result.repair_summary = {
                                "fix_pattern_id": fix_pattern.fix_pattern_id,
                                "fix_summary": fix_pattern.fix_summary,
                                "confidence": fix_pattern.confidence,
                            }

                # Record retry attempt
                if self._error_loop_manager and should_retry:
                    self._error_loop_manager.record_retry_attempt(
                        actions_executed=[step],
                        success=False,
                        error_on_retry=str(e),
                    )

        # All retries exhausted
        if last_error:
            result.success = False
            result.execution_time_ms = (time.perf_counter() - start_time) * 1000

            # Complete error loop with failure
            if self._error_loop_manager:
                error_loop_result = self._error_loop_manager.complete(success=False)
                self._update_result_with_error_loop(result, error_loop_result)

            # Save failure to memory
            if self._enable_memory:
                save_execution_result(
                    domain=self._domain,
                    query=query,
                    success=False,
                    result_data={
                        "description": f"Failed step: {step.get('action', 'unknown')}",
                        "error": str(last_error),
                        "attempts": max_retries,
                        "checkpoint_id": self._current_checkpoint.checkpoint_id if self._current_checkpoint else None,
                        "error_loop_id": result.error_loop_id,
                    },
                    repo_root=self._repo_root,
                )
                result.memory_writeback_done = True

        return result

    def _execute_step_touchdesigner(self, step: dict[str, Any], attempt: int = 0) -> dict[str, Any]:
        """Execute a step using TouchDesigner bridge.

        Routes the step to TDExecutor/TDLiveClient for actual bridge communication.
        Supports both live bridge calls and dry-run simulation.

        Args:
            step: Step definition with action, target_network, command_type, payload
            attempt: Current attempt number (for logging/debugging)

        Returns:
            Dictionary with success, verified, and bridge_response fields
        """
        from app.domains.touchdesigner.td_executor import TDExecutor
        from app.domains.touchdesigner.td_live_protocol import TDLiveCommandRequest, TDLiveCommandResponse
        from app.domains.touchdesigner.td_live_commands import (
            build_basic_top_chain_request,
            build_inspect_network_request,
            validate_command_request,
        )
        from app.domains.touchdesigner.td_live_client import TDLiveClient

        action = step.get("action", "")
        command_type = step.get("command_type", "basic_top_chain")
        target_network = step.get("target_network", "/project1")
        payload = step.get("payload", {})
        dry_run = step.get("dry_run", False)
        host = step.get("bridge_host", "127.0.0.1")
        port = step.get("bridge_port", 9988)
        timeout = step.get("bridge_timeout", 3.0)

        executor = TDExecutor()

        # Build command request based on action type
        if command_type == "basic_top_chain":
            request = build_basic_top_chain_request(target_network=target_network)
            # Override with custom payload if provided
            if payload:
                request = TDLiveCommandRequest(
                    command_id=request.command_id,
                    command_type=request.command_type,
                    task_id=request.task_id,
                    target_network=request.target_network,
                    payload=payload,
                    safety_level=request.safety_level,
                )
        elif command_type == "inspect_network":
            request = build_inspect_network_request(target_network=target_network)
        else:
            # Build custom request
            from app.domains.touchdesigner.td_live_protocol import new_command_id
            request = TDLiveCommandRequest(
                command_id=new_command_id(),
                command_type=command_type,
                task_id=self._task_id or "td_step",
                target_network=target_network,
                payload=payload,
                safety_level=step.get("safety_level", "safe"),
            )

        # Validate request against MVP policy
        is_valid, reason = validate_command_request(request)
        if not is_valid:
            raise ValueError(f"Invalid TD command request: {reason}")

        # Execute via bridge or simulate
        if dry_run:
            # Simulated response for dry-run mode
            response = executor.simulate_live_basic_top_chain_result(target_network=target_network)
        else:
            # Live bridge call
            try:
                client = TDLiveClient(host=host, port=port, timeout_seconds=timeout)
                response = client.send_command(request)
            except Exception as e:
                # Bridge communication failed
                raise RuntimeError(f"TD bridge communication failed: {e}") from e

        # Parse response
        success = response.status == "succeeded"
        verified = success and step.get("verify", False)

        return {
            "success": success,
            "verified": verified,
            "bridge_response": response.to_dict(),
        }

    def build_recipe_rag_context(
        self,
        recipe: dict[str, Any],
        user_query: str = "",
        task_type: str = "",
    ) -> MergedContext | None:
        """Build enhanced context using RecipeRAGBridge.

        Integrates recipe structure with RAG knowledge for enhanced execution.

        Args:
            recipe: Recipe dictionary with steps and metadata
            user_query: User's original query
            task_type: Type of task (e.g., "houdini_sop_chain")

        Returns:
            MergedContext or None if integration fails
        """
        try:
            bridge = RecipeRAGBridge(max_context_tokens=10000)

            # Build RecipeKnowledge from recipe steps
            steps = recipe.get("steps", [])
            recipe_knowledge = build_recipe_knowledge_from_steps(
                steps=steps,
                task_type=task_type or recipe.get("name", "unknown"),
                dependencies=recipe.get("dependencies", {}),
                context_requirements=recipe.get("context_requirements", []),
            )

            # Build RAGContext from RAG index
            rag_context = RAGContext(
                domain=self._domain,
                retrieved_docs=[],
                query_interpretation=user_query,
                confidence_score=0.0,
            )

            # Try to get RAG context if available
            if self._enable_memory:
                try:
                    from app.core.rag_context_builder import build_context
                    rag_bundle = build_context(
                        query=user_query,
                        domain=self._domain,
                        max_chunks=5,
                    )
                    rag_context = build_rag_context_from_bundle(
                        bundle=rag_bundle,
                        domain=self._domain,
                        query_interpretation=user_query,
                    )
                except Exception:
                    pass  # RAG may not be available

            # Merge contexts
            return bridge.merge_contexts(
                recipe_knowledge=recipe_knowledge,
                rag_context=rag_context,
                user_query=user_query,
            )

        except Exception:
            return None

    def execute_recipe(
        self,
        recipe: dict[str, Any],
        task_id: str = "",
        attempt_resume: bool = True,
    ) -> RuntimeLoopResult:
        """Execute a complete recipe with full integration and checkpoint support.

        Args:
            recipe: Recipe with steps to execute
            task_id: Task ID for tracking
            attempt_resume: Whether to attempt resume from checkpoint

        Returns:
            RuntimeLoopResult with aggregated execution status
        """
        start_time = time.perf_counter()
        result = RuntimeLoopResult(
            domain=self._domain,
            task_id=task_id or self._task_id,
        )

        steps = recipe.get("steps", [])
        if not steps:
            result.success = False
            result.execution_time_ms = 0.0
            return result

        # Attempt resume if enabled
        if attempt_resume and self._enable_checkpoints and self._task_id:
            resume_result = self.attempt_resume()
            if resume_result:
                result.resumed_from_checkpoint = resume_result.success
                result.resume_checkpoint_id = resume_result.checkpoint_id
                result.resume_success = resume_result.success
                result.recovery_mode = resume_result.recovery_mode
                result.replayed_steps = resume_result.replayed_steps
                result.resume_context = resume_result.to_dict()

                if resume_result.success and resume_result.resume_context:
                    # Restore execution position from checkpoint
                    checkpoint = resume_result.resume_context.checkpoint
                    # Skip already completed steps
                    completed_steps = set(checkpoint.completed_step_ids)
                    steps = [s for s in steps if s.get("step_id", "") not in completed_steps]

        # Create checkpoint for recipe start if not resuming
        if self._enable_checkpoints and not self._current_checkpoint:
            query = recipe.get("description", recipe.get("name", ""))
            self.create_checkpoint(
                current_goal=query,
                steps=steps,
                reason="recipe_start",
            )
            result.checkpoint_created = True
            if self._current_checkpoint:
                result.checkpoint_id = self._current_checkpoint.checkpoint_id
                self.save_checkpoint()
                result.checkpoint_saved = True

        # Retrieve memory for the recipe
        query = recipe.get("description", recipe.get("name", ""))
        runtime_memory = self.retrieve_memory(query)
        result.memory_retrieved = runtime_memory.memory_influenced
        result.memory_items_used = runtime_memory.total_patterns
        result.success_patterns_used = runtime_memory.success_pattern_count
        result.failure_patterns_used = runtime_memory.failure_pattern_count
        result.repair_patterns_used = runtime_memory.repair_pattern_count

        # Build Recipe+RAG enhanced context
        merged_context = self.build_recipe_rag_context(
            recipe=recipe,
            user_query=query,
            task_type=recipe.get("task_type", ""),
        )
        if merged_context:
            result.metadata["merged_context_tokens"] = merged_context.total_context_tokens
            result.metadata["recipe_steps_count"] = len(merged_context.execution_roadmap.split("STEP")) - 1

        # Check bridge health if any step requires bridge
        requires_bridge = any(step.get("requires_bridge", False) for step in steps)
        if requires_bridge:
            bridge_health = self.check_bridge_health()
            if bridge_health:
                result.bridge_health_summary = bridge_health.to_dict()

                if not bridge_health.is_healthy:
                    # Normalize bridge failure
                    normalized = normalize_error(
                        Exception(f"Bridge unhealthy: {bridge_health.last_error_message}"),
                        context={
                            "domain": self._domain,
                            "task_id": task_id or self._task_id,
                            "bridge_health": bridge_health.to_dict(),
                        },
                    )
                    self._error_memory.append(normalized)
                    result.normalized_errors.append(normalized.to_dict())
                    result.error_count = 1
                    result.success = False
                    result.execution_time_ms = (time.perf_counter() - start_time) * 1000
                    return result

        # Execute each step
        all_success = True
        for i, step in enumerate(steps):
            step_id = step.get("step_id") or f"step_{i}"

            # Check if this step needs replay (from resume)
            if result.replayed_steps and step_id not in result.replayed_steps:
                # Step was already completed in previous run
                continue

            step_result = self.execute_step_with_retry(
                step,
                task_id=f"{task_id or self._task_id}_step_{i}",
                step_id=step_id,
            )

            result.normalized_errors.extend(step_result.normalized_errors)
            result.error_count += step_result.error_count
            result.checkpoint_id = step_result.checkpoint_id
            result.checkpoint_saved = step_result.checkpoint_saved

            if not step_result.success:
                all_success = False
                if not step.get("continue_on_error", False):
                    break

        result.success = all_success
        result.execution_time_ms = (time.perf_counter() - start_time) * 1000

        # Mark checkpoint as completed if successful
        if all_success and self._current_checkpoint and self._enable_checkpoints:
            from app.core.checkpoint_lifecycle import CheckpointLifecycle, CheckpointStatus
            lifecycle = self._checkpoint_lifecycle or CheckpointLifecycle(repo_root=self._repo_root)
            lifecycle.mark_checkpoint_status(
                checkpoint=self._current_checkpoint,
                status=CheckpointStatus.COMPLETED,
                reason="Recipe completed successfully",
            )
            self.save_checkpoint()

        # Save final result to memory
        if self._enable_memory:
            save_execution_result(
                domain=self._domain,
                query=query,
                success=all_success,
                result_data={
                    "description": f"Executed recipe: {recipe.get('name', 'unknown')}",
                    "steps": len(steps),
                    "errors": result.error_count,
                    "checkpoint_id": result.checkpoint_id,
                    "resumed": result.resumed_from_checkpoint,
                },
                repo_root=self._repo_root,
            )
            result.memory_writeback_done = True

        return result

    def get_error_memory(self) -> list[NormalizedError]:
        """Get all normalized errors captured during execution.

        Returns:
            List of NormalizedError instances
        """
        return self._error_memory.copy()

    def clear_error_memory(self) -> None:
        """Clear the error memory."""
        self._error_memory.clear()
