"""Tests for Execution-Based Self-Improvement."""

from __future__ import annotations

import pytest
from datetime import datetime
from pathlib import Path

from app.learning.execution_self_improvement import (
    # Enums
    ImprovementOpportunity,
    RiskLevel,
    ImprovementStatus,
    # Dataclasses
    ExecutionAnalysis,
    ImprovementApproval,
    PendingImprovement,
    ImprovementMetrics,
    # Core classes
    ExecutionAnalyzer,
    ImprovementRiskAssessor,
    AutonomousImprover,
    SelfImprovingExecutionAgent,
    HumanReviewQueue,
)


class TestImprovementOpportunity:
    """Tests for ImprovementOpportunity enum."""

    def test_opportunity_values(self) -> None:
        """Test opportunity enum values."""
        assert ImprovementOpportunity.PARAMETER_OPTIMIZATION.value == "parameter_optimization"
        assert ImprovementOpportunity.CONFIDENCE_BOOSTING.value == "confidence_boosting"
        assert ImprovementOpportunity.ERROR_PREVENTION.value == "error_prevention"
        assert ImprovementOpportunity.FALLBACK_STRATEGY.value == "fallback_strategy"
        assert ImprovementOpportunity.PERFORMANCE_IMPROVEMENT.value == "performance_improvement"

    def test_all_opportunities_defined(self) -> None:
        """Test all expected opportunities exist."""
        expected = [
            "parameter_optimization",
            "step_reordering",
            "fallback_strategy",
            "error_prevention",
            "performance_improvement",
            "confidence_boosting",
            "recipe_simplification",
            "retry_strategy_update",
        ]
        for opp in expected:
            assert any(o.value == opp for o in ImprovementOpportunity)


class TestRiskLevel:
    """Tests for RiskLevel enum."""

    def test_risk_levels(self) -> None:
        """Test risk level values."""
        assert RiskLevel.LOW.value == "low"
        assert RiskLevel.MEDIUM.value == "medium"
        assert RiskLevel.HIGH.value == "high"


class TestExecutionAnalysis:
    """Tests for ExecutionAnalysis dataclass."""

    def test_create_analysis(self) -> None:
        """Test creating an execution analysis."""
        analysis = ExecutionAnalysis(
            execution_id="exec_001",
            goal="Create geometry node",
            success=True,
            duration_ms=5000.0,
        )

        assert analysis.execution_id == "exec_001"
        assert analysis.success is True
        assert analysis.duration_ms == 5000.0

    def test_success_rate(self) -> None:
        """Test success rate calculation."""
        analysis = ExecutionAnalysis(
            execution_id="exec_001",
            goal="Test",
            success=True,
            duration_ms=1000.0,
            steps_completed=8,
            steps_failed=2,
        )

        assert analysis.success_rate == 0.8

    def test_retry_ratio(self) -> None:
        """Test retry ratio calculation."""
        analysis = ExecutionAnalysis(
            execution_id="exec_001",
            goal="Test",
            success=True,
            duration_ms=1000.0,
            steps_completed=10,
            retries_needed=3,
        )

        assert analysis.retry_ratio == 0.3

    def test_error_rate(self) -> None:
        """Test error rate calculation."""
        analysis = ExecutionAnalysis(
            execution_id="exec_001",
            goal="Test",
            success=False,
            duration_ms=1000.0,
            steps_completed=5,
            steps_failed=5,
            errors_encountered=["error1", "error2"],
        )

        assert analysis.error_rate == 0.2  # 2 errors / 10 total steps

    def test_serialization(self) -> None:
        """Test serialization to dict."""
        analysis = ExecutionAnalysis(
            execution_id="exec_001",
            goal="Test goal",
            success=True,
            duration_ms=5000.0,
            steps_completed=10,
            recipes_used=["recipe_001"],
            opportunities=[(ImprovementOpportunity.CONFIDENCE_BOOSTING, "Test opportunity")],
        )

        data = analysis.to_dict()

        assert data["execution_id"] == "exec_001"
        assert data["success"] is True
        assert data["recipes_used"] == ["recipe_001"]
        assert data["opportunities"] == [("confidence_boosting", "Test opportunity")]


