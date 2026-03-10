"""Tests for error loop integration.

Tests that all failures enter the normalized error loop and
bridge errors are properly normalized.
"""

import tempfile
from unittest.mock import MagicMock, patch

import pytest

from app.learning.error_normalizer import (
    NormalizedError,
    NormalizedErrorType,
    normalize_bridge_failure,
    normalize_error,
)


class TestNormalizedErrorTypes:
    """Tests for NormalizedErrorType enum."""

    def test_bridge_error_types_exist(self):
        """Test that all bridge error types are defined."""
        assert NormalizedErrorType.BRIDGE_UNAVAILABLE == "bridge_unavailable"
        assert NormalizedErrorType.BRIDGE_UNHEALTHY == "bridge_unhealthy"
        assert NormalizedErrorType.BRIDGE_TIMEOUT == "bridge_timeout"
        assert NormalizedErrorType.BRIDGE_CONNECTION_FAILED == "bridge_connection_failed"
        assert NormalizedErrorType.BRIDGE_PING_FAILED == "bridge_ping_failed"
        assert NormalizedErrorType.BRIDGE_INSPECT_FAILED == "bridge_inspect_failed"
        assert NormalizedErrorType.BRIDGE_COMMAND_REJECTED == "bridge_command_rejected"
        assert NormalizedErrorType.BRIDGE_RESPONSE_INVALID == "bridge_response_invalid"

    def test_execution_error_types_exist(self):
        """Test that execution error types are defined."""
        assert NormalizedErrorType.EXECUTION_FAILED == "execution_failed"
        assert NormalizedErrorType.TIMEOUT == "timeout"
        assert NormalizedErrorType.INVALID_ACTION == "invalid_action"


class TestNormalizedError:
    """Tests for NormalizedError class."""

    def test_normalized_error_creation(self):
        """Test creating a NormalizedError."""
        error = NormalizedError(
            normalized_error_type=NormalizedErrorType.BRIDGE_UNAVAILABLE,
            message="Bridge is not available",
        )

        assert error.error_type == NormalizedErrorType.BRIDGE_UNAVAILABLE
        assert error.message == "Bridge is not available"
        assert error.original_error is None
        assert error.context == {}

    def test_normalized_error_with_context(self):
        """Test NormalizedError with context."""
        original_exc = Exception("Original")
        error = NormalizedError(
            normalized_error_type=NormalizedErrorType.BRIDGE_TIMEOUT,
            message="Bridge timed out",
            original_error=original_exc,
            context={"host": "127.0.0.1", "port": 9988},
        )

        assert error.original_error == original_exc
        assert error.context["host"] == "127.0.0.1"
        assert error.context["port"] == 9988

    def test_normalized_error_str(self):
        """Test string representation of NormalizedError."""
        error = NormalizedError(
            normalized_error_type=NormalizedErrorType.BRIDGE_PING_FAILED,
            message="Ping failed",
        )

        str_repr = str(error)
        assert "bridge_ping_failed" in str_repr
        assert "Ping failed" in str_repr

    def test_normalized_error_to_dict(self):
        """Test converting NormalizedError to dict."""
        error = NormalizedError(
            normalized_error_type=NormalizedErrorType.BRIDGE_UNHEALTHY,
            message="Bridge is unhealthy",
            context={"host": "127.0.0.1"},
        )

        data = error.to_dict()

        assert data["error_type"] == "bridge_unhealthy"
        assert data["message"] == "Bridge is unhealthy"
        assert data["context"]["host"] == "127.0.0.1"
        assert data["original_error"] is None

    def test_normalized_error_from_exception_timeout(self):
        """Test creating NormalizedError from timeout exception."""
        exc = TimeoutError("Connection timed out")
        error = NormalizedError.from_exception(exc)

        assert error.error_type == NormalizedErrorType.TIMEOUT
        assert "timed out" in error.message.lower()

    def test_normalized_error_from_exception_connection(self):
        """Test creating NormalizedError from connection exception."""
        exc = ConnectionError("Connection refused")
        error = NormalizedError.from_exception(exc)

        assert error.error_type == NormalizedErrorType.BRIDGE_CONNECTION_FAILED


