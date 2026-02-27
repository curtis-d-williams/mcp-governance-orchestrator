### Real E2E Example Output — v0.2.1

This example demonstrates a clean installation and verification of mcp-governance-orchestrator with the release_guardian optional extra in a new virtual environment.

\`\`\`bash
rm -rf /tmp/mgo_e2e_021
python3 -m venv /tmp/mgo_e2e_021
source /tmp/mgo_e2e_021/bin/activate
python -m pip install -U pip
python -V
python -m pip -V

mkdir -p /tmp/mgo_release
cd /tmp/mgo_release
curl -L -O https://github.com/curtis-d-williams/mcp-governance-orchestrator/archive/refs/tags/v0.2.1.tar.gz

python -m pip install /tmp/mgo_release/v0.2.1.tar.gz
python -m pip show mcp-governance-orchestrator

python -m pip install "mcp-release-guardian==0.1.4"
python -m pip show mcp-release-guardian
\`\`\`

#### Expected Output
\`\`\`text
python -m pip show mcp-governance-orchestrator
Name: mcp-governance-orchestrator
Version: 0.2.1
Summary: Deterministic MCP server for validating repository policy governance artifacts
Location: /private/tmp/mgo_e2e_021/lib/python3.13/site-packages
Requires: fastmcp

python -m pip show mcp-release-guardian
Name: mcp-release-guardian
Version: 0.1.4
Summary: Deterministic MCP server for validating release hygiene in local repositories
Location: /private/tmp/mgo_e2e_021/lib/python3.13/site-packages
Requires: fastmcp
\`\`\`
