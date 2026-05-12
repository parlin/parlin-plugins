---
name: deployed-artifacts
description: >
  Use when the user asks to list, show, see, or get all of their publicly
  deployed artifacts, apps, demos, sites, or web projects — e.g. "what have
  I deployed", "show my live apps", "list deployed artifacts", "/deployed".
  Reads two manifests (agentis-apps/apps.json for static Pages apps,
  agentis-user-pelle/context/artifacts_index.md for Vercel apps), pulls
  last-commit dates via git/gh, and returns a single combined list with
  name, one-line description, public URL, and "X ago" recency.
allowed-tools: Read, Bash, Glob
---

# Deployed Artifacts — Claude Code Skill

List every publicly deployed digital artifact the user owns, with recency info.

## Sources of truth (read both)

1. **Static / GitHub Pages apps** — `/Users/pelle/code/git/agentis-apps/apps.json`
   - Shape: `{ "apps": [ { "slug", "title", "description" } ] }`
   - Live URL pattern: `https://parlin.github.io/agentis-apps/<slug>/`
   - Repo is the local clone at `/Users/pelle/code/git/agentis-apps/`

2. **App / Vercel artifacts** — `/Users/pelle/code/git/agentis-user-pelle/context/artifacts_index.md`
   - Markdown table with columns: Slug, Title, Type, Live URL, Repo, Project folder, Deployed at, Status
   - Only include rows where `Status` is `deployed` (skip `awaiting-import`, `archived`, etc.)
   - For non-deployed rows, mention them separately at the end as "Pending" so the user sees they exist.

## How to get last-commit info

### Static apps (one folder per slug inside `agentis-apps`)

```bash
git -C /Users/pelle/code/git/agentis-apps log -1 --format="%cI" -- <slug>/
```

Returns an ISO-8601 timestamp. If empty (folder doesn't exist yet), fall back to repo HEAD.

### Vercel apps (separate GitHub repos)

The repos are usually not cloned locally. Use `gh` to query GitHub:

```bash
gh api repos/parlin/<repo-name>/commits --jq '.[0].commit.committer.date' 2>/dev/null
```

Extract `<repo-name>` from the Repo column URL (strip `https://github.com/parlin/`).
If `gh` fails or returns empty (private repo without access, repo missing), mark recency as `unknown`.

## Computing "time ago"

Today is whatever `date -u +%Y-%m-%dT%H:%M:%SZ` returns. Subtract the commit timestamp and format:

- `< 60s` → `just now`
- `< 60m` → `N min ago` (1 min ago, 45 min ago)
- `< 24h` → `N hr ago` / `N hrs ago`
- `< 7d` → `N day ago` / `N days ago`
- `< 5w` → `N wk ago` / `N wks ago`
- `< 12mo` → `N mo ago`
- else → `N yr ago` / `N yrs ago`

Quick way: shell it out.

```bash
python3 - <<'PY'
from datetime import datetime, timezone
import sys
ts = sys.argv[1]
dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
delta = datetime.now(timezone.utc) - dt
s = int(delta.total_seconds())
if s < 60: out = "just now"
elif s < 3600: out = f"{s//60} min ago"
elif s < 86400: h = s//3600; out = f"{h} hr ago" if h == 1 else f"{h} hrs ago"
elif s < 604800: d = s//86400; out = f"{d} day ago" if d == 1 else f"{d} days ago"
elif s < 3024000: w = s//604800; out = f"{w} wk ago" if w == 1 else f"{w} wks ago"
elif s < 31536000: out = f"{s//2592000} mo ago"
else: y = s//31536000; out = f"{y} yr ago" if y == 1 else f"{y} yrs ago"
print(out)
PY
```

Pass the ISO timestamp as `argv[1]`. Print one number per call, or batch in a loop.

## Output format

Plain markdown, newest-first by last-commit. One block per artifact:

```
### <Title> (<slug>)
<one-line description>
URL: <live url>
Last commit: <YYYY-MM-DD> · <X ago>
```

Then a brief footer summary: total count, deployed vs pending.

If a row is `awaiting-import` / not yet deployed, list it in a separate "Pending deployments" section after the deployed list — title, slug, status, no recency.

## Procedure

1. Read both manifests.
2. Build a unified list of `{ slug, title, description, url, repo_kind, repo_ref, status }`.
   - `repo_kind`: `"local-folder"` (agentis-apps) or `"github-repo"` (Vercel).
   - `repo_ref`: the slug subfolder, or the `parlin/<repo>` slug.
3. For each `deployed` entry, fetch last-commit timestamp using the right method.
4. Compute "time ago" for each.
5. Sort by timestamp descending; print.
6. Print pending entries (if any) below.

## Things to be careful about

- Skip duplicates: `sleepy-hour` appears in both manifests. The artifacts_index entry is authoritative for title/URL; the apps.json entry confirms it's a Pages app. List it once.
- If apps.json grows new entries that aren't yet in artifacts_index.md (or vice versa), still list them.
- Don't pull `git` history that requires network unless `gh` is the only option — local git log is free and fast.
- Don't invent recency — if `gh` fails for a private/missing repo, say `Last commit: unknown` and move on.
