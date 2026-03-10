"""Error Normalizer Module.

Provides normalized error types for consistent error handling across
different execution backends.

This module implements the core error loop normalization:
- Structured error facts with reusable signatures
- Source layer classification (provider, backend, bridge, execution, etc.)
- Recovery hints (recoverable, retry_recommended, repair_candidate)
- Error signature generation for pattern matching
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4


class NormalizedErrorType(str, Enum):
    """Normalized error types for consistent error handling."""

    # Bridge-related errors
    BRIDGE_UNAVAILABLE = "bridge_unavailable"
    BRIDGE_UNHEALTHY = "bridge_unhealthy"
    BRIDGE_DEGRADED = "bridge_degraded"
    BRIDGE_TIMEOUT = "bridge_timeout"
    BRIDGE_CONNECTION_FAILED = "bridge_connection_failed"
    BRIDGE_PING_FAILED = "bridge_ping_failed"
    BRIDGE_PING_TIMEOUT = "bridge_ping_timeout"
    BRIDGE_INSPECT_FAILED = "bridge_inspect_failed"
    BRIDGE_INSPECT_TIMEOUT = "bridge_inspect_timeout"
    BRIDGE_COMMAND_FAILED = "bridge_command_failed"
    BRIDGE_COMMAND_TIMEOUT = "bridge_command_timeout"
    BRIDGE_COMMAND_REJECTED = "bridge_command_rejected"
    BRIDGE_RESPONSE_INVALID = "bridge_response_invalid"
    BRIDGE_LAST_RESULT_MISSING = "bridge_last_result_missing"
    BRIDGE_HEALTH_UNKNOWN = "bridge_health_unknown"

    # Backend selection errors
    NO_SAFE_BACKEND = "no_safe_backend"
    UI_FALLBACK_BLOCKED = "ui_fallback_blocked"

    # Safety-related errors
    SAFETY_BLOCKED = "safety_blocked"
    KILLSWITCH_ACTIVE = "killswitch_active"
    WRONG_WINDOW_FOCUS = "wrong_window_focus"
    BLOCKED_INPUT = "blocked_input"

    # Execution errors
    EXECUTION_FAILED = "execution_failed"
    TIMEOUT = "timeout"
    INVALID_ACTION = "invalid_action"
    INVALID_PARAMS = "invalid_params"
    WRONG_PARAMETER_NAME = "wrong_parameter_name"
    MISSING_OUTPUT = "missing_output"
    MISSING_CONNECTION = "missing_connection"
    WRONG_CONTEXT = "wrong_context"
    NO_PROGRESS = "no_progress"
    REPEATED_NO_PROGRESS = "repeated_no_progress"
    VERIFICATION_FAILED = "verification_failed"

    # Recipe errors
    RECIPE_INVALID = "recipe_invalid"
    STEP_FAILED = "step_failed"
    PRECONDITION_FAILED = "precondition_failed"

    # Checkpoint and recovery errors
    CHECKPOINT_MISSING = "checkpoint_missing"
    CHECKPOINT_INVALID = "checkpoint_invalid"
    CHECKPOINT_INCOMPATIBLE = "checkpoint_incompatible"
    CHECKPOINT_CORRUPT = "checkpoint_corrupt"
    RESUME_NOT_ALLOWED = "resume_not_allowed"
    RECOVERY_CONTEXT_INSUFFICIENT = "recovery_context_insufficient"
    REPLAY_REQUIRED_BUT_BLOCKED = "replay_required_but_blocked"
    CHECKPOINT_RESTORE_FAILED = "checkpoint_restore_failed"
    CHECKPOINT_STALE = "checkpoint_stale"
    UNSAFE_TO_RESUME = "unsafe_to_resume"

    # Repair errors
    REPAIR_FAILED = "repair_failed"
    RETRY_EXHAUSTED = "retry_exhausted"

    # Memory errors
    MEMORY_STORE_FAILED = "memory_store_failed"
    MEMORY_RETRIEVAL_FAILED = "memory_retrieval_failed"

    # Provider errors
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PROVIDER_TIMEOUT = "provider_timeout"
    PROVIDER_EXECUTION_FAILED = "provider_execution_failed"

    # Video/Media processing errors
    VIDEO_LOAD_FAILED = "video_load_failed"
    VIDEO_SAVE_FAILED = "video_save_failed"
    FRAME_EXTRACTION_FAILED = "frame_extraction_failed"
    FRAME_SAMPLING_FAILED = "frame_sampling_failed"
    ACTION_EXTRACTION_FAILED = "action_extraction_failed"
    INTENT_INFERENCE_FAILED = "intent_inference_failed"
    RECIPE_GENERATION_FAILED = "recipe_generation_failed"
    RECIPE_VALIDATION_FAILED = "recipe_validation_failed"
    TUTORIAL_SIGNAL_INSUFFICIENT = "tutorial_signal_insufficient"
    INSUFFICIENT_TUTORIAL_SIGNAL = "insufficient_tutorial_signal"
    CONFIDENCE_BELOW_THRESHOLD = "confidence_below_threshold"

    # Unknown
    UNKNOWN = "unknown"
    UNKNOWN_RUNTIME_ERROR = "unknown_runtime_error"


class SourceLayer(str, Enum):
    """Source layer where an error originated.

    Used for routing errors to appropriate handlers.
    """

    PROVIDER = "provider"
    BACKEND = "backend"
    BRIDGE = "bridge"
    EXECUTION = "execution"
    VERIFICATION = "verification"
    PLANNING = "planning"
    DECOMPOSITION = "decomposition"
    RECIPE = "recipe"
    MEMORY = "memory"
    RUNTIME = "runtime"
    CHECKPOINT = "checkpoint"
    SAFETY = "safety"
    UNKNOWN = "unknown"


class ErrorCategory(str, Enum):
    """High-level error categories for routing decisions."""

    TRANSIENT = "transient"  # Temporary, may succeed on retry
    RECOVERABLE = "recoverable"  # Can be fixed with repair
    PERMANENT = "permanent"  # Cannot be recovered
    SAFETY = "safety"  # Safety constraint violation
    UNKNOWN = "unknown"


def _now_iso() -> str:
    """Return current UTC timestamp in ISO format."""
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _new_error_id() -> str:
    """Generate a unique error ID."""
    stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    return f"nerr_{stamp}_{uuid4().hex[:8]}"


@dataclass
class NormalizedError:
    """Normalized error with consistent structure for error loop lifecycle.

    This is the core error fact model for the unified error loop.
    All important runtime failures should be normalized into this structure.

    Fields:
        error_id: Unique identifier for this error instance
        normalized_error_type: Typed error category
        message: Human-readable error message
        raw_message: Original error message before normalization
        domain: Execution domain (houdini, touchdesigner, etc.)
        task_id: Associated task ID
        session_id: Associated session ID (if available)
        trace_id: Associated trace ID (if available)
        source_layer: Where the error originated
        error_category: High-level category for routing
        error_code: Domain-specific error code
        fix_hint: Suggested fix for this error
        confidence: Confidence in the error classification
        recoverable: Whether this error can be recovered
        retry_recommended: Whether retry is recommended
        repair_candidate: Whether this error is a candidate for repair
        no_progress_related: Whether this error is related to no-progress
        operator_or_node: Specific operator/node involved
        parameter_name: Parameter name if parameter-related
        corrected_value: Suggested corrected value
        wrong_value: The wrong value that was used
        backend_context: Backend-related context
        bridge_context: Bridge-related context
        provider_context: Provider-related context
        verification_context: Verification-related context
        context_summary: Brief summary for logging
        created_at: ISO timestamp when created
        original_error: Original exception (if any)
        context: Additional context dictionary
    """

    # Identity
    error_id: str = field(default_factory=_new_error_id)

    # Core error info
    normalized_error_type: NormalizedErrorType = NormalizedErrorType.UNKNOWN
    message: str = ""
    raw_message: str = ""

    # Context
    domain: str = ""
    task_id: str = ""
    session_id: str = ""
    trace_id: str = ""

    # Classification
    source_layer: SourceLayer = SourceLayer.UNKNOWN
    error_category: ErrorCategory = ErrorCategory.UNKNOWN
    error_code: str = ""

    # Fix hints
    fix_hint: str = ""
    confidence: float = 1.0

    # Recovery flags
    recoverable: bool = True
    retry_recommended: bool = True
    repair_candidate: bool = False
    no_progress_related: bool = False

    # Domain-specific context
    operator_or_node: str = ""
    parameter_name: str = ""
    corrected_value: str = ""
    wrong_value: str = ""

    # Layer-specific context
    backend_context: dict[str, Any] = field(default_factory=dict)
    bridge_context: dict[str, Any] = field(default_factory=dict)
    provider_context: dict[str, Any] = field(default_factory=dict)
    verification_context: dict[str, Any] = field(default_factory=dict)

    # Summary
    context_summary: str = ""
    created_at: str = field(default_factory=_now_iso)

    # Original error
    original_error: Exception | None = None
    context: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Set derived fields after initialization."""
        if not self.raw_message and self.message:
            self.raw_message = self.message
        if not self.created_at:
            self.created_at = _now_iso()
        if not self.error_id:
            self.error_id = _new_error_id()

    @property
    def error_type(self) -> NormalizedErrorType:
        """Alias for normalized_error_type for compatibility."""
        return self.normalized_error_type

    @property
    def error_signature(self) -> str:
        """Generate a signature for matching similar errors.

        The signature is used for pattern matching and retrieval.
        Format: domain|error_type|source_layer|operator_or_node|parameter_name
        """
        parts = [
            self.domain,
            self.normalized_error_type.value,
            self.source_layer.value,
            self.operator_or_node,
            self.parameter_name,
        ]
        return "|".join(p for p in parts if p)

    @property
    def error_hash(self) -> str:
        """Generate a stable hash for this error for deduplication."""
        sig = self.error_signature + "|" + self.message[:100]
        return hashlib.sha256(sig.encode()).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "error_id": self.error_id,
            "normalized_error_type": self.normalized_error_type.value,
            "error_type": self.normalized_error_type.value,
            "message": self.message,
            "raw_message": self.raw_message,
            "domain": self.domain,
            "task_id": self.task_id,
            "session_id": self.session_id,
            "trace_id": self.trace_id,
            "source_layer": self.source_layer.value,
            "error_category": self.error_category.value,
            "error_code": self.error_code,
            "fix_hint": self.fix_hint,
            "confidence": self.confidence,
            "recoverable": self.recoverable,
            "retry_recommended": self.retry_recommended,
            "repair_candidate": self.repair_candidate,
            "no_progress_related": self.no_progress_related,
            "operator_or_node": self.operator_or_node,
            "parameter_name": self.parameter_name,
            "corrected_value": self.corrected_value,
            "wrong_value": self.wrong_value,
            "backend_context": self.backend_context,
            "bridge_context": self.bridge_context,
            "provider_context": self.provider_context,
            "verification_context": self.verification_context,
            "context_summary": self.context_summary,
            "error_signature": self.error_signature,
            "error_hash": self.error_hash,
            "created_at": self.created_at,
            "original_error": str(self.original_error) if self.original_error else None,
            "context": self.context,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NormalizedError":
        """Deserialize from dictionary."""
        error_type_value = data.get("normalized_error_type") or data.get("error_type", "unknown")
        try:
            error_type = NormalizedErrorType(error_type_value)
        except ValueError:
            error_type = NormalizedErrorType.UNKNOWN

        source_layer_value = data.get("source_layer", "unknown")
        try:
            source_layer = SourceLayer(source_layer_value)
        except ValueError:
            source_layer = SourceLayer.UNKNOWN

        error_category_value = data.get("error_category", "unknown")
        try:
            error_category = ErrorCategory(error_category_value)
        except ValueError:
            error_category = ErrorCategory.UNKNOWN

        return cls(
            error_id=str(data.get("error_id", "")),
            normalized_error_type=error_type,
            message=str(data.get("message", "")),
            raw_message=str(data.get("raw_message", "")),
            domain=str(data.get("domain", "")),
            task_id=str(data.get("task_id", "")),
            session_id=str(data.get("session_id", "")),
            trace_id=str(data.get("trace_id", "")),
            source_layer=source_layer,
            error_category=error_category,
            error_code=str(data.get("error_code", "")),
            fix_hint=str(data.get("fix_hint", "")),
            confidence=float(data.get("confidence", 1.0)),
            recoverable=bool(data.get("recoverable", True)),
            retry_recommended=bool(data.get("retry_recommended", True)),
            repair_candidate=bool(data.get("repair_candidate", False)),
            no_progress_related=bool(data.get("no_progress_related", False)),
            operator_or_node=str(data.get("operator_or_node", "")),
            parameter_name=str(data.get("parameter_name", "")),
            corrected_value=str(data.get("corrected_value", "")),
            wrong_value=str(data.get("wrong_value", "")),
            backend_context=dict(data.get("backend_context", {})),
            bridge_context=dict(data.get("bridge_context", {})),
            provider_context=dict(data.get("provider_context", {})),
            verification_context=dict(data.get("verification_context", {})),
            context_summary=str(data.get("context_summary", "")),
            created_at=str(data.get("created_at", "")),
            context=dict(data.get("context", {})),
        )

    @classmethod
    def from_exception(
        cls,
        exc: Exception,
        context: dict[str, Any] | None = None,
        domain: str = "",
        task_id: str = "",
        session_id: str = "",
        trace_id: str = "",
        source_layer: SourceLayer | None = None,
    ) -> "NormalizedError":
        """Create a normalized error from an exception.

        Args:
            exc: Exception to normalize
            context: Optional additional context
            domain: Execution domain
            task_id: Associated task ID
            session_id: Associated session ID
            trace_id: Associated trace ID
            source_layer: Where the error originated

        Returns:
            NormalizedError instance
        """
        # Map common exceptions to types
        error_type = NormalizedErrorType.UNKNOWN
        error_category = ErrorCategory.UNKNOWN
        fix_hint = ""
        confidence = 0.5
        recoverable = True
        retry_recommended = True
        repair_candidate = False

        exc_name = type(exc).__name__.lower()
        message = str(exc)
        message_lower = message.lower()

        if "timeout" in exc_name or "timeout" in message_lower:
            error_type = NormalizedErrorType.TIMEOUT
            error_category = ErrorCategory.TRANSIENT
            fix_hint = "Operation timed out. Try increasing timeout or check system resources."
            confidence = 0.9
            retry_recommended = True
        elif "connection" in exc_name or "connection" in message_lower:
            error_type = NormalizedErrorType.BRIDGE_CONNECTION_FAILED
            error_category = ErrorCategory.TRANSIENT
            fix_hint = "Connection failed. Check if the bridge server is running."
            confidence = 0.9
            retry_recommended = True
        elif "permission" in message_lower or "access" in message_lower:
            error_type = NormalizedErrorType.SAFETY_BLOCKED
            error_category = ErrorCategory.SAFETY
            fix_hint = "Permission denied. Check access rights."
            confidence = 0.9
            recoverable = False
            retry_recommended = False

        return cls(
            normalized_error_type=error_type,
            message=message,
            raw_message=message,
            domain=domain,
            task_id=task_id,
            session_id=session_id,
            trace_id=trace_id,
            source_layer=source_layer or SourceLayer.UNKNOWN,
            error_category=error_category,
            fix_hint=fix_hint,
            confidence=confidence,
            recoverable=recoverable,
            retry_recommended=retry_recommended,
            repair_candidate=repair_candidate,
            original_error=exc,
            context=context or {},
        )

    def __str__(self) -> str:
        """Return string representation."""
        return f"[{self.normalized_error_type.value}] {self.message}"

    def __repr__(self) -> str:
        """Return repr."""
        return f"NormalizedError({self.normalized_error_type.value!r}, {self.message!r})"


