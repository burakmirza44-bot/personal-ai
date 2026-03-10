"""Unified Inference Orchestrator - Single entrypoint for all inference calls.

This module provides the central inference entrypoint that:
- Enforces local-first provider selection (Ollama default)
- Integrates provider router, cache, budget, and audit
- Provides session-level tracking and visibility
- Normalizes all errors through the error handling system
- Exposes complete route metadata for runtime/session visibility

Architecture:
- InferenceSession: Session-level inference context
- InferenceOrchestrator: Central inference entrypoint
- InferenceResult: Structured result with full metadata

Usage:
    orchestrator = InferenceOrchestrator()
    result = orchestrator.run_inference(
        prompt="What is the current network state?",
        task_class="state_explanation",
        domain="touchdesigner",
    )
    if result.success:
        print(result.text)
    print(result.route_summary())
"""

from __future__ import annotations

__all__ = [
    "InferenceSession",
    "InferenceOrchestrator",
    "InferenceResult",
    "InferenceContext",
    "build_default_orchestrator",
    "build_local_first_orchestrator",
    "get_global_orchestrator",
    "set_global_orchestrator",
    "run_inference",
    "ask_local",
    "is_available",
]

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from app.core.provider_fallback_chain import (
    CostEstimator,
    ProviderErrorCategory,
    ProviderFallbackChain,
    ProviderPolicy,
    ProviderRouteResult,
    ProviderHealthTracker,
    build_default_policy,
    build_local_first_policy,
    build_offline_policy,
    LOCAL_PROVIDERS,
    REMOTE_PROVIDERS,
)
from app.core.provider_audit import ProviderAudit, build_default_audit
from app.core.prompt_cache import PromptCache, PromptCacheKeyParts, build_default_prompt_cache
from app.core.token_budget import TokenBudget, build_default_token_budget

if TYPE_CHECKING:
    from app.integrations.ollama_client import OllamaClient

logger = logging.getLogger(__name__)

# Repository root for default paths
_REPO = Path(__file__).resolve().parents[2]

# Default models per MODEL_POLICY.md
_DEFAULT_REASONING_MODEL = "qwen3:14b"
_DEFAULT_VISION_MODEL = "qwen3-vl:30b"
_DEFAULT_FAST_MODEL = "qwen3:4b"


# ------------------------------------------------------------------
# InferenceContext - Input context for inference
# ------------------------------------------------------------------

@dataclass(slots=True)
class InferenceContext:
    """Structured input context for inference calls.

    Provides all the context needed for routing decisions,
    cache keys, and prompt enrichment.
    """

    prompt: str
    task_class: str = "summarization"
    domain: str = ""
    system_prompt: str = ""

    # Cache key components
    relevant_file_ids: tuple[str, ...] = ()
    prompt_template_version: str = "v1"

    # Token estimates
    estimated_input_tokens: int | None = None
    estimated_output_tokens: int = 300

    # Routing hints
    require_remote: bool = False
    preferred_provider: str | None = None
    allow_cache: bool = True
    allow_remote_fallback: bool | None = None  # None = use policy default

    # Execution context
    session_id: str = ""
    task_id: str = ""
    step_id: str = ""

    # Domain-specific context
    domain_context: dict[str, Any] = field(default_factory=dict)

    def compact_state_summary(self, max_len: int = 700) -> str:
        """Build compact state summary for cache key."""
        parts = [self.domain, self.prompt]
        text = " ".join(parts)
        return " ".join(text.split())[:max_len]


# ------------------------------------------------------------------
# InferenceResult - Output from inference
# ------------------------------------------------------------------

