---
name: hermes-delegate-task
description: Route Hermes `delegate_task(background=True)` to named, persistent AgentMint subagents — specialists that accumulate `/workspace/MEMORY.md` across calls. After `pip install agentmint-hermes-runner` and a one-time `agentmint-hermes-init`, the adapter auto-wires at every Hermes boot. Catch-all default via `general-worker`; per-call specialist routing via `toolsets=["agentmint-<name>"]`.
version: 0.10.0
author: AgentMint
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [Subagents, Delegation, Payments, Sandbox]
    related_skills: [stripe-link-cli]
---

# AgentMint × Hermes

Bridges Hermes' `delegate_task(background=True)` to **named, persistent AgentMint subagents** — sandboxed Upstash Box runs whose `/workspace/MEMORY.md` accumulates context across every dispatch. Subagents hibernate to zero between calls; billed only when running.

## When to use

- Hermes' session needs **specialists** that accumulate domain knowledge across days/weeks (code reviewer, data analyst, support agent, codebase oracle, ...) → pre-mint per specialist, the LLM addresses each by name.
- You want `delegate_task(background=True)` to dispatch the actual work to an isolated sandbox with its own MEMORY, not into the Hermes gateway itself.
- You want predictable per-call cost (BYOK $0.02 flat or all-inclusive actual-cost + $0.02 platform fee) from a server-side credit wallet you fund once via any rail.

Not the right tool when:

