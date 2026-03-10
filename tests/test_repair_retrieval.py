"""Tests for Repair-Time Knowledge Retrieval."""

from __future__ import annotations

import pytest
from pathlib import Path
from datetime import datetime

from app.learning.repair_retrieval import (
    ErrorClassification,
    ErrorRepairStrategy,
    TutorialRepairHint,
    RepairKnowledge,
    RepairMetrics,
    classify_error,
    extract_concepts,
    matches_error_pattern,
    compute_adaptive_backoff,
)


class TestErrorClassification:
    """Tests for error classification."""

    def test_classify_execution_error(self) -> None:
        """Test classification of execution errors."""
        result = classify_error("Node 'box1' not found in geometry network")
        assert result == ErrorClassification.EXECUTION

    def test_classify_validation_error(self) -> None:
        """Test classification of validation errors."""
        result = classify_error("Output does not match expected format")
        assert result == ErrorClassification.VALIDATION

    def test_classify_timeout_error(self) -> None:
        """Test classification of timeout errors."""
        result = classify_error("Operation timed out after 30 seconds")
        assert result == ErrorClassification.TIMEOUT

    def test_classify_resource_error(self) -> None:
        """Test classification of resource errors."""
        result = classify_error("Connection refused to localhost")
        assert result == ErrorClassification.RESOURCE

    def test_classify_domain_error(self) -> None:
        """Test classification of domain-specific errors."""
        result = classify_error("Houdini: Invalid VEX syntax")
        assert result == ErrorClassification.DOMAIN

    def test_classify_with_context(self) -> None:
        """Test classification with context hints."""
        result = classify_error(
            "Operation failed",
            error_context={"duration_ms": 60000, "domain": "houdini"}
        )
        assert result == ErrorClassification.TIMEOUT

    def test_classify_unknown_defaults_to_execution(self) -> None:
        """Test that unknown errors default to execution."""
        result = classify_error("Something weird happened")
        assert result == ErrorClassification.EXECUTION


class TestConceptExtraction:
    """Tests for concept extraction."""

    def test_extract_concepts_basic(self) -> None:
        """Test basic concept extraction."""
        concepts = extract_concepts("Node box1 not found in geometry network")
        assert "node" in concepts
        assert "geometry" in concepts
        assert "network" in concepts
        # Note: "box1" is not extracted because regex only matches [a-z]{3,}

    def test_extract_concepts_filters_stop_words(self) -> None:
        """Test that stop words are filtered."""
        concepts = extract_concepts("The node was not found in the network")
        assert "the" not in concepts
        assert "was" not in concepts

    def test_extract_concepts_limited(self) -> None:
        """Test that concepts are limited to 10."""
        long_text = " ".join([f"concept{i}" for i in range(20)])
        concepts = extract_concepts(long_text)
        assert len(concepts) <= 10


class TestErrorRepairStrategy:
    """Tests for error repair strategy."""

    def test_create_strategy(self) -> None:
        """Test creating a repair strategy."""
        strategy = ErrorRepairStrategy(
            error_pattern="node not found",
            successful_action="Create node before reference",
            success_rate=0.8,
            domain="houdini",
            source_error_id="err_001",
            last_used="2024-01-01T00:00:00Z",
        )

        assert strategy.error_pattern == "node not found"
        assert strategy.success_rate == 0.8
        assert strategy.use_count == 0

    def test_strategy_serialization(self) -> None:
        """Test strategy serialization."""
        strategy = ErrorRepairStrategy(
            error_pattern="timeout",
            successful_action="Reduce parameters",
            success_rate=0.7,
            domain="touchdesigner",
            source_error_id="err_002",
            last_used="2024-01-01T00:00:00Z",
        )

        data = strategy.to_dict()
        restored = ErrorRepairStrategy.from_dict(data)

        assert restored.error_pattern == strategy.error_pattern
        assert restored.success_rate == strategy.success_rate


class TestTutorialRepairHint:
    """Tests for tutorial repair hints."""

    def test_create_hint(self) -> None:
        """Test creating a repair hint."""
        hint = TutorialRepairHint(
            source_tutorial="procedural_geometry",
            repair_suggestion="Verify nodes exist before referencing",
            reasoning="Tutorial covers node lifecycle",
            applicability=0.8,
            confidence=0.9,
        )

        assert hint.source_tutorial == "procedural_geometry"
        assert hint.applicability == 0.8

    def test_hint_serialization(self) -> None:
        """Test hint serialization."""
        hint = TutorialRepairHint(
            source_tutorial="test",
            repair_suggestion="Check prerequisites",
            reasoning="Safety check",
            applicability=0.9,
            confidence=0.8,
            prerequisites=["node_exists", "parameter_valid"],
        )

        data = hint.to_dict()
        restored = TutorialRepairHint.from_dict(data)

        assert restored.source_tutorial == hint.source_tutorial
        assert restored.prerequisites == hint.prerequisites