@dataclass(slots=True)
class InferenceResult:
    """Structured result from inference with complete metadata.

    Provides the inference output along with full routing metadata
    for runtime/session visibility.
    """

    # Core result
    text: str = ""
    success: bool = False
    error: str = ""
    error_category: ProviderErrorCategory | None = None

    # Provider metadata
    selected_provider: str = ""
    attempted_providers: tuple[str, ...] = ()
    skipped_providers: tuple[str, ...] = ()
    provider_strategy: str = "local_first"

    # Routing metadata
    local_first_applied: bool = True
    fallback_used: bool = False
    fallback_depth: int = 0
    route_reason: str = ""

    # Cache metadata
    cache_checked: bool = False
    cache_hit: bool = False
    cache_key: str = ""

    # Budget metadata
    budget_status: str = "ok"
    token_budget_status: str = "ok"
    estimated_tokens: int = 0
    actual_tokens: int = 0

    # Cost metadata
    estimated_cost: float = 0.0
    actual_cost: float = 0.0
    cost_class: str = "zero"

    # Latency metadata
    provider_latency_ms: float = 0.0
    total_latency_ms: float = 0.0

    # Model metadata
    model: str = ""
    task_class: str = ""
    domain: str = ""

    # Session metadata
    session_id: str = ""
    task_id: str = ""
    timestamp: str = ""

    # Additional metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_cache_result(self) -> bool:
        """Check if result came from cache."""
        return self.cache_hit and self.selected_provider == "cache_only"

    @property
    def is_local_result(self) -> bool:
        """Check if result came from local provider."""
        return self.selected_provider in LOCAL_PROVIDERS

    @property
    def is_remote_result(self) -> bool:
        """Check if result came from remote provider."""
        return self.selected_provider in REMOTE_PROVIDERS

    @property
    def provider_error_summary(self) -> str:
        """Get a summary of provider errors."""
        if not self.error:
            return ""
        if self.error_category:
            return f"{self.error_category.value}: {self.error[:100]}"
        return self.error[:100]

    def route_summary(self) -> str:
        """Return a one-line summary of the routing decision."""
        parts = [
            f"provider={self.selected_provider}",
            f"strategy={self.provider_strategy}",
        ]
        if self.fallback_used:
            parts.append(f"fallback_depth={self.fallback_depth}")
        if self.cache_hit:
            parts.append("cache_hit")
        if not self.success:
            parts.append(f"error={self.error_category.value if self.error_category else 'unknown'}")
        return " ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for logging/serialization."""
        return {
            "text": self.text[:500] if self.text else "",
            "success": self.success,
            "error": self.error[:200] if self.error else "",
            "error_category": self.error_category.value if self.error_category else None,
            "selected_provider": self.selected_provider,
            "attempted_providers": list(self.attempted_providers),
            "skipped_providers": list(self.skipped_providers),
            "provider_strategy": self.provider_strategy,
            "local_first_applied": self.local_first_applied,
            "fallback_used": self.fallback_used,
            "fallback_depth": self.fallback_depth,
            "route_reason": self.route_reason,
            "cache_checked": self.cache_checked,
            "cache_hit": self.cache_hit,
            "budget_status": self.budget_status,
            "token_budget_status": self.token_budget_status,
            "estimated_tokens": self.estimated_tokens,
            "actual_tokens": self.actual_tokens,
            "estimated_cost": self.estimated_cost,
            "actual_cost": self.actual_cost,
            "cost_class": self.cost_class,
            "provider_latency_ms": self.provider_latency_ms,
            "total_latency_ms": self.total_latency_ms,
            "model": self.model,
            "task_class": self.task_class,
            "domain": self.domain,
            "session_id": self.session_id,
            "task_id": self.task_id,
            "timestamp": self.timestamp,
        }


# ------------------------------------------------------------------
# InferenceSession - Session-level context
# ------------------------------------------------------------------

