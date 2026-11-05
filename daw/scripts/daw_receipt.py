#!/usr/bin/env python3
"""Writing a validation receipt, in one place.

Six validators each had their own copy of "hash the text, write
`.daw-sessions/<prefix>-validated-<digest>`, print the path". Six copies of one
rule is how the rule drifts, and it is the shape this project keeps finding.

What is new here is the second half. The receipt is a file, and a file can be
written by anything that can write files — `printf > .daw-sessions/prd-validated-
abc123` forges one in a single shell command. The pre-write hook refuses that
path through a tool, but a shell is not a tool call with a path in it
(`docs/RATIONALE.md` decision 11 is honest that the shell is detected rather than
prevented). So the validator that writes a receipt also records THAT IT DID, in
the append-only journal the hook keeps — and the gate then asks for both. A
forged receipt with no journal line is a receipt nobody's validator wrote.

This does not make forgery impossible: both files can be written by the same
shell. It makes it take two coordinated writes instead of one, and it leaves the
second one in a record that survives deleting the state. Stated plainly rather
than implied, because a guarantee whose scope is unstated gets read as total.
"""
import hashlib
import json
import os
import re

JOURNAL = ".daw-journal.jsonl"
SESSIONS = ".daw-sessions"


def _tiers():
    """The tiers that exist, read from the graph that defines them.

    Every validator takes `--tier` and none of them constrained it, so any string
    at all was accepted — and since the tier selects which rules run, `--tier
    QUICK-FIX` on a FEATURE's document was a way to be judged by a shorter set of
    rules and get a receipt for it. Constraining the flag is half of closing
    that; the other half is the gate comparing the receipt's tier to the state's.

    Read from the graph rather than typed here, so a tier added there is
    accepted here without anyone remembering to. Falls back to the four that
    exist today if the graph cannot be read: a validator that cannot find the
    graph must still be able to validate a document.
    """
    graph = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         os.pardir, "rules", "transition-graph.json")
    try:
        with open(graph, encoding="utf-8") as fh:
            names = sorted(json.load(fh).get("tiers", {}))
        if names:
            return tuple(names)
    except (OSError, ValueError, AttributeError):
        pass
    return ("DISCOVERY", "FEATURE", "FIX", "QUICK-FIX")


TIERS = _tiers()



FAMILY_MAP_NAMES = ("daw-family.md", "familia.md")


def find_family_map(start, limit=6):
    """The family map at or above `start`: `daw-family.md`, or the deprecated
    `familia.md` (still read so existing families keep working; anything that
    CREATES a map writes the new name)."""
    for name in FAMILY_MAP_NAMES:
        p = find_upward(start, name, limit)
        if p:
            return p
    return None


def family_map_in(root):
    """The family map directly inside `root`, preferring the new name."""
    for name in FAMILY_MAP_NAMES:
        p = os.path.join(root, name)
        if os.path.isfile(p):
            return p
    return None


def find_upward(start, name, limit=6):
    """The nearest `name` walking up from `start`'s directory; None past `limit` levels.

    Reports live under docs/daw/reports/, so the project root is a few levels
    up. Bounded, because an unbounded walk from /tmp finds someone else's file.
    """
    d = os.path.dirname(os.path.abspath(start))
    for _ in range(limit):
        cand = os.path.join(d, name)
        if os.path.isfile(cand):
            return cand
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent
    return None


def repo_root(artifact_path):
    """The repository the artifact belongs to, from its own path.

    Every phase artifact lives under `docs/daw/…`, so the segment before `docs/`
    is the root. Falls back to the working directory, which is what the
    validators did individually.
    """
    ab = os.path.abspath(artifact_path)
    for marker in (os.sep + "docs" + os.sep, os.sep + ".daw-work" + os.sep):
        idx = ab.rfind(marker)
        if idx > 0:
            return ab[:idx]
    return os.getcwd()


