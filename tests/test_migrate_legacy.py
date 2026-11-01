"""A project set up under the product's former name keeps working under DAW's
(DiluxOne/dilux-agentic-workflow#60).

The fixture is a real pipeline: built with today's tools (a FEATURE ticket in
DEFINE whose `define` gate was earned with a receipt, a paused ticket, the
journal, the markers, an install record), then aged into the former names the
way the old plugin wrote them. This file writes those names itself rather than
asking the migration for them, so the two cannot agree on a mistake. After the
migration the gates are asked, not the files: `transition.py` and `hook-gate.py`
accept the step to PLAN, on the receipt the project earned before.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "daw", "scripts")
GRAPH = os.path.join(ROOT, "daw", "rules", "transition-graph.json")
TICKET = "FEAT-1"


def run(script, *args, cwd, stdin=None):
    return subprocess.run([sys.executable, os.path.join(SCRIPTS, script), *args], cwd=cwd,
                          input=stdin, capture_output=True, text=True, timeout=120)


def transition(repo, *args):
    return run("transition.py", "--state", ".daw-state.json", "--graph", GRAPH, *args, cwd=repo)


def receipt(repo, rel, prefix, text, tier="FEATURE", sessions=".daw-sessions",
            journal=".daw-journal.jsonl", witnessed=True):
    """A receipt as a validator writes it: the file, and the journal's line."""
    name = "%s-validated-%s" % (prefix, hashlib.sha256(text.encode("utf-8")).hexdigest()[:12])
    os.makedirs(os.path.join(repo, sessions), exist_ok=True)
    with open(os.path.join(repo, sessions, name), "w", encoding="utf-8") as fh:
        fh.write("%s\ntier: %s\n" % (os.path.basename(rel), tier))
    if witnessed:
        with open(os.path.join(repo, journal), "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"record": "receipt", "name": name, "file": os.path.basename(rel),
                                 "tier": tier}, sort_keys=True) + "\n")
    return name


