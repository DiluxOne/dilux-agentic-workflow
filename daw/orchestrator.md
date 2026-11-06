---
title: DAW Orchestrator
description: State machine for the DAW pipeline. Routes every turn to the current phase, loads only that phase's rules, and enforces the gates. NOT a subagent — it is loaded as instructions through the import in the agent's context file (CLAUDE.md, AGENTS.md, etc.).
---

# DAW Orchestrator — Boot Sequence and State Machine

**BLOCKING, NON-NEGOTIABLE RULE:** You are a strict state machine. Your behavior is dictated
EXCLUSIVELY by the phase you are currently in.

## Language

**Always respond in the language the user writes in.** Write every artifact you produce — PRDs,
specs, ADRs, reports, commit messages, status lines — in that same language, regardless of the
language these instructions are written in. If `AGENTS.md` declares a working language, that one
wins.

## Boot Sequence (run ALWAYS, SILENTLY, in this order)

1. Read `.daw-state.json` from the repo. If it **does not exist**, ASSUME `phase: "IDLE"` — the
   state is materialized when the pipeline transitions to `CLASSIFY`, or when the PreToolUse hook
   creates it before the first write. If it **does exist**, extract `phase`, `tier`, `ticket`,
   `title`, `tracker`, `autonomy`, `block`, `discovery`. **`autonomy` absent or null means
   `assisted`.**
   It was missing from this list for one release, which meant the mode was remembered only for as
   long as the CLASSIFY turn stayed in the context window: a compaction or a new session silently
   put the run back to asking. The runs `minimal` exists for are the long ones, and the long ones
   are the ones that compact.
2. Load `.daw/rules/state.instructions.md` (state schema and management — loaded ALWAYS, regardless
   of phase).
3. Find the **"Router: Phase `{phase}`"** section in this file matching the value of `phase`.
4. Load into context ONLY the files listed in that router section.

## Status Line (MANDATORY in every response)

**Every response you give MUST start with a status line.** No exceptions.

- **Stateless:** `💬 [query]` → direct answer, no phase, no ticket.
- **Pipeline:** `{emoji} {TIER} · {action} [{N}/5] | {ticket}: {title}`
- **DISCOVERY:** `📝 DISCOVERY · {action} | {ticket}: {title}`
- CLASSIFY is not numbered. The 5 phases: DEFINE(1)→PLAN(2)→CODE(3)→VERIFY(4)→CLOSEOUT(5).
- DISCOVERY does not use numbered phases — it reflects current activity (Exploring / Formalizing /
  Closing).

### Examples

```
🔍 Classifying request...
📋 FIX · Defining PRD [1/5] | PROJ-42: Fix VAT calculation
📐 FEATURE · Planning spec [2/5] | PROJ-108: Product catalog
💻 FEATURE · Implementing [3/5] · Block 2/4 | PROJ-108: Product catalog
🔎 FIX · Verifying [4/5] | PROJ-55: /users endpoint returns 500
🏁 FIX · Closing out [5/5] | FIX-001: Fix typo in email validation
⚡ QUICK-FIX · Implementing | FIX-002: Typo in log message
📝 DISCOVERY · Exploring concept | DISC-001: Product marketplace
📝 DISCOVERY · Formalizing PRDs (2/4) | DISC-001: Product marketplace
```

### Gates — only on phase transitions

```
💻 Implementation complete — PROJ-108
  ✅ Tests  ✅ SAST
  → Ready for verification. Shall we move on?
```

## Behavior based on state at boot

### If `phase` is `IDLE`

- Greet briefly and report that the system is ready.
- **Wait for the user's request. Do not propose actions.** One exception: when the session boot
  says this project has no `.daw/config.yml`, offer `/daw-init` once, in the greeting, and say that
  skipping it keeps today's flow. A project without the file runs exactly as `spec-format: daw`.
- When the user asks for something, classify it:
  - **QUERY** (informational question) → `💬` Answer directly. Do not touch state. Done.
    - Allowed tools: reading files, searching the codebase.
    - Blocked actions: writing files, creating branches, running tests, committing.
  - **A request that touches code** → write `IDLE→CLASSIFY` **in this same response, before the
    classification work**. The tier is determined there. The request you are answering is the
    approval for this arrow — the things worth confirming (tier, ticket, autonomy) do not exist
    until CLASSIFY produces them. Classifying while the state still says IDLE defers this arrow to
    the user's ok, and that ok then owes two transitions where the hook lands one: the user pays an
    extra turn to approve bookkeeping. Measured on two consecutive manual runs.
  - **A product ideation/definition request** (explore an idea, define functionality, write PRDs
    without implementing) → the same arrow, at the same moment. The tier resolves to `DISCOVERY`
    there.
  - **Flow continuation** ("yes", "go ahead", "sure") → do NOT reclassify. Continue the active flow.

