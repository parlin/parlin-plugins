# Backlog Tool

Terminal TUI for managing feature backlogs with markdown files.

Each feature is a standalone `.md` file. A central `backlog.md` is the source of truth for ordering, status, timing, and theme. The tool provides a Textual-based terminal UI for browsing, editing, reordering, and managing features.

## Getting started

**1. Install** (pipx recommended — keeps it isolated and on your `PATH`):

```bash
pipx install /path/to/backlog-tool
```

Or with pip:

```bash
pip install /path/to/backlog-tool
```

**2. Scaffold a backlog** in whichever project you want to track. Run this at the project root so there's one backlog per project:

```bash
cd ~/code/my-project
backlog --init
```

That creates a `context/` directory containing a `backlog.md` template and one sample feature (`F01-example-feature.md`), then tells you what it wrote.

**3. Open the TUI:**

```bash
backlog                  # uses ./context by default
backlog my-features      # or point it at a custom directory
backlog --help           # all commands
```

Press `n` to add a feature, `e` to edit its description, `s` to save, `q` to quit. Full key list below.

**4. Or drive it without the UI:**

```bash
backlog list                      # every feature except shipped/parked, one line each
backlog list -t now,next          # filter by timing (now/next/later/maybe)
backlog list -s ready,to-review   # filter by status
backlog list --theme moments      # filter by theme; --theme none for the unthemed
backlog list --json               # machine-readable
backlog show F12                  # header + description
backlog show F12 --plan           # and its plan file
backlog set F12 -s shipped        # updates the table row and the feature header together
backlog set F12 --theme moments   # put it in a theme; --theme "" clears it
backlog add "New thing" -t next -s ready --theme moments -b "One line of description."
backlog next-id                   # lowest free FXX
backlog themes                    # themes in use, with counts
backlog check                     # report drift between the table and the feature files
backlog migrate                   # bring a pre-1.9.0 backlog to Timing + Theme
```

These print one padded line per feature and never open a UI, which is what makes them
cheap for an AI agent to call: answering "what is F12's status" costs a few tokens instead
of a read of the whole table. `backlog set` is the one to reach for when changing state - it
writes both files, so the table and the feature header cannot drift apart. Add `-d <dir>` to
point any command at a backlog other than `./context`.

### Where your tasks and plans are stored

Everything lives in one plain-markdown directory — `context/` by default, in the project root:

```
my-project/
└── context/
    ├── backlog.md                     # Source of truth: ordering, status, timing, theme
    ├── F01-my-feature.md              # The task itself: description / spec
    ├── F01-my-feature-plan.md         # Optional: implementation plan   (press p)
    ├── F01-my-feature-research.md     # Optional: research notes        (press x)
    ├── F02-another-feature.md
    └── ...
```

How it fits together:

- **`backlog.md`** is a markdown table listing every feature with its order, theme, timing, and status. When the tool and the individual files disagree, `backlog.md` wins.
- **One task per file**, named `F<NN>-<slug>.md`. IDs are assigned sequentially (`F01`, `F02`, …).
- **Plan and research files derive their names from the task file** — `F01-my-feature.md` gets `F01-my-feature-plan.md` and `F01-my-feature-research.md`. Both are optional and created on demand.
- Nothing is hidden or in a database, so you can `grep`, `git diff`, and edit these by hand or hand them to an AI agent at any time.

If you scaffold into a directory that already contains `F*.md` files, `--init` leaves it untouched rather than overwriting your work.

## Themes

A theme groups related features the way an epic does. A feature has zero or one theme, and
themes are not declared anywhere: one exists because a feature uses it. The picker offers the
themes already in use plus "new theme…", which is how a new one gets created - and typing a
name that differs only in case reuses the existing spelling rather than making a twin.

`backlog themes` lists them with counts, and both the TUI's Theme column and
`backlog list --theme` filter on them. `--theme none` finds the features that have none.

## Timing, formerly Category

The column that holds `now` / `next` / `later` / `maybe` is called **Timing** as of 1.9.0.
Feature files write `**Timing:**`, and `backlog.md` has a `Timing` column. Older backlogs keep
working: `**Category:**` is still read, the five-column table still parses, and `-c/--category`
is still accepted everywhere `-t/--timing` is. `backlog migrate` converts a backlog in place
(`--dry-run` shows what it would touch first).

## Why

