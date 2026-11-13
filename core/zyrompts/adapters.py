"""Multi-platform adapters.

One canonical workflow, many platforms. An adapter is a pure function from the
canonical skill metadata to a platform's on-disk format, so the platforms can
never drift from the source of truth: the canonical skill is the input, and a
generator (scripts/generate-adapters.py) writes each platform's tree.

Supported targets:
- claude-code: plugin.json + hooks.json + skills/<name>/SKILL.md
- codex:       AGENTS.md with inlined skill summaries
- gemini:      .gemini/skills/<prefix-name>/SKILL.md + skills.json
- copilot:     .github/skills/<prefix-name>/SKILL.md
- opencode:    .opencode/agent/<name>.md
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SkillMeta:
    name: str
    description: str
    body: str
    allowed_tools: str = "Read, Glob, Grep"
    model: str = ""
    effort: str = ""
    argument_hint: str = ""
    disable_model_invocation: bool = False
    references: dict[str, str] = field(default_factory=dict)
    # Hard dependencies must run before this skill; optional ones improve it but
    # are not required. Declared in frontmatter so `validate` can check that a
    # dependency names a real skill and that the graph has no cycle. The Version
    # prose says the same thing, but prose cannot be checked.
    depends_on: tuple[str, ...] = ()
    optional_deps: tuple[str, ...] = ()

    @property
    def slug(self) -> str:
        return re.sub(r"[^a-z0-9]+", "-", self.name.lower()).strip("-")


_FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.S)


def parse_skill(text: str) -> SkillMeta:
    """Parse a canonical SKILL.md with YAML-ish frontmatter.

    Deliberately minimal: the frontmatter we emit is flat key: value, so a full
    YAML dependency would be weight without benefit.
    """
    match = _FRONTMATTER.match(text or "")
    if not match:
        return SkillMeta(name="unnamed", description="", body=(text or "").strip())

    meta: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line or line.strip().startswith("#"):
            continue
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip().strip("'\"")

    def _list(key: str) -> tuple[str, ...]:
        raw = meta.get(key, "").strip().strip("[]")
        items = (item.strip().strip("'\"") for item in raw.split(","))
        # "depends-on: none" is how a skill says it has no dependencies; it must
        # not become a dependency on a skill literally named "none".
        return tuple(item for item in items if item and item.lower() not in ("none", "n/a"))

    return SkillMeta(
        name=meta.get("name", "unnamed"),
        description=meta.get("description", ""),
        body=match.group(2).strip(),
        allowed_tools=meta.get("allowed-tools", "Read, Glob, Grep"),
        model=meta.get("model", ""),
        effort=meta.get("effort", ""),
        argument_hint=meta.get("argument-hint", ""),
        disable_model_invocation=meta.get("disable-model-invocation", "").lower() == "true",
        depends_on=_list("depends-on"),
        optional_deps=_list("optional-depends-on"),
    )


def _frontmatter(meta: SkillMeta, name: str, extra: dict[str, str] | None = None) -> str:
    lines = ["---", f"name: {name}"]
    if meta.description:
        lines.append(f"description: {meta.description}")
    if meta.allowed_tools:
        lines.append(f"allowed-tools: {meta.allowed_tools}")
    for key, value in (extra or {}).items():
        if value:
            lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines)


# --- per-platform renderers -------------------------------------------------

def render_claude_code(meta: SkillMeta) -> str:
    extra = {}
    if meta.argument_hint:
        extra["argument-hint"] = meta.argument_hint
    if meta.model:
        extra["model"] = meta.model
    if meta.effort:
        extra["effort"] = meta.effort
    if meta.disable_model_invocation:
        extra["disable-model-invocation"] = "true"
    return f"{_frontmatter(meta, meta.name, extra)}\n\n{meta.body}\n"


def render_gemini(meta: SkillMeta) -> str:
    return f"{_frontmatter(meta, f'zy-{meta.slug}')}\n\n{meta.body}\n"


def render_copilot(meta: SkillMeta) -> str:
    description = meta.description
    if "Use when" not in description:
        description += f" Use when the user runs /zy-{meta.slug}."
    lines = ["---", f"name: zy-{meta.slug}", f"description: {description}",
             "license: MIT", "---"]
    return "\n".join(lines) + f"\n\n{meta.body}\n"


def render_opencode(meta: SkillMeta) -> str:
    lines = ["---", f"description: {meta.description}", f"mode: subagent",
             f"tools: {meta.allowed_tools}", "---"]
    return "\n".join(lines) + f"\n\n{meta.body}\n"


def render_codex_index(skills: list[SkillMeta], version: str = "0.1.0") -> str:
    """AGENTS.md: a single index Codex can read without a skill loader."""
    lines = [
        "# ZyRompts",
        "",
        f"Version {version}. Canonical workflow skills, generated from skills/.",
        "",
        "## Skills",
        "",
    ]
    for meta in skills:
        lines.append(f"### {meta.name}")
        lines.append(meta.description)
        lines.append("")
        lines.append("```text")
        lines.append(meta.body)
        lines.append("```")
        lines.append("")
    return "\n".join(lines)


# --- manifest generation ----------------------------------------------------

def plugin_manifest(version: str, description: str, author: str = "") -> dict:
    return {
        "name": "zyrompts",
        "description": description,
        "version": version,
        "author": {"name": author} if author else {"name": "ZyRompts contributors"},
        "license": "MIT",
        "keywords": ["agents", "workflow", "planning", "critique", "prompt-engineering",
                     "code-review", "security", "skills"],
        "skills": ["./skills"],
        "hooks": "./hooks/hooks.json",
    }


def marketplace_manifest(version: str, description: str, owner: str = "") -> dict:
    return {
        "name": "zyrompts",
        "description": description,
        "owner": {"name": owner or "ZyRompts contributors"},
        "plugins": [{
            "name": "zyrompts",
            "source": "./",
            "description": description,
            "version": version,
        }],
    }


def hooks_manifest(entry_command: str) -> dict:
    """hooks.json for Claude Code, dispatching every event to the one engine."""
    def entry(event: str, matcher: str | None = None) -> dict:
        block: dict = {}
        if matcher:
            block["matcher"] = matcher
        block["hooks"] = [{
            "type": "command",
            "command": f"{entry_command} {event}",
            "timeout": 10,
        }]
        return block

    return {
        "description": "ZyRompts hook engine: one dispatcher, declarative rules",
        "hooks": {
            "UserPromptSubmit": [entry("UserPromptSubmit")],
            "PreToolUse": [entry("PreToolUse", "Bash|Write|Edit|MultiEdit|Bash")],
            "SubagentStart": [entry("SubagentStart")],
            "SessionStart": [entry("SessionStart")],
            "Stop": [entry("Stop")],
        },
    }


@dataclass
class AdapterResult:
    files: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def write(self, root: Path) -> list[Path]:
        written = []
        for relative, content in self.files.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            written.append(path)
        return written


def build_claude_code(skills: list[SkillMeta], version: str, description: str,
                      hooks_dir: str = "hooks/rules") -> AdapterResult:
    result = AdapterResult()
    result.files["adapters/claude-code/.claude-plugin/plugin.json"] = json.dumps(
        plugin_manifest(version, description), indent=2) + "\n"
    result.files["adapters/claude-code/.claude-plugin/marketplace.json"] = json.dumps(
        marketplace_manifest(version, description), indent=2) + "\n"
    result.files["adapters/claude-code/hooks/hooks.json"] = json.dumps(
        hooks_manifest('python3 "${CLAUDE_PLUGIN_ROOT}/scripts/engine.py"'), indent=2) + "\n"
    for meta in skills:
        result.files[f"adapters/claude-code/skills/{meta.name}/SKILL.md"] = render_claude_code(meta)
    return result


def build_gemini(skills: list[SkillMeta], version: str) -> AdapterResult:
    result = AdapterResult()
    entries = []
    for meta in skills:
        path = f"adapters/gemini/.gemini/skills/zy-{meta.slug}/SKILL.md"
        result.files[path] = render_gemini(meta)
        entries.append({"path": f".gemini/skills/zy-{meta.slug}"})
    result.files["adapters/gemini/.gemini/config/skills.json"] = json.dumps(
        {"version": version, "entries": entries}, indent=2) + "\n"
    return result


def build_copilot(skills: list[SkillMeta], version: str) -> AdapterResult:
    result = AdapterResult()
    for meta in skills:
        result.files[f"adapters/copilot/.github/skills/zy-{meta.slug}/SKILL.md"] = render_copilot(meta)
    result.files["adapters/copilot/.github/plugin/plugin.json"] = json.dumps(
        {"name": "zyrompts", "version": version, "skills": [".github/skills"]}, indent=2) + "\n"
    return result


def build_codex(skills: list[SkillMeta], version: str) -> AdapterResult:
    result = AdapterResult()
    result.files["adapters/codex/AGENTS.md"] = render_codex_index(skills, version)
    return result


def build_opencode(skills: list[SkillMeta], version: str) -> AdapterResult:
    result = AdapterResult()
    for meta in skills:
        result.files[f"adapters/opencode/.opencode/agent/zy-{meta.slug}.md"] = render_opencode(meta)
    return result


BUILDERS = {
    "claude-code": build_claude_code,
    "gemini": build_gemini,
    "copilot": build_copilot,
    "codex": build_codex,
    "opencode": build_opencode,
}


def load_canonical_skills(skills_dir: Path) -> list[SkillMeta]:
    skills = []
    for path in sorted(skills_dir.glob("*/SKILL.md")):
        try:
            skills.append(parse_skill(path.read_text(encoding="utf-8")))
        except OSError:
            continue
    return skills


def dependency_cycles(skills: list[SkillMeta]) -> list[list[str]]:
    """Return every hard-dependency cycle, each as a closed path.

    A cycle is a defect, not a style question: if A must run before B and B must
    run before A, neither can ever be activated first, so the loader has to
    reject the library rather than pick an arbitrary order. Optional dependencies
    are excluded because they are not ordering constraints.
    """
    graph = {skill.name: [d for d in skill.depends_on if d in {s.name for s in skills}]
             for skill in skills}
    cycles: list[list[str]] = []
    seen_cycles: set[frozenset[str]] = set()
    state: dict[str, int] = {}   # 0 unvisited, 1 on stack, 2 done
    stack: list[str] = []

    def visit(node: str) -> None:
        state[node] = 1
        stack.append(node)
        for dep in graph.get(node, []):
            if state.get(dep, 0) == 1:
                cycle = stack[stack.index(dep):] + [dep]
                key = frozenset(cycle)
                if key not in seen_cycles:
                    seen_cycles.add(key)
                    cycles.append(cycle)
            elif state.get(dep, 0) == 0:
                visit(dep)
        stack.pop()
        state[node] = 2

    for name in graph:
        if state.get(name, 0) == 0:
            visit(name)
    return cycles
