"""Knowledge Pipeline Error Normalization.

Extends the base error normalizer with knowledge/RAG-specific error types
and recovery strategies for the knowledge distillation pipeline.

This module implements:
- KnowledgeErrorType, RAGErrorType, PlanningErrorType enums
- ErrorDomain enum for subsystem classification
- KnowledgeErrorNormalizer for knowledge-specific normalization
- Safe wrappers for knowledge operations
- ErrorRecoveryHandler for automated recovery
- ErrorLogger for structured error logging
"""

from __future__ import annotations

__all__ = [
    # Enums
    "ErrorDomain",
    "KnowledgeErrorType",
    "RAGErrorType",
    "PlanningErrorType",
    "VerificationErrorType",
    "ExecutionErrorType",
    "ErrorSeverity",
    # Dataclasses
    "KnowledgeError",
    "ErrorRecoveryAction",
    # Normalizer
    "KnowledgeErrorNormalizer",
    # Safe wrappers
    "SafeDistillationWrapper",
    "SafeRAGWrapper",
    "SafeValidationWrapper",
    # Recovery
    "ErrorRecoveryHandler",
    # Logging
    "KnowledgeErrorLogger",
    "ErrorDashboard",
    # Mapping
    "ERROR_TYPE_BY_DOMAIN",
]

import json
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar

# Import base error types for compatibility
from app.learning.error_normalizer import (
    NormalizedError,
    NormalizedErrorType,
    SourceLayer,
    ErrorCategory,
)


# ============================================================================
# ERROR DOMAIN ENUMS
# ============================================================================

class ErrorDomain(str, Enum):
    """Error domain/subsystem for routing decisions."""

    EXECUTION = "execution"      # Bridge execution, node creation
    RAG = "rag"                  # RAG index, retrieval
    KNOWLEDGE = "knowledge"      # Distillation, validation, storage
    PLANNING = "planning"        # Plan generation, subgoal decomposition
    MEMORY = "memory"            # Memory operations
    VERIFICATION = "verification"  # Post-execution verification
    GENERAL = "general"          # Uncategorized errors


class ErrorSeverity(str, Enum):
    """Error severity levels."""

    CRITICAL = "critical"  # Blocks all execution
    HIGH = "high"          # Major issue, blocks current task
    MEDIUM = "medium"      # Degraded functionality
    LOW = "low"            # Informational, minor issue


class ExecutionErrorType(str, Enum):
    """Execution errors (domain: EXECUTION)."""

    NODE_NOT_FOUND = "node_not_found"
    PARAMETER_INVALID = "parameter_invalid"
    CONNECTION_FAILED = "connection_failed"
    TIMEOUT = "timeout"
    PERMISSION_DENIED = "permission_denied"
    INVALID_OPERATION = "invalid_operation"
    NETWORK_ERROR = "network_error"
    BRIDGE_UNAVAILABLE = "bridge_unavailable"


class RAGErrorType(str, Enum):
    """RAG/Retrieval errors (domain: RAG)."""

    RAG_INDEX_CORRUPTED = "rag_index_corrupted"
    RAG_INDEX_MISSING = "rag_index_missing"
    RETRIEVAL_FAILED = "retrieval_failed"
    CHUNK_MALFORMED = "chunk_malformed"
    INDEX_OUT_OF_SYNC = "index_out_of_sync"
    EMBEDDING_FAILED = "embedding_failed"
    EMBEDDING_TIMEOUT = "embedding_timeout"
    INVALID_QUERY = "invalid_query"


class KnowledgeErrorType(str, Enum):
    """Knowledge pipeline errors (domain: KNOWLEDGE)."""

    TRANSCRIPT_SOURCE_MISSING = "transcript_source_missing"
    TRANSCRIPT_PARSE_FAILED = "transcript_parse_failed"
    TUTORIAL_DISTILLATION_FAILED = "tutorial_distillation_failed"
    KNOWLEDGE_SCHEMA_INVALID = "knowledge_schema_invalid"
    RECIPE_EXTRACTION_FAILED = "recipe_extraction_failed"
    DISTILLATION_CONFIDENCE_TOO_LOW = "distillation_confidence_too_low"
    VALIDATION_FAILED = "validation_failed"
    CONTRADICTORY_KNOWLEDGE = "contradictory_knowledge"
    KNOWLEDGE_STORE_ERROR = "knowledge_store_error"
    PROVENANCE_MISSING = "provenance_missing"
    DUPLICATE_ARTIFACT = "duplicate_artifact"
    UNSUPPORTED_DOMAIN = "unsupported_domain"
    INSUFFICIENT_CONTENT = "insufficient_content"


class PlanningErrorType(str, Enum):
    """Planning errors (domain: PLANNING)."""

    DECOMPOSITION_FAILED = "decomposition_failed"
    INVALID_SUBGOALS = "invalid_subgoals"
    NO_VIABLE_PLAN = "no_viable_plan"
    PLANNER_TIMEOUT = "planner_timeout"
    INSUFFICIENT_CONTEXT = "insufficient_context"
    PLAN_CONFLICT = "plan_conflict"
    CIRCULAR_DEPENDENCY = "circular_dependency"