def normalize_error(
    raw_error: str | Exception | NormalizedError | None = None,
    error_type: NormalizedErrorType = NormalizedErrorType.UNKNOWN,
    context: dict[str, Any] | None = None,
    domain: str = "",
    task_id: str = "",
    session_id: str = "",
    trace_id: str = "",
    source_layer: SourceLayer | None = None,
    error: str | Exception | NormalizedError | None = None,
    operator_or_node: str = "",
    parameter_name: str = "",
) -> NormalizedError:
    """Normalize an error to a consistent format.

    This is the primary entry point for error normalization in the error loop.
    All important runtime failures should pass through this function.

    Args:
        raw_error: Raw error string or exception
        error_type: Type to use if creating new error
        context: Optional additional context
        domain: Execution domain
        task_id: Associated task ID
        session_id: Associated session ID
        trace_id: Associated trace ID
        source_layer: Where the error originated
        error: Alternative parameter name for raw_error
        operator_or_node: Specific operator/node involved
        parameter_name: Parameter name if parameter-related

    Returns:
        NormalizedError instance with structured error fact
    """
    # Support both 'raw_error' and 'error' parameter names
    error_value = raw_error or error

    if isinstance(error_value, NormalizedError):
        return error_value

    if isinstance(error_value, Exception):
        return NormalizedError.from_exception(
            error_value,
            context,
            domain,
            task_id,
            session_id,
            trace_id,
            source_layer,
        )

    if isinstance(error_value, str):
        # Analyze the error message to determine type and provide hints
        message_lower = error_value.lower()
        inferred_type = error_type
        error_category = ErrorCategory.UNKNOWN
        fix_hint = ""
        confidence = 0.5
        recoverable = True
        retry_recommended = True
        repair_candidate = False
        inferred_node = operator_or_node
        inferred_param = parameter_name

        # Parameter-related errors
        if "parameter" in message_lower and ("not found" in message_lower or "does not exist" in message_lower):
            inferred_type = NormalizedErrorType.WRONG_PARAMETER_NAME
            error_category = ErrorCategory.RECOVERABLE
            confidence = 0.9
            repair_candidate = True
            retry_recommended = True

            # Extract parameter name from message
            import re
            param_match = re.search(r"parameter\s+['\"]?(\w+)['\"]?", message_lower)
            if param_match and not inferred_param:
                inferred_param = param_match.group(1)

            if "dist" in message_lower:
                inferred_node = "polybevel"
                if domain == "houdini":
                    fix_hint = "Parameter 'dist' does not exist. Use 'offset' instead for polybevel."
                else:
                    fix_hint = "Parameter 'dist' not found. Check parameter name."
            elif "width" in message_lower or "size" in message_lower:
                fix_hint = "Parameter name may be incorrect. Check the operator documentation."
            else:
                fix_hint = "Parameter not found. Verify the correct parameter name."

        # Missing output errors
        elif "missing output" in message_lower or ("null" in message_lower and "missing" in message_lower):
            inferred_type = NormalizedErrorType.MISSING_OUTPUT
            error_category = ErrorCategory.RECOVERABLE
            confidence = 0.9
            repair_candidate = True
            retry_recommended = False  # Better to repair than retry
            if domain == "houdini":
                fix_hint = "Add a null OUT node at the end of the SOP chain."
            elif domain == "touchdesigner":
                fix_hint = "Add a nullTOP at the end of the chain for proper output."
            else:
                fix_hint = "Add an output/null node at the end of the chain."

        # Missing connection errors
        elif "missing connection" in message_lower or "not connected" in message_lower:
            inferred_type = NormalizedErrorType.MISSING_CONNECTION
            error_category = ErrorCategory.RECOVERABLE
            confidence = 0.9
            repair_candidate = True
            retry_recommended = False
            fix_hint = "Connect the operators in the chain."

        # No progress errors
        elif "repeated no progress" in message_lower or "repeated" in message_lower and "no progress" in message_lower:
            inferred_type = NormalizedErrorType.REPEATED_NO_PROGRESS
            error_category = ErrorCategory.PERMANENT
            confidence = 0.8
            fix_hint = "Repeated execution made no progress. Stop and try a different approach."
            recoverable = False
            retry_recommended = False
        elif "no progress" in message_lower or "stuck" in message_lower:
            inferred_type = NormalizedErrorType.NO_PROGRESS
            error_category = ErrorCategory.PERMANENT
            confidence = 0.8
            fix_hint = "Execution made no progress. Try a different approach."
            recoverable = False
            retry_recommended = False

        # Verification failures
        elif "verification" in message_lower or "verify" in message_lower:
            inferred_type = NormalizedErrorType.VERIFICATION_FAILED
            error_category = ErrorCategory.RECOVERABLE
            confidence = 0.8
            fix_hint = "Verification failed. Check if the operation completed correctly."
            repair_candidate = True

        # Bridge errors
        elif "bridge" in message_lower:
            inferred_type = NormalizedErrorType.BRIDGE_UNAVAILABLE
            error_category = ErrorCategory.TRANSIENT
            confidence = 0.9
            fix_hint = "Check if the bridge server is running."

        # Timeout errors
        elif "timeout" in message_lower:
            inferred_type = NormalizedErrorType.TIMEOUT
            error_category = ErrorCategory.TRANSIENT
            confidence = 0.9
            fix_hint = "Operation timed out. Consider increasing timeout."

        return NormalizedError(
            normalized_error_type=inferred_type,
            message=error_value,
            raw_message=error_value,
            domain=domain,
            task_id=task_id,
            session_id=session_id,
            trace_id=trace_id,
            source_layer=source_layer or SourceLayer.UNKNOWN,
            error_category=error_category,
            fix_hint=fix_hint,
            confidence=confidence,
            recoverable=recoverable,
            retry_recommended=retry_recommended,
            repair_candidate=repair_candidate,
            operator_or_node=inferred_node,
            parameter_name=inferred_param,
            context=context or {},
        )

    return NormalizedError(
        normalized_error_type=NormalizedErrorType.UNKNOWN,
        message=str(error_value) if error_value else "Unknown error",
        domain=domain,
        task_id=task_id,
        session_id=session_id,
        trace_id=trace_id,
        source_layer=source_layer or SourceLayer.UNKNOWN,
        context=context or {},
    )


