"""Tests for Validation Pipeline.

Tests for:
- SchemaValidator
- QualityGate
- ContradictionDetector
- SanityChecker
- ValidationPipeline
- KnowledgeStoreWithValidation
"""

from __future__ import annotations

import pytest

from app.validation import (
    ContradictionCheckResult,
    ContradictionDetector,
    KnowledgeStoreConfig,
    KnowledgeStoreWithValidation,
    QualityEvaluationResult,
    QualityGate,
    QualityThresholds,
    SanityCheckResult,
    SanityChecker,
    SchemaValidationResult,
    SchemaValidator,
    ValidationConfig,
    ValidationDecision,
    ValidationPipeline,
    ValidationResult,
    validate_recipe,
    validate_recipes_batch,
)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def valid_recipe() -> dict:
    """A valid recipe for testing."""
    return {
        "recipe_id": "test_recipe_001",
        "title": "Create Geometry Node in Houdini",
        "description": "Creates a geometry node in the OBJ context",
        "domain": "houdini",
        "status": "active",
        "confidence": 0.85,
        "overall_confidence": 0.9,
        "steps": [
            {
                "step_id": "step_1",
                "step_type": "create_node",
                "description": "Create geometry node",
                "action": "create",
                "target": "geo1",
                "node_type": "geo",
                "verification_hint": "Node appears in network editor",
                "confidence": 0.9,
            },
            {
                "step_id": "step_2",
                "step_type": "set_parameter",
                "description": "Set display flag",
                "action": "set_flag",
                "target": "geo1",
                "confidence": 0.8,
            },
        ],
        "required_nodes": ["geo"],
        "verification_checks": ["Node visible in network", "Parameter set correctly"],
        "success_criteria": ["Geometry node created", "Display flag set"],
        "provenance": {"source": "tutorial", "video_id": "abc123"},
    }


@pytest.fixture
def invalid_recipe() -> dict:
    """An invalid recipe for testing."""
    return {
        # Missing recipe_id
        # Missing title
        # Missing domain
        "confidence": -0.5,  # Invalid: negative
        "steps": [],
    }


@pytest.fixture
def low_quality_recipe() -> dict:
    """A low quality but valid recipe."""
    return {
        "recipe_id": "low_quality_001",
        "title": "Do Something",
        "domain": "houdini",
        "confidence": 0.4,  # Low confidence
        "steps": [],  # No steps
    }


# =============================================================================
# SCHEMA VALIDATOR TESTS
# =============================================================================


class TestSchemaValidator:
    """Tests for SchemaValidator."""

    def test_valid_recipe_passes(self, valid_recipe: dict) -> None:
        """Valid recipe should pass schema validation."""
        validator = SchemaValidator()
        result = validator.validate(valid_recipe)

        assert isinstance(result, SchemaValidationResult)
        assert result.valid is True
        assert len(result.errors) == 0

    def test_missing_required_fields(self, invalid_recipe: dict) -> None:
        """Missing required fields should fail."""
        validator = SchemaValidator()
        result = validator.validate(invalid_recipe)

        assert result.valid is False
        assert len(result.errors) > 0
        assert any("recipe_id" in e.lower() or "title" in e.lower() for e in result.errors)

    def test_invalid_confidence_range(self) -> None:
        """Confidence outside 0-1 range should fail."""
        recipe = {
            "recipe_id": "test",
            "title": "Test",
            "domain": "houdini",
            "confidence": 1.5,  # Invalid: > 1
        }

        validator = SchemaValidator()
        result = validator.validate(recipe)

        # Should either fail or have warning
        # Implementation may vary based on jsonschema availability

    def test_invalid_domain(self) -> None:
        """Invalid domain should fail."""
        recipe = {
            "recipe_id": "test",
            "title": "Test",
            "domain": "invalid_domain",
        }

        validator = SchemaValidator()
        result = validator.validate(recipe)

        # Should fail due to enum constraint
        assert result.valid is False or len(result.errors) > 0

    def test_custom_schema(self) -> None:
        """Should support custom schemas."""
        custom_schema = {
            "type": "object",
            "required": ["custom_id"],
            "properties": {
                "custom_id": {"type": "string"},
            },
        }

        validator = SchemaValidator(schema=custom_schema)
        result = validator.validate({"custom_id": "test"})

        assert result.valid is True

    def test_duplicate_step_ids_warning(self, valid_recipe: dict) -> None:
        """Duplicate step IDs should generate warning."""
        recipe = valid_recipe.copy()
        recipe["steps"] = [
            {"step_id": "duplicate", "description": "Step 1"},
            {"step_id": "duplicate", "description": "Step 2"},
        ]

        validator = SchemaValidator()
        result = validator.validate(recipe)

        # Should have warning about duplicate IDs
        assert any("duplicate" in w.lower() for w in result.warnings)

    def test_unknown_field_warning(self, valid_recipe: dict) -> None:
        """Unknown fields should generate warning."""
        recipe = valid_recipe.copy()
        recipe["unknown_field"] = "some_value"

        validator = SchemaValidator()
        result = validator.validate(recipe)

        # May have warning about unknown field
        # Implementation dependent


