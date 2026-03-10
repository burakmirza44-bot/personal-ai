"""Recipe Executor Module.

Provides recipe execution with backend selection integration,
bridge executors for TD and Houdini, precondition validation,
and checkpoint/resume support.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.agent_core.backend_policy import BackendPolicy, BackendType
from app.agent_core.backend_result import BackendSelectionResult
from app.agent_core.backend_selector import BackendSelector
from app.core.checkpoint import Checkpoint, StepStatus, create_step_id


# ============================================================================
# Enums
# ============================================================================

class RecipeStatus:
    """Status of a recipe execution."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


class SafetyLevel:
    """Safety level for execution."""
    SAFE = "safe"
    CAUTION = "caution"
    DANGEROUS = "dangerous"
    BLOCKED = "blocked"


# ============================================================================
# Data Classes
# ============================================================================

@dataclass(slots=True)
class ExecutionResult:
    """Result of a single execution step."""

    success: bool = False
    action: str = ""
    result_data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    execution_time_ms: float = 0.0
    backend_used: str = ""
    verified: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "action": self.action,
            "result_data": self.result_data,
            "error": self.error,
            "execution_time_ms": self.execution_time_ms,
            "backend_used": self.backend_used,
            "verified": self.verified,
        }


@dataclass
class Step:
    """A single step in a recipe."""

    step_id: str = ""
    action: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    description: str = ""
    expected_outcome: str = ""
    safety_level: str = SafetyLevel.SAFE
    title: str = ""
    intent: str = ""
    executable_operation: str = ""
    target: str = ""
    verification_hint: str = ""
    requires_focus: bool = False
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "step_id": self.step_id,
            "action": self.action,
            "params": self.params,
            "description": self.description,
            "expected_outcome": self.expected_outcome,
            "safety_level": self.safety_level,
            "title": self.title,
            "intent": self.intent,
            "executable_operation": self.executable_operation,
            "target": self.target,
            "verification_hint": self.verification_hint,
            "requires_focus": self.requires_focus,
            "notes": self.notes,
        }


@dataclass
class Result:
    """Generic result container."""

    success: bool = False
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "message": self.message,
        }


@dataclass
class StepExecutionRecord:
    """Record of a step execution for history."""

    step_id: str = ""
    action: str = ""
    started_at: float = 0.0
    completed_at: float = 0.0
    success: bool = False
    error: str | None = None
    result_data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "step_id": self.step_id,
            "action": self.action,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "success": self.success,
            "error": self.error,
            "result_data": self.result_data,
        }


@dataclass
class Recipe:
    """A recipe defines a sequence of steps to execute."""

    name: str = ""
    description: str = ""
    domain: str = ""
    steps: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    plan_id: str = ""
    # Extended fields for video-to-recipe conversion
    recipe_id: str = ""
    title: str = ""
    task_summary: str = ""
    stages: list[Any] = field(default_factory=list)
    verification_checks: list[Any] = field(default_factory=list)
    confidence: float = 0.0
    ambiguity: list[str] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)
    required_context: str = ""
    required_nodes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "domain": self.domain,
            "steps": self.steps,
            "metadata": self.metadata,
            "plan_id": self.plan_id,
            "recipe_id": self.recipe_id,
            "title": self.title,
            "task_summary": self.task_summary,
            "stages": self.stages,
            "verification_checks": self.verification_checks,
            "confidence": self.confidence,
            "ambiguity": self.ambiguity,
            "provenance": self.provenance,
            "required_context": self.required_context,
            "required_nodes": self.required_nodes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Recipe":
        """Create from dictionary."""
        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            domain=data.get("domain", ""),
            steps=data.get("steps", []),
            metadata=data.get("metadata", {}),
            plan_id=data.get("plan_id", ""),
            recipe_id=data.get("recipe_id", ""),
            title=data.get("title", ""),
            task_summary=data.get("task_summary", ""),
            stages=data.get("stages", []),
            verification_checks=data.get("verification_checks", []),
            confidence=data.get("confidence", 0.0),
            ambiguity=data.get("ambiguity", []),
            provenance=data.get("provenance", {}),
            required_context=data.get("required_context", ""),
            required_nodes=data.get("required_nodes", []),
        )