class TestRepairKnowledge:
    """Tests for repair knowledge aggregation."""

    def test_empty_knowledge(self) -> None:
        """Test empty knowledge returns no best repair."""
        knowledge = RepairKnowledge(
            error_classification=ErrorClassification.EXECUTION,
        )

        assert knowledge.get_best_repair() is None
        assert knowledge.has_repairs is False

    def test_knowledge_with_strategies(self) -> None:
        """Test knowledge with repair strategies."""
        strategy = ErrorRepairStrategy(
            error_pattern="not found",
            successful_action="Create node",
            success_rate=0.8,
            domain="houdini",
            source_error_id="err_001",
            last_used="2024-01-01T00:00:00Z",
        )

        knowledge = RepairKnowledge(
            error_classification=ErrorClassification.EXECUTION,
            similar_error_repairs=[strategy],
        )

        assert knowledge.has_repairs is True
        best = knowledge.get_best_repair()
        assert best is not None
        assert isinstance(best, ErrorRepairStrategy)

    def test_knowledge_mixed_sources(self) -> None:
        """Test knowledge from both errors and tutorials."""
        strategy = ErrorRepairStrategy(
            error_pattern="timeout",
            successful_action="Reduce params",
            success_rate=0.6,
            domain="td",
            source_error_id="err_001",
            last_used="2024-01-01T00:00:00Z",
        )

        hint = TutorialRepairHint(
            source_tutorial="optimization",
            repair_suggestion="Use cache",
            reasoning="Reduces computation",
            applicability=0.9,
            confidence=0.95,
        )

        knowledge = RepairKnowledge(
            error_classification=ErrorClassification.TIMEOUT,
            similar_error_repairs=[strategy],
            tutorial_hints=[hint],
        )

        # Hint has higher effective score (0.95 * 0.9 = 0.855 vs 0.6)
        best = knowledge.get_best_repair()
        assert isinstance(best, TutorialRepairHint)

    def test_knowledge_serialization(self) -> None:
        """Test knowledge serialization."""
        strategy = ErrorRepairStrategy(
            error_pattern="test",
            successful_action="fix",
            success_rate=0.5,
            domain="test",
            source_error_id="err",
            last_used="2024-01-01T00:00:00Z",
        )

        knowledge = RepairKnowledge(
            error_classification=ErrorClassification.EXECUTION,
            similar_error_repairs=[strategy],
            confidence_in_repair=0.7,
        )

        data = knowledge.to_dict()
        assert data["error_classification"] == "execution"
        assert len(data["similar_error_repairs"]) == 1


class TestAdaptiveBackoff:
    """Tests for adaptive backoff calculation."""

    def test_first_attempt_short(self) -> None:
        """Test first attempt has short backoff."""
        backoff = compute_adaptive_backoff(
            attempt_count=1,
            confidence=0.9,
        )
        assert 0.4 < backoff < 1.0

    def test_low_confidence_longer(self) -> None:
        """Test low confidence results in longer backoff."""
        high_conf = compute_adaptive_backoff(attempt_count=1, confidence=0.9)
        low_conf = compute_adaptive_backoff(attempt_count=1, confidence=0.3)

        assert low_conf > high_conf

    def test_exponential_growth(self) -> None:
        """Test backoff grows exponentially."""
        b1 = compute_adaptive_backoff(attempt_count=1, confidence=0.9)
        b2 = compute_adaptive_backoff(attempt_count=2, confidence=0.9)
        b3 = compute_adaptive_backoff(attempt_count=3, confidence=0.9)

        assert b2 > b1
        assert b3 > b2

    def test_max_backoff_capped(self) -> None:
        """Test backoff is capped at maximum."""
        backoff = compute_adaptive_backoff(
            attempt_count=10,
            confidence=0.1,
            max_backoff=5.0,
        )
        assert backoff <= 5.0


