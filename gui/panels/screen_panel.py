"""Screen Panel - Screen capture and OCR context surface."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTextEdit,
    QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QPixmap, QImage

from .base import BasePanel, Styles


class ScreenPanel(BasePanel):
    """Minimalist screen capture and OCR panel."""

    capture_requested = pyqtSignal(str)
    ocr_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ocr_text = ""
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Header
        header = QHBoxLayout()
        title = QLabel("Screen")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        header.addWidget(title)
        header.addStretch()

        layout.addLayout(header)

        # Preview area
        self._preview = QLabel()
        self._preview.setMinimumHeight(200)
        self._preview.setStyleSheet(Styles.PREVIEW_STYLE)
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setText("No capture")
        layout.addWidget(self._preview)

        # Capture buttons
        btn_layout = QHBoxLayout()

        fullscreen_btn = QPushButton("Fullscreen")
        fullscreen_btn.clicked.connect(lambda: self._capture("fullscreen"))
        btn_layout.addWidget(fullscreen_btn)

        window_btn = QPushButton("Window")
        window_btn.clicked.connect(lambda: self._capture("window"))
        btn_layout.addWidget(window_btn)

        region_btn = QPushButton("Region")
        region_btn.clicked.connect(lambda: self._capture("region"))
        btn_layout.addWidget(region_btn)

        layout.addLayout(btn_layout)

        # OCR section
        ocr_header = QHBoxLayout()
        ocr_label = QLabel("OCR Output")
        ocr_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        ocr_header.addWidget(ocr_label)

        ocr_btn = QPushButton("Run OCR")
        ocr_btn.clicked.connect(self._run_ocr)
        ocr_header.addWidget(ocr_btn)

        copy_btn = QPushButton("Copy")
        copy_btn.clicked.connect(self._copy_ocr)
        ocr_header.addWidget(copy_btn)

        layout.addLayout(ocr_header)

        # OCR output
        self._ocr_output = QTextEdit()
        self._ocr_output.setReadOnly(True)
        self._ocr_output.setPlaceholderText("OCR text will appear here...")
        self._ocr_output.setStyleSheet(Styles.TEXT_EDIT_STYLE)
        self._ocr_output.setMaximumHeight(150)
        layout.addWidget(self._ocr_output)

        # Status
        self._status_label = QLabel("")
        self._status_label.setStyleSheet(f"color: {Styles.TEXT_SECONDARY}; font-size: 10px;")
        layout.addWidget(self._status_label)

    def _capture(self, capture_type: str):
        """Capture screen."""
        try:
            from PIL import ImageGrab

            if capture_type == "fullscreen":
                img = ImageGrab.grab()
            elif capture_type == "window":
                img = ImageGrab.grab()
            else:
                img = ImageGrab.grab()

            # Convert to QPixmap
            qimg = QImage(
                img.tobytes(),
                img.width,
                img.height,
                img.width * 3,
                QImage.Format.Format_RGB888
            )
            pixmap = QPixmap.fromImage(qimg)

            if pixmap:
                self._preview.setPixmap(pixmap.scaled(
                    self._preview.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                ))
                self._status_label.setText(f"Captured: {capture_type}")
            else:
                self._status_label.setText("Capture failed")

        except ImportError:
            self._status_label.setText("PIL not installed - cannot capture")
        except Exception as e:
            self._status_label.setText(f"Error: {e}")

    def _run_ocr(self):
        """Run OCR on current capture."""
        try:
            from app.agent_core.ocr_engine import tesseract_available, extract_text_from_path

            pixmap = self._preview.pixmap()
            if not pixmap:
                self._status_label.setText("No image captured")
                return

            if not tesseract_available():
                self._status_label.setText("Tesseract OCR not available")
                return

            # Save pixmap to temp file and run OCR
            import tempfile
            import os

            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp_path = tmp.name
                pixmap.save(tmp_path)

            try:
                result = extract_text_from_path(tmp_path)
                self._ocr_text = result.text
                self._ocr_output.setText(self._ocr_text)
                self._status_label.setText(f"OCR complete: {result.char_count} chars")
            finally:
                os.unlink(tmp_path)

        except ImportError:
            self._status_label.setText("OCR module not available")
        except Exception as e:
            self._status_label.setText(f"OCR error: {e}")

    def _copy_ocr(self):
        """Copy OCR text to clipboard."""
        if self._ocr_text:
            QApplication.clipboard().setText(self._ocr_text)
            self._status_label.setText("Copied to clipboard")