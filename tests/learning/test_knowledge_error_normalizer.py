"""Tests for Knowledge Pipeline Error Normalization."""

from __future__ import annotations

import json
import pytest
from pathlib import Path
from datetime import datetime

from app.learning.knowledge_error_normalizer import (
    # Enums
    ErrorDomain,
    KnowledgeErrorType,
    RAGErrorType,
    PlanningErrorType,
    VerificationErrorType,
    ExecutionErrorType,
    ErrorSeverity,
    # Dataclasses
    KnowledgeError,
    ErrorRecoveryAction,
    # Normalizer
    KnowledgeErrorNormalizer,
    # Recovery
    ErrorRecoveryHandler,
    # Logging
    KnowledgeErrorLogger,
    ErrorDashboard,
    # Mapping
    ERROR_TYPE_BY_DOMAIN,
)


class TestErrorDomainEnum:
    """Tests for ErrorDomain enum."""

    def test_domain_values(self) -> None:
        """Test domain enum values."""
        assert ErrorDomain.EXECUTION.value == "execution"
        assert ErrorDomain.RAG.value == "rag"
        assert ErrorDomain.KNOWLEDGE.value == "knowledge"
        assert ErrorDomain.PLANNING.value == "planning"
        assert ErrorDomain.VERIFICATION.value == "verification"
        assert ErrorDomain.GENERAL.value == "general"

    def test_domain_from_string(self) -> None:
        """Test creating domain from string."""
        assert ErrorDomain("execution") == ErrorDomain.EXECUTION
        assert ErrorDomain("knowledge") == ErrorDomain.KNOWLEDGE


class TestKnowledgeErrorType:
    """Tests for KnowledgeErrorType enum."""

    def test_knowledge_error_types(self) -> None:
        """Test knowledge error type values."""
        assert KnowledgeErrorType.TRANSCRIPT_SOURCE_MISSING.value == "transcript_source_missing"
        assert KnowledgeErrorType.TUTORIAL_DISTILLATION_FAILED.value == "tutorial_distillation_failed"
        assert KnowledgeErrorType.KNOWLEDGE_SCHEMA_INVALID.value == "knowledge_schema_invalid"
        assert KnowledgeErrorType.DISTILLATION_CONFIDENCE_TOO_LOW.value == "distillation_confidence_too_low"
        assert KnowledgeErrorType.CONTRADICTORY_KNOWLEDGE.value == "contradictory_knowledge"

    def test_all_knowledge_errors_defined(self) -> None:
        """Test all expected knowledge error types exist."""
        expected = [
            "transcript_source_missing",
            "transcript_parse_failed",
            "tutorial_distillation_failed",
            "knowledge_schema_invalid",
            "recipe_extraction_failed",
            "distillation_confidence_too_low",
            "validation_failed",
            "contradictory_knowledge",
            "knowledge_store_error",
            "provenance_missing",
            "duplicate_artifact",
            "unsupported_domain",
            "insufficient_content",
        ]
        for error_type in expected:
            assert any(e.value == error_type for e in KnowledgeErrorType)


class TestRAGErrorType:
    """Tests for RAGErrorType enum."""

    def test_rag_error_types(self) -> None:
        """Test RAG error type values."""
        assert RAGErrorType.RAG_INDEX_CORRUPTED.value == "rag_index_corrupted"
        assert RAGErrorType.RETRIEVAL_FAILED.value == "retrieval_failed"
        assert RAGErrorType.CHUNK_MALFORMED.value == "chunk_malformed"
        assert RAGErrorType.EMBEDDING_FAILED.value == "embedding_failed"


class TestPlanningErrorType:
    """Tests for PlanningErrorType enum."""

    def test_planning_error_types(self) -> None:
        """Test planning error type values."""
        assert PlanningErrorType.DECOMPOSITION_FAILED.value == "decomposition_failed"
        assert PlanningErrorType.NO_VIABLE_PLAN.value == "no_viable_plan"
        assert PlanningErrorType.PLANNER_TIMEOUT.value == "planner_timeout"


