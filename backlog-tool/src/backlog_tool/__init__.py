"""
backlog-tool — markdown feature backlogs in the terminal.

Importing this package must stay cheap. The Textual TUI lives in tui.py and is
imported only when something actually opens it, so `backlog list` and the other
agent-facing commands do not pay for a UI toolkit they never draw.
"""

from .model import (  # noqa: F401  (re-exported: the data layer is the API)
    BACKLOG_TEMPLATE,
    CATEGORIES,
    CAT_ORDER,
    SAMPLE_FEATURE,
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
    read_backlog_rows,
    save_associated_file,
    save_backlog_index,
    save_feature_file,
    slugify,
    sort_features,
)

_TUI_NAMES = {"BacklogApp", "DetailPane", "TabBar", "ValuePickerScreen",
              "NewFeatureScreen", "ConfirmSwitchScreen", "ConfirmDeleteScreen",
              "ConfirmCloseClaudeScreen"}


def __getattr__(name):
    """Reach the TUI through the package only if asked — keeps Textual lazy."""
    if name in _TUI_NAMES:
        from . import tui
        return getattr(tui, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def main():
    """Entry point kept for older installs pointing at backlog_tool:main."""
    from .cli import main as cli_main
    cli_main()
