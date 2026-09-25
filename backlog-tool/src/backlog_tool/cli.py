"""
Non-interactive commands — the agent-facing half of backlog-tool.

The TUI is for humans; these commands are for agents and scripts. They print one
padded line per feature and nothing else, so answering "what is F68's status" costs
a few tokens instead of a full read of backlog.md. Textual is imported lazily, and
only on the TUI path.

Both front ends write through model.py, so a status set here and a status set with
[s] in the TUI produce byte-identical files.
"""

import argparse
import json
import sys
from pathlib import Path

from .model import (
    NO_THEME,
    STATUSES,
    TIMINGS,
    Feature,
    do_init,
    get_version,
    load_features,
    migrate,
    next_fid,
    save_backlog_index,
    save_feature_file,
    slugify,
    sort_features,
    theme_counts,
    themes_in_use,
)

# Hidden by default: a shipped or parked feature is rarely what a question is about,
# and on a 170-row backlog they are a third of the table.
DEFAULT_HIDDEN = {"shipped", "parked"}


# ── helpers ────────────────────────────────────────────────────────────

def _die(msg: str, code: int = 1):
    print(f"backlog: {msg}", file=sys.stderr)
    sys.exit(code)


def _context_dir(arg: str | None) -> Path:
    d = Path(arg) if arg else Path("context")
    if not d.is_dir():
        _die(f"directory not found: {d}\nHint: run 'backlog --init {d}' to create it")
    return d


def _csv(val: str | None) -> set[str] | None:
    if not val:
        return None
    return {v.strip().lower() for v in val.split(",") if v.strip()}


def _validate(values: set[str] | None, valid: list[str], what: str):
    if not values:
        return
    bad = sorted(values - set(valid))
    if bad:
        _die(f"unknown {what}: {', '.join(bad)}\nvalid: {', '.join(valid)}")


def _find(features: list[Feature], fid: str) -> Feature:
    want = fid.upper()
    for f in features:
        if f.fid.upper() == want:
            return f
    _die(f"no such feature: {fid}")


def _row(f: Feature, w: int, theme_w: int = 0) -> str:
    theme = f"{(f.theme or '-')[:theme_w]:<{theme_w}} " if theme_w else ""
    return f"{f.fid:<5} {theme}{f.timing:<6} {f.status:<15} {f.name[:w]}"


def _theme_width(features: list[Feature]) -> int:
    """Only spend a column on themes when some feature actually has one."""
    widest = max((len(f.theme) for f in features if f.theme), default=0)
    return min(max(widest, 5), 18) if widest else 0


def _as_dict(f: Feature) -> dict:
    return {
        "fid": f.fid, "name": f.name, "theme": f.theme, "timing": f.timing,
        "status": f.status, "file": f.filename,
        "plan": f.plan_file, "research": f.research_file,
    }


def _theme_matches(f: Feature, wanted: set[str] | None) -> bool:
    if not wanted:
        return True
    if f.theme:
        return f.theme.lower() in wanted
    return "none" in wanted or NO_THEME in wanted


# ── commands ───────────────────────────────────────────────────────────

def cmd_list(args) -> int:
    context_dir = _context_dir(args.dir)
    timings, stats, themes = _csv(args.timing), _csv(args.status), _csv(args.theme)
    _validate(timings, TIMINGS, "timing")
    _validate(stats, STATUSES, "status")
    features = load_features(context_dir, with_bodies=False)
    out = []
    for f in features:
        if timings and f.timing not in timings:
            continue
        if stats and f.status not in stats:
            continue
        if not _theme_matches(f, themes):
            continue
        if not args.all and not stats and f.status in DEFAULT_HIDDEN:
            continue
        out.append(f)
    if args.json:
        print(json.dumps([_as_dict(f) for f in out], indent=None))
        return 0
    tw = _theme_width(out)
    for f in out:
        print(_row(f, args.width, tw))
    if not out:
        print("(no matching features)")
    return 0


def cmd_show(args) -> int:
    context_dir = _context_dir(args.dir)
    features = load_features(context_dir, with_bodies=False)
    f = _find(features, args.fid)
    if args.json:
        print(json.dumps(_as_dict(f), indent=None))
        return 0
    print(f"# {f.fid}: {f.name}")
    theme = f"   theme: {f.theme}" if f.theme else ""
    print(f"status: {f.status}   timing: {f.timing}{theme}   file: {f.filename}")
    extras = [n for n in (f.plan_file, f.research_file) if n]
    if extras:
        print(f"also: {', '.join(extras)}")
    if not args.head:
        print()
        print(f.body.strip())
    # Plan and research stay opt-in: they are the files that grow to 15k tokens.
    for flag, name in ((args.plan, f.plan_file), (args.research, f.research_file)):
        if not flag:
            continue
        if not name:
            print(f"\n(no such file for {f.fid})")
            continue
        print(f"\n--- {name} ---")
        print((context_dir / name).read_text(encoding="utf-8").strip())
    return 0


