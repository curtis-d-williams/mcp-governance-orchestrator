# SPDX-License-Identifier: MIT
"""Tests for v0.39 experiment report generator.

Covers:
- deterministic report generation
- correct aggregation of evaluation summaries
- markdown output matches JSON content
- works with and without policy_sweep_results.json
- existing experiment tests unchanged
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_SCRIPT = _REPO_ROOT / "scripts" / "generate_experiment_report.py"
_spec = importlib.util.spec_from_file_location("generate_experiment_report", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_EVAL_SUMMARY_IDENTICAL = {
    "envelope_count": 3,
    "identical": True,
    "ordering_differences": False,
    "runs": [
        {"index": 0, "selected_actions": ["repo_insights_example"], "selection_count": 1, "inputs": {}, "planner_version": "0.35"},
        {"index": 1, "selected_actions": ["repo_insights_example"], "selection_count": 1, "inputs": {}, "planner_version": "0.35"},
        {"index": 2, "selected_actions": ["repo_insights_example"], "selection_count": 1, "inputs": {}, "planner_version": "0.35"},
    ],
}

_EVAL_SUMMARY_DIFFERING = {
    "envelope_count": 2,
    "identical": False,
    "ordering_differences": False,
    "runs": [
        {"index": 0, "selected_actions": ["repo_insights_example"], "selection_count": 1, "inputs": {}, "planner_version": "0.35"},
        {"index": 1, "selected_actions": ["build_portfolio_dashboard"], "selection_count": 1, "inputs": {}, "planner_version": "0.35"},
    ],
}

_EXPERIMENT_RESULTS_IDENTICAL = {
    "run_count": 3,
    "envelope_paths": ["p1.json", "p2.json", "p3.json"],
    "evaluation_summary": _EVAL_SUMMARY_IDENTICAL,
}

_EXPERIMENT_RESULTS_DIFFERING = {
    "run_count": 2,
    "envelope_paths": ["p1.json", "p2.json"],
    "evaluation_summary": _EVAL_SUMMARY_DIFFERING,
}

_SWEEP_DATA = {
    "sweep_count": 2,
    "entries": [
        {
            "name": "baseline",
            "weights": {},
            "experiment_results_path": "sweep_baseline_experiment_results.json",
            "evaluation_summary": _EVAL_SUMMARY_IDENTICAL,
            "run_envelope_paths": ["e1.json", "e2.json", "e3.json"],
        },
        {
            "name": "completeness_high",
            "weights": {"artifact_completeness": 2.0},
            "experiment_results_path": "sweep_completeness_high_experiment_results.json",
            "evaluation_summary": _EVAL_SUMMARY_DIFFERING,
            "run_envelope_paths": ["e1.json", "e2.json"],
        },
    ],
}


def _write_json(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# 1. build_report — top-level structure
# ---------------------------------------------------------------------------

class TestBuildReport:
    def test_report_has_report_version(self):
        report = _mod.build_report(_EXPERIMENT_RESULTS_IDENTICAL)
        assert report["report_version"] == _mod.REPORT_VERSION

    def test_report_has_run_count(self):
        report = _mod.build_report(_EXPERIMENT_RESULTS_IDENTICAL)
        assert report["run_count"] == 3

    def test_report_has_stability(self):
        report = _mod.build_report(_EXPERIMENT_RESULTS_IDENTICAL)
        assert "stability" in report

    def test_report_has_action_selection(self):
        report = _mod.build_report(_EXPERIMENT_RESULTS_IDENTICAL)
        assert "action_selection" in report

    def test_report_no_sweep_key_when_none(self):
        report = _mod.build_report(_EXPERIMENT_RESULTS_IDENTICAL)
        assert "policy_sweep" not in report

    def test_report_has_sweep_key_when_provided(self):
        report = _mod.build_report(_EXPERIMENT_RESULTS_IDENTICAL, _SWEEP_DATA)
        assert "policy_sweep" in report


# ---------------------------------------------------------------------------
# 2. Stability metrics
# ---------------------------------------------------------------------------

class TestStabilityMetrics:
    def test_identical_true_propagated(self):
        report = _mod.build_report(_EXPERIMENT_RESULTS_IDENTICAL)
        assert report["stability"]["identical"] is True

    def test_identical_false_propagated(self):
        report = _mod.build_report(_EXPERIMENT_RESULTS_DIFFERING)
        assert report["stability"]["identical"] is False

    def test_ordering_differences_false(self):
        report = _mod.build_report(_EXPERIMENT_RESULTS_IDENTICAL)
        assert report["stability"]["ordering_differences"] is False

    def test_envelope_count_correct(self):
        report = _mod.build_report(_EXPERIMENT_RESULTS_IDENTICAL)
        assert report["stability"]["envelope_count"] == 3

    def test_envelope_count_from_differing(self):
        report = _mod.build_report(_EXPERIMENT_RESULTS_DIFFERING)
        assert report["stability"]["envelope_count"] == 2


# ---------------------------------------------------------------------------
# 3. Action selection consistency
# ---------------------------------------------------------------------------

class TestActionConsistency:
    def test_unique_action_sets_identical_runs(self):
        report = _mod.build_report(_EXPERIMENT_RESULTS_IDENTICAL)
        assert report["action_selection"]["unique_action_sets"] == 1

    def test_unique_action_sets_differing_runs(self):
        report = _mod.build_report(_EXPERIMENT_RESULTS_DIFFERING)
        assert report["action_selection"]["unique_action_sets"] == 2

    def test_most_common_actions_identical(self):
        report = _mod.build_report(_EXPERIMENT_RESULTS_IDENTICAL)
        assert report["action_selection"]["most_common_actions"] == ["repo_insights_example"]

    def test_most_common_actions_is_list(self):
        report = _mod.build_report(_EXPERIMENT_RESULTS_IDENTICAL)
        assert isinstance(report["action_selection"]["most_common_actions"], list)

    def test_most_common_actions_empty_runs(self):
        ev = {"envelope_count": 0, "identical": True, "ordering_differences": False, "runs": []}
        result = _EXPERIMENT_RESULTS_IDENTICAL.copy()
        result = {"run_count": 0, "envelope_paths": [], "evaluation_summary": ev}
        report = _mod.build_report(result)
        assert report["action_selection"]["most_common_actions"] == []

    def test_most_common_picks_highest_count(self):
        # 3 runs with "repo_insights_example", 1 run with "build_portfolio_dashboard"
        ev = {
            "envelope_count": 4,
            "identical": False,
            "ordering_differences": False,
            "runs": [
                {"index": 0, "selected_actions": ["repo_insights_example"], "selection_count": 1, "inputs": {}, "planner_version": "0.35"},
                {"index": 1, "selected_actions": ["repo_insights_example"], "selection_count": 1, "inputs": {}, "planner_version": "0.35"},
                {"index": 2, "selected_actions": ["repo_insights_example"], "selection_count": 1, "inputs": {}, "planner_version": "0.35"},
                {"index": 3, "selected_actions": ["build_portfolio_dashboard"], "selection_count": 1, "inputs": {}, "planner_version": "0.35"},
            ],
        }
        data = {"run_count": 4, "envelope_paths": [], "evaluation_summary": ev}
        report = _mod.build_report(data)
        assert report["action_selection"]["most_common_actions"] == ["repo_insights_example"]

    def test_consistency_deterministic_repeated_calls(self):
        r1 = _mod.build_report(_EXPERIMENT_RESULTS_IDENTICAL)
        r2 = _mod.build_report(_EXPERIMENT_RESULTS_IDENTICAL)
        assert r1["action_selection"] == r2["action_selection"]


# ---------------------------------------------------------------------------
# 4. Policy sweep summary
# ---------------------------------------------------------------------------

class TestSweepSummary:
    def test_sweep_count_correct(self):
        report = _mod.build_report(_EXPERIMENT_RESULTS_IDENTICAL, _SWEEP_DATA)
        assert report["policy_sweep"]["sweep_count"] == 2

    def test_sweep_entries_length(self):
        report = _mod.build_report(_EXPERIMENT_RESULTS_IDENTICAL, _SWEEP_DATA)
        assert len(report["policy_sweep"]["entries"]) == 2

    def test_sweep_entry_has_name(self):
        report = _mod.build_report(_EXPERIMENT_RESULTS_IDENTICAL, _SWEEP_DATA)
        assert report["policy_sweep"]["entries"][0]["name"] == "baseline"

    def test_sweep_entry_has_identical(self):
        report = _mod.build_report(_EXPERIMENT_RESULTS_IDENTICAL, _SWEEP_DATA)
        assert report["policy_sweep"]["entries"][0]["identical"] is True

    def test_sweep_entry_has_unique_action_sets(self):
        report = _mod.build_report(_EXPERIMENT_RESULTS_IDENTICAL, _SWEEP_DATA)
        assert "unique_action_sets" in report["policy_sweep"]["entries"][0]

    def test_sweep_entry_most_common_actions(self):
        report = _mod.build_report(_EXPERIMENT_RESULTS_IDENTICAL, _SWEEP_DATA)
        assert report["policy_sweep"]["entries"][0]["most_common_actions"] == ["repo_insights_example"]

    def test_sweep_entry_envelope_count(self):
        report = _mod.build_report(_EXPERIMENT_RESULTS_IDENTICAL, _SWEEP_DATA)
        assert report["policy_sweep"]["entries"][0]["envelope_count"] == 3

    def test_sweep_entry_weights_preserved(self):
        report = _mod.build_report(_EXPERIMENT_RESULTS_IDENTICAL, _SWEEP_DATA)
        assert report["policy_sweep"]["entries"][1]["weights"] == {"artifact_completeness": 2.0}


# ---------------------------------------------------------------------------
# 5. Markdown rendering — content matches JSON
# ---------------------------------------------------------------------------

class TestRenderMarkdown:
    def test_markdown_contains_run_count(self):
        report = _mod.build_report(_EXPERIMENT_RESULTS_IDENTICAL)
        md = _mod.render_markdown(report)
        assert "Run count: 3" in md

    def test_markdown_contains_identical(self):
        report = _mod.build_report(_EXPERIMENT_RESULTS_IDENTICAL)
        md = _mod.render_markdown(report)
        assert "Identical runs: True" in md

    def test_markdown_contains_unique_action_sets(self):
        report = _mod.build_report(_EXPERIMENT_RESULTS_IDENTICAL)
        md = _mod.render_markdown(report)
        assert "Unique action sets: 1" in md

    def test_markdown_contains_most_common_action(self):
        report = _mod.build_report(_EXPERIMENT_RESULTS_IDENTICAL)
        md = _mod.render_markdown(report)
        assert "repo_insights_example" in md

    def test_markdown_no_sweep_section_without_sweep(self):
        report = _mod.build_report(_EXPERIMENT_RESULTS_IDENTICAL)
        md = _mod.render_markdown(report)
        assert "Policy Sweep" not in md

    def test_markdown_has_sweep_section_with_sweep(self):
        report = _mod.build_report(_EXPERIMENT_RESULTS_IDENTICAL, _SWEEP_DATA)
        md = _mod.render_markdown(report)
        assert "Policy Sweep Summary" in md

    def test_markdown_sweep_table_has_entry_names(self):
        report = _mod.build_report(_EXPERIMENT_RESULTS_IDENTICAL, _SWEEP_DATA)
        md = _mod.render_markdown(report)
        assert "baseline" in md
        assert "completeness_high" in md

    def test_markdown_sweep_count_in_output(self):
        report = _mod.build_report(_EXPERIMENT_RESULTS_IDENTICAL, _SWEEP_DATA)
        md = _mod.render_markdown(report)
        assert "Sweep count: 2" in md

    def test_markdown_envelope_count_consistent_with_json(self):
        report = _mod.build_report(_EXPERIMENT_RESULTS_IDENTICAL)
        md = _mod.render_markdown(report)
        envelope_count = report["stability"]["envelope_count"]
        assert f"Envelope count: {envelope_count}" in md

    def test_markdown_ends_with_newline(self):
        report = _mod.build_report(_EXPERIMENT_RESULTS_IDENTICAL)
        md = _mod.render_markdown(report)
        assert md.endswith("\n")


# ---------------------------------------------------------------------------
# 6. generate_report — file I/O
# ---------------------------------------------------------------------------

class TestGenerateReport:
    def test_json_file_created(self, tmp_path):
        er = _write_json(tmp_path / "exp.json", _EXPERIMENT_RESULTS_IDENTICAL)
        out_json = tmp_path / "report.json"
        out_md = tmp_path / "report.md"
        _mod.generate_report(str(er), output_json_path=str(out_json), output_md_path=str(out_md))
        assert out_json.exists()

    def test_md_file_created(self, tmp_path):
        er = _write_json(tmp_path / "exp.json", _EXPERIMENT_RESULTS_IDENTICAL)
        out_json = tmp_path / "report.json"
        out_md = tmp_path / "report.md"
        _mod.generate_report(str(er), output_json_path=str(out_json), output_md_path=str(out_md))
        assert out_md.exists()

    def test_json_file_is_valid_json(self, tmp_path):
        er = _write_json(tmp_path / "exp.json", _EXPERIMENT_RESULTS_IDENTICAL)
        out_json = tmp_path / "report.json"
        out_md = tmp_path / "report.md"
        _mod.generate_report(str(er), output_json_path=str(out_json), output_md_path=str(out_md))
        data = json.loads(out_json.read_text(encoding="utf-8"))
        assert isinstance(data, dict)

    def test_json_contains_run_count(self, tmp_path):
        er = _write_json(tmp_path / "exp.json", _EXPERIMENT_RESULTS_IDENTICAL)
        out_json = tmp_path / "report.json"
        out_md = tmp_path / "report.md"
        _mod.generate_report(str(er), output_json_path=str(out_json), output_md_path=str(out_md))
        data = json.loads(out_json.read_text(encoding="utf-8"))
        assert data["run_count"] == 3

    def test_json_path_returned(self, tmp_path):
        er = _write_json(tmp_path / "exp.json", _EXPERIMENT_RESULTS_IDENTICAL)
        out_json = tmp_path / "report.json"
        out_md = tmp_path / "report.md"
        result = _mod.generate_report(str(er), output_json_path=str(out_json), output_md_path=str(out_md))
        assert result["json_path"] == str(out_json)

    def test_md_path_returned(self, tmp_path):
        er = _write_json(tmp_path / "exp.json", _EXPERIMENT_RESULTS_IDENTICAL)
        out_json = tmp_path / "report.json"
        out_md = tmp_path / "report.md"
        result = _mod.generate_report(str(er), output_json_path=str(out_json), output_md_path=str(out_md))
        assert result["md_path"] == str(out_md)

    def test_report_dict_returned(self, tmp_path):
        er = _write_json(tmp_path / "exp.json", _EXPERIMENT_RESULTS_IDENTICAL)
        out_json = tmp_path / "report.json"
        out_md = tmp_path / "report.md"
        result = _mod.generate_report(str(er), output_json_path=str(out_json), output_md_path=str(out_md))
        assert isinstance(result["report"], dict)

    def test_nested_output_dirs_created(self, tmp_path):
        er = _write_json(tmp_path / "exp.json", _EXPERIMENT_RESULTS_IDENTICAL)
        out_json = tmp_path / "a" / "b" / "report.json"
        out_md = tmp_path / "a" / "b" / "report.md"
        _mod.generate_report(str(er), output_json_path=str(out_json), output_md_path=str(out_md))
        assert out_json.exists()
        assert out_md.exists()


# ---------------------------------------------------------------------------
# 7. Without policy sweep
# ---------------------------------------------------------------------------

class TestWithoutPolicySweep:
    def test_no_sweep_arg_omits_sweep_from_json(self, tmp_path):
        er = _write_json(tmp_path / "exp.json", _EXPERIMENT_RESULTS_IDENTICAL)
        out_json = tmp_path / "report.json"
        out_md = tmp_path / "report.md"
        _mod.generate_report(str(er), output_json_path=str(out_json), output_md_path=str(out_md))
        data = json.loads(out_json.read_text(encoding="utf-8"))
        assert "policy_sweep" not in data

    def test_no_sweep_arg_omits_sweep_from_md(self, tmp_path):
        er = _write_json(tmp_path / "exp.json", _EXPERIMENT_RESULTS_IDENTICAL)
        out_json = tmp_path / "report.json"
        out_md = tmp_path / "report.md"
        _mod.generate_report(str(er), output_json_path=str(out_json), output_md_path=str(out_md))
        md = out_md.read_text(encoding="utf-8")
        assert "Policy Sweep" not in md

    def test_no_sweep_has_stability_section(self, tmp_path):
        er = _write_json(tmp_path / "exp.json", _EXPERIMENT_RESULTS_IDENTICAL)
        out_md = tmp_path / "report.md"
        _mod.generate_report(str(er), output_json_path=str(tmp_path / "r.json"), output_md_path=str(out_md))
        md = out_md.read_text(encoding="utf-8")
        assert "## Summary" in md

    def test_no_sweep_has_action_section(self, tmp_path):
        er = _write_json(tmp_path / "exp.json", _EXPERIMENT_RESULTS_IDENTICAL)
        out_md = tmp_path / "report.md"
        _mod.generate_report(str(er), output_json_path=str(tmp_path / "r.json"), output_md_path=str(out_md))
        md = out_md.read_text(encoding="utf-8")
        assert "## Action Selection Consistency" in md


# ---------------------------------------------------------------------------
# 8. With policy sweep
# ---------------------------------------------------------------------------

class TestWithPolicySweep:
    def test_sweep_included_in_json(self, tmp_path):
        er = _write_json(tmp_path / "exp.json", _EXPERIMENT_RESULTS_IDENTICAL)
        sw = _write_json(tmp_path / "sweep.json", _SWEEP_DATA)
        out_json = tmp_path / "report.json"
        out_md = tmp_path / "report.md"
        _mod.generate_report(str(er), sweep_path=str(sw), output_json_path=str(out_json), output_md_path=str(out_md))
        data = json.loads(out_json.read_text(encoding="utf-8"))
        assert "policy_sweep" in data
        assert data["policy_sweep"]["sweep_count"] == 2

    def test_sweep_section_in_md(self, tmp_path):
        er = _write_json(tmp_path / "exp.json", _EXPERIMENT_RESULTS_IDENTICAL)
        sw = _write_json(tmp_path / "sweep.json", _SWEEP_DATA)
        out_md = tmp_path / "report.md"
        _mod.generate_report(str(er), sweep_path=str(sw), output_json_path=str(tmp_path / "r.json"), output_md_path=str(out_md))
        md = out_md.read_text(encoding="utf-8")
        assert "Policy Sweep Summary" in md

    def test_sweep_entry_names_in_md(self, tmp_path):
        er = _write_json(tmp_path / "exp.json", _EXPERIMENT_RESULTS_IDENTICAL)
        sw = _write_json(tmp_path / "sweep.json", _SWEEP_DATA)
        out_md = tmp_path / "report.md"
        _mod.generate_report(str(er), sweep_path=str(sw), output_json_path=str(tmp_path / "r.json"), output_md_path=str(out_md))
        md = out_md.read_text(encoding="utf-8")
        assert "baseline" in md
        assert "completeness_high" in md


# ---------------------------------------------------------------------------
# 9. Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_build_report_is_deterministic(self):
        r1 = _mod.build_report(_EXPERIMENT_RESULTS_IDENTICAL)
        r2 = _mod.build_report(_EXPERIMENT_RESULTS_IDENTICAL)
        assert r1 == r2

    def test_render_markdown_is_deterministic(self):
        report = _mod.build_report(_EXPERIMENT_RESULTS_IDENTICAL)
        md1 = _mod.render_markdown(report)
        md2 = _mod.render_markdown(report)
        assert md1 == md2

    def test_generate_report_json_is_byte_identical(self, tmp_path):
        er = _write_json(tmp_path / "exp.json", _EXPERIMENT_RESULTS_IDENTICAL)
        out_json = tmp_path / "report.json"
        out_md = tmp_path / "report.md"
        _mod.generate_report(str(er), output_json_path=str(out_json), output_md_path=str(out_md))
        first = out_json.read_bytes()
        _mod.generate_report(str(er), output_json_path=str(out_json), output_md_path=str(out_md))
        second = out_json.read_bytes()
        assert first == second

    def test_generate_report_md_is_byte_identical(self, tmp_path):
        er = _write_json(tmp_path / "exp.json", _EXPERIMENT_RESULTS_IDENTICAL)
        out_json = tmp_path / "report.json"
        out_md = tmp_path / "report.md"
        _mod.generate_report(str(er), output_json_path=str(out_json), output_md_path=str(out_md))
        first = out_md.read_bytes()
        _mod.generate_report(str(er), output_json_path=str(out_json), output_md_path=str(out_md))
        second = out_md.read_bytes()
        assert first == second

    def test_build_report_with_sweep_is_deterministic(self):
        r1 = _mod.build_report(_EXPERIMENT_RESULTS_IDENTICAL, _SWEEP_DATA)
        r2 = _mod.build_report(_EXPERIMENT_RESULTS_IDENTICAL, _SWEEP_DATA)
        assert r1 == r2


# ---------------------------------------------------------------------------
# 10. main() CLI
# ---------------------------------------------------------------------------

class TestMainCli:
    def test_main_requires_experiment_results(self, tmp_path):
        with pytest.raises(SystemExit):
            _mod.main([])

    def test_main_writes_json_and_md(self, tmp_path):
        er = _write_json(tmp_path / "exp.json", _EXPERIMENT_RESULTS_IDENTICAL)
        out_json = tmp_path / "report.json"
        out_md = tmp_path / "report.md"
        _mod.main([
            "--experiment-results", str(er),
            "--output-json", str(out_json),
            "--output-md", str(out_md),
        ])
        assert out_json.exists()
        assert out_md.exists()

    def test_main_with_sweep(self, tmp_path):
        er = _write_json(tmp_path / "exp.json", _EXPERIMENT_RESULTS_IDENTICAL)
        sw = _write_json(tmp_path / "sweep.json", _SWEEP_DATA)
        out_json = tmp_path / "report.json"
        out_md = tmp_path / "report.md"
        _mod.main([
            "--experiment-results", str(er),
            "--policy-sweep", str(sw),
            "--output-json", str(out_json),
            "--output-md", str(out_md),
        ])
        data = json.loads(out_json.read_text(encoding="utf-8"))
        assert "policy_sweep" in data

    def test_main_without_sweep(self, tmp_path):
        er = _write_json(tmp_path / "exp.json", _EXPERIMENT_RESULTS_IDENTICAL)
        out_json = tmp_path / "report.json"
        out_md = tmp_path / "report.md"
        _mod.main([
            "--experiment-results", str(er),
            "--output-json", str(out_json),
            "--output-md", str(out_md),
        ])
        data = json.loads(out_json.read_text(encoding="utf-8"))
        assert "policy_sweep" not in data


# ---------------------------------------------------------------------------
# 11. Existing experiment tests unchanged (smoke check)
# ---------------------------------------------------------------------------

class TestExistingTestsUnchanged:
    def test_run_planner_experiment_importable(self):
        from scripts.run_planner_experiment import run_experiment
        assert callable(run_experiment)

    def test_evaluate_envelopes_importable(self):
        from scripts.evaluate_planner_runs import evaluate_envelopes
        assert callable(evaluate_envelopes)

    def test_planner_version_unchanged(self):
        from scripts.claude_dynamic_planner_loop import PLANNER_VERSION
        assert PLANNER_VERSION == "0.35"

    def test_run_policy_sweep_importable(self):
        from scripts.run_planner_experiment import run_policy_sweep
        assert callable(run_policy_sweep)

    def test_report_version_is_0_39(self):
        assert _mod.REPORT_VERSION == "0.39"
