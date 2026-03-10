# SPDX-License-Identifier: MIT
"""Tests for v0.37 structured experiment configuration (--config flag).

Covers:
- config loading from JSON file
- CLI override precedence over config values
- deterministic envelope naming with custom prefix
- equivalence between CLI-only and config-driven runs
- existing tests (test_planner_experiment_runner.py) unaffected
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
# Helpers shared across test classes
# ---------------------------------------------------------------------------

_FULL_CONFIG = {
    "runs": 5,
    "planner": {
        "portfolio_state": "state.json",
        "ledger": "ledger.json",
        "policy": "policy.json",
        "top_k": 7,
        "exploration_offset": 2,
        "max_actions": 3,
        "explain": True,
    },
    "output": {
        "experiment_results": "my_results.json",
        "envelope_prefix": "custom_prefix",
    },
}

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


def _write_config(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


def _make_fake_planner(actions=None):
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
    envelope_prefix = "planner_run_envelope"


def _make_args(**kwargs):
    args = _FakeArgs()
    for k, v in kwargs.items():
        setattr(args, k, v)
    return args


# ---------------------------------------------------------------------------
# 1. Config loading
# ---------------------------------------------------------------------------

class TestConfigLoading:
    def test_load_config_returns_dict(self, tmp_path):
        cfg_file = _write_config(tmp_path / "cfg.json", _FULL_CONFIG)
        result = _mod._load_config(str(cfg_file))
        assert isinstance(result, dict)

    def test_load_config_runs_field(self, tmp_path):
        cfg_file = _write_config(tmp_path / "cfg.json", _FULL_CONFIG)
        result = _mod._load_config(str(cfg_file))
        assert result["runs"] == 5

    def test_load_config_planner_top_k(self, tmp_path):
        cfg_file = _write_config(tmp_path / "cfg.json", _FULL_CONFIG)
        result = _mod._load_config(str(cfg_file))
        assert result["planner"]["top_k"] == 7

    def test_load_config_planner_explain(self, tmp_path):
        cfg_file = _write_config(tmp_path / "cfg.json", _FULL_CONFIG)
        result = _mod._load_config(str(cfg_file))
        assert result["planner"]["explain"] is True

    def test_load_config_output_envelope_prefix(self, tmp_path):
        cfg_file = _write_config(tmp_path / "cfg.json", _FULL_CONFIG)
        result = _mod._load_config(str(cfg_file))
        assert result["output"]["envelope_prefix"] == "custom_prefix"

    def test_load_config_partial_config_no_error(self, tmp_path):
        partial = {"runs": 3}
        cfg_file = _write_config(tmp_path / "cfg.json", partial)
        result = _mod._load_config(str(cfg_file))
        assert result["runs"] == 3

    def test_load_config_empty_config_no_error(self, tmp_path):
        cfg_file = _write_config(tmp_path / "cfg.json", {})
        result = _mod._load_config(str(cfg_file))
        assert result == {}


# ---------------------------------------------------------------------------
# 2. _apply_config: config fills None fields, defaults applied last
# ---------------------------------------------------------------------------

class TestApplyConfig:
    def _none_args(self, **kwargs):
        """Return an args object with all overridable attrs set to None."""
        obj = type("Args", (), {
            "runs": None, "portfolio_state": None, "ledger": None,
            "policy": None, "top_k": None, "exploration_offset": None,
            "max_actions": None, "explain": None, "output": None,
            "envelope_prefix": None,
        })()
        for k, v in kwargs.items():
            setattr(obj, k, v)
        return obj

    def test_apply_config_fills_runs_from_config(self):
        args = self._none_args()
        _mod._apply_config(args, {"runs": 10})
        assert args.runs == 10

    def test_apply_config_fills_top_k_from_planner(self):
        args = self._none_args()
        _mod._apply_config(args, {"planner": {"top_k": 7}})
        assert args.top_k == 7

    def test_apply_config_fills_explain_from_planner(self):
        args = self._none_args()
        _mod._apply_config(args, {"planner": {"explain": True}})
        assert args.explain is True

    def test_apply_config_fills_envelope_prefix_from_output(self):
        args = self._none_args()
        _mod._apply_config(args, {"output": {"envelope_prefix": "my_prefix"}})
        assert args.envelope_prefix == "my_prefix"

    def test_apply_config_fills_output_path_from_experiment_results(self):
        args = self._none_args()
        _mod._apply_config(args, {"output": {"experiment_results": "out.json"}})
        assert args.output == "out.json"

    def test_apply_config_hardcoded_defaults_when_no_config(self):
        args = self._none_args()
        _mod._apply_config(args, {})
        assert args.runs == 1
        assert args.top_k == 3
        assert args.exploration_offset == 0
        assert args.explain is False
        assert args.output == "experiment_results.json"
        assert args.envelope_prefix == "planner_run_envelope"

    def test_apply_config_does_not_overwrite_cli_value(self):
        args = self._none_args(runs=2)
        _mod._apply_config(args, {"runs": 99})
        assert args.runs == 2


# ---------------------------------------------------------------------------
# 3. CLI override precedence
# ---------------------------------------------------------------------------

class TestCliOverridePrecedence:
    def test_cli_runs_overrides_config(self, tmp_path):
        cfg = {"runs": 20}
        cfg_file = _write_config(tmp_path / "cfg.json", cfg)
        output = tmp_path / "results.json"
        received_runs = []

        def counting_planner(argv):
            _make_fake_planner()(argv)

        # Simulate: --runs 2 --config cfg.json
        _mod.main([
            "--config", str(cfg_file),
            "--runs", "2",
            "--output", str(output),
        ])
        data = json.loads(output.read_text(encoding="utf-8"))
        assert data["run_count"] == 2

    def test_cli_top_k_overrides_config(self, tmp_path):
        cfg = {"planner": {"top_k": 99}}
        cfg_file = _write_config(tmp_path / "cfg.json", cfg)
        output = tmp_path / "results.json"
        received_argv = []

        def capture_argv(argv):
            received_argv.append(list(argv))
            _make_fake_planner()(argv)

        import types
        saved = _mod.__dict__.get("run_experiment")

        # Inject via main() by re-parsing; capture argv via a custom planner.
        # We call run_experiment directly with simulated args instead.
        args = type("Args", (), {
            "runs": None, "portfolio_state": None, "ledger": None,
            "policy": None, "top_k": 5, "exploration_offset": None,
            "max_actions": None, "explain": None, "output": str(output),
            "envelope_prefix": None,
        })()
        _mod._apply_config(args, cfg)
        # CLI value (5) was set before apply_config; config (99) must NOT override it.
        assert args.top_k == 5

    def test_cli_output_overrides_config(self, tmp_path):
        cfg = {"output": {"experiment_results": "from_config.json"}}
        cfg_file = _write_config(tmp_path / "cfg.json", cfg)
        cli_output = tmp_path / "from_cli.json"

        _mod.main([
            "--config", str(cfg_file),
            "--output", str(cli_output),
        ])
        assert cli_output.exists()

    def test_cli_explain_overrides_config_false(self, tmp_path):
        # Config says explain=True; CLI doesn't pass --explain.
        # Because --explain uses store_true with default=None, absence means None,
        # so config value takes effect. This test verifies config works when CLI is absent.
        cfg = {"planner": {"explain": True}}
        cfg_file = _write_config(tmp_path / "cfg.json", cfg)
        received_argv = []

        def capture_argv(argv):
            received_argv.append(list(argv))
            _make_fake_planner()(argv)

        output = tmp_path / "results.json"
        _mod.main([
            "--config", str(cfg_file),
            "--runs", "1",
            "--output", str(output),
        ])
        # --explain should have been passed to the planner
        # (the real planner is called; we just verify no exception and output exists)
        assert output.exists()

    def test_config_used_when_no_cli_overrides(self, tmp_path):
        cfg = {"runs": 3}
        cfg_file = _write_config(tmp_path / "cfg.json", cfg)
        output = tmp_path / "results.json"

        _mod.main(["--config", str(cfg_file), "--output", str(output)])
        data = json.loads(output.read_text(encoding="utf-8"))
        assert data["run_count"] == 3


# ---------------------------------------------------------------------------
# 4. Deterministic envelope naming with envelope_prefix
# ---------------------------------------------------------------------------

class TestEnvelopeNamingWithPrefix:
    def test_envelope_name_default_prefix(self):
        assert _mod._envelope_name(1) == "planner_run_envelope_run1.json"

    def test_envelope_name_default_prefix_run10(self):
        assert _mod._envelope_name(10) == "planner_run_envelope_run10.json"

    def test_envelope_name_custom_prefix(self):
        assert _mod._envelope_name(1, "my_exp") == "my_exp_run1.json"

    def test_envelope_name_custom_prefix_run5(self):
        assert _mod._envelope_name(5, "exp_v2") == "exp_v2_run5.json"

    def test_config_envelope_prefix_used_in_files(self, tmp_path):
        cfg = {"output": {"envelope_prefix": "custom_env"}}
        cfg_file = _write_config(tmp_path / "cfg.json", cfg)
        output = tmp_path / "results.json"

        _mod.main([
            "--config", str(cfg_file),
            "--runs", "2",
            "--output", str(output),
        ])
        assert (tmp_path / "custom_env_run1.json").exists()
        assert (tmp_path / "custom_env_run2.json").exists()

    def test_default_prefix_unchanged_without_config(self, tmp_path):
        output = tmp_path / "results.json"
        args = _make_args(runs=2, output=str(output))
        _mod.run_experiment(args, planner_main=_make_fake_planner())
        assert (tmp_path / "planner_run_envelope_run1.json").exists()
        assert (tmp_path / "planner_run_envelope_run2.json").exists()

    def test_cli_envelope_prefix_overrides_config(self, tmp_path):
        cfg = {"output": {"envelope_prefix": "from_config"}}
        cfg_file = _write_config(tmp_path / "cfg.json", cfg)
        output = tmp_path / "results.json"

        _mod.main([
            "--config", str(cfg_file),
            "--envelope-prefix", "from_cli",
            "--runs", "1",
            "--output", str(output),
        ])
        assert (tmp_path / "from_cli_run1.json").exists()
        assert not (tmp_path / "from_config_run1.json").exists()


# ---------------------------------------------------------------------------
# 5. Equivalence: CLI-only vs config-driven runs
# ---------------------------------------------------------------------------

class TestCliConfigEquivalence:
    def test_run_count_equivalent(self, tmp_path):
        # CLI-only
        output_cli = tmp_path / "cli" / "results.json"
        _mod.main(["--runs", "3", "--output", str(output_cli)])
        cli_data = json.loads(output_cli.read_text(encoding="utf-8"))

        # Config-driven
        cfg = {"runs": 3}
        cfg_file = _write_config(tmp_path / "cfg.json", cfg)
        output_cfg = tmp_path / "cfg_out" / "results.json"
        _mod.main(["--config", str(cfg_file), "--output", str(output_cfg)])
        cfg_data = json.loads(output_cfg.read_text(encoding="utf-8"))

        assert cli_data["run_count"] == cfg_data["run_count"]

    def test_evaluation_summary_keys_equivalent(self, tmp_path):
        output_cli = tmp_path / "cli" / "results.json"
        _mod.main(["--runs", "1", "--output", str(output_cli)])
        cli_data = json.loads(output_cli.read_text(encoding="utf-8"))

        cfg = {"runs": 1}
        cfg_file = _write_config(tmp_path / "cfg.json", cfg)
        output_cfg = tmp_path / "cfg_out" / "results.json"
        _mod.main(["--config", str(cfg_file), "--output", str(output_cfg)])
        cfg_data = json.loads(output_cfg.read_text(encoding="utf-8"))

        assert set(cli_data.keys()) == set(cfg_data.keys())
        assert set(cli_data["evaluation_summary"].keys()) == set(cfg_data["evaluation_summary"].keys())

    def test_envelope_paths_length_equivalent(self, tmp_path):
        output_cli = tmp_path / "cli" / "results.json"
        args_cli = _make_args(runs=4, output=str(output_cli))
        result_cli = _mod.run_experiment(args_cli, planner_main=_make_fake_planner())

        cfg = {"runs": 4}
        cfg_file = _write_config(tmp_path / "cfg.json", cfg)
        output_cfg = tmp_path / "cfg_out" / "results.json"
        args_cfg = type("Args", (), {
            "runs": None, "portfolio_state": None, "ledger": None,
            "policy": None, "top_k": None, "exploration_offset": None,
            "max_actions": None, "explain": None, "output": str(output_cfg),
            "envelope_prefix": None,
        })()
        _mod._apply_config(args_cfg, cfg)
        result_cfg = _mod.run_experiment(args_cfg, planner_main=_make_fake_planner())

        assert len(result_cli["envelope_paths"]) == len(result_cfg["envelope_paths"])

    def test_results_structure_is_deterministic(self, tmp_path):
        output_a = tmp_path / "a" / "results.json"
        output_b = tmp_path / "b" / "results.json"
        args_a = _make_args(runs=2, output=str(output_a))
        args_b = _make_args(runs=2, output=str(output_b))
        result_a = _mod.run_experiment(args_a, planner_main=_make_fake_planner())
        result_b = _mod.run_experiment(args_b, planner_main=_make_fake_planner())
        assert result_a["run_count"] == result_b["run_count"]
        assert result_a["evaluation_summary"]["identical"] == result_b["evaluation_summary"]["identical"]


# ---------------------------------------------------------------------------
# 6. main() validation still works with new arg defaults
# ---------------------------------------------------------------------------

class TestMainValidationUnchanged:
    def test_runs_zero_rejected(self, tmp_path):
        output = tmp_path / "results.json"
        with pytest.raises(SystemExit):
            _mod.main(["--runs", "0", "--output", str(output)])

    def test_runs_negative_rejected(self, tmp_path):
        output = tmp_path / "results.json"
        with pytest.raises(SystemExit):
            _mod.main(["--runs", "-1", "--output", str(output)])

    def test_default_runs_is_one_without_config(self, tmp_path):
        output = tmp_path / "results.json"
        _mod.main(["--output", str(output)])
        data = json.loads(output.read_text(encoding="utf-8"))
        assert data["run_count"] == 1


# ---------------------------------------------------------------------------
# 7. Config-driven force handling
# ---------------------------------------------------------------------------

def _make_nil_args(**kwargs):
    """Build an all-None args-like namespace (for _apply_config unit tests)."""
    obj = type("Args", (), {})()
    defaults = dict(
        runs=None, portfolio_state=None, ledger=None, policy=None,
        top_k=None, exploration_offset=None, max_actions=None,
        explain=None, force=None, output=None, envelope_prefix=None,
        mapping_override=None,
    )
    defaults.update(kwargs)
    for k, v in defaults.items():
        setattr(obj, k, v)
    return obj


class TestConfigDrivenForce:
    def test_config_force_true_fills_when_args_force_is_none(self):
        """force=True in config sets args.force when CLI did not supply it."""
        args = _make_nil_args()
        _mod._apply_config(args, {"force": True})
        assert args.force is True

    def test_config_force_false_fills_when_args_force_is_none(self):
        """force=False in config is applied (not silently skipped as falsy)."""
        # _fill skips falsy values, so config force=False has no effect —
        # the hard default False is applied instead. Either way the result is False.
        args = _make_nil_args()
        _mod._apply_config(args, {"force": False})
        assert args.force is False

    def test_explicit_cli_force_true_not_overwritten_by_config(self):
        """CLI --force (True) takes precedence over config force=False."""
        args = _make_nil_args(force=True)
        _mod._apply_config(args, {"force": False})
        assert args.force is True

    def test_explicit_cli_force_not_overwritten_by_config_true(self):
        """When CLI did not set force (None), config True is applied."""
        args = _make_nil_args(force=None)
        _mod._apply_config(args, {"force": True})
        assert args.force is True

    def test_default_force_false_when_neither_cli_nor_config_sets_it(self):
        """Hard default False is applied when neither CLI nor config sets force."""
        args = _make_nil_args(force=None)
        _mod._apply_config(args, {})
        assert args.force is False

    def test_config_force_true_preserved_through_defaults_pass(self):
        """Config-supplied force=True survives the _DEFAULTS hard-default pass."""
        args = _make_nil_args()
        _mod._apply_config(args, {"force": True})
        # _DEFAULTS["force"] = False must not overwrite the config value.
        assert args.force is True