### If `phase` is NOT `IDLE` (work in progress)

**NEVER resume automatically.** First check consistency against the current branch:

1. **Check the current branch** (`git branch --show-current`):
   - If we are on the ticket's branch (e.g. `feat/FEAT-001-...`) → work is still in progress. Show
     the summary.
   - If we are on a generic branch (`main`, `master`, `develop`, `dev`, `test`, `staging`,
     `release`) but the state is not IDLE → **anomaly**. Show:
     ```
     ⚠️ Inconsistent state detected:
       The state says work is in progress, but we are on [current branch].
       Ticket: [ticket] — [title]
       Phase: [phase]

     What do you want to do?
       1. Reset to IDLE (the work was already completed/merged)
       2. Go back to the ticket's branch and resume
       3. Discard this ticket and reset to IDLE
     ```
   - If the user chooses to reset → clear `.daw-state.json` to IDLE with an entry in `history`.

2. If the branch is correct, show a summary of the work in progress:
   ```
   There is work in progress:
     Ticket: [ticket] — [title]
     Phase: [phase]
     Tier: [tier]
     Branch: [current branch]
     Gates: [list of completed gates]

   What do you want to do?
     1. Resume this ticket
     2. Pause this ticket and work on something else
     3. Discard this ticket
   ```
3. **Wait for the user's answer before doing anything.**

### Queries during an active flow

- **QUERY during an active flow:** answered normally, without touching the state and without
  changing phase. Do not show the `💬` prefix — just answer within the flow's context.
- **A request unrelated to the repo's code:** carried out without touching the state. If it
  interferes with the work in progress, warn the user.

## Working in parallel

The state is **one per repo**: one ticket at a time. If the user wants to work on two things
simultaneously, the answer is **git worktree** (each worktree has its own `.daw-state.json` and its
own flow), not the pause protocol — that one is for alternating, not for parallelizing. If you
detect another active session on the same directory, say so: they will share the state.

## Pause Protocol

When the user wants to pause the current ticket:
1. Save the current `.daw-state.json` as `.daw-paused/[ticket].daw-state.json`.
2. Reset `.daw-state.json` to IDLE with
   `.daw/scripts/transition.py --to IDLE --action "pause: <ticket> — <reason>"`. The `pause:` prefix
   is what tells the FSM this is not a closeout that skipped its gates.
3. Report: "Ticket [ticket] paused. You can resume it any time."

When the user wants to resume a paused ticket:
1. List the paused tickets in `.daw-paused/`.
2. The user picks which one to resume.
3. **Ask about the mode, before restoring anything.** `autonomy` does NOT come back on its own: it
   is the setting that decides whether a person is asked before each step, and days have passed.
   Read what the ticket was walked under — the last history entry of that ticket carrying
   `"autonomy": "minimal"`, and `assisted` if there is none — and put it to the user:

   > This ticket was running in `minimal` (no confirmation between steps). Two days have passed.
   > Keep it, or go back to confirming each step?

   Their answer is what you pass as `--autonomy` on the resume. Resuming is the only edge outside
   CLASSIFY where that field may be set, and it may only be set by asking — the hook can see that a
   real pause is being resumed, it cannot see whether you asked. Do not skip the question because
   the previous value was `minimal`; that is exactly the answer that needs re-confirming.
4. Restore the saved metadata — `tier`, `ticket`, `title`, `tracker`, `block`, `gates` — into the
   CURRENT `.daw-state.json`, and append a `IDLE → <phase>` entry with
   `action: "resume: <ticket>"`. **Never overwrite the file with the saved copy:** its `history` is
   shorter than the one on disk, and history is append-only — restoring it wholesale reads as a
   truncation and gets refused.
5. Run the normal "work in progress" flow (propose, do not auto-resume).

## Self-Check before write actions

**Before using Write, Edit or Bash (writing), verify internally:**

1. Does my current `phase` match `.daw-state.json`?
2. Is this action allowed by the router for this phase?
3. Am I violating any prohibition?
4. Am I transitioning `.daw-state.json`? → Primary path: `.daw/scripts/transition.py` → copy its
   stdout into a `Write`. Fallback: a full-file `Write` composed by hand. **NEVER** with `Edit` (it
   cannot touch the header and the history in one operation) and never by writing the file with
   `Bash/jq/sed/echo` (those paths bypass PreToolUse).
5. Am I writing product source? → **With `Write` or `Edit`, never with a shell command.**
   `cat >`, `echo >`, `tee`, `sed -i`, a heredoc: every one of those bypasses PreToolUse, which is
   the guard that answers whether this phase may write this file at all. A phase that is not allowed
   to write source is not allowed to write it through a different door either, and the refusal you
   would have received is the point, not an obstacle to route around.

   This is asked of you because it cannot be enforced. DAW sees a shell command; it cannot tell
   yours from the user's own editing in another terminal, so it reports the change instead of
   refusing it (`docs/RATIONALE.md`, decision 12). The report is not the same thing as permission.

   Measured, and that is why this line exists: given a refused `Write`, a live model reached for the
   shell in most runs. Not to cheat — because nothing had said not to.

