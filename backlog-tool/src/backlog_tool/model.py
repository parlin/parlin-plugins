"""
Backlog data layer — shared by the TUI and the non-interactive CLI.

Nothing here imports Textual: `backlog list` must not pay for a UI toolkit.
Both front ends go through these parsers and writers, so the file format cannot
drift between what a human saves in the TUI and what an agent writes from the CLI.
"""

import re
from pathlib import Path

# ── Constants ──────────────────────────────────────────────────────────

TIMINGS = ["now", "next", "later", "maybe"]
STATUSES = ["idea", "research-needed", "researching", "research-done", "ready", "in-progress", "to-review", "shipped", "parked"]

TIMING_ORDER = {t: i for i, t in enumerate(TIMINGS)}

# "Timing" was called "Category" up to 1.7.0. These aliases exist because this
# package is published and something outside this repo may still import them.
CATEGORIES = TIMINGS
CAT_ORDER = TIMING_ORDER

# ── Feature model ──────────────────────────────────────────────────────

class Feature:
    def __init__(self, fid: str, name: str, timing: str, status: str, filename: str,
                 body: str, theme: str = ""):
        self.fid = fid
        self.name = name
        self.timing = timing.strip().lower()
        self.status = status.strip().lower()
        # A theme groups related features, the way an epic does. Empty means none.
        self.theme = theme.strip()
        self.filename = filename
        self.body = body
        self.dirty = False
        self._backlog_pos: int = 0  # order from backlog.md; renumbered on manual reorder
        # Associated doc filenames (set by _detect_associated_files)
        self.plan_file: str | None = None
        self.research_file: str | None = None
        self.plan_body: str = ""
        self.research_body: str = ""
        self._plan_dirty: bool = False
        self._research_dirty: bool = False

    @property
    def category(self) -> str:
        """Pre-1.8.0 name for `timing`, kept for outside callers."""
        return self.timing

    @category.setter
    def category(self, val: str):
        self.timing = val

    def set_timing(self, val: str):
        if val != self.timing:
            self.timing = val
            self.dirty = True

    def set_category(self, val: str):
        """Pre-1.8.0 name for `set_timing`."""
        self.set_timing(val)

    def set_theme(self, val: str):
        val = (val or "").strip()
        if val != self.theme:
            self.theme = val
            self.dirty = True

    def set_status(self, val: str):
        if val != self.status:
            self.status = val
            self.dirty = True

    def set_body(self, val: str):
        if val != self.body:
            self.body = val
            self.dirty = True

    def set_plan_body(self, val: str):
        if val != self.plan_body:
            self.plan_body = val
            self._plan_dirty = True

    def set_research_body(self, val: str):
        if val != self.research_body:
            self.research_body = val
            self._research_dirty = True

    @property
    def has_plan(self) -> bool:
        return self.plan_file is not None

    @property
    def has_research(self) -> bool:
        return self.research_file is not None

    def plan_filename_for(self) -> str:
        """Derive plan filename from the feature filename."""
        base = self.filename.removesuffix(".md")
        return f"{base}-plan.md"

    def research_filename_for(self) -> str:
        """Derive research filename from the feature filename."""
        base = self.filename.removesuffix(".md")
        return f"{base}-research.md"