@dataclass
class VerificationSummary:
    """Summary of verification results."""

    verified: bool = False
    verification_type: str = ""
    confidence: float = 0.0
    issues: list[str] = field(default_factory=list)
    execution_time_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "verified": self.verified,
            "verification_type": self.verification_type,
            "confidence": self.confidence,
            "issues": self.issues,
            "execution_time_ms": self.execution_time_ms,
        }


# ============================================================================
# Fake/Mock Classes for Testing
# ============================================================================

class FakeVerifier:
    """Fake verifier for testing purposes."""

    def __init__(self, result: bool = True):
        """Initialize with expected result.

        Args:
            result: Verification result to return
        """
        self._result = result
        self.call_count = 0

    def verify(self, step: dict[str, Any], result: dict[str, Any]) -> VerificationSummary:
        """Verify a step execution.

        Args:
            step: Step that was executed
            result: Execution result

        Returns:
            VerificationSummary with fake result
        """
        self.call_count += 1
        return VerificationSummary(
            verified=self._result,
            verification_type="fake",
            confidence=1.0,
            issues=[],
        )


# ============================================================================
# Helper Functions
# ============================================================================

def create_recipe_executor(
    domain: str = "touchdesigner",
    dry_run: bool = True,
    enable_checkpoints: bool = False,
    repo_root: str = ".",
) -> RecipeExecutor:
    """Create a recipe executor with default settings.

    Args:
        domain: Execution domain
        dry_run: Whether to simulate execution
        enable_checkpoints: Whether to enable checkpointing
        repo_root: Repository root path

    Returns:
        Configured RecipeExecutor instance
    """
    return RecipeExecutor(
        enable_checkpoints=enable_checkpoints,
        repo_root=repo_root,
    )


def load_and_execute_recipe(
    recipe_path: str,
    domain: str = "touchdesigner",
    dry_run: bool = True,
    policy: BackendPolicy | None = None,
) -> RecipeExecutorResult:
    """Load a recipe from file and execute it.

    Args:
        recipe_path: Path to recipe JSON file
        domain: Execution domain
        dry_run: Whether to simulate execution
        policy: Optional backend policy

    Returns:
        RecipeExecutorResult with execution outcome
    """
    import json
    from pathlib import Path

    # Load recipe
    recipe_file = Path(recipe_path)
    if not recipe_file.exists():
        return RecipeExecutorResult(
            success=False,
            error=f"Recipe file not found: {recipe_path}",
        )

    with open(recipe_file, "r", encoding="utf-8") as f:
        recipe_data = json.load(f)

    # Create executor
    executor = create_recipe_executor(
        domain=domain,
        dry_run=dry_run,
    )

    # Create default policy if not provided
    if policy is None:
        policy = BackendPolicy()

    # Execute
    return executor.execute_recipe(recipe_data, policy, dry_run=dry_run)


@dataclass(slots=True)
class PreconditionsReport:
    """Validation report for recipe execution preconditions.

    Follows the same pattern as existing validation reports in the codebase.
    """

    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        """Check if there are any errors."""
        return len(self.errors) > 0

    @property
    def has_warnings(self) -> bool:
        """Check if there are any warnings."""
        return len(self.warnings) > 0

    def add_error(self, error: str) -> None:
        """Add an error to the report."""
        self.errors.append(error)
        self.valid = False

    def add_warning(self, warning: str) -> None:
        """Add a warning to the report."""
        self.warnings.append(warning)


@dataclass(slots=True)
class RecipeExecutorResult:
    """Result of recipe execution with checkpoint support."""

    success: bool = False
    step_count: int = 0
    step_results: list[dict[str, Any]] = field(default_factory=list)
    selection: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    step_index: int | None = None
    # Checkpoint metadata
    checkpoint_created: bool = False
    checkpoint_id: str | None = None
    checkpoint_saved: bool = False
    resumed_from_checkpoint: bool = False
    resumed_from_step: int | None = None
    completed_steps_from_checkpoint: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "step_count": self.step_count,
            "step_results": self.step_results,
            "selection": self.selection,
            "error": self.error,
            "step_index": self.step_index,
            "checkpoint_created": self.checkpoint_created,
            "checkpoint_id": self.checkpoint_id,
            "checkpoint_saved": self.checkpoint_saved,
            "resumed_from_checkpoint": self.resumed_from_checkpoint,
            "resumed_from_step": self.resumed_from_step,
            "completed_steps_from_checkpoint": self.completed_steps_from_checkpoint,
        }


