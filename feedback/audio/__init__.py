# Audio Module
# Speech-to-text for tutorial learning

from feedback.audio.stt_engine import (
    STTEngine,
    STTResult,
    transcribe_video_audio,
)

from feedback.audio.audio_extractor import (
    AudioExtractor,
    AudioExtractionResult,
    extract_audio_from_video,
)

from feedback.audio.transcript_aligner import (
    TranscriptAligner,
    AlignedTranscript,
    align_transcript_to_frames,
)

__all__ = [
    # STT Engine
    "STTEngine",
    "STTResult",
    "transcribe_video_audio",
    # Audio Extractor
    "AudioExtractor",
    "AudioExtractionResult",
    "extract_audio_from_video",
    # Transcript Aligner
    "TranscriptAligner",
    "AlignedTranscript",
    "align_transcript_to_frames",
]