"""The product has one name (DiluxOne/dilux-agentic-workflow#60).

Its former one is kept in two places only: the migration that reads a project's
old files (with its test), and the CHANGELOG's history. Anywhere else, a file
that still says it is a file the rename missed. The pattern is written so this
file does not match it.
"""
import os
import re
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORMER = "d[d]w"
ALLOWED = {"daw/scripts/migrate_legacy.py", "tests/test_migrate_legacy.py", "CHANGELOG.md"}
# A workflow file, which the autopilot cannot push: a maintainer renames it in
# this pull request (#65) and removes it from here with it.
PENDING = {".github/workflows/behavioral.yml"}


def git(*args):
    return subprocess.run(["git", "-C", ROOT, *args], capture_output=True, text=True, timeout=60)


def tracked():
    if git("rev-parse", "--is-inside-work-tree").returncode != 0:
        pytest.skip("not a git checkout")
    return set(git("ls-files").stdout.split())


def test_the_former_name_is_only_where_it_is_read():
    files = tracked()
    out = git("grep", "-I", "-l", "-i", "-E", FORMER)
    found = set(out.stdout.split())
    assert not found - ALLOWED - PENDING, sorted(found - ALLOWED - PENDING)
    paths = sorted(p for p in files if re.search(FORMER, p, re.I))
    assert not paths, paths


def test_and_the_changelog_keeps_it_in_its_history_only():
    text = open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8").read()
    head, _sep, _history = text.partition("\n## [")
    assert not re.search(FORMER, head, re.I), "the CHANGELOG's preamble still says the former name"


@pytest.mark.xfail(strict=True, reason="behavioral.yml is renamed by a maintainer (#65)")
def test_the_workflows_say_the_new_name():
    out = git("grep", "-I", "-l", "-i", "-E", FORMER, "--", *sorted(PENDING))
    assert not out.stdout.strip(), out.stdout