class TestKnowledgeError:
    """Tests for KnowledgeError dataclass."""

    def test_create_error(self) -> None:
        """Test creating a knowledge error."""
        error = KnowledgeError(
            error_type=KnowledgeErrorType.TRANSCRIPT_SOURCE_MISSING.value,
            domain=ErrorDomain.KNOWLEDGE,
            severity=ErrorSeverity.HIGH,
            message="Transcript file not found",
        )

        assert error.error_type == "transcript_source_missing"
        assert error.domain == ErrorDomain.KNOWLEDGE
        assert error.severity == ErrorSeverity.HIGH
        assert error.message == "Transcript file not found"
        assert error.error_id.startswith("kerr_")

    def test_error_serialization(self) -> None:
        """Test error serialization to dict."""
        error = KnowledgeError(
            error_type=KnowledgeErrorType.VALIDATION_FAILED.value,
            domain=ErrorDomain.KNOWLEDGE,
            severity=ErrorSeverity.MEDIUM,
            message="Validation failed",
            context={"field": "confidence", "value": 0.3},
            recovery_suggestion="Increase confidence threshold",
        )

        data = error.to_dict()

        assert data["error_type"] == "validation_failed"
        assert data["domain"] == "knowledge"
        assert data["severity"] == "medium"
        assert data["context"]["field"] == "confidence"
        assert data["recovery_suggestion"] == "Increase confidence threshold"

    def test_error_deserialization(self) -> None:
        """Test error deserialization from dict."""
        data = {
            "error_id": "kerr_20240101120000",
            "error_type": "tutorial_distillation_failed",
            "domain": "knowledge",
            "severity": "high",
            "message": "Distillation error",
            "context": {"source": "tutorial.txt"},
        }

        error = KnowledgeError.from_dict(data)

        assert error.error_id == "kerr_20240101120000"
        assert error.error_type == "tutorial_distillation_failed"
        assert error.domain == ErrorDomain.KNOWLEDGE
        assert error.severity == ErrorSeverity.HIGH


class TestErrorRecoveryAction:
    """Tests for ErrorRecoveryAction dataclass."""

    def test_create_retry_action(self) -> None:
        """Test creating a retry action."""
        action = ErrorRecoveryAction(
            action="retry",
            reason="Temporary failure",
            max_retries=3,
            retry_delay=1.0,
            backoff_factor=2.0,
        )

        assert action.action == "retry"
        assert action.max_retries == 3
        assert action.should_retry() is True

    def test_retry_exhausted(self) -> None:
        """Test retry exhausted check."""
        action = ErrorRecoveryAction(
            action="retry",
            reason="Temporary failure",
            max_retries=2,
            retry_count=2,
        )

        assert action.should_retry() is False

    def test_backoff_calculation(self) -> None:
        """Test backoff delay calculation."""
        action = ErrorRecoveryAction(
            action="retry",
            reason="Timeout",
            retry_delay=1.0,
            backoff_factor=2.0,
        )

        # First retry: 1.0 * (2.0 ** 0) = 1.0
        action.retry_count = 0
        assert action.next_retry_delay() == 1.0

        # Second retry: 1.0 * (2.0 ** 1) = 2.0
        action.retry_count = 1
        assert action.next_retry_delay() == 2.0

        # Third retry: 1.0 * (2.0 ** 2) = 4.0
        action.retry_count = 2
        assert action.next_retry_delay() == 4.0

    def test_escalate_action(self) -> None:
        """Test escalate action."""
        action = ErrorRecoveryAction(
            action="queue_for_review",
            reason="Needs human review",
            escalate_to_human=True,
        )

        assert action.escalate_to_human is True
        assert action.should_retry() is False


