# SPDX-License-Identifier: MIT
"""Tests for scripts/execute_governed_actions.py.

Covers:
A. Task extraction — selected_actions, action_mapping_fallback, no-task abort.
B. Execution success — status ok, fields populated, parsed_output decoded.
C. Execution failure — non-zero returncode → status aborted.
D. Error cases — unreadable governed result, aborted deterministic JSON.
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Module loading
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_SCRIPT = _REPO_ROOT / "scripts" / "execute_governed_actions.py"
_spec = importlib.util.spec_from_file_location("execute_governed_actions", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

execute_governed_actions = _mod.execute_governed_actions
_extract_selected_tasks = _mod._extract_selected_tasks
_write_json = _mod._write_json


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _governed_result_with_selected(tasks):
    """Build a governed result dict with selected_actions populated."""
    return {
        "status": "ok",
        "result": {
            "evaluation_summary": {
                "runs": [{
                    "selected_actions": tasks,
                    "selection_detail": {
                        "ranked_action_window": ["refresh_repo_health"],
                    },
                }]
            }
        },
    }


def _governed_result_with_window(actions):
    """Build a governed result dict with only ranked_action_window (no selected_actions)."""
    return {
        "status": "ok",
        "result": {
            "evaluation_summary": {
                "runs": [{
                    "selection_detail": {
                        "ranked_action_window": actions,
                    },
                }]
            }
        },
    }


def _write_governed_result(tmp_path, data):
    p = tmp_path / "governed_result.json"
    p.write_text(json.dumps(data) + "\n", encoding="utf-8")
    return p


def _ok_proc(stdout="", returncode=0):
    proc = MagicMock()
    proc.returncode = returncode
    proc.stdout = stdout
    proc.stderr = ""
    return proc


# ---------------------------------------------------------------------------
# A. Task extraction unit tests
# ---------------------------------------------------------------------------

class TestExtractSelectedTasks:
    def test_extracts_from_selected_actions(self):
        gr = _governed_result_with_selected(["build_portfolio_dashboard"])
        tasks, via = _extract_selected_tasks(gr)
        assert tasks == ["build_portfolio_dashboard"]
        assert via == "selected_actions"

    def test_multiple_selected_actions_all_returned(self):
        gr = _governed_result_with_selected(["artifact_audit_example", "repo_insights_example"])
        tasks, via = _extract_selected_tasks(gr)
        assert tasks == ["artifact_audit_example", "repo_insights_example"]
        assert via == "selected_actions"

    def test_falls_back_to_window_when_selected_actions_empty(self):
        gr = _governed_result_with_selected([])  # empty selected_actions
        # override window to something resolvable
        gr["result"]["evaluation_summary"]["runs"][0]["selection_detail"]["ranked_action_window"] = [
            "refresh_repo_health"
        ]
        tasks, via = _extract_selected_tasks(gr)
        assert tasks == ["build_portfolio_dashboard"]
        assert via == "action_mapping_fallback"

    def test_falls_back_to_window_when_selected_actions_missing(self):
        gr = _governed_result_with_window(["rerun_failed_task"])
        tasks, via = _extract_selected_tasks(gr)
        assert tasks == ["build_portfolio_dashboard"]
        assert via == "action_mapping_fallback"

    def test_fallback_skips_unmapped_actions(self):
        gr = _governed_result_with_window(["unknown_action_xyz", "analyze_repo_insights"])
        tasks, via = _extract_selected_tasks(gr)
        # unknown_action_xyz is unmapped; analyze_repo_insights maps to repo_insights_example
        assert tasks == ["repo_insights_example"]
        assert via == "action_mapping_fallback"

    def test_returns_empty_when_nothing_resolves(self):
        gr = _governed_result_with_window(["unknown_action_xyz"])
        tasks, via = _extract_selected_tasks(gr)
        assert tasks == []
        assert via is None

    def test_returns_empty_on_missing_result_key(self):
        tasks, via = _extract_selected_tasks({})
        assert tasks == []
        assert via is None

    def test_returns_empty_on_empty_runs(self):
        gr = {"result": {"evaluation_summary": {"runs": []}}}
        tasks, via = _extract_selected_tasks(gr)
        assert tasks == []
        assert via is None


# ---------------------------------------------------------------------------
# B. Execution success
# ---------------------------------------------------------------------------

class TestExecutionSuccess:
    def test_returns_zero_on_success(self, tmp_path):
        gr = _governed_result_with_selected(["build_portfolio_dashboard"])
        gr_path = _write_governed_result(tmp_path, gr)
        output = tmp_path / "execution_result.json"
        manifest = tmp_path / "manifest.json"
        manifest.write_text("{}", encoding="utf-8")

        task_stdout = json.dumps({"task_name": "build_portfolio_dashboard"})
        with patch("subprocess.run", return_value=_ok_proc(stdout=task_stdout)) as mock_run:
            rc = execute_governed_actions(str(gr_path), str(manifest), str(output))

        assert rc == 0

    def test_output_file_written(self, tmp_path):
        gr = _governed_result_with_selected(["build_portfolio_dashboard"])
        gr_path = _write_governed_result(tmp_path, gr)
        output = tmp_path / "execution_result.json"
        manifest = tmp_path / "manifest.json"
        manifest.write_text("{}", encoding="utf-8")

        with patch("subprocess.run", return_value=_ok_proc()):
            execute_governed_actions(str(gr_path), str(manifest), str(output))

        assert output.exists()

    def test_status_ok_in_output(self, tmp_path):
        gr = _governed_result_with_selected(["artifact_audit_example"])
        gr_path = _write_governed_result(tmp_path, gr)
        output = tmp_path / "execution_result.json"
        manifest = tmp_path / "manifest.json"
        manifest.write_text("{}", encoding="utf-8")

        with patch("subprocess.run", return_value=_ok_proc()):
            execute_governed_actions(str(gr_path), str(manifest), str(output))

        data = json.loads(output.read_text())
        assert data["status"] == "ok"

    def test_selected_tasks_recorded(self, tmp_path):
        gr = _governed_result_with_selected(["artifact_audit_example"])
        gr_path = _write_governed_result(tmp_path, gr)
        output = tmp_path / "execution_result.json"
        manifest = tmp_path / "manifest.json"
        manifest.write_text("{}", encoding="utf-8")

        with patch("subprocess.run", return_value=_ok_proc()):
            execute_governed_actions(str(gr_path), str(manifest), str(output))

        data = json.loads(output.read_text())
        assert data["selected_tasks"] == ["artifact_audit_example"]

    def test_resolved_via_selected_actions(self, tmp_path):
        gr = _governed_result_with_selected(["artifact_audit_example"])
        gr_path = _write_governed_result(tmp_path, gr)
        output = tmp_path / "execution_result.json"
        manifest = tmp_path / "manifest.json"
        manifest.write_text("{}", encoding="utf-8")

        with patch("subprocess.run", return_value=_ok_proc()):
            execute_governed_actions(str(gr_path), str(manifest), str(output))

        data = json.loads(output.read_text())
        assert data["resolved_via"] == "selected_actions"

    def test_parsed_output_decoded_when_valid_json(self, tmp_path):
        gr = _governed_result_with_selected(["build_portfolio_dashboard"])
        gr_path = _write_governed_result(tmp_path, gr)
        output = tmp_path / "execution_result.json"
        manifest = tmp_path / "manifest.json"
        manifest.write_text("{}", encoding="utf-8")

        payload = {"task_name": "build_portfolio_dashboard", "ok": True}
        with patch("subprocess.run", return_value=_ok_proc(stdout=json.dumps(payload))):
            execute_governed_actions(str(gr_path), str(manifest), str(output))

        data = json.loads(output.read_text())
        assert data["parsed_output"] == payload

    def test_parsed_output_null_when_stdout_not_json(self, tmp_path):
        gr = _governed_result_with_selected(["build_portfolio_dashboard"])
        gr_path = _write_governed_result(tmp_path, gr)
        output = tmp_path / "execution_result.json"
        manifest = tmp_path / "manifest.json"
        manifest.write_text("{}", encoding="utf-8")

        with patch("subprocess.run", return_value=_ok_proc(stdout="not json")):
            execute_governed_actions(str(gr_path), str(manifest), str(output))

        data = json.loads(output.read_text())
        assert data["parsed_output"] is None

    def test_returncode_recorded(self, tmp_path):
        gr = _governed_result_with_selected(["artifact_audit_example"])
        gr_path = _write_governed_result(tmp_path, gr)
        output = tmp_path / "execution_result.json"
        manifest = tmp_path / "manifest.json"
        manifest.write_text("{}", encoding="utf-8")

        with patch("subprocess.run", return_value=_ok_proc(returncode=0)):
            execute_governed_actions(str(gr_path), str(manifest), str(output))

        data = json.loads(output.read_text())
        assert data["returncode"] == 0

    def test_subprocess_receives_task_and_manifest(self, tmp_path):
        gr = _governed_result_with_selected(["artifact_audit_example"])
        gr_path = _write_governed_result(tmp_path, gr)
        output = tmp_path / "execution_result.json"
        manifest = tmp_path / "manifest.json"
        manifest.write_text("{}", encoding="utf-8")

        with patch("subprocess.run", return_value=_ok_proc()) as mock_run:
            execute_governed_actions(str(gr_path), str(manifest), str(output))

        cmd = mock_run.call_args[0][0]
        assert "run_portfolio_task.py" in cmd[1]
        assert "artifact_audit_example" in cmd
        assert str(manifest) == cmd[-1]


# ---------------------------------------------------------------------------
# C. Execution failure
# ---------------------------------------------------------------------------

class TestExecutionFailure:
    def test_returns_one_on_task_failure(self, tmp_path):
        gr = _governed_result_with_selected(["artifact_audit_example"])
        gr_path = _write_governed_result(tmp_path, gr)
        output = tmp_path / "execution_result.json"
        manifest = tmp_path / "manifest.json"
        manifest.write_text("{}", encoding="utf-8")

        with patch("subprocess.run", return_value=_ok_proc(returncode=1)):
            rc = execute_governed_actions(str(gr_path), str(manifest), str(output))

        assert rc == 1

    def test_status_aborted_on_task_failure(self, tmp_path):
        gr = _governed_result_with_selected(["artifact_audit_example"])
        gr_path = _write_governed_result(tmp_path, gr)
        output = tmp_path / "execution_result.json"
        manifest = tmp_path / "manifest.json"
        manifest.write_text("{}", encoding="utf-8")

        with patch("subprocess.run", return_value=_ok_proc(returncode=1)):
            execute_governed_actions(str(gr_path), str(manifest), str(output))

        data = json.loads(output.read_text())
        assert data["status"] == "aborted"

    def test_output_still_written_on_failure(self, tmp_path):
        gr = _governed_result_with_selected(["artifact_audit_example"])
        gr_path = _write_governed_result(tmp_path, gr)
        output = tmp_path / "execution_result.json"
        manifest = tmp_path / "manifest.json"
        manifest.write_text("{}", encoding="utf-8")

        with patch("subprocess.run", return_value=_ok_proc(returncode=1)):
            execute_governed_actions(str(gr_path), str(manifest), str(output))

        assert output.exists()


# ---------------------------------------------------------------------------
# D. Error cases
# ---------------------------------------------------------------------------

class TestErrorCases:
    def test_aborts_when_governed_result_missing(self, tmp_path):
        output = tmp_path / "execution_result.json"
        manifest = tmp_path / "manifest.json"
        manifest.write_text("{}", encoding="utf-8")

        rc = execute_governed_actions(
            str(tmp_path / "nonexistent.json"),
            str(manifest),
            str(output),
        )
        assert rc == 1

    def test_abort_artifact_written_when_governed_result_missing(self, tmp_path):
        output = tmp_path / "execution_result.json"
        manifest = tmp_path / "manifest.json"
        manifest.write_text("{}", encoding="utf-8")

        execute_governed_actions(
            str(tmp_path / "nonexistent.json"),
            str(manifest),
            str(output),
        )
        data = json.loads(output.read_text())
        assert data["status"] == "aborted"
        assert data["reason"] == "governed_result_unreadable"

    def test_aborts_cleanly_when_no_tasks_resolvable(self, tmp_path):
        gr = _governed_result_with_window(["totally_unknown_action"])
        gr_path = _write_governed_result(tmp_path, gr)
        output = tmp_path / "execution_result.json"
        manifest = tmp_path / "manifest.json"
        manifest.write_text("{}", encoding="utf-8")

        with patch("subprocess.run") as mock_run:
            rc = execute_governed_actions(str(gr_path), str(manifest), str(output))

        assert rc == 1
        mock_run.assert_not_called()

    def test_abort_artifact_no_selected_tasks(self, tmp_path):
        gr = _governed_result_with_window(["totally_unknown_action"])
        gr_path = _write_governed_result(tmp_path, gr)
        output = tmp_path / "execution_result.json"
        manifest = tmp_path / "manifest.json"
        manifest.write_text("{}", encoding="utf-8")

        with patch("subprocess.run"):
            execute_governed_actions(str(gr_path), str(manifest), str(output))

        data = json.loads(output.read_text())
        assert data["status"] == "aborted"
        assert data["reason"] == "no_selected_tasks"

    def test_output_is_valid_json_in_all_cases(self, tmp_path):
        """Output file is always valid deterministic JSON."""
        gr = _governed_result_with_selected(["artifact_audit_example"])
        gr_path = _write_governed_result(tmp_path, gr)
        output = tmp_path / "execution_result.json"
        manifest = tmp_path / "manifest.json"
        manifest.write_text("{}", encoding="utf-8")

        with patch("subprocess.run", return_value=_ok_proc()):
            execute_governed_actions(str(gr_path), str(manifest), str(output))

        text = output.read_text(encoding="utf-8")
        assert text.endswith("\n")
        data = json.loads(text)
        assert isinstance(data, dict)

    def test_fallback_resolved_via_action_mapping_fallback(self, tmp_path):
        gr = _governed_result_with_window(["recover_failed_workflow"])
        gr_path = _write_governed_result(tmp_path, gr)
        output = tmp_path / "execution_result.json"
        manifest = tmp_path / "manifest.json"
        manifest.write_text("{}", encoding="utf-8")

        with patch("subprocess.run", return_value=_ok_proc()):
            execute_governed_actions(str(gr_path), str(manifest), str(output))

        data = json.loads(output.read_text())
        assert data["resolved_via"] == "action_mapping_fallback"
        assert data["selected_tasks"] == ["failure_recovery_example"]
