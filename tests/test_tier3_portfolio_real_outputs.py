import pytest

import importlib

# List of Tier 3 guardians to simulate
tier3_guardians = [
    "templates.intelligence_layer_template.server",
    "templates.repo_insights.server",
    "templates.sample_template.server",
]

def test_tier3_portfolio_real_outputs():
    all_outputs = []
    for mod_path in tier3_guardians:
        mod = importlib.import_module(mod_path)
        output = mod.main()
        all_outputs.append(output)

    # Deterministic ordering
    suggestion_ids = [g["suggestions"]["suggestion_id"] for g in all_outputs]
    assert suggestion_ids == sorted(suggestion_ids), "Non-deterministic ordering detected"

    # fail_closed must remain False
    for g in all_outputs:
        assert g["fail_closed"] is False

    # Aggregate safely
    aggregated = {g["suggestions"]["suggestion_id"]: g["suggestions"] for g in all_outputs}
    for g in all_outputs:
        assert g["suggestions"]["suggestion_id"] in aggregated
