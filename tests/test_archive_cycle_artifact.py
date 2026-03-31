# SPDX-License-Identifier: MIT
"""Tests for scripts/archive_cycle_artifact.py.

Covers:
A. archive dir auto-created when absent
B. timestamped file created in archive dir
C. original input preserved after archiving
D. archived contents identical to input
E. --timestamp override produces exact expected filename
F. missing input returns error result
G. success stdout JSON parseable and contains expected keys
H. collision-safe naming when same timestamp is reused
"""

import importlib.util
import json
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Module loading
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_SCRIPT = _REPO_ROOT / "scripts" / "archive_cycle_artifact.py"
_spec = importlib.util.spec_from_file_location("archive_cycle_artifact", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

archive_artifact = _mod.archive_artifact
_archive_filename = _mod._archive_filename
_now_timestamp = _mod._now_timestamp
_resolve_archive_path = _mod._resolve_archive_path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FIXED_TS = "2024-03-01T12-00-00"
_CYCLE_CONTENT = json.dumps({"status": "ok", "selected_offset": 0}, indent=2) + "\n"


def _make_input(tmp_path, content=None):
    """Write a cycle artifact file and return its path."""
    p = tmp_path / "governed_portfolio_cycle.json"
    p.write_text(content or _CYCLE_CONTENT, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# A. Archive dir auto-created
# ---------------------------------------------------------------------------

class TestArchiveDirCreation:
    def test_dir_created_when_absent(self, tmp_path):
        src = _make_input(tmp_path)
        archive_dir = tmp_path / "new" / "subdir" / "cycles"
        assert not archive_dir.exists()
        archive_artifact(str(src), str(archive_dir), timestamp=_FIXED_TS)
        assert archive_dir.exists()

    def test_dir_creation_is_idempotent(self, tmp_path):
        src = _make_input(tmp_path)
        archive_dir = tmp_path / "cycles"
        archive_dir.mkdir()
        # Should not raise even if dir already exists.
        result = archive_artifact(str(src), str(archive_dir), timestamp=_FIXED_TS)
        assert result["status"] == "ok"


# ---------------------------------------------------------------------------
# B. Timestamped file created
# ---------------------------------------------------------------------------

class TestTimestampedFileCreated:
    def test_archived_file_exists(self, tmp_path):
        src = _make_input(tmp_path)
        archive_dir = tmp_path / "cycles"
        archive_artifact(str(src), str(archive_dir), timestamp=_FIXED_TS)
        expected = archive_dir / f"{_FIXED_TS}_cycle.json"
        assert expected.exists()

    def test_archived_to_path_in_result(self, tmp_path):
        src = _make_input(tmp_path)
        archive_dir = tmp_path / "cycles"
        result = archive_artifact(str(src), str(archive_dir), timestamp=_FIXED_TS)
        assert result["archived_to"] == str(archive_dir / f"{_FIXED_TS}_cycle.json")

    def test_timestamp_in_result(self, tmp_path):
        src = _make_input(tmp_path)
        archive_dir = tmp_path / "cycles"
        result = archive_artifact(str(src), str(archive_dir), timestamp=_FIXED_TS)
        assert result["timestamp"] == _FIXED_TS


# ---------------------------------------------------------------------------
# C. Original input preserved
# ---------------------------------------------------------------------------

class TestOriginalPreserved:
    def test_input_still_exists(self, tmp_path):
        src = _make_input(tmp_path)
        archive_dir = tmp_path / "cycles"
        archive_artifact(str(src), str(archive_dir), timestamp=_FIXED_TS)
        assert src.exists()

    def test_input_content_unchanged(self, tmp_path):
        src = _make_input(tmp_path)
        original_text = src.read_text(encoding="utf-8")
        archive_dir = tmp_path / "cycles"
        archive_artifact(str(src), str(archive_dir), timestamp=_FIXED_TS)
        assert src.read_text(encoding="utf-8") == original_text


# ---------------------------------------------------------------------------
# D. Archived contents identical to input
# ---------------------------------------------------------------------------

class TestArchivedContents:
    def test_archived_content_matches_input(self, tmp_path):
        src = _make_input(tmp_path)
        archive_dir = tmp_path / "cycles"
        archive_artifact(str(src), str(archive_dir), timestamp=_FIXED_TS)
        archived = archive_dir / f"{_FIXED_TS}_cycle.json"
        assert archived.read_text(encoding="utf-8") == src.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# E. --timestamp override produces exact filename
# ---------------------------------------------------------------------------

class TestTimestampOverride:
    def test_custom_timestamp_used_in_filename(self, tmp_path):
        src = _make_input(tmp_path)
        archive_dir = tmp_path / "cycles"
        ts = "2099-12-31T23-59-59"
        archive_artifact(str(src), str(archive_dir), timestamp=ts)
        assert (archive_dir / f"{ts}_cycle.json").exists()

    def test_no_other_file_created(self, tmp_path):
        src = _make_input(tmp_path)
        archive_dir = tmp_path / "cycles"
        ts = "2099-12-31T23-59-59"
        archive_artifact(str(src), str(archive_dir), timestamp=ts)
        files = list(archive_dir.iterdir())
        assert len(files) == 1
        assert files[0].name == f"{ts}_cycle.json"

    def test_archive_filename_helper(self):
        assert _archive_filename("2024-01-01T00-00-00") == "2024-01-01T00-00-00_cycle.json"


# ---------------------------------------------------------------------------
# F. Missing input returns error result
# ---------------------------------------------------------------------------

class TestMissingInput:
    def test_missing_input_returns_error_status(self, tmp_path):
        result = archive_artifact(
            str(tmp_path / "nonexistent.json"),
            str(tmp_path / "cycles"),
            timestamp=_FIXED_TS,
        )
        assert result["status"] == "error"

    def test_missing_input_archived_to_is_none(self, tmp_path):
        result = archive_artifact(
            str(tmp_path / "nonexistent.json"),
            str(tmp_path / "cycles"),
            timestamp=_FIXED_TS,
        )
        assert result["archived_to"] is None

    def test_missing_input_no_dir_created(self, tmp_path):
        archive_dir = tmp_path / "cycles"
        archive_artifact(
            str(tmp_path / "nonexistent.json"),
            str(archive_dir),
            timestamp=_FIXED_TS,
        )
        # Archive dir should not be created for a missing input.
        assert not archive_dir.exists()


# ---------------------------------------------------------------------------
# G. Success stdout JSON via main()
# ---------------------------------------------------------------------------

class TestMainStdout:
    def test_success_stdout_is_valid_json(self, tmp_path, capsys):
        src = _make_input(tmp_path)
        archive_dir = tmp_path / "cycles"
        _mod.main([
            "--input", str(src),
            "--archive-dir", str(archive_dir),
            "--timestamp", _FIXED_TS,
        ])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert isinstance(data, dict)

    def test_success_stdout_contains_status(self, tmp_path, capsys):
        src = _make_input(tmp_path)
        archive_dir = tmp_path / "cycles"
        _mod.main([
            "--input", str(src),
            "--archive-dir", str(archive_dir),
            "--timestamp", _FIXED_TS,
        ])
        data = json.loads(capsys.readouterr().out)
        assert data["status"] == "ok"

    def test_success_stdout_contains_input(self, tmp_path, capsys):
        src = _make_input(tmp_path)
        archive_dir = tmp_path / "cycles"
        _mod.main([
            "--input", str(src),
            "--archive-dir", str(archive_dir),
            "--timestamp", _FIXED_TS,
        ])
        data = json.loads(capsys.readouterr().out)
        assert data["input"] == str(src)

    def test_success_stdout_contains_archived_to(self, tmp_path, capsys):
        src = _make_input(tmp_path)
        archive_dir = tmp_path / "cycles"
        _mod.main([
            "--input", str(src),
            "--archive-dir", str(archive_dir),
            "--timestamp", _FIXED_TS,
        ])
        data = json.loads(capsys.readouterr().out)
        assert data["archived_to"] is not None
        assert data["archived_to"].endswith(f"{_FIXED_TS}_cycle.json")

    def test_success_stdout_contains_timestamp(self, tmp_path, capsys):
        src = _make_input(tmp_path)
        archive_dir = tmp_path / "cycles"
        _mod.main([
            "--input", str(src),
            "--archive-dir", str(archive_dir),
            "--timestamp", _FIXED_TS,
        ])
        data = json.loads(capsys.readouterr().out)
        assert data["timestamp"] == _FIXED_TS

    def test_failure_exits_one(self, tmp_path, capsys):
        with pytest.raises(SystemExit) as exc_info:
            _mod.main([
                "--input", str(tmp_path / "missing.json"),
                "--archive-dir", str(tmp_path / "cycles"),
                "--timestamp", _FIXED_TS,
            ])
        assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# H. Collision-safe naming
# ---------------------------------------------------------------------------

class TestCollisionSafety:
    def test_two_calls_same_timestamp_produce_distinct_files(self, tmp_path):
        src = _make_input(tmp_path)
        archive_dir = tmp_path / "cycles"
        r1 = archive_artifact(str(src), str(archive_dir), timestamp=_FIXED_TS)
        r2 = archive_artifact(str(src), str(archive_dir), timestamp=_FIXED_TS)
        assert r1["status"] == "ok"
        assert r2["status"] == "ok"
        assert r1["archived_to"] != r2["archived_to"]
        assert len(list(archive_dir.glob("*_cycle*.json"))) == 2

    def test_first_archive_unchanged_after_second_call(self, tmp_path):
        src = _make_input(tmp_path)
        archive_dir = tmp_path / "cycles"
        r1 = archive_artifact(str(src), str(archive_dir), timestamp=_FIXED_TS)
        content_after_first = Path(r1["archived_to"]).read_text(encoding="utf-8")
        archive_artifact(str(src), str(archive_dir), timestamp=_FIXED_TS)
        assert Path(r1["archived_to"]).read_text(encoding="utf-8") == content_after_first

    def test_second_archive_gets_suffixed_filename(self, tmp_path):
        src = _make_input(tmp_path)
        archive_dir = tmp_path / "cycles"
        archive_artifact(str(src), str(archive_dir), timestamp=_FIXED_TS)
        r2 = archive_artifact(str(src), str(archive_dir), timestamp=_FIXED_TS)
        assert Path(r2["archived_to"]).name == f"{_FIXED_TS}_cycle_1.json"

    def test_third_call_gets_next_suffix(self, tmp_path):
        src = _make_input(tmp_path)
        archive_dir = tmp_path / "cycles"
        archive_artifact(str(src), str(archive_dir), timestamp=_FIXED_TS)
        archive_artifact(str(src), str(archive_dir), timestamp=_FIXED_TS)
        r3 = archive_artifact(str(src), str(archive_dir), timestamp=_FIXED_TS)
        assert Path(r3["archived_to"]).name == f"{_FIXED_TS}_cycle_2.json"

    def test_resolve_archive_path_no_collision(self, tmp_path):
        dst_dir = tmp_path / "cycles"
        dst_dir.mkdir()
        p = _resolve_archive_path(dst_dir, _FIXED_TS)
        assert p.name == f"{_FIXED_TS}_cycle.json"
        assert not p.exists()

    def test_resolve_archive_path_with_collision(self, tmp_path):
        dst_dir = tmp_path / "cycles"
        dst_dir.mkdir()
        # Pre-create the base file to force a suffix.
        (dst_dir / f"{_FIXED_TS}_cycle.json").write_text("x", encoding="utf-8")
        p = _resolve_archive_path(dst_dir, _FIXED_TS)
        assert p.name == f"{_FIXED_TS}_cycle_1.json"


# ---------------------------------------------------------------------------
# I. Sidecar archiving
# ---------------------------------------------------------------------------

class TestSidecarArchiving:
    def test_sidecar_archived_when_present(self, tmp_path):
        src = _make_input(tmp_path)
        sidecar = tmp_path / "planner_priority_breakdown.json"
        sidecar.write_text('{"breakdown": []}', encoding="utf-8")
        archive_dir = tmp_path / "cycles"

        result = archive_artifact(str(src), str(archive_dir),
                                  timestamp=_FIXED_TS,
                                  sidecar_paths=[str(sidecar)])

        assert result["status"] == "ok"
        expected_sidecar = archive_dir / f"{_FIXED_TS}_planner_priority_breakdown.json"
        assert expected_sidecar.exists()
        assert result["sidecars_archived"] == [str(expected_sidecar)]

    def test_sidecar_content_matches_source(self, tmp_path):
        src = _make_input(tmp_path)
        sidecar = tmp_path / "planner_scoring_metrics.json"
        sidecar_content = '{"metrics": []}'
        sidecar.write_text(sidecar_content, encoding="utf-8")
        archive_dir = tmp_path / "cycles"

        archive_artifact(str(src), str(archive_dir),
                         timestamp=_FIXED_TS,
                         sidecar_paths=[str(sidecar)])

        archived_sidecar = archive_dir / f"{_FIXED_TS}_planner_scoring_metrics.json"
        assert archived_sidecar.read_text(encoding="utf-8") == sidecar_content

    def test_absent_sidecar_does_not_fail(self, tmp_path):
        src = _make_input(tmp_path)
        archive_dir = tmp_path / "cycles"

        result = archive_artifact(str(src), str(archive_dir),
                                  timestamp=_FIXED_TS,
                                  sidecar_paths=[str(tmp_path / "missing.json")])

        assert result["status"] == "ok"
        assert result["sidecars_archived"] == []

    def test_no_sidecar_paths_backward_compatible(self, tmp_path):
        src = _make_input(tmp_path)
        archive_dir = tmp_path / "cycles"

        result = archive_artifact(str(src), str(archive_dir), timestamp=_FIXED_TS)

        assert result["status"] == "ok"
        assert result["sidecars_archived"] == []
        assert len(list(archive_dir.iterdir())) == 1
