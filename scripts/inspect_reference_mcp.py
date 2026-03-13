# SPDX-License-Identifier: MIT
"""Deterministic reference MCP inspection CLI.

Inspects a reference MCP implementation repository and emits a normalized
evaluation artifact for Stage 3 comparison.

Current extraction dimensions:
- descriptor
- tooling
- capabilities
- testability
- consistency

Usage:
    python3 scripts/inspect_reference_mcp.py \
        --reference PATH

Optional:
    --output PATH   Write inspection JSON to this path (default: stdout only).
"""

import argparse
import json
import re
from pathlib import Path


def _load_server_descriptor(reference_root):
    reference_root = Path(reference_root)
    server_json = reference_root / "server.json"
    if not server_json.exists():
        raise FileNotFoundError(f"server.json not found: {server_json}")

    raw = json.loads(server_json.read_text(encoding="utf-8"))

    package_transports = sorted(
        {
            pkg.get("transport", {}).get("type")
            for pkg in raw.get("packages", [])
            if pkg.get("transport", {}).get("type")
        }
    )
    remote_transports = sorted(
        {
            remote.get("type")
            for remote in raw.get("remotes", [])
            if remote.get("type")
        }
    )

    return {
        "schema": raw.get("$schema"),
        "name": raw.get("name"),
        "title": raw.get("title"),
        "description": raw.get("description"),
        "repository_url": raw.get("repository", {}).get("url"),
        "repository_source": raw.get("repository", {}).get("source"),
        "version": raw.get("version"),
        "package_count": len(raw.get("packages", [])),
        "remote_count": len(raw.get("remotes", [])),
        "package_transports": package_transports,
        "remote_transports": remote_transports,
    }


def _collect_testability(reference_root):
    reference_root = Path(reference_root)
    test_files = sorted(reference_root.rglob("*_test.go"))

    return {
        "has_e2e_tests": (reference_root / "e2e").exists(),
        "has_server_tests": any(path.name == "server_test.go" for path in test_files),
        "test_file_count": len(test_files),
    }


def _collect_tooling(reference_root):
    reference_root = Path(reference_root)
    tools_go = reference_root / "pkg" / "github" / "tools.go"
    readme_md = reference_root / "README.md"
    server_config_md = reference_root / "docs" / "server-configuration.md"

    if not tools_go.exists():
        raise FileNotFoundError(f"tools.go not found: {tools_go}")

    text = tools_go.read_text(encoding="utf-8")
    readme_text = readme_md.read_text(encoding="utf-8") if readme_md.exists() else ""
    server_config_text = (
        server_config_md.read_text(encoding="utf-8") if server_config_md.exists() else ""
    )
    docs_text = readme_text + "\n" + server_config_text

    registered_toolsets = sorted(
        set(
            re.findall(
                r'ToolsetMetadata[A-Za-z0-9_]+\s*=\s*inventory\.ToolsetMetadata\{\s*ID:\s*"([^"]+)"',
                text,
            )
        )
    )

    default_toolsets = sorted(
        set(
            match[0]
            for match in re.findall(
                r'ToolsetMetadata[A-Za-z0-9_]+\s*=\s*inventory\.ToolsetMetadata\{\s*ID:\s*"([^"]+)",(.*?)\}',
                text,
                re.DOTALL,
            )
            if re.search(r"Default:\s*true", match[1])
        )
    )

    all_tools_block_match = re.search(
        r'func\s+AllTools\s*\([^)]*\)\s*\[\]inventory\.ServerTool\s*\{\s*return\s+\[\]inventory\.ServerTool\s*\{(.*?)\}\s*\}',
        text,
        re.DOTALL,
    )
    all_tools_block = all_tools_block_match.group(1) if all_tools_block_match else ""
    registered_tool_functions = sorted(
        set(re.findall(r'^\s*([A-Za-z0-9_]+)\(t\),\s*$', all_tools_block, re.MULTILINE))
    )

    remote_only_block_match = re.search(
        r'func\s+RemoteOnlyToolsets\s*\(\)\s*\[\]inventory\.ToolsetMetadata\s*\{\s*return\s+\[\]inventory\.ToolsetMetadata\s*\{(.*?)\}\s*\}',
        text,
        re.DOTALL,
    )
    remote_only_block = remote_only_block_match.group(1) if remote_only_block_match else ""
    remote_only_vars = re.findall(r'(ToolsetMetadata[A-Za-z0-9_]+)', remote_only_block)
    remote_only_toolsets = []
    for var_name in remote_only_vars:
        metadata_match = re.search(
            rf'{re.escape(var_name)}\s*=\s*inventory\.ToolsetMetadata\{{\s*ID:\s*"([^"]+)"',
            text,
            re.DOTALL,
        )
        if metadata_match:
            remote_only_toolsets.append(metadata_match.group(1))

    documented_toolsets = sorted(
        set(re.findall(r'`([a-z_]+)`', docs_text))
        & set(registered_toolsets + sorted(set(remote_only_toolsets)))
    )

    documented_tools = sorted(
        set(re.findall(r'^- \*\*([a-z0-9_]+)\*\* -', readme_text, re.MULTILINE))
    )

    return {
        "registered_toolsets": registered_toolsets,
        "default_toolsets": default_toolsets,
        "remote_only_toolsets": sorted(set(remote_only_toolsets)),
        "registered_tool_functions": registered_tool_functions,
        "documented_toolsets": documented_toolsets,
        "documented_tools": documented_tools,
    }


