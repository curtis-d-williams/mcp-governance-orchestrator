# SPDX-License-Identifier: MIT
"""Canonical capability specifications for the capability factory."""

CAPABILITY_SPECS = {
    "github_repository_management": {
        "artifact_kind": "mcp_server",
        "provider": "github",
        "slug": "github",
        "title": "GitHub Repository Management",
        "default_tools": [
            "list_repositories",
            "get_repository",
            "create_issue",
        ],
    },
    "slack_workspace_access": {
        "artifact_kind": "agent_adapter",
        "provider": "slack",
        "slug": "slack",
        "title": "Slack Workspace Access",
        "default_tools": [
            "list_channels",
            "get_channel",
            "post_message",
        ],
    },
    "postgres_data_access": {
        "artifact_kind": "data_connector",
        "provider": "postgres",
        "slug": "postgres",
        "title": "Postgres Data Access",
        "default_tools": [
            "list_tables",
            "describe_table",
            "run_query",
        ],
    },
}


def get_capability_spec(capability):
    return CAPABILITY_SPECS.get(capability)
