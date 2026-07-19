# Backlog Tool

Terminal TUI for managing feature backlogs with markdown files.

Each feature is a standalone `.md` file. A central `backlog.md` is the source of truth for ordering, status, and category. The tool provides a Textual-based terminal UI for browsing, editing, reordering, and managing features.

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

### Where your tasks and plans are stored

Everything lives in one plain-markdown directory — `context/` by default, in the project root:

```
my-project/
└── context/
    ├── backlog.md                     # Source of truth: ordering, status, category
    ├── F01-my-feature.md              # The task itself: description / spec
    ├── F01-my-feature-plan.md         # Optional: implementation plan   (press p)
    ├── F01-my-feature-research.md     # Optional: research notes        (press x)
    ├── F02-another-feature.md
    └── ...
```

How it fits together:

- **`backlog.md`** is a markdown table listing every feature with its order, status, and category. When the tool and the individual files disagree, `backlog.md` wins.
- **One task per file**, named `F<NN>-<slug>.md`. IDs are assigned sequentially (`F01`, `F02`, …).
- **Plan and research files derive their names from the task file** — `F01-my-feature.md` gets `F01-my-feature-plan.md` and `F01-my-feature-research.md`. Both are optional and created on demand.
- Nothing is hidden or in a database, so you can `grep`, `git diff`, and edit these by hand or hand them to an AI agent at any time.

If you scaffold into a directory that already contains `F*.md` files, `--init` leaves it untouched rather than overwriting your work.

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
| Enter/Space | Open value picker on Category/Status cell |
| Shift+↑/↓ | Reorder feature within its category |
| e | Edit description |
| p | Edit plan file |
| x | Edit research file |
| n | New feature |
| d | Delete feature (with confirmation) |
| c | Toggle Claude pane for current feature + tab |
| i | Initiate implementation of current feature |
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

Inside `tmux` the session opens in a **new window** (named `impl-FXX`) so the backlog stays on screen; without tmux the TUI suspends. Combined with the agent watch below, the backlog becomes a live progress view while the agent works.

### Agent watch

The TUI always watches the context directory (2s poll) and auto-reloads when files change on disk — so when Claude (or any agent, or another editor) writes to a spec, plan, or research file, you see it immediately. Your unsaved local edits are never clobbered: if disk changes arrive while you're typing or have unsaved work, a banner appears instead and `r` reloads when you're ready.
