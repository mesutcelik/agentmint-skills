---
name: hermes-delegate-task
description: Teach the Hermes LLM the AgentMint routing convention. When the LLM includes `"agentmint-<subagent-name>"` in `delegate_task`'s `toolsets` list, the patched dispatcher routes that background call to a pre-minted AgentMint subagent (sandboxed, persistent MEMORY.md, pay-as-you-go USDC). Without the directive, `delegate_task` falls through to Hermes-native — AgentMint is strictly opt-in.
version: 0.12.0
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

## Routing model — strictly opt-in

The runner patches `delegate_task` to recognize a routing directive in the `toolsets` argument:

- LLM includes `"agentmint-<subagent-name>"` in `toolsets` → call routes to that AgentMint subagent
- LLM does NOT include the directive → call falls through to Hermes-native `delegate_task` untouched

There is no catch-all. AgentMint is never selected transparently; the LLM has to consciously emit the directive on each call where AgentMint is appropriate.

### When the LLM should use the directive

The LLM should dispatch to an AgentMint subagent when the task matches a pre-minted specialist's purpose. The operator pre-mints subagents per use case (PR reviewer, data analyst, support triager, codebase oracle, etc.) and tells the LLM what's available — either by extending the Hermes session persona, or by letting the LLM discover available specialists via `agent.list` over the AgentMint API.

The convention:

```python
delegate_task(
    background=True,
    goal="<what the specialist should do>",
    toolsets=["terminal", "file", "agentmint-<specialist-name>"],
    workspace_files=[...],   # optional — ship secrets/inputs into the box
)
```

The adapter parses `agentmint-<name>` out of the list, dispatches to that subagent, strips the directive from the toolsets before composing the prompt the subagent receives. First `agentmint-*` match wins; additional entries are logged + ignored.

## Operator setup

```bash
# 1. Install the runner
pip install agentmint-hermes-runner

# 2. Bootstrap a Bearer JWT via the AgentMint API. Any rail works
#    (Stripe-Link / x402 Base / Tempo MPP). The full per-rail flow
#    is documented at https://agentmint.store/SKILL.md.
#    Then expose the JWT to Hermes — either as an env var…
export AGENTMINT_JWT=<the access_token>
#    …or cache it to ~/.agentmint/credentials.json (see "JWT cache
#    file shape" section below).

# 3. Install this skill so the LLM knows the routing convention
hermes skills install mesutcelik/agentmint-skills/hermes-delegate-task

# 4. Mint your subagents — one curl per use case
JWT=$AGENTMINT_JWT
curl -X POST https://api.agentmint.store/a2a \
  -H "Authorization: Bearer $JWT" \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"agent.create","params":{
    "name":"<specialist-name>",
    "mode":"all-inclusive",
    "persona":"<what this subagent does>",
    "skills":["<optional skill refs>"]
  }}'

# 5. Restart Hermes — the autoload entry-point attaches the patch at boot
```

That's the entire wiring. The runner installs a `hermes_agent.plugins` entry-point; Hermes' plugin discovery calls it at gateway boot; the patch installs in opt-in mode automatically.

### JWT cache file shape

If you prefer the cache file over an env var (survives shell restarts; same format the agentmint CLI uses), write it at `~/.agentmint/credentials.json`:

```json
{
  "tokens": {
    "link_stripe:cus_…": {
      "access_token": "eyJhbGciOiJI…",
      "saved_at": 1782152633
    }
  }
}
```

Perms: `0700` on the directory, `0600` on the file. The autoload picks the first token in the map; set `AGENTMINT_JWT` explicitly to disambiguate when multiple principals are cached.

If the LLM ever forgets the routing directive (or the user asks for a non-AgentMint task), the call simply falls through to Hermes-native `delegate_task`. AgentMint is never "stuck on" — it's a tool the LLM picks when appropriate.

## How the Hermes LLM uses this (LLM-facing instructions)

