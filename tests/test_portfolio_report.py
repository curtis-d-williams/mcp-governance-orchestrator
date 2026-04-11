import importlib.util
import json
import sys
from pathlib import Path

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


def test_g_evolution_and_regression_simultaneous(tmp_path, monkeypatch, capsys):
    ledger = {
        "capabilities": {
            "delta_cap": {
                "artifact_kind": "mcp_server",
                "total_syntheses": 2,
                "successful_syntheses": 2,
                "successful_evolved_syntheses": 1,
                "last_synthesis_source": "planner_request",
                "last_synthesis_status": "ok",
                "last_synthesis_used_evolution": True,
                "similarity_score": 0.60,
                "previous_similarity_score": 0.70,
                "similarity_delta": -0.10,
            }
        }
    }
    ledger_path = tmp_path / "ledger.json"
    ledger_path.write_text(json.dumps(ledger))

    monkeypatch.setattr(sys, "argv", ["portfolio_report.py", str(ledger_path)])
    _mod.main()
    out = capsys.readouterr().out

    adaptation_section = out.split("ADAPTATION SIGNAL SUMMARY")[1]
    evo_subsection = adaptation_section.split("Regression flags")[0]
    regression_subsection = adaptation_section.split("Regression flags")[1]

    # delta_cap used evolution → must appear in the evolution subsection
    assert "delta_cap" in evo_subsection

    # delta_cap has negative similarity_delta → must appear in the regression subsection
    assert "delta_cap" in regression_subsection

    # neither empty-state sentinel should appear
    assert "No capabilities used evolution" not in out
    assert "No regression flags." not in out


def test_h_no_evolution_sentinel(tmp_path, monkeypatch, capsys):
    ledger = {
        "capabilities": {
            "epsilon_cap": {
                "artifact_kind": "mcp_server",
                "total_syntheses": 3,
                "successful_syntheses": 3,
                "successful_evolved_syntheses": 0,
                "last_synthesis_source": "planner_request",
                "last_synthesis_status": "ok",
                "last_synthesis_used_evolution": False,
                "similarity_score": 0.45,
                "previous_similarity_score": 0.55,
                "similarity_delta": -0.10,
            }
        }
    }
    ledger_path = tmp_path / "ledger.json"
    ledger_path.write_text(json.dumps(ledger))

    monkeypatch.setattr(sys, "argv", ["portfolio_report.py", str(ledger_path)])
    _mod.main()
    out = capsys.readouterr().out

    # No capability used evolution — sentinel must appear
    assert "No capabilities used evolution on last synthesis." in out

    # epsilon_cap has negative delta — regression sentinel must NOT appear
    assert "No regression flags." not in out


