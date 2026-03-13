# SPDX-License-Identifier: MIT
"""Regression tests for scripts/update_capability_gaps_from_mcp_comparison.py."""

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

_SCRIPT = _REPO_ROOT / "scripts" / "update_capability_gaps_from_mcp_comparison.py"
_spec = importlib.util.spec_from_file_location(
    "update_capability_gaps_from_mcp_comparison", _SCRIPT
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

derive_capability_gaps_from_comparison = _mod.derive_capability_gaps_from_comparison


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_gap_derivation_basic():
    comparison = {
        "structure": {
            "generated_capability": "github_repository_management",
        },
        "tool_surface": {
            "coverage_ratio": 0.33,
            "missing_tools": ["create_issue", "get_repository"],
        },
        "capability_surface": {
            "coverage_ratio": 0.50,
            "missing_enabled": ["supports_dynamic_toolsets"],
        },
        "testability": {
            "coverage_ratio": 0.20,
        },
    }

    result = derive_capability_gaps_from_comparison(comparison)

    assert "capability_gaps" in result
    gaps = result["capability_gaps"]
    assert len(gaps) == 1

    gap = gaps[0]

    assert gap["capability"] == "github_repository_management"
    assert gap["missing_tools"] == ["create_issue", "get_repository"]
    assert gap["missing_tool_count"] == 2
    assert gap["missing_enabled_capabilities"] == ["supports_dynamic_toolsets"]
    assert gap["missing_enabled_capability_count"] == 1

    # Deterministic severity calculation
    # missing_tool_ratio = 0.67
    # missing_capability_ratio = 0.50
    # missing_testability_ratio = 0.80
    # severity = 0.5*0.67 + 0.3*0.50 + 0.2*0.80 = 0.65
    assert gap["severity"] == 0.65


def test_invalid_comparison_returns_empty():
    result = derive_capability_gaps_from_comparison(None)
    assert result == {"capability_gaps": []}


def test_missing_capability_returns_empty():
    comparison = {
        "tool_surface": {"coverage_ratio": 1.0},
        "capability_surface": {"coverage_ratio": 1.0},
        "testability": {"coverage_ratio": 1.0},
    }

    result = derive_capability_gaps_from_comparison(comparison)
    assert result == {"capability_gaps": []}


def test_deterministic_output():
    comparison = {
        "structure": {
            "generated_capability": "github_repository_management",
        },
        "tool_surface": {
            "coverage_ratio": 0.25,
            "missing_tools": ["b", "a"],
        },
        "capability_surface": {
            "coverage_ratio": 0.50,
            "missing_enabled": ["z", "y"],
        },
        "testability": {
            "coverage_ratio": 0.50,
        },
    }

    result1 = derive_capability_gaps_from_comparison(comparison)
    result2 = derive_capability_gaps_from_comparison(comparison)

    assert json.dumps(result1, sort_keys=True) == json.dumps(result2, sort_keys=True)
