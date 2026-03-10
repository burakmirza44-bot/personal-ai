"""Self-Improvement Panel - Self-improvement operations interface."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QTextEdit,
    QComboBox, QSpinBox, QCheckBox,
    QListWidget, QGroupBox, QTabWidget
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from .base import BasePanel, Styles


class SelfImprovementPanel(BasePanel):
    """Panel for self-improvement operations."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header
        title = QLabel("Self-Improvement")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        layout.addWidget(title)

        # Status cards
        cards_layout = QHBoxLayout()

        self._proposals_card = self._create_stat_card("Proposals", "0", Styles.ACCENT_YELLOW)
        cards_layout.addWidget(self._proposals_card)

        self._applied_card = self._create_stat_card("Applied", "0", Styles.ACCENT_GREEN)
        cards_layout.addWidget(self._applied_card)

        self._rollbacks_card = self._create_stat_card("Rollbacks", "0", Styles.ACCENT_RED)
        cards_layout.addWidget(self._rollbacks_card)

        layout.addLayout(cards_layout)

        # Tabs
        tabs = QTabWidget()

        # Run Tab
        run_tab = QWidget()
        run_layout = QVBoxLayout(run_tab)

        run_group = QGroupBox("Run Improvement")
        run_inner = QVBoxLayout(run_group)

        source_layout = QHBoxLayout()
        source_layout.addWidget(QLabel("Source:"))
        self._source_combo = QComboBox()
        self._source_combo.addItems(["error_memory", "test_failures", "docs_drift"])
        source_layout.addWidget(self._source_combo)
        run_inner.addLayout(source_layout)

        options_layout = QHBoxLayout()
        self._auto_apply = QCheckBox("Auto-apply low-risk")
        options_layout.addWidget(self._auto_apply)
        options_layout.addWidget(QLabel("Max:"))
        self._max_proposals = QSpinBox()
        self._max_proposals.setRange(1, 10)
        options_layout.addWidget(self._max_proposals)
        run_inner.addLayout(options_layout)

        btn_layout = QHBoxLayout()
        preview_btn = QPushButton("Preview")
        preview_btn.clicked.connect(self._preview_improvement)
        btn_layout.addWidget(preview_btn)

        run_btn = QPushButton("Run")
        run_btn.setStyleSheet(f"background-color: {Styles.ACCENT_GREEN}; color: #1e1e2e; font-weight: bold;")
        run_btn.clicked.connect(self._run_improvement)
        btn_layout.addWidget(run_btn)

        run_inner.addLayout(btn_layout)
        run_layout.addWidget(run_group)

        self._improve_output = QTextEdit()
        self._improve_output.setReadOnly(True)
        run_layout.addWidget(self._improve_output, 1)

        tabs.addTab(run_tab, "Run")

        # Review Tab
        review_tab = QWidget()
        review_layout = QVBoxLayout(review_tab)

        self._proposals_list = self.create_list_widget()
        review_layout.addWidget(self._proposals_list)

        proposal_btn_layout = QHBoxLayout()
        review_btn = QPushButton("Review")
        review_btn.clicked.connect(self._review_proposal)
        proposal_btn_layout.addWidget(review_btn)

        apply_btn = QPushButton("Apply")
        apply_btn.clicked.connect(self._apply_proposal)
        proposal_btn_layout.addWidget(apply_btn)

        reject_btn = QPushButton("Reject")
        reject_btn.clicked.connect(self._reject_proposal)
        proposal_btn_layout.addWidget(reject_btn)

        review_layout.addLayout(proposal_btn_layout)
        tabs.addTab(review_tab, "Review")

        # History Tab
        history_tab = QWidget()
        history_layout = QVBoxLayout(history_tab)

        self._history_list = self.create_list_widget()
        history_layout.addWidget(self._history_list)

        rollback_btn = QPushButton("Rollback Last")
        rollback_btn.clicked.connect(self._rollback_improvement)
        history_layout.addWidget(rollback_btn)

        tabs.addTab(history_tab, "History")

        layout.addWidget(tabs)

    def _create_stat_card(self, label: str, value: str, color: str) -> QFrame:
        card = QFrame()
        card.setStyleSheet(Styles.stat_card_style(color))

        layout = QVBoxLayout(card)
        value_label = QLabel(value)
        value_label.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
        value_label.setStyleSheet(f"color: {color};")
        value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(value_label)

        name_label = QLabel(label)
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(name_label)

        return card

    def _preview_improvement(self):
        self._improve_output.append("Previewing improvements...")

    def _run_improvement(self):
        self._improve_output.append("Running improvement cycle...")

    def _review_proposal(self):
        pass

    def _apply_proposal(self):
        current = self._proposals_list.currentRow()
        if current >= 0:
            self._proposals_list.takeItem(current)

    def _reject_proposal(self):
        current = self._proposals_list.currentRow()
        if current >= 0:
            self._proposals_list.takeItem(current)

    def _rollback_improvement(self):
        pass