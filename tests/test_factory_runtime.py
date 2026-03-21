# SPDX-License-Identifier: MIT
"""Targeted tests for factory_runtime.py helpers."""

import json
from datetime import datetime

import pytest

from factory_runtime import (
    extract_factory_status,
    extract_learning_applied,
    extract_repair_applied,
    extract_risk_level,
    initial_factory_state,
    read_json,
    reasons_indicate_idle,
    should_stop_factory,
    update_factory_state,
    utcnow_iso,
)


# ---------------------------------------------------------------------------
# utcnow_iso
# ---------------------------------------------------------------------------


def test_utcnow_iso_returns_iso_format():
    result = utcnow_iso()
    dt = datetime.fromisoformat(result)
    assert dt.tzinfo is not None


# ---------------------------------------------------------------------------
# read_json
# ---------------------------------------------------------------------------


def test_read_json_missing_returns_default(tmp_path):
    missing = tmp_path / "does_not_exist.json"
    default = {"sentinel": True}
    assert read_json(str(missing), default) == default


def test_read_json_existing_returns_parsed(tmp_path):
    p = tmp_path / "data.json"
    payload = {"key": "value", "num": 42}
    p.write_text(json.dumps(payload), encoding="utf-8")
    assert read_json(str(p), {}) == payload


# ---------------------------------------------------------------------------
# initial_factory_state
# ---------------------------------------------------------------------------


def test_initial_factory_state_shape():
    state = initial_factory_state()
    expected_keys = {
        "cycle_count",
        "last_cycle_status",
        "last_decision",
        "last_risk_level",
        "last_learning_applied",
        "consecutive_idle_cycles",
        "consecutive_failed_cycles",
        "last_updated_at",
    }
    assert set(state.keys()) == expected_keys
    assert state["cycle_count"] == 0
    assert state["last_cycle_status"] is None
    assert state["last_decision"] is None
    assert state["last_risk_level"] is None
    assert state["last_learning_applied"] is False
    assert state["consecutive_idle_cycles"] == 0
    assert state["consecutive_failed_cycles"] == 0
    assert state["last_updated_at"] is None


# ---------------------------------------------------------------------------
# extract_risk_level
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "artifact, expected",
    [
        # evaluation.risk_level present — returned directly
        ({"evaluation": {"risk_level": "high"}}, "high"),
        # evaluation absent, cycle_result.risk_level present
        ({"cycle_result": {"risk_level": "medium"}}, "medium"),
        # both absent, baseline_evaluation.risk_level present
        ({"cycle_result": {"baseline_evaluation": {"risk_level": "low"}}}, "low"),
        # all absent — None
        ({}, None),
    ],
)
def test_extract_risk_level_priority_and_none(artifact, expected):
    assert extract_risk_level(artifact) == expected


# ---------------------------------------------------------------------------
# extract_learning_applied
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "artifact, expected",
    [
        # top-level learning_update.applied=True
        ({"learning_update": {"applied": True}}, True),
        # nested cycle_result.learning_update.applied=True
        ({"cycle_result": {"learning_update": {"applied": True}}}, True),
        # both absent
        ({}, False),
    ],
)
def test_extract_learning_applied_branches(artifact, expected):
    assert extract_learning_applied(artifact) == expected


# ---------------------------------------------------------------------------
# extract_repair_applied
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "artifact, expected",
    [
        # auto_repair_applied=True
        ({"cycle_result": {"auto_repair_applied": True}}, True),
        # repair_success=True
        ({"cycle_result": {"repair_success": True}}, True),
        # auto_repair_cycle.repair_success=True
        ({"cycle_result": {"auto_repair_cycle": {"repair_success": True}}}, True),
    ],
)
def test_extract_repair_applied_three_paths(artifact, expected):
    assert extract_repair_applied(artifact) == expected