class BridgeExecutor(ABC):
    """Abstract base class for bridge executors.

    Defines the interface for bridge-based execution across
    different domains (TouchDesigner, Houdini, etc.).
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 9988,
        timeout_seconds: float = 5.0,
    ):
        """Initialize the bridge executor.

        Args:
            host: Bridge server host
            port: Bridge server port
            timeout_seconds: Connection timeout
        """
        self.host = host
        self.port = port
        self.timeout_seconds = timeout_seconds
        self._connected = False

    @abstractmethod
    def ping(self) -> bool:
        """Check if the bridge is available.

        Returns:
            True if bridge is responsive
        """
        pass

    @abstractmethod
    def execute(self, command: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute a command on the bridge.

        Args:
            command: Command name to execute
            params: Optional parameters for the command

        Returns:
            Result dictionary with success status and data
        """
        pass

    @abstractmethod
    def execute_step(self, step: dict[str, Any]) -> dict[str, Any]:
        """Execute a recipe step.

        Args:
            step: Step definition dictionary

        Returns:
            Result dictionary with execution outcome
        """
        pass

    def connect(self) -> bool:
        """Connect to the bridge.

        Returns:
            True if connection successful
        """
        self._connected = self.ping()
        return self._connected

    def disconnect(self) -> None:
        """Disconnect from the bridge."""
        self._connected = False

    @property
    def is_connected(self) -> bool:
        """Check if connected to bridge."""
        return self._connected


class TDBridgeExecutor(BridgeExecutor):
    """Bridge executor for TouchDesigner.

    Communicates with TouchDesigner via the live bridge on port 9988.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 9988,
        timeout_seconds: float = 5.0,
        dry_run: bool = False,
    ):
        """Initialize TD bridge executor.

        Args:
            host: Bridge server host (default: 127.0.0.1)
            port: Bridge server port (default: 9988 for TD)
            timeout_seconds: Connection timeout
            dry_run: If True, simulate execution without bridge calls
        """
        super().__init__(host, port, timeout_seconds)
        self.dry_run = dry_run
        self._client = None

    def _get_client(self):
        """Lazy-initialize TDLiveClient."""
        if self._client is None:
            from app.domains.touchdesigner.td_live_client import TDLiveClient
            self._client = TDLiveClient(
                host=self.host,
                port=self.port,
                timeout_seconds=self.timeout_seconds,
            )
        return self._client

    def ping(self) -> bool:
        """Check if TouchDesigner bridge is available.

        Returns:
            True if bridge is responsive
        """
        if self.dry_run:
            return True
        try:
            client = self._get_client()
            result = client.ping()
            return result.get("status") == "ok" or result.get("ping") == "pong"
        except Exception:
            return False

    def execute(self, command: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute a command on TouchDesigner.

        Args:
            command: Command type (e.g., "create_node", "set_parameter")
            params: Command parameters

        Returns:
            Result dictionary with success, result_data, error
        """
        params = params or {}

        # Dry run mode - return mock success
        if self.dry_run:
            return {
                "success": True,
                "dry_run": True,
                "command": command,
                "params": params,
                "message": f"Dry run: would execute {command}",
            }

        # Real bridge communication
        try:
            from app.domains.touchdesigner.td_live_protocol import (
                TDLiveCommandRequest,
                new_command_id,
            )

            client = self._get_client()

            # Build command request
            request = TDLiveCommandRequest(
                command_id=new_command_id(),
                command_type=command,
                task_id=params.get("task_id", "unknown"),
                target_network=params.get("target_network", "/project1"),
                payload=params.get("payload", params),
                safety_level=params.get("safety_level", "safe"),
            )

            # Send to bridge
            response = client.send_command(request)

            # Map response to result
            return {
                "success": response.status == "ok",
                "command": command,
                "command_id": response.command_id,
                "result_data": response.result,
                "message": response.message,
                "error": None if response.status == "ok" else response.message,
            }

        except Exception as exc:
            return {
                "success": False,
                "command": command,
                "error": str(exc),
                "error_type": type(exc).__name__,
            }

    def execute_step(self, step: dict[str, Any]) -> dict[str, Any]:
        """Execute a recipe step on TouchDesigner.

        Args:
            step: Step definition with action and parameters

        Returns:
            Execution result
        """
        action = step.get("action", "")
        params = step.get("params", {})

        # Merge step metadata into params
        merged_params = {
            **params,
            "task_id": step.get("task_id", step.get("step_id", "unknown")),
            "target_network": step.get("target_network", step.get("target", "/project1")),
            "payload": {
                **params.get("payload", {}),
                "node_type": step.get("node_type", ""),
                "node_path": step.get("node_path", ""),
                "parameter": step.get("parameter", ""),
                "value": step.get("value", ""),
            },
        }

        return self.execute(action, merged_params)


