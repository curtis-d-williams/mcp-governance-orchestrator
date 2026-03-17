# SPDX-License-Identifier: MIT
"""Verify that importing factory_pipeline triggers builder registration side effects.

This test does NOT use an isolated_registry fixture — it intentionally asserts
the real post-import state of ARTIFACT_BUILDERS to confirm the canonical build
path seam is connected.
"""

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def test_factory_pipeline_import_populates_artifact_builders():
    """Importing factory_pipeline must populate ARTIFACT_BUILDERS with all three canonical builders."""
    import factory_pipeline  # noqa: F401 — import for side effects
    from builder.artifact_registry import ARTIFACT_BUILDERS

    assert "mcp_server" in ARTIFACT_BUILDERS, "mcp_server builder not registered"
    assert "agent_adapter" in ARTIFACT_BUILDERS, "agent_adapter builder not registered"
    assert "data_connector" in ARTIFACT_BUILDERS, "data_connector builder not registered"
