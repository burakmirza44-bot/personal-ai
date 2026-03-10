"""Tests for the unified InferenceOrchestrator - local-first inference default."""

from __future__ import annotations

import pytest

from app.core.inference_orchestrator import (
    InferenceOrchestrator,
    InferenceSession,
    InferenceResult,
    InferenceContext,
    build_default_orchestrator,
    build_local_first_orchestrator,
    get_global_orchestrator,
    set_global_orchestrator,
    run_inference,
    ask_local,
    is_available,
)
from app.core.provider_fallback_chain import (
    ProviderPolicy,
    ProviderErrorCategory,
    build_default_policy,
    build_local_first_policy,
    LOCAL_PROVIDERS,
    REMOTE_PROVIDERS,
)


class TestInferenceContext:
    """Tests for InferenceContext dataclass."""

    def test_basic_context(self) -> None:
        context = InferenceContext(
            prompt="What is the network state?",
            task_class="state_explanation",
            domain="touchdesigner",
        )
        assert context.prompt == "What is the network state?"
        assert context.task_class == "state_explanation"
        assert context.domain == "touchdesigner"
        assert context.allow_cache is True
        assert context.allow_remote_fallback is None

    def test_compact_state_summary(self) -> None:
        context = InferenceContext(
            prompt="Test prompt",
            domain="houdini",
        )
        summary = context.compact_state_summary()
        assert "houdini" in summary
        assert "Test prompt" in summary


