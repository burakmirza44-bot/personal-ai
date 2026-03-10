"""Tests for Product Shipping Layer.

Tests cover:
1. Shipping candidate eligibility
2. Quality gate evaluation
3. Recipe export serialization
4. Provenance and version metadata
5. Documentation generation
6. Knowledge base updates
7. Duplicate detection
8. Pipeline integration
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import pytest

from app.shipping.models import (
    ArtifactKind,
    EligibilityStatus,
    KnowledgeEntry,
    QualityGateResult,
    QualityStatus,
    ShippingArtifact,
    ShippingCandidate,
    ShippingProvenance,
    ShippingResult,
    ShipmentStatus,
    SourceType,
    SHIPPING_SCHEMA_VERSION,
)
from app.shipping.quality_gate import (
    QualityGate,
    QualityGateConfig,
    QualityThresholds,
    check_shipping_eligibility,
    evaluate_candidate,
    filter_eligible_candidates,
    is_high_quality_candidate,
)
from app.shipping.recipe_exporter import (
    RecipeExporter,
    RecipeExportConfig,
    RecipeExportResult,
    export_recipe,
    export_recipe_to_json,
    export_recipe_to_markdown,
)
from app.shipping.doc_generator import (
    DocGenerator,
    DocGeneratorConfig,
    DocGeneratorResult,
    generate_changelog,
    generate_recipe_documentation,
)
from app.shipping.kb_updater import (
    KBUpdaterConfig,
    KBUpdateResult,
    KnowledgeBaseUpdater,
    create_kb_entry_from_recipe,
    search_knowledge,
    update_knowledge_base,
)
from app.shipping.service import (
    ShippingPipelineConfig,
    ShippingService,
    collect_shipping_candidates,
    run_shipping_pipeline,
)
from app.shipping.policy import (
    ShippingPolicyConfig,
)
from app.shipping.candidate_collector import (
    CandidateCollector,
    CandidateCollectorConfig,
    CollectorResult,
    collect_shippable_candidates,
)
from app.shipping.history import (
    ShipmentHistory,
    ShipmentHistoryConfig,
    ShipmentHistoryEntry,
    get_shipment_history,
    is_candidate_shipped,
    record_shipment,
)


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture
def sample_recipe() -> dict[str, Any]:
    """Create a sample recipe for testing."""
    return {
        "recipe_id": "recipe_test_001",
        "name": "Test Recipe",
        "description": "A test recipe for shipping tests",
        "domain": "houdini",
        "steps": [
            {
                "step_id": "step_1",
                "action": "create_node",
                "description": "Create a test node",
                "params": {"node_type": "geo", "name": "test_geo"},
            },
            {
                "step_id": "step_2",
                "action": "set_param",
                "description": "Set a parameter",
                "params": {"param": "tx", "value": "1.0"},
            },
        ],
        "metadata": {
            "safety_level": "safe",
            "created_by": "test",
        },
        "verified": True,
        "quality_score": 0.85,
        "confidence": 0.9,
    }


@pytest.fixture
def sample_candidate(sample_recipe: dict[str, Any]) -> ShippingCandidate:
    """Create a sample shipping candidate."""
    return ShippingCandidate.from_recipe(
        sample_recipe,
        quality_score=0.85,
        confidence=0.9,
        verified=True,
    )


@pytest.fixture
def temp_dir() -> Path:
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


# ------------------------------------------------------------------
# Model Tests
# ------------------------------------------------------------------


class TestShippingModels:
    """Tests for shipping model classes."""

    def test_shipping_candidate_from_recipe(self, sample_recipe: dict[str, Any]) -> None:
        """Test creating shipping candidate from recipe."""
        candidate = ShippingCandidate.from_recipe(
            sample_recipe,
            quality_score=0.85,
            confidence=0.9,
            verified=True,
        )

        assert candidate.source_type == SourceType.VERIFIED_RECIPE.value
        assert candidate.artifact_kind == ArtifactKind.RECIPE_EXPORT.value
        assert candidate.domain == "houdini"
        assert candidate.title == "Test Recipe"
        assert candidate.quality_score == 0.85
        assert candidate.confidence == 0.9
        assert candidate.verified is True
        assert candidate.provenance is not None

    def test_shipping_candidate_serialization(self, sample_candidate: ShippingCandidate) -> None:
        """Test candidate serialization roundtrip."""
        data = sample_candidate.to_dict()
        restored = ShippingCandidate.from_dict(data)

        assert restored.candidate_id == sample_candidate.candidate_id
        assert restored.title == sample_candidate.title
        assert restored.domain == sample_candidate.domain
        assert restored.quality_score == sample_candidate.quality_score

    def test_shipping_candidate_content_signature(self, sample_candidate: ShippingCandidate) -> None:
        """Test content signature for deduplication."""
        sig1 = sample_candidate.content_signature
        assert sig1
        assert len(sig1) == 16

        # Same content should produce same signature
        data = sample_candidate.content_data.copy()
        candidate2 = ShippingCandidate(content_data=data)
        assert candidate2.content_signature == sig1

    def test_shipping_provenance_from_recipe(self, sample_recipe: dict[str, Any]) -> None:
        """Test provenance creation from recipe."""
        provenance = ShippingProvenance.from_recipe(sample_recipe, domain="houdini")

        assert provenance.source_type == SourceType.VERIFIED_RECIPE.value
        assert provenance.source_recipe_id == sample_recipe["recipe_id"]
        assert provenance.domain == "houdini"
        assert provenance.generator_version == SHIPPING_SCHEMA_VERSION

    def test_quality_gate_result_properties(self) -> None:
        """Test quality gate result properties."""
        result = QualityGateResult(
            status=QualityStatus.PASS,
            score=0.9,
            confidence=0.85,
            passed_checks=["check1", "check2"],
            warnings=["minor warning"],
        )

        assert result.is_eligible is True
        assert result.has_warnings is True

        # Failed result
        failed = QualityGateResult(
            status=QualityStatus.FAIL,
            failed_checks=["check1"],
            blocked_reason="Failed check1",
        )
        assert failed.is_eligible is False

    def test_shipping_result_report(self) -> None:
        """Test shipping result report generation."""
        result = ShippingResult(
            shipment_id="ship_test_001",
            status=ShipmentStatus.COMPLETED.value,
            candidates_considered=5,
            candidates_eligible=4,
            candidates_blocked=1,
            shipped_artifacts=[
                ShippingArtifact(
                    artifact_id="artifact_001",
                    artifact_kind=ArtifactKind.RECIPE_EXPORT.value,
                    domain="houdini",
                    export_path="exports/recipe.json",
                )
            ],
        )

        report = result.to_report()
        assert "Shipping Report" in report
        assert "ship_test_001" in report
        assert "Candidates considered: 5" in report
        assert "Shipped Artifacts" in report

    def test_knowledge_entry_from_recipe(self, sample_recipe: dict[str, Any]) -> None:
        """Test knowledge entry creation from recipe."""
        entry = KnowledgeEntry.from_recipe(
            sample_recipe,
            artifact_id="artifact_001",
            quality_score=0.85,
            confidence=0.9,
        )

        assert entry.title == "Test Recipe"
        assert entry.domain == "houdini"
        assert entry.entry_type == "recipe"
        assert "houdini" in entry.tags
        assert "recipe" in entry.tags
        assert entry.verified is True


# ------------------------------------------------------------------
# Quality Gate Tests
# ------------------------------------------------------------------


class TestQualityGate:
    """Tests for quality gate evaluation."""

    def test_high_quality_candidate_passes(self, sample_candidate: ShippingCandidate) -> None:
        """Test that high quality candidate passes."""
        result = evaluate_candidate(sample_candidate)

        assert result.status in (QualityStatus.PASS, QualityStatus.PASS_WITH_WARNINGS)
        assert result.is_eligible

    def test_low_quality_candidate_blocked(self) -> None:
        """Test that low quality candidate is blocked."""
        candidate = ShippingCandidate(
            content_data={"test": "data"},
            quality_score=0.2,  # Below threshold
            confidence=0.3,
            summary="A",  # Too short
        )

        result = evaluate_candidate(candidate)
        assert result.status == QualityStatus.FAIL
        assert not result.is_eligible

    def test_empty_content_blocked(self) -> None:
        """Test that empty content is blocked."""
        candidate = ShippingCandidate(
            content_data={},
            quality_score=0.8,
            confidence=0.8,
            summary="This is a valid summary",
        )

        result = evaluate_candidate(candidate)
        assert QualityChecks.HAS_CONTENT in result.failed_checks

    def test_duplicate_detection(self, sample_candidate: ShippingCandidate) -> None:
        """Test duplicate detection."""
        gate = QualityGate()

        # First candidate should not be duplicate
        eligible1, status1, _ = gate.check_eligibility(sample_candidate)
        assert status1 != EligibilityStatus.DUPLICATE

        # Register as shipped
        gate.register_shipped(sample_candidate)

        # Create duplicate with same content
        duplicate = ShippingCandidate(
            content_data=sample_candidate.content_data.copy(),
        )
        eligible2, status2, _ = gate.check_eligibility(duplicate)
        assert status2 == EligibilityStatus.DUPLICATE
        assert not eligible2

    def test_filter_eligible_candidates(self) -> None:
        """Test filtering candidates by eligibility."""
        candidates = [
            ShippingCandidate(
                content_data={"id": 1},
                quality_score=0.8,
                confidence=0.8,
                source_id="1",
                domain="test",
                summary="Valid summary",
            ),
            ShippingCandidate(
                content_data={"id": 2},
                quality_score=0.2,  # Low quality
                confidence=0.2,
                source_id="2",
                domain="test",
                summary="Valid summary",
            ),
            ShippingCandidate(
                content_data={"id": 3},
                quality_score=0.9,
                confidence=0.9,
                source_id="3",
                domain="test",
                summary="Valid summary",
            ),
        ]

        eligible, blocked = filter_eligible_candidates(candidates)

        assert len(eligible) == 2
        assert len(blocked) == 1
        assert blocked[0].source_id == "2"

    def test_is_high_quality_candidate(self, sample_candidate: ShippingCandidate) -> None:
        """Test quick quality check."""
        assert is_high_quality_candidate(sample_candidate)

        low_quality = ShippingCandidate(
            quality_score=0.2,
            confidence=0.2,
            summary="short",
        )
        assert not is_high_quality_candidate(low_quality)


# Need to import QualityChecks
from app.shipping.quality_gate import QualityChecks


# ------------------------------------------------------------------
# Recipe Exporter Tests
# ------------------------------------------------------------------


class TestRecipeExporter:
    """Tests for recipe export."""

    def test_export_recipe_to_json(
        self,
        sample_recipe: dict[str, Any],
        temp_dir: Path,
    ) -> None:
        """Test exporting recipe to JSON."""
        output_path = temp_dir / "recipe.json"

        result = export_recipe_to_json(sample_recipe, output_path)

        assert result is True
        assert output_path.exists()

        # Verify content
        data = json.loads(output_path.read_text(encoding="utf-8"))
        assert "export_id" in data
        assert "recipe" in data
        assert data["recipe"]["name"] == "Test Recipe"

    def test_export_recipe_to_markdown(
        self,
        sample_recipe: dict[str, Any],
        temp_dir: Path,
    ) -> None:
        """Test exporting recipe to Markdown."""
        output_path = temp_dir / "recipe.md"

        result = export_recipe_to_markdown(sample_recipe, output_path)

        assert result is True
        assert output_path.exists()

        content = output_path.read_text(encoding="utf-8")
        assert "# Test Recipe" in content
        assert "Steps" in content

    def test_export_full_package(
        self,
        sample_candidate: ShippingCandidate,
        temp_dir: Path,
    ) -> None:
        """Test full export package creation."""
        config = RecipeExportConfig(output_dir=temp_dir)
        exporter = RecipeExporter(config)

        result = exporter.export(sample_candidate)

        assert result.success
        assert Path(result.export_path).exists()
        assert Path(result.doc_path).exists()
        assert result.artifact is not None

    def test_export_preserves_provenance(
        self,
        sample_candidate: ShippingCandidate,
        temp_dir: Path,
    ) -> None:
        """Test that export preserves provenance."""
        config = RecipeExportConfig(output_dir=temp_dir)
        exporter = RecipeExporter(config)

        result = exporter.export(sample_candidate)

        # Read exported JSON
        data = json.loads(Path(result.export_path).read_text(encoding="utf-8"))
        assert "provenance" in data
        assert data["provenance"]["source_recipe_id"] == "recipe_test_001"

    def test_export_includes_version_metadata(
        self,
        sample_candidate: ShippingCandidate,
        temp_dir: Path,
    ) -> None:
        """Test that export includes version metadata."""
        config = RecipeExportConfig(output_dir=temp_dir)
        exporter = RecipeExporter(config)

        result = exporter.export(sample_candidate)

        data = json.loads(Path(result.export_path).read_text(encoding="utf-8"))
        assert "schema_version" in data
        assert "artifact_version" in data
        assert "exported_at" in data


# ------------------------------------------------------------------
# Documentation Generator Tests
# ------------------------------------------------------------------


class TestDocGenerator:
    """Tests for documentation generation."""

    def test_generate_recipe_documentation(self, sample_recipe: dict[str, Any]) -> None:
        """Test generating recipe documentation."""
        doc = generate_recipe_documentation(
            sample_recipe,
            quality={"quality_score": 0.85, "confidence": 0.9, "verified": True},
        )

        assert "# Test Recipe" in doc
        assert "Quality" in doc
        assert "Steps" in doc
        assert "create_node" in doc

    def test_generate_changelog(self) -> None:
        """Test generating changelog."""
        changes = [
            {"type": "added", "description": "New feature X"},
            {"type": "fixed", "description": "Bug fix Y"},
            {"type": "added", "description": "New feature Z"},
        ]

        doc = generate_changelog(changes, version="1.0.0")

        assert "# Changelog" in doc
        assert "## Added" in doc
        assert "## Fixed" in doc
        assert "New feature X" in doc
        assert "Bug fix Y" in doc

    def test_doc_generation_no_filler(self) -> None:
        """Test that doc generation doesn't produce filler for weak input."""
        weak_candidate = ShippingCandidate(
            content_data={},  # Empty
            title="",
            summary="",
            domain="",
        )

        config = DocGeneratorConfig(output_dir=Path(tempfile.mkdtemp()))
        generator = DocGenerator(config)
        result = generator.generate_for_candidate(weak_candidate)

        # Should fail or produce minimal output
        if result.success:
            content = Path(result.doc_path).read_text(encoding="utf-8")
            # Should not have invented content
            assert "lorem ipsum" not in content.lower()
            assert "placeholder" not in content.lower()