After the operator has minted one or more subagents and made the LLM aware of them (via session persona or by listing them via `agent.list`), the dispatch pattern is:

```python
delegate_task(
    background=True,
    goal="Review the diff in /workspace/pr-42",
    toolsets=["terminal", "file", "agentmint-<one-of-your-subagent-names>"],
)
```

Multiple subagents → one per call:

```python
delegate_task(background=True, goal="...", toolsets=["agentmint-reviewer-myrepo", ...])
delegate_task(background=True, goal="...", toolsets=["agentmint-data-analyst", ...])
delegate_task(background=True, goal="...", toolsets=["agentmint-slack-bot", ...])
```

Each subagent maintains its own `/workspace/MEMORY.md` — accumulating domain knowledge across calls. Memory persists across days/weeks/hibernation until `agent.delete`.

### Shipping per-call inputs to the box

When the specialist needs secrets (API tokens, PATs) or input files, ship them via `workspace_files`:

```python
delegate_task(
    background=True,
    goal="Review PR <N> in <owner>/<repo>. Post a short comment.",
    toolsets=["terminal", "file", "agentmint-pr-reviewer"],
    workspace_files=[
        {"path": "/workspace/.github_pat", "content": "<the PAT>"}
    ],
)
```

Files are written into the sandbox before the run starts. Max 10 files, 10 MB each. Don't embed secrets in `goal` or `context` — they get logged.

## Hermes coverage (runner v0.11.x)

