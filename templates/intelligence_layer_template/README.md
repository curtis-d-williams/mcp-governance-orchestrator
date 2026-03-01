


# Tier 3 Intelligence Layer — Template Guide

## Overview
Tier 3 guardians are **suggestion-only, deterministic**, and **do not enforce policy**. They can produce analysis, metrics, or evidence artifacts without affecting Tier 1/2 enforcement.

## Registration
All Tier 3 templates are registered in the **central registry**:

```json
{
  "intelligence_layer_template:v1": "templates/intelligence_layer_template.server"
}
```
The orchestrator dynamically loads this registry at startup.

Each Tier 3 template must call  in :

```python
from .guardian_registry import register_guardian

register_guardian(
    guardian_id="intelligence_layer_template:v1",
    module_path="templates.intelligence_layer_template.server",
    description="Tier 3 intelligence layer template - suggestion-only, deterministic"
)
```


## Invocation
Call Tier 3 guardians via run_guardians:

```python
from mcp_governance_orchestrator.server import run_guardians

out = run_guardians(
    guardians=["intelligence_layer_template:v1"],
    repo_path=".",
)
```

- invoked: true indicates the template ran.
- ok: true indicates successful execution.
- output contains deterministic JSON results.

## Canonical Example Output
Stored at templates/intelligence_layer_template/example_output.json:

```json
{
  "fail_closed": false,
  "guardians": [
    {
      "fail_closed": false,
      "guardian_id": "intelligence_layer_template:v1",
      "invoked": true,
      "ok": true,
      "output": {}
    }
  ],
  "ok": true,
  "repo_path": ".",
  "tool": "run_guardians"
}
```

## Adding New Tier 3 Templates
1. Create a new template directory under templates/.
2. Ensure it is a Python package (__init__.py present).
3. Implement server.py with deterministic outputs.
4. Register in server.py with register_guardian.
5. Add entry to config/guardians.json.
6. Test with run_guardians([<guardian_id>]).
7. Update canonical example output and documentation.