A nimble but powerful task manager that lives **in your terminal, inside your project** — so you can stay where the work happens instead of switching to a separate app to check what's next.

It deliberately uses plain markdown in a conventional file layout: tasks and plans are individual `.md` files with obvious, intuitive names. That structure is already familiar to AI coding agents, so an agent can read, write, and reason about your backlog with no special integration — the files *are* the API. Your backlog stays greppable, diffable, and version-controlled alongside the code it describes.

## User experience

- **Navigate by arrow keys or mouse** — both work; use whichever suits the moment.
- **Keyboard shortcuts for everything** — see the table below.

## Keyboard Controls

| Key | Action |
|---|---|
| ↑/↓ | Move between rows |
| ←/→ | Move between columns |
| Enter/Space | Open value picker on the Theme, Timing or Status cell |
| Shift+↑/↓ | Reorder feature within its timing group |
| f | Filter the column the cursor is in: Theme, Timing or Status (also: click a **▾** header, or ↑ onto it and Enter) |
| e | Edit description |
| p | Edit plan file |
| x | Edit research file |
| n | New feature |
| d | Delete feature (with confirmation) |
| c | Toggle Claude pane for current feature + tab |
| i | Initiate implementation of current feature |
| o | Open the agent session interactively (from Agent tab) |
| s | Save all changes |
| r | Reload from disk |
| Ctrl+R | Restart process |
| [ / ] | Resize pane ratio |
| q | Quit |

### Claude pane

Press `c` on a feature row to launch an interactive Claude Code session briefed for that feature and the currently active tab:

- **Description tab** — conversational refinement; Claude won't write to the spec without confirmation.
- **Plan tab** — Claude drafts or refines `FXX-…-plan.md`.
- **Research tab** — Claude investigates and writes findings to `FXX-…-research.md`.

Inside `tmux`, the pane opens as a vertical split next to the TUI. Outside `tmux`, the TUI suspends and Claude takes the full terminal until you exit. Press `c` again to close the pane; switching tabs while a pane is open will prompt to close and respawn with the new brief.

### Initiate implementation

Press `i` on a feature row to hand it to an agent for implementation. The tool flushes all unsaved work to disk, sets the feature's status to `in-progress`, and launches a Claude Code session briefed to work through the plan step by step — ticking the plan's checkboxes (`- [ ]` → `- [x]`) as it completes them, and setting the status to `to-review` when done. If no plan exists yet, the brief has the agent write one first.

**Implementations always run in an isolated git worktree** — `.worktrees/FXX-slug/` on branch `impl/FXX-slug` — so any number of features can be implemented in parallel without agents sharing a working directory. The agent commits to its branch and never merges; you review and merge when the feature reaches `to-review` (then `git worktree remove .worktrees/FXX-slug`). Backlog files stay in the main checkout (the brief references them by absolute path), so plan checkboxes and status updates remain live in the TUI. Non-git projects simply run in the project root.

The agent runs in a **detached tmux session** (`impl-<project>-FXX`) that survives even a TUI restart. A fourth tab — **Agent** — appears on the feature, mirroring the agent's terminal live (read-only). The feature list shows each row's agent state at a glance: `⚙` working, `✋` waiting for your input (e.g. a permission prompt), `✓` finished. Press `o` in the Agent tab to open the session interactively (answer prompts, type to the agent), and detach (`Ctrl+B D`) to come back. `i` on an already-running feature jumps to its Agent tab instead of relaunching. `Esc` leaves the Agent tab.

Without tmux installed, `i` falls back to opening a plain new terminal window (macOS) or suspending the TUI (other platforms).

### Agent watch

The TUI always watches the context directory (2s poll) and auto-reloads when files change on disk — so when Claude (or any agent, or another editor) writes to a spec, plan, or research file, you see it immediately. Your unsaved local edits are never clobbered: if disk changes arrive while you're typing or have unsaved work, a banner appears instead and `r` reloads when you're ready.

## Development

The package is split so a query never pays for the UI:

    src/backlog_tool/model.py   parsing and writing (no Textual import)
    src/backlog_tool/cli.py     non-interactive commands, dispatch, entry point
    src/backlog_tool/tui.py     the Textual app

Tests are stdlib `unittest` and need no dependencies beyond Python:

    cd backlog-tool && python3 -m unittest discover -s tests -t .

After editing the source, reinstall before the `backlog` on your PATH changes:

    pipx install --force --backend pip ./backlog-tool
