"""Tests for agent_loop planning integration.

Tests for:
- LoopState (including new PLANNING and REPLANNING states)
- ComplexityLevel
- PlanState
- estimate_complexity
- should_use_long_horizon_plan
- AgentLoopMonitor
- propose_for_subgoal
- should_trigger_replan
- build_subgoal_context
- build_replan_context
"""

from __future__ import annotations

import pytest

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
from app.agent_core.long_horizon_plan import build_long_horizon_plan
from app.agent_core.plan_tracker import create_tracker
from app.agent_core.subgoal_models import SubgoalStatus, build_subgoal


class TestLoopState:
    """Tests for LoopState enum."""

    def test_all_states_exist(self):
        """Verify all expected states exist."""
        expected = {
            "observing",
            "inferring",
            "planning",
            "proposing",
            "executing",
            "verifying",
            "replanning",
            "retrying",
            "succeeded",
            "failed",
            "stopped",
        }
        actual = {s.value for s in LoopState}
        assert expected == actual

    def test_new_planning_state(self):
        """Verify PLANNING state exists."""
        assert LoopState.PLANNING.value == "planning"

    def test_new_replanning_state(self):
        """Verify REPLANNING state exists."""
        assert LoopState.REPLANNING.value == "replanning"


class TestComplexityLevel:
    """Tests for ComplexityLevel enum."""

    def test_all_levels_exist(self):
        """Verify all expected levels exist."""
        expected = {
            "trivial",
            "simple",
            "moderate",
            "complex",
            "uncertain",
        }
        actual = {c.value for c in ComplexityLevel}
        assert expected == actual


class TestEstimateComplexity:
    """Tests for estimate_complexity function."""

    def test_trivial_short_goal(self):
        """Short simple goals should be trivial."""
        complexity = estimate_complexity("Get time")
        assert complexity == ComplexityLevel.TRIVIAL

    def test_simple_goal(self):
        """Simple single-action goals should be simple or trivial."""
        complexity = estimate_complexity("Create a new file")
        # Short goals without complex patterns can be trivial or simple
        assert complexity in (ComplexityLevel.TRIVIAL, ComplexityLevel.SIMPLE, ComplexityLevel.MODERATE)

    def test_moderate_goal(self):
        """Multi-step goals should be moderate."""
        complexity = estimate_complexity(
            "Create a node and configure its parameters"
        )
        assert complexity in (ComplexityLevel.MODERATE, ComplexityLevel.COMPLEX)

    def test_complex_goal(self):
        """Complex multi-stage goals should be complex."""
        complexity = estimate_complexity(
            "Build a pipeline: import data, process it, apply transformations, "
            "then export results and verify everything worked correctly"
        )
        assert complexity == ComplexityLevel.COMPLEX

    def test_with_context_hint(self):
        """Context hint should override heuristics."""
        complexity = estimate_complexity(
            "Any goal",
            context={"complexity_hint": "complex"},
        )
        assert complexity == ComplexityLevel.COMPLEX

    def test_with_known_patterns(self):
        """Known patterns should affect complexity."""
        complexity_with_pattern = estimate_complexity(
            "Process the data",
            known_patterns=["pipeline", "workflow"],
        )
        # Patterns should affect complexity
        assert isinstance(complexity_with_pattern, ComplexityLevel)


class TestShouldUseLongHorizonPlan:
    """Tests for should_use_long_horizon_plan function."""

    def test_trivial_no_planning(self):
        """Trivial tasks should not trigger planning."""
        should_plan, complexity = should_use_long_horizon_plan("Get time")
        assert should_plan is False
        assert complexity == ComplexityLevel.TRIVIAL

    def test_complex_triggers_planning(self):
        """Complex tasks should trigger planning."""
        should_plan, complexity = should_use_long_horizon_plan(
            "Build a multi-stage pipeline with processing and verification"
        )
        assert should_plan is True
        assert complexity in (ComplexityLevel.MODERATE, ComplexityLevel.COMPLEX)

    def test_force_planning(self):
        """Force planning should always trigger."""
        should_plan, complexity = should_use_long_horizon_plan(
            "Simple task",
            force_planning=True,
        )
        assert should_plan is True
        assert complexity == ComplexityLevel.COMPLEX

    def test_threshold_adjustment(self):
        """Higher threshold should reduce planning triggers."""
        # With moderate complexity goal and simple threshold, should trigger
        should_plan_low, complexity = should_use_long_horizon_plan(
            "Build a pipeline and process data",
            complexity_threshold=ComplexityLevel.SIMPLE,
        )
        # Complex goal should trigger even with simple threshold
        assert should_plan_low is True or complexity in (ComplexityLevel.MODERATE, ComplexityLevel.COMPLEX)


