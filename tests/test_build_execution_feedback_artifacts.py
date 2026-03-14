from __future__ import annotations

import json
from pathlib import Path

from tests.cli_test_utils import run_script_cli


def _write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


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


def test_build_execution_feedback_artifacts_happy_path(tmp_path: Path):
    before_path = tmp_path / "before.json"
    after_path = tmp_path / "after.json"
    actions_path = tmp_path / "actions.json"
    evaluation_output = tmp_path / "evaluation_records.json"
    ledger_output = tmp_path / "ledger.json"

    _write_json(before_path, _portfolio_state("repo-a", health_score=0.75, risk_level="medium"))
    _write_json(after_path, _portfolio_state("repo-a", health_score=0.90, risk_level="low"))
    _write_json(actions_path, [{"action_type": "refresh_repo_health", "repo_id": "repo-a"}])

    result = run_script_cli(
        "scripts/build_execution_feedback_artifacts.py",
        [
            "--before", str(before_path),
            "--after", str(after_path),
            "--executed-actions", str(actions_path),
            "--evaluation-output", str(evaluation_output),
            "--ledger-output", str(ledger_output),
            "--generated-at", "",
        ],
    )

    assert result.returncode == 0, result.stderr
    assert evaluation_output.exists()
    assert ledger_output.exists()

    records = json.loads(evaluation_output.read_text(encoding="utf-8"))
    assert isinstance(records, list)
    assert len(records) == 1
    assert records[0]["executed_actions"] == [
        {"action_type": "refresh_repo_health", "repo_id": "repo-a"}
    ]

    ledger = json.loads(ledger_output.read_text(encoding="utf-8"))
    assert ledger["schema_version"] == "v1"
    assert ledger["summary"]["actions_tracked"] == 1
    assert ledger["action_types"][0]["action_type"] == "refresh_repo_health"
    assert ledger["action_types"][0]["times_executed"] == 1
    assert ledger["action_types"][0]["success_rate"] == 1.0


def test_build_execution_feedback_artifacts_fails_closed_on_bad_actions(tmp_path: Path):
    before_path = tmp_path / "before.json"
    after_path = tmp_path / "after.json"
    actions_path = tmp_path / "actions.json"
    evaluation_output = tmp_path / "evaluation_records.json"
    ledger_output = tmp_path / "ledger.json"

    _write_json(before_path, _portfolio_state("repo-a", health_score=0.75, risk_level="medium"))
    _write_json(after_path, _portfolio_state("repo-a", health_score=0.90, risk_level="low"))
    _write_json(actions_path, [{"repo_id": "repo-a"}])

    result = run_script_cli(
        "scripts/build_execution_feedback_artifacts.py",
        [
            "--before", str(before_path),
            "--after", str(after_path),
            "--executed-actions", str(actions_path),
            "--evaluation-output", str(evaluation_output),
            "--ledger-output", str(ledger_output),
        ],
    )

    assert result.returncode == 1
    assert "evaluation record build failed" in result.stderr
    assert not ledger_output.exists()