@dataclass
class InferenceSession:
    """Session-level inference context.

    Maintains session state including:
    - Provider policy configuration
    - Aggregated cost/token usage
    - Provider health tracking
    - Audit trail
    """

    session_id: str
    policy: ProviderPolicy = field(default_factory=build_default_policy)
    audit: ProviderAudit = field(default_factory=build_default_audit)
    health_tracker: ProviderHealthTracker = field(default_factory=ProviderHealthTracker)
    cost_estimator: CostEstimator = field(default_factory=CostEstimator)

    # Session stats
    _call_count: int = field(default=0, repr=False)
    _cache_hits: int = field(default=0, repr=False)
    _local_calls: int = field(default=0, repr=False)
    _remote_calls: int = field(default=0, repr=False)
    _total_tokens: int = field(default=0, repr=False)
    _total_cost: float = field(default=0.0, repr=False)
    _errors: list[dict[str, Any]] = field(default_factory=list, repr=False)

    def record_call(self, result: InferenceResult) -> None:
        """Record a call result to session stats."""
        self._call_count += 1
        if result.cache_hit:
            self._cache_hits += 1
        if result.is_local_result:
            self._local_calls += 1
        if result.is_remote_result:
            self._remote_calls += 1
        self._total_tokens += result.actual_tokens
        self._total_cost += result.actual_cost

        if not result.success:
            self._errors.append({
                "provider": result.selected_provider,
                "error": result.error[:100],
                "category": result.error_category.value if result.error_category else None,
            })

    def get_summary(self) -> dict[str, Any]:
        """Get session summary."""
        return {
            "session_id": self.session_id,
            "policy": self.policy.to_dict(),
            "stats": {
                "call_count": self._call_count,
                "cache_hits": self._cache_hits,
                "cache_hit_rate": self._cache_hits / max(1, self._call_count),
                "local_calls": self._local_calls,
                "remote_calls": self._remote_calls,
                "total_tokens": self._total_tokens,
                "total_cost": self._total_cost,
            },
            "errors": self._errors[-10:],  # Last 10 errors
            "healthy_providers": [
                p for p in list(LOCAL_PROVIDERS | REMOTE_PROVIDERS)
                if self.health_tracker.is_healthy(p)
            ],
        }


# ------------------------------------------------------------------
# InferenceOrchestrator - Central inference entrypoint
# ------------------------------------------------------------------

