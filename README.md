# mcp-governance-orchestrator

Deterministic, network-free, read-only orchestrator that aggregates MCP “guardian” outputs without interpretation.

## V1 Contract

See:
- `docs/V1_CONTRACT.md`
- `docs/EXAMPLE_OUTPUTS.md`

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
