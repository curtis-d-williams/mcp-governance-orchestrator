# SPDX-License-Identifier: MIT
"""Regression tests for scripts/evaluate_planner_config.py.

Covers:
1. JSON output structure (all required keys present).
2. Deterministic classification (identical inputs → identical outputs).
3. low_risk / moderate_risk / high_risk cases.
4. reasons and recommendations fields are non-empty lists for non-low cases.
5. Reuse of analyzer's _compute_risk (not a copy of planner simulation logic).
6. Full evaluate_planner_config() round-trip with mocked _fetch_actions.
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

_SCRIPT = _REPO_ROOT / "scripts" / "evaluate_planner_config.py"
_spec = importlib.util.spec_from_file_location("evaluate_planner_config", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

_classify_risk = _mod._classify_risk
build_evaluation = _mod.build_evaluation
evaluate_planner_config = _mod.evaluate_planner_config
_compute_risk = _mod._compute_risk          # imported from analyzer via the module
_fetch_actions_ref = _mod._fetch_actions    # same reference used for patching
ACTION_TO_TASK = _mod.ACTION_TO_TASK

_ANALYZER_SCRIPT = _REPO_ROOT / "scripts" / "analyze_planner_collision_risk.py"
_analyzer_spec = importlib.util.spec_from_file_location(
    "analyze_planner_collision_risk", _ANALYZER_SCRIPT
)
_analyzer_mod = importlib.util.module_from_spec(_analyzer_spec)
_analyzer_spec.loader.exec_module(_analyzer_mod)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_actions(specs):
    """Build action list from [(action_type, priority), ...] specs."""
    return [
        {
            "action_type": at,
            "priority": pri,
            "action_id": f"aid-{i}",
            "repo_id": f"repo-{i}",
        }
        for i, (at, pri) in enumerate(specs)
    ]


def _metrics(specs, top_k=3, mapping=None):
    """Compute risk metrics from action specs using real _compute_risk."""
    m = mapping if mapping is not None else dict(ACTION_TO_TASK)
    return _compute_risk(
        actions=_make_actions(specs),
        top_k=top_k,
        ledger={},
        signals={},
        policy={},
        active_mapping=m,
    )


# Canonical low-risk: 2 actions → 2 unique tasks, no collision
_LOW_SPECS = [
    ("analyze_repo_insights", 0.90),    # → repo_insights_example
    ("recover_failed_workflow", 0.80),  # → failure_recovery_example
]

# Canonical moderate-risk: 3 actions, 1 collision
_MOD_SPECS = [
    ("regenerate_missing_artifact", 0.95),  # → build_portfolio_dashboard (new)
    ("recover_failed_workflow", 0.85),      # → failure_recovery_example  (new)
    ("refresh_repo_health", 0.80),          # → build_portfolio_dashboard  (COLLISION)
]

# Canonical high-risk: 3 actions all → same task
_HIGH_SPECS = [
    ("refresh_repo_health", 0.90),
    ("regenerate_missing_artifact", 0.80),
    ("rerun_failed_task", 0.70),
]

_REQUIRED_EVAL_KEYS = {
    "ranked_action_window",
    "mapped_tasks",
    "unique_tasks",
    "collapse_count",
    "collision_ratio",
    "task_entropy",
    "action_entropy",
    "risk_level",
    "reasons",
    "recommendations",
}


# ---------------------------------------------------------------------------
# 1. JSON structure
# ---------------------------------------------------------------------------

class TestOutputStructure:
    def test_all_required_keys_present_low(self):
        ev = build_evaluation(_metrics(_LOW_SPECS, top_k=2), top_k=2)
        assert _REQUIRED_EVAL_KEYS <= set(ev.keys())

    def test_all_required_keys_present_moderate(self):
        ev = build_evaluation(_metrics(_MOD_SPECS), top_k=3)
        assert _REQUIRED_EVAL_KEYS <= set(ev.keys())

    def test_all_required_keys_present_high(self):
        ev = build_evaluation(_metrics(_HIGH_SPECS), top_k=3)
        assert _REQUIRED_EVAL_KEYS <= set(ev.keys())

    def test_risk_level_is_string(self):
        ev = build_evaluation(_metrics(_MOD_SPECS), top_k=3)
        assert isinstance(ev["risk_level"], str)

    def test_reasons_is_list(self):
        ev = build_evaluation(_metrics(_MOD_SPECS), top_k=3)
        assert isinstance(ev["reasons"], list)

    def test_recommendations_is_list(self):
        ev = build_evaluation(_metrics(_MOD_SPECS), top_k=3)
        assert isinstance(ev["recommendations"], list)

    def test_risk_level_is_valid_value(self):
        valid = {"low_risk", "moderate_risk", "high_risk"}
        for specs, tk in [(_LOW_SPECS, 2), (_MOD_SPECS, 3), (_HIGH_SPECS, 3)]:
            ev = build_evaluation(_metrics(specs, top_k=tk), top_k=tk)
            assert ev["risk_level"] in valid

    def test_original_metrics_preserved(self):
        m = _metrics(_MOD_SPECS)
        ev = build_evaluation(m, top_k=3)
        for key in m:
            assert ev[key] == m[key]


# ---------------------------------------------------------------------------
# 2. Deterministic classification
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_repeated_classify_risk_identical(self):
        m = _metrics(_MOD_SPECS)
        r1 = _classify_risk(m, top_k=3)
        r2 = _classify_risk(m, top_k=3)
        assert r1 == r2

    def test_repeated_build_evaluation_identical(self):
        m = _metrics(_MOD_SPECS)
        e1 = build_evaluation(m, top_k=3)
        e2 = build_evaluation(m, top_k=3)
        assert e1 == e2

    def test_risk_level_stable_across_calls(self):
        m = _metrics(_HIGH_SPECS)
        levels = {build_evaluation(m, top_k=3)["risk_level"] for _ in range(3)}
        assert len(levels) == 1


# ---------------------------------------------------------------------------
# 3. Risk case correctness
# ---------------------------------------------------------------------------

class TestRiskCases:
    def test_low_risk_no_collision(self):
        ev = build_evaluation(_metrics(_LOW_SPECS, top_k=2), top_k=2)
        assert ev["risk_level"] == "low_risk"

    def test_moderate_risk_one_collision(self):
        ev = build_evaluation(_metrics(_MOD_SPECS), top_k=3)
        assert ev["risk_level"] == "moderate_risk"

    def test_high_risk_ratio_geq_half(self):
        # 3 actions → 1 unique task: collision_ratio = 2/3 >= 0.5
        ev = build_evaluation(_metrics(_HIGH_SPECS), top_k=3)
        assert ev["risk_level"] == "high_risk"

    def test_high_risk_unique_tasks_leq_1_top_k_geq_3(self):
        # 3 actions all mapping to same task → unique_tasks=1, top_k=3
        m = _metrics(_HIGH_SPECS, top_k=3)
        assert m["unique_tasks"] == 1
        ev = build_evaluation(m, top_k=3)
        assert ev["risk_level"] == "high_risk"

    def test_high_risk_ratio_threshold_boundary(self):
        # collision_ratio == 0.5 exactly (2 of 4 collide)
        specs = [
            ("analyze_repo_insights", 0.95),        # → repo_insights_example (new)
            ("recover_failed_workflow", 0.85),       # → failure_recovery_example (new)
            ("refresh_repo_health", 0.80),           # → build_portfolio_dashboard (new)
            ("regenerate_missing_artifact", 0.70),   # → build_portfolio_dashboard (COLLISION)
        ]
        # With top_k=4 and 1 collision: ratio = 1/4 = 0.25 → moderate
        ev4 = build_evaluation(_metrics(specs, top_k=4), top_k=4)
        assert ev4["risk_level"] == "moderate_risk"

        # Force ratio = 0.5 by using a mapping with 2 collisions out of 4
        mapping = {
            "analyze_repo_insights": "task_a",
            "recover_failed_workflow": "task_a",        # collision
            "refresh_repo_health": "task_b",
            "regenerate_missing_artifact": "task_b",    # collision
        }
        ev_high = build_evaluation(_metrics(specs, top_k=4, mapping=mapping), top_k=4)
        assert ev_high["collision_ratio"] == 0.5
        assert ev_high["risk_level"] == "high_risk"

    def test_moderate_risk_via_entropy_gap(self):
        # Build metrics with collision_ratio=0 but forced entropy gap
        # Use a 1-action window to get action_entropy=0 and task_entropy=0: still low_risk.
        # Instead construct directly:
        m = {
            "ranked_action_window": ["a", "b", "c"],
            "mapped_tasks": ["t_a", "t_b", "t_c"],
            "unique_tasks": 3,
            "collapse_count": 0,
            "collision_ratio": 0.0,
            "task_entropy": 0.5,          # artificially set
            "action_entropy": 1.0,        # gap = 0.5 > threshold (0.3)
        }
        risk_level, reasons, recommendations = _classify_risk(m, top_k=3)
        assert risk_level == "moderate_risk"
        assert any("materially below" in r for r in reasons)

    def test_low_risk_zero_collision_ratio(self):
        m = _metrics(_LOW_SPECS, top_k=2)
        assert m["collision_ratio"] == 0.0
        ev = build_evaluation(m, top_k=2)
        assert ev["risk_level"] == "low_risk"

    def test_empty_window_is_high_risk(self):
        m = _compute_risk(
            actions=[],
            top_k=3,
            ledger={},
            signals={},
            policy={},
            active_mapping=dict(ACTION_TO_TASK),
        )
        ev = build_evaluation(m, top_k=3)
        assert ev["risk_level"] == "high_risk"
        assert ev["collapse_count"] == 0

    def test_empty_window_reason_mentions_empty_or_no_actions(self):
        m = _compute_risk(
            actions=[], top_k=3, ledger={}, signals={}, policy={},
            active_mapping=dict(ACTION_TO_TASK),
        )
        ev = build_evaluation(m, top_k=3)
        combined = " ".join(ev["reasons"]).lower()
        assert "empty" in combined or "no actions" in combined

    def test_empty_window_recommendations_non_empty(self):
        m = _compute_risk(
            actions=[], top_k=3, ledger={}, signals={}, policy={},
            active_mapping=dict(ACTION_TO_TASK),
        )
        ev = build_evaluation(m, top_k=3)
        assert len(ev["recommendations"]) > 0

    def test_empty_window_does_not_recommend_safe_to_use(self):
        m = _compute_risk(
            actions=[], top_k=3, ledger={}, signals={}, policy={},
            active_mapping=dict(ACTION_TO_TASK),
        )
        ev = build_evaluation(m, top_k=3)
        combined = " ".join(ev["recommendations"]).lower()
        assert "safe to use as-is" not in combined


# ---------------------------------------------------------------------------
# 4. Reasons and recommendations
# ---------------------------------------------------------------------------

class TestReasonsAndRecommendations:
    def test_high_risk_has_nonempty_reasons(self):
        ev = build_evaluation(_metrics(_HIGH_SPECS), top_k=3)
        assert len(ev["reasons"]) >= 1

    def test_high_risk_has_nonempty_recommendations(self):
        ev = build_evaluation(_metrics(_HIGH_SPECS), top_k=3)
        assert len(ev["recommendations"]) >= 1

    def test_moderate_risk_reasons_mention_collision(self):
        ev = build_evaluation(_metrics(_MOD_SPECS), top_k=3)
        assert any("collision" in r.lower() or "collapse" in r.lower() for r in ev["reasons"])

    def test_moderate_risk_recommendations_present(self):
        ev = build_evaluation(_metrics(_MOD_SPECS), top_k=3)
        assert len(ev["recommendations"]) >= 1

    def test_low_risk_recommends_safe_to_use(self):
        ev = build_evaluation(_metrics(_LOW_SPECS, top_k=2), top_k=2)
        assert any("safe" in r.lower() for r in ev["recommendations"])

    def test_high_risk_mentions_collapse_or_diversity(self):
        ev = build_evaluation(_metrics(_HIGH_SPECS), top_k=3)
        combined = " ".join(ev["reasons"]).lower()
        assert "collaps" in combined or "divers" in combined

    def test_reasons_are_strings(self):
        for specs, tk in [(_LOW_SPECS, 2), (_MOD_SPECS, 3), (_HIGH_SPECS, 3)]:
            ev = build_evaluation(_metrics(specs, top_k=tk), top_k=tk)
            assert all(isinstance(r, str) for r in ev["reasons"])

    def test_recommendations_are_strings(self):
        for specs, tk in [(_LOW_SPECS, 2), (_MOD_SPECS, 3), (_HIGH_SPECS, 3)]:
            ev = build_evaluation(_metrics(specs, top_k=tk), top_k=tk)
            assert all(isinstance(r, str) for r in ev["recommendations"])


# ---------------------------------------------------------------------------
# 5. Reuse of analyzer logic (not copy-pasted)
# ---------------------------------------------------------------------------

class TestAnalyzerReuse:
    """Verify the evaluator delegates to the analyzer's _compute_risk."""

    def test_evaluator_imports_from_analyzer_script(self):
        # The evaluator source must reference the analyzer module by name,
        # proving it loads rather than re-implements the simulation logic.
        source = _SCRIPT.read_text(encoding="utf-8")
        assert "analyze_planner_collision_risk" in source

    def test_compute_risk_behavioral_equivalence(self):
        # Both the evaluator's and the analyzer's _compute_risk must produce
        # identical output for the same inputs (same logic, same results).
        actions = _make_actions(_MOD_SPECS)
        kwargs = dict(
            actions=actions, top_k=3, ledger={}, signals={},
            policy={}, active_mapping=dict(ACTION_TO_TASK),
        )
        assert _mod._compute_risk(**kwargs) == _analyzer_mod._compute_risk(**kwargs)

    def test_metrics_values_match_analyzer_output(self):
        # build_evaluation preserves all metric keys unchanged
        m = _metrics(_MOD_SPECS)
        ev = build_evaluation(m, top_k=3)
        for key in ("ranked_action_window", "mapped_tasks", "unique_tasks",
                    "collapse_count", "collision_ratio", "task_entropy", "action_entropy"):
            assert ev[key] == m[key]