class TestImprovementApproval:
    """Tests for ImprovementApproval dataclass."""

    def test_create_approval(self) -> None:
        """Test creating an approval."""
        approval = ImprovementApproval(
            opportunity=ImprovementOpportunity.PARAMETER_OPTIMIZATION,
            description="High retry ratio",
            risk_level=RiskLevel.LOW,
            requires_human_approval=False,
            confidence=0.85,
        )

        assert approval.opportunity == ImprovementOpportunity.PARAMETER_OPTIMIZATION
        assert approval.risk_level == RiskLevel.LOW
        assert approval.requires_human_approval is False

    def test_approval_serialization(self) -> None:
        """Test approval serialization."""
        approval = ImprovementApproval(
            opportunity=ImprovementOpportunity.CONFIDENCE_BOOSTING,
            description="Boost confidence",
            risk_level=RiskLevel.LOW,
            requires_human_approval=False,
            confidence=0.9,
            applied=True,
        )

        data = approval.to_dict()

        assert data["opportunity"] == "confidence_boosting"
        assert data["applied"] is True


class TestImprovementMetrics:
    """Tests for ImprovementMetrics dataclass."""

    def test_empty_metrics(self) -> None:
        """Test empty metrics."""
        metrics = ImprovementMetrics()

        assert metrics.total_executions_analyzed == 0
        assert metrics.pending_ratio == 0.0
        assert metrics.autonomous_ratio == 0.0

    def test_pending_ratio(self) -> None:
        """Test pending ratio calculation."""
        metrics = ImprovementMetrics(
            total_opportunities_found=10,
            improvements_pending_review=3,
        )

        assert metrics.pending_ratio == 0.3

    def test_autonomous_ratio(self) -> None:
        """Test autonomous ratio calculation."""
        metrics = ImprovementMetrics(
            total_opportunities_found=10,
            autonomous_improvements_applied=6,
        )

        assert metrics.autonomous_ratio == 0.6

    def test_metrics_serialization(self) -> None:
        """Test metrics serialization."""
        metrics = ImprovementMetrics(
            total_executions_analyzed=50,
            total_opportunities_found=20,
            autonomous_improvements_applied=15,
            by_opportunity={"confidence_boosting": 10, "parameter_optimization": 5},
        )

        data = metrics.to_dict()

        assert data["total_executions_analyzed"] == 50
        assert data["by_opportunity"]["confidence_boosting"] == 10


