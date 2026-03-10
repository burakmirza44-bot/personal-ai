"""Context Panels - Modular panel components.

Each panel provides a minimalist context surface for viewing and interacting
with different aspects of the system's data stores.
"""

from .base import BasePanel, Styles, REPO_ROOT
from .memory_panel import MemoryPanel
from .rag_panel import RAGPanel
from .sessions_panel import SessionsPanel
from .screen_panel import ScreenPanel
from .self_improvement_panel import SelfImprovementPanel
from .settings_panel import SettingsPanel

__all__ = [
    # Base
    "BasePanel",
    "Styles",
    "REPO_ROOT",
    # Panels
    "MemoryPanel",
    "RAGPanel",
    "SessionsPanel",
    "ScreenPanel",
    "SelfImprovementPanel",
    "SettingsPanel",
]