def test_live_portfolio_report_multi_cycle_learning_sequence(tmp_path, monkeypatch, capsys):
    """Two sequential live factory cycles feed capability_effectiveness_ledger data,
    then portfolio_report.main() is called to confirm the report renders correctly
    against real builder output across both cycles.

    Only planner stubs and get_reference_artifact_path are monkeypatched;
    build_capability_artifact and compare_mcp_servers run live.
    """
    import importlib.util as _ilu
    import shutil
    import json as _json

    # ------------------------------------------------------------------
    # Load run_autonomous_factory_cycle locally as _rac_mod
    # ------------------------------------------------------------------
    _rac_script = _REPO_ROOT / "scripts" / "run_autonomous_factory_cycle.py"
    _rac_spec = _ilu.spec_from_file_location("run_autonomous_factory_cycle", _rac_script)
    _rac_mod = _ilu.module_from_spec(_rac_spec)
    _rac_spec.loader.exec_module(_rac_mod)

    # ------------------------------------------------------------------
    # Load factory_pipeline locally as _pipeline for monkeypatching
    # ------------------------------------------------------------------
    _fp_spec = _ilu.spec_from_file_location("factory_pipeline", _REPO_ROOT / "factory_pipeline.py")
    _pipeline = _ilu.module_from_spec(_fp_spec)
    _fp_spec.loader.exec_module(_pipeline)

    # ------------------------------------------------------------------
    # Build minimal reference fixture
    # ------------------------------------------------------------------
    ref_root = tmp_path / "reference_mcp_github_repository_management"
    ref_root.mkdir(parents=True)

    # server.json
    (ref_root / "server.json").write_text(
        _json.dumps({
            "$schema": "https://example.com/schema",
            "name": "github-mcp-server",
            "title": "GitHub MCP Server",
            "description": "Reference GitHub MCP server.",
            "repository": {"url": "https://github.com/example/mcp-github", "source": "github"},
            "version": "0.1.0",
            "packages": [],
            "remotes": [],
        }),
        encoding="utf-8",
    )

    # README.md
    (ref_root / "README.md").write_text(
        "# GitHub MCP Server\n\n"
        "## Tools\n\n"
        "- `list_repositories` — list repositories\n"
        "- `get_me` — get current user\n",
        encoding="utf-8",
    )

    # pkg/github/tools.go
    tools_go_dir = ref_root / "pkg" / "github"
    tools_go_dir.mkdir(parents=True)
    (tools_go_dir / "tools.go").write_text(
        "package github\n\n"
        "func AllTools(t interface{}) []interface{} { return []interface{}{} }\n"
        "func RemoteOnlyToolsets() []interface{} { return []interface{}{} }\n",
        encoding="utf-8",
    )

    # pkg/github/server.go
    (tools_go_dir / "server.go").write_text(
        "package github\n\n// DynamicToolsets enabled\n",
        encoding="utf-8",
    )

    # internal/ghmcp/server.go
    ghmcp_dir = ref_root / "internal" / "ghmcp"
    ghmcp_dir.mkdir(parents=True)
    (ghmcp_dir / "server.go").write_text(
        "package ghmcp\n\n// ReadOnly mode supported\n",
        encoding="utf-8",
    )

    # ------------------------------------------------------------------
    # Portfolio state file
    # ------------------------------------------------------------------
    ps_path = tmp_path / "portfolio_state.json"
    ps_path.write_text(_json.dumps({"capability_gaps": ["github_repository_management"]}))

    # ------------------------------------------------------------------
    # Monkeypatch 1: get_reference_artifact_path -> tmp_path fixture
    # (patch against the factory_pipeline module _rac_mod actually imported)
    # ------------------------------------------------------------------
    import factory_pipeline as _fp_canonical
    monkeypatch.setattr(
        _fp_canonical,
        "get_reference_artifact_path",
        lambda capability, registry_root=None: str(ref_root),
    )

    # ------------------------------------------------------------------
    # Monkeypatch 2: planner stubs
    # ------------------------------------------------------------------
    evaluation = {"risk_level": "moderate_risk", "reasons": []}

    governed_result = {
        "selected_offset": 0,
        "result": {
            "evaluation_summary": {
                "runs": [
                    {
                        "selected_actions": ["build_mcp_server"],
                        "selection_detail": {
                            "ranked_action_window": ["build_mcp_server"],
                            "ranked_action_window_detail": [
                                {
                                    "action_type": "build_mcp_server",
                                    "task_binding": {
                                        "args": {
                                            "capability": "github_repository_management",
                                        }
                                    },
                                }
                            ],
                        },
                    }
                ]
            }
        },
    }

    monkeypatch.setattr(_rac_mod, "evaluate_planner_config", lambda **kwargs: evaluation)
    monkeypatch.setattr(_rac_mod, "run_governed_loop", lambda args: governed_result)

    ledger_path = tmp_path / "ledger_live.json"
    generated_dir = _REPO_ROOT / "generated_mcp_server_github"

    try:
        # -------- cycle 1 --------
        artifact1 = _rac_mod.run_autonomous_factory_cycle(
            portfolio_state=str(ps_path),
            capability_ledger_output=str(ledger_path),
            top_k=3,
            output=str(tmp_path / "cycle1.json"),
        )

        # -------- cycle 2 (carries forward ledger) --------
        artifact2 = _rac_mod.run_autonomous_factory_cycle(
            portfolio_state=str(ps_path),
            capability_ledger=str(ledger_path),
            capability_ledger_output=str(ledger_path),
            top_k=3,
            output=str(tmp_path / "cycle2.json"),
        )

        # -------- portfolio report --------
        monkeypatch.setattr(sys, "argv", ["portfolio_report.py", str(ledger_path)])
        _mod.main()
        out = capsys.readouterr().out

        # Section headers always present
        assert "CAPABILITY EFFECTIVENESS LEDGER REPORT" in out
        assert "PER-CAPABILITY DETAIL" in out
        assert "SIMILARITY PROGRESSION SUMMARY" in out
        assert "ADAPTATION SIGNAL SUMMARY" in out
        assert "END OF REPORT" in out

        # Per-capability fields always present
        assert "total_syntheses" in out
        assert "success_rate" in out
        assert "evolution_rate" in out

        # Capability appears in similarity progression (live builder produces real similarity_score)
        sim_section = out.split("SIMILARITY PROGRESSION SUMMARY")[1].split("ADAPTATION SIGNAL SUMMARY")[0]
        assert "github_repository_management" in sim_section

        # Ledger accumulated two cycles
        ledger_data = _json.loads(ledger_path.read_text())
        cap = ledger_data["capabilities"]["github_repository_management"]
        assert cap["total_syntheses"] == 2
        assert cap["successful_syntheses"] == 2

        # Adaptation signal summary has at least one sentinel (not entirely absent)
        adapt_section = out.split("ADAPTATION SIGNAL SUMMARY")[1]
        has_evo_text = (
            "No capabilities used evolution" in adapt_section
            or "Capabilities using evolution" in adapt_section
        )
        assert has_evo_text, "ADAPTATION SIGNAL SUMMARY evolution subsection missing"

    finally:
        if generated_dir.exists():
            shutil.rmtree(generated_dir)