def normalize_bridge_failure(
    bridge_type: str,
    failure_reason: str,
    error_code: str = "",
    host: str = "",
    port: int = 0,
    latency_ms: float = 0.0,
    original_error: Exception | None = None,
    task_id: str = "",
    session_id: str = "",
    trace_id: str = "",
    is_timeout: bool = False,
    operation_type: str = "",  # "ping", "inspect", "command"
) -> NormalizedError:
    """Normalize a bridge failure to a consistent error format.

    Args:
        bridge_type: Type of bridge (houdini, touchdesigner)
        failure_reason: Human-readable failure reason
        error_code: Bridge-specific error code
        host: Bridge host address
        port: Bridge port
        latency_ms: Response latency
        original_error: Original exception
        task_id: Associated task ID
        session_id: Associated session ID
        trace_id: Associated trace ID
        is_timeout: Whether failure was due to timeout
        operation_type: Type of operation that failed (ping, inspect, command)

    Returns:
        NormalizedError with bridge failure details
    """
    error_type = NormalizedErrorType.BRIDGE_UNAVAILABLE
    error_category = ErrorCategory.TRANSIENT
    reason_lower = failure_reason.lower()
    code_lower = error_code.lower()

    # Determine error type based on operation and reason
    if operation_type == "ping" or "ping" in reason_lower or "ping" in code_lower:
        error_type = NormalizedErrorType.BRIDGE_PING_TIMEOUT if is_timeout else NormalizedErrorType.BRIDGE_PING_FAILED
    elif operation_type == "inspect" or "inspect" in reason_lower or "inspect" in code_lower:
        error_type = NormalizedErrorType.BRIDGE_INSPECT_TIMEOUT if is_timeout else NormalizedErrorType.BRIDGE_INSPECT_FAILED
    elif operation_type == "command" or "command" in reason_lower or "reject" in reason_lower:
        error_type = NormalizedErrorType.BRIDGE_COMMAND_TIMEOUT if is_timeout else NormalizedErrorType.BRIDGE_COMMAND_FAILED
        error_category = ErrorCategory.RECOVERABLE
    elif "timeout" in reason_lower or is_timeout:
        error_type = NormalizedErrorType.BRIDGE_TIMEOUT
    elif "invalid" in reason_lower or "malformed" in reason_lower:
        error_type = NormalizedErrorType.BRIDGE_RESPONSE_INVALID
        error_category = ErrorCategory.RECOVERABLE
    elif "unhealthy" in reason_lower:
        error_type = NormalizedErrorType.BRIDGE_UNHEALTHY
    elif "degraded" in reason_lower:
        error_type = NormalizedErrorType.BRIDGE_DEGRADED
    elif "connection" in reason_lower:
        error_type = NormalizedErrorType.BRIDGE_CONNECTION_FAILED
    elif "unknown" in reason_lower or "health" in reason_lower:
        error_type = NormalizedErrorType.BRIDGE_HEALTH_UNKNOWN

    bridge_context = {
        "bridge_type": bridge_type,
        "error_code": error_code,
        "host": host,
        "port": port,
        "latency_ms": latency_ms,
    }

    return NormalizedError(
        normalized_error_type=error_type,
        message=f"[{bridge_type}] {failure_reason}",
        raw_message=failure_reason,
        domain=bridge_type,
        task_id=task_id,
        session_id=session_id,
        trace_id=trace_id,
        source_layer=SourceLayer.BRIDGE,
        error_category=error_category,
        error_code=error_code,
        fix_hint="Check if the bridge server is running and accessible.",
        confidence=0.9,
        recoverable=True,
        retry_recommended=True,
        bridge_context=bridge_context,
        original_error=original_error,
        context_summary=f"Bridge {bridge_type} failure: {error_code or failure_reason[:50]}",
    )


