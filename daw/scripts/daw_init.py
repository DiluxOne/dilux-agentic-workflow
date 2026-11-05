#!/usr/bin/env python3
"""daw-init, the mechanical half: writes `.daw/config.yml`, and asks nothing.

The skill (`skills/daw-init/SKILL.md`) talks to the person; this does the work,
deterministically, and is what the tests call — the same split as
`daw-family-impact` and `family_impact.py`.

    daw_init.py --repo . --spec-format daw|openspec [--force]

It writes only inside the repository, and only `.daw/config.yml`. What it wrote
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
    ap.add_argument("--spec-format", choices=FORMATS, required=True)
    ap.add_argument("--force", action="store_true",
                    help="replace an existing .daw/config.yml")
    args = ap.parse_args()
    repo = os.path.abspath(args.repo)
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
