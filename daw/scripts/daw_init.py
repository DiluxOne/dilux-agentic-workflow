#!/usr/bin/env python3
"""daw-init, the mechanical half: writes `.daw/config.yml`, and asks nothing.

The skill (`skills/daw-init/SKILL.md`) talks to the person; this does the work,
deterministically, and is what the tests call — the same split as
`daw-family-impact` and `family_impact.py`.

    daw_init.py --repo . --detect                          # prints the proposal
    daw_init.py --repo . --spec-format daw|openspec [--force]

`--detect` proposes `openspec` when the repository already has an `openspec/`
folder, and `daw` otherwise. It is a proposal: the person answers.

Choosing `openspec` in a repository with no `openspec/` creates OpenSpec's
layout — `openspec/project.md`, `openspec/specs/`, `openspec/changes/` — so the
first change has somewhere to go. Offline and deterministic: no `npx`, no
network. An `openspec/` that exists, in any shape, is never touched.

It writes only inside the repository: `.daw/config.yml`, and `openspec/` when
it creates one. What it wrote
is read back through `daw_config`, the one reader, so a file this leaves behind
is one the schema accepts. An existing config is never overwritten without
`--force`, and never while a ticket is running: the settings decide which rules
the ticket is held to, and they do not change under it.

Exit: 0 = written · 1 = refused (nothing written) · 2 = what was written does
not validate.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import daw_config  # noqa: E402 — same directory, resolved above

FORMATS = ("daw", "openspec")
HEADER = ("# DAW's settings for this project, validated against daw/config.schema.json.\n"
          "# Written by /daw-init; edit it between tickets, never during one.\n")


class Refused(Exception):
    """Nothing was written, and this says why."""


def _inside(repo, path):
    """`path` resolves inside `repo`: no symlink carries a write out of it."""
    real, root = os.path.realpath(path), os.path.realpath(repo)
    return real == root or real.startswith(root + os.sep)


def _phase(repo):
    """The pipeline's phase, IDLE when nothing has started, None when unreadable."""
    path = os.path.join(repo, ".daw-state.json")
    if not os.path.exists(path):
        return "IDLE"
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return (data.get("phase") or "IDLE") if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def detect(repo):
    """The format to propose: `openspec` where an `openspec/` folder exists."""
    return "openspec" if os.path.isdir(os.path.join(repo, "openspec")) else "daw"


PROJECT_MD = """# Project context

What every OpenSpec change in this repository can assume. Fill it in once; the
changes under `changes/` describe what each one adds, and `specs/` holds what
the project already does.

## Purpose

## Tech stack

## Conventions
"""
KEEP = "# Kept so git keeps the folder. OpenSpec writes here.\n"


def scaffold_openspec(repo):
    """OpenSpec's layout, when the repository has none. Returns what it made.

    Anything already named `openspec` — a folder, a file, a symlink — is left
    exactly as it is, and nothing is made.
    """
    base = os.path.join(repo, "openspec")
    if os.path.lexists(base):
        return []
    made = []
    for sub in ("specs", "changes"):
        os.makedirs(os.path.join(base, sub))
        with open(os.path.join(base, sub, ".gitkeep"), "w", encoding="utf-8") as fh:
            fh.write(KEEP)
        made.append("openspec/%s/" % sub)
    with open(os.path.join(base, "project.md"), "w", encoding="utf-8") as fh:
        fh.write(PROJECT_MD)
    made.insert(0, "openspec/project.md")
    return made


def render(spec_format):
    return HEADER + "version: 1\nspec-format: %s\n" % spec_format


def write_config(repo, spec_format, force=False):
    """Write `.daw/config.yml` and read it back. Returns its path."""
    if spec_format not in FORMATS:
        raise Refused("spec-format must be one of %s" % ", ".join(FORMATS))
    if not os.path.isdir(repo):
        raise Refused("%s is not a directory" % repo)
    phase = _phase(repo)
    if phase != "IDLE":
        raise Refused("the pipeline is in %s, not IDLE: a ticket's settings do not change "
                      "under it. Finish or pause the ticket, then run this again"
                      % (phase or "an unreadable state"))
    folder = os.path.join(repo, ".daw")
    path = os.path.join(repo, daw_config.CONFIG)
    for p in (folder, path):
        if os.path.lexists(p) and (os.path.islink(p) or not _inside(repo, p)):
            raise Refused("%s is a symlink; the settings are written in the repository itself"
                          % os.path.relpath(p, repo))
    if os.path.lexists(path) and not force:
        raise Refused("%s already exists; pass --force to replace it" % daw_config.CONFIG)
    os.makedirs(folder, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(render(spec_format))
    os.replace(tmp, path)
    return path


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--repo", default=".")
    what = ap.add_mutually_exclusive_group(required=True)
    what.add_argument("--detect", action="store_true",
                      help="print the spec format to propose, and write nothing")
    what.add_argument("--spec-format", choices=FORMATS)
    ap.add_argument("--force", action="store_true",
                    help="replace an existing .daw/config.yml")
    args = ap.parse_args()
    repo = os.path.abspath(args.repo)
    if args.detect:
        print(detect(repo))
        return 0
    try:
        write_config(repo, args.spec_format, args.force)
    except (Refused, OSError) as why:
        print("daw_init: nothing written: %s" % why, file=sys.stderr)
        return 1
    try:
        data = daw_config.load(repo)
    except daw_config.Invalid as why:
        print("daw_init: wrote %s and it does not validate: %s" % (daw_config.CONFIG, why),
              file=sys.stderr)
        return 2
    print("Wrote %s: spec-format: %s" % (daw_config.CONFIG, data["spec-format"]))
    if data["spec-format"] == "openspec":
        try:
            made = scaffold_openspec(repo)
        except OSError as why:
            print("daw_init: could not create openspec/: %s" % why, file=sys.stderr)
            return 1
        if made:
            print("Created OpenSpec's layout, ready for a first change: %s" % ", ".join(made))
        else:
            print("openspec/ is already here: left as it is.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