def normalize_checkpoint_failure(
    checkpoint_id: str,
    failure_reason: str,
    error_type: NormalizedErrorType = NormalizedErrorType.CHECKPOINT_INVALID,
    task_id: str = "",
    plan_id: str = "",
    session_id: str = "",
    trace_id: str = "",
    original_error: Exception | None = None,
) -> NormalizedError:
    """Normalize a checkpoint failure to a consistent error format.

    Args:
        checkpoint_id: Checkpoint identifier
        failure_reason: Human-readable failure reason
        error_type: Specific checkpoint error type
        task_id: Associated task ID
        plan_id: Associated plan ID
        session_id: Associated session ID
        trace_id: Associated trace ID
        original_error: Original exception

    Returns:
        NormalizedError with checkpoint failure details
    """
    context = {
        "checkpoint_id": checkpoint_id,
        "plan_id": plan_id,
    }

    return NormalizedError(
        normalized_error_type=error_type,
        message=f"[Checkpoint {checkpoint_id}] {failure_reason}",
        raw_message=failure_reason,
        domain="checkpoint",
        task_id=task_id,
        session_id=session_id,
        trace_id=trace_id,
        source_layer=SourceLayer.CHECKPOINT,
        error_category=ErrorCategory.RECOVERABLE,
        fix_hint="Checkpoint operation failed. Check checkpoint state.",
        confidence=0.9,
        recoverable=True,
        retry_recommended=False,
        context=context,
        original_error=original_error,
        context_summary=f"Checkpoint {checkpoint_id} failure: {failure_reason[:50]}",
    )


