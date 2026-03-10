"""Knowledge Store with Validation Integration.

Wraps the distilled knowledge indexing with validation pipeline,
ensuring only validated knowledge is indexed for RAG retrieval.

Provides:
- KnowledgeStoreWithValidation: Main store with validation integration
- ValidatedKnowledge: Container for validated knowledge
- Validation-aware CRUD operations
"""

from __future__ import annotations

__all__ = [
    "KnowledgeStoreWithValidation",
    "ValidatedKnowledge",
    "KnowledgeStoreConfig",
    "create_validated_store",
]

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.core.distilled_indexer import (
    RAGDocument,
    build_distilled_chunks,
    index_recipe,
    index_recipes,
)
from app.core.rag_models import RagChunk

if TYPE_CHECKING:
    from app.validation import (
        QualityThresholds,
        ValidationConfig,
        ValidationDecision,
        ValidationPipeline,
        ValidationResult,
    )

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class KnowledgeStoreConfig:
    """Configuration for the validated knowledge store."""

    # Validation settings
    auto_validate: bool = True
    reject_on_validation_failure: bool = True
    store_rejected: bool = False  # Keep rejected items for review

    # Quality thresholds
    min_confidence_for_index: float = 0.6
    min_completeness_for_index: float = 0.7

    # Storage paths
    recipes_dir: Path | None = None
    rejected_dir: Path | None = None

    # Indexing settings
    auto_index: bool = True  # Auto-index validated items
    boost_scores: dict[str, float] | None = None


@dataclass(slots=True)
class ValidatedKnowledge:
    """Container for a validated knowledge item."""

    knowledge_id: str
    knowledge_type: str  # "recipe", "repair_hint", "verification_hint"
    data: dict[str, Any]
    validation_result: ValidationResult  # type: ignore[valid-type]
    rag_chunks: list[RagChunk] = field(default_factory=list)
    indexed: bool = False
    indexed_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "knowledge_id": self.knowledge_id,
            "knowledge_type": self.knowledge_type,
            "data": self.data,
            "validation_result": self.validation_result.to_dict(),
            "rag_chunks": [c.to_dict() for c in self.rag_chunks],
            "indexed": self.indexed,
            "indexed_at": self.indexed_at,
        }


