# SPDX-License-Identifier: MIT
"""Regression tests for scripts/compare_mcp_servers.py.

Covers:
1. Tool surface comparison correctness.
2. Structural manifest comparison.
3. Test surface detection.
4. Deterministic output for identical inputs.
"""

import importlib.util
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Module loading
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_SCRIPT = _REPO_ROOT / "scripts" / "compare_mcp_servers.py"
_spec = importlib.util.spec_from_file_location("compare_mcp_servers", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

compare_mcp_servers = _mod.compare_mcp_servers


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_manifest(root, name, capability, tools):
    root.mkdir(parents=True, exist_ok=True)
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "name": name,
                "capability": capability,
                "protocol": "model-context-protocol",
                "version": "0.1.0",
                "tools": tools,
            }
        ),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestToolSurfaceComparison:

    def test_matching_tools(self, tmp_path):
        gen = tmp_path / "gen"
        ref = tmp_path / "ref"

        _write_manifest(gen, "gen", "cap", ["a", "b"])
        _write_manifest(ref, "ref", "cap", ["a", "b"])

        result = compare_mcp_servers(gen, ref)

        ts = result["tool_surface"]
        assert ts["matching_tool_count"] == 2
        assert ts["coverage_ratio"] == 1.0
        assert ts["missing_tools"] == []
        assert ts["extra_tools"] == []

    def test_missing_and_extra_tools(self, tmp_path):
        gen = tmp_path / "gen"
        ref = tmp_path / "ref"

        _write_manifest(gen, "gen", "cap", ["a", "b"])
        _write_manifest(ref, "ref", "cap", ["a", "c"])

        result = compare_mcp_servers(gen, ref)

        ts = result["tool_surface"]
        assert ts["matching_tools"] == ["a"]
        assert ts["missing_tools"] == ["c"]
        assert ts["extra_tools"] == ["b"]


class TestStructureComparison:

    def test_protocol_and_capability_match(self, tmp_path):
        gen = tmp_path / "gen"
        ref = tmp_path / "ref"

        _write_manifest(gen, "gen", "github_repository_management", ["a"])
        _write_manifest(ref, "ref", "github_repository_management", ["a"])

        result = compare_mcp_servers(gen, ref)

        structure = result["structure"]
        assert structure["protocol_match"] is True
        assert structure["capability_match"] is True

    def test_protocol_mismatch(self, tmp_path):
        gen = tmp_path / "gen"
        ref = tmp_path / "ref"

        gen.mkdir()
        ref.mkdir()

        (gen / "manifest.json").write_text(
            json.dumps(
                {
                    "name": "gen",
                    "capability": "cap",
                    "protocol": "model-context-protocol",
                    "version": "0.1.0",
                    "tools": [],
                }
            ),
            encoding="utf-8",
        )

        (ref / "manifest.json").write_text(
            json.dumps(
                {
                    "name": "ref",
                    "capability": "cap",
                    "protocol": "different-protocol",
                    "version": "0.1.0",
                    "tools": [],
                }
            ),
            encoding="utf-8",
        )

        result = compare_mcp_servers(gen, ref)
        assert result["structure"]["protocol_match"] is False


class TestTestSurface:

    def test_detects_tests(self, tmp_path):
        gen = tmp_path / "gen"
        ref = tmp_path / "ref"

        _write_manifest(gen, "gen", "cap", ["a"])
        _write_manifest(ref, "ref", "cap", ["a"])

        tests_dir = gen / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_example.py").write_text("def test_x(): pass")

        result = compare_mcp_servers(gen, ref)

        gen_tests = result["testability"]["generated"]
        assert gen_tests["has_tests"] is True
        assert gen_tests["test_file_count"] == 1


class TestDeterminism:

    def test_repeated_calls_identical(self, tmp_path):
        gen = tmp_path / "gen"
        ref = tmp_path / "ref"

        _write_manifest(gen, "gen", "cap", ["a", "b"])
        _write_manifest(ref, "ref", "cap", ["a", "b"])

        r1 = compare_mcp_servers(gen, ref)
        r2 = compare_mcp_servers(gen, ref)

        assert r1 == r2
