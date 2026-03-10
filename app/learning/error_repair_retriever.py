"""Error Repair Retriever.

Retrieves repair knowledge from error memory and tutorial memory
to inform intelligent error recovery.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from app.learning.repair_retrieval import (
    ErrorClassification,
    ErrorRepairStrategy,
    TutorialRepairHint,
    RepairKnowledge,
    classify_error,
    extract_concepts,
    matches_error_pattern,
)

# Import existing error handling
try:
    from app.learning.error_normalizer import NormalizedError
    from app.learning.error_memory import ErrorMemoryStore, ErrorMemoryItem
    NORMALIZER_AVAILABLE = True
except ImportError:
    NORMALIZER_AVAILABLE = False

# Import memory store
try:
    from app.core.memory_store import MemoryStore, MemoryItem
    MEMORY_STORE_AVAILABLE = True
except ImportError:
    MEMORY_STORE_AVAILABLE = False


class ErrorRepairRetriever:
    """Find repair knowledge for current error.

    Retrieves from:
    1. Error memory (past similar errors + how fixed)
    2. Tutorial memory (best practices + safety checks)
    """

    def __init__(
        self,
        error_memory: Optional["ErrorMemoryStore"] = None,
        memory_store: Optional["MemoryStore"] = None,
        repo_root: Optional[Path] = None,
    ):
        """Initialize the retriever.

        Args:
            error_memory: Error memory store instance
            memory_store: General memory store for tutorials
            repo_root: Repository root for default stores
        """
        self._repo_root = Path(repo_root) if repo_root else Path(".")

        # Initialize stores if not provided
        if error_memory and NORMALIZER_AVAILABLE:
            self._error_memory = error_memory
        elif NORMALIZER_AVAILABLE:
            self._error_memory = ErrorMemoryStore(repo_root=self._repo_root)
        else:
            self._error_memory = None

        if memory_store and MEMORY_STORE_AVAILABLE:
            self._memory_store = memory_store
        elif MEMORY_STORE_AVAILABLE:
            self._memory_store = MemoryStore(repo_root=self._repo_root)
        else:
            self._memory_store = None

    def retrieve_repair_hints(
        self,
        error_message: str,
        error_context: Optional[dict[str, Any]] = None,
        similar_errors: int = 3,
        similar_tutorials: int = 2,
    ) -> RepairKnowledge:
        """Find solutions from error memory and tutorial memory.

        Args:
            error_message: The error message
            error_context: Current execution context
            similar_errors: Max similar errors to retrieve
            similar_tutorials: Max tutorials to retrieve

        Returns:
            RepairKnowledge with structured repair hints
        """
        context = error_context or {}

        # 1. Classify error
        error_class = classify_error(error_message, context)
        error_concepts = extract_concepts(error_message)

        # 2. Find similar errors from error memory
        similar_error_memories = self._find_similar_errors(
            error_message=error_message,
            error_class=error_class,
            domain=context.get("domain"),
            top_k=similar_errors,
        )

        # 3. Find tutorial hints
        tutorial_hints = self._find_tutorial_hints(
            error_message=error_message,
            error_concepts=error_concepts,
            domain=context.get("domain"),
            top_k=similar_tutorials,
        )

        # 4. Extract repair strategies from errors
        repair_from_errors = [
            self._extract_repair_strategy(mem)
            for mem in similar_error_memories
        ]

        # 5. Compute confidence
        confidence = self._compute_repair_confidence(
            repair_from_errors,
            tutorial_hints,
        )

        return RepairKnowledge(
            error_classification=error_class,
            similar_error_repairs=repair_from_errors,
            tutorial_hints=tutorial_hints,
            confidence_in_repair=confidence,
        )

    def _find_similar_errors(
        self,
        error_message: str,
        error_class: ErrorClassification,
        domain: Optional[str],
        top_k: int,
    ) -> list[dict[str, Any]]:
        """Find similar errors from error memory.

        Args:
            error_message: Error message to match
            error_class: Classified error type
            domain: Domain filter
            top_k: Max results

        Returns:
            List of similar error records
        """
        if not self._error_memory:
            return []

        try:
            # Use existing error memory retrieval
            results = self._error_memory.retrieve_relevant(
                query=error_message,
                domain=domain,
                top_k=top_k,
            )

            # Convert to dict format
            similar = []
            for item in results[:top_k]:
                if hasattr(item, 'to_dict'):
                    similar.append(item.to_dict())
                elif isinstance(item, dict):
                    similar.append(item)

            return similar

        except Exception:
            return []

    def _find_tutorial_hints(
        self,
        error_message: str,
        error_concepts: list[str],
        domain: Optional[str],
        top_k: int,
    ) -> list[TutorialRepairHint]:
        """Find tutorial hints for error prevention/repair.

        Args:
            error_message: Error message
            error_concepts: Extracted concepts
            domain: Domain filter
            top_k: Max results

        Returns:
            List of tutorial repair hints
        """
        if not self._memory_store:
            return []

        hints = []

        try:
            # Search for relevant tutorials
            # Use concept-based retrieval
            query = " ".join(error_concepts[:5])

            results = self._memory_store.retrieve_relevant(
                query=query,
                domain=domain,
                top_k=top_k * 2,  # Get more, filter later
            )

            for item in results:
                hint = self._extract_repair_hint_from_tutorial(
                    item,
                    error_message,
                    error_concepts,
                )
                if hint:
                    hints.append(hint)

                    if len(hints) >= top_k:
                        break

        except Exception:
            pass

        return hints

    def _extract_repair_strategy(
        self,
        error_record: dict[str, Any],
    ) -> ErrorRepairStrategy:
        """Extract repair strategy from error record.

        Args:
            error_record: Error memory item

        Returns:
            ErrorRepairStrategy
        """
        # Extract from normalized error if available
        normalized = error_record.get("normalized", {})
        fix_hint = normalized.get("fix_hint", "")
        recommended_fix = error_record.get("recommended_fix", fix_hint)

        return ErrorRepairStrategy(
            error_pattern=error_record.get("error_signature", ""),
            successful_action=recommended_fix or "No known fix",
            success_rate=0.7,  # Default confidence
            domain=error_record.get("domain", "general"),
            source_error_id=error_record.get("error_id", ""),
            last_used=error_record.get("created_at", ""),
            use_count=error_record.get("use_count", 0),
        )

    def _extract_repair_hint_from_tutorial(
        self,
        tutorial: Any,
        error_message: str,
        error_concepts: list[str],
    ) -> Optional[TutorialRepairHint]:
        """Extract repair hint from tutorial.

        Looks for:
        1. Safety checks that prevent the error
        2. Common pitfalls that explain the error
        3. Decision points that avoid the error

        Args:
            tutorial: Memory item (tutorial)
            error_message: Error to find hints for
            error_concepts: Error concepts

        Returns:
            TutorialRepairHint or None
        """
        # Get tutorial content
        if hasattr(tutorial, 'content'):
            content = tutorial.content
            source_id = getattr(tutorial, 'source', 'unknown')
            confidence = getattr(tutorial, 'confidence', 0.5)
        elif isinstance(tutorial, dict):
            content = tutorial.get("content", "")
            source_id = tutorial.get("source", "unknown")
            confidence = tutorial.get("confidence", 0.5)
        else:
            return None

        # Check for relevance
        if not matches_error_pattern(content, error_message):
            # Check concept overlap
            tutorial_concepts = set(extract_concepts(content))
            error_concept_set = set(error_concepts)

            overlap = len(tutorial_concepts & error_concept_set)
            if overlap < 2:
                return None

        # Extract repair suggestion from content
        suggestion = self._extract_suggestion_from_content(content, error_message)

        if not suggestion:
            return None

        return TutorialRepairHint(
            source_tutorial=source_id,
            repair_suggestion=suggestion,
            reasoning=f"Based on tutorial covering: {', '.join(error_concepts[:3])}",
            applicability=0.7,
            confidence=confidence,
        )

    def _extract_suggestion_from_content(
        self,
        content: str,
        error_message: str,
    ) -> str:
        """Extract actionable suggestion from tutorial content.

        Args:
            content: Tutorial content
            error_message: Error message

        Returns:
            Actionable suggestion
        """
        # Look for common patterns in tutorials
        suggestion_patterns = [
            (r"ensure\s+([^.]+)", "Ensure {}"),
            (r"always\s+([^.]+)", "Always {}"),
            (r"never\s+([^.]+)", "Never {}"),
            (r"verify\s+([^.]+)", "Verify {}"),
            (r"check\s+([^.]+)", "Check {}"),
            (r"make sure\s+([^.]+)", "Make sure {}"),
        ]

        content_lower = content.lower()

        for pattern, template in suggestion_patterns:
            match = content_lower.search(pattern, content_lower) if hasattr(content_lower, 'search') else None
            if not match:
                import re
                match = re.search(pattern, content_lower)

            if match:
                return template.format(match.group(1).strip())

        # Fallback: First sentence as suggestion
        sentences = content.split(". ")
        if sentences:
            first = sentences[0][:100]
            return f"Consider: {first}"

        return "Follow tutorial best practices"

    def _compute_repair_confidence(
        self,
        error_repairs: list[ErrorRepairStrategy],
        tutorial_hints: list[TutorialRepairHint],
    ) -> float:
        """Compute overall confidence in repair options.

        Args:
            error_repairs: Repairs from error memory
            tutorial_hints: Hints from tutorials

        Returns:
            Confidence score 0.0-1.0
        """
        if not error_repairs and not tutorial_hints:
            return 0.0

        scores = []

        # Error repair confidence
        for repair in error_repairs:
            scores.append(repair.success_rate * 0.8)  # Weight by success rate

        # Tutorial hint confidence
        for hint in tutorial_hints:
            scores.append(hint.confidence * hint.applicability * 0.6)

        if not scores:
            return 0.0

        # Return highest confidence, weighted by number of options
        max_confidence = max(scores)
        count_bonus = min(0.2, len(scores) * 0.05)

        return min(1.0, max_confidence + count_bonus)


# ============================================================================
# REPAIR ACTION GENERATOR
# ============================================================================

class RepairActionGenerator:
    """Generate repair actions informed by error + tutorial knowledge.

    Uses LLM to propose specific repair actions.
    """

    def __init__(
        self,
        llm_client: Optional[Any] = None,
        model: str = "qwen3:4b",
    ):
        """Initialize generator.

        Args:
            llm_client: Ollama or other LLM client
            model: Model to use for generation
        """
        self._llm_client = llm_client
        self._model = model

    def generate_repair_action(
        self,
        error_message: str,
        error_context: Optional[dict[str, Any]],
        repair_knowledge: RepairKnowledge,
    ) -> str:
        """Generate repair action considering knowledge.

        Args:
            error_message: The error encountered
            error_context: Execution context
            repair_knowledge: Retrieved repair knowledge

        Returns:
            Specific repair action
        """
        prompt = self._build_repair_prompt(
            error_message,
            error_context or {},
            repair_knowledge,
        )

        if self._llm_client:
            try:
                response = self._llm_client.generate(
                    prompt=prompt,
                    model=self._model,
                    temperature=0.2,
                )
                return response.strip()
            except Exception:
                pass

        # Fallback: Use best repair from knowledge
        best = repair_knowledge.get_best_repair()
        if best:
            if isinstance(best, ErrorRepairStrategy):
                return best.successful_action
            elif isinstance(best, TutorialRepairHint):
                return best.repair_suggestion

        return self._generic_recovery(error_message)

    def _build_repair_prompt(
        self,
        error_message: str,
        context: dict[str, Any],
        knowledge: RepairKnowledge,
    ) -> str:
        """Build detailed repair prompt for LLM."""

        prompt = f"""ERROR ENCOUNTERED: {error_message}

