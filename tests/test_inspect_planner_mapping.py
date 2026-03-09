# SPDX-License-Identifier: MIT
"""Regression tests for scripts/inspect_planner_mapping.py.

Covers:
1. Clusters built correctly from ranked_action_window + mapped_tasks.
2. Deterministic output (identical inputs → identical results).
3. largest_cluster_size computed correctly.
4. collision_count computed correctly.
5. Full inspect_mapping() round-trip with mocked _fetch_actions.
6. Reuse of analyzer's _compute_risk (not a copy of planner logic).
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

_SCRIPT = _REPO_ROOT / "scripts" / "inspect_planner_mapping.py"
_spec = importlib.util.spec_from_file_location("inspect_planner_mapping", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

_build_clusters = _mod._build_clusters
inspect_mapping = _mod.inspect_mapping
ACTION_TO_TASK = _mod.ACTION_TO_TASK

_ANALYZER_SCRIPT = _REPO_ROOT / "scripts" / "analyze_planner_collision_risk.py"
_aspec = importlib.util.spec_from_file_location("analyze_planner_collision_risk", _ANALYZER_SCRIPT)
_analyzer_mod = importlib.util.module_from_spec(_aspec)
_aspec.loader.exec_module(_analyzer_mod)

_REQUIRED_KEYS = {
    "policy", "top_k", "window_actions", "mapped_tasks",
    "task_clusters", "cluster_count", "largest_cluster_size", "collision_count",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_actions(specs):
    return [
        {"action_type": at, "priority": pri, "action_id": f"aid-{i}", "repo_id": f"repo-{i}"}
        for i, (at, pri) in enumerate(specs)
    ]


def _run_clusters(window, tasks):
    """Shorthand for _build_clusters."""
    return _build_clusters(window, tasks)


# ---------------------------------------------------------------------------
# 1. _build_clusters — correctness
# ---------------------------------------------------------------------------

class TestBuildClusters:
    def test_empty_inputs(self):
        result = _run_clusters([], [])
        assert result["task_clusters"] == {}
        assert result["cluster_count"] == 0
        assert result["largest_cluster_size"] == 0
        assert result["collision_count"] == 0

    def test_all_unique_tasks(self):
        window = ["a", "b", "c"]
        tasks  = ["t1", "t2", "t3"]
        result = _run_clusters(window, tasks)
        assert result["cluster_count"] == 3
        assert result["largest_cluster_size"] == 1
        assert result["collision_count"] == 0
        assert result["task_clusters"] == {"t1": ["a"], "t2": ["b"], "t3": ["c"]}

    def test_two_actions_same_task(self):
        window = ["a", "b", "c"]
        tasks  = ["t1", "t1", "t2"]
        result = _run_clusters(window, tasks)
        assert result["cluster_count"] == 2
        assert result["task_clusters"]["t1"] == ["a", "b"]
        assert result["task_clusters"]["t2"] == ["c"]
        assert result["largest_cluster_size"] == 2
        assert result["collision_count"] == 1

    def test_all_same_task(self):
        window = ["a", "b", "c"]
        tasks  = ["t1", "t1", "t1"]
        result = _run_clusters(window, tasks)
        assert result["cluster_count"] == 1
        assert result["largest_cluster_size"] == 3
        assert result["collision_count"] == 2
        assert result["task_clusters"] == {"t1": ["a", "b", "c"]}

    def test_unmapped_actions_go_to_unmapped_key(self):
        window = ["a", "b", "c"]
        tasks  = ["t1", None, "t1"]
        result = _run_clusters(window, tasks)
        assert "unmapped" in result["task_clusters"]
        assert result["task_clusters"]["unmapped"] == ["b"]

    def test_unmapped_key_absent_when_all_mapped(self):
        result = _run_clusters(["a", "b"], ["t1", "t2"])
        assert "unmapped" not in result["task_clusters"]

    def test_cluster_keys_sorted(self):
        window = ["a", "b", "c"]
        tasks  = ["z_task", "a_task", "m_task"]
        keys = list(_run_clusters(window, tasks)["task_clusters"].keys())
        assert keys == sorted(keys)

    def test_window_order_preserved_within_cluster(self):
        # Actions appear in window order inside their cluster.
        window = ["first", "second", "third"]
        tasks  = ["t1",    "t1",     "t1"]
        result = _run_clusters(window, tasks)
        assert result["task_clusters"]["t1"] == ["first", "second", "third"]

    def test_single_action_window(self):
        result = _run_clusters(["a"], ["t1"])
        assert result["cluster_count"] == 1
        assert result["largest_cluster_size"] == 1
        assert result["collision_count"] == 0

    def test_collision_count_formula(self):
        # collision_count == window_size - cluster_count
        window = ["a", "b", "c", "d", "e"]
        tasks  = ["t1", "t1", "t2", "t2", "t3"]
        result = _run_clusters(window, tasks)
        window_size = len(window)
        assert result["collision_count"] == window_size - result["cluster_count"]

    def test_largest_cluster_size_with_multiple_clusters(self):
        window = ["a", "b", "c", "d", "e"]
        tasks  = ["big", "big", "big", "small", "small"]
        result = _run_clusters(window, tasks)
        assert result["largest_cluster_size"] == 3

    def test_returns_correct_keys(self):
        result = _run_clusters(["a"], ["t1"])
        assert set(result.keys()) == {
            "task_clusters", "cluster_count", "largest_cluster_size", "collision_count"
        }


# ---------------------------------------------------------------------------
# 2. Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    def _input(self):
        window = ["regenerate_missing_artifact", "recover_failed_workflow", "refresh_repo_health"]
        tasks  = ["build_portfolio_dashboard", "failure_recovery_example", "build_portfolio_dashboard"]
        return window, tasks

    def test_repeated_calls_identical(self):
        w, t = self._input()
        assert _run_clusters(w, t) == _run_clusters(w, t)

    def test_cluster_key_order_stable(self):
        w, t = self._input()
        keys1 = list(_run_clusters(w, t)["task_clusters"].keys())
        keys2 = list(_run_clusters(w, t)["task_clusters"].keys())
        assert keys1 == keys2

    def test_cluster_values_order_stable(self):
        w, t = self._input()
        r1 = _run_clusters(w, t)
        r2 = _run_clusters(w, t)
        for key in r1["task_clusters"]:
            assert r1["task_clusters"][key] == r2["task_clusters"][key]


# ---------------------------------------------------------------------------
# 3. largest_cluster_size correctness
# ---------------------------------------------------------------------------

class TestLargestClusterSize:
    def test_all_unique(self):
        assert _run_clusters(["a", "b"], ["t1", "t2"])["largest_cluster_size"] == 1

    def test_two_in_one_cluster(self):
        assert _run_clusters(["a", "b", "c"], ["t1", "t1", "t2"])["largest_cluster_size"] == 2

    def test_all_in_one_cluster(self):
        assert _run_clusters(["a", "b", "c"], ["t1", "t1", "t1"])["largest_cluster_size"] == 3

    def test_largest_when_multiple_clusters_of_different_sizes(self):
        window = ["a", "b", "c", "d", "e", "f"]
        tasks  = ["big", "big", "big", "big", "small", "tiny"]
        result = _run_clusters(window, tasks)
        assert result["largest_cluster_size"] == 4

    def test_empty_window_zero(self):
        assert _run_clusters([], [])["largest_cluster_size"] == 0


# ---------------------------------------------------------------------------
# 4. collision_count correctness
# ---------------------------------------------------------------------------

class TestCollisionCount:
    def test_zero_collisions_all_unique(self):
        assert _run_clusters(["a", "b"], ["t1", "t2"])["collision_count"] == 0

    def test_one_collision_in_three(self):
        # a→t1 (new), b→t2 (new), c→t1 (collision)
        result = _run_clusters(["a", "b", "c"], ["t1", "t2", "t1"])
        assert result["collision_count"] == 1

    def test_two_collisions_all_same(self):
        result = _run_clusters(["a", "b", "c"], ["t1", "t1", "t1"])
        assert result["collision_count"] == 2

    def test_collision_count_equals_window_minus_clusters(self):
        window = ["a", "b", "c", "d"]
        tasks  = ["t1", "t1", "t2", "t2"]
        result = _run_clusters(window, tasks)
        assert result["collision_count"] == len(window) - result["cluster_count"]

    def test_unmapped_adds_to_unmapped_cluster_collision(self):
        # Two unmapped actions → "unmapped" cluster has size 2 → 1 collision
        window = ["a", "b", "c"]
        tasks  = [None, None, "t1"]
        result = _run_clusters(window, tasks)
        assert result["collision_count"] == 1


# ---------------------------------------------------------------------------
# 5. Full inspect_mapping() round-trip with mocked _fetch_actions
# ---------------------------------------------------------------------------

_MOD_SPECS = [
    ("regenerate_missing_artifact", 0.95),  # → build_portfolio_dashboard
    ("recover_failed_workflow", 0.85),       # → failure_recovery_example
    ("refresh_repo_health", 0.80),           # → build_portfolio_dashboard (collision)
]


def _make_raw_actions(specs=_MOD_SPECS):
    return _make_actions(specs)


class TestInspectMappingRoundTrip:
    def test_output_has_all_required_keys(self, tmp_path):
        ps = tmp_path / "ps.json"
        ps.write_text(json.dumps({"repos": []}), encoding="utf-8")
        out = tmp_path / "diag.json"

        with patch.object(_mod, "_fetch_actions", return_value=_make_raw_actions()):
            result = inspect_mapping(
                policy_path=None, top_k=3,
                portfolio_state_path=str(ps), ledger_path=None,
                output_path=str(out),
            )

        assert _REQUIRED_KEYS <= set(result.keys())

    def test_file_written_when_output_given(self, tmp_path):
        ps = tmp_path / "ps.json"
        ps.write_text(json.dumps({"repos": []}), encoding="utf-8")
        out = tmp_path / "diag.json"

        with patch.object(_mod, "_fetch_actions", return_value=_make_raw_actions()):
            result = inspect_mapping(
                policy_path=None, top_k=3,
                portfolio_state_path=str(ps), ledger_path=None,
                output_path=str(out),
            )

        assert out.exists()
        assert json.loads(out.read_text(encoding="utf-8")) == result

    def test_stdout_when_no_output_path(self, tmp_path, capsys):
        ps = tmp_path / "ps.json"
        ps.write_text(json.dumps({"repos": []}), encoding="utf-8")

        with patch.object(_mod, "_fetch_actions", return_value=_make_raw_actions()):
            inspect_mapping(
                policy_path=None, top_k=3,
                portfolio_state_path=str(ps), ledger_path=None,
                output_path=None,
            )

        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert _REQUIRED_KEYS <= set(parsed.keys())

    def test_stdout_empty_when_file_path_given(self, tmp_path, capsys):
        ps = tmp_path / "ps.json"
        ps.write_text(json.dumps({"repos": []}), encoding="utf-8")
        out = tmp_path / "diag.json"

        with patch.object(_mod, "_fetch_actions", return_value=_make_raw_actions()):
            inspect_mapping(
                policy_path=None, top_k=3,
                portfolio_state_path=str(ps), ledger_path=None,
                output_path=str(out),
            )

        assert capsys.readouterr().out == ""

    def test_clusters_correct_for_known_specs(self, tmp_path):
        ps = tmp_path / "ps.json"
        ps.write_text(json.dumps({"repos": []}), encoding="utf-8")

        with patch.object(_mod, "_fetch_actions", return_value=_make_raw_actions()):
            result = inspect_mapping(
                policy_path=None, top_k=3,
                portfolio_state_path=str(ps), ledger_path=None,
                output_path=str(tmp_path / "out.json"),
            )

        # build_portfolio_dashboard gets 2 actions (collision)
        assert "build_portfolio_dashboard" in result["task_clusters"]
        assert len(result["task_clusters"]["build_portfolio_dashboard"]) == 2
        assert result["collision_count"] == 1
        assert result["largest_cluster_size"] == 2

    def test_collision_count_matches_analyzer_collapse_count(self, tmp_path):
        ps = tmp_path / "ps.json"
        ps.write_text(json.dumps({"repos": []}), encoding="utf-8")

        # Run inspect_mapping and the analyzer on the same actions
        actions = _make_raw_actions()

        with patch.object(_mod, "_fetch_actions", return_value=actions):
            diag = inspect_mapping(
                policy_path=None, top_k=3,
                portfolio_state_path=str(ps), ledger_path=None,
                output_path=str(tmp_path / "out.json"),
            )

        analyzer_risk = _analyzer_mod._compute_risk(
            actions=actions, top_k=3, ledger={}, signals={}, policy={},
            active_mapping=dict(ACTION_TO_TASK),
        )
        assert diag["collision_count"] == analyzer_risk["collapse_count"]

    def test_window_actions_matches_analyzer_ranked_window(self, tmp_path):
        ps = tmp_path / "ps.json"
        ps.write_text(json.dumps({"repos": []}), encoding="utf-8")
        actions = _make_raw_actions()

        with patch.object(_mod, "_fetch_actions", return_value=actions):
            diag = inspect_mapping(
                policy_path=None, top_k=3,
                portfolio_state_path=str(ps), ledger_path=None,
                output_path=str(tmp_path / "out.json"),
            )

        analyzer_risk = _analyzer_mod._compute_risk(
            actions=actions, top_k=3, ledger={}, signals={}, policy={},
            active_mapping=dict(ACTION_TO_TASK),
        )
        assert diag["window_actions"] == analyzer_risk["ranked_action_window"]

    def test_deterministic_repeated_calls(self, tmp_path):
        ps = tmp_path / "ps.json"
        ps.write_text(json.dumps({"repos": []}), encoding="utf-8")
        actions = _make_raw_actions()

        results = []
        for i in range(2):
            with patch.object(_mod, "_fetch_actions", return_value=actions):
                results.append(inspect_mapping(
                    policy_path=None, top_k=3,
                    portfolio_state_path=str(ps), ledger_path=None,
                    output_path=str(tmp_path / f"out{i}.json"),
                ))

        assert results[0] == results[1]

    def test_mapping_override_changes_clusters(self, tmp_path):
        ps = tmp_path / "ps.json"
        ps.write_text(json.dumps({"repos": []}), encoding="utf-8")
        # Override: all three → unique tasks → no collisions
        override_file = tmp_path / "override.json"
        override_file.write_text(json.dumps({
            "regenerate_missing_artifact": "artifact_audit_example",
            "recover_failed_workflow": "failure_recovery_example",
            "refresh_repo_health": "repo_insights_example",
        }), encoding="utf-8")

        with patch.object(_mod, "_fetch_actions", return_value=_make_raw_actions()):
            result = inspect_mapping(
                policy_path=None, top_k=3,
                portfolio_state_path=str(ps), ledger_path=None,
                mapping_override_path=str(override_file),
                output_path=str(tmp_path / "out.json"),
            )

        assert result["collision_count"] == 0
        assert result["largest_cluster_size"] == 1
        assert result["cluster_count"] == 3

    def test_top_k_in_result(self, tmp_path):
        ps = tmp_path / "ps.json"
        ps.write_text(json.dumps({"repos": []}), encoding="utf-8")

        with patch.object(_mod, "_fetch_actions", return_value=_make_raw_actions()):
            result = inspect_mapping(
                policy_path=None, top_k=2,
                portfolio_state_path=str(ps), ledger_path=None,
                output_path=str(tmp_path / "out.json"),
            )

        assert result["top_k"] == 2
        assert len(result["window_actions"]) == 2


# ---------------------------------------------------------------------------
# 6. Analyzer reuse
# ---------------------------------------------------------------------------

class TestAnalyzerReuse:
    def test_script_references_analyzer(self):
        source = _SCRIPT.read_text(encoding="utf-8")
        assert "analyze_planner_collision_risk" in source

    def test_compute_risk_behavioral_equivalence(self):
        actions = _make_actions(_MOD_SPECS)
        kwargs = dict(
            actions=actions, top_k=3, ledger={}, signals={},
            policy={}, active_mapping=dict(ACTION_TO_TASK),
        )
        assert _mod._compute_risk(**kwargs) == _analyzer_mod._compute_risk(**kwargs)


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

    def test_real_fixtures_produce_valid_output(self):
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

        risk = _mod._compute_risk(
            actions=actions, top_k=3, ledger=ledger, signals=signals,
            policy={}, active_mapping=dict(ACTION_TO_TASK),
        )
        clusters = _build_clusters(risk["ranked_action_window"], risk["mapped_tasks"])

        assert isinstance(clusters["task_clusters"], dict)
        assert clusters["cluster_count"] >= 0
        assert clusters["largest_cluster_size"] >= 0
        assert clusters["collision_count"] >= 0
        # Verify collision_count formula holds
        window_size = len(risk["ranked_action_window"])
        assert clusters["collision_count"] == window_size - clusters["cluster_count"]

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
            risk = _mod._compute_risk(
                actions=actions, top_k=3, ledger=ledger, signals=signals,
                policy={}, active_mapping=dict(ACTION_TO_TASK),
            )
            return _build_clusters(risk["ranked_action_window"], risk["mapped_tasks"])

        assert _run() == _run()
