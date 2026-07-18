# parlin-plugins

A **Claude Code plugin marketplace** — the repo *is* the distributable.
`.claude-plugin/marketplace.json` lists every plugin; each subdirectory is one plugin.

This repo is public: marketplace users read these files. Keep private notes and
plans in `context/` (gitignored).

## Layout

    .claude-plugin/marketplace.json     # marketplace manifest — lists all plugins
    <plugin>/.claude-plugin/plugin.json # per-plugin manifest
    <plugin>/skills/<skill>/SKILL.md    # the actual behavior
    backlog-tool/src/backlog_tool/      # only plugin with real code (Python/Textual TUI)

Plugins: `backlog-tool` (Textual TUI + skill), `apple-dev` (build-to-phone,
testflight), `deployed-artifacts` (list live deploys).

A skill's frontmatter `description` is what makes Claude trigger it — write it as
"use when the user…" phrasing, not as a summary.

## backlog-tool: design intent

Read this before changing its behavior — these are goals, not accidents.

A nimble but powerful task manager living in the terminal and inside the user's
project, so they can stay in the terminal instead of switching to another app.

- **Plain markdown, conventional layout.** Tasks and plans are individual `.md`
  files with intuitive names. This is deliberate: the structure is already familiar
  to AI agents, so the files *are* the integration surface — no API needed. Keep
  backlogs greppable, diffable, and versioned next to the code.
- **Arrow keys or mouse.** Both navigation modes are supported; don't regress either.
- **Shortcuts for everything** — keyboard-first, documented in the plugin README.

## Gotchas

- **backlog-tool's version lives in THREE places** — bumping one is not enough:
  `backlog-tool/pyproject.toml`, `backlog-tool/.claude-plugin/plugin.json`, and the
  `backlog-tool` entry in `.claude-plugin/marketplace.json`. These drifted once
  already (pyproject shipped 1.1.1 while both manifests still said 1.0.0).
- `context/` is gitignored repo-wide — that's where private plans/notes go. It is
  also the dir the backlog skill scaffolds, so don't run `backlog --init` here and
  expect tracked output.
- Author name is `Par Lindhe` in all manifests. Keep new plugins consistent.
- No tests, no linter, no CI. Verification is manual — run the tool and look.

## backlog-tool dev loop

Editing the TUI source has no effect until reinstalled — `backlog` runs from pipx,
not from this repo:

    pipx install --force ./backlog-tool
    backlog --init     # scaffold a context/ backlog in the cwd
    backlog            # run TUI against ./context

## Publishing

Pushing to `main` is what publishes to marketplace users — there is no build or
release step. Push deliberately.
