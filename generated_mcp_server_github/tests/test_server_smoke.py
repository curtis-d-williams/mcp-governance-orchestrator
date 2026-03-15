
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server

def test_list_tools():
    tools = server.list_tools()
    assert tools == {
  "list_repositories": {},
  "get_repository": {
    "params": [
      "repo"
    ]
  },
  "create_issue": {
    "params": [
      "repo",
      "title",
      "body"
    ]
  }
}
