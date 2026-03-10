"""Reward Signal - Calculate reward/penalty for feedback loop.

Converts evaluation scores into reward signals for training.
Supports positive/negative examples and correction pairs.

Design principles:
- Score thresholds define example type
- Reward shaping for continuous improvement
- Trend detection for bonus/penalty
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from feedback.loop.evaluator import EvaluationResult, QualityTier

logger = logging.getLogger(__name__)

RewardType = Literal["positive", "correction", "negative", "neutral"]
RewardStrength = Literal["strong", "moderate", "weak"]


@dataclass(slots=True)
class RewardConfig:
    """Configuration for reward calculation."""

    # Score thresholds
    positive_threshold: float = 0.8      # Score >= this: positive example
    correction_threshold: float = 0.4    # Score >= this: correction example
    # Score < correction_threshold: negative example

    # Trend bonuses/penalties
    improvement_bonus: float = 0.1       # Bonus for improving
    regression_penalty: float = 0.15     # Penalty for getting worse

    # Stability bonus
    stability_bonus: float = 0.05        # Bonus for consistent good performance

    # Example limits
    max_positive_per_session: int = 100
    max_correction_per_session: int = 50
    max_negative_per_session: int = 20


@dataclass(slots=True)
class RewardSignal:
    """Reward signal for a single evaluation."""

    reward_id: str
    reward_type: RewardType
    reward_strength: RewardStrength
    score: float
    quality_tier: QualityTier

    # Trend info
    previous_score: float | None = None
    score_delta: float = 0.0
    trend_bonus: float = 0.0

    # Final reward value (-1 to 1)
    reward_value: float = 0.0

    # Metadata
    domain: str = ""
    task_id: str = ""
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "reward_id": self.reward_id,
            "reward_type": self.reward_type,
            "reward_strength": self.reward_strength,
            "score": self.score,
            "quality_tier": self.quality_tier,
            "previous_score": self.previous_score,
            "score_delta": self.score_delta,
            "trend_bonus": self.trend_bonus,
            "reward_value": self.reward_value,
            "domain": self.domain,
            "task_id": self.task_id,
            "timestamp": self.timestamp,
            "notes": self.notes,
        }


class RewardCalculator:
    """Calculate reward signals from evaluation results.

    Converts evaluation scores into training-friendly reward signals:
    - Positive examples for high-quality output
    - Correction examples for partial success
    - Negative examples for failure

    Usage:
        calculator = RewardCalculator()
        signal = calculator.calculate(evaluation_result, previous_score=0.5)
    """

    def __init__(self, config: RewardConfig | None = None) -> None:
        """Initialize reward calculator.

        Args:
            config: Optional reward configuration
        """
        self.config = config or RewardConfig()
        self._score_history: list[float] = []

    def calculate(
        self,
        evaluation: EvaluationResult,
        previous_score: float | None = None,
        task_id: str = "",
        domain: str = "",
    ) -> RewardSignal:
        """Calculate reward signal from evaluation result.

        Args:
            evaluation: Evaluation result to calculate reward for
            previous_score: Optional previous score for trend
            task_id: Task identifier
            domain: Domain identifier

        Returns:
            RewardSignal with reward type and value
        """
        reward_id = f"reward_{uuid4().hex[:8]}"
        score = evaluation.overall_score

        # Determine reward type based on score
        reward_type = self._determine_reward_type(score)
        reward_strength = self._determine_reward_strength(score, reward_type)

        # Calculate trend bonus/penalty
        score_delta = 0.0
        trend_bonus = 0.0

        if previous_score is not None:
            score_delta = score - previous_score

            if score_delta > 0.1:
                # Improvement bonus
                trend_bonus = self.config.improvement_bonus
            elif score_delta < -0.1:
                # Regression penalty
                trend_bonus = -self.config.regression_penalty
            elif score >= self.config.positive_threshold:
                # Stability bonus
                trend_bonus = self.config.stability_bonus

        # Calculate final reward value
        reward_value = self._calculate_reward_value(
            score=score,
            reward_type=reward_type,
            trend_bonus=trend_bonus,
        )

        # Track history
        self._score_history.append(score)

        return RewardSignal(
            reward_id=reward_id,
            reward_type=reward_type,
            reward_strength=reward_strength,
            score=score,
            quality_tier=evaluation.quality_tier,
            previous_score=previous_score,
            score_delta=score_delta,
            trend_bonus=trend_bonus,
            reward_value=reward_value,
            domain=domain or evaluation.domain,
            task_id=task_id,
            notes=self._generate_notes(evaluation, reward_type, trend_bonus),
        )

    def _determine_reward_type(self, score: float) -> RewardType:
        """Determine reward type from score."""
        if score >= self.config.positive_threshold:
            return "positive"
        elif score >= self.config.correction_threshold:
            return "correction"
        elif score > 0.0:
            return "negative"
        else:
            return "negative"

    def _determine_reward_strength(
        self,
        score: float,
        reward_type: RewardType,
    ) -> RewardStrength:
        """Determine reward strength."""
        if reward_type == "positive":
            if score >= 0.95:
                return "strong"
            elif score >= 0.85:
                return "moderate"
            else:
                return "weak"
        elif reward_type == "correction":
            if score >= 0.6:
                return "moderate"
            else:
                return "weak"
        else:  # negative
            if score < 0.1:
                return "strong"
            elif score < 0.25:
                return "moderate"
            else:
                return "weak"

    def _calculate_reward_value(
        self,
        score: float,
        reward_type: RewardType,
        trend_bonus: float,
    ) -> float:
        """Calculate final reward value (-1 to 1)."""
        base_value = {
            "positive": 1.0,
            "correction": 0.0,
            "negative": -1.0,
            "neutral": 0.0,
        }[reward_type]

        # Add trend bonus
        value = base_value + trend_bonus

        # Clamp to [-1, 1]
        return max(-1.0, min(1.0, value))

    def _generate_notes(
        self,
        evaluation: EvaluationResult,
        reward_type: RewardType,
        trend_bonus: float,
    ) -> str:
        """Generate human-readable notes."""
        parts = []

        if reward_type == "positive":
            parts.append("High quality output - added to positive examples")
        elif reward_type == "correction":
            parts.append("Partial success - created correction example")
        else:
            parts.append("Failed output - marked as negative example")

        if trend_bonus > 0:
            parts.append(f"Trend bonus: +{trend_bonus:.2f}")
        elif trend_bonus < 0:
            parts.append(f"Trend penalty: {trend_bonus:.2f}")

        if evaluation.errors:
            parts.append(f"Errors: {len(evaluation.errors)}")

        return "; ".join(parts)

    def get_trend_summary(self) -> dict[str, Any]:
        """Get summary of score trends."""
        if len(self._score_history) < 2:
            return {"trend": "insufficient_data"}

        recent = self._score_history[-10:]
        overall_trend = recent[-1] - recent[0]

        return {
            "trend": "improving" if overall_trend > 0.05 else "declining" if overall_trend < -0.05 else "stable",
            "average_score": sum(self._score_history) / len(self._score_history),
            "recent_average": sum(recent) / len(recent),
            "total_evaluations": len(self._score_history),
            "trend_delta": overall_trend,
        }

    def reset_history(self) -> None:
        """Reset score history."""
        self._score_history = []