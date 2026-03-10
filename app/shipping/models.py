"""Shipping Models - Core data structures for the Product Shipping layer.

This module defines the bounded models for shipping validated internal outputs
into portable, versioned, and documented artifacts.

Key models:
- ShippingCandidate: A candidate artifact eligible for shipping
- QualityGateResult: Result of quality gate evaluation
- ShippingArtifact: A shipped output artifact
- ShippingResult: Complete shipping pipeline result
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4


# Schema version for all shipping structures
SHIPPING_SCHEMA_VERSION = "shipping_v1"


def _now_iso() -> str:
    """Return current UTC timestamp in ISO format."""
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _new_id(prefix: str = "ship") -> str:
    """Generate a unique ID with prefix."""
    stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    return f"{prefix}_{stamp}_{uuid4().hex[:8]}"


# ------------------------------------------------------------------
# Enums
# ------------------------------------------------------------------


class ArtifactKind(str, Enum):
    """Types of shippable artifacts."""

    RECIPE_EXPORT = "recipe_export"
    DOCUMENTATION = "documentation"
    KNOWLEDGE_ENTRY = "knowledge_entry"
    RUNTIME_TRACE = "runtime_trace"
    SESSION_SUMMARY = "session_summary"
    REPAIR_PATTERN = "repair_pattern"
    TUTORIAL_KNOWLEDGE = "tutorial_knowledge"
    UNKNOWN = "unknown"


class SourceType(str, Enum):
    """Source types for shipping candidates."""

    VERIFIED_RECIPE = "verified_recipe"
    SUCCESSFUL_REPAIR = "successful_repair"
    DISTILLED_TUTORIAL = "distilled_tutorial"
    VALIDATED_TRACE = "validated_trace"
    APPROVED_GOAL = "approved_goal"
    KNOWLEDGE_DELTA = "knowledge_delta"
    SESSION_SUMMARY = "session_summary"
    UNKNOWN = "unknown"


class EligibilityStatus(str, Enum):
    """Eligibility status for shipping."""

    ELIGIBLE = "eligible"
    ELIGIBLE_WITH_WARNINGS = "eligible_with_warnings"
    BLOCKED = "blocked"
    DUPLICATE = "duplicate"
    PENDING_REVIEW = "pending_review"


class ShipmentStatus(str, Enum):
    """Status of a shipment."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"


class QualityStatus(str, Enum):
    """Quality gate status."""

    PASS = "pass"
    PASS_WITH_WARNINGS = "pass_with_warnings"
    FAIL = "fail"
    INSUFFICIENT_DATA = "insufficient_data"


# ------------------------------------------------------------------
# Quality Gate Result
# ------------------------------------------------------------------


@dataclass(slots=True)
class QualityGateResult:
    """Result of quality gate evaluation for a shipping candidate.

    Tracks whether a candidate passes quality requirements and why.
    """

    status: QualityStatus = QualityStatus.INSUFFICIENT_DATA
    score: float = 0.0
    confidence: float = 0.0
    verified: bool = False
    passed_checks: list[str] = field(default_factory=list)
    failed_checks: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    blocked_reason: str = ""
    required_checks: list[str] = field(default_factory=list)
    optional_checks: list[str] = field(default_factory=list)

    @property
    def is_eligible(self) -> bool:
        """Check if candidate is eligible for shipping."""
        return self.status in (QualityStatus.PASS, QualityStatus.PASS_WITH_WARNINGS)

    @property
    def has_warnings(self) -> bool:
        """Check if there are warnings."""
        return len(self.warnings) > 0 or self.status == QualityStatus.PASS_WITH_WARNINGS

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "status": self.status.value,
            "score": self.score,
            "confidence": self.confidence,
            "verified": self.verified,
            "passed_checks": self.passed_checks,
            "failed_checks": self.failed_checks,
            "warnings": self.warnings,
            "blocked_reason": self.blocked_reason,
            "required_checks": self.required_checks,
            "optional_checks": self.optional_checks,
            "is_eligible": self.is_eligible,
            "has_warnings": self.has_warnings,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QualityGateResult":
        """Deserialize from dictionary."""
        return cls(
            status=QualityStatus(data.get("status", "insufficient_data")),
            score=float(data.get("score", 0.0)),
            confidence=float(data.get("confidence", 0.0)),
            verified=bool(data.get("verified", False)),
            passed_checks=list(data.get("passed_checks", [])),
            failed_checks=list(data.get("failed_checks", [])),
            warnings=list(data.get("warnings", [])),
            blocked_reason=str(data.get("blocked_reason", "")),
            required_checks=list(data.get("required_checks", [])),
            optional_checks=list(data.get("optional_checks", [])),
        )


