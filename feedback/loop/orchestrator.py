"""Feedback Loop Orchestrator - Main feedback loop controller.

Coordinates the complete feedback loop:
1. Run inference
2. Evaluate output
3. Calculate reward
4. Collect training data
5. Trigger retraining when ready

Design principles:
- Bounded execution with safety limits
- Observable at every step
- Supports both single and batch processing
- Integrates with existing memory/runtime systems
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

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

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class FeedbackTask:
    """A single task for feedback loop processing."""

    task_id: str
    input_text: str
    expected_output: str = ""
    domain: str = "generic"
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "input_text": self.input_text,
            "expected_output": self.expected_output,
            "domain": self.domain,
            "context": self.context,
        }


@dataclass(slots=True)
class FeedbackResult:
    """Result of a single feedback loop iteration."""

    result_id: str
    task_id: str

    # Inference
    input_text: str = ""
    output_text: str = ""
    inference_success: bool = False

    # Evaluation
    evaluation: EvaluationResult | None = None
    score: float = 0.0
    quality_tier: str = ""

    # Reward
    reward: RewardSignal | None = None
    reward_value: float = 0.0
    reward_type: str = ""

    # Collection
    example_collected: bool = False
    example_id: str = ""

    # Metadata
    domain: str = ""
    processing_time_seconds: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "result_id": self.result_id,
            "task_id": self.task_id,
            "input_text": self.input_text[:500],
            "output_text": self.output_text[:500],
            "inference_success": self.inference_success,
            "score": self.score,
            "quality_tier": self.quality_tier,
            "reward_value": self.reward_value,
            "reward_type": self.reward_type,
            "example_collected": self.example_collected,
            "example_id": self.example_id,
            "domain": self.domain,
            "processing_time_seconds": self.processing_time_seconds,
            "timestamp": self.timestamp,
            "error": self.error,
        }


@dataclass(slots=True)
class BatchReport:
    """Report from batch feedback processing."""

    batch_id: str
    total_tasks: int = 0
    successful_tasks: int = 0
    failed_tasks: int = 0

    # Score statistics
    average_score: float = 0.0
    min_score: float = 0.0
    max_score: float = 0.0

    # Reward statistics
    positive_count: int = 0
    correction_count: int = 0
    negative_count: int = 0

    # Collection statistics
    examples_collected: int = 0

    # Time
    total_time_seconds: float = 0.0
    average_time_per_task: float = 0.0

    # Weak areas
    weak_areas: list[str] = field(default_factory=list)
    common_errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "total_tasks": self.total_tasks,
            "successful_tasks": self.successful_tasks,
            "failed_tasks": self.failed_tasks,
            "average_score": self.average_score,
            "min_score": self.min_score,
            "max_score": self.max_score,
            "positive_count": self.positive_count,
            "correction_count": self.correction_count,
            "negative_count": self.negative_count,
            "examples_collected": self.examples_collected,
            "total_time_seconds": self.total_time_seconds,
            "average_time_per_task": self.average_time_per_task,
            "weak_areas": self.weak_areas,
            "common_errors": self.common_errors,
        }


@dataclass(slots=True)
class ImprovementReport:
    """Report on improvement over time."""

    session_id: str
    total_iterations: int = 0
    score_trend: str = "stable"
    initial_score: float = 0.0
    final_score: float = 0.0
    improvement_delta: float = 0.0

    # Best/worst tasks
    best_task_ids: list[str] = field(default_factory=list)
    worst_task_ids: list[str] = field(default_factory=list)

    # Weak areas
    persistent_weak_areas: list[str] = field(default_factory=list)
    improved_areas: list[str] = field(default_factory=list)

    # Retraining
    retrain_triggered: bool = False
    retrain_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "total_iterations": self.total_iterations,
            "score_trend": self.score_trend,
            "initial_score": self.initial_score,
            "final_score": self.final_score,
            "improvement_delta": self.improvement_delta,
            "best_task_ids": self.best_task_ids,
            "worst_task_ids": self.worst_task_ids,
            "persistent_weak_areas": self.persistent_weak_areas,
            "improved_areas": self.improved_areas,
            "retrain_triggered": self.retrain_triggered,
            "retrain_reason": self.retrain_reason,
        }


class FeedbackOrchestrator:
    """Main feedback loop orchestrator.

    Coordinates the complete feedback loop for continuous improvement:
    - Runs inference on tasks
    - Evaluates output quality
    - Calculates reward signals
    - Collects training examples
    - Triggers retraining when ready

    Usage:
        orchestrator = FeedbackOrchestrator()
        result = orchestrator.run_single(task)
        report = orchestrator.run_batch(tasks)
    """

    def __init__(
        self,
        domain: str = "generic",
        evaluation_config: EvaluationConfig | None = None,
        reward_config: RewardConfig | None = None,
        collection_config: DataCollectionConfig | None = None,
        inference_callback: Callable | None = None,
    ) -> None:
        """Initialize feedback orchestrator.

        Args:
            domain: Default domain for evaluation
            evaluation_config: Evaluation configuration
            reward_config: Reward calculation configuration
            collection_config: Data collection configuration
            inference_callback: Optional custom inference function
        """
        self.domain = domain
        self.evaluator = OutputEvaluator(
            domain=domain,
            config=evaluation_config,
        )
        self.reward_calculator = RewardCalculator(config=reward_config)
        self.data_collector = FeedbackDataCollector(config=collection_config)
        self.inference_callback = inference_callback

        # Session tracking
        self._session_id = f"session_{uuid4().hex[:8]}"
        self._results: list[FeedbackResult] = []
        self._iteration_count = 0
        self._retrain_threshold = 500

    def run_single(
        self,
        task: FeedbackTask,
        inference_output: str | None = None,
    ) -> FeedbackResult:
        """Run a single feedback loop iteration.

        Args:
            task: Task to process
            inference_output: Pre-computed output (calls inference if None)

        Returns:
            FeedbackResult with evaluation and reward
        """
        start = time.monotonic()
        result_id = f"result_{uuid4().hex[:8]}"

        result = FeedbackResult(
            result_id=result_id,
            task_id=task.task_id,
            input_text=task.input_text,
            domain=task.domain,
        )

        try:
            # Run inference
            if inference_output is not None:
                output_text = inference_output
            elif self.inference_callback:
                output_text = self.inference_callback(task.input_text, task.domain)
            else:
                # Use default inference orchestrator
                output_text = self._default_inference(task.input_text, task.domain)

            result.output_text = output_text
            result.inference_success = bool(output_text)

            if not output_text:
                result.error = "Inference produced no output"
                return result

            # Evaluate output
            expected = {"output": task.expected_output} if task.expected_output else None
            evaluation = self.evaluator.evaluate(
                output={"text": output_text},
                expected=expected,
                context=task.context,
            )
            result.evaluation = evaluation
            result.score = evaluation.overall_score
            result.quality_tier = evaluation.quality_tier

            # Calculate reward
            previous_score = self._get_previous_score(task.domain)
            reward = self.reward_calculator.calculate(
                evaluation=evaluation,
                previous_score=previous_score,
                task_id=task.task_id,
                domain=task.domain,
            )
            result.reward = reward
            result.reward_value = reward.reward_value
            result.reward_type = reward.reward_type

            # Collect training example
            example = self.data_collector.collect(
                input_text=task.input_text,
                output_text=output_text,
                evaluation=evaluation,
                signal=reward,
                session_id=self._session_id,
            )
            if example:
                result.example_collected = True
                result.example_id = example.example_id

            self._iteration_count += 1

        except Exception as e:
            result.error = str(e)
            logger.error(f"Feedback loop error: {e}")

        result.processing_time_seconds = time.monotonic() - start
        self._results.append(result)

        return result

    def run_batch(
        self,
        tasks: list[FeedbackTask],
        progress_callback: Callable | None = None,
    ) -> BatchReport:
        """Run feedback loop on a batch of tasks.

        Args:
            tasks: List of tasks to process
            progress_callback: Optional progress callback

        Returns:
            BatchReport with aggregate statistics
        """
        batch_id = f"batch_{uuid4().hex[:8]}"
        start = time.monotonic()

        report = BatchReport(batch_id=batch_id, total_tasks=len(tasks))

        scores: list[float] = []
        errors: dict[str, int] = {}

        for i, task in enumerate(tasks):
            if progress_callback:
                progress_callback(i, len(tasks), task.task_id)

            result = self.run_single(task)

            if result.inference_success:
                report.successful_tasks += 1
                scores.append(result.score)
            else:
                report.failed_tasks += 1

            # Track reward types
            if result.reward_type == "positive":
                report.positive_count += 1
            elif result.reward_type == "correction":
                report.correction_count += 1
            else:
                report.negative_count += 1

            # Track errors
            if result.error:
                error_key = result.error[:50]
                errors[error_key] = errors.get(error_key, 0) + 1

            if result.example_collected:
                report.examples_collected += 1

        # Calculate statistics
        if scores:
            report.average_score = sum(scores) / len(scores)
            report.min_score = min(scores)
            report.max_score = max(scores)

        report.total_time_seconds = time.monotonic() - start
        report.average_time_per_task = report.total_time_seconds / max(1, len(tasks))

        # Common errors
        report.common_errors = sorted(errors.keys(), key=lambda k: errors[k], reverse=True)[:5]

        # Identify weak areas
        report.weak_areas = self._identify_weak_areas()

        return report

    def trigger_retrain(self, min_new_examples: int = 500) -> bool:
        """Check if retraining should be triggered.

        Args:
            min_new_examples: Minimum new examples to trigger retrain

        Returns:
            True if retrain was triggered
        """
        summary = self.data_collector.get_summary()
        total_examples = summary["positive_count"] + summary["correction_count"]

        if total_examples >= min_new_examples:
            logger.info(f"Retrain triggered: {total_examples} new examples")
            return True

        return False

    def get_improvement_report(self) -> ImprovementReport:
        """Get report on improvement over time.

        Returns:
            ImprovementReport with trend analysis
        """
        report = ImprovementReport(session_id=self._session_id)
        report.total_iterations = self._iteration_count

        if len(self._results) < 2:
            return report

        scores = [r.score for r in self._results if r.inference_success]
        if not scores:
            return report

        report.initial_score = scores[0]
        report.final_score = scores[-1]
        report.improvement_delta = report.final_score - report.initial_score

        # Determine trend
        if report.improvement_delta > 0.1:
            report.score_trend = "improving"
        elif report.improvement_delta < -0.1:
            report.score_trend = "declining"
        else:
            report.score_trend = "stable"

        # Best/worst tasks
        sorted_results = sorted(
            [r for r in self._results if r.inference_success],
            key=lambda r: r.score,
            reverse=True,
        )

        report.best_task_ids = [r.task_id for r in sorted_results[:3]]
        report.worst_task_ids = [r.task_id for r in sorted_results[-3:]]

        # Retrain status
        report.retrain_triggered = self.trigger_retrain()
        if report.retrain_triggered:
            report.retrain_reason = f"Collected {self.data_collector.get_summary()['total_examples']} examples"

        return report

    def _default_inference(self, input_text: str, domain: str) -> str:
        """Default inference using the main orchestrator."""
        try:
            from app.core.inference_orchestrator import run_inference
            result = run_inference(
                prompt=input_text,
                task_class="coding_patch",
                domain=domain,
            )
            return result.text if result.success else ""
        except Exception as e:
            logger.error(f"Default inference failed: {e}")
            return ""

    def _get_previous_score(self, domain: str) -> float | None:
        """Get previous score for trend calculation."""
        domain_results = [r for r in self._results if r.domain == domain and r.inference_success]
        if domain_results:
            return domain_results[-1].score
        return None

    def _identify_weak_areas(self) -> list[str]:
        """Identify weak areas from recent results."""
        weak_areas: list[str] = []

        # Check recent evaluations
        recent = self._results[-20:]
        error_counts: dict[str, int] = {}

        for result in recent:
            if result.evaluation and result.evaluation.errors:
                for error in result.evaluation.errors:
                    # Extract error category
                    if "node" in error.lower():
                        error_counts["node_graph"] = error_counts.get("node_graph", 0) + 1
                    elif "connection" in error.lower():
                        error_counts["connections"] = error_counts.get("connections", 0) + 1
                    elif "parameter" in error.lower():
                        error_counts["parameters"] = error_counts.get("parameters", 0) + 1
                    elif "vex" in error.lower() or "python" in error.lower():
                        error_counts["code_quality"] = error_counts.get("code_quality", 0) + 1

        # Sort by frequency
        weak_areas = sorted(error_counts.keys(), key=lambda k: error_counts[k], reverse=True)[:3]

        return weak_areas

    def export_training_data(
        self,
        output_dir: Path | str,
    ) -> dict[str, int]:
        """Export collected training data.

        Args:
            output_dir: Output directory

        Returns:
            Dict with export counts
        """
        return self.data_collector.export_training_set(output_dir)

    def get_status(self) -> dict[str, Any]:
        """Get current status of the feedback loop."""
        return {
            "session_id": self._session_id,
            "iteration_count": self._iteration_count,
            "results_count": len(self._results),
            "data_summary": self.data_collector.get_summary(),
            "trend_summary": self.reward_calculator.get_trend_summary(),
            "retrain_ready": self.trigger_retrain(),
        }

    def reset_session(self) -> None:
        """Reset the current session."""
        self._session_id = f"session_{uuid4().hex[:8]}"
        self._results = []
        self._iteration_count = 0
        self.data_collector.clear()
        self.reward_calculator.reset_history()


def run_feedback_loop(
    tasks: list[FeedbackTask],
    domain: str = "generic",
    inference_callback: Callable | None = None,
) -> tuple[BatchReport, ImprovementReport]:
    """Convenience function to run a complete feedback loop.

    Args:
        tasks: List of tasks to process
        domain: Domain for evaluation
        inference_callback: Optional custom inference function

    Returns:
        Tuple of (BatchReport, ImprovementReport)
    """
    orchestrator = FeedbackOrchestrator(
        domain=domain,
        inference_callback=inference_callback,
    )

    batch_report = orchestrator.run_batch(tasks)
    improvement_report = orchestrator.get_improvement_report()

    return batch_report, improvement_report