# Installing DAW

Two ways in, and the difference is **where the method lives**.

| | Plugin | Drop-in |
|---|---|---|
| The method sits | outside your repo, in the tool | inside your repo, in `.daw/` |
| Your repo gets | your `AGENTS.md`, the artifacts, the state file | that, plus `.daw/` and a wiring directory |
| Upgrading | the tool's plugin update | re-run `install.sh` |
| Editing the method | not until you eject | open the file and change it |
| Your teammates | install the plugin too | get it on clone |

**Start with the plugin.** Drop-in is the right answer once you want to change how the method
works — and `/daw-eject` walks you through it when that day comes, after which plugin updates stop
reaching that repo. That is the trade.

The eject itself is a command **you** run, not something the agent does for you:

```bash
bash "<plugin root>/install.sh" . --method-only
```

Not a limitation of the skill — a consequence of the rule underneath it. Every write into `.daw/` is
refused in every phase, because that seal is what stops a pipeline editing the rules that stop it,
and it cannot tell installing the method apart from disarming it: a fresh `.daw/` with weaker rules
is the same write. So ejecting is what installing and uninstalling already are — something done from
outside the ticket, with the hooks looking on. `--method-only` copies the method, records it in the
manifest so the drift check can see it change afterwards, and touches no wiring.

---

## As a plugin

### Let the installer do it

```
bash install.sh . --mode plugin --target claude,copilot,opencode
```

It calls each tool's own plugin CLI rather than writing that tool's cache layout
itself, and for Copilot it also wires the user-level hooks that the plugin
manifest cannot carry — the step that, skipped, leaves an install looking alive
and enforcing nothing. The marketplace it registers is the organisation's catalog,
`DiluxOne/diluxone-plugins-ai`, so what lands is the version released there; a
change not released yet is tried with `--mode dropin`.

Nothing here needs administrator rights on any platform: every path written is
under `$HOME` or inside the repo you named. Run it before you open the tool and
there is nothing to restart; OpenCode's first launch is slower because that is
when it clones the plugin.

Without `--mode` the installer always asks which of the two you want, whether or
not you named a tool: those are different questions, and the answers leave very
different repositories behind.

`--mode plugin` covers Claude Code, Copilot CLI and OpenCode. For Codex, Cursor
and Gemini it says so and stops — a manifest exists for them in this repository,
but no install procedure for one has been written or driven, and running
something plausible would be worse than saying nothing.

The manual equivalents are below, and are what the installer runs.

### Claude Code

```
/plugin marketplace add DiluxOne/diluxone-plugins-ai
/plugin install daw@diluxone-plugins-ai --scope user
```

DAW is published in the organisation's catalog, `diluxone-plugins-ai`, from this repository; this
repository is not a marketplace of its own. **Added the `dilux` marketplace before?** Remove it
first, `/plugin marketplace remove dilux` (which uninstalls what came from it), then add the
catalog as above.

`--scope user` installs the method to your profile, once: every repo you open has it, and each repo
decides its own behavior from its own context files — a `## Repo family` section makes it part of a
family, no section leaves it standalone, and `claude plugin disable daw` standing in a repo switches
it off there. `--scope project` (recorded in the repo's `.claude/settings.json`, so teammates get it
on clone) and `--scope local` remain the tool's own options for teams that want per-repo activation.

### Copilot CLI and OpenCode

Both need steps of their own, and the reason is worth knowing before you start. Copilot reads the
plugin manifest for its skills and **ignores the hooks in it**, so the gates ride user-level hooks
instead — install the skills and stop, and it looks alive while enforcing nothing. OpenCode
registers the plugin in `opencode.json` and needs a permission for the directory the method lives in.

Both are written out as steps to hand to your agent:
[`.github/INSTALL.md`](../.github/INSTALL.md) · [`.opencode/INSTALL.md`](../.opencode/INSTALL.md)

### Codex CLI and Cursor

Both ship a plugin manifest in this repository and the test suite installs and drives them in that
mode. Nobody has run a full session against either one yet, which is what the README's status
section means by *verified at the boundary*.

### What a plugin install does not do

