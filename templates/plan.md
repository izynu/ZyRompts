# Plan: <feature name>

Status: draft | under review | approved | in progress | done
Spec: ./specification.md
Author: <agent or person>
Date: <YYYY-MM-DD>

## Context

What the plan changes and why, in three sentences. Link the specification; do
not restate it.

## Chapters

Each chapter leaves the tree working. Each has its files, its steps, and the
command that proves it worked.

## Chapter 1 - <name>

**Goal:** <what is true after this chapter>

**Affected files:**
- `path/to/file.py` - <what changes>
- `path/to/test_file.py` - <what changes>

**Steps:**
1. <exact step>
2. <exact step>

**Verification:**
```bash
<command>
```
Pass means: <the output or exit code that proves it>

**Risk if wrong:** <what breaks, and how it would be noticed>

## Chapter 2 - <name>

**Goal:** <what is true after this chapter>

**Affected files:**
- `path/to/file.py` - <what changes>

**Steps:**
1. <exact step>

**Verification:**
```bash
<command>
```
Pass means: <the output or exit code that proves it>

**Risk if wrong:** <what breaks>

## Out of scope

- <what this plan deliberately does not do>

## Rollback

How to undo the change if it is wrong after merge.

## Open questions

- <question> - blocking: yes/no - owner: <who>