def parse_feature_file(filepath: Path) -> Feature:
    text = filepath.read_text(encoding="utf-8")
    lines = text.split("\n")
    fid = filepath.stem.split("-")[0]
    name, timing, status, theme = "", "later", "idea", ""
    body_start = 0

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("# "):
            m = re.match(r"#\s+\w+:\s*(.*)", stripped)
            name = m.group(1).strip() if m else stripped.lstrip("# ").strip()
        elif stripped.lower().startswith("**status:**"):
            m = re.search(r"\*\*Status:\*\*\s*(\S+)", stripped, re.IGNORECASE)
            if m: status = m.group(1).strip().lower()
        elif stripped.lower().startswith(("**timing:**", "**category:**")):
            # **Category:** is the pre-1.8.0 spelling and is still read.
            m = re.search(r"\*\*(?:Timing|Category):\*\*\s*(\S+)", stripped, re.IGNORECASE)
            if m: timing = m.group(1).strip().lower()
        elif stripped.lower().startswith("**theme:**"):
            m = re.search(r"\*\*Theme:\*\*\s*(.+)", stripped, re.IGNORECASE)
            if m: theme = m.group(1).strip()
        elif stripped.startswith("## "):
            body_start = i
            break

    if body_start == 0:
        for i, line in enumerate(lines):
            if i > 3 and line.strip() == "":
                body_start = i
                break

    body = "\n".join(lines[body_start:]).strip()
    return Feature(fid=fid.upper(), name=name, timing=timing, status=status,
                   filename=filepath.name, body=body, theme=theme)


def save_feature_file(context_dir: Path, feature: Feature):
    filepath = context_dir / feature.filename
    # The Theme line is omitted entirely when unset, so an unthemed file looks
    # exactly as it did before themes existed.
    theme_line = f"**Theme:** {feature.theme}\n" if feature.theme else ""
    content = (f"# {feature.fid}: {feature.name}\n\n"
               f"**Status:** {feature.status}\n**Timing:** {feature.timing}\n{theme_line}"
               f"\n{feature.body}\n")
    filepath.write_text(content, encoding="utf-8")
    feature.dirty = False


def save_associated_file(context_dir: Path, feature: Feature, kind: str):
    """Save a plan or research file for a feature."""
    if kind == "plan":
        filename = feature.plan_file or feature.plan_filename_for()
        body = feature.plan_body
        feature.plan_file = filename
        feature._plan_dirty = False
    else:
        filename = feature.research_file or feature.research_filename_for()
        body = feature.research_body
        feature.research_file = filename
        feature._research_dirty = False
    filepath = context_dir / filename
    label = "Plan" if kind == "plan" else "Research"
    content = f"# {feature.fid}: {feature.name} — {label}\n\n{body}\n"
    filepath.write_text(content, encoding="utf-8")


def load_associated_body(context_dir: Path, filename: str) -> str:
    """Read the body of a plan/research file (everything after the title line)."""
    filepath = context_dir / filename
    if not filepath.exists():
        return ""
    text = filepath.read_text(encoding="utf-8")
    lines = text.split("\n")
    # Skip the title line and any blank lines after it
    start = 0
    for i, line in enumerate(lines):
        if line.strip().startswith("# "):
            start = i + 1
            break
    # Skip leading blank lines after title
    while start < len(lines) and lines[start].strip() == "":
        start += 1
    return "\n".join(lines[start:]).strip()


def save_backlog_index(context_dir: Path, features: list[Feature]):
    backlog = context_dir / "backlog.md"
    # Preserve the user's custom H1 title if one is already in the file.
    title = "# Feature Backlog"
    existing_decision_log = None
    if backlog.exists():
        old_text = backlog.read_text(encoding="utf-8")
        for line in old_text.split("\n"):
            stripped = line.strip()
            if stripped.startswith("# "):
                title = stripped
                break
        m = re.search(r"(---\s*\n## Decision Log.*)", old_text, re.DOTALL)
        if m:
            existing_decision_log = m.group(1)

    lines = [
        title, "",
        "> Lean index of all features. Each row links to a detailed feature file.",
        "> Open the feature file to see full scope, design notes, dependencies, and open questions.",
        "", "## Timing Key",
        "- **now** — Shipped or actively being worked on",
        "- **next** — Up next, research done or low-hanging fruit",
        "- **later** — Planned but not yet prioritized",
        "- **maybe** — Ideas worth capturing, not committed",
        "", "## Status Key",
        "- **idea** — Captured, not yet researched",
        "- **research-needed** — Needs investigation before scoping",
        "- **researching** — Investigating feasibility",
        "- **research-done** — Research complete, ready to scope",
        "- **ready** — Scoped and ready to build",
        "- **in-progress** — Under active development",
        "- **to-review** — Implementation done, awaiting review",
        "- **shipped** — Live",
        "- **parked** — Deprioritized or blocked",
        "", "---", "",
        "| # | Feature | Theme | Timing | Status | File |",
        "|---|---|---|---|---|---|",
    ]
    for f in features:
        lines.append(f"| {f.fid} | {f.name} | {f.theme} | {f.timing} | {f.status} | `{f.filename}` |")
    lines.append("")
    if existing_decision_log:
        # rstrip: the capture takes the file's trailing newlines with it, so
        # appending it verbatim grew backlog.md by a byte on every single save.
        lines.append(existing_decision_log.rstrip())
    # Exactly one trailing newline, so a no-op save is a no-op in git too.
    backlog.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")


