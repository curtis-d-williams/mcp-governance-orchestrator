# SPDX-License-Identifier: MIT
"""Regression tests for scripts/run_governed_planner_loop.py.

Covers:
1. low_risk on first attempt executes immediately (no retries).
2. high_risk then low_risk retries and selects the later offset.
3. moderate_risk executes without further retries.
4. all high_risk aborts with SystemExit(1) without --force.
5. all high_risk with --force executes the final attempt.
6. Output structure includes required keys (selected_offset, attempts, result).
7. _build_offset_sequence deduplication and ordering.
8. Empty-window high_risk short-circuits immediately (no further offset retries).
9. Mapping override threaded through preflight and execution.
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

_SCRIPT = _REPO_ROOT / "scripts" / "run_governed_planner_loop.py"
_spec = importlib.util.spec_from_file_location("run_governed_planner_loop", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

run_governed_loop = _mod.run_governed_loop
_build_offset_sequence = _mod._build_offset_sequence
_is_empty_window_high_risk = _mod._is_empty_window_high_risk


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_args(tmp_path, **kwargs):
    """Build a minimal args-like namespace for run_governed_loop."""
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
        output=str(tmp_path / "governed_result.json"),
        envelope_prefix="planner_run_envelope",
        mapping_override=None,
    )
    defaults.update(kwargs)
    for k, v in defaults.items():
        setattr(obj, k, v)
    return obj


def _make_envelope(tmp_path, run_number=1, prefix="planner_run_envelope"):
    """Write a minimal valid envelope file and return its path."""
    envelope = {
        "planner_version": "0.36",
        "inputs": {
            "top_k": 3, "exploration_offset": 0, "policy": None,
            "ledger": None, "portfolio_state": None, "explain": False,
            "max_actions": None,
        },
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
    path = tmp_path / f"{prefix}_run{run_number}.json"
    path.write_text(json.dumps(envelope, indent=2) + "\n", encoding="utf-8")
    return path


def _noop_planner(argv):
    """Planner stub that writes a minimal valid envelope."""
    import argparse as _ap
    p = _ap.ArgumentParser()
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
            "inputs": {
                "top_k": ns.top_k, "exploration_offset": ns.exploration_offset,
                "policy": ns.policy, "ledger": ns.ledger,
                "portfolio_state": ns.portfolio_state, "explain": ns.explain,
                "max_actions": ns.max_actions,
            },
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


def _preflight_sequence(risk_levels):
    """Return a preflight_fn that returns risk levels from a list in order."""
    calls = iter(risk_levels)

    def _fn(args):
        level = next(calls)
        return {
            "risk_level": level,
            "collision_ratio": 0.67 if level == "high_risk" else 0.0,
            "unique_tasks": 1 if level == "high_risk" else 2,
        }

    return _fn


def _preflight_always(level):
    """Return a preflight_fn that always returns the same risk level."""
    return _preflight_sequence([level] * 20)


# ---------------------------------------------------------------------------
# 1. low_risk on first attempt executes immediately
# ---------------------------------------------------------------------------

class TestLowRiskFirstAttempt:
    def test_executes_without_retry(self, tmp_path):
        args = _make_args(tmp_path, exploration_offset=0)
        calls = []

        def tracking_preflight(a):
            calls.append(a.exploration_offset)
            return {"risk_level": "low_risk", "collision_ratio": 0.0, "unique_tasks": 2}

        result = run_governed_loop(args, planner_main=_noop_planner,
                                   preflight_fn=tracking_preflight)
        assert len(calls) == 1

    def test_selected_offset_is_starting_offset(self, tmp_path):
        args = _make_args(tmp_path, exploration_offset=0)
        result = run_governed_loop(args, planner_main=_noop_planner,
                                   preflight_fn=_preflight_always("low_risk"))
        assert result["selected_offset"] == 0

    def test_attempts_has_one_entry(self, tmp_path):
        args = _make_args(tmp_path, exploration_offset=0)
        result = run_governed_loop(args, planner_main=_noop_planner,
                                   preflight_fn=_preflight_always("low_risk"))
        assert len(result["attempts"]) == 1

    def test_attempts_entry_has_correct_risk(self, tmp_path):
        args = _make_args(tmp_path, exploration_offset=0)
        result = run_governed_loop(args, planner_main=_noop_planner,
                                   preflight_fn=_preflight_always("low_risk"))
        assert result["attempts"][0]["risk_level"] == "low_risk"

    def test_result_key_present(self, tmp_path):
        args = _make_args(tmp_path)
        result = run_governed_loop(args, planner_main=_noop_planner,
                                   preflight_fn=_preflight_always("low_risk"))
        assert "result" in result

    def test_forced_key_absent(self, tmp_path):
        args = _make_args(tmp_path)
        result = run_governed_loop(args, planner_main=_noop_planner,
                                   preflight_fn=_preflight_always("low_risk"))
        assert "forced" not in result


# ---------------------------------------------------------------------------
# 2. high_risk then low_risk retries and selects the later offset
# ---------------------------------------------------------------------------

class TestHighThenLowRisk:
    def test_retries_to_later_offset(self, tmp_path):
        args = _make_args(tmp_path, exploration_offset=0)
        result = run_governed_loop(
            args, planner_main=_noop_planner,
            preflight_fn=_preflight_sequence(["high_risk", "low_risk"]),
        )
        assert result["selected_offset"] != 0

    def test_attempts_has_two_entries(self, tmp_path):
        args = _make_args(tmp_path, exploration_offset=0)
        result = run_governed_loop(
            args, planner_main=_noop_planner,
            preflight_fn=_preflight_sequence(["high_risk", "low_risk"]),
        )
        assert len(result["attempts"]) == 2

    def test_first_attempt_is_high_risk(self, tmp_path):
        args = _make_args(tmp_path, exploration_offset=0)
        result = run_governed_loop(
            args, planner_main=_noop_planner,
            preflight_fn=_preflight_sequence(["high_risk", "low_risk"]),
        )
        assert result["attempts"][0]["risk_level"] == "high_risk"

    def test_second_attempt_is_low_risk(self, tmp_path):
        args = _make_args(tmp_path, exploration_offset=0)
        result = run_governed_loop(
            args, planner_main=_noop_planner,
            preflight_fn=_preflight_sequence(["high_risk", "low_risk"]),
        )
        assert result["attempts"][1]["risk_level"] == "low_risk"

    def test_result_present_after_retry(self, tmp_path):
        args = _make_args(tmp_path, exploration_offset=0)
        result = run_governed_loop(
            args, planner_main=_noop_planner,
            preflight_fn=_preflight_sequence(["high_risk", "low_risk"]),
        )
        assert "result" in result

    def test_attempts_record_offsets(self, tmp_path):
        args = _make_args(tmp_path, exploration_offset=0)
        result = run_governed_loop(
            args, planner_main=_noop_planner,
            preflight_fn=_preflight_sequence(["high_risk", "low_risk"]),
        )
        offsets = [a["offset"] for a in result["attempts"]]
        # First offset is the starting one; both must be distinct.
        assert offsets[0] == 0
        assert offsets[1] != offsets[0]


# ---------------------------------------------------------------------------
# 3. moderate_risk executes without further retries
# ---------------------------------------------------------------------------

class TestModerateRiskExecutesImmediately:
    def test_executes_on_moderate_risk(self, tmp_path):
        args = _make_args(tmp_path)
        result = run_governed_loop(args, planner_main=_noop_planner,
                                   preflight_fn=_preflight_always("moderate_risk"))
        assert "result" in result

    def test_only_one_attempt_for_moderate(self, tmp_path):
        args = _make_args(tmp_path, exploration_offset=0)
        calls = []

        def tracking(a):
            calls.append(1)
            return {"risk_level": "moderate_risk", "collision_ratio": 0.1, "unique_tasks": 2}

        run_governed_loop(args, planner_main=_noop_planner, preflight_fn=tracking)
        assert len(calls) == 1

    def test_forced_key_absent_for_moderate(self, tmp_path):
        args = _make_args(tmp_path)
        result = run_governed_loop(args, planner_main=_noop_planner,
                                   preflight_fn=_preflight_always("moderate_risk"))
        assert "forced" not in result

    def test_selected_offset_correct_for_moderate(self, tmp_path):
        args = _make_args(tmp_path, exploration_offset=2)
        result = run_governed_loop(args, planner_main=_noop_planner,
                                   preflight_fn=_preflight_always("moderate_risk"))
        assert result["selected_offset"] == 2


# ---------------------------------------------------------------------------
# 4. all high_risk aborts with SystemExit(1) (no --force)
# ---------------------------------------------------------------------------

class TestAllHighRiskAborts:
    def test_raises_system_exit(self, tmp_path):
        args = _make_args(tmp_path, force=False)
        with pytest.raises(SystemExit) as exc_info:
            run_governed_loop(args, planner_main=_noop_planner,
                              preflight_fn=_preflight_always("high_risk"))
        assert exc_info.value.code == 1

    def test_planner_not_called_on_abort(self, tmp_path):
        args = _make_args(tmp_path, force=False)
        planner_calls = []

        def tracking_planner(argv):
            planner_calls.append(argv)
            _noop_planner(argv)

        with pytest.raises(SystemExit):
            run_governed_loop(args, planner_main=tracking_planner,
                              preflight_fn=_preflight_always("high_risk"))
        assert len(planner_calls) == 0

    def test_all_attempts_recorded_before_abort(self, tmp_path):
        args = _make_args(tmp_path, exploration_offset=0, force=False)
        attempts_seen = []

        def recording_preflight(a):
            attempts_seen.append(a.exploration_offset)
            return {"risk_level": "high_risk", "collision_ratio": 0.67, "unique_tasks": 1}

        with pytest.raises(SystemExit):
            run_governed_loop(args, planner_main=_noop_planner,
                              preflight_fn=recording_preflight)
        # All offsets in the sequence must have been tried.
        assert len(attempts_seen) > 1

    def test_abort_prints_to_stderr(self, tmp_path, capsys):
        args = _make_args(tmp_path, force=False)
        with pytest.raises(SystemExit):
            run_governed_loop(args, planner_main=_noop_planner,
                              preflight_fn=_preflight_always("high_risk"))
        assert len(capsys.readouterr().err) > 0

    def test_abort_writes_artifact_file(self, tmp_path):
        """Abort now writes an artifact before raising — the file must exist."""
        output = tmp_path / "governed_result.json"
        args = _make_args(tmp_path, force=False, output=str(output))
        with pytest.raises(SystemExit):
            run_governed_loop(args, planner_main=_noop_planner,
                              preflight_fn=_preflight_always("high_risk"))
        assert output.exists()


# ---------------------------------------------------------------------------
# 5. all high_risk with --force executes final attempt
# ---------------------------------------------------------------------------

class TestAllHighRiskWithForce:
    def test_does_not_raise(self, tmp_path):
        args = _make_args(tmp_path, force=True)
        result = run_governed_loop(args, planner_main=_noop_planner,
                                   preflight_fn=_preflight_always("high_risk"))
        assert result is not None

    def test_forced_key_is_true(self, tmp_path):
        args = _make_args(tmp_path, force=True)
        result = run_governed_loop(args, planner_main=_noop_planner,
                                   preflight_fn=_preflight_always("high_risk"))
        assert result.get("forced") is True

    def test_result_key_present_with_force(self, tmp_path):
        args = _make_args(tmp_path, force=True)
        result = run_governed_loop(args, planner_main=_noop_planner,
                                   preflight_fn=_preflight_always("high_risk"))
        assert "result" in result

    def test_selected_offset_is_last_offset(self, tmp_path):
        args = _make_args(tmp_path, force=True, exploration_offset=0)
        result = run_governed_loop(args, planner_main=_noop_planner,
                                   preflight_fn=_preflight_always("high_risk"))
        # selected_offset must be one of the tried offsets (the last one).
        assert result["selected_offset"] == result["attempts"][-1]["offset"]

    def test_all_offsets_tried_before_force(self, tmp_path):
        args = _make_args(tmp_path, force=True, exploration_offset=0)
        calls = []

        def tracking(a):
            calls.append(a.exploration_offset)
            return {"risk_level": "high_risk", "collision_ratio": 0.67, "unique_tasks": 1}

        result = run_governed_loop(args, planner_main=_noop_planner, preflight_fn=tracking)
        # Every tracked offset must appear in the attempts list.
        attempt_offsets = [a["offset"] for a in result["attempts"]]
        assert calls == attempt_offsets


# ---------------------------------------------------------------------------
# 6. Output structure
# ---------------------------------------------------------------------------

class TestOutputStructure:
    _REQUIRED_KEYS = {"selected_offset", "attempts", "result"}

    def test_required_keys_present_on_success(self, tmp_path):
        args = _make_args(tmp_path)
        result = run_governed_loop(args, planner_main=_noop_planner,
                                   preflight_fn=_preflight_always("low_risk"))
        assert self._REQUIRED_KEYS <= set(result.keys())

    def test_attempts_is_list(self, tmp_path):
        args = _make_args(tmp_path)
        result = run_governed_loop(args, planner_main=_noop_planner,
                                   preflight_fn=_preflight_always("low_risk"))
        assert isinstance(result["attempts"], list)

    def test_each_attempt_has_offset_and_risk(self, tmp_path):
        args = _make_args(tmp_path)
        result = run_governed_loop(
            args, planner_main=_noop_planner,
            preflight_fn=_preflight_sequence(["high_risk", "low_risk"]),
        )
        for attempt in result["attempts"]:
            assert "offset" in attempt
            assert "risk_level" in attempt

    def test_artifact_written_to_output_path(self, tmp_path):
        output = tmp_path / "my_governed.json"
        args = _make_args(tmp_path, output=str(output))
        run_governed_loop(args, planner_main=_noop_planner,
                          preflight_fn=_preflight_always("low_risk"))
        assert output.exists()

    def test_artifact_is_valid_json(self, tmp_path):
        output = tmp_path / "out.json"
        args = _make_args(tmp_path, output=str(output))
        run_governed_loop(args, planner_main=_noop_planner,
                          preflight_fn=_preflight_always("low_risk"))
        data = json.loads(output.read_text(encoding="utf-8"))
        assert isinstance(data, dict)

    def test_artifact_selected_offset_matches_return(self, tmp_path):
        output = tmp_path / "out.json"
        args = _make_args(tmp_path, output=str(output))
        result = run_governed_loop(args, planner_main=_noop_planner,
                                   preflight_fn=_preflight_always("low_risk"))
        data = json.loads(output.read_text(encoding="utf-8"))
        assert data["selected_offset"] == result["selected_offset"]

    def test_forced_run_artifact_includes_forced_key(self, tmp_path):
        output = tmp_path / "out.json"
        args = _make_args(tmp_path, force=True, output=str(output))
        run_governed_loop(args, planner_main=_noop_planner,
                          preflight_fn=_preflight_always("high_risk"))
        data = json.loads(output.read_text(encoding="utf-8"))
        assert data.get("forced") is True


# ---------------------------------------------------------------------------
# 7. _build_offset_sequence
# ---------------------------------------------------------------------------

class TestBuildOffsetSequence:
    def test_starting_offset_is_first(self):
        seq = _build_offset_sequence(0)
        assert seq[0] == 0

    def test_no_duplicates(self):
        seq = _build_offset_sequence(0)
        assert len(seq) == len(set(seq))

    def test_starting_offset_not_duplicated_when_in_defaults(self):
        # 1 is in _DEFAULT_OFFSETS; it should appear only once.
        seq = _build_offset_sequence(1)
        assert seq.count(1) == 1

    def test_starting_offset_not_in_defaults_is_prepended(self):
        seq = _build_offset_sequence(99)
        assert seq[0] == 99
        # 0, 1, 2, 3, 5 are all still present
        assert 0 in seq

    def test_default_starting_zero_includes_all_defaults(self):
        seq = _build_offset_sequence(0)
        for expected in [0, 1, 2, 3, 5]:
            assert expected in seq

    def test_length_with_novel_start(self):
        seq = _build_offset_sequence(99)
        # 99 + 5 default values = 6
        assert len(seq) == 6

    def test_length_with_default_start_zero(self):
        seq = _build_offset_sequence(0)
        # 0 is already in defaults, so length = 5
        assert len(seq) == 5


# ---------------------------------------------------------------------------
# 8. Empty-window high_risk short-circuits immediately
# ---------------------------------------------------------------------------

def _empty_window_preflight(args):
    """Preflight stub that always returns empty-window high_risk."""
    return {
        "risk_level": "high_risk",
        "collision_ratio": 0.0,
        "unique_tasks": 0,
        "reasons": [
            "action window is empty: the planner produced no actions for the given inputs"
        ],
        "recommendations": ["inspect portfolio state"],
    }


def _collision_high_risk_preflight(risk_levels):
    """Preflight stub returning collision-based high_risk, then optionally better."""
    calls = iter(risk_levels)

    def _fn(args):
        level = next(calls)
        return {
            "risk_level": level,
            "collision_ratio": 0.67 if level == "high_risk" else 0.0,
            "unique_tasks": 1 if level == "high_risk" else 3,
            "reasons": ["collision_ratio is 0.670000 (>=0.5): ..."] if level == "high_risk" else [],
            "recommendations": [],
        }

    return _fn


class TestEmptyWindowShortCircuit:
    def test_empty_window_aborts_after_single_attempt(self, tmp_path):
        """Empty-window high_risk must not try further offsets — exits after 1 attempt."""
        args = _make_args(tmp_path, force=False, exploration_offset=0)
        calls = []

        def tracking_preflight(a):
            calls.append(a.exploration_offset)
            return _empty_window_preflight(a)

        with pytest.raises(SystemExit) as exc_info:
            run_governed_loop(args, planner_main=_noop_planner,
                              preflight_fn=tracking_preflight)

        assert exc_info.value.code == 1
        assert len(calls) == 1  # short-circuited after first attempt

    def test_empty_window_abort_records_attempt(self, tmp_path, capsys):
        """Attempts list contains the single failing attempt even on abort."""
        args = _make_args(tmp_path, force=False)

        # Capture attempts via a side-channel before the exception propagates.
        recorded = []

        def tracking_preflight(a):
            ev = _empty_window_preflight(a)
            recorded.append(ev)
            return ev

        with pytest.raises(SystemExit):
            run_governed_loop(args, planner_main=_noop_planner,
                              preflight_fn=tracking_preflight)

        assert len(recorded) == 1
        assert recorded[0]["risk_level"] == "high_risk"

    def test_empty_window_force_executes_immediately(self, tmp_path):
        """With --force, empty-window high_risk executes after 1 attempt (no retries)."""
        args = _make_args(tmp_path, force=True, exploration_offset=0)
        calls = []

        def tracking_preflight(a):
            calls.append(a.exploration_offset)
            return _empty_window_preflight(a)

        result = run_governed_loop(args, planner_main=_noop_planner,
                                   preflight_fn=tracking_preflight)

        assert len(calls) == 1  # executed immediately, no retries
        assert result.get("forced") is True
        assert "result" in result

    def test_empty_window_force_selected_offset_matches_attempt(self, tmp_path):
        """With --force, selected_offset is the first (and only) attempted offset."""
        args = _make_args(tmp_path, force=True, exploration_offset=2)
        result = run_governed_loop(args, planner_main=_noop_planner,
                                   preflight_fn=_empty_window_preflight)
        assert result["selected_offset"] == result["attempts"][0]["offset"]

    def test_non_empty_high_risk_still_retries(self, tmp_path):
        """Collision-based high_risk must still retry across multiple offsets."""
        args = _make_args(tmp_path, force=False, exploration_offset=0)
        calls = []

        def tracking_preflight(a):
            calls.append(a.exploration_offset)
            return _collision_high_risk_preflight(["high_risk", "low_risk"])(a)

        # Reset the generator each time via a fresh closure.
        risk_iter = iter(["high_risk", "low_risk"])

        def fresh_preflight(a):
            calls.append(a.exploration_offset)
            level = next(risk_iter)
            return {
                "risk_level": level,
                "collision_ratio": 0.67 if level == "high_risk" else 0.0,
                "unique_tasks": 1 if level == "high_risk" else 3,
                "reasons": ["collision_ratio is 0.670000 (>=0.5): ..."] if level == "high_risk" else [],
                "recommendations": [],
            }

        result = run_governed_loop(args, planner_main=_noop_planner,
                                   preflight_fn=fresh_preflight)

        assert len(calls) == 2  # retried — did not short-circuit
        assert result["attempts"][0]["risk_level"] == "high_risk"
        assert result["attempts"][1]["risk_level"] == "low_risk"


class TestIsEmptyWindowHighRisk:
    """Unit tests for the _is_empty_window_high_risk helper."""

    def test_returns_true_for_empty_window_reason(self):
        ev = {
            "risk_level": "high_risk",
            "reasons": ["action window is empty: the planner produced no actions for the given inputs"],
        }
        assert _is_empty_window_high_risk(ev) is True

    def test_returns_true_for_no_actions_reason(self):
        ev = {"risk_level": "high_risk", "reasons": ["no actions available"]}
        assert _is_empty_window_high_risk(ev) is True

    def test_returns_false_for_collision_reason(self):
        ev = {
            "risk_level": "high_risk",
            "reasons": ["collision_ratio is 0.670000 (>=0.5): more than half the window..."],
        }
        assert _is_empty_window_high_risk(ev) is False

    def test_returns_false_for_low_risk(self):
        ev = {"risk_level": "low_risk", "reasons": ["action window is empty"]}
        assert _is_empty_window_high_risk(ev) is False

    def test_returns_false_for_none(self):
        assert _is_empty_window_high_risk(None) is False

    def test_returns_false_for_empty_reasons(self):
        ev = {"risk_level": "high_risk", "reasons": []}
        assert _is_empty_window_high_risk(ev) is False


# ---------------------------------------------------------------------------
# 11. Governance metadata in artifact
# ---------------------------------------------------------------------------

class TestGovernanceMetadata:
    def test_artifact_contains_governance_key(self, tmp_path):
        """Every successful artifact must include a top-level 'governance' key."""
        args = _make_args(tmp_path)
        result = run_governed_loop(args, planner_main=_noop_planner,
                                   preflight_fn=_preflight_always("low_risk"))
        assert "governance" in result

    def test_governance_contains_planner_version(self, tmp_path):
        """governance.planner_version must be populated from the run result."""
        args = _make_args(tmp_path)
        result = run_governed_loop(args, planner_main=_noop_planner,
                                   preflight_fn=_preflight_always("low_risk"))
        assert result["governance"]["planner_version"] == "0.36"

    def test_governance_mapping_override_is_none_when_absent(self, tmp_path):
        """governance.mapping_override is None when no override was provided."""
        args = _make_args(tmp_path)  # mapping_override_path not set
        result = run_governed_loop(args, planner_main=_noop_planner,
                                   preflight_fn=_preflight_always("low_risk"))
        assert result["governance"]["mapping_override"] is None

    def test_governance_mapping_override_recorded_when_cli_flag_used(self, tmp_path):
        """governance.mapping_override records the file path when override is given."""
        override_data = {"action_a": "task_x"}
        override_file = tmp_path / "override.json"
        override_file.write_text(json.dumps(override_data) + "\n", encoding="utf-8")
        output = tmp_path / "governed_result.json"

        captured_governance = []

        def capturing_loop(args, **kwargs):
            # Run real loop, capture result, then return it.
            r = run_governed_loop(args, planner_main=_noop_planner,
                                  preflight_fn=_preflight_always("low_risk"))
            captured_governance.append(r.get("governance"))
            return r

        original = _mod.run_governed_loop
        _mod.run_governed_loop = capturing_loop
        try:
            _mod.main([
                "--mapping-override", str(override_file),
                "--output", str(output),
            ])
        finally:
            _mod.run_governed_loop = original

        assert len(captured_governance) == 1
        assert captured_governance[0]["mapping_override"] == str(override_file)

    def test_governance_contains_governed_loop_version(self, tmp_path):
        """governance.governed_loop_version is present and non-empty."""
        args = _make_args(tmp_path)
        result = run_governed_loop(args, planner_main=_noop_planner,
                                   preflight_fn=_preflight_always("low_risk"))
        assert result["governance"].get("governed_loop_version")

    def test_governance_present_in_forced_run(self, tmp_path):
        """governance block is included when --force overrides high_risk."""
        args = _make_args(tmp_path, force=True)
        result = run_governed_loop(args, planner_main=_noop_planner,
                                   preflight_fn=_preflight_always("high_risk"))
        assert "governance" in result
        assert result["governance"]["planner_version"] == "0.36"

    def test_existing_fields_unchanged(self, tmp_path):
        """Adding governance must not remove selected_offset, attempts, or result."""
        args = _make_args(tmp_path)
        result = run_governed_loop(args, planner_main=_noop_planner,
                                   preflight_fn=_preflight_always("low_risk"))
        for key in ("selected_offset", "attempts", "result"):
            assert key in result


# ---------------------------------------------------------------------------
# 9. Mapping override threading
# ---------------------------------------------------------------------------

class TestMappingOverride:
    def test_cli_accepts_mapping_override_flag(self, tmp_path):
        """main() must parse --mapping-override without error."""
        override_file = tmp_path / "override.json"
        override_file.write_text("{}", encoding="utf-8")
        output = tmp_path / "governed_result.json"
        # If the flag is unrecognised, parse_args raises SystemExit(2).
        # We stop before run_governed_loop does real work by injecting stubs.
        captured_args = []

        def capturing_loop(args, **kwargs):
            captured_args.append(args)
            return {"selected_offset": 0, "attempts": [], "result": {}}

        original = _mod.run_governed_loop
        _mod.run_governed_loop = capturing_loop
        try:
            _mod.main([
                "--mapping-override", str(override_file),
                "--output", str(output),
            ])
        finally:
            _mod.run_governed_loop = original

        assert len(captured_args) == 1
        # After the bug fix, mapping_override is the loaded dict, not the path string.
        assert isinstance(captured_args[0].mapping_override, dict)

    def test_governed_loop_passes_mapping_override_to_preflight(self, tmp_path):
        """mapping_override on args is forwarded to each preflight call."""
        sentinel = {"action_a": "task_x"}
        args = _make_args(tmp_path, mapping_override=sentinel)

        seen_overrides = []

        def recording_preflight(a):
            seen_overrides.append(getattr(a, "mapping_override", "MISSING"))
            return {"risk_level": "low_risk", "collision_ratio": 0.0, "unique_tasks": 2}

        run_governed_loop(args, planner_main=_noop_planner,
                          preflight_fn=recording_preflight)

        assert len(seen_overrides) == 1
        assert seen_overrides[0] == sentinel

    def test_no_mapping_override_is_none_by_default(self, tmp_path):
        """When mapping_override is absent, preflight receives None."""
        args = _make_args(tmp_path)  # mapping_override defaults to None

        seen_overrides = []

        def recording_preflight(a):
            seen_overrides.append(getattr(a, "mapping_override", "MISSING"))
            return {"risk_level": "low_risk", "collision_ratio": 0.0, "unique_tasks": 2}

        run_governed_loop(args, planner_main=_noop_planner,
                          preflight_fn=recording_preflight)

        assert seen_overrides[0] is None


# ---------------------------------------------------------------------------
# 10. CLI loads mapping override JSON file into dict (bug-fix regression)
# ---------------------------------------------------------------------------

class TestMappingOverrideJsonLoading:
    def test_cli_loads_mapping_override_file_as_dict(self, tmp_path):
        """main() must load the JSON file so mapping_override is a dict, not a path string."""
        override_data = {"action_a": "task_x", "action_b": "task_y"}
        override_file = tmp_path / "override.json"
        override_file.write_text(
            json.dumps(override_data, indent=2) + "\n", encoding="utf-8"
        )
        output = tmp_path / "governed_result.json"

        captured_args = []

        def capturing_loop(args, **kwargs):
            captured_args.append(args)
            return {"selected_offset": 0, "attempts": [], "result": {}}

        original = _mod.run_governed_loop
        _mod.run_governed_loop = capturing_loop
        try:
            _mod.main([
                "--mapping-override", str(override_file),
                "--output", str(output),
            ])
        finally:
            _mod.run_governed_loop = original

        assert isinstance(captured_args[0].mapping_override, dict)
        assert captured_args[0].mapping_override == override_data

    def test_cli_loaded_dict_passed_to_preflight(self, tmp_path):
        """Preflight receives dict-form mapping_override when CLI flag is used."""
        override_data = {"regenerate_missing_artifact": "build_portfolio_dashboard"}
        override_file = tmp_path / "override.json"
        override_file.write_text(json.dumps(override_data) + "\n", encoding="utf-8")
        output = tmp_path / "governed_result.json"

        seen_overrides = []

        def recording_preflight(a):
            seen_overrides.append(getattr(a, "mapping_override", "MISSING"))
            return {"risk_level": "low_risk", "collision_ratio": 0.0, "unique_tasks": 2}

        original_loop = _mod.run_governed_loop

        def patched_loop(args, **kwargs):
            return original_loop(args, planner_main=_noop_planner,
                                 preflight_fn=recording_preflight)

        original_main_loop = _mod.run_governed_loop
        _mod.run_governed_loop = patched_loop
        try:
            _mod.main([
                "--mapping-override", str(override_file),
                "--output", str(output),
            ])
        finally:
            _mod.run_governed_loop = original_main_loop

        assert len(seen_overrides) == 1
        assert isinstance(seen_overrides[0], dict)
        assert seen_overrides[0] == override_data

    def test_absent_mapping_override_remains_none_through_cli(self, tmp_path):
        """When --mapping-override is not given, mapping_override stays None."""
        output = tmp_path / "governed_result.json"

        captured_args = []

        def capturing_loop(args, **kwargs):
            captured_args.append(args)
            return {"selected_offset": 0, "attempts": [], "result": {}}

        original = _mod.run_governed_loop
        _mod.run_governed_loop = capturing_loop
        try:
            _mod.main(["--output", str(output)])
        finally:
            _mod.run_governed_loop = original

        assert captured_args[0].mapping_override is None


# ---------------------------------------------------------------------------
# 12. Abort artifact written on persistent high_risk
# ---------------------------------------------------------------------------

def _collision_preflight_with_window():
    """Persistent collision-based high_risk preflight that includes window/mapping data."""
    def _fn(args):
        return {
            "risk_level": "high_risk",
            "collision_ratio": 0.67,
            "unique_tasks": 1,
            "reasons": ["collision_ratio is 0.670000 (>=0.5): ..."],
            "recommendations": [],
            # ranked_action_window / mapped_tasks used by _build_abort_artifact
            "ranked_action_window": [
                "refresh_repo_health",
                "regenerate_missing_artifact",
                "rerun_failed_task",
            ],
            "mapped_tasks": [
                "build_portfolio_dashboard",
                "build_portfolio_dashboard",
                "build_portfolio_dashboard",
            ],
        }
    return _fn


def _unrepairable_preflight():
    """Persistent high_risk preflight with no window data (unrepairable)."""
    def _fn(args):
        return {
            "risk_level": "high_risk",
            "collision_ratio": 0.67,
            "unique_tasks": 1,
            "reasons": ["collision_ratio is 0.670000 (>=0.5): ..."],
            "recommendations": [],
            "ranked_action_window": [],
            "mapped_tasks": [],
        }
    return _fn


class TestAbortArtifact:
    def test_persistent_high_risk_writes_artifact(self, tmp_path):
        """Abort path must write the artifact file before raising SystemExit."""
        output = tmp_path / "governed_result.json"
        args = _make_args(tmp_path, force=False, output=str(output))
        with pytest.raises(SystemExit):
            run_governed_loop(args, planner_main=_noop_planner,
                              preflight_fn=_collision_preflight_with_window())
        assert output.exists()

    def test_abort_artifact_contains_abort_reason(self, tmp_path):
        """abort_reason must be 'high_risk_persistent' in the written artifact."""
        output = tmp_path / "governed_result.json"
        args = _make_args(tmp_path, force=False, output=str(output))
        with pytest.raises(SystemExit):
            run_governed_loop(args, planner_main=_noop_planner,
                              preflight_fn=_collision_preflight_with_window())
        data = json.loads(output.read_text(encoding="utf-8"))
        assert data["abort_reason"] == "high_risk_persistent"

    def test_repairable_abort_includes_non_empty_repair_proposal(self, tmp_path):
        """When the window has collisions, repair_proposal must be non-empty."""
        output = tmp_path / "governed_result.json"
        args = _make_args(tmp_path, force=False, output=str(output))
        with pytest.raises(SystemExit):
            run_governed_loop(args, planner_main=_noop_planner,
                              preflight_fn=_collision_preflight_with_window())
        data = json.loads(output.read_text(encoding="utf-8"))
        assert data["repair_proposal"] is not None
        assert data["repair_proposal"]["proposed_mapping_override"] != {}

    def test_unrepairable_abort_has_null_repair_proposal(self, tmp_path):
        """When the window is empty, repair_proposal must be None/null."""
        output = tmp_path / "governed_result.json"
        args = _make_args(tmp_path, force=False, output=str(output))
        with pytest.raises(SystemExit):
            run_governed_loop(args, planner_main=_noop_planner,
                              preflight_fn=_unrepairable_preflight())
        data = json.loads(output.read_text(encoding="utf-8"))
        assert data["repair_proposal"] is None

    def test_abort_artifact_contains_attempts(self, tmp_path):
        """Abort artifact must record the attempts list."""
        output = tmp_path / "governed_result.json"
        args = _make_args(tmp_path, force=False, output=str(output))
        with pytest.raises(SystemExit):
            run_governed_loop(args, planner_main=_noop_planner,
                              preflight_fn=_collision_preflight_with_window())
        data = json.loads(output.read_text(encoding="utf-8"))
        assert isinstance(data["attempts"], list)
        assert len(data["attempts"]) > 0

    def test_abort_artifact_contains_governance(self, tmp_path):
        """Abort artifact must include the governance block."""
        output = tmp_path / "governed_result.json"
        args = _make_args(tmp_path, force=False, output=str(output))
        with pytest.raises(SystemExit):
            run_governed_loop(args, planner_main=_noop_planner,
                              preflight_fn=_collision_preflight_with_window())
        data = json.loads(output.read_text(encoding="utf-8"))
        assert "governance" in data

    def test_successful_run_artifact_unchanged(self, tmp_path):
        """Successful execution artifact must still contain selected_offset and result."""
        args = _make_args(tmp_path, force=False)
        result = run_governed_loop(args, planner_main=_noop_planner,
                                   preflight_fn=_preflight_always("low_risk"))
        for key in ("selected_offset", "attempts", "result", "governance"):
            assert key in result
        assert "abort_reason" not in result
