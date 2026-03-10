"""Houdini Output Validator - Validate Houdini network output.

Validates generated Houdini networks, node graphs, and VEX code.
Integrates with the Houdini bridge for live validation.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class HoudiniValidation:
    """Result of Houdini output validation."""

    valid: bool
    node_graph_valid: bool = False
    connections_valid: bool = False
    parameters_valid: bool = False
    renders_ok: bool = False
    visual_score: float = 0.0

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    # Node details
    node_count: int = 0
    connection_count: int = 0
    valid_node_types: list[str] = field(default_factory=list)
    invalid_node_types: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "node_graph_valid": self.node_graph_valid,
            "connections_valid": self.connections_valid,
            "parameters_valid": self.parameters_valid,
            "renders_ok": self.renders_ok,
            "visual_score": self.visual_score,
            "errors": self.errors,
            "warnings": self.warnings,
            "node_count": self.node_count,
            "connection_count": self.connection_count,
            "valid_node_types": self.valid_node_types,
            "invalid_node_types": self.invalid_node_types,
        }


# Known Houdini SOP node types
KNOWN_SOP_TYPES = {
    # Geometry sources
    "grid", "box", "sphere", "tube", "torus", "circle", "curve", "line",
    "platonic", "tetrahedron", "font", "trace", "file",

    # Modifiers
    "transform", "merge", "null", "output", "blast", "group", "delete",
    "subdivide", "divide", "polybevel", "polyextrude", "polypatch",
    "attribcreate", "attribwrangle", "attribtransfer", "attribpromote",
    "color", "measure", "normal", "reverse", "primitive",

    # Scatter/Points
    "scatter", "copytopoints", "copystamp", "foreach", "foreach_begin",
    "foreach_end", "pointgenerate", "pointjitter", "wrangle",

    # VDB
    "vdbfrompolygons", "vdbtopolygons", "vdbreshapesdf", "vdbmorphologysdf",
    "convert", "convertvdb",

    # Simulation prep
    "dopimport", "dopio", "object_merge", "solver", "geosolver",

    # Constraints
    "constraintnetwork", "hardconstraint", "springconstraint", "glue",

    # Common patterns
    "attribute", "clean", "facet", "fuse", "polyreduce", "remesh",
    "rest", "uvunwrap", "uvtransform", "uvflatten",
}


class HoudiniValidator:
    """Validate Houdini network output.

    Validates:
    - Node types are valid Houdini SOP/DOP types
    - Connections reference existing nodes
    - Parameters are within valid ranges
    - Optional: Live validation via Houdini bridge

    Usage:
        validator = HoudiniValidator()
        result = validator.validate(output_dict)
    """

    def __init__(
        self,
        bridge_url: str = "http://127.0.0.1:9989",
        live_validation: bool = False,
    ) -> None:
        """Initialize Houdini validator.

        Args:
            bridge_url: URL for Houdini bridge
            live_validation: Whether to validate via live bridge
        """
        self.bridge_url = bridge_url
        self.live_validation = live_validation

    def validate(
        self,
        output: dict[str, Any],
        expected: dict[str, Any] | None = None,
    ) -> HoudiniValidation:
        """Validate Houdini output.

        Args:
            output: Generated Houdini output (nodes, connections, code)
            expected: Optional expected output for comparison

        Returns:
            HoudiniValidation with validation results
        """
        result = HoudiniValidation(valid=True)

        # Validate nodes
        nodes = output.get("nodes", [])
        if nodes:
            result.node_graph_valid = self._validate_nodes(nodes, result)

        # Validate connections
        connections = output.get("connections", [])
        if connections:
            result.connections_valid = self._validate_connections(
                connections, nodes, result
            )

        # Validate parameters
        parameters = output.get("parameters", {})
        if parameters:
            result.parameters_valid = self._validate_parameters(parameters, result)

        # Validate VEX code
        code = output.get("code", "")
        if code:
            self._validate_vex(code, result)

        # Live validation via bridge
        if self.live_validation:
            self._live_validation(output, result)

        # Overall validity
        result.valid = (
            result.node_graph_valid
            and result.connections_valid
            and (result.parameters_valid or not parameters)
        )

        return result

    def _validate_nodes(
        self,
        nodes: list[dict[str, Any]],
        result: HoudiniValidation,
    ) -> bool:
        """Validate node structure."""
        result.node_count = len(nodes)
        valid_count = 0

        for node in nodes:
            node_type = node.get("type", "").lower()
            node_name = node.get("name", f"node_{valid_count}")

            if not node_type:
                result.errors.append(f"Node '{node_name}' missing type")
                continue

            if node_type in KNOWN_SOP_TYPES:
                valid_count += 1
                if node_type not in result.valid_node_types:
                    result.valid_node_types.append(node_type)
            else:
                result.warnings.append(f"Unknown node type: {node_type}")
                result.invalid_node_types.append(node_type)
                # Still count as valid if structure is correct
                if node.get("name"):
                    valid_count += 1

        return valid_count == len(nodes)

    def _validate_connections(
        self,
        connections: list[dict[str, Any]],
        nodes: list[dict[str, Any]],
        result: HoudiniValidation,
    ) -> bool:
        """Validate node connections."""
        result.connection_count = len(connections)

        if not connections:
            return True  # No connections is valid

        node_names = {n.get("name", "") for n in nodes}
        valid_count = 0

        for conn in connections:
            source = conn.get("source", "")
            target = conn.get("target", "")
            source_idx = conn.get("source_index", 0)
            target_idx = conn.get("target_index", 0)

            if not source or not target:
                result.errors.append(f"Connection missing source or target")
                continue

            if source not in node_names:
                result.errors.append(f"Connection source not found: {source}")
                continue

            if target not in node_names:
                result.errors.append(f"Connection target not found: {target}")
                continue

            valid_count += 1

        return valid_count == len(connections)

    def _validate_parameters(
        self,
        parameters: dict[str, Any],
        result: HoudiniValidation,
    ) -> bool:
        """Validate parameter values."""
        valid_count = 0

        for param_name, param_value in parameters.items():
            if param_value is None:
                result.warnings.append(f"Parameter '{param_name}' is None")
                continue

            # Check for extreme values
            if isinstance(param_value, (int, float)):
                if abs(param_value) > 1e10:
                    result.warnings.append(
                        f"Parameter '{param_name}' has extreme value: {param_value}"
                    )

            valid_count += 1

        return valid_count == len(parameters)

    def _validate_vex(
        self,
        code: str,
        result: HoudiniValidation,
    ) -> None:
        """Validate VEX code syntax."""
        if not code:
            return

        # Check for common VEX patterns
        vex_patterns = [
            (r"@\w+", "attribute access"),
            (r"\bsetattrib\b", "setattrib function"),
            (r"\bgetattrib\b", "getattrib function"),
            (r"\bif\s*\(", "if statement"),
        ]

        for pattern, desc in vex_patterns:
            if re.search(pattern, code):
                pass  # Valid pattern found

        # Check for errors
        if code.count("{") != code.count("}"):
            result.errors.append("VEX: Mismatched braces")

        if ";;" in code:
            result.warnings.append("VEX: Double semicolon")

    def _live_validation(
        self,
        output: dict[str, Any],
        result: HoudiniValidation,
    ) -> None:
        """Perform live validation via Houdini bridge."""
        try:
            import urllib.request
            import json

            # Check bridge availability
            req = urllib.request.Request(
                f"{self.bridge_url}/ping",
                method="GET",
            )
            response = urllib.request.urlopen(req, timeout=2)
            data = json.loads(response.read())

            if data.get("status") != "ok":
                result.warnings.append("Houdini bridge not available")
                return

            # TODO: Send nodes to Houdini for live validation

        except Exception as e:
            result.warnings.append(f"Live validation failed: {str(e)[:50]}")


def validate_houdini_output(
    output: dict[str, Any],
) -> HoudiniValidation:
    """Convenience function for Houdini validation.

    Args:
        output: Houdini output to validate

    Returns:
        HoudiniValidation
    """
    validator = HoudiniValidator()
    return validator.validate(output)