import json
from pathlib import Path
from .guardian_registry import register_guardian  # new central registry

# Dynamic guardian registry loading
registry_file = Path(__file__).parent.parent.parent / "config" / "guardians.json"
if registry_file.exists():
    with open(registry_file) as f:
        registry = json.load(f)
    for guardian_id, module_path in registry.items():
        register_guardian(guardian_id, module_path)

# (Existing orchestrator code below remains untouched)
