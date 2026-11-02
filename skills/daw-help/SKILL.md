---
name: daw-help
description: >
  Getting-started guide for DAW. Use it when the user asks "how do I use DAW", "how do I start /
  install DAW", "what is DAW", or "what commands does DAW have".
  Trigger: /daw-help.
---

# Skill: /daw-help — How to use DAW

Show this guide when the user asks how to use, start with, or install DAW; what it is; or what
commands it has. Match the level of detail to the question — there is no need to dump all of it
every time.

## What DAW is

DAW (Dilux Agentic Workflow) is a phased development pipeline, driven by an orchestrator agent
(a state machine), that takes over on its own as soon as you ask for a code change:

```
CLASSIFY → DEFINE → PLAN → CODE → VERIFY → CLOSEOUT
```

The method lives in `.daw/` and is the same for every tool. What changes per tool is the wiring —
where its skills, its subagents and its hooks go.

## 1. Install

From the DAW repo:

```bash
bash install.sh /path/to/target-repo --target claude|codex|copilot|cursor|gemini|opencode|all
```

Without `--target` it asks. Without a path it uses the current directory. It is idempotent, and it
never overwrites a skill or agent you already have.

The installer:
- copies the method to `.daw/`,
- writes the skills and subagents into the location your tool looks in,
- wires that tool's hooks,
- adds the activation block to its context file (`CLAUDE.md`, `AGENTS.md` or `GEMINI.md`),
- adds the pipeline state to `.gitignore`.

**Installing is activating**: once it is in, the pipeline is live in that repo.

Then fill in the "Stack" section of `AGENTS.md`. Without it, DAW has nothing to plan or implement
against, and it will stop and ask.

## 2. Use it

Open your agent in the repo and ask for a code change: the pipeline starts by itself. You never
invoke phases by hand. Day-to-day commands:

- `/daw-status` — which phase the pipeline is in for this repo.
- `/daw-family-status` — the initiative's next step across the family, answered by the forge.
- `/daw-self-check` — check the installation and the state are sound.

Each phase's skills (`daw-create-prd`, `daw-create-spec`, `daw-test`, `daw-commit`, `daw-create-pr`,
and so on) are orchestrated by the state machine; you rarely invoke them yourself.

Not every request pays the full price: CLASSIFY assigns a **tier** and the tier picks the pipeline.
A question is answered directly, a typo takes a short lane, a feature runs the whole thing.

## 2b. How much of it waits for you

At classification time DAW records **`autonomy`**. The default, `assisted`, asks you to approve every
arrow. Say "no me preguntes en cada paso" (or the equivalent) and you get `minimal`: the arrows stop
waiting and **nothing else changes** — the same eight gates, refused by the same hook, over the same
bytes. What goes away is being asked to approve something a receipt already attests.

Three things stop the run in either mode: a decision nobody wrote down, a corrective loop that hit
its ceiling, and a corrupt state. And merging a pull request or closing a tracker ticket always asks
— those are acts on systems other people read.

## What a gate rests on

Eight gates, and none of them is the model's word. Six need a **receipt** naming their document's
current bytes (the PRD, the spec, the threat model, the SAST report, the test run report, the
verification verdict); `commit` asks git; `pr` asks the forge. Editing the document after validating
it stops the receipt matching.

**What that does not say:** DAW does not run your suite and does not scan your code. The receipts
attest that the *report* is complete — not that the work it describes was done right. A complete
report can still be a false one; what it can no longer be is absent or vague.

## 3. Work on two things at once

The state is one per directory. For real parallelism use a worktree — each gets its own state:

```bash
git worktree add ../myapp-FEAT-002 -b feat/FEAT-002
```

## 4. Uninstall

DAW touches none of your code: everything lives in `.daw/`, the `BEGIN DAW` block of the context
file, your tool's hooks, and `.daw-state.json` (gitignored). Remove those pieces and it is gone.

## More information

- **Full usage:** the DAW repo's `README.md`.
- **Internals** (orchestrator, hooks, FSM, helpers): `docs/DEVELOPMENT.md`.

## What this skill does NOT do

- It is **read-only**: it installs and modifies nothing. It only explains. To install, tell the user
  to run `install.sh`.

## Language

Answer in the language the user is writing in.