# ------------------------------------------------------------------
# Provenance
# ------------------------------------------------------------------


@dataclass(slots=True)
class ShippingProvenance:
    """Provenance tracking for shipped artifacts.

    Ensures all shipped artifacts are traceable to their sources.
    """

    source_type: str = ""
    source_id: str = ""
    source_goal_id: str = ""
    source_task_id: str = ""
    source_session_id: str = ""
    source_recipe_id: str = ""
    source_trace_id: str = ""
    domain: str = ""
    created_at: str = field(default_factory=_now_iso)
    generator_version: str = SHIPPING_SCHEMA_VERSION
    evidence_summary: str = ""
    verification_summary: str = ""
    source_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "source_type": self.source_type,
            "source_id": self.source_id,
            "source_goal_id": self.source_goal_id,
            "source_task_id": self.source_task_id,
            "source_session_id": self.source_session_id,
            "source_recipe_id": self.source_recipe_id,
            "source_trace_id": self.source_trace_id,
            "domain": self.domain,
            "created_at": self.created_at,
            "generator_version": self.generator_version,
            "evidence_summary": self.evidence_summary,
            "verification_summary": self.verification_summary,
            "source_metadata": self.source_metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ShippingProvenance":
        """Deserialize from dictionary."""
        return cls(
            source_type=str(data.get("source_type", "")),
            source_id=str(data.get("source_id", "")),
            source_goal_id=str(data.get("source_goal_id", "")),
            source_task_id=str(data.get("source_task_id", "")),
            source_session_id=str(data.get("source_session_id", "")),
            source_recipe_id=str(data.get("source_recipe_id", "")),
            source_trace_id=str(data.get("source_trace_id", "")),
            domain=str(data.get("domain", "")),
            created_at=str(data.get("created_at", "")),
            generator_version=str(data.get("generator_version", SHIPPING_SCHEMA_VERSION)),
            evidence_summary=str(data.get("evidence_summary", "")),
            verification_summary=str(data.get("verification_summary", "")),
            source_metadata=dict(data.get("source_metadata", {})),
        )

    @classmethod
    def from_recipe(cls, recipe: dict[str, Any], domain: str = "") -> "ShippingProvenance":
        """Create provenance from a recipe."""
        return cls(
            source_type=SourceType.VERIFIED_RECIPE.value,
            source_id=recipe.get("recipe_id", ""),
            source_recipe_id=recipe.get("recipe_id", ""),
            source_task_id=recipe.get("task_id", ""),
            domain=domain or recipe.get("domain", ""),
            evidence_summary=recipe.get("description", "")[:200],
            verification_summary=recipe.get("verification_summary", ""),
            source_metadata={
                "recipe_name": recipe.get("name", ""),
                "step_count": len(recipe.get("steps", [])),
            },
        )

    @classmethod
    def from_session(cls, session: dict[str, Any], domain: str = "") -> "ShippingProvenance":
        """Create provenance from a session."""
        return cls(
            source_type=SourceType.SESSION_SUMMARY.value,
            source_id=session.get("session_id", ""),
            source_session_id=session.get("session_id", ""),
            source_task_id=session.get("task_id", ""),
            domain=domain or session.get("domain", ""),
            evidence_summary=session.get("summary", "")[:200],
            verification_summary=session.get("verification_summary", ""),
            source_metadata={
                "status": session.get("status", ""),
                "event_count": session.get("event_count", 0),
            },
        )


# ------------------------------------------------------------------
# Shipping Candidate
# ------------------------------------------------------------------