class KnowledgeStoreWithValidation:
    """Knowledge store with integrated validation pipeline.

    This class wraps the distilled knowledge indexing with validation,
    ensuring only validated knowledge is indexed for RAG retrieval.

    Usage:
        store = KnowledgeStoreWithValidation(
            recipes_dir=Path("recipes"),
            config=KnowledgeStoreConfig(auto_validate=True),
        )

        # Add a recipe
        result = store.add_recipe(recipe_data)
        if result.validation_result.is_acceptable:
            print("Recipe validated and indexed")

        # Get validated recipes
        recipes = store.get_validated_recipes()

        # Get RAG chunks for indexing
        chunks = store.get_rag_chunks()
    """

    def __init__(
        self,
        config: KnowledgeStoreConfig | None = None,
        validation_config: ValidationConfig | None = None,  # type: ignore[valid-type]
    ):
        """Initialize the knowledge store.

        Args:
            config: Store configuration
            validation_config: Validation pipeline configuration
        """
        from app.validation import ValidationConfig, ValidationPipeline

        self._config = config or KnowledgeStoreConfig()
        self._validation_config = validation_config or ValidationConfig()
        self._pipeline = ValidationPipeline(config=self._validation_config)

        # In-memory stores
        self._validated: dict[str, ValidatedKnowledge] = {}
        self._rejected: dict[str, ValidatedKnowledge] = {}
        self._pending_review: dict[str, ValidatedKnowledge] = {}

        # RAG chunks cache
        self._rag_chunks: list[RagChunk] = []

        # Load existing if paths provided
        if self._config.recipes_dir:
            self._load_existing_recipes()

    def add_recipe(
        self,
        recipe: dict[str, Any],
        skip_validation: bool = False,
    ) -> ValidatedKnowledge:
        """Add a recipe to the store.

        Args:
            recipe: Recipe data
            skip_validation: Skip validation (use with caution)

        Returns:
            ValidatedKnowledge with validation result
        """
        from app.validation import ValidationDecision, ValidationResult

        recipe_id = recipe.get("recipe_id", self._generate_id())

        # Validate if enabled
        if self._config.auto_validate and not skip_validation:
            validation_result = self._pipeline.validate(recipe)
        else:
            # Create a default ACCEPT result
            validation_result = ValidationResult(
                item_id=recipe_id,
                item_type="recipe",
                decision=ValidationDecision.ACCEPT,
                confidence=1.0,
                schema_valid=True,
                validated_at=datetime.now(timezone.utc).isoformat(),
            )

        # Create validated knowledge
        knowledge = ValidatedKnowledge(
            knowledge_id=recipe_id,
            knowledge_type="recipe",
            data=recipe,
            validation_result=validation_result,
        )

        # Route based on decision
        if validation_result.decision == ValidationDecision.ACCEPT:
            self._validated[recipe_id] = knowledge

            # Auto-index if enabled
            if self._config.auto_index:
                self._index_knowledge(knowledge)

            # Add to pipeline for future contradiction detection
            self._pipeline.add_existing_recipe(recipe)

        elif validation_result.decision == ValidationDecision.REVIEW:
            self._pending_review[recipe_id] = knowledge

        elif validation_result.decision == ValidationDecision.REJECT:
            if self._config.store_rejected:
                self._rejected[recipe_id] = knowledge

        return knowledge

    def add_recipes_batch(
        self,
        recipes: list[dict[str, Any]],
    ) -> list[ValidatedKnowledge]:
        """Add multiple recipes to the store.

        Args:
            recipes: List of recipe data

        Returns:
            List of ValidatedKnowledge results
        """
        results: list[ValidatedKnowledge] = []

        for recipe in recipes:
            result = self.add_recipe(recipe)
            results.append(result)

        return results

    def get_validated_recipes(self) -> list[dict[str, Any]]:
        """Get all validated recipes.

        Returns:
            List of validated recipe data
        """
        return [k.data for k in self._validated.values()]

    def get_pending_review(self) -> list[ValidatedKnowledge]:
        """Get items pending human review.

        Returns:
            List of items with REVIEW decision
        """
        return list(self._pending_review.values())

    def get_rejected(self) -> list[ValidatedKnowledge]:
        """Get rejected items.

        Returns:
            List of items with REJECT decision
        """
        return list(self._rejected.values())

    def get_rag_chunks(self) -> list[RagChunk]:
        """Get all RAG chunks from validated knowledge.

        Returns:
            List of RagChunks ready for indexing
        """
        return self._rag_chunks

    def get_recipe(self, recipe_id: str) -> ValidatedKnowledge | None:
        """Get a specific recipe by ID.

        Args:
            recipe_id: Recipe ID

        Returns:
            ValidatedKnowledge or None
        """
        return self._validated.get(recipe_id) or self._pending_review.get(recipe_id)

    def update_recipe(
        self,
        recipe_id: str,
        updates: dict[str, Any],
    ) -> ValidatedKnowledge | None:
        """Update a recipe and re-validate.

        Args:
            recipe_id: Recipe ID to update
            updates: Fields to update

        Returns:
            Updated ValidatedKnowledge or None
        """
        existing = self.get_recipe(recipe_id)
        if existing is None:
            return None

        # Merge updates
        updated_data = {**existing.data, **updates}
        updated_data["updated_at"] = datetime.now(timezone.utc).isoformat()

        # Re-add (which triggers re-validation)
        return self.add_recipe(updated_data)

    def accept_review(
        self,
        recipe_id: str,
        notes: str = "",
    ) -> ValidatedKnowledge | None:
        """Accept an item pending review.

        Args:
            recipe_id: Recipe ID
            notes: Optional acceptance notes

        Returns:
            Updated ValidatedKnowledge or None
        """
        from app.validation import ValidationDecision, ValidationResult

        pending = self._pending_review.pop(recipe_id, None)
        if pending is None:
            return None

        # Create new ACCEPT result
        pending.validation_result = ValidationResult(
            item_id=recipe_id,
            item_type="recipe",
            decision=ValidationDecision.ACCEPT,
            confidence=0.9,  # Human-verified
            schema_valid=True,
            suggestions=[f"Human accepted: {notes}"] if notes else [],
            validated_at=datetime.now(timezone.utc).isoformat(),
        )

        # Move to validated
        self._validated[recipe_id] = pending

        # Index if enabled
        if self._config.auto_index:
            self._index_knowledge(pending)

        return pending

    def reject_review(
        self,
        recipe_id: str,
        reason: str,
    ) -> ValidatedKnowledge | None:
        """Reject an item pending review.

        Args:
            recipe_id: Recipe ID
            reason: Rejection reason

        Returns:
            Updated ValidatedKnowledge or None
        """
        from app.validation import ValidationDecision, ValidationResult

        pending = self._pending_review.pop(recipe_id, None)
        if pending is None:
            return None

        # Create new REJECT result
        pending.validation_result = ValidationResult(
            item_id=recipe_id,
            item_type="recipe",
            decision=ValidationDecision.REJECT,
            confidence=1.0,
            errors=[f"Human rejected: {reason}"],
            validated_at=datetime.now(timezone.utc).isoformat(),
        )

        # Move to rejected
        if self._config.store_rejected:
            self._rejected[recipe_id] = pending

        return pending

    def remove_recipe(self, recipe_id: str) -> bool:
        """Remove a recipe from the store.

        Args:
            recipe_id: Recipe ID

        Returns:
            True if removed, False if not found
        """
        removed = False

        if recipe_id in self._validated:
            del self._validated[recipe_id]
            removed = True

        if recipe_id in self._pending_review:
            del self._pending_review[recipe_id]
            removed = True

        if recipe_id in self._rejected:
            del self._rejected[recipe_id]
            removed = True

        if removed:
            # Rebuild RAG chunks
            self._rebuild_rag_chunks()

        return removed

    def get_stats(self) -> dict[str, Any]:
        """Get store statistics.

        Returns:
            Statistics dictionary
        """
        return {
            "validated_count": len(self._validated),
            "pending_review_count": len(self._pending_review),
            "rejected_count": len(self._rejected),
            "rag_chunks_count": len(self._rag_chunks),
            "auto_validate": self._config.auto_validate,
            "auto_index": self._config.auto_index,
        }

    def _index_knowledge(self, knowledge: ValidatedKnowledge) -> None:
        """Index validated knowledge for RAG."""
        if knowledge.knowledge_type == "recipe":
            # Build RAG documents
            docs = index_recipe(knowledge.data, self._config.boost_scores)

            # Convert to chunks
            chunks = [doc.to_rag_chunk() for doc in docs]
            knowledge.rag_chunks = chunks
            knowledge.indexed = True
            knowledge.indexed_at = datetime.now(timezone.utc).isoformat()

            # Add to cache
            self._rag_chunks.extend(chunks)

            logger.debug(
                "Indexed recipe %s: %d chunks",
                knowledge.knowledge_id,
                len(chunks),
            )

    def _rebuild_rag_chunks(self) -> None:
        """Rebuild RAG chunks from all validated knowledge."""
        self._rag_chunks = []

        for knowledge in self._validated.values():
            if knowledge.indexed and knowledge.rag_chunks:
                self._rag_chunks.extend(knowledge.rag_chunks)
            elif knowledge.indexed:
                self._index_knowledge(knowledge)

    def _load_existing_recipes(self) -> None:
        """Load existing recipes from configured directory."""
        from app.core.distilled_indexer import load_recipes_from_dir

        recipes_dir = self._config.recipes_dir
        if recipes_dir is None or not recipes_dir.exists():
            return

        recipes = load_recipes_from_dir(recipes_dir)
        logger.info("Loaded %d existing recipes from %s", len(recipes), recipes_dir)

        # Add without re-indexing initially
        for recipe in recipes:
            self.add_recipe(recipe)

    def _generate_id(self) -> str:
        """Generate a unique ID."""
        import uuid
        return f"recipe_{uuid.uuid4().hex[:12]}"


def create_validated_store(
    recipes_dir: Path | str | None = None,
    auto_validate: bool = True,
    auto_index: bool = True,
    min_confidence: float = 0.7,
    min_completeness: float = 0.8,
) -> KnowledgeStoreWithValidation:
    """Create a validated knowledge store with common settings.

    Args:
        recipes_dir: Optional directory for existing recipes
        auto_validate: Enable automatic validation
        auto_index: Enable automatic RAG indexing
        min_confidence: Minimum confidence threshold
        min_completeness: Minimum completeness threshold

    Returns:
        Configured KnowledgeStoreWithValidation
    """
    from app.validation import QualityThresholds, ValidationConfig

    config = KnowledgeStoreConfig(
        auto_validate=auto_validate,
        auto_index=auto_index,
        recipes_dir=Path(recipes_dir) if recipes_dir else None,
        min_confidence_for_index=min_confidence,
        min_completeness_for_index=min_completeness,
    )

    validation_config = ValidationConfig(
        quality_thresholds=QualityThresholds(
            min_confidence=min_confidence,
            min_completeness=min_completeness,
        ),
    )

    return KnowledgeStoreWithValidation(
        config=config,
        validation_config=validation_config,
    )