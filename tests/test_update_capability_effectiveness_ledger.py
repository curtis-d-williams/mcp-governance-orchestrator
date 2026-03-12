# SPDX-License-Identifier: MIT
"""Tests for scripts/update_capability_effectiveness_ledger.py."""

import importlib.util
import json
import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_SCRIPT = _REPO_ROOT / "scripts" / "update_capability_effectiveness_ledger.py"
_spec = importlib.util.spec_from_file_location("update_capability_effectiveness_ledger", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

update_capability_effectiveness_ledger = _mod.update_capability_effectiveness_ledger


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_creates_new_capability_entry(tmp_path):
    ledger = tmp_path / "capability_ledger.json"
    cycle = tmp_path / "cycle.json"

    cycle.write_text(json.dumps({
        "capability_effectiveness_ledger": {
            "capabilities": {
                "snowflake_data_access": {
                    "artifact_kind": "data_connector",
                    "failed_syntheses": 0,
                    "successful_syntheses": 1,
                    "total_syntheses": 1,
                    "last_synthesis_source": "planner_request",
                    "last_synthesis_status": "ok",
                }
            }
        }
    }), encoding="utf-8")

    update_capability_effectiveness_ledger(str(ledger), str(cycle))

    result = _read_json(ledger)

    assert result == {
        "capabilities": {
            "snowflake_data_access": {
                "artifact_kind": "data_connector",
                "failed_syntheses": 0,
                "successful_syntheses": 1,
                "total_syntheses": 1,
                "last_synthesis_source": "planner_request",
                "last_synthesis_status": "ok",
            }
        }
    }


def test_merges_existing_capability(tmp_path):
    ledger = tmp_path / "capability_ledger.json"
    cycle = tmp_path / "cycle.json"

    ledger.write_text(json.dumps({
        "capabilities": {
            "snowflake_data_access": {
                "artifact_kind": "data_connector",
                "failed_syntheses": 1,
                "successful_syntheses": 2,
                "total_syntheses": 3,
                "last_synthesis_source": "planner_request",
                "last_synthesis_status": "ok",
            }
        }
    }), encoding="utf-8")

    cycle.write_text(json.dumps({
        "capability_effectiveness_ledger": {
            "capabilities": {
                "snowflake_data_access": {
                    "artifact_kind": "data_connector",
                    "failed_syntheses": 0,
                    "successful_syntheses": 1,
                    "total_syntheses": 1,
                    "last_synthesis_source": "portfolio_gap",
                    "last_synthesis_status": "ok",
                }
            }
        }
    }), encoding="utf-8")

    update_capability_effectiveness_ledger(str(ledger), str(cycle))

    result = _read_json(ledger)

    assert result["capabilities"]["snowflake_data_access"]["total_syntheses"] == 4
    assert result["capabilities"]["snowflake_data_access"]["successful_syntheses"] == 3
    assert result["capabilities"]["snowflake_data_access"]["failed_syntheses"] == 1
    assert result["capabilities"]["snowflake_data_access"]["last_synthesis_source"] == "portfolio_gap"


def test_handles_missing_cycle_capability_section(tmp_path):
    ledger = tmp_path / "capability_ledger.json"
    cycle = tmp_path / "cycle.json"

    cycle.write_text("{}", encoding="utf-8")

    update_capability_effectiveness_ledger(str(ledger), str(cycle))

    result = _read_json(ledger)

    assert result == {"capabilities": {}}


def test_deterministic_sorted_output(tmp_path):
    ledger = tmp_path / "capability_ledger.json"
    cycle = tmp_path / "cycle.json"

    cycle.write_text(json.dumps({
        "capability_effectiveness_ledger": {
            "capabilities": {
                "z_cap": {
                    "artifact_kind": "connector",
                    "failed_syntheses": 0,
                    "successful_syntheses": 1,
                    "total_syntheses": 1,
                },
                "a_cap": {
                    "artifact_kind": "connector",
                    "failed_syntheses": 0,
                    "successful_syntheses": 1,
                    "total_syntheses": 1,
                },
            }
        }
    }), encoding="utf-8")

    update_capability_effectiveness_ledger(str(ledger), str(cycle))

    data = _read_json(ledger)

    assert list(data["capabilities"].keys()) == ["a_cap", "z_cap"]
