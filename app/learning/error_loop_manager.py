"""Error Loop Manager - Unified error lifecycle management.

This module provides the central orchestrator for the error loop:

1. Capture raw failures
2. Normalize into structured facts
3. Attach to runtime/session state
4. Evaluate retry decision
5. Retrieve repair/fix candidates
6. Persist failures to memory
7. Detect successful recovery
8. Promote fix patterns

The ErrorLoopManager integrates:
- Error normalization (error_normalizer.py)
- Retry strategy selection (retry_strategy.py)
- Fix pattern promotion (fix_pattern.py)
- Error memory persistence (error_memory.py)
- Repair trace recording (repair_trace.py)
- Trace event emission (trace_events.py)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from app.learning.error_normalizer import (
    ErrorCategory,
    NormalizedError,
    NormalizedErrorType,
    SourceLayer,
    normalize_error,
    normalize_bridge_failure,
    normalize_checkpoint_failure,
    normalize_execution_failure,
    normalize_provider_error,
    normalize_recipe_failure,
    normalize_verification_failure,
)
from app.learning.fix_pattern import (
    FixPattern,
    FixPatternStore,
    PromotionPolicy,
    build_default_fix_pattern_store,
    promote_fix_pattern,
)
from app.learning.retry_strategy import (
    RetryStrategy,
    RetryStrategyType,
    choose_retry_strategy,
    should_retry,
    should_stop_due_to_no_progress,
)
from app.learning.repair_trace import (
    FeedbackLoopResult,
    RepairFailureRecord,
    RepairSuccessRecord,
    RetryAttemptRecord,
    create_feedback_loop_result,
    create_repair_failure_record,
    create_repair_success_record,
    create_retry_attempt_record,
)
from app.recording.trace_events import (
    RuntimeStage,
    RuntimeTraceEvent,
    TraceEventType,
    emit_trace_event,
)


def _now_iso() -> str:
    """Return current UTC timestamp in ISO format."""
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _new_loop_id() -> str:
    """Generate a unique loop ID."""
    stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    return f"errloop_{stamp}_{uuid4().hex[:8]}"


@dataclass
class ErrorLoopState:
    """Current state of the error loop for a task.

    Tracks all errors, retries, repairs, and outcomes for a single
    task execution through the error loop lifecycle.
    """

    loop_id: str = field(default_factory=_new_loop_id)
    task_id: str = ""
    session_id: str = ""
    trace_id: str = ""
    domain: str = ""

    # Error tracking
    normalized_errors: list[NormalizedError] = field(default_factory=list)
    current_error: NormalizedError | None = None

    # Retry tracking
    retry_count: int = 0
    max_retries: int = 3
    retry_strategies_used: list[str] = field(default_factory=list)
    retry_attempts: list[RetryAttemptRecord] = field(default_factory=list)

    # Repair tracking
    repair_attempted: bool = False
    repair_successful: bool = False
    fix_pattern_found: bool = False
    fix_pattern_used: str = ""

    # Outcome
    final_outcome: str = "pending"  # pending, success, failed, deferred
    stop_reason: str = ""
    success_after_fix: bool = False

    # Fix pattern promotion
    fix_pattern_candidate: FixPattern | None = None
    fix_pattern_promoted: bool = False

    # Metadata
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    completed_at: str = ""

    @property
    def error_count(self) -> int:
        """Total number of normalized errors."""
        return len(self.normalized_errors)

    @property
    def has_recoverable_error(self) -> bool:
        """Check if current error is recoverable."""
        if not self.current_error:
            return False
        return self.current_error.recoverable

    @property
    def should_retry(self) -> bool:
        """Check if retry is recommended."""
        if not self.current_error:
            return False
        if self.retry_count >= self.max_retries:
            return False
        return self.current_error.retry_recommended

    @property
    def needs_repair(self) -> bool:
        """Check if repair is needed."""
        if not self.current_error:
            return False
        return self.current_error.repair_candidate and not self.should_retry

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "loop_id": self.loop_id,
            "task_id": self.task_id,
            "session_id": self.session_id,
            "trace_id": self.trace_id,
            "domain": self.domain,
            "error_count": self.error_count,
            "normalized_errors": [e.to_dict() for e in self.normalized_errors],
            "current_error": self.current_error.to_dict() if self.current_error else None,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "retry_strategies_used": self.retry_strategies_used,
            "repair_attempted": self.repair_attempted,
            "repair_successful": self.repair_successful,
            "fix_pattern_found": self.fix_pattern_found,
            "fix_pattern_used": self.fix_pattern_used,
            "final_outcome": self.final_outcome,
            "stop_reason": self.stop_reason,
            "success_after_fix": self.success_after_fix,
            "fix_pattern_candidate": self.fix_pattern_candidate.to_dict() if self.fix_pattern_candidate else None,
            "fix_pattern_promoted": self.fix_pattern_promoted,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
        }


@dataclass
class ErrorLoopResult:
    """Result of error loop processing.

    Provides visibility into the error loop lifecycle outcome.
    """

    success: bool = False
    loop_id: str = ""
    task_id: str = ""
    domain: str = ""

    # Error summary
    normalized_error_count: int = 0
    normalized_error_summary: dict[str, Any] = field(default_factory=dict)
    error_signatures: list[str] = field(default_factory=list)

    # Retry summary
    retry_count: int = 0
    retry_decision_summary: dict[str, Any] = field(default_factory=dict)
    retry_strategies_used: list[str] = field(default_factory=list)

    # Repair summary
    repair_attempted: bool = False
    repair_summary: dict[str, Any] = field(default_factory=dict)
    repair_successful: bool = False

    # Fix pattern summary
    fix_pattern_candidate_generated: bool = False
    fix_pattern_promoted: bool = False
    fix_pattern_id: str = ""
    promoted_fix_pattern_count: int = 0

    # Status
    no_progress_detected: bool = False
    retry_exhausted: bool = False
    final_error_loop_status: str = "pending"

    # Duration
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "success": self.success,
            "loop_id": self.loop_id,
            "task_id": self.task_id,
            "domain": self.domain,
            "normalized_error_count": self.normalized_error_count,
            "normalized_error_summary": self.normalized_error_summary,
            "error_signatures": self.error_signatures,
            "retry_count": self.retry_count,
            "retry_decision_summary": self.retry_decision_summary,
            "retry_strategies_used": self.retry_strategies_used,
            "repair_attempted": self.repair_attempted,
            "repair_summary": self.repair_summary,
            "repair_successful": self.repair_successful,
            "fix_pattern_candidate_generated": self.fix_pattern_candidate_generated,
            "fix_pattern_promoted": self.fix_pattern_promoted,
            "fix_pattern_id": self.fix_pattern_id,
            "promoted_fix_pattern_count": self.promoted_fix_pattern_count,
            "no_progress_detected": self.no_progress_detected,
            "retry_exhausted": self.retry_exhausted,
            "final_error_loop_status": self.final_error_loop_status,
            "duration_ms": self.duration_ms,
        }


class ErrorLoopManager:
    """Unified error loop lifecycle manager.

    This is the central orchestrator for the error loop. It coordinates:
    - Error normalization
    - Retry decision making
    - Repair candidate lookup
    - Fix pattern promotion
    - Memory persistence

    Usage:
        manager = ErrorLoopManager(domain="houdini", task_id="task_123")

        # On error
        result = manager.process_error(
            raw_error="Parameter 'dist' not found",
            source_layer=SourceLayer.EXECUTION,
        )

        if result.should_retry:
            # Execute retry with suggested strategy
            strategy = manager.get_retry_strategy()
            ...

        # On successful recovery
        manager.record_recovery_success(verification_result={...})
    """

    def __init__(
        self,
        domain: str = "",
        task_id: str = "",
        session_id: str = "",
        trace_id: str = "",
        repo_root: Path | None = None,
        max_retries: int = 3,
        enable_fix_promotion: bool = True,
        trace_emitter: Callable[[RuntimeTraceEvent], None] | None = None,
    ) -> None:
        """Initialize the error loop manager.

        Args:
            domain: Execution domain
            task_id: Task ID
            session_id: Session ID
            trace_id: Trace ID
            repo_root: Repository root for persistence
            max_retries: Maximum retry attempts
            enable_fix_promotion: Whether to promote fix patterns
            trace_emitter: Optional callback for emitting trace events
        """
        self._domain = domain
        self._task_id = task_id
        self._session_id = session_id
        self._trace_id = trace_id
        self._repo_root = repo_root or Path.cwd()
        self._max_retries = max_retries
        self._enable_fix_promotion = enable_fix_promotion
        self._trace_emitter = trace_emitter

        # State
        self._state = ErrorLoopState(
            task_id=task_id,
            session_id=session_id,
            trace_id=trace_id,
            domain=domain,
            max_retries=max_retries,
        )

        # Current retry strategy
        self._current_strategy: RetryStrategy | None = None

        # Stores
        self._fix_pattern_store: FixPatternStore | None = None

        # Timing
        self._start_time = time.perf_counter()

    @property
    def state(self) -> ErrorLoopState:
        """Get current error loop state."""
        return self._state

    @property
    def current_error(self) -> NormalizedError | None:
        """Get current normalized error."""
        return self._state.current_error

    @property
    def retry_strategy(self) -> RetryStrategy | None:
        """Get current retry strategy."""
        return self._current_strategy

    def _emit_trace_event(
        self,
        event_type: TraceEventType,
        runtime_stage: RuntimeStage = RuntimeStage.ERROR_GATE,
        **extra_fields: Any,
    ) -> RuntimeTraceEvent | None:
        """Emit a trace event if emitter is configured.

        Args:
            event_type: Type of trace event
            runtime_stage: Current runtime stage
            **extra_fields: Additional fields for the event

        Returns:
            The emitted event or None if no emitter configured
        """
        if not self._trace_emitter:
            return None

        event = emit_trace_event(
            trace_id=self._trace_id,
            session_id=self._session_id,
            event_type=event_type,
            domain=self._domain,
            task_id=self._task_id,
            runtime_stage=runtime_stage,
            **extra_fields,
        )

        self._trace_emitter(event)
        return event

    def process_error(
        self,
        raw_error: str | Exception | NormalizedError,
        source_layer: SourceLayer = SourceLayer.UNKNOWN,
        context: dict[str, Any] | None = None,
        operator_or_node: str = "",
        parameter_name: str = "",
    ) -> ErrorLoopResult:
        """Process an error through the error loop.

        This is the main entry point for error handling. It:
        1. Normalizes the error
        2. Evaluates retry decision
        3. Looks up fix patterns
        4. Updates state

        Args:
            raw_error: Error to process
            source_layer: Where the error originated
            context: Additional context
            operator_or_node: Specific operator/node involved
            parameter_name: Parameter name if relevant

        Returns:
            ErrorLoopResult with processing outcome
        """
        self._state.updated_at = _now_iso()

        # Normalize the error
        normalized = normalize_error(
            raw_error=raw_error,
            domain=self._domain,
            task_id=self._task_id,
            session_id=self._session_id,
            trace_id=self._trace_id,
            source_layer=source_layer,
            context=context,
            operator_or_node=operator_or_node,
            parameter_name=parameter_name,
        )

        # Add to error list
        self._state.normalized_errors.append(normalized)
        self._state.current_error = normalized

        # Emit trace event for error normalization
        self._emit_trace_event(
            TraceEventType.ERROR_NORMALIZED,
            normalized_error_summary={
                "error_id": normalized.error_id,
                "error_type": normalized.normalized_error_type.value,
                "error_category": normalized.error_category.value,
                "recoverable": normalized.recoverable,
                "source_layer": source_layer.value,
                "operator_or_node": operator_or_node,
                "parameter_name": parameter_name,
            },
        )

        # Evaluate retry decision
        self._evaluate_retry_decision()

        # Look up fix patterns
        self._lookup_fix_patterns()

        # Emit trace event if fix pattern found
        if self._state.fix_pattern_found:
            self._emit_trace_event(
                TraceEventType.FIX_PATTERN_FOUND,
                normalized_error_summary={
                    "fix_pattern_id": self._state.fix_pattern_used,
                    "error_type": normalized.normalized_error_type.value,
                },
            )

        return self._build_result()

    def process_bridge_failure(
        self,
        bridge_type: str,
        failure_reason: str,
        error_code: str = "",
        host: str = "",
        port: int = 0,
        latency_ms: float = 0.0,
        original_error: Exception | None = None,
    ) -> ErrorLoopResult:
        """Process a bridge failure through the error loop.

        Args:
            bridge_type: Type of bridge
            failure_reason: Failure reason
            error_code: Bridge error code
            host: Bridge host
            port: Bridge port
            latency_ms: Response latency
            original_error: Original exception

        Returns:
            ErrorLoopResult with processing outcome
        """
        normalized = normalize_bridge_failure(
            bridge_type=bridge_type,
            failure_reason=failure_reason,
            error_code=error_code,
            host=host,
            port=port,
            latency_ms=latency_ms,
            original_error=original_error,
            task_id=self._task_id,
            session_id=self._session_id,
            trace_id=self._trace_id,
        )

        return self.process_error(normalized, SourceLayer.BRIDGE)

    def process_verification_failure(
        self,
        verification_type: str,
        failure_reason: str,
        step_id: str = "",
        expected_value: Any = None,
        actual_value: Any = None,
        original_error: Exception | None = None,
    ) -> ErrorLoopResult:
        """Process a verification failure through the error loop.

        Args:
            verification_type: Type of verification
            failure_reason: Failure reason
            step_id: Step ID
            expected_value: Expected value
            actual_value: Actual value
            original_error: Original exception

        Returns:
            ErrorLoopResult with processing outcome
        """
        normalized = normalize_verification_failure(
            verification_type=verification_type,
            failure_reason=failure_reason,
            domain=self._domain,
            task_id=self._task_id,
            session_id=self._session_id,
            trace_id=self._trace_id,
            step_id=step_id,
            expected_value=expected_value,
            actual_value=actual_value,
            original_error=original_error,
        )

        return self.process_error(normalized, SourceLayer.VERIFICATION)

    def process_recipe_failure(
        self,
        error_message: str,
        recipe_name: str = "",
        step_index: int = -1,
        original_error: Exception | None = None,
    ) -> ErrorLoopResult:
        """Process a recipe execution failure.

        Args:
            error_message: Error message
            recipe_name: Recipe name
            step_index: Step index
            original_error: Original exception

        Returns:
            ErrorLoopResult with processing outcome
        """
        normalized = normalize_recipe_failure(
            error_message=error_message,
            recipe_name=recipe_name,
            step_index=step_index,
            domain=self._domain,
            task_id=self._task_id,
            session_id=self._session_id,
            trace_id=self._trace_id,
            original_error=original_error,
        )

        return self.process_error(normalized, SourceLayer.RECIPE)

    def get_retry_strategy(
        self,
        state_summary: dict[str, Any] | None = None,
        recent_actions: list[dict[str, Any]] | None = None,
    ) -> RetryStrategy | None:
        """Get the recommended retry strategy.

        Args:
            state_summary: Current runtime state summary
            recent_actions: Recent actions taken

        Returns:
            RetryStrategy or None if no retry recommended
        """
        if not self._state.current_error:
            return None

        if not self._state.should_retry:
            return None

        # Choose strategy based on normalized error
        strategy = choose_retry_strategy(
            normalized_error=self._state.current_error,
            state_summary=state_summary,
            recent_actions=recent_actions,
            prior_retry_count=self._state.retry_count,
        )

        self._current_strategy = strategy
        self._state.retry_strategies_used.append(strategy.strategy_type.value)

        # Emit trace event for retry decision
        self._emit_trace_event(
            TraceEventType.RETRY_DECIDED,
            retry_summary={
                "strategy_type": strategy.strategy_type.value,
                "rationale": strategy.rationale,
                "expected_fix": strategy.expected_fix,
                "confidence": strategy.confidence,
                "retry_count": self._state.retry_count + 1,
                "max_retries": self._state.max_retries,
            },
        )

        return strategy

    def record_retry_attempt(
        self,
        actions_executed: list[dict[str, Any]],
        success: bool,
        verification_result: dict[str, Any] | None = None,
        error_on_retry: str = "",
        duration_ms: float = 0.0,
    ) -> None:
        """Record a retry attempt.

        Args:
            actions_executed: Actions taken during retry
            success: Whether retry succeeded
            verification_result: Verification result
            error_on_retry: Error if retry failed
            duration_ms: Duration in milliseconds
        """
        self._state.retry_count += 1

        attempt = create_retry_attempt_record(
            retry_number=self._state.retry_count,
            strategy=self._current_strategy or RetryStrategy(
                strategy_id="unknown",
                strategy_type=RetryStrategyType.RETRY_SAME_STEP,
                rationale="No strategy selected",
                expected_fix="Unknown",
            ),
            actions=actions_executed,
            verification=verification_result or {},
            success=success,
            duration_ms=int(duration_ms),
        )

        self._state.retry_attempts.append(attempt)
        self._state.updated_at = _now_iso()

        # Emit trace event for repair attempt
        self._emit_trace_event(
            TraceEventType.REPAIR_ATTEMPTED,
            repair_summary={
                "retry_number": self._state.retry_count,
                "success": success,
                "actions_count": len(actions_executed),
                "error_on_retry": error_on_retry,
                "duration_ms": duration_ms,
            },
        )

        if success:
            self._handle_recovery_success(verification_result)
        else:
            self._handle_retry_failure(error_on_retry)

    def record_recovery_success(
        self,
        verification_result: dict[str, Any] | None = None,
        fix_summary: str = "",
        fix_steps: list[str] | None = None,
    ) -> FixPattern | None:
        """Record successful recovery and potentially promote fix pattern.

        Args:
            verification_result: Verification result after recovery
            fix_summary: Summary of the fix that worked
            fix_steps: Steps taken for the fix

        Returns:
            Promoted FixPattern or None
        """
        return self._handle_recovery_success(
            verification_result=verification_result,
            fix_summary=fix_summary,
            fix_steps=fix_steps,
        )

    def get_fix_pattern(self) -> FixPattern | None:
        """Get the fix pattern for current error.

        Returns:
            Matching FixPattern or None
        """
        if not self._state.current_error:
            return None

        store = self._get_fix_pattern_store()
        pattern = store.find_matching_pattern(
            self._state.current_error,
            min_confidence=0.5,
        )

        if pattern:
            self._state.fix_pattern_found = True
            self._state.fix_pattern_used = pattern.fix_pattern_id

        return pattern

    def complete(self, success: bool = False) -> ErrorLoopResult:
        """Complete the error loop and get final result.

        Args:
            success: Whether the overall execution succeeded

        Returns:
            Final ErrorLoopResult
        """
        self._state.final_outcome = "success" if success else "failed"
        self._state.completed_at = _now_iso()

        # Emit trace event for error loop completion
        self._emit_trace_event(
            TraceEventType.ERROR_LOOP_COMPLETED,
            normalized_error_summary={
                "final_outcome": self._state.final_outcome,
                "error_count": self._state.error_count,
                "retry_count": self._state.retry_count,
                "repair_successful": self._state.repair_successful,
                "fix_pattern_promoted": self._state.fix_pattern_promoted,
            },
        )

        return self._build_result()

    def _evaluate_retry_decision(self) -> None:
        """Evaluate whether retry should be attempted."""
        if not self._state.current_error:
            return

        # Check max retries
        if self._state.retry_count >= self._state.max_retries:
            self._state.current_error.retry_recommended = False
            return

        # Check for no-progress
        if self._state.current_error.no_progress_related:
            self._state.current_error.retry_recommended = False
            return

        # Check error category
        if self._state.current_error.error_category == ErrorCategory.PERMANENT:
            self._state.current_error.retry_recommended = False
            return

        if self._state.current_error.error_category == ErrorCategory.SAFETY:
            self._state.current_error.retry_recommended = False
            return

    def _lookup_fix_patterns(self) -> None:
        """Look up fix patterns for current error."""
        if not self._state.current_error:
            return

        store = self._get_fix_pattern_store()
        pattern = store.find_matching_pattern(
            self._state.current_error,
            min_confidence=0.5,
        )

        if pattern:
            self._state.fix_pattern_found = True
            self._state.fix_pattern_used = pattern.fix_pattern_id

    def _handle_recovery_success(
        self,
        verification_result: dict[str, Any] | None = None,
        fix_summary: str = "",
        fix_steps: list[str] | None = None,
    ) -> FixPattern | None:
        """Handle successful recovery from error."""
        self._state.success_after_fix = True
        self._state.repair_successful = True
        self._state.final_outcome = "success"
        self._state.updated_at = _now_iso()

        # Emit trace event for recovery success
        self._emit_trace_event(
            TraceEventType.RECOVERY_SUCCEEDED,
            normalized_error_summary={
                "error_type": (
                    self._state.current_error.normalized_error_type.value
                    if self._state.current_error else "unknown"
                ),
                "fix_summary": fix_summary or "Recovered successfully",
                "retry_count": self._state.retry_count,
            },
        )

        if not self._enable_fix_promotion:
            return None

        if not self._state.current_error:
            return None

        # Generate fix summary if not provided
        if not fix_summary:
            fix_summary = self._generate_fix_summary()

        # Get fix strategy type
        fix_strategy_type = (
            self._current_strategy.strategy_type.value
            if self._current_strategy
            else "unknown"
        )

        # Promote fix pattern
        pattern = promote_fix_pattern(
            normalized_error=self._state.current_error,
            fix_summary=fix_summary,
            fix_strategy_type=fix_strategy_type,
            fix_steps=fix_steps,
            verification_result=verification_result,
            session_id=self._session_id,
            trace_id=self._trace_id,
            repo_root=self._repo_root,
        )

        if pattern:
            self._state.fix_pattern_candidate = pattern
            self._state.fix_pattern_promoted = True

            # Emit trace event for fix pattern promotion
            self._emit_trace_event(
                TraceEventType.FIX_PATTERN_PROMOTED,
                normalized_error_summary={
                    "fix_pattern_id": pattern.fix_pattern_id,
                    "error_type": self._state.current_error.normalized_error_type.value,
                    "fix_summary": fix_summary,
                    "confidence": pattern.confidence,
                },
            )

        return pattern

    def _handle_retry_failure(self, error_message: str) -> None:
        """Handle retry failure."""
        if self._state.retry_count >= self._state.max_retries:
            self._state.stop_reason = "max_retries_exceeded"
            self._state.final_outcome = "failed"

    def _generate_fix_summary(self) -> str:
        """Generate a fix summary from current state."""
        if not self._state.current_error:
            return "Unknown fix"

        error = self._state.current_error

        if error.normalized_error_type == NormalizedErrorType.WRONG_PARAMETER_NAME:
            return f"Corrected parameter name: {error.parameter_name}"
        elif error.normalized_error_type == NormalizedErrorType.MISSING_OUTPUT:
            return "Added missing output node"
        elif error.normalized_error_type == NormalizedErrorType.MISSING_CONNECTION:
            return "Connected missing link"
        else:
            return f"Recovered from {error.normalized_error_type.value}"

    def _get_fix_pattern_store(self) -> FixPatternStore:
        """Get or create fix pattern store."""
        if self._fix_pattern_store is None:
            self._fix_pattern_store = build_default_fix_pattern_store(self._repo_root)
        return self._fix_pattern_store

    def _build_result(self) -> ErrorLoopResult:
        """Build result from current state."""
        duration_ms = (time.perf_counter() - self._start_time) * 1000

        # Build error summary
        error_summary = {}
        if self._state.current_error:
            error_summary = {
                "error_id": self._state.current_error.error_id,
                "error_type": self._state.current_error.normalized_error_type.value,
                "error_category": self._state.current_error.error_category.value,
                "recoverable": self._state.current_error.recoverable,
                "retry_recommended": self._state.current_error.retry_recommended,
                "repair_candidate": self._state.current_error.repair_candidate,
                "fix_hint": self._state.current_error.fix_hint,
                "context_summary": self._state.current_error.context_summary,
            }

        # Build retry summary
        retry_summary = {}
        if self._current_strategy:
            retry_summary = {
                "strategy_type": self._current_strategy.strategy_type.value,
                "rationale": self._current_strategy.rationale,
                "expected_fix": self._current_strategy.expected_fix,
                "confidence": self._current_strategy.confidence,
            }

        # Build repair summary
        repair_summary = {
            "repair_attempted": self._state.repair_attempted,
            "repair_successful": self._state.repair_successful,
            "fix_pattern_found": self._state.fix_pattern_found,
            "fix_pattern_used": self._state.fix_pattern_used,
        }

        # Collect error signatures
        error_signatures = [
            e.error_signature for e in self._state.normalized_errors if e.error_signature
        ]

        return ErrorLoopResult(
            success=self._state.final_outcome == "success",
            loop_id=self._state.loop_id,
            task_id=self._task_id,
            domain=self._domain,
            normalized_error_count=self._state.error_count,
            normalized_error_summary=error_summary,
            error_signatures=error_signatures,
            retry_count=self._state.retry_count,
            retry_decision_summary=retry_summary,
            retry_strategies_used=self._state.retry_strategies_used.copy(),
            repair_attempted=self._state.repair_attempted,
            repair_summary=repair_summary,
            repair_successful=self._state.repair_successful,
            fix_pattern_candidate_generated=self._state.fix_pattern_candidate is not None,
            fix_pattern_promoted=self._state.fix_pattern_promoted,
            fix_pattern_id=self._state.fix_pattern_candidate.fix_pattern_id if self._state.fix_pattern_candidate else "",
            no_progress_detected=self._state.current_error.no_progress_related if self._state.current_error else False,
            retry_exhausted=self._state.retry_count >= self._state.max_retries,
            final_error_loop_status=self._state.final_outcome,
            duration_ms=duration_ms,
        )


def create_error_loop_manager(
    domain: str = "",
    task_id: str = "",
    session_id: str = "",
    trace_id: str = "",
    repo_root: Path | None = None,
    max_retries: int = 3,
    trace_emitter: Callable[[RuntimeTraceEvent], None] | None = None,
) -> ErrorLoopManager:
    """Factory function for creating ErrorLoopManager.

    Args:
        domain: Execution domain
        task_id: Task ID
        session_id: Session ID
        trace_id: Trace ID
        repo_root: Repository root
        max_retries: Maximum retries
        trace_emitter: Optional callback for emitting trace events

    Returns:
        Configured ErrorLoopManager
    """
    return ErrorLoopManager(
        domain=domain,
        task_id=task_id,
        session_id=session_id,
        trace_id=trace_id,
        repo_root=repo_root,
        max_retries=max_retries,
        trace_emitter=trace_emitter,
    )