# ---------------------------------------------------------------------------
# 6. Full round-trip with mocked _fetch_actions
# ---------------------------------------------------------------------------

class TestEvaluatePlannerConfigRoundTrip:
    def _raw_actions(self):
        return _make_actions(_MOD_SPECS)

    def test_stdout_output_is_valid_json(self, tmp_path, capsys):
        portfolio_state = tmp_path / "ps.json"
        portfolio_state.write_text(json.dumps({"repos": []}), encoding="utf-8")

        with patch.object(_mod, "_fetch_actions", return_value=self._raw_actions()):
            evaluate_planner_config(
                policy_path=None,
                top_k=3,
                portfolio_state_path=str(portfolio_state),
                ledger_path=None,
                output_path=None,
            )

        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert _REQUIRED_EVAL_KEYS <= set(parsed.keys())

    def test_file_output_written_when_path_given(self, tmp_path):
        out = tmp_path / "eval.json"
        portfolio_state = tmp_path / "ps.json"
        portfolio_state.write_text(json.dumps({"repos": []}), encoding="utf-8")

        with patch.object(_mod, "_fetch_actions", return_value=self._raw_actions()):
            result = evaluate_planner_config(
                policy_path=None,
                top_k=3,
                portfolio_state_path=str(portfolio_state),
                ledger_path=None,
                output_path=str(out),
            )

        assert out.exists()
        written = json.loads(out.read_text(encoding="utf-8"))
        assert written == result

    def test_stdout_empty_when_file_output_given(self, tmp_path, capsys):
        out = tmp_path / "eval.json"
        portfolio_state = tmp_path / "ps.json"
        portfolio_state.write_text(json.dumps({"repos": []}), encoding="utf-8")

        with patch.object(_mod, "_fetch_actions", return_value=self._raw_actions()):
            evaluate_planner_config(
                policy_path=None,
                top_k=3,
                portfolio_state_path=str(portfolio_state),
                ledger_path=None,
                output_path=str(out),
            )

        captured = capsys.readouterr()
        # stdout should be empty (file path note goes to stderr)
        assert captured.out.strip() == ""

    def test_moderate_risk_round_trip(self, tmp_path):
        portfolio_state = tmp_path / "ps.json"
        portfolio_state.write_text(json.dumps({"repos": []}), encoding="utf-8")

        with patch.object(_mod, "_fetch_actions", return_value=self._raw_actions()):
            result = evaluate_planner_config(
                policy_path=None,
                top_k=3,
                portfolio_state_path=str(portfolio_state),
                ledger_path=None,
                output_path=str(tmp_path / "out.json"),
            )

        assert result["risk_level"] == "moderate_risk"

    def test_high_risk_round_trip(self, tmp_path):
        portfolio_state = tmp_path / "ps.json"
        portfolio_state.write_text(json.dumps({"repos": []}), encoding="utf-8")

        with patch.object(_mod, "_fetch_actions", return_value=_make_actions(_HIGH_SPECS)):
            result = evaluate_planner_config(
                policy_path=None,
                top_k=3,
                portfolio_state_path=str(portfolio_state),
                ledger_path=None,
                output_path=str(tmp_path / "out.json"),
            )

        assert result["risk_level"] == "high_risk"

    def test_low_risk_round_trip(self, tmp_path):
        portfolio_state = tmp_path / "ps.json"
        portfolio_state.write_text(json.dumps({"repos": []}), encoding="utf-8")

        with patch.object(_mod, "_fetch_actions", return_value=_make_actions(_LOW_SPECS)):
            result = evaluate_planner_config(
                policy_path=None,
                top_k=2,
                portfolio_state_path=str(portfolio_state),
                ledger_path=None,
                output_path=str(tmp_path / "out.json"),
            )

        assert result["risk_level"] == "low_risk"

    def test_deterministic_repeated_calls(self, tmp_path):
        portfolio_state = tmp_path / "ps.json"
        portfolio_state.write_text(json.dumps({"repos": []}), encoding="utf-8")
        actions = self._raw_actions()

        results = []
        for i in range(2):
            with patch.object(_mod, "_fetch_actions", return_value=actions):
                r = evaluate_planner_config(
                    policy_path=None,
                    top_k=3,
                    portfolio_state_path=str(portfolio_state),
                    ledger_path=None,
                    output_path=str(tmp_path / f"out{i}.json"),
                )
            results.append(r)

        assert results[0] == results[1]

    def test_mapping_override_changes_risk(self, tmp_path):
        portfolio_state = tmp_path / "ps.json"
        portfolio_state.write_text(json.dumps({"repos": []}), encoding="utf-8")
        override_file = tmp_path / "override.json"
        # Override: all three actions map to unique tasks → low_risk
        override_file.write_text(json.dumps({
            "regenerate_missing_artifact": "artifact_audit_example",
            "recover_failed_workflow": "failure_recovery_example",
            "refresh_repo_health": "repo_insights_example",
        }), encoding="utf-8")

        with patch.object(_mod, "_fetch_actions", return_value=_make_actions(_MOD_SPECS)):
            result = evaluate_planner_config(
                policy_path=None,
                top_k=3,
                portfolio_state_path=str(portfolio_state),
                ledger_path=None,
                mapping_override_path=str(override_file),
                output_path=str(tmp_path / "out.json"),
            )

        assert result["risk_level"] == "low_risk"
        assert result["collapse_count"] == 0


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

    def test_real_fixture_produces_valid_evaluation(self):
        import json as _json
        from scripts.planner_scoring import (
            load_effectiveness_ledger,
            load_portfolio_signals,
        )

        ps_data = _json.loads(self._PS.read_text(encoding="utf-8"))
        actions = []
        for repo in ps_data.get("repos", []):
            for act in repo.get("recommended_actions", []):
                entry = dict(act)
                entry.setdefault("repo_id", repo.get("repo_id", ""))
                actions.append(entry)

        ledger = load_effectiveness_ledger(str(self._LEDGER))
        signals = load_portfolio_signals(str(self._PS))

        metrics = _compute_risk(
            actions=actions,
            top_k=3,
            ledger=ledger,
            signals=signals,
            policy={},
            active_mapping=dict(ACTION_TO_TASK),
        )
        ev = build_evaluation(metrics, top_k=3)

        assert _REQUIRED_EVAL_KEYS <= set(ev.keys())
        assert ev["risk_level"] in {"low_risk", "moderate_risk", "high_risk"}
        assert len(ev["reasons"]) >= 1
        assert len(ev["recommendations"]) >= 1

    def test_real_fixture_deterministic(self):
        import json as _json
        from scripts.planner_scoring import (
            load_effectiveness_ledger,
            load_portfolio_signals,
        )

        ps_data = _json.loads(self._PS.read_text(encoding="utf-8"))
        actions = []
        for repo in ps_data.get("repos", []):
            for act in repo.get("recommended_actions", []):
                entry = dict(act)
                entry.setdefault("repo_id", repo.get("repo_id", ""))
                actions.append(entry)

        ledger = load_effectiveness_ledger(str(self._LEDGER))
        signals = load_portfolio_signals(str(self._PS))

        ev1 = build_evaluation(
            _compute_risk(actions, 3, ledger, signals, {}, dict(ACTION_TO_TASK)), top_k=3
        )
        ev2 = build_evaluation(
            _compute_risk(actions, 3, ledger, signals, {}, dict(ACTION_TO_TASK)), top_k=3
        )
        assert ev1 == ev2


