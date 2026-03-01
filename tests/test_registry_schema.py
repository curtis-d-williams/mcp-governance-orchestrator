import json
from pathlib import Path


def _canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def test_registry_schema_and_determinism():
    registry_path = Path(__file__).resolve().parents[1] / "config" / "guardians.json"
    assert registry_path.exists()

    raw = registry_path.read_text(encoding="utf-8")
    data = json.loads(raw)

    # 1) Top-level must be dict
    assert isinstance(data, dict)

    for guardian_id, entry in data.items():
        # 2) guardian_id must be string
        assert isinstance(guardian_id, str)
        assert guardian_id

        # 3) Entry may be legacy string
        if isinstance(entry, str):
            assert entry  # non-empty module_path
            continue

        # 4) Or structured dict
        assert isinstance(entry, dict)

        # Required: module_path
        assert "module_path" in entry
        assert isinstance(entry["module_path"], str)
        assert entry["module_path"]

        # Optional: callable
        if "callable" in entry:
            assert isinstance(entry["callable"], str)

        # Optional: tier
        if "tier" in entry:
            assert isinstance(entry["tier"], int)

        # Optional: description
        if "description" in entry:
            assert isinstance(entry["description"], str)

    # 5) Deterministic canonicalization round-trip
    canon1 = _canonical(data)
    canon2 = _canonical(json.loads(canon1))
    assert canon1 == canon2
