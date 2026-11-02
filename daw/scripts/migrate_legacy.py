#!/usr/bin/env python3
"""A project set up under DAW's former name, moved to DAW's.

Until the rename the plugin, its directory, its runtime files and its markers all
carried the product's former name, `ddw`/`DDW`. This module is the one place in
DAW that still knows that name (a test greps for it): everything else reads the
new one, and a project that has the old files is moved here, once.

What moves, each by a rename and the state file last, so an interrupted run is
finished by the next one:

  - the runtime: `.ddw-paused/`, `.ddw-sessions/`, `.ddw-work/`,
    `.ddw-journal.jsonl`, the method's copy `.ddw/`, the install record
    `.ddw-installed.json`, the artifacts `docs/ddw/`, a family map
    `ddw-family.md`, and `.ddw-state.json`, whose old names are rewritten;
  - what an older installer put in the project under the old name, as its
    install record lists it (skills, agents, commands, hook directories), so
    the next install reads it as its own and upgrades it in place;
  - the `BEGIN/END DDW` blocks of `.gitignore`, AGENTS.md, CLAUDE.md and
    GEMINI.md, and the markers of the managed blocks under `docs/daw/`;
  - the hook entries in each tool's settings that run one of the files moved.
    Nothing else in those files is touched: a hook of the project's own does
    not name a file DAW installed.

An artifact whose markers are rewritten has new bytes, so its receipt (a digest
of them, `daw_receipt.py`) is sealed again: only a receipt the journal shows a
validator wrote is carried over, so the move cannot turn a forged one into a
real one. The journal gets one entry naming what moved.

It refuses, and changes nothing, when a runtime file exists under both names:
which of the two is the project's pipeline is not something to guess.

    migrate_legacy.py --repo DIR [--quiet]

Exit 0: moved, or nothing to move. Exit 3: refused (it says why). Stdlib only.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import daw_receipt  # noqa: E402

OLD, NEW = "ddw", "daw"

# (old, new), from the project's root. The state file is last on purpose.
RUNTIME = (
    (".ddw-paused", ".daw-paused"),
    (".ddw-sessions", ".daw-sessions"),
    (".ddw-work", ".daw-work"),
    (".ddw-journal.jsonl", ".daw-journal.jsonl"),
    (".ddw", ".daw"),
    (".ddw-installed.json", ".daw-installed.json"),
    (os.path.join("docs", "ddw"), os.path.join("docs", "daw")),
    ("ddw-family.md", "daw-family.md"),
)
STATE = (".ddw-state.json", ".daw-state.json")

CONTEXT_FILES = ("AGENTS.md", "CLAUDE.md", "GEMINI.md")
# Each tool's settings, where DAW merges its hooks (adapters/*/adapter.json
# `settings_merge.to`).
SETTINGS = (".claude/settings.json", ".codex/hooks.json", ".cursor/hooks.json",
            ".gemini/settings.json")

# The name as a word of a path or an identifier: `ddw/`, `.ddw-state.json`,
# `skills/ddw-eject`, `DDW_PLUGIN_ROOT`, `<!-- BEGIN DDW -->`.
_TOKEN = re.compile(r"(?<![A-Za-z])(ddw|DDW|Ddw)(?![a-z])")
_NEW_TOKEN = re.compile(r"(?<![A-Za-z])(daw|DAW|Daw)(?![a-z])")
_CASES = {"ddw": "daw", "DDW": "DAW", "Ddw": "Daw"}
_GITIGNORE_BLOCK = re.compile(r"^# BEGIN DDW\b.*?^# END DDW[^\n]*$", re.M | re.S)
_HTML_BLOCK = re.compile(r"<!-- BEGIN DDW\b.*?<!-- END DDW -->", re.S)
_MARKER = re.compile(r"<!--\s*(BEGIN|END) DDW\b")
# In the state, only the paths: a ticket's title is the user's words.
_STATE_PATH = re.compile(r"(?<![A-Za-z0-9])(\.ddw(?=[-/.\"]|$)|docs/ddw(?=/)|ddw-family\.md)")


class Refused(Exception):
    pass


def current_text(text):
    """A text written under the old name, in the new one."""
    return _TOKEN.sub(lambda m: _CASES[m.group(1)], text)


def legacy_path(rel):
    """Where a file of DAW's repository was before the rename (for reading an
    older commit: `git show <commit>:<legacy_path(rel)>`)."""
    back = {v: k for k, v in _CASES.items()}
    return _NEW_TOKEN.sub(lambda m: back[m.group(1)], rel)


def legacy_present(repo):
    """Whether the project still has a runtime file under the old name."""
    return any(os.path.lexists(os.path.join(repo, old)) for old, _ in RUNTIME + (STATE,))


def _read(path):
    """A file's text; None when it cannot be read as UTF-8, and then it is
    left as it is: not DAW's to repair."""
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except (OSError, UnicodeDecodeError):
        return None