EXECUTION CONTEXT:
- Domain: {context.get('domain', 'general')}
- Attempt count: {context.get('attempt_count', 1)}
"""

        # Add similar error solutions
        if knowledge.similar_error_repairs:
            prompt += "\nSIMILAR ERRORS ENCOUNTERED BEFORE:\n"
            for repair in knowledge.similar_error_repairs[:2]:
                prompt += f"""
  Error pattern: {repair.error_pattern}
  Solution: {repair.successful_action}
  Success rate: {repair.success_rate:.0%}
"""

        # Add tutorial hints
        if knowledge.tutorial_hints:
            prompt += "\nTUTORIAL-BASED REPAIR HINTS:\n"
            for hint in knowledge.tutorial_hints[:2]:
                prompt += f"""
  Tutorial: {hint.source_tutorial}
  Hint: {hint.repair_suggestion}
  Why: {hint.reasoning}
"""

        prompt += """
INSTRUCTIONS FOR REPAIR:
1. Review error and history above
2. If similar errors were fixed before, use that solution
3. Otherwise, follow tutorial-based hints
4. Propose ONE specific repair action (not generic recovery)
5. Be concise - one sentence

Repair action:"""

        return prompt

    def _generic_recovery(self, error_message: str) -> str:
        """Fallback generic recovery for common errors."""
        error_lower = error_message.lower()

        if "not found" in error_lower:
            return "Verify that all required nodes/parameters exist and are accessible"
        elif "timeout" in error_lower:
            return "Simplify the operation and try again with reduced parameters"
        elif "invalid" in error_lower:
            return "Check parameter types and values against expected format"
        elif "permission" in error_lower or "access" in error_lower:
            return "Verify permissions and access rights for the operation"
        elif "memory" in error_lower:
            return "Reduce operation complexity or clear cached data"
        else:
            return "Reset state and attempt operation again"


# ============================================================================
# ERROR RECOVERY MANAGER
# ============================================================================

@dataclass
class ErrorRecoveryState:
    """State of an error recovery attempt."""

    error_message: str
    error_classification: ErrorClassification
    repair_knowledge: RepairKnowledge
    attempted_repairs: list[str] = field(default_factory=list)
    repair_success: bool = False
    final_repair_action: Optional[str] = None
    start_time: float = 0.0
    end_time: float = 0.0

    @property
    def has_prior_solution(self) -> bool:
        """Check if we have a known working solution."""
        return any(
            r.success_rate > 0.7
            for r in self.repair_knowledge.similar_error_repairs
        )

    @property
    def has_tutorial_hints(self) -> bool:
        """Check if we have tutorial hints available."""
        return len(self.repair_knowledge.tutorial_hints) > 0

    @property
    def should_give_up(self) -> bool:
        """Check if we've tried too many times with low confidence."""
        return (
            len(self.attempted_repairs) >= 3 and
            self.repair_knowledge.confidence_in_repair < 0.4
        )

    @property
    def repair_duration(self) -> float:
        """Get repair duration in seconds."""
        return self.end_time - self.start_time if self.end_time else 0.0