def digest_of(text):
    """The receipt's key: the artifact's CURRENT bytes, read as text.

    Text, not bytes, and the gate reads it the same way — the two disagreeing on
    `\\r\\n` alone made a Windows-authored report hash one way for the validator
    and another for the gate, and the refusal said "validate it again", which was
    a loop with no exit.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


# ── The OpenSpec change a spec names, sealed with it ─────────────────────────
#
# Under `spec-format: openspec` the what lives in an OpenSpec change and the
# spec writes only the how. Approving the spec approves both, so the receipt
# has to name both: hashing the spec alone let the change be rewritten after
# the approval with every gate still green. `sealed_text` is the one place that
# says what a spec's receipt covers, and the validator and the gate both call
# it — two copies of "what is sealed" is how they come to disagree.
#
# It goes by what the SPEC names, never by the config: switching the project
# back to `spec-format: daw` mid-ticket must not unseal a change already sealed.
OPENSPEC_LABEL = re.compile(r"^[ \t]*\*\*OpenSpec change:\*\*[ \t]*(.*?)[ \t]*$", re.M)
CHANGE_PATH = re.compile(r"^openspec/changes/([a-z0-9][a-z0-9-]*)/?$")
SEAL_MAX_FILES = 400
SEAL_MAX_BYTES = 2 * 1024 * 1024


class SealError(ValueError):
    """The change a spec names cannot be sealed, and this says why."""


def openspec_named(text):
    """Every value written after `**OpenSpec change:**`, backticks dropped."""
    return [m.group(1).strip().strip("`").strip() for m in OPENSPEC_LABEL.finditer(text)]


def openspec_change(text):
    """`openspec/changes/<name>` for the one change the spec names, or None.

    Raises SealError for two or more, or for a value that is not a change's
    path: a name like `../../x` never reaches the filesystem.
    """
    named = openspec_named(text)
    if not named:
        return None
    if len(named) > 1:
        raise SealError("the spec names %d OpenSpec changes; it names exactly one" % len(named))
    m = CHANGE_PATH.match(named[0])
    if not m:
        raise SealError("`%s` is not `openspec/changes/<name>` with a name of lowercase "
                        "letters, digits and hyphens" % named[0])
    return "openspec/changes/" + m.group(1)


def _inside(path, root):
    real, top = os.path.realpath(path), os.path.realpath(root)
    return real == top or real.startswith(top + os.sep)


def change_files(root, change):
    """The change's regular files as (repo-relative path, text), sorted.

    Fails closed: a missing folder, a symlink out of the repository, a file that
    is not UTF-8, or a folder past the caps is a SealError, never a pass.
    Symlinks that stay inside are not followed and not hashed — only regular
    files are what the change says.
    """
    folder = os.path.join(root, *change.split("/"))
    if os.path.islink(folder) or not os.path.isdir(folder):
        raise SealError("%s is not a folder in this repository" % change)
    if not _inside(folder, root):
        raise SealError("%s resolves outside the repository" % change)
    out, total = [], 0
    for base, dirs, files in os.walk(folder):
        dirs.sort()
        for name in list(dirs):
            p = os.path.join(base, name)
            if os.path.islink(p):
                if not _inside(p, root):
                    raise SealError("%s is a symlink out of the repository"
                                    % os.path.relpath(p, root))
                dirs.remove(name)
        for name in sorted(files):
            p = os.path.join(base, name)
            relp = os.path.relpath(p, root).replace(os.sep, "/")
            if os.path.islink(p):
                if not _inside(p, root):
                    raise SealError("%s is a symlink out of the repository" % relp)
                continue
            if not os.path.isfile(p):
                continue
            total += os.path.getsize(p)
            if len(out) >= SEAL_MAX_FILES or total > SEAL_MAX_BYTES:
                raise SealError("%s holds more than %d files or %d bytes, past what a "
                                "receipt seals" % (change, SEAL_MAX_FILES, SEAL_MAX_BYTES))
            try:
                with open(p, encoding="utf-8") as fh:
                    out.append((relp, fh.read()))
            except UnicodeDecodeError:
                raise SealError("%s is not UTF-8 text, so no receipt can name it" % relp)
    return out


def sealed_text(spec_path, text, root=None):
    """What a spec's receipt hashes: its text, and the change it names.

    A spec that names no change returns its text unchanged, so its digest is the
    one it always had and receipts already on disk stay valid. One that names a
    change gets every regular file under that folder appended in sorted order,
    `relpath\\0content\\0` each: edit, add or remove one and the digest moves.
    """
    change = openspec_change(text)
    if change is None:
        return text
    root = root or repo_root(spec_path)
    return text + "".join("%s\0%s\0" % (relp, body) for relp, body in change_files(root, change))


def write(artifact_path, prefix, text, tier=None, asof=None, openspec=None):
    """Write the receipt for `artifact_path` and record having written it.

    Returns the receipt's name, so the caller can print it.

    The receipt records WHICH RULES the document was judged under. Every
    validator takes `--tier`, and the tier decides which rules run: the same
    bytes that FAIL as a FEATURE PASS as a QUICK-FIX. Nothing recorded which one
    had been asked for, and the receipt's name is a digest of the content alone,
    so the two runs produced byte-identical receipts. Anyone could validate a
    FEATURE's PRD under QUICK-FIX rules, and the gate — which knows the state's
    tier perfectly well — had nothing to compare it to.

    A receipt with no tier line is one written before this existed, and it is
    still honoured; the gate only refuses a tier that is present and wrong.

    `asof` is the same argument for a different variable: the CLOCK. SAST
    suppressions expire, `validate_sast.py --today` lets the caller say which
    day to age them against, and nothing recorded the answer — so a report whose
    suppressions lapsed months ago passed under `--today 2025-02-01` and left a
    receipt indistinguishable from one earned this morning. Recorded here, the
    gate can ask; unrecorded, there was nothing to ask.
    """
    root = repo_root(artifact_path)
    name = "%s-validated-%s" % (prefix, digest_of(text))
    sess = os.path.join(root, SESSIONS)
    os.makedirs(sess, exist_ok=True)
    filename = os.path.basename(os.path.abspath(artifact_path))
    with open(os.path.join(sess, name), "w", encoding="utf-8") as fh:
        fh.write(filename + "\n")
        if tier:
            fh.write("tier: %s\n" % tier)
        if asof:
            fh.write("asof: %s\n" % asof)
        if openspec:
            fh.write("openspec: %s\n" % openspec)
    # Best effort, like every other write to the journal: a record that cannot be
    # kept must not stop a validation that passed. It costs the extra guarantee,
    # not the run.
    try:
        record = {"record": "receipt", "name": name, "file": filename}
        if tier:
            record["tier"] = tier
        if asof:
            record["asof"] = asof
        if openspec:
            record["openspec"] = openspec
        line = json.dumps(record, sort_keys=True)
        with open(os.path.join(root, JOURNAL), "a+", encoding="utf-8") as fh:
            # Re-validating unchanged bytes is legitimate and common — the same
            # digest, the same record. Twice in a row is noise the audit then
            # has to explain (measured: lines 48/49 of a live journal, identical
            # and consecutive, one validator run). Skip only the exact repeat of
            # the LAST line: a later re-validation after other records is a real
            # event and stays.
            fh.seek(0)
            tail = ""
            for tail in fh:
                pass
            if tail.strip() != line:
                fh.write(line + "\n")
    except OSError:
        pass
    return name
