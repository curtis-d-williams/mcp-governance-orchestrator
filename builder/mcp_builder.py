# SPDX-License-Identifier: MIT
"""
Deterministic MCP server builder.

Renders templates from templates/mcp_server and generates a minimal
MCP server repository.
"""

import json
from pathlib import Path


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


def _default_tools_for_capability(capability):
    if capability == "github_repository_management":
        return [
            "list_repositories",
            "get_repository",
            "create_issue",
        ]
    if capability == "slack_workspace_access":
        return [
            "list_channels",
            "get_channel",
            "post_message",
        ]
    if capability == "postgres_data_access":
        return [
            "list_tables",
            "describe_table",
            "run_query",
        ]
    return [
        "health_check",
    ]


def _default_repo_name_for_capability(capability):
    if capability == "github_repository_management":
        return "generated_mcp_github"
    if capability == "slack_workspace_access":
        return "generated_mcp_slack"
    if capability == "postgres_data_access":
        return "generated_mcp_postgres"
    suffix = capability.lower().replace(" ", "_")
    return f"generated_mcp_{suffix}"


def build_mcp_server(
    name=None,
    capability="github_repository_management",
    tools=None,
):
    """
    Generate a deterministic MCP server repo.
    """

    if name is None:
        name = _default_repo_name_for_capability(capability)

    if tools is None:
        tools = _default_tools_for_capability(capability)

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
