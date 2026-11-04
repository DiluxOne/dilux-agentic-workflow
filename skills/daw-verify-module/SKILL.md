---
name: daw-verify-module
description: >
  Verifies that a completed module meets every acceptance criterion in its PRD and every task in its
  spec. A blocking gate.
  Trigger: /daw-verify-module, during DAW's VERIFY phase.
---

# Skill: /daw-verify-module

## Description
Verifies that a completed module meets every acceptance criterion in its PRD and every task in its
spec. A blocking gate.

## Inputs
- The PRD at `docs/daw/prd/prd-{ticket}.md` (if `gates.define` is true and the tier is FEATURE).
- The spec/fix-plan at `docs/daw/specs/spec-{ticket}.md` or `docs/daw/specs/fix-{ticket}.md` (if
  `gates.spec` is true).
- The implemented code.
- The tests, and their results.
- `.daw/rules/validation-rules.instructions.md` §5 for the rules (F-VER-01 to F-VER-06, W-VER-01 to
  W-VER-03) — the single source of truth.
- The `tier` from `.daw-state.json`.

## Execution Protocol

### For FEATURE

1. **Verify the PRD's acceptance criteria** (F-VER-01):
   For EVERY acceptance criterion:
   - Does the code implement it? (exact location: file:function)
   - Is there a test verifying it — and is that test passing?
   - Does the test verify the actual behavior, or only the status code? Status-code-only is a
     WARNING, not a PASS.

2. **Verify the spec's tasks** (F-VER-02, F-VER-06):
   For EVERY checkbox in the spec:
   - Is it marked complete?
   - Does the corresponding code exist?
   - Does every test the spec listed exist and pass? Those are approved commitments.

3. **Verify coverage** (F-VER-03):
   - Lines ≥ 80%, branches ≥ 80%, functions ≥ 80% over the new/modified code. Below any of them is a
     FAIL, not a warning.
   - Core business logic between 80–90% is a WARNING (W-VER-02): it should be higher.

4. **Verify sad paths** (F-VER-04):
   - Every endpoint or function accepting input needs at least one test with invalid input.
     Happy-path-only is a FAIL.

5. **Verify quality:**
   - Lint/type checker passes with no errors (F-VER-05).
   - No dead code or unused imports (W-VER-01).
   - No fragile tests: order dependencies, global state, hardcoded timestamps/IDs (W-VER-03).

### For FIX

The fix-plan is the contract. Run the validator with `--tier FIX`: it reads the plan the way the
fix-plan template writes it, not as a spec, so it asks for no `## Block N` and no `test_x` names the
plan never had.

1. **Verify the PRD's acceptance criteria, if there is a PRD** (F-VER-01):
   - A PRD for the ticket, passed or found at `docs/daw/prd/prd-{ticket}.md`, is checked as for
     FEATURE. With none, F-VER-01 passes and says the fix-plan's steps and tests are the contract.

2. **Verify the fix-plan's solution** (F-VER-02):
   - Was every numbered step under `## Solution — steps` implemented? Name each in the verdict as
     `Step N`. A step missing from the verdict, or marked ❌, is a FAIL that names it.

3. **Verify the tests the fix-plan promised** (F-VER-06):
   - Every bullet under `## Tests` exists and passes. One that opens with a `test_x` name is named by
     it; one that is only a description is named by its position, `Test N`. `Test 1` is the
     regression test: does it reproduce the original bug, and pass with the fix applied?

4. **Verify no regressions were introduced:**
   - The full test suite passes, with the coverage numbers (F-VER-03) and a sad path (F-VER-04).
   - Lint passes (F-VER-05).

### Then, for every tier: write the verdict and validate that it is complete

Write the verdict to `docs/daw/reports/verify-{ticket}.md` — every AC by ID with its result, every
block, the three coverage numbers, the sad-path answer and the lint answer. Then run:

`python3 .daw/scripts/validate_verify.py docs/daw/reports/verify-{ticket}.md --tier <tier>`