# ---------------------------------------------------------------------------
# 9. entropy_gap >= 1.0 high-risk rule
# ---------------------------------------------------------------------------

def _metrics_from_raw(ranked_action_window, mapped_tasks):
    """Build a minimal metrics dict directly from window/mapping lists.

    Computes unique_tasks, collapse_count, collision_ratio, and entropy fields
    so that _classify_risk can be called without invoking _compute_risk.
    """
    from math import log2

    def _entropy(counts):
        total = sum(counts)
        if total == 0 or len(counts) <= 1:
            return 0.0
        result = 0.0
        for c in sorted(counts):
            if c > 0:
                p = c / total
                result -= p * log2(p)
        return round(result, 6)

    seen_tasks = {}
    for task in mapped_tasks:
        if task is not None:
            seen_tasks[task] = seen_tasks.get(task, 0) + 1
    action_counts = [1] * len(ranked_action_window)
    task_counts = list(seen_tasks.values())

    unique_tasks = len(seen_tasks)
    window_size = len(ranked_action_window)
    collapse_count = window_size - unique_tasks
    collision_ratio = round(collapse_count / window_size, 6) if window_size > 0 else 0.0
    task_entropy = _entropy(task_counts)
    action_entropy = _entropy(action_counts)

    return {
        "ranked_action_window": ranked_action_window,
        "mapped_tasks": mapped_tasks,
        "unique_tasks": unique_tasks,
        "collapse_count": collapse_count,
        "collision_ratio": collision_ratio,
        "task_entropy": task_entropy,
        "action_entropy": action_entropy,
    }


