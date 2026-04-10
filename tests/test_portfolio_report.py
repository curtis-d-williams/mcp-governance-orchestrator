import importlib.util
import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO_ROOT / "scripts" / "portfolio_report.py"
_spec = importlib.util.spec_from_file_location("portfolio_report", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)


def test_e_portfolio_report_smoke(tmp_path, monkeypatch, capsys):
    ledger = {
        "capabilities": {
            "github_repository_management": {
                "artifact_kind": "mcp_server",
                "total_syntheses": 2,
                "successful_syntheses": 2,
                "successful_evolved_syntheses": 1,
                "last_synthesis_source": "planner_request",
                "last_synthesis_status": "ok",
                "last_synthesis_used_evolution": True,
                "similarity_score": 0.72,
                "previous_similarity_score": 0.55,
                "similarity_delta": 0.17,
            }
        }
    }
    ledger_path = tmp_path / "ledger.json"
    ledger_path.write_text(json.dumps(ledger))

    monkeypatch.setattr(sys, "argv", ["portfolio_report.py", str(ledger_path)])
    _mod.main()
    out = capsys.readouterr().out

    assert "CAPABILITY EFFECTIVENESS LEDGER REPORT" in out
    assert "PER-CAPABILITY DETAIL" in out
    assert "SIMILARITY PROGRESSION SUMMARY" in out
    assert "ADAPTATION SIGNAL SUMMARY" in out
    assert "END OF REPORT" in out

    assert "total_syntheses" in out
    assert "success_rate" in out
    assert "evolution_rate" in out


def test_f_multi_capability_fixture(tmp_path, monkeypatch, capsys):
    ledger = {
        "capabilities": {
            "alpha_cap": {
                "artifact_kind": "mcp_server",
                "total_syntheses": 3,
                "successful_syntheses": 3,
                "successful_evolved_syntheses": 2,
                "last_synthesis_source": "planner_request",
                "last_synthesis_status": "ok",
                "last_synthesis_used_evolution": True,
                "similarity_score": 0.80,
                "previous_similarity_score": 0.65,
                "similarity_delta": 0.15,
            },
            "beta_cap": {
                "artifact_kind": "mcp_server",
                "total_syntheses": 4,
                "successful_syntheses": 4,
                "successful_evolved_syntheses": 0,
                "last_synthesis_source": "planner_request",
                "last_synthesis_status": "ok",
                "last_synthesis_used_evolution": False,
                "similarity_score": 0.50,
                "previous_similarity_score": 0.58,
                "similarity_delta": -0.08,
            },
            "gamma_cap": {
                "artifact_kind": "data_connector",
                "total_syntheses": 1,
                "successful_syntheses": 1,
                "successful_evolved_syntheses": 0,
                "last_synthesis_source": "planner_request",
                "last_synthesis_status": "ok",
            },
        }
    }
    ledger_path = tmp_path / "ledger.json"
    ledger_path.write_text(json.dumps(ledger))

    monkeypatch.setattr(sys, "argv", ["portfolio_report.py", str(ledger_path)])
    _mod.main()
    out = capsys.readouterr().out

    assert "    - alpha_cap" in out

    assert "    - beta_cap" in out

    # beta_cap must not appear in the evolution subsection of ADAPTATION SIGNAL SUMMARY
    adaptation_section = out.split("ADAPTATION SIGNAL SUMMARY")[1]
    evo_subsection = adaptation_section.split("Regression flags")[0]
    assert "beta_cap" not in evo_subsection

    # gamma_cap has no similarity_delta so must be absent from the adaptation summary tail
    adaptation_tail = out.split("ADAPTATION SIGNAL SUMMARY")[1]
    assert "gamma_cap" not in adaptation_tail

    assert "No regression flags." not in out
