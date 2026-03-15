# SPDX-License-Identifier: MIT
"""Tests for the artifact bridge: build_portfolio_state_from_artifacts.py.

All fixtures are built in tmp_path; no real artifact files are read.
Output is deterministic when --generated-at is fixed.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from tests.cli_test_utils import run_script_cli

_REPO_ROOT = Path(__file__).resolve().parents[1]
_BRIDGE = str(_REPO_ROOT / "scripts" / "build_portfolio_state_from_artifacts.py")

_TS = "2025-01-01T00:00:00+00:00"


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _write_csv(path: Path, rows: list[dict]) -> None:
    """Write a tier3-style CSV: columns repo, task, result (JSON-encoded)."""
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["repo", "task", "result"])
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "repo": row["repo"],
                "task": row.get("task", "build_portfolio_dashboard"),
                "result": json.dumps(row.get("result", {})),
            })


def _write_agg(path: Path, items: list[dict]) -> None:
    """Write a tier3-style aggregate JSON file."""
    path.write_text(json.dumps(items, indent=2), encoding="utf-8")


def _run_bridge(tmp_path: Path, report: Path, agg: Path, extra: list[str] | None = None) -> tuple[int, Path]:
    """Run the bridge CLI and return (returncode, output_path)."""
    output = tmp_path / "portfolio_state.json"
    args = [
        "--report", str(report),
        "--aggregate", str(agg),
        "--output", str(output),
    ] + (extra or [])
    result = run_script_cli(_BRIDGE, args)
    return result.returncode, output


# ---------------------------------------------------------------------------
# Shared fixture: one healthy repo, one failing repo, one det-fail repo
# ---------------------------------------------------------------------------

def _make_fixtures(tmp_path: Path):
    """Create CSV + aggregate fixtures and return their paths."""

    # CSV rows ---------------------------------------------------------------
    healthy_result = {
        "lifecycle_ok": True,
        "review": {"ok": True, "artifacts": ["report.csv", "dashboard.html"]},
        "plan": {"valid": True},
        "execute": {"executed": True},
    }
    failing_result = {
        "lifecycle_ok": False,
        "review": {"ok": False, "artifacts": []},
        "plan": {"valid": True},
        "execute": {"executed": False},
    }
    det_fail_result = {
        "lifecycle_ok": True,
        "review": {"ok": True, "artifacts": ["report.csv"]},
        "plan": {"valid": True},
        "execute": {"executed": True},
    }

    csv_rows = [
        {"repo": "repo-alpha", "task": "build_portfolio_dashboard", "result": healthy_result},
        {"repo": "repo-failing", "task": "build_portfolio_dashboard", "result": failing_result},
        {"repo": "repo-det-fail", "task": "build_portfolio_dashboard", "result": det_fail_result},
    ]
    report = tmp_path / "report.csv"
    _write_csv(report, csv_rows)

    # Aggregate items --------------------------------------------------------
    # repo-det-fail explicitly signals determinism failure via result.determinism_ok=false.
    agg_items = [
        {
            "repo": "repo-alpha",
            "task": "build_portfolio_dashboard",
            "result": {
                "lifecycle_ok": True,
                "review": {"ok": True, "artifacts": ["report.csv"]},
            },
        },
        {
            "repo": "repo-det-fail",
            "task": "build_portfolio_dashboard",
            "result": {
                "lifecycle_ok": True,
                "determinism_ok": False,
                "review": {"ok": True, "artifacts": ["report.csv"]},
            },
        },
    ]
    agg = tmp_path / "aggregate.json"
    _write_agg(agg, agg_items)

    return report, agg


# ---------------------------------------------------------------------------
# Test 1: output file is created on valid input
# ---------------------------------------------------------------------------

class TestOutputCreated:
    def test_output_file_exists(self, tmp_path):
        report, agg = _make_fixtures(tmp_path)
        rc, output = _run_bridge(tmp_path, report, agg)
        assert rc == 0, "bridge should succeed on valid input"
        assert output.exists(), "output file must be created"

    def test_output_is_valid_json(self, tmp_path):
        report, agg = _make_fixtures(tmp_path)
        _run_bridge(tmp_path, report, agg)
        output = tmp_path / "portfolio_state.json"
        state = json.loads(output.read_text(encoding="utf-8"))
        assert isinstance(state, dict)


# ---------------------------------------------------------------------------
# Test 2: schema_version == "v1"
# ---------------------------------------------------------------------------

class TestSchemaVersion:
    def test_schema_version_is_v1(self, tmp_path):
        report, agg = _make_fixtures(tmp_path)
        _run_bridge(tmp_path, report, agg)
        state = json.loads((tmp_path / "portfolio_state.json").read_text())
        assert state["schema_version"] == "v1"

    def test_top_level_keys_present(self, tmp_path):
        report, agg = _make_fixtures(tmp_path)
        _run_bridge(tmp_path, report, agg)
        state = json.loads((tmp_path / "portfolio_state.json").read_text())
        for key in ("schema_version", "portfolio_id", "generated_at", "summary", "repos", "portfolio_recommendations"):
            assert key in state, f"missing top-level key: {key}"


# ---------------------------------------------------------------------------
# Test 3: healthy repo maps correctly
# ---------------------------------------------------------------------------

class TestHealthyRepoMapping:
    def _get_repo(self, state: dict, repo_id: str) -> dict:
        return next(r for r in state["repos"] if r["repo_id"] == repo_id)

    def test_healthy_repo_status(self, tmp_path):
        report, agg = _make_fixtures(tmp_path)
        _run_bridge(tmp_path, report, agg)
        state = json.loads((tmp_path / "portfolio_state.json").read_text())
        repo = self._get_repo(state, "repo-alpha")
        assert repo["status"] == "healthy"

    def test_healthy_repo_risk_low(self, tmp_path):
        report, agg = _make_fixtures(tmp_path)
        _run_bridge(tmp_path, report, agg)
        state = json.loads((tmp_path / "portfolio_state.json").read_text())
        repo = self._get_repo(state, "repo-alpha")
        assert repo["risk_level"] == "low"

    def test_healthy_repo_health_score_1(self, tmp_path):
        report, agg = _make_fixtures(tmp_path)
        _run_bridge(tmp_path, report, agg)
        state = json.loads((tmp_path / "portfolio_state.json").read_text())
        repo = self._get_repo(state, "repo-alpha")
        assert repo["health_score"] == 1.0

    def test_healthy_repo_no_issues(self, tmp_path):
        report, agg = _make_fixtures(tmp_path)
        _run_bridge(tmp_path, report, agg)
        state = json.loads((tmp_path / "portfolio_state.json").read_text())
        repo = self._get_repo(state, "repo-alpha")
        assert repo["open_issues"] == []

    def test_repos_sorted_by_repo_id(self, tmp_path):
        report, agg = _make_fixtures(tmp_path)
        _run_bridge(tmp_path, report, agg)
        state = json.loads((tmp_path / "portfolio_state.json").read_text())
        ids = [r["repo_id"] for r in state["repos"]]
        assert ids == sorted(ids)


# ---------------------------------------------------------------------------
# Test 4: determinism failure in aggregate → risk_level critical
# ---------------------------------------------------------------------------

class TestDeterminismFailureMapping:
    def _get_repo(self, state: dict, repo_id: str) -> dict:
        return next(r for r in state["repos"] if r["repo_id"] == repo_id)

    def test_det_fail_repo_risk_critical(self, tmp_path):
        report, agg = _make_fixtures(tmp_path)
        _run_bridge(tmp_path, report, agg)
        state = json.loads((tmp_path / "portfolio_state.json").read_text())
        repo = self._get_repo(state, "repo-det-fail")
        assert repo["risk_level"] == "critical"

    def test_det_fail_repo_status_failing(self, tmp_path):
        report, agg = _make_fixtures(tmp_path)
        _run_bridge(tmp_path, report, agg)
        state = json.loads((tmp_path / "portfolio_state.json").read_text())
        repo = self._get_repo(state, "repo-det-fail")
        assert repo["status"] == "failing"

    def test_det_fail_has_determinism_regression_issue(self, tmp_path):
        report, agg = _make_fixtures(tmp_path)
        _run_bridge(tmp_path, report, agg)
        state = json.loads((tmp_path / "portfolio_state.json").read_text())
        repo = self._get_repo(state, "repo-det-fail")
        issue_types = [i["issue_type"] for i in repo["open_issues"]]
        assert "determinism_regression" in issue_types

    def test_det_fail_action_is_run_determinism_suite(self, tmp_path):
        report, agg = _make_fixtures(tmp_path)
        _run_bridge(tmp_path, report, agg)
        state = json.loads((tmp_path / "portfolio_state.json").read_text())
        repo = self._get_repo(state, "repo-det-fail")
        action_types = [a["action_type"] for a in repo["recommended_actions"]]
        assert "run_determinism_regression_suite" in action_types

    def test_det_fail_determinism_via_determinism_failures_field(self, tmp_path):
        """Also accepts determinism_failures > 0 as the signal."""
        report = tmp_path / "report.csv"
        _write_csv(report, [
            {"repo": "repo-df2", "task": "t", "result": {"lifecycle_ok": True, "review": {"ok": True, "artifacts": ["x"]}}},
        ])
        agg = tmp_path / "agg.json"
        _write_agg(agg, [
            {"repo": "repo-df2", "task": "t", "result": {"lifecycle_ok": True, "determinism_failures": 2}},
        ])
        rc, output = _run_bridge(tmp_path, report, agg)
        assert rc == 0
        state = json.loads(output.read_text())
        repo = next(r for r in state["repos"] if r["repo_id"] == "repo-df2")
        assert repo["risk_level"] == "critical"


# ---------------------------------------------------------------------------
# Test 5: missing inputs fail closed
# ---------------------------------------------------------------------------

class TestFailClosed:
    def test_missing_report_fails(self, tmp_path):
        agg = tmp_path / "agg.json"
        _write_agg(agg, [])
        rc, _ = _run_bridge(tmp_path, tmp_path / "no_report.csv", agg)
        assert rc != 0

    def test_missing_aggregate_fails(self, tmp_path):
        report = tmp_path / "report.csv"
        _write_csv(report, [])
        rc, _ = _run_bridge(tmp_path, report, tmp_path / "no_agg.json")
        assert rc != 0

    def test_malformed_csv_fails(self, tmp_path):
        report = tmp_path / "report.csv"
        report.write_text("{not csv\x00garbage", encoding="utf-8")
        agg = tmp_path / "agg.json"
        _write_agg(agg, [])
        # Malformed CSV with no recognisable repo rows → fails with "no repos found"
        rc, _ = _run_bridge(tmp_path, report, agg)
        assert rc != 0

    def test_malformed_aggregate_json_fails(self, tmp_path):
        report = tmp_path / "report.csv"
        _write_csv(report, [
            {"repo": "r1", "task": "t", "result": {"lifecycle_ok": True}},
        ])
        agg = tmp_path / "agg.json"
        agg.write_text("{not valid json", encoding="utf-8")
        rc, _ = _run_bridge(tmp_path, report, agg)
        assert rc != 0

    def test_empty_csv_and_aggregate_fails(self, tmp_path):
        """No repos found in either source → fail closed."""
        report = tmp_path / "report.csv"
        report.write_text("repo,task,result\n", encoding="utf-8")
        agg = tmp_path / "agg.json"
        _write_agg(agg, [])
        rc, _ = _run_bridge(tmp_path, report, agg)
        assert rc != 0


# ---------------------------------------------------------------------------
# Test 6: byte-identical output with fixed --generated-at
# ---------------------------------------------------------------------------

class TestByteIdenticalOutput:
    def test_byte_identical_two_runs(self, tmp_path):
        report, agg = _make_fixtures(tmp_path)

        out1 = tmp_path / "out1.json"
        out2 = tmp_path / "out2.json"

        cmd_base = [
            "--report", str(report),
            "--aggregate", str(agg),
            "--generated-at", _TS,
        ]
        r1 = run_script_cli(_BRIDGE, cmd_base + ["--output", str(out1)])
        r2 = run_script_cli(_BRIDGE, cmd_base + ["--output", str(out2)])

        assert r1.returncode == 0
        assert r2.returncode == 0
        assert out1.read_text(encoding="utf-8") == out2.read_text(encoding="utf-8"), (
            "byte-identical output required when inputs and --generated-at are fixed"
        )

    def test_generated_at_flag_is_present_in_output(self, tmp_path):
        report, agg = _make_fixtures(tmp_path)
        _run_bridge(tmp_path, report, agg, ["--generated-at", _TS])
        state = json.loads((tmp_path / "portfolio_state.json").read_text())
        assert state["generated_at"] == _TS

    def test_default_generated_at_is_empty_string(self, tmp_path):
        report, agg = _make_fixtures(tmp_path)
        _run_bridge(tmp_path, report, agg)
        state = json.loads((tmp_path / "portfolio_state.json").read_text())
        assert state["generated_at"] == ""

    def test_byte_identical_default_no_clock(self, tmp_path):
        """Without --generated-at both runs use "" producing identical output."""
        report, agg = _make_fixtures(tmp_path)
        out1 = tmp_path / "out1.json"
        out2 = tmp_path / "out2.json"
        r1 = run_script_cli(
            _BRIDGE,
            ["--report", str(report), "--aggregate", str(agg), "--output", str(out1)],
        )
        r2 = run_script_cli(
            _BRIDGE,
            ["--report", str(report), "--aggregate", str(agg), "--output", str(out2)],
        )
        assert r1.returncode == 0
        assert r2.returncode == 0
        assert out1.read_text(encoding="utf-8") == out2.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Test 7: real Tier-3 artifacts (smoke test — skipped when missing)
# ---------------------------------------------------------------------------

class TestRealArtifacts:
    """Smoke test against the real artifact files in the repo root.
    Skipped when either file is absent so CI never fails on a missing artifact.
    """

    _REPORT = _REPO_ROOT / "tier3_portfolio_report.csv"
    _AGG = _REPO_ROOT / "tier3_multi_run_aggregate.json"

    @pytest.mark.skipif(
        not (_REPO_ROOT / "tier3_portfolio_report.csv").exists()
        or not (_REPO_ROOT / "tier3_multi_run_aggregate.json").exists(),
        reason="real Tier-3 artifacts not present",
    )
    def test_real_artifacts_produce_valid_state(self, tmp_path):
        output = tmp_path / "portfolio_state.json"
        result = run_script_cli(
            _BRIDGE,
            [
                "--report", str(self._REPORT),
                "--aggregate", str(self._AGG),
                "--output", str(output),
                "--generated-at", _TS,
            ],
        )
        assert result.returncode == 0, f"bridge failed: {result.stderr}"
        state = json.loads(output.read_text(encoding="utf-8"))
        assert state["schema_version"] == "v1"
        assert len(state["repos"]) >= 1
        ids = [r["repo_id"] for r in state["repos"]]
        assert ids == sorted(ids), "repos must be sorted by repo_id"


class TestComparisonGapArtifactIntegration:
    def test_optional_gap_artifact_populates_capability_gaps(self, tmp_path):
        report, agg = _make_fixtures(tmp_path)

        gap_artifact = tmp_path / "comparison_gaps.json"
        gap_artifact.write_text(
            json.dumps(
                {
                    "capability_gaps": [
                        {
                            "capability": "github_repository_management",
                            "gap_source": "reference_mcp_comparison",
                            "severity": 0.65,
                        }
                    ]
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        rc, output = _run_bridge(
            tmp_path,
            report,
            agg,
            ["--comparison-gap-artifact", str(gap_artifact)],
        )

        assert rc == 0
        state = json.loads(output.read_text(encoding="utf-8"))
        assert state["capability_gaps"] == ["github_repository_management"]

    def test_missing_optional_gap_artifact_path_fails_closed(self, tmp_path):
        report, agg = _make_fixtures(tmp_path)

        rc, _ = _run_bridge(
            tmp_path,
            report,
            agg,
            ["--comparison-gap-artifact", str(tmp_path / "no_such_gap_artifact.json")],
        )

        assert rc != 0

    def test_unknown_gap_capability_is_ignored(self, tmp_path):
        report, agg = _make_fixtures(tmp_path)

        gap_artifact = tmp_path / "comparison_gaps.json"
        gap_artifact.write_text(
            json.dumps(
                {
                    "capability_gaps": [
                        {
                            "capability": "unknown_capability",
                            "gap_source": "reference_mcp_comparison",
                            "severity": 0.90,
                        }
                    ]
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        rc, output = _run_bridge(
            tmp_path,
            report,
            agg,
            ["--comparison-gap-artifact", str(gap_artifact)],
        )

        assert rc == 0
        state = json.loads(output.read_text(encoding="utf-8"))
        assert state["capability_gaps"] == []


class TestCapabilityArtifactRegistryIntegration:
    def test_optional_artifact_registry_populates_capability_artifacts(self, tmp_path):
        report, agg = _make_fixtures(tmp_path)

        registry = tmp_path / "capability_artifact_registry.json"
        registry.write_text(
            json.dumps(
                {
                    "capabilities": {
                        "github_repository_management": {
                            "artifact_kind": "mcp_server",
                            "history": [
                                {
                                    "artifact": "generated_mcp_server_github_v1",
                                    "revision": 1,
                                    "source": "portfolio_gap",
                                    "status": "ok",
                                    "used_evolution": False,
                                },
                                {
                                    "artifact": "generated_mcp_server_github_v2",
                                    "revision": 2,
                                    "source": "planner_request",
                                    "status": "ok",
                                    "used_evolution": True,
                                },
                            ],
                            "latest_artifact": "generated_mcp_server_github_v2",
                            "revision": 2,
                        }
                    }
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        rc, output = _run_bridge(
            tmp_path,
            report,
            agg,
            ["--capability-artifact-registry", str(registry)],
        )

        assert rc == 0
        state = json.loads(output.read_text(encoding="utf-8"))
        assert state["capability_artifacts"] == {
            "github_repository_management": {
                "artifact_kind": "mcp_server",
                "latest_artifact": "generated_mcp_server_github_v2",
                "revision": 2,
            }
        }

    def test_missing_optional_artifact_registry_path_fails_closed(self, tmp_path):
        report, agg = _make_fixtures(tmp_path)

        rc, _ = _run_bridge(
            tmp_path,
            report,
            agg,
            ["--capability-artifact-registry", str(tmp_path / "no_such_registry.json")],
        )

        assert rc != 0

    def test_invalid_optional_artifact_registry_fails_closed(self, tmp_path):
        report, agg = _make_fixtures(tmp_path)

        registry = tmp_path / "capability_artifact_registry.json"
        registry.write_text('{"capabilities": []}\n', encoding="utf-8")

        rc, _ = _run_bridge(
            tmp_path,
            report,
            agg,
            ["--capability-artifact-registry", str(registry)],
        )

        assert rc != 0