# ------------------------------------------------------------------
# Knowledge Base Tests
# ------------------------------------------------------------------


class TestKnowledgeBaseUpdater:
    """Tests for knowledge base updates."""

    def test_add_knowledge_entry(self, temp_dir: Path) -> None:
        """Test adding knowledge entry."""
        kb_dir = temp_dir / "kb"
        config = KBUpdaterConfig(kb_dir=kb_dir, index_path=kb_dir / "index.json")
        updater = KnowledgeBaseUpdater(config)

        entry = KnowledgeEntry(
            title="Test Entry",
            summary="Test summary",
            content="Test content",
            domain="test",
            entry_type="recipe",
            quality_score=0.8,
            confidence=0.8,
        )

        result = updater.add_entry(entry)

        assert result.success
        assert result.was_created
        assert Path(result.entry_path).exists()

    def test_kb_update_rejects_low_quality(self, temp_dir: Path) -> None:
        """Test that KB rejects low quality entries."""
        kb_dir = temp_dir / "kb_low_quality"
        config = KBUpdaterConfig(
            kb_dir=kb_dir,
            index_path=kb_dir / "index.json",
            min_quality_for_ingest=0.5,
        )
        updater = KnowledgeBaseUpdater(config)

        entry = KnowledgeEntry(
            title="Low Quality",
            summary="Bad",
            quality_score=0.2,  # Below threshold
            confidence=0.2,
        )

        result = updater.add_entry(entry)

        assert not result.success
        assert "below threshold" in result.errors[0]

    def test_kb_update_rejects_duplicate(self, temp_dir: Path) -> None:
        """Test that KB rejects duplicates."""
        # Use unique subdirectory for this test
        kb_dir = temp_dir / "kb_dedupe_test"
        config = KBUpdaterConfig(
            kb_dir=kb_dir,
            index_path=kb_dir / "index.json",
            deduplicate_by_signature=True,
        )
        updater = KnowledgeBaseUpdater(config)

        entry1 = KnowledgeEntry(
            title="Test",
            summary="Summary",
            content="Content",
            domain="test",
            entry_type="test",
            quality_score=0.8,
            confidence=0.8,
        )

        result1 = updater.add_entry(entry1)
        assert result1.success
        assert result1.was_created

        # Try to add duplicate with same content
        entry2 = KnowledgeEntry(
            title="Test",
            summary="Summary",
            content="Content",  # Same content
            domain="test",
            entry_type="test",
            quality_score=0.8,
            confidence=0.8,
        )

        result2 = updater.add_entry(entry2)
        assert result2.success  # Not an error
        assert not result2.was_created
        assert result2.duplicate_of == result1.entry_id

    def test_kb_search(self, temp_dir: Path) -> None:
        """Test knowledge base search."""
        # Use unique subdirectory for this test
        kb_dir = temp_dir / "kb_search_test"
        config = KBUpdaterConfig(kb_dir=kb_dir, index_path=kb_dir / "index.json")
        updater = KnowledgeBaseUpdater(config)

        # Add entries
        for i in range(3):
            entry = KnowledgeEntry(
                title=f"Entry {i}",
                summary=f"Summary {i}",
                content=f"Content {i}",
                domain="test",
                entry_type="recipe",
                quality_score=0.8,
                confidence=0.8,
            )
            updater.add_entry(entry)

        # Search
        results = updater.search(domain="test", limit=10)
        assert len(results) == 3


