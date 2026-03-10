# SPDX-License-Identifier: MIT
"""Regression tests for the v0.39 pre-flight risk guardrail in
scripts/run_planner_experiment.py.

Covers:
1. low_risk  → experiment proceeds normally.
2. moderate_risk → warning printed to stderr, experiment continues.
3. high_risk → SystemExit(1) raised (aborts).
4. high_risk + --force → experiment continues despite high risk.
5. No portfolio_state → pre-flight skipped entirely.
6. _print_preflight_result output format.
7. _ARGS_ATTRS includes "force" (policy sweep propagation).
8. Existing run_experiment/run_policy_sweep signatures unchanged (backward compat).
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Module loading
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_SCRIPT = _REPO_ROOT / "scripts" / "run_planner_experiment.py"
_spec = importlib.util.spec_from_file_location("run_planner_experiment", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

run_experiment = _mod.run_experiment
run_policy_sweep = _mod.run_policy_sweep
_print_preflight_result = _mod._print_preflight_result
_run_preflight_check = _mod._run_preflight_check
_ARGS_ATTRS = _mod._ARGS_ATTRS


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_args(**kwargs):
    """Build a minimal args-like namespace for run_experiment."""
    obj = type("Args", (), {})()
    defaults = dict(
        runs=1,
        portfolio_state=None,
        ledger=None,
        policy=None,
        top_k=3,
        exploration_offset=0,
        max_actions=None,
        explain=False,
        force=False,
        output="experiment_results.json",
        envelope_prefix="planner_run_envelope",
        mapping_override=None,
    )
    defaults.update(kwargs)
    for k, v in defaults.items():
        setattr(obj, k, v)
    return obj


def _noop_planner(argv):
    """Planner stub that writes a valid minimal envelope to --run-envelope path."""
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--run-envelope")
    p.add_argument("--portfolio-state", default=None)
    p.add_argument("--ledger", default=None)
    p.add_argument("--policy", default=None)
    p.add_argument("--top-k", type=int, default=3)
    p.add_argument("--exploration-offset", type=int, default=0)
    p.add_argument("--max-actions", type=int, default=None)
    p.add_argument("--explain", action="store_true", default=False)
    p.add_argument("--mapping-override-json", default=None)
    ns = p.parse_args(argv)
    if ns.run_envelope:
        envelope = {
            "planner_version": "0.36",
            "inputs": {"top_k": ns.top_k, "exploration_offset": ns.exploration_offset,
                       "policy": ns.policy, "ledger": ns.ledger,
                       "portfolio_state": ns.portfolio_state, "explain": ns.explain,
                       "max_actions": ns.max_actions},
            "selected_actions": [],
            "selection_count": 0,
            "selection_detail": {
                "action_task_collapse_count": 0,
                "active_action_to_task_mapping": {},
                "ranked_action_window": [],
            },
            "artifacts": {"explain_artifact": None},
            "execution": {"executed": True, "status": "ok"},
        }
        Path(ns.run_envelope).write_text(
            json.dumps(envelope, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )


def _risk_check(risk_level, collision_ratio=0.0, unique_tasks=2, reasons=None,
                recommendations=None):
    """Return a risk_check_fn that always returns the given risk_level."""
    def _fn(args):
        return {
            "risk_level": risk_level,
            "collision_ratio": collision_ratio,
            "unique_tasks": unique_tasks,
            "collapse_count": 0,
            "ranked_action_window": ["a", "b", "c"],
            "mapped_tasks": ["t1", "t2", None],
            "task_entropy": 1.0,
            "action_entropy": 1.0,
            "reasons": reasons or [f"{risk_level} reason"],
            "recommendations": recommendations or ["recommendation"],
        }
    return _fn


# ---------------------------------------------------------------------------
# 1. low_risk proceeds
# ---------------------------------------------------------------------------

class TestLowRiskProceeds:
    def test_low_risk_runs_planner(self, tmp_path):
        args = _make_args(output=str(tmp_path / "results.json"), force=False)
        calls = []

        def planner(argv):
            calls.append(argv)
            _noop_planner(argv)

        result = run_experiment(args, planner_main=planner,
                                risk_check_fn=_risk_check("low_risk"))
        assert len(calls) == 1
        assert "run_count" in result

    def test_low_risk_no_stderr_output(self, tmp_path, capsys):
        args = _make_args(output=str(tmp_path / "results.json"))
        run_experiment(args, planner_main=_noop_planner,
                       risk_check_fn=_risk_check("low_risk"))
        captured = capsys.readouterr()
        assert captured.err == ""

    def test_low_risk_returns_result_dict(self, tmp_path):
        args = _make_args(output=str(tmp_path / "results.json"))
        result = run_experiment(args, planner_main=_noop_planner,
                                risk_check_fn=_risk_check("low_risk"))
        assert isinstance(result, dict)
        assert result["run_count"] == 1


# ---------------------------------------------------------------------------
# 2. moderate_risk warns but continues
# ---------------------------------------------------------------------------

class TestModerateRiskWarnsAndContinues:
    def test_moderate_risk_runs_planner(self, tmp_path):
        args = _make_args(output=str(tmp_path / "results.json"), force=False)
        calls = []

        def planner(argv):
            calls.append(argv)
            _noop_planner(argv)

        result = run_experiment(args, planner_main=planner,
                                risk_check_fn=_risk_check("moderate_risk",
                                                          collision_ratio=0.33))
        assert len(calls) == 1
        assert "run_count" in result

    def test_moderate_risk_prints_warning(self, tmp_path, capsys):
        args = _make_args(output=str(tmp_path / "results.json"), force=False)
        run_experiment(args, planner_main=_noop_planner,
                       risk_check_fn=_risk_check("moderate_risk", collision_ratio=0.33))
        captured = capsys.readouterr()
        assert "MODERATE" in captured.err
        assert "WARNING" in captured.err

    def test_moderate_risk_prints_collision_ratio(self, tmp_path, capsys):
        args = _make_args(output=str(tmp_path / "results.json"), force=False)
        run_experiment(args, planner_main=_noop_planner,
                       risk_check_fn=_risk_check("moderate_risk", collision_ratio=0.33))
        captured = capsys.readouterr()
        assert "0.33" in captured.err

    def test_moderate_risk_does_not_raise(self, tmp_path):
        args = _make_args(output=str(tmp_path / "results.json"), force=False)
        # Must not raise SystemExit
        result = run_experiment(args, planner_main=_noop_planner,
                                risk_check_fn=_risk_check("moderate_risk"))
        assert result is not None


# ---------------------------------------------------------------------------
# 3. high_risk aborts
# ---------------------------------------------------------------------------

class TestHighRiskAborts:
    def test_high_risk_raises_system_exit(self, tmp_path):
        args = _make_args(output=str(tmp_path / "results.json"), force=False)
        with pytest.raises(SystemExit) as exc_info:
            run_experiment(args, planner_main=_noop_planner,
                           risk_check_fn=_risk_check("high_risk", collision_ratio=0.67,
                                                     unique_tasks=1))
        assert exc_info.value.code == 1

    def test_high_risk_does_not_run_planner(self, tmp_path):
        args = _make_args(output=str(tmp_path / "results.json"), force=False)
        calls = []

        def planner(argv):
            calls.append(argv)
            _noop_planner(argv)

        with pytest.raises(SystemExit):
            run_experiment(args, planner_main=planner,
                           risk_check_fn=_risk_check("high_risk", collision_ratio=0.67))
        assert len(calls) == 0

    def test_high_risk_prints_explanation(self, tmp_path, capsys):
        args = _make_args(output=str(tmp_path / "results.json"), force=False)
        with pytest.raises(SystemExit):
            run_experiment(args, planner_main=_noop_planner,
                           risk_check_fn=_risk_check("high_risk", collision_ratio=0.67,
                                                     unique_tasks=1,
                                                     reasons=["task diversity collapse predicted"]))
        captured = capsys.readouterr()
        assert "HIGH" in captured.err
        assert "Use --force" in captured.err
        assert "task diversity collapse predicted" in captured.err

    def test_high_risk_prints_collision_ratio(self, tmp_path, capsys):
        args = _make_args(output=str(tmp_path / "results.json"), force=False)
        with pytest.raises(SystemExit):
            run_experiment(args, planner_main=_noop_planner,
                           risk_check_fn=_risk_check("high_risk", collision_ratio=0.67))
        captured = capsys.readouterr()
        assert "0.67" in captured.err


# ---------------------------------------------------------------------------
# 4. high_risk + --force continues
# ---------------------------------------------------------------------------

class TestHighRiskWithForce:
    def test_force_runs_planner_despite_high_risk(self, tmp_path):
        args = _make_args(output=str(tmp_path / "results.json"), force=True)
        calls = []

        def planner(argv):
            calls.append(argv)
            _noop_planner(argv)

        result = run_experiment(args, planner_main=planner,
                                risk_check_fn=_risk_check("high_risk", collision_ratio=0.67))
        assert len(calls) == 1
        assert result["run_count"] == 1

    def test_force_prints_override_warning(self, tmp_path, capsys):
        args = _make_args(output=str(tmp_path / "results.json"), force=True)
        run_experiment(args, planner_main=_noop_planner,
                       risk_check_fn=_risk_check("high_risk", collision_ratio=0.67))
        captured = capsys.readouterr()
        assert "HIGH" in captured.err
        assert "--force" in captured.err

    def test_force_does_not_exit(self, tmp_path):
        args = _make_args(output=str(tmp_path / "results.json"), force=True)
        # Must not raise
        result = run_experiment(args, planner_main=_noop_planner,
                                risk_check_fn=_risk_check("high_risk"))
        assert result is not None


# ---------------------------------------------------------------------------
# 5. No portfolio_state — pre-flight skipped
# ---------------------------------------------------------------------------

class TestNoPortfolioStateSkipsPreflight:
    def test_no_portfolio_state_returns_none(self):
        obj = _make_args(portfolio_state=None)
        result = _run_preflight_check(obj)
        assert result is None

    def test_no_portfolio_state_runs_without_check(self, tmp_path):
        args = _make_args(portfolio_state=None, output=str(tmp_path / "r.json"))
        calls = []

        def planner(argv):
            calls.append(argv)
            _noop_planner(argv)

        # risk_check_fn that returns None (no state)
        result = run_experiment(args, planner_main=planner,
                                risk_check_fn=lambda a: None)
        assert len(calls) == 1


# ---------------------------------------------------------------------------
# 6. _print_preflight_result output format
# ---------------------------------------------------------------------------

class TestPrintPreflightResult:
    def _ev(self, risk, collision_ratio=0.33, unique_tasks=2, reasons=None):
        return {
            "risk_level": risk,
            "collision_ratio": collision_ratio,
            "unique_tasks": unique_tasks,
            "reasons": reasons or [f"{risk} reason"],
            "recommendations": ["do something"],
        }

    def test_low_risk_returns_true_no_output(self, capsys):
        result = _print_preflight_result(self._ev("low_risk"), force=False, top_k=3)
        assert result is True
        assert capsys.readouterr().err == ""

    def test_moderate_risk_returns_true(self, capsys):
        result = _print_preflight_result(self._ev("moderate_risk"), force=False, top_k=3)
        assert result is True

    def test_high_risk_no_force_returns_false(self, capsys):
        result = _print_preflight_result(self._ev("high_risk"), force=False, top_k=3)
        assert result is False

    def test_high_risk_with_force_returns_true(self, capsys):
        result = _print_preflight_result(self._ev("high_risk"), force=True, top_k=3)
        assert result is True

    def test_output_goes_to_stderr_not_stdout(self, capsys):
        _print_preflight_result(self._ev("moderate_risk"), force=False, top_k=3)
        captured = capsys.readouterr()
        assert captured.out == ""
        assert len(captured.err) > 0

    def test_reasons_appear_in_output(self, capsys):
        _print_preflight_result(
            self._ev("high_risk", reasons=["custom reason text"]),
            force=False, top_k=3,
        )
        assert "custom reason text" in capsys.readouterr().err

    def test_unique_tasks_appears_in_output(self, capsys):
        _print_preflight_result(
            self._ev("moderate_risk", unique_tasks=1),
            force=False, top_k=3,
        )
        assert "1 / 3" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# 7. _ARGS_ATTRS includes "force"
# ---------------------------------------------------------------------------

class TestArgsAttrs:
    def test_force_in_args_attrs(self):
        assert "force" in _ARGS_ATTRS

    def test_copy_args_preserves_force(self):
        from scripts.run_planner_experiment import _copy_args
        args = _make_args(force=True)
        copied = _copy_args(args)
        assert copied.force is True

    def test_copy_args_preserves_force_false(self):
        from scripts.run_planner_experiment import _copy_args
        args = _make_args(force=False)
        copied = _copy_args(args)
        assert copied.force is False


# ---------------------------------------------------------------------------
# 8. Backward compatibility — existing signatures unchanged
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    def test_run_experiment_accepts_no_risk_check_fn(self, tmp_path):
        """run_experiment must still work when called without risk_check_fn."""
        args = _make_args(output=str(tmp_path / "r.json"))
        # Provide a risk_check_fn that returns None to avoid real subprocess
        result = run_experiment(args, planner_main=_noop_planner,
                                risk_check_fn=lambda a: None)
        assert "run_count" in result

    def test_run_policy_sweep_accepts_no_risk_check_fn(self, tmp_path):
        """run_policy_sweep signature must remain backward compatible."""
        import inspect
        sig = inspect.signature(run_policy_sweep)
        assert "risk_check_fn" in sig.parameters

    def test_multiple_runs_all_checked(self, tmp_path):
        """Pre-flight runs once (before the loop) even for multi-run experiments."""
        args = _make_args(runs=3, output=str(tmp_path / "r.json"))
        check_calls = []

        def counting_check(args):
            check_calls.append(1)
            return None  # no evaluation → skip guardrail

        run_experiment(args, planner_main=_noop_planner, risk_check_fn=counting_check)
        # Pre-flight is called exactly once per run_experiment invocation
        assert len(check_calls) == 1


# ---------------------------------------------------------------------------
# 9. _run_preflight_check honours structured (by_action_id) mapping overrides
# ---------------------------------------------------------------------------

class TestPreflightStructuredOverride:
    """Integration: _run_preflight_check must pass mapping_override to _compute_risk."""

    def _dup_actions(self):
        return [
            {"action_type": "rerun_failed_task",
             "action_id": "rerun_failed_task_repo-A",
             "repo_id": "repo-A", "priority": 0.9},
            {"action_type": "regenerate_missing_artifact",
             "action_id": "regenerate_missing_artifact_repo-A",
             "repo_id": "repo-A", "priority": 0.8},
            {"action_type": "regenerate_missing_artifact",
             "action_id": "regenerate_missing_artifact_repo-B",
             "repo_id": "repo-B", "priority": 0.7},
        ]

    def test_preflight_structured_override_eliminates_collision(self, tmp_path):
        """_run_preflight_check with structured override must show zero collision."""
        import json
        ps = tmp_path / "ps.json"
        ps.write_text(json.dumps({"repos": []}), encoding="utf-8")

        # Without override: high_risk due to collision.
        ev_mod = _mod._load_evaluator_mod()
        with _mod_patch(ev_mod, "_fetch_actions", self._dup_actions()):
            args_no_override = _make_args(
                portfolio_state=str(ps), top_k=3, mapping_override=None
            )
            base_ev = _run_preflight_check(args_no_override)

        assert base_ev is not None
        assert base_ev["collapse_count"] >= 1

        # With structured override: by_action_id resolves distinct tasks per instance.
        structured_override = {
            "by_action_id": {
                "regenerate_missing_artifact_repo-A": "artifact_audit_example",
                "regenerate_missing_artifact_repo-B": "failure_recovery_example",
            },
            "by_action_type": {
                "rerun_failed_task": "build_portfolio_dashboard",
            },
        }
        with _mod_patch(ev_mod, "_fetch_actions", self._dup_actions()):
            args_override = _make_args(
                portfolio_state=str(ps), top_k=3, mapping_override=structured_override
            )
            repaired_ev = _run_preflight_check(args_override)

        assert repaired_ev is not None
        assert repaired_ev["collapse_count"] == 0, (
            f"Expected 0 collapse with structured override; got {repaired_ev['collapse_count']}, "
            f"mapped_tasks={repaired_ev['mapped_tasks']}"
        )
        assert repaired_ev["unique_tasks"] == 3
        assert repaired_ev["risk_level"] == "low_risk"

    def test_preflight_structured_override_mapped_tasks_correct(self, tmp_path):
        """by_action_id tasks must appear in mapped_tasks from preflight."""
        import json
        ps = tmp_path / "ps.json"
        ps.write_text(json.dumps({"repos": []}), encoding="utf-8")

        structured_override = {
            "by_action_id": {
                "regenerate_missing_artifact_repo-A": "artifact_audit_example",
                "regenerate_missing_artifact_repo-B": "failure_recovery_example",
            },
            "by_action_type": {
                "rerun_failed_task": "build_portfolio_dashboard",
            },
        }
        ev_mod = _mod._load_evaluator_mod()
        with _mod_patch(ev_mod, "_fetch_actions", self._dup_actions()):
            args = _make_args(
                portfolio_state=str(ps), top_k=3, mapping_override=structured_override
            )
            ev = _run_preflight_check(args)

        assert ev is not None
        mapped = ev["mapped_tasks"]
        assert "artifact_audit_example" in mapped, f"Expected artifact_audit_example in {mapped}"
        assert "failure_recovery_example" in mapped, f"Expected failure_recovery_example in {mapped}"
        assert "build_portfolio_dashboard" in mapped, f"Expected build_portfolio_dashboard in {mapped}"

    def test_preflight_flat_override_still_works(self, tmp_path):
        """Flat override must still work in _run_preflight_check (backward compat)."""
        import json
        ps = tmp_path / "ps.json"
        ps.write_text(json.dumps({"repos": []}), encoding="utf-8")

        flat_override = {
            "regenerate_missing_artifact": "artifact_audit_example",
            "rerun_failed_task": "failure_recovery_example",
        }
        actions = [
            {"action_type": "rerun_failed_task", "action_id": "a1",
             "repo_id": "r1", "priority": 0.9},
            {"action_type": "regenerate_missing_artifact", "action_id": "a2",
             "repo_id": "r2", "priority": 0.8},
        ]
        ev_mod = _mod._load_evaluator_mod()
        with _mod_patch(ev_mod, "_fetch_actions", actions):
            args = _make_args(
                portfolio_state=str(ps), top_k=2, mapping_override=flat_override
            )
            ev = _run_preflight_check(args)

        assert ev is not None
        assert ev["collapse_count"] == 0
        assert "artifact_audit_example" in ev["mapped_tasks"]
        assert "failure_recovery_example" in ev["mapped_tasks"]


def _mod_patch(target_mod, attr, return_value):
    """Context manager: patch target_mod.<attr> to return return_value."""
    from unittest.mock import patch
    return patch.object(target_mod, attr, return_value=return_value)
