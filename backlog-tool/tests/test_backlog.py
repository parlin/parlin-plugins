"""
Tests for the backlog data layer and the non-interactive CLI.

Stdlib unittest on purpose: the plugin's only runtime dependency is Textual, and
these tests must run without it — the point of the model/cli/tui split is that a
query never touches a UI toolkit, and test 'ImportLaziness' is what holds that.

Run from backlog-tool/:   python3 -m unittest discover -s tests -t .
"""

import io
import json
import subprocess
import sys
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from tempfile import TemporaryDirectory

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from backlog_tool import cli, model  # noqa: E402


# ── helpers ────────────────────────────────────────────────────────────

def run(*argv) -> tuple[int, str, str]:
    """Call the CLI in-process. Returns (exit_code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    code = 0
    old = sys.argv
    sys.argv = ["backlog", *argv]
    try:
        with redirect_stdout(out), redirect_stderr(err):
            cli.main()
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else 1
    finally:
        sys.argv = old
    return code, out.getvalue(), err.getvalue()


FEATURE_WITH_EXTRAS = """\
# F07: A feature with structure

**Status:** ready
**Timing:** next

## Description
First paragraph, with a `backtick` and an - hyphen.

## Notes
- a bullet
- another

```bash
echo "a fenced block that must survive a round trip"
```

## Open questions
Does the parser keep this?
"""


class BacklogTestCase(unittest.TestCase):
    """Each test gets its own scaffolded backlog in a temp dir."""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.ctx = self.root / "context"
        code, _, err = run("--init", str(self.ctx))
        self.assertEqual(code, 0, err)

    def tearDown(self):
        self._tmp.cleanup()

    def write_feature(self, filename: str, text: str):
        (self.ctx / filename).write_text(text, encoding="utf-8")

    def table_rows(self) -> dict[str, tuple[str, str]]:
        """{FID: (timing, status)} as backlog.md states it — via the shipped parser,
        so these tests do not hard-code column positions."""
        rows = {}
        for line in (self.ctx / "backlog.md").read_text(encoding="utf-8").split("\n"):
            row = model.parse_table_row(line)
            if row:
                rows[row["fid"]] = (row["timing"], row["status"])
        return rows

    def table_themes(self) -> dict[str, str]:
        themes = {}
        for line in (self.ctx / "backlog.md").read_text(encoding="utf-8").split("\n"):
            row = model.parse_table_row(line)
            if row:
                themes[row["fid"]] = row["theme"]
        return themes

    def header_of(self, filename: str) -> tuple[str, str]:
        """(timing, status) as the feature file's own header states it."""
        status = timing = ""
        for line in (self.ctx / filename).read_text(encoding="utf-8").split("\n"):
            s = line.strip().lower()
            if s.startswith("**status:**"):
                status = s.split("**status:**", 1)[1].strip()
            elif s.startswith("**timing:**"):
                timing = s.split("**timing:**", 1)[1].strip()
            elif s.startswith("**category:**"):
                timing = s.split("**category:**", 1)[1].strip()
        return timing, status

    def theme_header_of(self, filename: str) -> str:
        for line in (self.ctx / filename).read_text(encoding="utf-8").split("\n"):
            if line.strip().lower().startswith("**theme:**"):
                return line.strip()[len("**Theme:**"):].strip()
        return ""


# ── the data layer ─────────────────────────────────────────────────────

