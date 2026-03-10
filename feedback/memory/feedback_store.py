"""Feedback Store - Persistent storage for feedback data.

Stores all feedback records with scores, rewards, and metadata.
Provides querying capabilities for analysis and retraining.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class FeedbackRecord:
    """A single feedback record."""

    record_id: str
    task_id: str
    session_id: str

    # Content
    input_text: str
    output_text: str
    score: float
    reward_value: float
    reward_type: str

    # Metadata
    domain: str = ""
    quality_tier: str = ""
    model_version: str = ""
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    # Additional
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "task_id": self.task_id,
            "session_id": self.session_id,
            "input_text": self.input_text[:500],
            "output_text": self.output_text[:500],
            "score": self.score,
            "reward_value": self.reward_value,
            "reward_type": self.reward_type,
            "domain": self.domain,
            "quality_tier": self.quality_tier,
            "model_version": self.model_version,
            "timestamp": self.timestamp,
            "errors": self.errors,
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class FeedbackQuery:
    """Query for feedback records."""

    session_id: str | None = None
    domain: str | None = None
    min_score: float | None = None
    max_score: float | None = None
    reward_type: str | None = None
    limit: int = 100
    offset: int = 0


class FeedbackStore:
    """Persistent storage for feedback records.

    Uses SQLite for local-first storage.
    Provides querying and aggregation capabilities.

    Usage:
        store = FeedbackStore()
        store.save(record)
        records = store.query(FeedbackQuery(domain="houdini"))
    """

    def __init__(
        self,
        db_path: Path | str | None = None,
    ) -> None:
        """Initialize feedback store.

        Args:
            db_path: Optional database path (default: data/feedback/feedback.db)
        """
        if db_path:
            self.db_path = Path(db_path)
        else:
            self.db_path = Path("data/feedback/feedback.db")

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """Initialize database schema."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                record_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                input_text TEXT,
                output_text TEXT,
                score REAL,
                reward_value REAL,
                reward_type TEXT,
                domain TEXT,
                quality_tier TEXT,
                model_version TEXT,
                timestamp TEXT,
                errors TEXT,
                metadata TEXT
            )
        """)

        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_session ON feedback(session_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_domain ON feedback(domain)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_score ON feedback(score)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON feedback(timestamp)")

        conn.commit()
        conn.close()

    def save(
        self,
        record: FeedbackRecord,
    ) -> bool:
        """Save a feedback record.

        Args:
            record: Record to save

        Returns:
            True if saved successfully
        """
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT OR REPLACE INTO feedback VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
            """, (
                record.record_id,
                record.task_id,
                record.session_id,
                record.input_text,
                record.output_text,
                record.score,
                record.reward_value,
                record.reward_type,
                record.domain,
                record.quality_tier,
                record.model_version,
                record.timestamp,
                json.dumps(record.errors),
                json.dumps(record.metadata),
            ))

            conn.commit()
            return True

        except Exception as e:
            logger.error(f"Failed to save feedback record: {e}")
            return False

        finally:
            conn.close()

    def query(
        self,
        query: FeedbackQuery,
    ) -> list[FeedbackRecord]:
        """Query feedback records.

        Args:
            query: Query parameters

        Returns:
            List of matching records
        """
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        conditions = []
        params = []

        if query.session_id:
            conditions.append("session_id = ?")
            params.append(query.session_id)

        if query.domain:
            conditions.append("domain = ?")
            params.append(query.domain)

        if query.min_score is not None:
            conditions.append("score >= ?")
            params.append(query.min_score)

        if query.max_score is not None:
            conditions.append("score <= ?")
            params.append(query.max_score)

        if query.reward_type:
            conditions.append("reward_type = ?")
            params.append(query.reward_type)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        sql = f"""
            SELECT * FROM feedback
            WHERE {where_clause}
            ORDER BY timestamp DESC
            LIMIT ? OFFSET ?
        """
        params.extend([query.limit, query.offset])

        cursor.execute(sql, params)
        rows = cursor.fetchall()
        conn.close()

        return [self._row_to_record(row) for row in rows]

    def _row_to_record(self, row: tuple) -> FeedbackRecord:
        """Convert database row to FeedbackRecord."""
        return FeedbackRecord(
            record_id=row[0],
            task_id=row[1],
            session_id=row[2],
            input_text=row[3] or "",
            output_text=row[4] or "",
            score=row[5] or 0.0,
            reward_value=row[6] or 0.0,
            reward_type=row[7] or "",
            domain=row[8] or "",
            quality_tier=row[9] or "",
            model_version=row[10] or "",
            timestamp=row[11] or "",
            errors=json.loads(row[12]) if row[12] else [],
            metadata=json.loads(row[13]) if row[13] else {},
        )

    def get_summary(
        self,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Get feedback summary statistics.

        Args:
            session_id: Optional session filter

        Returns:
            Summary statistics
        """
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        where = "WHERE session_id = ?" if session_id else ""
        params = [session_id] if session_id else []

        cursor.execute(f"""
            SELECT
                COUNT(*) as total,
                AVG(score) as avg_score,
                MIN(score) as min_score,
                MAX(score) as max_score,
                SUM(CASE WHEN reward_type = 'positive' THEN 1 ELSE 0 END) as positive,
                SUM(CASE WHEN reward_type = 'correction' THEN 1 ELSE 0 END) as correction,
                SUM(CASE WHEN reward_type = 'negative' THEN 1 ELSE 0 END) as negative
            FROM feedback
            {where}
        """, params)

        row = cursor.fetchone()
        conn.close()

        return {
            "total_records": row[0] or 0,
            "average_score": row[1] or 0.0,
            "min_score": row[2] or 0.0,
            "max_score": row[3] or 0.0,
            "positive_count": row[4] or 0,
            "correction_count": row[5] or 0,
            "negative_count": row[6] or 0,
        }

    def get_recent(
        self,
        limit: int = 100,
    ) -> list[FeedbackRecord]:
        """Get most recent feedback records.

        Args:
            limit: Maximum records to return

        Returns:
            List of recent records
        """
        query = FeedbackQuery(limit=limit)
        return self.query(query)

    def get_best(
        self,
        limit: int = 10,
        domain: str | None = None,
    ) -> list[FeedbackRecord]:
        """Get best performing records.

        Args:
            limit: Maximum records
            domain: Optional domain filter

        Returns:
            List of best records
        """
        query = FeedbackQuery(
            min_score=0.8,
            limit=limit,
            domain=domain,
        )
        return self.query(query)

    def get_worst(
        self,
        limit: int = 10,
        domain: str | None = None,
    ) -> list[FeedbackRecord]:
        """Get worst performing records.

        Args:
            limit: Maximum records
            domain: Optional domain filter

        Returns:
            List of worst records
        """
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        conditions = ["score < 0.5"]
        params = []

        if domain:
            conditions.append("domain = ?")
            params.append(domain)

        where = " AND ".join(conditions)

        sql = f"""
            SELECT * FROM feedback
            WHERE {where}
            ORDER BY score ASC
            LIMIT ?
        """
        params.append(limit)

        cursor.execute(sql, params)
        rows = cursor.fetchall()
        conn.close()

        return [self._row_to_record(row) for row in rows]

    def export_jsonl(
        self,
        output_path: Path | str,
        query: FeedbackQuery | None = None,
    ) -> int:
        """Export records to JSONL.

        Args:
            output_path: Output file path
            query: Optional query filter

        Returns:
            Number of records exported
        """
        records = self.query(query or FeedbackQuery(limit=10000))

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        with open(output, "w", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")

        return len(records)