#!/usr/bin/env python3
"""A project's DAW settings, `.daw/config.yml`, read in one place.

The settings used to be loose lines in `AGENTS.md` (`Spec format: OpenSpec`),
which nothing validated and every agent read its own way. They are data now:
one file, committed in the project, validated against `daw/config.schema.json`
by this reader and by no other. A script that parses the file on its own is the
second copy that drifts.

The method's scripts run without PyYAML, so this is not YAML: it is the flat
`key: value` subset the schema needs. Comments and quoted values are read;
nesting, lists, anchors, aliases, flow and block scalars and a key written twice
are refused, because a reader that guesses at them reads a file differently
from the person who wrote it.

A missing file is `None`, and every caller treats `None` exactly like
`spec-format: daw`: that is what keeps today's flow for a project that set
nothing. An invalid file is `Invalid`, never read as `daw` — a setting nobody
can read is not a setting somebody chose.

    daw_config.py --repo . [--check]
"""
import argparse
import json
import os
import re
import sys

CONFIG = os.path.join(".daw", "config.yml")
SCHEMA = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir,
                      "config.schema.json")
# Far above anything the schema can hold; a file past it is not settings.
MAX_BYTES = 64 * 1024
KEY = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")


class Invalid(ValueError):
    """The file is there and is not settings this reader can vouch for."""


def _scalar(raw, lineno):
    """One value: a quoted string, an integer, or a bare word."""
    raw = raw.strip()
    if raw[:1] in ("'", '"'):
        quote = raw[0]
        end = raw.find(quote, 1)
        if end == -1:
            raise Invalid("line %d: the quote is never closed" % lineno)
        rest = raw[end + 1:].strip()
        if rest and not rest.startswith("#"):
            raise Invalid("line %d: text after the closing quote" % lineno)
        return raw[1:end]
    raw = re.split(r"\s#", raw, 1)[0].strip()
    if not raw:
        raise Invalid("line %d: a key with no value (nesting is not read here)" % lineno)
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    if raw[0] in "&*!|>[{-@`%":
        raise Invalid("line %d: `%s` is YAML this reader does not read (anchors, aliases, "
                      "tags, block or flow values, lists); write a plain value" % (lineno, raw))
    return raw


def parse(text):
    """The flat mapping `text` writes, or `Invalid` saying which line is not."""
    out = {}
    for lineno, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line in ("---", "..."):
            continue
        if line[0].isspace():
            raise Invalid("line %d: indented — nesting is not part of this file" % lineno)
        key, sep, value = line.partition(":")
        key = key.strip()
        if not sep or not KEY.match(key):
            raise Invalid("line %d: expected `key: value`" % lineno)
        if key in out:
            raise Invalid("line %d: `%s` is written twice" % (lineno, key))
        out[key] = _scalar(value, lineno)
    return out


def load_schema():
    with open(SCHEMA, encoding="utf-8") as fh:
        return json.load(fh)


def _same(a, b):
    """Equal and of the same type: `True == 1` in Python, and not in a schema."""
    return type(a) is type(b) and a == b


def validate(data, schema=None):
    """The ways `data` breaks the schema, as sentences; empty when it does not.

    The subset of JSON Schema the file's schema uses — object, required,
    additionalProperties, const, enum, type — and no more: a keyword this does
    not know is refused, so the schema cannot grow a rule nobody enforces.
    """
    schema = schema if schema is not None else load_schema()
    known = {"$schema", "$id", "title", "description", "type", "additionalProperties",
             "required", "properties"}
    unknown = sorted(set(schema) - known)
    if unknown:
        raise Invalid("the schema uses %s, which this reader does not check" % ", ".join(unknown))
    if not isinstance(data, dict):
        return ["the file is not a mapping of settings"]
    props = schema.get("properties", {})
    errors = ["`%s` is required" % k for k in schema.get("required", []) if k not in data]
    for key in sorted(data):
        if key not in props:
            if schema.get("additionalProperties", True) is False:
                errors.append("`%s` is not a setting (known: %s)" % (key, ", ".join(sorted(props))))
            continue
        rule, value = props[key], data[key]
        bad = set(rule) - {"description", "const", "enum", "type", "default"}
        if bad:
            raise Invalid("the schema's `%s` uses %s, which this reader does not check"
                          % (key, ", ".join(sorted(bad))))
        if "const" in rule and not _same(value, rule["const"]):
            errors.append("`%s` must be %s, not %r" % (key, json.dumps(rule["const"]), value))
        if "enum" in rule and not any(_same(value, v) for v in rule["enum"]):
            errors.append("`%s` must be one of %s, not %r"
                          % (key, ", ".join(rule["enum"]), value))
        kind = {"string": str, "integer": int}.get(rule.get("type"))
        if kind and type(value) is not kind:
            errors.append("`%s` must be a %s" % (key, rule["type"]))
    return errors


def read(path):
    """The validated settings in the file at `path`, defaults filled in."""
    try:
        if os.path.getsize(path) > MAX_BYTES:
            raise Invalid("%s is over %d bytes" % (path, MAX_BYTES))
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except (OSError, UnicodeDecodeError) as exc:
        raise Invalid("cannot read it (%s)" % type(exc).__name__)
    data = parse(text)
    schema = load_schema()
    errors = validate(data, schema)
    if errors:
        raise Invalid("; ".join(errors))
    for key, rule in schema.get("properties", {}).items():
        if "default" in rule:
            data.setdefault(key, rule["default"])
    return data


def load(repo):
    """The project's settings, or None when it has no `.daw/config.yml`.

    A `.daw/config.yml` that is a symlink, or is not a regular file, is
    `Invalid`: settings that live somewhere else are somebody else's.
    """
    path = os.path.join(repo, CONFIG)
    if not os.path.lexists(path):
        return None
    if os.path.islink(path) or not os.path.isfile(path):
        raise Invalid("%s is not a regular file" % CONFIG)
    return read(path)


def spec_format(repo):
    """`daw` or `openspec`. No file reads as `daw`; an invalid one raises."""
    data = load(repo)
    return "daw" if data is None else data.get("spec-format", "daw")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--repo", default=".")
    args = ap.parse_args()
    try:
        data = load(args.repo)
    except Invalid as why:
        print("%s is invalid: %s" % (CONFIG, why), file=sys.stderr)
        return 2
    if data is None:
        print("%s: none — today's flow (spec-format: daw)" % CONFIG)
        return 0
    for key in sorted(data):
        print("%s: %s" % (key, data[key]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