class TestKnowledgeErrorNormalizer:
    """Tests for KnowledgeErrorNormalizer."""

    def test_normalize_file_not_found(self) -> None:
        """Test normalizing FileNotFoundError."""
        exc = FileNotFoundError("tutorial.txt not found")
        error = KnowledgeErrorNormalizer.normalize(
            exc,
            context={"expected_path": "data/tutorials/tutorial.txt"},
        )

        assert error.error_type == KnowledgeErrorType.TRANSCRIPT_SOURCE_MISSING.value
        assert error.domain == ErrorDomain.KNOWLEDGE
        assert error.severity == ErrorSeverity.HIGH

    def test_normalize_json_decode_error(self) -> None:
        """Test normalizing JSONDecodeError."""
        exc = json.JSONDecodeError("Expecting value", "", 0)
        error = KnowledgeErrorNormalizer.normalize(
            exc,
            error_message="Invalid JSON in recipe",
        )

        assert error.error_type == KnowledgeErrorType.KNOWLEDGE_SCHEMA_INVALID.value
        assert error.domain == ErrorDomain.KNOWLEDGE

    def test_normalize_timeout_error(self) -> None:
        """Test normalizing TimeoutError."""
        exc = TimeoutError("Operation timed out")
        error = KnowledgeErrorNormalizer.normalize(exc)

        assert error.error_type == ExecutionErrorType.TIMEOUT.value
        assert error.domain == ErrorDomain.EXECUTION
        assert error.severity == ErrorSeverity.MEDIUM

    def test_normalize_from_string_transcript_missing(self) -> None:
        """Test normalizing transcript missing from string."""
        error = KnowledgeErrorNormalizer.normalize_from_string(
            "Transcript file not found at path",
            domain=ErrorDomain.KNOWLEDGE,
        )

        assert error.error_type == KnowledgeErrorType.TRANSCRIPT_SOURCE_MISSING.value
        assert error.domain == ErrorDomain.KNOWLEDGE

    def test_normalize_from_string_distillation_failed(self) -> None:
        """Test normalizing distillation failure from string."""
        error = KnowledgeErrorNormalizer.normalize_from_string(
            "Distillation failed for tutorial",
            domain=ErrorDomain.KNOWLEDGE,
        )

        assert error.error_type == KnowledgeErrorType.TUTORIAL_DISTILLATION_FAILED.value

    def test_normalize_from_string_confidence_low(self) -> None:
        """Test normalizing low confidence from string."""
        error = KnowledgeErrorNormalizer.normalize_from_string(
            "Confidence too low: 0.42",
            domain=ErrorDomain.KNOWLEDGE,
            context={"confidence": 0.42, "threshold": 0.7},
        )

        assert error.error_type == KnowledgeErrorType.DISTILLATION_CONFIDENCE_TOO_LOW.value
        assert error.severity == ErrorSeverity.MEDIUM

    def test_normalize_from_string_rag_error(self) -> None:
        """Test normalizing RAG error from string."""
        error = KnowledgeErrorNormalizer.normalize_from_string(
            "RAG index corrupted",
            domain=ErrorDomain.RAG,
        )

        assert error.error_type == RAGErrorType.RAG_INDEX_CORRUPTED.value
        assert error.domain == ErrorDomain.RAG
        assert error.severity == ErrorSeverity.CRITICAL

    def test_normalize_from_string_node_not_found(self) -> None:
        """Test normalizing node not found from string."""
        error = KnowledgeErrorNormalizer.normalize_from_string(
            "Node geo1 not found in network",
            domain=ErrorDomain.EXECUTION,
            context={"node_name": "geo1"},
        )

        assert error.error_type == ExecutionErrorType.NODE_NOT_FOUND.value
        assert error.domain == ErrorDomain.EXECUTION

    def test_recovery_suggestion_transcript_missing(self) -> None:
        """Test recovery suggestion for transcript missing."""
        error = KnowledgeErrorNormalizer.normalize_from_string(
            "Transcript not found",
            context={"expected_path": "/data/tutorials/vid1.txt"},
        )

        assert "expected_path" in error.recovery_suggestion.lower() or "transcript" in error.recovery_suggestion.lower()

    def test_recovery_suggestion_confidence_low(self) -> None:
        """Test recovery suggestion for low confidence."""
        error = KnowledgeErrorNormalizer.normalize_from_string(
            "Confidence too low",
            context={"confidence": 0.42, "threshold": 0.7},
        )

        assert "confidence" in error.recovery_suggestion.lower() or "threshold" in error.recovery_suggestion.lower()


