"""Shipping Policy Configuration.

Provides bounded policy controls for the Product Shipper,
ensuring safe, controlled automatic shipping behavior.

Key functionality:
- Enable/disable flags for each shipping output type
- Quality thresholds for shipping eligibility
- Rate limiting and budget controls
- Duplicate handling configuration
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _default_recipe_tags() -> tuple[str, ...]:
    return ("verified", "high_quality")


def _default_doc_tags() -> tuple[str, ...]:
    return ("auto_generated",)


@dataclass
class ShippingPolicyConfig:
    """Configuration for the Product Shipper.

    This policy controls automatic shipping behavior with bounded,
    safe defaults.
    """

    # Enable/disable automatic shipping
    enable_auto_shipping: bool = True
    enable_auto_recipe_export: bool = True
    enable_auto_doc_generation: bool = True
    enable_auto_kb_update: bool = True

    # Quality thresholds
    require_evaluator_gate: bool = True
    require_verification_for_shipping: bool = True
    minimum_ship_score: float = 0.6
    minimum_recipe_score: float = 0.5
    minimum_doc_score: float = 0.4
    minimum_kb_score: float = 0.5
    minimum_confidence: float = 0.5

    # Rate limiting
    max_shipments_per_run: int = 10
    max_shipments_per_candidate: int = 3
    max_candidates_per_run: int = 50

    # Duplicate handling
    skip_duplicates: bool = True
    require_content_change_for_version: bool = True

    # Artifact types to ship
    ship_recipes: bool = True
    ship_documentation: bool = True
    ship_kb_entries: bool = True
    ship_session_summaries: bool = False
    ship_repair_patterns: bool = True

    # Archive behavior
    archive_rejected_candidates: bool = True
    archive_blocked_candidates: bool = True
    archive_low_quality: bool = False

    # Package options
    allow_partial_package: bool = True
    generate_full_package: bool = False
    include_provenance: bool = True
    include_quality_metrics: bool = True

    # Tags for shipped artifacts
    recipe_tags: tuple[str, ...] = field(default_factory=_default_recipe_tags)
    doc_tags: tuple[str, ...] = field(default_factory=_default_doc_tags)

    # Version
    policy_version: str = "1.0.0"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "enable_auto_shipping": self.enable_auto_shipping,
            "enable_auto_recipe_export": self.enable_auto_recipe_export,
            "enable_auto_doc_generation": self.enable_auto_doc_generation,
            "enable_auto_kb_update": self.enable_auto_kb_update,
            "require_evaluator_gate": self.require_evaluator_gate,
            "require_verification_for_shipping": self.require_verification_for_shipping,
            "minimum_ship_score": self.minimum_ship_score,
            "minimum_recipe_score": self.minimum_recipe_score,
            "minimum_doc_score": self.minimum_doc_score,
            "minimum_kb_score": self.minimum_kb_score,
            "minimum_confidence": self.minimum_confidence,
            "max_shipments_per_run": self.max_shipments_per_run,
            "max_shipments_per_candidate": self.max_shipments_per_candidate,
            "max_candidates_per_run": self.max_candidates_per_run,
            "skip_duplicates": self.skip_duplicates,
            "require_content_change_for_version": self.require_content_change_for_version,
            "ship_recipes": self.ship_recipes,
            "ship_documentation": self.ship_documentation,
            "ship_kb_entries": self.ship_kb_entries,
            "ship_session_summaries": self.ship_session_summaries,
            "ship_repair_patterns": self.ship_repair_patterns,
            "archive_rejected_candidates": self.archive_rejected_candidates,
            "archive_blocked_candidates": self.archive_blocked_candidates,
            "archive_low_quality": self.archive_low_quality,
            "allow_partial_package": self.allow_partial_package,
            "generate_full_package": self.generate_full_package,
            "include_provenance": self.include_provenance,
            "include_quality_metrics": self.include_quality_metrics,
            "recipe_tags": list(self.recipe_tags),
            "doc_tags": list(self.doc_tags),
            "policy_version": self.policy_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ShippingPolicyConfig":
        """Deserialize from dictionary."""
        return cls(
            enable_auto_shipping=data.get("enable_auto_shipping", True),
            enable_auto_recipe_export=data.get("enable_auto_recipe_export", True),
            enable_auto_doc_generation=data.get("enable_auto_doc_generation", True),
            enable_auto_kb_update=data.get("enable_auto_kb_update", True),
            require_evaluator_gate=data.get("require_evaluator_gate", True),
            require_verification_for_shipping=data.get("require_verification_for_shipping", True),
            minimum_ship_score=data.get("minimum_ship_score", 0.6),
            minimum_recipe_score=data.get("minimum_recipe_score", 0.5),
            minimum_doc_score=data.get("minimum_doc_score", 0.4),
            minimum_kb_score=data.get("minimum_kb_score", 0.5),
            minimum_confidence=data.get("minimum_confidence", 0.5),
            max_shipments_per_run=data.get("max_shipments_per_run", 10),
            max_shipments_per_candidate=data.get("max_shipments_per_candidate", 3),
            max_candidates_per_run=data.get("max_candidates_per_run", 50),
            skip_duplicates=data.get("skip_duplicates", True),
            require_content_change_for_version=data.get("require_content_change_for_version", True),
            ship_recipes=data.get("ship_recipes", True),
            ship_documentation=data.get("ship_documentation", True),
            ship_kb_entries=data.get("ship_kb_entries", True),
            ship_session_summaries=data.get("ship_session_summaries", False),
            ship_repair_patterns=data.get("ship_repair_patterns", True),
            archive_rejected_candidates=data.get("archive_rejected_candidates", True),
            archive_blocked_candidates=data.get("archive_blocked_candidates", True),
            archive_low_quality=data.get("archive_low_quality", False),
            allow_partial_package=data.get("allow_partial_package", True),
            generate_full_package=data.get("generate_full_package", False),
            include_provenance=data.get("include_provenance", True),
            include_quality_metrics=data.get("include_quality_metrics", True),
            recipe_tags=tuple(data.get("recipe_tags", ["verified", "high_quality"])),
            doc_tags=tuple(data.get("doc_tags", ["auto_generated"])),
            policy_version=data.get("policy_version", "1.0.0"),
        )

    @classmethod
    def conservative(cls) -> "ShippingPolicyConfig":
        """Create a conservative policy with strict controls."""
        return cls(
            enable_auto_shipping=True,
            enable_auto_recipe_export=True,
            enable_auto_doc_generation=True,
            enable_auto_kb_update=False,  # Conservative: no auto KB updates
            require_evaluator_gate=True,
            require_verification_for_shipping=True,
            minimum_ship_score=0.7,
            minimum_recipe_score=0.6,
            minimum_doc_score=0.5,
            minimum_kb_score=0.6,
            minimum_confidence=0.6,
            max_shipments_per_run=5,
            max_shipments_per_candidate=1,
            skip_duplicates=True,
            ship_session_summaries=False,
            ship_repair_patterns=True,
            allow_partial_package=False,
        )

    @classmethod
    def testing(cls) -> "ShippingPolicyConfig":
        """Create a policy suitable for testing."""
        return cls(
            enable_auto_shipping=True,
            enable_auto_recipe_export=True,
            enable_auto_doc_generation=True,
            enable_auto_kb_update=True,
            require_evaluator_gate=False,  # Easier for testing
            require_verification_for_shipping=False,
            minimum_ship_score=0.3,
            minimum_recipe_score=0.3,
            minimum_doc_score=0.3,
            minimum_kb_score=0.3,
            minimum_confidence=0.3,
            max_shipments_per_run=100,
            max_shipments_per_candidate=5,
            max_candidates_per_run=100,
        )

    @classmethod
    def disabled(cls) -> "ShippingPolicyConfig":
        """Create a policy that disables automatic shipping."""
        return cls(
            enable_auto_shipping=False,
            enable_auto_recipe_export=False,
            enable_auto_doc_generation=False,
            enable_auto_kb_update=False,
        )

    def is_shipping_enabled(self, artifact_kind: str) -> bool:
        """Check if shipping is enabled for a specific artifact kind.

        Args:
            artifact_kind: Type of artifact

        Returns:
            True if shipping is enabled for this kind
        """
        if not self.enable_auto_shipping:
            return False

        kind_map = {
            "recipe_export": self.ship_recipes,
            "documentation": self.ship_documentation,
            "knowledge_entry": self.ship_kb_entries,
            "session_summary": self.ship_session_summaries,
            "repair_pattern": self.ship_repair_patterns,
        }
        return kind_map.get(artifact_kind, False)

    def get_minimum_score(self, artifact_kind: str) -> float:
        """Get minimum quality score for an artifact kind.

        Args:
            artifact_kind: Type of artifact

        Returns:
            Minimum quality score threshold
        """
        score_map = {
            "recipe_export": self.minimum_recipe_score,
            "documentation": self.minimum_doc_score,
            "knowledge_entry": self.minimum_kb_score,
            "session_summary": self.minimum_ship_score,
            "repair_pattern": self.minimum_ship_score,
        }
        return score_map.get(artifact_kind, self.minimum_ship_score)

    def validate_for_shipping(self) -> tuple[bool, list[str]]:
        """Validate that policy settings are consistent.

        Returns:
            Tuple of (is_valid, issues)
        """
        issues = []

        # Check score thresholds are valid
        for name, score in [
            ("minimum_ship_score", self.minimum_ship_score),
            ("minimum_recipe_score", self.minimum_recipe_score),
            ("minimum_doc_score", self.minimum_doc_score),
            ("minimum_kb_score", self.minimum_kb_score),
            ("minimum_confidence", self.minimum_confidence),
        ]:
            if not 0.0 <= score <= 1.0:
                issues.append(f"{name} must be between 0.0 and 1.0, got {score}")

        # Check rate limits
        if self.max_shipments_per_run < 1:
            issues.append("max_shipments_per_run must be at least 1")
        if self.max_candidates_per_run < 1:
            issues.append("max_candidates_per_run must be at least 1")

        # Check logical consistency
        if self.enable_auto_shipping:
            if not any([
                self.ship_recipes,
                self.ship_documentation,
                self.ship_kb_entries,
                self.ship_session_summaries,
                self.ship_repair_patterns,
            ]):
                issues.append("Auto shipping enabled but no artifact types enabled")

        return len(issues) == 0, issues