@dataclass
class NormalizedErrorReport:
    """Report for normalized errors with fix hints."""

    normalized_error_type: NormalizedErrorType
    raw_message: str
    fix_hint: str = ""
    confidence: float = 1.0
    domain: str = ""
    task_id: str = ""
    command_id: str = ""
    parameter_name: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "normalized_error_type": self.normalized_error_type.value,
            "raw_message": self.raw_message,
            "fix_hint": self.fix_hint,
            "confidence": self.confidence,
            "domain": self.domain,
            "task_id": self.task_id,
            "command_id": self.command_id,
            "parameter_name": self.parameter_name,
        }


def normalize_bridge_command_cache_error(
    error_type: str,
    raw_message: str,
    domain: str = "",
    task_id: str = "",
    command_id: str = "",
    parameter_name: str = "",
) -> NormalizedErrorReport:
    """Normalize a bridge command cache error."""
    error_mapping = {
        "command_cache_miss": (
            NormalizedErrorType.UNKNOWN,
            "No known-good command found. Generate a fresh command for this task.",
        ),
        "command_cache_unavailable": (
            NormalizedErrorType.UNKNOWN,
            "Cache store not available. Proceed with standard command generation.",
        ),
        "known_good_command_degraded": (
            NormalizedErrorType.UNKNOWN,
            "Previously known-good command has multiple failures. Consider alternative approaches.",
        ),
        "cache_validation_failed": (
            NormalizedErrorType.UNKNOWN,
            "Cache entry failed validation. Regenerate command.",
        ),
    }

    mapped_type, fix_hint = error_mapping.get(
        error_type,
        (NormalizedErrorType.UNKNOWN, f"Unknown cache error: {error_type}"),
    )

    return NormalizedErrorReport(
        normalized_error_type=mapped_type,
        raw_message=raw_message,
        fix_hint=fix_hint,
        confidence=0.9 if error_type != "command_cache_miss" else 1.0,
        domain=domain,
        task_id=task_id,
        command_id=command_id,
        parameter_name=parameter_name,
    )