class TestExecutionAnalyzer:
    """Tests for ExecutionAnalyzer."""

    def test_analyze_success_execution(self) -> None:
        """Test analyzing a successful execution."""
        analyzer = ExecutionAnalyzer()

        execution_data = {
            "execution_id": "exec_001",
            "goal": "Create geometry",
            "success": True,
            "duration_ms": 5000.0,
            "steps_completed": 10,
            "steps_failed": 0,
            "retries_needed": 0,
            "errors": [],
            "recipes_used": ["recipe_001"],
            "avg_confidence": 0.75,
        }

        analysis = analyzer.analyze_execution(execution_data)

        assert analysis.success is True
        assert analysis.steps_completed == 10
        assert len(analyzer.execution_history) == 1

    def test_identify_parameter_optimization_opportunity(self) -> None:
        """Test identifying parameter optimization opportunity."""
        analyzer = ExecutionAnalyzer()

        execution_data = {
            "execution_id": "exec_001",
            "goal": "Test goal",
            "success": False,
            "duration_ms": 30000.0,
            "steps_completed": 5,
            "steps_failed": 3,
            "retries_needed": 3,  # High retry ratio
            "errors": ["timeout"],
        }

        analysis = analyzer.analyze_execution(execution_data)

        # Should have PARAMETER_OPTIMIZATION opportunity due to high retry ratio
        opportunity_types = [o for o, _ in analysis.opportunities]
        assert ImprovementOpportunity.PARAMETER_OPTIMIZATION in opportunity_types

    def test_identify_confidence_boosting_opportunity(self) -> None:
        """Test identifying confidence boosting opportunity."""
        analyzer = ExecutionAnalyzer()

        execution_data = {
            "execution_id": "exec_001",
            "goal": "Test goal",
            "success": True,
            "duration_ms": 5000.0,
            "steps_completed": 10,
            "recipes_used": ["recipe_001"],
            "avg_confidence": 0.5,  # Low confidence but succeeded
        }

        analysis = analyzer.analyze_execution(execution_data)

        # Should have CONFIDENCE_BOOSTING opportunity
        opportunity_types = [o for o, _ in analysis.opportunities]
        assert ImprovementOpportunity.CONFIDENCE_BOOSTING in opportunity_types

    def test_identify_error_prevention_opportunity(self) -> None:
        """Test identifying error prevention opportunity."""
        analyzer = ExecutionAnalyzer()

        execution_data = {
            "execution_id": "exec_001",
            "goal": "Test goal",
            "success": False,
            "duration_ms": 5000.0,
            "steps_completed": 5,
            "errors": ["node_not_found", "node_not_found", "timeout"],  # Repeated error
        }

        analysis = analyzer.analyze_execution(execution_data)

        # Should have ERROR_PREVENTION opportunity for repeated error
        opportunity_types = [o for o, _ in analysis.opportunities]
        assert ImprovementOpportunity.ERROR_PREVENTION in opportunity_types

    def test_identify_fallback_strategy_opportunity(self) -> None:
        """Test identifying fallback strategy opportunity."""
        analyzer = ExecutionAnalyzer()

        execution_data = {
            "execution_id": "exec_001",
            "goal": "Test goal",
            "success": False,
            "duration_ms": 5000.0,
            "steps_completed": 5,
            "recipes_used": ["recipe_001"],
            "avg_confidence": 0.4,  # Very low confidence
        }

        analysis = analyzer.analyze_execution(execution_data)

        # Should have FALLBACK_STRATEGY opportunity
        opportunity_types = [o for o, _ in analysis.opportunities]
        assert ImprovementOpportunity.FALLBACK_STRATEGY in opportunity_types

    def test_get_execution_trends(self) -> None:
        """Test getting execution trends."""
        analyzer = ExecutionAnalyzer()

        # Add multiple executions
        for i in range(5):
            analyzer.analyze_execution({
                "execution_id": f"exec_{i:03d}",
                "goal": "Same goal",
                "success": i < 4,  # 4 successes, 1 failure
                "duration_ms": 5000.0 + i * 1000,
                "steps_completed": 10,
            })

        trends = analyzer.get_execution_trends("Same goal")

        assert trends["total_executions"] == 5
        assert trends["success_rate"] == 0.8
        assert trends["avg_duration_ms"] == 7000.0

    def test_history_window(self) -> None:
        """Test history window limit."""
        analyzer = ExecutionAnalyzer(history_window=5)

        # Add 10 executions
        for i in range(10):
            analyzer.analyze_execution({
                "execution_id": f"exec_{i:03d}",
                "goal": "Test",
                "success": True,
                "duration_ms": 1000.0,
            })

        # Should only keep 5
        assert len(analyzer.execution_history) == 5

    def test_get_summary(self) -> None:
        """Test getting summary statistics."""
        analyzer = ExecutionAnalyzer()

        for i in range(10):
            analyzer.analyze_execution({
                "execution_id": f"exec_{i:03d}",
                "goal": f"goal_{i % 3}",
                "success": i < 7,  # 70% success rate
                "duration_ms": 5000.0,
            })

        summary = analyzer.get_summary()

        assert summary["total_executions"] == 10
        assert summary["overall_success_rate"] == 0.7
        assert summary["unique_goals"] == 3


