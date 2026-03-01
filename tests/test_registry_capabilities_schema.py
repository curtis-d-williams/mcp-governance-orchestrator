from mcp_governance_orchestrator.registry import normalize_registry


def test_capabilities_schema_rejects_non_object_capabilities():
    raw = {
        "bad_caps:v1": {
            "module_path": "templates.repo_insights.server",
            "callable": "main",
            "tier": 3,
            "description": "",
            "capabilities": "not-an-object",
        }
    }

    try:
        normalize_registry(raw)
        assert False, "Expected ValueError for non-object capabilities"
    except ValueError as e:
        assert "Invalid capabilities format" in str(e)


def test_capabilities_schema_accepts_valid_minimal_object():
    raw = {
        "good_caps:v1": {
            "module_path": "templates.repo_insights.server",
            "callable": "main",
            "tier": 3,
            "description": "",
            "capabilities": {
                "domain": "repo",
                "checks": ["repo_insights_summary"],
                "io": {"reads_repo": True, "reads_network": False, "writes_repo": False},
                "outputs": {"suggestions": True, "findings": False, "metrics": True},
                "notes": "ok",
            },
        }
    }

    out = normalize_registry(raw)
    meta = out["good_caps:v1"]
    assert meta["capabilities"]["domain"] == "repo"
    assert meta["capabilities"]["checks"] == ["repo_insights_summary"]


def test_capabilities_schema_error_messages_are_deterministic():
    # Importing the helper is acceptable for unit-level determinism tests.
    from mcp_governance_orchestrator.registry import _validate_capabilities_schema  # type: ignore

    errs = _validate_capabilities_schema(
        {
            "domain": 123,
            "checks": ["ok", 5],
            "io": {"reads_repo": "yes", "writes_repo": False},
            "outputs": {"suggestions": "true"},
            "notes": 7,
        }
    )

    assert errs == [
        "capabilities.domain must be a string",
        "capabilities.checks must be a list of strings",
        "capabilities.notes must be a string",
        "capabilities.io.reads_repo must be a boolean",
        "capabilities.outputs.suggestions must be a boolean",
    ]
