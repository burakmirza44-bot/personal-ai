"""Documentation Generator - Evidence-backed documentation generation.

This module implements documentation generation for the shipping layer,
producing human-readable docs grounded in repo evidence.

Document types:
- Recipe documentation
- Changelog/release notes
- Knowledge delta summaries
- Shipping reports
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.shipping.models import (
    ArtifactKind,
    ShippingArtifact,
    ShippingCandidate,
    ShippingResult,
    SHIPPING_SCHEMA_VERSION,
)


def _now_iso() -> str:
    """Return current UTC timestamp in ISO format."""
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _new_doc_id() -> str:
    """Generate a unique document ID."""
    stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    return f"doc_{stamp}_{uuid4().hex[:8]}"


@dataclass
class DocGeneratorConfig:
    """Configuration for documentation generation."""

    output_dir: Path = field(default_factory=lambda: Path("data/docs"))
    max_line_width: int = 100
    include_toc: bool = True
    include_metadata: bool = True
    include_provenance: bool = True


@dataclass
class DocGeneratorResult:
    """Result of documentation generation."""

    success: bool = False
    doc_id: str = ""
    doc_path: str = ""
    doc_type: str = ""
    artifact: ShippingArtifact | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "success": self.success,
            "doc_id": self.doc_id,
            "doc_path": self.doc_path,
            "doc_type": self.doc_type,
            "artifact": self.artifact.to_dict() if self.artifact else None,
            "errors": self.errors,
            "warnings": self.warnings,
        }


class DocGenerator:
    """Generates evidence-backed documentation.

    Produces documentation grounded in actual artifacts and provenance,
    avoiding generic filler.
    """

    def __init__(self, config: DocGeneratorConfig | None = None) -> None:
        """Initialize the documentation generator.

        Args:
            config: Optional configuration
        """
        self._config = config or DocGeneratorConfig()

    def generate_for_candidate(
        self,
        candidate: ShippingCandidate,
        shipment_id: str = "",
    ) -> DocGeneratorResult:
        """Generate documentation for a shipping candidate.

        Args:
            candidate: Candidate to document
            shipment_id: Optional shipment ID

        Returns:
            DocGeneratorResult
        """
        doc_id = _new_doc_id()
        result = DocGeneratorResult(doc_id=doc_id)

        if not candidate.content_data:
            result.errors.append("No content to document")
            return result

        # Determine document type based on artifact kind
        doc_type = self._get_doc_type(candidate.artifact_kind)
        result.doc_type = doc_type

        try:
            # Ensure output directory exists
            self._config.output_dir.mkdir(parents=True, exist_ok=True)

            # Generate document content
            content = self._generate_doc_content(candidate, doc_id, doc_type)

            # Write document
            doc_path = self._config.output_dir / f"{doc_id}.md"
            doc_path.write_text(content, encoding="utf-8")
            result.doc_path = str(doc_path)

            # Create artifact
            result.artifact = ShippingArtifact(
                artifact_id=f"doc_artifact_{doc_id}",
                shipment_id=shipment_id,
                candidate_id=candidate.candidate_id,
                artifact_kind=ArtifactKind.DOCUMENTATION.value,
                domain=candidate.domain,
                doc_path=result.doc_path,
                content_summary=candidate.summary[:200],
                metadata={
                    "doc_type": doc_type,
                    "source_artifact_kind": candidate.artifact_kind,
                },
            )

            result.success = True

        except Exception as e:
            result.errors.append(f"Documentation generation failed: {str(e)}")

        return result

    def generate_recipe_doc(
        self,
        recipe: dict[str, Any],
        provenance: dict[str, Any] | None = None,
        quality: dict[str, Any] | None = None,
    ) -> str:
        """Generate documentation for a recipe.

        Args:
            recipe: Recipe data
            provenance: Optional provenance
            quality: Optional quality metrics

        Returns:
            Markdown documentation string
        """
        return self._generate_recipe_doc(recipe, provenance, quality)

    def generate_changelog_entry(
        self,
        changes: list[dict[str, Any]],
        version: str = "",
    ) -> str:
        """Generate a changelog-style entry.

        Args:
            changes: List of change records
            version: Optional version string

        Returns:
            Markdown changelog string
        """
        lines = [
            f"# Changelog - {version or _now_iso()[:10]}",
            "",
        ]

        # Group changes by type
        grouped: dict[str, list[dict[str, Any]]] = {}
        for change in changes:
            change_type = change.get("type", "changed")
            if change_type not in grouped:
                grouped[change_type] = []
            grouped[change_type].append(change)

        type_labels = {
            "added": "Added",
            "changed": "Changed",
            "fixed": "Fixed",
            "removed": "Removed",
            "deprecated": "Deprecated",
        }

        for change_type, items in grouped.items():
            label = type_labels.get(change_type, change_type.title())
            lines.append(f"## {label}")
            lines.append("")
            for item in items:
                desc = item.get("description", "No description")
                lines.append(f"- {desc}")
                if item.get("evidence"):
                    lines.append(f"  - Evidence: {item.get('evidence')}")
            lines.append("")

        return "\n".join(lines)

    def generate_knowledge_delta_doc(
        self,
        entries: list[dict[str, Any]],
        summary: str = "",
    ) -> str:
        """Generate documentation for knowledge base updates.

        Args:
            entries: Knowledge entries added/updated
            summary: Optional summary

        Returns:
            Markdown documentation string
        """
        lines = [
            "# Knowledge Base Delta",
            "",
            f"**Generated:** {_now_iso()}",
            f"**Entries:** {len(entries)}",
            "",
        ]

        if summary:
            lines.append("## Summary")
            lines.append("")
            lines.append(summary)
            lines.append("")

        lines.append("## Entries")
        lines.append("")

        for i, entry in enumerate(entries, 1):
            title = entry.get("title", f"Entry {i}")
            entry_type = entry.get("entry_type", "unknown")
            domain = entry.get("domain", "")

            lines.append(f"### {title}")
            lines.append("")
            if domain:
                lines.append(f"- **Domain:** {domain}")
            if entry_type:
                lines.append(f"- **Type:** {entry_type}")
            if entry.get("summary"):
                lines.append(f"- **Summary:** {entry.get('summary')}")
            lines.append("")

        return "\n".join(lines)

    def generate_shipping_report(
        self,
        shipping_result: ShippingResult,
    ) -> str:
        """Generate a shipping report document.

        Args:
            shipping_result: Shipping result to report

        Returns:
            Markdown report string
        """
        return shipping_result.to_report()

    def _get_doc_type(self, artifact_kind: str) -> str:
        """Get document type from artifact kind."""
        mapping = {
            ArtifactKind.RECIPE_EXPORT.value: "recipe_doc",
            ArtifactKind.KNOWLEDGE_ENTRY.value: "knowledge_doc",
            ArtifactKind.SESSION_SUMMARY.value: "session_doc",
            ArtifactKind.REPAIR_PATTERN.value: "repair_doc",
            ArtifactKind.TUTORIAL_KNOWLEDGE.value: "tutorial_doc",
        }
        return mapping.get(artifact_kind, "general_doc")

    def _generate_doc_content(
        self,
        candidate: ShippingCandidate,
        doc_id: str,
        doc_type: str,
    ) -> str:
        """Generate document content based on type.

        Args:
            candidate: Candidate to document
            doc_id: Document ID
            doc_type: Document type

        Returns:
            Markdown content
        """
        if doc_type == "recipe_doc":
            return self._generate_recipe_doc(
                candidate.content_data,
                candidate.provenance.to_dict() if candidate.provenance else None,
                {
                    "quality_score": candidate.quality_score,
                    "confidence": candidate.confidence,
                    "verified": candidate.verified,
                },
            )
        elif doc_type == "session_doc":
            return self._generate_session_doc(candidate)
        elif doc_type == "repair_doc":
            return self._generate_repair_doc(candidate)
        elif doc_type == "knowledge_doc":
            return self._generate_knowledge_doc(candidate)
        else:
            return self._generate_generic_doc(candidate, doc_id, doc_type)

    def _generate_recipe_doc(
        self,
        recipe: dict[str, Any],
        provenance: dict[str, Any] | None,
        quality: dict[str, Any] | None,
    ) -> str:
        """Generate recipe documentation."""
        lines = [
            f"# {recipe.get('name', 'Recipe')}",
            "",
        ]

        # Metadata
        if self._config.include_metadata:
            lines.append(f"**Generated:** {_now_iso()}")
            lines.append(f"**Schema Version:** {SHIPPING_SCHEMA_VERSION}")
            if recipe.get("domain"):
                lines.append(f"**Domain:** {recipe.get('domain')}")
            lines.append("")

        # Description
        desc = recipe.get("description", "")
        if desc:
            lines.append("## Overview")
            lines.append("")
            lines.append(desc)
            lines.append("")

        # Quality
        if quality:
            lines.append("## Quality")
            lines.append("")
            lines.append(f"| Metric | Value |")
            lines.append(f"|--------|-------|")
            lines.append(f"| Quality Score | {quality.get('quality_score', 0):.2f} |")
            lines.append(f"| Confidence | {quality.get('confidence', 0):.2f} |")
            lines.append(f"| Verified | {'Yes' if quality.get('verified') else 'No'} |")
            lines.append("")

        # Steps
        steps = recipe.get("steps", [])
        if steps:
            lines.append("## Steps")
            lines.append("")

            if self._config.include_toc:
                for i, step in enumerate(steps, 1):
                    action = step.get("action", f"Step {i}")
                    lines.append(f"{i}. [{action}](#step-{i}-{self._slugify(action)})")
                lines.append("")

            for i, step in enumerate(steps, 1):
                action = step.get("action", f"Step {i}")
                lines.append(f"### Step {i}: {action}")
                lines.append("")

                if step.get("description"):
                    lines.append(step.get("description"))
                    lines.append("")

                params = step.get("params", {})
                if params:
                    lines.append("**Parameters:**")
                    lines.append("")
                    lines.append("| Parameter | Value |")
                    lines.append("|-----------|-------|")
                    for key, value in params.items():
                        lines.append(f"| `{key}` | `{value}` |")
                    lines.append("")

                if step.get("expected_outcome"):
                    lines.append(f"**Expected outcome:** {step.get('expected_outcome')}")
                    lines.append("")

                if step.get("safety_level") and step.get("safety_level") != "safe":
                    lines.append(f"> ⚠️ **Safety Level:** {step.get('safety_level')}")
                    lines.append("")

        # Provenance
        if self._config.include_provenance and provenance:
            lines.append("## Provenance")
            lines.append("")
            lines.append(f"- **Source Type:** {provenance.get('source_type', '')}")
            lines.append(f"- **Source ID:** {provenance.get('source_id', '')}")
            if provenance.get("evidence_summary"):
                lines.append(f"- **Evidence:** {provenance.get('evidence_summary')}")
            lines.append("")

        return "\n".join(lines)

    def _generate_session_doc(self, candidate: ShippingCandidate) -> str:
        """Generate session summary documentation."""
        session = candidate.content_data
        lines = [
            f"# Session: {session.get('session_id', 'Unknown')}",
            "",
        ]

        if self._config.include_metadata:
            lines.append(f"**Domain:** {session.get('domain', candidate.domain)}")
            lines.append(f"**Generated:** {_now_iso()}")
            lines.append("")

        summary = session.get("summary", candidate.summary)
        if summary:
            lines.append("## Summary")
            lines.append("")
            lines.append(summary)
            lines.append("")

        # Events summary
        events = session.get("events", [])
        if events:
            lines.append(f"## Events ({len(events)} total)")
            lines.append("")
            # Group by type
            event_types: dict[str, int] = {}
            for event in events:
                etype = event.get("type", "unknown")
                event_types[etype] = event_types.get(etype, 0) + 1
            for etype, count in sorted(event_types.items()):
                lines.append(f"- {etype}: {count}")
            lines.append("")

        # Quality metrics
        if candidate.quality_score > 0 or candidate.confidence > 0:
            lines.append("## Quality Metrics")
            lines.append("")
            lines.append(f"- Quality Score: {candidate.quality_score:.2f}")
            lines.append(f"- Confidence: {candidate.confidence:.2f}")
            lines.append(f"- Verified: {'Yes' if candidate.verified else 'No'}")
            lines.append("")

        return "\n".join(lines)

    def _generate_repair_doc(self, candidate: ShippingCandidate) -> str:
        """Generate repair pattern documentation."""
        data = candidate.content_data
        lines = [
            f"# Repair Pattern: {candidate.title}",
            "",
        ]

        lines.append(f"**Domain:** {candidate.domain}")
        lines.append(f"**Generated:** {_now_iso()}")
        lines.append("")

        if candidate.summary:
            lines.append("## Summary")
            lines.append("")
            lines.append(candidate.summary)
            lines.append("")

        # Error context
        error_type = data.get("error_type", "")
        if error_type:
            lines.append("## Error Type")
            lines.append("")
            lines.append(f"`{error_type}`")
            lines.append("")

        # Fix steps
        fix_steps = data.get("fix_steps", [])
        if fix_steps:
            lines.append("## Fix Steps")
            lines.append("")
            for i, step in enumerate(fix_steps, 1):
                lines.append(f"{i}. {step}")
            lines.append("")

        # Success rate
        success_rate = data.get("success_rate", 0)
        if success_rate > 0:
            lines.append("## Success Rate")
            lines.append("")
            lines.append(f"{success_rate:.1%}")
            lines.append("")

        return "\n".join(lines)

    def _generate_knowledge_doc(self, candidate: ShippingCandidate) -> str:
        """Generate knowledge entry documentation."""
        data = candidate.content_data
        lines = [
            f"# {candidate.title}",
            "",
        ]

        lines.append(f"**Domain:** {candidate.domain}")
        lines.append(f"**Type:** {data.get('entry_type', 'knowledge')}")
        lines.append("")

        if candidate.summary:
            lines.append("## Summary")
            lines.append("")
            lines.append(candidate.summary)
            lines.append("")

        # Tags
        if candidate.tags:
            lines.append("## Tags")
            lines.append("")
            lines.append(", ".join(f"`{t}`" for t in candidate.tags))
            lines.append("")

        # Quality
        lines.append("## Quality")
        lines.append("")
        lines.append(f"- Quality Score: {candidate.quality_score:.2f}")
        lines.append(f"- Confidence: {candidate.confidence:.2f}")
        lines.append("")

        return "\n".join(lines)

    def _generate_generic_doc(
        self,
        candidate: ShippingCandidate,
        doc_id: str,
        doc_type: str,
    ) -> str:
        """Generate generic documentation."""
        lines = [
            f"# {candidate.title or doc_id}",
            "",
        ]

        lines.append(f"**Document ID:** {doc_id}")
        lines.append(f"**Type:** {doc_type}")
        lines.append(f"**Domain:** {candidate.domain}")
        lines.append(f"**Generated:** {_now_iso()}")
        lines.append("")

        if candidate.summary:
            lines.append("## Summary")
            lines.append("")
            lines.append(candidate.summary)
            lines.append("")

        if candidate.tags:
            lines.append("## Tags")
            lines.append("")
            lines.append(", ".join(f"`{t}`" for t in candidate.tags))
            lines.append("")

        return "\n".join(lines)

    def _slugify(self, text: str) -> str:
        """Convert text to URL-friendly slug."""
        import re
        text = text.lower()
        text = re.sub(r"[^a-z0-9]+", "-", text)
        text = text.strip("-")
        return text


# ------------------------------------------------------------------
# Convenience Functions
# ------------------------------------------------------------------


def generate_recipe_documentation(
    recipe: dict[str, Any],
    output_path: Path | str | None = None,
    provenance: dict[str, Any] | None = None,
    quality: dict[str, Any] | None = None,
) -> str:
    """Generate markdown documentation for a recipe.

    Args:
        recipe: Recipe data
        output_path: Optional path to write documentation
        provenance: Optional provenance
        quality: Optional quality metrics

    Returns:
        Markdown documentation string
    """
    generator = DocGenerator()
    doc = generator.generate_recipe_doc(recipe, provenance, quality)

    if output_path:
        Path(output_path).write_text(doc, encoding="utf-8")

    return doc


def generate_changelog(
    changes: list[dict[str, Any]],
    output_path: Path | str | None = None,
    version: str = "",
) -> str:
    """Generate a changelog document.

    Args:
        changes: List of change records
        output_path: Optional path to write changelog
        version: Optional version string

    Returns:
        Markdown changelog string
    """
    generator = DocGenerator()
    doc = generator.generate_changelog_entry(changes, version)

    if output_path:
        Path(output_path).write_text(doc, encoding="utf-8")

    return doc


def generate_docs_for_artifact(
    candidate: ShippingCandidate,
    output_dir: Path | str = "data/docs",
) -> DocGeneratorResult:
    """Generate documentation for a shipping candidate.

    Args:
        candidate: Candidate to document
        output_dir: Output directory

    Returns:
        DocGeneratorResult
    """
    config = DocGeneratorConfig(output_dir=Path(output_dir))
    generator = DocGenerator(config)
    return generator.generate_for_candidate(candidate)