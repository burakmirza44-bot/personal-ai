"""Core runtime infrastructure.

Provides runtime memory management, bridge health monitoring,
checkpoint/resume functionality, unified error handling,
and local-first inference orchestration across all execution paths.

LOCAL-FIRST DEFAULT:
All inference calls route through InferenceOrchestrator which enforces
local-first defaults with Ollama as the preferred provider. Remote
providers (Gemini, OpenAI) are only used when explicitly allowed via
policy configuration.
"""

from app.core.bridge_health import (
    BridgeHealthReport,
    check_bridge_health,
    normalize_bridge_error,
)
from app.core.checkpoint import (
    BridgeHealthSummary,
    Checkpoint,
    CheckpointStatus,
    ExecutionBackendSummary,
    MemoryContextSummary,
    RepairState,
    RetryState,
    StepState,
    StepStatus,
    SubgoalState,
    VerificationSummary,
    create_checkpoint_id,
    create_step_id,
    create_subgoal_id,
)
from app.core.checkpoint_lifecycle import (
    CheckpointBoundaryDetector,
    CheckpointLifecycle,
    CheckpointValidationResult,
)
from app.core.checkpoint_resume import (
    ResumeContext,
    ResumeDecision,
    ResumeManager,
    ResumeResult,
    should_attempt_resume,
)
from app.core.memory_runtime import (
    RuntimeMemoryContext,
    build_runtime_memory_context,
    get_memory_influence_summary,
)

# Unified inference orchestrator - local-first default
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

__all__ = [
    # Bridge health
    "BridgeHealthReport",
    "check_bridge_health",
    "normalize_bridge_error",
    # Checkpoint
    "Checkpoint",
    "CheckpointStatus",
    "StepState",
    "StepStatus",
    "SubgoalState",
    "RetryState",
    "RepairState",
    "BridgeHealthSummary",
    "ExecutionBackendSummary",
    "MemoryContextSummary",
    "VerificationSummary",
    "create_checkpoint_id",
    "create_step_id",
    "create_subgoal_id",
    # Checkpoint lifecycle
    "CheckpointLifecycle",
    "CheckpointBoundaryDetector",
    "CheckpointValidationResult",
    # Checkpoint resume
    "ResumeManager",
    "ResumeDecision",
    "ResumeContext",
    "ResumeResult",
    "should_attempt_resume",
    # Memory runtime
    "RuntimeMemoryContext",
    "build_runtime_memory_context",
    "get_memory_influence_summary",
    # Inference orchestrator (local-first default)
    "InferenceOrchestrator",
    "InferenceSession",
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
