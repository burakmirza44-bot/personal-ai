"""Output Evaluator - Evaluate inference output quality.

Evaluates generated output (code, recipes, actions) against expected
results and returns a quality score. Part of the feedback loop.

Supports:
- Houdini validation (node graph, render output)
- TouchDesigner validation (network, output)
- Code quality (VEX, Python)
- Visual similarity (reference comparison)
"""

from __future__ import annotations

import ast
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)

DomainType = Literal["houdini", "touchdesigner", "generic"]
QualityTier = Literal["excellent", "good", "acceptable", "poor", "failed"]


@dataclass(slots=True)
class EvaluationConfig:
    """Configuration for output evaluation."""

    # Thresholds
    excellent_threshold: float = 0.9
    good_threshold: float = 0.75
    acceptable_threshold: float = 0.5
    poor_threshold: float = 0.3

    # Weights for combined score
    node_graph_weight: float = 0.30
    connections_weight: float = 0.25
    parameters_weight: float = 0.15
    render_weight: float = 0.15
    code_quality_weight: float = 0.10
    visual_similarity_weight: float = 0.05

    # Safety
    fail_on_safety_violation: bool = True
    max_retry_drift: float = 0.25


@dataclass(slots=True)
class EvaluationResult:
    """Result of output evaluation."""

    success: bool
    overall_score: float
    quality_tier: QualityTier

    # Component scores
    node_graph_score: float = 0.0
    connections_score: float = 0.0
    parameters_score: float = 0.0
    render_score: float = 0.0
    code_quality_score: float = 0.0
    visual_similarity_score: float = 0.0

    # Details
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)

    # Metadata
    domain: DomainType = "generic"
    evaluation_time_seconds: float = 0.0
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "overall_score": self.overall_score,
            "quality_tier": self.quality_tier,
            "node_graph_score": self.node_graph_score,
            "connections_score": self.connections_score,
            "parameters_score": self.parameters_score,
            "render_score": self.render_score,
            "code_quality_score": self.code_quality_score,
            "visual_similarity_score": self.visual_similarity_score,
            "errors": self.errors,
            "warnings": self.warnings,
            "suggestions": self.suggestions,
            "domain": self.domain,
            "evaluation_time_seconds": self.evaluation_time_seconds,
            "error": self.error,
        }


