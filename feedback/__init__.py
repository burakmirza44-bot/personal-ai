# Feedback Loop Module
# Closed-loop learning system for continuous improvement

"""
Feedback Loop - Kapalı çevrim öğrenme sistemi

Bu modül, sistemin kendi çıktılarını değerlendirmesini, hatalardan öğrenmesini
ve her iterasyonda daha iyi üretmesini sağlayan bir kapalı çevrim mekanizması sunar.

Ana bileşenler:
- Audio/STT: Video tutorial'lardan ses → metin dönüşümü
- Evaluation: Çıktı kalite değerlendirme
- Training: Veri hazırlama ve fine-tuning
- Memory: Feedback depolama ve pattern takibi
- Orchestrator: Ana döngü kontrolü

Kullanım:
    from feedback.loop import FeedbackOrchestrator, FeedbackTask

    orchestrator = FeedbackOrchestrator(domain="houdini")
    task = FeedbackTask(
        task_id="test_1",
        input_text="Create a box and bevel it",
        domain="houdini"
    )
    result = orchestrator.run_single(task)
    print(f"Score: {result.score}")
"""

from feedback.loop import (
    FeedbackOrchestrator,
    FeedbackResult,
    FeedbackTask,
    BatchReport,
    ImprovementReport,
    OutputEvaluator,
    EvaluationResult,
    RewardSignal,
    RewardCalculator,
    FeedbackDataCollector,
    CollectedExample,
)

from feedback.audio import (
    STTEngine,
    AudioExtractor,
    TranscriptAligner,
)

from feedback.evaluation import (
    HoudiniValidator,
    TDValidator,
    CodeQualityAnalyzer,
)

from feedback.training import (
    DataFormatter,
    CurriculumLearner,
    FineTuner,
)

from feedback.memory import (
    FeedbackStore,
    PatternTracker,
)

__all__ = [
    # Orchestrator
    "FeedbackOrchestrator",
    "FeedbackResult",
    "FeedbackTask",
    "BatchReport",
    "ImprovementReport",

    # Evaluation
    "OutputEvaluator",
    "EvaluationResult",
    "HoudiniValidator",
    "TDValidator",
    "CodeQualityAnalyzer",

    # Reward
    "RewardSignal",
    "RewardCalculator",

    # Data Collection
    "FeedbackDataCollector",
    "CollectedExample",

    # Audio
    "STTEngine",
    "AudioExtractor",
    "TranscriptAligner",

    # Training
    "DataFormatter",
    "CurriculumLearner",
    "FineTuner",

    # Memory
    "FeedbackStore",
    "PatternTracker",
]