def _collect_capabilities(reference_root):
    reference_root = Path(reference_root)
    github_server_go = reference_root / "pkg" / "github" / "server.go"
    ghmcp_server_go = reference_root / "internal" / "ghmcp" / "server.go"

    if not github_server_go.exists():
        raise FileNotFoundError(f"server.go not found: {github_server_go}")
    if not ghmcp_server_go.exists():
        raise FileNotFoundError(f"server.go not found: {ghmcp_server_go}")

    github_server_text = github_server_go.read_text(encoding="utf-8")
    ghmcp_server_text = ghmcp_server_go.read_text(encoding="utf-8")
    combined = github_server_text + "\n" + ghmcp_server_text

    return {
        "supports_dynamic_toolsets": "DynamicToolsets" in combined,
        "supports_explicit_tools": "EnabledTools" in combined,
        "supports_exclude_tools": "ExcludeTools" in combined,
        "supports_read_only": "ReadOnly" in combined,
        "supports_feature_flags": "EnabledFeatures" in combined or "FeatureFlags" in combined,
        "supports_scope_filtering": "TokenScopes" in combined or "scope filtering" in combined,
        "supports_lockdown_mode": "LockdownMode" in combined,
    }


def _collect_consistency(tooling):
    special_toolsets = {"all", "default", "dynamic"}
    registered_toolset_pool = (
        set(tooling["registered_toolsets"]) | set(tooling["remote_only_toolsets"])
    ) - special_toolsets
    documented_toolset_pool = set(tooling["documented_toolsets"])

    return {
        "documented_default_toolsets_match_registered_defaults": set(
            tooling["default_toolsets"]
        ).issubset(documented_toolset_pool),
        "documented_toolsets_cover_registered_toolsets": registered_toolset_pool.issubset(
            documented_toolset_pool
        ),
        "documented_tools_present": len(tooling["documented_tools"]) > 0,
        "registered_tools_present": len(tooling["registered_tool_functions"]) > 0,
    }


def inspect_reference_mcp(reference_path, output_path=None):
    reference_root = Path(reference_path)
    tooling = _collect_tooling(reference_root)

    result = {
        "reference_path": str(reference_root),
        "descriptor": _load_server_descriptor(reference_root),
        "tooling": tooling,
        "capabilities": _collect_capabilities(reference_root),
        "testability": _collect_testability(reference_root),
        "consistency": _collect_consistency(tooling),
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
        description="Inspect a reference MCP implementation repository.",
        add_help=True,
    )
    parser.add_argument(
        "--reference",
        required=True,
        metavar="PATH",
        help="Path to the reference MCP repository root.",
    )
    parser.add_argument(
        "--output",
        default=None,
        metavar="FILE",
        help="Write inspection JSON to this path. Omit to print to stdout only.",
    )
    args = parser.parse_args(argv)

    inspect_reference_mcp(
        reference_path=args.reference,
        output_path=args.output,
    )


if __name__ == "__main__":
    main()