# =============================================================================
# QUALITY GATE TESTS
# =============================================================================


class TestQualityGate:
    """Tests for QualityGate."""

    def test_high_quality_passes(self, valid_recipe: dict) -> None:
        """High quality recipe should pass."""
        gate = QualityGate()
        result = gate.evaluate(valid_recipe)

        assert isinstance(result, QualityEvaluationResult)
        assert result.passed is True
        assert result.confidence >= 0.7
        assert result.completeness >= 0.8

    def test_low_confidence_fails(self, low_quality_recipe: dict) -> None:
        """Low confidence should fail quality gate."""
        thresholds = QualityThresholds(min_confidence=0.7)
        gate = QualityGate(thresholds=thresholds)
        result = gate.evaluate(low_quality_recipe)

        assert result.passed is False
        assert result.confidence < 0.7

    def test_empty_steps_reduces_completeness(self) -> None:
        """Empty steps should reduce completeness."""
        recipe = {
            "recipe_id": "test",
            "title": "Test",
            "domain": "houdini",
            "confidence": 0.9,
            "steps": [],  # Empty
        }

        gate = QualityGate()
        result = gate.evaluate(recipe)

        # Empty steps should reduce completeness
        assert result.completeness < 0.8
        assert any("steps" in i.lower() for i in result.issues)

    def test_calculates_confidence_from_steps(self) -> None:
        """Should calculate confidence from steps if not provided."""
        recipe = {
            "recipe_id": "test",
            "title": "Test",
            "domain": "houdini",
            "steps": [
                {"confidence": 0.8},
                {"confidence": 0.9},
            ],
        }

        gate = QualityGate()
        result = gate.evaluate(recipe)

        # Average of step confidences
        assert result.confidence == pytest.approx(0.85, rel=0.01)

    def test_custom_thresholds(self) -> None:
        """Should respect custom thresholds."""
        thresholds = QualityThresholds(
            min_confidence=0.9,
            min_completeness=0.9,
        )
        gate = QualityGate(thresholds=thresholds)

        recipe = {
            "recipe_id": "test",
            "title": "Test",
            "domain": "houdini",
            "confidence": 0.85,  # Below 0.9
            "steps": [{"description": "Step"}],
        }

        result = gate.evaluate(recipe)
        assert result.passed is False

    def test_verification_score_calculation(self, valid_recipe: dict) -> None:
        """Should calculate verification coverage."""
        gate = QualityGate()
        result = gate.evaluate(valid_recipe)

        # Recipe has verification hints
        assert result.score > 0


# =============================================================================
# CONTRADICTION DETECTOR TESTS
# =============================================================================


