"""Domain-aware runtime inference with local-first provider routing, cache, and memory reuse.

This module provides the run_task() function that serves as a high-level
wrapper around the InferenceOrchestrator, adding:
- Domain-specific system prompts
- Memory context injection
- RAG context injection
- Success/failure pattern recording

All inference calls route through InferenceOrchestrator which enforces
local-first defaults with Ollama as the preferred provider.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from app.core.memory_store import MemoryStore, build_default_memory_store
from app.core.ollama_client import OllamaClient, OllamaUnavailableError
from app.core.prompt_cache import PromptCache, PromptCacheKeyParts, build_default_prompt_cache
from app.core.provider_router import ProviderRouter
from app.core.task_router import TaskRouter
from app.core.token_budget import TokenBudget, build_default_token_budget
from app.learning.error_memory import ErrorMemoryStore, build_default_error_memory_store
from app.learning.success_patterns import SuccessPatternStore, build_default_success_pattern_store

# Unified inference orchestrator (local-first default)
from app.core.inference_orchestrator import (
    InferenceOrchestrator,
    InferenceResult,
    InferenceContext,
    build_default_orchestrator,
    get_global_orchestrator,
)

# Memory runtime integration
from app.core.memory_runtime import (
    RuntimeMemoryContext,
    build_runtime_memory_context,
    inject_memory_into_prompt,
    promote_success_to_pattern,
    record_failure_for_avoidance,
    get_memory_influence_summary,
)

_REPO = Path(__file__).resolve().parents[2]


logger = logging.getLogger(__name__)

_DEFAULT_REASONING_MODEL = "qwen3:14b"
_DEFAULT_VISION_MODEL = "qwen3-vl:30b"
_MAX_QUERY_CHARS = 1800
_MAX_SYSTEM_CHARS = 2200


# Session recording helpers
def _record_session_event(event_type: str, payload: dict) -> None:
    """Record event to active session if one exists."""
    try:
        from app.recording.session_runtime import record_runtime_event
        record_runtime_event(_REPO, event_type, payload)
    except Exception as exc:
        logger.debug("Session recording skipped: %s", exc)


@dataclass(slots=True)
class TaskResult:
    """Result of a routed inference call."""

    query: str
    domain: str
    role: str
    model: str
    response: str
    provider: str
    decision_reason: str
    cache_hit: bool = False
    remote_allowed: bool = False
    metadata: dict[str, object] = field(default_factory=dict)
    error: str = ""
    # Enhanced routing metadata
    selected_provider: str = ""
    provider_strategy: str = "local_first"
    attempted_providers: tuple[str, ...] = ()
    local_first_applied: bool = True
    fallback_used: bool = False
    route_reason: str = ""
    provider_error_summary: str = ""

    @property
    def ok(self) -> bool:
        return self.error == ""


def _build_td_system_prompt() -> str:
    from app.domains.touchdesigner.td_knowledge import build_default_td_knowledge
    from app.domains.touchdesigner.td_tasks import build_td_task_catalog

    kb = build_default_td_knowledge()
    catalog = build_td_task_catalog()

    family_lines = "\n".join(f"- {kb.describe_family(code)}" for code in kb.list_family_codes())
    task_lines = "\n".join(f"- {t.title}: {t.goal}" for t in catalog.tasks.values())
    return f"""You are a TouchDesigner specialist assistant. Be concise, exact, and practical.
Use exact operator names, network structure, and parameter names when relevant.
Avoid filler.

Operator families:
{family_lines}

Known task patterns:
{task_lines}
"""


def _build_houdini_system_prompt() -> str:
    from app.domains.houdini.houdini_knowledge import build_default_houdini_knowledge

    kb = build_default_houdini_knowledge()
    context_lines = "\n".join(f"- {kb.describe_context(code)}" for code in kb.list_context_codes())
    concept_lines = "\n".join(f"- {note.key}: {note.summary}" for note in kb.concept_notes.values())
    return f"""You are a Houdini Senior Technical Director.