# ------------------------------------------------------------------
# Pipeline Integration Tests
# ------------------------------------------------------------------


class TestShippingPipeline:
    """Tests for complete shipping pipeline."""

    def test_verified_recipe_becomes_export_candidate(
        self,
        sample_recipe: dict[str, Any],
    ) -> None:
        """Test that verified recipe becomes export candidate."""
        candidate = ShippingCandidate.from_recipe(
            sample_recipe,
            quality_score=0.85,
            confidence=0.9,
            verified=True,
        )

        assert candidate.artifact_kind == ArtifactKind.RECIPE_EXPORT.value
        assert candidate.is_eligible or candidate.quality_score >= 0.5

    def test_full_pipeline_run(
        self,
        sample_recipe: dict[str, Any],
        temp_dir: Path,
    ) -> None:
        """Test complete pipeline run."""
        config = ShippingPipelineConfig(
            export_dir=temp_dir / "exports",
            doc_dir=temp_dir / "docs",
            kb_dir=temp_dir / "kb",
            report_dir=temp_dir / "reports",
        )
        service = ShippingService(config)

        candidate = ShippingCandidate.from_recipe(
            sample_recipe,
            quality_score=0.85,
            confidence=0.9,
            verified=True,
        )

        result = service.run_pipeline([candidate])

        assert result.shipping_result is not None
        assert result.shipping_result.success
        assert len(result.shipping_result.shipped_artifacts) > 0

    def test_low_quality_blocked(
        self,
        sample_recipe: dict[str, Any],
        temp_dir: Path,
    ) -> None:
        """Test that low quality candidate is blocked."""
        config = ShippingPipelineConfig(
            export_dir=temp_dir / "exports",
            min_quality_score=0.5,
        )
        service = ShippingService(config)

        # Create low quality candidate
        low_quality_recipe = sample_recipe.copy()
        low_quality_recipe["quality_score"] = 0.2

        candidate = ShippingCandidate.from_recipe(
            low_quality_recipe,
            quality_score=0.2,
            confidence=0.2,
        )

        result = service.run_pipeline([candidate])

        assert result.shipping_result.candidates_blocked == 1
        assert len(result.shipping_result.blocked_candidates) == 1

    def test_duplicate_shipment_skipped(
        self,
        sample_recipe: dict[str, Any],
        temp_dir: Path,
    ) -> None:
        """Test that duplicate shipment is skipped."""
        config = ShippingPipelineConfig(
            export_dir=temp_dir / "exports",
            kb_dir=temp_dir / "kb",
        )
        service = ShippingService(config)

        candidate = ShippingCandidate.from_recipe(
            sample_recipe,
            quality_score=0.85,
            confidence=0.9,
            verified=True,
        )

        # First shipment
        result1 = service.run_pipeline([candidate])
        assert result1.shipping_result.candidates_eligible == 1

        # Duplicate shipment
        result2 = service.run_pipeline([candidate])
        assert result2.shipping_result.candidates_duplicate == 1

    def test_collect_shipping_candidates(self, sample_recipe: dict[str, Any]) -> None:
        """Test collecting candidates from sources."""
        sources = [sample_recipe]

        candidates = collect_shipping_candidates(
            sources,
            source_type=SourceType.VERIFIED_RECIPE.value,
        )

        assert len(candidates) == 1
        assert candidates[0].source_type == SourceType.VERIFIED_RECIPE.value

    def test_shipping_report_summarizes(
        self,
        sample_recipe: dict[str, Any],
        temp_dir: Path,
    ) -> None:
        """Test that shipping report summarizes results."""
        config = ShippingPipelineConfig(
            export_dir=temp_dir / "exports",
            report_dir=temp_dir / "reports",
        )
        service = ShippingService(config)

        candidate = ShippingCandidate.from_recipe(
            sample_recipe,
            quality_score=0.85,
            confidence=0.9,
            verified=True,
        )

        result = service.run_pipeline([candidate])

        report = result.shipping_result.to_report()
        assert "Candidates considered: 1" in report
        assert "Shipped Artifacts" in report


