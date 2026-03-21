# SPDX-License-Identifier: MIT
"""Tests for scripts/run_factory_trigger_loop.py."""

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_SCRIPT = _REPO_ROOT / "scripts" / "run_factory_trigger_loop.py"
_spec = importlib.util.spec_from_file_location("run_factory_trigger_loop", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)


def _make_args(tmp_path, **overrides):
    obj = SimpleNamespace(
        watch=None,
        portfolio_state="portfolio_state.json",
        ledger=None,
        policy=None,
        top_k=3,
        cycle_output=str(tmp_path / "autonomous_factory_cycle.json"),
        factory_state_output=str(tmp_path / "factory_state.json"),
        factory_journal_output=str(tmp_path / "factory_cycle_journal.jsonl"),
        trigger_state_output=str(tmp_path / "factory_trigger_state.json"),
        trigger_journal_output=str(tmp_path / "factory_trigger_journal.jsonl"),
        max_consecutive_failures=3,
        max_consecutive_idle_cycles=5,
        poll_seconds=0,
        max_polls=1,
        trigger_on_start=False,
        journal_no_change=False,
    )
    for k, v in overrides.items():
        setattr(obj, k, v)
    return obj


def _read_jsonl(path):
    return [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


# ---------------------------------------------------------------------------
# Tests 1–2: _changed_paths
# ---------------------------------------------------------------------------

def test_changed_paths_detects_modified_file():
    previous = {
        "/some/file.json": {"exists": True, "sha256": "aaa"},
    }
    current = {
        "/some/file.json": {"exists": True, "sha256": "bbb"},
    }
    result = _mod._changed_paths(previous, current)
    assert result == ["/some/file.json"]


def test_changed_paths_returns_empty_when_identical():
    snapshot = {
        "/some/file.json": {"exists": True, "sha256": "aaa"},
    }
    result = _mod._changed_paths(snapshot, snapshot)
    assert result == []


# ---------------------------------------------------------------------------
# Tests 3–4: _resolve_watch_paths
# ---------------------------------------------------------------------------

def test_resolve_watch_paths_uses_explicit_watch_arg():
    args = SimpleNamespace(watch=["/a/b.json", "/a/b.json", "/c/d.json"], ledger=None)
    result = _mod._resolve_watch_paths(args)
    # duplicates removed, order preserved
    assert result == ["/a/b.json", "/c/d.json"]


def test_resolve_watch_paths_appends_ledger_to_defaults():
    ledger_path = "/custom/ledger.json"
    args = SimpleNamespace(watch=None, ledger=ledger_path)
    result = _mod._resolve_watch_paths(args)
    assert ledger_path in result
    # ledger is after the two defaults
    assert result.index(ledger_path) == 2
    assert len(result) == 3


# ---------------------------------------------------------------------------
# Test 5: _build_daemon_cmd — optional ledger and policy flags
# ---------------------------------------------------------------------------

def test_build_daemon_cmd_includes_optional_ledger_and_policy(tmp_path):
    # With ledger and policy set: both flags present
    args_with = _make_args(tmp_path, ledger="/l/ledger.json", policy="/p/policy.json")
    cmd_with = _mod._build_daemon_cmd(args_with)
    assert "--ledger" in cmd_with
    assert "/l/ledger.json" in cmd_with
    assert "--policy" in cmd_with
    assert "/p/policy.json" in cmd_with

    # Without ledger and policy: neither flag present
    args_without = _make_args(tmp_path, ledger=None, policy=None)
    cmd_without = _mod._build_daemon_cmd(args_without)
    assert "--ledger" not in cmd_without
    assert "--policy" not in cmd_without


# ---------------------------------------------------------------------------
# Test 6: _update_state — last_triggered_at only set when triggered=True
# ---------------------------------------------------------------------------

def test_update_state_sets_triggered_at_only_when_triggered():
    base_state = {
        "last_checked_at": None,
        "last_triggered_at": None,
        "watched_paths": [],
        "signal_snapshot": {},
        "last_changed_paths": [],
        "last_daemon_returncode": None,
    }
    snapshot = {"/w/file.json": {"exists": True, "sha256": "abc"}}

    not_triggered = _mod._update_state(
        base_state, snapshot, changed_paths=[], daemon_rc=None, triggered=False
    )
    assert not_triggered["last_triggered_at"] is None
    assert not_triggered["last_checked_at"] is not None

    was_triggered = _mod._update_state(
        base_state, snapshot, changed_paths=["/w/file.json"], daemon_rc=0, triggered=True
    )
    assert was_triggered["last_triggered_at"] is not None
    assert was_triggered["last_triggered_at"] == was_triggered["last_checked_at"]


# ---------------------------------------------------------------------------
# Test 7: loop — no file changes → state written, journal NOT created
# ---------------------------------------------------------------------------

def test_run_factory_trigger_loop_no_change_writes_state_no_journal_entry(
    tmp_path, monkeypatch
):
    fixed_snapshot = {str(tmp_path / "watch.json"): {"exists": False, "sha256": None}}

    monkeypatch.setattr(_mod, "_build_signal_snapshot", lambda paths: fixed_snapshot)

    args = _make_args(
        tmp_path,
        trigger_on_start=False,
        max_polls=1,
        journal_no_change=False,
    )

    # Pre-seed state so previous_snapshot == fixed_snapshot on first poll.
    seed_state = _mod._default_state()
    seed_state["signal_snapshot"] = fixed_snapshot
    from factory_runtime import write_json
    write_json(Path(args.trigger_state_output), seed_state)

    rc = _mod.run_factory_trigger_loop(args)

    assert rc == 0

    state_path = Path(args.trigger_state_output)
    assert state_path.exists(), "trigger state file must be written"

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["last_checked_at"] is not None
    assert state["last_triggered_at"] is None

    journal_path = Path(args.trigger_journal_output)
    assert not journal_path.exists(), "journal must NOT be created when no change and journal_no_change=False"


# ---------------------------------------------------------------------------
# Test 8: loop — trigger_on_start=True → daemon dispatched, journal entry written
# ---------------------------------------------------------------------------

def test_run_factory_trigger_loop_trigger_on_start_dispatches_daemon(
    tmp_path, monkeypatch
):
    fixed_snapshot = {str(tmp_path / "watch.json"): {"exists": False, "sha256": None}}

    monkeypatch.setattr(_mod, "_build_signal_snapshot", lambda paths: fixed_snapshot)

    run_calls = []

    def fake_subprocess_run(cmd, check=False):
        run_calls.append(cmd)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(_mod.subprocess, "run", fake_subprocess_run)

    args = _make_args(
        tmp_path,
        trigger_on_start=True,
        max_polls=1,
    )

    rc = _mod.run_factory_trigger_loop(args)

    assert rc == 0
    assert len(run_calls) == 1, "subprocess.run must be called exactly once"

    journal_path = Path(args.trigger_journal_output)
    assert journal_path.exists(), "journal file must be created after trigger"

    entries = _read_jsonl(journal_path)
    assert len(entries) == 1
    assert entries[0]["status"] == "triggered"
    assert entries[0]["daemon_returncode"] == 0
