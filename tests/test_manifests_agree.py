"""The manifests every tool reads agree on the plugin's name, version and
description (the ai-agent-plugin kind, DiluxOne/.github#552).

The check itself is the organisation's `scripts/agent-manifests.py`, the one
`make pre-pr` and the pull request's `plugin-checks-ai` run; there is no local
copy of it to drift. It is found in a checkout of DiluxOne/.github: DX_CENTRAL,
or `.dx-central` beside this repository, as `dx.mk` finds it. Where neither is
there (this repository's own `verify` workflow checks out nothing else) the
test says so and skips, and the pull request's check is the measurement.
"""
import json
import os
import shutil
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


def test_two_manifests_that_disagree_fail_and_are_named(tmp_path):
    # C2: a copy of the plugin whose Gemini manifest moved on its own.
    paths = shipped()
    assert "gemini-extension.json" in paths
    for rel in paths:
        dest = tmp_path / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(os.path.join(ROOT, rel), dest)
    gemini = tmp_path / "gemini-extension.json"
    data = json.loads(gemini.read_text(encoding="utf-8"))
    data["version"] = data["version"] + "-drifted"
    gemini.write_text(json.dumps(data), encoding="utf-8")

    out = manifests("check", str(tmp_path))
    assert out.returncode != 0, "a version only one manifest says passed the check"
    report = out.stdout + out.stderr
    lines = [l for l in report.splitlines() if "gemini-extension.json" in l and "version" in l]
    assert lines, report
    # Every other manifest is named against it, on the same line.
    for rel in paths:
        if rel != "gemini-extension.json":
            assert any(rel in l for l in lines), "%s is not named beside the drifted file:\n%s" % (rel, report)
