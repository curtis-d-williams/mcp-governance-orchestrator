# Agent Execution Protocol (AEP) — v0.1

This protocol defines how automated agents may interact with the
MCP Automation Factory.

Agents are mechanical executors only.

Authority retains policy control.

---

# Roles

Authority:
Approves template changes, policy semantics, schema changes.

Executor (Agent):
Runs mechanical steps. May not mutate policy.

Guardian:
Enforces invariants. Blocks drift.

---

# Allowed Agent Operations

- Run factory scaffold commands
- Run deterministic validation
- Regenerate example outputs
- Commit evidence artifacts
- Bump versions when explicitly instructed
- Open pull requests summarizing results

---

# Disallowed Agent Actions

- Modify guardian logic
- Change canonical JSON schema
- Alter fail-closed semantics
- Introduce nondeterminism
- Modify aggregation rules
- Introduce network calls
- Silence invariant failures

If uncertainty exists, the agent must stop.

---

# Required Verification Gates

1. Invariant Gate  
   Structural checks must pass.

2. Determinism Gate  
   Repeated executions must produce byte-identical outputs.

3. Evidence Gate  
   EXAMPLE_OUTPUTS must be reproducible.

4. Composition Gate  
   Aggregation semantics must match specification.

5. CI Gate  
   Required workflows must pass.

Failure at any gate halts execution.

---

# Stop Conditions

The agent must stop if:

- An invariant fails
- Determinism breaks
- Policy semantics appear to change
- A decision requires interpretation

Agents escalate to Authority rather than proceed.

---

# Executor Output Standard

When completing a task, the agent must provide:

- Commands executed
- Files modified
- Canonical JSON artifacts
- Confirmation: "No policy semantics modified"
- Evidence supporting that confirmation