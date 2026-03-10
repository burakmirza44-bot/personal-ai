"""Data Formatter - Format feedback data for training.

Converts collected feedback examples into training-ready formats
compatible with various training frameworks.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
import random

logger = logging.getLogger(__name__)

OutputFormat = Literal["alpaca", "jsonl", "openai", "sharegpt"]


@dataclass(slots=True)
class FormattingConfig:
    """Configuration for data formatting."""

    output_format: OutputFormat = "alpaca"
    train_val_split: float = 0.9
    shuffle: bool = True
    seed: int = 42
    max_input_length: int = 2048
    max_output_length: int = 1024


class DataFormatter:
    """Format feedback data for training.

    Converts collected examples into training-ready formats.
    Handles train/val splitting and deduplication.

    Usage:
        formatter = DataFormatter()
        formatter.format_and_save(examples, output_dir)
    """

    def __init__(
        self,
        config: FormattingConfig | None = None,
    ) -> None:
        """Initialize data formatter.

        Args:
            config: Optional formatting configuration
        """
        self.config = config or FormattingConfig()

    def format_example(
        self,
        input_text: str,
        output_text: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Format a single example.

        Args:
            input_text: Input text
            output_text: Output text
            metadata: Optional metadata

        Returns:
            Formatted example dict
        """
        # Truncate if needed
        if len(input_text) > self.config.max_input_length:
            input_text = input_text[:self.config.max_input_length]
            logger.warning("Input truncated to max length")

        if len(output_text) > self.config.max_output_length:
            output_text = output_text[:self.config.max_output_length]
            logger.warning("Output truncated to max length")

        if self.config.output_format == "alpaca":
            return {
                "instruction": input_text,
                "input": "",
                "output": output_text,
            }
        elif self.config.output_format == "jsonl":
            return {
                "input": input_text,
                "output": output_text,
                "metadata": metadata or {},
            }
        elif self.config.output_format == "openai":
            return {
                "messages": [
                    {"role": "user", "content": input_text},
                    {"role": "assistant", "content": output_text},
                ],
            }
        elif self.config.output_format == "sharegpt":
            return {
                "conversations": [
                    {"from": "human", "value": input_text},
                    {"from": "gpt", "value": output_text},
                ],
            }
        else:
            return {
                "input": input_text,
                "output": output_text,
            }

    def format_batch(
        self,
        examples: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Format a batch of examples.

        Args:
            examples: List of raw examples

        Returns:
            List of formatted examples
        """
        formatted = []

        for ex in examples:
            input_text = ex.get("input_text", "")
            output_text = ex.get("output_text", "")
            metadata = ex.get("metadata", {})

            if not input_text or not output_text:
                continue

            formatted_ex = self.format_example(input_text, output_text, metadata)
            formatted.append(formatted_ex)

        return formatted

    def split_train_val(
        self,
        examples: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Split examples into train and validation sets.

        Args:
            examples: List of formatted examples

        Returns:
            Tuple of (train_examples, val_examples)
        """
        if self.config.shuffle:
            random.seed(self.config.seed)
            random.shuffle(examples)

        split_idx = int(len(examples) * self.config.train_val_split)
        train = examples[:split_idx]
        val = examples[split_idx:]

        return train, val

    def save(
        self,
        examples: list[dict[str, Any]],
        output_path: Path | str,
    ) -> int:
        """Save examples to file.

        Args:
            examples: List of formatted examples
            output_path: Output file path

        Returns:
            Number of examples saved
        """
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        with open(output, "w", encoding="utf-8") as f:
            for ex in examples:
                f.write(json.dumps(ex, ensure_ascii=False) + "\n")

        logger.info(f"Saved {len(examples)} examples to {output}")
        return len(examples)

    def format_and_save(
        self,
        examples: list[dict[str, Any]],
        output_dir: Path | str,
    ) -> dict[str, int]:
        """Format examples and save with train/val split.

        Args:
            examples: List of raw examples
            output_dir: Output directory

        Returns:
            Dict with counts
        """
        formatted = self.format_batch(examples)
        train, val = self.split_train_val(formatted)

        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)

        counts = {}

        if train:
            train_path = output / "train.jsonl"
            counts["train"] = self.save(train, train_path)

        if val:
            val_path = output / "val.jsonl"
            counts["val"] = self.save(val, val_path)

        return counts


def format_for_training(
    examples: list[dict[str, Any]],
    output_dir: Path | str,
    format: OutputFormat = "alpaca",
) -> dict[str, int]:
    """Convenience function for formatting data.

    Args:
        examples: List of raw examples
        output_dir: Output directory
        format: Output format

    Returns:
        Dict with counts
    """
    config = FormattingConfig(output_format=format)
    formatter = DataFormatter(config=config)
    return formatter.format_and_save(examples, output_dir)