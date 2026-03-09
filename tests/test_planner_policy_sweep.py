# SPDX-License-Identifier: MIT
"""Tests for v0.38 policy sweep experiment runner.

Covers:
- non-sweep behavior unchanged (no policy_sweep key)
- sweep config parsed correctly
- deterministic naming of sweep outputs
- one result produced per sweep entry
- aggregate sweep results deterministic
- existing experiment runner/config tests still pass (import smoke check)
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
# Shared helpers
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

_SWEEP_ENTRIES = [
    {"name": "baseline", "weights": {}},
    {"name": "completeness_high", "weights": {"artifact_completeness": 2.0}},
    {"name": "failures_high", "weights": {"recent_failures": -3.0}},
]


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
    runs = 2
    portfolio_state = None
    ledger = None
    policy = None
    top_k = 3
    exploration_offset = 0
    max_actions = None
    explain = False
    output = "experiment_results.json"
    envelope_prefix = "planner_run_envelope"


def _make_args(**kwargs):
    args = _FakeArgs()
    for k, v in kwargs.items():
        setattr(args, k, v)
    return args


def _write_config(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# 1. Non-sweep behavior unchanged
# ---------------------------------------------------------------------------

class TestNonSweepBehaviorUnchanged:
    def test_no_policy_sweep_key_runs_normal_experiment(self, tmp_path):
        output = tmp_path / "results.json"
        args = _make_args(runs=2, output=str(output))
        result = _mod.run_experiment(args, planner_main=_make_fake_planner())
        assert result["run_count"] == 2
        assert "evaluation_summary" in result

    def test_no_policy_sweep_key_creates_no_aggregate(self, tmp_path):
        output = tmp_path / "results.json"
        args = _make_args(runs=1, output=str(output))
        _mod.run_experiment(args, planner_main=_make_fake_planner())
        assert not (tmp_path / "policy_sweep_results.json").exists()

    def test_empty_policy_sweep_list_via_main_runs_normal(self, tmp_path):
        cfg = {"runs": 2, "policy_sweep": []}
        cfg_file = _write_config(tmp_path / "cfg.json", cfg)
        output = tmp_path / "results.json"
        _mod.main(["--config", str(cfg_file), "--output", str(output)])
        data = json.loads(output.read_text(encoding="utf-8"))
        assert data["run_count"] == 2

    def test_empty_policy_sweep_creates_no_aggregate(self, tmp_path):
        cfg = {"runs": 1, "policy_sweep": []}
        cfg_file = _write_config(tmp_path / "cfg.json", cfg)
        output = tmp_path / "results.json"
        _mod.main(["--config", str(cfg_file), "--output", str(output)])
        assert not (tmp_path / "policy_sweep_results.json").exists()

    def test_no_config_cli_only_runs_normal(self, tmp_path):
        output = tmp_path / "results.json"
        _mod.main(["--runs", "1", "--output", str(output)])
        data = json.loads(output.read_text(encoding="utf-8"))
        assert data["run_count"] == 1
        assert not (tmp_path / "policy_sweep_results.json").exists()


# ---------------------------------------------------------------------------
# 2. Sweep config parsed correctly
# ---------------------------------------------------------------------------

class TestSweepConfigParsing:
    def test_policy_sweep_list_extracted_from_config(self, tmp_path):
        cfg = {"policy_sweep": _SWEEP_ENTRIES}
        cfg_file = _write_config(tmp_path / "cfg.json", cfg)
        loaded = _mod._load_config(str(cfg_file))
        assert loaded["policy_sweep"] == _SWEEP_ENTRIES

    def test_sweep_entry_has_name(self):
        assert _SWEEP_ENTRIES[0]["name"] == "baseline"

    def test_sweep_entry_has_weights(self):
        entry = _SWEEP_ENTRIES[1]
        assert "artifact_completeness" in entry["weights"]

    def test_sweep_entry_weights_values(self):
        assert _SWEEP_ENTRIES[1]["weights"]["artifact_completeness"] == 2.0
        assert _SWEEP_ENTRIES[2]["weights"]["recent_failures"] == -3.0

    def test_materialize_sweep_policy_writes_file(self, tmp_path):
        entry = {"name": "baseline", "weights": {}}
        path = _mod._materialize_sweep_policy(tmp_path, entry)
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data == {}

    def test_materialize_sweep_policy_weights_content(self, tmp_path):
        entry = {"name": "completeness_high", "weights": {"artifact_completeness": 2.0}}
        path = _mod._materialize_sweep_policy(tmp_path, entry)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data == {"artifact_completeness": 2.0}

    def test_materialize_sweep_policy_negative_weights(self, tmp_path):
        entry = {"name": "failures_high", "weights": {"recent_failures": -3.0}}
        path = _mod._materialize_sweep_policy(tmp_path, entry)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["recent_failures"] == -3.0


# ---------------------------------------------------------------------------
# 3. Deterministic naming of sweep outputs
# ---------------------------------------------------------------------------

class TestDeterministicNaming:
    def test_sweep_policy_filename_baseline(self):
        assert _mod._sweep_policy_filename("baseline") == "sweep_baseline_policy.json"

    def test_sweep_policy_filename_completeness(self):
        assert _mod._sweep_policy_filename("completeness_high") == "sweep_completeness_high_policy.json"

    def test_sweep_result_filename_baseline(self):
        assert _mod._sweep_result_filename("baseline") == "sweep_baseline_experiment_results.json"

    def test_sweep_result_filename_failures(self):
        assert _mod._sweep_result_filename("failures_high") == "sweep_failures_high_experiment_results.json"

    def test_sweep_envelope_prefix_baseline(self):
        assert _mod._sweep_envelope_prefix("baseline") == "sweep_baseline_envelope"

    def test_sweep_envelope_prefix_completeness(self):
        assert _mod._sweep_envelope_prefix("completeness_high") == "sweep_completeness_high_envelope"

    def test_sweep_creates_policy_file_named_deterministically(self, tmp_path):
        output = tmp_path / "results.json"
        args = _make_args(runs=1, output=str(output))
        _mod.run_policy_sweep(
            [{"name": "baseline", "weights": {}}],
            args,
            planner_main=_make_fake_planner(),
        )
        assert (tmp_path / "sweep_baseline_policy.json").exists()

    def test_sweep_creates_result_file_named_deterministically(self, tmp_path):
        output = tmp_path / "results.json"
        args = _make_args(runs=1, output=str(output))
        _mod.run_policy_sweep(
            [{"name": "baseline", "weights": {}}],
            args,
            planner_main=_make_fake_planner(),
        )
        assert (tmp_path / "sweep_baseline_experiment_results.json").exists()

    def test_sweep_envelopes_named_with_prefix(self, tmp_path):
        output = tmp_path / "results.json"
        args = _make_args(runs=2, output=str(output))
        _mod.run_policy_sweep(
            [{"name": "baseline", "weights": {}}],
            args,
            planner_main=_make_fake_planner(),
        )
        assert (tmp_path / "sweep_baseline_envelope_run1.json").exists()
        assert (tmp_path / "sweep_baseline_envelope_run2.json").exists()

    def test_repeated_sweep_names_are_stable(self, tmp_path):
        output = tmp_path / "results.json"
        args = _make_args(runs=1, output=str(output))
        r1 = _mod.run_policy_sweep(
            [{"name": "alpha", "weights": {}}],
            args,
            planner_main=_make_fake_planner(),
        )
        r2 = _mod.run_policy_sweep(
            [{"name": "alpha", "weights": {}}],
            args,
            planner_main=_make_fake_planner(),
        )
        # Names in entries must be identical across runs
        assert r1["entries"][0]["name"] == r2["entries"][0]["name"]


# ---------------------------------------------------------------------------
# 4. One result produced per sweep entry
# ---------------------------------------------------------------------------

class TestOneResultPerEntry:
    def test_three_entries_three_results(self, tmp_path):
        output = tmp_path / "results.json"
        args = _make_args(runs=1, output=str(output))
        result = _mod.run_policy_sweep(
            _SWEEP_ENTRIES, args, planner_main=_make_fake_planner()
        )
        assert result["sweep_count"] == 3
        assert len(result["entries"]) == 3

    def test_one_entry_one_result(self, tmp_path):
        output = tmp_path / "results.json"
        args = _make_args(runs=1, output=str(output))
        result = _mod.run_policy_sweep(
            [{"name": "only", "weights": {}}],
            args,
            planner_main=_make_fake_planner(),
        )
        assert result["sweep_count"] == 1

    def test_each_entry_has_experiment_results_path(self, tmp_path):
        output = tmp_path / "results.json"
        args = _make_args(runs=1, output=str(output))
        result = _mod.run_policy_sweep(
            _SWEEP_ENTRIES, args, planner_main=_make_fake_planner()
        )
        for entry in result["entries"]:
            assert "experiment_results_path" in entry
            assert Path(entry["experiment_results_path"]).exists()

    def test_each_entry_has_evaluation_summary(self, tmp_path):
        output = tmp_path / "results.json"
        args = _make_args(runs=1, output=str(output))
        result = _mod.run_policy_sweep(
            _SWEEP_ENTRIES, args, planner_main=_make_fake_planner()
        )
        for entry in result["entries"]:
            assert "evaluation_summary" in entry
            assert "envelope_count" in entry["evaluation_summary"]

    def test_each_entry_has_run_envelope_paths(self, tmp_path):
        output = tmp_path / "results.json"
        args = _make_args(runs=2, output=str(output))
        result = _mod.run_policy_sweep(
            _SWEEP_ENTRIES, args, planner_main=_make_fake_planner()
        )
        for entry in result["entries"]:
            assert "run_envelope_paths" in entry
            assert len(entry["run_envelope_paths"]) == 2

    def test_entry_names_match_input(self, tmp_path):
        output = tmp_path / "results.json"
        args = _make_args(runs=1, output=str(output))
        result = _mod.run_policy_sweep(
            _SWEEP_ENTRIES, args, planner_main=_make_fake_planner()
        )
        names = [e["name"] for e in result["entries"]]
        assert names == ["baseline", "completeness_high", "failures_high"]

    def test_entry_weights_match_input(self, tmp_path):
        output = tmp_path / "results.json"
        args = _make_args(runs=1, output=str(output))
        result = _mod.run_policy_sweep(
            _SWEEP_ENTRIES, args, planner_main=_make_fake_planner()
        )
        assert result["entries"][0]["weights"] == {}
        assert result["entries"][1]["weights"] == {"artifact_completeness": 2.0}
        assert result["entries"][2]["weights"] == {"recent_failures": -3.0}


# ---------------------------------------------------------------------------
# 5. Aggregate sweep results deterministic
# ---------------------------------------------------------------------------

class TestAggregateSweepResults:
    def test_aggregate_file_created(self, tmp_path):
        output = tmp_path / "results.json"
        args = _make_args(runs=1, output=str(output))
        result = _mod.run_policy_sweep(
            _SWEEP_ENTRIES, args, planner_main=_make_fake_planner()
        )
        assert Path(result["aggregate_path"]).exists()

    def test_aggregate_filename_is_policy_sweep_results(self, tmp_path):
        output = tmp_path / "results.json"
        args = _make_args(runs=1, output=str(output))
        result = _mod.run_policy_sweep(
            _SWEEP_ENTRIES, args, planner_main=_make_fake_planner()
        )
        assert Path(result["aggregate_path"]).name == "policy_sweep_results.json"

    def test_aggregate_is_valid_json(self, tmp_path):
        output = tmp_path / "results.json"
        args = _make_args(runs=1, output=str(output))
        result = _mod.run_policy_sweep(
            _SWEEP_ENTRIES, args, planner_main=_make_fake_planner()
        )
        data = json.loads(Path(result["aggregate_path"]).read_text(encoding="utf-8"))
        assert isinstance(data, dict)

    def test_aggregate_sweep_count_field(self, tmp_path):
        output = tmp_path / "results.json"
        args = _make_args(runs=1, output=str(output))
        result = _mod.run_policy_sweep(
            _SWEEP_ENTRIES, args, planner_main=_make_fake_planner()
        )
        data = json.loads(Path(result["aggregate_path"]).read_text(encoding="utf-8"))
        assert data["sweep_count"] == 3

    def test_aggregate_entries_list_length(self, tmp_path):
        output = tmp_path / "results.json"
        args = _make_args(runs=1, output=str(output))
        result = _mod.run_policy_sweep(
            _SWEEP_ENTRIES, args, planner_main=_make_fake_planner()
        )
        data = json.loads(Path(result["aggregate_path"]).read_text(encoding="utf-8"))
        assert len(data["entries"]) == 3

    def test_aggregate_deterministic_repeated_calls(self, tmp_path):
        output = tmp_path / "results.json"
        args = _make_args(runs=1, output=str(output))
        r1 = _mod.run_policy_sweep(
            _SWEEP_ENTRIES, args, planner_main=_make_fake_planner()
        )
        r2 = _mod.run_policy_sweep(
            _SWEEP_ENTRIES, args, planner_main=_make_fake_planner()
        )
        d1 = json.loads(Path(r1["aggregate_path"]).read_text(encoding="utf-8"))
        d2 = json.loads(Path(r2["aggregate_path"]).read_text(encoding="utf-8"))
        assert d1["sweep_count"] == d2["sweep_count"]
        assert [e["name"] for e in d1["entries"]] == [e["name"] for e in d2["entries"]]

    def test_aggregate_colocated_with_base_output(self, tmp_path):
        subdir = tmp_path / "nested"
        output = subdir / "results.json"
        args = _make_args(runs=1, output=str(output))
        result = _mod.run_policy_sweep(
            [{"name": "x", "weights": {}}],
            args,
            planner_main=_make_fake_planner(),
        )
        assert Path(result["aggregate_path"]).parent == subdir

    def test_aggregate_via_main_with_config(self, tmp_path):
        cfg = {
            "runs": 1,
            "policy_sweep": _SWEEP_ENTRIES,
        }
        cfg_file = _write_config(tmp_path / "cfg.json", cfg)
        output = tmp_path / "results.json"
        _mod.main(["--config", str(cfg_file), "--output", str(output)])
        agg = tmp_path / "policy_sweep_results.json"
        assert agg.exists()
        data = json.loads(agg.read_text(encoding="utf-8"))
        assert data["sweep_count"] == 3

    def test_aggregate_entry_keys_complete(self, tmp_path):
        output = tmp_path / "results.json"
        args = _make_args(runs=1, output=str(output))
        result = _mod.run_policy_sweep(
            [{"name": "baseline", "weights": {}}],
            args,
            planner_main=_make_fake_planner(),
        )
        entry = result["entries"][0]
        for key in ("name", "weights", "experiment_results_path",
                    "evaluation_summary", "run_envelope_paths"):
            assert key in entry, f"missing key: {key}"


# ---------------------------------------------------------------------------
# 6. Existing runner/config tests still pass (import smoke check)
# ---------------------------------------------------------------------------

class TestExistingTestsUnaffected:
    def test_run_experiment_still_callable(self):
        assert callable(_mod.run_experiment)

    def test_apply_config_still_callable(self):
        assert callable(_mod._apply_config)

    def test_envelope_name_helper_unchanged(self):
        assert _mod._envelope_name(1) == "planner_run_envelope_run1.json"
        assert _mod._envelope_name(3) == "planner_run_envelope_run3.json"

    def test_run_experiment_returns_run_count(self, tmp_path):
        output = tmp_path / "results.json"
        args = _make_args(runs=3, output=str(output))
        result = _mod.run_experiment(args, planner_main=_make_fake_planner())
        assert result["run_count"] == 3

    def test_run_experiment_envelope_paths_unchanged(self, tmp_path):
        output = tmp_path / "results.json"
        args = _make_args(runs=2, output=str(output))
        result = _mod.run_experiment(args, planner_main=_make_fake_planner())
        for i, ep in enumerate(result["envelope_paths"], start=1):
            assert ep.endswith(f"planner_run_envelope_run{i}.json")

    def test_main_runs_zero_still_rejected(self, tmp_path):
        output = tmp_path / "results.json"
        with pytest.raises(SystemExit):
            _mod.main(["--runs", "0", "--output", str(output)])

    def test_planner_version_is_0_36(self):
        from scripts.claude_dynamic_planner_loop import PLANNER_VERSION
        assert PLANNER_VERSION == "0.36"

    def test_evaluate_envelopes_still_callable(self):
        from scripts.evaluate_planner_runs import evaluate_envelopes
        assert callable(evaluate_envelopes)
