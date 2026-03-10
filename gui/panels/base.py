"""Panel base classes and shared styles."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import QWidget, QListWidget, QFrame, QLabel
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt

# Repository root for data access
REPO_ROOT = Path(__file__).resolve().parents[2]


# ============================================================================
# SHARED STYLES
# ============================================================================

class Styles:
    """Centralized style definitions."""

    # Colors (Catppuccin Mocha)
    BACKGROUND_DARK = "#11111b"
    BACKGROUND_SURFACE = "#181825"
    BORDER = "#313244"
    TEXT_PRIMARY = "#cdd6f4"
    TEXT_SECONDARY = "#6c7086"
    ACCENT_BLUE = "#89b4fa"
    ACCENT_GREEN = "#a6e3a1"
    ACCENT_YELLOW = "#f9e2af"
    ACCENT_RED = "#f38ba8"

    # List styles
    LIST_STYLE = f"""
        QListWidget {{
            background: {BACKGROUND_SURFACE};
            border: 1px solid {BORDER};
            border-radius: 4px;
        }}
        QListWidget::item {{
            padding: 8px;
            border-bottom: 1px solid {BORDER};
        }}
        QListWidget::item:selected {{
            background: {BORDER};
        }}
    """

    # Detail frame style
    DETAIL_FRAME_STYLE = f"""
        QFrame {{
            background: {BACKGROUND_DARK};
            border: 1px solid {BORDER};
            border-radius: 4px;
        }}
    """

    # Text edit style
    TEXT_EDIT_STYLE = f"""
        QTextEdit {{
            background: {BACKGROUND_DARK};
            border: 1px solid {BORDER};
            border-radius: 4px;
            font-family: Consolas;
        }}
    """

    # Preview area style
    PREVIEW_STYLE = f"""
        background-color: {BACKGROUND_SURFACE};
        border: 2px dashed {BORDER};
        border-radius: 8px;
    """

    @classmethod
    def stat_card_style(cls, color: str) -> str:
        """Generate stat card style with accent color."""
        return f"""
            QFrame {{
                background-color: {cls.BACKGROUND_SURFACE};
                border: 1px solid {cls.BORDER};
                border-radius: 8px;
                padding: 12px;
            }}
        """


# ============================================================================
# BASE PANEL
# ============================================================================

class BasePanel(QWidget):
    """Base class for context panels."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._repo_root = REPO_ROOT

    def create_header(self, title: str, stats_text: str = "") -> tuple[QLabel, QLabel]:
        """Create a standard panel header.

        Returns:
            Tuple of (title_label, stats_label)
        """
        from PyQt6.QtWidgets import QHBoxLayout, QPushButton

        header = QHBoxLayout()

        title_label = QLabel(title)
        title_label.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        header.addWidget(title_label)

        stats_label = QLabel(stats_text)
        stats_label.setStyleSheet(f"color: {Styles.TEXT_SECONDARY}; font-size: 11px;")
        header.addWidget(stats_label)
        header.addStretch()

        # Return header layout and labels for further customization
        return title_label, stats_label

    def create_list_widget(self) -> QListWidget:
        """Create a styled list widget."""
        list_widget = QListWidget()
        list_widget.setAlternatingRowColors(True)
        list_widget.setStyleSheet(Styles.LIST_STYLE)
        return list_widget

    def create_detail_frame(self) -> QFrame:
        """Create a styled detail frame."""
        frame = QFrame()
        frame.setStyleSheet(Styles.DETAIL_FRAME_STYLE)
        return frame