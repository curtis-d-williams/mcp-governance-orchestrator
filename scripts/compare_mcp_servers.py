# SPDX-License-Identifier: MIT
"""Deterministic MCP server comparison CLI.

Compares a generated MCP server repository against a reference MCP server
repository and emits structured evaluation signals focused on capability
completeness rather than code similarity.

Current comparison dimensions:
- tool surface
- basic structure fields from manifest.json
- test surface

Usage:
    python3 scripts/compare_mcp_servers.py \
        --generated PATH \
        --reference PATH

Optional:
    --output PATH   Write comparison JSON to this path (default: stdout only).
"""

import argparse
import json
from pathlib import Path


def _load_manifest(repo_root):
    """Load manifest.json from a repo root."""
    repo_root = Path(repo_root)
    manifest_path = repo_root / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest.json not found: {manifest_path}")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _normalize_tools(manifest):
    """Return a deterministically sorted tool list."""
    tools = manifest.get("tools", [])
    return sorted(str(tool) for tool in tools)


def _compare_tool_surface(generated_manifest, reference_manifest):
    """Compare tool lists between generated and reference manifests."""
    generated_tools = set(_normalize_tools(generated_manifest))
    reference_tools = set(_normalize_tools(reference_manifest))

    matching_tools = sorted(generated_tools & reference_tools)
    missing_tools = sorted(reference_tools - generated_tools)
    extra_tools = sorted(generated_tools - reference_tools)

    reference_count = len(reference_tools)
    coverage_ratio = (
        len(matching_tools) / reference_count if reference_count else 1.0
    )

    return {
        "generated_tools": sorted(generated_tools),
        "reference_tools": sorted(reference_tools),
        "matching_tools": matching_tools,
        "missing_tools": missing_tools,
        "extra_tools": extra_tools,
        "generated_tool_count": len(generated_tools),
        "reference_tool_count": len(reference_tools),
        "matching_tool_count": len(matching_tools),
        "coverage_ratio": coverage_ratio,
    }


def _compare_structure(generated_manifest, reference_manifest):
    """Compare selected structural manifest fields."""
    generated_protocol = generated_manifest.get("protocol")
    reference_protocol = reference_manifest.get("protocol")

    generated_capability = generated_manifest.get("capability")
    reference_capability = reference_manifest.get("capability")

    return {
        "generated_protocol": generated_protocol,
        "reference_protocol": reference_protocol,
        "protocol_match": generated_protocol == reference_protocol,
        "generated_capability": generated_capability,
        "reference_capability": reference_capability,
        "capability_match": generated_capability == reference_capability,
    }


def _collect_test_surface(repo_root):
    """Collect deterministic test surface signals from a repo root."""
    repo_root = Path(repo_root)
    tests_dir = repo_root / "tests"
    test_files = []
    if tests_dir.exists() and tests_dir.is_dir():
        test_files = sorted(
            str(path.relative_to(repo_root))
            for path in tests_dir.rglob("test_*.py")
            if path.is_file()
        )

    return {
        "has_tests": bool(test_files),
        "test_file_count": len(test_files),
        "test_files": test_files,
    }


def compare_mcp_servers(generated_path, reference_path, output_path=None):
    """Compare two MCP server repo roots and return a structured report."""
    generated_root = Path(generated_path)
    reference_root = Path(reference_path)

    generated_manifest = _load_manifest(generated_root)
    reference_manifest = _load_manifest(reference_root)

    result = {
        "generated": str(generated_root),
        "reference": str(reference_root),
        "tool_surface": _compare_tool_surface(
            generated_manifest, reference_manifest
        ),
        "structure": _compare_structure(
            generated_manifest, reference_manifest
        ),
        "testability": {
            "generated": _collect_test_surface(generated_root),
            "reference": _collect_test_surface(reference_root),
        },
    }

    serialized = json.dumps(result, indent=2) + "\n"

    if output_path is not None:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(serialized, encoding="utf-8")
    else:
        print(serialized, end="")

    return result


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Compare a generated MCP server against a reference MCP server.",
        add_help=True,
    )
    parser.add_argument(
        "--generated",
        required=True,
        metavar="PATH",
        help="Path to generated MCP server repository root.",
    )
    parser.add_argument(
        "--reference",
        required=True,
        metavar="PATH",
        help="Path to reference MCP server repository root.",
    )
    parser.add_argument(
        "--output",
        default=None,
        metavar="FILE",
        help="Write comparison JSON to this path. Omit to print to stdout only.",
    )
    args = parser.parse_args(argv)

    compare_mcp_servers(
        generated_path=args.generated,
        reference_path=args.reference,
        output_path=args.output,
    )


if __name__ == "__main__":
    main()