class ModelRoundTrip(BacklogTestCase):

    def test_feature_file_survives_a_parse_and_save(self):
        """Lossless: sections, bullets and fenced blocks must come back unchanged.

        `set` rewrites the whole feature file, so anything the parser drops here
        is content silently deleted from a real backlog.
        """
        self.write_feature("F07-a-feature-with-structure.md", FEATURE_WITH_EXTRAS)
        before = (self.ctx / "F07-a-feature-with-structure.md").read_text(encoding="utf-8")
        f = model.parse_feature_file(self.ctx / "F07-a-feature-with-structure.md")
        model.save_feature_file(self.ctx, f)
        after = (self.ctx / "F07-a-feature-with-structure.md").read_text(encoding="utf-8")
        self.assertEqual(before, after)

    def test_writing_the_index_is_idempotent(self):
        """A no-op save must not churn the file — otherwise every TUI visit is a git diff."""
        run("add", "Second", "-c", "next", "-d", str(self.ctx))
        feats = model.load_features(self.ctx)
        model.save_backlog_index(self.ctx, feats)
        once = (self.ctx / "backlog.md").read_bytes()
        model.save_backlog_index(self.ctx, model.load_features(self.ctx))
        self.assertEqual(once, (self.ctx / "backlog.md").read_bytes())

    def test_backlog_table_wins_over_the_feature_header(self):
        """Documented contract: backlog.md owns status, category and order."""
        self.write_feature("F09-disagreeing.md",
                           "# F09: Disagreeing\n\n**Status:** idea\n**Category:** maybe\n\n## Description\nx\n")
        backlog = self.ctx / "backlog.md"
        backlog.write_text(
            backlog.read_text(encoding="utf-8").replace(
                "| F01 |", "| F09 | Disagreeing | now | shipped | `F09-disagreeing.md` |\n| F01 |", 1),
            encoding="utf-8")
        f = {x.fid: x for x in model.load_features(self.ctx)}["F09"]
        self.assertEqual((f.category, f.status), ("now", "shipped"))

    def test_next_fid_fills_gaps_and_widens_past_99(self):
        def fids(*ids):
            return [model.Feature(i, i, "later", "idea", f"{i}-x.md", "") for i in ids]
        self.assertEqual(model.next_fid(fids("F01", "F03")), "F02")
        self.assertEqual(model.next_fid(fids("F01", "F02")), "F03")
        self.assertEqual(model.next_fid(fids(*[f"F{n:02d}" for n in range(1, 100)])), "F100")
        self.assertEqual(model.next_fid([]), "F01")

    def test_slugify(self):
        self.assertEqual(model.slugify("Apple Watch — create a moment!"), "apple-watch-create-a-moment")
        self.assertEqual(model.slugify("***"), "feature")
        self.assertLessEqual(len(model.slugify("x" * 200)), 60)


# ── the commands ───────────────────────────────────────────────────────

class ListCommand(BacklogTestCase):

    def setUp(self):
        super().setUp()
        run("add", "Live thing", "-c", "now", "-s", "in-progress", "-d", str(self.ctx))
        run("add", "Done thing", "-c", "now", "-s", "shipped", "-d", str(self.ctx))
        run("add", "Cold thing", "-c", "later", "-s", "parked", "-d", str(self.ctx))

    def test_shipped_and_parked_are_hidden_by_default(self):
        _, out, _ = run("list", "-d", str(self.ctx))
        self.assertIn("Live thing", out)
        self.assertNotIn("Done thing", out)
        self.assertNotIn("Cold thing", out)

    def test_all_shows_them(self):
        _, out, _ = run("list", "--all", "-d", str(self.ctx))
        for name in ("Live thing", "Done thing", "Cold thing"):
            self.assertIn(name, out)

    def test_explicit_status_overrides_the_default_hiding(self):
        _, out, _ = run("list", "-s", "shipped", "-d", str(self.ctx))
        self.assertIn("Done thing", out)
        self.assertNotIn("Live thing", out)

    def test_category_filter(self):
        _, out, _ = run("list", "-c", "later", "--all", "-d", str(self.ctx))
        self.assertIn("Cold thing", out)
        self.assertNotIn("Live thing", out)

    def test_json_is_parseable_and_carries_the_fields(self):
        _, out, _ = run("list", "--json", "-d", str(self.ctx))
        rows = json.loads(out)
        self.assertTrue(rows)
        self.assertEqual(set(rows[0]),
                         {"fid", "name", "theme", "timing", "status", "file", "plan", "research"})

    def test_unknown_filter_value_fails_loudly(self):
        code, _, err = run("list", "-s", "nearly-done", "-d", str(self.ctx))
        self.assertEqual(code, 1)
        self.assertIn("unknown status", err)
        self.assertIn("to-review", err)          # the valid list is printed

    def test_output_is_one_line_per_feature(self):
        _, out, _ = run("list", "--all", "-d", str(self.ctx))
        self.assertEqual(len([l for l in out.strip().split("\n") if l]), 4)