class OutputEvaluator:
    """Evaluate inference output quality.

    Provides comprehensive evaluation of generated output:
    - Node graph structure validity
    - Connection correctness
    - Parameter range validation
    - Render output quality
    - Code quality analysis
    - Visual similarity (when reference available)

    Usage:
        evaluator = OutputEvaluator(domain="houdini")
        result = evaluator.evaluate(output, expected)
    """

    def __init__(
        self,
        domain: DomainType = "generic",
        config: EvaluationConfig | None = None,
    ) -> None:
        """Initialize evaluator.

        Args:
            domain: Domain for evaluation (houdini, touchdesigner, generic)
            config: Optional evaluation configuration
        """
        self.domain = domain
        self.config = config or EvaluationConfig()

    def evaluate(
        self,
        output: dict[str, Any],
        expected: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> EvaluationResult:
        """Evaluate output against expected results.

        Args:
            output: Generated output to evaluate
            expected: Expected output (if available)
            context: Additional context (task info, etc.)

        Returns:
            EvaluationResult with scores and details
        """
        import time
        start = time.monotonic()

        result = EvaluationResult(
            success=False,
            overall_score=0.0,
            quality_tier="failed",
            domain=self.domain,
        )

        try:
            # Domain-specific evaluation
            if self.domain == "houdini":
                result = self._evaluate_houdini(output, expected, context)
            elif self.domain == "touchdesigner":
                result = self._evaluate_touchdesigner(output, expected, context)
            else:
                result = self._evaluate_generic(output, expected, context)

            # Calculate overall score
            result.overall_score = self._calculate_weighted_score(result)

            # Determine quality tier
            result.quality_tier = self._determine_quality_tier(result.overall_score)

            # Determine success
            result.success = (
                result.overall_score >= self.config.acceptable_threshold
                and len(result.errors) == 0
            )

        except Exception as e:
            result.error = str(e)
            result.quality_tier = "failed"

        result.evaluation_time_seconds = time.monotonic() - start
        result.domain = self.domain

        return result

    def _evaluate_houdini(
        self,
        output: dict[str, Any],
        expected: dict[str, Any] | None,
        context: dict[str, Any] | None,
    ) -> EvaluationResult:
        """Evaluate Houdini-specific output."""
        result = EvaluationResult(
            success=False,
            overall_score=0.0,
            quality_tier="failed",
            domain="houdini",
        )

        # Node graph validation
        nodes = output.get("nodes", [])
        if nodes:
            result.node_graph_score = self._validate_houdini_nodes(nodes, result)

        # Connections validation
        connections = output.get("connections", [])
        if connections:
            result.connections_score = self._validate_connections(connections, nodes, result)

        # Parameters validation
        parameters = output.get("parameters", {})
        if parameters:
            result.parameters_score = self._validate_parameters(parameters, result)

        # Code quality (VEX)
        code = output.get("code", "")
        if code:
            result.code_quality_score = self._validate_vex_code(code, result)

        # Render output (if available)
        render_output = output.get("render_output")
        if render_output:
            result.render_score = self._validate_render_output(render_output, result)

        return result

    def _evaluate_touchdesigner(
        self,
        output: dict[str, Any],
        expected: dict[str, Any] | None,
        context: dict[str, Any] | None,
    ) -> EvaluationResult:
        """Evaluate TouchDesigner-specific output."""
        result = EvaluationResult(
            success=False,
            overall_score=0.0,
            quality_tier="failed",
            domain="touchdesigner",
        )

        # Operator network validation
        operators = output.get("operators", [])
        if operators:
            result.node_graph_score = self._validate_td_operators(operators, result)

        # Connections validation
        connections = output.get("connections", [])
        if connections:
            result.connections_score = self._validate_td_connections(connections, operators, result)

        # Parameters validation
        parameters = output.get("parameters", {})
        if parameters:
            result.parameters_score = self._validate_td_parameters(parameters, result)

        # Code quality (Python)
        code = output.get("code", "")
        if code:
            result.code_quality_score = self._validate_python_code(code, result)

        return result

    def _evaluate_generic(
        self,
        output: dict[str, Any],
        expected: dict[str, Any] | None,
        context: dict[str, Any] | None,
    ) -> EvaluationResult:
        """Evaluate generic output."""
        result = EvaluationResult(
            success=False,
            overall_score=0.0,
            quality_tier="failed",
            domain="generic",
        )

        # Basic structure validation
        if output:
            result.node_graph_score = 0.7  # Basic pass for having output

        # Code validation
        code = output.get("code", "")
        if code:
            result.code_quality_score = self._validate_generic_code(code, result)

        # Compare with expected if available
        if expected:
            similarity = self._calculate_output_similarity(output, expected)
            result.visual_similarity_score = similarity

        return result

    def _validate_houdini_nodes(
        self,
        nodes: list[dict[str, Any]],
        result: EvaluationResult,
    ) -> float:
        """Validate Houdini node structure."""
        if not nodes:
            result.warnings.append("No nodes in output")
            return 0.0

        valid_count = 0
        known_sop_types = {
            "grid", "box", "sphere", "tube", "scatter", "copytopoints",
            "transform", "merge", "null", "attribwrangle", "attribcreate",
            "group", "blast", "polybevel", "vdbfrompolygons", "convert",
        }

        for node in nodes:
            node_type = node.get("type", "").lower()
            node_name = node.get("name", "")

            if not node_type:
                result.errors.append(f"Node missing type: {node_name}")
                continue

            if node_type in known_sop_types:
                valid_count += 1
            else:
                result.warnings.append(f"Unknown node type: {node_type}")

        return min(1.0, valid_count / max(1, len(nodes)))

    def _validate_td_operators(
        self,
        operators: list[dict[str, Any]],
        result: EvaluationResult,
    ) -> float:
        """Validate TouchDesigner operators."""
        if not operators:
            result.warnings.append("No operators in output")
            return 0.0

        valid_count = 0
        known_types = {
            "moviefilein", "null", "out", "level", "blur", "composite",
            "math", "noise", "ramp", "feedback", "delay", "select",
        }

        for op in operators:
            op_type = op.get("type", "").lower()
            op_name = op.get("name", "")

            if not op_type:
                result.errors.append(f"Operator missing type: {op_name}")
                continue

            if op_type in known_types:
                valid_count += 1
            else:
                result.warnings.append(f"Unknown operator type: {op_type}")

        return min(1.0, valid_count / max(1, len(operators)))

    def _validate_connections(
        self,
        connections: list[dict[str, Any]],
        nodes: list[dict[str, Any]],
        result: EvaluationResult,
    ) -> float:
        """Validate node connections."""
        if not connections:
            return 1.0  # No connections is valid

        node_names = {n.get("name", "") for n in nodes}
        valid_count = 0

        for conn in connections:
            source = conn.get("source", "")
            target = conn.get("target", "")

            if not source or not target:
                result.errors.append(f"Invalid connection: missing source or target")
                continue

            if source in node_names and target in node_names:
                valid_count += 1
            else:
                result.warnings.append(f"Connection references unknown node: {source} -> {target}")

        return min(1.0, valid_count / max(1, len(connections)))

    def _validate_td_connections(
        self,
        connections: list[dict[str, Any]],
        operators: list[dict[str, Any]],
        result: EvaluationResult,
    ) -> float:
        """Validate TouchDesigner connections."""
        return self._validate_connections(connections, operators, result)

    def _validate_parameters(
        self,
        parameters: dict[str, Any],
        result: EvaluationResult,
    ) -> float:
        """Validate parameter values."""
        if not parameters:
            return 1.0

        valid_count = 0

        for param_name, param_value in parameters.items():
            if param_value is None:
                result.warnings.append(f"Parameter {param_name} is None")
                continue

            # Check for obviously invalid values
            if isinstance(param_value, (int, float)):
                if param_value < -1e10 or param_value > 1e10:
                    result.warnings.append(f"Parameter {param_name} has extreme value: {param_value}")
                    continue

            valid_count += 1

        return min(1.0, valid_count / max(1, len(parameters)))

    def _validate_td_parameters(
        self,
        parameters: dict[str, Any],
        result: EvaluationResult,
    ) -> float:
        """Validate TouchDesigner parameters."""
        return self._validate_parameters(parameters, result)

    def _validate_vex_code(
        self,
        code: str,
        result: EvaluationResult,
    ) -> float:
        """Validate VEX code syntax."""
        if not code:
            return 1.0

        score = 0.5  # Start with base score

        # Check for common VEX patterns
        vex_patterns = [
            r"@\w+",  # Attributes like @P, @N
            r"\b(if|else|for|while|foreach)\b",  # Control flow
            r"\b(setattrib|getattrib|addpoint|addprim)\b",  # Functions
        ]

        for pattern in vex_patterns:
            if re.search(pattern, code):
                score += 0.1

        # Check for syntax errors
        if ";;" in code:
            result.warnings.append("VEX: Double semicolon detected")
            score -= 0.1

        if code.count("{") != code.count("}"):
            result.errors.append("VEX: Mismatched braces")
            score -= 0.3

        return max(0.0, min(1.0, score))

    def _validate_python_code(
        self,
        code: str,
        result: EvaluationResult,
    ) -> float:
        """Validate Python code syntax."""
        if not code:
            return 1.0

        try:
            ast.parse(code)
            return 1.0
        except SyntaxError as e:
            result.errors.append(f"Python syntax error: {e}")
            return 0.3

    def _validate_generic_code(
        self,
        code: str,
        result: EvaluationResult,
    ) -> float:
        """Validate generic code."""
        # Try Python first
        try:
            ast.parse(code)
            return 1.0
        except SyntaxError:
            pass

        # Check basic code structure
        score = 0.5
        if "{" in code and "}" in code:
            score += 0.2
        if "(" in code and ")" in code:
            score += 0.1

        return min(1.0, score)

    def _validate_render_output(
        self,
        render_output: dict[str, Any],
        result: EvaluationResult,
    ) -> float:
        """Validate render output."""
        if not render_output:
            return 0.0

        # Check for render success
        if render_output.get("success"):
            return 1.0

        if render_output.get("error"):
            result.errors.append(f"Render error: {render_output['error']}")
            return 0.0

        return 0.5

    def _calculate_output_similarity(
        self,
        output: dict[str, Any],
        expected: dict[str, Any],
    ) -> float:
        """Calculate similarity between output and expected."""
        if not output or not expected:
            return 0.0

        # Simple key overlap metric
        output_keys = set(output.keys())
        expected_keys = set(expected.keys())

        if not expected_keys:
            return 1.0

        overlap = output_keys & expected_keys
        return len(overlap) / len(expected_keys)

    def _calculate_weighted_score(self, result: EvaluationResult) -> float:
        """Calculate weighted overall score."""
        weights = [
            (result.node_graph_score, self.config.node_graph_weight),
            (result.connections_score, self.config.connections_weight),
            (result.parameters_score, self.config.parameters_weight),
            (result.render_score, self.config.render_weight),
            (result.code_quality_score, self.config.code_quality_weight),
            (result.visual_similarity_score, self.config.visual_similarity_weight),
        ]

        total_weight = sum(w for _, w in weights if _ > 0)
        if total_weight == 0:
            return 0.0

        weighted_sum = sum(score * weight for score, weight in weights if score > 0)
        return weighted_sum / total_weight

    def _determine_quality_tier(self, score: float) -> QualityTier:
        """Determine quality tier from score."""
        if score >= self.config.excellent_threshold:
            return "excellent"
        elif score >= self.config.good_threshold:
            return "good"
        elif score >= self.config.acceptable_threshold:
            return "acceptable"
        elif score >= self.config.poor_threshold:
            return "poor"
        else:
            return "failed"