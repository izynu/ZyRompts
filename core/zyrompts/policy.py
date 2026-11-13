"""Policy and permission engine.

Deterministic security controls live here, never in prompt text. A model can be
talked out of an instruction; it cannot be talked out of a Python `if`.

The engine answers one question per tool call: given this tool, these
arguments, and this autonomy level, is the call ALLOWED, DENIED, or does it
need explicit human confirmation (ASK)?

Layers, in order of precedence:
1. Hard denials      - never allowed at any autonomy level (destructive rm,
                       force-push to protected branches, writes outside root).
2. Injection floor   - content flagged as untrusted cannot escalate privilege.
3. Secret redaction  - detected credentials are stripped before logging.
4. Autonomy policy   - read-only / ask / auto / yolo gate for everything else.
"""

from __future__ import annotations

import fnmatch
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class Decision(str, Enum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


class Autonomy(str, Enum):
    """How much the agent may do without asking.

    READ_ONLY - inspect only; every mutating tool asks.
    ASK       - default; mutating tools ask, read tools pass.
    AUTO      - safe mutating tools pass, destructive ones ask.
    YOLO      - everything except hard denials passes. Still denies hard rules.
    """

    READ_ONLY = "read-only"
    ASK = "ask"
    AUTO = "auto"
    YOLO = "yolo"


@dataclass(frozen=True)
class Verdict:
    decision: Decision
    reason: str
    rule: str = ""
    redacted_args: dict | None = None

    def to_dict(self) -> dict:
        out = {"decision": self.decision.value, "reason": self.reason, "rule": self.rule}
        if self.redacted_args is not None:
            out["redacted_args"] = self.redacted_args
        return out


# Tools that only read. Everything not listed is treated as mutating.
READ_ONLY_TOOLS = {
    "Read", "Glob", "Grep", "WebFetch", "WebSearch", "LS", "NotebookRead",
    "TodoWrite", "TodoRead", "list_files", "read_file", "search_files",
}

# Tools that mutate the filesystem or run code.
MUTATING_TOOLS = {
    "Write", "Edit", "MultiEdit", "NotebookEdit", "Bash", "execute_command",
    "run_shell_command", "run_kali_tool", "Task", "Agent",
}

# Every tool name the evaluator has an opinion about. The CLI uses this to tell
# a tool name from a bare shell command, so it must stay the union of the two
# sets above rather than a third hand-maintained list.
KNOWN_TOOLS = READ_ONLY_TOOLS | MUTATING_TOOLS

# Commands that are read-only even though they run through Bash.
_READONLY_COMMANDS = re.compile(
    r"^\s*(ls|cat|head|tail|grep|rg|find|fd|wc|stat|file|which|whoami|pwd|"
    r"git\s+(status|log|diff|show|branch|remote|describe)|"
    r"python3?\s+--version|node\s+--version|npm\s+(ls|list)|pip\s+(list|show)|"
    r"df|du|free|uname|date|echo|env|printenv|id|ps|ss|netstat)\b", re.I)

# Hard denials: matched against a shell command. These fire at every autonomy
# level including YOLO, because a wrong answer here is unrecoverable.
_HARD_DENY_COMMANDS: list[tuple[str, re.Pattern[str]]] = [
    ("root-delete", re.compile(r"\brm\s+(-[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*|-[a-zA-Z]*f[a-zA-Z]*r[a-zA-Z]*)\s+(/|/\*|~|~/\*|\$HOME)\s*$")),
    ("root-delete", re.compile(r"\brm\s+-rf\s+/(?!\w)")),
    ("disk-overwrite", re.compile(r"\bdd\b.*\bof=/dev/(sd|nvme|hd|vd)")),
    ("mkfs", re.compile(r"\bmkfs(\.\w+)?\s+/dev/")),
    ("fork-bomb", re.compile(r":\(\)\s*\{\s*:\|:&\s*\}\s*;\s*:")),
    ("history-rewrite", re.compile(r"\bgit\s+push\b.*\s(--force|-f)\b.*\b(main|master|release|prod)\b")),
    ("history-rewrite", re.compile(r"\bgit\s+filter-(branch|repo)\b")),
    # `reset --hard` discards uncommitted work with no recovery path. It is not
    # an approval question: the answer has to be "commit or stash first".
    ("history-rewrite", re.compile(r"\bgit\s+reset\s+--hard\b")),
    ("history-rewrite", re.compile(r"\bgit\s+clean\s+-[a-zA-Z]*[fdx]")),
    ("credential-exfil", re.compile(r"\b(curl|wget)\b[^|;]*\b(\.ssh/id_|\.aws/credentials|\.env\b|id_rsa)")),
    ("pipe-to-shell", re.compile(r"\b(curl|wget)\b[^|]*\|\s*(sudo\s+)?(ba|z|k)?sh\b")),
    ("permission-nuke", re.compile(r"\bchmod\s+-R\s+777\s+/(?!\w)")),
    ("sudo-anything", re.compile(r"\bsudo\s+")),
]

# Paths that must never be written, even under YOLO.
_PROTECTED_PATH_PATTERNS = [
    "/etc/passwd", "/etc/shadow", "/etc/sudoers", "~/.ssh/*", "~/.aws/*",
    "~/.config/gh/*", "**/.git/config", "/boot/*", "/dev/sd*",
]

_SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("anthropic_key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("aws_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("slack_token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("private_key", re.compile(r"-----BEGIN (RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    ("generic_assignment", re.compile(
        r"\b(api[_-]?key|secret|password|passwd|token|bearer)\s*[:=]\s*['\"]?([A-Za-z0-9_\-./+]{12,})", re.I)),
]

_PEM_BLOCK = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S)


def redact_secrets(text: str) -> tuple[str, list[str]]:
    """Replace detected credentials with [REDACTED:kind]. Returns (text, kinds)."""
    if not isinstance(text, str):
        return text, []
    kinds: list[str] = []
    out = _PEM_BLOCK.sub("[REDACTED:private_key]", text)
    if out != text:
        kinds.append("private_key")
    for name, pattern in _SECRET_PATTERNS:
        if name == "private_key":
            continue
        def _sub(match: re.Match) -> str:
            kinds.append(name)
            if match.lastindex and match.lastindex >= 2:
                return match.group(0).replace(match.group(2), "[REDACTED]")
            return "[REDACTED]"
        out = pattern.sub(_sub, out)
    return out, sorted(set(kinds))


def contains_secret(text: str) -> bool:
    return bool(redact_secrets(text)[1])


def _within(root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
        return True
    except (ValueError, OSError):
        return False


def _is_protected_path(path_str: str) -> bool:
    expanded = os.path.expanduser(path_str)
    for pattern in _PROTECTED_PATH_PATTERNS:
        if fnmatch.fnmatch(expanded, os.path.expanduser(pattern)):
            return True
        if pattern.startswith("/") and expanded.startswith(pattern.rstrip("*")):
            return True
    return False


def check_command(command: str, autonomy: Autonomy = Autonomy.ASK) -> Verdict:
    """Apply the hard-deny table and the read-only fast path to a shell command."""
    if not isinstance(command, str):
        return Verdict(Decision.DENY, "command is not a string", "invalid-input")

    # Nothing to run is nothing to approve. Without this, an empty command falls
    # through to the autonomy band and asks the user to approve a no-op.
    if not command.strip():
        return Verdict(Decision.ALLOW, "empty command is a no-op", "empty-command")

    for name, pattern in _HARD_DENY_COMMANDS:
        match = pattern.search(command)
        if match:
            return Verdict(Decision.DENY,
                           f"hard denial {name!r}: {match.group(0)[:80]!r} is never allowed",
                           f"hard-deny:{name}")

    if _READONLY_COMMANDS.match(command):
        return Verdict(Decision.ALLOW, "read-only command", "readonly-command")

    if autonomy is Autonomy.READ_ONLY:
        return Verdict(Decision.ASK, "read-only autonomy: mutating command needs approval",
                       "autonomy:read-only")
    if autonomy is Autonomy.YOLO:
        return Verdict(Decision.ALLOW, "yolo autonomy", "autonomy:yolo")
    if autonomy is Autonomy.AUTO:
        return Verdict(Decision.ALLOW, "auto autonomy: non-destructive command", "autonomy:auto")
    return Verdict(Decision.ASK, "ask autonomy: command needs approval", "autonomy:ask")


def check_path(path_str: str, root: Path | None, write: bool = True) -> Verdict:
    """Enforce workspace containment and protected-path rules."""
    if not isinstance(path_str, str) or not path_str:
        return Verdict(Decision.DENY, "empty or non-string path", "invalid-input")
    if "\x00" in path_str:
        return Verdict(Decision.DENY, "null byte in path", "path-traversal")
    if _is_protected_path(path_str):
        return Verdict(Decision.DENY, f"protected path {path_str!r}", "protected-path")
    if write and root is not None:
        if not _within(root, Path(os.path.expanduser(path_str))):
            return Verdict(Decision.DENY,
                           f"write outside workspace root {root}: {path_str!r}",
                           "workspace-containment")
    return Verdict(Decision.ALLOW, "path allowed", "path-ok")


def evaluate(tool_name: str, args: dict, autonomy: Autonomy = Autonomy.ASK,
             root: Path | None = None, untrusted: bool = False) -> Verdict:
    """Full verdict for one tool call.

    `untrusted` marks calls whose content came from tool output or a web page.
    Untrusted content cannot escalate: it is capped at ASK even under YOLO.
    """
    args = args if isinstance(args, dict) else {}

    if not isinstance(tool_name, str) or not tool_name:
        return Verdict(Decision.DENY, "missing tool name", "invalid-input")

    if tool_name == "Bash" or tool_name in {"execute_command", "run_shell_command", "run_kali_tool"}:
        command = args.get("command") or args.get("cmd") or ""
        verdict = check_command(command, autonomy)
        if verdict.decision is Decision.DENY:
            return verdict
        if untrusted and verdict.decision is Decision.ALLOW:
            return Verdict(Decision.ASK, "untrusted content cannot escalate privilege",
                           "injection-floor")
        return verdict

    if tool_name in {"Write", "Edit", "MultiEdit", "NotebookEdit"}:
        path = args.get("file_path") or args.get("path") or ""
        verdict = check_path(str(path), root, write=True)
        if verdict.decision is Decision.DENY:
            return verdict
        if untrusted:
            return Verdict(Decision.ASK, "untrusted content cannot write without approval",
                           "injection-floor")
        # Read-only means no mutation at all. Asking would imply "yes" is an
        # answer, which would let the level be negotiated away by one approval.
        if autonomy is Autonomy.READ_ONLY:
            return Verdict(Decision.DENY, "read-only autonomy: file writes are disabled",
                           "autonomy:read-only")
        if autonomy is Autonomy.ASK:
            return Verdict(Decision.ASK, f"{autonomy.value} autonomy: file write needs approval",
                           f"autonomy:{autonomy.value}")
        return Verdict(Decision.ALLOW, "file write allowed", "file-write-ok")

    if tool_name in READ_ONLY_TOOLS:
        return Verdict(Decision.ALLOW, "read-only tool", "readonly-tool")

    # Unknown tools are treated as mutating: fail closed, not open.
    if autonomy is Autonomy.YOLO:
        return Verdict(Decision.ALLOW, "yolo autonomy for unknown tool", "autonomy:yolo")
    return Verdict(Decision.ASK, f"unknown tool {tool_name!r} needs approval", "unknown-tool")


@dataclass
class PolicyConfig:
    autonomy: Autonomy = Autonomy.ASK
    root: Path | None = None
    allow_tools: set[str] = field(default_factory=set)
    deny_tools: set[str] = field(default_factory=set)
    allow_commands: list[str] = field(default_factory=list)

    def evaluate(self, tool_name: str, args: dict, untrusted: bool = False) -> Verdict:
        if tool_name in self.deny_tools:
            return Verdict(Decision.DENY, f"tool {tool_name!r} is on the deny list", "deny-list")
        if tool_name in self.allow_tools:
            return Verdict(Decision.ALLOW, f"tool {tool_name!r} is on the allow list", "allow-list")
        command = args.get("command", "") if isinstance(args, dict) else ""
        for pattern in self.allow_commands:
            if command and fnmatch.fnmatch(command, pattern):
                return Verdict(Decision.ALLOW, f"command matches {pattern!r}", "allow-command")
        return evaluate(tool_name, args, self.autonomy, self.root, untrusted)

    @classmethod
    def from_dict(cls, data: dict, root: Path | None = None) -> "PolicyConfig":
        data = data if isinstance(data, dict) else {}
        try:
            autonomy = Autonomy(str(data.get("autonomy", "ask")).lower())
        except ValueError:
            autonomy = Autonomy.ASK
        return cls(
            autonomy=autonomy,
            root=root or (Path(data["root"]) if data.get("root") else None),
            allow_tools=set(data.get("allow_tools") or []),
            deny_tools=set(data.get("deny_tools") or []),
            allow_commands=list(data.get("allow_commands") or []),
        )