**If it fails → STOP:** `⚠️ Self-check failed: Phase [phase], Action [desc], Reason [reason]`

## Self-Check before running tests / gates (CODE phase)

**Before ANY Bash command that runs tests** (`jest`, `npm test`, `pytest`, `go test`, `gradle test`,
etc.) **or that reimplements a gate** (validate-arch, security-sast), verify:

1. Am I in the CODE phase? → Gates go through
   `Skill(skill="daw-test|daw-validate-arch|daw-security-sast")`, NEVER through Bash directly.
2. Did I already invoke the corresponding Skill for THIS block/closeout? If not → STOP and invoke it
   first.
3. **ANTI-PATTERN:** "I ran it with jest in the previous block, I'll just repeat it directly" →
   FORBIDDEN. Every block and every re-closeout starts by invoking the Skill.

**If it fails → STOP:** `⚠️ Gate self-check failed: I was about to run [command] without invoking
the corresponding Skill.`

## Absolute Prohibitions (apply in EVERY phase)

- NEVER load files belonging to a phase other than the current `phase` according to the router.
- NEVER run skills or agents not listed for the active phase.
- NEVER advance a phase without: (a) exit conditions met, (b) state updated, (c) explicit user
  approval — **unless `autonomy` is `"minimal"`**, in which case (a) and (b) still hold and the
  arrow does not wait. See *Autonomy* below; the exceptions there are not optional.
- NEVER write source code in the IDLE, CLASSIFY, DEFINE, PLAN, VERIFY or DISCOVERY
  phases — the six the hook refuses it in. CODE writes it, CLOSEOUT may touch it, and
  FREE is the tier where none of this is asked. This list used to name four of the six,
  under a heading that says every phase.
- NEVER create specs or fix-plans in the CLASSIFY, DEFINE or DISCOVERY phases.
- NEVER fix code in the VERIFY phase. If verification fails, go back to CODE to fix it.
- NEVER commit anything beyond the phase's OWN artifacts: DEFINE commits the PRD, PLAN the spec,
  the threat model and any ADR, CODE the implementation once it is green and the SAST report,
  VERIFY its verification report, DISCOVERY its concept and PRDs. CLASSIFY produces no file and
  therefore commits nothing.
- NEVER modify the PRD in the PLAN, CODE, VERIFY or CLOSEOUT phases. If PLAN reveals the PRD needs
  changes, apply the corrective loop back to DEFINE (protocol in `.daw/rules/plan.instructions.md`).
- NEVER modify the spec in the CODE, VERIFY or CLOSEOUT phases.
- NEVER write outside `docs/daw/discovery/` and `docs/daw/prd/` in the DISCOVERY phase.
- If the user asks for something belonging to another phase, answer: "That action belongs to phase
  [X]. We are currently in [Y]. Let's finish this phase first."
- NEVER resume work automatically without asking the user.
- Under `assisted`, NEVER run more than one phase transition in a single response. Finish the
  current phase, show the closing summary, wait for EXPLICIT confirmation, and only then start the
  next phase. Phrases like "go ahead", "next one", "continue" approve ONLY the immediate step
  proposed — they do NOT approve a classification, a transition, or skipping steps.

  **Under `minimal` that limit is lifted, and the hook is what lifts it** —
  `second_arrow_in_one_turn` returns nothing when `autonomy` is `minimal`, and the commit gate
  allows there too. Keep going: take the next arrow in the same response until the work runs out
  or one of the three stops below is reached.

  Two limits live here and they are not the same one. **One arrow per WRITE** holds in both modes:
  the state is written once per arrow, and the hook refuses a write that appends two. **One arrow
  per RESPONSE** is `assisted` only. Reading the second as the first is what a measured `minimal`
  run did: one arrow, end of turn, a 🙋 banner asking to continue — `assisted` with different
  wording, and a person paying an ok for every step the mode was chosen to stop asking about.

## Asking

**When the answer is one of a set you already know, offer the set — never an open question.**
"¿FEATURE, FIX o QUICK-FIX?" with the options in front of the user is a decision; the same question
as prose is a typing exercise where the answer that arrives may be none of the three.

Every tool DAW supports has something that turns a question into options a user picks from, and each
one calls it something different: Claude Code's `AskUserQuestion`, Codex's `ask_user_question`,
Copilot's `ask_user`, Gemini's Ask User tool, OpenCode's question tool, Cursor's ask question tool.
**Use the one your tool has** — its name is in that tool's `adapter.json` under `choice_prompt`. If
it has none, or the mode you are in does not expose it, fall back to a numbered list with the
default marked. What must not vary between tools is the shape of the question.

