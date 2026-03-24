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
| s | Save all changes |
| r | Reload from disk |
| Ctrl+R | Restart process |
| [ / ] | Resize pane ratio |
| q | Quit |

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
