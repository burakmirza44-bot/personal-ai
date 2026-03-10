# Audio Processing Module
# Speech-to-text and audio extraction for tutorial learning

from app.audio.whisper_local import (
    WhisperLocal,
    TranscriptResult,
    TranscriptSegment,
    transcribe_audio,
    is_whisper_available,
)

__all__ = [
    "WhisperLocal",
    "TranscriptResult",
    "TranscriptSegment",
    "transcribe_audio",
    "is_whisper_available",
]