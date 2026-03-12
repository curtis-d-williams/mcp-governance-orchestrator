import {{module_name}}


def test_get_adapter_metadata():
    metadata = {{module_name}}.get_adapter_metadata()
    assert metadata["artifact_kind"] == "agent_adapter"
    assert metadata["provider"] == "{{provider}}"
    assert metadata["status"] == "ok"
