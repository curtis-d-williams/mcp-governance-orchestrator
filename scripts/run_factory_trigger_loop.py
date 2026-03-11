# SPDX-License-Identifier: MIT
"""Event-driven trigger loop for the autonomous MCP factory."""

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

from factory_runtime import read_json, utcnow_iso, write_json


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


_DEFAULT_WATCH_PATHS = [
    "portfolio_state.json",
    "policies/default.json",
]


def _normalize_watch_paths(paths):
    seen = set()
    result = []
    for raw in paths:
        value = str(Path(raw))
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _resolve_watch_paths(args):
    if args.watch:
        return _normalize_watch_paths(args.watch)

    paths = list(_DEFAULT_WATCH_PATHS)
    if args.ledger:
        paths.append(args.ledger)
    return _normalize_watch_paths(paths)


def _sha256_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _build_signal_snapshot(paths):
    snapshot = {}
    for raw in paths:
        path = Path(raw)
        exists = path.exists()
        snapshot[str(path)] = {
            "exists": exists,
            "sha256": _sha256_file(path) if exists else None,
        }
    return snapshot


def _changed_paths(previous, current):
    changed = []
    all_paths = sorted(set(previous) | set(current))
    for path in all_paths:
        if previous.get(path) != current.get(path):
            changed.append(path)
    return changed


def _build_trigger_entry(changed, snapshot, daemon_rc, daemon_cmd):
    return {
        "timestamp": utcnow_iso(),
        "changed_paths": changed,
        "watched_paths": sorted(snapshot.keys()),
        "daemon_returncode": daemon_rc,
        "daemon_command": daemon_cmd,
        "status": "triggered",
    }


def _build_idle_entry(snapshot):
    return {
        "timestamp": utcnow_iso(),
        "changed_paths": [],
        "watched_paths": sorted(snapshot.keys()),
        "status": "no_change",
    }


def _default_state():
    return {
        "last_checked_at": None,
        "last_triggered_at": None,
        "watched_paths": [],
        "signal_snapshot": {},
        "last_changed_paths": [],
        "last_daemon_returncode": None,
    }


def _update_state(state, snapshot, *, changed_paths, daemon_rc=None, triggered=False):
    next_state = dict(state)
    next_state["last_checked_at"] = utcnow_iso()
    next_state["watched_paths"] = sorted(snapshot.keys())
    next_state["signal_snapshot"] = snapshot
    next_state["last_changed_paths"] = changed_paths
    next_state["last_daemon_returncode"] = daemon_rc
    if triggered:
        next_state["last_triggered_at"] = next_state["last_checked_at"]
    return next_state


def _build_daemon_cmd(args):
    cmd = [
        sys.executable,
        "scripts/run_factory_daemon.py",
        "--portfolio-state",
        args.portfolio_state,
        "--top-k",
        str(args.top_k),
        "--cycle-output",
        args.cycle_output,
        "--state-output",
        args.factory_state_output,
        "--journal-output",
        args.factory_journal_output,
        "--max-consecutive-failures",
        str(args.max_consecutive_failures),
        "--max-consecutive-idle-cycles",
        str(args.max_consecutive_idle_cycles),
        "--sleep-seconds",
        "0",
        "--max-cycles",
        "1",
    ]
    if args.ledger:
        cmd.extend(["--ledger", args.ledger])
    if args.policy:
        cmd.extend(["--policy", args.policy])
    return cmd