class VerificationErrorType(str, Enum):
    """Verification errors (domain: VERIFICATION)."""

    VERIFICATION_FAILED = "verification_failed"
    STATE_MISMATCH = "state_mismatch"
    EXPECTED_STATE_UNDEFINED = "expected_state_undefined"
    SCREENSHOT_ANALYSIS_FAILED = "screenshot_analysis_failed"
    OUTPUT_MISMATCH = "output_mismatch"
    PREREQUISITE_NOT_MET = "prerequisite_not_met"


# Map error types by domain
ERROR_TYPE_BY_DOMAIN: dict[ErrorDomain, type[Enum]] = {
    ErrorDomain.EXECUTION: ExecutionErrorType,
    ErrorDomain.RAG: RAGErrorType,
    ErrorDomain.KNOWLEDGE: KnowledgeErrorType,
    ErrorDomain.PLANNING: PlanningErrorType,
    ErrorDomain.VERIFICATION: VerificationErrorType,
}


# ============================================================================
# KNOWLEDGE ERROR DATACLASS
# ============================================================================

@dataclass
class KnowledgeError:
    """
    Normalized error representation for knowledge pipeline.

    Consistent across all domains with recovery suggestions.
    """

    error_type: str  # One of the error type enum values
    domain: ErrorDomain
    severity: ErrorSeverity
    message: str
    original_error: Optional[str] = None
    context: dict[str, Any] = field(default_factory=dict)
    recovery_suggestion: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    traceback_str: Optional[str] = None
    error_id: str = field(default_factory=lambda: f"kerr_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "error_id": self.error_id,
            "error_type": self.error_type,
            "domain": self.domain.value,
            "severity": self.severity.value,
            "message": self.message,
            "original_error": self.original_error,
            "context": self.context,
            "recovery_suggestion": self.recovery_suggestion,
            "timestamp": self.timestamp,
            "traceback": self.traceback_str,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "KnowledgeError":
        """Deserialize from dictionary."""
        domain_value = data.get("domain", "general")
        try:
            domain = ErrorDomain(domain_value)
        except ValueError:
            domain = ErrorDomain.GENERAL

        severity_value = data.get("severity", "medium")
        try:
            severity = ErrorSeverity(severity_value)
        except ValueError:
            severity = ErrorSeverity.MEDIUM

        return cls(
            error_id=str(data.get("error_id", "")),
            error_type=str(data.get("error_type", "unknown")),
            domain=domain,
            severity=severity,
            message=str(data.get("message", "")),
            original_error=data.get("original_error"),
            context=dict(data.get("context", {})),
            recovery_suggestion=data.get("recovery_suggestion"),
            timestamp=str(data.get("timestamp", "")),
            traceback_str=data.get("traceback"),
        )

    def to_normalized_error(self) -> NormalizedError:
        """Convert to base NormalizedError for compatibility."""
        # Map domain to SourceLayer
        domain_to_source = {
            ErrorDomain.EXECUTION: SourceLayer.EXECUTION,
            ErrorDomain.RAG: SourceLayer.RUNTIME,
            ErrorDomain.KNOWLEDGE: SourceLayer.RUNTIME,
            ErrorDomain.PLANNING: SourceLayer.PLANNING,
            ErrorDomain.VERIFICATION: SourceLayer.VERIFICATION,
            ErrorDomain.MEMORY: SourceLayer.MEMORY,
            ErrorDomain.GENERAL: SourceLayer.UNKNOWN,
        }

        # Map severity to recoverable
        recoverable = self.severity not in (ErrorSeverity.CRITICAL,)

        return NormalizedError(
            error_id=self.error_id,
            normalized_error_type=NormalizedErrorType.UNKNOWN,
            message=self.message,
            raw_message=self.original_error or self.message,
            source_layer=domain_to_source.get(self.domain, SourceLayer.UNKNOWN),
            error_category=ErrorCategory.RECOVERABLE if recoverable else ErrorCategory.PERMANENT,
            fix_hint=self.recovery_suggestion or "",
            recoverable=recoverable,
            created_at=self.timestamp,
            context=self.context,
        )


# ============================================================================
# ERROR RECOVERY ACTION
# ============================================================================

@dataclass
class ErrorRecoveryAction:
    """Recovery action for an error."""

    action: str  # "retry", "queue_for_review", "reject", "fallback", "fail_safe", "rebuild_index"
    reason: str
    max_retries: int = 0
    retry_delay: float = 1.0
    backoff_factor: float = 1.0
    fallback: Optional[str] = None
    escalate_to_human: bool = False
    reject: bool = False
    retry_count: int = 0

    def should_retry(self) -> bool:
        """Check if should retry."""
        return self.action == "retry" and self.retry_count < self.max_retries

    def next_retry_delay(self) -> float:
        """Get delay for next retry with backoff."""
        return self.retry_delay * (self.backoff_factor ** self.retry_count)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "action": self.action,
            "reason": self.reason,
            "max_retries": self.max_retries,
            "retry_delay": self.retry_delay,
            "backoff_factor": self.backoff_factor,
            "fallback": self.fallback,
            "escalate_to_human": self.escalate_to_human,
            "reject": self.reject,
            "retry_count": self.retry_count,
        }