class ShowCommand(BacklogTestCase):

    def test_head_omits_the_body(self):
        _, out, _ = run("show", "F01", "--head", "-d", str(self.ctx))
        self.assertIn("F01", out)
        self.assertNotIn("Describe what this feature does", out)

    def test_body_is_printed_without_head(self):
        _, out, _ = run("show", "F01", "-d", str(self.ctx))
        self.assertIn("Describe what this feature does", out)

    def test_plan_and_research_are_opt_in(self):
        (self.ctx / "F01-example-feature-plan.md").write_text("PLAN BODY\n", encoding="utf-8")
        _, out, _ = run("show", "F01", "-d", str(self.ctx))
        self.assertNotIn("PLAN BODY", out)
        self.assertIn("F01-example-feature-plan.md", out)      # existence is still reported
        _, out, _ = run("show", "F01", "--plan", "-d", str(self.ctx))
        self.assertIn("PLAN BODY", out)

    def test_unknown_fid_exits_nonzero(self):
        code, _, err = run("show", "F99", "-d", str(self.ctx))
        self.assertEqual(code, 1)
        self.assertIn("no such feature", err)

    def test_lowercase_fid_works(self):
        code, out, _ = run("show", "f01", "--head", "-d", str(self.ctx))
        self.assertEqual(code, 0)
        self.assertIn("F01", out)


class SetCommand(BacklogTestCase):

    def test_both_files_are_updated(self):
        """The whole reason this command exists: table and header cannot drift."""
        code, out, err = run("set", "F01", "--status", "to-review", "--category", "now", "-d", str(self.ctx))
        self.assertEqual(code, 0, err)
        self.assertEqual(self.table_rows()["F01"], ("now", "to-review"))
        self.assertEqual(self.header_of("F01-example-feature.md"), ("now", "to-review"))
        self.assertIn("->", out)

    def test_invalid_status_changes_nothing(self):
        before = (self.ctx / "backlog.md").read_bytes()
        code, _, err = run("set", "F01", "--status", "almost", "-d", str(self.ctx))
        self.assertEqual(code, 1)
        self.assertIn("unknown status", err)
        self.assertEqual(before, (self.ctx / "backlog.md").read_bytes())

    def test_empty_set_is_refused(self):
        code, _, err = run("set", "F01", "-d", str(self.ctx))
        self.assertEqual(code, 1)
        self.assertIn("nothing to set", err)

    def test_setting_the_same_value_is_a_no_op(self):
        run("set", "F01", "-s", "ready", "-d", str(self.ctx))
        before = (self.ctx / "backlog.md").read_bytes()
        code, out, _ = run("set", "F01", "-s", "ready", "-d", str(self.ctx))
        self.assertEqual(code, 0)
        self.assertIn("unchanged", out)
        self.assertEqual(before, (self.ctx / "backlog.md").read_bytes())

    def test_set_leaves_the_description_intact(self):
        self.write_feature("F07-a-feature-with-structure.md", FEATURE_WITH_EXTRAS)
        run("set", "F07", "-s", "shipped", "-d", str(self.ctx))
        text = (self.ctx / "F07-a-feature-with-structure.md").read_text(encoding="utf-8")
        self.assertIn("a fenced block that must survive a round trip", text)
        self.assertIn("## Open questions", text)


class AddCommand(BacklogTestCase):

    def test_add_creates_file_and_row(self):
        code, out, err = run("add", "Wrist mark queue", "-c", "next", "-s", "ready",
                             "-b", "The tap must arrive.", "-d", str(self.ctx))
        self.assertEqual(code, 0, err)
        self.assertIn("F02", out)
        path = self.ctx / "F02-wrist-mark-queue.md"
        self.assertTrue(path.exists())
        self.assertIn("The tap must arrive.", path.read_text(encoding="utf-8"))
        self.assertEqual(self.table_rows()["F02"], ("next", "ready"))
        self.assertEqual(self.header_of(path.name), ("next", "ready"))

    def test_defaults_are_later_idea(self):
        run("add", "Someday", "-d", str(self.ctx))
        self.assertEqual(self.table_rows()["F02"], ("later", "idea"))

    def test_invalid_timing_creates_nothing(self):
        code, _, err = run("add", "Bad", "-t", "urgent", "-d", str(self.ctx))
        self.assertEqual(code, 1)
        self.assertIn("unknown timing", err)
        self.assertEqual(list(self.ctx.glob("F02-*.md")), [])

    def test_added_features_keep_getting_distinct_ids(self):
        for name in ("One", "Two", "Three"):
            run("add", name, "-d", str(self.ctx))
        rows = self.table_rows()
        self.assertEqual(sorted(rows), ["F01", "F02", "F03", "F04"])


class NextIdCommand(BacklogTestCase):

    def test_next_id_is_bare_and_advances(self):
        _, out, _ = run("next-id", "-d", str(self.ctx))
        self.assertEqual(out.strip(), "F02")
        run("add", "Taken", "-d", str(self.ctx))
        _, out, _ = run("next-id", "-d", str(self.ctx))
        self.assertEqual(out.strip(), "F03")


