"""Validation Pipeline for Distilled Knowledge.

Provides comprehensive validation for recipes and other distilled knowledge
before they are committed to the knowledge store.

Components:
- SchemaValidator: JSON schema validation
- QualityGate: Confidence and completeness thresholds
- ContradictionDetector: Detect conflicts with existing knowledge
- SanityChecker: Logical consistency checks
- ValidationPipeline: Unified validation pipeline

Validation Results:
- ACCEPT: Knowledge passes all checks
- REVIEW: Needs human review (borderline)
- REJECT: Fails validation, should not be stored
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

# =============================================================================
# VALIDATION DECISION TYPES
# =============================================================================


class ValidationDecision(str, Enum):
    """Final validation decision."""

    ACCEPT = "accept"  # Pass all checks, store immediately
    REVIEW = "review"  # Borderline, needs human review
    REJECT = "reject"  # Fails validation, do not store


@dataclass(slots=True)
class ValidationResult:
    """Complete validation result for a recipe or knowledge item."""

    item_id: str
    item_type: str  # "recipe", "repair_hint", etc.
    decision: ValidationDecision
    confidence: float  # Overall confidence in the decision

    # Individual stage results
    schema_valid: bool = True
    quality_score: float = 0.0
    has_contradictions: bool = False
    sanity_issues: list[str] = field(default_factory=list)

    # Detailed issues
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)

    # Metadata
    validated_at: str = ""
    validator_version: str = "1.0.0"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "item_id": self.item_id,
            "item_type": self.item_type,
            "decision": self.decision.value,
            "confidence": self.confidence,
            "schema_valid": self.schema_valid,
            "quality_score": self.quality_score,
            "has_contradictions": self.has_contradictions,
            "sanity_issues": self.sanity_issues,
            "errors": self.errors,
            "warnings": self.warnings,
            "suggestions": self.suggestions,
            "validated_at": self.validated_at,
            "validator_version": self.validator_version,
        }

    @property
    def is_acceptable(self) -> bool:
        """Check if item can be stored (ACCEPT or REVIEW)."""
        return self.decision in (ValidationDecision.ACCEPT, ValidationDecision.REVIEW)


@dataclass(slots=True)
class SchemaValidationResult:
    """Result of schema validation."""

    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class QualityEvaluationResult:
    """Result of quality gate evaluation."""

    passed: bool
    score: float
    confidence: float
    completeness: float
    issues: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ContradictionCheckResult:
    """Result of contradiction detection."""

    has_contradictions: bool
    contradictions: list[dict[str, Any]] = field(default_factory=list)
    severity: str = "none"  # "none", "minor", "major", "critical"


@dataclass(slots=True)
class SanityCheckResult:
    """Result of sanity checks."""

    passed: bool
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# =============================================================================
# CONFIGURATION
# =============================================================================


@dataclass(slots=True)
class QualityThresholds:
    """Quality thresholds for validation."""

    min_confidence: float = 0.7
    min_completeness: float = 0.8
    review_confidence: float = 0.5  # Below this = REJECT, below min_confidence = REVIEW
    review_completeness: float = 0.6

    # Scoring weights
    confidence_weight: float = 0.4
    completeness_weight: float = 0.3
    verification_weight: float = 0.3


@dataclass(slots=True)
class ValidationConfig:
    """Configuration for the validation pipeline."""

    # Stage enables
    enable_schema_validation: bool = True
    enable_quality_gate: bool = True
    enable_contradiction_detection: bool = True
    enable_sanity_checks: bool = True

    # Thresholds
    quality_thresholds: QualityThresholds = field(default_factory=QualityThresholds)

    # Decision thresholds
    accept_min_score: float = 0.8
    review_min_score: float = 0.5

    # Strictness mode
    strict_mode: bool = False  # In strict mode, REVIEW becomes REJECT

    # Sanity check options
    check_step_ordering: bool = True
    check_input_output_chains: bool = True
    check_circular_dependencies: bool = True
    check_operator_availability: bool = False  # Requires domain knowledge


# =============================================================================
# SCHEMA VALIDATOR
# =============================================================================


# JSON Schema for recipe validation
RECIPE_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "required": ["recipe_id", "title", "domain"],
    "properties": {
        "recipe_id": {"type": "string", "minLength": 1},
        "title": {"type": "string", "minLength": 1},
        "description": {"type": "string"},
        "domain": {"type": "string", "enum": ["houdini", "touchdesigner", "general"]},
        "status": {"type": "string", "enum": ["draft", "active", "deprecated", "archived"]},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "overall_confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["step_id", "description"],
                "properties": {
                    "step_id": {"type": "string"},
                    "step_type": {"type": "string"},
                    "description": {"type": "string"},
                    "action": {"type": "string"},
                    "target": {"type": "string"},
                    "node_type": {"type": "string"},
                    "params": {"type": "object"},
                    "parameters": {"type": "object"},
                    "expected_outcome": {"type": "string"},
                    "verification_hint": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
            },
        },
        "stages": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "stage_id": {"type": "string"},
                    "name": {"type": "string"},
                    "steps": {"type": "array"},
                },
            },
        },
        "required_nodes": {"type": "array", "items": {"type": "string"}},
        "verification_checks": {"type": "array", "items": {"type": "string"}},
        "success_criteria": {"type": "array", "items": {"type": "string"}},
        "provenance": {"type": "object"},
        "created_at": {"type": "string"},
        "updated_at": {"type": "string"},
    },
}


class SchemaValidator:
    """Validates recipes against JSON schema."""

    def __init__(self, schema: dict[str, Any] | None = None):
        """Initialize with optional custom schema.

        Args:
            schema: Custom JSON schema, defaults to RECIPE_SCHEMA
        """
        self._schema = schema or RECIPE_SCHEMA
        self._validator = None

    def validate(self, data: dict[str, Any]) -> SchemaValidationResult:
        """Validate data against schema.

        Args:
            data: Data to validate

        Returns:
            SchemaValidationResult with valid flag and any errors
        """
        errors: list[str] = []
        warnings: list[str] = []

        # Try to use jsonschema library if available
        try:
            import jsonschema
            from jsonschema import validate as json_validate
            from jsonschema.exceptions import ValidationError

            try:
                json_validate(instance=data, schema=self._schema)
            except ValidationError as e:
                errors.append(f"Schema validation: {e.message}")
                return SchemaValidationResult(valid=False, errors=errors, warnings=warnings)

        except ImportError:
            # Fallback to manual validation
            result = self._manual_validate(data, errors, warnings)
            return result

        # Additional semantic checks
        self._check_semantics(data, warnings)

        return SchemaValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)

    def _manual_validate(
        self,
        data: dict[str, Any],
        errors: list[str],
        warnings: list[str],
    ) -> SchemaValidationResult:
        """Manual validation when jsonschema is not available."""
        schema_props = self._schema.get("properties", {})
        required = self._schema.get("required", [])

        # Check required fields
        for field_name in required:
            if field_name not in data:
                errors.append(f"Missing required field: {field_name}")

        # Check field types
        for key, value in data.items():
            if key not in schema_props:
                warnings.append(f"Unknown field: {key}")
                continue

            prop_schema = schema_props[key]
            expected_type = prop_schema.get("type")

            if expected_type and not self._check_type(value, expected_type):
                errors.append(f"Field '{key}' has wrong type, expected {expected_type}")

            # Check enums
            if "enum" in prop_schema and value not in prop_schema["enum"]:
                errors.append(f"Field '{key}' value '{value}' not in allowed values: {prop_schema['enum']}")

            # Check min/max for numbers
            if isinstance(value, (int, float)):
                if "minimum" in prop_schema and value < prop_schema["minimum"]:
                    errors.append(f"Field '{key}' value {value} below minimum {prop_schema['minimum']}")
                if "maximum" in prop_schema and value > prop_schema["maximum"]:
                    errors.append(f"Field '{key}' value {value} above maximum {prop_schema['maximum']}")

        return SchemaValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)

    def _check_type(self, value: Any, expected_type: str) -> bool:
        """Check if value matches expected JSON schema type."""
        type_map = {
            "string": str,
            "number": (int, float),
            "integer": int,
            "boolean": bool,
            "array": list,
            "object": dict,
            "null": type(None),
        }
        expected = type_map.get(expected_type)
        if expected is None:
            return True
        return isinstance(value, expected)

    def _check_semantics(self, data: dict[str, Any], warnings: list[str]) -> None:
        """Check semantic validity beyond schema."""
        # Check for duplicate step IDs
        steps = data.get("steps", [])
        step_ids = [s.get("step_id") for s in steps if s.get("step_id")]
        if len(step_ids) != len(set(step_ids)):
            warnings.append("Duplicate step IDs detected")

        # Check for empty steps array with stages
        if not steps and data.get("stages"):
            stage_steps = []
            for stage in data["stages"]:
                stage_steps.extend(stage.get("steps", []))
            if stage_steps:
                warnings.append("Steps in stages but not in top-level steps array")


# =============================================================================
# QUALITY GATE
# =============================================================================


class QualityGate:
    """Evaluates recipe quality against thresholds."""

    def __init__(self, thresholds: QualityThresholds | None = None):
        """Initialize with quality thresholds.

        Args:
            thresholds: Quality thresholds configuration
        """
        self._thresholds = thresholds or QualityThresholds()

    def evaluate(self, recipe: dict[str, Any]) -> QualityEvaluationResult:
        """Evaluate recipe quality.

        Args:
            recipe: Recipe to evaluate

        Returns:
            QualityEvaluationResult with pass/fail and scores
        """
        issues: list[str] = []

        # Calculate confidence
        confidence = self._calculate_confidence(recipe)

        # Calculate completeness
        completeness = self._calculate_completeness(recipe, issues)

        # Calculate verification score
        verification = self._calculate_verification_score(recipe)

        # Calculate overall score
        score = (
            confidence * self._thresholds.confidence_weight
            + completeness * self._thresholds.completeness_weight
            + verification * self._thresholds.verification_weight
        )

        # Determine if passed
        passed = (
            confidence >= self._thresholds.min_confidence
            and completeness >= self._thresholds.min_completeness
        )

        return QualityEvaluationResult(
            passed=passed,
            score=score,
            confidence=confidence,
            completeness=completeness,
            issues=issues,
        )

    def _calculate_confidence(self, recipe: dict[str, Any]) -> float:
        """Calculate overall confidence score."""
        # Use explicit confidence if available
        if "overall_confidence" in recipe:
            return float(recipe["overall_confidence"])
        if "confidence" in recipe:
            return float(recipe["confidence"])

        # Calculate from steps
        steps = self._get_all_steps(recipe)
        if not steps:
            return 0.3  # Default low confidence for empty recipes

        step_confidences = [s.get("confidence", 0.5) for s in steps]
        return sum(step_confidences) / len(step_confidences)

    def _calculate_completeness(self, recipe: dict[str, Any], issues: list[str]) -> float:
        """Calculate recipe completeness score."""
        scores: list[float] = []

        # Has description
        if recipe.get("description"):
            scores.append(1.0)
        else:
            scores.append(0.5)
            issues.append("Missing description")

        # Has steps
        steps = self._get_all_steps(recipe)
        if steps:
            scores.append(1.0)
        else:
            scores.append(0.0)
            issues.append("No steps defined")

        # Steps have descriptions
        if steps:
            described_steps = sum(1 for s in steps if s.get("description"))
            step_desc_ratio = described_steps / len(steps)
            scores.append(step_desc_ratio)
            if step_desc_ratio < 0.8:
                issues.append(f"Only {described_steps}/{len(steps)} steps have descriptions")

        # Has verification checks
        if recipe.get("verification_checks"):
            scores.append(1.0)
        else:
            scores.append(0.6)
            issues.append("No verification checks defined")

        # Has success criteria
        if recipe.get("success_criteria"):
            scores.append(1.0)
        else:
            scores.append(0.7)

        # Has required nodes/operators
        if recipe.get("required_nodes"):
            scores.append(1.0)
        else:
            scores.append(0.8)

        return sum(scores) / len(scores) if scores else 0.5

    def _calculate_verification_score(self, recipe: dict[str, Any]) -> float:
        """Calculate verification coverage score."""
        steps = self._get_all_steps(recipe)
        if not steps:
            return 0.5

        # Check how many steps have verification hints
        steps_with_verification = sum(
            1 for s in steps
            if s.get("verification_hint") or s.get("expected_outcome")
        )

        return steps_with_verification / len(steps)

    def _get_all_steps(self, recipe: dict[str, Any]) -> list[dict[str, Any]]:
        """Get all steps from recipe, including from stages."""
        steps = list(recipe.get("steps", []))

        for stage in recipe.get("stages", []):
            steps.extend(stage.get("steps", []))

        return steps


# =============================================================================
# CONTRADICTION DETECTOR
# =============================================================================


class ContradictionDetector:
    """Detects contradictions between new and existing knowledge."""

    def __init__(
        self,
        existing_recipes: list[dict[str, Any]] | None = None,
        similarity_threshold: float = 0.8,
    ):
        """Initialize with existing knowledge.

        Args:
            existing_recipes: Existing recipes to check against
            similarity_threshold: Threshold for considering items similar
        """
        self._existing_recipes = existing_recipes or []
        self._similarity_threshold = similarity_threshold

    def check(self, recipe: dict[str, Any]) -> ContradictionCheckResult:
        """Check for contradictions with existing knowledge.

        Args:
            recipe: Recipe to check

        Returns:
            ContradictionCheckResult with any found contradictions
        """
        contradictions: list[dict[str, Any]] = []

        # Check for duplicate IDs
        recipe_id = recipe.get("recipe_id", "")
        for existing in self._existing_recipes:
            if existing.get("recipe_id") == recipe_id:
                contradictions.append({
                    "type": "duplicate_id",
                    "severity": "critical",
                    "message": f"Recipe with ID '{recipe_id}' already exists",
                    "existing_id": recipe_id,
                })

        # Check for similar recipes with different actions
        for existing in self._existing_recipes:
            if self._is_similar(recipe, existing):
                # Check for action conflicts
                conflict = self._check_action_conflict(recipe, existing)
                if conflict:
                    contradictions.append(conflict)

        # Check for internal contradictions
        internal = self._check_internal_contradictions(recipe)
        contradictions.extend(internal)

        # Determine severity
        severity = "none"
        if contradictions:
            severities = [c.get("severity", "minor") for c in contradictions]
            if "critical" in severities:
                severity = "critical"
            elif "major" in severities:
                severity = "major"
            else:
                severity = "minor"

        return ContradictionCheckResult(
            has_contradictions=len(contradictions) > 0,
            contradictions=contradictions,
            severity=severity,
        )

    def _is_similar(self, recipe1: dict[str, Any], recipe2: dict[str, Any]) -> bool:
        """Check if two recipes are similar."""
        # Check title similarity
        title1 = recipe1.get("title", "").lower()
        title2 = recipe2.get("title", "").lower()

        # Simple similarity check
        if title1 and title2:
            # Check if one contains the other or they share significant words
            words1 = set(title1.split())
            words2 = set(title2.split())
            common = words1 & words2

            if common:
                similarity = len(common) / max(len(words1), len(words2))
                return similarity >= self._similarity_threshold

        return False

    def _check_action_conflict(
        self,
        recipe1: dict[str, Any],
        recipe2: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Check for conflicting actions between similar recipes."""
        steps1 = recipe1.get("steps", [])
        steps2 = recipe2.get("steps", [])

        # Check if domains differ
        domain1 = recipe1.get("domain", "")
        domain2 = recipe2.get("domain", "")

        if domain1 != domain2 and self._is_similar(recipe1, recipe2):
            return {
                "type": "domain_mismatch",
                "severity": "major",
                "message": f"Similar recipes have different domains: {domain1} vs {domain2}",
                "recipe_ids": [recipe1.get("recipe_id"), recipe2.get("recipe_id")],
            }

        return None

    def _check_internal_contradictions(self, recipe: dict[str, Any]) -> list[dict[str, Any]]:
        """Check for internal contradictions within a recipe."""
        contradictions: list[dict[str, Any]] = []

        steps = self._get_all_steps(recipe)

        # Check for contradictory step expectations
        for i, step in enumerate(steps):
            expected = step.get("expected_outcome", "").lower()
            if not expected:
                continue

            for j, other in enumerate(steps[i + 1 :], i + 1):
                other_expected = other.get("expected_outcome", "").lower()
                if not other_expected:
                    continue

                # Check for negation patterns
                if self._are_contradictory(expected, other_expected):
                    contradictions.append({
                        "type": "contradictory_expectations",
                        "severity": "minor",
                        "message": f"Steps {i} and {j} have contradictory expectations",
                        "step_indices": [i, j],
                    })

        return contradictions

    def _are_contradictory(self, text1: str, text2: str) -> bool:
        """Check if two texts are contradictory."""
        # Simple heuristics for contradiction detection
        negation_words = ["not", "no ", "never", "without", "avoid", "don't"]

        # Check if one has negation and the other doesn't
        has_negation1 = any(neg in text1 for neg in negation_words)
        has_negation2 = any(neg in text2 for neg in negation_words)

        # If both have negation or neither has, not contradictory
        if has_negation1 == has_negation2:
            return False

        # Check for common keywords suggesting same topic
        words1 = set(text1.split())
        words2 = set(text2.split())
        common = words1 & words2 - {"the", "a", "an", "is", "are", "will", "be"}

        # If they share significant words but have different negation, possible contradiction
        return len(common) >= 2

    def _get_all_steps(self, recipe: dict[str, Any]) -> list[dict[str, Any]]:
        """Get all steps from recipe."""
        steps = list(recipe.get("steps", []))
        for stage in recipe.get("stages", []):
            steps.extend(stage.get("steps", []))
        return steps

    def add_existing_recipe(self, recipe: dict[str, Any]) -> None:
        """Add a recipe to the existing knowledge base."""
        self._existing_recipes.append(recipe)

    def set_existing_recipes(self, recipes: list[dict[str, Any]]) -> None:
        """Set the existing knowledge base."""
        self._existing_recipes = recipes