# ── Loading a whole backlog ────────────────────────────────────────────

FEATURE_PAT = re.compile(r"^F\d{2,3}-.*\.md$", re.IGNORECASE)
ASSOCIATED_PAT = re.compile(r"-(plan|research)\.md$", re.IGNORECASE)


def detect_associated_files(context_dir: Path, features: list[Feature], with_bodies: bool = True):
    """Link FXX-slug-plan.md / -research.md to their feature.

    with_bodies=False records only the filenames — the CLI needs to know a plan
    exists without paying to read it.
    """
    for feature in features:
        plan_name = feature.plan_filename_for()
        research_name = feature.research_filename_for()
        if (context_dir / plan_name).exists():
            feature.plan_file = plan_name
            if with_bodies:
                feature.plan_body = load_associated_body(context_dir, plan_name)
        if (context_dir / research_name).exists():
            feature.research_file = research_name
            if with_bodies:
                feature.research_body = load_associated_body(context_dir, research_name)


ROW_FID_PAT = re.compile(r"^F\d{2,3}$", re.IGNORECASE)


def parse_table_row(line: str) -> dict | None:
    """One row of the backlog.md table, or None if the line is not one.

    Two layouts are in the wild:

        | FID | Name | Timing | Status | File |            <- up to 1.7.0
        | FID | Name | Theme | Timing | Status | File |    <- 1.8.0 on

    Parsed **from the right**, because the rightmost fields are the ones with closed
    vocabularies: File is last, Status before it, Timing before that. A name
    containing an unescaped pipe therefore cannot shift timing or status, which is
    what `apply_backlog_order` relies on. Such a row can still mis-attribute a name
    fragment as a theme, and its name; the feature file owns the name regardless.
    """
    line = line.strip()
    if not line.startswith("|"):
        return None
    parts = [c.strip() for c in line.strip("|").split("|")]
    if len(parts) < 5 or not ROW_FID_PAT.match(parts[0]):
        return None

    timing, status = parts[-3].lower(), parts[-2].lower()
    if timing in TIMING_ORDER and status in STATUSES:
        has_theme = len(parts) >= 6
        theme = parts[-4] if has_theme else ""
        name = " | ".join(parts[1:-4] if has_theme else parts[1:-3])
    else:
        # Values outside the vocabularies (a hand-typed status, say). Fall back to
        # fixed positions, choosing the layout by width.
        if len(parts) >= 6:
            theme, timing, status = parts[2], parts[3].lower(), parts[4].lower()
        else:
            theme, timing, status = "", parts[2].lower(), parts[3].lower()
        name = parts[1]
    return {"fid": parts[0].upper(), "name": name,
            "theme": theme, "timing": timing, "status": status}