def normalize_verification_failure(
    verification_type: str | dict[str, Any] = "",
    failure_reason: str = "",
    domain: str = "",
    task_id: str = "",
    session_id: str = "",
    trace_id: str = "",
    step_id: str = "",
    expected_value: Any = None,
    actual_value: Any = None,
    original_error: Exception | None = None,
    verification_result: dict[str, Any] | None = None,
) -> NormalizedError:
    """Normalize a verification failure.

    Args:
        verification_type: Type of verification (bridge, visual, graph) or dict with verification result
        failure_reason: Human-readable failure reason
        domain: Execution domain
        task_id: Associated task ID
        session_id: Associated session ID
        trace_id: Associated trace ID
        step_id: Associated step ID
        expected_value: Expected value
        actual_value: Actual value
        original_error: Original exception
        verification_result: Alternative parameter - dict with verification result

    Returns:
        NormalizedError with verification failure details
    """
    # Support both verification_result dict and individual parameters
    if verification_result is not None and isinstance(verification_result, dict):
        # Extract from verification_result dict
        v_type = verification_result.get("verification_type", "unknown")
        missing_operators = verification_result.get("missing_operators", [])
        passed = verification_result.get("passed", True)

        # Build failure reason from verification result
        if not passed:
            if missing_operators:
                failure_reason = f"Missing operators: {', '.join(missing_operators)}"
            else:
                failure_reason = verification_result.get("error_message", "Verification failed")
        else:
            failure_reason = "Verification passed"

        verification_type = v_type

    verification_context = {
        "verification_type": verification_type if isinstance(verification_type, str) else str(verification_type),
        "step_id": step_id,
        "expected_value": str(expected_value) if expected_value is not None else None,
        "actual_value": str(actual_value) if actual_value is not None else None,
    }

    # Determine error type based on failure reason
    error_type = NormalizedErrorType.VERIFICATION_FAILED
    reason_lower = failure_reason.lower() if failure_reason else ""

    if "missing" in reason_lower and ("output" in reason_lower or "operator" in reason_lower):
        error_type = NormalizedErrorType.MISSING_OUTPUT

    return NormalizedError(
        normalized_error_type=error_type,
        message=f"[Verification] {verification_type}: {failure_reason}",
        raw_message=failure_reason,
        domain=domain,
        task_id=task_id,
        session_id=session_id,
        trace_id=trace_id,
        source_layer=SourceLayer.VERIFICATION,
        error_category=ErrorCategory.RECOVERABLE,
        fix_hint="Verification failed. Check if the operation completed correctly.",
        confidence=0.8,
        recoverable=True,
        retry_recommended=False,
        repair_candidate=True,
        verification_context=verification_context,
        original_error=original_error,
        context_summary=f"Verification failed: {verification_type} - {failure_reason[:50] if failure_reason else 'unknown'}",
    )


