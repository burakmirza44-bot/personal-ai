"""Sessions Panel - Session history context surface."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTextEdit,
    QComboBox, QListWidget, QListWidgetItem,
    QSplitter, QMessageBox, QInputDialog
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from .base import BasePanel, Styles, REPO_ROOT


class SessionsPanel(BasePanel):
    """Minimalist session history panel with event inspection."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._store = None
        self._sessions = []
        self._init_ui()
        self._load_sessions()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Header
        header = QHBoxLayout()
        title = QLabel("Sessions")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        header.addWidget(title)

        self._stats_label = QLabel("0 sessions")
        self._stats_label.setStyleSheet(f"color: {Styles.TEXT_SECONDARY}; font-size: 11px;")
        header.addWidget(self._stats_label)
        header.addStretch()

        refresh_btn = QPushButton("↻")
        refresh_btn.setFixedWidth(28)
        refresh_btn.setToolTip("Refresh")
        refresh_btn.clicked.connect(self._load_sessions)
        header.addWidget(refresh_btn)

        layout.addLayout(header)

        # Filter bar
        filter_layout = QHBoxLayout()
        self._domain_filter = QComboBox()
        self._domain_filter.addItems(["All", "touchdesigner", "houdini"])
        self._domain_filter.setFixedWidth(120)
        self._domain_filter.currentTextChanged.connect(self._filter_sessions)
        filter_layout.addWidget(self._domain_filter)

        self._status_filter = QComboBox()
        self._status_filter.addItems(["All", "active", "completed", "partial", "failed"])
        self._status_filter.setFixedWidth(100)
        self._status_filter.currentTextChanged.connect(self._filter_sessions)
        filter_layout.addWidget(self._status_filter)

        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        # Splitter
        splitter = QSplitter(Qt.Orientation.Vertical)

        # Session list
        self._session_list = self.create_list_widget()
        self._session_list.itemClicked.connect(self._show_session_detail)
        splitter.addWidget(self._session_list)

        # Event log
        self._event_log = QTextEdit()
        self._event_log.setReadOnly(True)
        self._event_log.setPlaceholderText("Select a session to view events")
        self._event_log.setStyleSheet(Styles.TEXT_EDIT_STYLE)
        splitter.addWidget(self._event_log)

        splitter.setSizes([200, 150])
        layout.addWidget(splitter)

        # Actions
        actions = QHBoxLayout()
        new_btn = QPushButton("+ New Session")
        new_btn.clicked.connect(self._new_session)
        actions.addWidget(new_btn)

        export_btn = QPushButton("Export")
        export_btn.clicked.connect(self._export_session)
        actions.addWidget(export_btn)

        actions.addStretch()
        layout.addLayout(actions)

    def _load_sessions(self):
        """Load sessions from store."""
        try:
            from app.recording.session_store import SessionStore
            self._store = SessionStore(REPO_ROOT)
            self._sessions = self._list_all_sessions()
            self._refresh_list()
            self._stats_label.setText(f"{len(self._sessions)} sessions")
        except Exception as e:
            self._stats_label.setText(f"Error: {e}")

    def _list_all_sessions(self) -> list:
        """List all sessions from both domains."""
        sessions = []
        if not self._store:
            return sessions

        for domain in ["touchdesigner", "houdini"]:
            try:
                root = self._store.td_root if domain == "touchdesigner" else self._store.hou_root
                for session_dir in root.iterdir():
                    if session_dir.is_dir():
                        manifest_path = session_dir / "manifest.json"
                        if manifest_path.exists():
                            manifest = self._store.load_manifest(session_dir.name, domain)
                            sessions.append((domain, manifest))
            except Exception:
                pass
        return sessions

    def _refresh_list(self):
        """Refresh session list."""
        self._session_list.clear()
        domain_filter = self._domain_filter.currentText()
        status_filter = self._status_filter.currentText()

        for domain, manifest in self._sessions:
            meta = manifest.metadata
            if domain_filter != "All" and meta.domain != domain_filter:
                continue
            if status_filter != "All" and meta.status != status_filter:
                continue

            status_icon = {"active": "●", "completed": "✓", "partial": "◐", "failed": "✗"}.get(meta.status, "○")
            task_hint = meta.task_hint[:40] + "..." if len(meta.task_hint) > 40 else meta.task_hint
            item_text = f"{status_icon} [{meta.domain}] {task_hint} | {meta.status}"
            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemDataRole.UserRole, (domain, manifest))
            self._session_list.addItem(item)

    def _filter_sessions(self):
        """Filter sessions."""
        self._refresh_list()

    def _show_session_detail(self, list_item: QListWidgetItem):
        """Show session events."""
        data = list_item.data(Qt.ItemDataRole.UserRole)
        if not data:
            return

        domain, manifest = data
        meta = manifest.metadata

        try:
            events_path = self._store.events_path(meta.session_id, domain)
            events_text = events_path.read_text(encoding="utf-8") if events_path.exists() else ""

            summary = f"""Session: {meta.session_id}
Domain: {meta.domain}
Task: {meta.task_hint}
Started: {meta.started_at}
Status: {meta.status}

Events:
{events_text[:2000]}{'...' if len(events_text) > 2000 else ''}"""

            self._event_log.setPlainText(summary)
        except Exception as e:
            self._event_log.setText(f"Error loading events: {e}")

    def _new_session(self):
        """Start new session dialog."""
        if not self._store:
            return

        domain = "touchdesigner" if self._domain_filter.currentText() == "touchdesigner" else "houdini"
        task, ok = QInputDialog.getText(self, "New Session", "Task hint:")
        if ok and task:
            try:
                self._store.create_session(domain, task)
                self._load_sessions()
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to create session: {e}")

    def _export_session(self):
        """Export selected session."""
        current = self._session_list.currentItem()
        if current:
            QMessageBox.information(self, "Export", "Session export coming soon")