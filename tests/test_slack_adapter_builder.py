# SPDX-License-Identifier: MIT
"""Regression tests for the deterministic Slack agent adapter builder."""

import json
import shutil
from pathlib import Path

import builder.slack_adapter_builder as _mod
from builder.artifact_registry import ARTIFACT_BUILDERS, build_capability_artifact


def _read(path):
    return Path(path).read_text(encoding="utf-8")


def test_build_agent_adapter_generates_expected_repo_shape():
    repo_root = _mod.REPO_ROOT
    generated = repo_root / "generated_agent_adapter_slack"

    if generated.exists():
        shutil.rmtree(generated)

    result = _mod.build_agent_adapter()

    assert result == {
        "status": "ok",
        "generated_repo": str(generated),
        "artifact_kind": "agent_adapter",
        "capability": "slack_workspace_access",
    }

    assert generated.is_dir()
    assert (generated / "README.md").is_file()
    assert (generated / "adapter_manifest.json").is_file()
    assert (generated / "slack_adapter.py").is_file()
    assert (generated / "tests" / "test_adapter_smoke.py").is_file()

    manifest = json.loads((generated / "adapter_manifest.json").read_text(encoding="utf-8"))
    assert manifest == {
        "name": "generated_agent_adapter_slack",
        "artifact_kind": "agent_adapter",
        "capability": "slack_workspace_access",
        "provider": "slack",
        "version": "0.1.0",
        "entrypoint": "slack_adapter.py",
    }

    shutil.rmtree(generated)


def test_build_agent_adapter_is_deterministic_across_repeated_runs():
    repo_root = _mod.REPO_ROOT
    generated = repo_root / "generated_agent_adapter_slack"

    if generated.exists():
        shutil.rmtree(generated)

    _mod.build_agent_adapter()
    first_snapshot = {
        str(path.relative_to(generated)): _read(path)
        for path in sorted(p for p in generated.rglob("*") if p.is_file())
    }

    _mod.build_agent_adapter()
    second_snapshot = {
        str(path.relative_to(generated)): _read(path)
        for path in sorted(p for p in generated.rglob("*") if p.is_file())
    }

    assert first_snapshot == second_snapshot

    shutil.rmtree(generated)


def test_agent_adapter_builder_registers_in_artifact_registry():
    assert ARTIFACT_BUILDERS["agent_adapter"] is _mod.build_agent_adapter


def test_build_capability_artifact_dispatches_agent_adapter_builder():
    repo_root = _mod.REPO_ROOT
    generated = repo_root / "generated_agent_adapter_slack"

    if generated.exists():
        shutil.rmtree(generated)

    result = build_capability_artifact(
        artifact_kind="agent_adapter",
        capability="slack_workspace_access",
    )

    assert result == {
        "status": "ok",
        "generated_repo": str(generated),
        "artifact_kind": "agent_adapter",
        "capability": "slack_workspace_access",
    }

    assert generated.is_dir()

    shutil.rmtree(generated)