class CheckCommand(BacklogTestCase):

    def test_clean_backlog_passes(self):
        code, out, _ = run("check", "-d", str(self.ctx))
        self.assertEqual(code, 0)
        self.assertIn("0 problem", out)

    def test_status_drift_is_reported(self):
        path = self.ctx / "F01-example-feature.md"
        path.write_text(path.read_text(encoding="utf-8").replace("**Status:** idea", "**Status:** shipped"),
                        encoding="utf-8")
        code, out, _ = run("check", "-d", str(self.ctx))
        self.assertEqual(code, 1)
        self.assertIn("F01", out)
        self.assertIn("shipped", out)

    def test_row_without_a_file_is_reported(self):
        backlog = self.ctx / "backlog.md"
        backlog.write_text(backlog.read_text(encoding="utf-8").replace(
            "| F01 |", "| F42 | Ghost | now | ready | `F42-ghost.md` |\n| F01 |", 1), encoding="utf-8")
        code, out, _ = run("check", "-d", str(self.ctx))
        self.assertEqual(code, 1)
        self.assertIn("F42", out)
        self.assertIn("no feature file", out)

    def test_file_without_a_row_is_reported(self):
        self.write_feature("F08-orphan.md", "# F08: Orphan\n\n**Status:** idea\n**Category:** later\n\n## Description\nx\n")
        code, out, _ = run("check", "-d", str(self.ctx))
        self.assertEqual(code, 1)
        self.assertIn("no row in backlog.md", out)

    def test_check_never_writes(self):
        before = (self.ctx / "backlog.md").read_bytes()
        run("check", "-d", str(self.ctx))
        self.assertEqual(before, (self.ctx / "backlog.md").read_bytes())


class Themes(BacklogTestCase):
    """A theme is optional, free-form, and lives in both files like timing does."""

    def test_add_with_a_theme_writes_both_files(self):
        run("add", "Prefetch", "-t", "next", "--theme", "moments", "-d", str(self.ctx))
        self.assertEqual(self.table_themes()["F02"], "moments")
        self.assertEqual(self.theme_header_of("F02-prefetch.md"), "moments")

    def test_unthemed_file_has_no_theme_line(self):
        run("add", "Plain", "-d", str(self.ctx))
        text = (self.ctx / "F02-plain.md").read_text(encoding="utf-8")
        self.assertNotIn("**Theme:**", text)

    def test_set_assigns_and_clears(self):
        run("set", "F01", "--theme", "watch", "-d", str(self.ctx))
        self.assertEqual(self.table_themes()["F01"], "watch")
        run("set", "F01", "--theme", "", "-d", str(self.ctx))
        self.assertEqual(self.table_themes()["F01"], "")
        self.assertEqual(self.theme_header_of("F01-example-feature.md"), "")

    def test_none_also_clears(self):
        run("set", "F01", "--theme", "watch", "-d", str(self.ctx))
        run("set", "F01", "--theme", "none", "-d", str(self.ctx))
        self.assertEqual(self.table_themes()["F01"], "")

    def test_list_filters_by_theme(self):
        run("add", "A", "--theme", "moments", "-d", str(self.ctx))
        run("add", "B", "--theme", "watch", "-d", str(self.ctx))
        _, out, _ = run("list", "--theme", "moments", "-d", str(self.ctx))
        self.assertIn("F02", out)
        self.assertNotIn("F03", out)

    def test_theme_none_lists_the_unthemed(self):
        run("add", "Themed", "--theme", "moments", "-d", str(self.ctx))
        _, out, _ = run("list", "--theme", "none", "-d", str(self.ctx))
        self.assertIn("F01", out)          # the scaffolded sample has no theme
        self.assertNotIn("F02", out)

    def test_themes_command_counts(self):
        run("add", "A", "--theme", "moments", "-d", str(self.ctx))
        run("add", "B", "--theme", "moments", "-d", str(self.ctx))
        run("add", "C", "--theme", "watch", "-d", str(self.ctx))
        _, out, _ = run("themes", "-d", str(self.ctx))
        self.assertRegex(out, r"2\s+moments")
        self.assertRegex(out, r"1\s+watch")
        self.assertRegex(out, r"1\s+\(none\)")

    def test_themes_are_deduplicated_case_insensitively(self):
        run("add", "A", "--theme", "Moments", "-d", str(self.ctx))
        run("add", "B", "--theme", "moments", "-d", str(self.ctx))
        feats = model.load_features(self.ctx, with_bodies=False)
        self.assertEqual(len(model.themes_in_use(feats)), 1)

    def test_a_theme_with_spaces_survives_the_table(self):
        run("add", "A", "--theme", "watch app", "-d", str(self.ctx))
        self.assertEqual(self.table_themes()["F02"], "watch app")
        feats = {f.fid: f for f in model.load_features(self.ctx, with_bodies=False)}
        self.assertEqual(feats["F02"].theme, "watch app")