@dataclass(slots=True)
class ShippingCandidate:
    """A candidate artifact eligible for shipping.

    Represents an internal validated output that can be shipped
    as an exportable artifact.
    """

    candidate_id: str = field(default_factory=lambda: _new_id("candidate"))
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    # Source info
    source_type: str = ""
    source_id: str = ""
    domain: str = ""

    # Artifact info
    artifact_kind: str = ""
    title: str = ""
    summary: str = ""
    content_ref: str = ""  # Path or reference to content
    content_data: dict[str, Any] = field(default_factory=dict)

    # Quality metrics
    quality_score: float = 0.0
    confidence: float = 0.0
    verified: bool = False

    # Eligibility
    eligibility_status: str = EligibilityStatus.PENDING_REVIEW.value
    quality_gate_result: QualityGateResult | None = None
    blocked_reason: str = ""

    # Provenance
    provenance: ShippingProvenance | None = None

    # Tags and metadata
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    # Versioning
    schema_version: str = SHIPPING_SCHEMA_VERSION

    @property
    def is_eligible(self) -> bool:
        """Check if candidate is eligible."""
        return self.eligibility_status in (
            EligibilityStatus.ELIGIBLE.value,
            EligibilityStatus.ELIGIBLE_WITH_WARNINGS.value,
        )

    @property
    def content_signature(self) -> str:
        """Generate content signature for deduplication."""
        content_str = json.dumps(self.content_data, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(content_str.encode()).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "candidate_id": self.candidate_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "source_type": self.source_type,
            "source_id": self.source_id,
            "domain": self.domain,
            "artifact_kind": self.artifact_kind,
            "title": self.title,
            "summary": self.summary,
            "content_ref": self.content_ref,
            "content_data": self.content_data,
            "quality_score": self.quality_score,
            "confidence": self.confidence,
            "verified": self.verified,
            "eligibility_status": self.eligibility_status,
            "quality_gate_result": self.quality_gate_result.to_dict() if self.quality_gate_result else None,
            "blocked_reason": self.blocked_reason,
            "provenance": self.provenance.to_dict() if self.provenance else None,
            "tags": self.tags,
            "metadata": self.metadata,
            "content_signature": self.content_signature,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ShippingCandidate":
        """Deserialize from dictionary."""
        qgr_data = data.get("quality_gate_result")
        prov_data = data.get("provenance")

        return cls(
            candidate_id=str(data.get("candidate_id", "")),
            created_at=str(data.get("created_at", "")),
            updated_at=str(data.get("updated_at", "")),
            source_type=str(data.get("source_type", "")),
            source_id=str(data.get("source_id", "")),
            domain=str(data.get("domain", "")),
            artifact_kind=str(data.get("artifact_kind", "")),
            title=str(data.get("title", "")),
            summary=str(data.get("summary", "")),
            content_ref=str(data.get("content_ref", "")),
            content_data=dict(data.get("content_data", {})),
            quality_score=float(data.get("quality_score", 0.0)),
            confidence=float(data.get("confidence", 0.0)),
            verified=bool(data.get("verified", False)),
            eligibility_status=str(data.get("eligibility_status", EligibilityStatus.PENDING_REVIEW.value)),
            quality_gate_result=QualityGateResult.from_dict(qgr_data) if qgr_data else None,
            blocked_reason=str(data.get("blocked_reason", "")),
            provenance=ShippingProvenance.from_dict(prov_data) if prov_data else None,
            tags=list(data.get("tags", [])),
            metadata=dict(data.get("metadata", {})),
            schema_version=str(data.get("schema_version", SHIPPING_SCHEMA_VERSION)),
        )

    @classmethod
    def from_recipe(
        cls,
        recipe: dict[str, Any],
        quality_score: float = 0.0,
        confidence: float = 0.0,
        verified: bool = False,
    ) -> "ShippingCandidate":
        """Create candidate from a verified recipe."""
        provenance = ShippingProvenance.from_recipe(recipe)
        return cls(
            source_type=SourceType.VERIFIED_RECIPE.value,
            source_id=recipe.get("recipe_id", ""),
            domain=recipe.get("domain", ""),
            artifact_kind=ArtifactKind.RECIPE_EXPORT.value,
            title=recipe.get("name", "Unnamed Recipe"),
            summary=recipe.get("description", "")[:500],
            content_data=recipe,
            quality_score=quality_score,
            confidence=confidence,
            verified=verified,
            provenance=provenance,
            tags=[recipe.get("domain", ""), "recipe"],
            metadata={
                "step_count": len(recipe.get("steps", [])),
                "safety_level": recipe.get("safety_level", "safe"),
            },
        )

    @classmethod
    def from_session_summary(
        cls,
        session: dict[str, Any],
        quality_score: float = 0.0,
        confidence: float = 0.0,
        verified: bool = False,
    ) -> "ShippingCandidate":
        """Create candidate from a session summary."""
        provenance = ShippingProvenance.from_session(session)
        return cls(
            source_type=SourceType.SESSION_SUMMARY.value,
            source_id=session.get("session_id", ""),
            domain=session.get("domain", ""),
            artifact_kind=ArtifactKind.SESSION_SUMMARY.value,
            title=f"Session: {session.get('session_id', 'Unknown')}",
            summary=session.get("summary", "")[:500],
            content_data=session,
            quality_score=quality_score,
            confidence=confidence,
            verified=verified,
            provenance=provenance,
            tags=[session.get("domain", ""), "session"],
        )


# ------------------------------------------------------------------
# Shipping Artifact
# ------------------------------------------------------------------


@dataclass(slots=True)
class ShippingArtifact:
    """A shipped output artifact.

    Represents a successfully shipped artifact with its outputs
    and references.
    """

    artifact_id: str = field(default_factory=lambda: _new_id("artifact"))
    shipment_id: str = ""
    shipped_at: str = field(default_factory=_now_iso)

    # Source
    candidate_id: str = ""
    artifact_kind: str = ""
    domain: str = ""

    # Outputs
    export_path: str = ""
    doc_path: str = ""
    kb_entry_id: str = ""
    manifest_ref: str = ""

    # Versioning
    artifact_version: str = "1.0.0"
    schema_version: str = SHIPPING_SCHEMA_VERSION

    # Content
    content_summary: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def has_export(self) -> bool:
        """Check if artifact has an export."""
        return bool(self.export_path)

    @property
    def has_doc(self) -> bool:
        """Check if artifact has documentation."""
        return bool(self.doc_path)

    @property
    def has_kb_entry(self) -> bool:
        """Check if artifact has a KB entry."""
        return bool(self.kb_entry_id)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "artifact_id": self.artifact_id,
            "shipment_id": self.shipment_id,
            "shipped_at": self.shipped_at,
            "candidate_id": self.candidate_id,
            "artifact_kind": self.artifact_kind,
            "domain": self.domain,
            "export_path": self.export_path,
            "doc_path": self.doc_path,
            "kb_entry_id": self.kb_entry_id,
            "manifest_ref": self.manifest_ref,
            "artifact_version": self.artifact_version,
            "schema_version": self.schema_version,
            "content_summary": self.content_summary,
            "metadata": self.metadata,
            "has_export": self.has_export,
            "has_doc": self.has_doc,
            "has_kb_entry": self.has_kb_entry,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ShippingArtifact":
        """Deserialize from dictionary."""
        return cls(
            artifact_id=str(data.get("artifact_id", "")),
            shipment_id=str(data.get("shipment_id", "")),
            shipped_at=str(data.get("shipped_at", "")),
            candidate_id=str(data.get("candidate_id", "")),
            artifact_kind=str(data.get("artifact_kind", "")),
            domain=str(data.get("domain", "")),
            export_path=str(data.get("export_path", "")),
            doc_path=str(data.get("doc_path", "")),
            kb_entry_id=str(data.get("kb_entry_id", "")),
            manifest_ref=str(data.get("manifest_ref", "")),
            artifact_version=str(data.get("artifact_version", "1.0.0")),
            schema_version=str(data.get("schema_version", SHIPPING_SCHEMA_VERSION)),
            content_summary=str(data.get("content_summary", "")),
            metadata=dict(data.get("metadata", {})),
        )


# ------------------------------------------------------------------
# Shipping Result
# ------------------------------------------------------------------


@dataclass(slots=True)
class ShippingResult:
    """Complete shipping pipeline result.

    Tracks all shipping outcomes including exports, docs, KB updates,
    and any issues encountered.
    """

    shipment_id: str = field(default_factory=lambda: _new_id("shipment"))
    shipped_at: str = field(default_factory=_now_iso)
    status: str = ShipmentStatus.PENDING.value

    # Candidates processed
    candidates_considered: int = 0
    candidates_eligible: int = 0
    candidates_blocked: int = 0
    candidates_duplicate: int = 0
    candidates_skipped: int = 0

    # Artifacts shipped
    shipped_artifacts: list[ShippingArtifact] = field(default_factory=list)
    exported_recipe_refs: list[str] = field(default_factory=list)
    generated_doc_refs: list[str] = field(default_factory=list)
    kb_update_refs: list[str] = field(default_factory=list)

    # Blocked/skipped
    blocked_candidates: list[dict[str, Any]] = field(default_factory=list)
    skipped_candidates: list[dict[str, Any]] = field(default_factory=list)
    duplicate_candidates: list[dict[str, Any]] = field(default_factory=list)

    # Quality summary
    quality_gate_summary: dict[str, Any] = field(default_factory=dict)
    version_summary: dict[str, Any] = field(default_factory=dict)

    # Issues
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    # Metadata
    duration_ms: float = 0.0
    schema_version: str = SHIPPING_SCHEMA_VERSION

    @property
    def success(self) -> bool:
        """Check if shipping was successful."""
        return self.status in (ShipmentStatus.COMPLETED.value, ShipmentStatus.PARTIAL.value)

    @property
    def has_shipped_artifacts(self) -> bool:
        """Check if any artifacts were shipped."""
        return len(self.shipped_artifacts) > 0

    @property
    def has_errors(self) -> bool:
        """Check if there were errors."""
        return len(self.errors) > 0

    @property
    def has_warnings(self) -> bool:
        """Check if there were warnings."""
        return len(self.warnings) > 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "shipment_id": self.shipment_id,
            "shipped_at": self.shipped_at,
            "status": self.status,
            "candidates_considered": self.candidates_considered,
            "candidates_eligible": self.candidates_eligible,
            "candidates_blocked": self.candidates_blocked,
            "candidates_duplicate": self.candidates_duplicate,
            "candidates_skipped": self.candidates_skipped,
            "shipped_artifacts": [a.to_dict() for a in self.shipped_artifacts],
            "exported_recipe_refs": self.exported_recipe_refs,
            "generated_doc_refs": self.generated_doc_refs,
            "kb_update_refs": self.kb_update_refs,
            "blocked_candidates": self.blocked_candidates,
            "skipped_candidates": self.skipped_candidates,
            "duplicate_candidates": self.duplicate_candidates,
            "quality_gate_summary": self.quality_gate_summary,
            "version_summary": self.version_summary,
            "warnings": self.warnings,
            "errors": self.errors,
            "duration_ms": self.duration_ms,
            "schema_version": self.schema_version,
            "success": self.success,
            "has_shipped_artifacts": self.has_shipped_artifacts,
            "has_errors": self.has_errors,
            "has_warnings": self.has_warnings,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ShippingResult":
        """Deserialize from dictionary."""
        return cls(
            shipment_id=str(data.get("shipment_id", "")),
            shipped_at=str(data.get("shipped_at", "")),
            status=str(data.get("status", ShipmentStatus.PENDING.value)),
            candidates_considered=int(data.get("candidates_considered", 0)),
            candidates_eligible=int(data.get("candidates_eligible", 0)),
            candidates_blocked=int(data.get("candidates_blocked", 0)),
            candidates_duplicate=int(data.get("candidates_duplicate", 0)),
            candidates_skipped=int(data.get("candidates_skipped", 0)),
            shipped_artifacts=[
                ShippingArtifact.from_dict(a) for a in data.get("shipped_artifacts", [])
            ],
            exported_recipe_refs=list(data.get("exported_recipe_refs", [])),
            generated_doc_refs=list(data.get("generated_doc_refs", [])),
            kb_update_refs=list(data.get("kb_update_refs", [])),
            blocked_candidates=list(data.get("blocked_candidates", [])),
            skipped_candidates=list(data.get("skipped_candidates", [])),
            duplicate_candidates=list(data.get("duplicate_candidates", [])),
            quality_gate_summary=dict(data.get("quality_gate_summary", {})),
            version_summary=dict(data.get("version_summary", {})),
            warnings=list(data.get("warnings", [])),
            errors=list(data.get("errors", [])),
            duration_ms=float(data.get("duration_ms", 0.0)),
            schema_version=str(data.get("schema_version", SHIPPING_SCHEMA_VERSION)),
        )

    def to_report(self) -> str:
        """Generate human-readable report."""
        lines = [
            f"# Shipping Report: {self.shipment_id}",
            f"",
            f"**Status:** {self.status}",
            f"**Shipped at:** {self.shipped_at}",
            f"**Duration:** {self.duration_ms:.0f}ms",
            f"",
            f"## Summary",
            f"",
            f"- Candidates considered: {self.candidates_considered}",
            f"- Candidates eligible: {self.candidates_eligible}",
            f"- Candidates blocked: {self.candidates_blocked}",
            f"- Candidates duplicate: {self.candidates_duplicate}",
            f"- Artifacts shipped: {len(self.shipped_artifacts)}",
            f"",
        ]

        if self.shipped_artifacts:
            lines.append("## Shipped Artifacts")
            lines.append("")
            for artifact in self.shipped_artifacts:
                lines.append(f"### {artifact.artifact_id}")
                lines.append(f"- Kind: {artifact.artifact_kind}")
                lines.append(f"- Domain: {artifact.domain}")
                if artifact.export_path:
                    lines.append(f"- Export: {artifact.export_path}")
                if artifact.doc_path:
                    lines.append(f"- Doc: {artifact.doc_path}")
                if artifact.kb_entry_id:
                    lines.append(f"- KB Entry: {artifact.kb_entry_id}")
                lines.append("")

        if self.blocked_candidates:
            lines.append("## Blocked Candidates")
            lines.append("")
            for c in self.blocked_candidates:
                lines.append(f"- {c.get('candidate_id', 'unknown')}: {c.get('reason', 'unknown reason')}")
            lines.append("")

        if self.warnings:
            lines.append("## Warnings")
            lines.append("")
            for w in self.warnings:
                lines.append(f"- {w}")
            lines.append("")

        if self.errors:
            lines.append("## Errors")
            lines.append("")
            for e in self.errors:
                lines.append(f"- {e}")
            lines.append("")

        return "\n".join(lines)


# ------------------------------------------------------------------
# Knowledge Entry
# ------------------------------------------------------------------


@dataclass(slots=True)
class KnowledgeEntry:
    """A knowledge base entry for shipping.

    Represents structured knowledge that can be added to the KB.
    """

    entry_id: str = field(default_factory=lambda: _new_id("kb"))
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    # Content
    title: str = ""
    summary: str = ""
    content: str = ""
    domain: str = ""

    # Classification
    entry_type: str = ""  # recipe, repair_pattern, tutorial, etc.
    tags: list[str] = field(default_factory=list)

    # Provenance
    provenance: ShippingProvenance | None = None
    source_artifact_id: str = ""

    # Quality
    quality_score: float = 0.0
    confidence: float = 0.0
    verified: bool = False

    # Versioning
    version: str = "1.0.0"
    schema_version: str = SHIPPING_SCHEMA_VERSION

    # Search/indexing
    search_text: str = ""
    embedding_ref: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "entry_id": self.entry_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "title": self.title,
            "summary": self.summary,
            "content": self.content,
            "domain": self.domain,
            "entry_type": self.entry_type,
            "tags": self.tags,
            "provenance": self.provenance.to_dict() if self.provenance else None,
            "source_artifact_id": self.source_artifact_id,
            "quality_score": self.quality_score,
            "confidence": self.confidence,
            "verified": self.verified,
            "version": self.version,
            "schema_version": self.schema_version,
            "search_text": self.search_text,
            "embedding_ref": self.embedding_ref,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "KnowledgeEntry":
        """Deserialize from dictionary."""
        prov_data = data.get("provenance")
        return cls(
            entry_id=str(data.get("entry_id", "")),
            created_at=str(data.get("created_at", "")),
            updated_at=str(data.get("updated_at", "")),
            title=str(data.get("title", "")),
            summary=str(data.get("summary", "")),
            content=str(data.get("content", "")),
            domain=str(data.get("domain", "")),
            entry_type=str(data.get("entry_type", "")),
            tags=list(data.get("tags", [])),
            provenance=ShippingProvenance.from_dict(prov_data) if prov_data else None,
            source_artifact_id=str(data.get("source_artifact_id", "")),
            quality_score=float(data.get("quality_score", 0.0)),
            confidence=float(data.get("confidence", 0.0)),
            verified=bool(data.get("verified", False)),
            version=str(data.get("version", "1.0.0")),
            schema_version=str(data.get("schema_version", SHIPPING_SCHEMA_VERSION)),
            search_text=str(data.get("search_text", "")),
            embedding_ref=str(data.get("embedding_ref", "")),
        )

    @classmethod
    def from_recipe(
        cls,
        recipe: dict[str, Any],
        artifact_id: str = "",
        quality_score: float = 0.0,
        confidence: float = 0.0,
    ) -> "KnowledgeEntry":
        """Create KB entry from a recipe."""
        provenance = ShippingProvenance.from_recipe(recipe)
        domain = recipe.get("domain", "")
        title = recipe.get("name", "Unnamed Recipe")
        summary = recipe.get("description", "")[:500]
        steps = recipe.get("steps", [])

        # Build search text from recipe content
        search_parts = [title, summary, domain]
        for step in steps:
            search_parts.append(step.get("action", ""))
            search_parts.append(step.get("description", ""))

        return cls(
            title=title,
            summary=summary,
            content=json.dumps(recipe, ensure_ascii=False, indent=2),
            domain=domain,
            entry_type="recipe",
            tags=[domain, "recipe"] + recipe.get("tags", []),
            provenance=provenance,
            source_artifact_id=artifact_id,
            quality_score=quality_score,
            confidence=confidence,
            verified=recipe.get("verified", False),
            search_text=" ".join(p for p in search_parts if p),
        )


# ------------------------------------------------------------------
# Convenience Functions
# ------------------------------------------------------------------


def create_shipping_candidate(
    source_type: str,
    source_data: dict[str, Any],
    quality_score: float = 0.0,
    confidence: float = 0.0,
    verified: bool = False,
) -> ShippingCandidate:
    """Create a shipping candidate from source data.

    Args:
        source_type: Type of source (verified_recipe, session_summary, etc.)
        source_data: Source data dictionary
        quality_score: Quality score (0.0 - 1.0)
        confidence: Confidence score (0.0 - 1.0)
        verified: Whether source is verified

    Returns:
        ShippingCandidate instance
    """
    if source_type == SourceType.VERIFIED_RECIPE.value:
        return ShippingCandidate.from_recipe(source_data, quality_score, confidence, verified)
    elif source_type == SourceType.SESSION_SUMMARY.value:
        return ShippingCandidate.from_session_summary(source_data, quality_score, confidence, verified)
    else:
        # Generic candidate
        return ShippingCandidate(
            source_type=source_type,
            source_id=source_data.get("id", source_data.get("recipe_id", source_data.get("session_id", ""))),
            domain=source_data.get("domain", ""),
            artifact_kind=ArtifactKind.UNKNOWN.value,
            title=source_data.get("name", source_data.get("title", "Unknown")),
            summary=source_data.get("description", source_data.get("summary", ""))[:500],
            content_data=source_data,
            quality_score=quality_score,
            confidence=confidence,
            verified=verified,
        )