def _build_high_entropy_gap_metrics(gap_value):
    """Return a metrics dict whose entropy_gap equals gap_value.

    We craft action_entropy and task_entropy directly so the gap is precise.
    We use a window with no collisions (collision_ratio=0, unique_tasks=window_size)
    so the only high-risk trigger is the entropy_gap rule.
    """
    # 8 actions, each mapping to a unique task → collision_ratio=0, unique_tasks=8
    # action_entropy = log2(8) = 3.0 bits (uniform over 8)
    # We want task_entropy = 3.0 - gap_value
    # We achieve that by building a custom metrics dict with the desired entropies.
    actions = [f"a{i}" for i in range(8)]
    tasks   = [f"t{i}" for i in range(8)]
    m = _metrics_from_raw(actions, tasks)
    # Override entropies to achieve the desired gap exactly.
    m = dict(m)
    m["action_entropy"] = round(3.0, 6)
    m["task_entropy"]   = round(3.0 - gap_value, 6)
    return m


class TestEntropyGapHighRiskRule:
    """entropy_gap >= 1.0 must trigger high_risk regardless of collision_ratio."""

    # --- Positive cases: entropy_gap >= 1.0 → high_risk ---

    def test_entropy_gap_exactly_1_is_high_risk(self):
        m = _build_high_entropy_gap_metrics(1.0)
        level, reasons, _ = _classify_risk(m, top_k=3)
        assert level == "high_risk"

    def test_entropy_gap_above_1_is_high_risk(self):
        m = _build_high_entropy_gap_metrics(1.5)
        level, reasons, _ = _classify_risk(m, top_k=3)
        assert level == "high_risk"

    def test_entropy_gap_large_value_is_high_risk(self):
        m = _build_high_entropy_gap_metrics(2.9)
        level, reasons, _ = _classify_risk(m, top_k=3)
        assert level == "high_risk"

    def test_entropy_gap_high_risk_reason_mentions_entropy_gap(self):
        m = _build_high_entropy_gap_metrics(1.0)
        _, reasons, _ = _classify_risk(m, top_k=3)
        assert any("entropy_gap" in r for r in reasons)

    def test_entropy_gap_high_risk_reason_mentions_threshold(self):
        m = _build_high_entropy_gap_metrics(1.0)
        _, reasons, _ = _classify_risk(m, top_k=3)
        assert any("1.0" in r for r in reasons)

    def test_entropy_gap_high_risk_reason_mentions_compression(self):
        m = _build_high_entropy_gap_metrics(1.2)
        _, reasons, _ = _classify_risk(m, top_k=3)
        assert any("compression" in r.lower() for r in reasons)

    def test_entropy_gap_high_risk_recommendations_non_empty(self):
        m = _build_high_entropy_gap_metrics(1.0)
        _, _, recs = _classify_risk(m, top_k=3)
        assert len(recs) > 0

    # --- Boundary / negative cases: entropy_gap < 1.0 does not trigger rule ---

    def test_entropy_gap_just_below_1_not_triggered(self):
        """gap=0.999999 must NOT trigger the entropy_gap high-risk rule."""
        m = _build_high_entropy_gap_metrics(0.999999)
        # collision_ratio=0 and unique_tasks=8, so if entropy_gap rule fires it's wrong.
        level, reasons, _ = _classify_risk(m, top_k=3)
        # Should not be high_risk from the entropy_gap rule alone.
        # (It might be moderate_risk due to the entropy divergence threshold.)
        assert "entropy_gap is" not in " ".join(reasons) or level != "high_risk"
        # Stricter: no reason should mention >=1.0
        assert not any(">=1.0" in r for r in reasons)

    def test_entropy_gap_zero_not_triggered(self):
        """gap=0.0 must not trigger high_risk."""
        m = _build_high_entropy_gap_metrics(0.0)
        level, _, _ = _classify_risk(m, top_k=3)
        assert level != "high_risk"

    def test_entropy_gap_moderate_threshold_not_triggered(self):
        """gap=0.4 (above moderate threshold 0.3 but below 1.0) → not high_risk."""
        m = _build_high_entropy_gap_metrics(0.4)
        level, _, _ = _classify_risk(m, top_k=3)
        assert level != "high_risk"

    # --- Rule is independent of top_k ---

    def test_entropy_gap_1_high_risk_with_small_top_k(self):
        """entropy_gap >= 1.0 triggers high_risk even with top_k=1."""
        m = _build_high_entropy_gap_metrics(1.0)
        level, _, _ = _classify_risk(m, top_k=1)
        assert level == "high_risk"

    def test_entropy_gap_1_high_risk_with_large_top_k(self):
        """entropy_gap >= 1.0 triggers high_risk with top_k=10."""
        m = _build_high_entropy_gap_metrics(1.0)
        level, _, _ = _classify_risk(m, top_k=10)
        assert level == "high_risk"

    # --- Existing high-risk rules unaffected ---

    def test_collision_ratio_rule_still_fires(self):
        """collision_ratio >= 0.5 still triggers high_risk."""
        m = _metrics(_HIGH_SPECS, top_k=3)
        level, _, _ = _classify_risk(m, top_k=3)
        assert level == "high_risk"

    def test_unique_tasks_rule_still_fires(self):
        """unique_tasks <= 1 with top_k >= 3 still triggers high_risk."""
        # All 3 actions map to the same task → unique_tasks=1
        mapping = {at: "single_task" for at, _ in _HIGH_SPECS}
        m = _metrics(_HIGH_SPECS, top_k=3, mapping=mapping)
        assert m["unique_tasks"] == 1
        level, _, _ = _classify_risk(m, top_k=3)
        assert level == "high_risk"


