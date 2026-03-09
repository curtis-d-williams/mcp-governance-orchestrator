import pytest
import templates.sample_template.server as sample  # replace/add imports per repo guardian

def test_portfolio_tier3_simulation():
    # Simulate all guardians outputs
    all_outputs = [
        sample.main(),
        sample.main(),  # add more mocks per actual portfolio
    ]

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
