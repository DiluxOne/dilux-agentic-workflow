"""Optional OpenSpec input for DAW's existing spec receipt.

The DAW spec remains the ticket's execution plan. An opted-in project also
binds that plan to one OpenSpec change; neither an unvalidated change nor a
later edit to it can reuse the plan's validation receipt.
"""

import hashlib
import json
import os
import re
import stat
import subprocess

_CHANGE_ROW = re.compile(
    r"^[ \t]*\|[ \t]*OpenSpec change[ \t]*\|(?P<value>.*)\|[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)
_CHANGE_PATH = re.compile(
    r"^(?:`(?P<ticked>openspec/changes/[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)`|"
    r"(?P<plain>openspec/changes/[a-z0-9](?:[a-z0-9-]*[a-z0-9])?))$"
)
_FRAMEWORK_HEADING = re.compile(r"^## Specification framework$", re.MULTILINE)
_FORMAT = re.compile(r"^Spec format: OpenSpec$", re.MULTILINE)


class OpenSpecError(ValueError):
    """The selected OpenSpec change cannot back a DAW gate."""


def opted_in(root: str) -> bool:
    """Only an explicit project setting activates the bridge."""
    try:
        with open(os.path.join(root, "AGENTS.md"), encoding="utf-8") as fh:
            text = fh.read()
    except FileNotFoundError:
        return False
    except (OSError, UnicodeError):
        # This bridge is strictly opt-in. An unreadable setting is not evidence
        # of opt-in, so legacy DAW specs continue to use their original receipt.
        # An explicit OpenSpec row is still rejected by change_path below.
        return False
    heading = _FRAMEWORK_HEADING.search(text)
    if not heading:
        return False
    next_heading = re.search(r"^## ", text[heading.end() :], re.MULTILINE)
    body_end = heading.end() + (
        next_heading.start() if next_heading else len(text[heading.end() :])
    )
    section = text[heading.end() : body_end]
    return bool(_FORMAT.search(section))


def change_path(root: str, spec_text: str) -> str | None:
    """Resolve the change named by the DAW execution plan, never an arbitrary path."""
    rows = _CHANGE_ROW.findall(spec_text)
    enabled = opted_in(root)
    if rows and not enabled:
        raise OpenSpecError(
            "OpenSpec change is named but the project did not opt in "
            "via AGENTS.md § Specification framework"
        )
    if not rows and not enabled:
        return None
    if len(rows) != 1 and (rows or enabled):
        raise OpenSpecError(
            "an OpenSpec project needs exactly one `| OpenSpec change | "
            "openspec/changes/<slug> |` row in the DAW spec"
        )
    value = rows[0].strip()
    match = _CHANGE_PATH.fullmatch(value)
    if not match:
        raise OpenSpecError(
            "the OpenSpec change row must be exactly `openspec/changes/<slug>`"
        )
    return match.group("ticked") or match.group("plain")


def receipt_text(root: str, spec_text: str) -> str:
    """Bind the ordinary spec receipt to every file in its OpenSpec change."""
    change = change_path(root, spec_text)
    if change is None:
        return spec_text
    root = os.path.realpath(root)
    baseline = os.path.join(root, "openspec", "specs")
    if not os.path.isdir(baseline):
        raise OpenSpecError(
            "an OpenSpec project needs the baseline openspec/specs/ directory"
        )
    directory = os.path.join(root, *change.split("/"))
    if os.path.islink(directory):
        raise OpenSpecError(f"symlinked OpenSpec change: {change}")
    if not os.path.realpath(directory).startswith(root + os.sep):
        raise OpenSpecError("OpenSpec change resolves outside the repository")
    if not os.path.isdir(directory):
        raise OpenSpecError(f"OpenSpec change does not exist: {change}")
    files: list[tuple[str, str]] = []
    for base, dirs, names in os.walk(directory, followlinks=False):
        for name in dirs:
            if os.path.islink(os.path.join(base, name)):
                raise OpenSpecError(
                    f"symlink in OpenSpec change: {os.path.join(base, name)}"
                )
        for name in names:
            path = os.path.join(base, name)
            if os.path.islink(path):
                raise OpenSpecError(f"symlink in OpenSpec change: {path}")
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            try:
                mode = os.lstat(path).st_mode
            except OSError as exc:
                raise OpenSpecError(f"cannot inspect {rel}: {exc}") from exc
            if not stat.S_ISREG(mode):
                raise OpenSpecError(f"non-regular file in OpenSpec change: {rel}")
            try:
                with open(path, "rb") as fh:
                    digest = hashlib.sha256(fh.read()).hexdigest()
            except OSError as exc:
                raise OpenSpecError(f"cannot read {rel}: {exc}") from exc
            files.append((rel, digest))
    expected = {f"{change}/{name}.md" for name in ("proposal", "design", "tasks")}
    present = {name for name, _ in files}
    if missing := expected - present:
        raise OpenSpecError("OpenSpec change is missing: " + ", ".join(sorted(missing)))
    if not any(
        re.fullmatch(re.escape(change) + r"/specs/[^/]+/spec\.md", name)
        for name in present
    ):
        raise OpenSpecError(
            f"OpenSpec change has no capability delta: {change}/specs/*/spec.md"
        )
    return (
        spec_text
        + "\n\0OpenSpec change\n"
        + json.dumps(sorted(files), separators=(",", ":"))
    )


def validate(root: str, spec_text: str) -> str:
    """Check OpenSpec syntax before the receipt attests to its current content."""
    bundled = receipt_text(root, spec_text)
    change = change_path(root, spec_text)
    if change is None:
        return bundled
    local_cli = os.path.join(root, "node_modules", ".bin", "openspec")
    cli = (
        local_cli
        if os.path.isfile(local_cli) and os.access(local_cli, os.X_OK)
        else "openspec"
    )
    try:
        result = subprocess.run(
            [cli, "validate", change.rsplit("/", 1)[-1], "--strict"],
            cwd=root,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=60,
            check=False,
        )
    except (OSError, UnicodeError, subprocess.TimeoutExpired) as exc:
        raise OpenSpecError(f"cannot run OpenSpec validation: {exc}") from exc
    if result.returncode:
        raise OpenSpecError(
            "OpenSpec validation failed for "
            + change
            + ": "
            + (result.stderr or result.stdout).strip()[:1200]
        )
    return bundled
