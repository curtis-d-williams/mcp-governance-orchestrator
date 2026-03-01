# mcp-governance-orchestrator

Deterministic, network-free, read-only orchestrator that aggregates MCP “guardian” outputs without interpretation.

## V1 Contract

See:
- `docs/V1_CONTRACT.md`
- `docs/EXAMPLE_OUTPUTS.md`

## Adding a guardian (V1)

V1 is intentionally static:
- Add a new guardian by inserting a single entry in the orchestrator routing table (see `src/mcp_governance_orchestrator/server.py`).
- No dynamic discovery/registry/plugins.
- Guardian outputs are preserved verbatim; the orchestrator does not normalize or reinterpret them.

After adding a routing entry, install the guardian package locally and run a composed invocation. Canonical composed JSON examples are captured in `docs/EXAMPLE_OUTPUTS.md`.

## Development

```bash
pytest -q
python3 -m build --sdist --wheel

```

## Optional: install release guardian

The orchestrator can invoke `mcp-release-guardian:v1` in-process when the release guardian package is installed. If it is not installed, invocation fail-closes deterministically with `fail-closed: guardian_import_failed`.

Install:

```bash
pip install "mcp-governance-orchestrator[release_guardian]==0.2.1"


```

## Create a new MCP repo (factory)

This repository includes a deterministic scaffold script that creates a new MCP repository from the golden template and verifies Tier-1 compliance using the installed orchestrator distribution (treat as 0.2.3 until explicitly upgraded).

Prerequisites:
- Python 3.11+
- mcp-governance-orchestrator installed (editable is fine)
- Guardians installed:
  - mcp-repo-hygiene-guardian:v1
  - mcp-release-guardian:v1

Create a new repository:

    ./tools/scaffold_new_mcp.sh mcp-my-domain-guardian

The script will:
- Copy the golden scaffold (mcp-test-guardian)
- Initialize git and commit
- Run Tier-1 guardians deterministically
- Write canonical JSON to docs/EXAMPLE_OUTPUTS.md
- Commit the canonical output