def _write(path, text):
    tmp = path + ".migrating"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)


def _empty_dir(path):
    return os.path.isdir(path) and not os.path.islink(path) and not os.listdir(path)


def _conflicts(repo):
    """The runtime files that exist under both names. An empty directory under
    the new name is not a pipeline (a hook that ran before this made it)."""
    found = []
    for old, new in RUNTIME + (STATE,):
        o, n = os.path.join(repo, old), os.path.join(repo, new)
        if os.path.lexists(o) and os.path.lexists(n) and not _empty_dir(n):
            found.append((old, new))
    return found


def _move(repo, old, new, moved):
    o, n = os.path.join(repo, old), os.path.join(repo, new)
    if not os.path.lexists(o):
        return
    if _empty_dir(n):
        os.rmdir(n)
    if os.path.lexists(n):
        return
    os.makedirs(os.path.dirname(n) or repo, exist_ok=True)
    os.replace(o, n)
    moved.append((old.replace(os.sep, "/"), new.replace(os.sep, "/")))


def _receipts(repo):
    """{digest: [(receipt name, its lines)]} of the receipts the journal shows a
    validator wrote."""
    journal = os.path.join(repo, ".daw-journal.jsonl")
    written = set()
    if os.path.isfile(journal):
        for line in (_read(journal) or "").splitlines():
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if isinstance(entry, dict) and entry.get("record") == "receipt":
                written.add(entry.get("name"))
    out = {}
    sessions = os.path.join(repo, ".daw-sessions")
    for name in sorted(os.listdir(sessions)) if os.path.isdir(sessions) else ():
        m = re.fullmatch(r"(.+)-validated-([0-9a-f]{12})", name)
        if m and name in written:
            lines = (_read(os.path.join(sessions, name)) or "").splitlines()
            out.setdefault(m.group(2), []).append((m.group(1), lines))
    return out


def _reseal(path, old_text, new_text, receipts):
    """Seal `path`'s new bytes with every receipt its old bytes carried."""
    sealed = []
    base = os.path.basename(path)
    for prefix, lines in receipts.get(daw_receipt.digest_of(old_text), []):
        if not lines or lines[0].strip() != base:
            continue
        fields = dict(l.split(": ", 1) for l in lines[1:] if ": " in l)
        sealed.append(daw_receipt.write(path, prefix, new_text,
                                        tier=fields.get("tier"), asof=fields.get("asof")))
    return sealed


def _markers(repo, rewritten):
    """The managed blocks' markers under docs/daw/ and in the family map,
    their receipts sealed again."""
    receipts = _receipts(repo)
    paths = [os.path.join(repo, "daw-family.md")]
    for base, _dirs, files in os.walk(os.path.join(repo, "docs", "daw")):
        paths += [os.path.join(base, f) for f in sorted(files) if f.endswith(".md")]
    for path in paths:
        if not os.path.isfile(path):
            continue
        text = _read(path)
        if text is None:
            continue
        new = _MARKER.sub(lambda m: m.group(0)[:-3] + "DAW", text)
        if new != text:
            _write(path, new)
            _reseal(path, text, new, receipts)
            rewritten.append(os.path.relpath(path, repo).replace(os.sep, "/"))


def _blocks(repo, rewritten):
    for rel, pattern in [(".gitignore", _GITIGNORE_BLOCK)] + [(f, _HTML_BLOCK) for f in CONTEXT_FILES]:
        path = os.path.join(repo, rel)
        if not os.path.isfile(path):
            continue
        text = _read(path)
        if text is None:
            continue
        new = pattern.sub(lambda m: current_text(m.group(0)), text)
        if new != text:
            _write(path, new)
            rewritten.append(rel)


