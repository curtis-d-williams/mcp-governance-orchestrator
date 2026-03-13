# SPDX-License-Identifier: MIT
"""Deterministic capability-gap derivation from MCP comparison output.

Reads a comparison artifact produced by scripts/compare_mcp_servers.py and
emits a normalized capability_gaps payload suitable for later
portfolio_state integration.

Design constraints:
- deterministic
- transparent severity scoring
- analysis only
- no planner/runtime integration here
"""

import argparse
import json
from pathlib import Path


def _load_json(path):
    """Load JSON from a filesystem path."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _clamp_ratio(value):
    """Clamp a numeric ratio into [0.0, 1.0]."""
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, numeric))


def _derive_severity(
    *,
    tool_coverage_ratio,
    capability_coverage_ratio,
    testability_coverage_ratio,
):
    """Return deterministic severity from comparison coverage ratios.

    First-pass transparent weighting:
    - 50% missing tool ratio
    - 30% missing capability ratio
    - 20% missing testability ratio
    """
    missing_tool_ratio = 1.0 - _clamp_ratio(tool_coverage_ratio)
    missing_capability_ratio = 1.0 - _clamp_ratio(capability_coverage_ratio)
    missing_testability_ratio = 1.0 - _clamp_ratio(testability_coverage_ratio)

    severity = (
        0.5 * missing_tool_ratio
        + 0.3 * missing_capability_ratio
        + 0.2 * missing_testability_ratio
    )
    return round(severity, 2)


def derive_capability_gaps_from_comparison(comparison):
    """Convert a comparison artifact into normalized capability gap records."""
    if not isinstance(comparison, dict):
        return {"capability_gaps": []}

    structure = comparison.get("structure", {})
    tool_surface = comparison.get("tool_surface", {})
    capability_surface = comparison.get("capability_surface", {})
    testability = comparison.get("testability", {})

    capability = structure.get("generated_capability")
    if not isinstance(capability, str) or not capability:
        return {"capability_gaps": []}

    tool_coverage_ratio = _clamp_ratio(tool_surface.get("coverage_ratio", 0.0))
    capability_coverage_ratio = _clamp_ratio(
        capability_surface.get("coverage_ratio", 0.0)
    )
    testability_coverage_ratio = _clamp_ratio(
        testability.get("coverage_ratio", 0.0)
    )

    missing_tools = sorted(
        str(tool)
        for tool in tool_surface.get("missing_tools", [])
        if isinstance(tool, str) and tool
    )
    missing_enabled_capabilities = sorted(
        str(item)
        for item in capability_surface.get("missing_enabled", [])
        if isinstance(item, str) and item
    )

    severity = _derive_severity(
        tool_coverage_ratio=tool_coverage_ratio,
        capability_coverage_ratio=capability_coverage_ratio,
        testability_coverage_ratio=testability_coverage_ratio,
    )

    return {
        "capability_gaps": [
            {
                "capability": capability,
                "gap_source": "reference_mcp_comparison",
                "severity": severity,
                "missing_tools": missing_tools,
                "missing_tool_count": len(missing_tools),
                "tool_coverage_ratio": tool_coverage_ratio,
                "missing_enabled_capabilities": missing_enabled_capabilities,
                "missing_enabled_capability_count": len(
                    missing_enabled_capabilities
                ),
                "capability_coverage_ratio": capability_coverage_ratio,
                "testability_coverage_ratio": testability_coverage_ratio,
            }
        ]
    }


def update_capability_gaps_from_mcp_comparison(comparison_path, output_path=None):
    """Read comparison JSON and emit deterministic capability gap JSON."""
    comparison = _load_json(comparison_path)
    result = derive_capability_gaps_from_comparison(comparison)
    serialized = json.dumps(result, indent=2) + "\n"

    if output_path is not None:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(serialized, encoding="utf-8")
    else:
        print(serialized, end="")

    return result


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Derive capability gap signals from MCP comparison output.",
        add_help=True,
    )
    parser.add_argument(
        "--comparison",
        required=True,
        metavar="FILE",
        help="Path to comparison JSON produced by compare_mcp_servers.py.",
    )
    parser.add_argument(
        "--output",
        default=None,
        metavar="FILE",
        help="Write derived capability gap JSON to this path. Omit to print to stdout only.",
    )
    args = parser.parse_args(argv)

    update_capability_gaps_from_mcp_comparison(
        comparison_path=args.comparison,
        output_path=args.output,
    )


if __name__ == "__main__":
    main()
