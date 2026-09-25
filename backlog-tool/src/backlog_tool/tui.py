#!/usr/bin/env python3
"""
Backlog Manager
Terminal TUI for managing feature backlog files.

Usage: python3 backlog-tool.py [context-dir]
  context-dir defaults to ./context

Keys:
  ↑/↓          Move between rows (same column)
  ←/→          Move between columns (same row)
  Enter/Space   Open value picker on Category/Status cell
  Shift+↑/↓    Reorder feature within its category group
  f             Filter categories (also: click the Cat. header, or ↑ onto it + Enter)
  e             Edit description        s       Save all changes
  p             Edit plan file          x       Edit research file
  n             New feature             d       Delete feature
  r             Reload from disk        Ctrl+r  Restart process
  c             Toggle Claude pane      i       Initiate implementation
  o             Open agent interactive  q       Quit

Files changed on disk (e.g. by an agent) reload automatically; unsaved
local edits are never clobbered — a banner offers \\[r] instead.
"""

import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from textual.app import App
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.events import Key
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.message import Message
from textual.widget import Widget
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Label,
    ListItem,
    ListView,
    Markdown,
    OptionList,
    SelectionList,
    Static,
    TextArea,
    Input,
)
from textual.widgets.option_list import Option
from textual.widgets.selection_list import Selection
from rich.text import Text

from .model import (
    BACKLOG_TEMPLATE,
    SAMPLE_FEATURE,
    CATEGORIES,
    CAT_ORDER,
    STATUSES,
    Feature,
    apply_backlog_order,
    detect_associated_files,
    do_init,
    get_version,
    load_associated_body,
    load_features,
    next_fid,
    parse_feature_file,
    save_associated_file,
    save_backlog_index,
    save_feature_file,
    sort_features,
)

# ── Constants ──────────────────────────────────────────────────────────

# Column keys in order
COL_KEYS = ["fid", "name", "category", "status"]
EDITABLE_COLS = {"category", "status"}

CAT_COLORS = {
    "now":   "#22c55e",
    "next":  "#3b82f6",
    "later": "#a855f7",
    "maybe": "#6b7280",
}
STATUS_COLORS = {
    "idea":            "#6b7280",
    "research-needed": "#d97706",
    "researching":     "#a855f7",
    "research-done":   "#8b5cf6",
    "ready":           "#3b82f6",
    "to-review":       "#06b6d4",
    "in-progress":     "#f59e0b",
    "shipped":         "#22c55e",
    "parked":          "#ef4444",
}

# Claude pane launcher
CLAUDE_BIN = shutil.which("claude") or "claude"
TMUX_BIN = shutil.which("tmux")

# Agent sessions live in detached tmux sessions named <prefix><FID>; the TUI
# mirrors them via capture-pane (see F01 plan). Best-effort patterns that mean
# the agent is waiting for a human answer (permission prompts etc.).
NEEDS_INPUT_RE = re.compile(
    r"do you want|allow this|\(y/n\)|\d\.\s*yes\b|press enter to continue", re.IGNORECASE
)
AGENT_TAB_LABELS = {"running": "Agent ⚙", "attention": "Agent ✋", "done": "Agent ✓"}
AGENT_ROW_MARKERS = {"running": " [#3b82f6]⚙[/]", "attention": " [bold #f59e0b]✋[/]", "done": " [#22c55e]✓[/]"}


def _tmux_out(*args: str) -> str | None:
    """Run a tmux command, returning stdout, or None on any failure."""
    if not TMUX_BIN:
        return None
    try:
        return subprocess.check_output([TMUX_BIN, *args], text=True, stderr=subprocess.DEVNULL)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None

# Per-tab brief templates. Substitution keys: {fid}, {name}, {ctx}, {spec_filename},
# {plan_filename}, {research_filename}. {ctx} is the basename of the context dir
# (e.g. "context") so the brief uses a project-root-relative path.
CLAUDE_PROMPTS = {
    "description": (
        'We\'re refining feature {fid} — "{name}". Spec: {ctx}/{spec_filename}. '
        'Help me sharpen the description, scope, and open questions; propose edits I '
        'can apply to the spec. Stay in dialogue — do not write to the spec without confirmation.'
    ),
    "plan_new": (
        'Draft an implementation plan for feature {fid} — "{name}". '
        'Spec: {ctx}/{spec_filename}. Write the plan to {ctx}/{plan_filename}. '
        'Use markdown with sections: Overview, Files to change, Step-by-step, Risks, Test plan.'
    ),
    "plan_existing": (
        'Refine the implementation plan for feature {fid} — "{name}". '
        'Spec: {ctx}/{spec_filename}. Existing plan: {ctx}/{plan_filename}. '
        'Update the plan in place to reflect any new constraints or feedback I share.'
    ),
    "research_new": (
        'Research feature {fid} — "{name}". Spec: {ctx}/{spec_filename}. '
        'Investigate open questions and unknowns; capture findings in '
        '{ctx}/{research_filename} with source links where possible.'
    ),
    "research_existing": (
        'Continue research on feature {fid} — "{name}". Spec: {ctx}/{spec_filename}. '
        'Existing notes: {ctx}/{research_filename}. Extend or revise as we discuss new angles.'
    ),
    "implement": (
        'Implement feature {fid} — "{name}". Spec: {ctx}/{spec_filename}. '
        'Plan: {ctx}/{plan_filename}. Work through the plan step by step, ticking its '
        'checkboxes (- [ ] → - [x]) in the plan file as you complete each step. '
        'When everything is done and verified, set the {fid} status to to-review '
        'in {ctx}/backlog.md.'
    ),
    "implement_no_plan": (
        'Implement feature {fid} — "{name}" from its spec: {ctx}/{spec_filename}. '
        'There is no plan yet: first write a short step-by-step plan with checkboxes '
        'to {ctx}/{plan_filename}, then implement it, ticking the boxes as you go. '
        'When everything is done and verified, set the {fid} status to to-review '
        'in {ctx}/backlog.md.'
    ),
}



# ── Value Picker dialog ───────────────────────────────────────────────

class ValuePickerScreen(ModalScreen):
    """Small modal showing a list of options to pick from."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", priority=True),
    ]

    DEFAULT_CSS = """
    ValuePickerScreen {
        align: center middle;
    }
    #picker-box {
        width: 30;
        border: solid $accent;
        background: $surface;
        padding: 1 2;
    }
    #picker-title {
        text-style: bold;
        margin-bottom: 1;
    }
    #picker-hint {
        color: $text-muted;
        margin-top: 1;
    }
    """

    def __init__(self, title: str, options: list[str], current: str, colors: dict[str, str]):
        super().__init__()
        self._title = title
        self._options = options
        self._current = current
        self._colors = colors
        self._dismissed = False
        # Calculate heights: 1 per option +4 extra rows for comfort, +6 for title/hint/padding/border
        self._list_height = len(options) + 4
        self._box_height = self._list_height + 6

    def compose(self):
        box = Vertical(id="picker-box")
        box.styles.height = self._box_height
        with box:
            yield Label(f" {self._title} ", id="picker-title")
            option_widgets = []
            for i, opt in enumerate(self._options):
                color = self._colors.get(opt, "white")
                option_widgets.append(Option(f"[{color}]  {opt}[/]", id=opt))
            ol = OptionList(*option_widgets, id="picker-list")
            ol.styles.height = self._list_height
            yield ol
            yield Label("[↑/↓] Navigate  [Enter] Select  [Esc] Cancel", id="picker-hint")

    def on_mount(self):
        ol = self.query_one("#picker-list", OptionList)
        for i, opt in enumerate(self._options):
            if opt == self._current:
                ol.highlighted = i
                break
        ol.focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected):
        if not self._dismissed:
            self._dismissed = True
            self.dismiss(event.option.id)

    def action_cancel(self):
        if not self._dismissed:
            self._dismissed = True
            self.dismiss(None)


# ── Category filter dialog ────────────────────────────────────────────

ALL_OPTION = "_all"


class CategoryFilterScreen(ModalScreen):
    """Multiselect of categories to show. Dismisses with the chosen set, or None on cancel."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", priority=True),
        # Enter would otherwise toggle the highlighted option, like Space does
        Binding("enter", "apply", "Apply", priority=True),
    ]

    DEFAULT_CSS = """
    CategoryFilterScreen {
        align: center middle;
    }
    #filter-box {
        width: 36;
        height: auto;
        border: solid $accent;
        background: $surface;
        padding: 1 2;
    }
    #filter-title {
        text-style: bold;
        margin-bottom: 1;
    }
    #filter-list { height: auto; }
    #filter-buttons { height: auto; margin-top: 1; }
    #filter-buttons Button { min-width: 10; margin-right: 1; }
    """

    def __init__(self, categories: list[str], visible: set[str]):
        super().__init__()
        self._categories = categories
        self._visible = visible
        self._syncing = False
        self._dismissed = False

    def compose(self):
        with Vertical(id="filter-box"):
            yield Label(" Show categories ", id="filter-title")
            all_on = all(c in self._visible for c in self._categories)
            options = [Selection("All", ALL_OPTION, all_on)]
            for cat in self._categories:
                color = CAT_COLORS.get(cat, "white")
                options.append(Selection(f"[{color}]{cat}[/]", cat, cat in self._visible))
            yield SelectionList[str](*options, id="filter-list")
            with Horizontal(id="filter-buttons"):
                yield Button("Apply", id="filter-apply", variant="primary")
                yield Button("Cancel", id="filter-cancel")

    def on_mount(self):
        self.query_one("#filter-list", SelectionList).focus()

    def on_selection_list_selection_toggled(self, event: SelectionList.SelectionToggled):
        """Keep "All" in step with the individual categories."""
        if self._syncing:
            return
        sl = self.query_one("#filter-list", SelectionList)
        self._syncing = True
        try:
            if event.selection.value == ALL_OPTION:
                if ALL_OPTION in sl.selected:
                    sl.select_all()
                else:
                    sl.deselect_all()
            elif all(c in sl.selected for c in self._categories):
                sl.select(ALL_OPTION)
            else:
                sl.deselect(ALL_OPTION)
        finally:
            self._syncing = False

    def on_button_pressed(self, event: Button.Pressed):
        event.stop()
        if event.button.id == "filter-apply":
            self.action_apply()
        else:
            self.action_cancel()

    def action_apply(self):
        if not self._dismissed:
            self._dismissed = True
            sl = self.query_one("#filter-list", SelectionList)
            self.dismiss({v for v in sl.selected if v != ALL_OPTION})

    def action_cancel(self):
        if not self._dismissed:
            self._dismissed = True
            self.dismiss(None)


