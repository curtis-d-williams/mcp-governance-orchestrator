import json
import shutil
from pathlib import Path

import mcp_governance_orchestrator.registry as reg


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_registry_selection_invariants_repo_vs_fallback(tmp_path: Path):
    """
    Freeze the engine's registry selection semantics:

    1) If <repo>/config/guardians.json exists => use repo registry (source=repo, path=<repo>/config/guardians.json)
    2) Otherwise => use orchestrator fallback registry (source=fallback, path=<orchestrator>/config/guardians.json)

    This test is intentionally at the registry layer (not portfolio) to prevent drift.
    """
    orchestrator_repo_root = Path(__file__).resolve().parents[1]
    fallback_registry_path = orchestrator_repo_root / "config" / "guardians.json"
    assert fallback_registry_path.exists(), f"expected fallback registry at {fallback_registry_path}"

    # --- Case A: repo-local registry exists
    repo_with_registry = tmp_path / "repo_with_registry"
    (repo_with_registry / "config").mkdir(parents=True)
    shutil.copyfile(fallback_registry_path, repo_with_registry / "config" / "guardians.json")

    raw_a, prov_a = reg.load_registry_with_provenance(str(repo_with_registry))
    assert isinstance(raw_a, dict)
    assert prov_a["source"] == "repo"
    assert Path(prov_a["path"]).resolve() == (repo_with_registry / "config" / "guardians.json").resolve()

    # Sanity: loaded content matches what we put there
    assert raw_a == _read_json(repo_with_registry / "config" / "guardians.json")

    # --- Case B: repo-local registry missing => fallback
    repo_without_registry = tmp_path / "repo_without_registry"
    repo_without_registry.mkdir(parents=True)

    raw_b, prov_b = reg.load_registry_with_provenance(str(repo_without_registry))
    assert isinstance(raw_b, dict)
    assert prov_b["source"] == "fallback"
    assert Path(prov_b["path"]).resolve() == fallback_registry_path.resolve()

    # Sanity: loaded content matches orchestrator fallback
    assert raw_b == _read_json(fallback_registry_path)