class TestImprovementRiskAssessor:
    """Tests for ImprovementRiskAssessor."""

    def test_assess_parameter_optimization_low_risk(self) -> None:
        """Test parameter optimization is low risk with conditions met."""
        assessor = ImprovementRiskAssessor()
        analyzer = ExecutionAnalyzer()

        # Add enough history
        for i in range(6):
            analyzer.analyze_execution({
                "execution_id": f"exec_{i}",
                "goal": "Test goal",
                "success": True,
                "duration_ms": 5000.0,
                "steps_completed": 10,
            })

        risk, can_approve = assessor.assess_improvement(
            ImprovementOpportunity.PARAMETER_OPTIMIZATION,
            analyzer,
            "Test goal",
            {"success": True, "errors": []},
        )

        assert risk == RiskLevel.LOW
        assert can_approve is True

    def test_assess_high_risk_needs_human_approval(self) -> None:
        """Test high risk improvement needs human approval."""
        assessor = ImprovementRiskAssessor()
        analyzer = ExecutionAnalyzer()

        risk, can_approve = assessor.assess_improvement(
            ImprovementOpportunity.FALLBACK_STRATEGY,  # HIGH risk
            analyzer,
            "Test goal",
            {"success": True, "errors": []},
        )

        assert risk == RiskLevel.HIGH
        assert can_approve is False

    def test_assess_confidence_boosting_with_success(self) -> None:
        """Test confidence boosting with success conditions."""
        assessor = ImprovementRiskAssessor()
        analyzer = ExecutionAnalyzer()

        # Add successful executions
        for i in range(5):
            analyzer.analyze_execution({
                "execution_id": f"exec_{i}",
                "goal": "Test goal",
                "success": True,
                "duration_ms": 5000.0,
            })

        risk, can_approve = assessor.assess_improvement(
            ImprovementOpportunity.CONFIDENCE_BOOSTING,
            analyzer,
            "Test goal",
            {"success": True, "errors": []},
        )

        assert risk == RiskLevel.LOW
        assert can_approve is True

    def test_assess_blocks_without_success(self) -> None:
        """Test that success-required improvements are blocked on failure."""
        assessor = ImprovementRiskAssessor()
        analyzer = ExecutionAnalyzer()

        # Add history but execution failed
        for i in range(5):
            analyzer.analyze_execution({
                "execution_id": f"exec_{i}",
                "goal": "Test goal",
                "success": True,
                "duration_ms": 5000.0,
            })

        risk, can_approve = assessor.assess_improvement(
            ImprovementOpportunity.CONFIDENCE_BOOSTING,
            analyzer,
            "Test goal",
            {"success": False, "errors": []},  # Failed execution
        )

        assert can_approve is False

    def test_get_risk_description(self) -> None:
        """Test getting risk description."""
        assessor = ImprovementRiskAssessor()

        assert "autonomously" in assessor.get_risk_description(RiskLevel.LOW).lower()
        assert "validation" in assessor.get_risk_description(RiskLevel.MEDIUM).lower()
        assert "human approval" in assessor.get_risk_description(RiskLevel.HIGH).lower()


