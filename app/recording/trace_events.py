"""Runtime trace event schema for structured session/session trace collection.

This module defines the standardized trace event model used across all runtime paths:
- Task runner
- Runtime loop
- Houdini/TouchDesigner execution
- Recipe executor
- Retry/repair paths
- Verification paths
- Memory retrieval/writeback paths
- Provider/backend routing

The schema is designed to be:
- Machine-friendly for downstream processing
- Rich enough for learning and debugging
- Linked to outcomes and verification
- Filterable for quality
- Transformable into finetune examples
"""

from __future__ import annotations

__all__ = [
    "RuntimeTraceEvent",
    "TraceEventType",
    "TraceSessionSummary",
    "TraceOutcome",
    "RuntimeStage",
    "emit_trace_event",
    "new_trace_id",
    "TRACE_SCHEMA_VERSION",
]

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4


TRACE_SCHEMA_VERSION = "runtime_trace_v1"


def _now_iso() -> str:
    """Return current UTC timestamp in ISO format."""
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def new_trace_id(prefix: str = "trace") -> str:
    """Generate a unique trace ID."""
    stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    return f"{prefix}_{stamp}_{uuid4().hex[:8]}"


class TraceEventType(str, Enum):
    """Standardized trace event types across the runtime.

    Events are categorized by runtime stage and purpose.
    """

    # Session lifecycle
    SESSION_STARTED = "session_started"
    SESSION_PAUSED = "session_paused"
    SESSION_RESUMED = "session_resumed"
    SESSION_COMPLETED = "session_completed"
    SESSION_FAILED = "session_failed"

    # Task lifecycle
    TASK_RECEIVED = "task_received"
    TASK_ROUTED = "task_routed"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"

    # Planning
    PLAN_CREATED = "plan_created"
    SUBGOAL_SELECTED = "subgoal_selected"
    PLAN_UPDATED = "plan_updated"

    # Execution
    STEP_EXECUTED = "step_executed"
    ACTION_PREDICTED = "action_predicted"
    ACTION_EXECUTED = "action_executed"
    COMMAND_SENT = "command_sent"

    # Backend/Provider selection
    BACKEND_SELECTED = "backend_selected"
    PROVIDER_SELECTED = "provider_selected"

    # Memory
    MEMORY_RETRIEVED = "memory_retrieved"
    MEMORY_WRITTEN = "memory_written"
    PATTERN_INJECTED = "pattern_injected"

    # Verification
    VERIFICATION_STARTED = "verification_started"
    VERIFICATION_COMPLETED = "verification_completed"

    # Retry/Repair
    RETRY_DECIDED = "retry_decided"
    REPAIR_ATTEMPTED = "repair_attempted"
    ERROR_NORMALIZED = "error_normalized"
    FIX_PATTERN_FOUND = "fix_pattern_found"
    FIX_PATTERN_PROMOTED = "fix_pattern_promoted"
    RECOVERY_SUCCEEDED = "recovery_succeeded"
    ERROR_LOOP_COMPLETED = "error_loop_completed"

    # Checkpointing
    CHECKPOINT_SAVED = "checkpoint_saved"
    CHECKPOINT_LOADED = "checkpoint_loaded"

    # Bridge
    BRIDGE_HEALTH_CHECKED = "bridge_health_checked"

    # Quality
    QUALITY_EVALUATED = "quality_evaluated"

    # Screen Feedback
    SCREEN_FEEDBACK_EMITTED = "screen_feedback_emitted"


class RuntimeStage(str, Enum):
    """Runtime execution stages."""

    INTAKE = "intake"
    ROUTING = "routing"
    MEMORY_GATE = "memory_gate"
    PLAN_GATE = "plan_gate"
    EXECUTION = "execution"
    VERIFICATION = "verification"
    ERROR_GATE = "error_gate"
    PERSIST_GATE = "persist_gate"
    DECIDER = "decider"


