# SPDX-License-Identifier: MIT

import json
import importlib.util
from pathlib import Path


_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "run_mapping_repair_cycle.py"
_SPEC = importlib.util.spec_from_file_location("run_mapping_repair_cycle", _SCRIPT)
_mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_mod)

run_mapping_repair_cycle = _mod.run_mapping_repair_cycle
_default_override_output = _mod._default_override_output


class TestDefaultOverrideOutput:
    def test_appends_override_suffix(self, tmp_path):
        out = tmp_path / "cycle.json"
        got = _default_override_output(str(out))
        assert got.endswith("cycle_override.json")


class TestRunMappingRepairCycle:
    def test_already_low_risk_skips_repair(self, monkeypatch, tmp_path):
        baseline = {
            "risk_level": "low_risk",
            "collision_ratio": 0.0,
            "unique_tasks": 3,
        }

        def fake_evaluate(**kwargs):
            return dict(baseline)

        def fake_propose(**kwargs):
            raise AssertionError("repair should not be proposed for low_risk baseline")

        monkeypatch.setattr(_mod, "evaluate_planner_config", fake_evaluate)
        monkeypatch.setattr(_mod, "propose_mapping_repair", fake_propose)

        output_path = tmp_path / "cycle.json"
        result = run_mapping_repair_cycle(
            portfolio_state_path="state.json",
            ledger_path="ledger.json",
            policy_path="policy.json",
            output_path=str(output_path),
        )

        assert result["status"] == "already_low_risk"
        assert result["repair_attempted"] is False
        assert result["repair_success"] is False
        assert result["repair_proposal"] is None
        assert result["override_artifact"] is None
        assert result["repaired_evaluation"] is None

        written = json.loads(output_path.read_text(encoding="utf-8"))
        assert written["status"] == "already_low_risk"

    def test_repair_validated_writes_override_and_repaired_eval(self, monkeypatch, tmp_path):
        baseline = {
            "risk_level": "moderate_risk",
            "collision_ratio": 0.333333,
            "unique_tasks": 2,
        }
        repaired = {
            "risk_level": "low_risk",
            "collision_ratio": 0.0,
            "unique_tasks": 3,
        }
        proposal = {
            "repair_needed": True,
            "proposed_mapping_override": {
                "refresh_repo_health": "artifact_audit_example",
                "recover_failed_workflow": "failure_recovery_example",
                "regenerate_missing_artifact": "build_portfolio_dashboard",
            },
            "reasons": ["repair proposed"],
        }

        calls = {"evaluate": []}

        def fake_evaluate(**kwargs):
            calls["evaluate"].append(dict(kwargs))
            if kwargs["mapping_override_path"] is None:
                return dict(baseline)
            return dict(repaired)

        def fake_propose(**kwargs):
            return dict(proposal)

        monkeypatch.setattr(_mod, "evaluate_planner_config", fake_evaluate)
        monkeypatch.setattr(_mod, "propose_mapping_repair", fake_propose)

        output_path = tmp_path / "cycle.json"
        override_path = tmp_path / "override.json"

        result = run_mapping_repair_cycle(
            portfolio_state_path="state.json",
            ledger_path="ledger.json",
            policy_path="policy.json",
            output_path=str(output_path),
            override_output_path=str(override_path),
        )

        assert result["status"] == "repair_validated"
        assert result["repair_attempted"] is True
        assert result["repair_success"] is True
        assert result["repair_proposal"] == proposal
        assert result["override_artifact"] == proposal["proposed_mapping_override"]
        assert result["override_artifact_path"] == str(override_path)
        assert result["repaired_evaluation"] == repaired

        assert len(calls["evaluate"]) == 2
        assert calls["evaluate"][0]["mapping_override_path"] is None
        assert calls["evaluate"][1]["mapping_override_path"] == str(override_path)

        override_written = json.loads(override_path.read_text(encoding="utf-8"))
        assert override_written == proposal["proposed_mapping_override"]

        written = json.loads(output_path.read_text(encoding="utf-8"))
        assert written["status"] == "repair_validated"

    def test_repair_unavailable_when_proposal_has_no_override(self, monkeypatch, tmp_path):
        baseline = {
            "risk_level": "high_risk",
            "collision_ratio": 1.0,
            "unique_tasks": 0,
        }
        proposal = {
            "repair_needed": False,
            "proposed_mapping_override": {},
            "reasons": ["no repair possible"],
        }

        def fake_evaluate(**kwargs):
            return dict(baseline)

        def fake_propose(**kwargs):
            return dict(proposal)

        monkeypatch.setattr(_mod, "evaluate_planner_config", fake_evaluate)
        monkeypatch.setattr(_mod, "propose_mapping_repair", fake_propose)

        output_path = tmp_path / "cycle.json"
        result = run_mapping_repair_cycle(
            portfolio_state_path="state.json",
            ledger_path="ledger.json",
            policy_path="policy.json",
            output_path=str(output_path),
        )

        assert result["status"] == "repair_unavailable"
        assert result["repair_attempted"] is True
        assert result["repair_success"] is False
        assert result["repair_proposal"] == proposal
        assert result["override_artifact"] == {}
        assert result["override_artifact_path"] is None
        assert result["repaired_evaluation"] is None

        written = json.loads(output_path.read_text(encoding="utf-8"))
        assert written["status"] == "repair_unavailable"
