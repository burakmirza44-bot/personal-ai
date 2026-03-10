"""Curriculum Learning - Organize training by difficulty.

Sorts training examples by difficulty level for more effective learning.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Literal
import json
from pathlib import Path

logger = logging.getLogger(__name__)

DifficultyLevel = Literal["level_1", "level_2", "level_3", "level_4", "level_5"]


@dataclass(slots=True)
class CurriculumConfig:
    """Configuration for curriculum learning."""

    # Difficulty thresholds
    level_1_max_nodes: int = 2      # Single/duo node operations
    level_2_max_nodes: int = 5      # Small chains
    level_3_max_nodes: int = 10     # Medium chains
    level_4_max_nodes: int = 20     # Complex chains
    # level_5: unlimited

    # Code complexity thresholds
    level_1_max_lines: int = 5
    level_2_max_lines: int = 15
    level_3_max_lines: int = 30
    level_4_max_lines: int = 50

    # Training order
    start_level: DifficultyLevel = "level_1"
    advance_threshold: float = 0.8  # Accuracy to advance
    epochs_per_level: int = 1


@dataclass(slots=True)
class CurriculumLevel:
    """A single curriculum level."""

    level: DifficultyLevel
    name: str
    description: str
    example_count: int = 0
    examples: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "name": self.name,
            "description": self.description,
            "example_count": self.example_count,
        }


class CurriculumLearner:
    """Organize training examples by difficulty.

    Levels:
    - Level 1: Single node operations
    - Level 2: 2-5 node chains
    - Level 3: 5-10 node chains with parameters
    - Level 4: Complex chains (9-step SOP demo level)
    - Level 5: VEX + node combinations

    Usage:
        curriculum = CurriculumLearner()
        curriculum.add_examples(examples)
        for level in curriculum.get_training_order():
            train_on(level.examples)
    """

    def __init__(
        self,
        config: CurriculumConfig | None = None,
    ) -> None:
        """Initialize curriculum learner.

        Args:
            config: Optional curriculum configuration
        """
        self.config = config or CurriculumConfig()
        self._levels: dict[DifficultyLevel, CurriculumLevel] = {
            "level_1": CurriculumLevel(
                level="level_1",
                name="Basic Operations",
                description="Single node operations (create box, add transform)",
            ),
            "level_2": CurriculumLevel(
                level="level_2",
                name="Simple Chains",
                description="2-5 node chains",
            ),
            "level_3": CurriculumLevel(
                level="level_3",
                name="Medium Chains",
                description="5-10 node chains with parameters",
            ),
            "level_4": CurriculumLevel(
                level="level_4",
                name="Complex Chains",
                description="Complex SOP chains (9-step demo level)",
            ),
            "level_5": CurriculumLevel(
                level="level_5",
                name="Advanced",
                description="VEX + node combinations",
            ),
        }

    def classify_example(
        self,
        example: dict[str, Any],
    ) -> DifficultyLevel:
        """Classify an example into a difficulty level.

        Args:
            example: Example to classify

        Returns:
            DifficultyLevel
        """
        # Count nodes/operators
        output = example.get("output", "") or example.get("output_text", "")
        input_text = example.get("input", "") or example.get("instruction", "")

        # Count node mentions
        node_patterns = [
            r"createNode\s*\(",
            r"createNode\s*\(\s*['\"](\w+)['\"]",
            r"addNode",
            r"geo\.createNode",
            r"\.createNode\(",
        ]

        node_count = 0
        for pattern in node_patterns:
            matches = re.findall(pattern, output)
            node_count += len(matches)

        # Count code lines
        code_lines = len(output.split("\n"))

        # Classify by node count
        if node_count <= self.config.level_1_max_nodes and code_lines <= self.config.level_1_max_lines:
            return "level_1"
        elif node_count <= self.config.level_2_max_nodes and code_lines <= self.config.level_2_max_lines:
            return "level_2"
        elif node_count <= self.config.level_3_max_nodes and code_lines <= self.config.level_3_max_lines:
            return "level_3"
        elif node_count <= self.config.level_4_max_nodes and code_lines <= self.config.level_4_max_lines:
            return "level_4"
        else:
            return "level_5"

    def add_example(
        self,
        example: dict[str, Any],
    ) -> DifficultyLevel:
        """Add an example to the appropriate level.

        Args:
            example: Example to add

        Returns:
            Level the example was added to
        """
        level = self.classify_example(example)
        self._levels[level].examples.append(example)
        self._levels[level].example_count += 1
        return level

    def add_examples(
        self,
        examples: list[dict[str, Any]],
    ) -> dict[DifficultyLevel, int]:
        """Add multiple examples.

        Args:
            examples: Examples to add

        Returns:
            Dict of counts per level
        """
        counts = {level: 0 for level in self._levels}

        for example in examples:
            level = self.add_example(example)
            counts[level] += 1

        return counts

    def get_level(
        self,
        level: DifficultyLevel,
    ) -> CurriculumLevel:
        """Get examples for a specific level.

        Args:
            level: Difficulty level

        Returns:
            CurriculumLevel with examples
        """
        return self._levels[level]

    def get_training_order(self) -> list[CurriculumLevel]:
        """Get levels in training order.

        Returns:
            List of levels from easiest to hardest
        """
        order: list[DifficultyLevel] = [
            "level_1", "level_2", "level_3", "level_4", "level_5"
        ]
        return [self._levels[level] for level in order if self._levels[level].example_count > 0]

    def get_summary(self) -> dict[str, Any]:
        """Get curriculum summary."""
        return {
            "total_examples": sum(l.example_count for l in self._levels.values()),
            "levels": {
                level: {
                    "name": data.name,
                    "count": data.example_count,
                }
                for level, data in self._levels.items()
            },
        }

    def save_curriculum(
        self,
        output_dir: Path | str,
    ) -> dict[str, int]:
        """Save curriculum levels to separate files.

        Args:
            output_dir: Output directory

        Returns:
            Dict with counts per level
        """
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)

        counts = {}

        for level_key, level_data in self._levels.items():
            if level_data.examples:
                level_path = output / f"{level_key}.jsonl"
                with open(level_path, "w", encoding="utf-8") as f:
                    for ex in level_data.examples:
                        f.write(json.dumps(ex, ensure_ascii=False) + "\n")
                counts[level_key] = len(level_data.examples)

        return counts