class TraceOutcome(str, Enum):
    """Outcome labels for trace events."""

    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"
    SKIPPED = "skipped"
    DRY_RUN = "dry_run"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class RuntimeTraceEvent:
    """A structured runtime trace event.

    This is the primary trace record emitted by all runtime paths.
    It captures enough context for later learning, debugging, and finetune.
    """

    # Identity
    trace_id: str
    session_id: str
    event_id: str
    event_type: str  # TraceEventType value
    timestamp: str

    # Context
    domain: str = ""
    task_id: str = ""
    plan_id: str = ""
    step_id: str = ""
    runtime_stage: str = ""  # RuntimeStage value

    # Task context
    task_summary: str = ""
    current_goal: str = ""
    current_subgoal: str = ""

    # Input context
    input_context_summary: dict[str, Any] = field(default_factory=dict)

    # Provider/Backend
    selected_provider: str = ""
    provider_strategy: str = ""
    selected_backend: str = ""
    backend_reason: str = ""

    # Bridge health
    bridge_health_summary: dict[str, Any] = field(default_factory=dict)

    # Memory
    memory_summary: dict[str, Any] = field(default_factory=dict)
    patterns_used: list[str] = field(default_factory=list)

    # Prediction/Action
    prediction_summary: dict[str, Any] = field(default_factory=dict)
    action_summary: dict[str, Any] = field(default_factory=dict)
    command_summary: dict[str, Any] = field(default_factory=dict)

    # Verification
    verification_summary: dict[str, Any] = field(default_factory=dict)
    verification_passed: bool | None = None

    # Error/Retry/Repair
    normalized_error_summary: dict[str, Any] = field(default_factory=dict)
    retry_summary: dict[str, Any] = field(default_factory=dict)
    repair_summary: dict[str, Any] = field(default_factory=dict)

    # Outcome
    outcome: str = "unknown"  # TraceOutcome value
    outcome_label: str = ""
    final_status: str = ""

    # Checkpoint
    checkpoint_summary: dict[str, Any] = field(default_factory=dict)

    # Evidence references
    artifact_refs: list[str] = field(default_factory=list)
    screenshot_refs: list[str] = field(default_factory=list)

    # Quality signals
    quality_score: float = 0.0
    quality_status: str = "pending"

    # Schema
    schema_version: str = TRACE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return asdict(self)

    def to_json(self) -> str:
        """Serialize to JSON."""
        return json.dumps(self.to_dict(), ensure_ascii=True)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RuntimeTraceEvent":
        """Deserialize from dictionary."""
        return cls(
            trace_id=str(data.get("trace_id", "")),
            session_id=str(data.get("session_id", "")),
            event_id=str(data.get("event_id", "")),
            event_type=str(data.get("event_type", "")),
            timestamp=str(data.get("timestamp", "")),
            domain=str(data.get("domain", "")),
            task_id=str(data.get("task_id", "")),
            plan_id=str(data.get("plan_id", "")),
            step_id=str(data.get("step_id", "")),
            runtime_stage=str(data.get("runtime_stage", "")),
            task_summary=str(data.get("task_summary", "")),
            current_goal=str(data.get("current_goal", "")),
            current_subgoal=str(data.get("current_subgoal", "")),
            input_context_summary=dict(data.get("input_context_summary", {})),
            selected_provider=str(data.get("selected_provider", "")),
            provider_strategy=str(data.get("provider_strategy", "")),
            selected_backend=str(data.get("selected_backend", "")),
            backend_reason=str(data.get("backend_reason", "")),
            bridge_health_summary=dict(data.get("bridge_health_summary", {})),
            memory_summary=dict(data.get("memory_summary", {})),
            patterns_used=list(data.get("patterns_used", [])),
            prediction_summary=dict(data.get("prediction_summary", {})),
            action_summary=dict(data.get("action_summary", {})),
            command_summary=dict(data.get("command_summary", {})),
            verification_summary=dict(data.get("verification_summary", {})),
            verification_passed=data.get("verification_passed"),
            normalized_error_summary=dict(data.get("normalized_error_summary", {})),
            retry_summary=dict(data.get("retry_summary", {})),
            repair_summary=dict(data.get("repair_summary", {})),
            outcome=str(data.get("outcome", "unknown")),
            outcome_label=str(data.get("outcome_label", "")),
            final_status=str(data.get("final_status", "")),
            checkpoint_summary=dict(data.get("checkpoint_summary", {})),
            artifact_refs=list(data.get("artifact_refs", [])),
            screenshot_refs=list(data.get("screenshot_refs", [])),
            quality_score=float(data.get("quality_score", 0.0)),
            quality_status=str(data.get("quality_status", "pending")),
            schema_version=str(data.get("schema_version", TRACE_SCHEMA_VERSION)),
        )

    @classmethod
    def from_json(cls, text: str) -> "RuntimeTraceEvent":
        """Deserialize from JSON."""
        payload = json.loads(text)
        if not isinstance(payload, dict):
            raise ValueError("RuntimeTraceEvent JSON must decode to an object")
        return cls.from_dict(payload)


@dataclass(slots=True)
class TraceSessionSummary:
    """Summary of a trace collection session."""

    trace_id: str
    session_id: str
    domain: str
    task_id: str
    started_at: str
    ended_at: str = ""
    event_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    retry_count: int = 0
    repair_count: int = 0
    final_outcome: str = "unknown"
    quality_score: float = 0.0
    finetune_candidate_count: int = 0
    finetune_exportable: bool = False
    schema_version: str = TRACE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return asdict(self)


def emit_trace_event(
    trace_id: str,
    session_id: str,
    event_type: TraceEventType | str,
    domain: str = "",
    task_id: str = "",
    runtime_stage: RuntimeStage | str = "",
    **kwargs: Any,
) -> RuntimeTraceEvent:
    """Factory function to create a RuntimeTraceEvent.

    Args:
        trace_id: Trace collection ID
        session_id: Session ID
        event_type: Event type enum or string
        domain: Domain (houdini, touchdesigner, etc.)
        task_id: Task ID
        runtime_stage: Runtime stage enum or string
        **kwargs: Additional event fields

    Returns:
        RuntimeTraceEvent instance
    """
    event_type_str = event_type.value if isinstance(event_type, TraceEventType) else str(event_type)
    stage_str = runtime_stage.value if isinstance(runtime_stage, RuntimeStage) else str(runtime_stage)

    event_id = f"evt_{uuid4().hex[:10]}"

    return RuntimeTraceEvent(
        trace_id=trace_id,
        session_id=session_id,
        event_id=event_id,
        event_type=event_type_str,
        timestamp=_now_iso(),
        domain=domain,
        task_id=task_id,
        runtime_stage=stage_str,
        **kwargs,
    )