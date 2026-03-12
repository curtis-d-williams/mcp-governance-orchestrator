# SPDX-License-Identifier: MIT
"""
Deterministic MCP server builder.

Renders templates from templates/mcp_server and generates a minimal
MCP server repository.
"""

import json
from pathlib import Path
from builder.artifact_registry import register_builder
from builder.spec_builder_support import require_capability_spec, default_generated_repo_name


REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = REPO_ROOT / "templates" / "mcp_server"


def _read_template(name):
    return (TEMPLATE_DIR / name).read_text(encoding="utf-8")


def _write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def _render(template, variables):
    for k, v in variables.items():
        template = template.replace("{{" + k + "}}", v)
    return template


@register_builder("mcp_server")
def build_mcp_server(
    name=None,
    capability="github_repository_management",
    tools=None,
):
    """
    Generate a deterministic MCP server repo.
    """

    spec = require_capability_spec(capability, "mcp_server")

    if name is None:
        name = default_generated_repo_name(spec)

    if tools is None:
        tools = spec.get("default_tools", ["health_check"])

    root = REPO_ROOT / name

    tools_json = json.dumps(tools, indent=2)

    variables = {
        "name": name,
        "capability": capability,
        "tools": "\n".join(f"- {t}" for t in tools),
        "tools_json": tools_json,
    }

    # Render core templates
    readme = _render(_read_template("README.md.tpl"), variables)
    manifest = _render(_read_template("manifest.json.tpl"), variables)
    server = _render(_read_template("server.py.tpl"), variables)

    _write(root / "README.md", readme)
    _write(root / "manifest.json", manifest)
    _write(root / "server.py", server)

    # Tool stubs
    for tool in tools:
        _write(
            root / "tools" / f"{tool}.py",
            f"""
def {tool}():
    return {{"status": "ok", "tool": "{tool}"}}
""",
        )

    # Smoke test
    _write(
        root / "tests" / "test_server_smoke.py",
        """
import server

def test_list_tools():
    tools = server.list_tools()
    assert isinstance(tools, list)
""",
    )

    return {
        "status": "ok",
        "generated_repo": str(root),
        "tools": tools,
    }
