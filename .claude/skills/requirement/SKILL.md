---
name: requirement
description: Create a requirement under a spec — plans the work as todos, executes them, and produces the requirement.md content. Use after /spec has created the scaffolding.
argument-hint: "[spec-name] description of the requirement"
allowed-tools: Read, Grep, Glob, Write, Edit, Task, WebSearch, WebFetch, Bash
---

# Requirement Agent

You create requirements for a spec. You plan the work, execute it, and produce the content for `requirement.md`.

## Input

The user provides via `$ARGUMENTS`:
- A spec reference (name or slug) — identifies which spec this requirement belongs to
- A description of what this requirement covers

Examples:
- "world-lore-validator Validates research packages for completeness and source quality"
- "websocket-log-streaming Real-time streaming of agent structured logs to the UI"

If only a description is given (no clear spec reference), search `.claude/specs/` for the most likely match. If ambiguous, ask the user.

## Process

### Step 1: Locate the Spec

1. Search `.claude/specs/` for a matching spec folder (by slug or name match)
2. Verify the spec folder exists at `.claude/specs/{slug}/`
3. If the spec can't be found, stop and ask the user

### Step 2: Gather Context

Before planning, read everything relevant:
- `CLAUDE.md` — project architecture and constraints
- Existing `requirement.md` in the spec folder (may have content from previous requirements)
- Any `.claude/research/` documents referenced by or relevant to this spec
- Any `.claude/blueprints/` that apply to this component type
- The project's existing requirement files (for format consistency): scan `.claude/specs/*/requirement.md` for non-empty files and read one as a style reference

### Step 3: Plan Todos

Break the requirement work into concrete todos. These are **work items**, not content sections. Each todo describes an action that produces part of the requirement content.

Examples of good todos:
- "Research domain constraints that affect validation rules"
- "Draft user stories for the core processing workflow"
- "Define acceptance criteria for the feedback loop"
- "Identify infrastructure dependencies and integration points"
- "Define configuration surface (env vars, config files)"

Examples of bad todos (too vague, or just content headers):
- "Write user stories" (which user stories? for what?)
- "Overview section" (that's a section, not a work item)
- "Finish requirement" (not actionable)

Rules for todos:
- **Minimum 1 todo.** Even a simple requirement needs at least one work item.
- **Each todo must be specific enough that its completion is unambiguous.**
- **Todos should be ordered** — later todos may build on earlier ones.
- **Each todo should produce a concrete deliverable** — a section, a set of user stories, a config spec, etc.

### Step 4: Execute Todos

For each todo, in order:

1. **Do the work** — research, think, draft the content this todo produces
2. **Move to the next todo**

**Parallelism:** Independent todos (no dependency between them) can be executed in parallel. Dependent todos must still be sequential.

During execution, you may:
- Use WebSearch/WebFetch if the todo requires research
- Use Task tool with subagents for parallel research
- Read existing code, configs, or docs for context
- Refer to completed todos' output when working on later ones

### Step 5: Write the Requirement File

After all todos are complete, write (or update) `.claude/specs/{slug}/requirement.md`.

**If the file is empty**: Write the full requirement document.

**If the file already has content**: This is an additional requirement for the same spec. Append new user stories (continuing the `{ABBR}-N` numbering), and merge any new sections (infrastructure dependencies, config, etc.) with existing ones. Do not duplicate or overwrite existing content.

## Output Format

The requirement file follows this structure (adapt sections as needed — not every requirement needs every section):

```markdown
# {Spec Title} — Requirements

## Overview

{1-3 paragraphs: what this is, why it matters, key constraints}

---

## User Stories

### {ABBR}-1: {Title}

**As a** {actor},
**I want to** {action},
**so that** {benefit}.

**Acceptance Criteria:**
- {Specific, testable criterion}
- {Another criterion}

### {ABBR}-2: {Title}
...

Where `{ABBR}` is a 2-4 letter abbreviation derived from the spec name. Examples:
- User Authentication → `UA-1`, `UA-2`
- WebSocket Log Streaming → `WLS-1`, `WLS-2`
- Circuit Breaker → `CB-1`, `CB-2`

If the spec already has user stories, continue the numbering and use the same abbreviation.

---

## Infrastructure Dependencies

| Dependency | Status | Notes |
|-----------|--------|-------|
| {Service} | {To be built / Exists} | {Brief note} |

---

## Configuration Summary

### Environment Variables

```
VAR_NAME=<description>
```

### Config Files

```
path/to/config.yml    # Purpose
```

---

## Out of Scope

- {Things explicitly NOT covered by this requirement}
```

## Rules

- **User stories must be testable.** Every acceptance criterion should be verifiable — no vague "should work well" criteria.
- **Don't invent scope.** The requirement captures what the spec needs. Don't add features the user didn't ask for. If something seems missing, note it in an "Open Questions" section rather than inventing requirements.
- **Respect existing content.** If requirement.md already has content, extend it — don't overwrite.
- **Format consistency.** Match the style of existing requirement files in the project. Read one as reference in Step 2.
