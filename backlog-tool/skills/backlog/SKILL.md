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

- **`context/backlog.md`** owns **ordering, theme, timing and status** (one table row per feature).
- **`context/FXX-slug.md`** owns the **name and description**. Optional siblings:
  `FXX-slug-plan.md`, `FXX-slug-research.md`.

Both files carry theme, timing and status, so **every change writes both**. Use `backlog set`,
which does that in one step - hand-editing two files is where they drift apart.

**Timing was called Category before 1.9.0.** Files now write `**Timing:**` and the table has a
`Timing` column; the old spelling is still read and `-c/--category` still works. `backlog migrate`
converts an old backlog in place.

## Use the commands, not full-file reads

The `backlog` command answers questions compactly. A backlog can hold 170+ features, so
**never `cat` the whole table, and never read a whole feature file** to check a status.

```bash
backlog list                      # all but shipped/parked, one line each
backlog list -t now,next          # by timing
backlog list -s ready,to-review   # by status (an explicit --status shows shipped too)
backlog list --theme moments      # by theme; --theme none for the unthemed
backlog list --json               # for scripting
backlog show F145                 # header + description
backlog show F145 --head          # header only
backlog show F145 --plan          # add the plan file (these get large - ask for them)
backlog set F145 -s shipped       # updates the table row AND the feature header
backlog set F145 -t now -s ready
backlog set F145 --theme moments  # '' or none clears it
backlog add "Name" -t next -s ready --theme moments -b "One-line description."
backlog next-id                   # lowest free FXX
backlog themes                    # themes in use, with counts
backlog check                     # report drift between table and feature files
backlog migrate                   # move a pre-1.9.0 backlog to Timing + Theme
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

## Statuses, timings and themes

`idea` → `research-needed` → `researching` → `research-done` → `ready` → `in-progress`
→ `to-review` → `shipped`, plus `parked`.

Timing: `now` (shipped or in flight) · `next` (up next) · `later` (planned) · `maybe` (uncommitted).

A **theme** groups related features the way an epic does. Zero or one per feature, free-form,
and never declared anywhere - a theme exists because a feature uses it. Check `backlog themes`
before inventing a name, and reuse an existing spelling rather than adding a case variant.

## Feature file format

```markdown
# FXX: Feature Name

**Status:** ready
**Timing:** next
**Theme:** moments

## Description
What it does and why it matters.
```

The `**Theme:**` line is omitted entirely when the feature has no theme.

## Other operations

- **Reorder:** row position in `backlog.md` defines order within a timing group. Move the row;
  never rename files to reorder.
- **Launch the TUI** (interactive, for the user - not for an agent): `backlog`, after
  running `ensure-installed.sh` above. A standalone-script project may use
  `python3 backlog-tool.py context` instead.
- **Scaffold a new backlog:** `backlog --init` at the project root, one backlog per project.