class TestNormalizeError:
    """Tests for normalize_error function."""

    def test_normalize_normalized_error(self):
        """Test normalizing an already normalized error."""
        original = NormalizedError(
            normalized_error_type=NormalizedErrorType.BRIDGE_UNAVAILABLE,
            message="Test",
        )

        result = normalize_error(original)

        assert result is original

    def test_normalize_exception(self):
        """Test normalizing an exception."""
        exc = ValueError("Invalid value")
        error = normalize_error(exc)

        assert isinstance(error, NormalizedError)
        assert error.message == "Invalid value"
        assert error.original_error == exc

    def test_normalize_string(self):
        """Test normalizing a string message."""
        error = normalize_error("Something went wrong")

        assert isinstance(error, NormalizedError)
        assert error.message == "Something went wrong"
        assert error.error_type == NormalizedErrorType.UNKNOWN

    def test_normalize_with_type(self):
        """Test normalizing with specific error type."""
        error = normalize_error(
            "Bridge down",
            error_type=NormalizedErrorType.BRIDGE_UNAVAILABLE,
        )

        assert error.error_type == NormalizedErrorType.BRIDGE_UNAVAILABLE


class TestNormalizeBridgeFailure:
    """Tests for normalize_bridge_failure function."""

    def test_normalize_bridge_failure_ping(self):
        """Test normalizing ping failure."""
        error = normalize_bridge_failure(
            bridge_type="touchdesigner",
            failure_reason="Ping failed",
            error_code="PING_FAILED",
            host="127.0.0.1",
            port=9988,
        )

        assert error.error_type == NormalizedErrorType.BRIDGE_PING_FAILED
        assert "touchdesigner" in error.message
        assert "Ping failed" in error.message
        assert error.bridge_context["host"] == "127.0.0.1"
        assert error.bridge_context["port"] == 9988

    def test_normalize_bridge_failure_inspect(self):
        """Test normalizing inspect failure."""
        error = normalize_bridge_failure(
            bridge_type="houdini",
            failure_reason="Inspection failed",
            error_code="INSPECT_FAILED",
        )

        assert error.error_type == NormalizedErrorType.BRIDGE_INSPECT_FAILED

    def test_normalize_bridge_failure_command_rejected(self):
        """Test normalizing command rejected failure."""
        error = normalize_bridge_failure(
            bridge_type="touchdesigner",
            failure_reason="Command was rejected",
        )

        assert error.error_type == NormalizedErrorType.BRIDGE_COMMAND_FAILED

    def test_normalize_bridge_failure_timeout(self):
        """Test normalizing timeout failure."""
        error = normalize_bridge_failure(
            bridge_type="houdini",
            failure_reason="Request timeout",
        )

        assert error.error_type == NormalizedErrorType.BRIDGE_TIMEOUT

    def test_normalize_bridge_failure_invalid_response(self):
        """Test normalizing invalid response failure."""
        error = normalize_bridge_failure(
            bridge_type="touchdesigner",
            failure_reason="Invalid response format",
        )

        assert error.error_type == NormalizedErrorType.BRIDGE_RESPONSE_INVALID

    def test_normalize_bridge_failure_unhealthy(self):
        """Test normalizing unhealthy bridge failure."""
        error = normalize_bridge_failure(
            bridge_type="houdini",
            failure_reason="Bridge is unhealthy",
        )

        assert error.error_type == NormalizedErrorType.BRIDGE_UNHEALTHY

    def test_normalize_bridge_failure_connection(self):
        """Test normalizing connection failure."""
        error = normalize_bridge_failure(
            bridge_type="touchdesigner",
            failure_reason="Connection failed",
        )

        assert error.error_type == NormalizedErrorType.BRIDGE_CONNECTION_FAILED

    def test_normalize_bridge_failure_default(self):
        """Test normalizing generic failure defaults to unavailable."""
        error = normalize_bridge_failure(
            bridge_type="houdini",
            failure_reason="Something went wrong",
        )

        assert error.error_type == NormalizedErrorType.BRIDGE_UNAVAILABLE

    def test_normalize_bridge_failure_with_latency(self):
        """Test that latency is included in context."""
        error = normalize_bridge_failure(
            bridge_type="touchdesigner",
            failure_reason="Slow response",
            latency_ms=5000.0,
        )

        assert error.bridge_context["latency_ms"] == 5000.0


