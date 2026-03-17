# SPDX-License-Identifier: MIT
"""Unit tests for builder/artifact_registry.py.

Imports builder/artifact_registry directly — no factory_pipeline dependency.

Covers:
- unknown artifact_kind raises ValueError with exact error message
- register_builder decorator wires dispatch correctly
- multiple builders coexist without collision
- register_builder returns the original function unchanged
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from builder import artifact_registry
from builder.artifact_registry import build_capability_artifact, register_builder


@pytest.fixture(autouse=True)
def isolated_registry():
    """Each test runs against an empty ARTIFACT_BUILDERS dict.

    patch.dict with clear=True prevents state leaking between tests and
    avoids interference from real builder modules imported elsewhere.
    """
    with patch.dict(artifact_registry.ARTIFACT_BUILDERS, {}, clear=True):
        yield


# ---------------------------------------------------------------------------
# Unknown artifact_kind — fail-closed error path
# ---------------------------------------------------------------------------

class TestUnknownKind:
    def test_raises_value_error(self):
        with pytest.raises(ValueError):
            build_capability_artifact(artifact_kind="unknown_xyz", capability="test")

    def test_error_message_contains_kind(self):
        with pytest.raises(ValueError, match="unknown artifact kind: unknown_xyz"):
            build_capability_artifact(artifact_kind="unknown_xyz", capability="test")


# ---------------------------------------------------------------------------
# Registration and dispatch
# ---------------------------------------------------------------------------

class TestDispatch:
    def test_registered_kind_dispatches(self):
        mock_fn = MagicMock(return_value={"status": "ok"})

        @register_builder("test_kind")
        def _builder(**kwargs):
            return mock_fn(**kwargs)

        result = build_capability_artifact(artifact_kind="test_kind", capability="my_cap")
        mock_fn.assert_called_once_with(capability="my_cap")
        assert result == {"status": "ok"}

    def test_multiple_builders_coexist(self):
        calls = []

        @register_builder("kind_a")
        def _builder_a(**kwargs):
            calls.append(("a", kwargs))
            return "a"

        @register_builder("kind_b")
        def _builder_b(**kwargs):
            calls.append(("b", kwargs))
            return "b"

        assert build_capability_artifact(artifact_kind="kind_a", capability="cap") == "a"
        assert build_capability_artifact(artifact_kind="kind_b", capability="cap") == "b"
        assert calls[0][0] == "a"
        assert calls[1][0] == "b"

    def test_register_builder_returns_original_function(self):
        def my_builder(**kwargs):
            return "original"

        decorated = register_builder("my_kind")(my_builder)
        assert decorated is my_builder