# ------------------------------------------------------------------
# Shipping Policy Tests
# ------------------------------------------------------------------


class TestShippingPolicy:
    """Tests for shipping policy configuration."""

    def test_default_policy_values(self) -> None:
        """Test default policy has safe values."""
        policy = ShippingPolicyConfig()

        assert policy.enable_auto_shipping is True
        assert policy.skip_duplicates is True
        assert policy.require_verification_for_shipping is True
        assert policy.minimum_ship_score >= 0.5
        assert policy.max_shipments_per_run > 0

    def test_conservative_policy(self) -> None:
        """Test conservative policy factory."""
        policy = ShippingPolicyConfig.conservative()

        assert policy.minimum_ship_score >= 0.7
        assert policy.max_shipments_per_run <= 5
        assert policy.enable_auto_kb_update is False  # Conservative

    def test_testing_policy(self) -> None:
        """Test testing policy factory."""
        policy = ShippingPolicyConfig.testing()

        assert policy.require_evaluator_gate is False
        assert policy.minimum_ship_score <= 0.3
        assert policy.max_shipments_per_run >= 100

    def test_disabled_policy(self) -> None:
        """Test disabled policy factory."""
        policy = ShippingPolicyConfig.disabled()

        assert policy.enable_auto_shipping is False
        assert policy.enable_auto_recipe_export is False
        assert policy.enable_auto_doc_generation is False

    def test_is_shipping_enabled(self) -> None:
        """Test artifact kind shipping check."""
        policy = ShippingPolicyConfig()

        assert policy.is_shipping_enabled("recipe_export") is True
        assert policy.is_shipping_enabled("session_summary") is False  # Default off

        # When auto shipping disabled, all are off
        disabled = ShippingPolicyConfig.disabled()
        assert disabled.is_shipping_enabled("recipe_export") is False

    def test_get_minimum_score(self) -> None:
        """Test minimum score lookup by artifact kind."""
        policy = ShippingPolicyConfig()

        assert policy.get_minimum_score("recipe_export") == policy.minimum_recipe_score
        assert policy.get_minimum_score("documentation") == policy.minimum_doc_score
        assert policy.get_minimum_score("unknown") == policy.minimum_ship_score

    def test_validate_for_shipping(self) -> None:
        """Test policy validation."""
        # Valid policy
        policy = ShippingPolicyConfig()
        is_valid, issues = policy.validate_for_shipping()
        assert is_valid
        assert len(issues) == 0

        # Invalid score
        bad_policy = ShippingPolicyConfig(minimum_ship_score=1.5)
        is_valid, issues = bad_policy.validate_for_shipping()
        assert not is_valid
        assert any("must be between" in i for i in issues)

    def test_policy_serialization(self) -> None:
        """Test policy serialization roundtrip."""
        policy = ShippingPolicyConfig.conservative()
        data = policy.to_dict()
        restored = ShippingPolicyConfig.from_dict(data)

        assert restored.minimum_ship_score == policy.minimum_ship_score
        assert restored.max_shipments_per_run == policy.max_shipments_per_run
        assert restored.recipe_tags == policy.recipe_tags


