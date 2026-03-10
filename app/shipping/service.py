"""Shipping Service - Main shipping pipeline orchestration.

This module provides the main shipping service that orchestrates
the complete shipping pipeline:

1. Collect shipping candidates
2. Evaluate eligibility via quality gate
3. Export recipes
4. Generate documentation
5. Update knowledge base
6. Produce shipping report

Key entry point: run_shipping_pipeline()
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.shipping.models import (
    ArtifactKind,
    EligibilityStatus,
    KnowledgeEntry,
    ShippingArtifact,
    ShippingCandidate,
    ShippingResult,
    ShipmentStatus,
    SourceType,
)
from app.shipping.quality_gate import (
    QualityGate,
    QualityGateConfig,
    filter_eligible_candidates,
)
from app.shipping.recipe_exporter import (
    RecipeExporter,
    RecipeExportConfig,
    RecipeExportResult,
)
from app.shipping.doc_generator import (
    DocGenerator,
    DocGeneratorConfig,
    DocGeneratorResult,
)
from app.shipping.kb_updater import (
    KnowledgeBaseUpdater,
    KBUpdaterConfig,
    KBUpdateResult,
)


@dataclass
class ShippingPipelineConfig:
    """Configuration for the shipping pipeline."""

    # Output directories
    export_dir: Path = field(default_factory=lambda: Path("data/exports"))
    doc_dir: Path = field(default_factory=lambda: Path("data/docs"))
    kb_dir: Path = field(default_factory=lambda: Path("data/knowledge"))

    # Feature flags
    enable_recipe_export: bool = True
    enable_doc_generation: bool = True
    enable_kb_update: bool = True

    # Quality gate
    min_quality_score: float = 0.5
    min_confidence: float = 0.4
    require_verified: bool = False

    # Limits
    max_candidates_per_run: int = 100

    # Report output
    report_dir: Path = field(default_factory=lambda: Path("data/shipping_reports"))


@dataclass
class PipelineRunResult:
    """Result of a complete pipeline run."""

    shipping_result: ShippingResult | None = None
    export_results: list[RecipeExportResult] = field(default_factory=list)
    doc_results: list[DocGeneratorResult] = field(default_factory=list)
    kb_results: list[KBUpdateResult] = field(default_factory=list)
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "shipping_result": self.shipping_result.to_dict() if self.shipping_result else None,
            "export_results": [r.to_dict() for r in self.export_results],
            "doc_results": [r.to_dict() for r in self.doc_results],
            "kb_results": [r.to_dict() for r in self.kb_results],
            "duration_ms": self.duration_ms,
        }


class ShippingService:
    """Main shipping service orchestrating the complete pipeline.

    Provides a single entry point for shipping validated outputs
    into portable, versioned, documented artifacts.
    """

    def __init__(self, config: ShippingPipelineConfig | None = None) -> None:
        """Initialize the shipping service.

        Args:
            config: Optional pipeline configuration
        """
        self._config = config or ShippingPipelineConfig()

        # Initialize components
        self._quality_gate = QualityGate(QualityGateConfig(
            min_quality_score=self._config.min_quality_score,
            min_confidence=self._config.min_confidence,
            require_verified=self._config.require_verified,
        ))

        self._recipe_exporter = RecipeExporter(RecipeExportConfig(
            output_dir=self._config.export_dir / "recipes",
        ))

        self._doc_generator = DocGenerator(DocGeneratorConfig(
            output_dir=self._config.doc_dir,
        ))

        self._kb_updater = KnowledgeBaseUpdater(KBUpdaterConfig(
            kb_dir=self._config.kb_dir,
        ))

    def run_pipeline(
        self,
        candidates: list[ShippingCandidate],
    ) -> PipelineRunResult:
        """Run the complete shipping pipeline.

        This is the main entry point for shipping.

        Args:
            candidates: Candidates to ship

        Returns:
            PipelineRunResult with complete shipping outcome
        """
        start_time = time.perf_counter()
        result = PipelineRunResult()
        shipping_result = ShippingResult()

        # Limit candidates
        candidates = candidates[:self._config.max_candidates_per_run]
        shipping_result.candidates_considered = len(candidates)

        # Process each candidate
        for candidate in candidates:
            self._process_candidate(
                candidate,
                shipping_result,
                result,
            )

        # Determine final status
        if shipping_result.candidates_blocked == len(candidates):
            shipping_result.status = ShipmentStatus.FAILED.value
        elif shipping_result.has_shipped_artifacts:
            if shipping_result.candidates_blocked > 0:
                shipping_result.status = ShipmentStatus.PARTIAL.value
            else:
                shipping_result.status = ShipmentStatus.COMPLETED.value
        else:
            shipping_result.status = ShipmentStatus.SKIPPED.value

        # Build quality gate summary
        shipping_result.quality_gate_summary = {
            "total_candidates": shipping_result.candidates_considered,
            "eligible": shipping_result.candidates_eligible,
            "blocked": shipping_result.candidates_blocked,
            "duplicates": shipping_result.candidates_duplicate,
            "shipped": len(shipping_result.shipped_artifacts),
        }

        # Build version summary
        shipping_result.version_summary = {
            "schema_version": "shipping_v1",
            "exported_recipes": len(shipping_result.exported_recipe_refs),
            "generated_docs": len(shipping_result.generated_doc_refs),
            "kb_updates": len(shipping_result.kb_update_refs),
        }

        # Calculate duration
        result.duration_ms = (time.perf_counter() - start_time) * 1000
        shipping_result.duration_ms = result.duration_ms

        # Write shipping report
        self._write_report(shipping_result)

        result.shipping_result = shipping_result
        return result

    def _process_candidate(
        self,
        candidate: ShippingCandidate,
        shipping_result: ShippingResult,
        pipeline_result: PipelineRunResult,
    ) -> None:
        """Process a single candidate through the pipeline.

        Args:
            candidate: Candidate to process
            shipping_result: Shipping result to update
            pipeline_result: Pipeline result to update
        """
        # Check eligibility
        is_eligible, status, reason = self._quality_gate.check_eligibility(candidate)

        if status == EligibilityStatus.DUPLICATE:
            shipping_result.candidates_duplicate += 1
            shipping_result.duplicate_candidates.append({
                "candidate_id": candidate.candidate_id,
                "reason": reason,
            })
            return

        if not is_eligible:
            shipping_result.candidates_blocked += 1
            shipping_result.blocked_candidates.append({
                "candidate_id": candidate.candidate_id,
                "status": status.value,
                "reason": reason,
            })
            candidate.quality_gate_result = self._quality_gate.evaluate(candidate)
            return

        # Candidate is eligible
        shipping_result.candidates_eligible += 1

        # Create artifact
        artifact = ShippingArtifact(
            shipment_id=shipping_result.shipment_id,
            candidate_id=candidate.candidate_id,
            artifact_kind=candidate.artifact_kind,
            domain=candidate.domain,
        )

        # Process based on artifact kind
        if candidate.artifact_kind == ArtifactKind.RECIPE_EXPORT.value:
            self._process_recipe(
                candidate,
                artifact,
                shipping_result,
                pipeline_result,
            )
        elif candidate.artifact_kind == ArtifactKind.KNOWLEDGE_ENTRY.value:
            self._process_knowledge(
                candidate,
                artifact,
                shipping_result,
                pipeline_result,
            )
        else:
            # Generic processing
            self._process_generic(
                candidate,
                artifact,
                shipping_result,
                pipeline_result,
            )

        # Register as shipped for duplicate detection
        self._quality_gate.register_shipped(candidate)

        # Add to shipped artifacts
        if artifact.export_path or artifact.doc_path or artifact.kb_entry_id:
            shipping_result.shipped_artifacts.append(artifact)

    def _process_recipe(
        self,
        candidate: ShippingCandidate,
        artifact: ShippingArtifact,
        shipping_result: ShippingResult,
        pipeline_result: PipelineRunResult,
    ) -> None:
        """Process a recipe candidate."""
        # Export recipe
        if self._config.enable_recipe_export:
            export_result = self._recipe_exporter.export(
                candidate,
                shipment_id=shipping_result.shipment_id,
            )
            pipeline_result.export_results.append(export_result)

            if export_result.success:
                artifact.export_path = export_result.export_path
                artifact.doc_path = export_result.doc_path
                shipping_result.exported_recipe_refs.append(export_result.export_path)

                # Track artifact ID from export
                if export_result.artifact:
                    artifact.artifact_id = export_result.artifact.artifact_id

        # Generate documentation
        if self._config.enable_doc_generation:
            doc_result = self._doc_generator.generate_for_candidate(
                candidate,
                shipment_id=shipping_result.shipment_id,
            )
            pipeline_result.doc_results.append(doc_result)

            if doc_result.success:
                if not artifact.doc_path:
                    artifact.doc_path = doc_result.doc_path
                shipping_result.generated_doc_refs.append(doc_result.doc_path)

        # Update knowledge base
        if self._config.enable_kb_update:
            kb_entry = KnowledgeEntry.from_recipe(
                candidate.content_data,
                artifact_id=artifact.artifact_id,
                quality_score=candidate.quality_score,
                confidence=candidate.confidence,
            )
            kb_result = self._kb_updater.add_entry(
                kb_entry,
                shipment_id=shipping_result.shipment_id,
            )
            pipeline_result.kb_results.append(kb_result)

            if kb_result.success and kb_result.was_created:
                artifact.kb_entry_id = kb_result.entry_id
                shipping_result.kb_update_refs.append(kb_result.entry_id)

    def _process_knowledge(
        self,
        candidate: ShippingCandidate,
        artifact: ShippingArtifact,
        shipping_result: ShippingResult,
        pipeline_result: PipelineRunResult,
    ) -> None:
        """Process a knowledge entry candidate."""
        if self._config.enable_kb_update:
            entry = KnowledgeEntry(
                title=candidate.title,
                summary=candidate.summary,
                content=str(candidate.content_data),
                domain=candidate.domain,
                entry_type=candidate.metadata.get("entry_type", "knowledge"),
                tags=candidate.tags,
                provenance=candidate.provenance,
                quality_score=candidate.quality_score,
                confidence=candidate.confidence,
                verified=candidate.verified,
            )

            kb_result = self._kb_updater.add_entry(
                entry,
                shipment_id=shipping_result.shipment_id,
            )
            pipeline_result.kb_results.append(kb_result)

            if kb_result.success and kb_result.was_created:
                artifact.kb_entry_id = kb_result.entry_id
                shipping_result.kb_update_refs.append(kb_result.entry_id)

        # Generate documentation
        if self._config.enable_doc_generation:
            doc_result = self._doc_generator.generate_for_candidate(
                candidate,
                shipment_id=shipping_result.shipment_id,
            )
            pipeline_result.doc_results.append(doc_result)

            if doc_result.success:
                artifact.doc_path = doc_result.doc_path
                shipping_result.generated_doc_refs.append(doc_result.doc_path)

    def _process_generic(
        self,
        candidate: ShippingCandidate,
        artifact: ShippingArtifact,
        shipping_result: ShippingResult,
        pipeline_result: PipelineRunResult,
    ) -> None:
        """Process a generic candidate."""
        # Generate documentation
        if self._config.enable_doc_generation:
            doc_result = self._doc_generator.generate_for_candidate(
                candidate,
                shipment_id=shipping_result.shipment_id,
            )
            pipeline_result.doc_results.append(doc_result)

            if doc_result.success:
                artifact.doc_path = doc_result.doc_path
                shipping_result.generated_doc_refs.append(doc_result.doc_path)

    def _write_report(self, shipping_result: ShippingResult) -> None:
        """Write shipping report to disk."""
        try:
            self._config.report_dir.mkdir(parents=True, exist_ok=True)
            report_path = self._config.report_dir / f"{shipping_result.shipment_id}.md"
            report_path.write_text(shipping_result.to_report(), encoding="utf-8")

            # Also write JSON version
            json_path = self._config.report_dir / f"{shipping_result.shipment_id}.json"
            json_path.write_text(
                shipping_result.to_dict().__str__().replace("'", '"'),
                encoding="utf-8",
            )
        except Exception:
            pass  # Report writing is best-effort

    # ------------------------------------------------------------------
    # Convenience Methods
    # ------------------------------------------------------------------

    def export_recipe(
        self,
        recipe: dict[str, Any],
        quality_score: float = 0.0,
        confidence: float = 0.0,
        verified: bool = False,
    ) -> RecipeExportResult:
        """Export a single recipe.

        Args:
            recipe: Recipe to export
            quality_score: Quality score
            confidence: Confidence score
            verified: Whether verified

        Returns:
            RecipeExportResult
        """
        candidate = ShippingCandidate.from_recipe(
            recipe,
            quality_score=quality_score,
            confidence=confidence,
            verified=verified,
        )
        return self._recipe_exporter.export(candidate)

    def generate_docs(
        self,
        candidate: ShippingCandidate,
    ) -> DocGeneratorResult:
        """Generate documentation for a candidate.

        Args:
            candidate: Candidate to document

        Returns:
            DocGeneratorResult
        """
        return self._doc_generator.generate_for_candidate(candidate)

    def update_knowledge_base(
        self,
        entry: KnowledgeEntry,
    ) -> KBUpdateResult:
        """Add an entry to the knowledge base.

        Args:
            entry: Entry to add

        Returns:
            KBUpdateResult
        """
        return self._kb_updater.add_entry(entry)


# ------------------------------------------------------------------
# Convenience Functions
# ------------------------------------------------------------------


def run_shipping_pipeline(
    candidates: list[ShippingCandidate],
    config: ShippingPipelineConfig | None = None,
) -> PipelineRunResult:
    """Run the shipping pipeline.

    This is the main entry point for shipping.

    Args:
        candidates: Candidates to ship
        config: Optional configuration

    Returns:
        PipelineRunResult
    """
    service = ShippingService(config)
    return service.run_pipeline(candidates)


def collect_shipping_candidates(
    sources: list[dict[str, Any]],
    source_type: str = "verified_recipe",
) -> list[ShippingCandidate]:
    """Collect shipping candidates from sources.

    Args:
        sources: Source data dictionaries
        source_type: Type of sources

    Returns:
        List of ShippingCandidate
    """
    candidates = []
    for source in sources:
        candidate = ShippingCandidate(
            source_type=source_type,
            source_id=source.get("id", source.get("recipe_id", "")),
            domain=source.get("domain", ""),
            artifact_kind=_infer_artifact_kind(source_type),
            title=source.get("name", source.get("title", "")),
            summary=source.get("description", source.get("summary", ""))[:500],
            content_data=source,
            quality_score=source.get("quality_score", 0.5),
            confidence=source.get("confidence", 0.5),
            verified=source.get("verified", False),
            tags=source.get("tags", [source.get("domain", "")]),
        )
        candidates.append(candidate)
    return candidates


def _infer_artifact_kind(source_type: str) -> str:
    """Infer artifact kind from source type."""
    mapping = {
        SourceType.VERIFIED_RECIPE.value: ArtifactKind.RECIPE_EXPORT.value,
        SourceType.SUCCESSFUL_REPAIR.value: ArtifactKind.REPAIR_PATTERN.value,
        SourceType.DISTILLED_TUTORIAL.value: ArtifactKind.TUTORIAL_KNOWLEDGE.value,
        SourceType.VALIDATED_TRACE.value: ArtifactKind.RUNTIME_TRACE.value,
        SourceType.SESSION_SUMMARY.value: ArtifactKind.SESSION_SUMMARY.value,
        SourceType.KNOWLEDGE_DELTA.value: ArtifactKind.KNOWLEDGE_ENTRY.value,
    }
    return mapping.get(source_type, ArtifactKind.UNKNOWN.value)


def get_shipping_report(
    shipment_id: str,
    report_dir: Path | str = "data/shipping_reports",
) -> str | None:
    """Get a shipping report by ID.

    Args:
        shipment_id: Shipment ID
        report_dir: Report directory

    Returns:
        Report content or None
    """
    report_path = Path(report_dir) / f"{shipment_id}.md"
    if report_path.exists():
        return report_path.read_text(encoding="utf-8")
    return None


def export_recipe(
    recipe: dict[str, Any],
    output_dir: Path | str = "data/exports/recipes",
    quality_score: float = 0.5,
    confidence: float = 0.5,
    verified: bool = False,
) -> RecipeExportResult:
    """Export a single recipe.

    Args:
        recipe: Recipe to export
        output_dir: Output directory
        quality_score: Quality score
        confidence: Confidence score
        verified: Whether verified

    Returns:
        RecipeExportResult
    """
    from app.shipping.recipe_exporter import export_recipe as _export_recipe
    return _export_recipe(recipe, Path(output_dir), quality_score=quality_score, confidence=confidence, verified=verified)


def generate_docs_for_artifact(
    candidate: ShippingCandidate,
    output_dir: Path | str = "data/docs",
) -> DocGeneratorResult:
    """Generate documentation for a candidate.

    Args:
        candidate: Candidate to document
        output_dir: Output directory

    Returns:
        DocGeneratorResult
    """
    from app.shipping.doc_generator import generate_docs_for_artifact as _gen_docs
    return _gen_docs(candidate, Path(output_dir))


def update_knowledge_base(
    entry: KnowledgeEntry,
    kb_dir: Path | str = "data/knowledge",
) -> KBUpdateResult:
    """Update knowledge base with an entry.

    Args:
        entry: Entry to add
        kb_dir: Knowledge base directory

    Returns:
        KBUpdateResult
    """
    config = KBUpdaterConfig(kb_dir=Path(kb_dir))
    updater = KnowledgeBaseUpdater(config)
    return updater.add_entry(entry)