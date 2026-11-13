---
name: zy-prompt-improver
description: Turn a vague request into an actionable one through grounded research and a small set of concrete questions. Use when a prompt is underspecified, when a request would otherwise need a correction round-trip, or when the user asks to improve or rewrite a prompt.
license: MIT
---

# Prompt Improver

## Purpose

Close the gap between what the user typed and what they meant, before any work
starts. The output is not a prettier prompt; it is a prompt that can be executed
correctly on the first attempt.

## Activation

- The intake hook flagged the prompt as underspecified.
- The user asks to improve, rewrite, fix, or sharpen a prompt.
- A request would otherwise need a clarifying round-trip after a bad first attempt.

Do not activate when the prompt already names its target, action and success
condition. A clear prompt needs no improvement, and adding ceremony costs tokens
without changing the output.

## Inputs and outputs

Input: the raw prompt, plus whatever conversation history exists.
Output: either an execution-ready prompt, or 1-6 grounded questions whose answers
make it execution-ready. Never both without a reason.

## Procedure

1. Score the prompt. Run `zyrompts score "<prompt>"` if the CLI is available;
   otherwise apply the seven checks yourself: precise verb, named target, output
   format, constraints, success criteria, scope boundary, examples.
2. Research before asking. Check conversation history first, then the codebase
   (`Glob`, `Grep`, targeted `Read`), then git history if relevant. Every option
   you later offer must come from something you actually found.
3. Decide: clear or vague.
   - Clear means the weakest of the seven checks is still specific enough to act
     on. Proceed, and say nothing about the prompt.
   - Vague means a reasonable engineer could build the wrong thing. Continue.
4. Generate 1-6 questions. One decision per question. Each option must be
   concrete and traceable to your research; include the tradeoff in the option
   description. Never offer "Other" as your only alternative, and never ask a
   question a cheap read would answer.
5. Ask with the AskUserQuestion tool. Set `multiSelect` explicitly. Group related
   questions into one call rather than interrupting repeatedly.
6. Execute the original request using the answers, the research, and the history.
   Do not restate the whole improved prompt unless the user asked for one.

## Question patterns

| Ambiguity | Question shape |
|---|---|
| Which target | "Which of these is the target?" with 2-4 concrete file/symbol options |
| Which approach | "Which approach?" with options naming the tradeoff |
| How much scope | "How far should this go?" with smallest/typical/largest |
| What counts as done | "What must be true when this is finished?" with checkable options |
| Which constraint wins | "These two conflict. Which takes priority?" |

## Failure handling

- Research returns nothing usable: say so, and ask an open question rather than
  inventing options.
- The user answers "whatever you think": pick the option with the least
  irreversible consequence, state the choice, proceed.
- The prompt is clear after all: proceed silently. Do not manufacture questions
  to justify the skill.

## Evaluation cases

- `fix the bug` in a repo with a failing auth test -> one question naming the
  actual failing test, then a fix.
- `add caching` -> questions about layer (HTTP, ORM, in-process) with tradeoffs.
- `Refactor getUserById in src/api/users.ts to async/await` -> no questions.

## Version

1.0.0. Depends on: none. Platforms: all.