**The method is never copied into your repo, and no pipeline artifact appears until one starts.**
Clone something to read for five minutes and you get no state file and no edited `.gitignore`. Under
the installer's user-scope activation nothing of DAW is written into the repo at all — Claude,
Copilot and OpenCode all register in your profile. (If you choose Claude's `--scope project`
yourself, the activation lands untracked in the repo's `.claude/settings.json`; commit it when you
want your teammates to have it.)

**The repo always wins.** Every hook looks for `.daw/` in the project first and the plugin second, so
a repo that wants its own version just has one.

**No `AGENTS.md` is created either**, and that file is where DAW reads your stack. Under a drop-in
install the installer copies a template when it finds none; under a plugin no content of DAW's is
copied anywhere in your tree. The first CLASSIFY offers to create it, from what it
can detect in the repo and with none of DAW's own content in it — or you write it yourself first.
Either way the file is yours: DAW never puts its blocks, phases or boilerplate in it under a plugin.

---

## Or into your repository

```bash
cd /path/to/your/project
curl -fsSL https://raw.githubusercontent.com/DiluxOne/dilux-agentic-workflow/main/install.sh | bash -s -- . --target claude
```

The installer copies the method out of its own tree, so pasted from a URL it has no tree: it
fetches one into a temporary directory, runs itself from there and removes it on the way out. It
still asks its questions — every read goes to your terminal, not to the pipe it arrived down.

`DAW_REF` picks what gets fetched (a branch or a tag; `main` by default). If you already have the
repository, run the same script out of it and nothing is downloaded:

```bash
git clone https://github.com/DiluxOne/dilux-agentic-workflow.git

cd /path/to/your/project
bash /path/to/dilux-agentic-workflow/install.sh . --target claude
```

Drop `--target` and it asks. Valid values: `claude`, `codex`, `copilot`, `cursor`, `gemini`,
`opencode`, several separated by commas, or `all`.

Installing **is** activating — there is no separate enable step.

**If the repo is git-tracked, a fresh install asks — before writing a byte —
where the installation lands:**

1. **A new setup branch** (`daw-setup-` + 6 random hex, recommended): created
   on the spot, installed and committed there, your branches untouched. After
   the commit it asks whether to push the branch and open a pull request — not
   a draft one, because it has to be merged before the first ticket; say no and
   the branch stays local, with the merge command printed.
2. **The current branch**, named out loud: installed and committed right there.
3. **Files only**: everything lands, nothing is committed, git stays yours.

Either committing path offers to commit the installation as exactly the paths
its manifest says it wrote, nothing of yours: a file that already had
uncommitted changes before the run is left out and named, for you to review.
The reason the offer exists: an installation that is never committed surfaces
at the first ticket's closeout, whose commit gate demands a clean tree — and
that ticket's pull request ends up carrying the whole framework alongside its
own change. Measured: 68 files of DAW inside a PR about a web form.

A repo with no commits yet skips the branch question (there is no base to
branch from) and offers the installation as the repository's first commit.
Updates skip it too — a refresh is committed where the branch already lives.
Without a terminal the installer asks nothing and touches git not at all; set
`DAW_GIT_FLOW=setup|current|none` (and `DAW_GIT_PUSH=y|n`) to answer the
questions from a script. Not a git repository at all? One warning, dropin
only: the pipeline branches, commits and opens PRs, so `git init` before the
first ticket.

### What lands in your repo

```
.daw/                      THE METHOD — identical for every tool
├── orchestrator.md          the state machine and the phase router
├── rules/                   per-phase instructions + transition-graph.json
└── scripts/                 the transition validator and the shared hook gate

.claude/  .codex/  …       THE WIRING — one per tool you install
├── skills/                  the actions: create-spec, test, security-sast, commit…
├── agents/                  the auditors: architecture, security, verification
└── hooks/                   the enforcement scripts

AGENTS.md                  your project's context — you fill this in
docs/daw/                  everything the pipeline produces, committed
.daw-state.json            the pipeline's memory (gitignored: it is yours)
```

That split is the point. **`.daw/` is byte-identical across tools.** Supporting a new one means
writing a recipe that says where that tool looks for things — never translating the framework. See
[`adapters/adapter.schema.md`](../adapters/adapter.schema.md).

