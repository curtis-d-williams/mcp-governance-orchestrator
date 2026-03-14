from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
import io
import os
import runpy
import sys


@dataclass
class CLIResult:
    returncode: int
    stdout: str
    stderr: str


def run_script_cli(script_path: str, args: list[str], cwd: str | None = None) -> CLIResult:
    old_argv = sys.argv[:]
    old_cwd = os.getcwd()
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()

    try:
        sys.argv = [script_path, *args]
        if cwd is not None:
            os.chdir(cwd)

        with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
            try:
                runpy.run_path(script_path, run_name="__main__")
                returncode = 0
            except SystemExit as exc:
                code = exc.code
                if code is None:
                    returncode = 0
                elif isinstance(code, int):
                    returncode = code
                else:
                    returncode = 1
    finally:
        sys.argv = old_argv
        os.chdir(old_cwd)

    return CLIResult(
        returncode=returncode,
        stdout=stdout_buf.getvalue(),
        stderr=stderr_buf.getvalue(),
    )
