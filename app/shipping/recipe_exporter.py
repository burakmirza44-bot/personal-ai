"""Recipe Exporter - Stable recipe export with versioning and provenance.

This module implements recipe export functionality for the shipping layer,
producing portable, versioned recipe artifacts.

Export formats:
- JSON: Structured, machine-readable
- Markdown: Human-readable documentation
- Manifest: Metadata and references
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.shipping.models import (
    ArtifactKind,
    ShippingArtifact,
    ShippingCandidate,
    ShippingProvenance,
    SHIPPING_SCHEMA_VERSION,
)


def _now_iso() -> str:
    """Return current UTC timestamp in ISO format."""
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _new_export_id() -> str:
    """Generate a unique export ID."""
    stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    return f"recipe_export_{stamp}_{uuid4().hex[:8]}"


@dataclass
class RecipeExportConfig:
    """Configuration for recipe export."""

    output_dir: Path = field(default_factory=lambda: Path("data/exports/recipes"))
    generate_markdown: bool = True
    generate_manifest: bool = True
    include_provenance: bool = True
    pretty_json: bool = True
    version: str = "1.0.0"


@dataclass
class RecipeExportResult:
    """Result of recipe export operation."""

    success: bool = False
    export_id: str = ""
    export_path: str = ""
    doc_path: str = ""
    manifest_path: str = ""
    artifact: ShippingArtifact | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "success": self.success,
            "export_id": self.export_id,
            "export_path": self.export_path,
            "doc_path": self.doc_path,
            "manifest_path": self.manifest_path,
            "artifact": self.artifact.to_dict() if self.artifact else None,
            "errors": self.errors,
            "warnings": self.warnings,
        }


class RecipeExporter:
    """Exports recipes to portable formats.

    Provides stable, versioned recipe exports with provenance tracking.
    """

    def __init__(self, config: RecipeExportConfig | None = None) -> None:
        """Initialize the recipe exporter.

        Args:
            config: Optional export configuration
        """
        self._config = config or RecipeExportConfig()

    def export(
        self,
        candidate: ShippingCandidate,
        shipment_id: str = "",
    ) -> RecipeExportResult:
        """Export a recipe candidate.

        Args:
            candidate: Shipping candidate with recipe content
            shipment_id: Optional shipment ID for tracking

        Returns:
            RecipeExportResult with export details
        """
        result = RecipeExportResult(export_id=_new_export_id())

        # Validate candidate
        if not candidate.content_data:
            result.errors.append("No recipe content in candidate")
            return result

        recipe = candidate.content_data
        export_id = result.export_id

        try:
            # Ensure output directory exists
            self._config.output_dir.mkdir(parents=True, exist_ok=True)

            # Build export package
            export_package = self._build_export_package(recipe, candidate, export_id)

            # Write JSON export
            json_path = self._config.output_dir / f"{export_id}.json"
            self._write_json(json_path, export_package)
            result.export_path = str(json_path)

            # Generate markdown documentation
            if self._config.generate_markdown:
                md_path = self._config.output_dir / f"{export_id}.md"
                self._write_markdown(md_path, export_package)
                result.doc_path = str(md_path)

            # Generate manifest
            if self._config.generate_manifest:
                manifest_path = self._config.output_dir / f"{export_id}_manifest.json"
                self._write_manifest(manifest_path, export_package)
                result.manifest_path = str(manifest_path)

            # Create artifact
            result.artifact = ShippingArtifact(
                artifact_id=f"artifact_{export_id}",
                shipment_id=shipment_id,
                candidate_id=candidate.candidate_id,
                artifact_kind=ArtifactKind.RECIPE_EXPORT.value,
                domain=candidate.domain,
                export_path=result.export_path,
                doc_path=result.doc_path,
                artifact_version=self._config.version,
                content_summary=candidate.summary[:200],
                metadata={
                    "recipe_name": recipe.get("name", ""),
                    "step_count": len(recipe.get("steps", [])),
                    "domain": candidate.domain,
                },
            )

            result.success = True

        except Exception as e:
            result.errors.append(f"Export failed: {str(e)}")

        return result

    def export_to_json(
        self,
        recipe: dict[str, Any],
        output_path: Path,
        provenance: ShippingProvenance | None = None,
    ) -> bool:
        """Export a recipe to JSON format.

        Args:
            recipe: Recipe data to export
            output_path: Output file path
            provenance: Optional provenance to include

        Returns:
            True if export succeeded
        """
        try:
            export_package = self._build_export_package(
                recipe,
                ShippingCandidate(content_data=recipe, provenance=provenance),
                _new_export_id(),
            )
            self._write_json(output_path, export_package)
            return True
        except Exception:
            return False

    def export_to_markdown(
        self,
        recipe: dict[str, Any],
        output_path: Path,
        provenance: ShippingProvenance | None = None,
    ) -> bool:
        """Export a recipe to Markdown format.

        Args:
            recipe: Recipe data to export
            output_path: Output file path
            provenance: Optional provenance to include

        Returns:
            True if export succeeded
        """
        try:
            export_package = self._build_export_package(
                recipe,
                ShippingCandidate(content_data=recipe, provenance=provenance),
                _new_export_id(),
            )
            self._write_markdown(output_path, export_package)
            return True
        except Exception:
            return False

    def _build_export_package(
        self,
        recipe: dict[str, Any],
        candidate: ShippingCandidate,
        export_id: str,
    ) -> dict[str, Any]:
        """Build the complete export package.

        Args:
            recipe: Recipe data
            candidate: Shipping candidate
            export_id: Export ID

        Returns:
            Complete export package dictionary
        """
        now = _now_iso()

        package = {
            "export_id": export_id,
            "exported_at": now,
            "schema_version": SHIPPING_SCHEMA_VERSION,
            "artifact_version": self._config.version,
            "artifact_kind": ArtifactKind.RECIPE_EXPORT.value,

            # Recipe content
            "recipe": {
                "recipe_id": recipe.get("recipe_id", export_id),
                "name": recipe.get("name", "Unnamed Recipe"),
                "description": recipe.get("description", ""),
                "domain": recipe.get("domain", candidate.domain),
                "steps": recipe.get("steps", []),
                "metadata": recipe.get("metadata", {}),
            },

            # Quality metrics
            "quality": {
                "quality_score": candidate.quality_score,
                "confidence": candidate.confidence,
                "verified": candidate.verified,
            },

            # Tags and classification
            "tags": candidate.tags,
            "domain": candidate.domain,

            # Execution hints
            "execution_hints": {
                "safety_level": recipe.get("safety_level", "safe"),
                "requires_bridge": any(
                    step.get("requires_bridge", False)
                    for step in recipe.get("steps", [])
                ),
                "step_count": len(recipe.get("steps", [])),
                "estimated_complexity": self._estimate_complexity(recipe),
            },
        }

        # Add provenance if available
        if self._config.include_provenance and candidate.provenance:
            package["provenance"] = candidate.provenance.to_dict()

        return package

    def _write_json(self, path: Path, data: dict[str, Any]) -> None:
        """Write data to JSON file.

        Args:
            path: Output path
            data: Data to write
        """
        indent = 2 if self._config.pretty_json else None
        path.write_text(
            json.dumps(data, indent=indent, ensure_ascii=False),
            encoding="utf-8",
        )

    def _write_markdown(self, path: Path, package: dict[str, Any]) -> None:
        """Write export package as markdown documentation.

        Args:
            path: Output path
            package: Export package
        """
        recipe = package.get("recipe", {})
        quality = package.get("quality", {})
        hints = package.get("execution_hints", {})
        provenance = package.get("provenance", {})

        lines = [
            f"# {recipe.get('name', 'Recipe Export')}",
            "",
            f"**Export ID:** {package.get('export_id', '')}",
            f"**Exported at:** {package.get('exported_at', '')}",
            f"**Version:** {package.get('artifact_version', '')}",
            f"**Domain:** {package.get('domain', '')}",
            "",
            "## Description",
            "",
            recipe.get("description", "No description available."),
            "",
            "## Quality Metrics",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Quality Score | {quality.get('quality_score', 0.0):.2f} |",
            f"| Confidence | {quality.get('confidence', 0.0):.2f} |",
            f"| Verified | {'Yes' if quality.get('verified') else 'No'} |",
            "",
            "## Execution Hints",
            "",
            f"- **Safety Level:** {hints.get('safety_level', 'safe')}",
            f"- **Requires Bridge:** {'Yes' if hints.get('requires_bridge') else 'No'}",
            f"- **Step Count:** {hints.get('step_count', 0)}",
            f"- **Estimated Complexity:** {hints.get('estimated_complexity', 'unknown')}",
            "",
        ]

        # Add steps
        steps = recipe.get("steps", [])
        if steps:
            lines.append("## Steps")
            lines.append("")
            for i, step in enumerate(steps, 1):
                lines.append(f"### Step {i}: {step.get('action', 'Unknown')}")
                lines.append("")
                if step.get("description"):
                    lines.append(step.get("description"))
                    lines.append("")
                if step.get("params"):
                    lines.append("**Parameters:**")
                    lines.append("")
                    for key, value in step.get("params", {}).items():
                        lines.append(f"- `{key}`: {value}")
                    lines.append("")

        # Add provenance
        if provenance:
            lines.append("## Provenance")
            lines.append("")
            lines.append(f"- **Source Type:** {provenance.get('source_type', '')}")
            lines.append(f"- **Source ID:** {provenance.get('source_id', '')}")
            lines.append(f"- **Domain:** {provenance.get('domain', '')}")
            if provenance.get("evidence_summary"):
                lines.append(f"- **Evidence:** {provenance.get('evidence_summary', '')}")
            lines.append("")

        # Add tags
        tags = package.get("tags", [])
        if tags:
            lines.append("## Tags")
            lines.append("")
            lines.append(", ".join(f"`{t}`" for t in tags))
            lines.append("")

        path.write_text("\n".join(lines), encoding="utf-8")

    def _write_manifest(self, path: Path, package: dict[str, Any]) -> None:
        """Write export manifest.

        Args:
            path: Output path
            package: Export package
        """
        manifest = {
            "manifest_version": "1.0",
            "export_id": package.get("export_id"),
            "exported_at": package.get("exported_at"),
            "schema_version": package.get("schema_version"),
            "artifact_kind": package.get("artifact_kind"),
            "domain": package.get("domain"),
            "recipe_name": package.get("recipe", {}).get("name"),
            "recipe_id": package.get("recipe", {}).get("recipe_id"),
            "quality_score": package.get("quality", {}).get("quality_score"),
            "confidence": package.get("quality", {}).get("confidence"),
            "verified": package.get("quality", {}).get("verified"),
            "step_count": len(package.get("recipe", {}).get("steps", [])),
            "files": {
                "export": f"{package.get('export_id')}.json",
                "documentation": f"{package.get('export_id')}.md",
            },
            "tags": package.get("tags", []),
        }

        self._write_json(path, manifest)

    def _estimate_complexity(self, recipe: dict[str, Any]) -> str:
        """Estimate recipe complexity.

        Args:
            recipe: Recipe data

        Returns:
            Complexity level string
        """
        steps = recipe.get("steps", [])
        step_count = len(steps)

        # Count parameters and dependencies
        total_params = sum(len(s.get("params", {})) for s in steps)
        deps = sum(1 for s in steps if s.get("depends_on"))

        if step_count <= 2 and total_params <= 5:
            return "simple"
        elif step_count <= 5 and total_params <= 15:
            return "moderate"
        elif step_count <= 10 and deps <= 3:
            return "complex"
        else:
            return "advanced"


# ------------------------------------------------------------------
# Convenience Functions
# ------------------------------------------------------------------


def export_recipe(
    recipe: dict[str, Any],
    output_dir: Path | str = "data/exports/recipes",
    provenance: ShippingProvenance | None = None,
    quality_score: float = 0.0,
    confidence: float = 0.0,
    verified: bool = False,
) -> RecipeExportResult:
    """Export a recipe to portable format.

    Args:
        recipe: Recipe data to export
        output_dir: Output directory
        provenance: Optional provenance
        quality_score: Quality score
        confidence: Confidence score
        verified: Whether recipe is verified

    Returns:
        RecipeExportResult
    """
    config = RecipeExportConfig(output_dir=Path(output_dir))
    exporter = RecipeExporter(config)

    candidate = ShippingCandidate(
        content_data=recipe,
        provenance=provenance,
        quality_score=quality_score,
        confidence=confidence,
        verified=verified,
        domain=recipe.get("domain", ""),
    )

    return exporter.export(candidate)


def export_recipe_to_json(
    recipe: dict[str, Any],
    output_path: Path | str,
    provenance: ShippingProvenance | None = None,
) -> bool:
    """Export recipe to JSON file.

    Args:
        recipe: Recipe data
        output_path: Output file path
        provenance: Optional provenance

    Returns:
        True if successful
    """
    exporter = RecipeExporter()
    return exporter.export_to_json(recipe, Path(output_path), provenance)


def export_recipe_to_markdown(
    recipe: dict[str, Any],
    output_path: Path | str,
    provenance: ShippingProvenance | None = None,
) -> bool:
    """Export recipe to Markdown file.

    Args:
        recipe: Recipe data
        output_path: Output file path
        provenance: Optional provenance

    Returns:
        True if successful
    """
    exporter = RecipeExporter()
    return exporter.export_to_markdown(recipe, Path(output_path), provenance)