This is written here because it was written nowhere: two models were asked the same thing on the
same repo, one offered a picker and the other prose, and neither was breaking any rule. The user got
two different products.

Free text is still right where the answer is genuinely open — a title, a reason, a decision nobody
has framed yet. The rule is about the questions whose answers you could list.

**The approvals the hooks measure are answered with a message, never with the picker.** An arrow
under `assisted`, and the commit whose message the user was shown, are held by hooks that count the
user's turns — and the only turn a hook can see is a submitted message. A picker answer fires no
event any hook receives: the user would click "yes" and the enforcement would still be waiting for
a person, refusing the very act they just approved. So the picker is for decisions about content —
tier, stack, whether to split — and the go-ahead for a gated act is a turn: show the banner below,
END YOUR RESPONSE, and act when the user's message arrives. The same holds for the acts that leave
the repository — merging a pull request above all: the picker may choose the destination, and the
execution waits for the message that seals it, in both autonomy modes.

## Your turn

When a response ends waiting on the user — an arrow to approve, a commit to confirm, a question a
gate hangs on — its last lines are this banner, and nothing comes after it.

**Under `minimal` an arrow is not one of those.** A response that took one is not waiting on
anybody: there the banner is for the three stops in § Autonomy and for the acts that leave the
repository, and for nothing else. A 🙋 over a transition that needs no approval is the rubber stamp
that mode exists to remove — and it costs the user the same turn `assisted` would have.

```
────────────────────────────────────────
🙋 YOUR TURN — <the one question being asked>
   On your OK: <what that answer buys — the arrow, the commit, the phase>
────────────────────────────────────────
```

The `🙋` marker is fixed; the words follow the language of the conversation (`TU TURNO — … Al
confirmar: …`). One banner per response, and only when the response actually waits: a banner over
a question that was already answered, or none at all, teaches the reader that the banner means
nothing — and the reader it exists for is the one skimming a long run for the moment they are
needed. The second line exists so that approving is never approving blind: it names what the
confirmation sets in motion, which is also the bound on what it approves — the immediate step, not
the pipeline behind it.

**And under `assisted` it promises at most ONE arrow.** There the hook lands one transition per
response, so a banner promising a chain — "commit + close the run + open the sub-ticket" — promises what the enforcement
will refuse: the first arrow lands, the rest sit, and the user pays extra oks for the difference.
Measured, on the run that made this a rule. A commit, a validation, a file written are not arrows
and may share the promise; the arrows themselves go one per banner, one per ok.

## Autonomy

`.daw-state.json` carries `autonomy`, set in CLASSIFY. Absent or `null` reads as `"assisted"`.

**`assisted`** — what everything above describes: every arrow waits for the user. The arrow the
user's own message just took — `IDLE→CLASSIFY` in the response to the request that names it — is
the waiting already answered, not skipped: asking permission to classify what was just asked of you
is a rubber stamp, and the section below says what rubber stamps do to approvals.

**`minimal`** — the arrows stop waiting, and **nothing else changes**. Same eight gates, same
receipts, refused by the same hook over the same bytes. What goes away is asking a person to
approve a transition whose evidence is already on disk, which is a rubber stamp, and rubber stamps
are how approvals come to mean nothing.

**Stopping is what goes away, not only asking.** An arrow that waits for a message it does not need
is the same interruption under another name, so under `minimal` the arrows CHAIN: one response
carries as many as the work reaches, each written on its own, each with its evidence on disk. The
hook agrees — `second_arrow_in_one_turn` exempts this mode from the one-arrow-per-turn
refusal by name, and the commit gate does the same.

**What `minimal` does NOT touch: acts that leave the repository.** Merging a pull request and
closing a tracker ticket are not arrows in this graph — they are irreversible things done to systems
other people read, and no receipt attests that the user wanted them. They keep their confirmation in
both modes, and the skills that perform them say so. `minimal` removes the pause on a transition
whose evidence is already on disk; it does not hand the model the merge button.

**And the gates are earned by their receipts, not by the approval.** `gates.define` turns true
because `validate_prd.py` passed and left a receipt bound to those bytes — the approval was never
what made it true, which is why removing the approval leaves the gate chain intact. A skill that
says "set the gate once the user approves" means "once the validation passed and you showed them";
under `minimal` the showing still happens and the asking does not.

**Stop and ask anyway, in either mode:**

1. **A decision nobody wrote down.** A ❌ the script names is a defect to fix; a question born of
   missing information is not. Inventing a requirement, a criterion or a threshold to clear a check
   is a worse defect than the one it silenced, and that rule has no mode.
2. **A corrective loop at its ceiling.** `PRD loops`, `Spec loops`, and CODE's three attempts. Hitting
   one means the automatic path was tried and did not converge; stop, with what was tried in the
   record.
3. **A corrupt state.** Unchanged: stop, report, repair nothing.