# ============================================================================
# KNOWLEDGE ERROR NORMALIZER
# ============================================================================

class KnowledgeErrorNormalizer:
    """
    Normalize errors from knowledge pipeline into consistent format.

    Handles knowledge, RAG, planning, and execution errors.
    """

    # Error type mapping: exception name -> normalized error info
    ERROR_MAPPINGS: dict[str, dict[str, Any]] = {
        # Knowledge/RAG errors
        "FileNotFoundError": {
            "error_type": KnowledgeErrorType.TRANSCRIPT_SOURCE_MISSING,
            "domain": ErrorDomain.KNOWLEDGE,
            "severity": ErrorSeverity.HIGH,
        },
        "JSONDecodeError": {
            "error_type": KnowledgeErrorType.KNOWLEDGE_SCHEMA_INVALID,
            "domain": ErrorDomain.KNOWLEDGE,
            "severity": ErrorSeverity.HIGH,
        },
        "ValueError": {
            "error_type": KnowledgeErrorType.RECIPE_EXTRACTION_FAILED,
            "domain": ErrorDomain.KNOWLEDGE,
            "severity": ErrorSeverity.MEDIUM,
        },
        "AssertionError": {
            "error_type": KnowledgeErrorType.VALIDATION_FAILED,
            "domain": ErrorDomain.KNOWLEDGE,
            "severity": ErrorSeverity.HIGH,
        },
        "KeyError": {
            "error_type": KnowledgeErrorType.KNOWLEDGE_SCHEMA_INVALID,
            "domain": ErrorDomain.KNOWLEDGE,
            "severity": ErrorSeverity.HIGH,
        },
        "TypeError": {
            "error_type": KnowledgeErrorType.KNOWLEDGE_SCHEMA_INVALID,
            "domain": ErrorDomain.KNOWLEDGE,
            "severity": ErrorSeverity.MEDIUM,
        },

        # Execution errors
        "AttributeError": {
            "error_type": ExecutionErrorType.NODE_NOT_FOUND,
            "domain": ErrorDomain.EXECUTION,
            "severity": ErrorSeverity.HIGH,
        },
        "TimeoutError": {
            "error_type": ExecutionErrorType.TIMEOUT,
            "domain": ErrorDomain.EXECUTION,
            "severity": ErrorSeverity.MEDIUM,
        },
        "ConnectionError": {
            "error_type": ExecutionErrorType.CONNECTION_FAILED,
            "domain": ErrorDomain.EXECUTION,
            "severity": ErrorSeverity.HIGH,
        },
        "PermissionError": {
            "error_type": ExecutionErrorType.PERMISSION_DENIED,
            "domain": ErrorDomain.EXECUTION,
            "severity": ErrorSeverity.HIGH,
        },

        # Planning errors
        "RecursionError": {
            "error_type": PlanningErrorType.DECOMPOSITION_FAILED,
            "domain": ErrorDomain.PLANNING,
            "severity": ErrorSeverity.HIGH,
        },
    }

    # Pattern-based error detection
    ERROR_PATTERNS: list[tuple[str, str, ErrorDomain, ErrorSeverity]] = [
        # Knowledge patterns
        (r"transcript.*not found", KnowledgeErrorType.TRANSCRIPT_SOURCE_MISSING.value, ErrorDomain.KNOWLEDGE, ErrorSeverity.HIGH),
        (r"transcript.*missing", KnowledgeErrorType.TRANSCRIPT_SOURCE_MISSING.value, ErrorDomain.KNOWLEDGE, ErrorSeverity.HIGH),
        (r"distill.*failed", KnowledgeErrorType.TUTORIAL_DISTILLATION_FAILED.value, ErrorDomain.KNOWLEDGE, ErrorSeverity.HIGH),
        (r"schema.*invalid", KnowledgeErrorType.KNOWLEDGE_SCHEMA_INVALID.value, ErrorDomain.KNOWLEDGE, ErrorSeverity.HIGH),
        (r"confidence.*low", KnowledgeErrorType.DISTILLATION_CONFIDENCE_TOO_LOW.value, ErrorDomain.KNOWLEDGE, ErrorSeverity.MEDIUM),
        (r"recipe.*failed", KnowledgeErrorType.RECIPE_EXTRACTION_FAILED.value, ErrorDomain.KNOWLEDGE, ErrorSeverity.HIGH),
        (r"contradict", KnowledgeErrorType.CONTRADICTORY_KNOWLEDGE.value, ErrorDomain.KNOWLEDGE, ErrorSeverity.MEDIUM),
        (r"validation.*failed", KnowledgeErrorType.VALIDATION_FAILED.value, ErrorDomain.KNOWLEDGE, ErrorSeverity.MEDIUM),

        # RAG patterns
        (r"rag.*corrupted", RAGErrorType.RAG_INDEX_CORRUPTED.value, ErrorDomain.RAG, ErrorSeverity.CRITICAL),
        (r"rag.*missing", RAGErrorType.RAG_INDEX_MISSING.value, ErrorDomain.RAG, ErrorSeverity.HIGH),
        (r"retrieval.*failed", RAGErrorType.RETRIEVAL_FAILED.value, ErrorDomain.RAG, ErrorSeverity.MEDIUM),
        (r"chunk.*malformed", RAGErrorType.CHUNK_MALFORMED.value, ErrorDomain.RAG, ErrorSeverity.MEDIUM),
        (r"embedding.*failed", RAGErrorType.EMBEDDING_FAILED.value, ErrorDomain.RAG, ErrorSeverity.HIGH),

        # Execution patterns
        (r"node.*not found", ExecutionErrorType.NODE_NOT_FOUND.value, ErrorDomain.EXECUTION, ErrorSeverity.HIGH),
        (r"parameter.*invalid", ExecutionErrorType.PARAMETER_INVALID.value, ErrorDomain.EXECUTION, ErrorSeverity.MEDIUM),
        (r"timeout", ExecutionErrorType.TIMEOUT.value, ErrorDomain.EXECUTION, ErrorSeverity.MEDIUM),
        (r"connection.*failed", ExecutionErrorType.CONNECTION_FAILED.value, ErrorDomain.EXECUTION, ErrorSeverity.HIGH),

        # Planning patterns
        (r"decomposition.*failed", PlanningErrorType.DECOMPOSITION_FAILED.value, ErrorDomain.PLANNING, ErrorSeverity.HIGH),
        (r"no.*viable.*plan", PlanningErrorType.NO_VIABLE_PLAN.value, ErrorDomain.PLANNING, ErrorSeverity.HIGH),
    ]

    @staticmethod
    def normalize(
        error: Exception,
        error_message: Optional[str] = None,
        context: Optional[dict[str, Any]] = None,
        domain_hint: Optional[ErrorDomain] = None,
    ) -> KnowledgeError:
        """
        Normalize raw exception into KnowledgeError.

        Args:
            error: The exception to normalize
            error_message: Optional custom error message
            context: Additional error context
            domain_hint: Hint about which domain the error occurred in

        Returns:
            Normalized KnowledgeError instance
        """
        import re

        context = context or {}
        error_type_name = type(error).__name__
        message = error_message or str(error)

        # Look up mapping by exception type
        mapping = KnowledgeErrorNormalizer.ERROR_MAPPINGS.get(error_type_name, {})

        normalized_type = mapping.get("error_type")
        domain = domain_hint or mapping.get("domain", ErrorDomain.GENERAL)
        severity = mapping.get("severity", ErrorSeverity.MEDIUM)

        # If no direct mapping, try pattern matching
        if not normalized_type:
            message_lower = message.lower()
            for pattern, err_type, err_domain, err_severity in KnowledgeErrorNormalizer.ERROR_PATTERNS:
                if re.search(pattern, message_lower):
                    normalized_type = err_type
                    domain = err_domain
                    severity = err_severity
                    break

        # Default to unknown if still no match
        if not normalized_type:
            normalized_type = f"unknown_{error_type_name}"
            domain = domain_hint or ErrorDomain.GENERAL
            severity = ErrorSeverity.LOW

        # Convert enum to value string if needed
        error_type_str = normalized_type.value if hasattr(normalized_type, 'value') else str(normalized_type)

        # Generate recovery suggestion
        recovery = KnowledgeErrorNormalizer._suggest_recovery(
            error_type_str,
            domain,
            context,
        )

        return KnowledgeError(
            error_type=error_type_str,
            domain=domain,
            severity=severity,
            message=message,
            original_error=str(error),
            context=context,
            recovery_suggestion=recovery,
            traceback_str=traceback.format_exc() if error else None,
        )

    @staticmethod
    def normalize_from_string(
        error_string: str,
        domain: ErrorDomain = ErrorDomain.GENERAL,
        context: Optional[dict[str, Any]] = None,
    ) -> KnowledgeError:
        """
        Normalize error from string (when exception not available).

        Args:
            error_string: The error message string
            domain: Hint about error domain
            context: Additional error context

        Returns:
            Normalized KnowledgeError instance
        """
        import re

        context = context or {}
        error_type = "unknown_error"
        severity = ErrorSeverity.MEDIUM
        detected_domain = domain

        message_lower = error_string.lower()

        # Pattern matching
        for pattern, err_type, err_domain, err_severity in KnowledgeErrorNormalizer.ERROR_PATTERNS:
            if re.search(pattern, message_lower):
                error_type = err_type
                detected_domain = err_domain
                severity = err_severity
                break

        recovery = KnowledgeErrorNormalizer._suggest_recovery(
            error_type,
            detected_domain,
            context,
        )

        return KnowledgeError(
            error_type=error_type,
            domain=detected_domain,
            severity=severity,
            message=error_string,
            context=context,
            recovery_suggestion=recovery,
        )

    @staticmethod
    def _suggest_recovery(
        error_type: str,
        domain: ErrorDomain,
        context: dict[str, Any],
    ) -> str:
        """Suggest recovery action for error."""

        suggestions: dict[str, str] = {
            # Knowledge errors
            KnowledgeErrorType.TRANSCRIPT_SOURCE_MISSING.value: (
                f"Ensure transcript file exists at {context.get('expected_path', 'specified path')}"
            ),
            KnowledgeErrorType.TUTORIAL_DISTILLATION_FAILED.value: (
                "Check transcript format and content quality. "
                "Try with verbose logging to identify parsing issue."
            ),
            KnowledgeErrorType.KNOWLEDGE_SCHEMA_INVALID.value: (
                "Recipe schema mismatch. Validate against schema. "
                f"Check: {', '.join(context.get('invalid_fields', ['all fields']))}"
            ),
            KnowledgeErrorType.DISTILLATION_CONFIDENCE_TOO_LOW.value: (
                f"Confidence {context.get('confidence', '?')} below threshold "
                f"{context.get('threshold', 0.7)}. Improve source material quality."
            ),
            KnowledgeErrorType.CONTRADICTORY_KNOWLEDGE.value: (
                f"Conflict with existing artifact: {context.get('conflicting_artifact', 'unknown')}. "
                "Manual review needed to resolve."
            ),
            KnowledgeErrorType.RECIPE_EXTRACTION_FAILED.value: (
                "Failed to extract recipe from content. Check format and structure."
            ),
            KnowledgeErrorType.VALIDATION_FAILED.value: (
                "Validation failed. Review validation criteria and artifact content."
            ),

            # RAG errors
            RAGErrorType.RAG_INDEX_CORRUPTED.value: (
                "RAG index is corrupted. Rebuild from source documents."
            ),
            RAGErrorType.RETRIEVAL_FAILED.value: (
                "Retrieval failed. Try alternative search or rebuild index."
            ),
            RAGErrorType.EMBEDDING_FAILED.value: (
                "Embedding generation failed. Check model availability and input format."
            ),

            # Execution errors
            ExecutionErrorType.NODE_NOT_FOUND.value: (
                f"Node '{context.get('node_name', 'unknown')}' not found. "
                f"Check node exists at '{context.get('expected_path', 'expected path')}'."
            ),
            ExecutionErrorType.TIMEOUT.value: (
                f"Operation timed out after {context.get('timeout', 30)}s. "
                "Increase timeout or optimize operation."
            ),
            ExecutionErrorType.CONNECTION_FAILED.value: (
                "Connection failed. Check if the target service is running."
            ),

            # Planning errors
            PlanningErrorType.DECOMPOSITION_FAILED.value: (
                "Decomposition failed. Try simpler goal or provide more context."
            ),
            PlanningErrorType.NO_VIABLE_PLAN.value: (
                "No viable plan found. Review goal feasibility and constraints."
            ),
        }

        return suggestions.get(error_type, "Unknown error type - manual investigation needed")


