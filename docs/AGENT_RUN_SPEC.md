# Agent Run Spec (Mechanical Executor)

This spec operationalizes AEP.md into a repeatable executor workflow.

The executor may run commands only.
The executor may not change policy.

---

## Preconditions (Stop if violated)

- Factory repo working tree must be clean
- Executor is uncertain whether an edit touches policy surface

---

## Standard Command

From the factory repo root, run:

    python tools/agent_runner.py --template guardian_skeleton --out /tmp/mcp_new_repo

Outputs:

- artifacts/agent_run_report.json (canonical JSON)

---

## Stop Conditions

Stop immediately if:

- preflight_clean_tree fails
- factory_create fails
- validate_generated_repo fails
- any invariants fail
- determinism differs across repeated runs

Escalate to Authority with:

- artifacts/agent_run_report.json
- stdout/stderr
- exact commands executed
