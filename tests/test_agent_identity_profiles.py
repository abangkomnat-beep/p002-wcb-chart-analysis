import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
PROJECT = REPO.parent
EXPECTED = {f"{number:02d}" for number in range(11)}


def test_every_p002_agent_has_identity_and_soul_loaded():
    agent_dirs = {path.name[:2]: path for path in (PROJECT / "Agents").iterdir()
                  if path.is_dir() and path.name[:2].isdigit()}
    assert set(agent_dirs) == EXPECTED
    for agent_id, folder in agent_dirs.items():
        identity = (folder / "IDENTITY-SOUL.md").read_text(encoding="utf-8")
        contract = (folder / "AGENTS.md").read_text(encoding="utf-8")
        assert "## Identity" in identity, agent_id
        assert "## Soul" in identity, agent_id
        assert "IDENTITY-SOUL.md" in contract, agent_id
        assert "หลักฐาน" in identity or "Evidence" in identity, agent_id


def test_machine_profiles_cover_actual_registry_without_role_collisions():
    profiles = []
    for path in sorted((REPO / "config" / "agents").glob("agent-*.json")):
        profiles.append(json.loads(path.read_text(encoding="utf-8")))
    assert {profile["agent_id"] for profile in profiles} == EXPECTED
    assert len(profiles) == 11
    assert len({profile["name"] for profile in profiles}) == 11
    for profile in profiles:
        assert profile["schema"] == "agent-identity-v1"
        assert profile["identity_version"].endswith("-v2")
        assert profile["soul"]["values"]
        assert profile["soul"]["non_negotiables"]
        assert profile["examples"]
        assert profile["self_check"]


def test_schema_allows_all_active_agent_ids():
    schema = json.loads((REPO / "schemas" / "agent-identity-v1.schema.json")
                        .read_text(encoding="utf-8"))
    assert set(schema["properties"]["agent_id"]["enum"]) == EXPECTED
