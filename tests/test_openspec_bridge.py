"""The opt-in OpenSpec bridge must not weaken the existing DAW spec gate."""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "ddw" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import ddw_receipt
import openspec_bridge as bridge


def _transition():
    spec = importlib.util.spec_from_file_location(
        "openspec_vt", SCRIPTS / "validate-transition.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _project(root: Path, *, enabled: bool = True) -> tuple[Path, Path]:
    if enabled:
        (root / "AGENTS.md").write_text(
            "## Specification framework\n\nSpec format: OpenSpec\n", encoding="utf-8"
        )
    change = root / "openspec" / "changes" / "add-ledger"
    (root / "openspec" / "specs").mkdir(parents=True)
    (change / "specs" / "ledger").mkdir(parents=True)
    for name in ("proposal.md", "design.md", "tasks.md", "specs/ledger/spec.md"):
        (change / name).write_text(f"# {name}\n", encoding="utf-8")
    spec = root / "docs" / "ddw" / "specs" / "spec-T-1.md"
    spec.parent.mkdir(parents=True)
    spec.write_text(
        "# Execution plan\n| OpenSpec change | openspec/changes/add-ledger |\n",
        encoding="utf-8",
    )
    return spec, change


def test_unconfigured_project_keeps_the_original_receipt(tmp_path):
    spec, _ = _project(tmp_path, enabled=False)
    assert (
        bridge.receipt_text(str(tmp_path), "# Normal DAW spec\n")
        == "# Normal DAW spec\n"
    )
    with pytest.raises(bridge.OpenSpecError, match="did not opt in"):
        bridge.receipt_text(str(tmp_path), spec.read_text(encoding="utf-8"))


def test_unreadable_setting_preserves_legacy_receipt_but_rejects_an_explicit_change(
    tmp_path,
):
    spec, _ = _project(tmp_path, enabled=False)
    (tmp_path / "AGENTS.md").write_bytes(b"\xff")
    assert (
        bridge.receipt_text(str(tmp_path), "# Normal DAW spec\n")
        == "# Normal DAW spec\n"
    )
    with pytest.raises(bridge.OpenSpecError, match="did not opt in"):
        bridge.receipt_text(str(tmp_path), spec.read_text(encoding="utf-8"))


def test_unreadable_setting_is_not_an_opt_in(tmp_path, monkeypatch):
    spec, _ = _project(tmp_path, enabled=False)
    agents = tmp_path / "AGENTS.md"
    agents.write_text(
        "## Specification framework\n\nSpec format: OpenSpec\n", encoding="utf-8"
    )
    original_open = open

    def deny_agents(path, *args, **kwargs):
        if path == str(agents):
            raise PermissionError("permission denied")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", deny_agents)
    assert (
        bridge.receipt_text(str(tmp_path), "# Normal DAW spec\n")
        == "# Normal DAW spec\n"
    )
    with pytest.raises(bridge.OpenSpecError, match="did not opt in"):
        bridge.receipt_text(str(tmp_path), spec.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "setting",
    [
        "## specification framework\n\nSpec format: OpenSpec\n",
        "## Specification framework \n\nSpec format: OpenSpec\n",
        "## Specification framework\n\nSpec format: openspec\n",
        "## Specification framework\n\nSpec format: OpenSpec \n",
        "Spec format: OpenSpec\n\n## Specification framework\n",
        "## Specification framework\n\n## Other section\nSpec format: OpenSpec\n",
    ],
)
def test_only_exact_opt_in_markers_in_the_framework_section_enable_openspec(
    tmp_path, setting
):
    spec, _ = _project(tmp_path, enabled=False)
    (tmp_path / "AGENTS.md").write_text(setting, encoding="utf-8")
    assert bridge.opted_in(str(tmp_path)) is False
    with pytest.raises(bridge.OpenSpecError, match="did not opt in"):
        bridge.receipt_text(str(tmp_path), spec.read_text(encoding="utf-8"))


def test_opt_in_requires_one_valid_change_and_strict_cli(tmp_path, monkeypatch):
    spec, change = _project(tmp_path)
    calls = []

    def run(argv, **kwargs):
        calls.append((argv, kwargs["cwd"]))
        return SimpleNamespace(returncode=0, stdout="valid", stderr="")

    monkeypatch.setattr(bridge.subprocess, "run", run)
    text = spec.read_text(encoding="utf-8")
    before = bridge.validate(str(tmp_path), text)
    assert calls == [
        (["openspec", "validate", "add-ledger", "--strict"], str(tmp_path))
    ]
    (change / "specs" / "ledger" / "spec.md").write_text(
        "# revised\n", encoding="utf-8"
    )
    assert bridge.receipt_text(str(tmp_path), text) != before
    with pytest.raises(bridge.OpenSpecError, match="exactly one"):
        bridge.receipt_text(str(tmp_path), "# No linked change\n")
    (change / "tasks.md").unlink()
    with pytest.raises(bridge.OpenSpecError, match="missing"):
        bridge.receipt_text(str(tmp_path), text)


def test_opt_in_uses_repo_local_cli_without_global_install(tmp_path, monkeypatch):
    spec, _ = _project(tmp_path)
    bin_dir = tmp_path / "node_modules" / ".bin"
    bin_dir.mkdir(parents=True)
    local_cli = bin_dir / "openspec"
    local_cli.write_text(
        '#!/bin/sh\nprintf "%s\\n" "$@" > "$OPENSPEC_LOG"\n', encoding="utf-8"
    )
    local_cli.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir.parent))
    log = tmp_path / "openspec.args"
    monkeypatch.setenv("OPENSPEC_LOG", str(log))

    assert bridge.validate(str(tmp_path), spec.read_text(encoding="utf-8"))
    assert log.read_text(encoding="utf-8").splitlines() == [
        "validate", "add-ledger", "--strict"
    ]


