"""Memory Panel - Searchable memory context surface."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QTextEdit,
    QLineEdit, QComboBox, QListWidget, QListWidgetItem,
    QTabWidget
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from .base import BasePanel, Styles, REPO_ROOT


class MemoryPanel(BasePanel):
    """Minimalist memory context panel with search and filtering."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._store = None
        self._items = []
        self._init_ui()
        self._load_data()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Header
        header = QHBoxLayout()
        title = QLabel("Memory")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        header.addWidget(title)

        self._stats_label = QLabel("0 items")
        self._stats_label.setStyleSheet(f"color: {Styles.TEXT_SECONDARY}; font-size: 11px;")
        header.addWidget(self._stats_label)
        header.addStretch()

        refresh_btn = QPushButton("↻")
        refresh_btn.setFixedWidth(28)
        refresh_btn.setToolTip("Refresh")
        refresh_btn.clicked.connect(self._load_data)
        header.addWidget(refresh_btn)

        layout.addLayout(header)

        # Search bar
        search_layout = QHBoxLayout()
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search memory...")
        self._search_input.textChanged.connect(self._filter_items)
        search_layout.addWidget(self._search_input)

        self._domain_filter = QComboBox()
        self._domain_filter.addItems(["All", "touchdesigner", "houdini", "general"])
        self._domain_filter.setFixedWidth(120)
        self._domain_filter.currentTextChanged.connect(self._filter_items)
        search_layout.addWidget(self._domain_filter)

        layout.addLayout(search_layout)

        # Bucket tabs
        self._bucket_tabs = QTabWidget()
        self._bucket_tabs.setDocumentMode(True)

        # Long-term bucket
        self._long_term_list = self.create_list_widget()
        self._long_term_list.itemClicked.connect(self._show_item_detail)
        self._bucket_tabs.addTab(self._long_term_list, "Long-term")

        # Short-term bucket
        self._short_term_list = self.create_list_widget()
        self._short_term_list.itemClicked.connect(self._show_item_detail)
        self._bucket_tabs.addTab(self._short_term_list, "Short-term")

        layout.addWidget(self._bucket_tabs)

        # Detail area
        self._detail_frame = self.create_detail_frame()
        detail_layout = QVBoxLayout(self._detail_frame)
        detail_layout.setContentsMargins(8, 8, 8, 8)

        self._detail_meta = QLabel()
        self._detail_meta.setStyleSheet(f"color: {Styles.TEXT_SECONDARY}; font-size: 10px;")
        detail_layout.addWidget(self._detail_meta)

        self._detail_text = QTextEdit()
        self._detail_text.setReadOnly(True)
        self._detail_text.setStyleSheet("background: transparent; border: none;")
        self._detail_text.setMaximumHeight(120)
        detail_layout.addWidget(self._detail_text)

        self._detail_frame.setVisible(False)
        layout.addWidget(self._detail_frame)

    def _load_data(self):
        """Load memory from store."""
        try:
            from app.core.memory_store import build_default_memory_store
            self._store = build_default_memory_store(REPO_ROOT)
            self._store.load()
            self._items = self._store.long_term + self._store.short_term
            self._refresh_lists()
            self._stats_label.setText(f"{len(self._items)} items")
        except Exception as e:
            self._stats_label.setText(f"Error: {e}")

    def _refresh_lists(self):
        """Refresh list widgets."""
        if not self._store:
            return

        self._long_term_list.clear()
        self._short_term_list.clear()

        query = self._search_input.text().lower()
        domain = self._domain_filter.currentText()

        for item in self._store.long_term:
            if self._matches_filter(item, query, domain):
                self._add_list_item(self._long_term_list, item)

        for item in self._store.short_term:
            if self._matches_filter(item, query, domain):
                self._add_list_item(self._short_term_list, item)

    def _matches_filter(self, item, query: str, domain: str) -> bool:
        """Check if item matches filter criteria."""
        if domain != "All" and item.domain != domain:
            return False
        if query and query not in item.content.lower():
            return False
        return True

    def _add_list_item(self, list_widget: QListWidget, item):
        """Add memory item to list."""
        display = item.content[:80] + "..." if len(item.content) > 80 else item.content
        list_item = QListWidgetItem(display)
        list_item.setData(Qt.ItemDataRole.UserRole, item)
        list_item.setToolTip(f"Domain: {item.domain}\nTags: {', '.join(item.tags)}\nCreated: {item.created_at}")
        list_widget.addItem(list_item)

    def _filter_items(self):
        """Filter items based on search and domain."""
        self._refresh_lists()

    def _show_item_detail(self, list_item: QListWidgetItem):
        """Show item detail in detail frame."""
        item = list_item.data(Qt.ItemDataRole.UserRole)
        if item:
            self._detail_meta.setText(
                f"Domain: {item.domain} | Tags: {', '.join(item.tags)} | Created: {item.created_at}"
            )
            self._detail_text.setText(item.content)
            self._detail_frame.setVisible(True)