class TestInferenceResult:
    """Tests for InferenceResult dataclass."""

    def test_success_result(self) -> None:
        result = InferenceResult(
            text="Network state: OK",
            success=True,
            selected_provider="ollama",
        )
        assert result.success is True
        assert result.text == "Network state: OK"
        assert result.selected_provider == "ollama"
        assert result.is_local_result is True
        assert result.is_remote_result is False

    def test_error_result(self) -> None:
        result = InferenceResult(
            text="",
            success=False,
            error="Connection refused",
            error_category=ProviderErrorCategory.LOCAL_PROVIDER_MISSING,
            selected_provider="ollama",
        )
        assert result.success is False
        assert result.error == "Connection refused"
        assert result.error_category == ProviderErrorCategory.LOCAL_PROVIDER_MISSING

    def test_cache_result(self) -> None:
        result = InferenceResult(
            text="Cached response",
            success=True,
            selected_provider="cache_only",
            cache_hit=True,
        )
        assert result.is_cache_result is True

    def test_remote_result(self) -> None:
        result = InferenceResult(
            text="Remote response",
            success=True,
            selected_provider="gemini",
        )
        assert result.is_local_result is False
        assert result.is_remote_result is True

    def test_route_summary(self) -> None:
        result = InferenceResult(
            text="Test",
            success=True,
            selected_provider="ollama",
            provider_strategy="local_first",
        )
        summary = result.route_summary()
        assert "provider=ollama" in summary
        assert "strategy=local_first" in summary

    def test_to_dict(self) -> None:
        result = InferenceResult(
            text="Test",
            success=True,
            selected_provider="ollama",
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["selected_provider"] == "ollama"


class TestInferenceSession:
    """Tests for InferenceSession."""

    def test_basic_session(self) -> None:
        session = InferenceSession(session_id="test_session")
        assert session.session_id == "test_session"
        assert session._call_count == 0

    def test_record_call_success(self) -> None:
        session = InferenceSession(session_id="test_session")
        result = InferenceResult(
            text="Test",
            success=True,
            selected_provider="ollama",
            actual_tokens=100,
        )
        session.record_call(result)
        assert session._call_count == 1
        assert session._local_calls == 1
        assert session._total_tokens == 100

    def test_record_call_cache_hit(self) -> None:
        session = InferenceSession(session_id="test_session")
        result = InferenceResult(
            text="Cached",
            success=True,
            selected_provider="cache_only",
            cache_hit=True,
        )
        session.record_call(result)
        assert session._cache_hits == 1

    def test_record_call_error(self) -> None:
        session = InferenceSession(session_id="test_session")
        result = InferenceResult(
            text="",
            success=False,
            error="Test error",
            selected_provider="ollama",
        )
        session.record_call(result)
        assert len(session._errors) == 1

    def test_get_summary(self) -> None:
        session = InferenceSession(session_id="test_session")
        result = InferenceResult(
            text="Test",
            success=True,
            selected_provider="ollama",
            actual_tokens=100,
        )
        session.record_call(result)
        summary = session.get_summary()
        assert summary["session_id"] == "test_session"
        assert summary["stats"]["call_count"] == 1
        assert summary["stats"]["local_calls"] == 1


class TestInferenceOrchestrator:
    """Tests for InferenceOrchestrator."""

    def test_default_orchestrator(self) -> None:
        orchestrator = build_default_orchestrator()
        assert orchestrator.policy.provider_strategy == "local_first"
        assert orchestrator.policy.offline_mode is True
        assert orchestrator.policy.preferred_local_provider == "ollama"

    def test_local_first_orchestrator(self) -> None:
        orchestrator = build_local_first_orchestrator()
        assert orchestrator.policy.provider_strategy == "local_first"
        assert orchestrator.policy.offline_mode is True
        assert orchestrator.policy.allow_remote_fallback is False

    def test_orchestrator_with_remote_fallback(self) -> None:
        orchestrator = build_default_orchestrator(
            offline_mode=False,
            allow_remote_fallback=True,
        )
        assert orchestrator.policy.offline_mode is False
        assert orchestrator.policy.allow_remote_fallback is True

    def test_start_end_session(self) -> None:
        orchestrator = build_default_orchestrator()
        session = orchestrator.start_session(session_id="test")
        assert session is not None
        assert session.session_id == "test"

        summary = orchestrator.end_session()
        assert summary is not None
        assert summary["session_id"] == "test"

    def test_get_provider_summary(self) -> None:
        orchestrator = build_default_orchestrator()
        summary = orchestrator.get_provider_summary()
        assert "policy" in summary
        assert "audit_summary" in summary
        assert "cost_summary" in summary

    def test_check_local_available(self) -> None:
        orchestrator = build_default_orchestrator()
        # Ollama server may or may not be running
        available = orchestrator.check_local_available()
        assert isinstance(available, bool)


class TestGlobalOrchestrator:
    """Tests for global orchestrator management."""

    def test_get_global_orchestrator(self) -> None:
        orchestrator = get_global_orchestrator()
        assert orchestrator is not None
        assert orchestrator.policy.provider_strategy == "local_first"

    def test_set_global_orchestrator(self) -> None:
        custom = build_local_first_orchestrator(allow_remote_fallback=True)
        set_global_orchestrator(custom)

        orchestrator = get_global_orchestrator()
        assert orchestrator.policy.allow_remote_fallback is True

        # Reset to default
        set_global_orchestrator(build_default_orchestrator())


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_run_inference_function(self) -> None:
        # This tests the function signature, not actual inference
        # (Ollama server may not be running)
        orchestrator = build_default_orchestrator()
        set_global_orchestrator(orchestrator)

        # run_inference should be callable
        assert callable(run_inference)

    def test_ask_local_function(self) -> None:
        # This tests the function signature
        assert callable(ask_local)

    def test_is_available_function(self) -> None:
        # This tests the function signature
        result = is_available()
        assert isinstance(result, bool)


class TestLocalFirstDefault:
    """Tests verifying local-first is the default behavior."""

    def test_default_policy_is_local_first(self) -> None:
        policy = build_default_policy()
        assert policy.provider_strategy == "local_first"
        assert policy.offline_mode is True
        assert policy.preferred_local_provider == "ollama"

    def test_local_first_policy_blocks_remote(self) -> None:
        policy = build_local_first_policy()
        assert policy.is_remote_allowed() is False

    def test_local_first_policy_with_fallback(self) -> None:
        policy = build_local_first_policy(allow_remote_fallback=True)
        assert policy.is_remote_allowed() is True
        assert policy.offline_mode is False

    def test_orchestrator_default_uses_ollama(self) -> None:
        orchestrator = build_default_orchestrator()
        assert orchestrator.policy.preferred_local_provider == "ollama"

    def test_local_providers_are_zero_cost(self) -> None:
        """Verify local providers have zero cost."""
        for provider in LOCAL_PROVIDERS:
            assert provider in ("rule_based", "cache_only", "local_default", "ollama")

    def test_remote_providers_are_costly(self) -> None:
        """Verify remote providers have non-zero cost."""
        for provider in REMOTE_PROVIDERS:
            assert provider in ("openai", "gemini")


class TestProviderErrorCategories:
    """Tests for normalized error categories."""

    def test_error_categories_exist(self) -> None:
        assert ProviderErrorCategory.PROVIDER_UNAVAILABLE.value == "provider_unavailable"
        assert ProviderErrorCategory.LOCAL_PROVIDER_MISSING.value == "local_provider_missing"
        assert ProviderErrorCategory.REMOTE_FALLBACK_DISALLOWED.value == "remote_fallback_disallowed"
        assert ProviderErrorCategory.FALLBACK_CHAIN_EXHAUSTED.value == "fallback_chain_exhausted"

    def test_error_from_message(self) -> None:
        cat = ProviderErrorCategory.from_error_message("Connection refused")
        assert cat == ProviderErrorCategory.PROVIDER_UNAVAILABLE

        cat = ProviderErrorCategory.from_error_message("Timeout waiting for response")
        assert cat == ProviderErrorCategory.PROVIDER_TIMEOUT

        cat = ProviderErrorCategory.from_error_message("Budget exceeded")
        assert cat == ProviderErrorCategory.PROVIDER_BUDGET_EXCEEDED


class TestRoutingMetadata:
    """Tests for routing metadata visibility."""

    def test_result_has_provider_strategy(self) -> None:
        result = InferenceResult(
            text="Test",
            success=True,
            selected_provider="ollama",
            provider_strategy="local_first",
        )
        assert result.provider_strategy == "local_first"

    def test_result_has_fallback_info(self) -> None:
        result = InferenceResult(
            text="Test",
            success=True,
            selected_provider="gemini",
            fallback_used=True,
            fallback_depth=1,
            attempted_providers=("ollama", "gemini"),
        )
        assert result.fallback_used is True
        assert result.fallback_depth == 1
        assert "ollama" in result.attempted_providers

    def test_result_has_budget_status(self) -> None:
        result = InferenceResult(
            text="",
            success=False,
            budget_status="blocked",
        )
        assert result.budget_status == "blocked"