- The task is one-shot and Hermes can answer directly.
- You need cross-subagent shared state (each subagent's MEMORY is its own).

## Routing model

Two surfaces, never conflated.

| Surface | Role |
|---|---|
| **`default_agent_name="general-worker"`** | Catch-all for unrouted delegations. The default is a **generic** worker — its job is "send any background offload here, accumulate the session breadcrumb." |
| **`toolsets=["agentmint-<name>"]`** | Per-call specialist routing. The LLM includes this in the toolsets list to send a particular call to a particular pre-minted expert. Each specialist has its own MEMORY.md. |

**Pattern discipline:** never name a specialist as `default_agent_name`. Specialists go through the toolsets directive; the default slot is generic. Naming a specialist as the default breaks the moment you add a second specialist.

## Operator setup

```bash
# 1. Install the runner inside Hermes' Python environment
pip install agentmint-hermes-runner

# 2. One-time bootstrap — interactive
agentmint-hermes-init
#    → picks a payment rail (link-cli / tempo-request / agentcash)
#    → tops up ≥ $1 (default $5)
#    → caches JWT to ~/.agentmint/credentials.json
#    → mints `general-worker` (the catch-all)

# 3. Restart Hermes
#    The runner's `hermes_agent.plugins` entry-point fires at boot,
#    reads the cached JWT, and auto-wires `delegate_task`. No edits to
#    Hermes' startup script needed.
```

After step 3, from Hermes:

```
> delegate this in the background via delegate_task:
  "say hello and tell me what you remember."
```

You should see the call dispatched to `general-worker`, polled until done, then re-injected as a new Hermes turn.

## Adding specialists

Specialists are pre-minted **separately** — not by `agentmint-hermes-init`. Use `curl` (or the agentmint CLI) per specialist:

```bash
JWT=$(jq -r '.tokens | to_entries[0].value.access_token' ~/.agentmint/credentials.json)

curl -X POST https://api.agentmint.store/a2a \
  -H "Authorization: Bearer $JWT" \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"agent.create","params":{
    "name":"<specialist-name>",
    "mode":"all-inclusive",
    "persona":"<what this specialist does>",
    "skills":["<optional GitHub skills>"]
  }}'
```

Cost: $0.10 per specialist mint. After it exists, the Hermes LLM addresses it by including `agentmint-<specialist-name>` in `toolsets`. The LLM only knows about specialists you tell it about — list them in the Hermes session persona.

## How the Hermes LLM uses this

After the operator setup above, the LLM has two patterns at its disposal:

**Pattern A — unrouted (lands in `general-worker`):**

```python
delegate_task(
    background=True,
    goal="Summarize the contents of /workspace/notes.md",
    toolsets=["terminal", "file"],
)
```

**Pattern B — routed to a specialist:**

```python
delegate_task(
    background=True,
    goal="Review the diff",
    toolsets=["terminal", "file", "agentmint-<specialist-name>"],
)
```

The runner parses `agentmint-<name>` out of the list, routes that call to that subagent, strips the entry before composing the prompt the subagent receives. First `agentmint-*` match wins; additional entries are logged + ignored.

This `toolsets` smuggling is a workaround for Hermes' `delegate_task` not having a first-class dispatcher argument — see `docs/hermes-feature-request.md` in the [agentmint-hermes](https://github.com/mesutcelik/agentmint-hermes) repo for the upstream proposal. Once Hermes adds a `dispatcher` or `metadata` parameter, the workaround will be deprecated in favor of the first-class arg.

## Hermes coverage (runner v0.10.x)

Audited against the live Hermes delegation docs. Status notation: ✅ supported, ✅ soft hint = prompt-level only (sandbox can't structurally enforce), ❌ not implemented, n/a = different model that doesn't reach us.

### Call parameters

| Hermes feature | Status | Notes |
|---|---|---|
| `goal` | ✅ | Concatenated under `## Goal` in the synthesized prompt. |
| `context` | ✅ | Concatenated under `## Context`. |
| `toolsets=["terminal", "file"]` | ✅ soft hint | Prompt restriction lines ("Do not run shell commands"). |
| `toolsets=["web"]` | ❌ | Raises `UnsupportedToolset`. |
| `toolsets=["agentmint-<name>", ...]` | ✅ (workaround) | **Routing directive** — adapter parses `agentmint-<name>`, dispatches to that subagent, strips entry from toolsets. Upstream Hermes proposal filed; the directive becomes a first-class parameter once that lands. |
| `role="leaf"` / `"orchestrator"` | ✅ soft hint | Prompt-level only. |
| `max_iterations` | ✅ soft hint | Harness-dependent enforcement. |
| `tasks=[{...}, {...}]` batch | ✅ | `dispatch_batch` — ThreadPoolExecutor; results in input order. |
| `background=True` (PR #40946) | ✅ | The path the runner patches. |
| `workspace_files=[{path, content}, ...]` | ✅ | Files written into the sandbox before the run starts; max 10 files, 10 MB each. |

### Hermes config knobs (`~/.hermes/config.yaml` under `delegation:`)

| Hermes feature | Status | Notes |
|---|---|---|
| `max_concurrent_children` | ✅ | `max_concurrent_children=N` on `dispatch_batch` (default 3). |
| `child_timeout_seconds` | ✅ | Floor 30s; fires `agent.cancel` on expiry. |
| `max_spawn_depth` | n/a | AgentMint sandboxes aren't structurally depth-bounded. |
| `orchestrator_enabled` | n/a | Hermes-level kill switch. |
| `api_mode` / `model` / `provider` / `base_url` / `api_key` | n/a | AgentMint subagents use server-managed stored keys (provider + model chosen at `agent.create` time). |
| `subagent_auto_approve` | n/a | AgentMint runs each box in its own isolated VM; no parent TUI. |

### Lifecycle + interrupt

| Hermes feature | Status | Notes |
|---|---|---|
| `delegate_task` blocks parent turn unless `background=True` | ✅ | Sync mirrors: `dispatch()` blocks until completion. |
| Interrupt cascade (parent `/stop` cancels all children) | ✅ | `cancel_event=threading.Event` fires `agent.cancel`. |
| Status `"interrupted"` on parent interrupt | ✅ | `DispatchResult.status="interrupted"`. |
| Hard-timeout diagnostic dumps | ❌ | The runner raises `DispatchTimeout`; no log file written. |

### Subagent restrictions

| Hermes feature | Status | Notes |
|---|---|---|
| Leaf-blocked tools (`delegation` / `clarify` / `memory` / `code_execution` / `send_message`) | n/a | AgentMint sandboxes don't expose Hermes' tool registry. Soft prompt hint only. |
| Orchestrator-blocked tools | n/a | Same. |
| Fresh conversation per call ("subagents know nothing") | **inverted** | This inversion is the AgentMint value prop — `/workspace/MEMORY.md` survives every dispatch to a named subagent. |
| Credential inheritance | **different model** | Hermes: subagents inherit parent's API key. AgentMint: each sandbox uses AgentMint's server-managed stored keys — no parent credential leakage. |

## Fleet management

The Hermes LLM can run any AgentMint method through its `terminal` tool — `agent.list`, `agent.create`, `agent.delete`, etc. — by sending a curl with `Authorization: Bearer <JWT from credentials.json>`. See https://agentmint.store/SKILL.md for the full method surface.

## Pitfalls

- **One JWT per principal**, shared across every subagent that principal owns. Loss = `credits.rekey` ($0.01 over x402/Tempo MPP) or fresh `credits.topup` over Stripe-Link.
- **`name` is global + immutable.** First mint wins. Pick something specific (`reviewer-mesutcelik-mono`, not `reviewer`). Released only by `agent.delete`.
- **Per-call pricing is end-of-run debit.** BYOK: flat $0.02. All-inclusive: actual provider cost (cache-aware estimate) + $0.02 platform fee.
- **Stripe topup carries a passthrough fee.** A $5 Stripe topup charges ~$5.30 on Stripe; wallet is credited $5.00. x402 and Tempo MPP settle 1:1.
- **Concurrency gate**: balance < $1 → 1 in-flight run per principal; ≥ $1 → 5. Topup to unlock parallel delegations.
- **Don't name a specialist as `default_agent_name`.** See routing-model section above.
- **Multiple cached JWTs**: if `~/.agentmint/credentials.json` has more than one principal, the autoload picks the first. Set `AGENTMINT_JWT` explicitly to disambiguate.

## Verification

```bash
# Adapter is installed + entry-point discoverable
python -c "
import importlib.metadata as m
print([(e.name, e.value) for e in m.entry_points(group='hermes_agent.plugins')])
"
# Expect: [('agentmint', 'agentmint_hermes_runner.autoload')]

# Endpoint reachable
curl -X POST https://api.agentmint.store/a2a \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"agent.create","params":{}}'
# Expect: 402 with accepts[] enumerating supported rails
```

## Example use case — code-review specialist

The pattern below is one concrete way to use the skill; nothing about it is built into the runner. Use it as a reference for shaping your own specialists.

```bash
# 1. Mint a code-review specialist on top of the operator setup above
curl -X POST https://api.agentmint.store/a2a \
  -H "Authorization: Bearer $JWT" \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"agent.create","params":{
    "name":"pr-reviewer",
    "mode":"all-inclusive",
    "persona":"You review GitHub PRs. Follow the pr-review skill exactly.",
    "skills":["mesutcelik/agentmint-skills/pr-review"]
  }}'
```

```
# 2. Tell the Hermes LLM the specialist exists (in the session persona):
You have one background specialist via delegate_task: `pr-reviewer` —
reviews GitHub PRs. To dispatch, include "agentmint-pr-reviewer" in
toolsets and ship the GitHub PAT via workspace_files.
```

```
# 3. From the chat:
> review PR 42 in owner/repo. Background it via delegate_task with the
  pr-reviewer specialist; ship the GH PAT.
```

The LLM dispatches:

```python
delegate_task(
    background=True,
    goal="Review PR 42 in owner/repo",
    toolsets=["terminal", "file", "agentmint-pr-reviewer"],
    workspace_files=[{"path": "/workspace/.github_pat", "content": "<PAT>"}],
)
```

The runner intercepts, routes to the `pr-reviewer` subagent, polls until done, re-injects the result into Hermes. The pr-review skill itself (`mesutcelik/agentmint-skills/pr-review`) is a separate skill — see its own SKILL.md for what the specialist actually does inside the box.

This use case is illustrative — adapt the pattern (different specialist, different skill, different goal shape) to whatever your Hermes session needs.