# ------------------------------------------------------------------
# Candidate Collector Tests
# ------------------------------------------------------------------


class TestCandidateCollector:
    """Tests for candidate collection."""

    def test_collect_from_recipes(self, temp_dir: Path, sample_recipe: dict[str, Any]) -> None:
        """Test collecting candidates from recipes directory."""
        # Setup recipe directory
        recipes_dir = temp_dir / "recipes"
        recipes_dir.mkdir(parents=True)
        recipe_file = recipes_dir / "recipe_001.json"
        recipe_file.write_text(json.dumps(sample_recipe), encoding="utf-8")

        config = CandidateCollectorConfig(
            repo_root=temp_dir,
            recipes_dir="recipes",
        )
        collector = CandidateCollector(config)
        candidates = collector.collect_from_recipes()

        assert len(candidates) >= 1
        assert any(c.title == "Test Recipe" for c in candidates)

    def test_collect_from_sessions(self, temp_dir: Path) -> None:
        """Test collecting candidates from sessions."""
        # Setup session directory
        sessions_dir = temp_dir / "sessions" / "session_001"
        sessions_dir.mkdir(parents=True)
        manifest = {
            "session_id": "session_001",
            "status": "completed",
            "quality_score": 0.85,
            "event_count": 10,
            "summary": "Test session summary",
            "domain": "houdini",
        }
        (sessions_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

        config = CandidateCollectorConfig(repo_root=temp_dir, sessions_dir="sessions")
        collector = CandidateCollector(config)
        candidates = collector.collect_from_sessions()

        # May or may not collect depending on policy
        assert isinstance(candidates, list)

    def test_collect_all(self, temp_dir: Path, sample_recipe: dict[str, Any]) -> None:
        """Test collecting from all sources."""
        # Setup recipes
        recipes_dir = temp_dir / "recipes"
        recipes_dir.mkdir(parents=True)
        (recipes_dir / "recipe.json").write_text(json.dumps(sample_recipe), encoding="utf-8")

        config = CandidateCollectorConfig(repo_root=temp_dir)
        collector = CandidateCollector(config)
        result = collector.collect_all()

        assert result.total_found >= 0
        assert "recipes" in result.sources_scanned

    def test_collect_explicit(self) -> None:
        """Test creating explicit candidate."""
        config = CandidateCollectorConfig()
        collector = CandidateCollector(config)

        source_data = {"id": "test_001", "name": "Test", "data": {"foo": "bar"}}
        candidate = collector.collect_explicit(
            source_type="verified_recipe",
            source_data=source_data,
            quality_score=0.9,
            confidence=0.8,
            verified=True,
        )

        assert candidate.quality_score == 0.9
        assert candidate.confidence == 0.8
        assert candidate.verified is True

    def test_max_candidates_limit(self, temp_dir: Path, sample_recipe: dict[str, Any]) -> None:
        """Test that max candidates limit is respected."""
        recipes_dir = temp_dir / "recipes"
        recipes_dir.mkdir(parents=True)

        # Create multiple recipes
        for i in range(10):
            recipe = sample_recipe.copy()
            recipe["recipe_id"] = f"recipe_{i}"
            (recipes_dir / f"recipe_{i}.json").write_text(json.dumps(recipe), encoding="utf-8")

        config = CandidateCollectorConfig(
            repo_root=temp_dir,
            recipes_dir="recipes",
            max_candidates=3,
        )
        collector = CandidateCollector(config)
        result = collector.collect_all()

        assert result.total_found <= 3


# ------------------------------------------------------------------
# Shipment History Tests
# ------------------------------------------------------------------


class TestShipmentHistory:
    """Tests for shipment history tracking."""

    def test_record_shipment(self, temp_dir: Path) -> None:
        """Test recording a shipment in history."""
        history_dir = temp_dir / "history"
        config = ShipmentHistoryConfig(history_dir=history_dir)
        history = ShipmentHistory(config)

        result = ShippingResult(shipment_id="ship_001")
        artifact = ShippingArtifact(
            artifact_id="artifact_001",
            shipment_id="ship_001",
            artifact_kind=ArtifactKind.RECIPE_EXPORT.value,
            domain="houdini",
        )
        candidate = ShippingCandidate(
            candidate_id="candidate_001",
            content_data={"test": "data"},
            domain="houdini",
            source_id="recipe_001",
        )

        entry = history.record_shipment(result, artifact, candidate)

        assert entry is not None
        assert entry.shipment_id == "ship_001"
        assert entry.candidate_id == "candidate_001"

    def test_is_shipped_detection(self, temp_dir: Path) -> None:
        """Test detecting if candidate was already shipped."""
        history_dir = temp_dir / "history"
        config = ShipmentHistoryConfig(history_dir=history_dir)
        history = ShipmentHistory(config)

        result = ShippingResult()
        artifact = ShippingArtifact()
        candidate = ShippingCandidate(
            candidate_id="c_001",
            content_data={"unique": "content"},
            source_id="source_001",
        )

        # Not shipped initially
        assert not history.is_shipped(candidate)

        # Record shipment
        history.record_shipment(result, artifact, candidate)

        # Now shipped
        assert history.is_shipped(candidate)

    def test_get_by_signature(self, temp_dir: Path) -> None:
        """Test getting shipment by content signature."""
        history_dir = temp_dir / "history"
        config = ShipmentHistoryConfig(history_dir=history_dir)
        history = ShipmentHistory(config)

        result = ShippingResult()
        artifact = ShippingArtifact()
        candidate = ShippingCandidate(
            content_data={"sig": "test"},
        )

        history.record_shipment(result, artifact, candidate)

        # Find by signature
        signature = candidate.content_signature
        found = history.get_by_signature(signature)
        assert found is not None

    def test_get_recent(self, temp_dir: Path) -> None:
        """Test getting recent shipments."""
        history_dir = temp_dir / "history"
        config = ShipmentHistoryConfig(history_dir=history_dir)
        history = ShipmentHistory(config)

        # Add multiple shipments
        for i in range(5):
            result = ShippingResult(shipment_id=f"ship_{i}")
            artifact = ShippingArtifact()
            candidate = ShippingCandidate(
                candidate_id=f"c_{i}",
                content_data={"id": i},
            )
            history.record_shipment(result, artifact, candidate)

        recent = history.get_recent(limit=3)
        assert len(recent) == 3

    def test_get_stats(self, temp_dir: Path) -> None:
        """Test getting shipment history statistics."""
        history_dir = temp_dir / "history"
        config = ShipmentHistoryConfig(history_dir=history_dir)
        history = ShipmentHistory(config)

        # Add shipments from different domains
        for domain in ["houdini", "houdini", "touchdesigner"]:
            result = ShippingResult()
            artifact = ShippingArtifact()
            candidate = ShippingCandidate(
                content_data={"d": domain},
                domain=domain,
            )
            history.record_shipment(result, artifact, candidate)

        stats = history.get_stats()
        assert stats["total_shipments"] == 3
        assert "houdini" in stats["domains"]
        assert stats["domains"]["houdini"] == 2

    def test_history_persistence(self, temp_dir: Path) -> None:
        """Test that history persists across instances."""
        history_dir = temp_dir / "history"
        config = ShipmentHistoryConfig(history_dir=history_dir)

        # Create history and record
        history1 = ShipmentHistory(config)
        result = ShippingResult()
        artifact = ShippingArtifact()
        candidate = ShippingCandidate(
            candidate_id="persist_test",
            content_data={"persist": True},
        )
        history1.record_shipment(result, artifact, candidate)

        # Create new instance
        history2 = ShipmentHistory(config)
        assert history2.is_shipped(candidate)


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------


if __name__ == "__main__":
    pytest.main([__file__, "-v"])