def apply_backlog_order(context_dir: Path, features: list[Feature]):
    """Read backlog.md table — the source of truth for order, status, timing and theme."""
    backlog_path = context_dir / "backlog.md"
    if not backlog_path.exists():
        return
    backlog_data: dict[str, dict] = {}
    idx = 0
    for line in backlog_path.read_text(encoding="utf-8").split("\n"):
        row = parse_table_row(line)
        if row is None:
            continue
        row["order"] = idx
        backlog_data[row["fid"]] = row
        idx += 1
    # Apply to features — backlog.md wins for status, timing, theme and order
    max_order = idx
    for feature in features:
        data = backlog_data.get(feature.fid)
        if data:
            feature.timing = data["timing"]
            feature.status = data["status"]
            # An older table has no theme column; keep what the feature file said
            # rather than blanking it.
            if data["theme"]:
                feature.theme = data["theme"]
            feature._backlog_pos = data["order"]
        else:
            feature._backlog_pos = max_order
            max_order += 1


def sort_features(features: list[Feature]):
    features.sort(key=lambda f: (TIMING_ORDER.get(f.timing, 99), f._backlog_pos))


def read_backlog_rows(context_dir: Path) -> list[str]:
    """FIDs present in the backlog.md table, in table order."""
    backlog_path = context_dir / "backlog.md"
    if not backlog_path.exists():
        return []
    fids = []
    for line in backlog_path.read_text(encoding="utf-8").split("\n"):
        row = parse_table_row(line)
        if row is not None:
            fids.append(row["fid"])
    return fids


def load_features(context_dir: Path, with_bodies: bool = True,
                  warn=None) -> list[Feature]:
    """Every feature in a backlog, ordered the way the table orders them.

    The single loader for both front ends. `warn` takes a message string for
    unparseable files; the default drops them silently.
    """
    features: list[Feature] = []
    for f in sorted(context_dir.iterdir()):
        if FEATURE_PAT.match(f.name) and not ASSOCIATED_PAT.search(f.name):
            try:
                features.append(parse_feature_file(f))
            except Exception as e:
                if warn:
                    warn(f"Warning: could not parse {f.name}: {e}")
    detect_associated_files(context_dir, features, with_bodies=with_bodies)
    apply_backlog_order(context_dir, features)
    sort_features(features)
    return features


def next_fid(features: list[Feature]) -> str:
    """Lowest unused FXX, zero-padded to the width the backlog already uses."""
    used = {int(f.fid[1:]) for f in features if f.fid[1:].isdigit()}
    n = 1
    while n in used:
        n += 1
    width = 3 if any(v >= 100 for v in used) or n >= 100 else 2
    return f"F{n:0{width}d}"


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s[:60].rstrip("-") or "feature"


# ── Themes ─────────────────────────────────────────────────────────────

# A theme is not declared anywhere: it exists because a feature uses it. That
# keeps one source of truth, at the cost of leaving typo-prevention to the picker.
NO_THEME = "(none)"


def themes_in_use(features: list[Feature]) -> list[str]:
    """Distinct themes, case-insensitively deduplicated, in alphabetical order."""
    seen: dict[str, str] = {}
    for f in features:
        if f.theme:
            seen.setdefault(f.theme.lower(), f.theme)
    return [seen[k] for k in sorted(seen)]


def theme_counts(features: list[Feature]) -> list[tuple[str, int]]:
    """(theme, count) by descending count, then name. Unthemed features are excluded."""
    counts: dict[str, int] = {}
    labels: dict[str, str] = {}
    for f in features:
        if not f.theme:
            continue
        k = f.theme.lower()
        counts[k] = counts.get(k, 0) + 1
        labels.setdefault(k, f.theme)
    return [(labels[k], counts[k]) for k in sorted(counts, key=lambda k: (-counts[k], k))]


# ── Migration to the 1.8.0 spelling ────────────────────────────────────

