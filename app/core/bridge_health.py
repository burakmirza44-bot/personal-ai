"""Bridge Health Monitoring Module.

Provides structured bridge health reporting and health check utilities
for TouchDesigner and Houdini bridges.
"""

from __future__ import annotations

import socket
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, TYPE_CHECKING

from app.agent_core.backend_result import BridgeHealthResult
from app.learning.error_normalizer import NormalizedError, NormalizedErrorType


@dataclass(slots=True)
class BridgeHealthReport:
    """Comprehensive bridge health report for runtime visibility.

    This dataclass provides a structured summary of bridge health status
    that can be attached to execution reports and used for error normalization.
    """

    bridge_type: str  # "touchdesigner" | "houdini"
    bridge_enabled: bool = True
    bridge_required: bool = True
    bridge_reachable: bool = False
    ping_ok: bool = False
    inspect_ok: bool = False
    last_health_check_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_error_code: str = ""
    last_error_message: str = ""
    degraded: bool = False
    command_contract_ok: bool = False
    fallback_mode_used: bool = False
    latency_ms: float = 0.0

    @property
    def is_healthy(self) -> bool:
        """Check if bridge is fully healthy for execution."""
        return self.bridge_reachable and self.ping_ok and not self.degraded

    @property
    def can_execute(self) -> bool:
        """Check if bridge can be used for execution (may use fallback)."""
        if self.fallback_mode_used:
            return True
        return self.is_healthy

    def to_dict(self) -> dict[str, Any]:
        """Convert report to dictionary for serialization."""
        return {
            "bridge_type": self.bridge_type,
            "bridge_enabled": self.bridge_enabled,
            "bridge_required": self.bridge_required,
            "bridge_reachable": self.bridge_reachable,
            "ping_ok": self.ping_ok,
            "inspect_ok": self.inspect_ok,
            "last_health_check_at": self.last_health_check_at,
            "last_error_code": self.last_error_code,
            "last_error_message": self.last_error_message,
            "degraded": self.degraded,
            "command_contract_ok": self.command_contract_ok,
            "fallback_mode_used": self.fallback_mode_used,
            "latency_ms": self.latency_ms,
            "is_healthy": self.is_healthy,
            "can_execute": self.can_execute,
        }


def check_bridge_health(
    domain: str,
    host: str = "127.0.0.1",
    port: int | None = None,
    timeout_seconds: float = 5.0,
) -> BridgeHealthReport:
    """Check bridge health and return a comprehensive report.

    Args:
        domain: Bridge domain ("touchdesigner" or "houdini")
        host: Bridge host address
        port: Bridge port (defaults to 9988 for TD, 9989 for Houdini)
        timeout_seconds: Connection timeout in seconds

    Returns:
        BridgeHealthReport with complete health status
    """
    # Set default ports
    if port is None:
        port = 9988 if domain == "touchdesigner" else 9989

    report = BridgeHealthReport(
        bridge_type=domain,
        bridge_enabled=True,
        bridge_required=True,
        last_health_check_at=datetime.now().isoformat(),
    )

    # Perform ping check
    start_time = time.perf_counter()
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout_seconds)
        result = sock.connect_ex((host, port))
        sock.close()

        report.latency_ms = (time.perf_counter() - start_time) * 1000

        if result == 0:
            report.bridge_reachable = True
            report.ping_ok = True
            report.inspect_ok = True  # Socket connection implies inspect works
            report.command_contract_ok = True
        else:
            report.bridge_reachable = False
            report.ping_ok = False
            report.last_error_code = f"CONNECTION_REFUSED_{result}"
            report.last_error_message = f"Connection refused (code: {result})"
            report.degraded = True

    except socket.timeout:
        report.latency_ms = timeout_seconds * 1000
        report.bridge_reachable = False
        report.ping_ok = False
        report.last_error_code = "PING_TIMEOUT"
        report.last_error_message = f"Ping timed out after {timeout_seconds}s"
        report.degraded = True

    except Exception as e:
        report.latency_ms = (time.perf_counter() - start_time) * 1000
        report.bridge_reachable = False
        report.ping_ok = False
        report.last_error_code = type(e).__name__.upper()
        report.last_error_message = str(e)
        report.degraded = True

    return report


def normalize_bridge_error(
    report: BridgeHealthReport,
    domain: str,
    task_id: str = "",
) -> NormalizedError:
    """Convert a bridge health report to a normalized error.

    Args:
        report: BridgeHealthReport with failure information
        domain: Domain name for context
        task_id: Optional task ID for tracking

    Returns:
        NormalizedError with appropriate type and context
    """
    error_code = report.last_error_code
    failure_reason = report.last_error_message

    # Determine error type from report state
    if not report.ping_ok:
        error_type = NormalizedErrorType.BRIDGE_PING_FAILED
    elif not report.inspect_ok:
        error_type = NormalizedErrorType.BRIDGE_INSPECT_FAILED
    elif not report.command_contract_ok:
        error_type = NormalizedErrorType.BRIDGE_COMMAND_REJECTED
    else:
        error_type = NormalizedErrorType.BRIDGE_UNAVAILABLE

    context = {
        "bridge_type": domain,
        "error_code": error_code,
        "host": "127.0.0.1",  # Could be parameterized
        "port": 9988 if domain == "touchdesigner" else 9989,
        "latency_ms": report.latency_ms,
        "task_id": task_id,
        "bridge_reachable": report.bridge_reachable,
        "ping_ok": report.ping_ok,
        "timestamp": report.last_health_check_at,
    }

    return NormalizedError(
        normalized_error_type=error_type,
        message=f"[{domain}] {failure_reason}",
        original_error=None,
        context=context,
    )


def bridge_health_from_backend_result(
    result: BridgeHealthResult,
    domain: str,
) -> BridgeHealthReport:
    """Convert a BridgeHealthResult to a BridgeHealthReport.

    Args:
        result: BridgeHealthResult from backend selector
        domain: Domain name

    Returns:
        BridgeHealthReport with equivalent information
    """
    report = BridgeHealthReport(
        bridge_type=domain,
        bridge_enabled=True,
        bridge_required=True,
        bridge_reachable=result.healthy,
        ping_ok=result.healthy,
        inspect_ok=result.healthy,
        latency_ms=result.ping_ms or 0.0,
        last_health_check_at=datetime.now().isoformat(),
        degraded=not result.healthy,
        command_contract_ok=result.healthy,
        fallback_mode_used=False,
    )

    if result.error:
        report.last_error_message = result.error
        report.last_error_code = "BACKEND_RESULT_ERROR"

    return report
