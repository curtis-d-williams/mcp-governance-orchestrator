from mcp_governance_orchestrator.policy import evaluate_policy


def _guardians():
    return [
        {
            "guardian_id": "g1:v1",
            "tier": 2,
            "capabilities": {
                "outputs": {"findings": True},
                "io": {"writes_repo": False},
            },
        },
        {
            "guardian_id": "g2:v1",
            "tier": 3,
            "capabilities": {
                "outputs": {"suggestions": True},
                "io": {"writes_repo": False},
            },
        },
    ]


def test_backward_compatible_no_select_means_all_guardians_selected():
    policy = {"require": [{"tier": 2}]}
    result = evaluate_policy(policy, _guardians())
    assert result["ok"] is True
    assert result["selection"]["selected_guardians"] == ["g1:v1", "g2:v1"]
    assert result["summary"]["selected_total"] == 2


def test_select_scopes_require():
    policy = {
        "select": [{"tier": 3}],
        "require": [{"capabilities.outputs.findings": True}],
    }
    result = evaluate_policy(policy, _guardians())
    assert result["ok"] is False
    assert result["selection"]["selected_guardians"] == ["g2:v1"]
    assert result["summary"]["selected_total"] == 1
    assert result["summary"]["require_passed"] == 0


def test_select_scopes_forbid():
    policy = {
        "select": [{"tier": 3}],
        "forbid": [{"tier": 2}],
    }
    result = evaluate_policy(policy, _guardians())
    assert result["ok"] is True
    assert result["summary"]["forbid_passed"] == 1


def test_disallow_tier3_only_fail_with_select():
    policy = {
        "select": [{"tier": 3}],
        "constraints": {"disallow_tier3_only": True},
    }
    result = evaluate_policy(policy, _guardians())
    assert result["ok"] is False
    assert result["constraints"][0]["name"] == "disallow_tier3_only"
    assert result["constraints"][0]["details"] == "all_selected_guardians_are_tier3"


def test_min_selected_pass():
    policy = {
        "select": [{"tier": 2}],
        "constraints": {"min_selected": 1},
    }
    result = evaluate_policy(policy, _guardians())
    assert result["ok"] is True
    assert result["constraints"][0]["name"] == "min_selected"


def test_min_selected_fail():
    policy = {
        "select": [{"tier": 2}],
        "constraints": {"min_selected": 2},
    }
    result = evaluate_policy(policy, _guardians())
    assert result["ok"] is False
    assert result["constraints"][0]["name"] == "min_selected"
    assert "selected_total" in result["constraints"][0]["details"]


def test_max_selected_pass():
    policy = {
        "constraints": {"max_selected": 2},
    }
    result = evaluate_policy(policy, _guardians())
    assert result["ok"] is True
    assert result["constraints"][0]["name"] == "max_selected"


def test_max_selected_fail():
    policy = {
        "constraints": {"max_selected": 1},
    }
    result = evaluate_policy(policy, _guardians())
    assert result["ok"] is False
    assert result["constraints"][0]["name"] == "max_selected"
    assert "selected_total" in result["constraints"][0]["details"]


def test_require_tiers_pass():
    policy = {
        "constraints": {"require_tiers": [2, 3]},
    }
    result = evaluate_policy(policy, _guardians())
    assert result["ok"] is True
    assert result["constraints"][0]["name"] == "require_tiers"
    assert result["constraints"][0]["present_tiers"] == [2, 3]


def test_require_tiers_fail():
    policy = {
        "select": [{"tier": 2}],
        "constraints": {"require_tiers": [2, 3]},
    }
    result = evaluate_policy(policy, _guardians())
    assert result["ok"] is False
    assert result["constraints"][0]["name"] == "require_tiers"
    assert "missing_tiers" in result["constraints"][0]["details"]