@dataclass
class InferenceOrchestrator:
    """Central inference entrypoint with local-first defaults.

    This is the single entrypoint for all inference calls in the system.
    It enforces:
    - Local-first provider selection (Ollama default)
    - Cache-aware routing
    - Budget-aware routing
    - Deterministic fallback behavior
    - Normalized provider failures
    - Runtime/session visibility

    Usage:
        orchestrator = InferenceOrchestrator()
        result = orchestrator.run_inference(prompt="...", task_class="summarization")
    """

    # Core components
    policy: ProviderPolicy = field(default_factory=build_default_policy)
    fallback_chain: ProviderFallbackChain = field(default_factory=ProviderFallbackChain)
    cache: PromptCache = field(default_factory=build_default_prompt_cache)
    budget: TokenBudget = field(default_factory=build_default_token_budget)
    audit: ProviderAudit = field(default_factory=build_default_audit)

    # Optional Ollama client (lazy-initialized)
    _ollama_client: OllamaClient | None = field(default=None, repr=False)

    # Provider executors (registered dynamically)
    _executors: dict[str, Callable] = field(default_factory=dict, repr=False)

    # Session tracking
    _session: InferenceSession | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """Initialize the fallback chain with components."""
        # Ensure fallback chain has cache and budget
        if self.fallback_chain.cache is None:
            self.fallback_chain.cache = self.cache
        if self.fallback_chain.budget is None:
            self.fallback_chain.budget = self.budget
        if self.fallback_chain.policy is None:
            self.fallback_chain.policy = self.policy

        # Register built-in executors
        self._register_builtin_executors()

    def _register_builtin_executors(self) -> None:
        """Register built-in provider executors."""
        # Rule-based executor
        self.register_executor("rule_based", self._execute_rule_based)

        # Cache executor (handled by fallback chain, but register for completeness)
        self.register_executor("cache_only", self._execute_cache_only)

    def _get_ollama_client(self) -> OllamaClient:
        """Get or create Ollama client (lazy initialization)."""
        if self._ollama_client is None:
            from app.integrations.ollama_client import OllamaClient
            self._ollama_client = OllamaClient(default_model=_DEFAULT_REASONING_MODEL)
        return self._ollama_client

    def register_executor(self, provider: str, executor: Callable) -> None:
        """Register a provider executor.

        Executor signature:
            (prompt: str, context: InferenceContext, **kwargs) -> InferenceResult

        Or the simpler fallback chain signature:
            (prompt: str, **kwargs) -> tuple[bool, str, int, str]
        """
        self._executors[provider] = executor
        # Also register with fallback chain
        self.fallback_chain.register_executor(provider, self._wrap_executor(executor))

    def _wrap_executor(self, executor: Callable) -> Callable:
        """Wrap an executor to match fallback chain signature."""
        def wrapped(prompt: str, **kwargs: Any) -> tuple[bool, str, int, str]:
            context = kwargs.get("context")
            try:
                if context and isinstance(context, InferenceContext):
                    result = executor(prompt, context=context, **kwargs)
                    if isinstance(result, InferenceResult):
                        return result.success, result.text, result.actual_tokens, result.error
                # Assume fallback chain signature
                result = executor(prompt, **kwargs)
                if isinstance(result, tuple):
                    return result
                return True, str(result), 0, ""
            except Exception as exc:
                return False, "", 0, str(exc)
        return wrapped

    def _execute_rule_based(
        self,
        prompt: str,
        context: InferenceContext | None = None,
        **kwargs: Any,
    ) -> InferenceResult:
        """Execute rule-based fallback provider."""
        prompt_lower = prompt.lower()

        if "state" in prompt_lower or "what is" in prompt_lower:
            text = "Unable to determine state without provider."
        elif "next action" in prompt_lower or "what should" in prompt_lower:
            text = "Review current state and identify the next logical step."
        else:
            text = "Rule-based fallback: unable to process without provider."

        return InferenceResult(
            text=text,
            success=True,
            selected_provider="rule_based",
            provider_strategy="local_first",
            cost_class="zero",
            actual_tokens=10,
            task_class=context.task_class if context else "",
            domain=context.domain if context else "",
        )

    def _execute_cache_only(
        self,
        prompt: str,
        context: InferenceContext | None = None,
        **kwargs: Any,
    ) -> InferenceResult:
        """Execute cache-only provider (should not be called directly)."""
        return InferenceResult(
            text="",
            success=False,
            error="cache_miss",
            error_category=ProviderErrorCategory.CACHE_LOOKUP_FAILED,
            selected_provider="cache_only",
        )

    def _execute_ollama(
        self,
        prompt: str,
        context: InferenceContext | None = None,
        **kwargs: Any,
    ) -> InferenceResult:
        """Execute Ollama local inference."""
        import time as time_module

        client = self._get_ollama_client()
        start_time = time_module.perf_counter()

        # Determine model
        model = kwargs.get("model")
        if not model and context:
            if context.task_class == "vision_like_interpretation":
                model = _DEFAULT_VISION_MODEL
            elif context.task_class in ("summarization", "state_explanation"):
                model = _DEFAULT_FAST_MODEL
            else:
                model = _DEFAULT_REASONING_MODEL

        try:
            system = kwargs.get("system", "")
            if context and context.system_prompt:
                system = context.system_prompt

            text = client.chat(
                messages=[{"role": "user", "content": prompt}],
                model=model,
                system=system,
                temperature=kwargs.get("temperature", 0.2),
            )

            latency_ms = (time_module.perf_counter() - start_time) * 1000

            return InferenceResult(
                text=text,
                success=True,
                selected_provider="ollama",
                provider_strategy="local_first",
                local_first_applied=True,
                cost_class="zero",
                actual_tokens=len(prompt) // 4 + len(text) // 4,
                provider_latency_ms=latency_ms,
                model=model,
                task_class=context.task_class if context else "",
                domain=context.domain if context else "",
            )

        except Exception as exc:
            latency_ms = (time_module.perf_counter() - start_time) * 1000
            error_msg = str(exc)

            # Determine error category
            if "unreachable" in error_msg.lower() or "connection" in error_msg.lower():
                error_cat = ProviderErrorCategory.LOCAL_PROVIDER_MISSING
            elif "timeout" in error_msg.lower():
                error_cat = ProviderErrorCategory.PROVIDER_TIMEOUT
            else:
                error_cat = ProviderErrorCategory.PROVIDER_EXECUTION_FAILED

            return InferenceResult(
                text="",
                success=False,
                error=error_msg,
                error_category=error_cat,
                selected_provider="ollama",
                provider_latency_ms=latency_ms,
                model=model,
                task_class=context.task_class if context else "",
                domain=context.domain if context else "",
            )

    def _execute_gemini(
        self,
        prompt: str,
        context: InferenceContext | None = None,
        **kwargs: Any,
    ) -> InferenceResult:
        """Execute Gemini/OpenAI remote inference."""
        import time as time_module

        start_time = time_module.perf_counter()

        try:
            from app.integrations.gemini_client import query_gemini

            model = kwargs.get("model", "gemini-2.5-pro")
            response = query_gemini(prompt, model=model)

            latency_ms = (time_module.perf_counter() - start_time) * 1000

            if not response.success:
                # Determine error category
                if "quota" in response.error.lower() or "exhausted" in response.error.lower():
                    error_cat = ProviderErrorCategory.PROVIDER_RATE_LIMITED
                elif "api_key" in response.error.lower() or "no_api_key" in response.error.lower():
                    error_cat = ProviderErrorCategory.PROVIDER_AUTH_ERROR
                else:
                    error_cat = ProviderErrorCategory.PROVIDER_EXECUTION_FAILED

                return InferenceResult(
                    text="",
                    success=False,
                    error=response.error,
                    error_category=error_cat,
                    selected_provider=response.provider or "gemini",
                    provider_latency_ms=latency_ms,
                    model=model,
                    task_class=context.task_class if context else "",
                    domain=context.domain if context else "",
                )

            return InferenceResult(
                text=response.text,
                success=True,
                selected_provider=response.provider or "gemini",
                provider_strategy="remote_fallback" if context and context.task_class not in ("complex_reasoning", "coding_patch") else "quality_first",
                local_first_applied=False,
                cost_class="medium" if "gemini" in response.provider else "high",
                actual_tokens=len(prompt) // 4 + len(response.text) // 4,
                provider_latency_ms=latency_ms,
                model=model,
                task_class=context.task_class if context else "",
                domain=context.domain if context else "",
            )

        except Exception as exc:
            latency_ms = (time_module.perf_counter() - start_time) * 1000
            return InferenceResult(
                text="",
                success=False,
                error=str(exc),
                error_category=ProviderErrorCategory.PROVIDER_EXECUTION_FAILED,
                selected_provider="gemini",
                provider_latency_ms=latency_ms,
                task_class=context.task_class if context else "",
                domain=context.domain if context else "",
            )

    def _execute_openai(
        self,
        prompt: str,
        context: InferenceContext | None = None,
        **kwargs: Any,
    ) -> InferenceResult:
        """Execute OpenAI remote inference (via gemini_client fallback)."""
        # The gemini_client handles OpenAI fallback internally
        return self._execute_gemini(prompt, context, **kwargs)

    def start_session(
        self,
        session_id: str | None = None,
        policy: ProviderPolicy | None = None,
    ) -> InferenceSession:
        """Start a new inference session.

        Args:
            session_id: Optional session ID (auto-generated if not provided)
            policy: Optional policy override

        Returns:
            InferenceSession instance
        """
        import time
        sid = session_id or f"session_{int(time.time())}"

        session_policy = policy or self.policy

        self._session = InferenceSession(
            session_id=sid,
            policy=session_policy,
            audit=self.audit,
            health_tracker=self.fallback_chain.health_tracker,
            cost_estimator=self.fallback_chain.cost_estimator,
        )

        return self._session

    def end_session(self) -> dict[str, Any] | None:
        """End the current session and return summary."""
        if self._session is None:
            return None

        summary = self._session.get_summary()
        self._session = None
        return summary

    def check_local_available(self) -> bool:
        """Check if local provider (Ollama) is available."""
        try:
            return self._get_ollama_client().ping()
        except Exception:
            return False

    def run_inference(
        self,
        prompt: str,
        task_class: str = "summarization",
        domain: str = "",
        system_prompt: str = "",
        context: InferenceContext | None = None,
        **kwargs: Any,
    ) -> InferenceResult:
        """Execute inference with full local-first routing.

        This is the main entrypoint for all inference calls.

        Args:
            prompt: The input prompt/query
            task_class: Type of task (summarization, coding_patch, etc.)
            domain: Domain context (houdini, touchdesigner, etc.)
            system_prompt: Optional system prompt override
            context: Optional InferenceContext with full context
            **kwargs: Additional routing/execution options

        Returns:
            InferenceResult with text and complete routing metadata
        """
        import time as time_module
        from datetime import datetime

        start_time = time_module.perf_counter()

        # Build context if not provided
        if context is None:
            context = InferenceContext(
                prompt=prompt,
                task_class=task_class,
                domain=domain,
                system_prompt=system_prompt,
                **kwargs,
            )

        # Check local availability
        local_available = self.check_local_available()

        # Determine remote fallback permission
        allow_remote = context.allow_remote_fallback
        if allow_remote is None:
            allow_remote = self.policy.allow_remote_fallback and not self.policy.offline_mode

        # Check cache first if allowed
        cache_key = ""
        if context.allow_cache and self.policy.allow_cache_short_circuit:
            cache_parts = PromptCacheKeyParts(
                task_class=context.task_class,
                provider=self.policy.preferred_local_provider,
                compact_state_summary=context.compact_state_summary(),
                relevant_file_ids=context.relevant_file_ids,
                prompt_template_version=context.prompt_template_version,
            )

            cached = self.cache.get(key_parts=cache_parts)
            if cached is not None:
                latency_ms = (time_module.perf_counter() - start_time) * 1000
                result = InferenceResult(
                    text=cached.result,
                    success=True,
                    selected_provider="cache_only",
                    provider_strategy="local_first",
                    local_first_applied=True,
                    cache_checked=True,
                    cache_hit=True,
                    cache_key=cached.cache_key,
                    cost_class="zero",
                    actual_tokens=len(cached.result) // 4,
                    total_latency_ms=latency_ms,
                    task_class=context.task_class,
                    domain=context.domain,
                    session_id=self._session.session_id if self._session else "",
                    task_id=context.task_id,
                    timestamp=datetime.utcnow().isoformat(timespec="seconds") + "Z",
                )

                if self._session:
                    self._session.record_call(result)

                return result

        # Route through fallback chain
        route_result = self.fallback_chain.route(
            task_class=context.task_class,
            prompt=prompt,
            estimated_tokens=context.estimated_input_tokens,
            require_remote=context.require_remote,
            preferred_provider=context.preferred_provider,
            allow_cache=False,  # Already checked
            domain=context.domain,
            relevant_file_ids=list(context.relevant_file_ids),
            prompt_template_version=context.prompt_template_version,
            local_provider_available=local_available,
        )

        # Execute with selected provider
        result = self._execute_with_route(
            prompt=prompt,
            context=context,
            route_result=route_result,
            start_time=start_time,
        )

        # Record to session
        if self._session:
            self._session.record_call(result)

        # Record to audit
        self._record_audit(context, result)

        # Cache successful result
        if result.success and context.allow_cache:
            self._cache_result(prompt, context, result)

        return result

    def _execute_with_route(
        self,
        prompt: str,
        context: InferenceContext,
        route_result: ProviderRouteResult,
        start_time: float,
    ) -> InferenceResult:
        """Execute inference using the route decision."""
        import time as time_module
        from datetime import datetime

        provider = route_result.selected_provider

        # Handle built-in providers
        if provider == "rule_based":
            result = self._execute_rule_based(prompt, context)
        elif provider == "cache_only":
            result = self._execute_cache_only(prompt, context)
        elif provider == "ollama":
            result = self._execute_ollama(prompt, context)
        elif provider == "gemini":
            result = self._execute_gemini(prompt, context)
        elif provider == "openai":
            result = self._execute_openai(prompt, context)
        elif provider in self._executors:
            # Custom registered executor
            try:
                result = self._executors[provider](prompt, context=context)
                if not isinstance(result, InferenceResult):
                    result = InferenceResult(
                        text=str(result),
                        success=True,
                        selected_provider=provider,
                        task_class=context.task_class,
                        domain=context.domain,
                    )
            except Exception as exc:
                result = InferenceResult(
                    text="",
                    success=False,
                    error=str(exc),
                    error_category=ProviderErrorCategory.PROVIDER_EXECUTION_FAILED,
                    selected_provider=provider,
                    task_class=context.task_class,
                    domain=context.domain,
                )
        else:
            result = InferenceResult(
                text="",
                success=False,
                error=f"Unknown provider: {provider}",
                error_category=ProviderErrorCategory.PROVIDER_UNAVAILABLE,
                selected_provider=provider,
                task_class=context.task_class,
                domain=context.domain,
            )

        # Enrich with route metadata
        result.provider_strategy = route_result.provider_strategy
        result.local_first_applied = provider in LOCAL_PROVIDERS
        result.fallback_used = route_result.fallback_used
        result.fallback_depth = route_result.fallback_depth
        result.route_reason = route_result.route_reason
        result.attempted_providers = route_result.attempted_providers
        result.skipped_providers = route_result.skipped_providers
        result.cache_checked = route_result.cache_checked
        result.budget_status = route_result.budget_status
        result.estimated_tokens = route_result.estimated_tokens
        result.estimated_cost = route_result.estimated_cost
        result.cost_class = route_result.cost_class
        result.total_latency_ms = (time_module.perf_counter() - start_time) * 1000
        result.task_class = context.task_class
        result.domain = context.domain
        result.session_id = self._session.session_id if self._session else ""
        result.task_id = context.task_id
        result.timestamp = datetime.utcnow().isoformat(timespec="seconds") + "Z"

        return result

    def _record_audit(
        self,
        context: InferenceContext,
        result: InferenceResult,
    ) -> None:
        """Record routing decision to audit log."""
        from app.core.provider_router import RoutingDecision

        # Build a minimal RoutingDecision for audit
        decision = RoutingDecision(
            chosen_provider=result.selected_provider,
            decision_reason=result.route_reason or "inference",
            local_first_applied=result.local_first_applied,
            cache_checked=result.cache_checked,
            cache_hit=result.cache_hit,
            remote_allowed=result.is_remote_result,
            blocked_by_offline=False,
            blocked_by_budget=result.budget_status == "blocked",
            blocked_by_missing_credentials=False,
            estimated_cost_class=result.cost_class,  # type: ignore
            task_class=context.task_class,
        )

        self.audit.record(
            task_class=context.task_class,
            domain=context.domain,
            decision=decision,
        )

    def _cache_result(
        self,
        prompt: str,
        context: InferenceContext,
        result: InferenceResult,
    ) -> None:
        """Cache a successful result."""
        if not result.success or not result.text:
            return

        cache_parts = PromptCacheKeyParts(
            task_class=context.task_class,
            provider=result.selected_provider,
            compact_state_summary=context.compact_state_summary(),
            relevant_file_ids=context.relevant_file_ids,
            prompt_template_version=context.prompt_template_version,
        )

        self.cache.put(
            key_parts=cache_parts,
            result=result.text,
            metadata={
                "provider": result.selected_provider,
                "model": result.model,
                "task_class": context.task_class,
                "domain": context.domain,
            },
        )

    def get_provider_summary(self) -> dict[str, Any]:
        """Get summary of provider usage and health."""
        return {
            "policy": self.policy.to_dict(),
            "audit_summary": self.audit.summary(),
            "cost_summary": self.fallback_chain.cost_estimator.get_summary(),
            "healthy_providers": [
                p for p in list(LOCAL_PROVIDERS | REMOTE_PROVIDERS)
                if self.fallback_chain.health_tracker.is_healthy(p)
            ],
            "unhealthy_providers": [
                p for p in list(LOCAL_PROVIDERS | REMOTE_PROVIDERS)
                if not self.fallback_chain.health_tracker.is_healthy(p)
            ],
            "session": self._session.get_summary() if self._session else None,
        }


