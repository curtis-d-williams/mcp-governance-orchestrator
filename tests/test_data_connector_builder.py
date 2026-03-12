# SPDX-License-Identifier: MIT
"""Regression tests for the deterministic data connector builder."""

import json
import shutil
from pathlib import Path

import builder.data_connector_builder as _mod
from builder.artifact_registry import ARTIFACT_BUILDERS, build_capability_artifact


def _read(path):
    return Path(path).read_text(encoding="utf-8")


def test_build_data_connector_generates_expected_repo_shape():
    repo_root = _mod.REPO_ROOT
    generated = repo_root / "generated_data_connector_postgres"

    if generated.exists():
        shutil.rmtree(generated)

    result = _mod.build_data_connector()

    assert result == {
        "status": "ok",
        "generated_repo": str(generated),
        "artifact_kind": "data_connector",
        "capability": "postgres_data_access",
    }

    assert generated.is_dir()
    assert (generated / "README.md").is_file()
    assert (generated / "connector_manifest.json").is_file()
    assert (generated / "postgres_connector.py").is_file()
    assert (generated / "tests" / "test_connector_smoke.py").is_file()

    manifest = json.loads((generated / "connector_manifest.json").read_text(encoding="utf-8"))
    assert manifest == {
        "name": "generated_data_connector_postgres",
        "artifact_kind": "data_connector",
        "capability": "postgres_data_access",
        "provider": "postgres",
        "version": "0.1.0",
        "entrypoint": "postgres_connector.py",
    }

    shutil.rmtree(generated)


def test_build_data_connector_is_deterministic_across_repeated_runs():
    repo_root = _mod.REPO_ROOT
    generated = repo_root / "generated_data_connector_postgres"

    if generated.exists():
        shutil.rmtree(generated)

    _mod.build_data_connector()
    first_snapshot = {
        str(path.relative_to(generated)): _read(path)
        for path in sorted(p for p in generated.rglob("*") if p.is_file())
    }

    _mod.build_data_connector()
    second_snapshot = {
        str(path.relative_to(generated)): _read(path)
        for path in sorted(p for p in generated.rglob("*") if p.is_file())
    }

    assert first_snapshot == second_snapshot

    shutil.rmtree(generated)


def test_data_connector_builder_registers_in_artifact_registry():
    assert ARTIFACT_BUILDERS["data_connector"] is _mod.build_data_connector


def test_build_capability_artifact_dispatches_data_connector_builder():
    repo_root = _mod.REPO_ROOT
    generated = repo_root / "generated_data_connector_postgres"

    if generated.exists():
        shutil.rmtree(generated)

    result = build_capability_artifact(
        artifact_kind="data_connector",
        capability="postgres_data_access",
    )

    assert result == {
        "status": "ok",
        "generated_repo": str(generated),
        "artifact_kind": "data_connector",
        "capability": "postgres_data_access",
    }

    assert generated.is_dir()

    shutil.rmtree(generated)
