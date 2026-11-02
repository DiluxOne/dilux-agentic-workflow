"""An issue opened here enters the organisation's flow (DiluxOne/.github#552).

`.github/workflows/issues.yml` is the caller of the organisation's issue
workflows: the triage labels an issue when it opens, and the acceptance puts
it on the board, which starts the autopilot. This asks the caller itself, and,
where a checkout of DiluxOne/.github is at hand (DX_CENTRAL, or `.dx-central`
beside this repository, as `dx.mk` finds it), the organisation's own drift
check (`sync-repos.py callers`) for the jobs it calls. The full drift check,
wording and triggers included, is the organisation's daily run: a template that
moves there is brought here by its own pull request, not by this test.
"""
import importlib.util
import os
import sys

import pytest

yaml = pytest.importorskip("yaml")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CENTRAL = os.environ.get("DX_CENTRAL") or os.path.join(ROOT, ".dx-central")
WORKFLOWS = os.path.join(ROOT, ".github", "workflows")
SHARED = "DiluxOne/.github/.github/workflows/"


def caller():
    with open(os.path.join(WORKFLOWS, "issues.yml"), encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def triggers(data):
    # PyYAML reads the key `on` as True.
    return data.get("on", data.get(True)) or {}


def test_an_opened_issue_is_triaged_and_an_accepted_one_reaches_the_board():
    data = caller()
    issues = triggers(data).get("issues") or {}
    assert {"opened", "labeled"} <= set(issues.get("types") or []), issues
    jobs = data["jobs"]
    calls = {name: str(job.get("uses", "")) for name, job in jobs.items()}
    assert calls["triage"].startswith(SHARED + "issue-triage.yml@"), calls
    assert jobs["triage"]["permissions"].get("issues") == "write"
    assert calls["accepted"].startswith(SHARED + "issue-accepted.yml@"), calls
    # The acceptance acts as dilux-bot: without its key nothing lands on the
    # board and the autopilot never starts.
    assert "DILUX_BOT_PRIVATE_KEY" in (jobs["accepted"].get("secrets") or {})
    assert calls["claim"].startswith(SHARED + "issue-claim.yml@"), calls


def sync_repos():
    script = os.path.join(CENTRAL, "scripts", "sync-repos.py")
    if not os.path.isfile(script):
        pytest.skip("no checkout of DiluxOne/.github (DX_CENTRAL): sync-repos.py is not here to ask")
    spec = importlib.util.spec_from_file_location("sync_repos", script)
    module = importlib.util.module_from_spec(spec)
    argv, sys.argv = sys.argv, [script]
    try:
        spec.loader.exec_module(module)
    finally:
        sys.argv = argv
    return module


def test_the_callers_call_every_job_of_the_organisations_templates():
    sync = sync_repos()
    conf = sync.load_yaml(os.path.join(CENTRAL, "repos.yml"))
    files = {}
    for name in sorted(os.listdir(WORKFLOWS)):
        if name.endswith((".yml", ".yaml")):
            with open(os.path.join(WORKFLOWS, name), encoding="utf-8") as fh:
                files[".github/workflows/" + name] = fh.read()
    missing = [(template, phrase)
               for template, _path, phrases in sync.callers_drift(files, conf)
               for phrase in phrases
               if phrase.startswith(("has no caller", "lacks the job"))
               or " calls `" in phrase]
    assert not missing, missing
