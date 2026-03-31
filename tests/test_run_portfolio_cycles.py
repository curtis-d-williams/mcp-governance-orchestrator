# SPDX-License-Identifier: MIT
"""Tests for scripts/run_portfolio_cycles.py.

Covers:
A. Cycle script subprocess invoked with expected args.
B. Archive triggered when output file exists after cycle.
C. time.sleep called with the configured interval.
D. --cycles 2 runs exactly two iterations.
E. Failed cycle run with existing output still archives.
F. Failed cycle run with missing output does not archive.
"""

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, call

import pytest

# ---------------------------------------------------------------------------
# Module loading
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_SCRIPT = _REPO_ROOT / "scripts" / "run_portfolio_cycles.py"
_spec = importlib.util.spec_from_file_location("run_portfolio_cycles", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

run_cycles = _mod.run_cycles
_build_cycle_cmd = _mod._build_cycle_cmd


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CYCLE_JSON = json.dumps({"status": "ok"}, indent=2) + "\n"


def _make_args(tmp_path, **kwargs):
    """Build a minimal args-like namespace for run_cycles."""
    defaults = dict(
        manifest=str(tmp_path / "manifest.json"),
        task=["artifact_audit_example"],
        output=str(tmp_path / "governed_portfolio_cycle.json"),
        ledger=None,
        policy=None,
        top_k=3,
        exploration_offset=0,
        max_actions=None,
        explain=False,
        force=False,
        governance_policy=None,
        archive_dir=str(tmp_path / "archives"),
        interval=60,
        cycles=1,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _noop_subprocess(cmd, **kwargs):
    """Subprocess stub that does nothing (simulates successful cycle)."""
    return MagicMock(returncode=0, stdout="", stderr="")


def _subprocess_writing_output(output_path, content=None):
    """Return a subprocess stub that writes the output file on each call."""
    def _fn(cmd, **kwargs):
        Path(output_path).write_text(content or _CYCLE_JSON, encoding="utf-8")
        return MagicMock(returncode=0, stdout="", stderr="")
    return _fn


def _subprocess_failing_with_output(output_path, content=None):
    """Return a subprocess stub that writes the output file and returns non-zero."""
    def _fn(cmd, **kwargs):
        Path(output_path).write_text(content or _CYCLE_JSON, encoding="utf-8")
        return MagicMock(returncode=1, stdout="", stderr="error")
    return _fn


def _noop_sleep(seconds):
    pass


# ---------------------------------------------------------------------------
# A. Cycle script subprocess invoked with expected args
# ---------------------------------------------------------------------------

class TestSubprocessCommand:
    def test_cycle_script_in_command(self, tmp_path):
        args = _make_args(tmp_path, cycles=1)
        captured = []

        def recording_subprocess(cmd, **kwargs):
            captured.append(cmd)
            return MagicMock(returncode=0, stdout="", stderr="")

        run_cycles(args, subprocess_run=recording_subprocess, sleep_fn=_noop_sleep)
        assert len(captured) == 1
        assert "run_governed_portfolio_cycle.py" in captured[0][1]

    def test_manifest_in_command(self, tmp_path):
        args = _make_args(tmp_path, cycles=1)
        captured = []

        def recording(cmd, **kwargs):
            captured.append(cmd)
            return MagicMock(returncode=0)

        run_cycles(args, subprocess_run=recording, sleep_fn=_noop_sleep)
        cmd = captured[0]
        assert "--manifest" in cmd
        assert args.manifest in cmd

    def test_output_in_command(self, tmp_path):
        args = _make_args(tmp_path, cycles=1)
        captured = []

        def recording(cmd, **kwargs):
            captured.append(cmd)
            return MagicMock(returncode=0)

        run_cycles(args, subprocess_run=recording, sleep_fn=_noop_sleep)
        cmd = captured[0]
        assert "--output" in cmd
        assert args.output in cmd

    def test_task_in_command(self, tmp_path):
        args = _make_args(tmp_path, cycles=1,
                          task=["artifact_audit_example", "failure_recovery_example"])
        captured = []

        def recording(cmd, **kwargs):
            captured.append(cmd)
            return MagicMock(returncode=0)

        run_cycles(args, subprocess_run=recording, sleep_fn=_noop_sleep)
        cmd = captured[0]
        assert cmd.count("--task") == 2
        assert "artifact_audit_example" in cmd
        assert "failure_recovery_example" in cmd

    def test_top_k_in_command(self, tmp_path):
        args = _make_args(tmp_path, cycles=1, top_k=5)
        captured = []

        def recording(cmd, **kwargs):
            captured.append(cmd)
            return MagicMock(returncode=0)

        run_cycles(args, subprocess_run=recording, sleep_fn=_noop_sleep)
        cmd = captured[0]
        idx = cmd.index("--top-k")
        assert cmd[idx + 1] == "5"

    def test_optional_ledger_in_command(self, tmp_path):
        ledger = str(tmp_path / "ledger.json")
        args = _make_args(tmp_path, cycles=1, ledger=ledger)
        captured = []

        def recording(cmd, **kwargs):
            captured.append(cmd)
            return MagicMock(returncode=0)

        run_cycles(args, subprocess_run=recording, sleep_fn=_noop_sleep)
        cmd = captured[0]
        assert "--ledger" in cmd
        assert ledger in cmd

    def test_optional_ledger_absent_when_none(self, tmp_path):
        args = _make_args(tmp_path, cycles=1, ledger=None)
        captured = []

        def recording(cmd, **kwargs):
            captured.append(cmd)
            return MagicMock(returncode=0)

        run_cycles(args, subprocess_run=recording, sleep_fn=_noop_sleep)
        assert "--ledger" not in captured[0]

    def test_force_flag_in_command(self, tmp_path):
        args = _make_args(tmp_path, cycles=1, force=True)
        captured = []

        def recording(cmd, **kwargs):
            captured.append(cmd)
            return MagicMock(returncode=0)

        run_cycles(args, subprocess_run=recording, sleep_fn=_noop_sleep)
        assert "--force" in captured[0]

    def test_force_flag_absent_by_default(self, tmp_path):
        args = _make_args(tmp_path, cycles=1, force=False)
        captured = []

        def recording(cmd, **kwargs):
            captured.append(cmd)
            return MagicMock(returncode=0)

        run_cycles(args, subprocess_run=recording, sleep_fn=_noop_sleep)
        assert "--force" not in captured[0]


# ---------------------------------------------------------------------------
# B. Archive triggered when output file exists
# ---------------------------------------------------------------------------

class TestArchiveTriggered:
    def test_archive_file_created_when_output_exists(self, tmp_path):
        args = _make_args(tmp_path, cycles=1)
        archive_dir = Path(args.archive_dir)

        run_cycles(
            args,
            subprocess_run=_subprocess_writing_output(args.output),
            sleep_fn=_noop_sleep,
        )

        archived_files = list(archive_dir.glob("*_cycle.json"))
        assert len(archived_files) == 1

    def test_archive_content_matches_output(self, tmp_path):
        args = _make_args(tmp_path, cycles=1)
        archive_dir = Path(args.archive_dir)

        run_cycles(
            args,
            subprocess_run=_subprocess_writing_output(args.output),
            sleep_fn=_noop_sleep,
        )

        archived = list(archive_dir.glob("*_cycle.json"))[0]
        assert archived.read_text(encoding="utf-8") == _CYCLE_JSON

    def test_no_archive_when_output_missing(self, tmp_path):
        args = _make_args(tmp_path, cycles=1)
        archive_dir = Path(args.archive_dir)

        run_cycles(
            args,
            subprocess_run=_noop_subprocess,  # does not write output
            sleep_fn=_noop_sleep,
        )

        assert not archive_dir.exists() or len(list(archive_dir.iterdir())) == 0


# ---------------------------------------------------------------------------
# C. time.sleep called with configured interval
# ---------------------------------------------------------------------------

class TestSleepBehavior:
    def test_sleep_called_with_interval(self, tmp_path):
        args = _make_args(tmp_path, cycles=2, interval=120)
        sleep_calls = []

        run_cycles(
            args,
            subprocess_run=_noop_subprocess,
            sleep_fn=lambda s: sleep_calls.append(s),
        )

        assert len(sleep_calls) == 1  # sleep between two iterations, not after last
        assert sleep_calls[0] == 120

    def test_no_sleep_for_single_cycle(self, tmp_path):
        args = _make_args(tmp_path, cycles=1, interval=60)
        sleep_calls = []

        run_cycles(
            args,
            subprocess_run=_noop_subprocess,
            sleep_fn=lambda s: sleep_calls.append(s),
        )

        assert len(sleep_calls) == 0


# ---------------------------------------------------------------------------
# D. --cycles 2 runs exactly two iterations
# ---------------------------------------------------------------------------

class TestCycleCount:
    def test_cycles_2_invokes_subprocess_twice(self, tmp_path):
        args = _make_args(tmp_path, cycles=2)
        call_count = []

        def counting(cmd, **kwargs):
            call_count.append(1)
            return MagicMock(returncode=0)

        run_cycles(args, subprocess_run=counting, sleep_fn=_noop_sleep)
        assert len(call_count) == 2

    def test_run_cycles_returns_iteration_count(self, tmp_path):
        args = _make_args(tmp_path, cycles=3)
        n = run_cycles(args, subprocess_run=_noop_subprocess, sleep_fn=_noop_sleep)
        assert n == 3

    def test_cycles_1_invokes_subprocess_once(self, tmp_path):
        args = _make_args(tmp_path, cycles=1)
        call_count = []

        def counting(cmd, **kwargs):
            call_count.append(1)
            return MagicMock(returncode=0)

        run_cycles(args, subprocess_run=counting, sleep_fn=_noop_sleep)
        assert len(call_count) == 1


# ---------------------------------------------------------------------------
# E. Failed cycle run with existing output still archives
# ---------------------------------------------------------------------------

class TestFailedCycleWithOutput:
    def test_archives_when_cycle_fails_but_output_exists(self, tmp_path):
        args = _make_args(tmp_path, cycles=1)
        archive_dir = Path(args.archive_dir)

        run_cycles(
            args,
            subprocess_run=_subprocess_failing_with_output(args.output),
            sleep_fn=_noop_sleep,
        )

        archived_files = list(archive_dir.glob("*_cycle.json"))
        assert len(archived_files) == 1

    def test_loop_continues_after_failed_cycle(self, tmp_path):
        """After a failed cycle, the loop continues to the next iteration."""
        args = _make_args(tmp_path, cycles=2)
        call_count = []

        def failing_then_ok(cmd, **kwargs):
            call_count.append(1)
            return MagicMock(returncode=1 if len(call_count) == 1 else 0)

        run_cycles(args, subprocess_run=failing_then_ok, sleep_fn=_noop_sleep)
        assert len(call_count) == 2


# ---------------------------------------------------------------------------
# F. Failed cycle run with missing output does not archive
# ---------------------------------------------------------------------------

class TestFailedCycleWithoutOutput:
    def test_no_archive_when_cycle_fails_and_output_missing(self, tmp_path):
        args = _make_args(tmp_path, cycles=1)
        archive_dir = Path(args.archive_dir)

        def failing_no_output(cmd, **kwargs):
            # Does not write the output file.
            return MagicMock(returncode=1, stdout="", stderr="planner aborted")

        run_cycles(args, subprocess_run=failing_no_output, sleep_fn=_noop_sleep)

        assert not archive_dir.exists() or len(list(archive_dir.glob("*_cycle.json"))) == 0

    def test_loop_still_completes_when_output_missing(self, tmp_path):
        args = _make_args(tmp_path, cycles=2)
        call_count = []

        def failing_no_output(cmd, **kwargs):
            call_count.append(1)
            return MagicMock(returncode=1)

        n = run_cycles(args, subprocess_run=failing_no_output, sleep_fn=_noop_sleep)
        assert n == 2
        assert len(call_count) == 2


# ---------------------------------------------------------------------------
# G. _build_cycle_cmd unit tests
# ---------------------------------------------------------------------------

class TestBuildCycleCmd:
    def test_contains_script_path(self, tmp_path):
        args = _make_args(tmp_path)
        cmd = _build_cycle_cmd(args)
        assert "run_governed_portfolio_cycle.py" in cmd[1]

    def test_max_actions_included_when_set(self, tmp_path):
        args = _make_args(tmp_path, max_actions=4)
        cmd = _build_cycle_cmd(args)
        assert "--max-actions" in cmd
        idx = cmd.index("--max-actions")
        assert cmd[idx + 1] == "4"

    def test_max_actions_absent_when_none(self, tmp_path):
        args = _make_args(tmp_path, max_actions=None)
        cmd = _build_cycle_cmd(args)
        assert "--max-actions" not in cmd

    def test_explain_flag_included_when_true(self, tmp_path):
        args = _make_args(tmp_path, explain=True)
        cmd = _build_cycle_cmd(args)
        assert "--explain" in cmd

    def test_explain_flag_absent_by_default(self, tmp_path):
        args = _make_args(tmp_path, explain=False)
        cmd = _build_cycle_cmd(args)
        assert "--explain" not in cmd

    def test_governance_policy_included_when_set(self, tmp_path):
        args = _make_args(tmp_path, governance_policy="/some/policy.json")
        cmd = _build_cycle_cmd(args)
        assert "--governance-policy" in cmd
        idx = cmd.index("--governance-policy")
        assert cmd[idx + 1] == "/some/policy.json"

    def test_governance_policy_absent_when_none(self, tmp_path):
        args = _make_args(tmp_path, governance_policy=None)
        cmd = _build_cycle_cmd(args)
        assert "--governance-policy" not in cmd


# ---------------------------------------------------------------------------
# G2. Work-dir ledger threading tests
# ---------------------------------------------------------------------------

class TestWorkDirLedgerThreading:
    def test_ledger_replaced_when_work_dir_ledger_exists(self, tmp_path):
        """When work_dir_ledger is written by cycle N, cycle N+1 cmd uses it."""
        args = _make_args(tmp_path, cycles=2, ledger=None)
        output_stem = Path(args.output).stem
        ledger_path = (
            Path(args.output).parent
            / f"{output_stem}_artifacts"
            / "action_effectiveness_ledger.json"
        )
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        captured_cmds = []

        def _writing_subprocess(cmd, **kwargs):
            captured_cmds.append(list(cmd))
            ledger_path.write_text('{"actions": {}}', encoding="utf-8")
            return MagicMock(returncode=0, stdout="", stderr="")

        run_cycles(args, subprocess_run=_writing_subprocess, sleep_fn=_noop_sleep)

        assert len(captured_cmds) == 2
        assert "--ledger" not in captured_cmds[0]
        assert "--ledger" in captured_cmds[1]
        idx = captured_cmds[1].index("--ledger")
        assert captured_cmds[1][idx + 1] == str(ledger_path)

    def test_ledger_path_stem_matches_output_stem(self, tmp_path):
        """Injected ledger path is <output_stem>_artifacts/action_effectiveness_ledger.json."""
        args = _make_args(tmp_path, cycles=2, ledger=None)
        output_stem = Path(args.output).stem
        ledger_path = (
            Path(args.output).parent
            / f"{output_stem}_artifacts"
            / "action_effectiveness_ledger.json"
        )
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        captured_cmds = []

        def _writing_subprocess(cmd, **kwargs):
            captured_cmds.append(list(cmd))
            ledger_path.write_text('{"actions": {}}', encoding="utf-8")
            return MagicMock(returncode=0, stdout="", stderr="")

        run_cycles(args, subprocess_run=_writing_subprocess, sleep_fn=_noop_sleep)

        idx = captured_cmds[1].index("--ledger")
        injected = captured_cmds[1][idx + 1]
        assert injected.endswith("action_effectiveness_ledger.json")
        assert f"{output_stem}_artifacts" in injected


# ---------------------------------------------------------------------------
# H. Collision-safe archiving across multiple iterations
# ---------------------------------------------------------------------------

class TestCollisionSafeArchiving:
    def test_two_cycles_same_second_produce_distinct_files(self, tmp_path):
        """Patching _now_timestamp to a fixed value forces the same-second scenario."""
        args = _make_args(tmp_path, cycles=2)
        archive_dir = Path(args.archive_dir)
        fixed_ts = "2024-03-01T12-00-00"

        # Both iterations write the output file and both archive calls see the
        # same timestamp, exercising the collision-avoidance logic.
        def writing_subprocess(cmd, **kwargs):
            Path(args.output).write_text(_CYCLE_JSON, encoding="utf-8")
            return MagicMock(returncode=0)

        # Patch _now_timestamp inside the loaded archive module so that both
        # archive calls receive an identical timestamp basis.
        import unittest.mock as _mock
        with _mock.patch.object(_mod._archive_mod, "_now_timestamp",
                                return_value=fixed_ts):
            run_cycles(args, subprocess_run=writing_subprocess,
                       sleep_fn=_noop_sleep)

        all_archives = sorted(archive_dir.glob(f"{fixed_ts}_cycle*.json"))
        assert len(all_archives) == 2, f"expected 2 archives, got {all_archives}"

    def test_two_cycles_archive_filenames_are_distinct(self, tmp_path):
        args = _make_args(tmp_path, cycles=2)
        archive_dir = Path(args.archive_dir)
        fixed_ts = "2024-03-01T12-00-00"

        def writing_subprocess(cmd, **kwargs):
            Path(args.output).write_text(_CYCLE_JSON, encoding="utf-8")
            return MagicMock(returncode=0)

        import unittest.mock as _mock
        with _mock.patch.object(_mod._archive_mod, "_now_timestamp",
                                return_value=fixed_ts):
            run_cycles(args, subprocess_run=writing_subprocess,
                       sleep_fn=_noop_sleep)

        names = sorted(p.name for p in archive_dir.glob(f"{fixed_ts}_cycle*.json"))
        assert names[0] == f"{fixed_ts}_cycle.json"
        assert names[1] == f"{fixed_ts}_cycle_1.json"

    def test_both_archived_contents_match_cycle_output(self, tmp_path):
        args = _make_args(tmp_path, cycles=2)
        archive_dir = Path(args.archive_dir)
        fixed_ts = "2024-03-01T12-00-00"

        def writing_subprocess(cmd, **kwargs):
            Path(args.output).write_text(_CYCLE_JSON, encoding="utf-8")
            return MagicMock(returncode=0)

        import unittest.mock as _mock
        with _mock.patch.object(_mod._archive_mod, "_now_timestamp",
                                return_value=fixed_ts):
            run_cycles(args, subprocess_run=writing_subprocess,
                       sleep_fn=_noop_sleep)

        for p in archive_dir.glob(f"{fixed_ts}_cycle*.json"):
            assert p.read_text(encoding="utf-8") == _CYCLE_JSON


# ---------------------------------------------------------------------------
# I. Ledger threading across all cycle invocations
# ---------------------------------------------------------------------------

class TestLedgerThreading:
    def test_explicit_ledger_present_in_every_cycle_invocation(self, tmp_path):
        ledger = str(tmp_path / "ledger.json")
        args = _make_args(tmp_path, cycles=3, ledger=ledger)
        captured_cmds = []

        def recording(cmd, **kwargs):
            captured_cmds.append(list(cmd))
            return MagicMock(returncode=0)

        run_cycles(args, subprocess_run=recording, sleep_fn=_noop_sleep)

        assert len(captured_cmds) == 3
        for cmd in captured_cmds:
            assert "--ledger" in cmd
            assert ledger in cmd

    def test_work_dir_ledger_replaces_explicit_ledger_in_next_cycle(self, tmp_path):
        original_ledger = str(tmp_path / "original_ledger.json")
        args = _make_args(tmp_path, cycles=2, ledger=original_ledger)
        work_dir_ledger = (
            Path(args.output).parent
            / f"{Path(args.output).stem}_artifacts"
            / "action_effectiveness_ledger.json"
        )
        work_dir_ledger.parent.mkdir(parents=True, exist_ok=True)
        work_dir_ledger.write_text("{}")
        captured_cmds = []

        def recording(cmd, **kwargs):
            captured_cmds.append(list(cmd))
            return MagicMock(returncode=0)

        run_cycles(args, subprocess_run=recording, sleep_fn=_noop_sleep)

        assert len(captured_cmds) == 2
        idx1 = captured_cmds[0].index("--ledger")
        assert captured_cmds[0][idx1 + 1] == original_ledger
        idx2 = captured_cmds[1].index("--ledger")
        assert captured_cmds[1][idx2 + 1] == str(work_dir_ledger)
        assert captured_cmds[1].count("--ledger") == 1

    def test_work_dir_ledger_appended_when_no_explicit_ledger(self, tmp_path):
        args = _make_args(tmp_path, cycles=2, ledger=None)
        work_dir_ledger = (
            Path(args.output).parent
            / f"{Path(args.output).stem}_artifacts"
            / "action_effectiveness_ledger.json"
        )
        work_dir_ledger.parent.mkdir(parents=True, exist_ok=True)
        work_dir_ledger.write_text("{}")
        captured_cmds = []

        def recording(cmd, **kwargs):
            captured_cmds.append(list(cmd))
            return MagicMock(returncode=0)

        run_cycles(args, subprocess_run=recording, sleep_fn=_noop_sleep)

        assert len(captured_cmds) == 2
        assert "--ledger" not in captured_cmds[0]
        assert "--ledger" in captured_cmds[1]
        assert captured_cmds[1][captured_cmds[1].index("--ledger") + 1] == str(work_dir_ledger)
        assert captured_cmds[1].count("--ledger") == 1


# ---------------------------------------------------------------------------
# J. Per-cycle operator status output
# ---------------------------------------------------------------------------

class TestCycleStatusOutput:
    def test_status_ok_printed_on_success(self, tmp_path, capsys):
        args = _make_args(tmp_path, cycles=1)
        run_cycles(args, subprocess_run=_noop_subprocess, sleep_fn=_noop_sleep)
        out = capsys.readouterr().out
        assert "[cycle 1]" in out
        assert "ok" in out

    def test_status_failed_printed_on_nonzero_returncode(self, tmp_path, capsys):
        def failing(cmd, **kwargs):
            return MagicMock(returncode=1, stdout="", stderr="")
        args = _make_args(tmp_path, cycles=1)
        run_cycles(args, subprocess_run=failing, sleep_fn=_noop_sleep)
        out = capsys.readouterr().out
        assert "[cycle 1]" in out
        assert "FAILED" in out

    def test_archive_path_shown_when_output_exists(self, tmp_path, capsys):
        args = _make_args(tmp_path, cycles=1)
        run_cycles(
            args,
            subprocess_run=_subprocess_writing_output(args.output),
            sleep_fn=_noop_sleep,
        )
        out = capsys.readouterr().out
        assert "archived:" in out
        assert "no output archived" not in out

    def test_no_archive_path_shown_when_output_missing(self, tmp_path, capsys):
        args = _make_args(tmp_path, cycles=1)
        run_cycles(args, subprocess_run=_noop_subprocess, sleep_fn=_noop_sleep)
        out = capsys.readouterr().out
        assert "no output archived" in out

    def test_status_line_printed_for_each_iteration(self, tmp_path, capsys):
        args = _make_args(tmp_path, cycles=3)
        run_cycles(args, subprocess_run=_noop_subprocess, sleep_fn=_noop_sleep)
        out = capsys.readouterr().out
        assert "[cycle 1]" in out
        assert "[cycle 2]" in out
        assert "[cycle 3]" in out

    def test_inner_cycle_stdout_forwarded_when_nonempty(self, tmp_path, capsys):
        def subprocess_with_stdout(cmd, **kwargs):
            return MagicMock(returncode=0,
                             stdout="[cycle] ok | output: governed_portfolio_cycle.json\n",
                             stderr="")
        args = _make_args(tmp_path, cycles=1)
        run_cycles(args, subprocess_run=subprocess_with_stdout, sleep_fn=_noop_sleep)
        out = capsys.readouterr().out
        assert "[cycle] ok" in out

    def test_inner_cycle_stdout_not_forwarded_when_empty(self, tmp_path, capsys):
        args = _make_args(tmp_path, cycles=1)
        run_cycles(args, subprocess_run=_noop_subprocess, sleep_fn=_noop_sleep)
        out = capsys.readouterr().out
        assert out.count("[cycle") == 1

    def test_inner_cycle_stdout_forwarded_on_failed_cycle(self, tmp_path, capsys):
        def failing_with_stdout(cmd, **kwargs):
            return MagicMock(returncode=1,
                             stdout="[cycle] ABORTED (phase: C) | output: governed_portfolio_cycle.json\n",
                             stderr="")
        args = _make_args(tmp_path, cycles=1)
        run_cycles(args, subprocess_run=failing_with_stdout, sleep_fn=_noop_sleep)
        out = capsys.readouterr().out
        assert "[cycle] ABORTED" in out
