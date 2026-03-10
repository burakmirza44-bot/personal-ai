"""Knowledge Base Updater - Approved knowledge entry ingestion.

This module implements knowledge base updates for the shipping layer,
with deduplication, provenance tracking, and index updates.

Key functionality:
- Add approved knowledge entries
- Update manifests/indexes
- Deduplicate overlapping entries
- Preserve provenance
- Version KB updates
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.shipping.models import (
    KnowledgeEntry,
    QualityStatus,
    ShippingArtifact,
    ShippingCandidate,
    SHIPPING_SCHEMA_VERSION,
)


def _now_iso() -> str:
    """Return current UTC timestamp in ISO format."""
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _new_kb_id() -> str:
    """Generate a unique KB entry ID."""
    stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    return f"kb_{stamp}_{uuid4().hex[:8]}"


@dataclass
class KBUpdaterConfig:
    """Configuration for knowledge base updater."""

    kb_dir: Path = field(default_factory=lambda: Path("data/knowledge"))
    index_path: Path = field(default_factory=lambda: Path("data/knowledge/index.json"))
    max_entries_per_domain: int = 1000
    min_quality_for_ingest: float = 0.5
    min_confidence_for_ingest: float = 0.4
    require_verified: bool = False
    deduplicate_by_signature: bool = True


@dataclass
class KBUpdateResult:
    """Result of a knowledge base update."""

    success: bool = False
    entry_id: str = ""
    entry_path: str = ""
    duplicate_of: str = ""
    was_updated: bool = False
    was_created: bool = False
    artifact: ShippingArtifact | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "success": self.success,
            "entry_id": self.entry_id,
            "entry_path": self.entry_path,
            "duplicate_of": self.duplicate_of,
            "was_updated": self.was_updated,
            "was_created": self.was_created,
            "artifact": self.artifact.to_dict() if self.artifact else None,
            "errors": self.errors,
            "warnings": self.warnings,
        }


class KnowledgeBaseUpdater:
    """Updates the knowledge base with approved entries.

    Provides bounded KB updates with quality gating, deduplication,
    and provenance preservation.
    """

    def __init__(self, config: KBUpdaterConfig | None = None) -> None:
        """Initialize the KB updater.

        Args:
            config: Optional configuration
        """
        self._config = config or KBUpdaterConfig()
        self._index: dict[str, Any] = {}
        self._signatures: dict[str, str] = {}  # signature -> entry_id
        self._loaded = False

    def add_entry(
        self,
        entry: KnowledgeEntry,
        shipment_id: str = "",
    ) -> KBUpdateResult:
        """Add a knowledge entry to the KB.

        Args:
            entry: Knowledge entry to add
            shipment_id: Optional shipment ID for tracking

        Returns:
            KBUpdateResult
        """
        result = KBUpdateResult(entry_id=entry.entry_id)

        # Load index if not loaded
        if not self._loaded:
            self._load_index()

        # Check quality threshold
        if entry.quality_score < self._config.min_quality_for_ingest:
            result.errors.append(
                f"Quality score {entry.quality_score:.2f} below threshold "
                f"{self._config.min_quality_for_ingest}"
            )
            return result

        if entry.confidence < self._config.min_confidence_for_ingest:
            result.errors.append(
                f"Confidence {entry.confidence:.2f} below threshold "
                f"{self._config.min_confidence_for_ingest}"
            )
            return result

        if self._config.require_verified and not entry.verified:
            result.errors.append("Entry must be verified")
            return result

        # Check for duplicate
        signature = self._compute_signature(entry)
        if self._config.deduplicate_by_signature and signature in self._signatures:
            existing_id = self._signatures[signature]
            result.duplicate_of = existing_id
            result.warnings.append(f"Duplicate of existing entry {existing_id}")
            result.success = True  # Not an error, just skipped
            return result

        try:
            # Ensure directory exists
            domain_dir = self._config.kb_dir / entry.domain
            domain_dir.mkdir(parents=True, exist_ok=True)

            # Write entry
            entry_path = domain_dir / f"{entry.entry_id}.json"
            entry_path.write_text(
                json.dumps(entry.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            result.entry_path = str(entry_path)
            result.was_created = True

            # Update index
            self._update_index(entry, signature)

            # Create artifact
            result.artifact = ShippingArtifact(
                artifact_id=f"kb_artifact_{entry.entry_id}",
                shipment_id=shipment_id,
                artifact_kind="knowledge_entry",
                domain=entry.domain,
                kb_entry_id=entry.entry_id,
                content_summary=entry.summary[:200],
                metadata={
                    "entry_type": entry.entry_type,
                    "quality_score": entry.quality_score,
                    "confidence": entry.confidence,
                },
            )

            result.success = True

        except Exception as e:
            result.errors.append(f"Failed to add entry: {str(e)}")

        return result

    def update_entry(
        self,
        entry_id: str,
        updates: dict[str, Any],
    ) -> KBUpdateResult:
        """Update an existing knowledge entry.

        Args:
            entry_id: Entry ID to update
            updates: Fields to update

        Returns:
            KBUpdateResult
        """
        result = KBUpdateResult(entry_id=entry_id)

        if not self._loaded:
            self._load_index()

        # Find entry
        entry_info = self._index.get("entries", {}).get(entry_id)
        if not entry_info:
            result.errors.append(f"Entry {entry_id} not found")
            return result

        try:
            # Load existing entry
            entry_path = Path(entry_info.get("path", ""))
            if not entry_path.exists():
                result.errors.append(f"Entry file not found: {entry_path}")
                return result

            entry_data = json.loads(entry_path.read_text(encoding="utf-8"))
            entry = KnowledgeEntry.from_dict(entry_data)

            # Apply updates
            for key, value in updates.items():
                if hasattr(entry, key):
                    setattr(entry, key, value)
            entry.updated_at = _now_iso()

            # Write updated entry
            entry_path.write_text(
                json.dumps(entry.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            result.entry_path = str(entry_path)
            result.was_updated = True
            result.success = True

        except Exception as e:
            result.errors.append(f"Failed to update entry: {str(e)}")

        return result

    def remove_entry(self, entry_id: str) -> bool:
        """Remove a knowledge entry.

        Args:
            entry_id: Entry ID to remove

        Returns:
            True if removed
        """
        if not self._loaded:
            self._load_index()

        entry_info = self._index.get("entries", {}).get(entry_id)
        if not entry_info:
            return False

        try:
            # Remove file
            entry_path = Path(entry_info.get("path", ""))
            if entry_path.exists():
                entry_path.unlink()

            # Remove from index
            if "entries" in self._index and entry_id in self._index["entries"]:
                del self._index["entries"][entry_id]

            # Remove from signatures
            signature = entry_info.get("signature", "")
            if signature in self._signatures:
                del self._signatures[signature]

            self._save_index()
            return True

        except Exception:
            return False

    def find_entry(self, entry_id: str) -> KnowledgeEntry | None:
        """Find a knowledge entry by ID.

        Args:
            entry_id: Entry ID

        Returns:
            KnowledgeEntry or None
        """
        if not self._loaded:
            self._load_index()

        entry_info = self._index.get("entries", {}).get(entry_id)
        if not entry_info:
            return None

        try:
            entry_path = Path(entry_info.get("path", ""))
            if not entry_path.exists():
                return None

            entry_data = json.loads(entry_path.read_text(encoding="utf-8"))
            return KnowledgeEntry.from_dict(entry_data)

        except Exception:
            return None

    def search(
        self,
        domain: str | None = None,
        entry_type: str | None = None,
        tags: list[str] | None = None,
        min_quality: float = 0.0,
        query: str = "",
        limit: int = 10,
    ) -> list[KnowledgeEntry]:
        """Search knowledge entries.

        Args:
            domain: Filter by domain
            entry_type: Filter by entry type
            tags: Filter by tags
            min_quality: Minimum quality score
            query: Text search query
            limit: Maximum results

        Returns:
            List of matching entries
        """
        if not self._loaded:
            self._load_index()

        results: list[tuple[float, KnowledgeEntry]] = []
        query_lower = query.lower() if query else ""

        for entry_id, entry_info in self._index.get("entries", {}).items():
            # Apply filters
            if domain and entry_info.get("domain") != domain:
                continue
            if entry_type and entry_info.get("entry_type") != entry_type:
                continue
            if min_quality > 0 and entry_info.get("quality_score", 0) < min_quality:
                continue
            if tags:
                entry_tags = set(entry_info.get("tags", []))
                if not set(tags).intersection(entry_tags):
                    continue

            # Calculate relevance
            score = 0.0
            if query_lower:
                if query_lower in entry_info.get("title", "").lower():
                    score += 10
                if query_lower in entry_info.get("summary", "").lower():
                    score += 5
                if query_lower in entry_info.get("search_text", "").lower():
                    score += 3
            else:
                score = entry_info.get("quality_score", 0.5)

            # Load entry
            entry = self.find_entry(entry_id)
            if entry:
                results.append((score, entry))

        # Sort by score
        results.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in results[:limit]]

    def get_domain_entries(self, domain: str) -> list[KnowledgeEntry]:
        """Get all entries for a domain.

        Args:
            domain: Domain name

        Returns:
            List of entries
        """
        return self.search(domain=domain, limit=self._config.max_entries_per_domain)

    def get_index_summary(self) -> dict[str, Any]:
        """Get summary of the knowledge base index.

        Returns:
            Summary dictionary
        """
        if not self._loaded:
            self._load_index()

        entries = self._index.get("entries", {})

        # Count by domain
        domains: dict[str, int] = {}
        for entry_info in entries.values():
            domain = entry_info.get("domain", "unknown")
            domains[domain] = domains.get(domain, 0) + 1

        # Count by type
        types: dict[str, int] = {}
        for entry_info in entries.values():
            etype = entry_info.get("entry_type", "unknown")
            types[etype] = types.get(etype, 0) + 1

        return {
            "total_entries": len(entries),
            "domains": domains,
            "entry_types": types,
            "last_updated": self._index.get("last_updated", ""),
            "schema_version": self._index.get("schema_version", ""),
        }

    def rebuild_index(self) -> dict[str, Any]:
        """Rebuild the index from existing entries.

        Returns:
            Summary of rebuild
        """
        self._index = {
            "schema_version": SHIPPING_SCHEMA_VERSION,
            "last_updated": _now_iso(),
            "entries": {},
        }
        self._signatures = {}

        count = 0
        errors = 0

        for domain_dir in self._config.kb_dir.iterdir():
            if not domain_dir.is_dir():
                continue

            for entry_file in domain_dir.glob("*.json"):
                try:
                    entry_data = json.loads(entry_file.read_text(encoding="utf-8"))
                    entry = KnowledgeEntry.from_dict(entry_data)
                    signature = self._compute_signature(entry)

                    self._index["entries"][entry.entry_id] = {
                        "path": str(entry_file),
                        "domain": entry.domain,
                        "entry_type": entry.entry_type,
                        "title": entry.title,
                        "summary": entry.summary[:200],
                        "tags": entry.tags,
                        "quality_score": entry.quality_score,
                        "confidence": entry.confidence,
                        "signature": signature,
                    }
                    self._signatures[signature] = entry.entry_id
                    count += 1

                except Exception:
                    errors += 1

        self._save_index()

        return {
            "indexed": count,
            "errors": errors,
            "total_entries": len(self._index["entries"]),
        }

    def _load_index(self) -> None:
        """Load the index from disk."""
        if self._config.index_path.exists():
            try:
                self._index = json.loads(
                    self._config.index_path.read_text(encoding="utf-8")
                )
                # Rebuild signatures from index
                for entry_id, entry_info in self._index.get("entries", {}).items():
                    signature = entry_info.get("signature", "")
                    if signature:
                        self._signatures[signature] = entry_id
            except Exception:
                self._index = {
                    "schema_version": SHIPPING_SCHEMA_VERSION,
                    "last_updated": _now_iso(),
                    "entries": {},
                }
        else:
            self._index = {
                "schema_version": SHIPPING_SCHEMA_VERSION,
                "last_updated": _now_iso(),
                "entries": {},
            }

        self._loaded = True

    def _save_index(self) -> None:
        """Save the index to disk."""
        self._config.index_path.parent.mkdir(parents=True, exist_ok=True)
        self._index["last_updated"] = _now_iso()
        self._config.index_path.write_text(
            json.dumps(self._index, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _update_index(self, entry: KnowledgeEntry, signature: str) -> None:
        """Update the index with a new entry."""
        domain_dir = self._config.kb_dir / entry.domain
        entry_path = domain_dir / f"{entry.entry_id}.json"

        self._index["entries"][entry.entry_id] = {
            "path": str(entry_path),
            "domain": entry.domain,
            "entry_type": entry.entry_type,
            "title": entry.title,
            "summary": entry.summary[:200],
            "tags": entry.tags,
            "quality_score": entry.quality_score,
            "confidence": entry.confidence,
            "signature": signature,
        }
        self._signatures[signature] = entry.entry_id

        self._save_index()

    def _compute_signature(self, entry: KnowledgeEntry) -> str:
        """Compute a signature for deduplication."""
        import hashlib
        # Use title, domain, entry_type, and content hash
        content = f"{entry.title}|{entry.domain}|{entry.entry_type}|{entry.content[:500]}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]


# ------------------------------------------------------------------
# Convenience Functions
# ------------------------------------------------------------------


def update_knowledge_base(
    entry: KnowledgeEntry,
    config: KBUpdaterConfig | None = None,
) -> KBUpdateResult:
    """Add a knowledge entry to the KB.

    Args:
        entry: Entry to add
        config: Optional configuration

    Returns:
        KBUpdateResult
    """
    updater = KnowledgeBaseUpdater(config)
    return updater.add_entry(entry)


def create_kb_entry_from_recipe(
    recipe: dict[str, Any],
    artifact_id: str = "",
    quality_score: float = 0.0,
    confidence: float = 0.0,
) -> KnowledgeEntry:
    """Create a KB entry from a recipe.

    Args:
        recipe: Recipe data
        artifact_id: Source artifact ID
        quality_score: Quality score
        confidence: Confidence score

    Returns:
        KnowledgeEntry
    """
    return KnowledgeEntry.from_recipe(recipe, artifact_id, quality_score, confidence)


def search_knowledge(
    query: str = "",
    domain: str | None = None,
    entry_type: str | None = None,
    limit: int = 10,
) -> list[KnowledgeEntry]:
    """Search knowledge entries.

    Args:
        query: Search query
        domain: Filter by domain
        entry_type: Filter by entry type
        limit: Maximum results

    Returns:
        List of matching entries
    """
    updater = KnowledgeBaseUpdater()
    return updater.search(
        domain=domain,
        entry_type=entry_type,
        query=query,
        limit=limit,
    )