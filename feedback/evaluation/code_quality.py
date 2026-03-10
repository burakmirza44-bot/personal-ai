"""Code Quality Analyzer - Analyze code quality for VEX and Python.

Provides syntax validation, complexity metrics, and anti-pattern detection.
"""

from __future__ import annotations

import ast
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Literal

logger = logging.getLogger(__name__)

CodeType = Literal["python", "vex", "glsl", "unknown"]


@dataclass(slots=True)
class CodeQualityResult:
    """Result of code quality analysis."""

    valid: bool
    code_type: CodeType = "unknown"

    # Metrics
    line_count: int = 0
    character_count: int = 0
    complexity_score: float = 0.0

    # Issues
    syntax_errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)

    # Quality
    quality_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "code_type": self.code_type,
            "line_count": self.line_count,
            "character_count": self.character_count,
            "complexity_score": self.complexity_score,
            "syntax_errors": self.syntax_errors,
            "warnings": self.warnings,
            "suggestions": self.suggestions,
            "quality_score": self.quality_score,
        }


class CodeQualityAnalyzer:
    """Analyze code quality for various languages.

    Supports:
    - Python: Full AST analysis
    - VEX: Syntax patterns and common issues
    - GLSL: Basic validation
    """

    def __init__(self) -> None:
        """Initialize code quality analyzer."""
        pass

    def analyze(
        self,
        code: str,
        code_type: CodeType | None = None,
    ) -> CodeQualityResult:
        """Analyze code quality.

        Args:
            code: Code to analyze
            code_type: Optional code type (auto-detected if None)

        Returns:
            CodeQualityResult with analysis
        """
        if not code:
            return CodeQualityResult(
                valid=True,
                code_type="unknown",
                quality_score=1.0,
            )

        # Auto-detect code type
        if code_type is None:
            code_type = self._detect_code_type(code)

        result = CodeQualityResult(
            valid=True,
            code_type=code_type,
            line_count=len(code.split("\n")),
            character_count=len(code),
        )

        # Analyze based on type
        if code_type == "python":
            self._analyze_python(code, result)
        elif code_type == "vex":
            self._analyze_vex(code, result)
        else:
            self._analyze_generic(code, result)

        # Calculate quality score
        result.quality_score = self._calculate_quality_score(result)

        return result

    def _detect_code_type(self, code: str) -> CodeType:
        """Detect code type from content."""
        # Python indicators
        if re.search(r"^\s*(import|from|def|class|if __name__)", code, re.MULTILINE):
            return "python"

        # VEX indicators
        if re.search(r"@\w+\s*=", code) or re.search(r"\b(setattrib|getattrib|addpoint|addprim)\s*\(", code):
            return "vex"

        # GLSL indicators
        if re.search(r"\b(vec|mat|sampler|void\s+main|gl_Position)\b", code):
            return "glsl"

        return "unknown"

    def _analyze_python(
        self,
        code: str,
        result: CodeQualityResult,
    ) -> None:
        """Analyze Python code."""
        try:
            tree = ast.parse(code)

            # Count complexity
            complexity = 0
            for node in ast.walk(tree):
                if isinstance(node, (ast.If, ast.While, ast.For, ast.ExceptHandler)):
                    complexity += 1
                elif isinstance(node, ast.FunctionDef):
                    complexity += 2

            result.complexity_score = min(1.0, complexity / 20)

            # Check for issues
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    if len(node.args.args) > 5:
                        result.warnings.append(f"Function '{node.name}' has many arguments")

        except SyntaxError as e:
            result.syntax_errors.append(f"Python syntax error: {e}")
            result.valid = False

    def _analyze_vex(
        self,
        code: str,
        result: CodeQualityResult,
    ) -> None:
        """Analyze VEX code."""
        # Check braces
        if code.count("{") != code.count("}"):
            result.syntax_errors.append("Mismatched braces")
            result.valid = False

        # Check for common issues
        if ";;" in code:
            result.warnings.append("Double semicolon detected")

        if re.search(r"=\s*=", code):
            result.warnings.append("Possible assignment in comparison (use == for comparison)")

        # Calculate complexity
        control_flow = len(re.findall(r"\b(if|else|for|while|foreach)\b", code))
        result.complexity_score = min(1.0, control_flow / 10)

    def _analyze_generic(
        self,
        code: str,
        result: CodeQualityResult,
    ) -> None:
        """Analyze generic code."""
        # Basic structure checks
        if "{" in code and code.count("{") != code.count("}"):
            result.warnings.append("Possible mismatched braces")

        if "(" in code and code.count("(") != code.count(")"):
            result.warnings.append("Possible mismatched parentheses")

        # Complexity estimate
        lines = code.split("\n")
        result.complexity_score = min(1.0, len(lines) / 100)

    def _calculate_quality_score(self, result: CodeQualityResult) -> float:
        """Calculate overall quality score."""
        score = 1.0

        # Penalize syntax errors
        score -= len(result.syntax_errors) * 0.3

        # Penalize warnings
        score -= len(result.warnings) * 0.1

        # Penalize high complexity
        score -= result.complexity_score * 0.1

        return max(0.0, min(1.0, score))


def analyze_code_quality(
    code: str,
    code_type: CodeType | None = None,
) -> CodeQualityResult:
    """Convenience function for code quality analysis."""
    analyzer = CodeQualityAnalyzer()
    return analyzer.analyze(code, code_type)