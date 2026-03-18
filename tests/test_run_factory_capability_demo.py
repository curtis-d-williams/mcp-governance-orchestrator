# SPDX-License-Identifier: MIT
"""Smoke test: scripts/run_factory_capability_demo.py loads and main() completes."""

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_SCRIPT = _REPO_ROOT / "scripts" / "run_factory_capability_demo.py"
_spec = importlib.util.spec_from_file_location("run_factory_capability_demo", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)


def test_demo_script_loads_without_import_error():
    """Module-level import of the demo script must succeed."""
    assert _mod is not None


def test_demo_main_completes_with_mocked_subprocess_and_verify(monkeypatch):
    """main() must complete without raising when subprocess and verify calls are mocked."""
    monkeypatch.setattr(_mod, "run_factory_cycle", lambda: None)
    monkeypatch.setattr(_mod, "verify_generated_repo", lambda: None)
    monkeypatch.setattr(_mod, "verify_factory_artifact", lambda: None)

    _mod.main()  # must not raise