class HoudiniBridgeExecutor(BridgeExecutor):
    """Bridge executor for Houdini.

    Communicates with Houdini via the live bridge on port 9989.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 9989,
        timeout_seconds: float = 5.0,
        dry_run: bool = False,
    ):
        """Initialize Houdini bridge executor.

        Args:
            host: Bridge server host (default: 127.0.0.1)
            port: Bridge server port (default: 9989 for Houdini)
            timeout_seconds: Connection timeout
            dry_run: If True, simulate execution without bridge calls
        """
        super().__init__(host, port, timeout_seconds)
        self.dry_run = dry_run
        self._client = None

    def _get_client(self):
        """Lazy-initialize HoudiniLiveClient."""
        if self._client is None:
            from app.domains.houdini.houdini_live_client import HoudiniLiveClient
            self._client = HoudiniLiveClient(
                host=self.host,
                port=self.port,
                timeout_seconds=self.timeout_seconds,
            )
        return self._client

    def ping(self) -> bool:
        """Check if Houdini bridge is available.

        Returns:
            True if bridge is responsive
        """
        if self.dry_run:
            return True
        try:
            client = self._get_client()
            result = client.ping()
            return result.get("status") == "ok"
        except Exception:
            return False

    def execute(self, command: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute a command on Houdini.

        Args:
            command: Command type (e.g., "create_node", "set_parameter", "run_python")
            params: Command parameters

        Returns:
            Result dictionary with success, result_data, error
        """
        params = params or {}

        # Dry run mode - return mock success
        if self.dry_run:
            return {
                "success": True,
                "dry_run": True,
                "command": command,
                "params": params,
                "message": f"Dry run: would execute {command} in Houdini",
            }

        # Real bridge communication
        try:
            from app.domains.houdini.houdini_live_protocol import (
                HoudiniLiveCommandRequest,
                new_houdini_command_id,
            )

            client = self._get_client()

            # Build command request
            request = HoudiniLiveCommandRequest(
                command_id=new_houdini_command_id(),
                command_type=command,
                task_id=params.get("task_id", "unknown"),
                target_context=params.get("target_context", "/obj"),
                payload=params.get("payload", params),
                safety_level=params.get("safety_level", "safe"),
            )

            # Send to bridge
            response = client.send_command(request)

            # Map response to result
            return {
                "success": response.status == "ok" or response.status == "succeeded",
                "command": command,
                "command_id": response.command_id,
                "result_data": response.result,
                "message": response.message,
                "error": None if response.status in ("ok", "succeeded") else response.message,
            }

        except Exception as exc:
            return {
                "success": False,
                "command": command,
                "error": str(exc),
                "error_type": type(exc).__name__,
            }

    def execute_step(self, step: dict[str, Any]) -> dict[str, Any]:
        """Execute a recipe step on Houdini.

        Args:
            step: Step definition with action and parameters

        Returns:
            Execution result
        """
        action = step.get("action", "")
        params = step.get("params", {})

        # Merge step metadata into params
        merged_params = {
            **params,
            "task_id": step.get("task_id", step.get("step_id", "unknown")),
            "target_context": step.get("target_context", step.get("target", "/obj")),
            "payload": {
                **params.get("payload", {}),
                "node_type": step.get("node_type", ""),
                "node_path": step.get("node_path", ""),
                "parameter": step.get("parameter", ""),
                "value": step.get("value", ""),
            },
        }

        return self.execute(action, merged_params)


