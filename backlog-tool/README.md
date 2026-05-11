# Backlog Tool

Terminal TUI for managing feature backlogs with markdown files.

Each feature is a standalone `.md` file. A central `backlog.md` is the source of truth for ordering, status, and category. The tool provides a Textual-based terminal UI for browsing, editing, reordering, and managing features.

## Install

```bash
pipx install /path/to/backlog-tool
```

Or with pip:

```bash
pip install /path/to/backlog-tool
```

## Usage

**Scaffold a new backlog in any project:**

```bash
cd my-project
backlog --init
```

This creates a `context/` directory with a `backlog.md` template and a sample feature file.

**Run the TUI:**

```bash
backlog              # uses ./context by default
backlog my-features  # or specify a custom directory
```

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

## File Structure

```
context/
  backlog.md              # Source of truth: ordering, status, category
  F01-my-feature.md       # Feature description
  F01-my-feature-plan.md  # Optional: implementation plan
  F01-my-feature-research.md  # Optional: research notes
  F02-another.md
  ...
```
