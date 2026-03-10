"""Settings Panel - Application settings interface."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QSpinBox,
    QTabWidget, QFormLayout, QMessageBox, QDoubleSpinBox
)
from PyQt6.QtGui import QFont

from .base import BasePanel


class SettingsPanel(BasePanel):
    """Panel for application settings."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header
        title = QLabel("Settings")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        layout.addWidget(title)

        # Tabs
        tabs = QTabWidget()

        # General Tab
        general_tab = QWidget()
        general_layout = QFormLayout(general_tab)

        self._provider_combo = QComboBox()
        self._provider_combo.addItems(["Ollama", "OpenAI", "Gemini"])
        general_layout.addRow("Provider:", self._provider_combo)

        self._model_combo = QComboBox()
        self._model_combo.addItems(["qwen3:4b", "qwen3:8b", "qwen3:14b", "llama3:8b"])
        general_layout.addRow("Model:", self._model_combo)

        self._temperature = QDoubleSpinBox()
        self._temperature.setRange(0.0, 1.0)
        self._temperature.setValue(0.2)
        self._temperature.setSingleStep(0.1)
        general_layout.addRow("Temperature:", self._temperature)

        tabs.addTab(general_tab, "General")

        # Bridge Tab
        bridge_tab = QWidget()
        bridge_layout = QFormLayout(bridge_tab)

        self._td_port = QSpinBox()
        self._td_port.setRange(1, 65535)
        self._td_port.setValue(9988)
        bridge_layout.addRow("TD Port:", self._td_port)

        self._hou_port = QSpinBox()
        self._hou_port.setRange(1, 65535)
        self._hou_port.setValue(9989)
        bridge_layout.addRow("Houdini Port:", self._hou_port)

        self._bridge_timeout = QDoubleSpinBox()
        self._bridge_timeout.setRange(0.5, 30.0)
        self._bridge_timeout.setValue(3.0)
        bridge_layout.addRow("Timeout (s):", self._bridge_timeout)

        tabs.addTab(bridge_tab, "Bridge")

        # Budget Tab
        budget_tab = QWidget()
        budget_layout = QFormLayout(budget_tab)

        self._daily_budget = QSpinBox()
        self._daily_budget.setRange(1000, 100000)
        self._daily_budget.setValue(10000)
        budget_layout.addRow("Daily Limit:", self._daily_budget)

        self._session_budget = QSpinBox()
        self._session_budget.setRange(100, 10000)
        self._session_budget.setValue(1000)
        budget_layout.addRow("Session Limit:", self._session_budget)

        tabs.addTab(budget_tab, "Budget")

        layout.addWidget(tabs)

        # Action buttons
        btn_layout = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._save_settings)
        btn_layout.addWidget(save_btn)

        reset_btn = QPushButton("Reset")
        reset_btn.clicked.connect(self._reset_settings)
        btn_layout.addWidget(reset_btn)

        layout.addLayout(btn_layout)

    def _save_settings(self):
        """Save settings."""
        QMessageBox.information(self, "Settings", "Settings saved")

    def _reset_settings(self):
        """Reset settings to defaults."""
        QMessageBox.information(self, "Settings", "Settings reset")