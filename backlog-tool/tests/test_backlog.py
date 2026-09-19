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
**Category:** next

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
        """{FID: (category, status)} as backlog.md states it."""
        rows = {}
        for line in (self.ctx / "backlog.md").read_text(encoding="utf-8").split("\n"):
            cells = [c.strip() for c in line.strip().split("|")]
            if len(cells) >= 6 and cells[1].upper().startswith("F") and cells[1][1:].isdigit():
                rows[cells[1].upper()] = (cells[3], cells[4])
        return rows

    def header_of(self, filename: str) -> tuple[str, str]:
        """(category, status) as the feature file's own header states it."""
        status = category = ""
        for line in (self.ctx / filename).read_text(encoding="utf-8").split("\n"):
            s = line.strip().lower()
            if s.startswith("**status:**"):
                status = s.split("**status:**", 1)[1].strip()
            elif s.startswith("**category:**"):
                category = s.split("**category:**", 1)[1].strip()
        return category, status


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
        self.assertEqual(set(rows[0]), {"fid", "name", "category", "status", "file", "plan", "research"})

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

    def test_invalid_category_creates_nothing(self):
        code, _, err = run("add", "Bad", "-c", "urgent", "-d", str(self.ctx))
        self.assertEqual(code, 1)
        self.assertIn("unknown category", err)
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


if __name__ == "__main__":
    unittest.main()