# ── New Feature dialog ─────────────────────────────────────────────────

class NewFeatureScreen(ModalScreen):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def compose(self):
        yield Vertical(
            Label(" New Feature ", id="dialog-title"),
            Label("Feature name:"),
            Input(id="feat-name", placeholder="e.g. Dark mode"),
            Label(""),
            Label("[Enter] Create  [Escape] Cancel", id="dialog-hint"),
            id="dialog",
        )

    def on_input_submitted(self, event: Input.Submitted):
        name = event.value.strip()
        self.dismiss(name if name else None)

    def action_cancel(self):
        self.dismiss(None)


# ── Confirm tab switch dialog ─────────────────────────────────────────

class ConfirmSwitchScreen(ModalScreen):
    """Asks user what to do with unsaved changes when switching tabs."""

    BINDINGS = [Binding("escape", "cancel", "Cancel", priority=True)]

    DEFAULT_CSS = """
    ConfirmSwitchScreen { align: center middle; }
    #confirm-box {
        width: 44;
        border: solid $accent;
        background: $surface;
        padding: 1 2;
    }
    #confirm-title { text-style: bold; margin-bottom: 1; }
    #confirm-hint { color: $text-muted; margin-top: 1; }
    """

    def __init__(self):
        super().__init__()
        self._dismissed = False
        self._list_height = 3 + 4
        self._box_height = self._list_height + 6

    def compose(self):
        box = Vertical(id="confirm-box")
        box.styles.height = self._box_height
        with box:
            yield Label(" Unsaved changes ", id="confirm-title")
            ol = OptionList(
                Option("  Save and switch", id="save"),
                Option("  Discard and switch", id="discard"),
                Option("  Cancel", id="cancel"),
                id="confirm-list",
            )
            ol.styles.height = self._list_height
            yield ol
            yield Label("[↑/↓] Navigate  [Enter] Select  [Esc] Cancel", id="confirm-hint")

    def on_mount(self):
        self.query_one("#confirm-list", OptionList).focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected):
        if not self._dismissed:
            self._dismissed = True
            self.dismiss(event.option.id)

    def action_cancel(self):
        if not self._dismissed:
            self._dismissed = True
            self.dismiss("cancel")


# ── Confirm delete dialog ─────────────────────────────────────────────

class ConfirmDeleteScreen(ModalScreen):
    """Asks user to confirm deletion of a feature."""

    BINDINGS = [Binding("escape", "cancel", "Cancel", priority=True)]

    DEFAULT_CSS = """
    ConfirmDeleteScreen { align: center middle; }
    #delete-box {
        width: 50;
        height: 12;
        border: solid $error;
        background: $surface;
        padding: 1 2;
    }
    #delete-title { text-style: bold; margin-bottom: 1; }
    #delete-hint { color: $text-muted; margin-top: 1; }
    #delete-list { height: 6; }
    #delete-list > ListItem { padding: 0 1; }
    """

    def __init__(self, fid: str, name: str):
        super().__init__()
        self._fid = fid
        self._name = name
        self._dismissed = False

    def compose(self):
        with Vertical(id="delete-box"):
            yield Label(f" Delete {self._fid}: {self._name}? ", id="delete-title")
            yield ListView(
                ListItem(Label("  Yes, delete permanently"), id="confirm"),
                ListItem(Label("  Cancel"), id="cancel-item"),
                id="delete-list",
            )
            yield Label("[↑/↓] Navigate  [Enter] Select  [Esc] Cancel", id="delete-hint")

    def on_mount(self):
        self.query_one("#delete-list", ListView).focus()

    def on_list_view_selected(self, event: ListView.Selected):
        if self._dismissed:
            return
        self._dismissed = True
        if event.item.id == "confirm":
            self.dismiss(True)
        else:
            self.dismiss(False)

    def action_cancel(self):
        if not self._dismissed:
            self._dismissed = True
            self.dismiss(False)


# ── Confirm close Claude pane dialog ──────────────────────────────────

class ConfirmCloseClaudeScreen(ModalScreen):
    """Asks user to confirm closing the active Claude pane when switching tabs."""

    BINDINGS = [Binding("escape", "cancel", "Cancel", priority=True)]

    DEFAULT_CSS = """
    ConfirmCloseClaudeScreen { align: center middle; }
    #cc-box {
        width: 56;
        border: solid $accent;
        background: $surface;
        padding: 1 2;
    }
    #cc-title { text-style: bold; margin-bottom: 1; }
    #cc-hint { color: $text-muted; margin-top: 1; }
    """

    def __init__(self):
        super().__init__()
        self._dismissed = False
        self._list_height = 2 + 4
        self._box_height = self._list_height + 6

    def compose(self):
        box = Vertical(id="cc-box")
        box.styles.height = self._box_height
        with box:
            yield Label(" Switching tab will close the Claude pane ", id="cc-title")
            ol = OptionList(
                Option("  Close pane and switch", id="confirm"),
                Option("  Cancel", id="cancel"),
                id="cc-list",
            )
            ol.styles.height = self._list_height
            yield ol
            yield Label("[↑/↓] Navigate  [Enter] Select  [Esc] Cancel", id="cc-hint")

    def on_mount(self):
        self.query_one("#cc-list", OptionList).focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected):
        if not self._dismissed:
            self._dismissed = True
            self.dismiss(event.option.id == "confirm")

    def action_cancel(self):
        if not self._dismissed:
            self._dismissed = True
            self.dismiss(False)


# ── Tab bar widget ────────────────────────────────────────────────────