class RecipeExecutor:
    """Executes recipes with unified backend selection and checkpoint support.

    Uses BackendSelector for consistent backend selection across
    all recipe steps, with fallback support, safety integration,
    and checkpoint/resume for long-running recipes.
    """

    def __init__(
        self,
        selector: BackendSelector | None = None,
        bridge_executors: dict[str, BridgeExecutor] | None = None,
        enable_checkpoints: bool = False,
        repo_root: str = ".",
        task_id: str = "",
        session_id: str = "",
        dry_run: bool = False,
    ):
        """Initialize the RecipeExecutor.

        Args:
            selector: Optional BackendSelector (creates default if None)
            bridge_executors: Optional dict of domain -> BridgeExecutor
            enable_checkpoints: Whether to enable checkpoint/resume
            repo_root: Repository root for checkpoint storage
            task_id: Task ID for checkpoint tracking
            session_id: Session ID for checkpoint tracking
            dry_run: If True, simulate execution without actual operations
        """
        self._selector = selector or BackendSelector()
        self._bridge_executors = bridge_executors or {}
        self._last_selection: BackendSelectionResult | None = None
        self._enable_checkpoints = enable_checkpoints
        self._repo_root = repo_root
        self._task_id = task_id
        self._session_id = session_id
        self._current_checkpoint: Checkpoint | None = None
        self._dry_run = dry_run

    def register_bridge_executor(self, domain: str, executor: BridgeExecutor) -> None:
        """Register a bridge executor for a domain.

        Args:
            domain: Domain name (e.g., "touchdesigner", "houdini")
            executor: BridgeExecutor instance
        """
        self._bridge_executors[domain] = executor

    def validate_preconditions(
        self,
        recipe: dict[str, Any],
        policy: BackendPolicy,
    ) -> PreconditionsReport:
        """Validate preconditions for recipe execution.

        Args:
            recipe: Recipe to validate
            policy: Backend policy for execution

        Returns:
            PreconditionsReport with validation results
        """
        report = PreconditionsReport(valid=True)

        # Check recipe structure
        if "steps" not in recipe:
            report.add_error("Recipe missing 'steps' field")
            return report

        steps = recipe.get("steps", [])
        if not steps:
            report.add_warning("Recipe has no steps to execute")

        # Check step validity
        for i, step in enumerate(steps):
            if not isinstance(step, dict):
                report.add_error(f"Step {i} is not a dictionary")
            elif "action" not in step:
                report.add_error(f"Step {i} missing 'action' field")

        # Check backend availability
        selection = self._selector.select(policy)
        self._last_selection = selection

        if not selection.is_executable:
            report.add_error(f"No available backend: {selection.message}")

        return report

    def create_checkpoint(
        self,
        recipe: dict[str, Any],
        domain: str,
    ) -> Checkpoint | None:
        """Create a checkpoint for recipe execution.

        Args:
            recipe: Recipe being executed
            domain: Execution domain

        Returns:
            Checkpoint or None if checkpoints disabled
        """
        if not self._enable_checkpoints:
            return None

        # Local import to avoid circular dependency
        from app.core.checkpoint_lifecycle import CheckpointLifecycle

        if not self._task_id:
            return None

        steps = recipe.get("steps", [])
        lifecycle = CheckpointLifecycle(repo_root=self._repo_root)
        checkpoint = lifecycle.create_checkpoint(
            task_id=self._task_id,
            session_id=self._session_id or f"session_{int(time.time())}",
            plan_id=recipe.get("plan_id") or f"recipe_{self._task_id}",
            domain=domain,
            current_goal=recipe.get("description", recipe.get("name", "")),
            steps=steps,
            checkpoint_reason="recipe_start",
        )

        self._current_checkpoint = checkpoint
        self._checkpoint_lifecycle = lifecycle
        return checkpoint

    def update_step_checkpoint(
        self,
        step_index: int,
        status: StepStatus,
        result: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
    ) -> bool:
        """Update checkpoint for a step completion.

        Args:
            step_index: Index of the step
            status: New step status
            result: Optional step result
            error: Optional error information

        Returns:
            True if checkpoint was updated
        """
        if not self._enable_checkpoints or not self._current_checkpoint:
            return False

        # Local import to avoid circular dependency
        from app.core.checkpoint_lifecycle import CheckpointLifecycle

        # Get step ID from checkpoint order
        if step_index >= len(self._current_checkpoint.step_order):
            return False

        step_id = self._current_checkpoint.step_order[step_index]
        verified = result.get("verified", False) if result else False

        try:
            lifecycle = CheckpointLifecycle(repo_root=self._repo_root)
            lifecycle.update_checkpoint(
                checkpoint=self._current_checkpoint,
                step_id=step_id,
                step_status=status,
                step_result=result,
                error=error,
                verified=verified,
            )
            lifecycle.save_checkpoint(self._current_checkpoint)
            return True
        except Exception:
            return False

    def mark_recipe_completed(self) -> bool:
        """Mark recipe as completed in checkpoint.

        Returns:
            True if checkpoint was updated
        """
        if not self._enable_checkpoints or not self._current_checkpoint:
            return False

        # Local import to avoid circular dependency
        from app.core.checkpoint_lifecycle import CheckpointLifecycle, CheckpointStatus

        try:
            lifecycle = CheckpointLifecycle(repo_root=self._repo_root)
            lifecycle.mark_checkpoint_status(
                checkpoint=self._current_checkpoint,
                status=CheckpointStatus.COMPLETED,
                reason="Recipe completed successfully",
            )
            lifecycle.save_checkpoint(self._current_checkpoint)
            return True
        except Exception:
            return False

    def attempt_resume(
        self,
        recipe: dict[str, Any],
        domain: str,
    ) -> tuple[bool, int]:
        """Attempt to resume from checkpoint.

        Args:
            recipe: Recipe to execute
            domain: Execution domain

        Returns:
            Tuple of (resumed, skip_steps_count)
        """
        if not self._enable_checkpoints or not self._task_id:
            return False, 0

        from app.core.checkpoint_resume import ResumeManager

        resume_manager = ResumeManager(
            lifecycle=self._checkpoint_lifecycle,
            repo_root=self._repo_root,
        )

        result = resume_manager.attempt_resume(
            task_id=self._task_id,
            plan_id=recipe.get("plan_id"),
        )

        if result.success and result.resume_context:
            self._current_checkpoint = result.resume_context.checkpoint
            skip_count = len(result.resume_context.resume_decision.steps_to_skip)
            return True, skip_count

        return False, 0

    def execute_recipe(
        self,
        recipe: dict[str, Any],
        policy: BackendPolicy,
        dry_run: bool = False,
        attempt_resume: bool = True,
    ) -> RecipeExecutorResult:
        """Execute a complete recipe with checkpoint support.

        Args:
            recipe: Recipe to execute
            policy: Backend policy for execution
            dry_run: Force dry-run mode
            attempt_resume: Whether to attempt resume from checkpoint

        Returns:
            RecipeExecutorResult with execution status and checkpoint metadata
        """
        result = RecipeExecutorResult()
        domain = policy.domain

        # Validate preconditions
        report = self.validate_preconditions(recipe, policy)
        if not report.valid:
            result.success = False
            result.error = "Precondition validation failed"
            return result

        # Override policy if dry_run requested
        if dry_run:
            policy = BackendPolicy.for_dry_run(domain=policy.domain)

        # Select backend
        selection = self._selector.select(policy)
        self._last_selection = selection
        result.selection = selection.to_dict()

        if not selection.is_executable:
            result.success = False
            result.error = f"No executable backend: {selection.message}"
            return result

        # Attempt resume if enabled
        resumed = False
        skip_steps = 0
        if attempt_resume and self._enable_checkpoints:
            resumed, skip_steps = self.attempt_resume(recipe, domain)
            result.resumed_from_checkpoint = resumed
            result.resumed_from_step = skip_steps if resumed else None
            result.completed_steps_from_checkpoint = skip_steps

        # Create checkpoint if not resuming
        if self._enable_checkpoints and not resumed:
            checkpoint = self.create_checkpoint(recipe, domain)
            if checkpoint:
                result.checkpoint_created = True
                result.checkpoint_id = checkpoint.checkpoint_id
                result.checkpoint_saved = True

        # Execute steps
        steps = recipe.get("steps", [])
        result.step_count = len(steps)
        step_results = []

        for i, step in enumerate(steps):
            # Skip already completed steps from resume
            if resumed and i < skip_steps:
                continue

            # Mark step as in-progress in checkpoint
            if self._enable_checkpoints:
                self.update_step_checkpoint(i, StepStatus.IN_PROGRESS)

            step_result = self.execute_step(step, selection, domain)
            step_results.append(step_result)

            # Update checkpoint based on result
            if self._enable_checkpoints:
                if step_result.get("success", False):
                    self.update_step_checkpoint(
                        i,
                        StepStatus.COMPLETED_VERIFIED if step_result.get("verified") else StepStatus.COMPLETED,
                        step_result,
                    )
                else:
                    self.update_step_checkpoint(
                        i,
                        StepStatus.FAILED,
                        step_result,
                        error={"message": step_result.get("error", "Unknown error")},
                    )

            # Stop on failure unless continue_on_error
            if not step_result.get("success", False):
                if not step.get("continue_on_error", False):
                    result.success = False
                    result.error = f"Step {i} failed: {step_result.get('error', 'Unknown error')}"
                    result.step_index = i
                    result.step_results = step_results
                    return result

        result.success = True
        result.step_results = step_results

        # Mark checkpoint as completed
        if self._enable_checkpoints:
            self.mark_recipe_completed()

        return result

    def execute_step(
        self,
        step: dict[str, Any],
        selection: BackendSelectionResult | None = None,
        domain: str = "",
    ) -> dict[str, Any]:
        """Execute a single recipe step.

        Args:
            step: Step definition to execute
            selection: Optional pre-computed backend selection
            domain: Domain for execution

        Returns:
            Step execution result
        """
        # Use provided selection or create new one
        if selection is None:
            if not domain:
                return {
                    "success": False,
                    "error": "No domain specified and no selection provided",
                }

            policy = BackendPolicy(domain=domain)
            selection = self._selector.select(policy)

        # Route to appropriate executor based on backend type
        backend = selection.selected_backend

        if backend == BackendType.DRY_RUN:
            return self._execute_dry_run(step)

        if backend == BackendType.BRIDGE:
            return self._execute_via_bridge(step, domain or selection.domain)

        if backend == BackendType.UI:
            return self._execute_via_ui(step)

        if backend == BackendType.DIRECT_API:
            return self._execute_via_direct_api(step, domain or selection.domain)

        return {
            "success": False,
            "error": f"No handler for backend type: {backend.value}",
        }

    def _execute_dry_run(self, step: dict[str, Any]) -> dict[str, Any]:
        """Execute step in dry-run mode (simulation).

        Args:
            step: Step to simulate

        Returns:
            Simulated result
        """
        return {
            "success": True,
            "dry_run": True,
            "action": step.get("action", "unknown"),
            "message": f"Dry-run: Would execute {step.get('action', 'unknown')}",
        }

    def _execute_via_bridge(self, step: dict[str, Any], domain: str) -> dict[str, Any]:
        """Execute step via bridge connection.

        Args:
            step: Step to execute
            domain: Target domain

        Returns:
            Execution result from bridge
        """
        executor = self._bridge_executors.get(domain)

        if executor is None:
            # Create default executor
            if domain == "touchdesigner":
                executor = TDBridgeExecutor()
            elif domain == "houdini":
                executor = HoudiniBridgeExecutor()
            else:
                return {
                    "success": False,
                    "error": f"No bridge executor for domain: {domain}",
                }

        return executor.execute_step(step)

    def _execute_via_ui(self, step: dict[str, Any]) -> dict[str, Any]:
        """Execute step via UI automation.

        Args:
            step: Step to execute

        Returns:
            Execution result from UI automation
        """
        # Placeholder for UI automation integration
        # Real implementation would route to UI automation system
        return {
            "success": False,
            "error": "UI automation not implemented",
            "action": step.get("action", "unknown"),
        }

    def _execute_via_direct_api(self, step: dict[str, Any], domain: str) -> dict[str, Any]:
        """Execute step via direct API.

        Args:
            step: Step to execute
            domain: Target domain

        Returns:
            Execution result from direct API
        """
        # Direct API is primarily for Houdini (hou module)
        if domain != "houdini":
            return {
                "success": False,
                "error": f"No direct API for domain: {domain}",
            }

        try:
            import hou

            # Execute using hou module
            action = step.get("action", "")
            params = step.get("params", {})

            # Placeholder for actual hou-based execution
            return {
                "success": True,
                "action": action,
                "message": f"Direct API: Would execute {action}",
            }
        except ImportError:
            return {
                "success": False,
                "error": "Houdini (hou) module not available",
            }

    @property
    def last_selection(self) -> BackendSelectionResult | None:
        """Get the last backend selection result."""
        return self._last_selection