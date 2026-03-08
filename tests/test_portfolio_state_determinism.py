# SPDX-License-Identifier: MIT
"""Determinism tests for portfolio_state v1.

Verifies byte-identical JSON serialization, stable repo ordering, stable
action/issue ordering, stable portfolio_id derivation, and byte-identical
CLI output when --generated-at is fixed.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mcp_governance_orchestrator.portfolio_state import build_portfolio_state

_TS = "2025-01-01T00:00:00+00:00"
_REPO_ROOT = Path(__file__).resolve().parents[1]


def _serialize(state: dict) -> str:
    """Canonical JSON serialization for byte-identical comparison."""
    return json.dumps(state, indent=2, ensure_ascii=False)


def _build(signals, ts="", portfolio_id=None):
    return build_portfolio_state(signals, generated_at=ts, portfolio_id=portfolio_id)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_SIGNALS_MULTI = [
    {
        "repo_id": "zzz-last",
        "last_run_ok": True,
        "artifact_completeness": 1.0,
        "determinism_ok": True,
        "recent_failures": 0,
        "stale_runs": 0,
    },
    {
        "repo_id": "aaa-first",
        "last_run_ok": False,
        "artifact_completeness": 0.0,
        "determinism_ok": False,
        "recent_failures": 3,
        "stale_runs": 5,
    },
    {
        "repo_id": "mmm-middle",
        "last_run_ok": True,
        "artifact_completeness": 0.7,
        "determinism_ok": True,
        "recent_failures": 0,
        "stale_runs": 3,
    },
]

_SIGNALS_SINGLE = [
    {
        "repo_id": "determinism-check-repo",
        "last_run_ok": False,
        "artifact_completeness": 0.5,
        "determinism_ok": False,
        "recent_failures": 2,
        "stale_runs": 4,
    }
]


# ---------------------------------------------------------------------------
# Byte-identical serialization (library)
# ---------------------------------------------------------------------------

class TestByteIdentical:
    def test_single_call_same_result(self):
        a = _build(_SIGNALS_SINGLE)
        b = _build(_SIGNALS_SINGLE)
        assert _serialize(a) == _serialize(b)

    def test_multi_call_same_result(self):
        a = _build(_SIGNALS_MULTI)
        b = _build(_SIGNALS_MULTI)
        assert _serialize(a) == _serialize(b)

    def test_ten_calls_all_identical(self):
        results = [_serialize(_build(_SIGNALS_MULTI)) for _ in range(10)]
        assert len(set(results)) == 1, "Expected all 10 serializations to be identical"

    def test_fixed_generated_at_produces_identical_output(self):
        a = _build(_SIGNALS_MULTI, ts=_TS)
        b = _build(_SIGNALS_MULTI, ts=_TS)
        assert _serialize(a) == _serialize(b)

    def test_default_generated_at_is_empty_string(self):
        state = _build(_SIGNALS_SINGLE)
        assert state["generated_at"] == ""

    def test_empty_generated_at_gives_byte_identical_output(self):
        a = _build(_SIGNALS_MULTI, ts="")
        b = _build(_SIGNALS_MULTI, ts="")
        assert _serialize(a) == _serialize(b)


# ---------------------------------------------------------------------------
# Stable repo ordering
# ---------------------------------------------------------------------------

class TestStableRepoOrdering:
    def test_repos_sorted_by_repo_id(self):
        state = _build(_SIGNALS_MULTI)
        ids = [r["repo_id"] for r in state["repos"]]
        assert ids == sorted(ids)

    def test_reverse_input_order_gives_same_output(self):
        forward = _build(_SIGNALS_MULTI)
        backward = _build(list(reversed(_SIGNALS_MULTI)))
        assert _serialize(forward) == _serialize(backward)

    def test_shuffled_input_gives_same_output(self):
        shuffled = [_SIGNALS_MULTI[2], _SIGNALS_MULTI[0], _SIGNALS_MULTI[1]]
        assert _serialize(_build(_SIGNALS_MULTI)) == _serialize(_build(shuffled))


# ---------------------------------------------------------------------------
# Stable action and issue ordering
# ---------------------------------------------------------------------------

class TestStableOrdering:
    def test_actions_priority_desc_stable(self):
        state = _build(_SIGNALS_MULTI)
        for repo in state["repos"]:
            priorities = [a["priority"] for a in repo["recommended_actions"]]
            assert priorities == sorted(priorities, reverse=True), (
                f"repo {repo['repo_id']} actions not sorted by priority desc"
            )

    def test_issues_severity_desc_stable(self):
        from mcp_governance_orchestrator.portfolio_state import _SEVERITY_RANK
        state = _build(_SIGNALS_MULTI)
        for repo in state["repos"]:
            ranks = [_SEVERITY_RANK[i["severity"]] for i in repo["open_issues"]]
            assert ranks == sorted(ranks, reverse=True), (
                f"repo {repo['repo_id']} issues not sorted by severity desc"
            )

    def test_portfolio_recommendations_sorted_priority_desc(self):
        state = _build(_SIGNALS_MULTI)
        priorities = [r["priority"] for r in state["portfolio_recommendations"]]
        assert priorities == sorted(priorities, reverse=True)

    def test_tiebreak_stable_across_calls(self):
        """Same-priority actions resolve identically across repeated calls."""
        signals = [
            {
                "repo_id": "aaa",
                "last_run_ok": True,
                "artifact_completeness": 1.0,
                "determinism_ok": True,
                "recent_failures": 0,
                "stale_runs": 3,
            },
            {
                "repo_id": "bbb",
                "last_run_ok": True,
                "artifact_completeness": 1.0,
                "determinism_ok": True,
                "recent_failures": 0,
                "stale_runs": 3,
            },
        ]
        a = _build(signals)
        b = _build(signals)
        assert (
            [r["action_id"] for r in a["portfolio_recommendations"]]
            == [r["action_id"] for r in b["portfolio_recommendations"]]
        )


# ---------------------------------------------------------------------------
# Stable portfolio_id
# ---------------------------------------------------------------------------

class TestStablePortfolioId:
    def test_same_inputs_same_portfolio_id(self):
        assert _build(_SIGNALS_MULTI)["portfolio_id"] == _build(_SIGNALS_MULTI)["portfolio_id"]

    def test_different_inputs_different_portfolio_id(self):
        assert _build(_SIGNALS_SINGLE)["portfolio_id"] != _build(_SIGNALS_MULTI)["portfolio_id"]

    def test_custom_portfolio_id_preserved(self):
        state = _build(_SIGNALS_SINGLE, portfolio_id="my-custom-id")
        assert state["portfolio_id"] == "my-custom-id"

    def test_portfolio_id_order_invariant(self):
        """portfolio_id is derived from sorted repo IDs, so input order doesn't matter."""
        a = _build(_SIGNALS_MULTI)
        b = _build(list(reversed(_SIGNALS_MULTI)))
        assert a["portfolio_id"] == b["portfolio_id"]


