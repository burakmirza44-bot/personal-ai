"""Feedback Data Collector - Collect and format training data.

Collects evaluation results and converts them into training-ready examples.
Supports multiple output formats and quality filtering.

Design principles:
- Quality-first: Only collect high-quality examples
- Format-agnostic: Support multiple training formats
- Deduplication: Avoid duplicate examples
- Privacy-aware: Scrub sensitive data
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from feedback.loop.evaluator import EvaluationResult
from feedback.loop.reward_signal import RewardSignal, RewardType

logger = logging.getLogger(__name__)

ExampleType = Literal["positive", "correction", "negative"]
OutputFormat = Literal["alpaca", "jsonl", "openai", "custom"]


@dataclass(slots=True)
class DataCollectionConfig:
    """Configuration for data collection."""

    # Quality thresholds
    min_score_for_positive: float = 0.8
    min_score_for_correction: float = 0.4
    max_negative_examples: int = 100  # Limit negative examples

    # Output
    output_format: OutputFormat = "alpaca"
    output_dir: str = "data/feedback_collected"

    # Filtering
    deduplicate: bool = True
    scrub_paths: bool = True
    scrub_tokens: bool = True

    # Limits
    max_examples_per_session: int = 500
    max_positive_examples: int = 10000
    max_correction_examples: int = 5000


@dataclass(slots=True)
class CollectedExample:
    """A collected training example."""

    example_id: str
    example_type: ExampleType
    score: float
    reward_value: float

    # Content
    input_text: str
    output_text: str
    correction_text: str = ""  # For correction examples

    # Metadata
    domain: str = ""
    task_id: str = ""
    session_id: str = ""
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    model_version: str = ""

    # Quality
    quality_tier: str = ""
    errors: list[str] = field(default_factory=list)

    # Hash for deduplication
    content_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "example_id": self.example_id,
            "example_type": self.example_type,
            "score": self.score,
            "reward_value": self.reward_value,
            "input_text": self.input_text,
            "output_text": self.output_text,
            "correction_text": self.correction_text,
            "domain": self.domain,
            "task_id": self.task_id,
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "model_version": self.model_version,
            "quality_tier": self.quality_tier,
            "errors": self.errors,
            "content_hash": self.content_hash,
        }

    def to_alpaca(self) -> dict[str, str]:
        """Convert to Alpaca format."""
        if self.example_type == "correction" and self.correction_text:
            return {
                "instruction": self.input_text,
                "input": "",
                "output": f"[CORRECTION] {self.correction_text}\n\n{self.output_text}",
            }
        return {
            "instruction": self.input_text,
            "input": "",
            "output": self.output_text,
        }

    def to_jsonl(self) -> str:
        """Convert to JSONL line."""
        return json.dumps(self.to_dict(), ensure_ascii=False)


class FeedbackDataCollector:
    """Collect and format training data from feedback.

    Collects evaluation results and reward signals, converts them
    into training-ready examples in various formats.

    Usage:
        collector = FeedbackDataCollector()
        example = collector.collect(input_text, output_text, evaluation, signal)
        collector.save_to_file("training_data.jsonl")
    """

    def __init__(
        self,
        config: DataCollectionConfig | None = None,
    ) -> None:
        """Initialize data collector.

        Args:
            config: Optional collection configuration
        """
        self.config = config or DataCollectionConfig()
        self._examples: list[CollectedExample] = []
        self._hashes: set[str] = set()
        self._counts = {"positive": 0, "correction": 0, "negative": 0}

    def collect(
        self,
        input_text: str,
        output_text: str,
        evaluation: EvaluationResult,
        signal: RewardSignal,
        correction_text: str = "",
        session_id: str = "",
        model_version: str = "",
    ) -> CollectedExample | None:
        """Collect a training example from feedback.

        Args:
            input_text: Input prompt/task
            output_text: Generated output
            evaluation: Evaluation result
            signal: Reward signal
            correction_text: Optional correction text
            session_id: Session identifier
            model_version: Model version used

        Returns:
            CollectedExample or None if filtered
        """
        # Check limits
        if len(self._examples) >= self.config.max_examples_per_session:
            logger.warning("Max examples per session reached")
            return None

        # Determine example type
        example_type = self._map_reward_type(signal.reward_type)

        # Check type limits
        if example_type == "negative" and self._counts["negative"] >= self.config.max_negative_examples:
            logger.debug("Max negative examples reached, skipping")
            return None

        # Scrub sensitive data
        if self.config.scrub_paths:
            input_text = self._scrub_paths(input_text)
            output_text = self._scrub_paths(output_text)

        if self.config.scrub_tokens:
            input_text = self._scrub_tokens(input_text)
            output_text = self._scrub_tokens(output_text)

        # Generate hash for deduplication
        content_hash = self._generate_hash(input_text, output_text)

        if self.config.deduplicate and content_hash in self._hashes:
            logger.debug("Duplicate example, skipping")
            return None

        # Create example
        example_id = f"ex_{uuid4().hex[:8]}"

        example = CollectedExample(
            example_id=example_id,
            example_type=example_type,
            score=signal.score,
            reward_value=signal.reward_value,
            input_text=input_text,
            output_text=output_text,
            correction_text=correction_text,
            domain=signal.domain,
            task_id=signal.task_id,
            session_id=session_id,
            model_version=model_version,
            quality_tier=signal.quality_tier,
            errors=evaluation.errors,
            content_hash=content_hash,
        )

        self._examples.append(example)
        self._hashes.add(content_hash)
        self._counts[example_type] += 1

        return example

    def _map_reward_type(self, reward_type: RewardType) -> ExampleType:
        """Map reward type to example type."""
        mapping = {
            "positive": "positive",
            "correction": "correction",
            "negative": "negative",
            "neutral": "negative",
        }
        return mapping[reward_type]

    def _generate_hash(self, input_text: str, output_text: str) -> str:
        """Generate content hash for deduplication."""
        content = f"{input_text}|{output_text}"
        return hashlib.md5(content.encode()).hexdigest()

    def _scrub_paths(self, text: str) -> str:
        """Remove absolute paths from text."""
        import re
        # Replace Windows paths
        text = re.sub(r'[A-Z]:\\[^\s]+', '[PATH]', text)
        # Replace Unix paths
        text = re.sub(r'/[^\s]+', '[PATH]', text)
        return text

    def _scrub_tokens(self, text: str) -> str:
        """Remove potential tokens/secrets from text."""
        import re
        # Remove potential API keys
        text = re.sub(r'[a-zA-Z0-9]{32,}', '[TOKEN]', text)
        return text

    def get_examples(
        self,
        example_type: ExampleType | None = None,
    ) -> list[CollectedExample]:
        """Get collected examples, optionally filtered by type.

        Args:
            example_type: Optional filter by type

        Returns:
            List of examples
        """
        if example_type:
            return [e for e in self._examples if e.example_type == example_type]
        return list(self._examples)

    def get_positive_examples(self) -> list[CollectedExample]:
        """Get all positive examples."""
        return self.get_examples("positive")

    def get_correction_examples(self) -> list[CollectedExample]:
        """Get all correction examples."""
        return self.get_examples("correction")

    def get_negative_examples(self) -> list[CollectedExample]:
        """Get all negative examples."""
        return self.get_examples("negative")

    def save_to_file(
        self,
        filepath: Path | str,
        format: OutputFormat | None = None,
    ) -> int:
        """Save collected examples to file.

        Args:
            filepath: Output file path
            format: Output format (uses config if None)

        Returns:
            Number of examples saved
        """
        output_format = format or self.config.output_format
        output_path = Path(filepath)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        examples = self.get_examples()
        saved_count = 0

        with open(output_path, "w", encoding="utf-8") as f:
            for example in examples:
                if output_format == "alpaca":
                    line = json.dumps(example.to_alpaca(), ensure_ascii=False)
                elif output_format == "jsonl":
                    line = example.to_jsonl()
                else:
                    line = json.dumps(example.to_dict(), ensure_ascii=False)

                f.write(line + "\n")
                saved_count += 1

        logger.info(f"Saved {saved_count} examples to {output_path}")
        return saved_count

    def export_training_set(
        self,
        output_dir: Path | str | None = None,
    ) -> dict[str, int]:
        """Export training set with train/val split.

        Args:
            output_dir: Output directory (uses config if None)

        Returns:
            Dict with counts per split
        """
        out_dir = Path(output_dir or self.config.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        positive = self.get_positive_examples()
        correction = self.get_correction_examples()
        negative = self.get_negative_examples()

        # Combine positive and correction for training
        train_examples = positive + correction

        # Shuffle (simple)
        import random
        random.shuffle(train_examples)

        # Split 90/10
        split_idx = int(len(train_examples) * 0.9)
        train_set = train_examples[:split_idx]
        val_set = train_examples[split_idx:]

        counts = {}

        # Save train set
        if train_set:
            train_path = out_dir / "train.jsonl"
            with open(train_path, "w", encoding="utf-8") as f:
                for ex in train_set:
                    f.write(json.dumps(ex.to_alpaca(), ensure_ascii=False) + "\n")
            counts["train"] = len(train_set)

        # Save val set
        if val_set:
            val_path = out_dir / "val.jsonl"
            with open(val_path, "w", encoding="utf-8") as f:
                for ex in val_set:
                    f.write(json.dumps(ex.to_alpaca(), ensure_ascii=False) + "\n")
            counts["val"] = len(val_set)

        # Save negative separately (for analysis)
        if negative:
            neg_path = out_dir / "negative.jsonl"
            with open(neg_path, "w", encoding="utf-8") as f:
                for ex in negative:
                    f.write(json.dumps(ex.to_dict(), ensure_ascii=False) + "\n")
            counts["negative"] = len(negative)

        return counts

    def get_summary(self) -> dict[str, Any]:
        """Get collection summary."""
        return {
            "total_examples": len(self._examples),
            "positive_count": self._counts["positive"],
            "correction_count": self._counts["correction"],
            "negative_count": self._counts["negative"],
            "unique_hashes": len(self._hashes),
        }

    def clear(self) -> None:
        """Clear collected examples."""
        self._examples = []
        self._hashes = set()
        self._counts = {"positive": 0, "correction": 0, "negative": 0}