class TabBar(Static, can_focus=True):
    """Horizontal tab bar with arrow-key navigation and Enter/click to activate."""

    class TabActivated(Message):
        """Posted when a tab is activated via Enter or click."""
        def __init__(self, tab_id: str):
            super().__init__()
            self.tab_id = tab_id

    DEFAULT_CSS = """
    TabBar {
        height: 1;
        margin-bottom: 1;
    }
    """

    TAB_IDS = ["description", "research", "plan"]

    def __init__(self, **kwargs):
        super().__init__("", **kwargs)
        self.tab_ids: list[str] = list(self.TAB_IDS)  # per-feature; may gain "agent"
        self._labels: dict[str, str] = {
            "description": "Description",
            "plan": "Plan +",
            "research": "Research +",
            "agent": "Agent",
        }
        self._focused_idx: int = 0
        self._active_id: str = "description"
        self._tab_ranges: list[tuple[int, int]] = []  # (start_x, end_x) per tab

    def set_tabs(self, tab_ids: list[str]):
        if tab_ids != self.tab_ids:
            self.tab_ids = list(tab_ids)
            if self._focused_idx >= len(self.tab_ids):
                self._focused_idx = len(self.tab_ids) - 1
            self._refresh_display()

    def set_active(self, tab_id: str):
        self._active_id = tab_id
        for i, t in enumerate(self.tab_ids):
            if t == tab_id:
                self._focused_idx = i
                break
        self._refresh_display()

    def set_label(self, tab_id: str, label: str):
        self._labels[tab_id] = label
        self._refresh_display()

    def _refresh_display(self):
        parts = []
        self._tab_ranges = []
        offset = 0
        has_focus = self.has_focus
        for i, tid in enumerate(self.tab_ids):
            label = self._labels[tid]
            is_active = tid == self._active_id
            is_focused = i == self._focused_idx and has_focus
            padded = f" {label} "
            tab_width = len(padded)

            if is_active and is_focused:
                parts.append(f"[bold white on #2563eb]{padded}[/]")
            elif is_active:
                parts.append(f"[bold #aabbdd on #1e4fad]{padded}[/]")
            elif is_focused:
                parts.append(f"[bold white on #555]{padded}[/]")
            else:
                parts.append(f"[#888 on #333]{padded}[/]")

            self._tab_ranges.append((offset, offset + tab_width))
            offset += tab_width + 1
            parts.append(" ")
        self.update("".join(parts))

    def on_mount(self):
        self._refresh_display()

    def on_focus(self, event):
        self._refresh_display()

    def on_blur(self, event):
        self._refresh_display()

    def on_key(self, event: Key):
        if event.key == "left":
            if self._focused_idx > 0:
                self._focused_idx -= 1
                self._refresh_display()
            event.prevent_default()
            event.stop()
        elif event.key == "right":
            if self._focused_idx < len(self.tab_ids) - 1:
                self._focused_idx += 1
                self._refresh_display()
            event.prevent_default()
            event.stop()
        elif event.key in ("enter", "space"):
            self.post_message(self.TabActivated(self.tab_ids[self._focused_idx]))
            event.prevent_default()
            event.stop()

    def on_click(self, event):
        x = event.x
        for i, (start, end) in enumerate(self._tab_ranges):
            if start <= x < end:
                self._focused_idx = i
                self.post_message(self.TabActivated(self.tab_ids[i]))
                self._refresh_display()
                return


# ── Detail pane ────────────────────────────────────────────────────────

class DetailPane(Widget):
    class EditRequested(Message):
        """Posted when user double-clicks the markdown view to start editing."""

    DEFAULT_CSS = """
    DetailPane {
        width: 1fr;
        padding: 1 2;
    }
    #detail-header { height: auto; margin-bottom: 1; }
    #detail-meta { height: auto; margin-bottom: 1; color: $text-muted; }
    #detail-body { height: 1fr; }
    #detail-body-md { height: 1fr; }
    #detail-body-md.hidden { display: none; }
    #detail-body.hidden { display: none; }
    #detail-body-term { height: 1fr; overflow-y: auto; background: #101010; padding: 0 1; }
    #detail-body-term.hidden { display: none; }
    #editor-save-bar {
        dock: bottom;
        height: 1;
        background: #1a3a2a;
        color: #6ee7a0;
        padding: 0 1;
        display: none;
    }
    #editor-save-bar.visible { display: block; }
    #editor-save-bar.saved { background: #14332a; color: #4ade80; }
    #editor-save-bar .save-hint { width: 1fr; }
    #editor-save-bar Button {
        min-width: 10;
        height: 1;
        margin: 0 0 0 1;
        background: #22c55e;
        color: #000;
        border: none;
        text-style: bold;
    }
    #editor-save-bar Button.hidden { display: none; }
    """

    def compose(self):
        yield Static("", id="detail-header")
        yield Static("", id="detail-meta")
        yield TabBar(id="tab-bar")
        yield Markdown("", id="detail-body-md")
        yield TextArea("", id="detail-body", language="markdown", classes="hidden")
        yield Static("", id="detail-body-term", classes="hidden")
        with Horizontal(id="editor-save-bar"):
            yield Static("", id="save-hint", classes="save-hint")
            yield Button("Save", id="editor-save-btn", variant="success")

    def set_active_tab(self, tab: str, feature: Feature | None = None, agent_state: str | None = None):
        """Highlight the active tab, update file-exists indicators, and show
        the Agent tab when this feature has (or had) an agent session."""
        tab_bar = self.query_one("#tab-bar", TabBar)
        tabs = list(TabBar.TAB_IDS)
        if agent_state:
            tabs.append("agent")
            tab_bar.set_label("agent", AGENT_TAB_LABELS.get(agent_state, "Agent"))
        tab_bar.set_tabs(tabs)
        tab_bar.set_active(tab)
        if feature:
            tab_bar.set_label("plan", "Plan \u25cf" if feature.has_plan else "Plan +")
            tab_bar.set_label("research", "Research \u25cf" if feature.has_research else "Research +")

    def show_save_bar(self, visible: bool, state: str = "modified"):
        """Show/hide the editor save bar. state: 'modified' or 'saved'."""
        bar = self.query_one("#editor-save-bar", Horizontal)
        hint = self.query_one("#save-hint", Static)
        btn = self.query_one("#editor-save-btn", Button)
        if visible:
            bar.add_class("visible")
            if state == "saved":
                bar.add_class("saved")
                btn.add_class("hidden")
                hint.update("  [bold]Saved to disk[/bold]")
            else:
                bar.remove_class("saved")
                btn.remove_class("hidden")
                hint.update("  \\[Ctrl+S] save to disk  \\[Esc] exit without saving")
        else:
            bar.remove_class("visible")
            bar.remove_class("saved")

    def on_click(self, event):
        """Double-click on the rendered markdown → enter edit mode."""
        md_widget = self.query_one("#detail-body-md", Markdown)
        if not md_widget.has_class("hidden") and event.chain >= 2:
            self.post_message(self.EditRequested())

    def show_agent_capture(self, capture: str, ended: bool = False):
        """Render captured agent-terminal output in the terminal view."""
        term = self.query_one("#detail-body-term", Static)
        if not capture.strip():
            term.update("(waiting for agent output\u2026)")
            return
        text = Text.from_ansi(capture.rstrip("\n"))
        if ended:
            text.append("\n\n\u2014 session ended \u2014", style="bold green")
        term.update(text)

    def update_content(self, feature: Feature | None, editing: bool = False, active_tab: str = "description",
                       agent_state: str | None = None, agent_capture: str = ""):
        """Update the detail pane."""
        header = self.query_one("#detail-header", Static)
        meta = self.query_one("#detail-meta", Static)
        body = self.query_one("#detail-body", TextArea)
        body_md = self.query_one("#detail-body-md", Markdown)
        term = self.query_one("#detail-body-term", Static)

        self.show_save_bar(False)
        self.set_active_tab(active_tab, feature, agent_state)

        if feature is None:
            header.update("No feature selected")
            meta.update("")
            body.load_text("")
            body.read_only = True
            body.add_class("hidden")
            term.add_class("hidden")
            body_md.remove_class("hidden")
            body_md.update("")
            return

        dirty = " \u2022" if feature.dirty else ""
        mode_label = ""
        if editing:
            mode_label = f"  [bold #f59e0b]editing {active_tab}[/]"
        elif active_tab == "agent":
            mode_label = "  [#6b7280]read-only agent view \u2014 \\[o] open interactive[/]"
        header.update(f"[bold]{feature.fid}: {feature.name}[/bold]{dirty}{mode_label}")

        cc = CAT_COLORS.get(feature.category, "white")
        sc = STATUS_COLORS.get(feature.status, "white")
        meta.update(f"Category: [{cc}]{feature.category}[/]  Status: [{sc}]{feature.status}[/]  File: {feature.filename}")

        # Agent tab: live terminal mirror \u2014 no editor, no markdown.
        if active_tab == "agent":
            body.add_class("hidden")
            body_md.add_class("hidden")
            term.remove_class("hidden")
            self.show_agent_capture(agent_capture, ended=(agent_state == "done"))
            return
        term.add_class("hidden")

        # Load content based on active tab
        if active_tab == "plan":
            content = feature.plan_body
        elif active_tab == "research":
            content = feature.research_body
        else:
            content = feature.body

        if editing:
            # Show TextArea, hide Markdown
            body_md.add_class("hidden")
            body.remove_class("hidden")
            body.read_only = False
            body.load_text(content)
            body.focus()
        else:
            # Show Markdown, hide TextArea
            body.add_class("hidden")
            body_md.remove_class("hidden")
            body_md.update(content)


# ── Main app ───────────────────────────────────────────────────────────

