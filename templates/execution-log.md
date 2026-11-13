# Execution log: <plan name>

Append-only. Each entry is written when the step finishes, not when it is
planned. An entry without a command and its output is a note, not a record.

## Entry 1 - <YYYY-MM-DD HH:MM>

**Chapter:** 1 - <name>
**Agent:** implementer
**Intent:** <what this step was meant to achieve>

**Command:**
```bash
<the exact command>
```

**Output:**
```text
<the raw output, trimmed to what matters>
```

**Exit code:** 0
**Result:** pass | fail | partial
**Notes:** <what changed, what surprised you, what is still open>

## Entry 2 - <YYYY-MM-DD HH:MM>

**Chapter:**
**Agent:**
**Intent:**

**Command:**
```bash
```

**Output:**
```text
```

**Exit code:**
**Result:**
**Notes:**

## Summary

- Chapters completed: <n>/<total>
- Verifications run: <n>, passed: <n>
- Open issues: <n>
- Handoff: <what the next agent needs to know first>