# ============================================================================
# ERROR RECOVERY HANDLER
# ============================================================================

class ErrorRecoveryHandler:
    """
    Handle errors with recovery strategies.

    Determines appropriate recovery action for each error type.
    """

    @staticmethod
    def handle_error(
        error: KnowledgeError,
        context: Optional[dict[str, Any]] = None,
    ) -> ErrorRecoveryAction:
        """
        Determine recovery action for error.

        Args:
            error: The normalized error
            context: Additional context for recovery decision

        Returns:
            ErrorRecoveryAction with recovery strategy
        """
        context = context or {}

        if error.domain == ErrorDomain.KNOWLEDGE:
            return ErrorRecoveryHandler._handle_knowledge_error(error, context)
        elif error.domain == ErrorDomain.RAG:
            return ErrorRecoveryHandler._handle_rag_error(error, context)
        elif error.domain == ErrorDomain.EXECUTION:
            return ErrorRecoveryHandler._handle_execution_error(error, context)
        elif error.domain == ErrorDomain.PLANNING:
            return ErrorRecoveryHandler._handle_planning_error(error, context)
        else:
            return ErrorRecoveryAction(
                action="log_and_continue",
                reason="Unknown domain, proceeding with caution",
            )

    @staticmethod
    def _handle_knowledge_error(
        error: KnowledgeError,
        context: dict[str, Any],
    ) -> ErrorRecoveryAction:
        """Handle knowledge pipeline errors."""

        error_type = error.error_type

        if error_type == KnowledgeErrorType.TRANSCRIPT_SOURCE_MISSING.value:
            return ErrorRecoveryAction(
                action="retry",
                reason="Transcript source missing, retry with alternative source",
                max_retries=3,
                retry_delay=2.0,
            )

        elif error_type == KnowledgeErrorType.DISTILLATION_CONFIDENCE_TOO_LOW.value:
            return ErrorRecoveryAction(
                action="queue_for_review",
                reason="Low confidence distillation, queue for manual review",
                escalate_to_human=True,
            )

        elif error_type == KnowledgeErrorType.KNOWLEDGE_SCHEMA_INVALID.value:
            return ErrorRecoveryAction(
                action="reject",
                reason="Invalid schema, artifact cannot be stored",
                reject=True,
            )

        elif error_type == KnowledgeErrorType.CONTRADICTORY_KNOWLEDGE.value:
            return ErrorRecoveryAction(
                action="queue_for_review",
                reason="Contradicts existing knowledge, needs manual resolution",
                escalate_to_human=True,
            )

        elif error_type == KnowledgeErrorType.TUTORIAL_DISTILLATION_FAILED.value:
            return ErrorRecoveryAction(
                action="retry",
                reason="Distillation failed, retry with different parameters",
                max_retries=2,
                retry_delay=3.0,
            )

        else:
            return ErrorRecoveryAction(
                action="log_and_skip",
                reason="Unknown knowledge error, skipping this artifact",
            )

    @staticmethod
    def _handle_rag_error(
        error: KnowledgeError,
        context: dict[str, Any],
    ) -> ErrorRecoveryAction:
        """Handle RAG errors."""

        error_type = error.error_type

        if error_type == RAGErrorType.RAG_INDEX_CORRUPTED.value:
            return ErrorRecoveryAction(
                action="rebuild_index",
                reason="RAG index corrupted, rebuild from source",
                escalate_to_human=True,
            )

        elif error_type == RAGErrorType.RETRIEVAL_FAILED.value:
            return ErrorRecoveryAction(
                action="fallback",
                reason="Retrieval failed, use fallback strategy",
                fallback="use_keyword_search",
            )

        elif error_type == RAGErrorType.EMBEDDING_FAILED.value:
            return ErrorRecoveryAction(
                action="retry",
                reason="Embedding failed, retry",
                max_retries=2,
                retry_delay=1.0,
            )

        else:
            return ErrorRecoveryAction(
                action="log_and_continue",
                reason="RAG error, trying alternative retrieval",
            )

    @staticmethod
    def _handle_execution_error(
        error: KnowledgeError,
        context: dict[str, Any],
    ) -> ErrorRecoveryAction:
        """Handle execution errors."""

        error_type = error.error_type

        if error_type == ExecutionErrorType.NODE_NOT_FOUND.value:
            return ErrorRecoveryAction(
                action="retry",
                reason="Node not found, retry creation",
                max_retries=2,
                retry_delay=1.0,
            )

        elif error_type == ExecutionErrorType.TIMEOUT.value:
            return ErrorRecoveryAction(
                action="retry_with_backoff",
                reason="Operation timed out, retry with longer timeout",
                backoff_factor=1.5,
                max_retries=2,
            )

        elif error_type == ExecutionErrorType.CONNECTION_FAILED.value:
            return ErrorRecoveryAction(
                action="retry",
                reason="Connection failed, retry",
                max_retries=3,
                retry_delay=2.0,
            )

        else:
            return ErrorRecoveryAction(
                action="fail_safe",
                reason="Execution error, cannot recover",
            )

    @staticmethod
    def _handle_planning_error(
        error: KnowledgeError,
        context: dict[str, Any],
    ) -> ErrorRecoveryAction:
        """Handle planning errors."""

        error_type = error.error_type

        if error_type == PlanningErrorType.DECOMPOSITION_FAILED.value:
            return ErrorRecoveryAction(
                action="simplify",
                reason="Decomposition failed, try simpler goal",
                fallback="use_direct_execution",
            )

        elif error_type == PlanningErrorType.NO_VIABLE_PLAN.value:
            return ErrorRecoveryAction(
                action="escalate",
                reason="No viable plan found, escalate for human input",
                escalate_to_human=True,
            )

        else:
            return ErrorRecoveryAction(
                action="fail_safe",
                reason="Planning error, cannot proceed",
            )


