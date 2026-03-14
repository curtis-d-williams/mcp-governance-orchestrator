# SPDX-License-Identifier: MIT
"""Regression tests for scripts/capture_execution_feedback.py.

All fixtures are built in tmp_path; no real artifact files are read.
Uses subprocess-based invocation consistent with other script CLI tests.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

from tests.cli_test_utils import run_script_cli

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = str(_REPO_ROOT / "scripts" / "capture_execution_feedback.py")

_TS = "2025-01-01T00:00:00+00:00"


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _portfolio_state(repo_id: str, *, health_score: float, risk_level: str) -> dict:
    return {
        "schema_version": "v1",
        "generated_at": "",
        "portfolio_id": "portfolio-test",
        "summary": {
            "repo_count": 1,
            "repos_healthy": 1 if health_score == 1.0 else 0,
            "repos_degraded": 0,
            "repos_failing": 0,
            "repos_stale": 0,
            "open_issues_total": 0,
            "eligible_actions_total": 0,
            "blocked_actions_total": 0,
        },
        "portfolio_recommendations": [],
        "repos": [
            {
                "repo_id": repo_id,
                "status": "healthy" if health_score == 1.0 else "degraded",
                "health_score": health_score,
                "risk_level": risk_level,
                "signals": {
                    "last_run_ok": True,
                    "artifact_completeness": 1.0,
                    "determinism_ok": True,
                    "recent_failures": 0,
                    "stale_runs": 0,
                },
                "open_issues": [],
                "recommended_actions": [
                    {
                        "action_id": f"refresh_repo_health_{repo_id}",
                        "action_type": "refresh_repo_health",
                        "priority": 0.55,
                        "reason": "stale signals for 3 or more runs",
                        "eligible": True,
                        "blocked_by": [],
                        "task_binding": {
                            "task_id": "repo_health_check",
                            "args": {},
                        },
                    }
                ],
                "action_history": [],
                "cooldowns": [],
                "escalations": [],
            }
        ],
    }


def _write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: list[dict]) -> None:
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
    path.write_text(json.dumps(items, indent=2), encoding="utf-8")


def _make_tier3_fixtures(tmp_path: Path) -> tuple[Path, Path]:
    """Return (report_csv, aggregate_json) fixtures with one healthy repo."""
    report = tmp_path / "report.csv"
    _write_csv(report, [
        {
            "repo": "repo-a",
            "task": "build_portfolio_dashboard",
            "result": {
                "lifecycle_ok": True,
                "review": {"ok": True, "artifacts": ["report.csv"]},
            },
        }
    ])
    agg = tmp_path / "aggregate.json"
    _write_agg(agg, [
        {
            "repo": "repo-a",
            "task": "build_portfolio_dashboard",
            "result": {"lifecycle_ok": True},
        }
    ])
    return report, agg


def _run_script(tmp_path: Path, before_source: Path, report: Path, agg: Path,
                executed: Path, extra: list[str] | None = None) -> tuple[int, str, str, dict[str, Path]]:
    """Run capture_execution_feedback.py and return (rc, stdout, stderr, output_paths)."""
    before_out = tmp_path / "before_out.json"
    after_out = tmp_path / "after_out.json"
    eval_out = tmp_path / "evaluation_records.json"
    ledger_out = tmp_path / "ledger.json"
    args = [
        "--before-source", str(before_source),
        "--report", str(report),
        "--aggregate", str(agg),
        "--executed-actions", str(executed),
        "--before-output", str(before_out),
        "--after-output", str(after_out),
        "--evaluation-output", str(eval_out),
        "--ledger-output", str(ledger_out),
    ] + (extra or [])
    result = run_script_cli(_SCRIPT, args)
    paths = {
        "before": before_out,
        "after": after_out,
        "evaluation": eval_out,
        "ledger": ledger_out,
    }
    return result.returncode, result.stdout, result.stderr, paths


# ---------------------------------------------------------------------------
# Test 1: happy path produces all four output files
# ---------------------------------------------------------------------------

class TestHappyPath:
    def _setup(self, tmp_path: Path):
        before_source = tmp_path / "before_source.json"
        _write_json(before_source, _portfolio_state("repo-a", health_score=0.75, risk_level="medium"))
        report, agg = _make_tier3_fixtures(tmp_path)
        executed = tmp_path / "actions.json"
        _write_json(executed, [{"action_type": "refresh_repo_health", "repo_id": "repo-a"}])
        return before_source, report, agg, executed

    def test_exit_zero(self, tmp_path):
        before_source, report, agg, executed = self._setup(tmp_path)
        rc, _, stderr, _ = _run_script(tmp_path, before_source, report, agg, executed)
        assert rc == 0, stderr

    def test_all_four_files_exist(self, tmp_path):
        before_source, report, agg, executed = self._setup(tmp_path)
        rc, _, _, paths = _run_script(tmp_path, before_source, report, agg, executed)
        assert rc == 0
        for name, path in paths.items():
            assert path.exists(), f"missing output: {name}"

    def test_stdout_reports_all_four_writes(self, tmp_path):
        before_source, report, agg, executed = self._setup(tmp_path)
        rc, stdout, _, paths = _run_script(tmp_path, before_source, report, agg, executed)
        assert rc == 0
        for path in paths.values():
            assert str(path) in stdout, f"stdout missing: {path}"


# ---------------------------------------------------------------------------
# Test 2: before snapshot is copied exactly (byte-for-byte)
# ---------------------------------------------------------------------------

class TestBeforeSnapshot:
    def test_before_output_is_byte_identical_to_source(self, tmp_path):
        before_source = tmp_path / "before_source.json"
        _write_json(before_source, _portfolio_state("repo-a", health_score=0.75, risk_level="medium"))
        report, agg = _make_tier3_fixtures(tmp_path)
        executed = tmp_path / "actions.json"
        _write_json(executed, [{"action_type": "refresh_repo_health", "repo_id": "repo-a"}])
        rc, _, _, paths = _run_script(tmp_path, before_source, report, agg, executed)
        assert rc == 0
        assert before_source.read_bytes() == paths["before"].read_bytes()

    def test_before_output_unchanged_when_after_differs(self, tmp_path):
        """The before output must remain the verbatim source regardless of after-state."""
        before_source = tmp_path / "before_source.json"
        source_payload = _portfolio_state("repo-a", health_score=0.50, risk_level="high")
        _write_json(before_source, source_payload)
        report, agg = _make_tier3_fixtures(tmp_path)
        executed = tmp_path / "actions.json"
        _write_json(executed, [{"action_type": "refresh_repo_health", "repo_id": "repo-a"}])
        rc, _, _, paths = _run_script(tmp_path, before_source, report, agg, executed)
        assert rc == 0
        copied = json.loads(paths["before"].read_text(encoding="utf-8"))
        assert copied["repos"][0]["health_score"] == 0.50


# ---------------------------------------------------------------------------
# Test 3: after-state is built from Tier-3 artifacts
# ---------------------------------------------------------------------------

class TestAfterStateBuild:
    def test_after_output_is_valid_portfolio_state(self, tmp_path):
        before_source = tmp_path / "before_source.json"
        _write_json(before_source, _portfolio_state("repo-a", health_score=0.75, risk_level="medium"))
        report, agg = _make_tier3_fixtures(tmp_path)
        executed = tmp_path / "actions.json"
        _write_json(executed, [{"action_type": "refresh_repo_health", "repo_id": "repo-a"}])
        rc, _, _, paths = _run_script(tmp_path, before_source, report, agg, executed)
        assert rc == 0
        after = json.loads(paths["after"].read_text(encoding="utf-8"))
        assert after["schema_version"] == "v1"
        assert len(after["repos"]) >= 1

    def test_after_output_contains_repo_from_artifacts(self, tmp_path):
        before_source = tmp_path / "before_source.json"
        _write_json(before_source, _portfolio_state("repo-a", health_score=0.75, risk_level="medium"))
        report, agg = _make_tier3_fixtures(tmp_path)
        executed = tmp_path / "actions.json"
        _write_json(executed, [{"action_type": "refresh_repo_health", "repo_id": "repo-a"}])
        rc, _, _, paths = _run_script(tmp_path, before_source, report, agg, executed)
        assert rc == 0
        after = json.loads(paths["after"].read_text(encoding="utf-8"))
        repo_ids = [r["repo_id"] for r in after["repos"]]
        assert "repo-a" in repo_ids

    def test_after_output_generated_at_propagated(self, tmp_path):
        before_source = tmp_path / "before_source.json"
        _write_json(before_source, _portfolio_state("repo-a", health_score=0.75, risk_level="medium"))
        report, agg = _make_tier3_fixtures(tmp_path)
        executed = tmp_path / "actions.json"
        _write_json(executed, [{"action_type": "refresh_repo_health", "repo_id": "repo-a"}])
        rc, _, _, paths = _run_script(
            tmp_path, before_source, report, agg, executed,
            extra=["--generated-at", _TS],
        )
        assert rc == 0
        after = json.loads(paths["after"].read_text(encoding="utf-8"))
        assert after["generated_at"] == _TS


# ---------------------------------------------------------------------------
# Test 4: evaluation and ledger are built
# ---------------------------------------------------------------------------

class TestEvaluationAndLedger:
    def _run_happy(self, tmp_path: Path):
        before_source = tmp_path / "before_source.json"
        _write_json(before_source, _portfolio_state("repo-a", health_score=0.75, risk_level="medium"))
        report, agg = _make_tier3_fixtures(tmp_path)
        executed = tmp_path / "actions.json"
        _write_json(executed, [{"action_type": "refresh_repo_health", "repo_id": "repo-a"}])
        rc, _, stderr, paths = _run_script(tmp_path, before_source, report, agg, executed)
        assert rc == 0, stderr
        return paths

    def test_evaluation_output_is_list(self, tmp_path):
        paths = self._run_happy(tmp_path)
        records = json.loads(paths["evaluation"].read_text(encoding="utf-8"))
        assert isinstance(records, list)

    def test_evaluation_output_contains_executed_actions(self, tmp_path):
        paths = self._run_happy(tmp_path)
        records = json.loads(paths["evaluation"].read_text(encoding="utf-8"))
        assert len(records) == 1
        assert records[0]["executed_actions"] == [
            {"action_type": "refresh_repo_health", "repo_id": "repo-a"}
        ]

    def test_ledger_output_schema_version(self, tmp_path):
        paths = self._run_happy(tmp_path)
        ledger = json.loads(paths["ledger"].read_text(encoding="utf-8"))
        assert ledger["schema_version"] == "v1"

    def test_ledger_output_tracks_action(self, tmp_path):
        paths = self._run_happy(tmp_path)
        ledger = json.loads(paths["ledger"].read_text(encoding="utf-8"))
        assert ledger["summary"]["actions_tracked"] == 1
        assert ledger["action_types"][0]["action_type"] == "refresh_repo_health"


# ---------------------------------------------------------------------------
# Test 5: fail closed on missing before-source
# ---------------------------------------------------------------------------

class TestFailClosed:
    def test_missing_before_source_exits_nonzero(self, tmp_path):
        report, agg = _make_tier3_fixtures(tmp_path)
        executed = tmp_path / "actions.json"
        _write_json(executed, [{"action_type": "refresh_repo_health", "repo_id": "repo-a"}])
        rc, _, stderr, paths = _run_script(
            tmp_path,
            tmp_path / "nonexistent_before.json",
            report, agg, executed,
        )
        assert rc != 0
        assert "before-source" in stderr

    def test_missing_before_source_does_not_write_outputs(self, tmp_path):
        report, agg = _make_tier3_fixtures(tmp_path)
        executed = tmp_path / "actions.json"
        _write_json(executed, [{"action_type": "refresh_repo_health", "repo_id": "repo-a"}])
        _, _, _, paths = _run_script(
            tmp_path,
            tmp_path / "nonexistent_before.json",
            report, agg, executed,
        )
        for name, path in paths.items():
            assert not path.exists(), f"should not have written {name}"

    def test_missing_report_exits_nonzero(self, tmp_path):
        before_source = tmp_path / "before_source.json"
        _write_json(before_source, _portfolio_state("repo-a", health_score=0.75, risk_level="medium"))
        _, agg = _make_tier3_fixtures(tmp_path)
        executed = tmp_path / "actions.json"
        _write_json(executed, [{"action_type": "refresh_repo_health", "repo_id": "repo-a"}])
        rc, _, _, _ = _run_script(tmp_path, before_source, tmp_path / "no_report.csv", agg, executed)
        assert rc != 0

    def test_missing_aggregate_exits_nonzero(self, tmp_path):
        before_source = tmp_path / "before_source.json"
        _write_json(before_source, _portfolio_state("repo-a", health_score=0.75, risk_level="medium"))
        report, _ = _make_tier3_fixtures(tmp_path)
        executed = tmp_path / "actions.json"
        _write_json(executed, [{"action_type": "refresh_repo_health", "repo_id": "repo-a"}])
        rc, _, _, _ = _run_script(tmp_path, before_source, report, tmp_path / "no_agg.json", executed)
        assert rc != 0

    def test_missing_executed_actions_exits_nonzero(self, tmp_path):
        before_source = tmp_path / "before_source.json"
        _write_json(before_source, _portfolio_state("repo-a", health_score=0.75, risk_level="medium"))
        report, agg = _make_tier3_fixtures(tmp_path)
        rc, _, _, _ = _run_script(
            tmp_path, before_source, report, agg,
            tmp_path / "nonexistent_actions.json",
        )
        assert rc != 0


# ---------------------------------------------------------------------------
# Test 6: after-state builder failure → exits nonzero, no success claim
# ---------------------------------------------------------------------------

class TestAfterStateBuildFailure:
    def test_malformed_aggregate_exits_nonzero(self, tmp_path):
        before_source = tmp_path / "before_source.json"
        _write_json(before_source, _portfolio_state("repo-a", health_score=0.75, risk_level="medium"))
        report, _ = _make_tier3_fixtures(tmp_path)
        bad_agg = tmp_path / "bad_aggregate.json"
        bad_agg.write_text("{not valid json", encoding="utf-8")
        executed = tmp_path / "actions.json"
        _write_json(executed, [{"action_type": "refresh_repo_health", "repo_id": "repo-a"}])
        rc, stdout, _, paths = _run_script(tmp_path, before_source, report, bad_agg, executed)
        assert rc != 0

    def test_after_state_failure_does_not_claim_success(self, tmp_path):
        before_source = tmp_path / "before_source.json"
        _write_json(before_source, _portfolio_state("repo-a", health_score=0.75, risk_level="medium"))
        report, _ = _make_tier3_fixtures(tmp_path)
        bad_agg = tmp_path / "bad_aggregate.json"
        bad_agg.write_text("{not valid json", encoding="utf-8")
        executed = tmp_path / "actions.json"
        _write_json(executed, [{"action_type": "refresh_repo_health", "repo_id": "repo-a"}])
        rc, stdout, _, paths = _run_script(tmp_path, before_source, report, bad_agg, executed)
        assert rc != 0
        # None of the "wrote:" success lines should appear in stdout.
        for path in paths.values():
            assert f"wrote: {path}" not in stdout, f"must not claim wrote: {path}"

    def test_after_state_failure_evaluation_not_created(self, tmp_path):
        before_source = tmp_path / "before_source.json"
        _write_json(before_source, _portfolio_state("repo-a", health_score=0.75, risk_level="medium"))
        report, _ = _make_tier3_fixtures(tmp_path)
        bad_agg = tmp_path / "bad_aggregate.json"
        bad_agg.write_text("{not valid json", encoding="utf-8")
        executed = tmp_path / "actions.json"
        _write_json(executed, [{"action_type": "refresh_repo_health", "repo_id": "repo-a"}])
        _, _, _, paths = _run_script(tmp_path, before_source, report, bad_agg, executed)
        assert not paths["evaluation"].exists()
        assert not paths["ledger"].exists()


# ---------------------------------------------------------------------------
# Test 7: deterministic ordering in outputs is preserved by existing builders
# ---------------------------------------------------------------------------

class TestDeterministicOrdering:
    def test_repos_sorted_in_after_output(self, tmp_path):
        """After-state repo ordering is deterministic (delegated to builder)."""
        before_source = tmp_path / "before_source.json"
        _write_json(before_source, _portfolio_state("repo-a", health_score=0.75, risk_level="medium"))

        report = tmp_path / "report.csv"
        _write_csv(report, [
            {"repo": "repo-z", "task": "t", "result": {"lifecycle_ok": True, "review": {"ok": True, "artifacts": ["x"]}}},
            {"repo": "repo-a", "task": "t", "result": {"lifecycle_ok": True, "review": {"ok": True, "artifacts": ["x"]}}},
            {"repo": "repo-m", "task": "t", "result": {"lifecycle_ok": True, "review": {"ok": True, "artifacts": ["x"]}}},
        ])
        agg = tmp_path / "agg.json"
        _write_agg(agg, [
            {"repo": "repo-z", "task": "t", "result": {"lifecycle_ok": True}},
            {"repo": "repo-a", "task": "t", "result": {"lifecycle_ok": True}},
            {"repo": "repo-m", "task": "t", "result": {"lifecycle_ok": True}},
        ])
        executed = tmp_path / "actions.json"
        _write_json(executed, [{"action_type": "refresh_repo_health", "repo_id": "repo-a"}])

        rc, _, stderr, paths = _run_script(tmp_path, before_source, report, agg, executed)
        assert rc == 0, stderr
        after = json.loads(paths["after"].read_text(encoding="utf-8"))
        ids = [r["repo_id"] for r in after["repos"]]
        assert ids == sorted(ids)

    def test_byte_identical_two_runs_with_fixed_generated_at(self, tmp_path):
        """With fixed --generated-at both runs produce byte-identical after-state."""
        before_source = tmp_path / "before_source.json"
        _write_json(before_source, _portfolio_state("repo-a", health_score=0.75, risk_level="medium"))
        report, agg = _make_tier3_fixtures(tmp_path)
        executed = tmp_path / "actions.json"
        _write_json(executed, [{"action_type": "refresh_repo_health", "repo_id": "repo-a"}])

        out1 = tmp_path / "run1"
        out1.mkdir()
        out2 = tmp_path / "run2"
        out2.mkdir()

        def _run_to(dest: Path):
            after_p = dest / "after.json"
            r = run_script_cli(
                _SCRIPT,
                [
                    "--before-source", str(before_source),
                    "--report", str(report),
                    "--aggregate", str(agg),
                    "--executed-actions", str(executed),
                    "--before-output", str(dest / "before.json"),
                    "--after-output", str(after_p),
                    "--evaluation-output", str(dest / "eval.json"),
                    "--ledger-output", str(dest / "ledger.json"),
                    "--generated-at", _TS,
                ],
            )
            return r.returncode, after_p

        rc1, after1 = _run_to(out1)
        rc2, after2 = _run_to(out2)

        assert rc1 == 0
        assert rc2 == 0
        assert after1.read_text(encoding="utf-8") == after2.read_text(encoding="utf-8")
