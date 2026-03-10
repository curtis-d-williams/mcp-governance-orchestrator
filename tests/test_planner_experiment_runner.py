# SPDX-License-Identifier: MIT
"""Tests for v0.36 planner experiment runner.

Covers:
- correct number of envelopes created
- deterministic naming (planner_run_envelope_run{n}.json)
- evaluation script integration (evaluation_summary present and correct)
- existing planner tests unaffected (no planner module modified)
- experiment_results.json structure
- run_count recorded correctly
- envelope_paths list matches created files
- --runs validation (< 1 rejected)
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_SCRIPT = _REPO_ROOT / "scripts" / "run_planner_experiment.py"
_spec = importlib.util.spec_from_file_location("run_planner_experiment", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MINIMAL_ENVELOPE = {
    "planner_version": "0.35",
    "inputs": {
        "exploration_offset": 0,
        "explain": False,
        "ledger": None,
        "max_actions": None,
        "policy": None,
        "portfolio_state": None,
        "top_k": 3,
    },
    "selected_actions": ["repo_insights_example"],
    "selection_count": 1,
    "artifacts": {"explain_artifact": None},
    "execution": {"executed": True, "status": "ok"},
}


def _make_fake_planner(actions=None):
    """Return a fake planner main that writes a minimal deterministic envelope."""
    if actions is None:
        actions = ["repo_insights_example"]

    def fake_main(argv):
        for i, arg in enumerate(argv):
            if arg == "--run-envelope" and i + 1 < len(argv):
                ep = Path(argv[i + 1])
                ep.parent.mkdir(parents=True, exist_ok=True)
                envelope = dict(_MINIMAL_ENVELOPE)
                envelope["selected_actions"] = list(actions)
                envelope["selection_count"] = len(actions)
                ep.write_text(
                    json.dumps(envelope, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                break

    return fake_main


class _FakeArgs:
    runs = 1
    portfolio_state = None
    ledger = None
    policy = None
    top_k = 3
    exploration_offset = 0
    max_actions = None
    explain = False
    output = "experiment_results.json"


def _make_args(**kwargs):
    args = _FakeArgs()
    for k, v in kwargs.items():
        setattr(args, k, v)
    return args


# ---------------------------------------------------------------------------
# 1. Correct number of envelopes created
# ---------------------------------------------------------------------------

class TestEnvelopeCount:
    def test_three_runs_creates_three_envelopes(self, tmp_path):
        output = tmp_path / "results.json"
        args = _make_args(runs=3, output=str(output))
        _mod.run_experiment(args, planner_main=_make_fake_planner())
        envelopes = sorted(tmp_path.glob("planner_run_envelope_run*.json"))
        assert len(envelopes) == 3

    def test_one_run_creates_one_envelope(self, tmp_path):
        output = tmp_path / "results.json"
        args = _make_args(runs=1, output=str(output))
        _mod.run_experiment(args, planner_main=_make_fake_planner())
        envelopes = list(tmp_path.glob("planner_run_envelope_run*.json"))
        assert len(envelopes) == 1

    def test_five_runs_creates_five_envelopes(self, tmp_path):
        output = tmp_path / "results.json"
        args = _make_args(runs=5, output=str(output))
        _mod.run_experiment(args, planner_main=_make_fake_planner())
        envelopes = list(tmp_path.glob("planner_run_envelope_run*.json"))
        assert len(envelopes) == 5

    def test_envelope_count_matches_run_count_in_result(self, tmp_path):
        output = tmp_path / "results.json"
        args = _make_args(runs=4, output=str(output))
        result = _mod.run_experiment(args, planner_main=_make_fake_planner())
        assert len(result["envelope_paths"]) == 4


# ---------------------------------------------------------------------------
# 2. Deterministic naming
# ---------------------------------------------------------------------------

class TestDeterministicNaming:
    def test_envelope_name_helper_run1(self):
        assert _mod._envelope_name(1) == "planner_run_envelope_run1.json"

    def test_envelope_name_helper_run2(self):
        assert _mod._envelope_name(2) == "planner_run_envelope_run2.json"

    def test_envelope_name_helper_run10(self):
        assert _mod._envelope_name(10) == "planner_run_envelope_run10.json"

    def test_envelope_files_named_correctly(self, tmp_path):
        output = tmp_path / "results.json"
        args = _make_args(runs=3, output=str(output))
        _mod.run_experiment(args, planner_main=_make_fake_planner())
        for i in range(1, 4):
            assert (tmp_path / f"planner_run_envelope_run{i}.json").exists()

    def test_envelope_paths_in_result_match_naming(self, tmp_path):
        output = tmp_path / "results.json"
        args = _make_args(runs=2, output=str(output))
        result = _mod.run_experiment(args, planner_main=_make_fake_planner())
        for i, ep in enumerate(result["envelope_paths"], start=1):
            assert ep.endswith(f"planner_run_envelope_run{i}.json")

    def test_second_experiment_same_output_is_deterministic(self, tmp_path):
        output = tmp_path / "results.json"
        args = _make_args(runs=2, output=str(output))
        result_a = _mod.run_experiment(args, planner_main=_make_fake_planner())
        result_b = _mod.run_experiment(args, planner_main=_make_fake_planner())
        assert result_a["envelope_paths"] == result_b["envelope_paths"]


# ---------------------------------------------------------------------------
# 3. Evaluation script integration
# ---------------------------------------------------------------------------

class TestEvaluationIntegration:
    def test_evaluation_summary_present(self, tmp_path):
        output = tmp_path / "results.json"
        args = _make_args(runs=2, output=str(output))
        result = _mod.run_experiment(args, planner_main=_make_fake_planner())
        assert "evaluation_summary" in result

    def test_evaluation_summary_envelope_count(self, tmp_path):
        output = tmp_path / "results.json"
        args = _make_args(runs=3, output=str(output))
        result = _mod.run_experiment(args, planner_main=_make_fake_planner())
        assert result["evaluation_summary"]["envelope_count"] == 3

    def test_identical_runs_flagged_as_identical(self, tmp_path):
        output = tmp_path / "results.json"
        args = _make_args(runs=3, output=str(output))
        result = _mod.run_experiment(args, planner_main=_make_fake_planner())
        assert result["evaluation_summary"]["identical"] is True

    def test_evaluation_summary_has_runs_list(self, tmp_path):
        output = tmp_path / "results.json"
        args = _make_args(runs=2, output=str(output))
        result = _mod.run_experiment(args, planner_main=_make_fake_planner())
        assert isinstance(result["evaluation_summary"]["runs"], list)
        assert len(result["evaluation_summary"]["runs"]) == 2

    def test_evaluation_summary_has_ordering_differences_key(self, tmp_path):
        output = tmp_path / "results.json"
        args = _make_args(runs=2, output=str(output))
        result = _mod.run_experiment(args, planner_main=_make_fake_planner())
        assert "ordering_differences" in result["evaluation_summary"]

    def test_differing_runs_not_identical(self, tmp_path):
        output = tmp_path / "results.json"
        call_count = [0]

        def varying_planner(argv):
            call_count[0] += 1
            actions = ["repo_insights_example"] if call_count[0] % 2 == 1 else ["build_portfolio_dashboard"]
            _make_fake_planner(actions)(argv)

        args = _make_args(runs=2, output=str(output))
        result = _mod.run_experiment(args, planner_main=varying_planner)
        assert result["evaluation_summary"]["identical"] is False


# ---------------------------------------------------------------------------
# 4. experiment_results.json written correctly
# ---------------------------------------------------------------------------

class TestExperimentResultsFile:
    def test_results_file_created(self, tmp_path):
        output = tmp_path / "results.json"
        args = _make_args(runs=1, output=str(output))
        _mod.run_experiment(args, planner_main=_make_fake_planner())
        assert output.exists()

    def test_results_file_is_valid_json(self, tmp_path):
        output = tmp_path / "results.json"
        args = _make_args(runs=1, output=str(output))
        _mod.run_experiment(args, planner_main=_make_fake_planner())
        data = json.loads(output.read_text(encoding="utf-8"))
        assert isinstance(data, dict)

    def test_results_file_has_run_count(self, tmp_path):
        output = tmp_path / "results.json"
        args = _make_args(runs=2, output=str(output))
        _mod.run_experiment(args, planner_main=_make_fake_planner())
        data = json.loads(output.read_text(encoding="utf-8"))
        assert data["run_count"] == 2

    def test_results_file_has_envelope_paths(self, tmp_path):
        output = tmp_path / "results.json"
        args = _make_args(runs=3, output=str(output))
        _mod.run_experiment(args, planner_main=_make_fake_planner())
        data = json.loads(output.read_text(encoding="utf-8"))
        assert isinstance(data["envelope_paths"], list)
        assert len(data["envelope_paths"]) == 3

    def test_results_file_has_evaluation_summary(self, tmp_path):
        output = tmp_path / "results.json"
        args = _make_args(runs=1, output=str(output))
        _mod.run_experiment(args, planner_main=_make_fake_planner())
        data = json.loads(output.read_text(encoding="utf-8"))
        assert "evaluation_summary" in data

    def test_results_file_in_nested_output_dir(self, tmp_path):
        output = tmp_path / "a" / "b" / "results.json"
        args = _make_args(runs=1, output=str(output))
        _mod.run_experiment(args, planner_main=_make_fake_planner())
        assert output.exists()

    def test_envelopes_colocated_with_results(self, tmp_path):
        output = tmp_path / "subdir" / "results.json"
        args = _make_args(runs=2, output=str(output))
        _mod.run_experiment(args, planner_main=_make_fake_planner())
        assert (tmp_path / "subdir" / "planner_run_envelope_run1.json").exists()
        assert (tmp_path / "subdir" / "planner_run_envelope_run2.json").exists()


# ---------------------------------------------------------------------------
# 5. Planner argv construction
# ---------------------------------------------------------------------------

class TestPlannerArgvConstruction:
    def test_run_envelope_in_argv(self, tmp_path):
        received = []

        def capture_argv(argv):
            received.append(list(argv))
            # Still write envelope so run_experiment doesn't fail
            _make_fake_planner()(argv)

        output = tmp_path / "results.json"
        args = _make_args(runs=1, output=str(output))
        _mod.run_experiment(args, planner_main=capture_argv)
        assert "--run-envelope" in received[0]

    def test_portfolio_state_passed_when_set(self, tmp_path):
        received = []

        def capture_argv(argv):
            received.append(list(argv))
            _make_fake_planner()(argv)

        state = tmp_path / "state.json"
        state.write_text("{}", encoding="utf-8")
        output = tmp_path / "results.json"
        args = _make_args(runs=1, output=str(output), portfolio_state=str(state))
        # Skip preflight: this test is about argv construction, not risk evaluation.
        _mod.run_experiment(args, planner_main=capture_argv,
                            risk_check_fn=lambda _a: None)
        assert "--portfolio-state" in received[0]

    def test_portfolio_state_absent_when_none(self, tmp_path):
        received = []

        def capture_argv(argv):
            received.append(list(argv))
            _make_fake_planner()(argv)

        output = tmp_path / "results.json"
        args = _make_args(runs=1, output=str(output), portfolio_state=None)
        _mod.run_experiment(args, planner_main=capture_argv)
        assert "--portfolio-state" not in received[0]

    def test_max_actions_passed_when_set(self, tmp_path):
        received = []

        def capture_argv(argv):
            received.append(list(argv))
            _make_fake_planner()(argv)

        output = tmp_path / "results.json"
        args = _make_args(runs=1, output=str(output), max_actions=2)
        _mod.run_experiment(args, planner_main=capture_argv)
        assert "--max-actions" in received[0]

    def test_explain_flag_passed_when_set(self, tmp_path):
        received = []

        def capture_argv(argv):
            received.append(list(argv))
            _make_fake_planner()(argv)

        output = tmp_path / "results.json"
        args = _make_args(runs=1, output=str(output), explain=True)
        _mod.run_experiment(args, planner_main=capture_argv)
        assert "--explain" in received[0]

    def test_explain_flag_absent_when_false(self, tmp_path):
        received = []

        def capture_argv(argv):
            received.append(list(argv))
            _make_fake_planner()(argv)

        output = tmp_path / "results.json"
        args = _make_args(runs=1, output=str(output), explain=False)
        _mod.run_experiment(args, planner_main=capture_argv)
        assert "--explain" not in received[0]

    def test_each_run_gets_unique_envelope_path(self, tmp_path):
        received = []

        def capture_argv(argv):
            received.append(list(argv))
            _make_fake_planner()(argv)

        output = tmp_path / "results.json"
        args = _make_args(runs=3, output=str(output))
        _mod.run_experiment(args, planner_main=capture_argv)
        envelope_paths = []
        for argv in received:
            idx = argv.index("--run-envelope")
            envelope_paths.append(argv[idx + 1])
        assert len(set(envelope_paths)) == 3


# ---------------------------------------------------------------------------
# 6. main() CLI validation
# ---------------------------------------------------------------------------

class TestMainCliValidation:
    def test_runs_zero_rejected(self, tmp_path):
        output = tmp_path / "results.json"
        with pytest.raises(SystemExit):
            _mod.main(["--runs", "0", "--output", str(output)])

    def test_runs_negative_rejected(self, tmp_path):
        output = tmp_path / "results.json"
        with pytest.raises(SystemExit):
            _mod.main(["--runs", "-1", "--output", str(output)])


# ---------------------------------------------------------------------------
# 7. Backward compat: existing planner module unmodified
# ---------------------------------------------------------------------------

class TestPlannerModuleUnmodified:
    def test_planner_version_is_0_36(self):
        from scripts.claude_dynamic_planner_loop import PLANNER_VERSION
        assert PLANNER_VERSION == "0.36"

    def test_write_run_envelope_still_callable(self):
        from scripts.claude_dynamic_planner_loop import write_run_envelope
        assert callable(write_run_envelope)

    def test_evaluate_envelopes_callable(self):
        from scripts.evaluate_planner_runs import evaluate_envelopes
        assert callable(evaluate_envelopes)
