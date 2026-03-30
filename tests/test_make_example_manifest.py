# SPDX-License-Identifier: MIT
"""Tests for scripts/make_example_manifest.py.

Covers:
A. Output file is created at the specified path.
B. Returned path matches the destination file.
C. repos[0]["path"] is an absolute path.
D. repos[0]["path"] exists on disk.
E. Output ends with a trailing newline.
"""

import importlib.util
import json
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_SCRIPT = _REPO_ROOT / "scripts" / "make_example_manifest.py"
_spec = importlib.util.spec_from_file_location("make_example_manifest", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

make_example_manifest = _mod.make_example_manifest


class TestMakeExampleManifest:
    def _run(self, tmp_path):
        """Call make_example_manifest with a tmp output path; return (dest, data)."""
        dest = make_example_manifest(tmp_path / "manifest.json")
        data = json.loads(dest.read_text(encoding="utf-8"))
        return dest, data

    def test_output_file_created(self, tmp_path):
        dest, _ = self._run(tmp_path)
        assert dest.exists()

    def test_returned_path_matches_dest(self, tmp_path):
        out = tmp_path / "manifest.json"
        returned = make_example_manifest(out)
        assert returned == out

    def test_repos_path_is_absolute(self, tmp_path):
        _, data = self._run(tmp_path)
        assert os.path.isabs(data["repos"][0]["path"]), (
            "repos[0]['path'] must be an absolute path so that "
            "run_portfolio_cycles.py resolves correctly from any work_dir"
        )

    def test_repos_path_exists(self, tmp_path):
        _, data = self._run(tmp_path)
        assert Path(data["repos"][0]["path"]).exists()

    def test_trailing_newline(self, tmp_path):
        dest, _ = self._run(tmp_path)
        assert dest.read_text(encoding="utf-8").endswith("\n")
