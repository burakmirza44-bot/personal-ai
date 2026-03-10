"""Score Calculator - Compute combined evaluation scores.

Calculates weighted combined scores from multiple evaluation components.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ScoreWeights:
    """Weights for score calculation."""

    node_graph: float = 0.30
    connections: float = 0.25
    parameters: float = 0.15
    render: float = 0.15
    code_quality: float = 0.10
    visual_similarity: float = 0.05

    def normalize(self) -> "ScoreWeights":
        """Return normalized weights."""
        total = (
            self.node_graph + self.connections + self.parameters +
            self.render + self.code_quality + self.visual_similarity
        )
        if total == 0:
            return ScoreWeights()
        return ScoreWeights(
            node_graph=self.node_graph / total,
            connections=self.connections / total,
            parameters=self.parameters / total,
            render=self.render / total,
            code_quality=self.code_quality / total,
            visual_similarity=self.visual_similarity / total,
        )


class ScoreCalculator:
    """Calculate combined evaluation scores.

    Usage:
        calculator = ScoreCalculator()
        score = calculator.compute(node_score=0.8, connections_score=0.9, ...)
    """

    def __init__(
        self,
        weights: ScoreWeights | None = None,
    ) -> None:
        """Initialize score calculator.

        Args:
            weights: Optional custom weights
        """
        self.weights = (weights or ScoreWeights()).normalize()

    def compute(
        self,
        node_graph_score: float = 0.0,
        connections_score: float = 0.0,
        parameters_score: float = 0.0,
        render_score: float = 0.0,
        code_quality_score: float = 0.0,
        visual_similarity_score: float = 0.0,
    ) -> float:
        """Compute weighted combined score.

        Args:
            node_graph_score: Node/validity score (0-1)
            connections_score: Connection correctness score (0-1)
            parameters_score: Parameter validity score (0-1)
            render_score: Render output score (0-1)
            code_quality_score: Code quality score (0-1)
            visual_similarity_score: Visual similarity score (0-1)

        Returns:
            Combined score (0-1)
        """
        weighted_sum = (
            node_graph_score * self.weights.node_graph +
            connections_score * self.weights.connections +
            parameters_score * self.weights.parameters +
            render_score * self.weights.render +
            code_quality_score * self.weights.code_quality +
            visual_similarity_score * self.weights.visual_similarity
        )

        # Calculate used weight
        active_weights = [
            (node_graph_score, self.weights.node_graph),
            (connections_score, self.weights.connections),
            (parameters_score, self.weights.parameters),
            (render_score, self.weights.render),
            (code_quality_score, self.weights.code_quality),
            (visual_similarity_score, self.weights.visual_similarity),
        ]

        total_weight = sum(w for s, w in active_weights if s > 0)

        if total_weight == 0:
            return 0.0

        return weighted_sum / total_weight


def compute_combined_score(
    node_graph_score: float = 0.0,
    connections_score: float = 0.0,
    parameters_score: float = 0.0,
    render_score: float = 0.0,
    code_quality_score: float = 0.0,
    visual_similarity_score: float = 0.0,
) -> float:
    """Convenience function for combined score calculation."""
    calculator = ScoreCalculator()
    return calculator.compute(
        node_graph_score=node_graph_score,
        connections_score=connections_score,
        parameters_score=parameters_score,
        render_score=render_score,
        code_quality_score=code_quality_score,
        visual_similarity_score=visual_similarity_score,
    )