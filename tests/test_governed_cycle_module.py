# SPDX-License-Identifier: MIT
"""Focused unit tests for the governed_cycle module.

Covers the pure/stateless helpers independently of the CLI entrypoint:
- write_json
- try_parse_json / try_read_json
- validate_manifest_repos
- work_dir / artifact_paths
- resolve_planner_ledger
- build_runtime_config
- run_governed_loop (subprocess cmd construction)
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from mcp_governance_orchestrator.governed_cycle import (
    artifact_paths,
    build_runtime_config,
    resolve_planner_ledger,
    run_cycle,
    run_governed_loop,
    try_parse_json,
    try_read_json,
    validate_manifest_repos,
    work_dir,
    write_json,
)


# ---------------------------------------------------------------------------
# write_json
# ---------------------------------------------------------------------------

class TestWriteJson:
    def test_creates_file(self, tmp_path):
        p = tmp_path / "out.json"
        write_json(str(p), {"k": "v"})
        assert p.exists()

    def test_valid_json(self, tmp_path):
        p = tmp_path / "out.json"
        write_json(str(p), {"a": 1, "b": 2})
        assert json.loads(p.read_text()) == {"a": 1, "b": 2}

    def test_sorted_keys(self, tmp_path):
        p = tmp_path / "out.json"
        write_json(str(p), {"z": 1, "a": 2})
        raw = p.read_text()
        assert raw.index('"a"') < raw.index('"z"')

    def test_trailing_newline(self, tmp_path):
        p = tmp_path / "out.json"
        write_json(str(p), {"x": 1})
        assert p.read_text().endswith("\n")

    def test_creates_parent_dirs(self, tmp_path):
        p = tmp_path / "nested" / "dir" / "out.json"
        write_json(str(p), {})
        assert p.exists()


# ---------------------------------------------------------------------------
# try_parse_json
# ---------------------------------------------------------------------------

class TestTryParseJson:
    def test_valid_json(self):
        assert try_parse_json('{"a": 1}') == {"a": 1}

    def test_invalid_json_returns_none(self):
        assert try_parse_json("not json") is None

    def test_none_input_returns_none(self):
        assert try_parse_json(None) is None

    def test_empty_string_returns_none(self):
        assert try_parse_json("") is None


# ---------------------------------------------------------------------------
# try_read_json
# ---------------------------------------------------------------------------

class TestTryReadJson:
    def test_reads_existing_file(self, tmp_path):
        p = tmp_path / "f.json"
        p.write_text('{"x": 42}', encoding="utf-8")
        assert try_read_json(str(p)) == {"x": 42}

    def test_missing_file_returns_none(self, tmp_path):
        assert try_read_json(str(tmp_path / "missing.json")) is None

    def test_malformed_json_returns_none(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{ broken", encoding="utf-8")
        assert try_read_json(str(p)) is None


# ---------------------------------------------------------------------------
# validate_manifest_repos
# ---------------------------------------------------------------------------

class TestValidateManifestRepos:
    def test_valid_repos_empty_list(self, tmp_path):
        data = {"repos": [{"id": "r", "path": str(tmp_path)}]}
        assert validate_manifest_repos(data) == []

    def test_missing_id_flagged(self, tmp_path):
        data = {"repos": [{"path": str(tmp_path)}]}
        result = validate_manifest_repos(data)
        assert len(result) == 1
        assert "missing id" in result[0]["reason"]

    def test_missing_path_flagged(self):
        data = {"repos": [{"id": "r"}]}
        result = validate_manifest_repos(data)
        assert len(result) == 1
        assert "missing path" in result[0]["reason"]

    def test_nonexistent_path_flagged(self, tmp_path):
        data = {"repos": [{"id": "r", "path": str(tmp_path / "no-such")}]}
        result = validate_manifest_repos(data)
        assert len(result) == 1
        assert "does not exist" in result[0]["reason"]

    def test_empty_repos_list(self):
        assert validate_manifest_repos({"repos": []}) == []

    def test_no_repos_key(self):
        assert validate_manifest_repos({}) == []


# ---------------------------------------------------------------------------
# work_dir / artifact_paths
# ---------------------------------------------------------------------------

class TestWorkDir:
    def test_stem_suffix(self, tmp_path):
        output = tmp_path / "cycle.json"
        wd = work_dir(str(output))
        assert wd.name == "cycle_artifacts"
        assert wd.parent == tmp_path

    def test_returns_path(self, tmp_path):
        output = tmp_path / "out.json"
        assert isinstance(work_dir(str(output)), Path)


class TestArtifactPaths:
    def test_required_keys(self, tmp_path):
        arts = artifact_paths(tmp_path)
        for key in (
            "work_dir", "report", "aggregate", "portfolio_state",
            "governed_result", "execution_result", "execution_history",
            "action_effectiveness_ledger", "cycle_history",
            "capability_effectiveness_ledger",
        ):
            assert key in arts

    def test_work_dir_value(self, tmp_path):
        arts = artifact_paths(tmp_path)
        assert arts["work_dir"] == str(tmp_path)

    def test_all_values_are_strings(self, tmp_path):
        arts = artifact_paths(tmp_path)
        assert all(isinstance(v, str) for v in arts.values())


# ---------------------------------------------------------------------------
# resolve_planner_ledger
# ---------------------------------------------------------------------------

class TestResolvePlannerLedger:
    def _arts(self, tmp_path):
        return artifact_paths(tmp_path)

    def test_explicit_arg_wins(self, tmp_path):
        arts = self._arts(tmp_path)
        source, path = resolve_planner_ledger("/some/ledger.json", arts)
        assert source == "explicit"
        assert path == "/some/ledger.json"

    def test_work_dir_ledger_used_when_present(self, tmp_path):
        arts = self._arts(tmp_path)
        ledger_path = Path(arts["action_effectiveness_ledger"])
        ledger_path.write_text("{}", encoding="utf-8")
        source, path = resolve_planner_ledger(None, arts)
        assert source == "work_dir"
        assert path == str(ledger_path)

    def test_none_when_no_ledger(self, tmp_path):
        arts = self._arts(tmp_path)
        source, path = resolve_planner_ledger(None, arts)
        assert source == "none"
        assert path is None

    def test_explicit_overrides_work_dir(self, tmp_path):
        arts = self._arts(tmp_path)
        Path(arts["action_effectiveness_ledger"]).write_text("{}", encoding="utf-8")
        source, path = resolve_planner_ledger("/explicit.json", arts)
        assert source == "explicit"
        assert path == "/explicit.json"


# ---------------------------------------------------------------------------
# build_runtime_config
# ---------------------------------------------------------------------------

class TestBuildRuntimeConfig:
    def _args(self, capability_ledger=None):
        return SimpleNamespace(
            top_k=3,
            exploration_offset=0,
            policy=None,
            max_actions=None,
            explain=False,
            force=False,
            governance_policy=None,
            repo_ids=None,
            capability_ledger=capability_ledger,
        )

    def test_capability_ledger_none_by_default(self):
        config = build_runtime_config(self._args(), ledger_path=None)
        assert "capability_ledger" in config
        assert config["capability_ledger"] is None

    def test_capability_ledger_threaded(self):
        config = build_runtime_config(self._args(capability_ledger="/some/cap.json"), ledger_path=None)
        assert config["capability_ledger"] == "/some/cap.json"

    def test_capability_ledger_absent_on_args(self):
        args = SimpleNamespace(
            top_k=3, exploration_offset=0, policy=None,
            max_actions=None, explain=False, force=False,
            governance_policy=None, repo_ids=None,
        )
        config = build_runtime_config(args, ledger_path=None)
        assert config["capability_ledger"] is None


# ---------------------------------------------------------------------------
# run_governed_loop — subprocess cmd construction
# ---------------------------------------------------------------------------

class TestRunGovernedLoopCapabilityLedger:
    def _arts(self, tmp_path):
        return artifact_paths(tmp_path)

    def test_capability_ledger_arg_included_when_provided(self, tmp_path):
        arts = self._arts(tmp_path)
        cap_path = "/persistent/capability_effectiveness_ledger.json"
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)
            run_governed_loop(arts, top_k=3, exploration_offset=0, capability_ledger=cap_path)
        cmd = mock_run.call_args[0][0]
        assert "--capability-ledger" in cmd
        assert cap_path in cmd

    def test_capability_ledger_arg_omitted_when_none(self, tmp_path):
        arts = self._arts(tmp_path)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)
            run_governed_loop(arts, top_k=3, exploration_offset=0, capability_ledger=None)
        cmd = mock_run.call_args[0][0]
        assert "--capability-ledger" not in cmd


# ---------------------------------------------------------------------------
# run_cycle — capability_effectiveness_ledger persistence
# ---------------------------------------------------------------------------

_GOVERNED_RESULT_DATA = {
    "status": "ok",
    "selected_offset": 0,
    "attempts": [{"offset": 0, "risk_level": "low_risk"}],
    "result": {"run_count": 1},
    "capability_effectiveness_ledger": {
        "capabilities": {
            "_repair_cycle": {
                "total_syntheses": 3,
                "failed_syntheses": 1,
                "successful_syntheses": 2,
                "successful_evolved_syntheses": 0,
            }
        }
    },
}


def _make_args(tmp_path, capability_ledger=None):
    """Build a minimal argparse-like namespace for run_cycle."""
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"repos": [{"id": "r", "path": str(tmp_path)}]}),
        encoding="utf-8",
    )
    return SimpleNamespace(
        manifest=str(manifest),
        task=["artifact_audit_example"],
        output=str(tmp_path / "cycle.json"),
        ledger=None,
        policy=None,
        top_k=3,
        exploration_offset=0,
        max_actions=None,
        explain=False,
        force=False,
        governance_policy=None,
        repo_ids=None,
        capability_ledger=capability_ledger,
    )


def _ok_proc(stdout="{}"):
    m = MagicMock()
    m.stdout = stdout
    m.stderr = ""
    m.returncode = 0
    return m


class TestCapabilityLedgerPersistenceInRunCycle:
    def test_capability_ledger_written_after_phase_c(self, tmp_path):
        """update_capability_effectiveness_ledger is called once when capability_ledger is set."""
        args = _make_args(tmp_path, capability_ledger=str(tmp_path / "cap.json"))
        wd = work_dir(args.output)
        wd.mkdir(parents=True, exist_ok=True)
        arts = artifact_paths(wd)

        # Write governed_result so try_read_json returns data after Phase C
        import json as _json
        Path(arts["governed_result"]).write_text(
            _json.dumps(_GOVERNED_RESULT_DATA), encoding="utf-8"
        )

        _phases = [
            "run_portfolio_tasks",
            "run_build_portfolio_state",
            "run_governed_loop",
            "run_execute_governed_actions",
            "run_update_execution_history",
            "run_update_action_effectiveness_from_history",
            "run_update_cycle_history",
            "run_aggregate_cycle_history",
            "run_detect_cycle_history_regression",
            "run_enforce_governance_policy",
        ]

        def _make_proc_returning_governed_result(name):
            proc = _ok_proc()
            if name == "run_portfolio_tasks":
                proc.stdout = "{}"
            return proc

        with patch.multiple(
            "mcp_governance_orchestrator.governed_cycle",
            run_portfolio_tasks=MagicMock(return_value=_ok_proc("{}")),
            run_build_portfolio_state=MagicMock(return_value=_ok_proc()),
            run_governed_loop=MagicMock(return_value=_ok_proc()),
            run_execute_governed_actions=MagicMock(return_value=_ok_proc()),
            run_update_execution_history=MagicMock(return_value=_ok_proc()),
            run_update_action_effectiveness_from_history=MagicMock(return_value=_ok_proc()),
            run_update_cycle_history=MagicMock(return_value=_ok_proc()),
            run_aggregate_cycle_history=MagicMock(return_value=_ok_proc()),
            run_detect_cycle_history_regression=MagicMock(return_value=_ok_proc()),
            run_enforce_governance_policy=MagicMock(return_value=_ok_proc()),
        ):
            with patch(
                "mcp_governance_orchestrator.governed_cycle.update_capability_effectiveness_ledger"
            ) as mock_update:
                run_cycle(args)

        mock_update.assert_called_once_with(
            ledger_path=arts["capability_effectiveness_ledger"],
            cycle_artifact_path=arts["governed_result"],
            output_path=arts["capability_effectiveness_ledger"],
        )

    def test_capability_ledger_not_written_when_no_ledger_arg(self, tmp_path):
        """update_capability_effectiveness_ledger is NOT called when capability_ledger is absent."""
        args = _make_args(tmp_path, capability_ledger=None)
        wd = work_dir(args.output)
        wd.mkdir(parents=True, exist_ok=True)
        arts = artifact_paths(wd)

        import json as _json
        Path(arts["governed_result"]).write_text(
            _json.dumps(_GOVERNED_RESULT_DATA), encoding="utf-8"
        )

        with patch.multiple(
            "mcp_governance_orchestrator.governed_cycle",
            run_portfolio_tasks=MagicMock(return_value=_ok_proc("{}")),
            run_build_portfolio_state=MagicMock(return_value=_ok_proc()),
            run_governed_loop=MagicMock(return_value=_ok_proc()),
            run_execute_governed_actions=MagicMock(return_value=_ok_proc()),
            run_update_execution_history=MagicMock(return_value=_ok_proc()),
            run_update_action_effectiveness_from_history=MagicMock(return_value=_ok_proc()),
            run_update_cycle_history=MagicMock(return_value=_ok_proc()),
            run_aggregate_cycle_history=MagicMock(return_value=_ok_proc()),
            run_detect_cycle_history_regression=MagicMock(return_value=_ok_proc()),
            run_enforce_governance_policy=MagicMock(return_value=_ok_proc()),
        ):
            with patch(
                "mcp_governance_orchestrator.governed_cycle.update_capability_effectiveness_ledger"
            ) as mock_update:
                run_cycle(args)

        mock_update.assert_not_called()

    def test_capability_ledger_written_to_disk_real_reference(self, tmp_path):
        """update_capability_effectiveness_ledger runs un-mocked and writes ledger to disk."""
        args = _make_args(tmp_path, capability_ledger=str(tmp_path / "cap.json"))
        wd = work_dir(args.output)
        wd.mkdir(parents=True, exist_ok=True)
        arts = artifact_paths(wd)

        Path(arts["governed_result"]).write_text(
            json.dumps(_GOVERNED_RESULT_DATA), encoding="utf-8"
        )

        with patch.multiple(
            "mcp_governance_orchestrator.governed_cycle",
            run_portfolio_tasks=MagicMock(return_value=_ok_proc("{}")),
            run_build_portfolio_state=MagicMock(return_value=_ok_proc()),
            run_governed_loop=MagicMock(return_value=_ok_proc()),
            run_execute_governed_actions=MagicMock(return_value=_ok_proc()),
            run_update_execution_history=MagicMock(return_value=_ok_proc()),
            run_update_action_effectiveness_from_history=MagicMock(return_value=_ok_proc()),
            run_update_cycle_history=MagicMock(return_value=_ok_proc()),
            run_aggregate_cycle_history=MagicMock(return_value=_ok_proc()),
            run_detect_cycle_history_regression=MagicMock(return_value=_ok_proc()),
            run_enforce_governance_policy=MagicMock(return_value=_ok_proc()),
        ):
            run_cycle(args)

        ledger_path = Path(arts["capability_effectiveness_ledger"])
        assert ledger_path.exists(), "capability_effectiveness_ledger.json was not written"
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        caps = ledger.get("capabilities", {})
        assert "_repair_cycle" in caps, "_repair_cycle capability not merged into ledger"
        assert caps["_repair_cycle"]["total_syntheses"] == 3


# ---------------------------------------------------------------------------
# run_cycle — execution_result.json → execution_history.json real handoff
# ---------------------------------------------------------------------------

import importlib.util as _importlib_util

def _load_update_execution_history():
    """Load update_execution_history.py directly from scripts/ without subprocess."""
    spec = _importlib_util.spec_from_file_location(
        "update_execution_history",
        str(_REPO_ROOT / "scripts" / "update_execution_history.py"),
    )
    mod = _importlib_util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestExecutionHistoryRealHandoff:
    """Exercise the real update_execution_history file handoff via the idle path.

    governed_result["idle"] == True causes governed_cycle.py to write
    execution_result.json itself (without calling run_execute_governed_actions).
    run_update_execution_history is replaced with a thin shim that calls the
    real update_execution_history() function directly, exercising the
    execution_result.json -> execution_history.json handoff without a subprocess.
    """

    def test_execution_history_written_via_real_update(self, tmp_path):
        args = _make_args(tmp_path)
        wd = work_dir(args.output)
        wd.mkdir(parents=True, exist_ok=True)
        arts = artifact_paths(wd)

        # governed_result with idle=True so governed_cycle writes execution_result itself
        idle_governed_result = {
            "status": "ok",
            "idle": True,
            "selected_offset": 0,
            "attempts": [],
            "result": {},
        }
        Path(arts["governed_result"]).write_text(
            json.dumps(idle_governed_result), encoding="utf-8"
        )

        _ueh_mod = _load_update_execution_history()

        def _real_update_execution_history_shim(artifacts):
            """Thin shim: calls the real update_execution_history() directly."""
            rc = _ueh_mod.update_execution_history(
                artifacts["execution_result"],
                artifacts["execution_history"],
            )
            if rc != 0:
                raise RuntimeError("update_execution_history returned non-zero")
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

        with patch.multiple(
            "mcp_governance_orchestrator.governed_cycle",
            run_portfolio_tasks=MagicMock(return_value=_ok_proc("{}")),
            run_build_portfolio_state=MagicMock(return_value=_ok_proc()),
            run_governed_loop=MagicMock(return_value=_ok_proc()),
            run_execute_governed_actions=MagicMock(return_value=_ok_proc()),
            run_update_execution_history=_real_update_execution_history_shim,
            run_update_action_effectiveness_from_history=MagicMock(return_value=_ok_proc()),
            run_update_cycle_history=MagicMock(return_value=_ok_proc()),
            run_aggregate_cycle_history=MagicMock(return_value=_ok_proc()),
            run_detect_cycle_history_regression=MagicMock(return_value=_ok_proc()),
            run_enforce_governance_policy=MagicMock(return_value=_ok_proc()),
        ):
            run_cycle(args)

        history_path = Path(arts["execution_history"])
        assert history_path.exists(), "execution_history.json was not written"
        history = json.loads(history_path.read_text(encoding="utf-8"))
        records = history.get("records", [])
        assert len(records) == 1, f"expected 1 record, got {len(records)}"
        record = records[0]
        # idle path sets status="ok", resolved_via="no_action_window", selected_tasks=[]
        assert record["status"] == "ok"
        assert record["resolved_via"] == "no_action_window"
        assert record["selected_tasks"] == []
