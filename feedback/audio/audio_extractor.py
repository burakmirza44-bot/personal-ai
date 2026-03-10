"""Audio Extractor - Extract audio from video files.

Uses FFmpeg to extract audio tracks from video files for transcription.
Part of the feedback loop for tutorial learning.

Design principles:
- FFmpeg-first (already integrated in project)
- Support multiple audio formats
- Configurable output format for Whisper
- Progress tracking for batch processing
"""

from __future__ import annotations

import logging
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Default output format for Whisper (16kHz mono WAV)
DEFAULT_AUDIO_FORMAT = "wav"
DEFAULT_SAMPLE_RATE = 16000
DEFAULT_CHANNELS = 1


@dataclass(slots=True)
class AudioExtractionResult:
    """Result of audio extraction."""

    success: bool
    audio_path: Path | None
    source_video: str
    duration_seconds: float = 0.0
    file_size_bytes: int = 0
    extraction_time_seconds: float = 0.0
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "audio_path": str(self.audio_path) if self.audio_path else None,
            "source_video": self.source_video,
            "duration_seconds": self.duration_seconds,
            "file_size_bytes": self.file_size_bytes,
            "extraction_time_seconds": self.extraction_time_seconds,
            "error": self.error,
        }


class AudioExtractor:
    """Extract audio from video files using FFmpeg.

    Converts video audio tracks to format suitable for speech recognition.
    Default output: 16kHz mono WAV (optimal for Whisper).

    Usage:
        extractor = AudioExtractor()
        result = extractor.extract("video.mp4", "audio.wav")
    """

    def __init__(
        self,
        output_format: str = DEFAULT_AUDIO_FORMAT,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        channels: int = DEFAULT_CHANNELS,
        timeout_seconds: int = 300,
    ) -> None:
        """Initialize audio extractor.

        Args:
            output_format: Output audio format (wav, mp3, etc.)
            sample_rate: Sample rate in Hz (16000 for Whisper)
            channels: Number of audio channels (1 for mono)
            timeout_seconds: Timeout for extraction
        """
        self.output_format = output_format
        self.sample_rate = sample_rate
        self.channels = channels
        self.timeout_seconds = timeout_seconds

    def extract(
        self,
        video_path: Path | str,
        output_path: Path | str | None = None,
        start_time: float = 0.0,
        end_time: float | None = None,
    ) -> AudioExtractionResult:
        """Extract audio from a video file.

        Args:
            video_path: Path to video file
            output_path: Path for output audio (auto-generated if None)
            start_time: Start time in seconds
            end_time: End time in seconds (None = entire video)

        Returns:
            AudioExtractionResult with extracted audio path
        """
        video = Path(video_path)
        start = time.monotonic()

        if not video.exists():
            return AudioExtractionResult(
                success=False,
                audio_path=None,
                source_video=str(video),
                error=f"Video file not found: {video}",
            )

        # Generate output path if not provided
        if output_path:
            audio = Path(output_path)
        else:
            audio = video.parent / f"{video.stem}_audio.{self.output_format}"

        # Build FFmpeg command
        cmd = [
            "ffmpeg",
            "-y",  # Overwrite output
            "-i", str(video),
            "-vn",  # No video
            "-acodec", "pcm_s16le" if self.output_format == "wav" else "libmp3lame",
            "-ar", str(self.sample_rate),
            "-ac", str(self.channels),
        ]

        # Add time range
        if start_time > 0:
            cmd.extend(["-ss", str(start_time)])
        if end_time is not None:
            cmd.extend(["-t", str(end_time - start_time)])

        cmd.append(str(audio))

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )

            if result.returncode != 0:
                return AudioExtractionResult(
                    success=False,
                    audio_path=None,
                    source_video=str(video),
                    error=f"FFmpeg error: {result.stderr[:500]}",
                    extraction_time_seconds=time.monotonic() - start,
                )

            # Get audio info
            duration = self._get_audio_duration(audio)
            file_size = audio.stat().st_size if audio.exists() else 0

            logger.info(
                f"Extracted audio from {video.name}: "
                f"{duration:.1f}s, {file_size / 1024 / 1024:.1f}MB"
            )

            return AudioExtractionResult(
                success=True,
                audio_path=audio,
                source_video=str(video),
                duration_seconds=duration,
                file_size_bytes=file_size,
                extraction_time_seconds=time.monotonic() - start,
            )

        except subprocess.TimeoutExpired:
            return AudioExtractionResult(
                success=False,
                audio_path=None,
                source_video=str(video),
                error=f"Extraction timed out after {self.timeout_seconds}s",
                extraction_time_seconds=time.monotonic() - start,
            )
        except Exception as e:
            return AudioExtractionResult(
                success=False,
                audio_path=None,
                source_video=str(video),
                error=str(e),
                extraction_time_seconds=time.monotonic() - start,
            )

    def extract_batch(
        self,
        video_dir: Path | str,
        output_dir: Path | str | None = None,
        pattern: str = "*.mp4",
        progress_callback: Any = None,
    ) -> list[tuple[str, AudioExtractionResult]]:
        """Extract audio from multiple videos.

        Args:
            video_dir: Directory containing video files
            output_dir: Output directory (same as input if None)
            pattern: Glob pattern for video files
            progress_callback: Optional callback for progress

        Returns:
            List of (video_name, AudioExtractionResult) tuples
        """
        video_path = Path(video_dir)
        output_path = Path(output_dir) if output_dir else video_path
        output_path.mkdir(parents=True, exist_ok=True)

        video_files = sorted(video_path.glob(pattern))
        results: list[tuple[str, AudioExtractionResult]] = []

        for i, video in enumerate(video_files):
            if progress_callback:
                progress_callback(i, len(video_files), video.name)

            audio_file = output_path / f"{video.stem}_audio.{self.output_format}"
            result = self.extract(video, audio_file)
            results.append((video.name, result))

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


def extract_audio_from_video(
    video_path: Path | str,
    output_path: Path | str | None = None,
) -> AudioExtractionResult:
    """Convenience function for single video audio extraction.

    Args:
        video_path: Path to video file
        output_path: Path for output audio

    Returns:
        AudioExtractionResult
    """
    extractor = AudioExtractor()
    return extractor.extract(video_path, output_path)