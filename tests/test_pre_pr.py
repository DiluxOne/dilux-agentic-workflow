"""`make pre-pr` runs the pull request's suites, in their order, and stops at
the first failure (DiluxOne/.github#552).

The commands are read from the workflows themselves, so a step added to
verify.yml or mutations.yml and not to the Makefile fails here. What CI alone
runs is named and left out: the mutation slice of the change (`mutations`, one
full run of the suite per fault: over two hours on one machine for a change to
the validators, longer than an autopilot run, #78; CI runs it in 96 shards,
required before a merge), and the kill map with its ledger (2.5 hours on one
machine; mutations.yml says why).
"""
import os
import re
import shutil
import subprocess

import pytest

yaml = pytest.importorskip("yaml")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOWS = os.path.join(ROOT, ".github", "workflows")
CI_ONLY_JOBS = {"mutations", "kill-map", "kill-map-ledger"}
COMMAND = re.compile(r"^(python3|bash) ((?:scripts|evals)/\S+)(.*)$")

if not shutil.which("make"):
    pytest.skip("make is not installed", allow_module_level=True)


def shape(line):
    """A command as (script, its flags): the values are the runner's (a ref,
    a shard), the flags are what the step asks."""
    m = COMMAND.match(line.strip())
    if not m:
        return None
    flags = [t for t in m.group(3).split() if t.startswith("--") and t != "--shard"]
    return (m.group(2), tuple(flags))


def run_lines(script):
    """The lines a step runs, its pull request branch only: in `if [ ... ];
    then A; else B; fi`, what a pull request runs is A."""
    out = []
    for line in script.splitlines():
        line = line.split(" #", 1)[0].strip()
        if line.startswith(("elif", "else")):
            break
        out.append(line)
    return out


def workflow_commands(name):
    with open(os.path.join(WORKFLOWS, name), encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    found = []
    for job, body in data["jobs"].items():
        if job in CI_ONLY_JOBS:
            continue
        for step in body.get("steps") or []:
            for line in run_lines(step.get("run") or ""):
                if (s := shape(line)) and s not in found:
                    found.append(s)
    return found


def triggers(name):
    with open(os.path.join(WORKFLOWS, name), encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data.get("on", data.get(True)) or {}


def make_commands():
    out = subprocess.run(["make", "-n", "pre-pr"], cwd=ROOT, capture_output=True,
                         text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return [s for line in out.stdout.splitlines() if (s := shape(line))]


def test_pre_pr_runs_the_pull_requests_suites_in_their_order():
    want = workflow_commands("verify.yml") + workflow_commands("mutations.yml")
    assert len(want) >= 9, want
    have = [s for s in make_commands() if s in want]
    assert have == want, "make -n pre-pr:\n  %s\nthe workflows:\n  %s" % (have, want)


# A workflow change, which the autopilot cannot push: the maintainer pushes the
# `merge_group: [checks_requested]` trigger of both to this pull request (#65),
# and removes this marker with it. Strict, so the marker cannot outlive it.
def test_the_merge_queue_runs_the_same_suites():
    for name in ("verify.yml", "mutations.yml"):
        assert "merge_group" in triggers(name), "%s does not run in the merge queue" % name


def test_the_first_failure_stops_it(tmp_path):
    # The Makefile over stand-ins of every script: each says it ran, and the
    # first one fails.
    for name in ("Makefile", "dx.mk"):
        shutil.copyfile(os.path.join(ROOT, name), tmp_path / name)
    log = tmp_path / "ran.log"
    for script, _flags in make_commands():
        path = tmp_path / script
        path.parent.mkdir(parents=True, exist_ok=True)
        fail = "exit 1" if script == "scripts/lint_method.py" else ""
        if script.endswith(".py"):
            fail = "raise SystemExit(1)" if fail else ""
            path.write_text("open(%r, 'a').write(%r + '\\n')\n%s\n" % (str(log), script, fail))
        else:
            path.write_text("echo %s >> %s\n%s\n" % (script, log, fail))
    out = subprocess.run(["make", "pre-pr"], cwd=tmp_path, capture_output=True, text=True, timeout=60)
    assert out.returncode != 0
    assert log.read_text().split() == ["scripts/lint_method.py"], log.read_text()
