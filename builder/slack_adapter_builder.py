# SPDX-License-Identifier: MIT
"""
Deterministic Slack agent adapter builder.

Generates a minimal adapter-style repository to prove that the capability
factory can build artifact kinds beyond MCP servers.
"""

import json
from pathlib import Path

from builder.artifact_registry import register_builder


REPO_ROOT = Path(__file__).resolve().parents[1]


def _write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def _default_repo_name_for_capability(capability):
    if capability == "slack_workspace_access":
        return "generated_agent_adapter_slack"
    suffix = capability.lower().replace(" ", "_")
    return f"generated_agent_adapter_{suffix}"


@register_builder("agent_adapter")
def build_agent_adapter(
    name=None,
    capability="slack_workspace_access",
):
    """
    Generate a deterministic agent adapter repo for Slack-style access.
    """

    if name is None:
        name = _default_repo_name_for_capability(capability)

    root = REPO_ROOT / name

    manifest = {
        "name": name,
        "artifact_kind": "agent_adapter",
        "capability": capability,
        "provider": "slack",
        "version": "0.1.0",
        "entrypoint": "slack_adapter.py",
    }

    readme = f"""
# {name}

Deterministic generated agent adapter.

## Artifact kind
agent_adapter

## Capability
{capability}

## Provider
slack
"""

    adapter_py = f'''
"""
Generated Slack adapter for capability: {capability}
"""


def get_adapter_metadata():
    return {{
        "artifact_kind": "agent_adapter",
        "capability": "{capability}",
        "provider": "slack",
        "status": "ok",
    }}
'''

    smoke_test = """
import slack_adapter


def test_get_adapter_metadata():
    metadata = slack_adapter.get_adapter_metadata()
    assert metadata["artifact_kind"] == "agent_adapter"
    assert metadata["provider"] == "slack"
    assert metadata["status"] == "ok"
"""

    _write(root / "README.md", readme)
    _write(root / "adapter_manifest.json", json.dumps(manifest, indent=2))
    _write(root / "slack_adapter.py", adapter_py)
    _write(root / "tests" / "test_adapter_smoke.py", smoke_test)

    return {
        "status": "ok",
        "generated_repo": str(root),
        "artifact_kind": "agent_adapter",
        "capability": capability,
    }