def normalize_provider_error(
    provider_name: str,
    error_message: str,
    error_type: str = "",
    domain: str = "",
    task_id: str = "",
    session_id: str = "",
    trace_id: str = "",
    original_error: Exception | None = None,
) -> NormalizedError:
    """Normalize a provider error.

    Args:
        provider_name: Name of the provider
        error_message: Error message from provider
        error_type: Provider-specific error type
        domain: Execution domain
        task_id: Associated task ID
        session_id: Associated session ID
        trace_id: Associated trace ID
        original_error: Original exception

    Returns:
        NormalizedError with provider failure details
    """
    normalized_type = NormalizedErrorType.UNKNOWN
    error_category = ErrorCategory.UNKNOWN
    message_lower = error_message.lower()

    if "timeout" in message_lower:
        normalized_type = NormalizedErrorType.PROVIDER_TIMEOUT
        error_category = ErrorCategory.TRANSIENT
    elif "unavailable" in message_lower:
        normalized_type = NormalizedErrorType.PROVIDER_UNAVAILABLE
        error_category = ErrorCategory.TRANSIENT
    elif "connection" in message_lower:
        normalized_type = NormalizedErrorType.BRIDGE_CONNECTION_FAILED
        error_category = ErrorCategory.TRANSIENT
    elif "invalid" in message_lower:
        normalized_type = NormalizedErrorType.INVALID_PARAMS
        error_category = ErrorCategory.RECOVERABLE
    else:
        normalized_type = NormalizedErrorType.PROVIDER_EXECUTION_FAILED
        error_category = ErrorCategory.UNKNOWN

    provider_context = {
        "provider_name": provider_name,
        "error_type": error_type,
    }

    return NormalizedError(
        normalized_error_type=normalized_type,
        message=f"[{provider_name}] {error_message}",
        raw_message=error_message,
        domain=domain,
        task_id=task_id,
        session_id=session_id,
        trace_id=trace_id,
        source_layer=SourceLayer.PROVIDER,
        error_category=error_category,
        error_code=error_type,
        fix_hint="Check provider availability and configuration.",
        confidence=0.8,
        recoverable=True,
        retry_recommended=True,
        provider_context=provider_context,
        original_error=original_error,
        context_summary=f"Provider {provider_name} error: {error_type or error_message[:50]}",
    )