(under a plugin install, resolve `.daw/scripts/` at the plugin's method path). **Paste its output
VERBATIM** — every row, every rule ID, on **every** run, including a re-validation of a verdict that
has not changed. A PASSED run writes the content-hashed receipt the `verify` gate demands; without it
the VERIFY→CLOSEOUT transition refuses.

**What that receipt does and does not say.** DAW does not run your suite — it does not know your
runner, your directory or your environment, and a gate that cannot be satisfied honestly gets
satisfied dishonestly (`docs/RATIONALE.md` decisions 2 and 16). The script checks that the verdict is
**complete**: that no acceptance criterion is missing from it, no block is unaccounted for, the three
coverage numbers are stated and clear the minimum, and lint and the sad paths have an answer instead
of a silence. The numbers themselves remain your report of what you ran. Say that plainly to the
user rather than letting the receipt imply more.

**Every ❌ from the script is a mandatory loop** — but the loop is on the *report*, not the code:
verification never patches code (see PASS/FAIL criteria below). A missing row gets written; a real
failure sends the ticket back to CODE.

## Verification levels

| Level | Meaning |
|-------|---------|
| ✅ **PASS** | The code implements the criterion AND a test verifies the behavior |
| ⚠️ **WARN** | Code is fine but the test is superficial (status code only), or a non-critical item is missing |
| ❌ **FAIL** | Missing code, missing test, or a failing test |

## Output Format

```
┌─────────────────────────────────────────────────────────┐
│  /daw-verify-module [name] — [PASSED | BLOCKED]          │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  Acceptance criteria:                                    │
│    ✅/❌ [ID] AC-01: [criterion] → [file:function] →     │
│       [test]                                             │
│    ✅/❌ [ID] AC-02: ...                                 │
│                                                          │
│  Spec tasks:                                             │
│    ✅/❌ [ID] Block 1: [X/Y tasks completed]             │
│    ✅/❌ [ID] Block 2: ...                               │
│                                                          │
│  Coverage:                                               │
│    ✅/❌ [ID] Lines: XX% · Branches: XX% · Functions: XX%│
│    ✅/❌ [ID] Sad-path tests                             │
│                                                          │
│  Quality:                                                │
│    ✅/❌ [ID] Lint / type checker                        │
│    ✅/⚠️ [ID] No dead code                               │
│    ✅/⚠️ [ID] No fragile tests                           │
│                                                          │
│  ─────────────────────────────────────────────────────   │
│  Total: X passed, Y failed, Z warnings                   │
│  Result: [PASSED if Y == 0 | BLOCKED if Y > 0]           │
│  Report: docs/daw/reports/verify-[ticket].md             │
│  Full checklist: verify-[ticket].validation.md           │
│  Next: [recommended action] (attempt N/3)                │
└─────────────────────────────────────────────────────────┘
```

Both rows are mandatory: the first is the verdict, the second is the validator's checklist — the
path the script printed, so the user can read every rule instead of asking for it again.

### The verdict document, in the shape the validator reads

The box above is what the USER sees. `docs/daw/reports/verify-{ticket}.md` is what the validator
reads, and it had no canonical shape at all — so a complete verdict could be refused for its layout:
an AC named without its identifier, a block referred to by name only, `sad-path` written with the
hyphen English actually uses. Write it like this:

```markdown
# Verification {ticket}

| Field | Value |
|---|---|
| Module | app/routes/public.py |
| Line coverage | 91% |
| Branch coverage | 84% |
| Function coverage | 88% |
| Coverage floor | 80% (AGENTS.md, "Testing") |
| Lint | `ruff check .` — clean |

## Acceptance criteria
- ✅ AC-01 — `test_form_visible` (app/routes/public.py:12)
- ✅ AC-02 — `test_campo_faltante_devuelve_400`
- ✅ AC-03 — `test_email_invalido_devuelve_422`

## Spec blocks
- ✅ Block 1 — every task done, tests named above

## Tests
- ✅ Sad-path tests: `test_email_invalido_devuelve_422` covers the documented 422 path

Result: PASSED
```

Every AC by its **identifier** (`AC-01`, not "the first criterion"), every block by its **number**,
every test the spec promised by **name**, the three coverage numbers, and the floor quoted from the
project. Those are what F-VER-01 to F-VER-06 look for, one rule each.

For a FIX, the fix-plan's steps and tests take the place of the blocks and the named tests. Each
step by its number as `Step N`, each test by its `test_x` name or, when the plan only describes it,
by its position as `Test N` — the order of the bullets under the fix-plan's `## Tests`:

```markdown
# Verification {ticket}

| Field | Value |
|---|---|
| Module | src/config/loader.ts |
| Line coverage | 95% |
| Branch coverage | 92% |
| Function coverage | 96% |
| Coverage floor | 80% (AGENTS.md, "Testing") |
| Lint | `eslint .` — clean |

## Fix-plan steps
- ✅ Step 1 — only the BOM is stripped (src/config/loader.ts:41)
- ✅ Step 2 — the text read is written back unmodified (src/config/loader.ts:58)

## Fix-plan tests
- ✅ Test 1 — regression: a config with a BOM keeps its trailing newline; red before the fix
- ✅ Test 2 — an unreadable file falls back to the defaults
- ✅ Test 3 — an invalid UTF-8 byte reports its offset (sad path)

Result: PASSED
```

A step or test on a line marked ❌, or carrying `fail`/`error`, reads as not done: write the failing
ones as failing, and describe the passing ones without those words.

## PASS/FAIL criteria
- **PASSED:** 0 FAILs → `gates.verify` = `true`. WARNINGs are reported and do not block.
- **BLOCKED:** 1+ FAILs → go back to the CODE phase to fix. Never patch the code in VERIFY. Max 3
  attempts, then escalate to the user.

For detailed cross-verification, spawn `daw-module-verifier` via the Agent tool — an agent that did
not write the code. That review is owed for every tier, FIX included, and a PASSED receipt does not
replace it: the receipt says the verdict is complete, not that anyone independent has read the code.

## Tier modifier: QUICK-FIX
Does not apply — that tier has no VERIFY phase.

## Updating .daw-state.json
- `gates.verify` → `true` on PASS. The report is saved to `docs/daw/reports/verify-{ticket}.md`
  (derived path), including the WARNINGs that did not block. A BLOCKED run is written too — the
  round that failed is what explains the corrective loop that follows it.

## Language

Write the report in the language the user is working in, citing the rule IDs verbatim.
