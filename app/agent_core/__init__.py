"""Agent Core Module.

Provides core agent functionality including action dispatch,
backend selection, safety mechanisms, and agent loop state machine.
"""

from app.agent_core.agent_loop import (
    AgentLoopMonitor,
    AgentLoopResult,
    AgentStepResult,
    ComplexityLevel,
    LoopState,
    PlanState,
    build_replan_context,
    build_subgoal_context,
    estimate_complexity,
    propose_for_subgoal,
    should_trigger_replan,
    should_use_long_horizon_plan,
)
from app.agent_core.backend_policy import BackendPolicy, BackendType
from app.agent_core.backend_result import (
    BackendSelectionResult,
    BridgeHealthResult,
    SafetyCheckResult,
    SelectionStatus,
)
from app.agent_core.backend_selector import BackendSelector, get_default_selector, select_backend

__all__ = [
    # Agent Loop
    "AgentLoopMonitor",
    "AgentLoopResult",
    "AgentStepResult",
    "ComplexityLevel",
    "LoopState",
    "PlanState",
    "build_replan_context",
    "build_subgoal_context",
    "estimate_complexity",
    "propose_for_subgoal",
    "should_trigger_replan",
    "should_use_long_horizon_plan",
    # Policy
    "BackendPolicy",
    "BackendType",
    # Result
    "BackendSelectionResult",
    "BridgeHealthResult",
    "SafetyCheckResult",
    "SelectionStatus",
    # Selector
    "BackendSelector",
    "get_default_selector",
    "select_backend",
]