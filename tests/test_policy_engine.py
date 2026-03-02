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


def test_require_success():
    policy = {
        "require": [
            {"tier": 2},
            {"capabilities.outputs.findings": True},
        ]
    }
    result = evaluate_policy(policy, _guardians())
    assert result["ok"] is True
    assert result["summary"]["require_passed"] == 2


def test_require_failure():
    policy = {
        "require": [
            {"tier": 1}
        ]
    }
    result = evaluate_policy(policy, _guardians())
    assert result["ok"] is False
    assert result["summary"]["require_passed"] == 0


def test_forbid_success():
    policy = {
        "forbid": [
            {"capabilities.io.writes_repo": True}
        ]
    }
    result = evaluate_policy(policy, _guardians())
    assert result["ok"] is True
    assert result["summary"]["forbid_passed"] == 1


def test_forbid_failure():
    policy = {
        "forbid": [
            {"tier": 2}
        ]
    }
    result = evaluate_policy(policy, _guardians())
    assert result["ok"] is False
    assert result["summary"]["forbid_passed"] == 0


def test_disallow_tier3_only_pass():
    policy = {
        "constraints": {
            "disallow_tier3_only": True
        }
    }
    result = evaluate_policy(policy, _guardians())
    assert result["ok"] is True


def test_disallow_tier3_only_fail():
    guardians = [
        {
            "guardian_id": "g3:v1",
            "tier": 3,
            "capabilities": {},
        }
    ]
    policy = {
        "constraints": {
            "disallow_tier3_only": True
        }
    }
    result = evaluate_policy(policy, guardians)
    assert result["ok"] is False
