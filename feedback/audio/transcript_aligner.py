"""Transcript Aligner - Align audio transcript with video frames.

Maps transcript segments to video frame timestamps for
synchronized analysis of audio and visual content.

Design principles:
- Timestamp-based alignment
- Confidence-aware matching
- Supports multiple alignment strategies
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AlignedSegment:
    """A transcript segment aligned with frame information."""

    segment_index: int
    text: str
    start_time: float
    end_time: float
    confidence: float

    # Frame alignment
    start_frame: int = -1
    end_frame: int = -1
    frame_path: Path | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "segment_index": self.segment_index,
            "text": self.text,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "confidence": self.confidence,
            "start_frame": self.start_frame,
            "end_frame": self.end_frame,
            "frame_path": str(self.frame_path) if self.frame_path else None,
        }


@dataclass(slots=True)
class AlignedTranscript:
    """Complete aligned transcript with frame mapping."""

    source_video: str
    total_segments: int
    total_frames: int
    segments: list[AlignedSegment] = field(default_factory=list)
    fps: float = 1.0
    duration_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_video": self.source_video,
            "total_segments": self.total_segments,
            "total_frames": self.total_frames,
            "segments": [s.to_dict() for s in self.segments],
            "fps": self.fps,
            "duration_seconds": self.duration_seconds,
        }

    def get_text_for_frame(self, frame_number: int) -> str:
        """Get transcript text for a specific frame."""
        for segment in self.segments:
            if segment.start_frame <= frame_number <= segment.end_frame:
                return segment.text
        return ""

    def get_text_for_time(self, timestamp_seconds: float) -> str:
        """Get transcript text for a specific time."""
        for segment in self.segments:
            if segment.start_time <= timestamp_seconds <= segment.end_time:
                return segment.text
        return ""


class TranscriptAligner:
    """Align audio transcript with video frames.

    Maps transcript segments to frame numbers based on timestamps.
    Supports both uniform and adaptive frame sampling.

    Usage:
        aligner = TranscriptAligner(fps=1.0)
        aligned = aligner.align(transcript_segments, frame_count, fps)
    """

    def __init__(
        self,
        fps: float = 1.0,
        overlap_strategy: str = "first",  # first, last, combine
    ) -> None:
        """Initialize transcript aligner.

        Args:
            fps: Frames per second for frame calculation
            overlap_strategy: How to handle overlapping segments
        """
        self.fps = fps
        self.overlap_strategy = overlap_strategy

    def align(
        self,
        segments: list[dict[str, Any]],
        frame_count: int,
        fps: float | None = None,
        video_path: str = "",
    ) -> AlignedTranscript:
        """Align transcript segments with frames.

        Args:
            segments: List of transcript segments with start/end times
            frame_count: Total number of frames
            fps: Frames per second (uses init value if None)
            video_path: Source video path for reference

        Returns:
            AlignedTranscript with frame mappings
        """
        actual_fps = fps or self.fps
        aligned_segments: list[AlignedSegment] = []

        for i, seg in enumerate(segments):
            start_time = seg.get("start", 0.0)
            end_time = seg.get("end", 0.0)
            text = seg.get("text", "")
            confidence = seg.get("confidence", 0.0)

            # Calculate frame numbers
            start_frame = int(start_time * actual_fps)
            end_frame = int(end_time * actual_fps)

            # Clamp to valid range
            start_frame = max(0, min(start_frame, frame_count - 1))
            end_frame = max(0, min(end_frame, frame_count - 1))

            aligned = AlignedSegment(
                segment_index=i,
                text=text,
                start_time=start_time,
                end_time=end_time,
                confidence=confidence,
                start_frame=start_frame,
                end_frame=end_frame,
            )
            aligned_segments.append(aligned)

        # Calculate total duration
        duration = 0.0
        if aligned_segments:
            last_seg = aligned_segments[-1]
            duration = last_seg.end_time

        return AlignedTranscript(
            source_video=video_path,
            total_segments=len(aligned_segments),
            total_frames=frame_count,
            segments=aligned_segments,
            fps=actual_fps,
            duration_seconds=duration,
        )

    def align_with_frame_paths(
        self,
        segments: list[dict[str, Any]],
        frame_paths: list[Path],
        fps: float | None = None,
        video_path: str = "",
    ) -> AlignedTranscript:
        """Align transcript with actual frame file paths.

        Args:
            segments: List of transcript segments
            frame_paths: List of frame file paths
            fps: Frames per second
            video_path: Source video path

        Returns:
            AlignedTranscript with frame paths
        """
        actual_fps = fps or self.fps
        aligned = self.align(segments, len(frame_paths), actual_fps, video_path)

        # Assign frame paths to segments
        for seg in aligned.segments:
            if 0 <= seg.start_frame < len(frame_paths):
                seg.frame_path = frame_paths[seg.start_frame]

        return aligned


def align_transcript_to_frames(
    segments: list[dict[str, Any]],
    frame_count: int,
    fps: float = 1.0,
) -> AlignedTranscript:
    """Convenience function for transcript alignment.

    Args:
        segments: List of transcript segments
        frame_count: Total number of frames
        fps: Frames per second

    Returns:
        AlignedTranscript
    """
    aligner = TranscriptAligner(fps=fps)
    return aligner.align(segments, frame_count, fps)