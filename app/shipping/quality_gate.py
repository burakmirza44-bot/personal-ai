"""Shipping Quality Gate - Eligibility checking and quality thresholds.

This module implements quality gates for shipping candidates,
ensuring only high-quality, verified artifacts are shipped.

Key functionality:
- Eligibility evaluation
- Quality threshold checking
- Duplicate detection
- Blocking reason tracking
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.shipping.models import (
    EligibilityStatus,
    QualityGateResult,
    QualityStatus,
    ShippingCandidate,
    ShippingResult,
)


# ------------------------------------------------------------------
# Quality Thresholds
# ------------------------------------------------------------------


class QualityThresholds:
    """Quality thresholds for shipping eligibility."""

    # Minimum scores
    MIN_QUALITY_SCORE = 0.5
    MIN_CONFIDENCE = 0.4
    MIN_VERIFIED_CONFIDENCE = 0.6  # Higher threshold for unverified

    # Content requirements
    MIN_SUMMARY_LENGTH = 10
    MIN_CONTENT_ITEMS = 1

    # Provenance requirements
    REQUIRE_PROVENANCE = True
    REQUIRE_SOURCE_ID = True
    REQUIRE_DOMAIN = True


class QualityChecks:
    """Names of quality checks."""

    VERIFICATION_PASSED = "verification_passed"
    QUALITY_SCORE_THRESHOLD = "quality_score_threshold"
    CONFIDENCE_THRESHOLD = "confidence_threshold"
    HAS_CONTENT = "has_content"
    HAS_SUMMARY = "has_summary"
    HAS_PROVENANCE = "has_provenance"
    HAS_SOURCE_ID = "has_source_id"
    HAS_DOMAIN = "has_domain"
    NOT_EMPTY = "not_empty"
    NOT_DUPLICATE = "not_duplicate"
    METADATA_COMPLETE = "metadata_complete"


# ------------------------------------------------------------------
# Quality Gate
# ------------------------------------------------------------------


@dataclass
class QualityGateConfig:
    """Configuration for the quality gate."""

    min_quality_score: float = QualityThresholds.MIN_QUALITY_SCORE
    min_confidence: float = QualityThresholds.MIN_CONFIDENCE
    min_verified_confidence: float = QualityThresholds.MIN_VERIFIED_CONFIDENCE
    min_summary_length: int = QualityThresholds.MIN_SUMMARY_LENGTH
    min_content_items: int = QualityThresholds.MIN_CONTENT_ITEMS
    require_provenance: bool = QualityThresholds.REQUIRE_PROVENANCE
    require_source_id: bool = QualityThresholds.REQUIRE_SOURCE_ID
    require_domain: bool = QualityThresholds.REQUIRE_DOMAIN
    require_verified: bool = False  # Whether to require verification

    # Checks to perform
    required_checks: list[str] = field(default_factory=lambda: [
        QualityChecks.QUALITY_SCORE_THRESHOLD,
        QualityChecks.CONFIDENCE_THRESHOLD,
        QualityChecks.HAS_CONTENT,
        QualityChecks.HAS_SUMMARY,
        QualityChecks.HAS_SOURCE_ID,
        QualityChecks.HAS_DOMAIN,
    ])

    optional_checks: list[str] = field(default_factory=lambda: [
        QualityChecks.VERIFICATION_PASSED,
        QualityChecks.HAS_PROVENANCE,
        QualityChecks.NOT_DUPLICATE,
        QualityChecks.METADATA_COMPLETE,
    ])


class QualityGate:
    """Evaluates shipping candidates for eligibility.

    The quality gate checks candidates against configured thresholds
    and requirements, determining if they can be shipped.
    """

    def __init__(self, config: QualityGateConfig | None = None) -> None:
        """Initialize the quality gate.

        Args:
            config: Optional configuration. Uses defaults if not provided.
        """
        self._config = config or QualityGateConfig()
        self._seen_signatures: set[str] = set()

    def evaluate(self, candidate: ShippingCandidate) -> QualityGateResult:
        """Evaluate a candidate for shipping eligibility.

        Args:
            candidate: Candidate to evaluate

        Returns:
            QualityGateResult with evaluation outcome
        """
        passed_checks: list[str] = []
        failed_checks: list[str] = []
        warnings: list[str] = []

        # Run required checks
        for check in self._config.required_checks:
            passed, warning = self._run_check(check, candidate)
            if passed:
                passed_checks.append(check)
            else:
                failed_checks.append(check)
            if warning:
                warnings.append(warning)

        # Run optional checks
        for check in self._config.optional_checks:
            passed, warning = self._run_check(check, candidate)
            if passed:
                passed_checks.append(check)
            else:
                warnings.append(f"Optional check '{check}' not passed")
            if warning:
                warnings.append(warning)

        # Determine status
        if failed_checks:
            status = QualityStatus.FAIL
        elif warnings:
            status = QualityStatus.PASS_WITH_WARNINGS
        else:
            status = QualityStatus.PASS

        # Calculate overall score
        total_checks = len(self._config.required_checks) + len(self._config.optional_checks)
        passed_count = len(passed_checks)
        score = passed_count / total_checks if total_checks > 0 else 0.0

        # Determine blocked reason
        blocked_reason = ""
        if failed_checks:
            blocked_reason = f"Failed checks: {', '.join(failed_checks)}"

        return QualityGateResult(
            status=status,
            score=score,
            confidence=candidate.confidence,
            verified=candidate.verified,
            passed_checks=passed_checks,
            failed_checks=failed_checks,
            warnings=warnings,
            blocked_reason=blocked_reason,
            required_checks=self._config.required_checks.copy(),
            optional_checks=self._config.optional_checks.copy(),
        )

    def check_eligibility(self, candidate: ShippingCandidate) -> tuple[bool, EligibilityStatus, str]:
        """Check if a candidate is eligible for shipping.

        Args:
            candidate: Candidate to check

        Returns:
            Tuple of (is_eligible, status, reason)
        """
        # Run quality gate
        result = self.evaluate(candidate)

        # Check for duplicate
        signature = candidate.content_signature
        if signature in self._seen_signatures:
            return False, EligibilityStatus.DUPLICATE, "Content already shipped"

        # Check result
        if result.status == QualityStatus.FAIL:
            return False, EligibilityStatus.BLOCKED, result.blocked_reason

        if result.status == QualityStatus.INSUFFICIENT_DATA:
            return False, EligibilityStatus.PENDING_REVIEW, "Insufficient data for evaluation"

        # Eligible (possibly with warnings)
        status = EligibilityStatus.ELIGIBLE
        if result.has_warnings:
            status = EligibilityStatus.ELIGIBLE_WITH_WARNINGS

        return True, status, ""

    def register_shipped(self, candidate: ShippingCandidate) -> None:
        """Register a candidate as shipped for duplicate detection.

        Args:
            candidate: Candidate that was shipped
        """
        self._seen_signatures.add(candidate.content_signature)

    def is_duplicate(self, candidate: ShippingCandidate) -> bool:
        """Check if a candidate is a duplicate.

        Args:
            candidate: Candidate to check

        Returns:
            True if duplicate
        """
        return candidate.content_signature in self._seen_signatures

    def _run_check(self, check: str, candidate: ShippingCandidate) -> tuple[bool, str | None]:
        """Run a single quality check.

        Args:
            check: Check name
            candidate: Candidate to check

        Returns:
            Tuple of (passed, warning_message)
        """
        if check == QualityChecks.VERIFICATION_PASSED:
            return self._check_verification(candidate)

        elif check == QualityChecks.QUALITY_SCORE_THRESHOLD:
            return self._check_quality_score(candidate)

        elif check == QualityChecks.CONFIDENCE_THRESHOLD:
            return self._check_confidence(candidate)

        elif check == QualityChecks.HAS_CONTENT:
            return self._check_has_content(candidate)

        elif check == QualityChecks.HAS_SUMMARY:
            return self._check_has_summary(candidate)

        elif check == QualityChecks.HAS_PROVENANCE:
            return self._check_has_provenance(candidate)

        elif check == QualityChecks.HAS_SOURCE_ID:
            return self._check_has_source_id(candidate)

        elif check == QualityChecks.HAS_DOMAIN:
            return self._check_has_domain(candidate)

        elif check == QualityChecks.NOT_EMPTY:
            return self._check_not_empty(candidate)

        elif check == QualityChecks.NOT_DUPLICATE:
            return self._check_not_duplicate(candidate)

        elif check == QualityChecks.METADATA_COMPLETE:
            return self._check_metadata_complete(candidate)

        else:
            return False, f"Unknown check: {check}"

    def _check_verification(self, candidate: ShippingCandidate) -> tuple[bool, str | None]:
        """Check if candidate is verified."""
        if candidate.verified:
            return True, None
        # Not verified is acceptable if confidence is high enough
        if candidate.confidence >= self._config.min_verified_confidence:
            return True, "Not verified but confidence is sufficient"
        return True, "Not verified"

    def _check_quality_score(self, candidate: ShippingCandidate) -> tuple[bool, str | None]:
        """Check quality score threshold."""
        if candidate.quality_score >= self._config.min_quality_score:
            return True, None
        return False, f"Quality score {candidate.quality_score:.2f} below threshold {self._config.min_quality_score}"

    def _check_confidence(self, candidate: ShippingCandidate) -> tuple[bool, str | None]:
        """Check confidence threshold."""
        threshold = self._config.min_confidence
        if not candidate.verified:
            threshold = self._config.min_verified_confidence

        if candidate.confidence >= threshold:
            return True, None
        return False, f"Confidence {candidate.confidence:.2f} below threshold {threshold}"

    def _check_has_content(self, candidate: ShippingCandidate) -> tuple[bool, str | None]:
        """Check if candidate has content."""
        if candidate.content_data and len(candidate.content_data) >= self._config.min_content_items:
            return True, None
        if candidate.content_ref:
            return True, None
        return False, "No content data or reference"

    def _check_has_summary(self, candidate: ShippingCandidate) -> tuple[bool, str | None]:
        """Check if candidate has summary."""
        if len(candidate.summary) >= self._config.min_summary_length:
            return True, None
        return False, f"Summary too short ({len(candidate.summary)} chars)"

    def _check_has_provenance(self, candidate: ShippingCandidate) -> tuple[bool, str | None]:
        """Check if candidate has provenance."""
        if candidate.provenance is not None:
            return True, None
        return False, "Missing provenance"

    def _check_has_source_id(self, candidate: ShippingCandidate) -> tuple[bool, str | None]:
        """Check if candidate has source ID."""
        if candidate.source_id:
            return True, None
        return False, "Missing source ID"

    def _check_has_domain(self, candidate: ShippingCandidate) -> tuple[bool, str | None]:
        """Check if candidate has domain."""
        if candidate.domain:
            return True, None
        return False, "Missing domain"

    def _check_not_empty(self, candidate: ShippingCandidate) -> tuple[bool, str | None]:
        """Check if candidate is not empty."""
        if candidate.content_data or candidate.content_ref or candidate.summary:
            return True, None
        return False, "Candidate is empty"

    def _check_not_duplicate(self, candidate: ShippingCandidate) -> tuple[bool, str | None]:
        """Check if candidate is not a duplicate."""
        if not self.is_duplicate(candidate):
            return True, None
        return False, "Duplicate content"

    def _check_metadata_complete(self, candidate: ShippingCandidate) -> tuple[bool, str | None]:
        """Check if metadata is reasonably complete."""
        missing = []
        if not candidate.title:
            missing.append("title")
        if not candidate.domain:
            missing.append("domain")
        if not candidate.tags:
            missing.append("tags")

        if not missing:
            return True, None
        return True, f"Metadata incomplete: missing {', '.join(missing)}"


# ------------------------------------------------------------------
# Convenience Functions
# ------------------------------------------------------------------


def evaluate_candidate(
    candidate: ShippingCandidate,
    config: QualityGateConfig | None = None,
) -> QualityGateResult:
    """Evaluate a shipping candidate.

    Args:
        candidate: Candidate to evaluate
        config: Optional quality gate configuration

    Returns:
        QualityGateResult
    """
    gate = QualityGate(config)
    return gate.evaluate(candidate)


def check_shipping_eligibility(
    candidate: ShippingCandidate,
    config: QualityGateConfig | None = None,
) -> tuple[bool, str]:
    """Check if a candidate can be shipped.

    Args:
        candidate: Candidate to check
        config: Optional quality gate configuration

    Returns:
        Tuple of (is_eligible, reason)
    """
    gate = QualityGate(config)
    eligible, status, reason = gate.check_eligibility(candidate)
    return eligible, f"{status.value}: {reason}" if reason else status.value


def is_high_quality_candidate(
    candidate: ShippingCandidate,
    min_quality: float = QualityThresholds.MIN_QUALITY_SCORE,
    min_confidence: float = QualityThresholds.MIN_CONFIDENCE,
) -> bool:
    """Quick check if candidate meets minimum quality thresholds.

    Args:
        candidate: Candidate to check
        min_quality: Minimum quality score
        min_confidence: Minimum confidence score

    Returns:
        True if candidate meets thresholds
    """
    return (
        candidate.quality_score >= min_quality
        and candidate.confidence >= min_confidence
        and bool(candidate.content_data or candidate.content_ref)
        and len(candidate.summary) >= 10
    )


def filter_eligible_candidates(
    candidates: list[ShippingCandidate],
    config: QualityGateConfig | None = None,
) -> tuple[list[ShippingCandidate], list[ShippingCandidate]]:
    """Filter candidates into eligible and blocked.

    Args:
        candidates: Candidates to filter
        config: Optional quality gate configuration

    Returns:
        Tuple of (eligible_candidates, blocked_candidates)
    """
    gate = QualityGate(config)
    eligible = []
    blocked = []

    for candidate in candidates:
        is_eligible, status, reason = gate.check_eligibility(candidate)
        if is_eligible:
            eligible.append(candidate)
        else:
            blocked.append(candidate)

    return eligible, blocked