# ============================================================================
# SAFE WRAPPERS FOR KNOWLEDGE OPERATIONS
# ============================================================================

T = TypeVar("T")


class SafeDistillationWrapper:
    """
    Safe wrapper for tutorial distillation with error handling.
    """

    def __init__(self, distiller: Any):
        """Initialize with a distiller instance."""
        self.distiller = distiller
        self.errors: list[KnowledgeError] = []

    def distill_with_error_handling(
        self,
        transcript_text: str,
        domain: str,
        title: str,
        source_url: str,
        confidence_threshold: float = 0.5,
    ) -> tuple[Optional[Any], list[KnowledgeError]]:
        """
        Distill recipe with error collection.

        Args:
            transcript_text: The transcript content
            domain: Domain (houdini, touchdesigner)
            title: Tutorial title
            source_url: Source URL
            confidence_threshold: Minimum confidence threshold

        Returns:
            Tuple of (recipe_or_none, list_of_errors)
        """
        errors: list[KnowledgeError] = []

        try:
            # Validate inputs
            if not transcript_text or not transcript_text.strip():
                errors.append(
                    KnowledgeErrorNormalizer.normalize_from_string(
                        "Transcript text is empty",
                        domain=ErrorDomain.KNOWLEDGE,
                        context={"source": source_url},
                    )
                )
                return None, errors

            # Distill
            try:
                recipe = self.distiller.distill_from_transcript(
                    transcript_text=transcript_text,
                    domain=domain,
                    title=title,
                    source_url=source_url,
                )
            except ValueError as e:
                errors.append(
                    KnowledgeErrorNormalizer.normalize(
                        e,
                        f"Recipe extraction failed: {str(e)}",
                        context={"domain": domain, "title": title},
                        domain_hint=ErrorDomain.KNOWLEDGE,
                    )
                )
                return None, errors
            except json.JSONDecodeError as e:
                errors.append(
                    KnowledgeErrorNormalizer.normalize(
                        e,
                        f"Invalid JSON in extraction: {str(e)}",
                        context={"source": source_url},
                        domain_hint=ErrorDomain.KNOWLEDGE,
                    )
                )
                return None, errors

            # Validate confidence
            if hasattr(recipe, "confidence") and recipe.confidence < confidence_threshold:
                errors.append(
                    KnowledgeError(
                        error_type=KnowledgeErrorType.DISTILLATION_CONFIDENCE_TOO_LOW.value,
                        domain=ErrorDomain.KNOWLEDGE,
                        severity=ErrorSeverity.MEDIUM,
                        message=f"Distilled recipe confidence too low: {recipe.confidence:.0%}",
                        context={
                            "confidence": recipe.confidence,
                            "threshold": confidence_threshold,
                            "source": source_url,
                        },
                        recovery_suggestion="Review source material quality or improve distillation parameters",
                    )
                )
                # Still return the recipe but with error
                return recipe, errors

            return recipe, errors

        except Exception as e:
            # Unexpected error
            errors.append(
                KnowledgeErrorNormalizer.normalize(
                    e,
                    f"Unexpected distillation error: {str(e)}",
                    context={"source": source_url},
                    domain_hint=ErrorDomain.KNOWLEDGE,
                )
            )
            return None, errors