class TestErrorRecoveryHandler:
    """Tests for ErrorRecoveryHandler."""

    def test_handle_transcript_missing(self) -> None:
        """Test handling transcript missing error."""
        error = KnowledgeError(
            error_type=KnowledgeErrorType.TRANSCRIPT_SOURCE_MISSING.value,
            domain=ErrorDomain.KNOWLEDGE,
            severity=ErrorSeverity.HIGH,
            message="Transcript not found",
        )

        action = ErrorRecoveryHandler.handle_error(error)

        assert action.action == "retry"
        assert action.max_retries == 3

    def test_handle_confidence_low(self) -> None:
        """Test handling low confidence error."""
        error = KnowledgeError(
            error_type=KnowledgeErrorType.DISTILLATION_CONFIDENCE_TOO_LOW.value,
            domain=ErrorDomain.KNOWLEDGE,
            severity=ErrorSeverity.MEDIUM,
            message="Confidence 0.42 below threshold 0.7",
        )

        action = ErrorRecoveryHandler.handle_error(error)

        assert action.action == "queue_for_review"
        assert action.escalate_to_human is True

    def test_handle_schema_invalid(self) -> None:
        """Test handling schema invalid error."""
        error = KnowledgeError(
            error_type=KnowledgeErrorType.KNOWLEDGE_SCHEMA_INVALID.value,
            domain=ErrorDomain.KNOWLEDGE,
            severity=ErrorSeverity.HIGH,
            message="Invalid schema",
        )

        action = ErrorRecoveryHandler.handle_error(error)

        assert action.action == "reject"
        assert action.reject is True

    def test_handle_contradictory_knowledge(self) -> None:
        """Test handling contradictory knowledge error."""
        error = KnowledgeError(
            error_type=KnowledgeErrorType.CONTRADICTORY_KNOWLEDGE.value,
            domain=ErrorDomain.KNOWLEDGE,
            severity=ErrorSeverity.MEDIUM,
            message="Conflicts with existing artifact",
        )

        action = ErrorRecoveryHandler.handle_error(error)

        assert action.escalate_to_human is True

    def test_handle_rag_index_corrupted(self) -> None:
        """Test handling RAG index corrupted."""
        error = KnowledgeError(
            error_type=RAGErrorType.RAG_INDEX_CORRUPTED.value,
            domain=ErrorDomain.RAG,
            severity=ErrorSeverity.CRITICAL,
            message="RAG index is corrupted",
        )

        action = ErrorRecoveryHandler.handle_error(error)

        assert action.action == "rebuild_index"
        assert action.escalate_to_human is True

    def test_handle_retrieval_failed(self) -> None:
        """Test handling retrieval failed."""
        error = KnowledgeError(
            error_type=RAGErrorType.RETRIEVAL_FAILED.value,
            domain=ErrorDomain.RAG,
            severity=ErrorSeverity.MEDIUM,
            message="Retrieval failed",
        )

        action = ErrorRecoveryHandler.handle_error(error)

        assert action.action == "fallback"
        assert action.fallback == "use_keyword_search"

    def test_handle_node_not_found(self) -> None:
        """Test handling node not found."""
        error = KnowledgeError(
            error_type=ExecutionErrorType.NODE_NOT_FOUND.value,
            domain=ErrorDomain.EXECUTION,
            severity=ErrorSeverity.HIGH,
            message="Node not found",
            context={"node_name": "geo1"},
        )

        action = ErrorRecoveryHandler.handle_error(error)

        assert action.action == "retry"
        assert action.max_retries == 2

    def test_handle_timeout(self) -> None:
        """Test handling timeout."""
        error = KnowledgeError(
            error_type=ExecutionErrorType.TIMEOUT.value,
            domain=ErrorDomain.EXECUTION,
            severity=ErrorSeverity.MEDIUM,
            message="Operation timed out",
        )

        action = ErrorRecoveryHandler.handle_error(error)

        assert action.action == "retry_with_backoff"
        assert action.backoff_factor == 1.5

    def test_handle_unknown_domain(self) -> None:
        """Test handling unknown domain error."""
        error = KnowledgeError(
            error_type="unknown_error",
            domain=ErrorDomain.GENERAL,
            severity=ErrorSeverity.LOW,
            message="Unknown error",
        )

        action = ErrorRecoveryHandler.handle_error(error)

        assert action.action == "log_and_continue"