# ---------------------------------------------------------------------------
# 8. evaluate_planner_config honors structured (by_action_id) overrides
# ---------------------------------------------------------------------------

class TestStructuredOverrideIntegration:
    """Integration: structured override must reach _compute_risk, not be dropped."""

    def _dup_actions(self):
        """Two same-type actions with different action_ids; all collapse without override."""
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

    def test_structured_override_reduces_collapse_in_evaluate(self, tmp_path):
        """evaluate_planner_config must honour by_action_id overrides."""
        ps = tmp_path / "ps.json"
        ps.write_text(json.dumps({"repos": []}), encoding="utf-8")

        # Without override: two regenerate_missing_artifact collapse to same task.
        with patch.object(_mod, "_fetch_actions", return_value=self._dup_actions()):
            base = evaluate_planner_config(
                policy_path=None, top_k=3,
                portfolio_state_path=str(ps), ledger_path=None,
                output_path=str(tmp_path / "base.json"),
            )
        assert base["collapse_count"] >= 1, "Baseline should have collision"

        # With structured override: two distinct action_ids → distinct tasks.
        override_file = tmp_path / "override.json"
        override_file.write_text(json.dumps({
            "by_action_id": {
                "regenerate_missing_artifact_repo-A": "artifact_audit_example",
                "regenerate_missing_artifact_repo-B": "failure_recovery_example",
            },
            "by_action_type": {
                "rerun_failed_task": "build_portfolio_dashboard",
            },
        }), encoding="utf-8")

        with patch.object(_mod, "_fetch_actions", return_value=self._dup_actions()):
            repaired = evaluate_planner_config(
                policy_path=None, top_k=3,
                portfolio_state_path=str(ps), ledger_path=None,
                mapping_override_path=str(override_file),
                output_path=str(tmp_path / "repaired.json"),
            )

        assert repaired["collapse_count"] == 0, (
            f"Structured override must eliminate collision; got collapse_count={repaired['collapse_count']}, "
            f"mapped_tasks={repaired['mapped_tasks']}"
        )
        assert repaired["unique_tasks"] == 3
        assert repaired["collision_ratio"] == 0.0
        assert repaired["risk_level"] == "low_risk"

    def test_by_action_id_tasks_appear_in_mapped_tasks(self, tmp_path):
        """The specific tasks from by_action_id must show in mapped_tasks."""
        ps = tmp_path / "ps.json"
        ps.write_text(json.dumps({"repos": []}), encoding="utf-8")
        override_file = tmp_path / "override.json"
        override_file.write_text(json.dumps({
            "by_action_id": {
                "regenerate_missing_artifact_repo-A": "artifact_audit_example",
                "regenerate_missing_artifact_repo-B": "failure_recovery_example",
            },
            "by_action_type": {
                "rerun_failed_task": "build_portfolio_dashboard",
            },
        }), encoding="utf-8")

        with patch.object(_mod, "_fetch_actions", return_value=self._dup_actions()):
            result = evaluate_planner_config(
                policy_path=None, top_k=3,
                portfolio_state_path=str(ps), ledger_path=None,
                mapping_override_path=str(override_file),
                output_path=str(tmp_path / "out.json"),
            )

        mapped = result["mapped_tasks"]
        assert "artifact_audit_example" in mapped, f"Expected artifact_audit_example in {mapped}"
        assert "failure_recovery_example" in mapped, f"Expected failure_recovery_example in {mapped}"
        assert "build_portfolio_dashboard" in mapped, f"Expected build_portfolio_dashboard in {mapped}"

    def test_structured_override_without_by_action_id_still_works(self, tmp_path):
        """A structured override with only by_action_type must also work correctly."""
        ps = tmp_path / "ps.json"
        ps.write_text(json.dumps({"repos": []}), encoding="utf-8")
        # Override maps all colliding action_types to distinct tasks via by_action_type.
        override_file = tmp_path / "override.json"
        override_file.write_text(json.dumps({
            "by_action_type": {
                "regenerate_missing_artifact": "artifact_audit_example",
                "rerun_failed_task": "failure_recovery_example",
            },
        }), encoding="utf-8")

        # Action window: all distinct action_types.
        actions = [
            {"action_type": "rerun_failed_task", "action_id": "a1",
             "repo_id": "r1", "priority": 0.9},
            {"action_type": "regenerate_missing_artifact", "action_id": "a2",
             "repo_id": "r2", "priority": 0.8},
        ]
        with patch.object(_mod, "_fetch_actions", return_value=actions):
            result = evaluate_planner_config(
                policy_path=None, top_k=2,
                portfolio_state_path=str(ps), ledger_path=None,
                mapping_override_path=str(override_file),
                output_path=str(tmp_path / "out.json"),
            )

        assert result["collapse_count"] == 0
        assert "artifact_audit_example" in result["mapped_tasks"]
        assert "failure_recovery_example" in result["mapped_tasks"]

    def test_flat_override_still_honored(self, tmp_path):
        """Flat override (backward compat) must still be honored in evaluate."""
        ps = tmp_path / "ps.json"
        ps.write_text(json.dumps({"repos": []}), encoding="utf-8")
        actions = _make_actions(_HIGH_SPECS)  # all collapse to build_portfolio_dashboard

        override_file = tmp_path / "override.json"
        override_file.write_text(json.dumps({
            "refresh_repo_health": "repo_insights_example",
            "regenerate_missing_artifact": "artifact_audit_example",
            "rerun_failed_task": "failure_recovery_example",
        }), encoding="utf-8")

        with patch.object(_mod, "_fetch_actions", return_value=actions):
            result = evaluate_planner_config(
                policy_path=None, top_k=3,
                portfolio_state_path=str(ps), ledger_path=None,
                mapping_override_path=str(override_file),
                output_path=str(tmp_path / "out.json"),
            )

        assert result["collapse_count"] == 0
        assert result["risk_level"] == "low_risk"