class TestHumanReviewQueue:
    """Tests for HumanReviewQueue."""

    def test_add_for_review(self) -> None:
        """Test adding improvement for review."""
        queue = HumanReviewQueue()
        analysis = ExecutionAnalysis(
            execution_id="exec_001",
            goal="Test goal",
            success=True,
            duration_ms=5000.0,
        )

        improvement_id = queue.add_for_review(
            opportunity=ImprovementOpportunity.STEP_REORDERING,
            description="Reorder steps",
            risk_level=RiskLevel.HIGH,
            confidence=0.6,
            analysis=analysis,
        )

        assert improvement_id.startswith("imp_")
        assert len(queue.pending) == 1

    def test_review_improvement_approved(self) -> None:
        """Test reviewing and approving improvement."""
        queue = HumanReviewQueue()
        analysis = ExecutionAnalysis(
            execution_id="exec_001",
            goal="Test goal",
            success=True,
            duration_ms=5000.0,
        )

        improvement_id = queue.add_for_review(
            opportunity=ImprovementOpportunity.PARAMETER_OPTIMIZATION,
            description="Optimize parameters",
            risk_level=RiskLevel.MEDIUM,
            confidence=0.7,
            analysis=analysis,
        )

        result = queue.review_improvement(
            improvement_id,
            approved=True,
            human_notes="Looks good",
        )

        assert result is True
        assert len(queue.pending) == 0
        assert len(queue.reviewed) == 1
        assert queue.reviewed[0]["approved"] is True

    def test_review_improvement_rejected(self) -> None:
        """Test reviewing and rejecting improvement."""
        queue = HumanReviewQueue()
        analysis = ExecutionAnalysis(
            execution_id="exec_001",
            goal="Test goal",
            success=True,
            duration_ms=5000.0,
        )

        improvement_id = queue.add_for_review(
            opportunity=ImprovementOpportunity.STEP_REORDERING,
            description="Reorder steps",
            risk_level=RiskLevel.HIGH,
            confidence=0.5,
            analysis=analysis,
        )

        result = queue.review_improvement(
            improvement_id,
            approved=False,
            human_notes="Too risky",
        )

        assert result is True
        assert queue.reviewed[0]["approved"] is False

    def test_get_pending_improvements_sorted(self) -> None:
        """Test getting pending improvements sorted by priority."""
        queue = HumanReviewQueue()

        # Add improvements with different risk levels
        for risk in [RiskLevel.LOW, RiskLevel.HIGH, RiskLevel.MEDIUM]:
            analysis = ExecutionAnalysis(
                execution_id=f"exec_{risk.value}",
                goal="Test goal",
                success=True,
                duration_ms=5000.0,
            )
            queue.add_for_review(
                opportunity=ImprovementOpportunity.PARAMETER_OPTIMIZATION,
                description=f"Improvement {risk.value}",
                risk_level=risk,
                confidence=0.7,
                analysis=analysis,
            )

        pending = queue.get_pending_improvements()

        # HIGH risk should be first
        assert pending[0].risk_level == RiskLevel.HIGH

    def test_clear_pending(self) -> None:
        """Test clearing all pending improvements."""
        queue = HumanReviewQueue()

        for i in range(5):
            analysis = ExecutionAnalysis(
                execution_id=f"exec_{i}",
                goal="Test goal",
                success=True,
                duration_ms=5000.0,
            )
            queue.add_for_review(
                opportunity=ImprovementOpportunity.PARAMETER_OPTIMIZATION,
                description=f"Improvement {i}",
                risk_level=RiskLevel.MEDIUM,
                confidence=0.7,
                analysis=analysis,
            )

        count = queue.clear_pending()

        assert count == 5
        assert len(queue.pending) == 0


