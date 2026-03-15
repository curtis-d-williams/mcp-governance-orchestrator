# SPDX-License-Identifier: MIT
"""
Deterministic MCP server builder.

Renders templates from templates/mcp_server and generates a minimal
MCP server repository.
"""

import json
import shutil
from pathlib import Path
from builder.artifact_registry import register_builder
from builder.spec_builder_support import require_capability_spec, default_generated_repo_name
from builder.template_renderer import read_template, write_file, render_template
from builder.result_contract import builder_result


REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = REPO_ROOT / "templates" / "mcp_server"


@register_builder("mcp_server")
def build_mcp_server(
    name=None,
    capability="github_repository_management",
    tools=None,
    features=None,
    test_expansion=False,
):
    """
    Generate a deterministic MCP server repo.
    """

    spec = require_capability_spec(capability, "mcp_server")

    if name is None:
        name = default_generated_repo_name(spec)

    if tools is None:
        tools = spec.get("default_tools", ["health_check"])

    # Stage 1E: normalize tool specs (list[str] -> dict[str, metadata])
    if isinstance(tools, list):
        tools = {t: {} for t in tools}

    if features is None:
        features = []

    root = REPO_ROOT / name

    if root.exists():
        shutil.rmtree(root)

    tools_json = json.dumps(tools, indent=2)
    features_json = json.dumps(features, indent=2)
    tool_imports = "\n".join(
        f"    from .tools.{tool} import {tool} as _{tool}" for tool in tools.keys()
    )
    tool_imports_fallback = "\n".join(
        f"    from tools.{tool} import {tool} as _{tool}" for tool in tools.keys()
    )
    
    # Stage 1E: schema-aware wrapper generation
    tool_wrappers = []

    for tool, meta in tools.items():
        params = meta.get("params", [])
        param_sig = ", ".join(f"{p}: str" for p in params)
        param_pass = ", ".join(params)

        if param_sig:
            wrapper = f"@mcp.tool()\ndef {tool}({param_sig}):\n    return _{tool}({param_pass})"
        else:
            wrapper = f"@mcp.tool()\ndef {tool}():\n    return _{tool}()"

        tool_wrappers.append(wrapper)

    tool_wrappers = "\n\n".join(tool_wrappers)

    variables = {
        "name": name,
        "capability": capability,
        "tools": "\n".join(f"- {t}" for t in tools),
        "features": "\n".join(f"- {f}" for f in features),
        "tools_json": tools_json,
        "features_json": features_json,
        "tool_imports": tool_imports,
        "tool_imports_fallback": tool_imports_fallback,
        "tool_wrappers": tool_wrappers,
    }

    # Render core templates
    readme = render_template(read_template(TEMPLATE_DIR, "README.md.tpl"), variables)
    manifest = render_template(read_template(TEMPLATE_DIR, "manifest.json.tpl"), variables)
    server = render_template(read_template(TEMPLATE_DIR, "server.py.tpl"), variables)

    write_file(root / "__init__.py", "")
    write_file(root / "tools" / "__init__.py", "")
    write_file(root / "README.md", readme)
    write_file(root / "manifest.json", manifest)
    write_file(root / "server.py", server)

    # Tool stubs
    for tool, meta in tools.items():
        params = meta.get("params", [])
        param_sig = ", ".join(params)
        arg_names = ", ".join(f'"{p}": {p}' for p in params)

        if param_sig:
            body = f"""
def {tool}({param_sig}):
    return {{"status": "ok", "tool": "{tool}", "args": {{{arg_names}}}}}
"""
        else:
            body = f"""
def {tool}():
    return {{"status": "ok", "tool": "{tool}"}}
"""
        write_file(root / "tools" / f"{tool}.py", body)

    # Smoke test
    write_file(
        root / "tests" / "test_server_smoke.py",
        f"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server

def test_list_tools():
    tools = server.list_tools()
    assert tools == {tools_json}
""",
    )

    # Deterministic optional test expansion
    if test_expansion:
        write_file(
            root / "tests" / "test_tools_basic.py",
            f"""
import server

def test_all_tools_callable():
    tools = server.list_tools()
    for tool in tools.keys():
        fn = getattr(server, tool)
        result = fn()
        assert isinstance(result, dict)
""",
        )

    return builder_result(
        generated_repo=str(root),
        artifact_kind="mcp_server",
        capability=capability,
        tools=tools,
        features=features,
        test_expansion=test_expansion,
    )