class TestHistoricalSuccessSignals:
    def test_round_trip_includes_expected_success_rate_and_historical_runs(self, tmp_path):
        portfolio_state = tmp_path / "ps.json"
        portfolio_state.write_text(json.dumps({"repos": []}), encoding="utf-8")

        ledger = tmp_path / "ledger.json"
        ledger.write_text(json.dumps({
            "actions": {
                "build_portfolio_dashboard": {
                    "total_runs": 10,
                    "success_count": 8,
                    "failure_count": 2,
                    "last_status": "ok",
                },
                "failure_recovery_example": {
                    "total_runs": 5,
                    "success_count": 2,
                    "failure_count": 3,
                    "last_status": "aborted",
                },
            }
        }), encoding="utf-8")

        with patch.object(_mod, "_fetch_actions", return_value=_make_actions(_MOD_SPECS)):
            result = evaluate_planner_config(
                policy_path=None,
                top_k=3,
                portfolio_state_path=str(portfolio_state),
                ledger_path=str(ledger),
                output_path=str(tmp_path / "out.json"),
            )

        assert result["expected_success_rate"] == 0.5
        assert result["historical_runs"] == 15

    def test_round_trip_uses_only_mapped_tasks_present_in_ledger(self, tmp_path):
        portfolio_state = tmp_path / "ps.json"
        portfolio_state.write_text(json.dumps({"repos": []}), encoding="utf-8")

        ledger = tmp_path / "ledger.json"
        ledger.write_text(json.dumps({
            "actions": {
                "build_portfolio_dashboard": {
                    "total_runs": 4,
                    "success_count": 4,
                    "failure_count": 0,
                    "last_status": "ok",
                },
            }
        }), encoding="utf-8")

        with patch.object(_mod, "_fetch_actions", return_value=_make_actions(_MOD_SPECS)):
            result = evaluate_planner_config(
                policy_path=None,
                top_k=3,
                portfolio_state_path=str(portfolio_state),
                ledger_path=str(ledger),
                output_path=str(tmp_path / "out.json"),
            )

        assert result["expected_success_rate"] == 1.0
        assert result["historical_runs"] == 4

    def test_round_trip_returns_none_and_zero_when_no_history_matches(self, tmp_path):
        portfolio_state = tmp_path / "ps.json"
        portfolio_state.write_text(json.dumps({"repos": []}), encoding="utf-8")

        ledger = tmp_path / "ledger.json"
        ledger.write_text(json.dumps({
            "actions": {
                "unrelated_task": {
                    "total_runs": 9,
                    "success_count": 9,
                    "failure_count": 0,
                    "last_status": "ok",
                },
            }
        }), encoding="utf-8")

        with patch.object(_mod, "_fetch_actions", return_value=_make_actions(_LOW_SPECS)):
            result = evaluate_planner_config(
                policy_path=None,
                top_k=2,
                portfolio_state_path=str(portfolio_state),
                ledger_path=str(ledger),
                output_path=str(tmp_path / "out.json"),
            )

        assert result["expected_success_rate"] is None
        assert result["historical_runs"] == 0


