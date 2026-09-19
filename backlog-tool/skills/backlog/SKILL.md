---
name: backlog
description: >
  Use this skill when the user mentions backlog, features, feature status,
  feature priorities, or wants to manage/query/update their project backlog.
  Also use when the user asks to scaffold a new backlog or launch the backlog TUI.
allowed-tools: Read, Grep, Edit, Write, Bash, Glob
---

# Backlog Tool

A feature backlog stored as markdown in a project's `context/` directory:

- **`context/backlog.md`** owns **ordering, status and category** (one table row per feature).
- **`context/FXX-slug.md`** owns the **name and description**. Optional siblings:
  `FXX-slug-plan.md`, `FXX-slug-research.md`.

Both files carry status and category, so **every change writes both**. Use `backlog set`,
which does that in one step - hand-editing two files is where they drift apart.

## Use the commands, not full-file reads

The `backlog` command answers questions compactly. A backlog can hold 170+ features, so
**never `cat` the whole table, and never read a whole feature file** to check a status.

```bash
backlog list                      # all but shipped/parked, one line each
backlog list -c now,next          # by category
backlog list -s ready,to-review   # by status (an explicit --status shows shipped too)
backlog list --json               # for scripting
backlog show F145                 # header + description
backlog show F145 --head          # header only
backlog show F145 --plan          # add the plan file (these get large - ask for them)
backlog set F145 -s shipped       # updates the table row AND the feature header
backlog set F145 -c now -s ready
backlog add "Name" -c next -s ready -b "One-line description."
backlog next-id                   # lowest free FXX
backlog check                     # report drift between table and feature files
```

Every command takes `-d <dir>` for a backlog outside `./context`. Run from the project root.

If `backlog` is missing or a different version than the plugin:

```bash
bash "${CLAUDE_PLUGIN_DIR}/scripts/ensure-installed.sh"
```

Only if the command is genuinely unavailable, fall back to `grep` on the rows you need
(`grep -n '^| F68' context/backlog.md`) - still not a full read.

## Keep feature files lean

The detail files are what make a backlog expensive to read. Keep each `FXX-slug.md` to
scope and decisions; move long research into `FXX-slug-research.md` and step-by-step plans
into `FXX-slug-plan.md`. When reading a file over ~200 lines, grep for the section you need
or read an offset - not the whole thing.

## Statuses and categories

`idea` → `research-needed` → `researching` → `research-done` → `ready` → `in-progress`
→ `to-review` → `shipped`, plus `parked`.

`now` (shipped or in flight) · `next` (up next) · `later` (planned) · `maybe` (uncommitted).

## Feature file format

```markdown
# FXX: Feature Name

**Status:** ready
**Category:** next

## Description
What it does and why it matters.
```

## Other operations

- **Reorder:** row position in `backlog.md` defines order within a category. Move the row;
  never rename files to reorder.
- **Launch the TUI** (interactive, for the user - not for an agent): `backlog`, after
  running `ensure-installed.sh` above. A standalone-script project may use
  `python3 backlog-tool.py context` instead.
- **Scaffold a new backlog:** `backlog --init` at the project root, one backlog per project.
