---
name: backlog
description: >
  Use this skill when the user mentions backlog, features, feature status,
  feature priorities, or wants to manage/query/update their project backlog.
  Also use when the user asks to scaffold a new backlog or launch the backlog TUI.
allowed-tools: Read, Grep, Edit, Write, Bash, Glob
---

# Backlog Tool — Claude Code Skill

You are helping manage a **feature backlog** stored as markdown files in a `context/` directory.

## Architecture

The backlog system has two parts:

1. **`context/backlog.md`** — The **single source of truth** for feature ordering, status, and category. Contains a markdown table listing all features.
2. **`context/FXX-slug.md`** — Individual feature files containing descriptions, notes, and details.

Optional per-feature files:
- `FXX-slug-plan.md` — Implementation plan
- `FXX-slug-research.md` — Research notes

## Source of Truth Rules

- **`backlog.md` owns**: ordering (row position), status, and category
- **Feature files own**: name, description body, plan, research
- When updating status or category, **always update `backlog.md`** (the table row)
- Feature files also contain status/category headers for human readability — update both when changing

## Statuses (in order)

`idea` → `research-needed` → `researching` → `research-done` → `ready` → `in-progress` → `to-review` → `shipped` → `parked`

## Categories

- `now` — Shipped or actively being worked on
- `next` — Up next, research done or low-hanging fruit
- `later` — Planned but not yet prioritized
- `maybe` — Ideas worth capturing, not committed

## Feature File Format

```markdown
# FXX: Feature Name

**Status:** status-here
**Category:** category-here

## Description
Feature description body...
```

## Common Operations

### Query the backlog
Read `context/backlog.md` and parse the table to answer questions about features, statuses, priorities.

### Update a feature's status
1. Edit the table row in `context/backlog.md`
2. Edit the `**Status:**` line in the feature file

### Add a new feature
1. Determine the next FXX number (scan existing files)
2. Create `context/FXX-slug.md` with the standard header format
3. Add a row to the table in `context/backlog.md`

### Reorder features
Edit the table rows in `context/backlog.md` — row position defines display order.

### Launch the TUI
If the user wants to interactively manage the backlog, first ensure the
`backlog` command is installed, then launch it:

```bash
# Install if missing, or upgrade if the PATH binary is older than this plugin.
# A plain `which backlog` check is NOT enough: it short-circuits forever once any
# binary exists, so plugin auto-updates would never reach the command you run.
PLUGIN_VER=$(python3 -c "import json,os;print(json.load(open(os.environ['CLAUDE_PLUGIN_DIR']+'/.claude-plugin/plugin.json'))['version'])")
CUR_VER=$(backlog --version 2>/dev/null || echo none)

if [ "$CUR_VER" != "$PLUGIN_VER" ]; then
  echo "backlog: $CUR_VER -> $PLUGIN_VER"
  if command -v pipx >/dev/null 2>&1; then
    pipx install --force --backend pip "${CLAUDE_PLUGIN_DIR}"
  else
    pip install --upgrade "${CLAUDE_PLUGIN_DIR}" --break-system-packages
  fi
fi

# Then launch
backlog
```

Prefer `pipx` when present — it isolates the tool instead of writing into system
Python. `--backend pip` sidesteps pipx's `uv` version requirement. Versions older
than 1.2.0 have no `--version` flag, so `CUR_VER` reads `none` and they upgrade
correctly on first run.

If the project uses a standalone `backlog-tool.py` script instead:
```bash
python3 backlog-tool.py context
```

### Scaffold a new backlog
First ensure `backlog` is installed (see above), then:
```bash
backlog --init       # creates context/ with backlog.md and a sample feature
```

## Important

- Always read `context/backlog.md` first to understand the current state
- Never reorder by renaming files — order lives in backlog.md table rows
- Feature file naming: `FXX-slug.md` (e.g., `F03-fire-modes.md`)
- Plan/research files: `FXX-slug-plan.md`, `FXX-slug-research.md`
