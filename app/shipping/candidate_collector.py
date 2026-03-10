"""Candidate Collector - Collects shippable candidates from various sources.

This module provides functionality to discover and collect shipping candidates
from verified recipes, session summaries, repair patterns, and other sources.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from app.shipping.models import (
    ArtifactKind,
    EligibilityStatus,
    ShippingCandidate,
    ShippingProvenance,
    SourceType,
    create_shipping_candidate,
)
from app.shipping.policy import ShippingPolicyConfig

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    """Return current UTC timestamp in ISO format."""
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


@dataclass
class CandidateCollectorConfig:
    """Configuration for the candidate collector."""

    repo_root: Path = field(default_factory=lambda: Path("."))
    recipes_dir: str = "data/recipes"
    sessions_dir: str = "data/sessions"
    traces_dir: str = "data/traces"
    memory_dir: str = "data/memory"
    max_candidates: int = 100


@dataclass
class CollectorResult:
    """Result of candidate collection."""

    candidates: list[ShippingCandidate] = field(default_factory=list)
    sources_scanned: list[str] = field(default_factory=list)
    total_found: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "candidates": [c.to_dict() for c in self.candidates],
            "sources_scanned": self.sources_scanned,
            "total_found": self.total_found,
            "errors": self.errors,
        }


class CandidateCollector:
    """Collects shipping candidates from various sources.

    Discovers candidates from:
    - Verified recipes
    - Successful session summaries
    - Repair patterns from memory
    - Validated traces
    """

    def __init__(
        self,
        config: CandidateCollectorConfig | None = None,
        policy: ShippingPolicyConfig | None = None,
    ) -> None:
        """Initialize the candidate collector.

        Args:
            config: Optional collector configuration
            policy: Optional shipping policy for filtering
        """
        self._config = config or CandidateCollectorConfig()
        self._policy = policy or ShippingPolicyConfig()
        self._seen_ids: set[str] = set()

    def collect_all(self) -> CollectorResult:
        """Collect candidates from all sources.

        Returns:
            CollectorResult with all discovered candidates
        """
        result = CollectorResult()

        # Collect from each source
        recipe_candidates = self.collect_from_recipes()
        result.candidates.extend(recipe_candidates)
        result.sources_scanned.append("recipes")

        session_candidates = self.collect_from_sessions()
        result.candidates.extend(session_candidates)
        result.sources_scanned.append("sessions")

        repair_candidates = self.collect_from_repair_patterns()
        result.candidates.extend(repair_candidates)
        result.sources_scanned.append("repair_patterns")

        # Apply max limit
        if len(result.candidates) > self._config.max_candidates:
            result.candidates = result.candidates[:self._config.max_candidates]

        result.total_found = len(result.candidates)

        return result

    def collect_from_recipes(self) -> list[ShippingCandidate]:
        """Collect candidates from verified recipes.

        Returns:
            List of ShippingCandidate from recipes
        """
        candidates = []
        recipes_path = self._config.repo_root / self._config.recipes_dir

        if not recipes_path.exists():
            logger.debug("Recipes directory does not exist: %s", recipes_path)
            return candidates

        # Scan for recipe files
        for recipe_file in recipes_path.glob("**/*.json"):
            try:
                recipe = self._load_json(recipe_file)
                if not recipe:
                    continue

                # Check if recipe is verified/high quality
                if self._is_recipe_shippable(recipe):
                    candidate = self._create_recipe_candidate(recipe)
                    if candidate and candidate.candidate_id not in self._seen_ids:
                        candidates.append(candidate)
                        self._seen_ids.add(candidate.candidate_id)

            except Exception as e:
                logger.warning("Error loading recipe %s: %s", recipe_file, e)

        return candidates

    def collect_from_sessions(self) -> list[ShippingCandidate]:
        """Collect candidates from session summaries.

        Returns:
            List of ShippingCandidate from sessions
        """
        candidates = []
        sessions_path = self._config.repo_root / self._config.sessions_dir

        if not sessions_path.exists():
            logger.debug("Sessions directory does not exist: %s", sessions_path)
            return candidates

        # Scan for session files
        for session_file in sessions_path.glob("**/manifest.json"):
            try:
                manifest = self._load_json(session_file)
                if not manifest:
                    continue

                # Check if session is successful
                if self._is_session_shippable(manifest):
                    candidate = self._create_session_candidate(manifest, session_file.parent)
                    if candidate and candidate.candidate_id not in self._seen_ids:
                        candidates.append(candidate)
                        self._seen_ids.add(candidate.candidate_id)

            except Exception as e:
                logger.warning("Error loading session %s: %s", session_file, e)

        return candidates

    def collect_from_repair_patterns(self) -> list[ShippingCandidate]:
        """Collect candidates from repair patterns.

        Returns:
            List of ShippingCandidate from repair patterns
        """
        candidates = []
        memory_path = self._config.repo_root / self._config.memory_dir

        if not memory_path.exists():
            logger.debug("Memory directory does not exist: %s", memory_path)
            return candidates

        # Look for repair patterns
        repair_file = memory_path / "repair_patterns.json"
        if repair_file.exists():
            try:
                patterns = self._load_json(repair_file)
                if patterns:
                    for pattern in patterns.get("patterns", []):
                        if self._is_repair_shippable(pattern):
                            candidate = self._create_repair_candidate(pattern)
                            if candidate and candidate.candidate_id not in self._seen_ids:
                                candidates.append(candidate)
                                self._seen_ids.add(candidate.candidate_id)
            except Exception as e:
                logger.warning("Error loading repair patterns: %s", e)

        return candidates

    def collect_from_trace(self, trace_id: str) -> ShippingCandidate | None:
        """Collect candidate from a specific trace.

        Args:
            trace_id: Trace ID to collect from

        Returns:
            ShippingCandidate or None
        """
        traces_path = self._config.repo_root / self._config.traces_dir / trace_id

        if not traces_path.exists():
            return None

        try:
            summary_file = traces_path / "summary.json"
            if not summary_file.exists():
                return None

            summary = self._load_json(summary_file)
            if not summary:
                return None

            # Check if trace is high quality
            if summary.get("final_outcome") == "success" and summary.get("quality_score", 0) >= 0.5:
                return self._create_trace_candidate(summary, trace_id)

        except Exception as e:
            logger.warning("Error loading trace %s: %s", trace_id, e)

        return None

    def collect_explicit(
        self,
        source_type: str,
        source_data: dict[str, Any],
        quality_score: float = 0.0,
        confidence: float = 0.0,
        verified: bool = False,
    ) -> ShippingCandidate:
        """Create a candidate from explicit source data.

        Args:
            source_type: Type of source
            source_data: Source data dictionary
            quality_score: Quality score
            confidence: Confidence score
            verified: Whether source is verified

        Returns:
            ShippingCandidate
        """
        return create_shipping_candidate(
            source_type=source_type,
            source_data=source_data,
            quality_score=quality_score,
            confidence=confidence,
            verified=verified,
        )

    def _load_json(self, path: Path) -> dict[str, Any] | None:
        """Load JSON file.

        Args:
            path: Path to JSON file

        Returns:
            Loaded dictionary or None
        """
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.debug("Error loading JSON %s: %s", path, e)
            return None

    def _is_recipe_shippable(self, recipe: dict[str, Any]) -> bool:
        """Check if a recipe is shippable.

        Args:
            recipe: Recipe data

        Returns:
            True if recipe can be shipped
        """
        # Check verification status
        if recipe.get("verified", False):
            return True

        # Check quality score
        quality_score = recipe.get("quality_score", 0)
        if quality_score >= self._policy.minimum_recipe_score:
            return True

        # Check success rate
        success_rate = recipe.get("success_rate", 0)
        if success_rate >= 0.8:
            return True

        # Check if explicitly marked as ship-ready
        if recipe.get("ship_ready", False):
            return True

        return False

    def _is_session_shippable(self, manifest: dict[str, Any]) -> bool:
        """Check if a session is shippable.

        Args:
            manifest: Session manifest

        Returns:
            True if session can be shipped
        """
        # Only ship successful sessions
        if manifest.get("status") != "completed":
            return False

        # Check quality
        quality_score = manifest.get("quality_score", 0)
        if quality_score < self._policy.minimum_ship_score:
            return False

        # Check if explicitly marked
        if manifest.get("ship_ready", False):
            return True

        # Check event count - need meaningful content
        if manifest.get("event_count", 0) < 5:
            return False

        return True

    def _is_repair_shippable(self, pattern: dict[str, Any]) -> bool:
        """Check if a repair pattern is shippable.

        Args:
            pattern: Repair pattern data

        Returns:
            True if pattern can be shipped
        """
        # Check success rate
        success_rate = pattern.get("success_rate", 0)
        if success_rate < 0.7:
            return False

        # Check if reused multiple times
        reuse_count = pattern.get("reuse_count", 0)
        if reuse_count < 2:
            return False

        return True

    def _create_recipe_candidate(self, recipe: dict[str, Any]) -> ShippingCandidate | None:
        """Create a candidate from a recipe.

        Args:
            recipe: Recipe data

        Returns:
            ShippingCandidate or None
        """
        try:
            provenance = ShippingProvenance.from_recipe(recipe)
            return ShippingCandidate(
                source_type=SourceType.VERIFIED_RECIPE.value,
                source_id=recipe.get("recipe_id", ""),
                domain=recipe.get("domain", ""),
                artifact_kind=ArtifactKind.RECIPE_EXPORT.value,
                title=recipe.get("name", "Unnamed Recipe"),
                summary=recipe.get("description", "")[:500],
                content_data=recipe,
                quality_score=recipe.get("quality_score", 0.5),
                confidence=recipe.get("confidence", 0.5),
                verified=recipe.get("verified", False),
                provenance=provenance,
                tags=list(set([recipe.get("domain", ""), "recipe"] + recipe.get("tags", []))),
            )
        except Exception as e:
            logger.warning("Error creating recipe candidate: %s", e)
            return None

    def _create_session_candidate(
        self,
        manifest: dict[str, Any],
        session_dir: Path,
    ) -> ShippingCandidate | None:
        """Create a candidate from a session.

        Args:
            manifest: Session manifest
            session_dir: Session directory path

        Returns:
            ShippingCandidate or None
        """
        try:
            # Load full session data
            events_file = session_dir / "events.jsonl"
            events = []
            if events_file.exists():
                with open(events_file, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            events.append(json.loads(line))

            session_data = {
                **manifest,
                "events": events[:100],  # Limit events
            }

            provenance = ShippingProvenance.from_session(manifest)
            return ShippingCandidate(
                source_type=SourceType.SESSION_SUMMARY.value,
                source_id=manifest.get("session_id", ""),
                domain=manifest.get("domain", ""),
                artifact_kind=ArtifactKind.SESSION_SUMMARY.value,
                title=f"Session: {manifest.get('session_id', 'Unknown')}",
                summary=manifest.get("summary", "")[:500],
                content_data=session_data,
                quality_score=manifest.get("quality_score", 0.5),
                confidence=manifest.get("confidence", 0.5),
                verified=manifest.get("verified", False),
                provenance=provenance,
                tags=[manifest.get("domain", ""), "session"],
            )
        except Exception as e:
            logger.warning("Error creating session candidate: %s", e)
            return None

    def _create_repair_candidate(self, pattern: dict[str, Any]) -> ShippingCandidate | None:
        """Create a candidate from a repair pattern.

        Args:
            pattern: Repair pattern data

        Returns:
            ShippingCandidate or None
        """
        try:
            provenance = ShippingProvenance(
                source_type=SourceType.SUCCESSFUL_REPAIR.value,
                source_id=pattern.get("pattern_id", ""),
                domain=pattern.get("domain", ""),
                evidence_summary=pattern.get("error_type", ""),
            )
            return ShippingCandidate(
                source_type=SourceType.SUCCESSFUL_REPAIR.value,
                source_id=pattern.get("pattern_id", ""),
                domain=pattern.get("domain", ""),
                artifact_kind=ArtifactKind.REPAIR_PATTERN.value,
                title=f"Repair: {pattern.get('error_type', 'Unknown')}",
                summary=pattern.get("description", "")[:500],
                content_data=pattern,
                quality_score=pattern.get("success_rate", 0.7),
                confidence=min(1.0, pattern.get("reuse_count", 1) / 5),
                verified=pattern.get("reuse_count", 0) >= 3,
                provenance=provenance,
                tags=[pattern.get("domain", ""), "repair", pattern.get("error_type", "")],
            )
        except Exception as e:
            logger.warning("Error creating repair candidate: %s", e)
            return None

    def _create_trace_candidate(
        self,
        summary: dict[str, Any],
        trace_id: str,
    ) -> ShippingCandidate | None:
        """Create a candidate from a trace.

        Args:
            summary: Trace summary
            trace_id: Trace ID

        Returns:
            ShippingCandidate or None
        """
        try:
            provenance = ShippingProvenance(
                source_type=SourceType.VALIDATED_TRACE.value,
                source_id=trace_id,
                domain=summary.get("domain", ""),
                evidence_summary=summary.get("task_summary", "")[:200],
            )
            return ShippingCandidate(
                source_type=SourceType.VALIDATED_TRACE.value,
                source_id=trace_id,
                domain=summary.get("domain", ""),
                artifact_kind=ArtifactKind.RUNTIME_TRACE.value,
                title=f"Trace: {trace_id}",
                summary=summary.get("task_summary", "")[:500],
                content_data=summary,
                quality_score=summary.get("quality_score", 0.5),
                confidence=summary.get("confidence", 0.5),
                verified=summary.get("final_outcome") == "success",
                provenance=provenance,
                tags=[summary.get("domain", ""), "trace"],
            )
        except Exception as e:
            logger.warning("Error creating trace candidate: %s", e)
            return None

    def clear_cache(self) -> None:
        """Clear the seen IDs cache."""
        self._seen_ids.clear()


# ------------------------------------------------------------------
# Convenience Functions
# ------------------------------------------------------------------


def collect_shippable_candidates(
    repo_root: Path | str = ".",
    policy: ShippingPolicyConfig | None = None,
    max_candidates: int = 50,
) -> list[ShippingCandidate]:
    """Collect shippable candidates from all sources.

    Args:
        repo_root: Repository root path
        policy: Optional shipping policy
        max_candidates: Maximum candidates to return

    Returns:
        List of ShippingCandidate
    """
    config = CandidateCollectorConfig(
        repo_root=Path(repo_root),
        max_candidates=max_candidates,
    )
    collector = CandidateCollector(config=config, policy=policy)
    result = collector.collect_all()
    return result.candidates


def collect_from_recipes(
    repo_root: Path | str = ".",
    policy: ShippingPolicyConfig | None = None,
) -> list[ShippingCandidate]:
    """Collect candidates from recipes only.

    Args:
        repo_root: Repository root path
        policy: Optional shipping policy

    Returns:
        List of ShippingCandidate from recipes
    """
    config = CandidateCollectorConfig(repo_root=Path(repo_root))
    collector = CandidateCollector(config=config, policy=policy)
    return collector.collect_from_recipes()


def collect_from_sessions(
    repo_root: Path | str = ".",
    policy: ShippingPolicyConfig | None = None,
) -> list[ShippingCandidate]:
    """Collect candidates from sessions only.

    Args:
        repo_root: Repository root path
        policy: Optional shipping policy

    Returns:
        List of ShippingCandidate from sessions
    """
    config = CandidateCollectorConfig(repo_root=Path(repo_root))
    collector = CandidateCollector(config=config, policy=policy)
    return collector.collect_from_sessions()