"""A project's DAW settings, `.daw/config.yml`, and `/daw-init`, which writes them.

What the settings promise is small and has to hold exactly: one reader that
validates against `daw/config.schema.json`, a missing file read as today's
flow, an invalid one refused rather than read as the default, and a boot that
offers `/daw-init` once and stops when it is declined.
"""
import importlib.util
import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "daw", "scripts")
INIT = os.path.join(SCRIPTS, "daw_init.py")
BOOT = os.path.join(SCRIPTS, "session-boot.py")


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


daw_config = _load("daw_config", "daw/scripts/daw_config.py")
vt = _load("vt_config", "daw/scripts/validate-transition.py")


def init(repo, *args):
    return subprocess.run([sys.executable, INIT, "--repo", str(repo), *args],
                          capture_output=True, text=True)


def boot(repo):
    """The session boot as a plugin runs it: the method outside the repo."""
    out = subprocess.run([sys.executable, BOOT, "--repo", str(repo),
                          "--method", os.path.join(ROOT, "daw")],
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return out.stdout


@pytest.fixture()
def repo(tmp_path):
    r = tmp_path / "proj"
    r.mkdir()
    (r / "AGENTS.md").write_text("# Proj\n\n## Stack\n- Python\n")
    return r


# ── C1: the offer at boot ─────────────────────────────────────────────────────

def test_boot_without_a_config_offers_daw_init(repo):
    said = boot(repo)
    assert "/daw-init" in said and "no .daw/config.yml" in said, \
        f"a project with no settings was not offered /daw-init: {said[:300]}"
    assert "keeps today's flow" in said, "the offer does not say skipping it changes nothing"


def test_a_declined_offer_stays_quiet(repo):
    (repo / "AGENTS.md").write_text("# Proj\n\n<!-- daw:declined init daw-init -->\n")
    said = boot(repo)
    assert "/daw-init" not in said, f"a declined offer was made again: {said[:300]}"
    assert "context recommendation" not in said, \
        "the init decline is reported as a context recommendation, which it is not"


def test_a_project_with_a_config_is_not_offered_init(repo):
    assert init(repo, "--spec-format", "daw").returncode == 0
    assert "/daw-init" not in boot(repo)


def test_an_invalid_config_is_reported_at_boot_with_its_reason(repo):
    (repo / ".daw").mkdir()
    (repo / ".daw" / "config.yml").write_text("version: 1\nspec-format: markdown\n")
    said = boot(repo)
    assert ".daw/config.yml is invalid" in said and "markdown" in said, said[:400]


def test_a_dot_daw_holding_only_the_config_is_not_a_dropin(repo):
    """Under a plugin `.daw/` may hold nothing but the project's settings. Read
    as "DAW is copied in", the boot warned that the install manifest was gone."""
    assert init(repo, "--spec-format", "daw").returncode == 0
    boot_mod = _load("boot_cfg", "daw/scripts/session-boot.py")
    assert boot_mod.enforcement_drift(str(repo)) == []
    said = boot(repo)
    assert "MISSING" not in said and "comes from a plugin" in said, said[:400]


# ── C1: daw_init.py writes a file the schema accepts ──────────────────────────

@pytest.mark.parametrize("fmt", ["daw", "openspec"])
def test_init_writes_a_config_that_passes_its_schema(repo, fmt):
    out = init(repo, "--spec-format", fmt)
    assert out.returncode == 0, out.stderr
    path = repo / ".daw" / "config.yml"
    data = daw_config.parse(path.read_text())
    assert daw_config.validate(data, json.load(open(daw_config.SCHEMA))) == []
    assert daw_config.load(str(repo)) == {"version": 1, "spec-format": fmt}
    assert daw_config.spec_format(str(repo)) == fmt


def test_init_never_replaces_a_config_without_force(repo):
    assert init(repo, "--spec-format", "daw").returncode == 0
    before = (repo / ".daw" / "config.yml").read_text()
    out = init(repo, "--spec-format", "openspec")
    assert out.returncode == 1 and "--force" in out.stderr
    assert (repo / ".daw" / "config.yml").read_text() == before
    assert init(repo, "--spec-format", "openspec", "--force").returncode == 0
    assert daw_config.spec_format(str(repo)) == "openspec"


def test_init_refuses_while_a_ticket_is_running(repo):
    (repo / ".daw-state.json").write_text(json.dumps({"phase": "PLAN", "tier": "FEATURE"}))
    out = init(repo, "--spec-format", "openspec")
    assert out.returncode == 1 and "PLAN" in out.stderr
    assert not (repo / ".daw" / "config.yml").exists()


def test_init_does_not_write_through_a_symlink(repo, tmp_path):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    os.symlink(elsewhere, repo / ".daw")
    assert init(repo, "--spec-format", "daw").returncode == 1
    assert not (elsewhere / "config.yml").exists()


def test_no_config_is_todays_flow(repo):
    assert daw_config.load(str(repo)) is None
    assert daw_config.spec_format(str(repo)) == "daw"


# ── C1: an invalid file is refused, never read as the default ─────────────────

@pytest.mark.parametrize("text,why", [
    ("spec-format: daw\n", "`version` is required"),
    ("version: 2\n", "`version` must be 1"),
    ("version: '1'\n", "`version` must be 1"),
    ("version: 1\nspec-format: markdown\n", "must be one of"),
    ("version: 1\nformat: daw\n", "is not a setting"),
    ("version: 1\nversion: 1\n", "written twice"),
    ("version: 1\nspec-format:\n  kind: daw\n", "no value"),
    ("version: 1\nspec-format: &a daw\n", "does not read"),
    ("version: 1\nspec-format: [daw]\n", "does not read"),
    ("version: 1\nspec-format: 'daw\n", "never closed"),
    ("just words\n", "expected `key: value`"),
])
def test_an_invalid_config_is_refused(repo, text, why):
    (repo / ".daw").mkdir()
    (repo / ".daw" / "config.yml").write_text(text)
    with pytest.raises(daw_config.Invalid) as exc:
        daw_config.spec_format(str(repo))
    assert why in str(exc.value), str(exc.value)


def test_comments_and_quotes_are_read(repo):
    (repo / ".daw").mkdir()
    (repo / ".daw" / "config.yml").write_text(
        "# settings\nversion: 1  # the format\nspec-format: \"openspec\"  # why\n")
    assert daw_config.spec_format(str(repo)) == "openspec"


# ── C1: who may write it (the gate's carve-out) ───────────────────────────────

def test_the_config_is_writable_at_idle_and_sealed_once_a_ticket_runs(repo):
    root = os.path.realpath(str(repo))
    cfg = os.path.join(root, ".daw", "config.yml")
    assert vt.enforcement_write_denied(cfg, root, "IDLE") is None
    assert vt.source_write_denied(cfg, root, "IDLE") is None
    for phase in ("CLASSIFY", "DEFINE", "PLAN", "CODE", "CLOSEOUT"):
        why = vt.enforcement_write_denied(cfg, root, phase)
        assert why and "IDLE" in why, f"the settings were writable in {phase}"
    # The carve-out is one file: the rest of `.daw/` stays sealed at IDLE too.
    assert vt.enforcement_write_denied(os.path.join(root, ".daw", "rules", "x.md"), root, "IDLE")
    assert vt.enforcement_write_denied(os.path.join(root, ".daw", "config.yaml"), root, "IDLE")


# ── C1: uninstalling DAW keeps the project's settings ─────────────────────────

def test_uninstall_keeps_the_projects_settings(repo):
    (repo / ".daw" / "rules").mkdir(parents=True)
    (repo / ".daw" / "orchestrator.md").write_text("x")
    (repo / ".daw" / "rules" / "a.md").write_text("x")
    (repo / ".daw" / "config.yml").write_text("version: 1\n")
    out = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "uninstall_repo.py"),
                          "--repo", str(repo), "--self", ROOT],
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert (repo / ".daw" / "config.yml").read_text() == "version: 1\n"
    assert sorted(os.listdir(repo / ".daw")) == ["config.yml"]
    assert "Kept .daw/config.yml" in out.stdout


# ── C2: an existing openspec/ is what init proposes ───────────────────────────

def test_detect_proposes_openspec_where_an_openspec_folder_exists(repo):
    (repo / "openspec" / "changes").mkdir(parents=True)
    out = init(repo, "--detect")
    assert out.returncode == 0 and out.stdout.strip() == "openspec", out.stdout + out.stderr
    assert not (repo / ".daw").exists(), "--detect wrote something"


def test_detect_proposes_daw_without_one(repo):
    out = init(repo, "--detect")
    assert out.returncode == 0 and out.stdout.strip() == "daw", out.stdout + out.stderr
    (repo / "openspec").write_text("not a folder\n")
    assert init(repo, "--detect").stdout.strip() == "daw"


def test_detect_and_a_format_are_one_question_or_the_other(repo):
    assert init(repo, "--detect", "--spec-format", "daw").returncode == 2
    assert init(repo).returncode == 2