| Hermes feature | Status | Notes |
|---|---|---|
| `goal` | ✅ | Concatenated under `## Goal` in the synthesized prompt. |
| `context` | ✅ | Concatenated under `## Context`. |
| `toolsets=["terminal", "file"]` | ✅ soft hint | Prompt restriction lines. |
| `toolsets=["web"]` | ❌ | Raises `UnsupportedToolset`. |
| `toolsets=["agentmint-<name>", ...]` | ✅ | **Routing directive** — adapter parses, dispatches, strips. First `agentmint-*` wins. |
| `role="leaf"` / `"orchestrator"` | ✅ soft hint | Prompt-level only. |
| `max_iterations` | ✅ soft hint | Harness-dependent enforcement. |
| `tasks=[{...}, {...}]` batch | ✅ | `dispatch_batch` — ThreadPoolExecutor; results in input order. |
| `background=True` (PR #40946) | ✅ | The path the runner patches. |
| `workspace_files` | ✅ | Files written into sandbox before run; max 10 × 10 MB. |

### Hermes config knobs (`~/.hermes/config.yaml` under `delegation:`)

| Hermes feature | Status | Notes |
|---|---|---|
| `max_concurrent_children` | ✅ | `max_concurrent_children=N` on `dispatch_batch` (default 3). |
| `child_timeout_seconds` | ✅ | Floor 30s; fires `agent.cancel` on expiry. |
| `max_spawn_depth` | n/a | AgentMint sandboxes aren't structurally depth-bounded. |
| `orchestrator_enabled` | n/a | Hermes-level kill switch. |
| `api_mode` / `model` / `provider` / `base_url` / `api_key` | n/a | AgentMint subagents use server-managed stored keys. |
| `subagent_auto_approve` | n/a | AgentMint runs each box in its own isolated VM. |

### Lifecycle + interrupt

| Hermes feature | Status | Notes |
|---|---|---|
| `delegate_task` blocks parent turn unless `background=True` | ✅ | Sync mirrors: `dispatch()` blocks until completion. |
| Interrupt cascade (parent `/stop` cancels all children) | ✅ | `cancel_event=threading.Event` fires `agent.cancel`. |
| Status `"interrupted"` on parent interrupt | ✅ | `DispatchResult.status="interrupted"`. |
| Hard-timeout diagnostic dumps | ❌ | Runner raises `DispatchTimeout`; no log file. |

### Subagent restrictions

| Hermes feature | Status | Notes |
|---|---|---|
| Leaf-blocked tools | n/a | AgentMint sandboxes don't expose Hermes' tool registry. Soft prompt hint only. |
| Orchestrator-blocked tools | n/a | Same. |
| Fresh conversation per call ("subagents know nothing") | **inverted** | The AgentMint value prop — `/workspace/MEMORY.md` survives every dispatch to a named subagent. |
| Credential inheritance | **different model** | AgentMint sandboxes use AgentMint's server-managed stored keys; no parent leakage. |

## Fleet management

The Hermes LLM can run any AgentMint method through its `terminal` tool — `agent.list`, `agent.create`, `agent.delete`, etc. — by sending a curl with `Authorization: Bearer <JWT from credentials.json>`. See https://agentmint.store/SKILL.md for the full method surface.

To discover available specialists from inside Hermes:

```bash
JWT=$(jq -r '.tokens | to_entries[0].value.access_token' ~/.agentmint/credentials.json)
curl -X POST https://api.agentmint.store/a2a \
  -H "Authorization: Bearer $JWT" -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"agent.list","params":{}}' \
  | jq '.result.agents[] | {name, persona}'
```

The LLM can pattern-match `name` against the goal at hand to pick the right specialist.

## Pitfalls

- **The skill is REQUIRED for the LLM to use AgentMint.** Without it, the LLM has no idea the toolsets directive exists and will never dispatch to AgentMint.
- **One JWT per principal**, shared across every subagent that principal owns. Loss = `credits.rekey` ($0.01 over x402/Tempo MPP) or fresh `credits.topup` over Stripe-Link.
- **`name` is global + immutable.** First mint wins. Pick something specific (`reviewer-mesutcelik-mono`, not `reviewer`).
- **Per-call pricing is end-of-run debit.** BYOK: flat $0.02. All-inclusive: actual provider cost (cache-aware estimate) + $0.02 platform fee.
- **Stripe topup carries a passthrough fee.** A $5 Stripe topup charges ~$5.30 on Stripe; wallet is credited $5.00. x402 and Tempo MPP settle 1:1.
- **Concurrency gate**: balance < $1 → 1 in-flight run per principal; ≥ $1 → 5. Topup to unlock parallel delegations.
- **Multiple cached JWTs**: if `~/.agentmint/credentials.json` has more than one principal, the autoload picks the first. Set `AGENTMINT_JWT` explicitly to disambiguate.
- **Catch-all override** (rarely needed): set `$AGENTMINT_DEFAULT_AGENT_NAME` in Hermes' env to a pre-minted subagent name. This restores 0.10.x's transparent-substrate behavior for that deployment.

## Verification

```bash
# Adapter installed + plugin discoverable
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
# 1. Mint the specialist
JWT=$(jq -r '.tokens | to_entries[0].value.access_token' ~/.agentmint/credentials.json)
curl -X POST https://api.agentmint.store/a2a \
  -H "Authorization: Bearer $JWT" \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"agent.create","params":{
    "name":"pr-reviewer",
    "mode":"all-inclusive",
    "persona":"You review GitHub PRs. Follow the pr-review skill exactly.",
    "skills":["mesutcelik/agentmint-skills/pr-review"]
  }}'

# 2. In Hermes session persona / system prompt, tell the LLM the specialist exists:
You have a pr-reviewer specialist available via delegate_task. To dispatch:

    delegate_task(
        background=True,
        goal="Review PR <N> in <owner>/<repo>",
        toolsets=["terminal", "file", "agentmint-pr-reviewer"],
        workspace_files=[{"path": "/workspace/.github_pat", "content": "<PAT>"}],
    )

# 3. From the chat:
> review PR 42 in owner/repo. Background it via delegate_task with the
  pr-reviewer specialist; ship the GH PAT.
```

The LLM dispatches → the runner routes to `pr-reviewer` → the specialist uses the `pr-review` skill inside the box → comment lands on the GitHub PR → completion event flows back to Hermes.

This use case is illustrative — adapt the pattern (different specialist, different skill, different goal shape) to whatever your Hermes session needs.
