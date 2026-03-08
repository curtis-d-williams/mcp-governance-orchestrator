import pytest
import templates.sample_template.server as sample

def test_cross_repo_tier3_aggregation():
    # Mock outputs from multiple templates / guardians
    guardians_outputs = [
        sample.main(),
        sample.main(),  # duplicate to simulate multiple repos
    ]

    # Ensure deterministic ordering
    ordered_ids = [g["suggestions"]["suggestion_id"] for g in guardians_outputs] 
    assert ordered_ids == sorted(ordered_ids), "Tier 3 suggestions not deterministically ordered"

    # Ensure fail_closed is not True (cannot affect frozen invariants)
    for g in guardians_outputs:
        assert g["fail_closed"] is False

    # Aggregate suggestions safely
    aggregated = {g["suggestions"]["suggestion_id"]: g["suggestions"] for g in guardians_outputs}
    assert "sample_template_example" in aggregated