class TestAutonomousImprover:
    """Tests for AutonomousImprover."""

    def test_apply_low_risk_improvements(self) -> None:
        """Test applying low-risk improvements."""
        analyzer = ExecutionAnalyzer()
        risk_assessor = ImprovementRiskAssessor()

        # Create a mock memory store
        class MockMemoryStore:
            def __init__(self):
                self.recipes = {"recipe_001": {"confidence": 0.5}}

            def get_recipe(self, recipe_id):
                return self.recipes.get(recipe_id)

            def update_recipe(self, recipe_id, recipe):
                self.recipes[recipe_id] = recipe

        mock_store = MockMemoryStore()
        improver = AutonomousImprover(memory_store=mock_store)

        # Add enough history for low-risk approval
        for i in range(6):
            analyzer.analyze_execution({
                "execution_id": f"exec_{i}",
                "goal": "Test goal",
                "success": True,
                "duration_ms": 5000.0,
                "steps_completed": 10,
                "recipes_used": ["recipe_001"],
                "avg_confidence": 0.5,  # Low confidence to trigger boosting
            })

        # Get last analysis
        analysis = analyzer.execution_history[-1]

        applied = improver.apply_improvements(
            analysis,
            analyzer,
            risk_assessor,
        )

        # Confidence boosting should be applied (low risk with conditions met)
        assert len(applied) > 0

    def test_calculate_confidence(self) -> None:
        """Test confidence calculation."""
        analyzer = ExecutionAnalyzer()
        improver = AutonomousImprover()

        # Add history
        for i in range(25):
            analyzer.analyze_execution({
                "execution_id": f"exec_{i}",
                "goal": "Test goal",
                "success": True,
                "duration_ms": 5000.0,
            })

        analysis = ExecutionAnalysis(
            execution_id="exec_test",
            goal="Test goal",
            success=True,
            duration_ms=5000.0,
            steps_completed=10,
            recipes_used=["recipe_001"],
        )

        confidence = improver._calculate_confidence(
            ImprovementOpportunity.CONFIDENCE_BOOSTING,
            analyzer,
            analysis,
        )

        # Should be high confidence due to success, history size, and type
        assert confidence > 0.8

    def test_get_improvement_history(self) -> None:
        """Test getting improvement history."""
        analyzer = ExecutionAnalyzer()
        risk_assessor = ImprovementRiskAssessor()

        # Create a mock memory store
        class MockMemoryStore:
            def __init__(self):
                self.recipes = {"recipe_001": {"confidence": 0.5}}

            def get_recipe(self, recipe_id):
                return self.recipes.get(recipe_id)

            def update_recipe(self, recipe_id, recipe):
                self.recipes[recipe_id] = recipe

        mock_store = MockMemoryStore()
        improver = AutonomousImprover(memory_store=mock_store)

        # Setup and apply
        for i in range(6):
            analyzer.analyze_execution({
                "execution_id": f"exec_{i}",
                "goal": "Test goal",
                "success": True,
                "duration_ms": 5000.0,
                "steps_completed": 10,
                "recipes_used": ["recipe_001"],
                "avg_confidence": 0.5,
            })

        analysis = analyzer.execution_history[-1]
        improver.apply_improvements(analysis, analyzer, risk_assessor)

        history = improver.get_improvement_history()

        assert len(history) > 0


class TestSelfImprovingExecutionAgent:
    """Tests for SelfImprovingExecutionAgent."""

    def test_execute_with_improvement(self) -> None:
        """Test executing with improvement analysis."""
        agent = SelfImprovingExecutionAgent()

        execution_callback = lambda goal, domain: {
            "success": True,
            "duration_ms": 5000.0,
            "steps_completed": 10,
            "steps_failed": 0,
            "retries_needed": 0,
            "errors": [],
            "recipes_used": ["recipe_001"],
            "avg_confidence": 0.6,
        }

        result, applied = agent.execute_with_improvement(
            goal="Test goal",
            domain="houdini",
            execution_callback=execution_callback,
        )

        assert result["success"] is True
        assert agent.metrics.total_executions_analyzed == 1

    def test_metrics_tracking(self) -> None:
        """Test metrics are tracked correctly."""
        agent = SelfImprovingExecutionAgent()

        for i in range(5):
            execution_callback = lambda goal, domain: {
                "success": i < 4,
                "duration_ms": 5000.0,
                "steps_completed": 10,
                "errors": ["error"] if i == 4 else [],
            }

            agent.execute_with_improvement(
                goal="Test goal",
                domain="houdini",
                execution_callback=execution_callback,
            )

        assert agent.metrics.total_executions_analyzed == 5

    def test_get_improvement_report(self) -> None:
        """Test getting improvement report."""
        agent = SelfImprovingExecutionAgent()

        for i in range(5):
            agent.execute_with_improvement(
                goal=f"goal_{i % 2}",
                domain="houdini",
                execution_callback=lambda g, d: {
                    "success": True,
                    "duration_ms": 5000.0,
                    "steps_completed": 10,
                },
            )

        report = agent.get_improvement_report()

        assert "metrics" in report
        assert "execution_summary" in report
        assert report["execution_summary"]["total_executions"] == 5

    def test_review_pending_improvement(self) -> None:
        """Test reviewing pending improvement."""
        agent = SelfImprovingExecutionAgent()

        # Add execution that will queue for review
        agent.execute_with_improvement(
            goal="Test goal",
            domain="houdini",
            execution_callback=lambda g, d: {
                "success": False,
                "duration_ms": 5000.0,
                "steps_completed": 10,
                "errors": ["timeout", "timeout", "timeout"],
                "recipes_used": ["recipe_001"],
                "avg_confidence": 0.3,
            },
        )

        pending = agent.get_pending_for_review()

        if pending:
            # Review the improvement
            result = agent.review_pending(
                pending[0].improvement_id,
                approved=True,
                human_notes="Approved for testing",
            )

            assert result is True