# ---------------------------------------------------------------------------
# reasons_indicate_idle
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "reasons",
    [
        ["no actions available"],
        ["planner produced no actions"],
        ["window is empty"],
        ["no action window found"],
    ],
)
def test_reasons_indicate_idle_trigger_phrases(reasons):
    assert reasons_indicate_idle(reasons) is True


def test_reasons_indicate_idle_no_match_and_none():
    assert reasons_indicate_idle(["everything is fine"]) is False
    assert reasons_indicate_idle(None) is False


# ---------------------------------------------------------------------------
# extract_factory_status
# ---------------------------------------------------------------------------


def test_extract_factory_status_error_branch():
    # error kwarg always → "failed"
    assert extract_factory_status({}, error="boom") == "failed"
    assert extract_factory_status({"decision": {"action": "idle"}}, error="x") == "failed"


def test_extract_factory_status_idle_branches():
    # decision.action == "idle" → "idle"
    assert extract_factory_status({"decision": {"action": "idle"}}) == "idle"
    # cycle_result.idle=True with a non-idle decision → "idle"
    artifact = {"decision": {"action": "run"}, "cycle_result": {"idle": True}}
    assert extract_factory_status(artifact) == "idle"


def test_extract_factory_status_repair_only():
    # repair_only + repair_success=True → "completed"
    artifact_ok = {
        "decision": {"action": "repair_only"},
        "cycle_result": {"repair_success": True},
    }
    assert extract_factory_status(artifact_ok) == "completed"

    # repair_only + repair_success absent → "failed"
    artifact_fail = {
        "decision": {"action": "repair_only"},
        "cycle_result": {},
    }
    assert extract_factory_status(artifact_fail) == "failed"


def test_extract_factory_status_abort_reason():
    # cycle_result.abort_reason set, non-repair decision → "failed"
    artifact = {
        "decision": {"action": "run"},
        "cycle_result": {"abort_reason": "timeout"},
    }
    assert extract_factory_status(artifact) == "failed"


# ---------------------------------------------------------------------------
# update_factory_state
# ---------------------------------------------------------------------------


def test_update_factory_state_counter_logic():
    base = initial_factory_state()
    base["consecutive_idle_cycles"] = 2
    base["consecutive_failed_cycles"] = 1

    # status="idle" increments idle, resets failed
    s_idle = update_factory_state(base, {}, status="idle")
    assert s_idle["consecutive_idle_cycles"] == 3
    assert s_idle["consecutive_failed_cycles"] == 0

    # status="failed" increments failed, resets idle
    s_fail = update_factory_state(base, {}, status="failed")
    assert s_fail["consecutive_failed_cycles"] == 2
    assert s_fail["consecutive_idle_cycles"] == 0

    # status="completed" resets both
    s_done = update_factory_state(base, {}, status="completed")
    assert s_done["consecutive_idle_cycles"] == 0
    assert s_done["consecutive_failed_cycles"] == 0


# ---------------------------------------------------------------------------
# should_stop_factory
# ---------------------------------------------------------------------------


def test_should_stop_factory_all_branches():
    # consecutive_failed_cycles >= max_failures → stop
    state_fail = {"consecutive_failed_cycles": 3, "consecutive_idle_cycles": 0}
    stopped, reason = should_stop_factory(state_fail, max_failures=3, max_idle_cycles=10)
    assert stopped is True
    assert reason == "max_consecutive_failures_reached"

    # consecutive_idle_cycles >= max_idle_cycles → stop
    state_idle = {"consecutive_failed_cycles": 0, "consecutive_idle_cycles": 5}
    stopped, reason = should_stop_factory(state_idle, max_failures=10, max_idle_cycles=5)
    assert stopped is True
    assert reason == "max_consecutive_idle_cycles_reached"

    # both below threshold → no stop
    state_ok = {"consecutive_failed_cycles": 1, "consecutive_idle_cycles": 2}
    stopped, reason = should_stop_factory(state_ok, max_failures=5, max_idle_cycles=5)
    assert stopped is False
    assert reason is None
