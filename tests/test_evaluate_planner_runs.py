# SPDX-License-Identifier: MIT
"""Regression tests for evaluate_planner_runs.py.

Covers:
- evaluate_envelopes detects matching envelopes (identical=True)
- evaluate_envelopes detects ordering differences
- evaluate_envelopes handles empty input
- evaluate_envelopes handles single envelope
- load_envelope loads valid JSON
- main() CLI outputs deterministic JSON
- main() writes to --output file
- main() errors on empty args
- output is deterministic across repeated calls
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_SCRIPT = _REPO_ROOT / "scripts" / "evaluate_planner_runs.py"
_spec = importlib.util.spec_from_file_location("evaluate_planner_runs", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_envelope(selected_actions, version="0.35"):
    return {
        "planner_version": version,
        "inputs": {
            "exploration_offset": 0,
            "explain": False,
            "ledger": None,
            "max_actions": None,
            "policy": None,
            "portfolio_state": None,
            "top_k": 3,
        },
        "selected_actions": selected_actions,
        "selection_count": len(selected_actions),
        "artifacts": {"explain_artifact": None},
        "execution": {"executed": True, "status": "ok"},
    }


def _write_envelope(tmp_path, name, selected_actions):
    env = _make_envelope(selected_actions)
    path = tmp_path / name
    path.write_text(json.dumps(env, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return str(path)


# ---------------------------------------------------------------------------
# 1. evaluate_envelopes
# ---------------------------------------------------------------------------

class TestEvaluateEnvelopes:
    def test_empty_list_returns_zero_count(self):
        result = _mod.evaluate_envelopes([])
        assert result["envelope_count"] == 0

    def test_empty_list_identical_true(self):
        result = _mod.evaluate_envelopes([])
        assert result["identical"] is True

    def test_empty_list_no_ordering_diff(self):
        result = _mod.evaluate_envelopes([])
        assert result["ordering_differences"] is False

    def test_empty_list_empty_runs(self):
        result = _mod.evaluate_envelopes([])
        assert result["runs"] == []

    def test_single_envelope_identical(self):
        env = _make_envelope(["repo_insights_example"])
        result = _mod.evaluate_envelopes([env])
        assert result["identical"] is True
        assert result["envelope_count"] == 1

    def test_two_matching_envelopes_identical(self):
        env = _make_envelope(["repo_insights_example", "build_portfolio_dashboard"])
        result = _mod.evaluate_envelopes([env, env])
        assert result["identical"] is True

    def test_different_envelopes_not_identical(self):
        env_a = _make_envelope(["repo_insights_example"])
        env_b = _make_envelope(["build_portfolio_dashboard"])
        result = _mod.evaluate_envelopes([env_a, env_b])
        assert result["identical"] is False

    def test_ordering_difference_detected(self):
        env_a = _make_envelope(["repo_insights_example", "build_portfolio_dashboard"])
        env_b = _make_envelope(["build_portfolio_dashboard", "repo_insights_example"])
        result = _mod.evaluate_envelopes([env_a, env_b])
        assert result["identical"] is False
        assert result["ordering_differences"] is True

    def test_ordering_differences_false_when_identical(self):
        env = _make_envelope(["repo_insights_example"])
        result = _mod.evaluate_envelopes([env, env])
        assert result["ordering_differences"] is False

    def test_ordering_differences_false_when_completely_different(self):
        """Entirely different sets → not an ordering difference."""
        env_a = _make_envelope(["repo_insights_example"])
        env_b = _make_envelope(["intelligence_layer_example"])
        result = _mod.evaluate_envelopes([env_a, env_b])
        assert result["ordering_differences"] is False

    def test_runs_count_matches_input(self):
        envs = [_make_envelope(["repo_insights_example"]) for _ in range(4)]
        result = _mod.evaluate_envelopes(envs)
        assert len(result["runs"]) == 4

    def test_runs_contain_selected_actions(self):
        env = _make_envelope(["repo_insights_example"])
        result = _mod.evaluate_envelopes([env])
        assert result["runs"][0]["selected_actions"] == ["repo_insights_example"]

    def test_runs_contain_selection_count(self):
        env = _make_envelope(["repo_insights_example", "build_portfolio_dashboard"])
        result = _mod.evaluate_envelopes([env])
        assert result["runs"][0]["selection_count"] == 2

    def test_runs_contain_planner_version(self):
        env = _make_envelope(["repo_insights_example"])
        result = _mod.evaluate_envelopes([env])
        assert result["runs"][0]["planner_version"] == "0.35"

    def test_runs_indexed_in_order(self):
        envs = [_make_envelope([]) for _ in range(3)]
        result = _mod.evaluate_envelopes(envs)
        for i, run in enumerate(result["runs"]):
            assert run["index"] == i

    def test_three_matching_envelopes_identical(self):
        env = _make_envelope(["a", "b", "c"])
        result = _mod.evaluate_envelopes([env, env, env])
        assert result["identical"] is True

    def test_three_envelopes_one_different(self):
        env_same = _make_envelope(["repo_insights_example"])
        env_diff = _make_envelope(["build_portfolio_dashboard"])
        result = _mod.evaluate_envelopes([env_same, env_same, env_diff])
        assert result["identical"] is False

    def test_empty_selected_actions_identical(self):
        env = _make_envelope([])
        result = _mod.evaluate_envelopes([env, env])
        assert result["identical"] is True

    def test_result_is_deterministic(self):
        env_a = _make_envelope(["repo_insights_example"])
        env_b = _make_envelope(["build_portfolio_dashboard"])
        r1 = _mod.evaluate_envelopes([env_a, env_b])
        r2 = _mod.evaluate_envelopes([env_a, env_b])
        assert r1 == r2


# ---------------------------------------------------------------------------
# 2. load_envelope
# ---------------------------------------------------------------------------

class TestLoadEnvelope:
    def test_loads_valid_file(self, tmp_path):
        path = _write_envelope(tmp_path, "env.json", ["repo_insights_example"])
        loaded = _mod.load_envelope(path)
        assert loaded["selected_actions"] == ["repo_insights_example"]

    def test_loads_planner_version(self, tmp_path):
        path = _write_envelope(tmp_path, "env.json", [])
        loaded = _mod.load_envelope(path)
        assert loaded["planner_version"] == "0.35"

    def test_nonexistent_file_raises(self, tmp_path):
        with pytest.raises(Exception):
            _mod.load_envelope(str(tmp_path / "does_not_exist.json"))

    def test_malformed_json_raises(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{not valid", encoding="utf-8")
        with pytest.raises(Exception):
            _mod.load_envelope(str(bad))


# ---------------------------------------------------------------------------
# 3. main() CLI
# ---------------------------------------------------------------------------

class TestMainCLI:
    def test_outputs_json_to_stdout(self, tmp_path, capsys):
        p = _write_envelope(tmp_path, "env.json", ["repo_insights_example"])
        _mod.main([p])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert "envelope_count" in data

    def test_summary_fields_present(self, tmp_path, capsys):
        p = _write_envelope(tmp_path, "env.json", ["repo_insights_example"])
        _mod.main([p])
        data = json.loads(capsys.readouterr().out)
        for field in ("envelope_count", "identical", "ordering_differences", "runs"):
            assert field in data

    def test_writes_to_output_file(self, tmp_path):
        p = _write_envelope(tmp_path, "env.json", ["repo_insights_example"])
        out_file = tmp_path / "summary.json"
        _mod.main([p, "--output", str(out_file)])
        data = json.loads(out_file.read_text(encoding="utf-8"))
        assert data["envelope_count"] == 1

    def test_no_args_exits_with_error(self):
        with pytest.raises(SystemExit):
            _mod.main([])

    def test_two_matching_envelopes_identical(self, tmp_path, capsys):
        p1 = _write_envelope(tmp_path, "e1.json", ["repo_insights_example"])
        p2 = _write_envelope(tmp_path, "e2.json", ["repo_insights_example"])
        _mod.main([p1, p2])
        data = json.loads(capsys.readouterr().out)
        assert data["identical"] is True

    def test_two_different_envelopes_not_identical(self, tmp_path, capsys):
        p1 = _write_envelope(tmp_path, "e1.json", ["repo_insights_example"])
        p2 = _write_envelope(tmp_path, "e2.json", ["build_portfolio_dashboard"])
        _mod.main([p1, p2])
        data = json.loads(capsys.readouterr().out)
        assert data["identical"] is False

    def test_ordering_difference_detected_via_cli(self, tmp_path, capsys):
        p1 = _write_envelope(tmp_path, "e1.json",
                              ["repo_insights_example", "build_portfolio_dashboard"])
        p2 = _write_envelope(tmp_path, "e2.json",
                              ["build_portfolio_dashboard", "repo_insights_example"])
        _mod.main([p1, p2])
        data = json.loads(capsys.readouterr().out)
        assert data["ordering_differences"] is True

    def test_output_deterministic_repeated_calls(self, tmp_path):
        p = _write_envelope(tmp_path, "env.json", ["repo_insights_example"])
        out1 = tmp_path / "out1.json"
        out2 = tmp_path / "out2.json"
        _mod.main([p, "--output", str(out1)])
        _mod.main([p, "--output", str(out2)])
        assert out1.read_text(encoding="utf-8") == out2.read_text(encoding="utf-8")

    def test_envelope_count_correct(self, tmp_path, capsys):
        paths = [_write_envelope(tmp_path, f"e{i}.json", []) for i in range(3)]
        _mod.main(paths)
        data = json.loads(capsys.readouterr().out)
        assert data["envelope_count"] == 3

    def test_single_envelope_stdout(self, tmp_path, capsys):
        p = _write_envelope(tmp_path, "env.json", [])
        _mod.main([p])
        data = json.loads(capsys.readouterr().out)
        assert data["envelope_count"] == 1
        assert data["identical"] is True