### Upgrading

Pull, re-run the same command. The installer is idempotent, replaces DAW's own files, and **never
overwrites something you made yours**: if one of your skills shares a name with one of DAW's, it says
so and leaves yours alone. Your state, your artifacts under `docs/daw/` and your stack are untouched.

Two things decide what "yours" means:

- **The activation block.** DAW writes a block delimited by `<!-- BEGIN DAW -->` / `<!-- END DAW -->`
  into your tool's context file and refreshes it on every upgrade — that block is what loads the
  orchestrator, so a stale one would quietly run an old method. **Only what is between the markers is
  touched.** Anything you wrote outside it is not read, moved or reformatted.
- **It is always `AGENTS.md`.** DAW's instructions live in that one file whatever tool you installed,
  so it holds both your stack and a managed block. Claude and Gemini read `CLAUDE.md`/`GEMINI.md`
  instead, so those get a four-line pointer and nothing else. Nothing is duplicated, so nothing can
  drift.

### Upgrading from the old name

The product, its plugin and every internal name changed at once (the [CHANGELOG](../CHANGELOG.md)
says from what). A project set up under the old name needs no step of its own:

- **Installed as a plugin:** the first session of the upgraded plugin moves it. It says so once.
- **Copied into the repository:** re-run the installer, as for any upgrade. It moves the project
  first, then upgrades what the old installer put there as its own older copy.

What moves: the state, the paused tickets, the session receipts, the scratch, the journal, the
method's copy, the install record and the artifacts, each to its `.daw-*` or `docs/daw/` name; the
`BEGIN/END` blocks of `.gitignore`, `AGENTS.md`, `CLAUDE.md` and `GEMINI.md`; and, in each tool's
settings, the hook entries that run a file DAW installed. A hook of your own is not touched. The
state keeps its phase, its tier and its gates, and a gate earned before keeps its receipt: a page the
move rewrites (the markers of a managed block) is sealed again, but only on a receipt the journal
shows a validator wrote. The journal gets one line naming what moved.

When a file exists under both names it refuses and changes nothing, because which of the two is the
pipeline is not something to guess: keep one of each pair and run it again,
`python3 <the plugin or .daw>/scripts/migrate_legacy.py --repo .`. Interrupted, the next run
finishes it: every move is a rename, and the state goes last.

### Taking it out

```bash
bash /path/to/dilux-agentic-workflow/uninstall.sh .        # shows the plan, then asks
bash /path/to/dilux-agentic-workflow/uninstall.sh . --plan # just the plan, changes nothing
```

It removes the method, the runtime, each installed tool's wiring, the activation block and the
`.gitignore` rules — **and nothing else**. What is DAW's is read from the manifest, not guessed from
directory names: `.claude/` is Claude Code's directory and your own skills live there too, so they
stay. Your hooks in `settings.json` stay while DAW's are unwired, which matters more than tidiness —
hooks left pointing at deleted scripts fail on every session afterwards.

**`docs/` is never removed.** The PRDs, specs, threat models and verification reports are the record
of what was decided and why. Uninstalling the tool is not a reason to lose them.

A DAW file you have edited since installing is kept and reported; `--force` removes those too.

---

## The file you have to write

`AGENTS.md` is the one part of the install you own — your stack, your architecture conventions, your
domain glossary. **Read [`AGENTS-MD.md`](AGENTS-MD.md) before you edit it.** DAW manages exactly one
block inside that file, and a heading the method looks up and does not find fails **quietly**: the
pipeline runs on, knowing nothing about your project.

## Requirements

- **Python 3** on your PATH — the transition validator and the hook gate.
- **Git.** The pipeline assumes a real repository.
- One of the six supported tools.

> **Codex and Gemini quarantine project hooks.** Both fingerprint what a repo brings and refuse to
> run it until you approve it. Run `/hooks` in either after installing, or the gates are decoration.

## Working in parallel

State is **one per directory**, so two sessions on the same folder will step on each other whichever
tools they are running. Every adapter registers its session and warns you when it sees another one
alive. For real parallelism, give each ticket a worktree — each gets its own state:

```bash
git worktree add ../myapp-FEAT-002 -b feat/FEAT-002
```
