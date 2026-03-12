# SPDX-License-Identifier: MIT
"""Canonical capability-to-artifact mapping for the capability factory."""

CAPABILITY_ARTIFACT_KIND = {
    "github_repository_management": "mcp_server",
    "slack_workspace_access": "agent_adapter",
    "postgres_data_access": "data_connector",
}


def artifact_kind_for_capability(capability):
    return CAPABILITY_ARTIFACT_KIND.get(capability)
