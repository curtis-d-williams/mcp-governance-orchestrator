# SPDX-License-Identifier: MIT
"""Canonical capability specifications for the capability factory."""

CAPABILITY_SPECS = {
    "github_repository_management": {
        "artifact_kind": "mcp_server",
        "provider": "github",
        "slug": "github",
        "title": "GitHub Repository Management",
    },
    "slack_workspace_access": {
        "artifact_kind": "agent_adapter",
        "provider": "slack",
        "slug": "slack",
        "title": "Slack Workspace Access",
    },
    "postgres_data_access": {
        "artifact_kind": "data_connector",
        "provider": "postgres",
        "slug": "postgres",
        "title": "Postgres Data Access",
    },
}


def get_capability_spec(capability):
    return CAPABILITY_SPECS.get(capability)
