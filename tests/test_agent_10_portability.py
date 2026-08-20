import json
import re
import shutil
from pathlib import Path
from urllib.parse import unquote


REPO = Path(__file__).resolve().parents[1]
SKILL_NAME = "direct-p002-market-visuals"
SKILL_DIR = REPO / ".claude" / "skills" / SKILL_NAME
PROFILE = REPO / "config" / "agents" / "agent-10-visual-director.json"
IDENTITY_SCHEMA = REPO / "schemas" / "agent-identity-v1.schema.json"
MATRIX = REPO / "docs" / "AGENT-SKILL-MATRIX.md"
LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
MACHINE_PATH = re.compile(r"(?i)(?:\b[A-Z]:[\\/]|/(?:Users|home)/[^/\s]+/)")
SECRET_PATH = re.compile(r"(?i)(?:^|[\s('`\"])(?:\.secrets|secrets?)/")
EMBEDDED_ID = re.compile(
    r"(?i)(?:\bsk-[A-Za-z0-9_-]{8,}|\b(?:provider|model|api[_ -]?key)[_ -]?id\s*[:=])"
)


def _frontmatter(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines and lines[0] == "---", f"missing frontmatter: {path}"
    try:
        end = lines.index("---", 1)
    except ValueError as exc:
        raise AssertionError(f"unterminated frontmatter: {path}") from exc
    result: dict[str, str] = {}
    for line in lines[1:end]:
        if ":" not in line or line.startswith((" ", "\t")):
            continue
        key, value = line.split(":", 1)
        result[key.strip()] = value.strip()
    return result


def _markdown_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.md") if path.is_file())


def _assert_links_are_portable(root: Path, repo_root: Path) -> None:
    repo_root = repo_root.resolve()
    for markdown in _markdown_files(root):
        text = markdown.read_text(encoding="utf-8")
        for raw_target in LINK.findall(text):
            target = unquote(raw_target.split("#", 1)[0].strip())
            if not target or target.startswith(("https://", "http://", "mailto:")):
                continue
            assert not MACHINE_PATH.search(target), (markdown, target)
            assert not Path(target).is_absolute(), (markdown, target)
            resolved = (markdown.parent / target).resolve()
            assert resolved.is_relative_to(repo_root), (markdown, target, resolved)
            assert resolved.exists(), (markdown, target, resolved)


def test_skill_is_discoverable_and_has_complete_frontmatter():
    discovered = {path.parent.name: path for path in
                  (REPO / ".claude" / "skills").glob("*/SKILL.md")}
    assert SKILL_NAME in discovered
    metadata = _frontmatter(discovered[SKILL_NAME])
    assert metadata["name"] == SKILL_NAME
    assert metadata.get("description")


def test_skill_links_and_identity_survive_an_isolated_repo_copy(tmp_path):
    _assert_links_are_portable(SKILL_DIR, REPO)

    isolated_repo = tmp_path / "portable-repo"
    isolated_skill = isolated_repo / ".claude" / "skills" / SKILL_NAME
    shutil.copytree(SKILL_DIR, isolated_skill)
    _assert_links_are_portable(isolated_skill, isolated_repo)

    skill_text = (isolated_skill / "SKILL.md").read_text(encoding="utf-8")
    all_skill_text = "\n".join(
        path.read_text(encoding="utf-8") for path in _markdown_files(isolated_skill)
    )
    assert "references/identity.md" in skill_text
    assert "Agents/10-Visual-Director" not in all_skill_text
    assert (isolated_skill / "references" / "identity.md").is_file()


def test_machine_profile_schema_and_registry_cover_agent_10():
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    schema = json.loads(IDENTITY_SCHEMA.read_text(encoding="utf-8"))
    matrix = MATRIX.read_text(encoding="utf-8")

    assert profile["schema"] == "agent-identity-v1"
    assert profile["agent_id"] == "10"
    assert profile["identity_version"].endswith("-v2")
    assert "10" in schema["properties"]["agent_id"]["enum"]
    assert "Visual Director (10)" in matrix
    assert f"`{SKILL_NAME}`" in matrix


def test_skill_contains_no_machine_path_secret_path_or_embedded_provider_id():
    for path in _markdown_files(SKILL_DIR):
        text = path.read_text(encoding="utf-8")
        assert not MACHINE_PATH.search(text), path
        assert not SECRET_PATH.search(text), path
        assert not EMBEDDED_ID.search(text), path