class BackwardCompatibility(BacklogTestCase):
    """A 1.7.0 backlog must keep working untouched — other people have these on disk."""

    OLD_TABLE = """# Old Backlog

| # | Feature | Category | Status | File |
|---|---|---|---|---|
| F01 | Example Feature | now | ready | `F01-example-feature.md` |
| F02 | Second | later | idea | `F02-second.md` |
"""
    OLD_FEATURE = """# F02: Second

**Status:** idea
**Category:** later

## Description
Written by 1.7.0.
"""

    def setUp(self):
        super().setUp()
        (self.ctx / "backlog.md").write_text(self.OLD_TABLE, encoding="utf-8")
        self.write_feature("F02-second.md", self.OLD_FEATURE)

    def test_old_five_column_table_still_parses(self):
        feats = {f.fid: f for f in model.load_features(self.ctx, with_bodies=False)}
        self.assertEqual((feats["F01"].timing, feats["F01"].status), ("now", "ready"))
        self.assertEqual((feats["F02"].timing, feats["F02"].status), ("later", "idea"))
        self.assertEqual(feats["F02"].theme, "")

    def test_old_category_header_is_read_as_timing(self):
        f = model.parse_feature_file(self.ctx / "F02-second.md")
        self.assertEqual(f.timing, "later")

    def test_category_flag_is_still_accepted(self):
        code, _, err = run("set", "F02", "-c", "now", "-d", str(self.ctx))
        self.assertEqual(code, 0, err)
        self.assertEqual(self.table_rows()["F02"][0], "now")

    def test_category_attribute_still_reads_and_writes(self):
        f = model.Feature("F09", "X", "next", "idea", "F09-x.md", "")
        self.assertEqual(f.category, "next")
        f.category = "later"
        self.assertEqual(f.timing, "later")

    def test_a_pipe_in_a_name_does_not_shift_timing_or_status(self):
        """Why the row parser works from the right, not from fixed positions.

        An unescaped pipe in a feature name must not be able to corrupt the two
        fields the loader acts on. It can still cost the theme on an old-layout
        row, which is asserted below so the limit is recorded rather than assumed.
        """
        row = model.parse_table_row("| F07 | Rename a | b file | moments | next | ready | `F07-x.md` |")
        self.assertEqual((row["fid"], row["timing"], row["status"]), ("F07", "next", "ready"))
        self.assertEqual(row["theme"], "moments")

        old = model.parse_table_row("| F08 | Pipe | in old | now | shipped | `F08-o.md` |")
        self.assertEqual((old["timing"], old["status"]), ("now", "shipped"))
        self.assertEqual(old["theme"], "in old")   # known limit, not a promise

    def test_a_short_or_malformed_row_is_ignored(self):
        self.assertIsNone(model.parse_table_row("| F09 | Odd | weird-status | `F09.md` |"))
        self.assertIsNone(model.parse_table_row("not a row"))
        self.assertIsNone(model.parse_table_row("|---|---|---|---|---|"))


class Migration(BacklogTestCase):

    def setUp(self):
        super().setUp()
        (self.ctx / "backlog.md").write_text(BackwardCompatibility.OLD_TABLE, encoding="utf-8")
        self.write_feature("F02-second.md", BackwardCompatibility.OLD_FEATURE)

    def test_migrate_rewrites_both_spellings(self):
        code, out, _ = run("migrate", "-d", str(self.ctx))
        self.assertEqual(code, 0)
        self.assertIn("F02-second.md", out)
        self.assertIn("**Timing:** later", (self.ctx / "F02-second.md").read_text(encoding="utf-8"))
        self.assertNotIn("**Category:**", (self.ctx / "F02-second.md").read_text(encoding="utf-8"))
        self.assertIn("| # | Feature | Theme | Timing | Status | File |",
                      (self.ctx / "backlog.md").read_text(encoding="utf-8"))

    def test_migrate_is_idempotent(self):
        run("migrate", "-d", str(self.ctx))
        after = (self.ctx / "backlog.md").read_bytes()
        code, out, _ = run("migrate", "-d", str(self.ctx))
        self.assertEqual(code, 0)
        self.assertIn("already on the current format", out)
        self.assertEqual(after, (self.ctx / "backlog.md").read_bytes())

    def test_dry_run_changes_nothing(self):
        before = (self.ctx / "F02-second.md").read_bytes()
        _, out, _ = run("migrate", "--dry-run", "-d", str(self.ctx))
        self.assertIn("would change", out)
        self.assertEqual(before, (self.ctx / "F02-second.md").read_bytes())

    def test_migrate_preserves_timing_and_status(self):
        run("migrate", "-d", str(self.ctx))
        self.assertEqual(self.table_rows()["F01"], ("now", "ready"))
        self.assertEqual(self.table_rows()["F02"], ("later", "idea"))


