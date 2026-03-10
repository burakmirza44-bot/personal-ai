"""Tests for Feedback Loop Module."""

import pytest
from pathlib import Path
import sys

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from feedback.loop.orchestrator import (
    FeedbackOrchestrator,
    FeedbackTask,
    FeedbackResult,
    BatchReport,
)
from feedback.loop.evaluator import (
    OutputEvaluator,
    EvaluationResult,
    EvaluationConfig,
)
from feedback.loop.reward_signal import (
    RewardCalculator,
    RewardSignal,
    RewardConfig,
)
from feedback.loop.data_collector import (
    FeedbackDataCollector,
    CollectedExample,
    DataCollectionConfig,
)


class TestOutputEvaluator:
    """Test output evaluation."""

    def test_evaluator_creation(self):
        """Test evaluator can be created."""
        evaluator = OutputEvaluator(domain="houdini")
        assert evaluator.domain == "houdini"

    def test_evaluate_houdini_nodes(self):
        """Test Houdini node validation."""
        evaluator = OutputEvaluator(domain="houdini")

        output = {
            "nodes": [
                {"name": "geo1", "type": "geo"},
                {"name": "box1", "type": "box"},
                {"name": "bevel1", "type": "polybevel"},
            ],
            "connections": [
                {"source": "box1", "target": "bevel1"},
            ],
        }

        result = evaluator.evaluate(output)

        assert result.success
        assert result.node_graph_score > 0
        assert result.connections_score > 0

    def test_evaluate_td_operators(self):
        """Test TouchDesigner operator validation."""
        evaluator = OutputEvaluator(domain="touchdesigner")

        output = {
            "operators": [
                {"name": "moviein1", "type": "moviefilein"},
                {"name": "null1", "type": "null"},
            ],
            "connections": [
                {"source": "moviein1", "target": "null1"},
            ],
        }

        result = evaluator.evaluate(output)

        assert result.success
        assert result.node_graph_score > 0

    def test_quality_tier_determination(self):
        """Test quality tier classification."""
        evaluator = OutputEvaluator(domain="generic")
        config = EvaluationConfig()

        # Excellent
        tier = evaluator._determine_quality_tier(0.95)
        assert tier == "excellent"

        # Good
        tier = evaluator._determine_quality_tier(0.8)
        assert tier == "good"

        # Acceptable
        tier = evaluator._determine_quality_tier(0.6)
        assert tier == "acceptable"

        # Failed
        tier = evaluator._determine_quality_tier(0.2)
        assert tier == "failed"


class TestRewardCalculator:
    """Test reward signal calculation."""

    def test_calculator_creation(self):
        """Test calculator can be created."""
        calculator = RewardCalculator()
        assert calculator is not None

    def test_positive_reward(self):
        """Test positive reward for high score."""
        from feedback.loop.evaluator import EvaluationResult

        calculator = RewardCalculator()

        evaluation = EvaluationResult(
            success=True,
            overall_score=0.9,
            quality_tier="excellent",
        )

        signal = calculator.calculate(evaluation, task_id="test_1")

        assert signal.reward_type == "positive"
        assert signal.reward_value > 0

    def test_correction_reward(self):
        """Test correction reward for medium score."""
        from feedback.loop.evaluator import EvaluationResult

        calculator = RewardCalculator()

        evaluation = EvaluationResult(
            success=True,
            overall_score=0.5,
            quality_tier="acceptable",
        )

        signal = calculator.calculate(evaluation, task_id="test_1")

        assert signal.reward_type == "correction"

    def test_negative_reward(self):
        """Test negative reward for low score."""
        from feedback.loop.evaluator import EvaluationResult

        calculator = RewardCalculator()

        evaluation = EvaluationResult(
            success=False,
            overall_score=0.2,
            quality_tier="failed",
        )

        signal = calculator.calculate(evaluation, task_id="test_1")

        assert signal.reward_type == "negative"
        assert signal.reward_value < 0

    def test_trend_bonus(self):
        """Test improvement trend bonus."""
        from feedback.loop.evaluator import EvaluationResult

        calculator = RewardCalculator()

        evaluation = EvaluationResult(
            success=True,
            overall_score=0.9,
            quality_tier="excellent",
        )

        # First result
        signal1 = calculator.calculate(evaluation, previous_score=0.5, task_id="test_1")

        # Should have improvement bonus
        assert signal1.trend_bonus > 0


