"""The manifests every tool reads agree on the plugin's name, version and
description (the ai-agent-plugin kind, DiluxOne/.github#552).

The check itself is the organisation's `scripts/agent-manifests.py`, the one
`make pre-pr` and the pull request's `plugin-checks-ai` run; there is no local
copy of it to drift. It is found in a checkout of DiluxOne/.github: DX_CENTRAL,
or `.dx-central` beside this repository, as `dx.mk` finds it. Where neither is
there (this repository's own `verify` workflow checks out nothing else) the
test says so and skips, and the pull request's check is the measurement.
"""
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CENTRAL = os.environ.get("DX_CENTRAL") or os.path.join(ROOT, ".dx-central")
SCRIPT = os.path.join(CENTRAL, "scripts", "agent-manifests.py")

if not os.path.isfile(SCRIPT):
    pytest.skip("no checkout of DiluxOne/.github (DX_CENTRAL): agent-manifests.py "
                "is not here to ask", allow_module_level=True)


def manifests(*args):
    return subprocess.run([sys.executable, SCRIPT, *args],
                          capture_output=True, text=True, timeout=60)


def shipped():
    """The manifest of every tool the kind knows that this plugin ships."""
    out = manifests("tools")
    assert out.returncode == 0, out.stderr
    paths = [line.split("\t")[1] for line in out.stdout.splitlines() if line.strip()]
    return [p for p in paths if p != "-" and os.path.isfile(os.path.join(ROOT, p))]


def test_the_kind_reads_the_manifests_of_this_plugin():
    # C1: the pack is valid, and this repository is a plugin of it. A tools.yml
    # the script refuses, or a plugin it finds no manifest in, fails here.
    out = manifests("check", ROOT)
    assert out.returncode == 0, out.stdout + out.stderr
    assert len(shipped()) >= 2, "the check compared fewer than two manifests: it compared nothing"