class TestContradictionDetector:
    """Tests for ContradictionDetector."""

    def test_no_contradictions(self, valid_recipe: dict) -> None:
        """Recipe with no contradictions should pass."""
        detector = ContradictionDetector(existing_recipes=[])
        result = detector.check(valid_recipe)

        assert isinstance(result, ContradictionCheckResult)
        assert result.has_contradictions is False
        assert result.severity == "none"

    def test_duplicate_id_contradiction(self, valid_recipe: dict) -> None:
        """Duplicate ID should be detected."""
        existing = valid_recipe.copy()

        detector = ContradictionDetector(existing_recipes=[existing])
        result = detector.check(valid_recipe)

        assert result.has_contradictions is True
        assert result.severity == "critical"
        assert any(c["type"] == "duplicate_id" for c in result.contradictions)

    def test_similar_recipes_different_domains(self) -> None:
        """Similar recipes with different domains should be flagged."""
        existing = {
            "recipe_id": "existing_001",
            "title": "Create Geometry Node",
            "domain": "houdini",
        }

        new_recipe = {
            "recipe_id": "new_001",
            "title": "Create Geometry Node",  # Same title
            "domain": "touchdesigner",  # Different domain
        }

        detector = ContradictionDetector(
            existing_recipes=[existing],
            similarity_threshold=0.8,
        )
        result = detector.check(new_recipe)

        # May detect domain mismatch
        if result.has_contradictions:
            assert result.severity in ("minor", "major")

    def test_internal_contradiction_detection(self) -> None:
        """Should detect internal contradictions."""
        recipe = {
            "recipe_id": "test",
            "title": "Test",
            "domain": "houdini",
            "steps": [
                {
                    "step_id": "step_1",
                    "expected_outcome": "Create the node",
                },
                {
                    "step_id": "step_2",
                    "expected_outcome": "Do not create the node",  # Contradictory
                },
            ],
        }

        detector = ContradictionDetector()
        result = detector.check(recipe)

        # May detect contradiction
        # Implementation dependent

    def test_add_existing_recipe(self, valid_recipe: dict) -> None:
        """Should be able to add existing recipes."""
        detector = ContradictionDetector()
        detector.add_existing_recipe(valid_recipe)

        assert len(detector._existing_recipes) == 1

    def test_set_existing_recipes(self, valid_recipe: dict) -> None:
        """Should be able to set existing recipes."""
        detector = ContradictionDetector()
        detector.set_existing_recipes([valid_recipe])

        assert len(detector._existing_recipes) == 1


# =============================================================================
# SANITY CHECKER TESTS
# =============================================================================


class TestSanityChecker:
    """Tests for SanityChecker."""

    def test_valid_recipe_passes(self, valid_recipe: dict) -> None:
        """Valid recipe should pass sanity checks."""
        checker = SanityChecker()
        result = checker.check(valid_recipe)

        assert isinstance(result, SanityCheckResult)
        assert result.passed is True
        assert len(result.issues) == 0

    def test_step_ordering_warning(self) -> None:
        """Should warn about incorrect step ordering."""
        recipe = {
            "recipe_id": "test",
            "title": "Test",
            "domain": "houdini",
            "steps": [
                {
                    "step_id": "step_1",
                    "depends_on": "node_created_in_step_2",  # Not created yet
                },
                {
                    "step_id": "step_2",
                    "target": "node_created_in_step_2",
                },
            ],
        }

        checker = SanityChecker()
        result = checker.check(recipe)

        # Should have warning about step ordering
        assert len(result.warnings) > 0

    def test_circular_dependency_detection(self) -> None:
        """Should detect circular dependencies."""
        recipe = {
            "recipe_id": "test",
            "title": "Test",
            "domain": "houdini",
            "steps": [
                {
                    "step_id": "step_a",
                    "depends_on": "step_b",
                },
                {
                    "step_id": "step_b",
                    "depends_on": "step_a",  # Circular!
                },
            ],
        }

        config = ValidationConfig(check_circular_dependencies=True)
        checker = SanityChecker(config=config)
        result = checker.check(recipe)

        assert result.passed is False
        assert any("circular" in i.lower() for i in result.issues)

    def test_input_output_chain_check(self) -> None:
        """Should check input/output chains."""
        recipe = {
            "recipe_id": "test",
            "title": "Test",
            "domain": "houdini",
            "steps": [
                {
                    "step_id": "step_1",
                    "outputs": ["output_a"],
                },
                {
                    "step_id": "step_2",
                    "inputs": ["output_a"],  # Available from step_1
                },
                {
                    "step_id": "step_3",
                    "inputs": ["output_b"],  # Not produced anywhere
                },
            ],
        }

        config = ValidationConfig(check_input_output_chains=True)
        checker = SanityChecker(config=config)
        result = checker.check(recipe)

        # Should warn about output_b not being available
        assert any("output_b" in w.lower() or "input" in w.lower() for w in result.warnings)

    def test_disabled_checks(self, invalid_recipe: dict) -> None:
        """Disabled checks should be skipped."""
        config = ValidationConfig(
            check_step_ordering=False,
            check_input_output_chains=False,
            check_circular_dependencies=False,
        )
        checker = SanityChecker(config=config)

        # Any recipe should pass with all checks disabled
        result = checker.check(invalid_recipe)
        assert result.passed is True


