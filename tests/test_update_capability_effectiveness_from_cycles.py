# SPDX-License-Identifier: MIT
"""Tests for scripts/update_capability_effectiveness_from_cycles.py."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_SCRIPT = _REPO_ROOT / "scripts" / "update_capability_effectiveness_from_cycles.py"
_spec = importlib.util.spec_from_file_location(
    "update_capability_effectiveness_from_cycles", _SCRIPT
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

update_capability_effectiveness_from_cycles = _mod.update_capability_effectiveness_from_cycles
_aggregate = _mod._aggregate


def _history(cycles):
    return {"cycles": cycles}


def _cycle(capabilities=None):
    return {
        "capability_effectiveness_ledger": {
            "capabilities": capabilities or {}
        }
    }


def _event_cycle(
    capability="snowflake_data_access",
    artifact_kind="data_connector",
    status="ok",
    source="planner_request",
    generated_repo="generated_data_connector_snowflake",
):
    return {
        "cycle_result": {
            "synthesis_event": {
                "capability": capability,
                "artifact_kind": artifact_kind,
                "status": status,
                "source": source,
                "generated_repo": generated_repo,
            }
        }
    }


def _entry(
    artifact_kind="data_connector",
    total_syntheses=1,
    successful_syntheses=1,
    failed_syntheses=0,
    last_synthesis_source="planner_request",
    last_synthesis_status="ok",
):
    return {
        "artifact_kind": artifact_kind,
        "total_syntheses": total_syntheses,
        "successful_syntheses": successful_syntheses,
        "failed_syntheses": failed_syntheses,
        "last_synthesis_source": last_synthesis_source,
        "last_synthesis_status": last_synthesis_status,
    }


def _write_history(tmp_path, cycles, name="cycle_history_with_capabilities.json"):
    p = tmp_path / name
    p.write_text(json.dumps(_history(cycles)) + "\n", encoding="utf-8")
    return p


class TestAggregateLogic:
    def test_empty_cycles(self):
        assert _aggregate([]) == {}

    def test_cycle_missing_capability_ledger_skips_gracefully(self):
        assert _aggregate([{}]) == {}

    def test_cycle_with_empty_capabilities(self):
        assert _aggregate([_cycle({})]) == {}

    def test_single_capability_ok(self):
        capabilities = {
            "snowflake_data_access": _entry(),
        }
        aggregated = _aggregate([_cycle(capabilities)])
        assert aggregated["snowflake_data_access"] == {
            "artifact_kind": "data_connector",
            "failed_syntheses": 0,
            "last_synthesis_source": "planner_request",
            "last_synthesis_status": "ok",
            "successful_evolved_syntheses": 0,
            "successful_syntheses": 1,
            "total_syntheses": 1,
        }

    def test_accumulates_same_capability_across_cycles(self):
        aggregated = _aggregate([
            _cycle({"snowflake_data_access": _entry(successful_syntheses=1)}),
            _cycle({"snowflake_data_access": _entry(successful_syntheses=2, total_syntheses=2)}),
        ])
        assert aggregated["snowflake_data_access"]["successful_syntheses"] == 3
        assert aggregated["snowflake_data_access"]["total_syntheses"] == 3

    def test_accumulates_failures(self):
        aggregated = _aggregate([
            _cycle({"snowflake_data_access": _entry(successful_syntheses=0, failed_syntheses=1, total_syntheses=1, last_synthesis_status="error")}),
            _cycle({"snowflake_data_access": _entry(successful_syntheses=0, failed_syntheses=2, total_syntheses=2, last_synthesis_status="error")}),
        ])
        assert aggregated["snowflake_data_access"]["failed_syntheses"] == 3
        assert aggregated["snowflake_data_access"]["successful_syntheses"] == 0
        assert aggregated["snowflake_data_access"]["total_syntheses"] == 3
        assert aggregated["snowflake_data_access"]["last_synthesis_status"] == "error"

    def test_tracks_most_recent_status_and_source(self):
        aggregated = _aggregate([
            _cycle({"snowflake_data_access": _entry(last_synthesis_source="planner_request", last_synthesis_status="ok")}),
            _cycle({"snowflake_data_access": _entry(last_synthesis_source="portfolio_gap", last_synthesis_status="error", successful_syntheses=0, failed_syntheses=1, total_syntheses=1)}),
        ])
        assert aggregated["snowflake_data_access"]["last_synthesis_source"] == "portfolio_gap"
        assert aggregated["snowflake_data_access"]["last_synthesis_status"] == "error"

    def test_multiple_capabilities(self):
        aggregated = _aggregate([
            _cycle({
                "snowflake_data_access": _entry(),
                "slack_workspace_access": _entry(
                    artifact_kind="agent_adapter",
                    last_synthesis_source="portfolio_gap",
                ),
            }),
        ])
        assert aggregated["snowflake_data_access"]["artifact_kind"] == "data_connector"
        assert aggregated["slack_workspace_access"]["artifact_kind"] == "agent_adapter"

    def test_missing_numeric_fields_default_to_zero(self):
        aggregated = _aggregate([
            _cycle({
                "snowflake_data_access": {
                    "artifact_kind": "data_connector",
                    "last_synthesis_source": "planner_request",
                    "last_synthesis_status": "ok",
                }
            })
        ])
        assert aggregated["snowflake_data_access"]["successful_syntheses"] == 0
        assert aggregated["snowflake_data_access"]["failed_syntheses"] == 0
        assert aggregated["snowflake_data_access"]["total_syntheses"] == 0


    def test_prefers_synthesis_event_when_present(self):
        aggregated = _aggregate([
            {
                "cycle_result": {
                    "synthesis_event": {
                        "capability": "snowflake_data_access",
                        "artifact_kind": "data_connector",
                        "status": "ok",
                        "source": "planner_request",
                        "generated_repo": "generated_data_connector_snowflake",
                    }
                },
                "capability_effectiveness_ledger": {
                    "capabilities": {
                        "snowflake_data_access": _entry(
                            successful_syntheses=99,
                            total_syntheses=99,
                        )
                    }
                },
            }
        ])
        assert aggregated["snowflake_data_access"]["successful_syntheses"] == 1
        assert aggregated["snowflake_data_access"]["failed_syntheses"] == 0
        assert aggregated["snowflake_data_access"]["total_syntheses"] == 1
        assert aggregated["snowflake_data_access"]["last_synthesis_source"] == "planner_request"
        assert aggregated["snowflake_data_access"]["last_synthesis_status"] == "ok"

    def test_aggregates_ok_synthesis_event(self):
        aggregated = _aggregate([
            _event_cycle(),
        ])
        assert aggregated["snowflake_data_access"] == {
            "artifact_kind": "data_connector",
            "failed_syntheses": 0,
            "last_synthesis_source": "planner_request",
            "last_synthesis_status": "ok",
            "last_synthesis_used_evolution": False,
            "successful_evolved_syntheses": 0,
            "successful_syntheses": 1,
            "total_syntheses": 1,
        }

    def test_aggregates_error_synthesis_event(self):
        aggregated = _aggregate([
            _event_cycle(status="error"),
        ])
        assert aggregated["snowflake_data_access"]["successful_syntheses"] == 0
        assert aggregated["snowflake_data_access"]["failed_syntheses"] == 1
        assert aggregated["snowflake_data_access"]["total_syntheses"] == 1
        assert aggregated["snowflake_data_access"]["last_synthesis_status"] == "error"

    def test_falls_back_to_legacy_capability_ledger_when_event_missing(self):
        aggregated = _aggregate([
            _cycle({"snowflake_data_access": _entry()}),
        ])
        assert aggregated["snowflake_data_access"]["successful_syntheses"] == 1
        assert aggregated["snowflake_data_access"]["total_syntheses"] == 1

    def test_no_op_synthesis_event_is_not_recorded(self):
        aggregated = _aggregate([
            _event_cycle(
                capability="none",
                artifact_kind="none",
                status="no_op",
                source="none",
            )
        ])
        assert aggregated == {}

    def test_idle_cycle_with_null_cycle_result_produces_empty_aggregation(self):
        assert _aggregate([{"cycle_result": None}]) == {}


class TestLedgerCreation:
    def test_returns_zero(self, tmp_path):
        h = _write_history(tmp_path, [_cycle({"snowflake_data_access": _entry()})])
        out = tmp_path / "capability_ledger.json"
        assert update_capability_effectiveness_from_cycles(str(h), str(out)) == 0

    def test_output_file_created(self, tmp_path):
        h = _write_history(tmp_path, [_cycle({"snowflake_data_access": _entry()})])
        out = tmp_path / "capability_ledger.json"
        update_capability_effectiveness_from_cycles(str(h), str(out))
        assert out.exists()

    def test_output_is_valid_json(self, tmp_path):
        h = _write_history(tmp_path, [_cycle({"snowflake_data_access": _entry()})])
        out = tmp_path / "capability_ledger.json"
        update_capability_effectiveness_from_cycles(str(h), str(out))
        data = json.loads(out.read_text())
        assert isinstance(data, dict)

    def test_output_has_trailing_newline(self, tmp_path):
        h = _write_history(tmp_path, [_cycle({"snowflake_data_access": _entry()})])
        out = tmp_path / "capability_ledger.json"
        update_capability_effectiveness_from_cycles(str(h), str(out))
        assert out.read_text(encoding="utf-8").endswith("\n")

    def test_output_has_capabilities_key(self, tmp_path):
        h = _write_history(tmp_path, [_cycle({"snowflake_data_access": _entry()})])
        out = tmp_path / "capability_ledger.json"
        update_capability_effectiveness_from_cycles(str(h), str(out))
        data = json.loads(out.read_text())
        assert "capabilities" in data

    def test_empty_history_produces_empty_capabilities(self, tmp_path):
        h = _write_history(tmp_path, [])
        out = tmp_path / "capability_ledger.json"
        update_capability_effectiveness_from_cycles(str(h), str(out))
        data = json.loads(out.read_text())
        assert data["capabilities"] == {}

    def test_creates_parent_dirs(self, tmp_path):
        h = _write_history(tmp_path, [_cycle({"snowflake_data_access": _entry()})])
        out = tmp_path / "sub" / "capability_ledger.json"
        assert update_capability_effectiveness_from_cycles(str(h), str(out)) == 0
        assert out.exists()

    def test_keys_sorted_by_capability(self, tmp_path):
        h = _write_history(tmp_path, [
            _cycle({"zzz_capability": _entry()}),
            _cycle({"aaa_capability": _entry()}),
        ])
        out = tmp_path / "capability_ledger.json"
        update_capability_effectiveness_from_cycles(str(h), str(out))
        data = json.loads(out.read_text())
        assert list(data["capabilities"].keys()) == ["aaa_capability", "zzz_capability"]


class TestIdempotency:
    def test_repeat_runs_identical(self, tmp_path):
        h = _write_history(tmp_path, [_cycle({"snowflake_data_access": _entry()})])
        out = tmp_path / "capability_ledger.json"
        update_capability_effectiveness_from_cycles(str(h), str(out))
        text1 = out.read_text(encoding="utf-8")
        update_capability_effectiveness_from_cycles(str(h), str(out))
        text2 = out.read_text(encoding="utf-8")
        assert text1 == text2


class TestErrorCases:
    def test_returns_one_when_history_missing(self, tmp_path):
        out = tmp_path / "capability_ledger.json"
        assert update_capability_effectiveness_from_cycles(
            str(tmp_path / "missing.json"),
            str(out),
        ) == 1

    def test_returns_one_when_history_bad_json(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("not json", encoding="utf-8")
        out = tmp_path / "capability_ledger.json"
        assert update_capability_effectiveness_from_cycles(str(bad), str(out)) == 1

    def test_returns_one_when_cycles_missing(self, tmp_path):
        p = tmp_path / "history.json"
        p.write_text(json.dumps({"not_cycles": []}) + "\n", encoding="utf-8")
        out = tmp_path / "capability_ledger.json"
        assert update_capability_effectiveness_from_cycles(str(p), str(out)) == 1

    def test_returns_one_when_cycles_not_list(self, tmp_path):
        p = tmp_path / "history.json"
        p.write_text(json.dumps({"cycles": "bad"}) + "\n", encoding="utf-8")
        out = tmp_path / "capability_ledger.json"
        assert update_capability_effectiveness_from_cycles(str(p), str(out)) == 1


class TestComparisonStatus:
    def test_comparison_status_error_propagated_to_ledger(self):
        aggregated = _aggregate([
            {
                "cycle_result": {
                    "synthesis_event": {
                        "capability": "snowflake_data_access",
                        "artifact_kind": "data_connector",
                        "status": "ok",
                        "source": "planner_request",
                        "comparison_status": "error",
                    }
                }
            }
        ])
        assert aggregated["snowflake_data_access"]["last_comparison_status"] == "error"