class TestDataCollector:
    """Test data collection."""

    def test_collector_creation(self):
        """Test collector can be created."""
        collector = FeedbackDataCollector()
        assert collector is not None

    def test_collect_positive_example(self):
        """Test collecting positive example."""
        from feedback.loop.evaluator import EvaluationResult
        from feedback.loop.reward_signal import RewardSignal

        collector = FeedbackDataCollector()

        evaluation = EvaluationResult(
            success=True,
            overall_score=0.9,
            quality_tier="excellent",
        )

        signal = RewardSignal(
            reward_id="reward_1",
            reward_type="positive",
            reward_strength="strong",
            score=0.9,
            quality_tier="excellent",
            reward_value=1.0,
        )

        example = collector.collect(
            input_text="Create a box",
            output_text="geo = hou.node('/obj').createNode('geo')",
            evaluation=evaluation,
            signal=signal,
        )

        assert example is not None
        assert example.example_type == "positive"

    def test_collector_summary(self):
        """Test collector summary."""
        from feedback.loop.evaluator import EvaluationResult
        from feedback.loop.reward_signal import RewardSignal

        collector = FeedbackDataCollector()

        evaluation = EvaluationResult(success=True, overall_score=0.9, quality_tier="excellent")
        signal = RewardSignal(
            reward_id="r1", reward_type="positive", reward_strength="strong",
            score=0.9, quality_tier="excellent", reward_value=1.0,
        )

        collector.collect("input", "output", evaluation, signal)

        summary = collector.get_summary()

        assert summary["total_examples"] == 1
        assert summary["positive_count"] == 1


class TestFeedbackOrchestrator:
    """Test feedback orchestrator."""

    def test_orchestrator_creation(self):
        """Test orchestrator can be created."""
        orchestrator = FeedbackOrchestrator(domain="houdini")
        assert orchestrator.domain == "houdini"

    def test_run_single_with_output(self):
        """Test running single task with pre-computed output."""
        orchestrator = FeedbackOrchestrator(domain="houdini")

        task = FeedbackTask(
            task_id="test_1",
            input_text="Create a box and bevel it",
            domain="houdini",
        )

        output = """
geo = hou.node('/obj').createNode('geo', 'box_bevel')
box = geo.createNode('box', 'box1')
bevel = geo.createNode('polybevel', 'bevel1')
bevel.setInput(0, box)
"""

        result = orchestrator.run_single(task, inference_output=output)

        assert result.task_id == "test_1"
        assert result.inference_success

    def test_batch_report(self):
        """Test batch processing report."""
        orchestrator = FeedbackOrchestrator(domain="houdini")

        tasks = [
            FeedbackTask(task_id=f"task_{i}", input_text=f"Task {i}", domain="houdini")
            for i in range(5)
        ]

        # Run with mock outputs
        outputs = [f"output_{i}" for i in range(5)]

        # Process manually to provide outputs
        for task, output in zip(tasks, outputs):
            orchestrator.run_single(task, inference_output=output)

        report = orchestrator.run_batch(tasks)

        assert report.total_tasks == 5

    def test_improvement_report(self):
        """Test improvement report generation."""
        orchestrator = FeedbackOrchestrator(domain="houdini")

        # Run some tasks
        for i in range(5):
            task = FeedbackTask(
                task_id=f"task_{i}",
                input_text=f"Task {i}",
                domain="houdini",
            )
            orchestrator.run_single(task, inference_output=f"output_{i}")

        report = orchestrator.get_improvement_report()

        assert report.total_iterations == 5

    def test_status(self):
        """Test status retrieval."""
        orchestrator = FeedbackOrchestrator(domain="houdini")

        status = orchestrator.get_status()

        assert "session_id" in status
        assert "iteration_count" in status


class TestFeedbackTask:
    """Test feedback task model."""

    def test_task_creation(self):
        """Test task can be created."""
        task = FeedbackTask(
            task_id="test_1",
            input_text="Create a box",
            domain="houdini",
        )

        assert task.task_id == "test_1"
        assert task.domain == "houdini"

    def test_task_to_dict(self):
        """Test task serialization."""
        task = FeedbackTask(
            task_id="test_1",
            input_text="Create a box",
            domain="houdini",
        )

        data = task.to_dict()

        assert data["task_id"] == "test_1"
        assert data["domain"] == "houdini"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])