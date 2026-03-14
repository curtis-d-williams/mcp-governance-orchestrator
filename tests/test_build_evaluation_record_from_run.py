from __future__ import annotations

import json
from pathlib import Path

from tests.cli_test_utils import run_script_cli


def _write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _portfolio_state(repo_ids: list[str]) -> dict:
    repos = []
    for repo_id in repo_ids:
        repos.append(
            {
                "repo_id": repo_id,
                "status": "healthy",
                "health_score": 1.0,
                "risk_level": "low",
                "signals": {
                    "last_run_ok": True,
                    "artifact_completeness": 1.0,
                    "determinism_ok": True,
                    "recent_failures": 0,
                    "stale_runs": 0,
                },
                "open_issues": [],
                "recommended_actions": [],
                "action_history": [],
                "cooldowns": [],
                "escalations": [],
            }
        )
    return {
        "schema_version": "v1",
        "generated_at": "",
        "portfolio_id": "portfolio-test",
        "summary": {
            "repo_count": len(repos),
            "repos_healthy": len(repos),
            "repos_degraded": 0,
            "repos_failing": 0,
            "repos_stale": 0,
            "open_issues_total": 0,
            "eligible_actions_total": 0,
            "blocked_actions_total": 0,
        },
        "portfolio_recommendations": [],
        "repos": repos,
    }


def test_build_evaluation_record_from_run_happy_path(tmp_path: Path):
    before_path = tmp_path / "before.json"
    after_path = tmp_path / "after.json"
    actions_path = tmp_path / "actions.json"
    output_path = tmp_path / "evaluation_records.json"

    _write_json(before_path, _portfolio_state(["repo-b", "repo-a"]))
    _write_json(after_path, _portfolio_state(["repo-b", "repo-a"]))
    _write_json(
        actions_path,
        [
            {"action_type": "rerun_failed_task", "repo_id": "repo-b"},
            {"action_type": "refresh_repo_health", "repo_id": "repo-a"},
        ],
    )

    result = run_script_cli(
        "scripts/build_evaluation_record_from_run.py",
        [
            "--before", str(before_path),
            "--after", str(after_path),
            "--executed-actions", str(actions_path),
            "--output", str(output_path),
        ],
    )

    assert result.returncode == 0, result.stderr
    assert output_path.exists()

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert isinstance(payload, list)
    assert len(payload) == 1

    rec = payload[0]
    assert rec["before_state"]["portfolio_id"] == "portfolio-test"
    assert rec["after_state"]["portfolio_id"] == "portfolio-test"
    assert rec["executed_actions"] == [
        {"action_type": "refresh_repo_health", "repo_id": "repo-a"},
        {"action_type": "rerun_failed_task", "repo_id": "repo-b"},
    ]


def test_build_evaluation_record_from_run_accepts_wrapped_executed_actions(tmp_path: Path):
    before_path = tmp_path / "before.json"
    after_path = tmp_path / "after.json"
    actions_path = tmp_path / "actions.json"
    output_path = tmp_path / "evaluation_records.json"

    _write_json(before_path, _portfolio_state(["repo-a"]))
    _write_json(after_path, _portfolio_state(["repo-a"]))
    _write_json(
        actions_path,
        {
            "executed_actions": [
                {"action_type": "refresh_repo_health", "repo_id": "repo-a"}
            ]
        },
    )

    result = run_script_cli(
        "scripts/build_evaluation_record_from_run.py",
        [
            "--before", str(before_path),
            "--after", str(after_path),
            "--executed-actions", str(actions_path),
            "--output", str(output_path),
        ],
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload[0]["executed_actions"] == [
        {"action_type": "refresh_repo_health", "repo_id": "repo-a"}
    ]


def test_build_evaluation_record_from_run_fails_closed_on_bad_actions(tmp_path: Path):
    before_path = tmp_path / "before.json"
    after_path = tmp_path / "after.json"
    actions_path = tmp_path / "actions.json"
    output_path = tmp_path / "evaluation_records.json"

    _write_json(before_path, _portfolio_state(["repo-a"]))
    _write_json(after_path, _portfolio_state(["repo-a"]))
    _write_json(actions_path, [{"repo_id": "repo-a"}])

    result = run_script_cli(
        "scripts/build_evaluation_record_from_run.py",
        [
            "--before", str(before_path),
            "--after", str(after_path),
            "--executed-actions", str(actions_path),
            "--output", str(output_path),
        ],
    )

    assert result.returncode == 1
    assert "missing action_type" in result.stderr
    assert not output_path.exists()