def normalize_execution_failure(
    error_message: str,
    domain: str = "",
    task_id: str = "",
    session_id: str = "",
    trace_id: str = "",
    step_id: str = "",
    action: str = "",
    original_error: Exception | None = None,
) -> NormalizedError:
    """Normalize an execution failure.

    Args:
        error_message: Error message from execution
        domain: Execution domain
        task_id: Associated task ID
        session_id: Associated session ID
        trace_id: Associated trace ID
        step_id: Associated step ID
        action: Action that failed
        original_error: Original exception

    Returns:
        NormalizedError with execution failure details
    """
    return NormalizedError(
        normalized_error_type=NormalizedErrorType.EXECUTION_FAILED,
        message=error_message,
        raw_message=error_message,
        domain=domain,
        task_id=task_id,
        session_id=session_id,
        trace_id=trace_id,
        source_layer=SourceLayer.EXECUTION,
        error_category=ErrorCategory.RECOVERABLE,
        fix_hint="Execution failed. Check error details for recovery options.",
        confidence=0.8,
        recoverable=True,
        retry_recommended=True,
        repair_candidate=True,
        operator_or_node=action,
        original_error=original_error,
        context_summary=f"Execution failed: {action} - {error_message[:50]}",
    )


def normalize_recipe_failure(
    error_message: str,
    recipe_name: str = "",
    step_index: int = -1,
    domain: str = "",
    task_id: str = "",
    session_id: str = "",
    trace_id: str = "",
    original_error: Exception | None = None,
) -> NormalizedError:
    """Normalize a recipe execution failure.

    Args:
        error_message: Error message from recipe execution
        recipe_name: Name of the recipe
        step_index: Index of the failed step
        domain: Execution domain
        task_id: Associated task ID
        session_id: Associated session ID
        trace_id: Associated trace ID
        original_error: Original exception

    Returns:
        NormalizedError with recipe failure details
    """
    return NormalizedError(
        normalized_error_type=NormalizedErrorType.STEP_FAILED,
        message=f"[Recipe {recipe_name}] Step {step_index}: {error_message}",
        raw_message=error_message,
        domain=domain,
        task_id=task_id,
        session_id=session_id,
        trace_id=trace_id,
        source_layer=SourceLayer.RECIPE,
        error_category=ErrorCategory.RECOVERABLE,
        fix_hint="Recipe step failed. Check step configuration.",
        confidence=0.9,
        recoverable=True,
        retry_recommended=True,
        repair_candidate=True,
        original_error=original_error,
        context_summary=f"Recipe {recipe_name} failed at step {step_index}: {error_message[:50]}",
    )