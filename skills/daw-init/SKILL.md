---
name: daw-init
description: >
  Sets a project up with DAW: asks which spec format it uses and writes `.daw/config.yml`, the
  project's DAW settings, validated against its schema. Use it when the session boot offers it,
  or when the user asks to set DAW up, configure it, or use OpenSpec. Trigger: /daw-init.
---

# Skill: /daw-init — Set a project up with DAW

## Description

A project's DAW settings live in `.daw/config.yml`, committed with the project and validated
against `daw/config.schema.json`. The plugin stays the same on every machine; this file is what
makes one project different from another. A project without it keeps today's flow, exactly as if
it said `spec-format: daw`.

The questions are yours; the writing is `daw_init.py`'s, which asks nothing and validates what it
wrote. Never write the file by hand from this skill: the script is what the schema holds to.

## Protocol

1. **Ask which spec format the project uses**:
   - `daw` — the spec carries both the what and the how, as it always has.
   - `openspec` — the what lives in an OpenSpec change (`openspec/changes/<name>`); the ticket's
     spec names that change and writes only the how (blocks, tests, order, gates), and its receipt
     seals the change too.

2. **Confirm** with the user what will be written: `.daw/config.yml` with `version: 1` and the
   format they chose.

3. **Write it**:

   ```bash
   python3 .daw/scripts/daw_init.py --repo . --spec-format <daw|openspec>
   ```

   It refuses to replace an existing `.daw/config.yml` (pass `--force` only when the user asked
   to change it) and refuses while a ticket is running: the settings decide which rules that
   ticket is held to. Show the user its output, and tell them to commit `.daw/config.yml`.

## If the user declines

Skipping it keeps today's flow. Add `<!-- daw:declined init daw-init -->` to the project's
`AGENTS.md`, and the session boot stops offering it.

## What this skill does NOT do

- It writes nothing but `.daw/config.yml`, and nothing outside the repository.
- It does not change a ticket in flight: run it at IDLE.

## Language

Answer in the language the user is writing in.
