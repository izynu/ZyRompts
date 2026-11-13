# Compatibility matrix

One canonical skill library, five generated platform trees. What each platform
gets, and what it does not, is listed here rather than inferred from the code.

## Support at a glance

| Capability | Claude Code | Gemini | Copilot | Codex | OpenCode |
|---|---|---|---|---|---|
| Skill library | yes (17) | yes (17) | yes (17) | yes (17) | yes (17) |
| Per-skill file | `skills/<name>/SKILL.md` | `.gemini/skills/zy-<slug>/SKILL.md` | `.github/skills/zy-<slug>/SKILL.md` | `AGENTS.md` index | `.opencode/agent/zy-<slug>.md` |
| Manifest | `plugin.json` + `marketplace.json` | `skills.json` | `plugin.json` | - | - |
| Hook engine | yes | no | no | no | no |
| Generated files | 20 | 18 | 18 | 1 | 17 |

"Skill library" means the same procedures are present on every platform. The
hook engine is Claude Code only, because it is the only one of the five with a
hook protocol this engine targets.

## Frontmatter, per platform

The canonical frontmatter is richer than any single platform accepts, so each
renderer emits only what that platform reads.

| Canonical key | Claude Code | Gemini | Copilot | OpenCode |
|---|---|---|---|---|
| `name` | as-is | `zy-<slug>` | `zy-<slug>` | omitted |
| `description` | yes | yes | yes, plus a "Use when ..." suffix | yes |
| `allowed-tools` | yes | yes | dropped | rendered as `tools:` |
| `argument-hint` | yes | dropped | dropped | dropped |
| `model` | yes | dropped | dropped | dropped |
| `effort` | yes | dropped | dropped | dropped |
| `disable-model-invocation` | yes | dropped | dropped | dropped |
| `depends-on` | not emitted | not emitted | not emitted | not emitted |

`depends-on` is validated at build time (unknown name, cycle) and used to order
the Codex index; it is not emitted into platform frontmatter because no
platform reads it.

## Naming

The `zy-` prefix is applied where a platform's namespace is flat and a bare
`execute` would collide with a built-in or a user skill:

```
canonical:  execute
claude-code: execute              (namespaced by the plugin)
gemini:      zy-execute
copilot:     zy-execute
codex:       ### execute          (a heading in AGENTS.md)
opencode:    zy-execute.md        (name derived from the filename)
```

## What degrades, and how

| Degradation | Consequence | Mitigation |
|---|---|---|
| No hook engine on Gemini/Copilot/Codex/OpenCode | no automatic intake classification, no pre-tool policy | the procedures still say "classify first"; run `zyrompts classify` as a CLI step |
| Codex has one file, not a skill directory | no per-skill activation | the index is short; Codex reads it whole |
| Tool names differ per platform | `allowed-tools` is advisory outside Claude Code | the policy engine is the real enforcement, and it is CLI-callable everywhere |
| `argument-hint` has no equivalent | slash-command UX differs | none needed; the procedure states the input |

## Adding a platform

1. Write `render_<platform>(meta) -> str` in `adapters.py`.
2. Write `build_<platform>(skills, version) -> AdapterResult`.
3. Register it in `BUILDERS`.
4. Add a row to this matrix and a test to `tests/test_adapters.py`.
5. Run `python3 scripts/generate-adapters.py`.

The builder must be pure: no clock, no network, no environment. That is what
makes `--check` in CI meaningful.
