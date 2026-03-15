# SPDX-License-Identifier: MIT
"""Deterministic MCP server comparison CLI.

Compares a generated MCP server repository against a normalized reference MCP
implementation and emits structured evaluation signals focused on capability
completeness rather than code similarity.

Current comparison dimensions:
- tool surface
- structure
- capability surface
- testability

Usage:
    python3 scripts/compare_mcp_servers.py \
        --generated PATH \
        --reference PATH

Optional:
    --output PATH   Write comparison JSON to this path (default: stdout only).
"""

import argparse
import json
import sys
from pathlib import Path

# Ensure repo root is on sys.path for `from scripts.*` imports.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.inspect_reference_mcp import inspect_reference_mcp


def _load_manifest(repo_root):
    """Load manifest.json from a repo root."""
    repo_root = Path(repo_root)
    manifest_path = repo_root / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest.json not found: {manifest_path}")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _normalize_generated_tools(manifest):
    """Return a deterministically sorted generated tool list."""
    tools = manifest.get("tools", [])
    return sorted(str(tool) for tool in tools)


def _collect_generated_test_surface(repo_root):
    """Collect deterministic test surface signals from a generated repo root."""
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




def _compare_toolsets(reference_inspection):
    """Compare reference toolset surface (generated MCPs currently expose none)."""
    tooling = reference_inspection.get("tooling", {})

    reference_toolsets = sorted(
        set(tooling.get("registered_toolsets", []))
        | set(tooling.get("remote_only_toolsets", []))
    )

    default_toolsets = sorted(tooling.get("default_toolsets", []))
    remote_only_toolsets = sorted(tooling.get("remote_only_toolsets", []))

    matching_toolsets = []  # generated MCP servers do not currently expose toolsets
    missing_toolsets = reference_toolsets

    reference_count = len(reference_toolsets)
    coverage_ratio = 0.0 if reference_count else 1.0

    return {
        "reference_toolsets": reference_toolsets,
        "default_toolsets": default_toolsets,
        "remote_only_toolsets": remote_only_toolsets,
        "matching_toolsets": matching_toolsets,
        "missing_toolsets": missing_toolsets,
        "coverage_ratio": coverage_ratio,
    }


def _compare_tool_surface(generated_manifest, reference_inspection):
    """Compare generated tool list against documented reference tools."""
    generated_tools = set(_normalize_generated_tools(generated_manifest))
    reference_tools = set(reference_inspection["tooling"]["documented_tools"])

    matching_tools = sorted(generated_tools & reference_tools)
    missing_tools = sorted(reference_tools - generated_tools)
    extra_tools = sorted(generated_tools - reference_tools)

    

    # --- shared tool structural evidence ---
    reference_tooling = reference_inspection.get("tooling", {})
    normalized_registered = set(reference_tooling.get("normalized_registered_tools", []))
    tool_metadata = reference_tooling.get("tool_metadata", {})

    shared_tools = sorted(generated_tools & reference_tools)

    shared_tool_metadata = {}
    for tool in shared_tools:
        meta = tool_metadata.get(tool, {})
        shared_tool_metadata[tool] = {
            "generated_present": True,
            "reference_documented": tool in reference_tools,
            "reference_registered": tool in normalized_registered,
            "reference_registered_function": meta.get("registered_function"),
        }

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
        "shared_tools": shared_tools,
        "shared_tool_count": len(shared_tools),
        "shared_tool_metadata": shared_tool_metadata,
        "coverage_ratio": coverage_ratio,
    }


def _compare_structure(generated_manifest, reference_inspection):
    """Compare generated manifest structure against normalized reference descriptor."""
    generated_protocol = generated_manifest.get("protocol")
    generated_capability = generated_manifest.get("capability")
    generated_version = generated_manifest.get("version")

    reference_descriptor = reference_inspection["descriptor"]
    reference_schema = reference_descriptor.get("schema")
    reference_name = reference_descriptor.get("name")
    reference_version = reference_descriptor.get("version")
    reference_transports = sorted(
        set(reference_descriptor.get("package_transports", []))
        | set(reference_descriptor.get("remote_transports", []))
    )

    return {
        "generated_protocol": generated_protocol,
        "reference_schema": reference_schema,
        "protocol_match": generated_protocol == "model-context-protocol",
        "generated_capability": generated_capability,
        "reference_name": reference_name,
        "capability_declared": bool(generated_capability),
        "generated_version": generated_version,
        "reference_version": reference_version,
        "version_match": generated_version == reference_version,
        "reference_transports": reference_transports,
    }