# =============================================================================
# SANITY CHECKER
# =============================================================================


class SanityChecker:
    """Performs sanity checks on recipes."""

    def __init__(self, config: ValidationConfig | None = None):
        """Initialize with validation config.

        Args:
            config: Validation configuration
        """
        self._config = config or ValidationConfig()

    def check(self, recipe: dict[str, Any]) -> SanityCheckResult:
        """Run sanity checks on recipe.

        Args:
            recipe: Recipe to check

        Returns:
            SanityCheckResult with issues and warnings
        """
        issues: list[str] = []
        warnings: list[str] = []

        # Check step ordering
        if self._config.check_step_ordering:
            self._check_step_ordering(recipe, issues, warnings)

        # Check input/output chains
        if self._config.check_input_output_chains:
            self._check_input_output_chains(recipe, issues, warnings)

        # Check circular dependencies
        if self._config.check_circular_dependencies:
            self._check_circular_dependencies(recipe, issues, warnings)

        return SanityCheckResult(
            passed=len(issues) == 0,
            issues=issues,
            warnings=warnings,
        )

    def _check_step_ordering(
        self,
        recipe: dict[str, Any],
        issues: list[str],
        warnings: list[str],
    ) -> None:
        """Check that steps are in logical order."""
        steps = self._get_all_steps(recipe)
        if len(steps) < 2:
            return

        # Check for prerequisite violations
        # A step that references something created in a later step is out of order
        created_names: set[str] = set()

        for i, step in enumerate(steps):
            # Track what this step creates
            target = step.get("target", step.get("target_name", ""))
            if target:
                created_names.add(target.lower())

            # Check if step references something not yet created
            depends_on = step.get("depends_on", step.get("requires", []))
            if isinstance(depends_on, str):
                depends_on = [depends_on]

            for dep in depends_on:
                if dep.lower() not in created_names:
                    warnings.append(
                        f"Step {i} references '{dep}' which may not be created yet"
                    )

    def _check_input_output_chains(
        self,
        recipe: dict[str, Any],
        issues: list[str],
        warnings: list[str],
    ) -> None:
        """Check that input/output chains are valid."""
        steps = self._get_all_steps(recipe)

        # Track inputs and outputs
        available_outputs: set[str] = set()

        for i, step in enumerate(steps):
            # Get expected inputs
            inputs = step.get("inputs", step.get("required_inputs", []))
            if isinstance(inputs, str):
                inputs = [inputs]

            # Get expected outputs
            outputs = step.get("outputs", step.get("expected_outputs", []))
            if isinstance(outputs, str):
                outputs = [outputs]

            # Check if inputs are available
            for inp in inputs:
                if inp.lower() not in available_outputs:
                    # Might be initial input
                    if i > 0:
                        warnings.append(
                            f"Step {i} requires input '{inp}' which is not produced by previous steps"
                        )

            # Add outputs to available
            for out in outputs:
                available_outputs.add(out.lower())

    def _check_circular_dependencies(
        self,
        recipe: dict[str, Any],
        issues: list[str],
        warnings: list[str],
    ) -> None:
        """Check for circular dependencies in steps."""
        steps = self._get_all_steps(recipe)

        # Build dependency graph
        dependencies: dict[str, set[str]] = {}

        for i, step in enumerate(steps):
            step_id = step.get("step_id", f"step_{i}")
            dependencies[step_id] = set()

            deps = step.get("depends_on", step.get("dependencies", []))
            if isinstance(deps, str):
                deps = [deps]

            for dep in deps:
                dependencies[step_id].add(dep)

        # Check for cycles using DFS
        visited: set[str] = set()
        rec_stack: set[str] = set()

        def has_cycle(node: str) -> bool:
            visited.add(node)
            rec_stack.add(node)

            for neighbor in dependencies.get(node, set()):
                if neighbor not in visited:
                    if has_cycle(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True

            rec_stack.remove(node)
            return False

        for step_id in dependencies:
            if step_id not in visited:
                if has_cycle(step_id):
                    issues.append(f"Circular dependency detected involving step '{step_id}'")

    def _get_all_steps(self, recipe: dict[str, Any]) -> list[dict[str, Any]]:
        """Get all steps from recipe."""
        steps = list(recipe.get("steps", []))
        for stage in recipe.get("stages", []):
            steps.extend(stage.get("steps", []))
        return steps


# =============================================================================
# VALIDATION PIPELINE
# =============================================================================


class ValidationPipeline:
    """Complete validation pipeline for recipes."""

    def __init__(
        self,
        config: ValidationConfig | None = None,
        existing_recipes: list[dict[str, Any]] | None = None,
    ):
        """Initialize the validation pipeline.

        Args:
            config: Validation configuration
            existing_recipes: Existing recipes for contradiction detection
        """
        self._config = config or ValidationConfig()

        # Initialize validators
        self._schema_validator = SchemaValidator()
        self._quality_gate = QualityGate(self._config.quality_thresholds)
        self._contradiction_detector = ContradictionDetector(existing_recipes)
        self._sanity_checker = SanityChecker(self._config)

    def validate(self, recipe: dict[str, Any]) -> ValidationResult:
        """Run full validation pipeline on a recipe.

        Args:
            recipe: Recipe to validate

        Returns:
            ValidationResult with final decision
        """
        import datetime

        recipe_id = recipe.get("recipe_id", "unknown")
        errors: list[str] = []
        warnings: list[str] = []
        suggestions: list[str] = []

        # Stage 1: Schema validation
        schema_valid = True
        if self._config.enable_schema_validation:
            schema_result = self._schema_validator.validate(recipe)
            schema_valid = schema_result.valid
            errors.extend(schema_result.errors)
            warnings.extend(schema_result.warnings)

            if not schema_valid:
                return ValidationResult(
                    item_id=recipe_id,
                    item_type="recipe",
                    decision=ValidationDecision.REJECT,
                    confidence=1.0,
                    schema_valid=False,
                    errors=errors,
                    warnings=warnings,
                    validated_at=datetime.datetime.utcnow().isoformat() + "Z",
                )

        # Stage 2: Quality gate
        quality_score = 0.0
        quality_result = None
        if self._config.enable_quality_gate:
            quality_result = self._quality_gate.evaluate(recipe)
            quality_score = quality_result.score
            if not quality_result.passed:
                warnings.extend(quality_result.issues)

        # Stage 3: Contradiction detection
        has_contradictions = False
        contradiction_result = None
        if self._config.enable_contradiction_detection:
            contradiction_result = self._contradiction_detector.check(recipe)
            has_contradictions = contradiction_result.has_contradictions

            if contradiction_result.severity == "critical":
                errors.append("Critical contradiction detected")
                for c in contradiction_result.contradictions:
                    if c.get("severity") == "critical":
                        errors.append(c.get("message", "Unknown contradiction"))

        # Stage 4: Sanity checks
        sanity_issues: list[str] = []
        sanity_result = None
        if self._config.enable_sanity_checks:
            sanity_result = self._sanity_checker.check(recipe)
            sanity_issues = sanity_result.issues
            warnings.extend(sanity_result.warnings)

            if sanity_result.issues:
                errors.extend(sanity_result.issues)

        # Determine final decision
        decision = self._make_decision(
            schema_valid=schema_valid,
            quality_result=quality_result,
            contradiction_result=contradiction_result,
            sanity_result=sanity_result,
            errors=errors,
        )

        # Generate suggestions
        suggestions = self._generate_suggestions(recipe, quality_result, sanity_result)

        # Calculate overall confidence in the decision
        confidence = self._calculate_decision_confidence(
            decision=decision,
            quality_score=quality_score,
            has_contradictions=has_contradictions,
            has_sanity_issues=len(sanity_issues) > 0,
        )

        return ValidationResult(
            item_id=recipe_id,
            item_type="recipe",
            decision=decision,
            confidence=confidence,
            schema_valid=schema_valid,
            quality_score=quality_score,
            has_contradictions=has_contradictions,
            sanity_issues=sanity_issues,
            errors=errors,
            warnings=warnings,
            suggestions=suggestions,
            validated_at=datetime.datetime.utcnow().isoformat() + "Z",
        )

    def _make_decision(
        self,
        schema_valid: bool,
        quality_result: QualityEvaluationResult | None,
        contradiction_result: ContradictionCheckResult | None,
        sanity_result: SanityCheckResult | None,
        errors: list[str],
    ) -> ValidationDecision:
        """Make final validation decision."""
        # Schema invalid = reject
        if not schema_valid:
            return ValidationDecision.REJECT

        # Critical contradictions = reject
        if contradiction_result and contradiction_result.severity == "critical":
            return ValidationDecision.REJECT

        # Sanity issues = reject (in strict mode) or review
        if sanity_result and sanity_result.issues:
            if self._config.strict_mode:
                return ValidationDecision.REJECT
            return ValidationDecision.REVIEW

        # Major contradictions = review
        if contradiction_result and contradiction_result.severity == "major":
            return ValidationDecision.REVIEW

        # Quality check
        if quality_result:
            thresholds = self._config.quality_thresholds

            # Below review threshold = reject
            if quality_result.confidence < thresholds.review_confidence:
                return ValidationDecision.REJECT
            if quality_result.completeness < thresholds.review_completeness:
                return ValidationDecision.REJECT

            # Below min threshold but above review = review
            if quality_result.confidence < thresholds.min_confidence:
                return ValidationDecision.REVIEW
            if quality_result.completeness < thresholds.min_completeness:
                return ValidationDecision.REVIEW

            # Quality score check
            if quality_result.score < self._config.review_min_score:
                return ValidationDecision.REJECT
            if quality_result.score < self._config.accept_min_score:
                return ValidationDecision.REVIEW

        # All checks passed
        return ValidationDecision.ACCEPT

    def _generate_suggestions(
        self,
        recipe: dict[str, Any],
        quality_result: QualityEvaluationResult | None,
        sanity_result: SanityCheckResult | None,
    ) -> list[str]:
        """Generate improvement suggestions."""
        suggestions: list[str] = []

        if quality_result:
            if quality_result.confidence < 0.8:
                suggestions.append("Consider adding more confident steps or refining existing ones")
            if quality_result.completeness < 0.8:
                suggestions.append("Add missing descriptions, verification checks, or success criteria")

        if sanity_result:
            if sanity_result.warnings:
                suggestions.append("Review step ordering and dependencies")

        # Check for missing fields
        if not recipe.get("verification_checks"):
            suggestions.append("Add verification checks to improve reliability")

        if not recipe.get("success_criteria"):
            suggestions.append("Define clear success criteria")

        return suggestions

    def _calculate_decision_confidence(
        self,
        decision: ValidationDecision,
        quality_score: float,
        has_contradictions: bool,
        has_sanity_issues: bool,
    ) -> float:
        """Calculate confidence in the validation decision."""
        base_confidence = 0.8

        # Adjust based on quality
        base_confidence *= 0.5 + 0.5 * quality_score

        # Reduce for contradictions
        if has_contradictions:
            base_confidence *= 0.8

        # Reduce for sanity issues
        if has_sanity_issues:
            base_confidence *= 0.9

        # Boost for clear decisions
        if decision == ValidationDecision.ACCEPT:
            base_confidence = min(1.0, base_confidence * 1.1)
        elif decision == ValidationDecision.REJECT:
            base_confidence = min(1.0, base_confidence * 1.05)

        return min(1.0, max(0.0, base_confidence))

    def update_existing_recipes(self, recipes: list[dict[str, Any]]) -> None:
        """Update the existing recipes for contradiction detection."""
        self._contradiction_detector.set_existing_recipes(recipes)

    def add_existing_recipe(self, recipe: dict[str, Any]) -> None:
        """Add a recipe to the existing knowledge base."""
        self._contradiction_detector.add_existing_recipe(recipe)


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


def validate_recipe(
    recipe: dict[str, Any],
    existing_recipes: list[dict[str, Any]] | None = None,
    config: ValidationConfig | None = None,
) -> ValidationResult:
    """Validate a single recipe.

    Args:
        recipe: Recipe to validate
        existing_recipes: Optional existing recipes for contradiction detection
        config: Optional validation configuration

    Returns:
        ValidationResult
    """
    pipeline = ValidationPipeline(config=config, existing_recipes=existing_recipes)
    return pipeline.validate(recipe)


def validate_recipes_batch(
    recipes: list[dict[str, Any]],
    config: ValidationConfig | None = None,
) -> list[ValidationResult]:
    """Validate multiple recipes.

    Args:
        recipes: Recipes to validate
        config: Optional validation configuration

    Returns:
        List of ValidationResults
    """
    pipeline = ValidationPipeline(config=config)

    results: list[ValidationResult] = []
    for recipe in recipes:
        result = pipeline.validate(recipe)
        results.append(result)

        # Add to existing for contradiction detection
        if result.decision == ValidationDecision.ACCEPT:
            pipeline.add_existing_recipe(recipe)

    return results


# =============================================================================
# KNOWLEDGE STORE INTEGRATION
# =============================================================================

# Import knowledge store after all types are defined to avoid circular import
from app.validation.knowledge_store import (
    KnowledgeStoreWithValidation,
    ValidatedKnowledge,
    KnowledgeStoreConfig,
    create_validated_store,
)


__all__ = [
    # Result types
    "ValidationDecision",
    "ValidationResult",
    "SchemaValidationResult",
    "QualityEvaluationResult",
    "ContradictionCheckResult",
    "SanityCheckResult",
    # Validators
    "SchemaValidator",
    "QualityGate",
    "ContradictionDetector",
    "SanityChecker",
    "ValidationPipeline",
    # Configuration
    "ValidationConfig",
    "QualityThresholds",
    # Convenience functions
    "validate_recipe",
    "validate_recipes_batch",
    # Knowledge Store Integration
    "KnowledgeStoreWithValidation",
    "ValidatedKnowledge",
    "KnowledgeStoreConfig",
    "create_validated_store",
]