def test_nonexecutable_repo_local_cli_does_not_bypass_missing_global_cli(
    tmp_path, monkeypatch
):
    spec, _ = _project(tmp_path)
    bin_dir = tmp_path / "node_modules" / ".bin"
    bin_dir.mkdir(parents=True)
    local_cli = bin_dir / "openspec"
    local_cli.write_text("not executable", encoding="utf-8")
    monkeypatch.setenv("PATH", str(bin_dir))

    with pytest.raises(bridge.OpenSpecError, match="cannot run OpenSpec validation"):
        bridge.validate(str(tmp_path), spec.read_text(encoding="utf-8"))


def test_opt_in_requires_the_baseline_specs_directory(tmp_path):
    spec, _ = _project(tmp_path)
    (tmp_path / "openspec" / "specs").rmdir()
    with pytest.raises(bridge.OpenSpecError, match="baseline openspec/specs"):
        bridge.receipt_text(str(tmp_path), spec.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "row, message",
    [
        (
            (
                "| OpenSpec change | openspec/changes/add-ledger |\n"
                "| OpenSpec change | openspec/changes/other |\n"
            ),
            "exactly one",
        ),
        ("| OpenSpec change | openspec/changes/Add-Ledger |\n", "must be exactly"),
        ("| OpenSpec change | `openspec/changes/add-ledger |\n", "must be exactly"),
    ],
)
def test_opt_in_rejects_duplicate_and_malformed_link_rows(tmp_path, row, message):
    spec, _ = _project(tmp_path)
    spec.write_text("# Execution plan\n" + row, encoding="utf-8")
    with pytest.raises(bridge.OpenSpecError, match=message):
        bridge.receipt_text(str(tmp_path), spec.read_text(encoding="utf-8"))


def test_failed_cli_never_attests_to_a_change(tmp_path, monkeypatch):
    spec, _ = _project(tmp_path)
    monkeypatch.setattr(
        bridge.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(
            returncode=1, stdout="", stderr="invalid delta"
        ),
    )
    with pytest.raises(bridge.OpenSpecError, match="invalid delta"):
        bridge.validate(str(tmp_path), spec.read_text(encoding="utf-8"))


def test_missing_cli_never_attests_to_a_change(tmp_path, monkeypatch):
    spec, _ = _project(tmp_path)

    def missing(*args, **kwargs):
        raise FileNotFoundError("openspec is not installed")

    monkeypatch.setattr(bridge.subprocess, "run", missing)
    with pytest.raises(bridge.OpenSpecError, match="cannot run OpenSpec validation"):
        bridge.validate(str(tmp_path), spec.read_text(encoding="utf-8"))


def test_existing_gate_rejects_changed_open_spec_bytes_and_seals_the_change(tmp_path):
    spec, change = _project(tmp_path)
    vt = _transition()
    state = {
        "ticket": "T-1",
        "tier": "FEATURE",
        "phase": "CODE",
        "gates": {"spec": True},
    }
    root = str(tmp_path)
    text = spec.read_text(encoding="utf-8")
    ddw_receipt.write(str(spec), "spec", bridge.receipt_text(root, text), "FEATURE")
    assert vt._spec_receipt_missing(root, state) is None
    target = change / "specs" / "ledger" / "spec.md"
    assert "Return to PLAN" in vt.sealed_artifact_denied(str(target), root, state)
    target.write_text("# modified after approval\n", encoding="utf-8")
    assert vt._spec_receipt_missing(root, state) is not None