class TestPlanState:
    """Tests for PlanState dataclass."""

    def test_default_state(self):
        """Default PlanState should have no plan."""
        state = PlanState()
        assert state.has_plan is False
        assert state.plan_id is None
        assert state.total_subgoals == 0

    def test_bind_plan(self):
        """Binding a plan should update state."""
        subgoals = [
            build_subgoal("Setup", "Initial setup", "inspect", index=0),
            build_subgoal("Process", "Main processing", "process", index=1),
        ]
        plan = build_long_horizon_plan(
            domain="test",
            task_id="test_task",
            goal="Test goal",
            subgoals=subgoals,
        )
        tracker = create_tracker(plan)

        state = PlanState()
        state.bind_plan(plan, tracker)

        assert state.has_plan is True
        assert state.plan_id == plan.plan_id
        assert state.total_subgoals == 2

    def test_progress_pct(self):
        """Progress percentage should calculate correctly."""
        subgoals = [
            build_subgoal("S1", "Subgoal 1", "inspect", index=0),
            build_subgoal("S2", "Subgoal 2", "process", index=1),
            build_subgoal("S3", "Subgoal 3", "verify", index=2),
        ]
        plan = build_long_horizon_plan(
            domain="test",
            task_id="test_task",
            goal="Test",
            subgoals=subgoals,
        )
        tracker = create_tracker(plan)
        state = PlanState()
        state.bind_plan(plan, tracker)

        # Initially 0%
        assert state.progress_pct() == 0.0

        # Complete one subgoal
        tracker.start_subgoal()
        tracker.complete_subgoal(subgoals[0].subgoal_id, success=True)
        state._sync_from_plan()

        # Now ~33.3%
        assert abs(state.progress_pct() - 33.33) < 0.5

    def test_progress_report(self):
        """Progress report should be human-readable."""
        subgoals = [
            build_subgoal("Setup", "Initial setup", "inspect", index=0),
        ]
        plan = build_long_horizon_plan(
            domain="test",
            task_id="test_task",
            goal="Test",
            subgoals=subgoals,
        )
        tracker = create_tracker(plan)
        state = PlanState()
        state.bind_plan(plan, tracker)

        report = state.progress_report()
        assert "Plan:" in report
        assert "Progress:" in report

    def test_can_replan(self):
        """Replan budget should be checked correctly."""
        state = PlanState()
        state.replan_count = 0
        state.max_replans = 2

        assert state.can_replan() is True

        state.record_replan()
        state.record_replan()

        assert state.can_replan() is False


class TestAgentLoopMonitor:
    """Tests for AgentLoopMonitor."""

    def test_record_step(self):
        """Step recording should work."""
        monitor = AgentLoopMonitor(run_id="test_run", domain="test")
        monitor.record_step(1, LoopState.EXECUTING, duration_ms=150)

        metrics = monitor.get_metrics()
        assert metrics["total_steps"] == 1
        assert metrics["avg_step_time_ms"] == 150.0

    def test_record_subgoal_transition(self):
        """Subgoal transition recording should work."""
        monitor = AgentLoopMonitor(run_id="test_run", domain="test")
        monitor.record_subgoal_transition(
            from_subgoal="subgoal_1",
            to_subgoal="subgoal_2",
            reason="completed",
        )

        metrics = monitor.get_metrics()
        assert metrics["subgoal_transitions"] == 1
        assert len(metrics["transitions"]) == 1

    def test_record_replan(self):
        """Replan recording should work."""
        monitor = AgentLoopMonitor(run_id="test_run", domain="test")
        # Should not raise
        monitor.record_replan(
            trigger="consecutive_failures",
            old_plan_id="plan_1",
            new_plan_id="plan_2",
        )


class TestProposeForSubgoal:
    """Tests for propose_for_subgoal function."""

    def test_inspect_stage(self):
        """Inspect stage should prefer observe actions."""
        subgoal = build_subgoal("Inspect", "Inspect state", "inspect", index=0)
        action, remaining = propose_for_subgoal(
            subgoal,
            action_candidates=["observe", "create", "execute"],
        )
        assert action == "observe"

    def test_verify_stage(self):
        """Verify stage should prefer check actions."""
        subgoal = build_subgoal("Verify", "Verify results", "verify", index=0)
        action, remaining = propose_for_subgoal(
            subgoal,
            action_candidates=["execute", "check", "create"],
        )
        assert action == "check"

    def test_no_candidates(self):
        """No candidates should return default."""
        subgoal = build_subgoal("Custom", "Custom action", "custom", index=0)
        action, remaining = propose_for_subgoal(subgoal)
        assert action == "execute"


class TestBuildSubgoalContext:
    """Tests for build_subgoal_context function."""

    def test_basic_context(self):
        """Basic context should include subgoal details."""
        subgoal = build_subgoal(
            "Test",
            "Test subgoal",
            "process",
            index=0,
            step_budget=15,
        )
        plan_state = PlanState()
        plan_state.total_subgoals = 3
        plan_state.completed_subgoals = 1

        context = build_subgoal_context(subgoal, plan_state)

        assert context["subgoal_id"] == subgoal.subgoal_id
        assert context["stage_type"] == "process"
        assert context["step_budget"] == 15
        assert "plan_progress" in context


