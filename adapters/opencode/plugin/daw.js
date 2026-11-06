// DAW — wiring for OpenCode.
// The METHOD does not live here: it lives in the repo's .daw/. This only plugs it in.
// Equivalent to Claude Code's PreToolUse/PostToolUse/SessionStart hooks.
//
// One file, both of OpenCode's plugin interfaces. V1 calls every named export
// (each must be a function or `{ server: fn }`); V2 runs only the default
// export, `{ id, setup(ctx) }`, and ignores V1's hooks entirely ("V1 plugin
// implementations do not run in V2"). The default carries both: V1 reaches the
// same `DawPlugin` through `server` and loads it once, V2's schema ignores the
// extra key. Only the registration differs; every decision is the same call.
//
// Everything this file does is delegate. The event is built from the tool's own
// arguments and piped to the validator on stdin: that is the only way it can
// judge a write that has not happened yet. Run with stdin closed it sees an
// empty envelope, exits 0, and the `throw` below becomes unreachable.
import { existsSync, readFileSync, readdirSync, realpathSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"
import { execFileSync } from "node:child_process"

// OpenCode's real tool ids (opencode.ai/docs/tools). `apply_patch` is a write
// tool and belongs here; ids that do not exist match nothing and gate nothing.
const WRITE_TOOLS = new Set(["write", "edit", "apply_patch"])
// V2 renamed two of them: `apply_patch` is `patch`, `bash` is `shell`. Both
// spellings stay, so the same file gates whichever version loads it.
const V2_WRITE_TOOLS = new Set(["patch"])
// The post-write net must also watch the shell: `bash` is exactly how a state
// gets forged behind the pre-write hook, and filtering it out meant the one
// check that exists to catch that could never see it.
const POST_TOOLS = new Set([...WRITE_TOOLS, ...V2_WRITE_TOOLS, "bash", "shell"])

// A read-only agent under V2: no edit at all, and a shell only with the user's
// say-so (it runs tests; it must not be the way round the edit rule). V2 reads
// an agent's rules as `permissions`, a list of {action, resource, effect}
// (AgentV2Info, @opencode-ai/sdk v2 types); V1's `permission:` map in the agent
// files is translated to that list, and these join after whatever it holds.
const READONLY_RULES = [
  { action: "edit", resource: "*", effect: "deny" },
  { action: "shell", resource: "*", effect: "ask" },
]
// The installer's rule for which agent writes (scripts/install_target.py):
// one whose source lists any of these tools.
const WRITING_TOOLS = ["Write", "Edit", "NotebookEdit"]

// A V2 tool id may arrive namespaced (`opencode.tool.write`); the last segment
// is the tool. Matching the whole string would gate nothing.
const toolId = (tool) => String(tool ?? "").split(".").pop()

// What both interfaces share: where the method is, how a gate is called, what
// the model is told. Everything version-specific is in how it is registered.
const wire = (directory) => {
  // Repo first, plugin second — the same resolution the Claude plugin's hooks
  // use. A repo that carries its own .daw/ (drop-in, or vendored to diverge)
  // keeps winning; a repo with none gets the method that travels with this
  // file, which is what makes the plugin install real: nothing of DAW's in the
  // repo. The state never moves — it is the project's, wherever the method
  // came from. realpathSync: resolved through a symlink the module URL names
  // the link, and the method must be found next to the real file.
  const here = dirname(realpathSync(fileURLToPath(import.meta.url)))
  const candidates = [
    join(directory, ".daw"),            // drop-in: the repo's own method
    join(here, "..", "..", "..", "daw"), // package layout: adapters/opencode/plugin/ → repo root
    join(here, "..", "daw"),            // global install: ~/.config/opencode/plugins/ → ~/.config/opencode/daw
  ]
  const daw = candidates.find((c) => existsSync(join(c, "scripts", "hook-gate.py"))) ?? candidates[0]
  const state = join(directory, ".daw-state.json")
  // The skills travel next to the method (repo root of the package). The
  // drop-in does not need this — its skills are installed to .opencode/skills,
  // which OpenCode discovers natively — so an absent directory is skipped, not
  // an error.
  const skills = join(daw, "..", "skills")

  // DAW's agents and whether each writes. A drop-in's are the files the
  // installer wrote to .opencode/agents, where a read-only one carries the
  // `edit: deny` it was given; a plugin install has only the packaged sources
  // (agents/ next to the method), judged by their tool list as the installer
  // judges them. The repo's own agents/ is the project's, so a drop-in never
  // reads it. The first file of a name wins: the installed one is what V2 loaded.
  const agents = () => {
    const dirs = [join(directory, ".opencode", "agents")]
    if (daw !== join(directory, ".daw")) dirs.push(join(daw, "..", "agents"))
    const found = new Map()
    for (const dir of dirs) {
      let names = []
      try { names = readdirSync(dir) } catch { continue }
      for (const file of names.sort()) {
        if (!/^daw-.+\.md$/.test(file)) continue
        const id = file.slice(0, -3)
        if (found.has(id)) continue
        const text = readFileSync(join(dir, file), "utf8")
        const m = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?/.exec(text)
        if (!m) continue
        const fm = m[1]
        const tools = /^tools:\s*(.*)$/m.exec(fm)?.[1]
        const readonly = tools !== undefined
          ? !tools.split(/[,\s]+/).some((t) => WRITING_TOOLS.includes(t))
          : /^\s+edit:\s*["']?deny["']?\s*$/m.test(fm)
        const description = /^description:\s*(.+)$/m.exec(fm)?.[1]?.trim().replace(/^["']|["']$/g, "")
        found.set(id, { id, readonly, description, system: text.slice(m[0].length).trim() })
      }
    }
    return [...found.values()]
  }

  // What the model reads before its first turn. Without this, a plugin install
  // enforces but never steers: the gates refuse what phases forbid, while the
  // model — never told the method exists, or where — codes straight from IDLE.
  // Rebuilt per call so the phase is current, marked so it is never doubled.
  // Set when OpenCode reports a compaction, consumed by the next message
  // transform. A flag rather than a print: the event hook's stdout goes to the
  // terminal, and a reminder the model never receives is not a reminder.
  const flags = { compacted: false }

  // The wording is the method's — every tool compacts, and six copies of one
  // paragraph is five nobody would remember to edit.
  const compactionNudge = () => {
    if (!existsSync(join(daw, "orchestrator.md"))) return ""
    try {
      return execFileSync("python3", [boot, "--repo", directory, "--method", daw,
                                      "--compact", "--format", "text"],
                          { stdio: ["ignore", "pipe", "pipe"] }).toString().trim()
    } catch {
      return ""
    }
  }

  const BOOT_MARK = "<DAW_BOOTSTRAP>"
  // A drop-in chose files: its .daw/ and its AGENTS.md block are DAW's by
  // design. Telling that model "do NOT install DAW, never put DAW content in
  // AGENTS.md" contradicts the repo it is looking at, so those two sentences
  // are the plugin install's alone.
  const dropin = daw === join(directory, ".daw")
  const bootstrap = () => {
    if (!existsSync(join(daw, "orchestrator.md"))) return ""
    let status = "There is no .daw-state.json: the pipeline is IDLE — no ticket has been started in this repo."
    try {
      const s = JSON.parse(readFileSync(state, "utf8"))
      status = `Current state: phase ${s.phase}, tier ${s.tier ?? "?"}, ticket ${s.ticket ?? "?"}.`
    } catch {}
    const where = dropin
      ? ["The method is installed in this repo, in .daw/ — read .daw/orchestrator.md and follow its Boot Sequence before doing anything else."]
      : [
        `The method lives at ${daw} — read ${join(daw, "orchestrator.md")} and follow its Boot Sequence before doing anything else.`,
        "The method STAYS with the plugin: do NOT install DAW into this repo — no install.sh, no copying .daw/ or .opencode/. " +
        "Where the method's documents say `.daw/...`, resolve them under the path above. " +
        "Only .daw-state.json, the context file and the phase artifacts (docs/) belong in the repo.",
        "The context file (AGENTS.md) is the PROJECT's, not DAW's: if it is missing, gather the stack and conventions " +
        "from the user and write it as a plain project file. Never put DAW content in it — no DAW blocks, no DAW " +
        "template boilerplate, no references to DAW or its phases. A reader without the plugin must see an ordinary repo.",
      ]
    return [
      BOOT_MARK,
      "This repo is governed by DAW (Dilux Agentic Workflow), a strict state machine over",
      "CLASSIFY → DEFINE → PLAN → CODE → VERIFY → CLOSEOUT, recorded in .daw-state.json at the repo root.",
      ...where,
      status,
      "Work that changes this repo starts by CLASSIFYING it into a ticket (the daw-* skills exist for each phase) — never by writing code first.",
      "Any message starting with `DAW:` comes from the plugin's gates, not from the user. Obey it literally — especially STOP instructions.",
      "</DAW_BOOTSTRAP>",
    ].join("\n")
  }
  const graph = join(daw, "rules", "transition-graph.json")
  const gate = join(daw, "scripts", "hook-gate.py")
  const boot = join(daw, "scripts", "session-boot.py")

  // DAW is installed when the gate is there. Requiring the state file too
  // meant that before the first transition — or after someone deleted it —
  // nothing was enforced at all, and the first write could fabricate any state
  // it liked. An absent state is IDLE, and IDLE is a phase like any other.
  const installed = () => existsSync(gate)

  // OpenCode names a write's arguments differently per tool; the shared gate
  // knows all the spellings, so pass them through untouched.
  const envelope = (tool, args = {}) => JSON.stringify({
    tool_name: tool,
    tool_input: args,
  })

  const runGate = (mode, payload) =>
    execFileSync("python3", [gate, "--dialect", "standard", "--mode", mode,
                             "--state", state, "--graph", graph, "--repo", directory,
                             "--method", daw], {
      input: payload ?? "",
      stdio: ["pipe", "pipe", "pipe"],
    })

  // The session boot, whichever interface reported the session. Its stdout
  // reaches the terminal, not the model: the bootstrap is what steers.
  const sessionBoot = (sid) => {
    if (!existsSync(join(daw, "orchestrator.md"))) return
    try {
      const out = execFileSync("python3", [boot, "--repo", directory, "--session-id", sid], {
        stdio: ["ignore", "pipe", "pipe"],
      }).toString().trim()
      if (out) console.log(out)
    } catch (e) {
      console.error(`DAW: could not run the session boot. ${(e.stderr?.toString() || "").trim()}`)
    }
  }

  // The user took a turn: the counter the commit gate waits on moves. Like
  // Claude's user-turn.sh it decides nothing, prints nothing and fails OPEN —
  // refusing the user's own message over bookkeeping would be the bigger fault.
  const userTurn = () => {
    if (!installed()) return
    try {
      execFileSync("python3", [gate, "--mode", "turn", "--state", state, "--graph", graph,
                               "--repo", directory], { stdio: ["ignore", "ignore", "ignore"] })
    } catch {}
  }

  return { daw, state, skills, agents, flags, BOOT_MARK, bootstrap, compactionNudge, installed,
           envelope, runGate, sessionBoot, userTurn }
}

export const DawPlugin = async ({ directory }) => {
  const { skills, flags, BOOT_MARK, bootstrap, compactionNudge, installed, envelope, runGate,
          sessionBoot } = wire(directory)

  return {
    // Registers the packaged skills with OpenCode's native discovery — the
    // same move Superpowers makes. Without it the bootstrap tells the model to
    // classify and gives it nothing to do it with.
    config: async (config) => {
      if (!existsSync(skills)) return
      config.skills = config.skills || {}
      config.skills.paths = config.skills.paths || []
      if (!config.skills.paths.includes(skills)) config.skills.paths.push(skills)
    },

    // The bootstrap rides as a prefix on the session's first user message —
    // not the system prompt, which is re-sent every turn, and not the session
    // event's stdout, which reaches the terminal but never the model.
    "experimental.chat.messages.transform": async (_input, output) => {
      if (!output?.messages?.length) return

      // The post-compaction reminder rides the NEWEST user message: the summary
      // it corrects sits behind that turn, and the first message may no longer
      // be in the context at all.
      if (flags.compacted) {
        const users = output.messages.filter((m) => m.info?.role === "user")
        const last = users[users.length - 1]
        if (last?.parts?.length) {
          const text = compactionNudge()
          if (text) {
            last.parts.unshift({ ...last.parts[0], type: "text", text })
            flags.compacted = false
          }
        }
      }

      const text = bootstrap()
      if (!text) return
      const firstUser = output.messages.find((m) => m.info?.role === "user")
      if (!firstUser || !firstUser.parts?.length) return
      if (firstUser.parts.some((p) => p.type === "text" && p.text?.includes(BOOT_MARK))) return
      const ref = firstUser.parts[0]
      firstUser.parts.unshift({ ...ref, type: "text", text })
    },

    // OpenCode has no "session.created" hook — that string is an event TYPE,
    // delivered through the generic `event` hook. Registered under the wrong
    // key it was never called, so the pipeline never booted, no state file was
    // ever created, and `installed()` stayed false: every write was allowed.
    event: async ({ event }) => {
      // Compaction drops the middle of the conversation, and what it drops is
      // the boot: the router and the state the model read at the start. It goes
      // on answering from a summary of the pipeline instead of the pipeline.
      // The reminder cannot be printed here — this hook's stdout reaches the
      // terminal and never the model — so it is flagged and rides the next user
      // message, the one channel to the model this plugin has.
      if (event?.type === "session.compacted") {
        flags.compacted = true
        return
      }
      if (event?.type !== "session.created") return
      sessionBoot(String(event?.properties?.info?.id ?? event?.properties?.sessionID
                         ?? `opencode-${process.pid}`))
    },

    // Before every write: validate the transition against the graph.
    // Throwing = blocking the operation (equivalent to Claude Code's exit 2).
    "tool.execute.before": async (input, output) => {
      if (!WRITE_TOOLS.has(input?.tool)) return
      if (!installed()) return
      try {
        runGate("pre", envelope(input.tool, output?.args ?? {}))
      } catch (e) {
        const reason = (e.stderr?.toString() || e.stdout?.toString() || "").trim()
        throw new Error(`DAW blocked the write.\n${reason}`)
      }
    },

    // After writing: revalidate the state on disk (the net under the net).
    "tool.execute.after": async (input) => {
      if (!POST_TOOLS.has(input?.tool)) return
      if (!installed()) return
      try {
        runGate("post", "")
      } catch (e) {
        const reason = (e.stderr?.toString() || "").trim()
        // A write that already landed cannot be undone from here, but leaving
        // it unmentioned would let an inconsistent state look accepted.
        throw new Error(`DAW: the state on disk is now inconsistent.\n${reason}`)
      }
    },
  }
}

// OpenCode V2. The same gates, registered through the context V2 hands its
// plugins. A domain the running build does not have is skipped rather than
// dereferenced: one missing domain must not take the others down with it.
const setup = async (ctx) => {
  const directory = ctx?.location?.directory ?? process.cwd()
  const { skills, agents, flags, BOOT_MARK, bootstrap, compactionNudge, installed, envelope,
          runGate, sessionBoot, userTurn } = wire(directory)
  const writes = (tool) => WRITE_TOOLS.has(tool) || V2_WRITE_TOOLS.has(tool)

  // A skipped domain is said once, on stderr: a plugin that loads and
  // enforces nothing must not look the same as one that enforces its gates.
  // The only published V2 build (0.0.0-dev-202610280534) offers neither.
  if (typeof ctx?.tool?.hook !== "function")
    console.error("DAW: this OpenCode V2 build offers plugins no tool hook; DAW's write gates are NOT enforced.")
  if (typeof ctx?.session?.hook !== "function")
    console.error("DAW: this OpenCode V2 build offers plugins no session hook; DAW's user-turn counter and bootstrap are NOT applied.")

  // Before every write. In V2 only `execute.before` may reject, and a
  // rejection fails that call alone, which is Claude Code's exit 2.
  await ctx?.tool?.hook?.("execute.before", async (event) => {
    const tool = toolId(event?.tool)
    if (!writes(tool)) return
    if (!installed()) return
    try {
      runGate("pre", envelope(tool, event?.input ?? {}))
    } catch (e) {
      const reason = (e.stderr?.toString() || e.stdout?.toString() || "").trim()
      throw new Error(`DAW blocked the write.\n${reason}`)
    }
  })

  // After a write or a shell: revalidate the state on disk. V2's `after`
  // cannot reject — a throw there is only logged — so the verdict goes where
  // the model reads it, appended to the tool's own result.
  await ctx?.tool?.hook?.("execute.after", async (event) => {
    if (!POST_TOOLS.has(toolId(event?.tool))) return
    if (!installed()) return
    try {
      runGate("post", "")
    } catch (e) {
      const reason = (e.stderr?.toString() || "").trim()
      const text = `DAW: the state on disk is now inconsistent.\n${reason}`
      if (event.status === "error") {
        console.error(text)
        return
      }
      event.result = appendText(event.result, text)
    }
  })

  // V2's destination for V1's `chat.message`: the user's own turn.
  await ctx?.session?.hook?.("prompt", async () => {
    userTurn()
  })

  // What the model reads. V2 rebuilds the request on every model call and
  // hands it here, so the mark is what keeps the bootstrap from doubling.
  await ctx?.session?.hook?.("context", async (event) => {
    const users = (event?.messages ?? []).filter((m) => m?.role === "user")
    if (!users.length) return
    const said = (m, mark) => (m.content ?? []).some((p) => p?.type === "text" && p.text?.includes(mark))
    const prefix = (m, text) => { m.content = [{ type: "text", text }, ...(m.content ?? [])] }
    if (flags.compacted) {
      const text = compactionNudge()
      if (text) {
        prefix(users[users.length - 1], text)
        flags.compacted = false
      }
    }
    const text = bootstrap()
    if (!text || said(users[0], BOOT_MARK)) return
    prefix(users[0], text)
  })

  // The session boot and the compaction arrive as events, on a stream that
  // lives as long as the plugin. Not awaited: `setup` has to return.
  const events = ctx?.event?.subscribe?.({ types: ["session.created", "session.compaction.ended"] })
  if (events?.[Symbol.asyncIterator]) {
    ;(async () => {
      for await (const ev of events) {
        if (ev?.type === "session.compaction.ended") flags.compacted = true
        if (ev?.type !== "session.created") continue
        const data = ev?.data ?? ev?.properties ?? ev
        sessionBoot(String(data?.sessionID ?? data?.id ?? `opencode-${process.pid}`))
      }
    })().catch(() => {})
  }

  // The read-only agents, in V2's own terms. Without the shell rule a verifier
  // under V2 has an unrestricted shell, which is an edit by another name. A
  // plugin install ships no agent files, so the verifier VERIFY spawns is added
  // from its packaged source; `update` on an id the draft does not have creates
  // it, as V2's own config-agent does.
  await ctx?.agent?.transform?.((draft) => {
    if (typeof draft?.update !== "function") return
    for (const agent of agents()) {
      if (!agent.readonly) continue
      const present = draft.get?.(agent.id) !== undefined
      if (!present && agent.id !== "daw-module-verifier") continue
      draft.update(agent.id, (info) => {
        if (!present) {
          info.mode = "subagent"
          if (agent.description) info.description = agent.description
          if (agent.system) info.system = agent.system
        }
        if (!Array.isArray(info.permissions)) info.permissions = []
        // A drop-in's own `edit: deny` already arrives translated; the same
        // rule twice would only make the list harder to read.
        const has = (r) => info.permissions.some((p) =>
          p?.action === r.action && p?.resource === r.resource && p?.effect === r.effect)
        info.permissions.push(...READONLY_RULES.filter((r) => !has(r)).map((r) => ({ ...r })))
      })
    }
  })
  // A transform registered from `setup` joins the domain's next rebuild, and
  // the agents were already built by then: driven against OpenCode
  // 0.0.0-dev-202610280534, the rules never reached `/api/agent` until a reload.
  await ctx?.agent?.reload?.()

  // The packaged skills, through V2's skill domain. A drop-in has none to add:
  // its skills sit in .opencode/skills, which V2 discovers on its own.
  await ctx?.skill?.transform?.((editor) => {
    if (!existsSync(skills)) return
    if (typeof editor?.source === "function") {
      editor.source({ type: "directory", path: skills })
      return
    }
    if (typeof editor?.add !== "function") return
    for (const name of readdirSync(skills)) {
      const file = join(skills, name, "SKILL.md")
      if (!existsSync(file) || editor.get?.(name)) continue
      const text = readFileSync(file, "utf8")
      const description = /^description:\s*(.+)$/m.exec(text)?.[1]?.replace(/^["']|["']$/g, "")
      editor.add({ id: name, name, description, path: file, content: text })
    }
  })
  // The same late registration as the agents'.
  await ctx?.skill?.reload?.()
}

// A V2 tool result carries its text as a string or as a list of parts; the
// verdict joins whichever it is, so the model reads the tool's output and
// DAW's message together.
const appendText = (result, text) => {
  const content = result?.content
  if (Array.isArray(content)) return { ...result, content: [...content, { type: "text", text }] }
  if (typeof content === "string") return { ...result, content: `${content}\n\n${text}` }
  const output = result?.output
  const shown = output === undefined ? "" : typeof output === "string" ? output : JSON.stringify(output)
  return { ...result, content: shown ? `${shown}\n\n${text}` : text }
}

export default { id: "daw", server: DawPlugin, setup }
