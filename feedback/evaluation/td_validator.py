"""TouchDesigner Output Validator - Validate TD network output.

Validates generated TouchDesigner networks, operators, and Python code.
"""

from __future__ import annotations

import ast
import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class TDValidation:
    """Result of TouchDesigner output validation."""

    valid: bool
    operator_graph_valid: bool = False
    connections_valid: bool = False
    parameters_valid: bool = False

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    operator_count: int = 0
    valid_operator_types: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "operator_graph_valid": self.operator_graph_valid,
            "connections_valid": self.connections_valid,
            "parameters_valid": self.parameters_valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "operator_count": self.operator_count,
            "valid_operator_types": self.valid_operator_types,
        }


# Known TouchDesigner operator types by family
KNOWN_TD_OPERATORS = {
    # TOP (Texture Operators)
    "moviefilein", "null", "out", "level", "blur", "composite", "math",
    "noise", "ramp", "feedback", "delay", "select", "merge", "switch",
    "transform", "resolution", "crop", "flip", "swap", "over", "under",
    "multiply", "add", "subtract", "divide", "abs", "cliff", "invert",
    "threshold", "limit", "lookup", "hsb", "rgb", "monochrome",

    # CHOP (Channel Operators)
    "mathchop", "noisec", "filter", "lag", "speed", "timer", "trigger",
    "sequence", "logic", "switchchop", "selectchop", "mergechop",
    "analyze", "count", "hold", "cross", "interpolate", "stretch",

    # SOP (Surface Operators)
    "gridsop", "boxsop", "spheresop", "tubesop", "nullsop", "mergesop",
    "transformsop", "wranglesop", "attribcreatesop", "scattersop",
    "copystamp", "copytopointssop", "polysop", "linesop",

    # DAT (Data Operators)
    "table", "text", "selectdat", "mergedat", "switchdat", "evaluate",
    "script", "execute", "webclient", "websocket", "udpin", "udpout",

    # COMP (Components)
    "container", "base", "panel", "slider", "button", "field", "kbinput",
}


class TDValidator:
    """Validate TouchDesigner output.

    Usage:
        validator = TDValidator()
        result = validator.validate(output_dict)
    """

    def __init__(
        self,
        bridge_url: str = "http://127.0.0.1:9988",
    ) -> None:
        """Initialize TD validator.

        Args:
            bridge_url: URL for TouchDesigner bridge
        """
        self.bridge_url = bridge_url

    def validate(
        self,
        output: dict[str, Any],
        expected: dict[str, Any] | None = None,
    ) -> TDValidation:
        """Validate TouchDesigner output.

        Args:
            output: Generated TD output
            expected: Optional expected output

        Returns:
            TDValidation with results
        """
        result = TDValidation(valid=True)

        # Validate operators
        operators = output.get("operators", [])
        if operators:
            result.operator_graph_valid = self._validate_operators(operators, result)

        # Validate connections
        connections = output.get("connections", [])
        if connections:
            result.connections_valid = self._validate_connections(connections, operators, result)

        # Validate parameters
        parameters = output.get("parameters", {})
        if parameters:
            result.parameters_valid = self._validate_parameters(parameters, result)

        # Validate Python code
        code = output.get("code", "")
        if code:
            self._validate_python(code, result)

        # Overall validity
        result.valid = (
            result.operator_graph_valid
            and result.connections_valid
        )

        return result

    def _validate_operators(
        self,
        operators: list[dict[str, Any]],
        result: TDValidation,
    ) -> bool:
        """Validate operator structure."""
        result.operator_count = len(operators)
        valid_count = 0

        for op in operators:
            op_type = op.get("type", "").lower()
            op_name = op.get("name", f"op_{valid_count}")

            if not op_type:
                result.errors.append(f"Operator '{op_name}' missing type")
                continue

            # Normalize type (remove family suffix)
            base_type = op_type.rstrip("chop").rstrip("sop").rstrip("top").rstrip("dat")

            if base_type in KNOWN_TD_OPERATORS or op_type in KNOWN_TD_OPERATORS:
                valid_count += 1
                if op_type not in result.valid_operator_types:
                    result.valid_operator_types.append(op_type)
            else:
                result.warnings.append(f"Unknown operator type: {op_type}")
                valid_count += 1  # Still count as valid

        return valid_count == len(operators)

    def _validate_connections(
        self,
        connections: list[dict[str, Any]],
        operators: list[dict[str, Any]],
        result: TDValidation,
    ) -> bool:
        """Validate operator connections."""
        if not connections:
            return True

        op_names = {op.get("name", "") for op in operators}
        valid_count = 0

        for conn in connections:
            source = conn.get("source", "")
            target = conn.get("target", "")

            if not source or not target:
                result.errors.append("Connection missing source or target")
                continue

            if source in op_names and target in op_names:
                valid_count += 1
            else:
                result.warnings.append(f"Connection references unknown operator")

        return valid_count == len(connections)

    def _validate_parameters(
        self,
        parameters: dict[str, Any],
        result: TDValidation,
    ) -> bool:
        """Validate parameter values."""
        valid_count = 0

        for param_name, param_value in parameters.items():
            if param_value is None:
                result.warnings.append(f"Parameter '{param_name}' is None")
                continue
            valid_count += 1

        return valid_count == len(parameters)

    def _validate_python(
        self,
        code: str,
        result: TDValidation,
    ) -> None:
        """Validate Python code syntax."""
        if not code:
            return

        try:
            ast.parse(code)
        except SyntaxError as e:
            result.errors.append(f"Python syntax error: {e}")


def validate_td_output(
    output: dict[str, Any],
) -> TDValidation:
    """Convenience function for TD validation."""
    validator = TDValidator()
    return validator.validate(output)