class TestIntegration:
    """Integration tests for self-improvement system."""

    def test_full_improvement_flow(self) -> None:
        """Test full improvement flow from execution to improvement."""
        analyzer = ExecutionAnalyzer()
        risk_assessor = ImprovementRiskAssessor()
        improver = AutonomousImprover()

        # Build up history with improving performance
        for i in range(10):
            execution_data = {
                "execution_id": f"exec_{i:03d}",
                "goal": "Create geometry node",
                "success": i >= 3,  # First 3 fail, rest succeed
                "duration_ms": 5000.0 - i * 200,  # Getting faster
                "steps_completed": 10,
                "steps_failed": 2 if i < 3 else 0,
                "retries_needed": 3 if i < 3 else 0,
                "errors": ["timeout", "node_not_found"] if i < 3 else [],
                "recipes_used": ["recipe_geo_001"],
                "avg_confidence": 0.5 + i * 0.05,  # Improving confidence
            }

            analysis = analyzer.analyze_execution(execution_data)

            # For successful executions, apply improvements
            if analysis.success:
                applied = improver.apply_improvements(
                    analysis,
                    analyzer,
                    risk_assessor,
                )

        # Check trends
        trends = analyzer.get_execution_trends("Create geometry node")

        assert trends["success_rate"] == 0.7  # 7/10 successes
        assert trends["trend"] in ("improving", "stable")

    def test_risk_based_routing(self) -> None:
        """Test that improvements are routed correctly by risk."""
        analyzer = ExecutionAnalyzer()
        risk_assessor = ImprovementRiskAssessor()
        review_queue = HumanReviewQueue()

        # Add minimal history
        for i in range(3):
            analyzer.analyze_execution({
                "execution_id": f"exec_{i}",
                "goal": "Test goal",
                "success": True,
                "duration_ms": 5000.0,
            })

        # Check different improvement types get correct risk
        test_cases = [
            (ImprovementOpportunity.PARAMETER_OPTIMIZATION, RiskLevel.LOW),
            (ImprovementOpportunity.CONFIDENCE_BOOSTING, RiskLevel.LOW),
            (ImprovementOpportunity.ERROR_PREVENTION, RiskLevel.MEDIUM),
            (ImprovementOpportunity.FALLBACK_STRATEGY, RiskLevel.HIGH),
            (ImprovementOpportunity.STEP_REORDERING, RiskLevel.HIGH),
        ]

        for opportunity, expected_risk in test_cases:
            risk, can_approve = risk_assessor.assess_improvement(
                opportunity,
                analyzer,
                "Test goal",
                {"success": True, "errors": []},
            )

            assert risk == expected_risk, f"{opportunity} should be {expected_risk}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])