# ---------------------------------------------------------------------------
# CLI determinism — byte-identical output with --generated-at fixed
# ---------------------------------------------------------------------------

class TestCLIDeterminism:
    _CLI = [sys.executable, str(_REPO_ROOT / "scripts" / "build_portfolio_state.py")]

    def _run_cli(self, input_file, output_file, extra_args=None):
        cmd = self._CLI + ["--input", str(input_file), "--output", str(output_file)]
        if extra_args:
            cmd += extra_args
        return subprocess.run(cmd, capture_output=True, text=True)

    def test_cli_succeeds_on_valid_input(self, tmp_path):
        input_file = tmp_path / "signals.json"
        output_file = tmp_path / "state.json"
        input_file.write_text(json.dumps(_SIGNALS_SINGLE), encoding="utf-8")

        result = self._run_cli(input_file, output_file)
        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        assert output_file.exists()

        state = json.loads(output_file.read_text(encoding="utf-8"))
        assert state["schema_version"] == "v1"
        assert len(state["repos"]) == 1

    def test_cli_default_generated_at_is_empty_string(self, tmp_path):
        input_file = tmp_path / "signals.json"
        output_file = tmp_path / "state.json"
        input_file.write_text(json.dumps(_SIGNALS_SINGLE), encoding="utf-8")

        result = self._run_cli(input_file, output_file)
        assert result.returncode == 0
        state = json.loads(output_file.read_text(encoding="utf-8"))
        assert state["generated_at"] == ""

    def test_cli_generated_at_flag_passthrough(self, tmp_path):
        input_file = tmp_path / "signals.json"
        output_file = tmp_path / "state.json"
        input_file.write_text(json.dumps(_SIGNALS_SINGLE), encoding="utf-8")

        result = self._run_cli(input_file, output_file, ["--generated-at", _TS])
        assert result.returncode == 0
        state = json.loads(output_file.read_text(encoding="utf-8"))
        assert state["generated_at"] == _TS

    def test_cli_byte_identical_with_fixed_generated_at(self, tmp_path):
        """Two CLI runs with --generated-at fixed produce byte-identical files."""
        input_file = tmp_path / "signals.json"
        input_file.write_text(json.dumps(_SIGNALS_MULTI), encoding="utf-8")

        out1 = tmp_path / "out1.json"
        out2 = tmp_path / "out2.json"

        r1 = self._run_cli(input_file, out1, ["--generated-at", _TS])
        r2 = self._run_cli(input_file, out2, ["--generated-at", _TS])
        assert r1.returncode == 0
        assert r2.returncode == 0
        assert out1.read_text(encoding="utf-8") == out2.read_text(encoding="utf-8")

    def test_cli_byte_identical_default_no_clock(self, tmp_path):
        """Two CLI runs with no --generated-at produce byte-identical files (both use "")."""
        input_file = tmp_path / "signals.json"
        input_file.write_text(json.dumps(_SIGNALS_MULTI), encoding="utf-8")

        out1 = tmp_path / "out1.json"
        out2 = tmp_path / "out2.json"

        r1 = self._run_cli(input_file, out1)
        r2 = self._run_cli(input_file, out2)
        assert r1.returncode == 0
        assert r2.returncode == 0
        assert out1.read_text(encoding="utf-8") == out2.read_text(encoding="utf-8")

    def test_cli_fails_on_missing_input(self, tmp_path):
        result = self._run_cli(tmp_path / "nonexistent.json", tmp_path / "out.json")
        assert result.returncode != 0

    def test_cli_fails_on_malformed_json(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{not valid json", encoding="utf-8")
        result = self._run_cli(bad, tmp_path / "out.json")
        assert result.returncode != 0

    def test_cli_fails_on_non_array_input(self, tmp_path):
        obj_file = tmp_path / "obj.json"
        obj_file.write_text(json.dumps({"repo_id": "x"}), encoding="utf-8")
        result = self._run_cli(obj_file, tmp_path / "out.json")
        assert result.returncode != 0

    def test_cli_output_schema_version_v1(self, tmp_path):
        input_file = tmp_path / "signals.json"
        output_file = tmp_path / "state.json"
        input_file.write_text(json.dumps(_SIGNALS_SINGLE), encoding="utf-8")
        self._run_cli(input_file, output_file)
        state = json.loads(output_file.read_text(encoding="utf-8"))
        assert state["schema_version"] == "v1"

    def test_cli_output_cooldowns_is_list(self, tmp_path):
        input_file = tmp_path / "signals.json"
        output_file = tmp_path / "state.json"
        input_file.write_text(json.dumps(_SIGNALS_SINGLE), encoding="utf-8")
        self._run_cli(input_file, output_file)
        state = json.loads(output_file.read_text(encoding="utf-8"))
        for repo in state["repos"]:
            assert isinstance(repo["cooldowns"], list)