class SafeRAGWrapper:
    """
    Safe wrapper for RAG operations with error handling.
    """

    def __init__(self, rag_index: Any):
        """Initialize with a RAG index instance."""
        self.rag_index = rag_index
        self.errors: list[KnowledgeError] = []

    def add_chunk_with_error_handling(
        self,
        chunk: Any,
    ) -> tuple[bool, Optional[KnowledgeError]]:
        """
        Add chunk to index with error handling.

        Args:
            chunk: The RAG chunk to add

        Returns:
            Tuple of (success, error_or_none)
        """
        try:
            # Validate chunk
            if not hasattr(chunk, "chunk_id") or not chunk.chunk_id:
                return False, KnowledgeError(
                    error_type=RAGErrorType.CHUNK_MALFORMED.value,
                    domain=ErrorDomain.RAG,
                    severity=ErrorSeverity.HIGH,
                    message="RAG chunk missing chunk_id",
                    context={"chunk": str(chunk)[:100]},
                    recovery_suggestion="Verify chunk has chunk_id attribute",
                )

            if not hasattr(chunk, "text") or not chunk.text:
                return False, KnowledgeError(
                    error_type=RAGErrorType.CHUNK_MALFORMED.value,
                    domain=ErrorDomain.RAG,
                    severity=ErrorSeverity.HIGH,
                    message="RAG chunk missing text content",
                    context={"chunk_id": chunk.chunk_id},
                    recovery_suggestion="Verify chunk has text attribute",
                )

            # Add to index
            self.rag_index.add_chunk(chunk)
            return True, None

        except Exception as e:
            return False, KnowledgeErrorNormalizer.normalize(
                e,
                f"Failed to add chunk to RAG index: {str(e)}",
                context={"chunk_id": getattr(chunk, "chunk_id", "unknown")},
                domain_hint=ErrorDomain.RAG,
            )

    def retrieve_with_error_handling(
        self,
        query: str,
        k: int = 5,
    ) -> tuple[list[Any], Optional[KnowledgeError]]:
        """
        Retrieve from index with error handling.

        Args:
            query: Search query
            k: Number of results

        Returns:
            Tuple of (results, error_or_none)
        """
        try:
            if not query or not query.strip():
                return [], KnowledgeError(
                    error_type=RAGErrorType.INVALID_QUERY.value,
                    domain=ErrorDomain.RAG,
                    severity=ErrorSeverity.LOW,
                    message="Empty query provided",
                    recovery_suggestion="Provide a non-empty query string",
                )

            results = self.rag_index.retrieve(query, k=k)
            return results, None

        except Exception as e:
            error = KnowledgeErrorNormalizer.normalize(
                e,
                f"RAG retrieval failed: {str(e)}",
                context={"query": query[:100], "k": k},
                domain_hint=ErrorDomain.RAG,
            )
            return [], error