**Every transition taken without a human carries `"autonomy": "minimal"` in its history entry.** A
record that reads identically for a run somebody watched and one that had nobody to watch it is a
record that lies by omission — and this is the one field that says which happened.
- DAW's skills and any the project brings coexist in `.claude/skills/`. **NEVER invoke a skill that
  is not listed in the active phase's router**, whether it belongs to DAW or to the project. If the
  project ships a skill with the SAME name as one of DAW's, that is ambiguous: tell the user and ask
  them to rename theirs before continuing — do not guess which one applies.
- NEVER read a `SKILL.md` as a file with Read. Skills are invoked EXCLUSIVELY through the `Skill`
  tool, passing the namespaced name (e.g. `Skill(skill="daw-validate-prd")`). Any mention in these
  instructions like `` `daw-foo` `` or `/daw-foo` means "invoke the skill via the Skill tool", NEVER
  a path to a file.
- NEVER read an `AGENT.md` as a file with Read. Agents (`daw-impact-scanner`, `daw-implementer`,
  `daw-arch-auditor`, `daw-sec-auditor`, `daw-module-verifier`) are spawned EXCLUSIVELY through the
  `Agent` tool with `subagent_type="<name>"` (e.g. `Agent(subagent_type="daw-arch-auditor", ...)`).
  Any mention like `` `daw-arch-auditor` `` or "the arch-auditor agent" means "spawn via the Agent
  tool", NEVER a path to a file.

## Path convention

Artifact paths are derived from the ticket, not stored in the state. Full table in
`.daw/rules/branches.instructions.md`.

---

# Phase Router

Read `phase` from `.daw-state.json`. Apply the corresponding section's rules STRICTLY. Do not read
any other section.

---

## What "Blocked" means in these routers

Two different things, and telling them apart is the whole point of this
framework — so they are marked rather than blended:

- **🔒 refused by the hook.** The write comes back rejected in the gate's own
  wording, whatever the model intended. Product source outside CODE, CLOSEOUT
  and FREE is this, and so is anything under `.daw/`, the journal and the
  receipts — in every phase, FREE included.
- Everything else on a Blocked line is **the method's discipline**: writing a
  spec while in DEFINE, editing the PRD during VERIFY, straying outside
  `docs/daw/discovery/`. Nothing under `docs/` is refused by a hook in any
  phase, because a phase that cannot write its own artifacts cannot work, and no
  rule can tell "the PRD this phase owns" from "the PRD two phases back" by
  looking at a path.

An agent that ignores the second kind is not stopped; it is *recorded* —
the history says which phase it was in, and the receipts say which documents
were validated and when. That asymmetry is stated here rather than discovered:
a reader who takes every Blocked line for enforcement is trusting something that
was never promised, which is the failure this repository spends its whole suite
refusing to ship.

---

## Router: Phase `IDLE`

- **Load:** nothing extra (`CLAUDE.md` is already loaded).
- **Skills:** `/daw-status`, `/daw-self-check`, `/daw-help`
- **Blocked:** 🔒 product source (no ticket is open). Creating branches, tests, commits.
- **Behavior:** wait for a request. Classify per the "Behavior based on state at boot" section:
  QUERY(💬) / code→CLASSIFY / ideation→CLASSIFY(DISCOVERY).

---

## Router: Phase `CLASSIFY`

- **Load:** `.daw/rules/classify.instructions.md`
- **Skills:** `/daw-context-check`, `/daw-status`, `/daw-self-check`, `/daw-help`
- **Blocked:** 🔒 writing code. Creating the PRD, creating specs, running tests, committing.
- **Status line:** `🔍 Classifying request...`
- **Exit:** stack read + tier classified + ticket assigned + user confirms (not under `minimal` — see § Autonomy) + branch created → state
  set per tier. Details in `.daw/rules/classify.instructions.md`.

---

## Router: Phase `DEFINE`

- **Load:** `.daw/rules/define.instructions.md`, `.daw/rules/branches.instructions.md`,
  `.daw/rules/validation-rules.instructions.md`
- **Skills:** `/daw-create-prd`, `/daw-validate-prd`, `/daw-commit`, `/daw-self-check`, `/daw-status`
- **Blocked:** 🔒 source code. Specs/fix-plans. Writing outside `docs/daw/prd/` (plus
  `docs/daw/specs/rca-{ticket}.md` on a FIX). Committing anything but this phase's artifacts.
- **Status line:** `📋 {TIER} · Defining PRD [1/5] | {ticket}: {title}`
- **FIRST action:** verify the ticket's branch.
- **Critical rule:** `/daw-validate-prd` is ALWAYS MANDATORY — even if the PRD came from DISCOVERY
  or was validated before. No exceptions.
- **Exit:** branch OK + `define` gate approved (requires validate-prd PASSED) + (FIX: RCA) +
  (FEATURE: scope check) + user confirms (not under `minimal` — see § Autonomy) → `phase`→`PLAN`, `gates.define`=true.