# ------------------------------------------------------------------
# Factory functions and global instance
# ------------------------------------------------------------------

# Global orchestrator instance (lazy-initialized)
_GLOBAL_ORCHESTRATOR: InferenceOrchestrator | None = None


def build_default_orchestrator(
    offline_mode: bool = True,
    allow_remote_fallback: bool = False,
    cache: PromptCache | None = None,
    budget: TokenBudget | None = None,
) -> InferenceOrchestrator:
    """Build the default orchestrator with local-first policy."""
    policy = build_local_first_policy(
        allow_remote_fallback=allow_remote_fallback,
        preferred_local="ollama",
        preferred_remote="gemini",
    )

    return InferenceOrchestrator(
        policy=policy,
        cache=cache or build_default_prompt_cache(),
        budget=budget or build_default_token_budget(),
    )


def build_local_first_orchestrator(
    allow_remote_fallback: bool = False,
) -> InferenceOrchestrator:
    """Build a strict local-first orchestrator."""
    return build_default_orchestrator(
        offline_mode=not allow_remote_fallback,
        allow_remote_fallback=allow_remote_fallback,
    )


def get_global_orchestrator() -> InferenceOrchestrator:
    """Get the global orchestrator instance (creates if needed)."""
    global _GLOBAL_ORCHESTRATOR
    if _GLOBAL_ORCHESTRATOR is None:
        _GLOBAL_ORCHESTRATOR = build_default_orchestrator()
    return _GLOBAL_ORCHESTRATOR


