# Guardian Orchestrator Contract — V0 (Design-Only)

Status: V0 (design-only, not implemented)
Applies to: Any future MCP that composes multiple Guardian Primitives
Non-binding on current repos until explicitly adopted and versioned

This document defines the **orchestrator contract** for composing Guardian Primitives while preserving the Guardian Primitive Pattern: deterministic, fail-closed, schema-stable, non-heuristic.

The orchestrator is an **aggregator**, not an interpreter.

---

## 1. Purpose

The orchestrator:

- invokes one or more Guardian Primitives against a target input (e.g., repo_path)
- collects each primitive’s output **verbatim**
- returns a single deterministic aggregation object

The orchestrator MUST NOT:

- score
- rank
- infer
- recommend
- rewrite primitive outputs
- “normalize” semantics across tools
- introduce heuristics or policy interpretation

---

## 2. Tool Surface (Planned)

V0 assumes exactly one orchestrator tool:

- `run_guardians(repo_path: string, guardians: array<string>) -> object`

Notes:
- `guardians` is an allowlist of known guardian identifiers (stable strings).
- No implicit defaults. If `guardians` is empty or unknown, fail-closed.

No other tools are part of the orchestrator surface.

---

## 3. Inputs

### 3.1 repo_path
- String path to a local repository root.
- Orchestrator is network-free and read-only.

### 3.2 guardians
- Array of stable guardian IDs (e.g., `"mcp-policy-guardian:v1"`, `"mcp-release-guardian:v1"`).
- Guardian IDs MUST be interpreted only as routing selectors.
- Unknown guardian IDs MUST cause fail-closed.

---

## 4. Determinism Requirements

Given identical:
- repo_path filesystem state
- requested guardians list (same order and values)
- identical versions of each guardian tool

The orchestrator output MUST be identical, including:
- stable top-level keys
- stable ordering
- stable error codes
- no timestamps
- no randomness
- no environment-dependent text

---

## 5. Fail-Closed Semantics

The orchestrator is fail-closed at two levels:

### 5.1 Orchestrator-level failure
If inputs are invalid (e.g., guardians list empty, unknown guardian ID, invalid repo_path):

- `ok` MUST be false
- `fail_closed` MUST be true
- no guardian invocation is performed (or, if performed, results MUST be omitted and replaced with deterministic failure stubs)
- `reason` MUST be a deterministic code

### 5.2 Guardian-level failure propagation
If any invoked guardian returns:
- `ok: false` OR
- indicates fail-closed posture (`fail_closed: true`)

Then orchestrator:
- `ok` MUST be false
- `fail_closed` MUST be true

The orchestrator MUST NOT downgrade failures or reinterpret them.

---

## 6. Output Schema (V0)

Top-level output MUST contain exactly these keys:

- `tool` (string) — always `"run_guardians"`
- `repo_path` (string) — echo input
- `ok` (boolean)
- `fail_closed` (boolean)
- `guardians` (array of objects)

No additional top-level keys are allowed without a new contract revision.

### 6.1 guardians[] item schema

Each entry in `guardians` MUST contain exactly:

- `guardian_id` (string) — echo requested guardian selector
- `invoked` (boolean)
- `ok` (boolean)
- `fail_closed` (boolean)
- `output` (object | null)
- `details` (string)

Rules:
- If `invoked` is true, `output` MUST be the guardian’s JSON output **verbatim**.
- If `invoked` is false (e.g., unknown guardian ID), `output` MUST be null and `details` MUST be deterministic.

### 6.2 Ordering (Frozen)
The `guardians` array MUST preserve the input order of the `guardians` parameter.

No sorting is allowed.

---

## 7. Verbatim Preservation Rule (Critical)

The orchestrator MUST embed each guardian output **as returned**.

Specifically, it MUST NOT:
- rename keys
- reorder checks inside guardian outputs
- remove keys
- add keys inside guardian outputs
- “normalize” fields (e.g., mapping `ok` into a new structure)
- translate or enrich detail strings

The orchestrator only wraps.

---

## 8. Composition Rules (No Interpretation)

The orchestrator MAY compute:

- overall `ok` as logical AND of guardian-level `ok`
- overall `fail_closed` as logical OR of guardian-level `fail_closed` (or equivalently `not ok` under fail-closed primitives)

The orchestrator MUST NOT compute:
- scores
- categories (e.g., “high risk”)
- maturity levels
- remediation steps
- inferred explanations

---

## 9. Backward Compatibility Rule

Once the orchestrator reaches v0.1.0 freeze:

- tool name is frozen
- signature is frozen
- top-level keys are frozen
- guardians[] schema is frozen
- ordering rules are frozen
- verbatim preservation rule is frozen

Any breaking change requires a major version increment and an explicit new contract.

---

## 10. Canonical Examples (Deferred)

Canonical examples must be added before any v0.1.0 freeze.

They must include:
- all-OK aggregation
- one guardian fail-closed
- unknown guardian ID fail-closed
- invalid repo_path fail-closed

---

End of Orchestrator Contract (V0).