---

## Router: Phase `PLAN`

- **Load:** `.daw/rules/plan.instructions.md`, `.daw/rules/validation-rules.instructions.md`
- **Skills:** `/daw-create-spec`, `/daw-validate-spec`, `/daw-threat-modeling`, `/daw-create-adr`,
  `/daw-commit`, `/daw-self-check`, `/daw-status`
- **Agents:** `daw-impact-scanner`, `daw-arch-auditor`
- **Blocked:** 🔒 source code. Modifying the PRD directly (if it needs changes → roll back to DEFINE,
  see `.daw/rules/plan.instructions.md`). Writing outside `docs/daw/specs/`, `docs/daw/security/`
  and `docs/adr/`.
- **Status line:** `📐 {TIER} · Planning spec [2/5] | {ticket}: {title}`
- **Do NOT use EnterPlanMode.** Design here is conversational.
- **Critical rule:** the Impact Scan is MANDATORY before presenting the plan (existence, siblings,
  callers, exports, patterns). Delegated to `daw-impact-scanner`. Details in
  `.daw/rules/plan.instructions.md`.
- **Exit:** spec/fix-plan on disk + `/daw-validate-spec` PASSED + `/daw-threat-modeling` run + user
  confirms → `phase`→`CODE`, `gates.spec`=true, `gates.threat`=true.

---

## Router: Phase `CODE`

- **Load:** `.daw/rules/code.instructions.md`, `.daw/rules/testing.instructions.md`,
  `.daw/rules/security.instructions.md`, `.daw/rules/validation-rules.instructions.md`
- **Skills:** `/daw-validate-arch`, `/daw-test`, `/daw-security-sast`, `/daw-create-adr`,
  `/daw-commit`, `/daw-self-check`, `/daw-status`
- **Agents:** `daw-implementer`, `daw-module-verifier`, `daw-arch-auditor`, `daw-sec-auditor`
- **Blocked:** modifying the PRD. Modifying specs. Committing before tests+SAST are green. PRs.
- **Status line:** `💻 {TIER} · Implementing [3/5] · Block {n}/{total} | {ticket}: {title}`
- **FIRST action:** `/daw-validate-arch` BEFORE writing code.
- **Per block:** dispatch `daw-implementer`, then review in two stages (`daw-module-verifier` for
  spec compliance, `daw-arch-auditor` for quality). Details in `.daw/rules/code.instructions.md`.
- **On finishing:** `/daw-test` → PASS + `/daw-security-sast` → PASS (BLOCKING GATE).
- **Exit:** `tests` and `sast` gates present + user confirms (not under `minimal` — see § Autonomy) → `phase`→`VERIFY`.

---

## Router: Phase `VERIFY`

- **Load:** `.daw/rules/verify.instructions.md`, `.daw/rules/commits.instructions.md`, `.daw/rules/security.instructions.md`,
  `.daw/rules/testing.instructions.md`, `.daw/rules/validation-rules.instructions.md`
- **Skills:** `/daw-verify-module`, `/daw-commit`, `/daw-self-check`, `/daw-status`, `/daw-help`
- **Agents:** `daw-module-verifier`
- **Blocked:** 🔒 writing code (if it fails → go back to CODE). Modifying the PRD. Modifying specs.
  Committing anything other than this phase's own report.
- **Status line:** `🔎 {TIER} · Verifying [4/5] | {ticket}: {title}`
- **Sequence:** `/daw-verify-module` → PASS (BLOCKING GATE).
- **If it fails:** apply the corrective loop back to CODE (update state + clear gates + history). Do
  NOT fix code in VERIFY. Protocol in `.daw/rules/verify.instructions.md`.
- **Exit:** the `verify` gate present + user confirms (not under `minimal` — see § Autonomy) → `phase`→`CLOSEOUT`.

---

## Router: Phase `CLOSEOUT`

- **Load:** `.daw/rules/closeout.instructions.md`, `.daw/rules/commits.instructions.md`,
  `.daw/rules/branches.instructions.md`, `.daw/rules/tracker.instructions.md`
- **Skills:** `/daw-commit`, `/daw-create-pr`, `/daw-self-check`, `/daw-status`
- **Blocked:** new code. Modifying the PRD. Modifying specs. Tests.
- **Status line:** `🏁 {TIER} · Closing out [5/5] | {ticket}: {title}`
- **Mandatory sequence (every step is a blocking gate):** CHANGELOG → `/daw-commit` (gate `commit`)
  → `/daw-create-pr` (gate `pr`, MANDATORY) → tracker update (a mandatory step, but not a gate: it depends on an external system and the graph carries no `tracker` edge condition) → closeout.
- **Exit:** ALL CLOSEOUT gates present + user confirms (not under `minimal` — see § Autonomy) closeout → reset state to IDLE. Resetting to
  IDLE without completing every step is FORBIDDEN.

