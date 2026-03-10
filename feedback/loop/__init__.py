# Feedback Loop Module
# Closed-loop learning system for continuous improvement

from feedback.loop.orchestrator import (
    FeedbackOrchestrator,
    FeedbackResult,
    FeedbackTask,
    BatchReport,
    ImprovementReport,
    run_feedback_loop,
)

from feedback.loop.evaluator import (
    OutputEvaluator,
    EvaluationResult,
    EvaluationConfig,
)

from feedback.loop.reward_signal import (
    RewardSignal,
    RewardCalculator,
    RewardType,
)

from feedback.loop.data_collector import (
    FeedbackDataCollector,
    CollectedExample,
    DataCollectionConfig,
)

__all__ = [
    # Orchestrator
    "FeedbackOrchestrator",
    "FeedbackResult",
    "BatchReport",
    "ImprovementReport",
    "run_feedback_loop",
    # Evaluator
    "OutputEvaluator",
    "EvaluationResult",
    "EvaluationConfig",
    # Reward
    "RewardSignal",
    "RewardCalculator",
    "RewardType",
    # Data Collector
    "FeedbackDataCollector",
    "CollectedExample",
    "DataCollectionConfig",
]