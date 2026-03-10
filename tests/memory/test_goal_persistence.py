"""Tests for unified goal persistence layer."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from app.memory.goal_persistence import (
    Goal,
    GoalType,
    GoalStatus,
    GoalPriority,
    ActionabilityStatus,
    GoalEvidence,
    GoalSignal,
    SignalType,
    GoalStore,
    create_goal,
    create_signal,
    build_goal_store,
)


class TestGoalEnums:
    """Tests for goal-related enums."""

    def test_goal_type_values(self):
        """Test that goal types have expected values."""
        assert GoalType.LEARN_NEW_OPERATOR == "learn_new_operator"
        assert GoalType.FIX_REPEATED_ERROR == "fix_repeated_error"
        assert GoalType.IMPROVE_MEMORY_REUSE == "improve_memory_reuse"

    def test_goal_status_values(self):
        """Test that goal statuses have expected values."""
        assert GoalStatus.PROPOSED == "proposed"
        assert GoalStatus.ACCEPTED == "accepted"
        assert GoalStatus.COMPLETED == "completed"
        assert GoalStatus.FAILED == "failed"

    def test_goal_priority_values(self):
        """Test that goal priorities have expected values."""
        assert GoalPriority.CRITICAL == "critical"
        assert GoalPriority.HIGH == "high"
        assert GoalPriority.MEDIUM == "medium"
        assert GoalPriority.LOW == "low"


class TestGoalEvidence:
    """Tests for GoalEvidence model."""

    def test_create_evidence(self):
        """Test creating goal evidence."""
        evidence = GoalEvidence(
            evidence_id="ev_001",
            evidence_type="error_pattern",
            summary="Repeated timeout errors",
            details={"count": 5},
            source="error_memory",
        )

        assert evidence.evidence_id == "ev_001"
        assert evidence.evidence_type == "error_pattern"
        assert evidence.confidence == 0.5

    def test_evidence_serialization(self):
        """Test evidence serialization roundtrip."""
        evidence = GoalEvidence(
            evidence_id="ev_002",
            evidence_type="usage_metric",
            summary="Low memory reuse",
            details={"reuse_rate": 0.2},
            source="memory_analyzer",
            confidence=0.8,
        )

        data = evidence.to_dict()
        restored = GoalEvidence.from_dict(data)

        assert restored.evidence_id == evidence.evidence_id
        assert restored.evidence_type == evidence.evidence_type
        assert restored.confidence == evidence.confidence


class TestGoal:
    """Tests for Goal model."""

    def test_create_goal(self):
        """Test creating a goal."""
        goal = Goal(
            goal_id="goal_001",
            goal_type=GoalType.FIX_REPEATED_ERROR,
            title="Fix timeout errors",
            description="Fix recurring timeout errors in bridge calls",
            domain="touchdesigner",
        )

        assert goal.goal_id == "goal_001"
        assert goal.status == GoalStatus.PROPOSED
        assert goal.priority == GoalPriority.MEDIUM

    def test_goal_effective_priority(self):
        """Test effective priority calculation."""
        goal = Goal(
            goal_id="goal_002",
            goal_type=GoalType.IMPROVE_BRIDGE_RELIABILITY,
            title="Improve bridge",
            description="Test",
            domain="houdini",
            priority=GoalPriority.HIGH,
            confidence=0.8,
            impact_score=0.9,
        )

        effective = goal.get_effective_priority()
        # HIGH=0.8 * confidence=0.8 * impact=0.9 = 0.576
        assert 0.5 < effective < 0.7

    def test_goal_can_derive_tasks(self):
        """Test task derivation eligibility."""
        goal = Goal(
            goal_id="goal_003",
            goal_type=GoalType.LEARN_NEW_OPERATOR,
            title="Learn TOP",
            description="Test",
            domain="touchdesigner",
            status=GoalStatus.PROPOSED,
            confidence=0.6,
        )

        assert goal.can_derive_tasks() is True

        # Lower confidence should fail
        goal_low_conf = Goal(
            goal_id="goal_004",
            goal_type=GoalType.LEARN_NEW_OPERATOR,
            title="Test",
            description="Test",
            domain="touchdesigner",
            confidence=0.2,
        )
        assert goal_low_conf.can_derive_tasks() is False

    def test_goal_status_transitions(self):
        """Test goal status transitions."""
        goal = Goal(
            goal_id="goal_005",
            goal_type=GoalType.FIX_REPEATED_ERROR,
            title="Fix errors",
            description="Test",
            domain="houdini",
        )

        goal.mark_scheduled(["task_001", "task_002"])
        assert goal.status == GoalStatus.SCHEDULED
        assert len(goal.derived_task_ids) == 2

        goal.mark_in_progress()
        assert goal.status == GoalStatus.IN_PROGRESS

        goal.mark_completed("All tasks succeeded")
        assert goal.status == GoalStatus.COMPLETED
        assert goal.resolution_notes == "All tasks succeeded"

    def test_goal_serialization(self):
        """Test goal serialization roundtrip."""
        goal = Goal(
            goal_id="goal_006",
            goal_type=GoalType.DISTILL_TUTORIAL_KNOWLEDGE,
            title="Distill tutorial",
            description="Extract knowledge from tutorial video",
            domain="touchdesigner",
            priority=GoalPriority.HIGH,
            confidence=0.9,
            evidence=[
                GoalEvidence(
                    evidence_id="ev_001",
                    evidence_type="tutorial_raw",
                    summary="New tutorial available",
                )
            ],
        )

        data = goal.to_dict()
        restored = Goal.from_dict(data)

        assert restored.goal_id == goal.goal_id
        assert restored.goal_type == goal.goal_type
        assert restored.priority == goal.priority
        assert len(restored.evidence) == 1


class TestGoalSignal:
    """Tests for GoalSignal model."""

    def test_create_signal(self):
        """Test creating a signal."""
        signal = GoalSignal(
            signal_id="sig_001",
            signal_type=SignalType.REPEATED_ERROR,
            domain="houdini",
            source="error_memory",
            evidence={"error_signature": "timeout_error"},
        )

        assert signal.signal_type == SignalType.REPEATED_ERROR
        assert signal.recurrence_count == 1

    def test_signal_serialization(self):
        """Test signal serialization roundtrip."""
        signal = GoalSignal(
            signal_id="sig_002",
            signal_type=SignalType.WEAK_RETRIEVAL,
            domain="touchdesigner",
            source="memory_analyzer",
            evidence={"reuse_rate": 0.15},
            recurrence_count=5,
        )

        data = signal.to_dict()
        restored = GoalSignal.from_dict(data)

        assert restored.signal_id == signal.signal_id
        assert restored.recurrence_count == 5


class TestGoalStore:
    """Tests for GoalStore."""

    @pytest.fixture
    def temp_store(self, tmp_path: Path) -> GoalStore:
        """Create a temporary goal store."""
        store_dir = tmp_path / "goals"
        return build_goal_store(storage_dir=store_dir)

    def test_add_and_get_goal(self, temp_store: GoalStore):
        """Test adding and retrieving goals."""
        goal = Goal(
            goal_id="goal_store_001",
            goal_type=GoalType.LEARN_NEW_OPERATOR,
            title="Learn CHOP",
            description="Learn CHOP operators",
            domain="touchdesigner",
        )

        temp_store.add_goal(goal)
        retrieved = temp_store.get_goal("goal_store_001")

        assert retrieved is not None
        assert retrieved.title == "Learn CHOP"

    def test_list_goals_with_filters(self, temp_store: GoalStore):
        """Test listing goals with filters."""
        goals = [
            Goal(
                goal_id=f"goal_{i}",
                goal_type=GoalType.LEARN_NEW_OPERATOR,
                title=f"Goal {i}",
                description="Test",
                domain="touchdesigner" if i % 2 == 0 else "houdini",
                priority=GoalPriority.HIGH if i < 3 else GoalPriority.LOW,
            )
            for i in range(5)
        ]

        for g in goals:
            temp_store.add_goal(g)

        # Filter by domain
        td_goals = temp_store.list_goals(domain="touchdesigner")
        assert len(td_goals) >= 2

        # Filter by priority
        high_goals = temp_store.list_goals(priority=GoalPriority.HIGH)
        assert len(high_goals) == 3

    def test_update_goal_status(self, temp_store: GoalStore):
        """Test updating goal status."""
        goal = Goal(
            goal_id="goal_update_001",
            goal_type=GoalType.FIX_REPEATED_ERROR,
            title="Fix error",
            description="Test",
            domain="houdini",
        )
        temp_store.add_goal(goal)

        updated = temp_store.update_goal_status(
            "goal_update_001",
            GoalStatus.COMPLETED,
            "Fixed successfully",
        )

        assert updated is not None
        assert updated.status == GoalStatus.COMPLETED
        assert updated.resolution_notes == "Fixed successfully"

    def test_find_similar_goal(self, temp_store: GoalStore):
        """Test finding similar goals for deduplication."""
        goal1 = Goal(
            goal_id="goal_sim_001",
            goal_type=GoalType.FIX_REPEATED_ERROR,
            title="Fix timeout errors in bridge calls",
            description="Test",
            domain="touchdesigner",
        )
        temp_store.add_goal(goal1)

        # Search for similar
        similar = temp_store.find_similar_goal(
            domain="touchdesigner",
            goal_type=GoalType.FIX_REPEATED_ERROR,
            title_keywords=["timeout", "errors", "bridge"],
        )

        assert similar is not None
        assert similar.goal_id == "goal_sim_001"

    def test_signal_operations(self, temp_store: GoalStore):
        """Test signal operations."""
        signal = GoalSignal(
            signal_id="sig_test_001",
            signal_type=SignalType.BRIDGE_DEGRADATION,
            domain="houdini",
            source="bridge_monitor",
            evidence={"latency_ms": 5000},
        )

        temp_store.add_signal(signal)

        # Retrieve
        retrieved = temp_store.get_signal("sig_test_001")
        assert retrieved is not None
        assert retrieved.signal_type == SignalType.BRIDGE_DEGRADATION

        # Update recurrence
        updated = temp_store.update_signal_recurrence("sig_test_001", 2)
        assert updated.recurrence_count == 3  # 1 + 2

    def test_get_stats(self, temp_store: GoalStore):
        """Test statistics generation."""
        goals = [
            Goal(
                goal_id=f"goal_stat_{i}",
                goal_type=GoalType.LEARN_NEW_OPERATOR,
                title=f"Goal {i}",
                description="Test",
                domain="touchdesigner" if i % 2 == 0 else "houdini",
                status=GoalStatus.COMPLETED if i < 2 else GoalStatus.PROPOSED,
            )
            for i in range(5)
        ]

        for g in goals:
            temp_store.add_goal(g)

        stats = temp_store.get_stats()

        assert stats["total_goals"] == 5
        assert "by_domain" in stats
        assert "by_status" in stats

    def test_get_active_goals(self, temp_store: GoalStore):
        """Test getting active goals."""
        goals = [
            Goal(
                goal_id=f"goal_active_{i}",
                goal_type=GoalType.LEARN_NEW_OPERATOR,
                title=f"Goal {i}",
                description="Test",
                domain="touchdesigner",
                status=GoalStatus.PROPOSED if i < 3 else GoalStatus.COMPLETED,
            )
            for i in range(5)
        ]

        for g in goals:
            temp_store.add_goal(g)

        active = temp_store.get_active_goals()
        assert len(active) == 3


class TestFactoryFunctions:
    """Tests for factory functions."""

    def test_create_goal_factory(self):
        """Test create_goal factory."""
        goal = create_goal(
            goal_type=GoalType.FIX_REPEATED_ERROR,
            title="Fix test error",
            description="Fix recurring test error",
            domain="touchdesigner",
            priority=GoalPriority.HIGH,
            confidence=0.9,
        )

        assert goal.goal_type == GoalType.FIX_REPEATED_ERROR
        assert goal.priority == GoalPriority.HIGH
        assert "goal_" in goal.goal_id

    def test_create_signal_factory(self):
        """Test create_signal factory."""
        signal = create_signal(
            signal_type=SignalType.REPEATED_ERROR,
            domain="houdini",
            source="test",
            evidence={"count": 5},
        )

        assert signal.signal_type == SignalType.REPEATED_ERROR
        assert signal.evidence["count"] == 5


class TestPersistenceRoundtrip:
    """Tests for persistence roundtrip."""

    def test_persistence_roundtrip(self, tmp_path: Path):
        """Test that data persists across store instances."""
        store_dir = tmp_path / "goals"

        # Create and save
        store1 = build_goal_store(storage_dir=store_dir)
        goal = Goal(
            goal_id="goal_persist_001",
            goal_type=GoalType.DISTILL_TUTORIAL_KNOWLEDGE,
            title="Distill tutorial",
            description="Test persistence",
            domain="touchdesigner",
        )
        store1.add_goal(goal)

        # Create new instance and load
        store2 = build_goal_store(storage_dir=store_dir)
        retrieved = store2.get_goal("goal_persist_001")

        assert retrieved is not None
        assert retrieved.title == "Distill tutorial"