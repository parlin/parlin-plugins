#!/usr/bin/env bash
# Install or upgrade the `backlog` command so it matches this plugin's version.
#
# This lives in a script rather than in SKILL.md because the skill text is loaded
# into the model's context on every invocation, and none of the reasoning below
# needs to be. Run it before `backlog`; it is a no-op when versions already agree.
#
# Why not `command -v backlog`: that short-circuits forever once any binary
# exists, so a plugin auto-update would never reach the command actually on PATH.
# Versions before 1.2.0 have no --version flag, so CUR_VER reads "none" and they
# upgrade correctly on first run.
#
# pipx is preferred: it isolates the tool instead of writing into system Python.
# `--backend pip` sidesteps pipx's own uv version requirement.
set -euo pipefail

PLUGIN_DIR="${CLAUDE_PLUGIN_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
PLUGIN_VER=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['version'])" \
             "${PLUGIN_DIR}/.claude-plugin/plugin.json")
CUR_VER=$(backlog --version 2>/dev/null || echo none)

if [ "$CUR_VER" = "$PLUGIN_VER" ]; then
  echo "backlog $CUR_VER (current)"
  exit 0
fi

echo "backlog: $CUR_VER -> $PLUGIN_VER"
if command -v pipx >/dev/null 2>&1; then
  pipx install --force --backend pip "$PLUGIN_DIR"
else
  pip install --upgrade "$PLUGIN_DIR" --break-system-packages
fi