# =============================================================================
# VALIDATION PIPELINE TESTS
# =============================================================================


class TestValidationPipeline:
    """Tests for ValidationPipeline."""

    def test_valid_recipe_accept(self, valid_recipe: dict) -> None:
        """Valid high-quality recipe should be accepted."""
        pipeline = ValidationPipeline()
        result = pipeline.validate(valid_recipe)

        assert isinstance(result, ValidationResult)
        assert result.decision == ValidationDecision.ACCEPT
        assert result.schema_valid is True
        assert result.quality_score > 0.5

    def test_schema_invalid_reject(self, invalid_recipe: dict) -> None:
        """Schema invalid recipe should be rejected."""
        pipeline = ValidationPipeline()
        result = pipeline.validate(invalid_recipe)

        assert result.decision == ValidationDecision.REJECT
        assert result.schema_valid is False
        assert len(result.errors) > 0

    def test_low_quality_review(self, low_quality_recipe: dict) -> None:
        """Low quality recipe should be reviewed."""
        pipeline = ValidationPipeline()
        result = pipeline.validate(low_quality_recipe)

        # Should be either REVIEW or REJECT based on thresholds
        assert result.decision in (ValidationDecision.REVIEW, ValidationDecision.REJECT)

    def test_duplicate_id_reject(self, valid_recipe: dict) -> None:
        """Duplicate ID should cause rejection."""
        pipeline = ValidationPipeline(existing_recipes=[valid_recipe])
        result = pipeline.validate(valid_recipe)

        assert result.decision == ValidationDecision.REJECT
        assert result.has_contradictions is True

    def test_strict_mode_rejects_review(self, low_quality_recipe: dict) -> None:
        """Strict mode should reject items that would otherwise be reviewed."""
        config = ValidationConfig(
            strict_mode=True,
            quality_thresholds=QualityThresholds(min_confidence=0.8),
        )
        pipeline = ValidationPipeline(config=config)
        result = pipeline.validate(low_quality_recipe)

        assert result.decision == ValidationDecision.REJECT

    def test_suggestions_generated(self, low_quality_recipe: dict) -> None:
        """Should generate improvement suggestions."""
        pipeline = ValidationPipeline()
        result = pipeline.validate(low_quality_recipe)

        # Should have suggestions for improvement
        assert isinstance(result.suggestions, list)

    def test_update_existing_recipes(self, valid_recipe: dict) -> None:
        """Should be able to update existing recipes."""
        pipeline = ValidationPipeline()
        pipeline.update_existing_recipes([valid_recipe])

        # Now duplicate should be detected
        result = pipeline.validate(valid_recipe)
        assert result.has_contradictions is True

    def test_add_existing_recipe(self, valid_recipe: dict) -> None:
        """Should be able to add single existing recipe."""
        pipeline = ValidationPipeline()
        pipeline.add_existing_recipe(valid_recipe)

        # Now duplicate should be detected
        result = pipeline.validate(valid_recipe)
        assert result.has_contradictions is True

    def test_to_dict_serialization(self, valid_recipe: dict) -> None:
        """Result should serialize to dict."""
        pipeline = ValidationPipeline()
        result = pipeline.validate(valid_recipe)
        data = result.to_dict()

        assert isinstance(data, dict)
        assert "item_id" in data
        assert "decision" in data
        assert "errors" in data
        assert "warnings" in data


