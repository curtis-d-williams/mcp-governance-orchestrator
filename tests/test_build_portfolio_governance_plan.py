# SPDX-License-Identifier: MIT
"""Tests for scripts/build_portfolio_governance_plan.py (Phase Q)."""

import importlib.util
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_SCRIPT = _REPO_ROOT / "scripts" / "build_portfolio_governance_plan.py"
_spec = importlib.util.spec_from_file_location("build_portfolio_governance_plan", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

build_plan = _mod.build_plan


def _write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_build_plan_enables_repo_with_no_prior_summary(tmp_path: Path):
    manifest_path = tmp_path / "manifest.json"
    output_dir = tmp_path / "portfolio_batch"

    _write_json(
        manifest_path,
        {
            "repos": [
                {"id": "repo_a"},
            ]
        },
    )

    plan = build_plan(manifest_path, output_dir)

    assert plan == {
        "repos": [
            {
                "enabled": True,
                "reason": "no_prior_run",
                "repo_id": "repo_a",
            }
        ]
    }


def test_build_plan_disables_stable_continue_repo(tmp_path: Path):
    manifest_path = tmp_path / "manifest.json"
    output_dir = tmp_path / "portfolio_batch"

    _write_json(
        manifest_path,
        {
            "repos": [
                {"id": "repo_a"},
            ]
        },
    )
    _write_json(
        output_dir / "repo_a" / "summary.json",
        {
            "alert_level": "none",
            "governance_decision": "continue",
        },
    )

    plan = build_plan(manifest_path, output_dir)

    assert plan == {
        "repos": [
            {
                "enabled": False,
                "reason": "stable_continue_last_cycle",
                "repo_id": "repo_a",
            }
        ]
    }


def test_build_plan_enables_repo_with_prior_attention_signal(tmp_path: Path):
    manifest_path = tmp_path / "manifest.json"
    output_dir = tmp_path / "portfolio_batch"

    _write_json(
        manifest_path,
        {
            "repos": [
                {"id": "repo_a"},
            ]
        },
    )
    _write_json(
        output_dir / "repo_a" / "summary.json",
        {
            "alert_level": "warning",
            "governance_decision": "warn",
        },
    )

    plan = build_plan(manifest_path, output_dir)

    assert plan == {
        "repos": [
            {
                "enabled": True,
                "reason": "prior_attention_signal",
                "repo_id": "repo_a",
            }
        ]
    }


def test_build_plan_applies_attention_budget_deterministically(tmp_path: Path):
    manifest_path = tmp_path / "manifest.json"
    output_dir = tmp_path / "portfolio_batch"

    _write_json(
        manifest_path,
        {
            "repos": [
                {"id": "repo_c"},
                {"id": "repo_a"},
                {"id": "repo_d"},
                {"id": "repo_b"},
            ]
        },
    )

    for repo_id in ("repo_c", "repo_a", "repo_d", "repo_b"):
        _write_json(
            output_dir / repo_id / "summary.json",
            {
                "alert_level": "warning",
                "governance_decision": "warn",
            },
        )

    plan = build_plan(manifest_path, output_dir, max_repos_per_cycle=3)

    assert plan == {
        "repos": [
            {
                "enabled": True,
                "reason": "prior_attention_signal",
                "repo_id": "repo_a",
            },
            {
                "enabled": True,
                "reason": "prior_attention_signal",
                "repo_id": "repo_b",
            },
            {
                "enabled": True,
                "reason": "prior_attention_signal",
                "repo_id": "repo_c",
            },
            {
                "enabled": False,
                "reason": "attention_budget_exceeded",
                "repo_id": "repo_d",
            },
        ]
    }


def test_build_plan_preserves_stable_skip_when_budget_is_present(tmp_path: Path):
    manifest_path = tmp_path / "manifest.json"
    output_dir = tmp_path / "portfolio_batch"

    _write_json(
        manifest_path,
        {
            "repos": [
                {"id": "repo_b"},
                {"id": "repo_a"},
                {"id": "repo_c"},
            ]
        },
    )

    _write_json(
        output_dir / "repo_a" / "summary.json",
        {
            "alert_level": "warning",
            "governance_decision": "warn",
        },
    )
    _write_json(
        output_dir / "repo_b" / "summary.json",
        {
            "alert_level": "none",
            "governance_decision": "continue",
        },
    )
    _write_json(
        output_dir / "repo_c" / "summary.json",
        {
            "alert_level": "warning",
            "governance_decision": "warn",
        },
    )

    plan = build_plan(manifest_path, output_dir, max_repos_per_cycle=1)

    assert plan == {
        "repos": [
            {
                "enabled": True,
                "reason": "prior_attention_signal",
                "repo_id": "repo_a",
            },
            {
                "enabled": False,
                "reason": "stable_continue_last_cycle",
                "repo_id": "repo_b",
            },
            {
                "enabled": False,
                "reason": "attention_budget_exceeded",
                "repo_id": "repo_c",
            },
        ]
    }

def test_build_plan_prioritizes_higher_alert_repos_within_budget(tmp_path: Path):
    manifest_path = tmp_path / "manifest.json"
    output_dir = tmp_path / "portfolio_batch"

    _write_json(
        manifest_path,
        {
            "repos": [
                {"id": "repo_c"},
                {"id": "repo_a"},
                {"id": "repo_b"},
            ]
        },
    )

    _write_json(
        output_dir / "repo_a" / "summary.json",
        {
            "alert_level": "warning",
            "governance_decision": "warn",
        },
    )
    _write_json(
        output_dir / "repo_b" / "summary.json",
        {
            "alert_level": "critical",
            "governance_decision": "abort",
        },
    )
    _write_json(
        output_dir / "repo_c" / "summary.json",
        {
            "alert_level": "warning",
            "governance_decision": "warn",
        },
    )

    plan = build_plan(manifest_path, output_dir, max_repos_per_cycle=1)

    assert plan == {
        "repos": [
            {
                "enabled": False,
                "reason": "attention_budget_exceeded",
                "repo_id": "repo_a",
            },
            {
                "enabled": True,
                "reason": "prior_attention_signal",
                "repo_id": "repo_b",
            },
            {
                "enabled": False,
                "reason": "attention_budget_exceeded",
                "repo_id": "repo_c",
            },
        ]
    }

def test_build_plan_latest_abort_bypasses_attention_budget(tmp_path: Path):
    manifest_path = tmp_path / "manifest.json"
    output_dir = tmp_path / "portfolio_batch"

    _write_json(
        manifest_path,
        {
            "repos": [
                {"id": "repo_a"},
                {"id": "repo_b"},
            ]
        },
    )

    _write_json(
        output_dir / "repo_a" / "summary.json",
        {
            "alert_level": "warning",
            "governance_decision": "warn",
            "regression_detected": False,
            "status": "ok",
            "timestamp": "2026-03-11T00:00:00Z",
        },
    )
    _write_json(
        output_dir / "repo_a" / "summary_history.json",
        [
            {
                "alert_level": "warning",
                "governance_decision": "warn",
                "regression_detected": False,
                "status": "ok",
                "timestamp": "2026-03-11T00:00:00Z",
            }
        ],
    )

    _write_json(
        output_dir / "repo_b" / "summary.json",
        {
            "alert_level": "warning",
            "governance_decision": "abort",
            "regression_detected": False,
            "status": "ok",
            "timestamp": "2026-03-11T01:00:00Z",
        },
    )
    _write_json(
        output_dir / "repo_b" / "summary_history.json",
        [
            {
                "alert_level": "warning",
                "governance_decision": "abort",
                "regression_detected": False,
                "status": "ok",
                "timestamp": "2026-03-11T01:00:00Z",
            }
        ],
    )

    plan = build_plan(manifest_path, output_dir, max_repos_per_cycle=0)

    assert plan == {
        "repos": [
            {
                "enabled": False,
                "reason": "attention_budget_exceeded",
                "repo_id": "repo_a",
            },
            {
                "enabled": True,
                "reason": "prior_attention_signal",
                "repo_id": "repo_b",
            },
        ]
    }