def write(repo, rel, text):
    path = os.path.join(repo, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def read(repo, rel):
    with open(os.path.join(repo, rel), encoding="utf-8") as fh:
        return fh.read()


def pipeline(repo):
    """A ticket at DEFINE whose define gate was earned, built with today's tools."""
    subprocess.run(["git", "init", "-q", repo], check=True)
    assert transition(repo, "--to", "CLASSIFY", "--action", "start", "--write").returncode == 0
    write(repo, ".daw-work/context-check-%s.md" % TICKET,
          "Nothing to report: the context file matches the repo.\n")
    out = transition(repo, "--to", "DEFINE", "--tier", "FEATURE", "--ticket", TICKET,
                     "--title", "a ticket", "--action", "classified", "--write")
    assert out.returncode == 0, out.stderr
    prd = "docs/daw/prd/prd-%s.md" % TICKET
    write(repo, prd, "# PRD %s\n\nWhat it is for.\n" % TICKET)
    receipt(repo, prd, "prd", read(repo, prd))
    out = transition(repo, "--claim", "define", "--write")
    assert out.returncode == 0, out.stderr


def age(repo):
    """The project as the former name left it: every path and every word of
    DAW's moved back to it. The PRD carries no name, so its receipt holds."""
    def back(text):
        return text.replace("daw", "ddw").replace("DAW", "DDW")

    for base, dirs, files in os.walk(repo, topdown=False):
        if os.sep + ".git" in base + os.sep:
            continue
        for name in files:
            path = os.path.join(base, name)
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(back(text))
        for name in files + dirs:
            if "daw" in name and name != ".git":
                os.rename(os.path.join(base, name), os.path.join(base, back(name)))


def legacy_project(repo):
    pipeline(repo)
    # A paused ticket, a store page with managed markers and its receipt, the
    # context block, the .gitignore block, and what an older installer recorded.
    write(repo, ".daw-paused/FEAT-0.json", json.dumps({"phase": "PLAN", "tier": "FIX",
                                                        "ticket": "FEAT-0", "gates": {"define": True}}))
    write(repo, "AGENTS.md", "# Project\n\nOur own words.\n\n<!-- BEGIN DAW (managed by DAW) -->\n"
                             "Read .daw/orchestrator.md\n<!-- END DAW -->\n")
    write(repo, ".gitignore", "node_modules/\n# BEGIN DAW — runtime\n.daw-state.json\n.daw-paused/\n"
                              ".daw-sessions/\n.daw-work/\n.daw-journal.jsonl\n# END DAW\n")
    write(repo, ".codex/hooks/daw/session-start.sh", "#!/bin/sh\necho start\n")
    write(repo, ".claude/skills/daw-status/SKILL.md", "---\nname: daw-status\n---\nStatus.\n")
    hook = 'bash "$(git rev-parse --show-toplevel)/.codex/hooks/daw/session-start.sh"'
    mine = "bash ./scripts/my-own-hook.sh"
    write(repo, ".codex/hooks.json", json.dumps({"hooks": {"SessionStart": [
        {"hooks": [{"type": "command", "command": hook}]},
        {"hooks": [{"type": "command", "command": mine}]}]}}, indent=2))
    write(repo, ".daw-installed.json", json.dumps({
        "codex:.codex/hooks/daw/session-start.sh": "x",
        "claude:.claude/skills/daw-status": "y"}, indent=2))
    age(repo)
    # The store page and its receipt, on the bytes the former name wrote.
    store = "docs/ddw/store/renglones.md"
    write(repo, store, "# Store\n\n<!-- BEGIN DDW ROWS -->\n| a | b |\n<!-- END DDW ROWS -->\n")
    receipt(repo, store, "store", read(repo, store), sessions=".ddw-sessions",
            journal=".ddw-journal.jsonl")
    # And a receipt nobody's validator wrote, for a page the move rewrites.
    forged = "docs/ddw/store/forged.md"
    write(repo, forged, "<!-- BEGIN DDW FICHA -->\nx\n<!-- END DDW FICHA -->\n")
    receipt(repo, forged, "store", read(repo, forged), sessions=".ddw-sessions", witnessed=False)
    return hook, mine


def snapshot(repo):
    out = {}
    for base, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__")]
        for name in files:
            path = os.path.join(base, name)
            with open(path, "rb") as fh:
                out[os.path.relpath(path, repo)] = fh.read()
    return out


def former(repo):
    return sorted(p for p in snapshot(repo) if "ddw" in p.lower())


def migrate(repo):
    return run("migrate_legacy.py", "--repo", repo, cwd=repo)


@pytest.fixture()
def project(tmp_path):
    repo = str(tmp_path / "project")
    os.makedirs(repo)
    hooks = legacy_project(repo)
    assert os.path.isfile(os.path.join(repo, ".ddw-state.json"))
    return repo, hooks


def test_the_project_keeps_its_phase_and_its_gates(project):
    repo, _hooks = project
    out = migrate(repo)
    assert out.returncode == 0, out.stderr
    assert former(repo) == [], former(repo)
    state = json.loads(read(repo, ".daw-state.json"))
    assert (state["phase"], state["tier"], state["ticket"], state["gates"]) == \
        ("DEFINE", "FEATURE", TICKET, {"define": True})
    # The gate is asked: the step to PLAN is taken on the receipt earned before.
    step = transition(repo, "--to", "PLAN", "--action", "to plan")
    assert step.returncode == 0, step.stderr
    event = {"hook_event_name": "PreToolUse", "tool_name": "Write", "cwd": repo,
             "tool_input": {"file_path": os.path.join(repo, ".daw-state.json"), "content": step.stdout}}
    gate = run("hook-gate.py", "--mode", "pre", "--state", ".daw-state.json", "--graph", GRAPH,
               "--repo", repo, "--method", os.path.join(ROOT, "daw"), cwd=repo, stdin=json.dumps(event))
    assert gate.returncode == 0, gate.stdout + gate.stderr


def test_the_gate_would_refuse_without_what_was_moved(project):
    # The control: the same step, with the receipts gone, is refused. Without
    # it the test above could pass on a gate that asks nothing.
    repo, _hooks = project
    assert migrate(repo).returncode == 0
    shutil.rmtree(os.path.join(repo, ".daw-sessions"))
    step = transition(repo, "--to", "PLAN", "--action", "to plan")
    event = {"hook_event_name": "PreToolUse", "tool_name": "Write", "cwd": repo,
             "tool_input": {"file_path": os.path.join(repo, ".daw-state.json"),
                            "content": step.stdout or read(repo, ".daw-state.json").replace('"DEFINE"', '"PLAN"', 1)}}
    gate = run("hook-gate.py", "--mode", "pre", "--state", ".daw-state.json", "--graph", GRAPH,
               "--repo", repo, "--method", os.path.join(ROOT, "daw"), cwd=repo, stdin=json.dumps(event))
    assert step.returncode != 0 or gate.returncode != 0


def test_what_else_moves_and_what_stays(project):
    repo, (hook, mine) = project
    paused = read(repo, ".ddw-paused/FEAT-0.json")
    assert migrate(repo).returncode == 0
    assert read(repo, ".daw-paused/FEAT-0.json") == paused
    assert "BEGIN DAW" in read(repo, "AGENTS.md") and "Our own words." in read(repo, "AGENTS.md")
    assert ".daw-state.json" in read(repo, ".gitignore") and "node_modules/" in read(repo, ".gitignore")
    commands = [h["command"] for b in json.loads(read(repo, ".codex/hooks.json"))["hooks"]["SessionStart"]
                for h in b["hooks"]]
    assert commands == [hook.replace("ddw", "daw"), mine]
    assert os.path.isfile(os.path.join(repo, ".codex/hooks/daw/session-start.sh"))
    assert os.path.isfile(os.path.join(repo, ".claude/skills/daw-status/SKILL.md"))
    assert sorted(json.loads(read(repo, ".daw-installed.json"))) == \
        ["claude:.claude/skills/daw-status", "codex:.codex/hooks/daw/session-start.sh"]
    journal = [json.loads(l) for l in read(repo, ".daw-journal.jsonl").splitlines()]
    assert journal[-1]["record"] == "notice" and "former name" in journal[-1]["note"]


def test_a_rewritten_page_keeps_a_receipt_a_validator_wrote_and_no_other(project):
    repo, _hooks = project
    assert migrate(repo).returncode == 0
    sessions = os.listdir(os.path.join(repo, ".daw-sessions"))
    witnessed = {e.get("name") for e in map(json.loads, read(repo, ".daw-journal.jsonl").splitlines())
                 if e.get("record") == "receipt"}
    for page, should in (("renglones.md", True), ("forged.md", False)):
        text = read(repo, "docs/daw/store/" + page)
        assert "DDW" not in text
        name = "store-validated-" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
        assert (name in sessions and name in witnessed) is should, (page, sessions)


def test_running_it_again_changes_nothing(project):
    repo, _hooks = project
    assert migrate(repo).returncode == 0
    before = snapshot(repo)
    again = migrate(repo)
    assert again.returncode == 0 and again.stdout == ""
    assert snapshot(repo) == before


def test_both_names_present_refuses_and_changes_nothing(project):
    repo, _hooks = project
    write(repo, ".daw-state.json", json.dumps({"phase": "IDLE", "gates": {}}))
    before = snapshot(repo)
    out = migrate(repo)
    assert out.returncode == 3
    assert ".ddw-state.json and .daw-state.json" in out.stderr
    assert snapshot(repo) == before


def test_the_plugins_session_start_moves_it(project):
    repo, _hooks = project
    out = run("session-boot.py", "--repo", repo, "--method", os.path.join(ROOT, "daw"), cwd=repo)
    assert out.returncode == 0, out.stderr
    assert "former name" in out.stdout
    assert former(repo) == [] and json.loads(read(repo, ".daw-state.json"))["gates"] == {"define": True}


def test_a_copied_in_method_is_left_to_the_installer(project):
    repo, _hooks = project
    write(repo, ".ddw/orchestrator.md", "the old copy\n")
    before = snapshot(repo)
    out = run("session-boot.py", "--repo", repo, "--method", os.path.join(ROOT, "daw"), cwd=repo)
    assert "install.sh" in out.stdout
    assert snapshot(repo) == before


@pytest.mark.skipif(not shutil.which("bash"), reason="bash is not installed")
def test_the_installer_moves_it_before_it_upgrades(project):
    repo, _hooks = project
    out = subprocess.run(["bash", os.path.join(ROOT, "install.sh"), repo, "--target", "claude"],
                         capture_output=True, text=True, timeout=300, stdin=subprocess.DEVNULL)
    assert out.returncode == 0, out.stdout[-2000:] + out.stderr[-2000:]
    assert former(repo) == [], former(repo)
    assert os.path.isfile(os.path.join(repo, ".daw", "orchestrator.md")), "nothing was installed"
    state = json.loads(read(repo, ".daw-state.json"))
    assert (state["phase"], state["gates"]) == ("DEFINE", {"define": True})
    assert transition(repo, "--to", "PLAN", "--action", "to plan").returncode == 0
