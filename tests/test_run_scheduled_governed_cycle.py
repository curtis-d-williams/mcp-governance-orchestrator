# SPDX-License-Identifier: MIT
"""Tests for scripts/run_scheduled_governed_cycle.py (Phase M).

Covers:
1.  Successful cycle with governance continue — summary/alert written, alert=false.
2.  Successful cycle with governance warn — alert=true, alert_level=warning.
3.  Successful cycle with governance abort — alert=true, alert_level=warning.
4.  Cycle status aborted — alert=true, alert_level=critical.
5.  Subprocess invocation wiring — manifest/task/top-k/force/governance-policy passthrough.
6.  Timestamp derivation logic.
7.  Deterministic output formatting.
8.  Invalid cycle artifact handling.
9.  Subprocess failure handling.
10. Parent directory creation for summary/alert outputs.
    Pure-function unit tests for helpers.
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Module loading
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_SCRIPT = _REPO_ROOT / "scripts" / "run_scheduled_governed_cycle.py"
_spec = importlib.util.spec_from_file_location("run_scheduled_governed_cycle", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

run_scheduled_cycle = _mod.run_scheduled_cycle
_build_summary = _mod._build_summary
_build_alert = _mod._build_alert
_classify_alert_level = _mod._classify_alert_level
_derive_timestamp = _mod._derive_timestamp
_get_planner_selected_tasks = _mod._get_planner_selected_tasks
_build_cycle_cmd = _mod._build_cycle_cmd


# ---------------------------------------------------------------------------
# Test fixtures and helpers
# ---------------------------------------------------------------------------

_CYCLE_OK = {
    "status": "ok",
    "governance_decision": {"decision": "continue"},
    "execution_result": {"selected_tasks": ["build_portfolio_dashboard"]},
    "cycle_history": {
        "cycles": [{"timestamp": "2026-01-01T00:00:00Z", "status": "ok"}],
    },
    "cycle_history_regression": {
        "current_cycle_timestamp": "2026-01-02T00:00:00Z",
        "regression_detected": False,
    },
}

_CYCLE_GOVERNANCE_WARN = {
    **_CYCLE_OK,
    "governance_decision": {"decision": "warn"},
}

_CYCLE_GOVERNANCE_ABORT = {
    **_CYCLE_OK,
    "governance_decision": {"decision": "abort"},
}

_CYCLE_ABORTED = {
    "status": "aborted",
    "phase": "governed_loop",
    "governance_decision": None,
    "execution_result": None,
    "cycle_history": None,
    "cycle_history_regression": None,
}


def _make_args(tmp_path, **kwargs):
    defaults = dict(
        manifest=str(tmp_path / "manifest.json"),
        output=str(tmp_path / "cycle.json"),
        task=["artifact_audit_example"],
        repo_ids=None,
        top_k=None,
        force=False,
        governance_policy=None,
        summary_output=str(tmp_path / "summary.json"),
        alert_output=str(tmp_path / "alert.json"),
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _ok_proc():
    proc = MagicMock()
    proc.returncode = 0
    return proc


def _write_cycle(path, data):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. Successful cycle with governance continue
# ---------------------------------------------------------------------------

class TestSuccessfulCycleGovernanceContinue:
    def test_returns_zero(self, tmp_path):
        args = _make_args(tmp_path)
        _write_cycle(args.output, _CYCLE_OK)
        with patch("subprocess.run", return_value=_ok_proc()):
            rc = run_scheduled_cycle(args)
        assert rc == 0

    def test_summary_written(self, tmp_path):
        args = _make_args(tmp_path)
        _write_cycle(args.output, _CYCLE_OK)
        with patch("subprocess.run", return_value=_ok_proc()):
            run_scheduled_cycle(args)
        assert Path(args.summary_output).exists()

    def test_alert_written(self, tmp_path):
        args = _make_args(tmp_path)
        _write_cycle(args.output, _CYCLE_OK)
        with patch("subprocess.run", return_value=_ok_proc()):
            run_scheduled_cycle(args)
        assert Path(args.alert_output).exists()

    def test_alert_false(self, tmp_path):
        args = _make_args(tmp_path)
        _write_cycle(args.output, _CYCLE_OK)
        with patch("subprocess.run", return_value=_ok_proc()):
            run_scheduled_cycle(args)
        alert = json.loads(Path(args.alert_output).read_text())
        assert alert["alert"] is False

    def test_alert_level_none(self, tmp_path):
        args = _make_args(tmp_path)
        _write_cycle(args.output, _CYCLE_OK)
        with patch("subprocess.run", return_value=_ok_proc()):
            run_scheduled_cycle(args)
        alert = json.loads(Path(args.alert_output).read_text())
        assert alert["alert_level"] == "none"

    def test_reasons_empty(self, tmp_path):
        args = _make_args(tmp_path)
        _write_cycle(args.output, _CYCLE_OK)
        with patch("subprocess.run", return_value=_ok_proc()):
            run_scheduled_cycle(args)
        alert = json.loads(Path(args.alert_output).read_text())
        assert alert["reasons"] == []

    def test_summary_status_ok(self, tmp_path):
        args = _make_args(tmp_path)
        _write_cycle(args.output, _CYCLE_OK)
        with patch("subprocess.run", return_value=_ok_proc()):
            run_scheduled_cycle(args)
        summary = json.loads(Path(args.summary_output).read_text())
        assert summary["status"] == "ok"

    def test_summary_governance_decision_continue(self, tmp_path):
        args = _make_args(tmp_path)
        _write_cycle(args.output, _CYCLE_OK)
        with patch("subprocess.run", return_value=_ok_proc()):
            run_scheduled_cycle(args)
        summary = json.loads(Path(args.summary_output).read_text())
        assert summary["governance_decision"] == "continue"

    def test_summary_planner_selected_tasks(self, tmp_path):
        args = _make_args(tmp_path)
        _write_cycle(args.output, _CYCLE_OK)
        with patch("subprocess.run", return_value=_ok_proc()):
            run_scheduled_cycle(args)
        summary = json.loads(Path(args.summary_output).read_text())
        assert summary["planner_selected_tasks"] == ["build_portfolio_dashboard"]

    def test_summary_cycle_output_path(self, tmp_path):
        args = _make_args(tmp_path)
        _write_cycle(args.output, _CYCLE_OK)
        with patch("subprocess.run", return_value=_ok_proc()):
            run_scheduled_cycle(args)
        summary = json.loads(Path(args.summary_output).read_text())
        assert summary["cycle_output"] == str(Path(args.output))


# ---------------------------------------------------------------------------
# 2. Successful cycle with governance warn
# ---------------------------------------------------------------------------

class TestSuccessfulCycleGovernanceWarn:
    def test_returns_zero(self, tmp_path):
        args = _make_args(tmp_path)
        _write_cycle(args.output, _CYCLE_GOVERNANCE_WARN)
        with patch("subprocess.run", return_value=_ok_proc()):
            rc = run_scheduled_cycle(args)
        assert rc == 0

    def test_alert_true(self, tmp_path):
        args = _make_args(tmp_path)
        _write_cycle(args.output, _CYCLE_GOVERNANCE_WARN)
        with patch("subprocess.run", return_value=_ok_proc()):
            run_scheduled_cycle(args)
        alert = json.loads(Path(args.alert_output).read_text())
        assert alert["alert"] is True

    def test_alert_level_warning(self, tmp_path):
        args = _make_args(tmp_path)
        _write_cycle(args.output, _CYCLE_GOVERNANCE_WARN)
        with patch("subprocess.run", return_value=_ok_proc()):
            run_scheduled_cycle(args)
        alert = json.loads(Path(args.alert_output).read_text())
        assert alert["alert_level"] == "warning"

    def test_reasons_include_governance_warn(self, tmp_path):
        args = _make_args(tmp_path)
        _write_cycle(args.output, _CYCLE_GOVERNANCE_WARN)
        with patch("subprocess.run", return_value=_ok_proc()):
            run_scheduled_cycle(args)
        alert = json.loads(Path(args.alert_output).read_text())
        assert "governance_decision_warn" in alert["reasons"]

    def test_summary_alert_level_warning(self, tmp_path):
        args = _make_args(tmp_path)
        _write_cycle(args.output, _CYCLE_GOVERNANCE_WARN)
        with patch("subprocess.run", return_value=_ok_proc()):
            run_scheduled_cycle(args)
        summary = json.loads(Path(args.summary_output).read_text())
        assert summary["alert_level"] == "warning"


# ---------------------------------------------------------------------------
# 3. Successful cycle with governance abort
# ---------------------------------------------------------------------------

class TestSuccessfulCycleGovernanceAbort:
    def test_returns_zero(self, tmp_path):
        args = _make_args(tmp_path)
        _write_cycle(args.output, _CYCLE_GOVERNANCE_ABORT)
        with patch("subprocess.run", return_value=_ok_proc()):
            rc = run_scheduled_cycle(args)
        assert rc == 0

    def test_alert_true(self, tmp_path):
        args = _make_args(tmp_path)
        _write_cycle(args.output, _CYCLE_GOVERNANCE_ABORT)
        with patch("subprocess.run", return_value=_ok_proc()):
            run_scheduled_cycle(args)
        alert = json.loads(Path(args.alert_output).read_text())
        assert alert["alert"] is True

    def test_alert_level_warning(self, tmp_path):
        args = _make_args(tmp_path)
        _write_cycle(args.output, _CYCLE_GOVERNANCE_ABORT)
        with patch("subprocess.run", return_value=_ok_proc()):
            run_scheduled_cycle(args)
        alert = json.loads(Path(args.alert_output).read_text())
        assert alert["alert_level"] == "warning"

    def test_reasons_include_governance_abort(self, tmp_path):
        args = _make_args(tmp_path)
        _write_cycle(args.output, _CYCLE_GOVERNANCE_ABORT)
        with patch("subprocess.run", return_value=_ok_proc()):
            run_scheduled_cycle(args)
        alert = json.loads(Path(args.alert_output).read_text())
        assert "governance_decision_abort" in alert["reasons"]

    def test_summary_governance_decision_abort(self, tmp_path):
        args = _make_args(tmp_path)
        _write_cycle(args.output, _CYCLE_GOVERNANCE_ABORT)
        with patch("subprocess.run", return_value=_ok_proc()):
            run_scheduled_cycle(args)
        summary = json.loads(Path(args.summary_output).read_text())
        assert summary["governance_decision"] == "abort"


# ---------------------------------------------------------------------------
# 4. Cycle status aborted
# ---------------------------------------------------------------------------

class TestCycleStatusAborted:
    """Tests alert classification when cycle artifact shows status=aborted.

    The subprocess mock returns rc=0 to isolate alert classification logic
    from subprocess failure handling.
    """

    def test_returns_zero(self, tmp_path):
        args = _make_args(tmp_path)
        _write_cycle(args.output, _CYCLE_ABORTED)
        with patch("subprocess.run", return_value=_ok_proc()):
            rc = run_scheduled_cycle(args)
        assert rc == 0

    def test_alert_true(self, tmp_path):
        args = _make_args(tmp_path)
        _write_cycle(args.output, _CYCLE_ABORTED)
        with patch("subprocess.run", return_value=_ok_proc()):
            run_scheduled_cycle(args)
        alert = json.loads(Path(args.alert_output).read_text())
        assert alert["alert"] is True

    def test_alert_level_critical(self, tmp_path):
        args = _make_args(tmp_path)
        _write_cycle(args.output, _CYCLE_ABORTED)
        with patch("subprocess.run", return_value=_ok_proc()):
            run_scheduled_cycle(args)
        alert = json.loads(Path(args.alert_output).read_text())
        assert alert["alert_level"] == "critical"

    def test_reasons_include_cycle_status_aborted(self, tmp_path):
        args = _make_args(tmp_path)
        _write_cycle(args.output, _CYCLE_ABORTED)
        with patch("subprocess.run", return_value=_ok_proc()):
            run_scheduled_cycle(args)
        alert = json.loads(Path(args.alert_output).read_text())
        assert "cycle_status_aborted" in alert["reasons"]

    def test_summary_status_aborted(self, tmp_path):
        args = _make_args(tmp_path)
        _write_cycle(args.output, _CYCLE_ABORTED)
        with patch("subprocess.run", return_value=_ok_proc()):
            run_scheduled_cycle(args)
        summary = json.loads(Path(args.summary_output).read_text())
        assert summary["status"] == "aborted"

    def test_summary_alert_level_critical(self, tmp_path):
        args = _make_args(tmp_path)
        _write_cycle(args.output, _CYCLE_ABORTED)
        with patch("subprocess.run", return_value=_ok_proc()):
            run_scheduled_cycle(args)
        summary = json.loads(Path(args.summary_output).read_text())
        assert summary["alert_level"] == "critical"


# ---------------------------------------------------------------------------
# 5. Subprocess invocation wiring
# ---------------------------------------------------------------------------

class TestSubprocessWiring:
    """Verify that CLI arguments are correctly forwarded to the governed cycle."""

    def _capture_cmd(self, args, cycle_data=None):
        _write_cycle(args.output, cycle_data or _CYCLE_OK)
        calls = []

        def _side(cmd, **kwargs):
            calls.append(list(cmd))
            return _ok_proc()

        with patch("subprocess.run", side_effect=_side):
            run_scheduled_cycle(args)
        return calls[0]

    def test_manifest_passthrough(self, tmp_path):
        args = _make_args(tmp_path, manifest="/some/manifest.json")
        cmd = self._capture_cmd(args)
        assert "--manifest" in cmd
        idx = cmd.index("--manifest")
        assert cmd[idx + 1] == "/some/manifest.json"

    def test_output_passthrough(self, tmp_path):
        args = _make_args(tmp_path)
        cmd = self._capture_cmd(args)
        assert "--output" in cmd
        idx = cmd.index("--output")
        assert cmd[idx + 1] == args.output

    def test_task_passthrough_single(self, tmp_path):
        args = _make_args(tmp_path, task=["my_task"])
        cmd = self._capture_cmd(args)
        task_args = [cmd[i + 1] for i, v in enumerate(cmd) if v == "--task"]
        assert task_args == ["my_task"]

    def test_task_passthrough_repeated(self, tmp_path):
        args = _make_args(tmp_path, task=["task_a", "task_b"])
        cmd = self._capture_cmd(args)
        task_args = [cmd[i + 1] for i, v in enumerate(cmd) if v == "--task"]
        assert "task_a" in task_args
        assert "task_b" in task_args
        assert len(task_args) == 2

    def test_top_k_passthrough(self, tmp_path):
        args = _make_args(tmp_path, top_k=5)
        cmd = self._capture_cmd(args)
        assert "--top-k" in cmd
        idx = cmd.index("--top-k")
        assert cmd[idx + 1] == "5"

    def test_top_k_omitted_when_none(self, tmp_path):
        args = _make_args(tmp_path, top_k=None)
        cmd = self._capture_cmd(args)
        assert "--top-k" not in cmd

    def test_force_passthrough(self, tmp_path):
        args = _make_args(tmp_path, force=True)
        cmd = self._capture_cmd(args)
        assert "--force" in cmd

    def test_force_omitted_when_false(self, tmp_path):
        args = _make_args(tmp_path, force=False)
        cmd = self._capture_cmd(args)
        assert "--force" not in cmd

    def test_governance_policy_passthrough(self, tmp_path):
        args = _make_args(tmp_path, governance_policy="/some/policy.json")
        cmd = self._capture_cmd(args)
        assert "--governance-policy" in cmd
        idx = cmd.index("--governance-policy")
        assert cmd[idx + 1] == "/some/policy.json"

    def test_governance_policy_omitted_when_none(self, tmp_path):
        args = _make_args(tmp_path, governance_policy=None)
        cmd = self._capture_cmd(args)
        assert "--governance-policy" not in cmd

    def test_invokes_governed_cycle_script(self, tmp_path):
        args = _make_args(tmp_path)
        cmd = self._capture_cmd(args)
        assert any("run_governed_portfolio_cycle" in part for part in cmd)


# ---------------------------------------------------------------------------
# 6. Timestamp derivation logic
# ---------------------------------------------------------------------------

class TestTimestampDerivation:
    def test_prefers_regression_timestamp(self):
        cycle = {
            "cycle_history_regression": {"current_cycle_timestamp": "2026-02-01T00:00:00Z"},
            "cycle_history": {"cycles": [{"timestamp": "2026-01-01T00:00:00Z"}]},
        }
        assert _derive_timestamp(cycle) == "2026-02-01T00:00:00Z"

    def test_falls_back_to_last_cycle_history_entry(self):
        cycle = {
            "cycle_history_regression": {"regression_detected": False},
            "cycle_history": {
                "cycles": [
                    {"timestamp": "2026-01-01T00:00:00Z"},
                    {"timestamp": "2026-01-15T00:00:00Z"},
                ],
            },
        }
        assert _derive_timestamp(cycle) == "2026-01-15T00:00:00Z"

    def test_returns_none_when_both_missing(self):
        cycle = {"cycle_history_regression": None, "cycle_history": None}
        assert _derive_timestamp(cycle) is None

    def test_returns_none_when_cycles_empty(self):
        cycle = {
            "cycle_history_regression": {},
            "cycle_history": {"cycles": []},
        }
        assert _derive_timestamp(cycle) is None

    def test_returns_none_when_regression_ts_missing(self):
        cycle = {
            "cycle_history_regression": {"regression_detected": False},
            "cycle_history": None,
        }
        assert _derive_timestamp(cycle) is None

    def test_timestamp_in_summary(self, tmp_path):
        args = _make_args(tmp_path)
        _write_cycle(args.output, _CYCLE_OK)
        with patch("subprocess.run", return_value=_ok_proc()):
            run_scheduled_cycle(args)
        summary = json.loads(Path(args.summary_output).read_text())
        assert summary["timestamp"] == "2026-01-02T00:00:00Z"


# ---------------------------------------------------------------------------
# 7. Deterministic output formatting
# ---------------------------------------------------------------------------

class TestDeterministicOutput:
    def test_summary_is_valid_json(self, tmp_path):
        args = _make_args(tmp_path)
        _write_cycle(args.output, _CYCLE_OK)
        with patch("subprocess.run", return_value=_ok_proc()):
            run_scheduled_cycle(args)
        data = json.loads(Path(args.summary_output).read_text())
        assert isinstance(data, dict)

    def test_alert_is_valid_json(self, tmp_path):
        args = _make_args(tmp_path)
        _write_cycle(args.output, _CYCLE_OK)
        with patch("subprocess.run", return_value=_ok_proc()):
            run_scheduled_cycle(args)
        data = json.loads(Path(args.alert_output).read_text())
        assert isinstance(data, dict)

    def test_summary_has_trailing_newline(self, tmp_path):
        args = _make_args(tmp_path)
        _write_cycle(args.output, _CYCLE_OK)
        with patch("subprocess.run", return_value=_ok_proc()):
            run_scheduled_cycle(args)
        text = Path(args.summary_output).read_text(encoding="utf-8")
        assert text.endswith("\n")

    def test_alert_has_trailing_newline(self, tmp_path):
        args = _make_args(tmp_path)
        _write_cycle(args.output, _CYCLE_OK)
        with patch("subprocess.run", return_value=_ok_proc()):
            run_scheduled_cycle(args)
        text = Path(args.alert_output).read_text(encoding="utf-8")
        assert text.endswith("\n")

    def test_summary_keys_sorted(self, tmp_path):
        args = _make_args(tmp_path)
        _write_cycle(args.output, _CYCLE_OK)
        with patch("subprocess.run", return_value=_ok_proc()):
            run_scheduled_cycle(args)
        text = Path(args.summary_output).read_text(encoding="utf-8")
        data = json.loads(text)
        assert list(data.keys()) == sorted(data.keys())

    def test_alert_keys_sorted(self, tmp_path):
        args = _make_args(tmp_path)
        _write_cycle(args.output, _CYCLE_OK)
        with patch("subprocess.run", return_value=_ok_proc()):
            run_scheduled_cycle(args)
        text = Path(args.alert_output).read_text(encoding="utf-8")
        data = json.loads(text)
        assert list(data.keys()) == sorted(data.keys())

    def test_summary_planner_tasks_sorted(self, tmp_path):
        cycle = {
            **_CYCLE_OK,
            "execution_result": {"selected_tasks": ["z_task", "a_task", "m_task"]},
        }
        args = _make_args(tmp_path)
        _write_cycle(args.output, cycle)
        with patch("subprocess.run", return_value=_ok_proc()):
            run_scheduled_cycle(args)
        summary = json.loads(Path(args.summary_output).read_text())
        tasks = summary["planner_selected_tasks"]
        assert tasks == sorted(tasks)

    def test_summary_required_fields_present(self, tmp_path):
        args = _make_args(tmp_path)
        _write_cycle(args.output, _CYCLE_OK)
        with patch("subprocess.run", return_value=_ok_proc()):
            run_scheduled_cycle(args)
        summary = json.loads(Path(args.summary_output).read_text())
        for field in ("alert_level", "cycle_history_length", "cycle_output",
                      "governance_decision", "planner_selected_tasks",
                      "regression_detected", "status", "timestamp"):
            assert field in summary, f"missing field: {field}"

    def test_alert_required_fields_present(self, tmp_path):
        args = _make_args(tmp_path)
        _write_cycle(args.output, _CYCLE_OK)
        with patch("subprocess.run", return_value=_ok_proc()):
            run_scheduled_cycle(args)
        alert = json.loads(Path(args.alert_output).read_text())
        for field in ("alert", "alert_level", "reasons"):
            assert field in alert, f"missing field: {field}"


# ---------------------------------------------------------------------------
# 8. Invalid cycle artifact handling
# ---------------------------------------------------------------------------

class TestInvalidCycleArtifact:
    def test_returns_one_on_missing_artifact(self, tmp_path):
        args = _make_args(tmp_path)
        # Do NOT write cycle artifact.
        with patch("subprocess.run", return_value=_ok_proc()):
            rc = run_scheduled_cycle(args)
        assert rc == 1

    def test_returns_one_on_invalid_json(self, tmp_path):
        args = _make_args(tmp_path)
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text("not-valid-json", encoding="utf-8")
        with patch("subprocess.run", return_value=_ok_proc()):
            rc = run_scheduled_cycle(args)
        assert rc == 1

    def test_alert_written_on_unreadable_artifact(self, tmp_path):
        args = _make_args(tmp_path)
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text("bad", encoding="utf-8")
        with patch("subprocess.run", return_value=_ok_proc()):
            run_scheduled_cycle(args)
        assert Path(args.alert_output).exists()

    def test_alert_critical_on_unreadable_artifact(self, tmp_path):
        args = _make_args(tmp_path)
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text("bad", encoding="utf-8")
        with patch("subprocess.run", return_value=_ok_proc()):
            run_scheduled_cycle(args)
        alert = json.loads(Path(args.alert_output).read_text())
        assert alert["alert"] is True
        assert alert["alert_level"] == "critical"

    def test_alert_reason_on_unreadable_artifact(self, tmp_path):
        args = _make_args(tmp_path)
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text("bad", encoding="utf-8")
        with patch("subprocess.run", return_value=_ok_proc()):
            run_scheduled_cycle(args)
        alert = json.loads(Path(args.alert_output).read_text())
        assert "wrapper_artifact_unreadable" in alert["reasons"]


# ---------------------------------------------------------------------------
# 9. Subprocess failure handling
# ---------------------------------------------------------------------------

class TestSubprocessFailure:
    def test_returns_one_on_called_process_error(self, tmp_path):
        args = _make_args(tmp_path)
        with patch("subprocess.run",
                   side_effect=subprocess.CalledProcessError(1, [])):
            rc = run_scheduled_cycle(args)
        assert rc == 1

    def test_alert_written_on_subprocess_failure(self, tmp_path):
        args = _make_args(tmp_path)
        with patch("subprocess.run",
                   side_effect=subprocess.CalledProcessError(1, [])):
            run_scheduled_cycle(args)
        assert Path(args.alert_output).exists()

    def test_alert_critical_on_subprocess_failure(self, tmp_path):
        args = _make_args(tmp_path)
        with patch("subprocess.run",
                   side_effect=subprocess.CalledProcessError(1, [])):
            run_scheduled_cycle(args)
        alert = json.loads(Path(args.alert_output).read_text())
        assert alert["alert"] is True
        assert alert["alert_level"] == "critical"

    def test_alert_reason_wrapper_subprocess_failed(self, tmp_path):
        args = _make_args(tmp_path)
        with patch("subprocess.run",
                   side_effect=subprocess.CalledProcessError(1, [])):
            run_scheduled_cycle(args)
        alert = json.loads(Path(args.alert_output).read_text())
        assert "wrapper_subprocess_failed" in alert["reasons"]

    def test_returns_one_on_file_not_found(self, tmp_path):
        args = _make_args(tmp_path)
        with patch("subprocess.run",
                   side_effect=FileNotFoundError("no python")):
            rc = run_scheduled_cycle(args)
        assert rc == 1

    def test_alert_written_on_file_not_found(self, tmp_path):
        args = _make_args(tmp_path)
        with patch("subprocess.run",
                   side_effect=FileNotFoundError("no python")):
            run_scheduled_cycle(args)
        alert = json.loads(Path(args.alert_output).read_text())
        assert "wrapper_subprocess_failed" in alert["reasons"]


# ---------------------------------------------------------------------------
# 10. Parent directory creation
# ---------------------------------------------------------------------------

class TestParentDirectoryCreation:
    def test_creates_parent_dirs_for_summary(self, tmp_path):
        nested = tmp_path / "a" / "b" / "summary.json"
        args = _make_args(tmp_path, summary_output=str(nested))
        _write_cycle(args.output, _CYCLE_OK)
        with patch("subprocess.run", return_value=_ok_proc()):
            run_scheduled_cycle(args)
        assert nested.exists()

    def test_creates_parent_dirs_for_alert(self, tmp_path):
        nested = tmp_path / "x" / "y" / "alert.json"
        args = _make_args(tmp_path, alert_output=str(nested))
        _write_cycle(args.output, _CYCLE_OK)
        with patch("subprocess.run", return_value=_ok_proc()):
            run_scheduled_cycle(args)
        assert nested.exists()

    def test_creates_parent_dirs_for_alert_on_failure(self, tmp_path):
        nested = tmp_path / "fail" / "alert.json"
        args = _make_args(tmp_path, alert_output=str(nested))
        with patch("subprocess.run",
                   side_effect=subprocess.CalledProcessError(1, [])):
            run_scheduled_cycle(args)
        assert nested.exists()


# ---------------------------------------------------------------------------
# Pure-function unit tests
# ---------------------------------------------------------------------------

class TestClassifyAlertLevel:
    def test_ok_continue_is_none(self):
        assert _classify_alert_level("ok", "continue") == "none"

    def test_ok_warn_is_warning(self):
        assert _classify_alert_level("ok", "warn") == "warning"

    def test_ok_abort_is_warning(self):
        assert _classify_alert_level("ok", "abort") == "warning"

    def test_aborted_cycle_is_critical(self):
        assert _classify_alert_level("aborted", "continue") == "critical"

    def test_aborted_with_governance_abort_is_critical(self):
        # cycle failure is more severe; critical wins
        assert _classify_alert_level("aborted", "abort") == "critical"

    def test_unknown_status_is_critical(self):
        assert _classify_alert_level("unknown", "continue") == "critical"

    def test_ok_unknown_governance_is_none(self):
        # only known governance values trigger warning
        assert _classify_alert_level("ok", "unknown") == "none"


class TestBuildAlert:
    def test_continue_no_alert(self):
        alert = _build_alert("ok", "continue")
        assert alert["alert"] is False
        assert alert["alert_level"] == "none"
        assert alert["reasons"] == []

    def test_warn_governance(self):
        alert = _build_alert("ok", "warn")
        assert alert["alert"] is True
        assert alert["alert_level"] == "warning"
        assert "governance_decision_warn" in alert["reasons"]
        assert "cycle_status_aborted" not in alert["reasons"]

    def test_abort_governance(self):
        alert = _build_alert("ok", "abort")
        assert alert["alert"] is True
        assert "governance_decision_abort" in alert["reasons"]
        assert "governance_decision_warn" not in alert["reasons"]

    def test_cycle_aborted(self):
        alert = _build_alert("aborted", "continue")
        assert alert["alert"] is True
        assert alert["alert_level"] == "critical"
        assert "cycle_status_aborted" in alert["reasons"]

    def test_cycle_aborted_with_governance_abort(self):
        alert = _build_alert("aborted", "abort")
        assert "cycle_status_aborted" in alert["reasons"]
        assert "governance_decision_abort" in alert["reasons"]
        assert alert["alert_level"] == "critical"


class TestGetPlannerSelectedTasks:
    def test_returns_sorted(self):
        cycle = {"execution_result": {"selected_tasks": ["z_task", "a_task"]}}
        assert _get_planner_selected_tasks(cycle) == ["a_task", "z_task"]

    def test_returns_empty_when_missing_execution_result(self):
        assert _get_planner_selected_tasks({}) == []

    def test_returns_empty_when_execution_result_none(self):
        assert _get_planner_selected_tasks({"execution_result": None}) == []

    def test_returns_empty_when_selected_tasks_none(self):
        cycle = {"execution_result": {"selected_tasks": None}}
        assert _get_planner_selected_tasks(cycle) == []

    def test_returns_empty_when_selected_tasks_not_list(self):
        cycle = {"execution_result": {"selected_tasks": "bad"}}
        assert _get_planner_selected_tasks(cycle) == []

    def test_single_task(self):
        cycle = {"execution_result": {"selected_tasks": ["only_task"]}}
        assert _get_planner_selected_tasks(cycle) == ["only_task"]


class TestBuildSummary:
    def test_regression_detected_field(self):
        cycle = {
            **_CYCLE_OK,
            "cycle_history_regression": {
                "current_cycle_timestamp": "2026-01-02T00:00:00Z",
                "regression_detected": True,
            },
        }
        summary = _build_summary(Path("/tmp/cycle.json"), cycle)
        assert summary["regression_detected"] is True

    def test_cycle_history_length(self):
        cycle = {
            **_CYCLE_OK,
            "cycle_history": {"cycles": [
                {"timestamp": "2026-01-01T00:00:00Z"},
                {"timestamp": "2026-01-02T00:00:00Z"},
            ]},
        }
        summary = _build_summary(Path("/tmp/cycle.json"), cycle)
        assert summary["cycle_history_length"] == 2

    def test_cycle_history_length_zero_when_none(self):
        cycle = {**_CYCLE_ABORTED}
        summary = _build_summary(Path("/tmp/cycle.json"), cycle)
        assert summary["cycle_history_length"] == 0