def migrate(context_dir: Path, dry_run: bool = False) -> list[str]:
    """Rewrite `**Category:**` as `**Timing:**` and the table with its Theme column.

    Idempotent: a backlog already on the new spelling reports nothing. Returns one
    line per file that needs changing (or was changed).
    """
    changed: list[str] = []
    cat_line = re.compile(r"^\*\*Category:\*\*(\s*)", re.IGNORECASE | re.MULTILINE)
    for path in sorted(context_dir.iterdir()):
        if not FEATURE_PAT.match(path.name) or ASSOCIATED_PAT.search(path.name):
            continue
        text = path.read_text(encoding="utf-8")
        if not cat_line.search(text):
            continue
        changed.append(f"{path.name}: **Category:** -> **Timing:**")
        if not dry_run:
            path.write_text(cat_line.sub(r"**Timing:**\1", text), encoding="utf-8")

    backlog = context_dir / "backlog.md"
    if backlog.exists():
        text = backlog.read_text(encoding="utf-8")
        needs_table = "| # | Feature | Theme | Timing | Status | File |" not in text
        if needs_table:
            changed.append("backlog.md: table gains a Theme column, Category header -> Timing")
            if not dry_run:
                # Load after the feature files were rewritten, so themes read correctly.
                save_backlog_index(context_dir, load_features(context_dir, with_bodies=False))
    return changed


# ── Init scaffolding ──────────────────────────────────────────────────

BACKLOG_TEMPLATE = """\
# Feature Backlog

> Lean index of all features. Each row links to a detailed feature file.
> Open the feature file to see full scope, design notes, dependencies, and open questions.

## Timing Key
- **now** — Shipped or actively being worked on
- **next** — Up next, research done or low-hanging fruit
- **later** — Planned but not yet prioritized
- **maybe** — Ideas worth capturing, not committed

## Status Key
- **idea** — Captured, not yet researched
- **research-needed** — Needs investigation before scoping
- **researching** — Investigating feasibility
- **research-done** — Research complete, ready to scope
- **ready** — Scoped and ready to build
- **in-progress** — Under active development
- **to-review** — Implementation done, awaiting review
- **shipped** — Live
- **parked** — Deprioritized or blocked

---

| # | Feature | Theme | Timing | Status | File |
|---|---|---|---|---|---|
| F01 | Example Feature |  | next | idea | `F01-example-feature.md` |

---

## Decision Log
| Date | Decision | Rationale |
|---|---|---|

---

## How to Use This Backlog
1. **Starting work on a feature?** Update status to `in-progress` in the backlog table.
2. **Feature shipped?** Update status to `shipped`, note version/date in the feature file.
3. **New idea?** Press `n` in the tool, or create a new `FXX-name.md` file and add a row here.
4. **Reprioritizing?** Change the timing column (now/next/later/maybe).
5. **Grouping related work?** Put a theme in the theme column — it works like an epic.
"""

SAMPLE_FEATURE = """\
# F01: Example Feature

**Status:** idea
**Timing:** next

## Description
Describe what this feature does and why it matters.

## Notes
- Delete this sample and create your own features with `n` in the backlog tool.
"""


def do_init(context_dir: Path):
    """Scaffold a new backlog in the given directory."""
    if context_dir.exists() and any(context_dir.iterdir()):
        # Check if it already has feature files
        has_features = any(f.name.startswith("F") and f.name.endswith(".md") for f in context_dir.iterdir())
        if has_features:
            print(f"✓ {context_dir}/ already contains feature files. Nothing to do.")
            return
    context_dir.mkdir(parents=True, exist_ok=True)
    backlog_path = context_dir / "backlog.md"
    if not backlog_path.exists():
        backlog_path.write_text(BACKLOG_TEMPLATE, encoding="utf-8")
        print(f"  Created {backlog_path}")
    sample_path = context_dir / "F01-example-feature.md"
    if not sample_path.exists():
        sample_path.write_text(SAMPLE_FEATURE, encoding="utf-8")
        print(f"  Created {sample_path}")
    print(f"\n✓ Backlog initialized in {context_dir}/")
    print(f"  Run: backlog {context_dir}")


def get_version() -> str:
    """Installed version. The backlog skill compares this against the plugin
    manifest to decide whether the PATH binary is stale — keep it printable
    as a bare version string on stdout."""
    try:
        from importlib.metadata import version
        return version("backlog-tool")
    except Exception:
        return "unknown"
