"""Tests for STT Pipeline (Speech-to-Text)."""

import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from feedback.audio.audio_extractor import (
    AudioExtractor,
    AudioExtractionResult,
)
from feedback.audio.transcript_aligner import (
    TranscriptAligner,
    AlignedTranscript,
)


class TestAudioExtractor:
    """Test audio extraction from video."""

    def test_extractor_creation(self):
        """Test extractor can be created."""
        extractor = AudioExtractor()
        assert extractor is not None

    def test_extraction_result_structure(self):
        """Test extraction result structure."""
        result = AudioExtractionResult(
            success=True,
            audio_path=Path("test.wav"),
            source_video="test.mp4",
            duration_seconds=10.0,
            file_size_bytes=1000,
        )

        assert result.success
        assert result.duration_seconds == 10.0

    def test_missing_video_error(self):
        """Test error handling for missing video."""
        extractor = AudioExtractor()

        result = extractor.extract("nonexistent_video.mp4")

        assert not result.success
        assert "not found" in result.error.lower()


class TestTranscriptAligner:
    """Test transcript alignment."""

    def test_aligner_creation(self):
        """Test aligner can be created."""
        aligner = TranscriptAligner()
        assert aligner is not None

    def test_align_segments(self):
        """Test aligning transcript segments to frames."""
        aligner = TranscriptAligner(fps=1.0)

        segments = [
            {"start": 0.0, "end": 2.0, "text": "Hello world", "confidence": 0.9},
            {"start": 2.0, "end": 5.0, "text": "This is a test", "confidence": 0.8},
        ]

        aligned = aligner.align(segments, frame_count=10, fps=1.0)

        assert aligned.total_segments == 2
        assert aligned.total_frames == 10
        assert len(aligned.segments) == 2

    def test_get_text_for_time(self):
        """Test getting text for specific time."""
        aligner = TranscriptAligner(fps=1.0)

        segments = [
            {"start": 0.0, "end": 2.0, "text": "First segment", "confidence": 0.9},
            {"start": 2.0, "end": 5.0, "text": "Second segment", "confidence": 0.8},
        ]

        aligned = aligner.align(segments, frame_count=10, fps=1.0)

        text = aligned.get_text_for_time(1.0)
        assert "First" in text

        text = aligned.get_text_for_time(3.0)
        assert "Second" in text

    def test_aligned_transcript_structure(self):
        """Test aligned transcript structure."""
        aligned = AlignedTranscript(
            source_video="test.mp4",
            total_segments=2,
            total_frames=100,
            fps=1.0,
            duration_seconds=10.0,
        )

        assert aligned.source_video == "test.mp4"
        assert aligned.total_frames == 100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])