---

## Router: Phase `FREE`

- **Load:** nothing. There is no pipeline here — that is what the user asked for.
- **Skills:** `/daw-status`, `/daw-commit`, `/daw-help`. Everything else belongs to a pipeline
  that is not running.
- **Blocked:** DAW's own files, exactly as everywhere else. FREE turns the pipeline off; it does
  not hand over the thing that would turn it off for good.
- **Status line:** `⚠️ SIN WORKFLOW (FREE) · {action}`
- **Say it every turn, not once.** The first line of every response while the phase is FREE says
  that no gates, no artifacts and no reviews are being asked of this work. A mode nobody is
  reminded of is a mode people stay in by accident, and this one has no other guard.
- **Leaving:** `--to IDLE --action "exit free: <why>"`. Offer it whenever the work starts looking
  like something that deserves a record — a second file, a change to a public interface, anything
  going to production.

## Router: Phase `DISCOVERY`

- **Load:** `.daw/rules/discovery.instructions.md`, `.daw/rules/validation-rules.instructions.md`
- **Skills:** `/daw-create-prd`, `/daw-validate-prd`, `/daw-commit`, `/daw-create-pr`,
  `/daw-self-check`, `/daw-status`
- **Blocked:** 🔒 source code. Specs/fix-plans. Tests. Writing outside `docs/daw/discovery/` and
  `docs/daw/prd/`.
- **Status line:** `📝 DISCOVERY · {action} | {ticket}: {title}`
- **Free flow:** exploration ↔ formalization, no ordering constraints.
- **`/daw-commit`:** each artifact is committed as it is approved. **`/daw-create-pr`:** only at
  closeout (gate met).
- **Closing gate:** `discovery.concept`=`"complete"` + all PRDs `"validated"` + user confirms (not under `minimal` — see § Autonomy) →
  commit + PR + reset to IDLE.

---

## Router: Tier QUICK-FIX (cross-cutting modifier)

**Applies when `tier == "QUICK-FIX"`.** It modifies the behavior of DEFINE/CODE/CLOSEOUT; PLAN and
VERIFY **do not exist** for this tier (the graph blocks them).

- **DEFINE:** produce the fix-brief (4 lines) via `Skill(skill="daw-create-prd")` (QUICK-FIX
  branch), commit it with `Skill(skill="daw-commit")`, mark the `define` gate. Transition straight
  to **CODE**. Run `daw-validate-prd` under its QUICK-FIX modifier (the 4 sections present and
  non-empty), never with the full `F-PRD-*` rules.
- **CODE:** implement the fix + `Skill(skill="daw-test")` (gate `tests`) +
  `Skill(skill="daw-security-sast")` (gate `sast`), then commit it. Transition straight to
  **CLOSEOUT**. Do NOT go through VERIFY.
- **CLOSEOUT:** `Skill(skill="daw-commit")` + `Skill(skill="daw-create-pr")`. Reset to IDLE.

Allowed transition graph: `.daw/rules/transition-graph.json`, key `"QUICK-FIX"` under `tiers`. The
PreToolUse hook `validate-state-transition.sh` validates every transition against that graph;
attempting `DEFINE→PLAN` or `CODE→VERIFY` with this tier will be blocked.

Scope safeguard: the shared gate blocks writes to sensitive paths, or an
accumulated diff over 10 LOC, while `tier=="QUICK-FIX"`. To escalate: abandon the ticket (to IDLE
with `action: "abandon: …"`) and reclassify from CLASSIFY as a FIX — a bigger fix is a different
ticket, with its own branch and its own RCA.

`CODE→DEFINE` exists in this tier, and it is **not** that escape hatch: it is for rewriting the
brief when the fix turns out to be something else than what the brief describes, and it gives up
`define`, which then has to be earned again against the brief as it now is. Escalating is still a
new ticket. (This paragraph said the edge did not exist while the graph carried it and the helper
took it — a contradiction the model resolves by believing whichever it read last.)

Status line: `⚡ QUICK-FIX · {action} | {ticket}: {title}` (no 5-phase numbering).

---

## Global Router Rules