class TestKnowledgeErrorLogger:
    """Tests for KnowledgeErrorLogger."""

    def test_log_error(self, tmp_path: Path) -> None:
        """Test logging an error."""
        logger = KnowledgeErrorLogger(log_dir=str(tmp_path / "logs"))

        error = KnowledgeError(
            error_type=KnowledgeErrorType.VALIDATION_FAILED.value,
            domain=ErrorDomain.KNOWLEDGE,
            severity=ErrorSeverity.MEDIUM,
            message="Validation failed",
        )

        logger.log_error(error)

        assert len(logger.errors) == 1
        assert logger.errors[0].error_type == "validation_failed"

    def test_log_with_recovery_action(self, tmp_path: Path) -> None:
        """Test logging with recovery action."""
        logger = KnowledgeErrorLogger(log_dir=str(tmp_path / "logs"))

        error = KnowledgeError(
            error_type=KnowledgeErrorType.CONTRADICTORY_KNOWLEDGE.value,
            domain=ErrorDomain.KNOWLEDGE,
            severity=ErrorSeverity.MEDIUM,
            message="Contradiction detected",
        )

        action = ErrorRecoveryAction(
            action="queue_for_review",
            reason="Needs manual review",
            escalate_to_human=True,
        )

        logger.log_error(error, action)

        # Check log file was created
        log_file = tmp_path / "logs" / "knowledge_errors.jsonl"
        assert log_file.exists()

        # Check log content
        content = log_file.read_text()
        assert "contradictory_knowledge" in content
        assert "queue_for_review" in content

    def test_error_summary(self, tmp_path: Path) -> None:
        """Test error summary generation."""
        logger = KnowledgeErrorLogger(log_dir=str(tmp_path / "logs"))

        # Log multiple errors
        logger.log_error(KnowledgeError(
            error_type=KnowledgeErrorType.TRANSCRIPT_SOURCE_MISSING.value,
            domain=ErrorDomain.KNOWLEDGE,
            severity=ErrorSeverity.HIGH,
            message="Error 1",
        ))

        logger.log_error(KnowledgeError(
            error_type=KnowledgeErrorType.VALIDATION_FAILED.value,
            domain=ErrorDomain.KNOWLEDGE,
            severity=ErrorSeverity.MEDIUM,
            message="Error 2",
        ))

        logger.log_error(KnowledgeError(
            error_type=RAGErrorType.RETRIEVAL_FAILED.value,
            domain=ErrorDomain.RAG,
            severity=ErrorSeverity.MEDIUM,
            message="Error 3",
        ))

        summary = logger.get_error_summary()

        assert summary["total_errors"] == 3
        assert summary["by_domain"]["knowledge"] == 2
        assert summary["by_domain"]["rag"] == 1
        assert summary["high_count"] == 1


class TestErrorDashboard:
    """Tests for ErrorDashboard."""

    def test_generate_report(self, tmp_path: Path) -> None:
        """Test report generation."""
        logger = KnowledgeErrorLogger(log_dir=str(tmp_path / "logs"))

        # Log some errors
        logger.log_error(KnowledgeError(
            error_type=KnowledgeErrorType.TUTORIAL_DISTILLATION_FAILED.value,
            domain=ErrorDomain.KNOWLEDGE,
            severity=ErrorSeverity.HIGH,
            message="Distillation failed",
        ))

        logger.log_error(KnowledgeError(
            error_type=RAGErrorType.RAG_INDEX_CORRUPTED.value,
            domain=ErrorDomain.RAG,
            severity=ErrorSeverity.CRITICAL,
            message="Index corrupted",
        ))

        report = ErrorDashboard.generate_report(logger)

        assert "Total Errors: 2" in report
        assert "Critical: 1" in report
        assert "High: 1" in report
        assert "knowledge" in report
        assert "rag" in report