class MissingDirectory(unittest.TestCase):

    def test_pointing_at_nothing_exits_with_a_hint(self):
        code, _, err = run("list", "-d", "/tmp/definitely-not-a-backlog-dir-9f3a")
        self.assertEqual(code, 1)
        self.assertIn("--init", err)


# ── the guarantee that makes this split worth it ───────────────────────

class ImportLaziness(unittest.TestCase):

    def test_a_query_does_not_import_textual(self):
        """`backlog list` must never pull in the UI toolkit.

        This is the property the model/cli/tui split exists for; if it breaks,
        every agent-facing command pays a Textual import it never uses.
        """
        with TemporaryDirectory() as tmp:
            ctx = Path(tmp) / "context"
            run("--init", str(ctx))
            probe = (
                "import sys;"
                f"sys.path.insert(0, {str(SRC)!r});"
                "sys.argv=['backlog','list','-d'," f"{str(ctx)!r}" "];"
                "from backlog_tool.cli import main;"
                "\ntry: main()\nexcept SystemExit: pass\n"
                "print('TEXTUAL_IMPORTED' if 'textual' in sys.modules else 'TEXTUAL_ABSENT', file=sys.stderr)"
            )
            p = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True)
            self.assertIn("TEXTUAL_ABSENT", p.stderr, p.stderr)

    def test_the_package_itself_stays_cheap_to_import(self):
        probe = (
            "import sys;"
            f"sys.path.insert(0, {str(SRC)!r});"
            "import backlog_tool;"
            "print('TEXTUAL_IMPORTED' if 'textual' in sys.modules else 'TEXTUAL_ABSENT', file=sys.stderr)"
        )
        p = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True)
        self.assertIn("TEXTUAL_ABSENT", p.stderr, p.stderr)


class TuiStillLoads(unittest.TestCase):
    """The TUI delegates to the same loaders; constructing it catches a broken split."""

    @classmethod
    def setUpClass(cls):
        try:
            import textual  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("Textual not installed — TUI checks skipped")

    def test_the_app_constructs_and_sees_the_same_features(self):
        with TemporaryDirectory() as tmp:
            ctx = Path(tmp) / "context"
            run("--init", str(ctx))
            run("add", "Second", "-c", "now", "-d", str(ctx))
            from backlog_tool.tui import BacklogApp
            app = BacklogApp(ctx)
            self.assertEqual([f.fid for f in app.features],
                             [f.fid for f in model.load_features(ctx)])
            self.assertEqual(len(app.features), 2)

    def test_the_tui_reaches_the_shared_writer(self):
        """A TUI save and a CLI set must produce the same bytes for the same state."""
        with TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a" / "context", Path(tmp) / "b" / "context"
            for d in (a, b):
                run("--init", str(d))
                run("add", "Shared", "-c", "next", "-s", "ready", "-d", str(d))
            # via the CLI
            run("set", "F02", "-s", "to-review", "-d", str(a))
            # via the TUI's own objects and save path
            from backlog_tool.tui import BacklogApp
            app = BacklogApp(b)
            {f.fid: f for f in app.features}["F02"].set_status("to-review")
            model.save_feature_file(b, {f.fid: f for f in app.features}["F02"])
            app._sort_features()
            model.save_backlog_index(b, app.features)
            self.assertEqual((a / "backlog.md").read_bytes(), (b / "backlog.md").read_bytes())
            self.assertEqual((a / "F02-shared.md").read_bytes(), (b / "F02-shared.md").read_bytes())