class BacklogApp(App):
    # Pane width ratios: (left%, right%) — cycled with [ and ]
    PANE_RATIOS = [(20, 80), (30, 70), (40, 60), (50, 50), (60, 40), (70, 30)]
    DEFAULT_RATIO_IDX = 2  # 40:60

    CSS = """
    Screen { layout: horizontal; }
    #left-pane {
        width: 40%;
        border-right: solid $primary-background;
    }
    #status-bar {
        dock: bottom;
        height: 1;
        background: $primary-background;
        color: $text;
        padding: 0 1;
    }
    #update-bar {
        dock: bottom;
        height: 1;
        background: $primary-background;
        color: $primary-background;
        padding: 0 1;
    }
    #update-bar.visible {
        background: #1e3a5f;
        color: #7cc4f5;
    }
    #dialog {
        align: center middle;
        padding: 1 2;
        border: solid $accent;
        background: $surface;
        width: 50;
        height: 12;
    }
    #dialog-title { text-style: bold; margin-bottom: 1; }
    #dialog-hint { color: $text-muted; }
    DataTable { height: 1fr; }
    DataTable > .datatable--cursor { background: $accent; color: $text; }
    """

    TITLE = "Backlog"
    BINDINGS = [
        # Letter keys: NO priority — so they type normally in TextArea
        Binding("s", "save", "Save backlog"),
        Binding("e", "edit", "Edit desc"),
        Binding("p", "edit_plan", "Plan"),
        Binding("x", "edit_research", "Research"),
        Binding("n", "new_feature", "New"),
        Binding("f", "filter_categories", "Filter"),
        Binding("d", "delete_feature", "Delete"),
        Binding("c", "toggle_claude", "Claude"),
        Binding("i", "implement", "Implement"),
        Binding("o", "open_agent_attach", "Attach", show=False),
        Binding("r", "reload", "Reload"),
        # Modifier keys: priority OK — won't conflict with typing
        Binding("ctrl+s", "save", "Save", priority=True, show=False),
        Binding("ctrl+r", "restart", "Restart", priority=True),
        Binding("q", "quit_app", "Quit"),
        Binding("[", "pane_ratio_left", "← Pane", show=False),
        Binding("]", "pane_ratio_right", "Pane →", show=False),
        Binding("escape", "stop_edit", "Back to list", show=False),
        Binding("tab", "focus_next", "Tab focus", show=False),
    ]

    editing = reactive(False)

    def __init__(self, context_dir: Path):
        super().__init__()
        self.context_dir = context_dir
        self.features: list[Feature] = []
        self.display_rows: list[Feature | None] = []
        self._last_cursor_row: int = 0
        self._reload_confirmed: bool = False
        self._restart_confirmed: bool = False
        self._quit_confirmed: bool = False
        self._order_dirty: bool = False  # manual reorder not yet written to backlog.md
        self._picker_open: bool = False
        self._hidden_cats: set[str] = set()  # category filter — view state only, never saved
        self._header_focused: bool = False   # keyboard cursor is on the Cat. column header
        self._active_tab: str = "description"  # "description", "plan", or "research"
        self._edit_snapshot: str = ""  # original text when editing started
        self._script_path = Path(__file__).resolve()
        self._script_mtime: float = self._script_path.stat().st_mtime
        self._update_available: bool = False
        self._ratio_idx: int = self.DEFAULT_RATIO_IDX
        self._claude_pane_id: str | None = None
        self._fs_pending: bool = False  # disk changed while local edits were unsaved
        # Agent sessions (detached tmux, mirrored read-only — see F01 plan)
        self._agent_alive: set[str] = set()          # fids with a live session
        self._agent_attention: dict[str, bool] = {}  # fid -> waiting for input?
        self._agent_done: set[str] = set()           # sessions that ended this run
        self._agent_last_capture: dict[str, str] = {}
        # Title shows the project folder (parent of context dir) so multiple
        # backlogs on screen are distinguishable; sub-title puts the tool
        # version in the header row.
        project_name = context_dir.parent.resolve().name or "Backlog"
        self.title = f"{project_name} — Backlog"
        self.sub_title = f"v{get_version()}"
        self._load_features()
        self._fs_snapshot: dict[str, float] = self._scan_context_mtimes()

    def _load_features(self):
        self.features = load_features(
            self.context_dir, with_bodies=True,
            warn=lambda msg: print(msg, file=sys.stderr),
        )

    def _detect_associated_files(self):
        detect_associated_files(self.context_dir, self.features, with_bodies=True)

    def _sort_features(self):
        sort_features(self.features)

    def _apply_backlog_order(self):
        apply_backlog_order(self.context_dir, self.features)

    def _build_display_rows(self) -> list[Feature | None]:
        rows: list[Feature | None] = []
        current_cat = None
        for f in self.features:
            if f.category in self._hidden_cats:
                continue
            if f.category != current_cat:
                current_cat = f.category
                rows.append(None)
            rows.append(f)
        return rows

    def _feature_for_display_row(self, row_idx: int) -> Feature | None:
        if 0 <= row_idx < len(self.display_rows):
            return self.display_rows[row_idx]
        return None

    def compose(self):
        yield Header()
        with Horizontal():
            with Vertical(id="left-pane"):
                yield DataTable(id="feature-table")
            yield DetailPane(id="detail-pane")
        yield Static("", id="update-bar")
        yield Static("←/→ columns  │  ↑/↓ rows  │  Enter pick value  │  f filter  │  Shift+↑/↓ reorder  │  e edit  p plan  x research  │  c claude  i impl  │  s save  │  \\[/] resize", id="status-bar")
        yield Footer()

    def on_mount(self):
        self.set_interval(3.0, self._check_for_update)
        self.set_interval(2.0, self._check_fs_changes)
        self.set_interval(3.0, self._poll_agents)
        self.set_interval(1.0, self._poll_agent_view)
        table = self.query_one("#feature-table", DataTable)
        table.cursor_type = "cell"
        table.zebra_stripes = False
        table.add_column("#", key="fid", width=5)
        table.add_column("Feature", key="name", width=30)
        table.add_column("Cat.", key="category", width=7)
        table.add_column("Status", key="status", width=12)
        self._update_cat_header()
        self._refresh_table()
        if len(self.display_rows) > 1:
            table.move_cursor(row=1, column=0)
        self._update_detail()

    def _refresh_table(self, preserve_cursor: bool = False):
        table = self.query_one("#feature-table", DataTable)
        old_row = table.cursor_row if preserve_cursor else -1
        old_col = table.cursor_column if preserve_cursor else 0
        table.clear()
        self.display_rows = self._build_display_rows()

        for i, entry in enumerate(self.display_rows):
            if entry is None:
                cat = "—"
                for j in range(i + 1, len(self.display_rows)):
                    if self.display_rows[j] is not None:
                        cat = self.display_rows[j].category.upper()
                        break
                cc = CAT_COLORS.get(cat.lower(), "#6b7280")
                table.add_row("", f"[bold {cc}]── {cat} ──[/]", "", "", key=f"_sep_{i}")
            else:
                f = entry
                cc = CAT_COLORS.get(f.category, "white")
                sc = STATUS_COLORS.get(f.status, "white")
                dirty = " •" if f.dirty else ""
                marker = AGENT_ROW_MARKERS.get(self._agent_state(f.fid) or "", "")
                table.add_row(
                    f.fid, f"{f.name}{dirty}{marker}",
                    f"[{cc}]{f.category}[/]",
                    f"[{sc}]{f.status}[/]",
                    key=f.fid,
                )

        if preserve_cursor and 0 <= old_row < len(self.display_rows):
            table.move_cursor(row=old_row, column=old_col)

    def _first_feature_row(self) -> int:
        for i, entry in enumerate(self.display_rows):
            if entry is not None:
                return i
        return -1

    def _move_cursor_to(self, feature: Feature | None) -> bool:
        table = self.query_one("#feature-table", DataTable)
        for i, entry in enumerate(self.display_rows):
            if entry is not None and entry is feature:
                table.move_cursor(row=i, column=table.cursor_column)
                return True
        return False

    def _current_feature(self) -> Feature | None:
        table = self.query_one("#feature-table", DataTable)
        if table.row_count == 0:
            return None
        return self._feature_for_display_row(table.cursor_row)

    def _current_feature_index(self) -> int:
        f = self._current_feature()
        if f is None:
            return -1
        try:
            return self.features.index(f)
        except ValueError:
            return -1

    def _current_col_key(self) -> str:
        table = self.query_one("#feature-table", DataTable)
        col_idx = table.cursor_column
        if 0 <= col_idx < len(COL_KEYS):
            return COL_KEYS[col_idx]
        return ""

    def _update_detail(self):
        feature = self._current_feature()
        detail = self.query_one("#detail-pane", DetailPane)
        agent_state = self._agent_state(feature.fid) if feature else None
        capture = self._agent_last_capture.get(feature.fid, "") if feature else ""
        detail.update_content(feature, editing=self.editing, active_tab=self._active_tab,
                              agent_state=agent_state, agent_capture=capture)

    # ── Agent sessions (detached tmux, mirrored read-only) ─────────────

    def _session_prefix(self) -> str:
        project = re.sub(r"[^A-Za-z0-9_-]", "-", self.context_dir.parent.resolve().name or "backlog")
        return f"impl-{project}-"

    def _session_name(self, fid: str) -> str:
        return f"{self._session_prefix()}{fid}"

    def _agent_state(self, fid: str) -> str | None:
        if self._agent_attention.get(fid):
            return "attention"
        if fid in self._agent_alive:
            return "running"
        if fid in self._agent_done:
            return "done"
        return None

    def _poll_agents(self):
        """Track live agent sessions and their needs-input state (~3s)."""
        if not TMUX_BIN:
            return
        prefix = self._session_prefix()
        alive: set[str] = set()
        out = _tmux_out("list-sessions", "-F", "#{session_name}")
        for line in (out or "").splitlines():
            if line.startswith(prefix) and re.match(r"^F\d+$", line[len(prefix):]):
                alive.add(line[len(prefix):])

        ended = self._agent_alive - alive
        self._agent_done |= ended
        changed = bool(ended or (alive - self._agent_alive))
        self._agent_alive = alive

        attention: dict[str, bool] = {}
        for fid in alive:
            cap = _tmux_out("capture-pane", "-p", "-t", self._session_name(fid))
            if cap is not None:
                self._agent_last_capture[fid] = cap
            tail = "\n".join((cap or "").rstrip().splitlines()[-12:])
            attention[fid] = bool(NEEDS_INPUT_RE.search(tail))
        if attention != self._agent_attention:
            changed = True
        self._agent_attention = attention

        if changed:
            self._refresh_table(preserve_cursor=True)
            if not self.editing:
                self._update_detail()

    def _poll_agent_view(self):
        """Refresh the visible Agent tab with a color capture (~1s)."""
        if self._active_tab != "agent" or not TMUX_BIN:
            return
        feature = self._current_feature()
        if feature is None or feature.fid not in self._agent_alive:
            return
        cap = _tmux_out("capture-pane", "-p", "-e", "-t", self._session_name(feature.fid))
        if cap is None:
            return
        detail = self.query_one("#detail-pane", DetailPane)
        detail.show_agent_capture(cap)

    def _set_status(self, msg: str):
        self.query_one("#status-bar", Static).update(msg)

    def _check_for_update(self):
        try:
            current_mtime = self._script_path.stat().st_mtime
        except OSError:
            return
        if current_mtime != self._script_mtime and not self._update_available:
            self._update_available = True
            bar = self.query_one("#update-bar", Static)
            bar.update("  ↻  New version available — press Ctrl+R to restart  ")
            bar.add_class("visible")

    # ── Agent watch: auto-reload when files change on disk ─────────────

    def _scan_context_mtimes(self) -> dict[str, float]:
        try:
            return {
                f.name: f.stat().st_mtime
                for f in self.context_dir.iterdir()
                if f.suffix == ".md"
            }
        except OSError:
            return getattr(self, "_fs_snapshot", {})

    def _check_fs_changes(self):
        """Reload when an agent (or anything else) edits the context files.
        Never clobbers local unsaved work — hints to reload instead."""
        snap = self._scan_context_mtimes()
        if snap == self._fs_snapshot:
            return
        if len(self.screen_stack) > 1:
            return  # modal open — try again next tick
        self._fs_snapshot = snap
        if self.editing or self._unsaved_count() > 0:
            if not self._fs_pending:
                self._fs_pending = True
                bar = self.query_one("#update-bar", Static)
                bar.update("  ✎  Files changed on disk — press \\[r] to reload  ")
                bar.add_class("visible")
            return
        self._auto_reload()

    def _auto_reload(self):
        """Reload from disk, keeping cursor position and active tab."""
        feature = self._current_feature()
        keep_fid = feature.fid if feature else None
        keep_tab = self._active_tab
        table = self.query_one("#feature-table", DataTable)
        keep_col = table.cursor_column
        self._load_features()
        self._refresh_table()
        row = next((i for i, e in enumerate(self.display_rows)
                    if e is not None and e.fid == keep_fid), None)
        if row is None:
            row = 1 if len(self.display_rows) > 1 else 0
            self._active_tab = "description"
        else:
            self._active_tab = keep_tab
        table.move_cursor(row=row, column=keep_col)
        self._update_detail()
        self._set_status("↻ Reloaded — files changed on disk")

    # ── Editor change detection ─────────────────────────────────────────

    def on_text_area_changed(self, event: TextArea.Changed):
        """Show/hide the editor save bar when text is modified during editing."""
        if not self.editing:
            return
        detail = self.query_one("#detail-pane", DetailPane)
        current_text = event.text_area.text
        if current_text != self._edit_snapshot:
            detail.show_save_bar(True, state="modified")
        else:
            detail.show_save_bar(False)

    def on_button_pressed(self, event: Button.Pressed):
        """Handle the save button click in the editor save bar."""
        if event.button.id == "editor-save-btn":
            self.action_save()

    def on_tab_bar_tab_activated(self, event: TabBar.TabActivated):
        """Handle tab activation from the tab bar (Enter or click)."""
        self._switch_tab(event.tab_id)

    def on_detail_pane_edit_requested(self, event: DetailPane.EditRequested):
        """Handle double-click on markdown view → enter edit mode for active tab."""
        if not self.editing:
            self._switch_tab(self._active_tab)

    # ── Cell navigation: skip separators ───────────────────────────────

    def on_data_table_cell_highlighted(self, event: DataTable.CellHighlighted):
        """Skip separator rows when cell cursor moves."""
        table = self.query_one("#feature-table", DataTable)
        row_idx = table.cursor_row
        entry = self._feature_for_display_row(row_idx)

        if entry is None and len(self.display_rows) > 0:
            going_down = row_idx >= self._last_cursor_row
            offsets = [1, 2, -1, -2] if going_down else [-1, -2, 1, 2]
            for offset in offsets:
                candidate = row_idx + offset
                if 0 <= candidate < len(self.display_rows) and self.display_rows[candidate] is not None:
                    self._last_cursor_row = candidate
                    table.move_cursor(row=candidate, column=table.cursor_column)
                    return

        # A click elsewhere in the table leaves the header (table refreshes
        # re-highlight the same row, so only a real move counts)
        if self._header_focused and row_idx != self._last_cursor_row:
            self._set_header_focus(False)
        prev_row = self._last_cursor_row
        self._last_cursor_row = row_idx
        if not self.editing:
            if row_idx != prev_row:
                self._active_tab = "description"
            self._update_detail()

    # ── Key handler ────────────────────────────────────────────────────

    def on_key(self, event: Key):
        if self.editing:
            return

        # Cancel pending confirmations on any other key
        if self._reload_confirmed and event.key != "r":
            self._reload_confirmed = False
            self._set_status("Reload cancelled")
        if self._restart_confirmed and event.key != "ctrl+r":
            self._restart_confirmed = False
            self._set_status("Restart cancelled")
        if self._quit_confirmed and event.key != "q":
            self._quit_confirmed = False
            self._set_status("Quit cancelled")

        # Keys typed inside a modal bubble up here too — leave them alone
        if isinstance(self.screen, ModalScreen):
            return

        # Keyboard focus on the Cat. header: Enter/Space opens the filter,
        # ↓ returns to the list, any other key just drops the header focus.
        if self._header_focused:
            if event.key in ("enter", "space"):
                event.prevent_default()
                self.action_filter_categories()
                return
            self._set_header_focus(False)
            if event.key in ("down", "escape"):
                event.prevent_default()
                return
        # ↑ from the top row of the Cat. column steps onto its header
        if event.key == "up" and self._current_col_key() == "category":
            table = self.query_one("#feature-table", DataTable)
            first = self._first_feature_row()
            if first == -1 or table.cursor_row <= first:
                event.prevent_default()
                self._set_header_focus(True)
                return

        # Shift+arrow: reorder within category
        if event.key == "shift+up":
            event.prevent_default()
            self._move_feature(-1)
        elif event.key == "shift+down":
            event.prevent_default()
            self._move_feature(1)
        # Enter/Space on an editable cell: open picker (if not already open)
        elif event.key in ("enter", "space") and not self._picker_open:
            col = self._current_col_key()
            if col in EDITABLE_COLS:
                event.prevent_default()
                self._open_picker(col)

    # ── Value picker ───────────────────────────────────────────────────

    def _open_picker(self, col: str):
        feature = self._current_feature()
        if not feature:
            return

        self._picker_open = True

        if col == "category":
            options = CATEGORIES
            current = feature.category
            colors = CAT_COLORS
            title = "Category"
        else:
            options = STATUSES
            current = feature.status
            colors = STATUS_COLORS
            title = "Status"

        def on_pick(value: str | None):
            self._picker_open = False
            if value is None or not feature:
                return
            if col == "category":
                feature.set_category(value)
                self._sort_features()
                self._refresh_table()
                self._move_cursor_to(feature)
            else:
                feature.set_status(value)
                self._refresh_table(preserve_cursor=True)
            self._update_detail()
            hidden = " (hidden by the category filter)" if value in self._hidden_cats else ""
            self._set_status(f"{feature.fid} {col} → {value}{hidden}")

        self.push_screen(ValuePickerScreen(title, options, current, colors), on_pick)

    # ── Category filter ────────────────────────────────────────────────

    def _filter_categories(self) -> list[str]:
        """The standard categories, plus any non-standard ones the files use."""
        cats = list(CATEGORIES)
        for f in self.features:
            if f.category not in cats:
                cats.append(f.category)
        return cats

    def _update_cat_header(self):
        """Header shows ▾ (opens the filter), * while filtering, reverse while keyboard-focused."""
        table = self.query_one("#feature-table", DataTable)
        text = "Cat.*▾" if self._hidden_cats else "Cat. ▾"
        style = "reverse bold" if self._header_focused else ("bold #f59e0b" if self._hidden_cats else "")
        for idx, (key, column) in enumerate(table.columns.items()):
            if key.value == "category":
                column.label = Text(text, style=style)
                table.refresh_column(idx)
                break
        table.refresh()

    def _set_header_focus(self, focused: bool):
        self._header_focused = focused
        self._update_cat_header()
        if focused:
            self._set_status("Category header — Enter to filter categories, ↓ back to list")

    def on_data_table_header_selected(self, event: DataTable.HeaderSelected):
        if event.column_key.value == "category":
            event.stop()
            self.action_filter_categories()

    def action_filter_categories(self):
        if self._picker_open or self.editing:
            return
        self._picker_open = True
        cats = self._filter_categories()
        current = self._current_feature()

        def on_pick(visible: set[str] | None):
            self._picker_open = False
            self._set_header_focus(False)
            if visible is None:
                return
            if not visible:
                visible = set(cats)  # an empty filter would only show an empty list
                self._set_status("No category selected — showing all")
            self._hidden_cats = {c for c in cats if c not in visible}
            self._update_cat_header()
            self._refresh_table()
            if not self._move_cursor_to(current):
                first = self._first_feature_row()
                if first != -1:
                    table = self.query_one("#feature-table", DataTable)
                    table.move_cursor(row=first, column=table.cursor_column)
            self._update_detail()
            if self._hidden_cats:
                shown = ", ".join(c for c in cats if c in visible)
                self._set_status(f"Showing categories: {shown}")
            elif visible == set(cats):
                self._set_status("Showing all categories")

        visible_now = {c for c in cats if c not in self._hidden_cats}
        self.push_screen(CategoryFilterScreen(cats, visible_now), on_pick)

    # ── Reorder ────────────────────────────────────────────────────────

    def _move_feature(self, direction: int):
        feat_idx = self._current_feature_index()
        if feat_idx < 0:
            return
        feature = self.features[feat_idx]
        target_idx = feat_idx + direction
        if target_idx < 0 or target_idx >= len(self.features):
            return
        neighbor = self.features[target_idx]
        if neighbor.category != feature.category:
            self._set_status(f"Already at {'top' if direction < 0 else 'bottom'} of {feature.category}")
            return

        self.features[feat_idx], self.features[target_idx] = self.features[target_idx], self.features[feat_idx]
        # Renumber positions so a later _sort_features() keeps this order —
        # without this, any re-sort (e.g. a category change) reverts the move.
        for i, f in enumerate(self.features):
            f._backlog_pos = i
        self._order_dirty = True

        table = self.query_one("#feature-table", DataTable)
        col = table.cursor_column
        self._refresh_table()
        for i, entry in enumerate(self.display_rows):
            if entry is feature:
                table.move_cursor(row=i, column=col)
                break
        self._update_detail()
        arrow = "↑" if direction < 0 else "↓"
        self._set_status(f"Moved {feature.fid} {arrow} within {feature.category}")

    # ── Tab switching ─────────────────────────────────────────────────

    def _switch_tab(self, target: str):
        """Switch to a tab, checking for an open Claude pane and unsaved edits."""
        feature = self._current_feature()
        if not feature:
            return
        if target == self._active_tab and self.editing:
            return  # already editing this tab

        # If a live Claude pane exists for the prior tab, confirm closing it first.
        if (target != self._active_tab
                and self._claude_pane_id
                and self._tmux_pane_alive(self._claude_pane_id)):
            def on_claude_confirm(confirmed: bool | None):
                if not confirmed:
                    return
                self._close_claude_pane()
                self._continue_switch_tab(target, respawn_claude=True)
            self.push_screen(ConfirmCloseClaudeScreen(), on_claude_confirm)
            return

        self._continue_switch_tab(target, respawn_claude=False)

    def _continue_switch_tab(self, target: str, respawn_claude: bool):
        """Tab switch after Claude-pane confirmation; handles unsaved-edit prompt."""
        if self.editing:
            body_widget = self.query_one("#detail-body", TextArea)
            if body_widget.text != self._edit_snapshot:
                def on_confirm(result: str):
                    if result == "save":
                        self._commit_editor_text()
                        self._do_save_all()
                        self._do_switch_tab(target)
                        if respawn_claude:
                            self._open_claude_pane(self._current_feature())
                    elif result == "discard":
                        self._do_switch_tab(target)
                        if respawn_claude:
                            self._open_claude_pane(self._current_feature())
                    # "cancel" — do nothing
                self.push_screen(ConfirmSwitchScreen(), on_confirm)
                return

        self._do_switch_tab(target)
        if respawn_claude:
            self._open_claude_pane(self._current_feature())

    def _do_switch_tab(self, target: str):
        """Actually perform the tab switch and enter edit mode."""
        feature = self._current_feature()
        if not feature:
            return

        # The Agent tab is a live view, not an editor.
        if target == "agent":
            if self._agent_state(feature.fid) is None:
                self._set_status(f"No agent session for {feature.fid} — press \\[i] to start one")
                return
            self._active_tab = "agent"
            self.editing = False
            self._update_detail()
            self._set_status(f"Agent view for {feature.fid} — \\[o] open interactive  \\[Esc] back")
            return

        # Create plan/research file if it doesn't exist yet
        if target == "plan" and not feature.has_plan:
            feature.plan_file = feature.plan_filename_for()
            feature.plan_body = "## Plan\n_(To be filled in)_"
            feature._plan_dirty = True
        elif target == "research" and not feature.has_research:
            feature.research_file = feature.research_filename_for()
            feature.research_body = "## Research\n_(To be filled in)_"
            feature._research_dirty = True

        self._active_tab = target
        self.editing = True

        # Set snapshot for change detection
        if target == "plan":
            self._edit_snapshot = feature.plan_body
        elif target == "research":
            self._edit_snapshot = feature.research_body
        else:
            self._edit_snapshot = feature.body

        self._update_detail()
        self._set_status(f"Editing {feature.fid} {target} — \\[Escape] to finish")

    def _commit_editor_text(self):
        """Save current TextArea content into the feature model (in memory)."""
        feature = self._current_feature()
        if not feature:
            return
        body_widget = self.query_one("#detail-body", TextArea)
        if self._active_tab == "plan":
            feature.set_plan_body(body_widget.text)
        elif self._active_tab == "research":
            feature.set_research_body(body_widget.text)
        else:
            feature.set_body(body_widget.text)

    def _unsaved_count(self) -> int:
        """Count unsaved work: dirty specs, plan/research docs, and pending reorders.
        This is what quit/reload/restart warnings must use — checking only
        f.dirty misses doc edits and manual reordering."""
        n = sum(
            1 for f in self.features
            if f.dirty or (f._plan_dirty and f.plan_file) or (f._research_dirty and f.research_file)
        )
        return n + (1 if self._order_dirty else 0)

    def _do_save_all(self) -> tuple[int, int]:
        """Write all dirty features and docs to disk. Returns (saved, docs_saved)."""
        saved = 0
        docs_saved = 0
        for f in self.features:
            if f.dirty:
                save_feature_file(self.context_dir, f)
                saved += 1
            if f._plan_dirty and f.plan_file:
                save_associated_file(self.context_dir, f, "plan")
                docs_saved += 1
            if f._research_dirty and f.research_file:
                save_associated_file(self.context_dir, f, "research")
                docs_saved += 1
        save_backlog_index(self.context_dir, self.features)
        self._order_dirty = False
        # Our own writes must not look like external changes to the agent watch.
        self._fs_snapshot = self._scan_context_mtimes()
        return saved, docs_saved

    # ── Claude pane launcher ──────────────────────────────────────────

    def _format_prompt(self, key: str, feature: Feature, ctx: str | None = None) -> str:
        return CLAUDE_PROMPTS[key].format(
            fid=feature.fid,
            name=feature.name,
            ctx=ctx or self.context_dir.name,
            spec_filename=feature.filename,
            plan_filename=feature.plan_file or feature.plan_filename_for(),
            research_filename=feature.research_file or feature.research_filename_for(),
        )

    def _build_claude_prompt(self, feature: Feature) -> str:
        plan_filename = feature.plan_file or feature.plan_filename_for()
        research_filename = feature.research_file or feature.research_filename_for()
        # Whether the on-disk file actually exists. has_plan / has_research can be
        # true purely from the user opening the tab (in-memory placeholder).
        plan_exists = (self.context_dir / plan_filename).exists()
        research_exists = (self.context_dir / research_filename).exists()

        if self._active_tab == "plan":
            key = "plan_existing" if plan_exists else "plan_new"
        elif self._active_tab == "research":
            key = "research_existing" if research_exists else "research_new"
        else:
            key = "description"

        return self._format_prompt(key, feature)

    def _tmux_pane_alive(self, pane_id: str) -> bool:
        try:
            out = subprocess.check_output(
                ["tmux", "list-panes", "-a", "-F", "#{pane_id}"],
                text=True,
                stderr=subprocess.DEVNULL,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False
        return pane_id in out.split()

    def _open_claude_pane(self, feature: Feature | None) -> None:
        if feature is None:
            return
        prompt = self._build_claude_prompt(feature)
        cwd = str(self.context_dir.parent)

        if os.environ.get("TMUX"):
            # Single shell-command string with proper quoting; `exec` so the pane
            # closes when claude exits instead of leaving an idle shell behind.
            shell_cmd = f"exec {shlex.quote(CLAUDE_BIN)} {shlex.quote(prompt)}"
            try:
                out = subprocess.check_output(
                    [
                        "tmux", "split-window", "-h",
                        "-c", cwd,
                        "-P", "-F", "#{pane_id}",
                        shell_cmd,
                    ],
                    text=True,
                    stderr=subprocess.PIPE,
                ).strip()
                self._claude_pane_id = out or None
                self._set_status(f"Claude pane opened ({self._active_tab}) — pane {out}")
            except subprocess.CalledProcessError as e:
                msg = (e.stderr or "").strip() or str(e)
                self._set_status(f"tmux split failed: {msg}")
            except FileNotFoundError:
                self._set_status("tmux not found on PATH")
        else:
            # No tmux — hand the terminal to Claude full-screen.
            self._claude_pane_id = None
            try:
                with self.suspend():
                    subprocess.run([CLAUDE_BIN, prompt], cwd=cwd)
            except FileNotFoundError:
                self._set_status(f"claude not found on PATH (tried {CLAUDE_BIN})")
                return
            self._set_status("Claude exited — back to backlog")

    def _close_claude_pane(self) -> None:
        if not self._claude_pane_id:
            return
        try:
            subprocess.run(
                ["tmux", "kill-pane", "-t", self._claude_pane_id],
                check=False,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            pass
        self._claude_pane_id = None

    def action_toggle_claude(self) -> None:
        if self.editing:
            return
        feature = self._current_feature()
        if feature is None:
            self._set_status("No feature selected — move cursor to a feature row.")
            return
        if self._claude_pane_id and self._tmux_pane_alive(self._claude_pane_id):
            self._close_claude_pane()
            self._set_status("Claude pane closed.")
        else:
            # Stale id (user exited Claude themselves) — clear it before re-opening.
            self._claude_pane_id = None
            self._open_claude_pane(feature)

    # ── Initiate implementation ───────────────────────────────────────

    def action_implement(self) -> None:
        """Launch an agent session that implements the selected feature."""
        if self.editing:
            return
        feature = self._current_feature()
        if feature is None:
            self._set_status("No feature selected — move cursor to a feature row.")
            return

        # Already running? Jump to its Agent tab instead of double-launching.
        if TMUX_BIN and _tmux_out("has-session", "-t", self._session_name(feature.fid)) is not None:
            self._agent_alive.add(feature.fid)
            self._active_tab = "agent"
            self._update_detail()
            self._set_status(f"Agent already running for {feature.fid} — showing its session")
            return

        plan_filename = feature.plan_file or feature.plan_filename_for()
        plan_exists = (self.context_dir / plan_filename).exists()
        key = "implement" if plan_exists else "implement_no_plan"

        # Rule: implementations run in an isolated git worktree so parallel
        # agents never share a working directory. Backlog files stay in the
        # main checkout (context/ is typically gitignored and absent from
        # worktrees) — the brief points there absolutely, which also keeps
        # the agent watch seeing status/checkbox updates live.
        worktree = self._prepare_worktree(feature)
        if worktree:
            cwd, branch = worktree
            prompt = self._format_prompt(key, feature, ctx=str(self.context_dir.resolve()))
            prompt += (
                f" You are working in an isolated git worktree at {cwd} on branch "
                f"{branch}: implement and commit there; do not merge. The backlog "
                f"files referenced above live in the main checkout — update the "
                f"plan checkboxes and status there."
            )
        else:
            cwd = str(self.context_dir.parent)
            prompt = self._format_prompt(key, feature)

        # Flush everything to disk first — the agent reads files, not our memory —
        # and mark the feature in-progress so backlog.md reflects reality.
        feature.set_status("in-progress")
        self._do_save_all()

        if TMUX_BIN:
            self._launch_agent_session(feature, prompt, cwd)
        else:
            self._launch_claude_window(feature, prompt, cwd)
        self._refresh_table(preserve_cursor=True)
        self._update_detail()

    def _prepare_worktree(self, feature: Feature) -> tuple[str, str] | None:
        """Create (or reuse) .worktrees/<FID-slug> on branch impl/<FID-slug>.
        Returns (path, branch), or None to run in the project root (not a git
        repo, or git failed). The .worktrees/ dir is excluded via
        .git/info/exclude so it never shows up as untracked noise."""
        root = self.context_dir.parent.resolve()
        def git(*args: str) -> subprocess.CompletedProcess:
            return subprocess.run(["git", "-C", str(root), *args],
                                  capture_output=True, text=True)
        if git("rev-parse", "--is-inside-work-tree").returncode != 0:
            return None

        slug = feature.filename.removesuffix(".md")
        wt_path = root / ".worktrees" / slug
        branch = f"impl/{slug}"
        if wt_path.is_dir():
            return str(wt_path), branch  # relaunch: reuse the existing worktree

        common = git("rev-parse", "--git-common-dir").stdout.strip()
        exclude = (root / common if not os.path.isabs(common) else Path(common)) / "info" / "exclude"
        try:
            existing = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
            if ".worktrees/" not in existing:
                exclude.parent.mkdir(parents=True, exist_ok=True)
                exclude.write_text(existing.rstrip("\n") + "\n.worktrees/\n", encoding="utf-8")
        except OSError:
            pass  # cosmetic only

        git("worktree", "prune")
        res = git("worktree", "add", str(wt_path), "-b", branch)
        if res.returncode != 0 and "already exists" in res.stderr:
            res = git("worktree", "add", str(wt_path), branch)  # branch left from earlier run
        if res.returncode != 0:
            self._set_status(f"worktree failed ({res.stderr.strip().splitlines()[-1] if res.stderr else '?'}) — running in project root")
            return None
        return str(wt_path), branch

    def _launch_agent_session(self, feature: Feature, prompt: str, cwd: str) -> None:
        """Start the agent in a detached tmux session and show its Agent tab.
        The session outlives the TUI — rediscovered on restart by _poll_agents."""
        name = self._session_name(feature.fid)
        shell_cmd = f"exec {shlex.quote(CLAUDE_BIN)} {shlex.quote(prompt)}"
        try:
            subprocess.check_output(
                [TMUX_BIN, "new-session", "-d", "-s", name, "-c", cwd, shell_cmd],
                text=True,
                stderr=subprocess.PIPE,
            )
        except subprocess.CalledProcessError as e:
            msg = (e.stderr or "").strip() or str(e)
            self._set_status(f"tmux new-session failed: {msg}")
            return
        except FileNotFoundError:
            self._set_status("tmux not found on PATH")
            return
        self._agent_done.discard(feature.fid)
        self._agent_last_capture.pop(feature.fid, None)
        self._agent_alive.add(feature.fid)
        self._active_tab = "agent"
        self._set_status(f"⚙ Implementing {feature.fid} — live view here, \\[o] opens interactive")

    def action_open_agent_attach(self) -> None:
        """From the Agent tab, open the session interactively (to answer
        permission prompts etc.). Read-only view stays available."""
        if self.editing or self._active_tab != "agent":
            return
        feature = self._current_feature()
        if feature is None:
            return
        name = self._session_name(feature.fid)
        if feature.fid not in self._agent_alive:
            self._set_status("Session has ended — nothing to attach to.")
            return
        if os.environ.get("TMUX"):
            subprocess.run([TMUX_BIN, "switch-client", "-t", name], check=False,
                           stderr=subprocess.DEVNULL)
        elif sys.platform == "darwin":
            self._open_macos_terminal_script(
                f"attach-{feature.fid}",
                f"exec {shlex.quote(TMUX_BIN)} attach -t {shlex.quote(name)}",
                str(self.context_dir.parent),
                f"Opened interactive window for {feature.fid} — detach (Ctrl+B D) to return",
            )
        else:
            self._set_status(f"Attach manually: tmux attach -t {name}")

    def _launch_claude_window(self, feature: Feature, prompt: str, cwd: str | None = None) -> None:
        """Run claude in a new tmux window (implementation is long-running, so a
        split would crowd out the backlog). Outside tmux, open a new terminal
        window on macOS — never take over the tab the backlog is running in."""
        cwd = cwd or str(self.context_dir.parent)
        if os.environ.get("TMUX"):
            shell_cmd = f"exec {shlex.quote(CLAUDE_BIN)} {shlex.quote(prompt)}"
            window_name = f"impl-{feature.fid}"
            try:
                subprocess.check_output(
                    ["tmux", "new-window", "-c", cwd, "-n", window_name, shell_cmd],
                    text=True,
                    stderr=subprocess.PIPE,
                )
                self._set_status(
                    f"⚙ Implementing {feature.fid} in tmux window “{window_name}” — status → in-progress"
                )
            except subprocess.CalledProcessError as e:
                msg = (e.stderr or "").strip() or str(e)
                self._set_status(f"tmux new-window failed: {msg}")
            except FileNotFoundError:
                self._set_status("tmux not found on PATH")
        elif sys.platform == "darwin":
            self._launch_macos_terminal_window(feature, prompt, cwd)
        else:
            try:
                with self.suspend():
                    subprocess.run([CLAUDE_BIN, prompt], cwd=cwd)
            except FileNotFoundError:
                self._set_status(f"claude not found on PATH (tried {CLAUDE_BIN})")
                return
            self._set_status(f"Claude exited — {feature.fid} implementation session ended")

    def _launch_macos_terminal_window(self, feature: Feature, prompt: str, cwd: str) -> None:
        """Open the agent session in a fresh terminal window, leaving the
        backlog's own tab untouched."""
        self._open_macos_terminal_script(
            f"impl-{feature.fid}",
            f"exec {shlex.quote(CLAUDE_BIN)} {shlex.quote(prompt)}",
            cwd,
            f"⚙ Implementing {feature.fid} in a new terminal window — status → in-progress",
        )

    def _open_macos_terminal_script(self, tag: str, shell_line: str, cwd: str, status_msg: str) -> None:
        """Run a shell line in a new macOS terminal window via a self-deleting
        .command script."""
        import tempfile
        script = (
            "#!/bin/zsh\n"
            'rm -f -- "$0"\n'
            f"cd {shlex.quote(cwd)} || exit 1\n"
            f"{shell_line}\n"
        )
        fd, path = tempfile.mkstemp(prefix=f"backlog-{tag}-", suffix=".command")
        with os.fdopen(fd, "w") as fh:
            fh.write(script)
        os.chmod(path, 0o755)
        try:
            subprocess.run(["open", path], check=True, capture_output=True, text=True)
            self._set_status(status_msg)
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            os.unlink(path)
            msg = getattr(e, "stderr", "") or str(e)
            self._set_status(f"Could not open a terminal window: {msg.strip()}")

    # ── Actions ────────────────────────────────────────────────────────

    def action_edit(self):
        self._switch_tab("description")

    def action_edit_plan(self):
        self._switch_tab("plan")

    def action_edit_research(self):
        self._switch_tab("research")

    def action_stop_edit(self):
        if not self.editing:
            if self._active_tab == "agent":
                self._active_tab = "description"
                self._update_detail()
            return
        self._commit_editor_text()
        self.editing = False
        self._edit_snapshot = ""
        self.query_one("#detail-pane", DetailPane).show_save_bar(False)
        self.query_one("#feature-table", DataTable).focus()
        self._refresh_table(preserve_cursor=True)
        self._update_detail()
        self._set_status("Edit saved in memory — press \\[s] to write to disk")

    def action_save(self):
        if self.editing:
            self._commit_editor_text()
            # Update snapshot so save bar knows text matches saved state
            body_widget = self.query_one("#detail-body", TextArea)
            self._edit_snapshot = body_widget.text
        saved, docs_saved = self._do_save_all()
        detail = self.query_one("#detail-pane", DetailPane)
        if self.editing:
            detail.show_save_bar(True, state="saved")
        else:
            detail.show_save_bar(False)
        self._refresh_table(preserve_cursor=True)
        if not self.editing:
            self._update_detail()
        extra = f" + {docs_saved} doc(s)" if docs_saved else ""
        self._set_status(f"Saved {saved} feature(s){extra} + backlog.md \u2713")

    def action_reload(self):
        unsaved = self._unsaved_count()
        if unsaved and not self._reload_confirmed:
            self._reload_confirmed = True
            self._set_status(f"⚠ {unsaved} unsaved change(s) will be lost — press \\[r] again to confirm, any other key to cancel")
            return
        self._do_reload(discard_count=unsaved)

    def _do_reload(self, discard_count: int = 0):
        self._reload_confirmed = False
        self._order_dirty = False
        self._fs_pending = False
        self._fs_snapshot = self._scan_context_mtimes()
        if not self._update_available:
            self.query_one("#update-bar", Static).remove_class("visible")
        if self.editing:
            self.editing = False
        self._active_tab = "description"
        self._load_features()
        self._refresh_table()
        table = self.query_one("#feature-table", DataTable)
        if len(self.display_rows) > 1:
            table.move_cursor(row=1, column=0)
        table.focus()
        self._update_detail()
        if discard_count:
            self._set_status(f"Reloaded — {discard_count} unsaved change(s) discarded")
        else:
            self._set_status("Reloaded from disk ✓")

    def action_new_feature(self):
        if self.editing:
            return

        def on_result(name: str | None):
            if not name:
                return
            max_num = 0
            for f in self.features:
                m = re.match(r"F(\d+)", f.fid)
                if m:
                    max_num = max(max_num, int(m.group(1)))
            new_num = max_num + 1
            fid = f"F{new_num:02d}"
            slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
            filename = f"{fid}-{slug}.md"

            new_feature = Feature(
                fid=fid, name=name, category="next", status="idea",
                filename=filename, body="## Description\n_(To be filled in)_",
            )
            new_feature.dirty = True
            if new_feature.category in self._hidden_cats:
                # Don't let a brand-new feature vanish behind the filter
                self._hidden_cats.discard(new_feature.category)
                self._update_cat_header()
            self.features.append(new_feature)
            self._sort_features()
            self._refresh_table()
            table = self.query_one("#feature-table", DataTable)
            for i, entry in enumerate(self.display_rows):
                if entry is new_feature:
                    table.move_cursor(row=i, column=0)
                    break
            self._update_detail()
            self._set_status(f"Created {fid}: {name} — press \\[s] to save")

        self.push_screen(NewFeatureScreen(), on_result)

    def action_delete_feature(self):
        if self.editing:
            return
        feature = self._current_feature()
        if not feature:
            return

        def on_confirm(confirmed: bool):
            if not confirmed:
                self._set_status("Delete cancelled")
                return
            filepath = self.context_dir / feature.filename
            self.features.remove(feature)
            if filepath.exists():
                filepath.unlink()
            # Also remove plan/research files
            if feature.plan_file:
                plan_path = self.context_dir / feature.plan_file
                if plan_path.exists():
                    plan_path.unlink()
            if feature.research_file:
                research_path = self.context_dir / feature.research_file
                if research_path.exists():
                    research_path.unlink()
            self._refresh_table()
            table = self.query_one("#feature-table", DataTable)
            if table.row_count > 1:
                table.move_cursor(row=min(table.cursor_row, len(self.display_rows) - 1), column=0)
            self._update_detail()
            save_backlog_index(self.context_dir, self.features)
            self._set_status(f"Deleted {feature.fid}: {feature.name}")

        self.push_screen(ConfirmDeleteScreen(feature.fid, feature.name), on_confirm)

    def action_restart(self):
        unsaved = self._unsaved_count()
        if unsaved and not self._restart_confirmed:
            self._restart_confirmed = True
            self._set_status(f"⚠ {unsaved} unsaved change(s) will be lost — press \\[Ctrl+R] again to confirm, any other key to cancel")
            return
        self._do_restart()

    def _do_restart(self):
        self.exit()
        os.execv(sys.executable, [sys.executable] + sys.argv)

    def action_quit_app(self):
        unsaved = self._unsaved_count()
        if unsaved and not self._quit_confirmed:
            self._quit_confirmed = True
            self._set_status(f"⚠ {unsaved} unsaved change(s) — press \\[s] to save or \\[q] again to quit")
            return
        self.exit()

    def _apply_pane_ratio(self):
        left, right = self.PANE_RATIOS[self._ratio_idx]
        pane = self.query_one("#left-pane", Vertical)
        pane.styles.width = f"{left}%"
        self._set_status(f"Pane ratio {left}:{right}  —  \\[[]  \\[]] to adjust")

    def action_pane_ratio_left(self):
        if self.editing:
            return
        if self._ratio_idx > 0:
            self._ratio_idx -= 1
            self._apply_pane_ratio()

    def action_pane_ratio_right(self):
        if self.editing:
            return
        if self._ratio_idx < len(self.PANE_RATIOS) - 1:
            self._ratio_idx += 1
            self._apply_pane_ratio()


if __name__ == "__main__":
    from .cli import main
    main()
