# SPDX-License-Identifier: MIT
"""Tests for scripts/run_example_governed_cycles.py.

Covers:
A. run_example_cycles — calls make_example_manifest then run_portfolio_cycles.
B. make_example_manifest failure short-circuits before run_portfolio_cycles.
C. CLI argument wiring — forwarded args reach run_portfolio_cycles correctly.
D. Default argument values.
E. run_portfolio_cycles exit code is propagated.
"""

import importlib.util
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

_SCRIPT = _REPO_ROOT / "scripts" / "run_example_governed_cycles.py"
_spec = importlib.util.spec_from_file_location("run_example_governed_cycles", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

run_example_cycles = _mod.run_example_cycles
main = _mod.main

_MAKE_MANIFEST_SCRIPT = _mod._MAKE_MANIFEST_SCRIPT
_RUN_CYCLES_SCRIPT = _mod._RUN_CYCLES_SCRIPT
_DEFAULT_TASK = _mod._DEFAULT_TASK
_DEFAULT_LEDGER = _mod._DEFAULT_LEDGER
_DEFAULT_TOP_K = _mod._DEFAULT_TOP_K
_DEFAULT_INTERVAL = _mod._DEFAULT_INTERVAL
_DEFAULT_CYCLES = _mod._DEFAULT_CYCLES
_DEFAULT_OUTPUT = _mod._DEFAULT_OUTPUT
_DEFAULT_ARCHIVE_DIR = _mod._DEFAULT_ARCHIVE_DIR
_DEFAULT_MANIFEST = _mod._DEFAULT_MANIFEST


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_proc(returncode=0, stdout="", stderr=""):
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = stderr
    return m


def _make_args(**kwargs):
    defaults = dict(
        manifest=_DEFAULT_MANIFEST,
        task=_DEFAULT_TASK,
        ledger=_DEFAULT_LEDGER,
        top_k=_DEFAULT_TOP_K,
        interval=_DEFAULT_INTERVAL,
        cycles=_DEFAULT_CYCLES,
        output=_DEFAULT_OUTPUT,
        archive_dir=_DEFAULT_ARCHIVE_DIR,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# A. Normal happy path
# ---------------------------------------------------------------------------

class TestRunExampleCycles:
    def test_calls_make_manifest_first(self):
        """make_example_manifest.py is invoked before run_portfolio_cycles.py."""
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd[1])  # record script path
            return _make_proc()

        run_example_cycles(_make_args(), subprocess_run=fake_run)
        assert calls[0] == _MAKE_MANIFEST_SCRIPT

    def test_calls_run_cycles_second(self):
        """run_portfolio_cycles.py is invoked after make_example_manifest.py."""
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd[1])
            return _make_proc()

        run_example_cycles(_make_args(), subprocess_run=fake_run)
        assert calls[1] == _RUN_CYCLES_SCRIPT

    def test_total_subprocess_calls(self):
        fake_run = MagicMock(return_value=_make_proc())
        run_example_cycles(_make_args(), subprocess_run=fake_run)
        assert fake_run.call_count == 2

    def test_returns_zero_on_success(self):
        fake_run = MagicMock(return_value=_make_proc(returncode=0))
        rc = run_example_cycles(_make_args(), subprocess_run=fake_run)
        assert rc == 0


# ---------------------------------------------------------------------------
# B. make_example_manifest failure short-circuits
# ---------------------------------------------------------------------------

class TestManifestFailure:
    def test_short_circuits_on_manifest_failure(self):
        """When make_example_manifest returns non-zero, run_portfolio_cycles is not called."""
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd[1])
            rc = 1 if "make_example_manifest" in cmd[1] else 0
            return _make_proc(returncode=rc, stderr="manifest error")

        rc = run_example_cycles(_make_args(), subprocess_run=fake_run)
        assert rc == 1
        assert len(calls) == 1
        assert "make_example_manifest" in calls[0]

    def test_propagates_manifest_exit_code(self):
        fake_run = MagicMock(return_value=_make_proc(returncode=2, stderr="err"))
        rc = run_example_cycles(_make_args(), subprocess_run=fake_run)
        assert rc == 2


# ---------------------------------------------------------------------------
# C. CLI arg forwarding
# ---------------------------------------------------------------------------

