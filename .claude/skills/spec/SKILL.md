---
name: spec
description: Create a new spec — the .claude/specs/ folder with requirement.md, design.md, and task.md placeholders. Use when starting a new feature or work item.
argument-hint: "description of the spec"
allowed-tools: Read, Glob, Bash
---

# Spec Creation Agent

You create the scaffolding for a new spec — the spec folder and placeholder files. Nothing else. No requirement writing, no design, no task lists.

## Input

The user provides a description of the spec via `$ARGUMENTS`. Examples:
- "WebSocket backend for real-time agent log streaming"
- "Circuit breaker pattern for MCP service calls"
- "World Lore Validator agent"

## Process

### Step 1: Derive the Slug

Generate a kebab-case slug from the description. Keep it concise (2-4 words). Examples:
- "WebSocket backend for real-time agent log streaming" → `websocket-log-streaming`
- "Circuit breaker pattern for MCP service calls" → `mcp-circuit-breaker`
- "World Lore Validator agent" → `world-lore-validator`

### Step 2: Check for Duplicates

- Check if `.claude/specs/{slug}/` already exists (Glob for the folder)
- If it exists, inform the user and stop — do not overwrite

### Step 3: Create the Spec Folder

Create `.claude/specs/{slug}/` with three empty placeholder files:
- `requirement.md` — empty
- `design.md` — empty
- `task.md` — empty

## Output

Report what was created:
- The spec folder path
- Remind the user that requirement.md is the next step

## Rules

- **Do not write content into the spec files.** They are placeholders. Other skills in the spec lifecycle will populate them.
- **Do not start any work.** This is scaffolding only.
- **One spec = one folder.** No exceptions.