Use exact node names, parameter names, solver details, and VEX/Python syntax when relevant.
If unsure, say so briefly.
Avoid filler.

Network contexts:
{context_lines}

Key concepts:
{concept_lines}
"""


def _build_general_system_prompt() -> str:
    return "You are a local-first technical assistant. Be concise, practical, and honest."


def _get_system_prompt(domain: str) -> str:
    if domain == "touchdesigner":
        return _build_td_system_prompt()
    if domain == "houdini":
        return _build_houdini_system_prompt()
    return _build_general_system_prompt()


def _inject_rag_context(system: str, query: str, domain: str) -> str:
    try:
        from app.core.rag_context_builder import build_context

        bundle = build_context(query, domain=domain, max_chunks=2, max_chars_per_chunk=220)
        if bundle.context_text:
            return system + "\n\n" + bundle.context_text
    except Exception as exc:
        logger.debug("RAG context injection skipped: %s", exc)
    return system


def _inject_memory_context(system: str, query: str, domain: str, memory: MemoryStore) -> str:
    """Retrieve top relevant memory items and prepend them to the system prompt."""
    try:
        memory.load()
        # Search long_term for relevant patterns
        hits = memory.search(query=query, domain=domain, bucket="long_term")[:3]
        if not hits:
            hits = memory.recent(3, bucket="long_term")
        if hits:
            # Record memory retrieval to active session
            _record_session_event("memory_retrieved", {
                "count": len(hits),
                "source": "long_term",
                "domain": domain,
            })
        if not hits:
            return system
        # Compact snippet for prompt injection
        snippet = "\n".join(
            f"- [{h.domain}] {h.content[:150]}" for h in hits
        )[:300]
        return system + f"\n\nPast relevant patterns (local memory):\n{snippet}"
    except Exception as exc:
        logger.debug("Memory context injection skipped: %s", exc)
    return system


def _inject_feedback_loop_context(
    system: str,
    query: str,
    domain: str,
    error_memory: ErrorMemoryStore | None = None,
    pattern_store: SuccessPatternStore | None = None,
) -> str:
    """Inject error memory and success patterns into system prompt.

    Retrieves relevant past errors and successful repair patterns
    to help the model avoid known issues and apply proven fixes.
    """
    try:
        snippets: list[str] = []

        # Get relevant error memory
        if error_memory is None:
            error_memory = build_default_error_memory_store(_REPO)

        similar_errors = error_memory.retrieve_relevant(
            domain=domain,
            task_id="",
            query=query,
            max_items=2,
        )
        if similar_errors:
            error_snippet = "\n".join(
                f"- [{e.error_type}] {e.message[:100]}: fix={e.recommended_fix[:80]}"
                for e in similar_errors
            )
            snippets.append(f"Known issues to avoid:\n{error_snippet}")

        # Get relevant success patterns
        if pattern_store is None:
            pattern_store = build_default_success_pattern_store(_REPO)

        patterns = pattern_store.search(
            domain=domain,
            query=query,
        )
        if patterns:
            pattern_snippet = "\n".join(
                f"- [{p.error_type}] {p.fix_description[:100]}"
                for p in patterns[:2]
            )
            snippets.append(f"Repair patterns:\n{pattern_snippet}")

        if snippets:
            return system + "\n\n" + "\n\n".join(snippets)
    except Exception as exc:
        logger.debug("Feedback loop context injection skipped: %s", exc)
    return system


def _promote_to_memory(
    memory: MemoryStore,
    query: str,
    response: str,
    domain: str,
    task_class: str,
    provider: str,
) -> None:
    """Store a successful inference result to memory.

    - Always write to short_term
    - Promote to long_term if domain is TD/Houdini and response is useful
    """
    try:
        content = f"Q: {query[:250]}\nA: {response[:350]}"

        # Always add to short_term
        memory.add(
            content=content,
            tags=(task_class, provider, "run_task"),
            domain=domain,
            source="run_task",
            bucket="short_term",
        )

        # Promote to long_term for domain-relevant content
        if domain in {"touchdesigner", "houdini"} and len(response) > 20:
            memory.add(
                content=content,
                tags=(task_class, provider, "run_task"),
                domain=domain,
                source="run_task",
                bucket="long_term",
            )
    except Exception as exc:
        logger.debug("Memory promotion failed: %s", exc)


def _record_error_to_memory(
    error_memory: ErrorMemoryStore,
    query: str,
    domain: str,
    error_signature: str,
    error_message: str,
    provider: str,
    task_class: str,
) -> None:
    """Record a failed task execution to error memory for future avoidance.

    This enables the system to learn from failures and avoid similar mistakes.
    """
    try:
        error_memory.add(
            domain=domain,
            task_id=task_class,
            error_signature=f"{domain}|{provider}|{error_signature}",
            message=error_message[:500],
            recommended_fix=f"Try alternative approach for: {query[:100]}",
        )
        # Record to session if active
        _record_session_event("error_recorded", {
            "domain": domain,
            "error_signature": error_signature,
            "provider": provider,
        })

        # Also record to runtime failure patterns
        record_failure_for_avoidance(
            domain=domain,
            task_id=task_class,
            error_message=error_message,
            error_type=error_signature,
            repo_root=_REPO,
            recommended_fix=f"Try alternative approach for: {query[:100]}",
        )
    except Exception as exc:
        logger.debug("Error recording to memory failed: %s", exc)


def _compact_text(text: str, limit: int) -> str:
    compact = " ".join(text.split())
    return compact[:limit].strip()


def _format_learning_guidance(guidance) -> str:
    """Format learning guidance for prompt injection."""
    parts = []

    # Support both dict and object access
    suggested = guidance.get("success_hints", []) if isinstance(guidance, dict) else getattr(guidance, "suggested_approaches", [])
    warnings = guidance.get("warnings", []) if isinstance(guidance, dict) else getattr(guidance, "warnings", [])
    repairs = guidance.get("suggested_fixes", []) if isinstance(guidance, dict) else getattr(guidance, "repair_strategies", [])

    if suggested:
        parts.append("Proven successful approaches:")
        for approach in suggested[:3]:
            if isinstance(approach, dict):
                parts.append(f"  - {approach.get('description', str(approach))[:150]}")
            else:
                parts.append(f"  - {str(approach)[:150]}")

    if warnings:
        parts.append("\nKnown issues to avoid:")
        for warning in warnings[:3]:
            if isinstance(warning, dict):
                parts.append(f"  - {warning.get('error_message', str(warning))[:150]}")
            else:
                parts.append(f"  - {str(warning)[:150]}")

    if repairs:
        parts.append("\nRepair strategies if errors occur:")
        for repair in repairs[:2]:
            if isinstance(repair, dict):
                parts.append(f"  - {repair.get('description', repair.get('fix_description', str(repair)))[:150]}")
            else:
                parts.append(f"  - {str(repair)[:150]}")

    return "\n".join(parts) if parts else ""


def _classify_task(query: str, domain: str) -> str:
    q = query.lower()
    if any(token in q for token in ("state", "what is on screen", "network state", "current state")):
        return "state_explanation"
    if any(token in q for token in ("next action", "what should i do next", "repair", "fix step")):
        return "next_action_suggestion"
    if any(token in q for token in ("plan", "patch", "generate code", "write code")):
        return "complex_reasoning"
    if domain in {"houdini", "touchdesigner"}:
        return "retrieval_synthesis"
    return "summarization"


def _select_model(task_class: str, explicit_model: str | None = None) -> str:
    if explicit_model:
        return explicit_model
    if task_class == "vision_like_interpretation":
        return _DEFAULT_VISION_MODEL
    return _DEFAULT_REASONING_MODEL


def _build_cache_key(task_class: str, provider: str, query: str, domain: str) -> PromptCacheKeyParts:
    # Format must match ProviderRouter key: compact_state_summary = f"{domain} {query}"
    summary = ' '.join(f'{domain} {query}'.split())[:700]
    return PromptCacheKeyParts(
        task_class=task_class,
        provider=provider,
        compact_state_summary=_compact_text(f"{domain}\n{query}", 700),
        prompt_template_version="runtime-v1",
        relevant_file_ids=(),
    )


def run_task(
    query: str,
    model: str | None = None,
    client: OllamaClient | None = None,
    *,
    offline_mode: bool = True,
    allow_remote_fallback: bool = False,
    preferred_remote: str = "openai",
    cache: PromptCache | None = None,
    budget: TokenBudget | None = None,
    memory: MemoryStore | None = None,
    error_memory: ErrorMemoryStore | None = None,
    use_runtime_memory: bool = True,
    orchestrator: InferenceOrchestrator | None = None,
) -> TaskResult:
    """Execute a task with local-first inference routing.

    This function wraps InferenceOrchestrator.run_inference() with:
    - Domain-specific system prompts (TD, Houdini, general)
    - Memory context injection
    - RAG context injection
    - Success/failure pattern recording

    All inference calls go through InferenceOrchestrator which enforces
    local-first defaults with Ollama as the preferred provider.

    Args:
        query: The user query/prompt
        model: Optional model override
        client: Optional OllamaClient (deprecated - use orchestrator)
        offline_mode: If True, block remote providers (default: True)
        allow_remote_fallback: If True, allow fallback to remote
        preferred_remote: Preferred remote provider
        cache: Optional PromptCache override
        budget: Optional TokenBudget override
        memory: Optional MemoryStore override
        error_memory: Optional ErrorMemoryStore override
        use_runtime_memory: If True, inject memory context
        orchestrator: Optional InferenceOrchestrator override

    Returns:
        TaskResult with response and routing metadata
    """
    router = TaskRouter()
    route = router.route(query)
    task_class = _classify_task(query, route.domain)

    # Record task started to active session
    _record_session_event("task_started", {
        "query": query[:200],
        "domain": route.domain,
        "task_class": task_class,
    })

    prompt_cache = cache or build_default_prompt_cache()
    token_budget = budget or build_default_token_budget()
    mem = memory or build_default_memory_store(_REPO)
    err_mem = error_memory or build_default_error_memory_store(_REPO)

    # Use provided orchestrator or get/create global one
    if orchestrator is None:
        orchestrator = get_global_orchestrator()

    compact_query = _compact_text(query, _MAX_QUERY_CHARS)
    system = _get_system_prompt(route.domain)
    system = _inject_rag_context(system, compact_query, route.domain)

    # Build runtime memory context and inject
    runtime_memory: RuntimeMemoryContext | None = None
    learning_guidance = None
    if use_runtime_memory:
        runtime_memory = build_runtime_memory_context(
            domain=route.domain,
            query=compact_query,
            repo_root=_REPO,
            max_success=3,
            max_failure=3,
            max_repair=2,
        )
        system = inject_memory_into_prompt(system, runtime_memory, max_chars=600)

        # APPLY LEARNED PATTERNS - This is where learning actually influences execution
        from app.core.memory_runtime import apply_learned_patterns
        learning_guidance = apply_learned_patterns(
            memory_context=runtime_memory,
            current_action=task_class,
        )

        # Record memory retrieval to session
        if runtime_memory.memory_influenced:
            _record_session_event("memory_retrieved", {
                "success_patterns": runtime_memory.success_pattern_count,
                "failure_patterns": runtime_memory.failure_pattern_count,
                "domain": route.domain,
                "guidance_applied": len(learning_guidance.get("success_hints", [])) + len(learning_guidance.get("suggested_fixes", [])),
            })

        # Enrich prompt with learning guidance if available
        if learning_guidance and learning_guidance.get("has_guidance"):
            guidance_text = _format_learning_guidance(learning_guidance)
            if guidance_text:
                system = system + "\n\n" + guidance_text

    system = _inject_memory_context(system, compact_query, route.domain, mem)
    system = _inject_feedback_loop_context(system, compact_query, route.domain)
    system = _compact_text(system, _MAX_SYSTEM_CHARS)

    # Build inference context
    inference_context = InferenceContext(
        prompt=compact_query,
        task_class=task_class,
        domain=route.domain,
        system_prompt=system,
        prompt_template_version="runtime-v1",
        allow_remote_fallback=allow_remote_fallback and not offline_mode,
    )

    # Run inference through orchestrator (local-first by default)
    result = orchestrator.run_inference(
        prompt=compact_query,
        context=inference_context,
        model=model,
    )

    # Record provider selection to active session
    _record_session_event("provider_selected", {
        "provider": result.selected_provider,
        "reason": result.route_reason,
        "cache_hit": result.cache_hit,
        "task_class": task_class,
    })

    # Handle result
    if not result.success:
        _record_error_to_memory(
            err_mem, query, route.domain,
            result.error_category.value if result.error_category else "unknown",
            result.error, result.selected_provider, task_class,
        )
        return TaskResult(
            query=query,
            domain=route.domain,
            role=route.role,
            model=_select_model(task_class, model),
            response="",
            provider=result.selected_provider,
            decision_reason=result.route_reason or "inference_failed",
            remote_allowed=result.is_remote_result,
            error=result.error,
            metadata={"task_class": task_class, "memory_injected": True},
            selected_provider=result.selected_provider,
            provider_strategy=result.provider_strategy,
            attempted_providers=result.attempted_providers,
            local_first_applied=result.local_first_applied,
            fallback_used=result.fallback_used,
            route_reason=result.route_reason,
            provider_error_summary=result.provider_error_summary,
        )

    # Record success to memory
    _promote_to_memory(mem, compact_query, result.text, route.domain, task_class, result.selected_provider)

    # Promote success pattern if runtime memory is enabled
    if use_runtime_memory:
        promote_success_to_pattern(
            domain=route.domain,
            task_id=task_class,
            success_summary=f"Task succeeded: {compact_query[:100]}",
            repo_root=_REPO,
            fix_steps=["execute_task", "verify_result"],
            tags=[route.domain, task_class, "success"],
        )

    # Record success to active session
    _record_session_event("success_recorded", {
        "provider": result.selected_provider,
        "domain": route.domain,
        "task_class": task_class,
        "response_length": len(result.text),
    })

    # Build memory metadata
    memory_metadata: dict[str, object] = {
        "task_class": task_class,
        "local_available": result.local_first_applied,
        "memory_injected": True,
    }
    if runtime_memory:
        memory_metadata["memory_influence"] = get_memory_influence_summary(runtime_memory)
    if learning_guidance:
        # learning_guidance is already a dict
        memory_metadata["learning_guidance"] = learning_guidance
        memory_metadata["patterns_applied"] = len(learning_guidance.get("success_hints", [])) + len(learning_guidance.get("suggested_fixes", []))

    return TaskResult(
        query=query,
        domain=route.domain,
        role=route.role,
        model=_select_model(task_class, model),
        response=result.text,
        provider=result.selected_provider,
        decision_reason=result.route_reason or "inference_success",
        cache_hit=result.cache_hit,
        remote_allowed=result.is_remote_result,
        metadata=memory_metadata,
        selected_provider=result.selected_provider,
        provider_strategy=result.provider_strategy,
        attempted_providers=result.attempted_providers,
        local_first_applied=result.local_first_applied,
        fallback_used=result.fallback_used,
        route_reason=result.route_reason,
    )