class SafeValidationWrapper:
    """
    Safe wrapper for validation operations with error collection.
    """

    def __init__(self, validator: Any):
        """Initialize with a validator instance."""
        self.validator = validator
        self.errors: list[KnowledgeError] = []

    def validate_with_error_collection(
        self,
        artifact: dict[str, Any],
        artifact_type: str = "recipe",
    ) -> tuple[bool, list[KnowledgeError]]:
        """
        Validate artifact and collect all errors.

        Args:
            artifact: The artifact to validate
            artifact_type: Type of artifact (recipe, tutorial, etc.)

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors: list[KnowledgeError] = []

        try:
            # Basic validation
            if not artifact:
                errors.append(KnowledgeError(
                    error_type=KnowledgeErrorType.KNOWLEDGE_SCHEMA_INVALID.value,
                    domain=ErrorDomain.KNOWLEDGE,
                    severity=ErrorSeverity.HIGH,
                    message="Empty artifact provided",
                    recovery_suggestion="Provide a valid artifact",
                ))
                return False, errors

            # Check required fields
            required_fields = ["id", "name"] if artifact_type == "recipe" else ["id"]
            missing_fields = [f for f in required_fields if f not in artifact]

            if missing_fields:
                errors.append(KnowledgeError(
                    error_type=KnowledgeErrorType.KNOWLEDGE_SCHEMA_INVALID.value,
                    domain=ErrorDomain.KNOWLEDGE,
                    severity=ErrorSeverity.HIGH,
                    message=f"Missing required fields: {', '.join(missing_fields)}",
                    context={"missing_fields": missing_fields, "artifact_id": artifact.get("id")},
                    recovery_suggestion="Add missing required fields",
                ))

            # Validate with underlying validator if available
            if hasattr(self.validator, "validate_artifact"):
                try:
                    result = self.validator.validate_artifact(artifact, artifact_type)
                    if not result:
                        errors.append(KnowledgeError(
                            error_type=KnowledgeErrorType.VALIDATION_FAILED.value,
                            domain=ErrorDomain.KNOWLEDGE,
                            severity=ErrorSeverity.MEDIUM,
                            message="Artifact failed validation",
                            context={"artifact_id": artifact.get("id")},
                            recovery_suggestion="Review artifact content against validation rules",
                        ))
                except Exception as e:
                    errors.append(KnowledgeErrorNormalizer.normalize(
                        e,
                        "Validation check failed",
                        context={"artifact_id": artifact.get("id")},
                        domain_hint=ErrorDomain.KNOWLEDGE,
                    ))

            is_valid = len(errors) == 0
            return is_valid, errors

        except Exception as e:
            errors.append(KnowledgeErrorNormalizer.normalize(
                e,
                f"Validation pipeline error: {str(e)}",
                context={"artifact_id": artifact.get("id", "unknown")},
                domain_hint=ErrorDomain.KNOWLEDGE,
            ))
            return False, errors


# ============================================================================
# ERROR LOGGING
# ============================================================================

class KnowledgeErrorLogger:
    """
    Log normalized errors with full context.
    """

    def __init__(self, log_dir: str = "data/logs/errors/"):
        """Initialize with log directory."""
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.errors: list[KnowledgeError] = []

    def log_error(
        self,
        error: KnowledgeError,
        recovery_action: Optional[ErrorRecoveryAction] = None,
    ) -> None:
        """
        Log error with recovery action.

        Args:
            error: The error to log
            recovery_action: Optional recovery action taken
        """
        self.errors.append(error)

        # Console output
        severity_icons = {
            ErrorSeverity.CRITICAL: "🔴",
            ErrorSeverity.HIGH: "🟠",
            ErrorSeverity.MEDIUM: "🟡",
            ErrorSeverity.LOW: "🟢",
        }
        icon = severity_icons.get(error.severity, "⚪")

        print(f"{icon} [{error.domain.value}] {error.error_type}: {error.message}")
        if error.recovery_suggestion:
            print(f"   Recovery: {error.recovery_suggestion}")
        if recovery_action:
            print(f"   Action: {recovery_action.action}")

        # File logging
        self._write_error_log(error, recovery_action)

    def _write_error_log(
        self,
        error: KnowledgeError,
        recovery_action: Optional[ErrorRecoveryAction],
    ) -> None:
        """Write error to log file."""
        log_file = self.log_dir / f"{error.domain.value}_errors.jsonl"

        log_entry = {
            **error.to_dict(),
            "recovery_action": recovery_action.to_dict() if recovery_action else None,
        }

        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")

    def get_error_summary(self) -> dict[str, Any]:
        """Get error summary statistics."""
        by_domain: dict[str, int] = {}
        by_severity: dict[str, int] = {s.value: 0 for s in ErrorSeverity}
        by_type: dict[str, int] = {}

        for error in self.errors:
            # By domain
            domain_name = error.domain.value
            by_domain[domain_name] = by_domain.get(domain_name, 0) + 1

            # By severity
            by_severity[error.severity.value] += 1

            # By type
            by_type[error.error_type] = by_type.get(error.error_type, 0) + 1

        return {
            "total_errors": len(self.errors),
            "by_domain": by_domain,
            "by_severity": by_severity,
            "by_type": by_type,
            "critical_count": by_severity.get("critical", 0),
            "high_count": by_severity.get("high", 0),
        }

    def clear(self) -> None:
        """Clear all logged errors."""
        self.errors.clear()


class ErrorDashboard:
    """Generate error reports and dashboards."""

    @staticmethod
    def generate_report(error_logger: KnowledgeErrorLogger) -> str:
        """Generate a formatted error report."""
        summary = error_logger.get_error_summary()

        report = f"""
ERROR REPORT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total Errors: {summary['total_errors']}
Critical: {summary['critical_count']}
High: {summary['high_count']}

By Domain:
{json.dumps(summary['by_domain'], indent=2)}

By Severity:
{json.dumps(summary['by_severity'], indent=2)}

By Type (Top 10):
"""
        # Top 10 error types
        sorted_types = sorted(summary['by_type'].items(), key=lambda x: -x[1])[:10]
        for error_type, count in sorted_types:
            report += f"  {error_type}: {count}\n"

        report += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"

        return report