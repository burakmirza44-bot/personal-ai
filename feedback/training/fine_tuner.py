"""Fine-Tuner - LoRA/QLoRA fine-tuning wrapper.

Provides a simple interface for fine-tuning models using PEFT.
Integrates with the existing inference infrastructure.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)

TrainingStatus = Literal["pending", "running", "completed", "failed", "cancelled"]


@dataclass(slots=True)
class FineTuneConfig:
    """Configuration for fine-tuning."""

    # Model
    base_model: str = "qwen2.5-14b"
    output_dir: str = "models/finetuned"

    # LoRA
    lora_r: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.05

    # Training
    num_epochs: int = 3
    batch_size: int = 4
    learning_rate: float = 2e-4
    warmup_steps: int = 100
    max_seq_length: int = 2048

    # Optimization
    gradient_accumulation_steps: int = 4
    fp16: bool = True
    gradient_checkpointing: bool = True

    # Saving
    save_steps: int = 500
    eval_steps: int = 500
    save_total_limit: int = 3


@dataclass(slots=True)
class FineTuneResult:
    """Result of a fine-tuning run."""

    run_id: str
    status: TrainingStatus
    config: FineTuneConfig

    # Metrics
    train_loss: float = 0.0
    eval_loss: float = 0.0
    final_accuracy: float = 0.0

    # Timing
    start_time: str = ""
    end_time: str = ""
    duration_seconds: float = 0.0

    # Output
    output_model_path: str = ""
    checkpoint_paths: list[str] = field(default_factory=list)

    # Errors
    error: str = ""
    logs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "config": self.config.__dict__,
            "train_loss": self.train_loss,
            "eval_loss": self.eval_loss,
            "final_accuracy": self.final_accuracy,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_seconds": self.duration_seconds,
            "output_model_path": self.output_model_path,
            "checkpoint_paths": self.checkpoint_paths,
            "error": self.error,
        }


class FineTuner:
    """LoRA/QLoRA fine-tuning wrapper.

    Provides a simple interface for fine-tuning with PEFT.
    Designed to work with the existing inference infrastructure.

    Usage:
        tuner = FineTuner(config)
        result = tuner.train(train_data_path, val_data_path)
    """

    def __init__(
        self,
        config: FineTuneConfig | None = None,
    ) -> None:
        """Initialize fine-tuner.

        Args:
            config: Optional fine-tuning configuration
        """
        self.config = config or FineTuneConfig()
        self._run_id = f"ft_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

    def prepare_training_script(self) -> str:
        """Generate training script content.

        Returns:
            Training script as string
        """
        script = f'''#!/usr/bin/env python
"""Auto-generated fine-tuning script for run {self._run_id}"""

import torch
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    TrainingArguments,
    Trainer,
    DataCollatorForSeq2Seq,
)
from peft import LoraConfig, get_peft_model, TaskType, prepare_model_for_kbit_training
from datasets import load_dataset
import sys

def main():
    # Load model and tokenizer
    model_name = "{self.config.base_model}"
    tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        torch_dtype=torch.float16 if {self.config.fp16} else torch.float32,
        device_map="auto",
        trust_remote_code=True,
    )

    # Prepare for training
    if {self.config.gradient_checkpointing}:
        model.gradient_checkpointing_enable()
        model = prepare_model_for_kbit_training(model)

    # LoRA config
    lora_config = LoraConfig(
        r={self.config.lora_r},
        lora_alpha={self.config.lora_alpha},
        lora_dropout={self.config.lora_dropout},
        bias="none",
        task_type=TaskType.CAUSAL_LM,
    )

    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    # Load dataset
    dataset = load_dataset("json", data_files={{"train": sys.argv[1]}})

    # Training arguments
    training_args = TrainingArguments(
        output_dir="{self.config.output_dir}",
        num_train_epochs={self.config.num_epochs},
        per_device_train_batch_size={self.config.batch_size},
        gradient_accumulation_steps={self.config.gradient_accumulation_steps},
        learning_rate={self.config.learning_rate},
        warmup_steps={self.config.warmup_steps},
        logging_steps=10,
        save_steps={self.config.save_steps},
        save_total_limit={self.config.save_total_limit},
        fp16={self.config.fp16},
        gradient_checkpointing={self.config.gradient_checkpointing},
        report_to="none",
    )

    # Trainer
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=dataset["train"],
        tokenizer=tokenizer,
    )

    # Train
    trainer.train()

    # Save
    model.save_pretrained("{self.config.output_dir}")
    tokenizer.save_pretrained("{self.config.output_dir}")

    print(f"Model saved to {self.config.output_dir}")

if __name__ == "__main__":
    main()
'''
        return script

    def train(
        self,
        train_data_path: Path | str,
        val_data_path: Path | str | None = None,
        dry_run: bool = False,
    ) -> FineTuneResult:
        """Run fine-tuning.

        Args:
            train_data_path: Path to training data
            val_data_path: Optional path to validation data
            dry_run: If True, only prepare but don't execute

        Returns:
            FineTuneResult with training status
        """
        result = FineTuneResult(
            run_id=self._run_id,
            status="pending",
            config=self.config,
            start_time=datetime.utcnow().isoformat(),
        )

        train_path = Path(train_data_path)
        if not train_path.exists():
            result.status = "failed"
            result.error = f"Training data not found: {train_path}"
            return result

        # Generate training script
        script = self.prepare_training_script()

        if dry_run:
            result.status = "completed"
            result.logs.append("Dry run - script generated but not executed")
            return result

        # Execute training
        try:
            import subprocess
            import tempfile

            # Write script to temp file
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".py",
                delete=False
            ) as f:
                f.write(script)
                script_path = f.name

            result.status = "running"

            # Run training
            process = subprocess.run(
                ["python", script_path, str(train_path)],
                capture_output=True,
                text=True,
                timeout=86400,  # 24 hours max
            )

            if process.returncode == 0:
                result.status = "completed"
                result.output_model_path = self.config.output_dir
            else:
                result.status = "failed"
                result.error = process.stderr[:1000]

            result.logs.append(process.stdout[:5000])

            # Cleanup
            os.unlink(script_path)

        except Exception as e:
            result.status = "failed"
            result.error = str(e)

        result.end_time = datetime.utcnow().isoformat()
        return result

    def estimate_training_time(
        self,
        num_examples: int,
    ) -> float:
        """Estimate training time in hours.

        Args:
            num_examples: Number of training examples

        Returns:
            Estimated hours
        """
        # Rough estimate based on typical speeds
        # ~2 examples/second on RTX 4080 with LoRA
        examples_per_second = 2
        total_steps = num_examples // self.config.batch_size
        total_steps = total_steps // self.config.gradient_accumulation_steps
        total_steps *= self.config.num_epochs

        hours = total_steps / (examples_per_second * 3600 / self.config.gradient_accumulation_steps)
        return max(0.1, hours)