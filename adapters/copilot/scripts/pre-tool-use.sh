#!/usr/bin/env bash
# DAW — Copilot CLI · preToolUse: refuse a write that would break the FSM.
#
# The whole job is: hand the event to the shared gate without touching it. The
# previous version read stdin into a variable first, so by the time the
# validator ran there was nothing left to read; it saw an empty envelope, exited
# 0, and every illegal transition went through. Copilot looked installed and
# enforced nothing.
#
# `--dialect copilot` covers the second half: Copilot's envelope is camelCase
# (`toolName`/`toolArgs`), and its refusal is a JSON verdict on stdout as well
# as exit 2.
set -uo pipefail

REPO="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
# Repo first, plugin second — the same order every adapter resolves in.
# There is no stand-down here any more, and there must not be one. It read: if
# this is the user-level copy and the repo wires its own hook, keep quiet —
# which was right only while a repo-level manifest existed to take over. DAW
# writes none: Copilot loads repository hooks only in a folder the user has
# trusted, and `-p` cannot ask for trust, so the gates live at user level ONLY.
# A copy that steps aside for a repo hook steps aside for nothing at all.
DAW="$REPO/.daw"
if [ ! -f "$DAW/scripts/hook-gate.py" ]; then
  if [ -n "${DAW_PLUGIN_ROOT:-}" ] && [ -f "$DAW_PLUGIN_ROOT/daw/scripts/hook-gate.py" ]; then
    DAW="$DAW_PLUGIN_ROOT/daw"
  else                      # DAW is not reachable from here
    echo '{}'
    exit 0
  fi
fi
# Without python3 there is nothing to judge this write, and a hook that
# cannot judge has to refuse. Copilot reads any exit other than 2 as a
# non-blocking error: without this block the `exec` below exits 127 and the
# write goes in. The other five adapters had it; these two did not — and they
# are precisely the two that decide writes.
#
# AFTER the reachability check, as in the other five: placed before it, a
# repo without DAW installed is left unable to write over a tool it does not
# need.
command -v python3 >/dev/null 2>&1 || {
  echo "DAW cannot enforce anything without python3 on PATH. Refusing the write." >&2
  exit 2
}

GATE="$DAW/scripts/hook-gate.py"
STATE="$REPO/.daw-state.json"
GRAPH="$DAW/rules/transition-graph.json"

exec python3 "$GATE" --dialect copilot --mode pre --state "$STATE" --graph "$GRAPH" --repo "$REPO" --method "$DAW"