def test_change_cannot_escape_repo_via_symlink(tmp_path):
    spec, change = _project(tmp_path)
    (change / "extra").symlink_to(tmp_path.parent, target_is_directory=True)
    with pytest.raises(bridge.OpenSpecError, match="symlink"):
        bridge.receipt_text(str(tmp_path), spec.read_text(encoding="utf-8"))


def test_change_directory_itself_cannot_be_a_symlink(tmp_path):
    spec, change = _project(tmp_path)
    moved = tmp_path / "stored-change"
    change.rename(moved)
    change.symlink_to(moved, target_is_directory=True)
    with pytest.raises(bridge.OpenSpecError, match="symlinked"):
        bridge.receipt_text(str(tmp_path), spec.read_text(encoding="utf-8"))


def _installed_fixture(marker, tag):
    """Use the installer fixture, so this invokes the real spec validator on a real plan."""
    suite = (
        Path(__file__).resolve().parents[1] / "scripts" / "verify_install.sh"
    ).read_text(encoding="utf-8")
    at = suite.index(marker)
    end = suite.index("\n" + tag, at)
    return suite[suite.index("\n", at) + 1 : end]


def test_validator_cli_binds_openspec_receipt_and_gate_to_current_change(tmp_path):
    """Exercise the validator subprocess and the gate, rather than only bridge helpers."""
    root = tmp_path / "project"
    root.mkdir()
    (root / "AGENTS.md").write_text(
        "## Specification framework\n\nSpec format: OpenSpec\n", encoding="utf-8"
    )
    (root / "openspec" / "specs").mkdir(parents=True)
    change = root / "openspec" / "changes" / "add-ledger"
    (change / "specs" / "ledger").mkdir(parents=True)
    for name in ("proposal.md", "design.md", "tasks.md", "specs/ledger/spec.md"):
        (change / name).write_text(f"# {name}\n", encoding="utf-8")
    spec = root / "docs" / "ddw" / "specs" / "spec-FEAT-001.md"
    spec.parent.mkdir(parents=True)
    spec.write_text(
        _installed_fixture("cat > \"$VS/spec-FEAT-001.md\" <<'SPECEOF'", "SPECEOF")
        + "\n| OpenSpec change | openspec/changes/add-ledger |\n",
        encoding="utf-8",
    )
    prd = root / "docs" / "ddw" / "prd" / "prd-FEAT-001.md"
    prd.parent.mkdir(parents=True)
    prd.write_text(
        _installed_fixture(
            "cat > \"$VP/docs/ddw/prd/prd-FEAT-001.md\" <<'PRDEOF'", "PRDEOF"
        ),
        encoding="utf-8",
    )
    bin_dir = root / "bin"
    bin_dir.mkdir()
    openspec = bin_dir / "openspec"
    openspec.write_text(
        '#!/bin/sh\nprintf \'%s\\n\' "$@" > "$OPENSPEC_LOG"\n', encoding="utf-8"
    )
    openspec.chmod(0o755)
    env = {
        **os.environ,
        "PATH": str(bin_dir) + os.pathsep + os.environ.get("PATH", ""),
        "OPENSPEC_LOG": str(root / "openspec.args"),
    }
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "validate_spec.py"),
            str(spec),
            "--tier",
            "FEATURE",
            "--prd",
            str(prd),
        ],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "F-OS-01" in result.stdout
    assert (root / "openspec.args").read_text(encoding="utf-8").splitlines() == [
        "validate",
        "add-ledger",
        "--strict",
    ]
    vt = _transition()
    state = {
        "ticket": "FEAT-001",
        "tier": "FEATURE",
        "phase": "CODE",
        "gates": {"spec": True},
    }
    assert vt._spec_receipt_missing(str(root), state) is None
    (change / "tasks.md").write_text("# changed after validation\n", encoding="utf-8")
    assert vt._spec_receipt_missing(str(root), state) is not None
    openspec.unlink()
    missing_cli = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "validate_spec.py"),
            str(spec),
            "--tier",
            "FEATURE",
            "--prd",
            str(prd),
        ],
        cwd=root,
        env={**env, "PATH": str(bin_dir)},
        text=True,
        capture_output=True,
        check=False,
    )
    assert missing_cli.returncode == 2 and "F-OS-01" in missing_cli.stdout
    assert vt._spec_receipt_missing(str(root), state) is not None
