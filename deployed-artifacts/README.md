# deployed-artifacts

Claude Code plugin that lists every publicly deployed Agentis artifact with a live URL and "X ago" recency.

## What it does

When you ask Claude something like:

- "list my deployed artifacts"
- "what have I deployed?"
- "show all live apps"
- "/deployed"

…the skill reads two manifests, fetches last-commit dates, and returns a combined list:

```
### Bed time (sleepy-hour)
Tap animals to tuck them in. Default 4×5; pass ?cols=N&rows=M to change the grid.
URL: https://parlin.github.io/agentis-apps/sleepy-hour/
Last commit: 2026-04-24 · 18 days ago
```

## Sources

| Manifest | Covers |
| --- | --- |
| `agentis-apps/apps.json` | Static GitHub Pages apps (one folder per slug in `agentis-apps`) |
| `agentis-user-pelle/context/artifacts_index.md` | Vercel-deployed app artifacts (one repo per slug) |

Static recency comes from local `git log` against the folder. Vercel recency comes from `gh api` against the GitHub repo. If `gh` can't reach a repo, the entry shows `Last commit: unknown`.

## Files

```
.claude-plugin/plugin.json
skills/deployed-artifacts/SKILL.md
```

No CLI, no install — Claude invokes the skill directly when it recognizes a matching request.