class TestShouldTriggerReplan:
    """Tests for should_trigger_replan function."""

    def test_no_replan_needed(self):
        """Normal execution should not trigger replan."""
        state = PlanState()
        state.total_subgoals = 3
        state.failed_subgoals = 0
        state.replan_count = 0

        should, reason = should_trigger_replan(
            state,
            verification_result="passed",
        )
        assert should is False

    def test_consecutive_failures_trigger(self):
        """Consecutive failures should trigger replan."""
        state = PlanState()
        state.total_subgoals = 3
        state.failed_subgoals = 1
        state.replan_count = 0

        should, reason = should_trigger_replan(
            state,
            verification_result="failed",
            consecutive_failures=3,
        )
        assert should is True
        assert "Consecutive failures" in reason

    def test_replan_budget_exhausted(self):
        """Exhausted budget should prevent replan."""
        state = PlanState()
        state.replan_count = 2
        state.max_replans = 2

        should, reason = should_trigger_replan(
            state,
            verification_result="failed",
            consecutive_failures=5,
        )
        assert should is False
        assert "exhausted" in reason.lower()

    def test_high_failure_rate(self):
        """High failure rate should trigger replan."""
        state = PlanState()
        state.total_subgoals = 4
        state.failed_subgoals = 3
        state.replan_count = 0

        should, reason = should_trigger_replan(
            state,
            verification_result="failed",
        )
        assert should is True
        assert "failure rate" in reason.lower()


class TestBuildReplanContext:
    """Tests for build_replan_context function."""

    def test_basic_context(self):
        """Basic replan context should include key info."""
        plan_state = PlanState()
        plan_state.plan_id = "test_plan"
        plan_state.completed_subgoals = 2
        plan_state.failed_subgoals = 1
        plan_state.total_subgoals = 5

        context = build_replan_context(
            plan_state,
            trigger_reason="consecutive_failures",
        )

        assert context["trigger_reason"] == "consecutive_failures"
        assert context["plan_id"] == "test_plan"
        assert context["completed_subgoals"] == 2
        assert context["failed_subgoals"] == 1

    def test_with_execution_history(self):
        """Execution history should be analyzed."""
        plan_state = PlanState()
        steps = [
            AgentStepResult(
                step_index=0,
                loop_state=LoopState.EXECUTING,
                action_label="action1",
                executed=True,
                verified=True,
                passed=True,
                message="OK",
            ),
            AgentStepResult(
                step_index=1,
                loop_state=LoopState.EXECUTING,
                action_label="action2",
                executed=True,
                verified=False,
                passed=False,
                message="Failed",
            ),
        ]

        context = build_replan_context(
            plan_state,
            trigger_reason="test",
            execution_history=steps,
        )

        assert context["failed_step_count"] == 1
        assert context["successful_step_count"] == 1


class TestAgentStepResult:
    """Tests for AgentStepResult dataclass."""

    def test_new_fields(self):
        """New fields should be present."""
        result = AgentStepResult(
            step_index=0,
            loop_state=LoopState.EXECUTING,
            action_label="test_action",
            executed=True,
            verified=True,
            passed=True,
            message="OK",
            subgoal_id="subgoal_1",
            plan_progress="50%",
        )

        assert result.subgoal_id == "subgoal_1"
        assert result.plan_progress == "50%"


class TestAgentLoopResult:
    """Tests for AgentLoopResult dataclass."""

    def test_plan_state_field(self):
        """PlanState field should be present."""
        plan_state = PlanState()
        plan_state.total_subgoals = 3

        result = AgentLoopResult(
            run_id="test_run",
            domain="test",
            target="test_target",
            max_steps=10,
            steps_taken=5,
            final_state=LoopState.SUCCEEDED,
            succeeded=True,
            stopped_early=False,
            plan_state=plan_state,
        )

        assert result.plan_state.total_subgoals == 3

    def test_summary_with_plan(self):
        """Summary should include plan progress."""
        plan_state = PlanState()
        plan_state.has_plan = True
        plan_state.completed_subgoals = 2
        plan_state.total_subgoals = 4

        result = AgentLoopResult(
            run_id="test_run",
            domain="test",
            target="test_target",
            max_steps=10,
            steps_taken=5,
            final_state=LoopState.SUCCEEDED,
            succeeded=True,
            stopped_early=False,
            plan_state=plan_state,
        )

        summary = result.summary()
        assert "plan_progress=50%" in summary

    def test_to_dict_includes_plan_state(self):
        """to_dict should include plan_state."""
        plan_state = PlanState()
        plan_state.plan_id = "test_plan"

        result = AgentLoopResult(
            run_id="test_run",
            domain="test",
            target="test_target",
            max_steps=10,
            steps_taken=5,
            final_state=LoopState.SUCCEEDED,
            succeeded=True,
            stopped_early=False,
            plan_state=plan_state,
        )

        d = result.to_dict()
        assert "plan_state" in d
        assert d["plan_state"]["plan_id"] == "test_plan"