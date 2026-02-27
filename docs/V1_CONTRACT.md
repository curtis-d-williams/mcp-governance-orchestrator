# mcp-governance-orchestrator — V1 Contract (Stubbed Wiring)

Status: V1 frozen (effective at tag v0.1.0)

This document defines the V1 contract for the mcp-governance-orchestrator MCP server.

V1 is intentionally narrow: a deterministic, network-free, read-only orchestrator that aggregates Guardian Primitive outputs without interpretation.

NOTE: In V1, guardian invocation is intentionally **not wired**. The orchestrator remains a deterministic wrapper that fail-closes per-guardian with a stable stub result.

---

## 1. Tool Surface (V1)

V1 exposes exactly one tool:

- `run_guardians(repo_path: string, guardians: array<string>) -> object`

No other tools are part of V1.

---

## 2. V1 Scope (Hard Boundary)

### 2.1 What V1 does

`run_guardians(repo_path, guardians)`:

- Validates inputs deterministically (fail-closed).
- Preserves the input order of `guardians` in the output.
- Produces an aggregation object with:
  - `tool`, `repo_path`, `ok`, `fail_closed`, `guardians`.

For each requested guardian ID:
- If guardian ID is unknown: returns a fail-closed guardian entry with `invoked=false`, `output=null`.
- If guardian ID is known but not wired (V1): returns a fail-closed guardian entry with `invoked=false`, `output=null`, `details="fail-closed: guardian_not_wired"`.

### 2.2 What V1 explicitly does NOT do (Non-Goals)

V1 does not:

- invoke external MCP servers
- make network calls
- call GitHub APIs
- execute repository code
- write to disk or mutate repo state
- normalize or rewrite guardian outputs
- score, rank, infer, or recommend
- add “summary” interpretations
- introduce heuristics or policy interpretation

If a capability is not explicitly listed in “What V1 does,” it is out of scope.

---

## 3. Determinism and Fail-Closed Semantics

### 3.1 Determinism requirements

For identical inputs, output must be identical:

- stable keys and types
- stable ordering
- stable guardian_id strings (echo)
- stable `details` strings
- no timestamps, randomness, or environment-dependent text

### 3.2 Fail-closed requirements

- If `repo_path` is invalid or empty: `ok=false`, `fail_closed=true`.
- If `guardians` is empty or not a list: `ok=false`, `fail_closed=true`.
- If any guardian entry is fail-closed: overall `ok=false`, `fail_closed=true`.

V1 never downgrades failures.

---

## 4. Output Schema (V1)

Top-level JSON object contains exactly:

- `tool` (string) — always `"run_guardians"`
- `repo_path` (string)
- `ok` (boolean)
- `fail_closed` (boolean)
- `guardians` (array)

No additional top-level keys are part of V1.

Each `guardians[]` item contains exactly:

- `guardian_id` (string)
- `invoked` (boolean)
- `ok` (boolean)
- `fail_closed` (boolean)
- `output` (object | null)
- `details` (string)

### 4.1 Ordering (Frozen)

The `guardians` array preserves the input order. No sorting.

---

## 5. Backward Compatibility Rule

After tag v0.1.0:

- Tool name and signature are frozen.
- Top-level schema is frozen.
- `guardians[]` item schema is frozen.
- Ordering rule is frozen.
- V1 must remain non-interpretive and deterministic.

Any breaking change requires a new major version (V2) and an explicit contract document.

---

## 6. Canonical Examples

Canonical example outputs are defined in `docs/EXAMPLE_OUTPUTS.md` and are part of the V1 contract.