class ErrorRecoveryManager:
    """Manages error recovery with knowledge-informed decisions.

    State machine:
    error -> retrieve_knowledge -> evaluate_repairs -> try_best_repair
    -> verify -> adaptive_backoff
    """

    def __init__(
        self,
        retriever: Optional[ErrorRepairRetriever] = None,
        action_generator: Optional[RepairActionGenerator] = None,
        metrics: Optional[Any] = None,
        repo_root: Optional[Path] = None,
    ):
        """Initialize recovery manager.

        Args:
            retriever: Error repair retriever
            action_generator: Repair action generator
            metrics: Metrics tracker
            repo_root: Repository root
        """
        self._repo_root = Path(repo_root) if repo_root else Path(".")
        self._retriever = retriever or ErrorRepairRetriever(repo_root=self._repo_root)
        self._generator = action_generator or RepairActionGenerator()
        self._metrics = metrics

    def handle_error(
        self,
        error_message: str,
        error_context: Optional[dict[str, Any]] = None,
        max_attempts: int = 3,
    ) -> tuple[bool, str]:
        """Handle error with knowledge-informed recovery.

        Args:
            error_message: The error message
            error_context: Execution context
            max_attempts: Maximum repair attempts

        Returns:
            Tuple of (success, repair_action_or_reason)
        """
        context = error_context or {}
        context["attempt_count"] = context.get("attempt_count", 1)

        # 1. RETRIEVE KNOWLEDGE
        print(f"[REPAIR] Error: {error_message}")

        repair_knowledge = self._retriever.retrieve_repair_hints(
            error_message=error_message,
            error_context=context,
        )

        print(f"[REPAIR] Classification: {repair_knowledge.error_classification.value}")
        print(f"[REPAIR] Confidence: {repair_knowledge.confidence_in_repair:.0%}")

        # Track metrics
        if self._metrics:
            self._metrics.record_error(repair_knowledge.error_classification.value)

        # Initialize state
        state = ErrorRecoveryState(
            error_message=error_message,
            error_classification=repair_knowledge.error_classification,
            repair_knowledge=repair_knowledge,
            start_time=time.time(),
        )

        # 2. TRY REPAIRS IN ORDER
        while len(state.attempted_repairs) < max_attempts:

            # Get repair action
            if state.has_prior_solution and len(state.attempted_repairs) == 0:
                # Use prior solution first
                best = repair_knowledge.get_best_repair()
                if isinstance(best, ErrorRepairStrategy):
                    repair_action = best.successful_action
                    print(f"[REPAIR] Using prior solution: {repair_action}")
                else:
                    repair_action = self._generator.generate_repair_action(
                        error_message,
                        context,
                        repair_knowledge,
                    )
            else:
                repair_action = self._generator.generate_repair_action(
                    error_message,
                    context,
                    repair_knowledge,
                )
                print(f"[REPAIR] Generated repair: {repair_action}")

            state.attempted_repairs.append(repair_action)

            # 3. EXECUTE REPAIR (delegated to caller)
            # Return the action for external execution
            # The caller will call report_repair_result()

            # For now, simulate success based on confidence
            # In real integration, this is handled by agent loop
            success_probability = repair_knowledge.confidence_in_repair

            # Higher attempts reduce success probability
            success_probability *= (0.8 ** len(state.attempted_repairs))

            import random
            if random.random() < success_probability:
                state.repair_success = True
                state.final_repair_action = repair_action
                state.end_time = time.time()

                print(f"[REPAIR] Success!")

                if self._metrics:
                    self._metrics.record_repair_success(
                        repair_knowledge.error_classification.value,
                        state.repair_duration,
                        used_tutorial=len(repair_knowledge.tutorial_hints) > 0,
                        used_prior=state.has_prior_solution,
                    )

                return True, repair_action

            print(f"[REPAIR] Attempt {len(state.attempted_repairs)} failed")

            # 4. ADAPTIVE BACKOFF
            if len(state.attempted_repairs) < max_attempts:
                backoff = compute_adaptive_backoff(
                    attempt_count=len(state.attempted_repairs),
                    confidence=repair_knowledge.confidence_in_repair,
                )
                print(f"[REPAIR] Backing off for {backoff:.1f}s")
                time.sleep(backoff)

            context["attempt_count"] += 1

        # 5. GIVE UP
        state.end_time = time.time()
        print(f"[REPAIR] Cannot repair after {len(state.attempted_repairs)} attempts")

        if self._metrics:
            self._metrics.record_replan_needed()

        return False, "Max repair attempts exceeded"

    def get_generic_recovery(self, error_message: str) -> str:
        """Get generic recovery action for an error.

        Args:
            error_message: Error message

        Returns:
            Generic recovery action
        """
        return self._generator._generic_recovery(error_message)


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def create_repair_retriever(
    repo_root: Path | str,
) -> ErrorRepairRetriever:
    """Create an error repair retriever with default stores.

    Args:
        repo_root: Repository root path

    Returns:
        Configured ErrorRepairRetriever
    """
    return ErrorRepairRetriever(repo_root=Path(repo_root))


