import pytest
import importlib

# Portfolio-wide Tier 1/2/3 guardians
portfolio_guardians = {
    "tier1": ["mcp_governance_orchestrator.smoke_guardians.tier1_smoke"],
    "tier2": ["mcp_governance_orchestrator.smoke_guardians.tier2_smoke"],
    "tier3": [
        "templates.intelligence_layer_template.server",
        "templates.repo_insights.server",
        "templates.sample_template.server",
    ]
}

def test_cross_repo_governance_simulation():
    all_outputs = []
    dummy_repo = "."  # Safe placeholder for repo_path

    # Simulate execution tier by tier
    for tier in ["tier1", "tier2", "tier3"]:
        for mod_path in portfolio_guardians[tier]:
            mod = importlib.import_module(mod_path)
            # Tier 1/2 require repo_path, Tier 3 do not
            if tier in ["tier1", "tier2"]:
                out = mod.main(dummy_repo)
            else:
                out = mod.main()
            all_outputs.append(out)

    # Deterministic ordering of Tier 3 suggestions only
    suggestion_ids = [
        g["suggestions"]["suggestion_id"]
        for g in all_outputs
        if "suggestions" in g
    ]
    assert suggestion_ids == sorted(suggestion_ids), "Non-deterministic ordering detected"

    # Fail-closed propagation: all Tier 3 must be non-enforcing
    for g in all_outputs:
        if g.get("fail_closed") is not None:
            assert g["fail_closed"] is False

    # Aggregate safely
    aggregated = {
        g["suggestions"]["suggestion_id"]: g["suggestions"]
        for g in all_outputs
        if "suggestions" in g
    }
    for g in all_outputs:
        if "suggestions" in g:
            assert g["suggestions"]["suggestion_id"] in aggregated
