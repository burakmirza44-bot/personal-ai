"""RAG Panel - Searchable RAG context surface with chunk detail."""

from __future__ import annotations

import math
import re
from collections import defaultdict

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTextEdit,
    QLineEdit, QComboBox, QListWidget, QListWidgetItem,
    QSplitter, QMessageBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from .base import BasePanel, Styles, REPO_ROOT


class RAGPanel(BasePanel):
    """Minimalist RAG context panel with search and chunk inspection."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._chunks = []
        self._idf = {}
        self._init_ui()
        self._load_index()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Header
        header = QHBoxLayout()
        title = QLabel("RAG Index")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        header.addWidget(title)

        self._stats_label = QLabel("0 chunks")
        self._stats_label.setStyleSheet(f"color: {Styles.TEXT_SECONDARY}; font-size: 11px;")
        header.addWidget(self._stats_label)
        header.addStretch()

        rebuild_btn = QPushButton("Rebuild")
        rebuild_btn.setFixedWidth(60)
        rebuild_btn.clicked.connect(self._rebuild_index)
        header.addWidget(rebuild_btn)

        layout.addLayout(header)

        # Search bar
        search_layout = QHBoxLayout()
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search chunks...")
        self._search_input.returnPressed.connect(self._search)
        search_layout.addWidget(self._search_input)

        self._domain_filter = QComboBox()
        self._domain_filter.addItems(["All", "touchdesigner", "houdini", "general"])
        self._domain_filter.setFixedWidth(120)
        search_layout.addWidget(self._domain_filter)

        search_btn = QPushButton("Search")
        search_btn.clicked.connect(self._search)
        search_layout.addWidget(search_btn)

        layout.addLayout(search_layout)

        # Splitter for results and detail
        splitter = QSplitter(Qt.Orientation.Vertical)

        # Results list
        self._results_list = self.create_list_widget()
        self._results_list.itemClicked.connect(self._show_chunk_detail)
        splitter.addWidget(self._results_list)

        # Chunk detail
        self._chunk_detail = QTextEdit()
        self._chunk_detail.setReadOnly(True)
        self._chunk_detail.setPlaceholderText("Select a chunk to view details")
        self._chunk_detail.setStyleSheet(Styles.TEXT_EDIT_STYLE)
        splitter.addWidget(self._chunk_detail)

        splitter.setSizes([200, 150])
        layout.addWidget(splitter)

    def _load_index(self):
        """Load RAG index from disk."""
        try:
            from app.core.rag_index import load_index
            self._chunks = load_index()
            self._idf = self._build_idf(self._chunks)
            self._stats_label.setText(f"{len(self._chunks)} chunks")
        except Exception as e:
            self._stats_label.setText(f"Error: {e}")

    def _build_idf(self, chunks) -> dict:
        """Build IDF dictionary from chunks."""
        STOPWORDS = frozenset({
            "a", "an", "the", "is", "in", "on", "at", "to", "of", "and", "or",
            "for", "with", "this", "that", "it", "be", "as", "by", "from",
        })

        def tokenize(text):
            tokens = re.findall(r"[a-z0-9]+", text.lower())
            return [t for t in tokens if len(t) >= 2 and t not in STOPWORDS]

        if not chunks:
            return {}

        N = len(chunks)
        df = defaultdict(int)
        for c in chunks:
            for tok in set(tokenize(c.text)):
                df[tok] += 1

        return {tok: math.log((N + 1) / (cnt + 1)) + 1.0 for tok, cnt in df.items()}

    def _rebuild_index(self):
        """Rebuild RAG index."""
        try:
            from app.core.rag_index import build_index, save_index
            chunks = build_index()
            save_index(chunks)
            self._load_index()
            QMessageBox.information(self, "RAG", "Index rebuilt successfully")
        except Exception as e:
            QMessageBox.warning(self, "RAG", f"Failed to rebuild: {e}")

    def _search(self):
        """Search RAG chunks."""
        query = self._search_input.text()
        if not query or not self._chunks:
            return

        try:
            from app.core.rag_retriever import search
            domain = self._domain_filter.currentText()
            if domain == "All":
                domain = ""

            hits = search(
                query=query,
                chunks=self._chunks,
                idf=self._idf,
                domain=domain,
                max_results=10,
            )

            self._results_list.clear()
            for hit in hits:
                item = QListWidgetItem(f"[{hit.chunk.domain}] {hit.chunk.title[:50]}... ({hit.relevance_score:.2f})")
                item.setData(Qt.ItemDataRole.UserRole, hit.chunk)
                self._results_list.addItem(item)

            if not hits:
                self._results_list.addItem("No results found")

        except Exception as e:
            self._results_list.addItem(f"Search error: {e}")

    def _show_chunk_detail(self, list_item: QListWidgetItem):
        """Show chunk detail."""
        chunk = list_item.data(Qt.ItemDataRole.UserRole)
        if chunk:
            detail = f"""Source: {chunk.source_type} - {chunk.source_id}
Domain: {chunk.domain}
Title: {chunk.title}
Labels: {', '.join(chunk.task_labels) or 'None'}
URL: {chunk.url or 'N/A'}

Content:
{chunk.text[:500]}{'...' if len(chunk.text) > 500 else ''}"""
            self._chunk_detail.setPlainText(detail)