class TestReliabilityWeightedRanking:
    def test_reliable_task_is_promoted_over_equal_priority_peer(self, tmp_path):
        portfolio_state = tmp_path / "ps.json"
        portfolio_state.write_text(json.dumps({"repos": []}), encoding="utf-8")

        ledger = tmp_path / "ledger.json"
        ledger.write_text(json.dumps({
            "actions": {
                "repo_insights_example": {
                    "total_runs": 10,
                    "success_count": 9,
                    "failure_count": 1,
                    "last_status": "ok",
                },
                "failure_recovery_example": {
                    "total_runs": 10,
                    "success_count": 1,
                    "failure_count": 9,
                    "last_status": "aborted",
                },
            }
        }), encoding="utf-8")

        actions = [
            {
                "action_type": "recover_failed_workflow",
                "priority": 0.80,
                "action_id": "a-1",
                "repo_id": "repo-1",
            },
            {
                "action_type": "analyze_repo_insights",
                "priority": 0.80,
                "action_id": "a-2",
                "repo_id": "repo-1",
            },
        ]

        with patch.object(_mod, "_fetch_actions", return_value=actions):
            result = evaluate_planner_config(
                policy_path=None,
                top_k=2,
                portfolio_state_path=str(portfolio_state),
                ledger_path=str(ledger),
                output_path=str(tmp_path / "out.json"),
            )

        assert result["ranked_action_window"][0] == "analyze_repo_insights"
        assert result["mapped_tasks"][0] == "repo_insights_example"

    def test_no_history_preserves_base_priority_order(self, tmp_path):
        portfolio_state = tmp_path / "ps.json"
        portfolio_state.write_text(json.dumps({"repos": []}), encoding="utf-8")

        actions = [
            {
                "action_type": "recover_failed_workflow",
                "priority": 0.81,
                "action_id": "a-1",
                "repo_id": "repo-1",
            },
            {
                "action_type": "analyze_repo_insights",
                "priority": 0.80,
                "action_id": "a-2",
                "repo_id": "repo-1",
            },
        ]

        with patch.object(_mod, "_fetch_actions", return_value=actions):
            result = evaluate_planner_config(
                policy_path=None,
                top_k=2,
                portfolio_state_path=str(portfolio_state),
                ledger_path=None,
                output_path=str(tmp_path / "out.json"),
            )

        assert result["ranked_action_window"] == [
            "recover_failed_workflow",
            "analyze_repo_insights",
        ]
