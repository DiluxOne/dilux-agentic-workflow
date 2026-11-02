#!/usr/bin/env bash
# DAW — gemini · before a write: refuse the ones that would break the FSM.
#
# A thin shim on purpose. Which transitions are legal, which gate is missing and
# what to say about it are the method's business and live in
# .daw/scripts/hook-gate.py, shared by every tool. What belongs HERE is only
# what is true of this tool: where its repo root comes from, and which dialect
# its refusal has to be written in.
set -uo pipefail

REPO="$([ -n "${GEMINI_PROJECT_DIR:-}" ] && printf "%s" "$GEMINI_PROJECT_DIR" || git rev-parse --show-toplevel 2>/dev/null || pwd)"
# Repo first, plugin second — the order every adapter resolves in. A `.daw/` in
# the project is the copy the user can read and edit, so it wins; under a plugin
# there is none, and a hook that looks only there allows every write it was
# installed to judge while the skills load and the pipeline looks installed.
PLUGIN_ROOT="${DAW_PLUGIN_ROOT:-}"
DAW="$REPO/.daw"
if [ ! -f "$DAW/scripts/hook-gate.py" ] && [ -n "$PLUGIN_ROOT" ] \
   && [ -f "$PLUGIN_ROOT/daw/scripts/hook-gate.py" ]; then
  DAW="$PLUGIN_ROOT/daw"
fi
GATE="$DAW/scripts/hook-gate.py"
STATE="$REPO/.daw-state.json"
GRAPH="$DAW/rules/transition-graph.json"

# Not installed here → say nothing and allow. A hook is not the place to
# complain about a repo that never asked for DAW.
if [ ! -f "$GATE" ]; then exit 0; fi   # DAW is not installed here
command -v python3 >/dev/null 2>&1 || {
  echo "DAW cannot enforce anything without python3 on PATH. Refusing the write." >&2
  exit 2
}

exec python3 "$GATE" --dialect gemini --mode pre --state "$STATE" --graph "$GRAPH" --repo "$REPO" --method "$DAW"