def cmd_set(args) -> int:
    context_dir = _context_dir(args.dir)
    if not args.status and not args.timing and args.theme is None:
        _die("nothing to set — pass --status, --timing and/or --theme")
    _validate(_csv(args.status), STATUSES, "status")
    _validate(_csv(args.timing), TIMINGS, "timing")
    features = load_features(context_dir, with_bodies=True)
    f = _find(features, args.fid)
    before = (f.status, f.timing, f.theme)
    if args.status:
        f.set_status(args.status.strip().lower())
    if args.timing:
        f.set_timing(args.timing.strip().lower())
    if args.theme is not None:
        # --theme "" and --theme none both clear it.
        val = args.theme.strip()
        f.set_theme("" if val.lower() in ("", "none", NO_THEME) else val)
    if (f.status, f.timing, f.theme) == before:
        print(f"{f.fid} unchanged ({f.timing}, {f.status}{', ' + f.theme if f.theme else ''})")
        return 0
    # Both files, always — the drift between them is the bug this command exists to kill.
    # Re-sort first so the table this writes is byte-identical to what the TUI
    # would write for the same state.
    sort_features(features)
    save_feature_file(context_dir, f)
    save_backlog_index(context_dir, features)
    was_theme = f" [{before[2]}]" if before[2] else ""
    now_theme = f" [{f.theme}]" if f.theme else ""
    print(f"{f.fid} {before[1]}/{before[0]}{was_theme} -> {f.timing}/{f.status}{now_theme}")
    return 0


def cmd_add(args) -> int:
    context_dir = _context_dir(args.dir)
    _validate(_csv(args.status), STATUSES, "status")
    _validate(_csv(args.timing), TIMINGS, "timing")
    features = load_features(context_dir, with_bodies=True)
    fid = next_fid(features)
    filename = f"{fid}-{slugify(args.name)}.md"
    body = args.body.strip() if args.body else "_No description yet._"
    theme = (args.theme or "").strip()
    if theme.lower() in ("none", NO_THEME):
        theme = ""
    feature = Feature(fid, args.name.strip(), args.timing, args.status, filename,
                      f"## Description\n{body}\n", theme=theme)
    feature._backlog_pos = max((x._backlog_pos for x in features), default=-1) + 1
    features.append(feature)
    sort_features(features)
    save_feature_file(context_dir, feature)
    save_backlog_index(context_dir, features)
    tag = f" [{feature.theme}]" if feature.theme else ""
    print(f"{fid} {feature.timing}/{feature.status}{tag} {context_dir / filename}")
    return 0


def cmd_next_id(args) -> int:
    context_dir = _context_dir(args.dir)
    print(next_fid(load_features(context_dir, with_bodies=False)))
    return 0


def cmd_themes(args) -> int:
    context_dir = _context_dir(args.dir)
    features = load_features(context_dir, with_bodies=False)
    counts = theme_counts(features)
    unthemed = sum(1 for f in features if not f.theme)
    if args.json:
        print(json.dumps({"themes": [{"theme": t, "count": c} for t, c in counts],
                          "unthemed": unthemed}, indent=None))
        return 0
    for t, c in counts:
        print(f"{c:>4}  {t}")
    print(f"{unthemed:>4}  {NO_THEME}")
    return 0


def cmd_migrate(args) -> int:
    context_dir = _context_dir(args.dir)
    changed = migrate(context_dir, dry_run=args.dry_run)
    for line in changed:
        print(line)
    verb = "would change" if args.dry_run else "changed"
    print(f"\n{verb} {len(changed)} file(s)" if changed else "already on the current format")
    return 0


def cmd_check(args) -> int:
    """Report drift between the table and the feature files. Never fixes it."""
    from .model import read_backlog_rows
    context_dir = _context_dir(args.dir)
    features = load_features(context_dir, with_bodies=False)
    table = read_backlog_rows(context_dir)
    problems = []
    by_fid = {f.fid.upper(): f for f in features}
    for fid in table:
        if fid not in by_fid:
            problems.append(f"{fid}: row in backlog.md has no feature file")
    for f in features:
        if f.fid.upper() not in table:
            problems.append(f"{f.fid}: {f.filename} has no row in backlog.md")
    # A feature file's own header drifting from the table it is indexed by.
    for f in features:
        header = _header_values(context_dir / f.filename)
        if header is None:
            continue
        h_status, h_timing, h_theme = header
        if h_status and h_status != f.status:
            problems.append(f"{f.fid}: status is '{f.status}' in backlog.md but '{h_status}' in {f.filename}")
        if h_timing and h_timing != f.timing:
            problems.append(f"{f.fid}: timing is '{f.timing}' in backlog.md but '{h_timing}' in {f.filename}")
        if h_theme.lower() != f.theme.lower():
            a = f.theme or "(none)"
            b = h_theme or "(none)"
            problems.append(f"{f.fid}: theme is '{a}' in backlog.md but '{b}' in {f.filename}")
    dup = {fid for fid in table if table.count(fid) > 1}
    for fid in sorted(dup):
        problems.append(f"{fid}: appears {table.count(fid)} times in backlog.md")
    for p in problems:
        print(p)
    print(f"\n{len(features)} feature files, {len(table)} table rows, {len(problems)} problem(s)")
    return 1 if problems else 0


