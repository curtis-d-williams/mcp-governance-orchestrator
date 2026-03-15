# tests/test_all_schema_tools_dynamic.py

import inspect
from generated_mcp_server_github import server

# Simple dummy values for parameter types
DUMMY_VALUES = {
    "repo": "example-repo",
    "title": "Test Title",
    "body": "Test Body"
}

def main():
    print("Dynamic schema-aware tool test starting...\n")
    for name, func in inspect.getmembers(server, inspect.isfunction):
        if not name.startswith("_") and name != "main":  # skip internal functions and server entrypoint
            sig = inspect.signature(func)
            args = [DUMMY_VALUES.get(p.name, f"dummy_{p.name}") for p in sig.parameters.values()]
            try:
                result = func(*args)
                print(f"{name} output: {result}")
            except Exception as e:
                print(f"{name} raised an exception: {e}")

if __name__ == "__main__":
    main()