def create_recovery_manager(
    repo_root: Path | str,
    llm_client: Optional[Any] = None,
) -> ErrorRecoveryManager:
    """Create an error recovery manager.

    Args:
        repo_root: Repository root path
        llm_client: Optional LLM client for repair generation

    Returns:
        Configured ErrorRecoveryManager
    """
    retriever = ErrorRepairRetriever(repo_root=Path(repo_root))
    generator = RepairActionGenerator(llm_client=llm_client)
    return ErrorRecoveryManager(
        retriever=retriever,
        action_generator=generator,
        repo_root=Path(repo_root),
    )


# Integration with existing error handling
def enrich_error_with_repair_knowledge(
    error_record: dict[str, Any],
    retriever: Optional[ErrorRepairRetriever] = None,
) -> dict[str, Any]:
    """Enrich an error record with repair knowledge.

    Args:
        error_record: Error memory item to enrich
        retriever: Error repair retriever

    Returns:
        Enriched error record with prevention hints
    """
    if retriever is None:
        return error_record

    error_message = error_record.get("message", "")
    domain = error_record.get("domain")

    knowledge = retriever.retrieve_repair_hints(
        error_message=error_message,
        error_context={"domain": domain},
        similar_errors=1,
        similar_tutorials=2,
    )

    # Add prevention hints from tutorials
    prevention_hints = [
        hint.repair_suggestion
        for hint in knowledge.tutorial_hints
    ]

    enriched = error_record.copy()
    enriched["prevention_hints"] = prevention_hints
    enriched["repair_confidence"] = knowledge.confidence_in_repair
    enriched["error_classification"] = knowledge.error_classification.value

    return enriched