class TestMatchesErrorPattern:
    """Tests for error pattern matching."""

    def test_match_found(self) -> None:
        """Test successful pattern match."""
        assert matches_error_pattern(
            "node not found",
            "Error: Node 'box1' not found in network"
        )

    def test_no_match(self) -> None:
        """Test no pattern match."""
        assert not matches_error_pattern(
            "database connection",
            "Error: Node not found"
        )

    def test_partial_match(self) -> None:
        """Test partial match with threshold."""
        assert matches_error_pattern(
            "timeout error",
            "Connection timeout after 30 seconds"
        )


class TestRepairMetrics:
    """Tests for repair metrics tracking."""

    def test_empty_metrics(self) -> None:
        """Test empty metrics."""
        metrics = RepairMetrics()

        assert metrics.repair_success_rate == 0.0
        assert metrics.avg_repair_time == 0.0
        assert metrics.tutorial_effectiveness == 0.0

    def test_record_error(self) -> None:
        """Test recording error."""
        metrics = RepairMetrics()
        metrics.record_error("execution")
        metrics.record_error("timeout")
        metrics.record_error("execution")

        assert metrics.total_errors == 3
        assert metrics.repair_attempts_by_type["execution"] == 2
        assert metrics.repair_attempts_by_type["timeout"] == 1

    def test_record_success(self) -> None:
        """Test recording repair success."""
        metrics = RepairMetrics()
        metrics.record_error("execution")
        metrics.record_repair_success("execution", 2.5)

        assert metrics.errors_repaired == 1
        assert metrics.total_repair_time == 2.5
        assert metrics.avg_repair_time == 2.5

    def test_effectiveness_calculation(self) -> None:
        """Test effectiveness calculations."""
        metrics = RepairMetrics()

        # Tutorial usage
        metrics.tutorial_hints_used = 4
        metrics.tutorial_hints_successful = 3

        # Prior solution usage
        metrics.prior_solution_used = 5
        metrics.prior_solution_successful = 4

        assert metrics.tutorial_effectiveness == 0.75
        assert metrics.prior_solution_effectiveness == 0.8

    def test_metrics_summary(self) -> None:
        """Test metrics summary output."""
        metrics = RepairMetrics()
        metrics.total_errors = 10
        metrics.errors_repaired = 8
        metrics.total_repair_time = 20.0
        metrics.tutorial_hints_used = 5
        metrics.tutorial_hints_successful = 4

        summary = metrics.summary()

        assert "Total errors: 10" in summary
        assert "Repair success rate: 80%" in summary


class TestIntegration:
    """Integration tests for repair system."""

    def test_full_flow(self) -> None:
        """Test full repair flow simulation."""
        # 1. Classify error
        error_msg = "Node 'scatter1' not found in geometry network"
        classification = classify_error(error_msg)
        assert classification == ErrorClassification.EXECUTION

        # 2. Extract concepts
        concepts = extract_concepts(error_msg)
        assert "node" in concepts
        # Note: "scatter1" contains digit, not extracted by [a-z]{3,} regex

        # 3. Create repair knowledge
        strategy = ErrorRepairStrategy(
            error_pattern="node not found",
            successful_action="Create node before reference",
            success_rate=0.8,
            domain="houdini",
            source_error_id="err_001",
            last_used=datetime.utcnow().isoformat() + "Z",
        )

        knowledge = RepairKnowledge(
            error_classification=classification,
            similar_error_repairs=[strategy],
            confidence_in_repair=0.8,
        )

        # 4. Get best repair
        best = knowledge.get_best_repair()
        assert best is not None
        assert best.successful_action == "Create node before reference"

        # 5. Compute backoff
        backoff = compute_adaptive_backoff(attempt_count=1, confidence=0.8)
        assert 0.3 < backoff < 1.0

    def test_metrics_tracking_flow(self) -> None:
        """Test metrics tracking through repair flow."""
        metrics = RepairMetrics()

        # Simulate multiple errors
        for error_type in ["execution", "timeout", "execution"]:
            metrics.record_error(error_type)

        # Simulate repairs
        metrics.record_repair_success("execution", 1.5, used_prior=True)
        metrics.record_repair_success("execution", 2.0, used_tutorial=True)
        metrics.record_replan_needed()

        assert metrics.total_errors == 3
        assert metrics.errors_repaired == 2
        assert metrics.repair_success_rate == 2/3
        assert metrics.prior_solution_used == 1
        assert metrics.tutorial_hints_used == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])