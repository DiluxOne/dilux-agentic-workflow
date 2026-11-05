"""The OpenSpec bridge: a spec that names one change, and a receipt that seals it.

Under `spec-format: openspec` the what lives in `openspec/changes/<name>` and
the ticket's spec writes only the how. Approving the spec approves both, so the
receipt hashes both (`daw_receipt.sealed_text`), and the spec gate refuses the
moment either one changes. The bridge is @mdiloreto's idea and code (#57,
part A), here chosen with a validated setting.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VALIDATE = os.path.join(ROOT, "daw", "scripts", "validate_spec.py")
CHANGE = "openspec/changes/add-export"


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sys.path.insert(0, os.path.join(ROOT, "daw", "scripts"))
import daw_receipt  # noqa: E402

vt = _load("vt_seal", "daw/scripts/validate-transition.py")


def _fixture(marker, tag):
    """The healthy spec and PRD the suite already carries, read rather than
    copied (the same source tests/test_validators.py reads)."""
    suite = open(os.path.join(ROOT, "scripts/verify_install.sh"), encoding="utf-8").read()
    at = suite.index(marker)
    return suite[suite.index("\n", at) + 1:suite.index("\n" + tag, at)]


SPEC = _fixture('cat > "$VS/spec-FEAT-001.md" <<\'SPECEOF\'', "SPECEOF")
PRD = _fixture('cat > "$VP/docs/daw/prd/prd-FEAT-001.md" <<\'PRDEOF\'', "PRDEOF")

PROPOSAL = """## Why
Customers ask for their invoices as a spreadsheet they can file with their accountant.

## What Changes
- Every invoice list can be exported to CSV with the same filters the screen shows.
"""
REQUIREMENT = """## ADDED Requirements
### Requirement: Invoice export
The system SHALL export the filtered invoice list as CSV on request by the owner.

