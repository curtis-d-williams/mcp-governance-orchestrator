import {{module_name}}


def test_get_connector_metadata():
    metadata = {{module_name}}.get_connector_metadata()
    assert metadata["artifact_kind"] == "data_connector"
    assert metadata["provider"] == "{{provider}}"
    assert metadata["status"] == "ok"