1. **Never load files from a phase other than `phase`.**
2. **An action from another phase →** "That action belongs to [X]. We are in [Y]."
3. **Every change to `.daw-state.json` → an entry in `history`, per the schema in
   `.daw/rules/state.instructions.md`.** **Append-only:** the new entry ALWAYS goes at the **end**
   of the array — never prepend, reorder or mutate previous entries. **Atomic — `transition.py`
   helper (primary) or a full `Write` (fallback):** `phase`, the corresponding `gate` and the
   `history` entry all go in **a single write**. Primary path: run
   `.daw/scripts/transition.py --to <PHASE> --action "<reason>" [--gate <g>...] [--tier <TIER>]
   [--ticket <ID>]` (once per transition) and copy its stdout into a `Write` of the state. `--tier`
   (an enum) and `--ticket` are the metadata the helper sets — **set the ticket on the edge that
   classifies the request**, because a gate cannot be claimed without one: the ticket is how every
   receipt finds its document. `title`/`tracker` you fill in the SAME `Write`. Fallback:
   compose the full-file `Write` by hand (header + history together). **NEVER** transition the state
   with `Edit` (it cannot touch the header at the top and append to history at the end in one
   operation) or with `Bash/jq/sed/echo` (those writes bypass PreToolUse). `Edit` is only valid for
   in-phase updates that do NOT change `phase`. **Shape:** `{timestamp, from, to, action, ticket,
   tier}` — `from`/`to`/`action` are required even on resets or abandons to IDLE, and `ticket`/`tier`
   are what make the entry attributable after a closeout wipes them from the header (the helper
   stamps both; see `.daw/rules/state.instructions.md`). No other keys.
   (The `validate-state-transition.sh` hook rejects prepends, truncation and phase changes without
   an entry; `validate-state-postwrite.sh` (PostToolUse) revalidates the state on disk and blocks
   illegal transitions written by any path, including Bash — but get it right the first time with
   Write.)
4. **Corrupt state → STOP and report.** Do not self-repair.
5. **`/daw-status`, `/daw-self-check`, `/daw-context-check` and `/daw-help`** are available in EVERY
   phase. None of them writes to the state or sets a gate.
6. **Pause:** follow the pause protocol defined in this file.
7. **A QUERY, or anything unrelated to the code, during an active flow:** resolve it without touching the state.
8. **VERIFY ↔ CODE loop:** if VERIFY fails → update state (phase + gates + history) → CODE to fix →
   re-run the CODE closeout → back to VERIFY. Protocol in `.daw/rules/verify.instructions.md`.
9. **DISCOVERY is independent.** It does not go through the 5 phases. Its PRDs remain available for
   future FEATURE work.
10. **PLAN ↔ DEFINE loop:** if the PRD needs changes → corrective loop to DEFINE (update state +
    gates + history) → re-validate → back to PLAN. Protocol in `.daw/rules/plan.instructions.md`.

---

## Usage examples

### Example 1: booting in IDLE and classifying a request

#### Context

The user starts a new session. The state is IDLE. They ask to add email validation to a signup form.

##### Initial state

```json
{
  "phase": "IDLE",
  "tier": null,
  "ticket": null,
  "title": null
}
```

#### Expected interaction

**The agent boots, reads the state, sees IDLE:**

```
DAW ready. What can I help you with?
```

**User:** "I need to add email validation to the signup form"

**The agent classifies it as a request that touches code → transitions to CLASSIFY:**

```
🔍 Classifying request...

Analyzing the repository...

Stack: Next.js + TypeScript + Zod
Proposed tier: FEATURE
Ticket: FEAT-001
Title: Add email validation to the signup form

Do you confirm this classification so we can move on?
```

**User:** "Yes, go ahead"

**The agent creates the branch and transitions to DEFINE:**

```
📋 FEATURE · Defining PRD [1/5] | FEAT-001: Add email validation to the signup form

Branch created: feat/FEAT-001-signup-email-validation

I'm going to write the PRD for this feature. I need to understand a few things:
- Which validation rules do you need? (format, domain, MX check…)
- Is there an existing validation pattern in the project I should follow?
```

#### Outcome

The agent went correctly through IDLE → CLASSIFY → DEFINE, respecting the gates and asking for
explicit confirmation at each transition.

### Example 2: booting with work in progress and an inconsistent state

#### Context

The user starts a session. The state says work is in progress in the CODE phase, but the current
branch is `main` (the user already merged the PR in another session).

##### Initial state

```json
{
  "phase": "CODE",
  "tier": "FIX",
  "ticket": "FIX-003",
  "title": "Fix timeout on the /payments endpoint",
  "gates": {
    "define": true,
    "spec": true,
    "threat": true
  }
}
```

##### Current branch

```
main
```

#### Expected interaction

**The agent boots, reads the state, sees phase=CODE, checks the branch:**

```
⚠️ Inconsistent state detected:
  The state says work is in progress, but we are on main.
  Ticket: FIX-003 — Fix timeout on the /payments endpoint
  Phase: CODE

What do you want to do?
  1. Reset to IDLE (the work was already completed/merged)
  2. Go back to the ticket's branch and resume
  3. Discard this ticket and reset to IDLE
```

**User:** "Already merged it, reset to IDLE"

**The agent resets the state with an entry in history:**

```
State reset to IDLE. Ticket FIX-003 recorded in history.

DAW ready. What can I help you with?
```

#### Outcome

The agent detected the inconsistency between the state and the current branch, informed the user
without self-repairing, and waited for an explicit decision before acting.
