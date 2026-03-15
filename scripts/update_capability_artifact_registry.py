# SPDX-License-Identifier: MIT
"""Deterministically update the capability artifact registry from one factory cycle.

Consumes an autonomous factory cycle artifact and persists the latest accepted
artifact per capability, with deterministic revision/history metadata.

Behavior:
- only records accepted syntheses (synthesis_event.status == "ok")
- prefers evolved_builder.generated_repo when present
- otherwise uses synthesis_event.generated_repo, then builder.generated_repo
- appends a new history entry only when the accepted artifact path changes
- keeps deterministic JSON formatting (indent=2, sort_keys=True, trailing newline)
- fails closed on invalid existing registry shape
"""

import argparse
import json
import sys
from pathlib import Path


def _write_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _try_read_json(path):
    p = Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _extract_registration(artifact):
    if not isinstance(artifact, dict):
        return None

    cycle_result = artifact.get("cycle_result") or {}
    if not isinstance(cycle_result, dict):
        return None

    synthesis_event = cycle_result.get("synthesis_event") or {}
    if not isinstance(synthesis_event, dict):
        return None

    if synthesis_event.get("status") != "ok":
        return None

    capability = synthesis_event.get("capability")
    artifact_kind = synthesis_event.get("artifact_kind")
    source = synthesis_event.get("source")
    used_evolution = synthesis_event.get("used_evolution", False)

    evolved_builder = cycle_result.get("evolved_builder") or {}
    builder = cycle_result.get("builder") or {}

    artifact_path = None
    if isinstance(evolved_builder, dict):
        artifact_path = evolved_builder.get("generated_repo")
    if artifact_path is None and isinstance(synthesis_event, dict):
        artifact_path = synthesis_event.get("generated_repo")
    if artifact_path is None and isinstance(builder, dict):
        artifact_path = builder.get("generated_repo")

    if not capability or not artifact_kind or not artifact_path:
        return None

    return {
        "capability": capability,
        "artifact_kind": artifact_kind,
        "artifact": artifact_path,
        "source": source,
        "status": "ok",
        "used_evolution": bool(used_evolution),
    }


def update_capability_artifact_registry(registry_path, cycle_artifact_path):
    try:
        artifact = json.loads(Path(cycle_artifact_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"error: cannot read cycle artifact: {exc}\n")
        return 1

    existing = _try_read_json(registry_path)
    if existing is None:
        existing = {"capabilities": {}}

    capabilities = existing.get("capabilities")
    if not isinstance(capabilities, dict):
        sys.stderr.write("error: capability artifact registry must contain 'capabilities' as an object\n")
        return 1

    registration = _extract_registration(artifact)
    if registration is None:
        _write_json(registry_path, {"capabilities": capabilities})
        return 0

    capability = registration["capability"]
    row = capabilities.get(capability)

    if row is None:
        revision = 1
        history = []
    else:
        if not isinstance(row, dict):
            sys.stderr.write("error: capability registry row must be an object\n")
            return 1
        history = row.get("history")
        if not isinstance(history, list):
            sys.stderr.write("error: capability registry row must contain 'history' as a list\n")
            return 1
        latest_artifact = row.get("latest_artifact")
        current_revision = row.get("revision")
        if not isinstance(current_revision, int) or current_revision < 0:
            sys.stderr.write("error: capability registry row must contain non-negative integer 'revision'\n")
            return 1
        if latest_artifact == registration["artifact"]:
            _write_json(registry_path, {"capabilities": {k: capabilities[k] for k in sorted(capabilities)}})
            return 0
        revision = current_revision + 1

    entry = {
        "artifact": registration["artifact"],
        "revision": revision,
        "source": registration["source"],
        "status": registration["status"],
        "used_evolution": registration["used_evolution"],
    }

    capabilities[capability] = {
        "artifact_kind": registration["artifact_kind"],
        "history": history + [entry],
        "latest_artifact": registration["artifact"],
        "revision": revision,
    }

    result = {
        "capabilities": {
            key: capabilities[key]
            for key in sorted(capabilities)
        }
    }
    _write_json(registry_path, result)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Update capability artifact registry from an autonomous factory cycle artifact."
    )
    parser.add_argument("--registry", required=True, metavar="FILE",
                        help="Path to capability_artifact_registry.json.")
    parser.add_argument("--cycle-artifact", required=True, metavar="FILE",
                        help="Path to autonomous factory cycle artifact JSON.")
    args = parser.parse_args(argv)

    sys.exit(
        update_capability_artifact_registry(
            registry_path=args.registry,
            cycle_artifact_path=args.cycle_artifact,
        )
    )


if __name__ == "__main__":
    main()