def set_global_orchestrator(orchestrator: InferenceOrchestrator) -> None:
    """Set the global orchestrator instance."""
    global _GLOBAL_ORCHESTRATOR
    _GLOBAL_ORCHESTRATOR = orchestrator


# ------------------------------------------------------------------
# Convenience functions
# ------------------------------------------------------------------

def run_inference(
    prompt: str,
    task_class: str = "summarization",
    domain: str = "",
    **kwargs: Any,
) -> InferenceResult:
    """Convenience function using global orchestrator.

    This is the simplest way to run inference with local-first defaults.

    Args:
        prompt: The input prompt/query
        task_class: Type of task (summarization, coding_patch, etc.)
        domain: Domain context (houdini, touchdesigner, etc.)
        **kwargs: Additional routing/execution options

    Returns:
        InferenceResult with text and complete routing metadata
    """
    return get_global_orchestrator().run_inference(
        prompt=prompt,
        task_class=task_class,
        domain=domain,
        **kwargs,
    )


def ask_local(
    query: str,
    system: str = "",
    model: str = _DEFAULT_REASONING_MODEL,
    **kwargs: Any,
) -> tuple[str, bool]:
    """Single-turn query to local Ollama (backward-compatible helper).

    This provides backward compatibility with existing code that uses
    the ask_local() function from app.core.ollama_client.

    Args:
        query: The input query
        system: Optional system prompt
        model: Model to use (default: qwen3:14b)
        **kwargs: Additional options

    Returns:
        (response_text, success) tuple
    """
    orchestrator = get_global_orchestrator()

    # Force local-only
    result = orchestrator.run_inference(
        prompt=query,
        task_class="summarization",
        system_prompt=system,
        preferred_provider="ollama",
        allow_remote_fallback=False,
        model=model,
        **kwargs,
    )

    return result.text, result.success


def is_available() -> bool:
    """Check if local inference is available."""
    try:
        return get_global_orchestrator().check_local_available()
    except Exception:
        return False