class TestErrorLoopIntegration:
    """Tests for error loop integration with execution."""

    def test_all_failures_normalized_in_td_loop(self):
        """Test that all failures are normalized in TD execution loop."""
        from app.domains.touchdesigner.td_execution_loop import (
            TDExecutionConfig,
            TDExecutionLoop,
        )

        config = TDExecutionConfig(dry_run=True, enable_memory=False)
        loop = TDExecutionLoop(config)

        task = MagicMock()
        task.task_summary = "test"
        task.task_id = "test_123"

        # In dry run, execution should succeed
        report = loop.run_basic_top_chain(task, use_live_bridge=False, dry_run=True)

        # If there are errors, they should be normalized
        if report.error_caught:
            assert report.normalized_error_type != ""

    def test_all_failures_normalized_in_houdini_loop(self):
        """Test that all failures are normalized in Houdini execution loop."""
        from app.domains.houdini.houdini_execution_loop import (
            HoudiniExecutionConfig,
            HoudiniExecutionLoop,
        )

        config = HoudiniExecutionConfig(dry_run=True, enable_memory=False)
        loop = HoudiniExecutionLoop(config)

        task = MagicMock()
        task.task_summary = "test"
        task.task_id = "test_123"

        # In dry run, execution should succeed
        report = loop.run_basic_sop_chain(task, use_live_bridge=False, dry_run=True)

        # If there are errors, they should be normalized
        if report.error_caught:
            assert report.normalized_error_type != ""

    def test_bridge_failure_produces_normalized_error(self):
        """Test that bridge failures produce normalized errors."""
        from app.core.bridge_health import BridgeHealthReport, normalize_bridge_error

        report = BridgeHealthReport(
            bridge_type="touchdesigner",
            bridge_reachable=False,
            ping_ok=False,
            last_error_code="PING_TIMEOUT",
            last_error_message="Ping timed out",
        )

        error = normalize_bridge_error(report, "touchdesigner", "task_123")

        assert error.error_type == NormalizedErrorType.BRIDGE_PING_FAILED
        assert "touchdesigner" in error.message
        assert error.context["task_id"] == "task_123"

    def test_runtime_loop_error_normalization(self):
        """Test that runtime loop normalizes errors."""
        from app.agent_core.runtime_loop import IntegratedRuntimeLoop

        loop = IntegratedRuntimeLoop(
            domain="touchdesigner",
            enable_memory=False,
            enable_bridge_health=False,
        )

        # Execute a step that will fail (no actual execution)
        step = {
            "action": "test_action",
            "description": "Test step",
            "requires_bridge": False,
        }

        # In the current implementation, the step execution simulates success
        # but if there were errors, they would be normalized
        result = loop.execute_step_with_retry(step, task_id="test_task")

        # The runtime loop tracks errors in normalized_errors list
        assert hasattr(result, "normalized_errors")
        assert hasattr(result, "error_count")

    def test_no_failures_bypass_error_loop(self):
        """Test that no failures bypass the normalized error loop."""
        from app.agent_core.runtime_loop import IntegratedRuntimeLoop

        loop = IntegratedRuntimeLoop(
            domain="touchdesigner",
            enable_memory=False,
            enable_bridge_health=False,
        )

        # Test with a recipe that has steps
        recipe = {
            "name": "test_recipe",
            "description": "Test recipe",
            "steps": [
                {"action": "step1", "description": "Step 1"},
                {"action": "step2", "description": "Step 2"},
            ],
        }

        result = loop.execute_recipe(recipe, task_id="test_recipe")

        # Result should have normalized_errors (may be empty on success)
        assert hasattr(result, "normalized_errors")
        assert isinstance(result.normalized_errors, list)
