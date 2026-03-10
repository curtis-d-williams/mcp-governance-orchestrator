# SPDX-License-Identifier: MIT
"""Tests for scripts/run_governed_portfolio_cycle.py.

Covers:
A. Successful cycle — status ok, all artifact fields populated.
B. Governed loop abort — CalledProcessError from governed loop, status aborted.
C. CLI argument wiring — subprocess commands receive expected args.
D. Early phase failure — portfolio_state phase fails, artifact written with phase tag.
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest

# ---------------------------------------------------------------------------
# Module loading
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_SCRIPT = _REPO_ROOT / "scripts" / "run_governed_portfolio_cycle.py"
_spec = importlib.util.spec_from_file_location("run_governed_portfolio_cycle", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

run_cycle = _mod.run_cycle
_work_dir = _mod._work_dir
_artifact_paths = _mod._artifact_paths
_validate_manifest_repos = _mod._validate_manifest_repos


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MANIFEST_DATA = {"repos": [{"id": "repo-a", "path": "/tmp/repo-a"}]}

_PORTFOLIO_TASK_STDOUT = json.dumps({
    "task_name": "artifact_audit_example",
    "repos": [{"id": "repo-a", "ok": True, "result": {}}],
    "summary": {"repos_total": 1, "repos_ok": 1, "repos_failed": 0},
}, indent=2)

_PORTFOLIO_STATE_DATA = {
    "repos": [{"repo_id": "repo-a", "actions": []}],
    "generated_at": "",
}

_GOVERNED_RESULT_DATA = {
    "status": "ok",
    "selected_offset": 0,
    "attempts": [{"offset": 0, "risk_level": "low_risk"}],
    "result": {"run_count": 1},
}

_EXECUTION_RESULT_DATA = {
    "status": "ok",
    "selected_tasks": ["build_portfolio_dashboard"],
    "resolved_via": "selected_actions",
    "returncode": 0,
    "parsed_output": None,
    "stdout": "",
    "stderr": "",
}


def _make_manifest(tmp_path, data=None):
    p = tmp_path / "manifest.json"
    if data is None:
        # Use tmp_path as the repo path so it exists on disk and passes
        # manifest repo-path validation.
        data = {"repos": [{"id": "repo-a", "path": str(tmp_path)}]}
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def _make_args(tmp_path, manifest=None, tasks=None, **kwargs):
    obj = SimpleNamespace(
        manifest=str(manifest or _make_manifest(tmp_path)),
        task=tasks or ["artifact_audit_example"],
        output=str(tmp_path / "governed_portfolio_cycle.json"),
        ledger=None,
        policy=None,
        top_k=3,
        exploration_offset=0,
        max_actions=None,
        explain=False,
        force=False,
    )
    for k, v in kwargs.items():
        setattr(obj, k, v)
    return obj


def _ok_proc(stdout=""):
    proc = MagicMock()
    proc.returncode = 0
    proc.stdout = stdout
    proc.stderr = ""
    return proc


def _side_effect_writing_state(
    artifacts,
    portfolio_state_data=None,
    governed_result_data=None,
    execution_result_data=None,
):
    """Return a side_effect function that writes JSON files on the appropriate subprocess call."""
    pstate = portfolio_state_data or _PORTFOLIO_STATE_DATA
    gresult = governed_result_data or _GOVERNED_RESULT_DATA
    eresult = execution_result_data or _EXECUTION_RESULT_DATA

    def _fn(cmd, **kwargs):
        cmd_str = " ".join(cmd)
        if "build_portfolio_state_from_artifacts" in cmd_str:
            # find --output arg and write the state file
            out_idx = cmd.index("--output")
            out_path = Path(cmd[out_idx + 1])
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(pstate) + "\n", encoding="utf-8")
            return _ok_proc()
        if "run_governed_planner_loop" in cmd_str:
            out_idx = cmd.index("--output")
            out_path = Path(cmd[out_idx + 1])
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(gresult) + "\n", encoding="utf-8")
            return _ok_proc()
        if "execute_governed_actions" in cmd_str:
            out_idx = cmd.index("--output")
            out_path = Path(cmd[out_idx + 1])
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(eresult) + "\n", encoding="utf-8")
            return _ok_proc()
        # portfolio task phase
        return _ok_proc(stdout=_PORTFOLIO_TASK_STDOUT)

    return _fn


# ---------------------------------------------------------------------------
# A. Successful cycle
# ---------------------------------------------------------------------------

class TestSuccessfulCycle:
    def test_returns_zero(self, tmp_path):
        args = _make_args(tmp_path)
        with patch("subprocess.run", side_effect=_side_effect_writing_state(_artifact_paths(_work_dir(args.output)))):
            rc = run_cycle(args)
        assert rc == 0

    def test_output_file_exists(self, tmp_path):
        args = _make_args(tmp_path)
        with patch("subprocess.run", side_effect=_side_effect_writing_state(_artifact_paths(_work_dir(args.output)))):
            run_cycle(args)
        assert Path(args.output).exists()

    def test_status_ok(self, tmp_path):
        args = _make_args(tmp_path)
        with patch("subprocess.run", side_effect=_side_effect_writing_state(_artifact_paths(_work_dir(args.output)))):
            run_cycle(args)
        data = json.loads(Path(args.output).read_text())
        assert data["status"] == "ok"

    def test_tasks_recorded(self, tmp_path):
        args = _make_args(tmp_path, tasks=["artifact_audit_example", "failure_recovery_example"])
        with patch("subprocess.run", side_effect=_side_effect_writing_state(_artifact_paths(_work_dir(args.output)))):
            run_cycle(args)
        data = json.loads(Path(args.output).read_text())
        assert data["tasks"] == ["artifact_audit_example", "failure_recovery_example"]

    def test_artifact_paths_present(self, tmp_path):
        args = _make_args(tmp_path)
        with patch("subprocess.run", side_effect=_side_effect_writing_state(_artifact_paths(_work_dir(args.output)))):
            run_cycle(args)
        data = json.loads(Path(args.output).read_text())
        for key in ("work_dir", "report", "aggregate", "portfolio_state", "governed_result"):
            assert key in data["artifacts"]

    def test_portfolio_task_summary_parsed(self, tmp_path):
        args = _make_args(tmp_path)
        with patch("subprocess.run", side_effect=_side_effect_writing_state(_artifact_paths(_work_dir(args.output)))):
            run_cycle(args)
        data = json.loads(Path(args.output).read_text())
        assert data["portfolio_task_summary"] is not None
        assert data["portfolio_task_summary"]["task_name"] == "artifact_audit_example"

    def test_portfolio_state_parsed(self, tmp_path):
        args = _make_args(tmp_path)
        with patch("subprocess.run", side_effect=_side_effect_writing_state(_artifact_paths(_work_dir(args.output)))):
            run_cycle(args)
        data = json.loads(Path(args.output).read_text())
        assert data["portfolio_state"] == _PORTFOLIO_STATE_DATA

    def test_governed_result_parsed(self, tmp_path):
        args = _make_args(tmp_path)
        with patch("subprocess.run", side_effect=_side_effect_writing_state(_artifact_paths(_work_dir(args.output)))):
            run_cycle(args)
        data = json.loads(Path(args.output).read_text())
        assert data["governed_result"]["selected_offset"] == 0

    def test_manifest_recorded(self, tmp_path):
        manifest = _make_manifest(tmp_path)
        args = _make_args(tmp_path, manifest=manifest)
        with patch("subprocess.run", side_effect=_side_effect_writing_state(_artifact_paths(_work_dir(args.output)))):
            run_cycle(args)
        data = json.loads(Path(args.output).read_text())
        assert data["manifest"] == str(manifest)

    def test_output_is_valid_json(self, tmp_path):
        args = _make_args(tmp_path)
        with patch("subprocess.run", side_effect=_side_effect_writing_state(_artifact_paths(_work_dir(args.output)))):
            run_cycle(args)
        data = json.loads(Path(args.output).read_text())
        assert isinstance(data, dict)


# ---------------------------------------------------------------------------
# B. Governed loop abort
# ---------------------------------------------------------------------------

class TestGovernedLoopAbort:
    def _setup(self, tmp_path):
        """Pre-create governed_result.json and return args + side_effect."""
        args = _make_args(tmp_path)
        wd = _work_dir(args.output)
        artifacts = _artifact_paths(wd)
        wd.mkdir(parents=True, exist_ok=True)

        # Pre-write the governed_result as the real loop does before exiting 1.
        governed_result = {"abort_reason": "high_risk_persistent", "attempts": []}
        Path(artifacts["governed_result"]).write_text(
            json.dumps(governed_result) + "\n", encoding="utf-8"
        )

        def _fn(cmd, **kwargs):
            cmd_str = " ".join(cmd)
            if "build_portfolio_state_from_artifacts" in cmd_str:
                out_idx = cmd.index("--output")
                Path(cmd[out_idx + 1]).parent.mkdir(parents=True, exist_ok=True)
                Path(cmd[out_idx + 1]).write_text(
                    json.dumps(_PORTFOLIO_STATE_DATA) + "\n", encoding="utf-8"
                )
                return _ok_proc()
            if "run_governed_planner_loop" in cmd_str:
                raise subprocess.CalledProcessError(
                    returncode=1, cmd=cmd, output="", stderr="high_risk"
                )
            return _ok_proc(stdout=_PORTFOLIO_TASK_STDOUT)

        return args, _fn

    def test_returns_one(self, tmp_path):
        args, side_effect = self._setup(tmp_path)
        with patch("subprocess.run", side_effect=side_effect):
            rc = run_cycle(args)
        assert rc == 1

    def test_output_file_exists(self, tmp_path):
        args, side_effect = self._setup(tmp_path)
        with patch("subprocess.run", side_effect=side_effect):
            run_cycle(args)
        assert Path(args.output).exists()

    def test_status_aborted(self, tmp_path):
        args, side_effect = self._setup(tmp_path)
        with patch("subprocess.run", side_effect=side_effect):
            run_cycle(args)
        data = json.loads(Path(args.output).read_text())
        assert data["status"] == "aborted"

    def test_phase_governed_loop(self, tmp_path):
        args, side_effect = self._setup(tmp_path)
        with patch("subprocess.run", side_effect=side_effect):
            run_cycle(args)
        data = json.loads(Path(args.output).read_text())
        assert data["phase"] == "governed_loop"

    def test_governed_result_populated_from_file(self, tmp_path):
        args, side_effect = self._setup(tmp_path)
        with patch("subprocess.run", side_effect=side_effect):
            run_cycle(args)
        data = json.loads(Path(args.output).read_text())
        assert data["governed_result"] is not None
        assert data["governed_result"]["abort_reason"] == "high_risk_persistent"


# ---------------------------------------------------------------------------
# C. CLI argument wiring
# ---------------------------------------------------------------------------

class TestCliArgumentWiring:
    def _capture_calls(self, tmp_path, tasks, extra_args=None):
        """Run cycle, capture subprocess.run calls, return (rc, calls)."""
        args = _make_args(tmp_path, tasks=tasks, **(extra_args or {}))
        captured = []

        def _fn(cmd, **kwargs):
            captured.append((cmd, kwargs))
            cmd_str = " ".join(cmd)
            if "build_portfolio_state_from_artifacts" in cmd_str:
                out_idx = cmd.index("--output")
                Path(cmd[out_idx + 1]).parent.mkdir(parents=True, exist_ok=True)
                Path(cmd[out_idx + 1]).write_text(
                    json.dumps(_PORTFOLIO_STATE_DATA) + "\n", encoding="utf-8"
                )
                return _ok_proc()
            if "run_governed_planner_loop" in cmd_str:
                out_idx = cmd.index("--output")
                Path(cmd[out_idx + 1]).parent.mkdir(parents=True, exist_ok=True)
                Path(cmd[out_idx + 1]).write_text(
                    json.dumps(_GOVERNED_RESULT_DATA) + "\n", encoding="utf-8"
                )
                return _ok_proc()
            return _ok_proc(stdout=_PORTFOLIO_TASK_STDOUT)

        with patch("subprocess.run", side_effect=_fn):
            rc = run_cycle(args)
        return rc, captured, args

    def test_portfolio_task_receives_tasks_and_manifest(self, tmp_path):
        _, calls, args = self._capture_calls(
            tmp_path, tasks=["artifact_audit_example", "failure_recovery_example"]
        )
        task_cmd = calls[0][0]
        assert "run_portfolio_task.py" in task_cmd[1]
        assert "artifact_audit_example" in task_cmd
        assert "failure_recovery_example" in task_cmd
        assert task_cmd[-1] == args.manifest

    def test_portfolio_task_uses_work_dir_as_cwd(self, tmp_path):
        _, calls, args = self._capture_calls(tmp_path, tasks=["artifact_audit_example"])
        _, kwargs = calls[0]
        expected_wd = str(_work_dir(args.output))
        assert kwargs.get("cwd") == expected_wd

    def test_state_builder_receives_report_aggregate_output(self, tmp_path):
        _, calls, args = self._capture_calls(tmp_path, tasks=["artifact_audit_example"])
        state_cmd = calls[1][0]
        assert "build_portfolio_state_from_artifacts.py" in state_cmd[1]
        assert "--report" in state_cmd
        assert "--aggregate" in state_cmd
        assert "--output" in state_cmd

    def test_governed_loop_receives_portfolio_state_and_output(self, tmp_path):
        _, calls, args = self._capture_calls(tmp_path, tasks=["artifact_audit_example"])
        loop_cmd = calls[2][0]
        assert "run_governed_planner_loop.py" in loop_cmd[1]
        assert "--portfolio-state" in loop_cmd
        assert "--output" in loop_cmd

    def test_governed_loop_receives_top_k(self, tmp_path):
        _, calls, args = self._capture_calls(
            tmp_path, tasks=["artifact_audit_example"], extra_args={"top_k": 5}
        )
        loop_cmd = calls[2][0]
        idx = loop_cmd.index("--top-k")
        assert loop_cmd[idx + 1] == "5"

    def test_governed_loop_receives_exploration_offset(self, tmp_path):
        _, calls, args = self._capture_calls(
            tmp_path, tasks=["artifact_audit_example"], extra_args={"exploration_offset": 2}
        )
        loop_cmd = calls[2][0]
        idx = loop_cmd.index("--exploration-offset")
        assert loop_cmd[idx + 1] == "2"

    def test_governed_loop_receives_ledger_when_set(self, tmp_path):
        ledger_file = tmp_path / "ledger.json"
        ledger_file.write_text("{}", encoding="utf-8")
        _, calls, args = self._capture_calls(
            tmp_path, tasks=["artifact_audit_example"],
            extra_args={"ledger": str(ledger_file)}
        )
        loop_cmd = calls[2][0]
        assert "--ledger" in loop_cmd

    def test_governed_loop_omits_ledger_when_none(self, tmp_path):
        _, calls, args = self._capture_calls(tmp_path, tasks=["artifact_audit_example"])
        loop_cmd = calls[2][0]
        assert "--ledger" not in loop_cmd

    def test_governed_loop_receives_force_flag(self, tmp_path):
        _, calls, args = self._capture_calls(
            tmp_path, tasks=["artifact_audit_example"], extra_args={"force": True}
        )
        loop_cmd = calls[2][0]
        assert "--force" in loop_cmd

    def test_governed_loop_omits_force_flag_by_default(self, tmp_path):
        _, calls, args = self._capture_calls(tmp_path, tasks=["artifact_audit_example"])
        loop_cmd = calls[2][0]
        assert "--force" not in loop_cmd

    def test_governed_loop_receives_explain_flag(self, tmp_path):
        _, calls, args = self._capture_calls(
            tmp_path, tasks=["artifact_audit_example"], extra_args={"explain": True}
        )
        loop_cmd = calls[2][0]
        assert "--explain" in loop_cmd

    def test_governed_loop_receives_max_actions_when_set(self, tmp_path):
        _, calls, args = self._capture_calls(
            tmp_path, tasks=["artifact_audit_example"], extra_args={"max_actions": 2}
        )
        loop_cmd = calls[2][0]
        assert "--max-actions" in loop_cmd
        idx = loop_cmd.index("--max-actions")
        assert loop_cmd[idx + 1] == "2"

    def test_governed_loop_omits_max_actions_when_none(self, tmp_path):
        _, calls, args = self._capture_calls(tmp_path, tasks=["artifact_audit_example"])
        loop_cmd = calls[2][0]
        assert "--max-actions" not in loop_cmd


# ---------------------------------------------------------------------------
# D. Early phase failure — portfolio_state phase
# ---------------------------------------------------------------------------

class TestEarlyPhaseFailure:
    def test_returns_one_on_state_phase_failure(self, tmp_path):
        args = _make_args(tmp_path)

        def _fn(cmd, **kwargs):
            cmd_str = " ".join(cmd)
            if "build_portfolio_state_from_artifacts" in cmd_str:
                raise subprocess.CalledProcessError(
                    returncode=1, cmd=cmd, output="", stderr="missing csv"
                )
            return _ok_proc(stdout=_PORTFOLIO_TASK_STDOUT)

        with patch("subprocess.run", side_effect=_fn):
            rc = run_cycle(args)
        assert rc == 1

    def test_artifact_written_on_state_phase_failure(self, tmp_path):
        args = _make_args(tmp_path)

        def _fn(cmd, **kwargs):
            cmd_str = " ".join(cmd)
            if "build_portfolio_state_from_artifacts" in cmd_str:
                raise subprocess.CalledProcessError(
                    returncode=1, cmd=cmd, output="", stderr="missing csv"
                )
            return _ok_proc(stdout=_PORTFOLIO_TASK_STDOUT)

        with patch("subprocess.run", side_effect=_fn):
            run_cycle(args)
        assert Path(args.output).exists()

    def test_artifact_status_aborted_on_state_phase_failure(self, tmp_path):
        args = _make_args(tmp_path)

        def _fn(cmd, **kwargs):
            cmd_str = " ".join(cmd)
            if "build_portfolio_state_from_artifacts" in cmd_str:
                raise subprocess.CalledProcessError(
                    returncode=1, cmd=cmd, output="", stderr="missing csv"
                )
            return _ok_proc(stdout=_PORTFOLIO_TASK_STDOUT)

        with patch("subprocess.run", side_effect=_fn):
            run_cycle(args)
        data = json.loads(Path(args.output).read_text())
        assert data["status"] == "aborted"

    def test_artifact_phase_tag_on_state_phase_failure(self, tmp_path):
        args = _make_args(tmp_path)

        def _fn(cmd, **kwargs):
            cmd_str = " ".join(cmd)
            if "build_portfolio_state_from_artifacts" in cmd_str:
                raise subprocess.CalledProcessError(
                    returncode=1, cmd=cmd, output="", stderr="missing csv"
                )
            return _ok_proc(stdout=_PORTFOLIO_TASK_STDOUT)

        with patch("subprocess.run", side_effect=_fn):
            run_cycle(args)
        data = json.loads(Path(args.output).read_text())
        assert data["phase"] == "portfolio_state"

    def test_manifest_invalid_repos_returns_one(self, tmp_path):
        bad_manifest = tmp_path / "bad.json"
        bad_manifest.write_text(json.dumps({"repos": "not-a-list"}), encoding="utf-8")
        args = _make_args(tmp_path, manifest=bad_manifest)
        with patch("subprocess.run") as mock_sub:
            rc = run_cycle(args)
        assert rc == 1
        mock_sub.assert_not_called()

    def test_missing_manifest_returns_one(self, tmp_path):
        args = _make_args(tmp_path)
        args.manifest = str(tmp_path / "nonexistent.json")
        with patch("subprocess.run") as mock_sub:
            rc = run_cycle(args)
        assert rc == 1
        mock_sub.assert_not_called()


# ---------------------------------------------------------------------------
# F. Manifest repo path validation
# ---------------------------------------------------------------------------

class TestValidateManifestRepos:
    """Unit tests for the _validate_manifest_repos helper."""

    def test_valid_repos_returns_empty_list(self, tmp_path):
        real_path = str(tmp_path)
        data = {"repos": [{"id": "repo-a", "path": real_path}]}
        assert _validate_manifest_repos(data) == []

    def test_missing_path_key_flagged(self, tmp_path):
        data = {"repos": [{"id": "repo-a"}]}
        invalid = _validate_manifest_repos(data)
        assert len(invalid) == 1
        assert invalid[0]["id"] == "repo-a"
        assert "missing path" in invalid[0]["reason"]

    def test_missing_id_key_flagged(self, tmp_path):
        data = {"repos": [{"path": str(tmp_path)}]}
        invalid = _validate_manifest_repos(data)
        assert len(invalid) == 1
        assert "missing id" in invalid[0]["reason"]

    def test_nonexistent_path_flagged(self, tmp_path):
        data = {"repos": [{"id": "repo-a", "path": str(tmp_path / "no-such-dir")}]}
        invalid = _validate_manifest_repos(data)
        assert len(invalid) == 1
        assert "does not exist" in invalid[0]["reason"]

    def test_multiple_repos_partial_invalid(self, tmp_path):
        data = {"repos": [
            {"id": "good", "path": str(tmp_path)},
            {"id": "bad", "path": str(tmp_path / "missing")},
        ]}
        invalid = _validate_manifest_repos(data)
        assert len(invalid) == 1
        assert invalid[0]["id"] == "bad"

    def test_empty_repos_list_returns_empty(self):
        assert _validate_manifest_repos({"repos": []}) == []


class TestManifestValidationInCycle:
    """Integration tests: invalid repo path aborts cycle before any subprocess."""

    def test_invalid_repo_path_returns_one(self, tmp_path):
        manifest = _make_manifest(tmp_path, data={
            "repos": [{"id": "repo-a", "path": str(tmp_path / "nonexistent")}]
        })
        args = _make_args(tmp_path, manifest=manifest)
        with patch("subprocess.run") as mock_sub:
            rc = run_cycle(args)
        assert rc == 1
        mock_sub.assert_not_called()

    def test_invalid_repo_path_writes_artifact(self, tmp_path):
        manifest = _make_manifest(tmp_path, data={
            "repos": [{"id": "repo-a", "path": str(tmp_path / "nonexistent")}]
        })
        args = _make_args(tmp_path, manifest=manifest)
        with patch("subprocess.run"):
            run_cycle(args)
        assert Path(args.output).exists()

    def test_invalid_repo_path_artifact_status_aborted(self, tmp_path):
        manifest = _make_manifest(tmp_path, data={
            "repos": [{"id": "repo-a", "path": str(tmp_path / "nonexistent")}]
        })
        args = _make_args(tmp_path, manifest=manifest)
        with patch("subprocess.run"):
            run_cycle(args)
        data = json.loads(Path(args.output).read_text())
        assert data["status"] == "aborted"

    def test_invalid_repo_path_artifact_phase_manifest_validation(self, tmp_path):
        manifest = _make_manifest(tmp_path, data={
            "repos": [{"id": "repo-a", "path": str(tmp_path / "nonexistent")}]
        })
        args = _make_args(tmp_path, manifest=manifest)
        with patch("subprocess.run"):
            run_cycle(args)
        data = json.loads(Path(args.output).read_text())
        assert data["phase"] == "manifest_validation"

    def test_invalid_repo_path_artifact_contains_invalid_repos(self, tmp_path):
        bad_path = str(tmp_path / "nonexistent")
        manifest = _make_manifest(tmp_path, data={
            "repos": [{"id": "repo-a", "path": bad_path}]
        })
        args = _make_args(tmp_path, manifest=manifest)
        with patch("subprocess.run"):
            run_cycle(args)
        data = json.loads(Path(args.output).read_text())
        assert isinstance(data["invalid_repos"], list)
        assert len(data["invalid_repos"]) == 1
        assert data["invalid_repos"][0]["id"] == "repo-a"

    def test_valid_repo_path_proceeds_to_subprocess(self, tmp_path):
        """A manifest with a real existing path must not abort at validation."""
        manifest = _make_manifest(tmp_path, data={
            "repos": [{"id": "repo-a", "path": str(tmp_path)}]
        })
        args = _make_args(tmp_path, manifest=manifest)
        with patch("subprocess.run",
                   side_effect=_side_effect_writing_state(
                       _artifact_paths(_work_dir(args.output))
                   )) as mock_sub:
            rc = run_cycle(args)
        assert rc == 0
        assert mock_sub.called

    def test_artifact_manifest_path_recorded(self, tmp_path):
        manifest = _make_manifest(tmp_path, data={
            "repos": [{"id": "repo-a", "path": str(tmp_path / "nonexistent")}]
        })
        args = _make_args(tmp_path, manifest=manifest)
        with patch("subprocess.run"):
            run_cycle(args)
        data = json.loads(Path(args.output).read_text())
        assert data["manifest"] == str(manifest)


# ---------------------------------------------------------------------------
# E. Work directory naming
# ---------------------------------------------------------------------------

class TestWorkDirNaming:
    def test_work_dir_adjacent_to_output(self, tmp_path):
        output = tmp_path / "my_cycle.json"
        wd = _work_dir(str(output))
        assert wd.parent == tmp_path

    def test_work_dir_stem_suffix(self, tmp_path):
        output = tmp_path / "my_cycle.json"
        wd = _work_dir(str(output))
        assert wd.name == "my_cycle_artifacts"

    def test_artifact_paths_contain_work_dir(self, tmp_path):
        output = tmp_path / "cycle.json"
        wd = _work_dir(str(output))
        ap = _artifact_paths(wd)
        assert ap["work_dir"] == str(wd)
        assert ap["report"].startswith(str(wd))
        assert ap["portfolio_state"].startswith(str(wd))
        assert ap["governed_result"].startswith(str(wd))
        assert ap["execution_result"].startswith(str(wd))


# ---------------------------------------------------------------------------
# G. Governed execution phase
# ---------------------------------------------------------------------------

class TestGovernedExecution:
    """Tests for Phase D: governed execution."""

    def test_success_cycle_includes_execution_result(self, tmp_path):
        args = _make_args(tmp_path)
        artifacts = _artifact_paths(_work_dir(args.output))
        with patch("subprocess.run",
                   side_effect=_side_effect_writing_state(artifacts)):
            run_cycle(args)
        data = json.loads(Path(args.output).read_text())
        assert "execution_result" in data
        assert data["execution_result"] == _EXECUTION_RESULT_DATA

    def test_execution_result_path_in_artifacts(self, tmp_path):
        output = tmp_path / "cycle.json"
        wd = _work_dir(str(output))
        ap = _artifact_paths(wd)
        assert "execution_result" in ap

    def test_executor_failure_returns_one(self, tmp_path):
        args = _make_args(tmp_path)
        wd = _work_dir(args.output)
        artifacts = _artifact_paths(wd)
        wd.mkdir(parents=True, exist_ok=True)

        exec_result = {"status": "aborted", "reason": "no_selected_tasks"}
        Path(artifacts["execution_result"]).parent.mkdir(parents=True, exist_ok=True)

        def _fn(cmd, **kwargs):
            cmd_str = " ".join(cmd)
            if "build_portfolio_state_from_artifacts" in cmd_str:
                out_idx = cmd.index("--output")
                Path(cmd[out_idx + 1]).parent.mkdir(parents=True, exist_ok=True)
                Path(cmd[out_idx + 1]).write_text(
                    json.dumps(_PORTFOLIO_STATE_DATA) + "\n", encoding="utf-8"
                )
                return _ok_proc()
            if "run_governed_planner_loop" in cmd_str:
                out_idx = cmd.index("--output")
                Path(cmd[out_idx + 1]).parent.mkdir(parents=True, exist_ok=True)
                Path(cmd[out_idx + 1]).write_text(
                    json.dumps(_GOVERNED_RESULT_DATA) + "\n", encoding="utf-8"
                )
                return _ok_proc()
            if "execute_governed_actions" in cmd_str:
                out_idx = cmd.index("--output")
                Path(cmd[out_idx + 1]).parent.mkdir(parents=True, exist_ok=True)
                Path(cmd[out_idx + 1]).write_text(
                    json.dumps(exec_result) + "\n", encoding="utf-8"
                )
                raise subprocess.CalledProcessError(
                    returncode=1, cmd=cmd, output="", stderr="no tasks"
                )
            return _ok_proc(stdout=_PORTFOLIO_TASK_STDOUT)

        with patch("subprocess.run", side_effect=_fn):
            rc = run_cycle(args)
        assert rc == 1

    def test_executor_failure_status_aborted(self, tmp_path):
        args = _make_args(tmp_path)
        wd = _work_dir(args.output)
        artifacts = _artifact_paths(wd)
        wd.mkdir(parents=True, exist_ok=True)

        exec_result = {"status": "aborted", "reason": "no_selected_tasks"}

        def _fn(cmd, **kwargs):
            cmd_str = " ".join(cmd)
            if "build_portfolio_state_from_artifacts" in cmd_str:
                out_idx = cmd.index("--output")
                Path(cmd[out_idx + 1]).parent.mkdir(parents=True, exist_ok=True)
                Path(cmd[out_idx + 1]).write_text(
                    json.dumps(_PORTFOLIO_STATE_DATA) + "\n", encoding="utf-8"
                )
                return _ok_proc()
            if "run_governed_planner_loop" in cmd_str:
                out_idx = cmd.index("--output")
                Path(cmd[out_idx + 1]).parent.mkdir(parents=True, exist_ok=True)
                Path(cmd[out_idx + 1]).write_text(
                    json.dumps(_GOVERNED_RESULT_DATA) + "\n", encoding="utf-8"
                )
                return _ok_proc()
            if "execute_governed_actions" in cmd_str:
                out_idx = cmd.index("--output")
                Path(cmd[out_idx + 1]).parent.mkdir(parents=True, exist_ok=True)
                Path(cmd[out_idx + 1]).write_text(
                    json.dumps(exec_result) + "\n", encoding="utf-8"
                )
                raise subprocess.CalledProcessError(
                    returncode=1, cmd=cmd, output="", stderr="no tasks"
                )
            return _ok_proc(stdout=_PORTFOLIO_TASK_STDOUT)

        with patch("subprocess.run", side_effect=_fn):
            run_cycle(args)
        data = json.loads(Path(args.output).read_text())
        assert data["status"] == "aborted"

    def test_executor_failure_phase_governed_execution(self, tmp_path):
        args = _make_args(tmp_path)
        wd = _work_dir(args.output)
        wd.mkdir(parents=True, exist_ok=True)

        def _fn(cmd, **kwargs):
            cmd_str = " ".join(cmd)
            if "build_portfolio_state_from_artifacts" in cmd_str:
                out_idx = cmd.index("--output")
                Path(cmd[out_idx + 1]).parent.mkdir(parents=True, exist_ok=True)
                Path(cmd[out_idx + 1]).write_text(
                    json.dumps(_PORTFOLIO_STATE_DATA) + "\n", encoding="utf-8"
                )
                return _ok_proc()
            if "run_governed_planner_loop" in cmd_str:
                out_idx = cmd.index("--output")
                Path(cmd[out_idx + 1]).parent.mkdir(parents=True, exist_ok=True)
                Path(cmd[out_idx + 1]).write_text(
                    json.dumps(_GOVERNED_RESULT_DATA) + "\n", encoding="utf-8"
                )
                return _ok_proc()
            if "execute_governed_actions" in cmd_str:
                raise subprocess.CalledProcessError(
                    returncode=1, cmd=cmd, output="", stderr="no tasks"
                )
            return _ok_proc(stdout=_PORTFOLIO_TASK_STDOUT)

        with patch("subprocess.run", side_effect=_fn):
            run_cycle(args)
        data = json.loads(Path(args.output).read_text())
        assert data["phase"] == "governed_execution"

    def test_executor_failure_preserves_prior_phase_data(self, tmp_path):
        args = _make_args(tmp_path)
        wd = _work_dir(args.output)
        wd.mkdir(parents=True, exist_ok=True)

        def _fn(cmd, **kwargs):
            cmd_str = " ".join(cmd)
            if "build_portfolio_state_from_artifacts" in cmd_str:
                out_idx = cmd.index("--output")
                Path(cmd[out_idx + 1]).parent.mkdir(parents=True, exist_ok=True)
                Path(cmd[out_idx + 1]).write_text(
                    json.dumps(_PORTFOLIO_STATE_DATA) + "\n", encoding="utf-8"
                )
                return _ok_proc()
            if "run_governed_planner_loop" in cmd_str:
                out_idx = cmd.index("--output")
                Path(cmd[out_idx + 1]).parent.mkdir(parents=True, exist_ok=True)
                Path(cmd[out_idx + 1]).write_text(
                    json.dumps(_GOVERNED_RESULT_DATA) + "\n", encoding="utf-8"
                )
                return _ok_proc()
            if "execute_governed_actions" in cmd_str:
                raise subprocess.CalledProcessError(
                    returncode=1, cmd=cmd, output="", stderr="no tasks"
                )
            return _ok_proc(stdout=_PORTFOLIO_TASK_STDOUT)

        with patch("subprocess.run", side_effect=_fn):
            run_cycle(args)
        data = json.loads(Path(args.output).read_text())
        assert data["portfolio_state"] == _PORTFOLIO_STATE_DATA
        assert data["governed_result"] == _GOVERNED_RESULT_DATA

    def test_executor_receives_governed_result_and_manifest(self, tmp_path):
        args = _make_args(tmp_path)
        artifacts = _artifact_paths(_work_dir(args.output))
        captured_exec_cmd = []

        def _fn(cmd, **kwargs):
            cmd_str = " ".join(cmd)
            if "build_portfolio_state_from_artifacts" in cmd_str:
                out_idx = cmd.index("--output")
                Path(cmd[out_idx + 1]).parent.mkdir(parents=True, exist_ok=True)
                Path(cmd[out_idx + 1]).write_text(
                    json.dumps(_PORTFOLIO_STATE_DATA) + "\n", encoding="utf-8"
                )
                return _ok_proc()
            if "run_governed_planner_loop" in cmd_str:
                out_idx = cmd.index("--output")
                Path(cmd[out_idx + 1]).parent.mkdir(parents=True, exist_ok=True)
                Path(cmd[out_idx + 1]).write_text(
                    json.dumps(_GOVERNED_RESULT_DATA) + "\n", encoding="utf-8"
                )
                return _ok_proc()
            if "execute_governed_actions" in cmd_str:
                captured_exec_cmd.extend(cmd)
                out_idx = cmd.index("--output")
                Path(cmd[out_idx + 1]).parent.mkdir(parents=True, exist_ok=True)
                Path(cmd[out_idx + 1]).write_text(
                    json.dumps(_EXECUTION_RESULT_DATA) + "\n", encoding="utf-8"
                )
                return _ok_proc()
            return _ok_proc(stdout=_PORTFOLIO_TASK_STDOUT)

        with patch("subprocess.run", side_effect=_fn):
            run_cycle(args)

        assert "execute_governed_actions.py" in captured_exec_cmd[1]
        assert "--governed-result" in captured_exec_cmd
        assert "--manifest" in captured_exec_cmd
        assert "--output" in captured_exec_cmd
