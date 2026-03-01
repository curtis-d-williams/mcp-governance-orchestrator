from mcp_governance_orchestrator.server import run_guardians

def test_fail_closed_propagates() -> None:
    out = run_guardians(
        repo_path='.',
        guardians=[
            'mcp-release-guardian:v1',
            'mcp-repo-hygiene-guardian:v1',
        ],
    )

    assert out['ok'] is False
    assert out['fail_closed'] is True
