"""Shipment History - Persists shipment state and prevents duplicates.

This module implements shipment history tracking with:
- Recent shipment persistence
- Duplicate detection via signatures
- Shipment state recovery
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.shipping.models import (
    ShippingArtifact,
    ShippingCandidate,
    ShippingResult,
    SHIPPING_SCHEMA_VERSION,
)

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    """Return current UTC timestamp in ISO format."""
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _new_history_id() -> str:
    """Generate a unique history entry ID."""
    stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    return f"hist_{stamp}_{uuid4().hex[:8]}"


@dataclass
class ShipmentHistoryConfig:
    """Configuration for shipment history."""

    history_dir: Path = field(default_factory=lambda: Path("data/shipping_history"))
    history_file: str = "shipments.json"
    max_history_entries: int = 1000
    max_signature_cache: int = 10000


@dataclass
class ShipmentHistoryEntry:
    """A single shipment history entry."""

    history_id: str = field(default_factory=_new_history_id)
    shipment_id: str = ""
    shipped_at: str = field(default_factory=_now_iso)
    candidate_id: str = ""
    content_signature: str = ""
    source_id: str = ""
    source_type: str = ""
    domain: str = ""
    artifact_kind: str = ""
    title: str = ""
    artifact_ids: list[str] = field(default_factory=list)
    quality_score: float = 0.0
    confidence: float = 0.0
    verified: bool = False
    schema_version: str = SHIPPING_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "history_id": self.history_id,
            "shipment_id": self.shipment_id,
            "shipped_at": self.shipped_at,
            "candidate_id": self.candidate_id,
            "content_signature": self.content_signature,
            "source_id": self.source_id,
            "source_type": self.source_type,
            "domain": self.domain,
            "artifact_kind": self.artifact_kind,
            "title": self.title,
            "artifact_ids": self.artifact_ids,
            "quality_score": self.quality_score,
            "confidence": self.confidence,
            "verified": self.verified,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ShipmentHistoryEntry":
        """Deserialize from dictionary."""
        return cls(
            history_id=data.get("history_id", ""),
            shipment_id=data.get("shipment_id", ""),
            shipped_at=data.get("shipped_at", ""),
            candidate_id=data.get("candidate_id", ""),
            content_signature=data.get("content_signature", ""),
            source_id=data.get("source_id", ""),
            source_type=data.get("source_type", ""),
            domain=data.get("domain", ""),
            artifact_kind=data.get("artifact_kind", ""),
            title=data.get("title", ""),
            artifact_ids=list(data.get("artifact_ids", [])),
            quality_score=float(data.get("quality_score", 0.0)),
            confidence=float(data.get("confidence", 0.0)),
            verified=bool(data.get("verified", False)),
            schema_version=data.get("schema_version", SHIPPING_SCHEMA_VERSION),
        )

    @classmethod
    def from_shipment(
        cls,
        result: ShippingResult,
        artifact: ShippingArtifact,
        candidate: ShippingCandidate,
    ) -> "ShipmentHistoryEntry":
        """Create history entry from shipment.

        Args:
            result: Shipping result
            artifact: Shipped artifact
            candidate: Source candidate

        Returns:
            ShipmentHistoryEntry
        """
        return cls(
            shipment_id=result.shipment_id,
            candidate_id=candidate.candidate_id,
            content_signature=candidate.content_signature,
            source_id=candidate.source_id,
            source_type=candidate.source_type,
            domain=candidate.domain,
            artifact_kind=artifact.artifact_kind,
            title=candidate.title,
            artifact_ids=[artifact.artifact_id],
            quality_score=candidate.quality_score,
            confidence=candidate.confidence,
            verified=candidate.verified,
        )


class ShipmentHistory:
    """Manages shipment history with duplicate detection.

    Provides:
    - Shipment persistence
    - Duplicate detection via content signatures
    - Recent shipment queries
    - History recovery
    """

    def __init__(self, config: ShipmentHistoryConfig | None = None) -> None:
        """Initialize shipment history.

        Args:
            config: Optional configuration
        """
        self._config = config or ShipmentHistoryConfig()
        self._history: dict[str, ShipmentHistoryEntry] = {}
        self._signatures: dict[str, str] = {}  # signature -> history_id
        self._source_ids: dict[str, str] = {}  # source_id -> history_id
        self._loaded = False

    def record_shipment(
        self,
        result: ShippingResult,
        artifact: ShippingArtifact,
        candidate: ShippingCandidate,
    ) -> ShipmentHistoryEntry | None:
        """Record a shipment in history.

        Args:
            result: Shipping result
            artifact: Shipped artifact
            candidate: Source candidate

        Returns:
            ShipmentHistoryEntry or None on error
        """
        if not self._loaded:
            self._load()

        entry = ShipmentHistoryEntry.from_shipment(result, artifact, candidate)

        # Add to history
        self._history[entry.history_id] = entry

        # Add to signature index
        if entry.content_signature:
            self._signatures[entry.content_signature] = entry.history_id

        # Add to source index
        if entry.source_id:
            self._source_ids[entry.source_id] = entry.history_id

        # Prune if needed
        self._prune_if_needed()

        # Save
        self._save()

        return entry

    def is_shipped(self, candidate: ShippingCandidate) -> bool:
        """Check if a candidate has already been shipped.

        Args:
            candidate: Candidate to check

        Returns:
            True if already shipped
        """
        if not self._loaded:
            self._load()

        # Check by content signature
        if candidate.content_signature in self._signatures:
            return True

        # Check by source ID
        if candidate.source_id and candidate.source_id in self._source_ids:
            return True

        return False

    def get_by_signature(self, signature: str) -> ShipmentHistoryEntry | None:
        """Get shipment by content signature.

        Args:
            signature: Content signature

        Returns:
            ShipmentHistoryEntry or None
        """
        if not self._loaded:
            self._load()

        history_id = self._signatures.get(signature)
        if not history_id:
            return None

        return self._history.get(history_id)

    def get_by_source_id(self, source_id: str) -> ShipmentHistoryEntry | None:
        """Get shipment by source ID.

        Args:
            source_id: Source ID

        Returns:
            ShipmentHistoryEntry or None
        """
        if not self._loaded:
            self._load()

        history_id = self._source_ids.get(source_id)
        if not history_id:
            return None

        return self._history.get(history_id)

    def get_recent(self, limit: int = 10) -> list[ShipmentHistoryEntry]:
        """Get recent shipments.

        Args:
            limit: Maximum entries to return

        Returns:
            List of ShipmentHistoryEntry sorted by date
        """
        if not self._loaded:
            self._load()

        entries = list(self._history.values())
        entries.sort(key=lambda e: e.shipped_at, reverse=True)
        return entries[:limit]

    def get_by_domain(self, domain: str, limit: int = 50) -> list[ShipmentHistoryEntry]:
        """Get shipments by domain.

        Args:
            domain: Domain to filter by
            limit: Maximum entries

        Returns:
            List of ShipmentHistoryEntry
        """
        if not self._loaded:
            self._load()

        entries = [e for e in self._history.values() if e.domain == domain]
        entries.sort(key=lambda e: e.shipped_at, reverse=True)
        return entries[:limit]

    def get_by_artifact_kind(self, artifact_kind: str, limit: int = 50) -> list[ShipmentHistoryEntry]:
        """Get shipments by artifact kind.

        Args:
            artifact_kind: Artifact kind to filter by
            limit: Maximum entries

        Returns:
            List of ShipmentHistoryEntry
        """
        if not self._loaded:
            self._load()

        entries = [e for e in self._history.values() if e.artifact_kind == artifact_kind]
        entries.sort(key=lambda e: e.shipped_at, reverse=True)
        return entries[:limit]

    def get_stats(self) -> dict[str, Any]:
        """Get shipment history statistics.

        Returns:
            Dictionary with stats
        """
        if not self._loaded:
            self._load()

        total = len(self._history)
        domains: dict[str, int] = {}
        kinds: dict[str, int] = {}

        for entry in self._history.values():
            domains[entry.domain] = domains.get(entry.domain, 0) + 1
            kinds[entry.artifact_kind] = kinds.get(entry.artifact_kind, 0) + 1

        recent = self.get_recent(1)
        last_shipped = recent[0].shipped_at if recent else None

        return {
            "total_shipments": total,
            "unique_signatures": len(self._signatures),
            "domains": domains,
            "artifact_kinds": kinds,
            "last_shipped_at": last_shipped,
        }

    def clear(self) -> None:
        """Clear shipment history."""
        self._history.clear()
        self._signatures.clear()
        self._source_ids.clear()
        self._save()

    def _load(self) -> None:
        """Load history from disk."""
        history_path = self._config.history_dir / self._config.history_file

        if history_path.exists():
            try:
                data = json.loads(history_path.read_text(encoding="utf-8"))
                for entry_data in data.get("entries", []):
                    entry = ShipmentHistoryEntry.from_dict(entry_data)
                    self._history[entry.history_id] = entry
                    if entry.content_signature:
                        self._signatures[entry.content_signature] = entry.history_id
                    if entry.source_id:
                        self._source_ids[entry.source_id] = entry.history_id
            except (json.JSONDecodeError, IOError) as e:
                logger.warning("Error loading shipment history: %s", e)

        self._loaded = True

    def _save(self) -> None:
        """Save history to disk."""
        self._config.history_dir.mkdir(parents=True, exist_ok=True)
        history_path = self._config.history_dir / self._config.history_file

        data = {
            "schema_version": SHIPPING_SCHEMA_VERSION,
            "last_updated": _now_iso(),
            "entries": [e.to_dict() for e in self._history.values()],
        }

        try:
            history_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except IOError as e:
            logger.error("Error saving shipment history: %s", e)

    def _prune_if_needed(self) -> None:
        """Prune history if limits exceeded."""
        # Prune history entries
        if len(self._history) > self._config.max_history_entries:
            # Remove oldest entries
            entries = sorted(self._history.values(), key=lambda e: e.shipped_at)
            to_remove = len(self._history) - self._config.max_history_entries

            for entry in entries[:to_remove]:
                self._history.pop(entry.history_id, None)
                self._signatures.pop(entry.content_signature, None)
                self._source_ids.pop(entry.source_id, None)

        # Prune signature cache
        if len(self._signatures) > self._config.max_signature_cache:
            # Rebuild from current history
            self._signatures.clear()
            self._source_ids.clear()
            for entry in self._history.values():
                if entry.content_signature:
                    self._signatures[entry.content_signature] = entry.history_id
                if entry.source_id:
                    self._source_ids[entry.source_id] = entry.history_id


# ------------------------------------------------------------------
# Convenience Functions
# ------------------------------------------------------------------


def get_shipment_history(repo_root: Path | str = ".") -> ShipmentHistory:
    """Get shipment history instance.

    Args:
        repo_root: Repository root path

    Returns:
        ShipmentHistory instance
    """
    config = ShipmentHistoryConfig(
        history_dir=Path(repo_root) / "data" / "shipping_history"
    )
    return ShipmentHistory(config)


def is_candidate_shipped(candidate: ShippingCandidate, repo_root: Path | str = ".") -> bool:
    """Check if a candidate has been shipped.

    Args:
        candidate: Candidate to check
        repo_root: Repository root path

    Returns:
        True if already shipped
    """
    history = get_shipment_history(repo_root)
    return history.is_shipped(candidate)


def record_shipment(
    result: ShippingResult,
    artifact: ShippingArtifact,
    candidate: ShippingCandidate,
    repo_root: Path | str = ".",
) -> ShipmentHistoryEntry | None:
    """Record a shipment in history.

    Args:
        result: Shipping result
        artifact: Shipped artifact
        candidate: Source candidate
        repo_root: Repository root path

    Returns:
        ShipmentHistoryEntry or None
    """
    history = get_shipment_history(repo_root)
    return history.record_shipment(result, artifact, candidate)