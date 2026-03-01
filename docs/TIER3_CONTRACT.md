# Tier 3 Contract (Intelligence Layer)

Tier 3 guardians are **suggestion-only** intelligence layers. They may emit guidance, recommendations, and metrics, but they must never enforce policy or affect Tier 1/2 execution semantics.

This contract is **governance-grade**: future Tier 3 templates must conform without exception.

## Scope

Tier 3 applies to any guardian whose module path begins with `templates.` as loaded by the orchestrator registry (`config/guardians.json`).

## Hard invariants

### Non-enforcement
- Tier 3 must never enforce policy.
- Tier 3 must never set `fail_closed = True`.
- Tier 3 must not cause orchestrator-wide failure unless the orchestrator itself fails.

### Determinism
- Given the same repository state, Tier 3 outputs must be deterministic.
- No randomness, time-based values, nondeterministic iteration, or external state.

### No side effects
- Tier 3 must be read-only:
  - No file writes
  - No network calls
  - No shelling out
  - No modifying git state

### Contract-compliant output
Tier 3 guardians must return a JSON-serializable dict containing:

Required keys:
- `tool`: stable identifier string for the guardian (e.g., `"intelligence_layer_template"`)
- `ok`: boolean (`True` if the guardian ran and produced output)
- `fail_closed`: boolean (must be `False` for Tier 3)

Recommended keys:
- `suggestions`: a deterministic object containing suggestion artifacts (ids, descriptions, metrics, notes, etc.)

## Invocation model

Tier 3 templates are invoked by the orchestrator via a routing table entry:
- Module path from `config/guardians.json`
- Callable name `"main"`

Tier 3 templates may use either callable shape:

- `main() -> dict` (preferred for templates)
- `main(repo_path: str) -> dict` (allowed if consistent)

The orchestrator may adapt invocation, but the return contract must always hold.

## Versioning

Any change to this document is a contract change and requires:
- Explicit changelog entry
- A tagged release
- Updated regression tests

