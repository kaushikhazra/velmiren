---
name: dryrun-blueprint
description: Dry-run a blueprint by simulating building a new instance of that category. Finds missing steps, unclear conventions, and untestable patterns.
argument-hint: "<blueprint-name or path>"
allowed-tools: Read, Grep, Glob, Agent, Write
---

# Blueprint Dry-Run Agent

You are a **blueprint reviewer**. Your job is to validate that a blueprint is complete and actionable — meaning any agent can follow it to build a new instance of that category without asking questions.

## Input

The user provides either:
- A blueprint name: `$ARGUMENTS` (resolves to `.claude/blueprints/$ARGUMENTS/readme.md`)
- A path to a blueprint file

If no argument is provided, find all blueprints in `.claude/blueprints/` and run the review on each.

## Process

### Step 1: Read the Blueprint

Read the blueprint file. Also read `CLAUDE.md` for project-level context that the blueprint should be consistent with.

### Step 2: Simulate Building an Instance

Spawn a sub-agent (using the Agent tool) with this prompt:

> You are a developer who needs to build a new instance of the category described in this blueprint. Read the blueprint and CLAUDE.md, then walk through building a fictional but realistic instance.
>
> For each step in the blueprint:
> 1. Is the instruction clear enough to follow without guessing?
> 2. Are there code examples for every pattern?
> 3. Does the checklist at the end cover everything you actually needed to do?
>
> Also check:
> - Does the blueprint contradict anything in CLAUDE.md?
> - Are there patterns shown in examples that aren't explained in the text?
> - Are there decisions left to the developer that should be prescribed?
> - Can you test what you built using only the testing guidance in the blueprint?

The sub-agent should ONLY read files, not create or modify anything.

### Step 3: Write Report

Determine the iteration number:
1. Check `.claude/` for existing `dryrun-blueprint-*.md` files
2. N = count of existing files + 1

Write the report to `.claude/dryrun-blueprint-{N}.md`.

## Report Format

```markdown
# Blueprint Dry-Run Report #{N}

**Blueprint**: {name/path}
**Reviewed**: {date}

---

## Critical Gaps (cannot follow blueprint without guessing)

### [C1] {title}
- **Section**: {which section}
- **What**: {what's missing}
- **Impact**: {what a developer would get wrong}
- **Fix**: {suggested addition}

---

## Warnings (blueprint works but could mislead)

### [W1] {title}
- **Section**: {which section}
- **What**: {the ambiguity}
- **Suggestion**: {how to clarify}

---

## Observations

### [O1] {title}
{description}

---

## Checklist Coverage

| Blueprint Checklist Step | Needed During Simulation? | Sufficient? |
|--------------------------|--------------------------|-------------|
| {step} | Yes/No | Yes/No/Missing |

---

## Summary

| Critical | Warnings | Observations |
|----------|----------|--------------|
| {count}  | {count}  | {count}      |

**Verdict**: {PASS / PASS WITH WARNINGS / FAIL — needs revision}
```

### Step 4: Update eval.md

If `.claude/eval.md` exists and has an unchecked entry for the blueprint file, mark it done.

### Step 5: Display to User

Output the verdict and summary counts to the conversation.

## Rules

- Blueprints teach patterns, not instances. Don't flag "this doesn't tell me how to build the weather skill" — that's a spec's job.
- DO flag "this doesn't tell me when to use inline handlers vs rpc/handlers.py" — that's a pattern decision the blueprint should prescribe.
- Code examples must be copy-paste-and-adapt ready. If an example requires understanding unstated conventions, that's a gap.
- The worked example (if present) should exercise every pattern described in the blueprint. Missing coverage is a warning.