class TestIntegration:
    """Integration tests for error normalization."""

    def test_full_error_flow(self) -> None:
        """Test full error handling flow."""
        # 1. Create error from exception
        exc = FileNotFoundError("Tutorial transcript not found")
        error = KnowledgeErrorNormalizer.normalize(
            exc,
            context={"expected_path": "data/tutorials/vid1.txt"},
        )

        # 2. Verify normalization
        assert error.error_type == KnowledgeErrorType.TRANSCRIPT_SOURCE_MISSING.value
        assert error.domain == ErrorDomain.KNOWLEDGE
        assert error.severity == ErrorSeverity.HIGH

        # 3. Get recovery action
        action = ErrorRecoveryHandler.handle_error(error)
        assert action.action == "retry"

        # 4. Verify recovery suggestion
        assert error.recovery_suggestion is not None

    def test_low_confidence_flow(self) -> None:
        """Test low confidence error handling flow."""
        # 1. Create error
        error = KnowledgeErrorNormalizer.normalize_from_string(
            "Distillation confidence too low: 0.42",
            domain=ErrorDomain.KNOWLEDGE,
            context={"confidence": 0.42, "threshold": 0.7},
        )

        # 2. Verify classification
        assert error.error_type == KnowledgeErrorType.DISTILLATION_CONFIDENCE_TOO_LOW.value

        # 3. Get recovery action
        action = ErrorRecoveryHandler.handle_error(error)
        assert action.action == "queue_for_review"
        assert action.escalate_to_human is True

    def test_rag_error_flow(self) -> None:
        """Test RAG error handling flow."""
        # 1. Create error
        error = KnowledgeErrorNormalizer.normalize_from_string(
            "RAG index corrupted, cannot retrieve",
            domain=ErrorDomain.RAG,
        )

        # 2. Verify classification
        assert error.error_type == RAGErrorType.RAG_INDEX_CORRUPTED.value
        assert error.severity == ErrorSeverity.CRITICAL

        # 3. Get recovery action
        action = ErrorRecoveryHandler.handle_error(error)
        assert action.action == "rebuild_index"
        assert action.escalate_to_human is True

    def test_error_logging_flow(self, tmp_path: Path) -> None:
        """Test error logging flow."""
        logger = KnowledgeErrorLogger(log_dir=str(tmp_path / "logs"))

        # Create and log multiple errors
        errors = [
            (KnowledgeErrorType.TRANSCRIPT_SOURCE_MISSING, ErrorDomain.KNOWLEDGE, ErrorSeverity.HIGH),
            (KnowledgeErrorType.DISTILLATION_CONFIDENCE_TOO_LOW, ErrorDomain.KNOWLEDGE, ErrorSeverity.MEDIUM),
            (RAGErrorType.RETRIEVAL_FAILED, ErrorDomain.RAG, ErrorSeverity.MEDIUM),
        ]

        for error_type, domain, severity in errors:
            error = KnowledgeError(
                error_type=error_type.value,
                domain=domain,
                severity=severity,
                message=f"Error: {error_type.value}",
            )
            action = ErrorRecoveryHandler.handle_error(error)
            logger.log_error(error, action)

        # Verify summary
        summary = logger.get_error_summary()
        assert summary["total_errors"] == 3
        assert summary["by_domain"]["knowledge"] == 2
        assert summary["by_domain"]["rag"] == 1

        # Generate report
        report = ErrorDashboard.generate_report(logger)
        assert "Total Errors: 3" in report


class TestErrorTypeByDomain:
    """Tests for ERROR_TYPE_BY_DOMAIN mapping."""

    def test_mapping_exists(self) -> None:
        """Test that domain to error type mapping exists."""
        assert ErrorDomain.EXECUTION in ERROR_TYPE_BY_DOMAIN
        assert ErrorDomain.RAG in ERROR_TYPE_BY_DOMAIN
        assert ErrorDomain.KNOWLEDGE in ERROR_TYPE_BY_DOMAIN
        assert ErrorDomain.PLANNING in ERROR_TYPE_BY_DOMAIN
        assert ErrorDomain.VERIFICATION in ERROR_TYPE_BY_DOMAIN

    def test_mapping_correct_types(self) -> None:
        """Test that mapping returns correct types."""
        assert ERROR_TYPE_BY_DOMAIN[ErrorDomain.KNOWLEDGE] == KnowledgeErrorType
        assert ERROR_TYPE_BY_DOMAIN[ErrorDomain.RAG] == RAGErrorType
        assert ERROR_TYPE_BY_DOMAIN[ErrorDomain.PLANNING] == PlanningErrorType
        assert ERROR_TYPE_BY_DOMAIN[ErrorDomain.VERIFICATION] == VerificationErrorType


if __name__ == "__main__":
    pytest.main([__file__, "-v"])