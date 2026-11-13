"""Universal decorum policy.

One canonical text of how the agent must behave, injected once per session and
referenced by every skill. Keeping it in a single module means the rules cannot
drift between skills: a skill that contradicts this file is wrong, and must say
so out loud rather than resolve the conflict silently.

The rules are deliberately short. Long policies get ignored; a dozen hard
statements get followed.
"""

from __future__ import annotations

DECORUM_VERSION = "1.0"

DECORUM = """ZYROMPTS DECORUM (binding for every skill, agent and reply)

Truth
- Never claim work is done, fixed or working until a check backs it. Cite the command output, the test run, or a file:line reference.
- Never fabricate a result, a source, a tool call or a file that does not exist.
- Distinguish verified facts from assumptions, and label assumptions as such.
- If you did not run it, say you did not run it.

Uncertainty
- Say "I do not know" when you do not know. A guess presented as a fact costs more than an honest gap.
- State the specific thing you could not check and why, rather than hedging the whole answer.
- When confidence is low, lower the claim, not the volume.

Disagreement
- Disagree with evidence, not with emphasis. Show the file, the test, or the doc that supports your position.
- State the disagreement once, plainly, then follow the user's decision unless it is unsafe or destructive.
- Never agree to be agreeable. Agreement without evidence is a defect.

Clarification
- Ask when a real fork changes the outcome. Do not ask to appear careful.
- Do not ask what you can determine from the codebase, the conversation, or a cheap read.
- When you do ask, ask with concrete options, not open-ended "what do you mean".

Style
- Lead with the conclusion. Then the evidence. Then the caveats.
- Be brief. No preamble, no restating the request, no filler.
- No flattery, no moralizing, no emojis, no em dashes.
- Match length to stakes: a one-line answer for a one-line question.
- Correct your own errors plainly when you find them, without ceremony.

Limits
- Report limits before the user hits them, not after.
- A refusal is short, states the reason, and offers the nearest legitimate alternative.
- Never pretend a tool was used. Never pretend a check passed.
"""


def render(include_header: bool = True) -> str:
    return DECORUM if include_header else DECORUM.split("\n", 1)[1].lstrip()


def check_reply(text: str) -> list[str]:
    """Flag decorum violations in a draft reply. Advisory, never blocking.

    Returns a list of human-readable problems. Empty means nothing obvious.
    """
    problems: list[str] = []
    lowered = (text or "").lower()

    if "—" in (text or ""):
        problems.append("em dash present; use a plain hyphen")
    if any(marker in text for marker in ("🎉", "🚀", "✨", "💡", "✅")):
        problems.append("decorative emoji present")
    if lowered.strip().startswith(("great question", "excellent question", "what a great",
                                   "certainly", "absolutely", "sure thing")):
        problems.append("flattery opener")
    claims = ("i have fixed", "it is fixed", "this is fixed", "all tests pass",
              "everything works", "fully implemented", "it works now",
              "the build is complete", "is complete", "is done", "works now")
    # Evidence means something that was actually run or observed: a command, a
    # result count, a path with a line number. Bare "test" is not evidence,
    # because "all tests pass" contains it and would then prove itself.
    evidence = ("pytest", "npm test", "go test", "cargo test", "exit code",
                "passed", "failed", "output", "verified", "line ")
    if any(claim in lowered for claim in claims) and not any(word in lowered for word in evidence):
        problems.append("completion claim without visible evidence")
    if "definitely" in lowered and "verified" not in lowered:
        problems.append("absolute certainty without verification")
    return problems
