"""Nexus Assistant - Context Panels.

This module re-exports panels from the modular gui.panels package.
All panels are now in separate files for better maintainability.

Panels:
- MemoryPanel: Searchable memory context surface
- RAGPanel: Searchable RAG context surface with chunk detail
- SessionsPanel: Session history context surface
- ScreenPanel: Screen capture and OCR context surface
- SelfImprovementPanel: Self-improvement operations interface
- SettingsPanel: Application settings interface
"""

# Re-export from modular panels
from gui.panels import (
    # Base
    BasePanel,
    Styles,
    REPO_ROOT,
    # Panels
    MemoryPanel,
    RAGPanel,
    SessionsPanel,
    ScreenPanel,
    SelfImprovementPanel,
    SettingsPanel,
)

__all__ = [
    "BasePanel",
    "Styles",
    "REPO_ROOT",
    "MemoryPanel",
    "RAGPanel",
    "SessionsPanel",
    "ScreenPanel",
    "SelfImprovementPanel",
    "SettingsPanel",
]