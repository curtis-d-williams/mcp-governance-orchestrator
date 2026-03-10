# SPDX-License-Identifier: MIT
"""Regression tests for scripts/run_diversity_sweep.py.

Covers:
1. Deterministic output (identical inputs → identical results).
2. Correct range of top_k (1..max_k, in order).
3. entropy_gap computed correctly (action_entropy - task_entropy, rounded to 6dp).
4. Evaluator/analyzer logic reused (not copy-pasted).
5. Output structure (required keys, correct types).
6. Full run_diversity_sweep() round-trip with mocked _fetch_actions.
"""
import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Module loading
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_SCRIPT = _REPO_ROOT / "scripts" / "run_diversity_sweep.py"
_spec = importlib.util.spec_from_file_location("run_diversity_sweep", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

compute_diversity_sweep = _mod.compute_diversity_sweep
_sweep_one = _mod._sweep_one
run_diversity_sweep = _mod.run_diversity_sweep
ACTION_TO_TASK = _mod.ACTION_TO_TASK

_ANALYZER_SCRIPT = _REPO_ROOT / "scripts" / "analyze_planner_collision_risk.py"
_aspec = importlib.util.spec_from_file_location("analyze_planner_collision_risk", _ANALYZER_SCRIPT)
_analyzer_mod = importlib.util.module_from_spec(_aspec)
_aspec.loader.exec_module(_analyzer_mod)

_ENTRY_KEYS = {
    "top_k", "unique_tasks", "collision_ratio",
    "task_entropy", "action_entropy", "entropy_gap",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_actions(specs):
    return [
        {"action_type": at, "priority": pri, "action_id": f"aid-{i}", "repo_id": f"repo-{i}"}
        for i, (at, pri) in enumerate(specs)
    ]


# 5 actions with known mapping outcomes (matches degraded_v2 action types)
_FIVE_SPECS = [
    ("regenerate_missing_artifact", 0.95),  # → build_portfolio_dashboard
    ("recover_failed_workflow",     0.85),  # → failure_recovery_example
    ("refresh_repo_health",         0.80),  # → build_portfolio_dashboard  (collision at k>=3)
    ("analyze_repo_insights",       0.78),  # → repo_insights_example
    ("rerun_failed_task",           0.70),  # → build_portfolio_dashboard  (collision at k>=5)
]


def _run_sweep(specs=_FIVE_SPECS, max_k=5, mapping=None):
    actions = _make_actions(specs)
    m = mapping if mapping is not None else dict(ACTION_TO_TASK)
    return compute_diversity_sweep(
        actions=actions, max_k=max_k,
        ledger={}, signals={}, policy={},
        active_mapping=m,
    )


# ---------------------------------------------------------------------------
# 1. Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_repeated_calls_identical(self):
        assert _run_sweep() == _run_sweep()

    def test_top_k_order_stable(self):
        r1 = _run_sweep()
        r2 = _run_sweep()
        assert [e["top_k"] for e in r1] == [e["top_k"] for e in r2]

    def test_entropy_gap_stable(self):
        r1 = _run_sweep()
        r2 = _run_sweep()
        assert [e["entropy_gap"] for e in r1] == [e["entropy_gap"] for e in r2]

    def test_collision_ratio_stable(self):
        r1 = _run_sweep()
        r2 = _run_sweep()
        assert [e["collision_ratio"] for e in r1] == [e["collision_ratio"] for e in r2]


# ---------------------------------------------------------------------------
# 2. Correct range of top_k
# ---------------------------------------------------------------------------

class TestTopKRange:
    def test_default_max_k_8_produces_8_entries(self):
        result = _run_sweep(max_k=8)
        assert len(result) == 8

    def test_top_k_values_are_1_to_max_k(self):
        result = _run_sweep(max_k=5)
        assert [e["top_k"] for e in result] == [1, 2, 3, 4, 5]

    def test_max_k_1_produces_single_entry(self):
        result = _run_sweep(max_k=1)
        assert len(result) == 1
        assert result[0]["top_k"] == 1

    def test_max_k_3_produces_three_entries(self):
        result = _run_sweep(max_k=3)
        assert len(result) == 3
        assert [e["top_k"] for e in result] == [1, 2, 3]

    def test_entries_in_ascending_order(self):
        result = _run_sweep(max_k=5)
        top_ks = [e["top_k"] for e in result]
        assert top_ks == sorted(top_ks)

    def test_max_k_exceeds_actions_still_produces_correct_count(self):
        # max_k=10 with only 5 actions — should still produce 10 entries.
        result = _run_sweep(max_k=10)
        assert len(result) == 10
        assert result[9]["top_k"] == 10


# ---------------------------------------------------------------------------
# 3. entropy_gap computed correctly
# ---------------------------------------------------------------------------

class TestEntropyGap:
    def test_entropy_gap_equals_action_minus_task_entropy(self):
        result = _run_sweep()
        for entry in result:
            expected = round(entry["action_entropy"] - entry["task_entropy"], 6)
            assert entry["entropy_gap"] == expected

    def test_entropy_gap_zero_when_entropies_equal(self):
        # With top_k=1 there is exactly one action/task, both entropies are 0.
        result = _run_sweep(max_k=1)
        assert result[0]["action_entropy"] == 0.0
        assert result[0]["task_entropy"] == 0.0
        assert result[0]["entropy_gap"] == 0.0

    def test_entropy_gap_non_negative_when_collision_present(self):
        # When actions collapse to fewer tasks, action_entropy >= task_entropy.
        result = _run_sweep(max_k=3)
        entry_k3 = result[2]
        assert entry_k3["entropy_gap"] >= 0.0

    def test_entropy_gap_zero_when_all_unique_tasks(self):
        # Mapping override: all 3 actions → unique tasks → no gap.
        mapping = {
            "regenerate_missing_artifact": "task_a",
            "recover_failed_workflow":     "task_b",
            "refresh_repo_health":         "task_c",
        }
        result = _run_sweep(specs=_FIVE_SPECS[:3], max_k=3, mapping=mapping)
        entry_k3 = result[2]
        assert entry_k3["entropy_gap"] == 0.0

    def test_entropy_gap_is_float(self):
        result = _run_sweep()
        for entry in result:
            assert isinstance(entry["entropy_gap"], float)

    def test_entropy_gap_rounded_to_6dp(self):
        result = _run_sweep()
        for entry in result:
            assert entry["entropy_gap"] == round(entry["entropy_gap"], 6)


# ---------------------------------------------------------------------------
# 4. Analyzer logic reused
# ---------------------------------------------------------------------------

class TestAnalyzerReuse:
    def test_script_references_analyzer(self):
        source = _SCRIPT.read_text(encoding="utf-8")
        assert "analyze_planner_collision_risk" in source

    def test_sweep_one_matches_analyzer_compute_risk(self):
        actions = _make_actions(_FIVE_SPECS[:3])
        kwargs = dict(
            actions=actions, top_k=3, ledger={}, signals={},
            policy={}, active_mapping=dict(ACTION_TO_TASK),
        )
        analyzer_result = _analyzer_mod._compute_risk(**kwargs)
        sweep_entry = _sweep_one(**kwargs)

        assert sweep_entry["unique_tasks"] == analyzer_result["unique_tasks"]
        assert sweep_entry["collision_ratio"] == analyzer_result["collision_ratio"]
        assert sweep_entry["task_entropy"] == analyzer_result["task_entropy"]
        assert sweep_entry["action_entropy"] == analyzer_result["action_entropy"]

    def test_compute_risk_behavioral_equivalence(self):
        actions = _make_actions(_FIVE_SPECS)
        kwargs = dict(
            actions=actions, top_k=5, ledger={}, signals={},
            policy={}, active_mapping=dict(ACTION_TO_TASK),
        )
        assert _mod._compute_risk(**kwargs) == _analyzer_mod._compute_risk(**kwargs)


# ---------------------------------------------------------------------------
# 5. Output structure
# ---------------------------------------------------------------------------

class TestOutputStructure:
    def test_all_required_keys_present(self):
        result = _run_sweep(max_k=3)
        for entry in result:
            assert _ENTRY_KEYS <= set(entry.keys())

    def test_top_k_is_int(self):
        for entry in _run_sweep(max_k=3):
            assert isinstance(entry["top_k"], int)

    def test_unique_tasks_is_int(self):
        for entry in _run_sweep(max_k=3):
            assert isinstance(entry["unique_tasks"], int)

    def test_collision_ratio_is_float(self):
        for entry in _run_sweep(max_k=3):
            assert isinstance(entry["collision_ratio"], float)

    def test_task_entropy_is_float(self):
        for entry in _run_sweep(max_k=3):
            assert isinstance(entry["task_entropy"], float)

    def test_action_entropy_is_float(self):
        for entry in _run_sweep(max_k=3):
            assert isinstance(entry["action_entropy"], float)

    def test_unique_tasks_non_decreasing_with_more_actions(self):
        # As top_k grows, unique_tasks can only stay flat or increase.
        result = _run_sweep(max_k=5)
        prev = 0
        for entry in result:
            assert entry["unique_tasks"] >= prev
            prev = entry["unique_tasks"]

    def test_collision_ratio_in_0_to_1(self):
        for entry in _run_sweep(max_k=8):
            assert 0.0 <= entry["collision_ratio"] <= 1.0

    def test_k1_no_collision(self):
        # A window of 1 action can never have a collision.
        entry = _run_sweep(max_k=1)[0]
        assert entry["collision_ratio"] == 0.0
        assert entry["unique_tasks"] == 1


# ---------------------------------------------------------------------------
# 6. Full run_diversity_sweep() round-trip with mocked _fetch_actions
# ---------------------------------------------------------------------------

class TestRunDiversitySweepRoundTrip:
    def _actions(self):
        return _make_actions(_FIVE_SPECS)

    def test_output_is_list(self, tmp_path):
        ps = tmp_path / "ps.json"
        ps.write_text(json.dumps({"repos": []}), encoding="utf-8")

        with patch.object(_mod, "_fetch_actions", return_value=self._actions()):
            result = run_diversity_sweep(
                policy_path=None, portfolio_state_path=str(ps),
                ledger_path=None, max_k=3,
                output_path=str(tmp_path / "sweep.json"),
            )

        assert isinstance(result, list)
        assert len(result) == 3

    def test_file_written_when_output_given(self, tmp_path):
        ps = tmp_path / "ps.json"
        ps.write_text(json.dumps({"repos": []}), encoding="utf-8")
        out = tmp_path / "sweep.json"

        with patch.object(_mod, "_fetch_actions", return_value=self._actions()):
            result = run_diversity_sweep(
                policy_path=None, portfolio_state_path=str(ps),
                ledger_path=None, max_k=3, output_path=str(out),
            )

        assert out.exists()
        assert json.loads(out.read_text(encoding="utf-8")) == result

    def test_stdout_when_no_output_path(self, tmp_path, capsys):
        ps = tmp_path / "ps.json"
        ps.write_text(json.dumps({"repos": []}), encoding="utf-8")

        with patch.object(_mod, "_fetch_actions", return_value=self._actions()):
            run_diversity_sweep(
                policy_path=None, portfolio_state_path=str(ps),
                ledger_path=None, max_k=2, output_path=None,
            )

        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert isinstance(parsed, list)
        assert len(parsed) == 2

    def test_stdout_empty_when_file_given(self, tmp_path, capsys):
        ps = tmp_path / "ps.json"
        ps.write_text(json.dumps({"repos": []}), encoding="utf-8")

        with patch.object(_mod, "_fetch_actions", return_value=self._actions()):
            run_diversity_sweep(
                policy_path=None, portfolio_state_path=str(ps),
                ledger_path=None, max_k=2,
                output_path=str(tmp_path / "out.json"),
            )

        assert capsys.readouterr().out == ""

    def test_deterministic_round_trip(self, tmp_path):
        ps = tmp_path / "ps.json"
        ps.write_text(json.dumps({"repos": []}), encoding="utf-8")
        actions = self._actions()

        results = []
        for i in range(2):
            with patch.object(_mod, "_fetch_actions", return_value=actions):
                results.append(run_diversity_sweep(
                    policy_path=None, portfolio_state_path=str(ps),
                    ledger_path=None, max_k=5,
                    output_path=str(tmp_path / f"out{i}.json"),
                ))

        assert results[0] == results[1]

    def test_max_k_respected(self, tmp_path):
        ps = tmp_path / "ps.json"
        ps.write_text(json.dumps({"repos": []}), encoding="utf-8")

        with patch.object(_mod, "_fetch_actions", return_value=self._actions()):
            result = run_diversity_sweep(
                policy_path=None, portfolio_state_path=str(ps),
                ledger_path=None, max_k=4,
                output_path=str(tmp_path / "out.json"),
            )

        assert len(result) == 4
        assert result[-1]["top_k"] == 4

    def test_entropy_gap_correct_in_round_trip(self, tmp_path):
        ps = tmp_path / "ps.json"
        ps.write_text(json.dumps({"repos": []}), encoding="utf-8")

        with patch.object(_mod, "_fetch_actions", return_value=self._actions()):
            result = run_diversity_sweep(
                policy_path=None, portfolio_state_path=str(ps),
                ledger_path=None, max_k=5,
                output_path=str(tmp_path / "out.json"),
            )

        for entry in result:
            expected_gap = round(entry["action_entropy"] - entry["task_entropy"], 6)
            assert entry["entropy_gap"] == expected_gap

    def test_mapping_override_applied(self, tmp_path):
        ps = tmp_path / "ps.json"
        ps.write_text(json.dumps({"repos": []}), encoding="utf-8")
        override_file = tmp_path / "override.json"
        # All 5 actions → unique tasks → no collisions anywhere in sweep
        override_file.write_text(json.dumps({
            "regenerate_missing_artifact": "t1",
            "recover_failed_workflow":     "t2",
            "refresh_repo_health":         "t3",
            "analyze_repo_insights":       "t4",
            "rerun_failed_task":           "t5",
        }), encoding="utf-8")

        with patch.object(_mod, "_fetch_actions", return_value=self._actions()):
            result = run_diversity_sweep(
                policy_path=None, portfolio_state_path=str(ps),
                ledger_path=None, max_k=5,
                mapping_override_path=str(override_file),
                output_path=str(tmp_path / "out.json"),
            )

        for entry in result:
            assert entry["collision_ratio"] == 0.0
            assert entry["entropy_gap"] == 0.0


# ---------------------------------------------------------------------------
# 7. Integration — real experiment fixtures
# ---------------------------------------------------------------------------

class TestRealFixtures:
    _PS = _REPO_ROOT / "experiments" / "portfolio_state_degraded_v2.json"
    _LEDGER = _REPO_ROOT / "experiments" / "action_effectiveness_ledger_synthetic_v2.json"

    @pytest.fixture(autouse=True)
    def _skip_if_missing(self):
        if not self._PS.exists() or not self._LEDGER.exists():
            pytest.skip("Experiment fixture files not present")

    def test_real_fixtures_produce_valid_sweep(self):
        import json as _json
        from scripts.planner_scoring import load_effectiveness_ledger, load_portfolio_signals

        ps_data = _json.loads(self._PS.read_text(encoding="utf-8"))
        actions = []
        for repo in ps_data.get("repos", []):
            for act in repo.get("recommended_actions", []):
                entry = dict(act)
                entry.setdefault("repo_id", repo.get("repo_id", ""))
                actions.append(entry)

        ledger = load_effectiveness_ledger(str(self._LEDGER))
        signals = load_portfolio_signals(str(self._PS))

        result = compute_diversity_sweep(
            actions=actions, max_k=5,
            ledger=ledger, signals=signals, policy={},
            active_mapping=dict(ACTION_TO_TASK),
        )

        assert len(result) == 5
        assert [e["top_k"] for e in result] == [1, 2, 3, 4, 5]
        for entry in result:
            assert _ENTRY_KEYS <= set(entry.keys())
            expected_gap = round(entry["action_entropy"] - entry["task_entropy"], 6)
            assert entry["entropy_gap"] == expected_gap

    def test_real_fixtures_deterministic(self):
        import json as _json
        from scripts.planner_scoring import load_effectiveness_ledger, load_portfolio_signals

        ps_data = _json.loads(self._PS.read_text(encoding="utf-8"))
        actions = []
        for repo in ps_data.get("repos", []):
            for act in repo.get("recommended_actions", []):
                entry = dict(act)
                entry.setdefault("repo_id", repo.get("repo_id", ""))
                actions.append(entry)

        ledger = load_effectiveness_ledger(str(self._LEDGER))
        signals = load_portfolio_signals(str(self._PS))

        def _run():
            return compute_diversity_sweep(
                actions=actions, max_k=5,
                ledger=ledger, signals=signals, policy={},
                active_mapping=dict(ACTION_TO_TASK),
            )

        assert _run() == _run()


# ---------------------------------------------------------------------------
# 8. Failure-mode guardrail — empty / missing action queue
# ---------------------------------------------------------------------------

class TestEmptyActionQueueGuardrail:
    """run_diversity_sweep() must exit nonzero instead of emitting all-zero rows
    when the action queue is empty (file missing or no eligible actions)."""

    def test_missing_portfolio_state_raises_system_exit(self, tmp_path):
        """File does not exist → SystemExit(1)."""
        nonexistent = str(tmp_path / "does_not_exist.json")
        with pytest.raises(SystemExit) as exc_info:
            run_diversity_sweep(
                policy_path=None,
                portfolio_state_path=nonexistent,
                ledger_path=None,
                max_k=3,
            )
        assert exc_info.value.code == 1

    def test_missing_file_prints_error_to_stderr(self, tmp_path, capsys):
        """File does not exist → error message on stderr mentioning the path."""
        nonexistent = str(tmp_path / "no_such_file.json")
        with pytest.raises(SystemExit):
            run_diversity_sweep(
                policy_path=None,
                portfolio_state_path=nonexistent,
                ledger_path=None,
                max_k=3,
            )
        err = capsys.readouterr().err
        assert "not found" in err
        assert "no_such_file.json" in err

    def test_missing_file_no_stdout_output(self, tmp_path, capsys):
        """File does not exist → no JSON (or any other) output on stdout."""
        nonexistent = str(tmp_path / "no_such_file.json")
        with pytest.raises(SystemExit):
            run_diversity_sweep(
                policy_path=None,
                portfolio_state_path=nonexistent,
                ledger_path=None,
                max_k=3,
            )
        assert capsys.readouterr().out == ""

    def test_empty_queue_raises_system_exit(self, tmp_path):
        """Valid file, _fetch_actions returns [] → SystemExit(1)."""
        ps = tmp_path / "ps.json"
        ps.write_text(json.dumps({"repos": []}), encoding="utf-8")
        with patch.object(_mod, "_fetch_actions", return_value=[]):
            with pytest.raises(SystemExit) as exc_info:
                run_diversity_sweep(
                    policy_path=None,
                    portfolio_state_path=str(ps),
                    ledger_path=None,
                    max_k=3,
                )
        assert exc_info.value.code == 1

    def test_empty_queue_prints_error_to_stderr(self, tmp_path, capsys):
        """Valid file, empty queue → error message on stderr."""
        ps = tmp_path / "ps.json"
        ps.write_text(json.dumps({"repos": []}), encoding="utf-8")
        with patch.object(_mod, "_fetch_actions", return_value=[]):
            with pytest.raises(SystemExit):
                run_diversity_sweep(
                    policy_path=None,
                    portfolio_state_path=str(ps),
                    ledger_path=None,
                    max_k=3,
                )
        err = capsys.readouterr().err
        assert len(err) > 0

    def test_empty_queue_no_stdout_output(self, tmp_path, capsys):
        """Valid file, empty queue → no JSON on stdout."""
        ps = tmp_path / "ps.json"
        ps.write_text(json.dumps({"repos": []}), encoding="utf-8")
        with patch.object(_mod, "_fetch_actions", return_value=[]):
            with pytest.raises(SystemExit):
                run_diversity_sweep(
                    policy_path=None,
                    portfolio_state_path=str(ps),
                    ledger_path=None,
                    max_k=3,
                )
        assert capsys.readouterr().out == ""

    def test_empty_queue_no_output_file_written(self, tmp_path):
        """Valid file, empty queue → output file must not be created."""
        ps = tmp_path / "ps.json"
        ps.write_text(json.dumps({"repos": []}), encoding="utf-8")
        out = tmp_path / "sweep.json"
        with patch.object(_mod, "_fetch_actions", return_value=[]):
            with pytest.raises(SystemExit):
                run_diversity_sweep(
                    policy_path=None,
                    portfolio_state_path=str(ps),
                    ledger_path=None,
                    max_k=3,
                    output_path=str(out),
                )
        assert not out.exists()

    def test_nonempty_queue_not_affected(self, tmp_path):
        """Non-empty queue → no SystemExit, normal sweep returned."""
        ps = tmp_path / "ps.json"
        ps.write_text(json.dumps({"repos": []}), encoding="utf-8")
        actions = _make_actions(_FIVE_SPECS[:2])
        with patch.object(_mod, "_fetch_actions", return_value=actions):
            result = run_diversity_sweep(
                policy_path=None,
                portfolio_state_path=str(ps),
                ledger_path=None,
                max_k=2,
                output_path=str(tmp_path / "out.json"),
            )
        assert len(result) == 2
        assert result[0]["top_k"] == 1

    def test_missing_file_error_message_mentions_portfolio_state(self, tmp_path, capsys):
        """Stderr for missing-file case includes the word 'portfolio-state'."""
        nonexistent = str(tmp_path / "ghost.json")
        with pytest.raises(SystemExit):
            run_diversity_sweep(
                policy_path=None,
                portfolio_state_path=nonexistent,
                ledger_path=None,
                max_k=2,
            )
        err = capsys.readouterr().err
        assert "portfolio" in err.lower()

    def test_empty_queue_error_mentions_eligible_actions(self, tmp_path, capsys):
        """Stderr for empty-queue case mentions eligible actions or similar guidance."""
        ps = tmp_path / "ps.json"
        ps.write_text(json.dumps({"repos": []}), encoding="utf-8")
        with patch.object(_mod, "_fetch_actions", return_value=[]):
            with pytest.raises(SystemExit):
                run_diversity_sweep(
                    policy_path=None,
                    portfolio_state_path=str(ps),
                    ledger_path=None,
                    max_k=3,
                )
        err = capsys.readouterr().err
        assert "action" in err.lower()
