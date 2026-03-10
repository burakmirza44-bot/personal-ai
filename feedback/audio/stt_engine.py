"""STT Engine - Speech-to-text engine wrapper.

Wraps the Whisper local inference for use in feedback loop.
Provides unified interface for transcribing audio from tutorials.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.audio.whisper_local import (
    WhisperLocal,
    TranscriptResult,
    WhisperModelSize,
    is_whisper_available,
)
from feedback.audio.audio_extractor import AudioExtractor, AudioExtractionResult

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class STTResult:
    """Result of speech-to-text processing."""

    success: bool
    transcript: str
    segments: list[dict[str, Any]]
    language: str
    confidence: float
    audio_duration_seconds: float
    processing_time_seconds: float
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "transcript": self.transcript,
            "segments": self.segments,
            "language": self.language,
            "confidence": self.confidence,
            "audio_duration_seconds": self.audio_duration_seconds,
            "processing_time_seconds": self.processing_time_seconds,
            "error": self.error,
        }


class STTEngine:
    """Speech-to-text engine for tutorial transcription.

    Combines audio extraction and Whisper transcription.
    Designed for tutorial video processing in feedback loop.

    Usage:
        engine = STTEngine(model_size="large-v3")
        result = engine.transcribe_video("tutorial.mp4")
    """

    def __init__(
        self,
        model_size: WhisperModelSize = "large-v3",
        language: str = "auto",
        device: str = "auto",
    ) -> None:
        """Initialize STT engine.

        Args:
            model_size: Whisper model size
            language: Language code (auto for detection)
            device: Device (auto, cuda, cpu)
        """
        self.model_size = model_size
        self.language = language
        self.device = device
        self._whisper: WhisperLocal | None = None
        self._extractor = AudioExtractor()

    def _get_whisper(self) -> WhisperLocal:
        """Get or create Whisper instance."""
        if self._whisper is None:
            if not is_whisper_available():
                raise RuntimeError(
                    "faster-whisper not installed. "
                    "Install with: pip install faster-whisper"
                )
            self._whisper = WhisperLocal(
                model_size=self.model_size,
                language=self.language,
                device=self.device,
            )
        return self._whisper

    def transcribe_audio(
        self,
        audio_path: Path | str,
    ) -> STTResult:
        """Transcribe an audio file.

        Args:
            audio_path: Path to audio file

        Returns:
            STTResult with transcript
        """
        whisper = self._get_whisper()
        result = whisper.transcribe(audio_path)

        return STTResult(
            success=result.success,
            transcript=result.text,
            segments=[s.to_dict() for s in result.segments],
            language=result.language,
            confidence=result.confidence,
            audio_duration_seconds=result.duration_seconds,
            processing_time_seconds=result.processing_time_seconds,
            error=result.error,
        )

    def transcribe_video(
        self,
        video_path: Path | str,
        extract_audio: bool = True,
        audio_output_path: Path | str | None = None,
    ) -> STTResult:
        """Transcribe audio from a video file.

        Args:
            video_path: Path to video file
            extract_audio: Whether to extract audio first
            audio_output_path: Path for extracted audio

        Returns:
            STTResult with transcript
        """
        video = Path(video_path)

        if not video.exists():
            return STTResult(
                success=False,
                transcript="",
                segments=[],
                language="",
                confidence=0.0,
                audio_duration_seconds=0.0,
                processing_time_seconds=0.0,
                error=f"Video file not found: {video}",
            )

        # Extract audio if needed
        if extract_audio:
            extraction = self._extractor.extract(video, audio_output_path)
            if not extraction.success:
                return STTResult(
                    success=False,
                    transcript="",
                    segments=[],
                    language="",
                    confidence=0.0,
                    audio_duration_seconds=0.0,
                    processing_time_seconds=0.0,
                    error=f"Audio extraction failed: {extraction.error}",
                )
            audio_path = extraction.audio_path
        else:
            audio_path = video

        # Transcribe
        return self.transcribe_audio(audio_path)

    def transcribe_batch(
        self,
        video_paths: list[Path | str],
        progress_callback: Any = None,
    ) -> list[tuple[str, STTResult]]:
        """Transcribe multiple videos.

        Args:
            video_paths: List of video paths
            progress_callback: Optional progress callback

        Returns:
            List of (video_name, STTResult) tuples
        """
        results: list[tuple[str, STTResult]] = []

        for i, video_path in enumerate(video_paths):
            if progress_callback:
                progress_callback(i, len(video_paths), str(video_path))

            result = self.transcribe_video(video_path)
            results.append((Path(video_path).name, result))

        return results


def transcribe_video_audio(
    video_path: Path | str,
    model_size: WhisperModelSize = "base",
) -> STTResult:
    """Convenience function for video transcription.

    Args:
        video_path: Path to video file
        model_size: Whisper model size (base for speed)

    Returns:
        STTResult with transcript
    """
    engine = STTEngine(model_size=model_size)
    return engine.transcribe_video(video_path)