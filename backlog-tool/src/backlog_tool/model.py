"""
Backlog data layer — shared by the TUI and the non-interactive CLI.

Nothing here imports Textual: `backlog list` must not pay for a UI toolkit.
Both front ends go through these parsers and writers, so the file format cannot
drift between what a human saves in the TUI and what an agent writes from the CLI.
"""

import re
from pathlib import Path

# ── Constants ──────────────────────────────────────────────────────────

CATEGORIES = ["now", "next", "later", "maybe"]
STATUSES = ["idea", "research-needed", "researching", "research-done", "ready", "in-progress", "to-review", "shipped", "parked"]

CAT_ORDER = {cat: i for i, cat in enumerate(CATEGORIES)}

# ── Feature model ──────────────────────────────────────────────────────

class Feature:
    def __init__(self, fid: str, name: str, category: str, status: str, filename: str, body: str):
        self.fid = fid
        self.name = name
        self.category = category.strip().lower()
        self.status = status.strip().lower()
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

    def set_category(self, val: str):
        if val != self.category:
            self.category = val
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
    name, category, status = "", "later", "idea"
    body_start = 0

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("# "):
            m = re.match(r"#\s+\w+:\s*(.*)", stripped)
            name = m.group(1).strip() if m else stripped.lstrip("# ").strip()
        elif stripped.lower().startswith("**status:**"):
            m = re.search(r"\*\*Status:\*\*\s*(\S+)", stripped, re.IGNORECASE)
            if m: status = m.group(1).strip().lower()
        elif stripped.lower().startswith("**category:**"):
            m = re.search(r"\*\*Category:\*\*\s*(\S+)", stripped, re.IGNORECASE)
            if m: category = m.group(1).strip().lower()
        elif stripped.startswith("## "):
            body_start = i
            break

    if body_start == 0:
        for i, line in enumerate(lines):
            if i > 3 and line.strip() == "":
                body_start = i
                break

    body = "\n".join(lines[body_start:]).strip()
    return Feature(fid=fid.upper(), name=name, category=category, status=status,
                   filename=filepath.name, body=body)


def save_feature_file(context_dir: Path, feature: Feature):
    filepath = context_dir / feature.filename
    content = f"# {feature.fid}: {feature.name}\n\n**Status:** {feature.status}\n**Category:** {feature.category}\n\n{feature.body}\n"
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
        "", "## Category Key",
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
        "| # | Feature | Category | Status | File |",
        "|---|---|---|---|---|",
    ]
    for f in features:
        lines.append(f"| {f.fid} | {f.name} | {f.category} | {f.status} | `{f.filename}` |")
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


def apply_backlog_order(context_dir: Path, features: list[Feature]):
    """Read backlog.md table — the single source of truth for order, status, and category."""
    backlog_path = context_dir / "backlog.md"
    if not backlog_path.exists():
        return
    text = backlog_path.read_text(encoding="utf-8")
    # Parse table rows: | FID | Name | Category | Status | File |
    backlog_data: dict[str, dict] = {}
    idx = 0
    for line in text.split("\n"):
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.split("|")]
        # cells: ['', FID, Name, Category, Status, File, '']
        if len(cells) >= 6 and re.match(r"^F\d{2,3}$", cells[1], re.IGNORECASE):
            fid = cells[1].upper()
            backlog_data[fid] = {
                "order": idx,
                "category": cells[3].strip().lower(),
                "status": cells[4].strip().lower(),
            }
            idx += 1
    # Apply to features — backlog.md wins for status, category, and order
    max_order = idx
    for feature in features:
        data = backlog_data.get(feature.fid)
        if data:
            feature.category = data["category"]
            feature.status = data["status"]
            feature._backlog_pos = data["order"]
        else:
            feature._backlog_pos = max_order
            max_order += 1


def sort_features(features: list[Feature]):
    features.sort(key=lambda f: (CAT_ORDER.get(f.category, 99), f._backlog_pos))


def read_backlog_rows(context_dir: Path) -> list[str]:
    """FIDs present in the backlog.md table, in table order."""
    backlog_path = context_dir / "backlog.md"
    if not backlog_path.exists():
        return []
    fids = []
    for line in backlog_path.read_text(encoding="utf-8").split("\n"):
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.split("|")]
        if len(cells) >= 6 and re.match(r"^F\d{2,3}$", cells[1], re.IGNORECASE):
            fids.append(cells[1].upper())
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


# ── Init scaffolding ──────────────────────────────────────────────────

BACKLOG_TEMPLATE = """\
# Feature Backlog

> Lean index of all features. Each row links to a detailed feature file.
> Open the feature file to see full scope, design notes, dependencies, and open questions.

## Category Key
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

| # | Feature | Category | Status | File |
|---|---|---|---|---|
| F01 | Example Feature | next | idea | `F01-example-feature.md` |

---

## Decision Log
| Date | Decision | Rationale |
|---|---|---|

---

## How to Use This Backlog
1. **Starting work on a feature?** Update status to `in-progress` in the backlog table.
2. **Feature shipped?** Update status to `shipped`, note version/date in the feature file.
3. **New idea?** Press `n` in the tool, or create a new `FXX-name.md` file and add a row here.
4. **Reprioritizing?** Change the category column (now/next/later/maybe).
"""

SAMPLE_FEATURE = """\
# F01: Example Feature

**Status:** idea
**Category:** next

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