#### Scenario: Owner exports
- **WHEN** the owner asks for an export
- **THEN** a CSV with one row per invoice is returned
"""


def linked(spec=SPEC, change=CHANGE):
    """The healthy spec with the one line that names its change."""
    head, sep, rest = spec.partition("\n\n")
    return "%s\n\n**OpenSpec change:** `%s`\n%s%s" % (head, change, sep, rest)


@pytest.fixture()
def repo(tmp_path):
    r = tmp_path / "proj"
    (r / "docs" / "daw" / "specs").mkdir(parents=True)
    (r / "docs" / "daw" / "prd").mkdir(parents=True)
    (r / "docs" / "daw" / "prd" / "prd-FEAT-001.md").write_text(PRD, encoding="utf-8")
    (r / ".daw").mkdir()
    (r / ".daw" / "config.yml").write_text("version: 1\nspec-format: openspec\n")
    ch = r / CHANGE
    (ch / "specs" / "invoices").mkdir(parents=True)
    (ch / "proposal.md").write_text(PROPOSAL, encoding="utf-8")
    (ch / "tasks.md").write_text("- [ ] 1.1 Add the export\n", encoding="utf-8")
    (ch / "specs" / "invoices" / "spec.md").write_text(REQUIREMENT, encoding="utf-8")
    (r / ".daw-state.json").write_text(json.dumps(
        {"phase": "PLAN", "tier": "FEATURE", "ticket": "FEAT-001", "gates": {}, "history": []}))
    return r


def validate(repo, text, name="spec-FEAT-001.md"):
    path = repo / "docs" / "daw" / "specs" / name
    path.write_text(text, encoding="utf-8")
    out = subprocess.run([sys.executable, VALIDATE, str(path), "--tier", "FEATURE"],
                         capture_output=True, text=True, cwd=str(repo))
    return out, path


def failed(out, rule):
    return any(rule in ln and "❌" in ln for ln in out.stdout.splitlines())


def gate(repo):
    root = os.path.realpath(str(repo))
    state = json.load(open(os.path.join(root, ".daw-state.json")))
    return vt._spec_receipt_missing(root, state)


# ── C4: the spec names one change, writes only the how, and seals it ──────────

def test_a_spec_naming_one_change_with_only_the_how_passes(repo):
    out, _ = validate(repo, linked())
    assert out.returncode == 0, out.stdout[-1500:] + out.stderr
    assert "✅ F-SPEC-OS-01" in out.stdout and "✅ F-SPEC-OS-02" in out.stdout
    assert "Seals: " + CHANGE in out.stdout


def test_the_receipt_names_the_change_and_its_digest_is_over_sealed_text(repo):
    out, path = validate(repo, linked())
    assert out.returncode == 0, out.stdout[-800:]
    text = path.read_text(encoding="utf-8")
    sealed = daw_receipt.sealed_text(str(path), text)
    assert sealed != text and sealed.startswith(text)
    for rel in ("proposal.md", "tasks.md", "specs/invoices/spec.md"):
        assert "%s/%s\0" % (CHANGE, rel) in sealed, rel
    name = "spec-validated-" + daw_receipt.digest_of(sealed)
    receipt = repo / ".daw-sessions" / name
    assert receipt.is_file(), os.listdir(repo / ".daw-sessions")
    assert "openspec: %s" % CHANGE in receipt.read_text().splitlines()
    assert not (repo / ".daw-sessions" / ("spec-validated-" + daw_receipt.digest_of(text))).exists()
    records = [json.loads(ln) for ln in open(repo / ".daw-journal.jsonl")]
    assert any(r.get("name") == name and r.get("openspec") == CHANGE for r in records)
    assert gate(repo) is None, "the gate does not open on the receipt the validator wrote"


def test_a_spec_naming_no_change_fails(repo):
    out, _ = validate(repo, SPEC)
    assert out.returncode == 2 and failed(out, "F-SPEC-OS-01"), out.stdout[-800:]


def test_a_spec_naming_two_changes_fails(repo):
    (repo / "openspec" / "changes" / "add-other").mkdir()
    (repo / "openspec" / "changes" / "add-other" / "proposal.md").write_text("## Why\nx\n")
    two = linked(linked(change="openspec/changes/add-other"))
    out, _ = validate(repo, two)
    assert out.returncode == 2 and failed(out, "F-SPEC-OS-01"), out.stdout[-800:]
    assert "exactly one" in out.stdout


@pytest.mark.parametrize("bad", ["openspec/changes/../../etc", "openspec/changes/Add_Export",
                                 "openspec/changes/-x", "changes/add-export",
                                 "openspec/changes/archive/2026-01-01-add-export"])
def test_a_change_name_that_is_not_one_fails(repo, bad):
    out, _ = validate(repo, linked(change=bad))
    assert out.returncode == 2 and failed(out, "F-SPEC-OS-01"), out.stdout[-800:]
    assert not list(repo.glob(".daw-sessions/spec-validated-*")), "a refused spec left a receipt"


def test_a_change_folder_that_does_not_exist_fails(repo):
    out, _ = validate(repo, linked(change="openspec/changes/add-nothing"))
    assert out.returncode == 2 and failed(out, "F-SPEC-OS-01"), out.stdout[-800:]


def test_a_change_with_no_proposal_fails(repo):
    os.remove(repo / CHANGE / "proposal.md")
    out, _ = validate(repo, linked())
    assert out.returncode == 2 and failed(out, "F-SPEC-OS-01") and "proposal.md" in out.stdout


@pytest.mark.parametrize("copied", [
    "### Requirement: Invoice export\n",
    "#### Scenario: Owner exports\n",
    "Customers ask for   their invoices as a spreadsheet they can file with their accountant.\n",
    "The system SHALL export the filtered invoice list as CSV on request by the owner.\n",
])
def test_a_spec_that_copies_the_what_fails(repo, copied):
    out, _ = validate(repo, linked() + "\n" + copied)
    assert out.returncode == 2 and failed(out, "F-SPEC-OS-02"), out.stdout[-800:]


def test_a_short_line_shared_with_the_proposal_is_not_a_copy(repo):
    out, _ = validate(repo, linked() + "\n## Why\n")
    assert out.returncode == 0 and not failed(out, "F-SPEC-OS-02"), out.stdout[-800:]


def test_a_change_with_a_symlink_out_of_the_repo_is_refused(repo, tmp_path):
    outside = tmp_path / "secret.md"
    outside.write_text("x\n")
    os.symlink(outside, repo / CHANGE / "leak.md")
    out, _ = validate(repo, linked())
    assert out.returncode == 2 and failed(out, "F-SPEC-OS-01") and "symlink" in out.stdout


def test_a_change_that_is_not_utf8_is_refused(repo):
    (repo / CHANGE / "blob.bin").write_bytes(b"\xff\xfe\x00")
    out, _ = validate(repo, linked())
    assert out.returncode == 2 and failed(out, "F-SPEC-OS-01"), out.stdout[-800:]


def test_a_change_past_the_caps_is_refused(repo, monkeypatch):
    monkeypatch.setattr(daw_receipt, "SEAL_MAX_FILES", 2)
    with pytest.raises(daw_receipt.SealError):
        daw_receipt.change_files(str(repo), CHANGE)


def test_an_invalid_config_stops_the_validation(repo):
    (repo / ".daw" / "config.yml").write_text("version: 1\nspec-format: open\n")
    out, _ = validate(repo, linked())
    assert out.returncode == 3 and "config.yml is invalid" in out.stderr


def test_the_change_may_be_written_while_planning(repo):
    """Choice B: `openspec/` is a document folder, like `docs/`."""
    root = os.path.realpath(str(repo))
    for phase in ("DEFINE", "PLAN", "IDLE"):
        assert vt.source_write_denied(os.path.join(root, CHANGE, "proposal.md"), root, phase) is None
    assert vt.source_write_denied(os.path.join(root, "openspecx", "a.py"), root, "PLAN")
    assert "openspec/" in vt.ALLOWED_DIR_PREFIXES
