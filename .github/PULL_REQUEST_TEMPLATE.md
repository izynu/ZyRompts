## What this changes

<!-- One paragraph. What was wrong, what is different now, and why. -->

## Evidence

<!-- The command you ran and its output. A claim without output is not evidence. -->

```text
$ python3 -m pytest tests/ -q
```

## Checklist

- [ ] `python3 -m pytest tests/ -q` passes
- [ ] `zyrompts validate` passes
- [ ] `zyrompts eval` passes
- [ ] `python3 scripts/generate-adapters.py --check` passes, or the regenerated
      `adapters/` is committed
- [ ] A test fails without this change and passes with it
- [ ] `CHANGELOG.md` updated under `[Unreleased]`

## Type of change

- [ ] Bug fix (a rule that must hold was not holding)
- [ ] New feature
- [ ] New skill, rule, agent or template
- [ ] Documentation
- [ ] Refactor with no behaviour change

## Security

- [ ] This change does not weaken a hard denial, the injection floor, workspace
      containment, or redaction
- [ ] If it touches `policy.py`, the test asserts the rule fires under `yolo`

## Notes for the reviewer

<!-- What you are unsure about. Naming the weak point is faster than being asked. -->
