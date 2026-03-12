# SPDX-License-Identifier: MIT
"""
Deterministic data connector builder.

Generates a minimal connector-style repository to prove that the capability
factory can build artifact kinds beyond MCP servers and agent adapters.
"""

import json
from pathlib import Path

from builder.artifact_registry import register_builder
from builder.spec_builder_support import require_capability_spec, default_generated_repo_name


REPO_ROOT = Path(__file__).resolve().parents[1]


def _write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


@register_builder("data_connector")
def build_data_connector(
    name=None,
    capability="postgres_data_access",
):
    """
    Generate a deterministic data connector repo.
    """

    spec = require_capability_spec(capability, "data_connector")

    if name is None:
        name = default_generated_repo_name(spec)

    root = REPO_ROOT / name

    manifest = {
        "name": name,
        "artifact_kind": "data_connector",
        "capability": capability,
        "provider": spec["provider"],
        "version": "0.1.0",
        "entrypoint": "postgres_connector.py",
    }

    readme = f"""
# {name}

Deterministic generated data connector.

## Artifact kind
data_connector

## Capability
{capability}

## Provider
{spec["provider"]}
"""

    connector_py = f'''
"""
Generated {spec["title"]} connector for capability: {capability}
"""


def get_connector_metadata():
    return {{
        "artifact_kind": "data_connector",
        "capability": "{capability}",
        "provider": "postgres",
        "status": "ok",
    }}
'''

    smoke_test = """
import postgres_connector


def test_get_connector_metadata():
    metadata = postgres_connector.get_connector_metadata()
    assert metadata["artifact_kind"] == "data_connector"
    assert metadata["provider"] == "postgres"
    assert metadata["status"] == "ok"
"""

    _write(root / "README.md", readme)
    _write(root / "connector_manifest.json", json.dumps(manifest, indent=2))
    _write(root / "postgres_connector.py", connector_py)
    _write(root / "tests" / "test_connector_smoke.py", smoke_test)

    return {
        "status": "ok",
        "generated_repo": str(root),
        "artifact_kind": "data_connector",
        "capability": capability,
    }