def _header_values(path: Path) -> tuple[str, str, str] | None:
    """The **Status:** / **Timing:** / **Theme:** lines as written in a feature file.

    **Category:** is still read: that is the pre-1.8.0 spelling, and reporting it as
    drift would flood `check` on any backlog that has not run `migrate`.
    """
    if not path.exists():
        return None
    status = timing = theme = ""
    for raw in path.read_text(encoding="utf-8").split("\n")[:20]:
        s = raw.strip()
        low = s.lower()
        if low.startswith("**status:**"):
            status = s[len("**status:**"):].strip().lower()
        elif low.startswith("**timing:**"):
            timing = s[len("**timing:**"):].strip().lower()
        elif low.startswith("**category:**"):
            timing = s[len("**category:**"):].strip().lower()
        elif low.startswith("**theme:**"):
            theme = s[len("**theme:**"):].strip()
    return status, timing, theme


# ── entry point ────────────────────────────────────────────────────────

HELP = """Backlog Tool — markdown feature backlogs in the terminal

Human (interactive):
  backlog [context-dir]              Run the TUI (default: ./context)
  backlog --init [dir]               Scaffold a new backlog in dir

Agent / script (non-interactive, compact output):
  backlog list [-t now,next] [-s ready] [--theme NAME] [--all] [--json]
  backlog show FXX [--head] [--plan] [--research] [--json]
  backlog set FXX [--status S] [--timing T] [--theme NAME]
  backlog add "Name" [--timing T] [--status S] [--theme NAME] [--body TEXT]
  backlog next-id
  backlog themes [--json]            Themes in use, with counts
  backlog check                      Report table vs feature-file drift
  backlog migrate [--dry-run]        Move a pre-1.9.0 backlog to Timing + Theme

  Every command takes --dir to point at a backlog other than ./context.
  list hides shipped and parked unless --all or an explicit --status.
  --theme none lists the features that have no theme.
  -c/--category still works everywhere -t/--timing does.

  backlog --version                  Print the installed version
  backlog --help                     Show this help

Timings:  %s
Statuses: %s
Themes:   free-form, created as you use them (see `backlog themes`)
""" % (", ".join(TIMINGS), ", ".join(STATUSES))

SUBCOMMANDS = {"list", "show", "set", "add", "next-id", "check", "themes", "migrate"}


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="backlog", add_help=False)
    sub = ap.add_subparsers(dest="cmd")

    def common(p):
        p.add_argument("--dir", "-d", help="backlog directory (default: ./context)")
        return p

    p = common(sub.add_parser("list", add_help=False))
    # --category/-c is the pre-1.8.0 name for the same option.
    p.add_argument("--timing", "-t", "--category", "-c", dest="timing")
    p.add_argument("--theme")
    p.add_argument("--status", "-s")
    p.add_argument("--all", action="store_true")
    p.add_argument("--json", action="store_true")
    p.add_argument("--width", type=int, default=70)
    p.set_defaults(func=cmd_list)

    p = common(sub.add_parser("show", add_help=False))
    p.add_argument("fid")
    p.add_argument("--head", action="store_true", help="header only, no description")
    p.add_argument("--plan", action="store_true")
    p.add_argument("--research", action="store_true")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_show)

    p = common(sub.add_parser("set", add_help=False))
    p.add_argument("fid")
    p.add_argument("--status", "-s")
    p.add_argument("--timing", "-t", "--category", "-c", dest="timing")
    p.add_argument("--theme", default=None, help='name, or "" / none to clear')
    p.set_defaults(func=cmd_set)

    p = common(sub.add_parser("add", add_help=False))
    p.add_argument("name")
    p.add_argument("--timing", "-t", "--category", "-c", dest="timing", default="later")
    p.add_argument("--status", "-s", default="idea")
    p.add_argument("--theme")
    p.add_argument("--body", "-b")
    p.set_defaults(func=cmd_add)

    p = common(sub.add_parser("next-id", add_help=False))
    p.set_defaults(func=cmd_next_id)

    p = common(sub.add_parser("check", add_help=False))
    p.set_defaults(func=cmd_check)

    p = common(sub.add_parser("themes", add_help=False))
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_themes)

    p = common(sub.add_parser("migrate", add_help=False))
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_migrate)
    return ap


def main():
    argv = sys.argv[1:]

    if "--version" in argv or "-V" in argv:
        print(get_version())
        return

    if "--init" in argv:
        rest = [a for a in argv if a != "--init"]
        do_init(Path(rest[0]) if rest else Path("context"))
        return

    if argv and argv[0] in SUBCOMMANDS:
        if "--help" in argv or "-h" in argv:
            print(HELP)
            return
        args = _parser().parse_args(argv)
        sys.exit(args.func(args))

    if "--help" in argv or "-h" in argv:
        print(HELP)
        return

    # No subcommand: the TUI. Textual is imported here and nowhere else, so the
    # commands above stay fast and work on a box without a terminal UI.
    context_dir = _context_dir(argv[0] if argv else None)
    from .tui import BacklogApp
    BacklogApp(context_dir).run()
