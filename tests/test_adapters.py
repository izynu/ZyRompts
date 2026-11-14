"""Adapter contract: every platform tree derives from the canonical skills.

The property: a skill exists once, in `skills/<name>/SKILL.md`, and each platform
renders from it. If an adapter invents content, the platforms drift and the
"one source of truth" claim is false.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from zyrompts.adapters import (
    BUILDERS,
    AdapterResult,
    build_claude_code,
    build_codex,
    build_copilot,
    build_gemini,
    build_opencode,
    dependency_cycles,
    hooks_manifest,
    load_canonical_skills,
    parse_skill,
    plugin_manifest,
    render_claude_code,
    render_codex_index,
    render_copilot,
    render_gemini,
    render_opencode,
)


SKILLS = Path(__file__).resolve().parent.parent / "skills"


def _frontmatter_of(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    return text.split("---")[1] if text.startswith("---") else ""


@pytest.fixture(scope="module")
def skills(skills_dir):
    return load_canonical_skills(skills_dir)


def test_all_canonical_skills_parse(skills):
    assert len(skills) >= 16
    assert all(skill.name and skill.description for skill in skills)


def test_parse_skill_reads_frontmatter():
    meta = parse_skill("---\nname: demo\ndescription: does a thing\n"
                       "allowed-tools: Read, Grep\n---\n\n# Demo\n\nBody here.\n")
    assert meta.name == "demo"
    assert meta.description == "does a thing"
    assert meta.allowed_tools == "Read, Grep"
    assert "Body here." in meta.body


def test_parse_skill_survives_missing_frontmatter():
    meta = parse_skill("# Just a body\n")
    assert meta.name == "unnamed"
    assert "Just a body" in meta.body


def test_parse_skill_survives_empty_input():
    assert parse_skill("").name == "unnamed"


@pytest.mark.parametrize("render", [render_claude_code, render_gemini,
                                    render_copilot, render_opencode])
def test_every_renderer_emits_frontmatter(render, skills):
    for skill in skills:
        text = render(skill)
        assert text.startswith("---"), f"{render.__name__} lost frontmatter for {skill.name}"
        assert "description:" in text


def test_claude_code_declares_the_bare_skill_name(skills):
    for skill in skills:
        assert f"name: {skill.name}" in render_claude_code(skill)


@pytest.mark.parametrize("render", [render_gemini, render_copilot])
def test_namespaced_platforms_prefix_the_skill_name(render, skills):
    """Gemini and Copilot share a namespace with other toolkits, so they prefix."""
    for skill in skills:
        assert f"name: zy-{skill.name}" in render(skill)


def test_opencode_names_come_from_the_filename(skills):
    result = build_opencode(skills, "0.1.0")
    for skill in skills:
        assert any(p.endswith(f"zy-{skill.slug}.md") for p in result.files)


@pytest.mark.parametrize("render", [render_claude_code, render_gemini,
                                    render_copilot, render_opencode])
def test_every_renderer_keeps_the_body(render, skills):
    for skill in skills:
        assert skill.body[:40] in render(skill)


def test_codex_index_lists_every_skill(skills):
    index = render_codex_index(skills)
    for skill in skills:
        assert skill.name in index


def test_plugin_manifest_is_valid_json_shape():
    manifest = plugin_manifest("1.0.0", "desc", author="someone")
    assert manifest["name"]
    assert manifest["version"] == "1.0.0"


def test_hooks_manifest_wires_every_event():
    manifest = hooks_manifest("python -m zyrompts.hooks")
    assert manifest["hooks"]
    for event in ("UserPromptSubmit", "PreToolUse", "SessionStart", "Stop"):
        assert event in manifest["hooks"]


@pytest.mark.parametrize("builder", [build_claude_code, build_gemini,
                                     build_copilot, build_codex, build_opencode])
def test_every_builder_produces_files(builder, skills):
    result = builder(skills, "0.1.0") if builder is not build_claude_code \
        else builder(skills, "0.1.0", "desc")
    assert isinstance(result, AdapterResult)
    assert result.files


def test_claude_code_builder_writes_plugin_and_skills(skills):
    result = build_claude_code(skills, "0.1.0", "desc")
    paths = set(result.files)
    assert any(p.endswith("plugin.json") for p in paths)
    assert any(p.endswith("hooks.json") for p in paths)
    for skill in skills:
        assert any(skill.name in p and p.endswith("SKILL.md") for p in paths)


def test_builders_cover_every_target():
    assert set(BUILDERS) == {"claude-code", "gemini", "copilot", "codex", "opencode"}


def test_builder_output_is_deterministic(skills):
    first = build_gemini(skills, "0.1.0")
    second = build_gemini(skills, "0.1.0")
    assert first.files == second.files


def test_adapter_write_creates_the_tree(tmp_path, skills):
    result = build_gemini(skills, "0.1.0")
    written = result.write(tmp_path)
    assert written
    for path in written:
        assert path.is_file()


def test_skill_with_no_description_is_reported_not_silently_dropped():
    meta = parse_skill("---\nname: bare\n---\nbody\n")
    result = build_gemini([meta], "0.1.0")
    assert result.warnings or result.files


# --- dependency declarations ------------------------------------------------

def test_parse_skill_reads_dependency_lists():
    meta = parse_skill("---\nname: a\ndescription: d\ndepends-on: b, c\n"
                       "optional-depends-on: d\n---\nbody\n")
    assert meta.depends_on == ("b", "c")
    assert meta.optional_deps == ("d",)


def test_depends_on_none_is_not_a_dependency():
    """`depends-on: none` is prose for "nothing"; it must not name a skill."""
    meta = parse_skill("---\nname: a\ndescription: d\ndepends-on: none\n---\nbody\n")
    assert meta.depends_on == ()


def test_skill_without_dependency_keys_has_empty_lists():
    meta = parse_skill("---\nname: a\ndescription: d\n---\nbody\n")
    assert meta.depends_on == () and meta.optional_deps == ()


def test_every_canonical_skill_declares_its_dependencies():
    """The Version prose says "Depends on: ..."; frontmatter must say it too."""
    for meta in load_canonical_skills(SKILLS):
        assert "depends-on" in _frontmatter_of(SKILLS / meta.name / "SKILL.md"), meta.name


def test_canonical_dependency_graph_is_acyclic():
    skills = load_canonical_skills(SKILLS)
    assert dependency_cycles(skills) == []


def test_dependency_cycles_detects_a_two_node_cycle():
    a = parse_skill("---\nname: a\ndescription: d\ndepends-on: b\n---\n")
    b = parse_skill("---\nname: b\ndescription: d\ndepends-on: a\n---\n")
    cycles = dependency_cycles([a, b])
    assert len(cycles) == 1
    assert set(cycles[0]) == {"a", "b"}


def test_dependency_cycles_ignores_optional_deps():
    a = parse_skill("---\nname: a\ndescription: d\noptional-depends-on: b\n---\n")
    b = parse_skill("---\nname: b\ndescription: d\noptional-depends-on: a\n---\n")
    assert dependency_cycles([a, b]) == []


def test_dependency_cycles_ignores_unknown_names():
    """A missing skill is reported by validate as unknown, not as a cycle."""
    a = parse_skill("---\nname: a\ndescription: d\ndepends-on: ghost\n---\n")
    assert dependency_cycles([a]) == []


# --- regression: the plugin must ship the dispatcher its manifest names -----

def test_claude_code_plugin_ships_the_engine_it_dispatches_to():
    """hooks.json named scripts/engine.py and no build ever wrote it.

    Every hook in the installed plugin failed with "can't open file", and no
    test noticed because the check compared the tree to the generator rather
    than to reality.
    """
    import json

    from zyrompts.adapters import build_claude_code, parse_skill

    skills = [parse_skill("---\nname: a\ndescription: d\n---\n# body\n")]
    result = build_claude_code(skills, "0.1.0", "d")

    assert "adapters/claude-code/scripts/engine.py" in result.files
    manifest = json.loads(result.files["adapters/claude-code/hooks/hooks.json"])
    commands = [hook["command"]
                for event in manifest["hooks"].values()
                for block in event for hook in block["hooks"]]
    assert commands, "the manifest declares no hooks"
    for command in commands:
        assert "scripts/engine.py" in command, command
    # The file the command names must be one of the files this build writes.
    for command in commands:
        relative = command.split("${CLAUDE_PLUGIN_ROOT}/", 1)[1]
        relative = relative.split()[0].strip('"\'')
        assert f"adapters/claude-code/{relative}" in result.files, relative


def test_every_skill_path_is_written_under_the_target_tree(tmp_path):
    """A skill name is data; it must not be able to name a path outside the tree."""
    from zyrompts.adapters import build_claude_code, parse_skill

    hostile = parse_skill("---\nname: ../../escape\ndescription: d\n---\n# body\n")
    result = build_claude_code([hostile], "0.1.0", "d")
    written = result.write(tmp_path)

    base = tmp_path.resolve()
    for path in written:
        assert base in path.parents, f"{path} escaped {base}"
    assert not (tmp_path.parent / "escape").exists()
