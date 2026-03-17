"""
Deterministic agent task: generate an MCP server via the canonical governed build path.

Thin wrapper over builder.mcp_builder.build_mcp_server — the same canonical
builder used by scripts/generate_mcp_server.py.
"""

from collections import OrderedDict

from builder.mcp_builder import build_mcp_server


TASK_NAME = "build_mcp_server_example"
DEFAULT_CAPABILITY = "github_repository_management"
DEFAULT_NAME = "generated_mcp_server_github"


def run(repo_root=None):
    """Entry point called by run_agent_task.

    Invokes the canonical MCP builder for the github_repository_management
    capability and returns the builder result as an OrderedDict.
    """
    result = build_mcp_server(
        name=DEFAULT_NAME,
        capability=DEFAULT_CAPABILITY,
    )
    return OrderedDict([
        ("task_name", TASK_NAME),
        ("capability", DEFAULT_CAPABILITY),
        ("status", result.get("status", "unknown")),
        ("generated_repo", result.get("generated_repo")),
    ])