class TuiActuallyRuns(unittest.IsolatedAsyncioTestCase):
    """Mount the real app headlessly — catches anything the split broke at compose time."""

    @classmethod
    def setUpClass(cls):
        try:
            import textual  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("Textual not installed — TUI checks skipped")

    async def test_mount_navigate_and_save(self):
        with TemporaryDirectory() as tmp:
            ctx = Path(tmp) / "context"
            run("--init", str(ctx))
            for name in ("Second", "Third"):
                run("add", name, "-c", "now", "-s", "ready", "-d", str(ctx))
            from backlog_tool.tui import BacklogApp
            app = BacklogApp(ctx)
            async with app.run_test() as pilot:
                table = app.query_one("#feature-table")
                self.assertGreater(table.row_count, 3)      # features + category separators
                await pilot.press("down", "right")
                before = (ctx / "backlog.md").read_bytes()
                await pilot.press("s")                      # save
                await pilot.pause()
                self.assertEqual(before, (ctx / "backlog.md").read_bytes(),
                                 "a save with no edits must not touch the file")

    async def test_timing_filter(self):
        with TemporaryDirectory() as tmp:
            ctx = Path(tmp) / "context"
            run("--init", str(ctx))
            run("add", "Soon", "-c", "now", "-d", str(ctx))
            run("add", "Someday", "-c", "later", "-d", str(ctx))
            from backlog_tool.tui import BacklogApp, ColumnFilterScreen
            app = BacklogApp(ctx)
            shown = lambda: {f.timing for f in app.display_rows if f is not None}
            before = (ctx / "backlog.md").read_bytes()
            async with app.run_test() as pilot:
                self.assertEqual(shown(), {"now", "next", "later"})
                await pilot.press("right", "right", "right", "up")   # onto the Timing header
                self.assertEqual(app._header_focused_col, "timing")
                await pilot.press("enter")
                await pilot.pause()
                self.assertIsInstance(app.screen, ColumnFilterScreen)
                await pilot.press("space", "down", "space", "enter")  # All off, "now" on
                await pilot.pause()
                self.assertEqual(shown(), {"now"})
                await pilot.press("f")
                await pilot.pause()
                await pilot.press("space", "enter")                   # All back on
                await pilot.pause()
                self.assertEqual(shown(), {"now", "next", "later"})
                await pilot.press("s")
                await pilot.pause()
            self.assertEqual(before, (ctx / "backlog.md").read_bytes(),
                             "the filter is view state and must not touch the files")


    async def test_theme_column_widens_for_a_long_theme(self):
        with TemporaryDirectory() as tmp:
            ctx = Path(tmp) / "context"
            run("--init", str(ctx))
            run("add", "Long", "--theme", "sync & conflicts", "-d", str(ctx))
            from backlog_tool.tui import BacklogApp
            app = BacklogApp(ctx)
            async with app.run_test() as pilot:
                await pilot.pause()
                width = next(c.width for c in app.query_one("#feature-table").columns.values()
                             if c.label.plain.startswith("Theme"))
                self.assertGreater(width, len("sync & conflicts"),
                                   "a theme must not be truncated in its own column")

    async def test_theme_filter_hides_the_unthemed(self):
        with TemporaryDirectory() as tmp:
            ctx = Path(tmp) / "context"
            run("--init", str(ctx))
            run("add", "Themed", "-t", "now", "--theme", "moments", "-d", str(ctx))
            from backlog_tool.tui import BacklogApp, ColumnFilterScreen
            app = BacklogApp(ctx)
            before = (ctx / "backlog.md").read_bytes()
            async with app.run_test() as pilot:
                themes = lambda: {f.theme for f in app.display_rows if f is not None}
                self.assertEqual(themes(), {"", "moments"})
                await pilot.press("right", "right", "up")        # onto the Theme header
                self.assertEqual(app._header_focused_col, "theme")
                await pilot.press("enter")
                await pilot.pause()
                self.assertIsInstance(app.screen, ColumnFilterScreen)
                # All off, then the first real value on — "moments" sorts before "(none)"
                await pilot.press("space", "down", "space", "enter")
                await pilot.pause()
                self.assertEqual(themes(), {"moments"})
            self.assertEqual(before, (ctx / "backlog.md").read_bytes(),
                             "a filter is view state and must not touch the files")

    async def test_status_filter_is_reachable_from_its_header(self):
        with TemporaryDirectory() as tmp:
            ctx = Path(tmp) / "context"
            run("--init", str(ctx))
            run("add", "Ready thing", "-t", "now", "-s", "ready", "-d", str(ctx))
            from backlog_tool.tui import BacklogApp, ColumnFilterScreen
            app = BacklogApp(ctx)
            async with app.run_test() as pilot:
                await pilot.press("right", "right", "right", "right", "up")
                self.assertEqual(app._header_focused_col, "status")
                await pilot.press("enter")
                await pilot.pause()
                self.assertIsInstance(app.screen, ColumnFilterScreen)
                await pilot.press("escape")
                await pilot.pause()
                self.assertEqual(app._hidden["status"], set(), "cancel must not filter")

    async def test_f_filters_the_column_the_cursor_is_in(self):
        with TemporaryDirectory() as tmp:
            ctx = Path(tmp) / "context"
            run("--init", str(ctx))
            from backlog_tool.tui import BacklogApp, ColumnFilterScreen
            app = BacklogApp(ctx)
            async with app.run_test() as pilot:
                await pilot.press("right", "right")              # Theme column
                await pilot.press("f")
                await pilot.pause()
                self.assertIsInstance(app.screen, ColumnFilterScreen)
                self.assertIn("theme", app.screen._title.lower())
                await pilot.press("escape")
                await pilot.pause()
                await pilot.press("right")                        # Timing column
                await pilot.press("f")
                await pilot.pause()
                self.assertIn("timing", app.screen._title.lower())

    async def test_theme_picker_assigns_and_can_create(self):
        """The Theme cell opens a picker of themes in use, plus a way to make a new one."""
        with TemporaryDirectory() as tmp:
            ctx = Path(tmp) / "context"
            run("--init", str(ctx))
            run("add", "Has theme", "-t", "now", "--theme", "moments", "-d", str(ctx))
            from backlog_tool.tui import BacklogApp, NewThemeScreen, ValuePickerScreen
            app = BacklogApp(ctx)

            async def open_theme_picker(feature):
                app._move_cursor_to(feature)
                table = app.query_one("#feature-table")
                table.move_cursor(row=table.cursor_row, column=2)   # the Theme column
                await pilot.press("enter")
                await pilot.pause()
                assert isinstance(app.screen, ValuePickerScreen), type(app.screen).__name__
                return app.screen.query_one("#picker-list")

            async def highlight(ol, wanted):
                """Walk to an option by id, rather than trusting a keypress count."""
                for _ in range(len(app.screen._options) + 1):
                    if ol.get_option_at_index(ol.highlighted).id == wanted:
                        return
                    await pilot.press("down")
                    await pilot.pause()
                raise AssertionError(f"{wanted!r} not reachable")

            async with app.run_test() as pilot:
                target = next(f for f in app.features if not f.theme)

                # 1. assign an existing theme
                ol = await open_theme_picker(target)
                # ValuePickerScreen keeps its options as plain strings
                self.assertEqual(app.screen._options[0], model.NO_THEME)
                self.assertIn("moments", app.screen._options)
                self.assertEqual(app.screen._options[-1], app.NEW_THEME_OPTION)
                await highlight(ol, "moments")
                await pilot.press("enter")
                await pilot.pause()
                await pilot.pause()
                self.assertEqual(target.theme, "moments")
                self.assertTrue(target.dirty, "an assigned theme is an unsaved edit")

                # 2. create one that does not exist yet
                ol = await open_theme_picker(target)
                await highlight(ol, app.NEW_THEME_OPTION)
                await pilot.press("enter")
                await pilot.pause()
                await pilot.pause()
                self.assertIsInstance(app.screen, NewThemeScreen)
                for ch in "watch":
                    await pilot.press(ch)
                await pilot.press("enter")
                await pilot.pause()
                await pilot.pause()
                self.assertEqual(target.theme, "watch")

                # 3. clearing it back to none
                ol = await open_theme_picker(target)
                await highlight(ol, model.NO_THEME)
                await pilot.press("enter")
                await pilot.pause()
                await pilot.pause()
                self.assertEqual(target.theme, "")

    async def test_a_new_theme_reuses_an_existing_spelling(self):
        """Typing "Moments" when "moments" exists must not create a case-variant twin."""
        with TemporaryDirectory() as tmp:
            ctx = Path(tmp) / "context"
            run("--init", str(ctx))
            run("add", "One", "-t", "now", "--theme", "moments", "-d", str(ctx))
            run("add", "Two", "-t", "now", "-d", str(ctx))
            from backlog_tool.tui import BacklogApp
            app = BacklogApp(ctx)
            async with app.run_test() as pilot:
                target = next(f for f in app.features if not f.theme)
                applied = []
                app._prompt_new_theme(target, applied.append)
                await pilot.pause()
                for ch in "Moments":
                    await pilot.press(ch)
                await pilot.press("enter")
                await pilot.pause()
                self.assertEqual(applied, ["moments"])


if __name__ == "__main__":
    unittest.main()