def _installed(repo, moved):
    """What the old installer recorded under the old name, moved to the new
    one, and the record with it. Returns the (old, new) paths moved."""
    files = []
    path = os.path.join(repo, ".daw-installed.json")
    legacy = os.path.join(repo, ".daw", ".installed.json")
    record = path if os.path.isfile(path) else legacy if os.path.isfile(legacy) else None
    if not record:
        return files
    try:
        manifest = json.loads(_read(record) or "")
    except ValueError:
        return files
    if not isinstance(manifest, dict):
        return files
    renamed = {}
    for key, value in manifest.items():
        prefix, sep, rel = key.partition(":") if ":" in key else ("", "", key)
        new_rel = current_text(rel)
        if new_rel != rel:
            # The method's own files (`method:.ddw/…`) already moved with it.
            _move(repo, rel, new_rel, moved)
            files.append((rel, new_rel))
        renamed[prefix + sep + new_rel] = value
    if renamed != manifest:
        _write(record, json.dumps(renamed, indent=2, sort_keys=True) + "\n")
    # The directories a move left empty (`.codex/hooks/ddw/`).
    for old_rel, _new in files:
        d = os.path.dirname(os.path.join(repo, old_rel))
        while d != repo and _empty_dir(d) and _TOKEN.search(os.path.basename(d)):
            os.rmdir(d)
            d = os.path.dirname(d)
    return files


def _settings(repo, files, rewritten):
    """The hook entries that run one of the files moved, pointed at the new
    path. Every other string in the file stays as it was."""
    pairs = [(o, n) for o, n in files if o != n]
    if not pairs:
        return

    def fix(node):
        if isinstance(node, dict):
            return {k: fix(v) for k, v in node.items()}
        if isinstance(node, list):
            return [fix(v) for v in node]
        if isinstance(node, str):
            for o, n in pairs:
                node = node.replace(o, n)
        return node

    for rel in SETTINGS:
        path = os.path.join(repo, rel)
        if not os.path.isfile(path):
            continue
        try:
            data = json.loads(_read(path) or "")
        except ValueError:
            continue
        if not isinstance(data, dict) or "hooks" not in data:
            continue
        hooks = fix(data["hooks"])
        if hooks != data["hooks"]:
            data["hooks"] = hooks
            _write(path, json.dumps(data, indent=2) + "\n")
            rewritten.append(rel)


def _state(repo, moved):
    old, new = (os.path.join(repo, p) for p in STATE)
    if not os.path.lexists(old):
        return
    try:
        data = json.loads(_read(old) or "")
    except ValueError:
        # Not readable is not ours to repair: it moves as it is, and the gate
        # says what is wrong with it under its new name.
        data = None
    if data is not None:
        fixed = json.loads(_STATE_PATH.sub(lambda m: current_text(m.group(0)), json.dumps(data)))
        if fixed != data:
            _write(old, json.dumps(fixed, indent=2, ensure_ascii=False) + "\n")
    _move(repo, STATE[0], STATE[1], moved)


def migrate(repo):
    """Move the project at `repo` to DAW's names. Returns what it did, as
    {"moved": [(old, new)], "rewritten": [path]}; raises Refused."""
    repo = os.path.abspath(repo)
    conflicts = _conflicts(repo)
    if conflicts:
        raise Refused("this project has DAW's files under both names (%s): which one is "
                      "its pipeline is not something to guess. Keep one of each pair and "
                      "run this again: python3 <daw>/scripts/migrate_legacy.py --repo ."
                      % ", ".join("%s and %s" % pair for pair in conflicts))
    moved, rewritten = [], []
    for old, new in RUNTIME:
        _move(repo, old, new, moved)
    files = _installed(repo, moved)
    # And a command that runs the method's own copy, which moved with `.ddw/`.
    _settings(repo, files + [("/.ddw/", "/.daw/")], rewritten)
    _blocks(repo, rewritten)
    _markers(repo, rewritten)
    had_state = os.path.lexists(os.path.join(repo, STATE[0]))
    _state(repo, moved)
    if moved or rewritten:
        entry = {"record": "notice", "note": "migrated from the former name: moved %s; rewrote %s"
                 % (", ".join("%s -> %s" % m for m in moved) or "nothing",
                    ", ".join(rewritten) or "nothing")}
        if had_state or os.path.isfile(os.path.join(repo, STATE[1])):
            try:
                with open(os.path.join(repo, ".daw-journal.jsonl"), "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(entry, sort_keys=True) + "\n")
            except OSError:
                pass
    return {"moved": moved, "rewritten": rewritten}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    ap.add_argument("--repo", default=".")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)
    try:
        done = migrate(args.repo)
    except Refused as why:
        print("daw-migrate: refused, nothing was changed. %s" % why, file=sys.stderr)
        return 3
    if not args.quiet and (done["moved"] or done["rewritten"]):
        print("daw-migrate: this project now uses DAW's names.")
        for old, new in done["moved"]:
            print("  moved %s -> %s" % (old, new))
        for rel in done["rewritten"]:
            print("  rewrote %s" % rel)
    return 0


if __name__ == "__main__":
    sys.exit(main())