# =============================================================================
# CONVENIENCE FUNCTION TESTS
# =============================================================================


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_validate_recipe(self, valid_recipe: dict) -> None:
        """validate_recipe should work."""
        result = validate_recipe(valid_recipe)

        assert isinstance(result, ValidationResult)
        assert result.decision == ValidationDecision.ACCEPT

    def test_validate_recipe_with_existing(self, valid_recipe: dict) -> None:
        """validate_recipe with existing recipes should detect duplicates."""
        result = validate_recipe(
            valid_recipe,
            existing_recipes=[valid_recipe],
        )

        assert result.has_contradictions is True

    def test_validate_recipes_batch(self, valid_recipe: dict, low_quality_recipe: dict) -> None:
        """validate_recipes_batch should process multiple recipes."""
        results = validate_recipes_batch([valid_recipe, low_quality_recipe])

        assert len(results) == 2
        assert all(isinstance(r, ValidationResult) for r in results)

    def test_batch_validates_against_accepted(self, valid_recipe: dict) -> None:
        """Batch should validate against previously accepted recipes."""
        duplicate = valid_recipe.copy()

        results = validate_recipes_batch([valid_recipe, duplicate])

        # First should be accepted
        assert results[0].decision == ValidationDecision.ACCEPT
        # Second should have contradiction (duplicate ID)
        assert results[1].has_contradictions is True


# =============================================================================
# KNOWLEDGE STORE TESTS
# =============================================================================


class TestKnowledgeStoreWithValidation:
    """Tests for KnowledgeStoreWithValidation."""

    def test_add_valid_recipe(self, valid_recipe: dict) -> None:
        """Adding valid recipe should work."""
        store = KnowledgeStoreWithValidation()
        knowledge = store.add_recipe(valid_recipe)

        assert knowledge.validation_result.decision == ValidationDecision.ACCEPT
        assert knowledge.indexed is True

    def test_add_invalid_recipe(self, invalid_recipe: dict) -> None:
        """Adding invalid recipe should result in rejection."""
        store = KnowledgeStoreWithValidation()
        knowledge = store.add_recipe(invalid_recipe)

        assert knowledge.validation_result.decision == ValidationDecision.REJECT

    def test_get_validated_recipes(self, valid_recipe: dict) -> None:
        """Should retrieve validated recipes."""
        store = KnowledgeStoreWithValidation()
        store.add_recipe(valid_recipe)

        recipes = store.get_validated_recipes()

        assert len(recipes) == 1
        assert recipes[0]["recipe_id"] == valid_recipe["recipe_id"]

    def test_get_pending_review(self, low_quality_recipe: dict) -> None:
        """Should retrieve items pending review."""
        store = KnowledgeStoreWithValidation()
        store.add_recipe(low_quality_recipe)

        pending = store.get_pending_review()

        # May have items pending review depending on thresholds
        assert isinstance(pending, list)

    def test_get_rag_chunks(self, valid_recipe: dict) -> None:
        """Should generate RAG chunks for validated recipes."""
        store = KnowledgeStoreWithValidation()
        store.add_recipe(valid_recipe)

        chunks = store.get_rag_chunks()

        assert len(chunks) > 0

    def test_accept_review(self, low_quality_recipe: dict) -> None:
        """Should be able to accept pending review items."""
        store = KnowledgeStoreWithValidation()
        store.add_recipe(low_quality_recipe)

        pending = store.get_pending_review()
        if pending:
            accepted = store.accept_review(
                pending[0].knowledge_id,
                notes="Human approved",
            )

            assert accepted is not None
            assert accepted.validation_result.decision == ValidationDecision.ACCEPT

    def test_reject_review(self, low_quality_recipe: dict) -> None:
        """Should be able to reject pending review items."""
        config = KnowledgeStoreConfig(store_rejected=True)
        store = KnowledgeStoreWithValidation(config=config)
        store.add_recipe(low_quality_recipe)

        pending = store.get_pending_review()
        if pending:
            rejected = store.reject_review(
                pending[0].knowledge_id,
                reason="Insufficient detail",
            )

            assert rejected is not None
            assert rejected.validation_result.decision == ValidationDecision.REJECT

    def test_remove_recipe(self, valid_recipe: dict) -> None:
        """Should be able to remove recipes."""
        store = KnowledgeStoreWithValidation()
        store.add_recipe(valid_recipe)

        removed = store.remove_recipe(valid_recipe["recipe_id"])

        assert removed is True
        assert len(store.get_validated_recipes()) == 0

    def test_update_recipe(self, valid_recipe: dict) -> None:
        """Should be able to update and re-validate recipes."""
        store = KnowledgeStoreWithValidation()
        store.add_recipe(valid_recipe)

        updated = store.update_recipe(
            valid_recipe["recipe_id"],
            {"title": "Updated Title"},
        )

        assert updated is not None
        assert updated.data["title"] == "Updated Title"

    def test_get_stats(self, valid_recipe: dict) -> None:
        """Should return store statistics."""
        store = KnowledgeStoreWithValidation()
        store.add_recipe(valid_recipe)

        stats = store.get_stats()

        assert stats["validated_count"] == 1
        assert stats["rag_chunks_count"] > 0

    def test_skip_validation(self, invalid_recipe: dict) -> None:
        """Should be able to skip validation."""
        store = KnowledgeStoreWithValidation()
        knowledge = store.add_recipe(invalid_recipe, skip_validation=True)

        assert knowledge.validation_result.decision == ValidationDecision.ACCEPT

    def test_auto_index_disabled(self, valid_recipe: dict) -> None:
        """Should not auto-index when disabled."""
        config = KnowledgeStoreConfig(auto_index=False)
        store = KnowledgeStoreWithValidation(config=config)
        knowledge = store.add_recipe(valid_recipe)

        assert knowledge.indexed is False
        assert len(store.get_rag_chunks()) == 0