def run_factory_trigger_loop(args):
    watch_paths = _resolve_watch_paths(args)
    state_path = Path(args.trigger_state_output)
    journal_path = Path(args.trigger_journal_output)

    state = read_json(state_path, _default_state())
    previous_snapshot = state.get("signal_snapshot", {})

    completed_polls = 0

    while True:
        snapshot = _build_signal_snapshot(watch_paths)
        changed = _changed_paths(previous_snapshot, snapshot)

        daemon_rc = None
        triggered = False

        if changed or args.trigger_on_start:
            daemon_cmd = _build_daemon_cmd(args)
            proc = subprocess.run(daemon_cmd, check=False)
            daemon_rc = proc.returncode
            triggered = True

            journal_entry = _build_trigger_entry(changed, snapshot, daemon_rc, daemon_cmd)
            state = _update_state(
                state,
                snapshot,
                changed_paths=changed,
                daemon_rc=daemon_rc,
                triggered=True,
            )
            write_json(state_path, state)

            journal_path.parent.mkdir(parents=True, exist_ok=True)
            with journal_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(journal_entry, sort_keys=True) + "\n")

            print(
                f"factory trigger: changed={len(changed)} "
                f"daemon_rc={daemon_rc}"
            )
            previous_snapshot = snapshot
            args.trigger_on_start = False
        else:
            state = _update_state(
                state,
                snapshot,
                changed_paths=[],
                daemon_rc=None,
                triggered=False,
            )
            write_json(state_path, state)

            if args.journal_no_change:
                journal_entry = _build_idle_entry(snapshot)
                journal_path.parent.mkdir(parents=True, exist_ok=True)
                with journal_path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(journal_entry, sort_keys=True) + "\n")

            print("factory trigger: no_change")
            previous_snapshot = snapshot

        completed_polls += 1
        if args.max_polls is not None and completed_polls >= args.max_polls:
            print("factory trigger loop stopped: max_polls_reached")
            return 0

        if args.poll_seconds <= 0:
            continue
        time.sleep(args.poll_seconds)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run event-driven factory trigger loop.")
    parser.add_argument(
        "--watch",
        action="append",
        default=None,
        help="Signal file to watch. May be provided multiple times.",
    )
    parser.add_argument(
        "--portfolio-state",
        default="portfolio_state.json",
        help="Path passed through to run_factory_daemon.py.",
    )
    parser.add_argument(
        "--ledger",
        default=None,
        help="Optional planner ledger path passed through to run_factory_daemon.py.",
    )
    parser.add_argument(
        "--policy",
        default="policies/default.json",
        help="Path passed through to run_factory_daemon.py.",
    )
    parser.add_argument("--top-k", type=int, default=3, help="Planner top-k value.")
    parser.add_argument(
        "--cycle-output",
        default="artifacts/autonomous_factory_cycle.json",
        help="Latest factory cycle artifact path.",
    )
    parser.add_argument(
        "--factory-state-output",
        default="artifacts/factory_state.json",
        help="Factory daemon persistent state output.",
    )
    parser.add_argument(
        "--factory-journal-output",
        default="artifacts/factory_cycle_journal.jsonl",
        help="Factory daemon cycle journal output.",
    )
    parser.add_argument(
        "--trigger-state-output",
        default="artifacts/factory_trigger_state.json",
        help="Persistent trigger state JSON.",
    )
    parser.add_argument(
        "--trigger-journal-output",
        default="artifacts/factory_trigger_journal.jsonl",
        help="Append-only trigger journal JSONL.",
    )
    parser.add_argument(
        "--max-consecutive-failures",
        type=int,
        default=3,
        help="Passed through to factory daemon.",
    )
    parser.add_argument(
        "--max-consecutive-idle-cycles",
        type=int,
        default=5,
        help="Passed through to factory daemon.",
    )
    parser.add_argument(
        "--poll-seconds",
        type=int,
        default=30,
        help="Polling interval for signal checks.",
    )
    parser.add_argument(
        "--max-polls",
        type=int,
        default=None,
        help="Optional hard cap on polling iterations for test runs.",
    )
    parser.add_argument(
        "--trigger-on-start",
        action="store_true",
        default=False,
        help="Trigger one daemon cycle immediately on startup.",
    )
    parser.add_argument(
        "--journal-no-change",
        action="store_true",
        default=False,
        help="Append journal entries even when no watched signals changed.",
    )

    args = parser.parse_args(argv)
    raise SystemExit(run_factory_trigger_loop(args))


if __name__ == "__main__":
    main()
