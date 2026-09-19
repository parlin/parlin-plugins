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
    CATEGORIES,
    STATUSES,
    Feature,
    do_init,
    get_version,
    load_features,
    next_fid,
    save_backlog_index,
    save_feature_file,
    slugify,
    sort_features,
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


def _row(f: Feature, w: int) -> str:
    return f"{f.fid:<5} {f.category:<6} {f.status:<15} {f.name[:w]}"


def _as_dict(f: Feature) -> dict:
    return {
        "fid": f.fid, "name": f.name, "category": f.category, "status": f.status,
        "file": f.filename, "plan": f.plan_file, "research": f.research_file,
    }


# ── commands ───────────────────────────────────────────────────────────

def cmd_list(args) -> int:
    context_dir = _context_dir(args.dir)
    cats, stats = _csv(args.category), _csv(args.status)
    _validate(cats, CATEGORIES, "category")
    _validate(stats, STATUSES, "status")
    features = load_features(context_dir, with_bodies=False)
    out = []
    for f in features:
        if cats and f.category not in cats:
            continue
        if stats and f.status not in stats:
            continue
        if not args.all and not stats and f.status in DEFAULT_HIDDEN:
            continue
        out.append(f)
    if args.json:
        print(json.dumps([_as_dict(f) for f in out], indent=None))
        return 0
    for f in out:
        print(_row(f, args.width))
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
    print(f"status: {f.status}   category: {f.category}   file: {f.filename}")
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
    if not args.status and not args.category:
        _die("nothing to set — pass --status and/or --category")
    _validate(_csv(args.status), STATUSES, "status")
    _validate(_csv(args.category), CATEGORIES, "category")
    features = load_features(context_dir, with_bodies=True)
    f = _find(features, args.fid)
    before = (f.status, f.category)
    if args.status:
        f.set_status(args.status.strip().lower())
    if args.category:
        f.set_category(args.category.strip().lower())
    if (f.status, f.category) == before:
        print(f"{f.fid} unchanged ({f.status}, {f.category})")
        return 0
    # Both files, always — the drift between them is the bug this command exists to kill.
    # Re-sort first so the table this writes is byte-identical to what the TUI
    # would write for the same state.
    sort_features(features)
    save_feature_file(context_dir, f)
    save_backlog_index(context_dir, features)
    print(f"{f.fid} {before[1]}/{before[0]} -> {f.category}/{f.status}")
    return 0


def cmd_add(args) -> int:
    context_dir = _context_dir(args.dir)
    _validate(_csv(args.status), STATUSES, "status")
    _validate(_csv(args.category), CATEGORIES, "category")
    features = load_features(context_dir, with_bodies=True)
    fid = next_fid(features)
    filename = f"{fid}-{slugify(args.name)}.md"
    body = args.body.strip() if args.body else "_No description yet._"
    feature = Feature(fid, args.name.strip(), args.category, args.status, filename,
                      f"## Description\n{body}\n")
    feature._backlog_pos = max((x._backlog_pos for x in features), default=-1) + 1
    features.append(feature)
    sort_features(features)
    save_feature_file(context_dir, feature)
    save_backlog_index(context_dir, features)
    print(f"{fid} {feature.category}/{feature.status} {context_dir / filename}")
    return 0


def cmd_next_id(args) -> int:
    context_dir = _context_dir(args.dir)
    print(next_fid(load_features(context_dir, with_bodies=False)))
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
        h_status, h_cat = header
        if h_status and h_status != f.status:
            problems.append(f"{f.fid}: status is '{f.status}' in backlog.md but '{h_status}' in {f.filename}")
        if h_cat and h_cat != f.category:
            problems.append(f"{f.fid}: category is '{f.category}' in backlog.md but '{h_cat}' in {f.filename}")
    dup = {fid for fid in table if table.count(fid) > 1}
    for fid in sorted(dup):
        problems.append(f"{fid}: appears {table.count(fid)} times in backlog.md")
    for p in problems:
        print(p)
    print(f"\n{len(features)} feature files, {len(table)} table rows, {len(problems)} problem(s)")
    return 1 if problems else 0


def _header_values(path: Path) -> tuple[str, str] | None:
    """The **Status:** / **Category:** lines as written in a feature file."""
    if not path.exists():
        return None
    status = category = ""
    for line in path.read_text(encoding="utf-8").split("\n")[:20]:
        s = line.strip().lower()
        if s.startswith("**status:**"):
            status = s.split("**status:**", 1)[1].strip()
        elif s.startswith("**category:**"):
            category = s.split("**category:**", 1)[1].strip()
    return status, category


# ── entry point ────────────────────────────────────────────────────────

HELP = """Backlog Tool — markdown feature backlogs in the terminal

Human (interactive):
  backlog [context-dir]              Run the TUI (default: ./context)
  backlog --init [dir]               Scaffold a new backlog in dir

Agent / script (non-interactive, compact output):
  backlog list [-c now,next] [-s ready] [--all] [--json]
  backlog show FXX [--head] [--plan] [--research] [--json]
  backlog set FXX [--status S] [--category C]
  backlog add "Name" [--category C] [--status S] [--body TEXT]
  backlog next-id
  backlog check                      Report table vs feature-file drift

  Every command takes --dir to point at a backlog other than ./context.
  list hides shipped and parked unless --all or an explicit --status.

  backlog --version                  Print the installed version
  backlog --help                     Show this help

Categories: %s
Statuses:   %s
""" % (", ".join(CATEGORIES), ", ".join(STATUSES))

SUBCOMMANDS = {"list", "show", "set", "add", "next-id", "check"}


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="backlog", add_help=False)
    sub = ap.add_subparsers(dest="cmd")

    def common(p):
        p.add_argument("--dir", "-d", help="backlog directory (default: ./context)")
        return p

    p = common(sub.add_parser("list", add_help=False))
    p.add_argument("--category", "-c")
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
    p.add_argument("--category", "-c")
    p.set_defaults(func=cmd_set)

    p = common(sub.add_parser("add", add_help=False))
    p.add_argument("name")
    p.add_argument("--category", "-c", default="later")
    p.add_argument("--status", "-s", default="idea")
    p.add_argument("--body", "-b")
    p.set_defaults(func=cmd_add)

    p = common(sub.add_parser("next-id", add_help=False))
    p.set_defaults(func=cmd_next_id)

    p = common(sub.add_parser("check", add_help=False))
    p.set_defaults(func=cmd_check)
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
