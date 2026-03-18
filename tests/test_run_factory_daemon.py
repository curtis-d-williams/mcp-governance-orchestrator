# SPDX-License-Identifier: MIT
"""Tests for scripts/run_factory_daemon.py."""

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_SCRIPT = _REPO_ROOT / "scripts" / "run_factory_daemon.py"
_spec = importlib.util.spec_from_file_location("run_factory_daemon", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)


def _make_args(tmp_path, **overrides):
    obj = SimpleNamespace(
        portfolio_state="portfolio_state.json",
        ledger="action_effectiveness_ledger.json",
        policy="planner_policy.json",
        top_k=3,
        cycle_output=str(tmp_path / "autonomous_factory_cycle.json"),
        state_output=str(tmp_path / "factory_state.json"),
        journal_output=str(tmp_path / "factory_cycle_journal.jsonl"),
        max_consecutive_failures=3,
        max_consecutive_idle_cycles=5,
        sleep_seconds=0,
        max_cycles=1,
        capability_ledger_output=None,
    )
    for k, v in overrides.items():
        setattr(obj, k, v)
    return obj


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _read_jsonl(path):
    return [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_run_factory_daemon_writes_state_and_journal_for_completed_cycle(tmp_path, monkeypatch):
    artifact = {
        "decision": {
            "action": "governed_run",
            "reason": "planner_acceptable_risk",
            "repair_enabled": True,
            "learning_enabled": True,
        },
        "evaluation": {
            "risk_level": "low_risk",
            "reasons": [],
        },
        "cycle_result": {
            "result": {"summary": {"repos_failed": 0}},
            "learning_update": {"applied": True},
        },
        "status": "completed",
    }

    monkeypatch.setattr(_mod, "run_autonomous_factory_cycle", lambda **kwargs: artifact)

    rc = _mod.run_factory_daemon(_make_args(tmp_path))

    assert rc == 0

    state = _read_json(tmp_path / "factory_state.json")
    assert state["cycle_count"] == 1
    assert state["last_cycle_status"] == "completed"
    assert state["last_decision"] == "governed_run"
    assert state["last_risk_level"] == "low_risk"
    assert state["last_learning_applied"] is True
    assert state["consecutive_idle_cycles"] == 0
    assert state["consecutive_failed_cycles"] == 0
    assert state["last_updated_at"]

    journal = _read_jsonl(tmp_path / "factory_cycle_journal.jsonl")
    assert len(journal) == 1
    assert journal[0]["decision"] == "governed_run"
    assert journal[0]["risk_level"] == "low_risk"
    assert journal[0]["learning_applied"] is True
    assert journal[0]["repair_applied"] is False
    assert journal[0]["status"] == "completed"
    assert journal[0]["timestamp"]


def test_run_factory_daemon_classifies_empty_window_as_idle(tmp_path, monkeypatch):
    artifact = {
        "decision": {
            "action": "repair_only",
            "reason": "planner_high_risk",
            "repair_enabled": True,
            "learning_enabled": False,
        },
        "evaluation": {
            "risk_level": "high_risk",
            "reasons": ["planner produced no actions"],
        },
        "cycle_result": {
            "baseline_evaluation": {
                "risk_level": "high_risk",
                "reasons": ["planner produced no actions"],
            },
            "repair_attempted": True,
            "repair_success": False,
            "status": "repair_unavailable",
        },
        "status": "completed",
    }

    monkeypatch.setattr(_mod, "run_autonomous_factory_cycle", lambda **kwargs: artifact)

    rc = _mod.run_factory_daemon(_make_args(tmp_path))

    assert rc == 0

    state = _read_json(tmp_path / "factory_state.json")
    assert state["last_cycle_status"] == "idle"
    assert state["consecutive_idle_cycles"] == 1
    assert state["consecutive_failed_cycles"] == 0

    journal = _read_jsonl(tmp_path / "factory_cycle_journal.jsonl")
    assert journal[0]["status"] == "idle"
    assert journal[0]["decision"] == "repair_only"
    assert journal[0]["risk_level"] == "high_risk"


def test_run_factory_daemon_stops_after_consecutive_failures(tmp_path, monkeypatch):
    artifact = {
        "decision": {
            "action": "repair_only",
            "reason": "planner_high_risk",
            "repair_enabled": True,
            "learning_enabled": False,
        },
        "evaluation": {
            "risk_level": "high_risk",
            "reasons": ["persistent collision risk"],
        },
        "cycle_result": {
            "abort_reason": "high_risk_persistent",
        },
        "status": "completed",
    }

    monkeypatch.setattr(_mod, "run_autonomous_factory_cycle", lambda **kwargs: artifact)
    monkeypatch.setattr(_mod.time, "sleep", lambda *_args, **_kwargs: None)

    rc = _mod.run_factory_daemon(
        _make_args(
            tmp_path,
            max_cycles=None,
            max_consecutive_failures=2,
            max_consecutive_idle_cycles=99,
        )
    )

    assert rc == 1

    state = _read_json(tmp_path / "factory_state.json")
    assert state["cycle_count"] == 2
    assert state["last_cycle_status"] == "failed"
    assert state["consecutive_failed_cycles"] == 2
    assert state["consecutive_idle_cycles"] == 0

    journal = _read_jsonl(tmp_path / "factory_cycle_journal.jsonl")
    assert len(journal) == 2
    assert [entry["status"] for entry in journal] == ["failed", "failed"]


def test_extract_status_treats_unsuccessful_repair_only_cycle_as_failed():
    artifact = {
        "decision": {"action": "repair_only"},
        "evaluation": {"risk_level": "high_risk", "reasons": ["collision risk remains high"]},
        "cycle_result": {
            "repair_attempted": True,
            "repair_success": False,
            "status": "repair_no_improvement",
        },
        "status": "completed",
    }

    assert _mod._extract_status(artifact) == "failed"


def test_run_factory_daemon_passes_capability_ledger_output_to_cycle(tmp_path, monkeypatch):
    received = {}

    def fake_cycle(**kwargs):
        received.update(kwargs)
        return {
            "decision": {"action": "governed_run", "reason": "planner_acceptable_risk",
                         "repair_enabled": True, "learning_enabled": True},
            "evaluation": {"risk_level": "low_risk", "reasons": []},
            "cycle_result": {},
            "status": "completed",
        }

    monkeypatch.setattr(_mod, "run_autonomous_factory_cycle", fake_cycle)

    ledger_path = str(tmp_path / "capability_ledger.json")
    args = _make_args(tmp_path, capability_ledger_output=ledger_path)
    _mod.run_factory_daemon(args)

    assert received["capability_ledger"] == ledger_path
    assert received["capability_ledger_output"] == ledger_path


def test_extract_repair_applied_detects_nested_auto_repair_cycle():
    artifact = {
        "cycle_result": {
            "auto_repair_cycle": {
                "repair_success": True,
            }
        }
    }

    assert _mod._extract_repair_applied(artifact) is True
