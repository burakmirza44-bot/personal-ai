"""Shipping Module - Product Shipping Layer.

This module implements bounded shipping of validated internal outputs
into portable, versioned, and documented artifacts.

Core components:
- models: Shipping candidate, artifact, result, and KB entry models
- quality_gate: Eligibility checking and quality thresholds
- recipe_exporter: Recipe export with versioning and provenance
- doc_generator: Evidence-backed documentation generation
- kb_updater: Knowledge base updates with deduplication
- service: Main shipping pipeline orchestration

Main entry point:
    from app.shipping import run_shipping_pipeline
    result = run_shipping_pipeline(candidates)
"""

from app.shipping.models import (
    # Enums
    ArtifactKind,
    SourceType,
    EligibilityStatus,
    ShipmentStatus,
    QualityStatus,
    # Models
    QualityGateResult,
    ShippingProvenance,
    ShippingCandidate,
    ShippingArtifact,
    ShippingResult,
    KnowledgeEntry,
    # Constants
    SHIPPING_SCHEMA_VERSION,
)

from app.shipping.quality_gate import (
    QualityGate,
    QualityGateConfig,
    evaluate_candidate,
    check_shipping_eligibility,
    is_high_quality_candidate,
    filter_eligible_candidates,
)

from app.shipping.recipe_exporter import (
    RecipeExporter,
    RecipeExportConfig,
    export_recipe,
    export_recipe_to_json,
    export_recipe_to_markdown,
)

from app.shipping.doc_generator import (
    DocGenerator,
    DocGeneratorConfig,
    generate_recipe_documentation,
    generate_changelog,
)

from app.shipping.kb_updater import (
    KnowledgeBaseUpdater,
    KBUpdaterConfig,
    update_knowledge_base,
    search_knowledge,
)

from app.shipping.service import (
    ShippingService,
    ShippingPipelineConfig,
    run_shipping_pipeline,
    collect_shipping_candidates,
    get_shipping_report,
)

__all__ = [
    # Enums
    "ArtifactKind",
    "SourceType",
    "EligibilityStatus",
    "ShipmentStatus",
    "QualityStatus",
    # Models
    "QualityGateResult",
    "ShippingProvenance",
    "ShippingCandidate",
    "ShippingArtifact",
    "ShippingResult",
    "KnowledgeEntry",
    # Constants
    "SHIPPING_SCHEMA_VERSION",
    # Quality Gate
    "QualityGate",
    "QualityGateConfig",
    "evaluate_candidate",
    "check_shipping_eligibility",
    "is_high_quality_candidate",
    "filter_eligible_candidates",
    # Recipe Exporter
    "RecipeExporter",
    "RecipeExportConfig",
    "export_recipe",
    "export_recipe_to_json",
    "export_recipe_to_markdown",
    # Doc Generator
    "DocGenerator",
    "DocGeneratorConfig",
    "generate_recipe_documentation",
    "generate_changelog",
    # KB Updater
    "KnowledgeBaseUpdater",
    "KBUpdaterConfig",
    "update_knowledge_base",
    "search_knowledge",
    # Service
    "ShippingService",
    "ShippingPipelineConfig",
    "run_shipping_pipeline",
    "collect_shipping_candidates",
    "get_shipping_report",
]