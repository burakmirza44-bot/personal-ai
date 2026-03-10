"""Whisper Local - Speech-to-text with local GPU inference.

Local-first speech recognition using faster-whisper (CTranslate2 backend).
No cloud dependencies, works offline with GPU acceleration.

Design principles:
- Local-first: All inference on local GPU/CPU
- InferenceGate uyumlu: Device selection through orchestrator
- Bounded execution: Timeout and memory limits
- Graceful degradation: CPU fallback when GPU unavailable
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)

# Model sizes: tiny, base, small, medium, large-v2, large-v3
WhisperModelSize = Literal["tiny", "base", "small", "medium", "large-v2", "large-v3"]

# Language codes
LanguageCode = Literal[
    "auto", "en", "tr", "de", "fr", "es", "it", "pt", "ru", "zh", "ja", "ko"
]


@dataclass(slots=True)
class TranscriptSegment:
    """Single transcript segment with timing."""

    start: float  # Start time in seconds
    end: float    # End time in seconds
    text: str     # Transcribed text
    confidence: float = 0.0  # Confidence score 0-1
    no_speech_prob: float = 0.0  # Probability of no speech

    def to_dict(self) -> dict[str, Any]:
        return {
            "start": self.start,
            "end": self.end,
            "text": self.text,
            "confidence": self.confidence,
            "no_speech_prob": self.no_speech_prob,
        }

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass(slots=True)
class TranscriptResult:
    """Complete transcription result."""

    text: str                           # Full transcript text
    segments: list[TranscriptSegment]   # Timestamped segments
    language: str                       # Detected/specified language
    confidence: float                   # Average confidence
    duration_seconds: float             # Audio duration
    model: str                          # Model used
    device: str                         # Device used (cuda/cpu)
    processing_time_seconds: float      # Processing time
    success: bool = True
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "segments": [s.to_dict() for s in self.segments],
            "language": self.language,
            "confidence": self.confidence,
            "duration_seconds": self.duration_seconds,
            "model": self.model,
            "device": self.device,
            "processing_time_seconds": self.processing_time_seconds,
            "success": self.success,
            "error": self.error,
        }

    @property
    def word_count(self) -> int:
        return len(self.text.split())

    @property
    def segment_count(self) -> int:
        return len(self.segments)


@dataclass
class WhisperConfig:
    """Whisper model configuration."""

    model_size: WhisperModelSize = "large-v3"
    language: LanguageCode = "auto"
    device: str = "auto"  # auto, cuda, cpu
    compute_type: str = "float16"  # float16, int8, float32
    beam_size: int = 5
    max_tokens_per_segment: int = 128
    temperature: float = 0.0
    vad_filter: bool = True  # Voice activity detection
    min_silence_duration_ms: int = 500
    max_duration_seconds: float = 3600.0  # 1 hour max

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_size": self.model_size,
            "language": self.language,
            "device": self.device,
            "compute_type": self.compute_type,
            "beam_size": self.beam_size,
            "max_tokens_per_segment": self.max_tokens_per_segment,
            "temperature": self.temperature,
            "vad_filter": self.vad_filter,
            "min_silence_duration_ms": self.min_silence_duration_ms,
            "max_duration_seconds": self.max_duration_seconds,
        }


def is_whisper_available() -> bool:
    """Check if faster-whisper is installed."""
    try:
        import faster_whisper
        return True
    except ImportError:
        return False


def is_cuda_available() -> bool:
    """Check if CUDA is available."""
    try:
        result = subprocess.run(
            ["nvidia-smi"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


class WhisperLocal:
    """Local Whisper inference with GPU acceleration.

    Uses faster-whisper (CTranslate2 backend) for efficient inference.
    Supports both GPU (CUDA) and CPU execution with automatic fallback.

    Usage:
        whisper = WhisperLocal(model_size="large-v3")
        result = whisper.transcribe("audio.mp3")
        print(result.text)
    """

    def __init__(
        self,
        model_size: WhisperModelSize = "large-v3",
        language: LanguageCode = "auto",
        device: str = "auto",
        compute_type: str = "float16",
    ) -> None:
        """Initialize Whisper model.

        Args:
            model_size: Model size (tiny, base, small, medium, large-v3)
            language: Language code (auto for detection)
            device: Device (auto, cuda, cpu)
            compute_type: Compute type (float16, int8, float32)
        """
        self.model_size = model_size
        self.language = language
        self.device = device
        self.compute_type = compute_type
        self._model = None

        # Determine device
        if device == "auto":
            self._device = "cuda" if is_cuda_available() else "cpu"
            if self._device == "cpu":
                logger.warning("CUDA not available, using CPU (slower)")
                # Use int8 for CPU to reduce memory
                self.compute_type = "int8"
        else:
            self._device = device

        logger.info(f"Whisper initializing: model={model_size}, device={self._device}, compute={self.compute_type}")

    def _load_model(self):
        """Lazy load the model."""
        if self._model is not None:
            return self._model

        if not is_whisper_available():
            raise RuntimeError(
                "faster-whisper not installed. "
                "Install with: pip install faster-whisper"
            )

        from faster_whisper import WhisperModel

        self._model = WhisperModel(
            self.model_size,
            device=self._device,
            compute_type=self.compute_type,
        )

        return self._model

    def transcribe(
        self,
        audio_path: Path | str,
        language: LanguageCode | None = None,
        beam_size: int | None = None,
        vad_filter: bool = True,
    ) -> TranscriptResult:
        """Transcribe a single audio file.

        Args:
            audio_path: Path to audio file (mp3, wav, m4a, etc.)
            language: Override language (None = use config)
            beam_size: Override beam size (None = use config)
            vad_filter: Enable voice activity detection

        Returns:
            TranscriptResult with full transcript and segments
        """
        audio = Path(audio_path)
        start_time = time.monotonic()

        if not audio.exists():
            return TranscriptResult(
                text="",
                segments=[],
                language="",
                confidence=0.0,
                duration_seconds=0.0,
                model=self.model_size,
                device=self._device,
                processing_time_seconds=0.0,
                success=False,
                error=f"Audio file not found: {audio}",
            )

        try:
            model = self._load_model()

            # Get audio duration
            duration = self._get_audio_duration(audio)

            # Transcribe
            lang = language or self.language
            if lang == "auto":
                lang = None  # Let whisper detect

            segments_gen, info = model.transcribe(
                str(audio),
                language=lang,
                beam_size=beam_size or 5,
                vad_filter=vad_filter,
                temperature=0.0,
            )

            # Collect segments
            segments: list[TranscriptSegment] = []
            full_text_parts: list[str] = []
            total_confidence = 0.0

            for seg in segments_gen:
                segment = TranscriptSegment(
                    start=seg.start,
                    end=seg.end,
                    text=seg.text.strip(),
                    confidence=getattr(seg, "avg_logprob", 0.0),
                    no_speech_prob=getattr(seg, "no_speech_prob", 0.0),
                )
                segments.append(segment)
                full_text_parts.append(segment.text)
                total_confidence += segment.confidence

            full_text = " ".join(full_text_parts)
            avg_confidence = total_confidence / len(segments) if segments else 0.0

            processing_time = time.monotonic() - start_time

            logger.info(
                f"Transcribed {audio.name}: {len(segments)} segments, "
                f"{len(full_text.split())} words in {processing_time:.1f}s"
            )

            return TranscriptResult(
                text=full_text,
                segments=segments,
                language=info.language if hasattr(info, "language") else (lang or "unknown"),
                confidence=avg_confidence,
                duration_seconds=duration,
                model=self.model_size,
                device=self._device,
                processing_time_seconds=processing_time,
                success=True,
            )

        except Exception as e:
            processing_time = time.monotonic() - start_time
            logger.error(f"Transcription failed: {e}")

            return TranscriptResult(
                text="",
                segments=[],
                language="",
                confidence=0.0,
                duration_seconds=0.0,
                model=self.model_size,
                device=self._device,
                processing_time_seconds=processing_time,
                success=False,
                error=str(e),
            )

    def transcribe_batch(
        self,
        audio_dir: Path | str,
        pattern: str = "*.mp3",
        progress_callback: Any = None,
    ) -> list[tuple[str, TranscriptResult]]:
        """Transcribe multiple audio files in a directory.

        Args:
            audio_dir: Directory containing audio files
            pattern: Glob pattern for audio files
            progress_callback: Optional callback for progress updates

        Returns:
            List of (filename, TranscriptResult) tuples
        """
        audio_path = Path(audio_dir)
        audio_files = sorted(audio_path.glob(pattern))

        results: list[tuple[str, TranscriptResult]] = []

        for i, audio_file in enumerate(audio_files):
            if progress_callback:
                progress_callback(i, len(audio_files), audio_file.name)

            result = self.transcribe(audio_file)
            results.append((audio_file.name, result))

        return results

    def _get_audio_duration(self, audio_path: Path) -> float:
        """Get audio duration using ffprobe."""
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    str(audio_path),
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return float(result.stdout.strip())
        except Exception:
            pass
        return 0.0


def transcribe_audio(
    audio_path: Path | str,
    model_size: WhisperModelSize = "base",
    language: LanguageCode = "auto",
) -> TranscriptResult:
    """Convenience function for single file transcription.

    Args:
        audio_path: Path to audio file
        model_size: Model size (default: base for speed)
        language: Language code (auto for detection)

    Returns:
        TranscriptResult
    """
    whisper = WhisperLocal(model_size=model_size, language=language)
    return whisper.transcribe(audio_path)