class TestArgForwarding:
    def _capture_cycles_cmd(self, **kwargs):
        """Return the argv list passed to run_portfolio_cycles.py."""
        captured = {}

        def fake_run(cmd, **run_kwargs):
            if "run_portfolio_cycles" in cmd[1]:
                captured["cmd"] = cmd
            return _make_proc()

        run_example_cycles(_make_args(**kwargs), subprocess_run=fake_run)
        return captured.get("cmd", [])

    def test_manifest_forwarded(self):
        cmd = self._capture_cycles_cmd(manifest="/abs/my_manifest.json")
        assert "--manifest" in cmd
        assert cmd[cmd.index("--manifest") + 1] == "/abs/my_manifest.json"

    def test_task_forwarded(self):
        cmd = self._capture_cycles_cmd(task="repo_insights_example")
        assert cmd[cmd.index("--task") + 1] == "repo_insights_example"

    def test_ledger_forwarded(self):
        cmd = self._capture_cycles_cmd(ledger="/abs/ledger.json")
        assert cmd[cmd.index("--ledger") + 1] == "/abs/ledger.json"

    def test_top_k_forwarded(self):
        cmd = self._capture_cycles_cmd(top_k=1)
        assert cmd[cmd.index("--top-k") + 1] == "1"

    def test_interval_forwarded(self):
        cmd = self._capture_cycles_cmd(interval=5)
        assert cmd[cmd.index("--interval") + 1] == "5"

    def test_output_forwarded(self):
        cmd = self._capture_cycles_cmd(output="my_cycle.json")
        assert cmd[cmd.index("--output") + 1] == "my_cycle.json"

    def test_archive_dir_forwarded(self):
        cmd = self._capture_cycles_cmd(archive_dir="my_archives")
        assert cmd[cmd.index("--archive-dir") + 1] == "my_archives"

    def test_cycles_forwarded(self):
        cmd = self._capture_cycles_cmd(cycles=3)
        assert "--cycles" in cmd
        assert cmd[cmd.index("--cycles") + 1] == "3"

    def test_cycles_none_omits_flag(self):
        """When cycles is None, --cycles is not passed (loop forever)."""
        cmd = self._capture_cycles_cmd(cycles=None)
        assert "--cycles" not in cmd


# ---------------------------------------------------------------------------
# D. Default argument values
# ---------------------------------------------------------------------------

class TestDefaults:
    def test_default_task(self):
        assert _DEFAULT_TASK == "health_probe_example"

    def test_default_top_k(self):
        assert _DEFAULT_TOP_K == 2

    def test_default_interval(self):
        assert _DEFAULT_INTERVAL == 0

    def test_default_cycles(self):
        assert _DEFAULT_CYCLES == 1

    def test_default_ledger_path_exists(self):
        assert Path(_DEFAULT_LEDGER).exists(), (
            f"Default ledger not found: {_DEFAULT_LEDGER}"
        )

    def test_default_manifest_path_under_repo_root(self):
        assert Path(_DEFAULT_MANIFEST).is_relative_to(_REPO_ROOT)

    def test_make_manifest_script_exists(self):
        assert Path(_MAKE_MANIFEST_SCRIPT).exists()

    def test_run_cycles_script_exists(self):
        assert Path(_RUN_CYCLES_SCRIPT).exists()


# ---------------------------------------------------------------------------
# E. Exit code propagation from run_portfolio_cycles
# ---------------------------------------------------------------------------

class TestExitCodePropagation:
    def test_propagates_cycles_exit_code(self):
        """Non-zero exit from run_portfolio_cycles is propagated."""
        call_count = [0]

        def fake_run(cmd, **kwargs):
            call_count[0] += 1
            # make_example_manifest succeeds; run_portfolio_cycles fails
            if call_count[0] == 1:
                return _make_proc(returncode=0)
            return _make_proc(returncode=1)

        rc = run_example_cycles(_make_args(), subprocess_run=fake_run)
        assert rc == 1

    def test_returns_zero_when_cycles_succeed(self):
        fake_run = MagicMock(return_value=_make_proc(returncode=0))
        rc = run_example_cycles(_make_args(), subprocess_run=fake_run)
        assert rc == 0