def _collect_generated_capabilities(generated_root):
    """Collect capability booleans that can be inferred from a generated repo."""
    generated_root = Path(generated_root)
    server_py = generated_root / "server.py"
    server_text = server_py.read_text(encoding="utf-8") if server_py.exists() else ""

    return {
        "supports_dynamic_toolsets": "enable_toolset" in server_text
        or "list_available_toolsets" in server_text,
        "supports_explicit_tools": True,  # manifest tool list is explicit selection
        "supports_exclude_tools": False,
        "supports_read_only": False,
        "supports_feature_flags": False,
        "supports_scope_filtering": False,
        "supports_lockdown_mode": False,
    }


def _compare_capability_surface(generated_root, reference_inspection):
    """Compare inferred generated capabilities against reference capabilities."""
    generated_capabilities = _collect_generated_capabilities(generated_root)
    reference_capabilities = reference_inspection["capabilities"]

    matching_enabled = sorted(
        key
        for key in sorted(reference_capabilities)
        if generated_capabilities.get(key) and reference_capabilities.get(key)
    )
    missing_enabled = sorted(
        key
        for key in sorted(reference_capabilities)
        if reference_capabilities.get(key) and not generated_capabilities.get(key)
    )

    reference_enabled_count = sum(bool(v) for v in reference_capabilities.values())
    matching_enabled_count = len(matching_enabled)
    coverage_ratio = (
        matching_enabled_count / reference_enabled_count
        if reference_enabled_count
        else 1.0
    )

    return {
        "generated": generated_capabilities,
        "reference": reference_capabilities,
        "matching_enabled": matching_enabled,
        "missing_enabled": missing_enabled,
        "matching_enabled_count": matching_enabled_count,
        "reference_enabled_count": reference_enabled_count,
        "coverage_ratio": coverage_ratio,
    }


def _compare_testability(generated_root, reference_inspection):
    """Compare generated test surface against normalized reference testability."""
    generated = _collect_generated_test_surface(generated_root)
    reference = reference_inspection["testability"]

    reference_count = reference["test_file_count"]
    generated_count = generated["test_file_count"]
    coverage_ratio = generated_count / reference_count if reference_count else 1.0

    return {
        "generated": generated,
        "reference": reference,
        "coverage_ratio": coverage_ratio,
    }


def _round_score(value):
    """Return a deterministic score rounded to 2 decimals."""
    return round(float(value), 2)


def _build_similarity_summary(tool_surface, structure, capability_surface, testability):
    """Build deterministic aggregate similarity scores from comparison dimensions."""
    tool_surface_score = _round_score(tool_surface.get("coverage_ratio", 0.0))
    capability_surface_score = _round_score(
        capability_surface.get("coverage_ratio", 0.0)
    )
    testability_score = _round_score(testability.get("coverage_ratio", 0.0))

    structural_components = [
        1.0 if structure.get("protocol_match") else 0.0,
        1.0 if structure.get("capability_declared") else 0.0,
        1.0 if structure.get("version_match") else 0.0,
    ]
    structural_score = _round_score(
        sum(structural_components) / len(structural_components)
    )

    overall_score = _round_score(
        0.4 * tool_surface_score
        + 0.3 * capability_surface_score
        + 0.2 * testability_score
        + 0.1 * structural_score
    )

    return {
        "tool_surface_score": tool_surface_score,
        "capability_surface_score": capability_surface_score,
        "testability_score": testability_score,
        "structural_score": structural_score,
        "overall_score": overall_score,
    }


def compare_mcp_servers(generated_path, reference_path, output_path=None):
    """Compare a generated MCP repo against a normalized reference MCP repo."""
    generated_root = Path(generated_path)
    generated_manifest = _load_manifest(generated_root)
    reference_inspection = inspect_reference_mcp(reference_path)

    tool_surface = _compare_tool_surface(
        generated_manifest, reference_inspection
    )
    structure = _compare_structure(
        generated_manifest, reference_inspection
    )
    capability_surface = _compare_capability_surface(
        generated_root, reference_inspection
    )
    testability = _compare_testability(
        generated_root, reference_inspection
    )

    result = {
        "generated": str(generated_root),
        "reference": str(Path(reference_path)),
        "tool_surface": tool_surface,
        "structure": structure,
        "consistency": reference_inspection.get("consistency", {}),
        "capability_surface": capability_surface,
        "testability": testability,
        "similarity": _build_similarity_summary(
            tool_surface,
            structure,
            capability_surface,
            testability,
        ),
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