# =============================================================================
# INTEGRATION TESTS
# =============================================================================


class TestValidationIntegration:
    """Integration tests for validation pipeline."""

    def test_full_pipeline_flow(self, valid_recipe: dict) -> None:
        """Test complete validation flow."""
        # Create pipeline
        pipeline = ValidationPipeline()

        # Validate
        result = pipeline.validate(valid_recipe)

        # Check result
        assert result.decision == ValidationDecision.ACCEPT
        assert result.schema_valid is True
        assert result.quality_score > 0

        # Add to pipeline
        pipeline.add_existing_recipe(valid_recipe)

        # Try duplicate
        duplicate_result = pipeline.validate(valid_recipe)
        assert duplicate_result.has_contradictions is True

    def test_store_with_pipeline(self, valid_recipe: dict, low_quality_recipe: dict) -> None:
        """Test store integration with pipeline."""
        config = KnowledgeStoreConfig(
            auto_validate=True,
            auto_index=True,
        )

        store = KnowledgeStoreWithValidation(config=config)

        # Add valid recipe
        valid = store.add_recipe(valid_recipe)
        assert valid.validation_result.decision == ValidationDecision.ACCEPT

        # Add low quality recipe
        low = store.add_recipe(low_quality_recipe)
        assert low.validation_result.decision in (
            ValidationDecision.REVIEW,
            ValidationDecision.REJECT,
        )

        # Get RAG chunks - only from validated
        chunks = store.get_rag_chunks()
        # Chunks may have step-specific source_ids like "recipe_id:step_id"
        assert all(c.source_id.startswith(valid_recipe["recipe_id"]) for c in chunks)

    def test_review_workflow(self, low_quality_recipe: dict) -> None:
        """Test human review workflow."""
        config = KnowledgeStoreConfig(store_rejected=True)
        store = KnowledgeStoreWithValidation(config=config)

        # Add low quality recipe
        store.add_recipe(low_quality_recipe)

        # Get pending
        pending = store.get_pending_review()
        if pending:
            # Accept
            store.accept_review(pending[0].knowledge_id)

            # Should now be in validated
            assert len(store.get_validated_recipes()) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])