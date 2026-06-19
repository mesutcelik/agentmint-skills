---
name: hermes-delegate-task
description: Route Hermes `delegate_task(background=True)` to AgentMint cloud subagents — ephemeral by default (fresh sandbox per call, matches Hermes-native stateless semantics) or persistent (named subagent that accumulates `/workspace/MEMORY.md` across calls). Optional `agentmint_delegate` plugin tool exposes named subagents addressable per call. Polling delivery (no public HTTPS required); pay via Stripe-Link (link-cli).
version: 0.5.0
author: AgentMint
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [Subagents, Delegation, Payments, MPP, Sandbox]
    related_skills: [mpp-agent, stripe-link-cli]
---

# AgentMint × Hermes

Bridges Hermes' `delegate_task(background=True)` to AgentMint cloud subagents — sandboxed Upstash Box runs with independent credentials and isolated filesystems. Hibernate to zero between calls; billed only when running.

## Runtime usage (for the LLM)

After the operator has set this skill up, Hermes' built-in `delegate_task` and (optionally) a new `agentmint_delegate` tool behave as follows. Pick based on what the operator configured:

### Ephemeral mode (default `install_delegate_task_wrapper(dispatcher)`)

Every `delegate_task(background=True)` call mints a FRESH cloud subagent, runs it, and deletes it on completion. Stateless per call — matches Hermes' native semantics exactly, but the subagent runs on isolated AgentMint cloud rather than locally.

- No memory across calls. Subagents don't remember prior dispatches.
- Multiple `delegate_task(background=True)` in parallel = multiple independent cloud subagents.
- Use this for fan-out research, code review of independent files, anything where each task is self-contained.

### Persistent mode (operator passed `default_agent_name="..."`)

Every `delegate_task(background=True)` lands in ONE pre-named subagent. Its `/workspace/MEMORY.md` accumulates across calls. The subagent is a specialist that LEARNS.

- Reference prior delegations: "you analyzed Module X last time — what did you find?"
- Skip re-stating context the subagent already has.
- Treat it like a colleague that remembers.

### Optional `agentmint_delegate` plugin tool (operator pip-installed the package)

If installed, Hermes exposes an extra tool alongside `delegate_task`:

```
agentmint_delegate(
    agent_name="reviewer-myrepo",       # which named specialist
    goal="Review the diff in /workspace/pr-42",
    context="Project uses Flask + PyJWT",
    async_=True,
)
```

LLM picks the subagent per call. Use when you want a FLEET of named specialists addressable individually (one per repo, one per customer, one per domain). The result re-injects as a new turn when ready — same UX as `delegate_task(background=True)`.

## When to use

- Hermes' main session needs a **specialist** (PR reviewer, compliance checker, customer-support agent, codebase oracle, …) that accumulates domain knowledge across days/weeks → persistent mode or `agentmint_delegate` to a named subagent.
- A task naturally **fans out** into N independent slices and you want each one on its own isolated cloud sandbox → ephemeral mode.
- You want **`delegate_task(background=true)`** to dispatch the actual work somewhere with isolated credentials, not the Hermes gateway itself.
- You want to use a **specific harness × model** combination (e.g. opencode + `openrouter/fusion`) without baking those choices into Hermes.

Not the right tool when:
- The task is one-shot and Hermes can answer directly.
- You need cross-subagent shared state (each subagent's MEMORY is its own).

## Wallet

AgentMint speaks the same `/a2a` endpoint for both rails, but **the `install_delegate_task_wrapper` flow polls `agent.run.status` which is Bearer-only**, so practically the operator funds AgentMint via Stripe-Link credit wallet (link-cli). Tempo customers can drive AgentMint directly via Tier 1 (curl) but not via the patched/plugin flows below.

Fetch the wallet skill via `web_extract` before invoking:
- `https://agentmint.store/SKILL.md` — full AgentMint API (every method, every rail)
- Hermes' built-in `stripe-link-cli` skill for `link-cli`

## Setup procedure

Pick the mode the operator wants, then follow the corresponding steps.

### Step 1 — Bootstrap a Stripe-Link wallet (one-time, all modes)

```bash
link-cli mpp pay https://api.agentmint.store/a2a -X POST \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"credits.topup","params":{"amount_usd":10}}'
# → response.result.access_token = <JWT>

export AGENTMINT_JWT=<the JWT>
```

### Step 2 — pip install the adapter (all modes)

```bash
pip install agentmint-hermes-runner   # in Hermes' venv
```

### Step 3 — pick a mode and wire it

**Ephemeral mode (default — recommended for stateless fan-out):**

No pre-mint needed. Three lines in Hermes gateway startup:

```python
import os
from agentmint_hermes_runner import AgentMintDispatcher, BearerAuth, install_delegate_task_wrapper

dispatcher = AgentMintDispatcher(auth=BearerAuth(jwt=os.environ["AGENTMINT_JWT"]))
install_delegate_task_wrapper(dispatcher)   # no default_agent_name → ephemeral
```

Cost: ~$0.16 USDC per `delegate_task` call.

**Persistent mode (one specialist that remembers):**

Pre-mint the subagent first:

```bash
curl -X POST https://api.agentmint.store/a2a \
  -H "Authorization: Bearer $AGENTMINT_JWT" \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"agent.create","params":{
        "name":"default-worker","harness":"opencode","model":"openrouter/fusion"}}'
```

Then in Hermes gateway startup:

```python
install_delegate_task_wrapper(dispatcher, default_agent_name="default-worker")
```

Cost: $0.10 one-time mint + ~$0.05 per `delegate_task` call.

**Plugin tool (named fleet via `agentmint_delegate`):**

Pre-mint each specialist you want addressable (one curl per name). Then in Hermes gateway startup:

```python
from agentmint_hermes_runner import set_dispatcher
set_dispatcher(dispatcher)
```

The `agentmint_delegate` tool auto-registers via Hermes' `hermes_agent.plugins` entry-point discovery. Cost: $0.10 per pre-mint + ~$0.05 per call.

You can combine the plugin tool with either ephemeral or persistent mode — both `delegate_task` and `agentmint_delegate` coexist:

```python
install_delegate_task_wrapper(dispatcher)   # ephemeral delegate_task
set_dispatcher(dispatcher)                   # named agentmint_delegate
```

### Step 4 — Restart Hermes

Restart the gateway so the new modules load and the patch / plugin registration take effect.

### Step 5 — Test

From a Hermes chat:

```
> Use delegate_task with background=true: "Say hello and tell me what you remember."
```

Behind the scenes the adapter dispatches to AgentMint, polls until done, and re-injects the result as a new turn.

For persistent mode or `agentmint_delegate`, you can ask follow-up delegations — the subagent's MEMORY.md will reflect prior calls.

## Fleet management — beyond default routing

Even without the `agentmint_delegate` plugin, the Hermes LLM can manage subagents directly via `terminal` + curl. The `delegate_task` patch only handles ONE subagent (the default in persistent mode, or a fresh ephem-* in ephemeral mode); for any other named subagent, use direct `/a2a` calls.

### List subagents you own

```bash
curl -X POST https://api.agentmint.store/a2a \
  -H "Authorization: Bearer $AGENTMINT_JWT" \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"agent.list","params":{}}'
```

### Create a new specialist

```bash
curl -X POST https://api.agentmint.store/a2a \
  -H "Authorization: Bearer $AGENTMINT_JWT" \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"agent.create","params":{
        "name":"reviewer-myrepo","harness":"opencode","model":"openrouter/fusion",
        "persona":"You are a code reviewer specialised in Python web apps."}}'
```

### Delete an unused subagent

```bash
curl -X POST https://api.agentmint.store/a2a \
  -H "Authorization: Bearer $AGENTMINT_JWT" \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"agent.delete","params":{"name":"reviewer-myrepo"}}'
```

### Dispatch to a non-default named subagent

Two options:
- **With the `agentmint_delegate` plugin installed**: just call the tool. Result re-injects.
- **Without the plugin**: use direct `agent.run` curl (no re-injection — response is in your terminal stdout):

```bash
curl -X POST https://api.agentmint.store/a2a \
  -H "Authorization: Bearer $AGENTMINT_JWT" \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"agent.run","params":{
        "name":"reviewer-myrepo","prompt":"Review the diff..."}}'
```

## Hermes `delegate_task` coverage (v0.6)

Audited against the live Hermes delegation docs. Status notation: ✅ supported, ✅ soft hint = prompt-level only (sandbox can't structurally enforce), ❌ not implemented, n/a = different model / Hermes-internal concern that doesn't reach us.

### Call parameters

| Hermes feature | Status | Notes |
|---|---|---|
| `goal` | ✅ | Concatenated under `## Goal` in the synthesized prompt |
| `context` | ✅ | Concatenated under `## Context`; client-side concat (no server `context` field) |
| `toolsets=["terminal", "file"]` | ✅ soft hint | Prompt restriction lines ("Do not run shell commands.") |
| `toolsets=["web"]` | ❌ | Raises `UnsupportedToolset` — no canonical AgentMint web-fetch skill yet |
| `role="leaf"` / `"orchestrator"` | ✅ soft hint | Prompt-level only; sandbox can't structurally enforce |
| `max_iterations` | ✅ soft hint | Harness-dependent enforcement inside the sandbox |
| `tasks=[{…}, {…}]` batch | ✅ | `dispatch_batch` — ThreadPoolExecutor; results returned in input order regardless of completion order |
| `background=True` (PR #40946) | ✅ | Three modes (see "Operator setup" earlier in this skill): ephemeral via `agent.run.stateless`, persistent via named subagent, or `agentmint_delegate` plugin tool |
| `agentmint_delegate(agent_name=…, …)` | ✅ | NEW tool via Hermes' `hermes_agent.plugins` entry-point; per-call subagent selection |

### Hermes config knobs (under `delegation:` in `~/.hermes/config.yaml`)

| Hermes feature | Status | Notes |
|---|---|---|
| `max_concurrent_children` | ✅ | `max_concurrent_children=N` on `dispatch_batch` (default 3) |
| `child_timeout_seconds` | ✅ | `child_timeout_seconds=N` on `dispatch` + `dispatch_batch`; floor 30s; fires `agent.cancel` on expiry |
| `max_spawn_depth` | n/a | AgentMint sandboxes aren't structurally depth-bounded (they cost more, not blocked) |
| `orchestrator_enabled` | n/a | Hermes-level kill switch; if false, callers never pass `role="orchestrator"` to us anyway |
| `api_mode` / `model` / `provider` / `base_url` / `api_key` | n/a | These configure Hermes' subagent LLM provider — AgentMint's stateless workers run all-inclusive opencode + openrouter/fusion server-side |
| `subagent_auto_approve` | n/a | Hermes' approval-callback for in-sandbox dangerous commands — AgentMint runs each box in its own isolated VM; no parent TUI to defer to |

### Lifecycle + interrupt

| Hermes feature | Status | Notes |
|---|---|---|
| Synchronicity (`delegate_task` blocks parent turn unless `background=True`) | ✅ | Sync mirrors: our `dispatch()` blocks until completion. `background=True` is the only async path on Hermes side, and that's the path we patch. |
| Interrupt cascade (parent `/stop` cancels all children) | ✅ | `cancel_event=threading.Event` on `dispatch_batch` fires `agent.cancel` for in-flight dispatches |
| Status `"interrupted"` on parent interrupt | ✅ | `DispatchResult.status="interrupted"` returned at the cancelled-task slot |
| Hard-timeout diagnostic dumps | ❌ | Hermes writes `~/.hermes/logs/subagent-timeout-<session>-<timestamp>.log` on zero-call timeout; we just raise `DispatchTimeout` and fire `agent.cancel`. Worth adding if customers need post-mortem on stuck runs. |

### Subagent restrictions

| Hermes feature | Status | Notes |
|---|---|---|
| Leaf-blocked tools (`delegation` / `clarify` / `memory` / `code_execution` / `send_message`) | n/a | Different model — AgentMint sandboxes don't expose Hermes' tool registry. The leaf role hint in the prompt is the soft equivalent ("Do not delegate further") |
| Orchestrator-blocked tools (same set minus `delegation`) | n/a | Same as above — soft prompt hint only |
| Fresh conversation per call ("subagents know nothing") | Ephemeral: ✅ same. Persistent: **inverted** | Inversion is the core value prop in persistent mode — `/workspace/MEMORY.md` survives every dispatch |
| Credential inheritance (parent's API key passed to children) | **different model** | Hermes: subagents inherit parent's API key + provider config (key rotation on rate limits). AgentMint: each sandbox runs against AgentMint's server-managed stored keys — no parent credential leakage between sessions or siblings. |

### Hermes-side UI / observability

| Hermes feature | Status | Notes |
|---|---|---|
| `/agents` TUI overlay (live tree, kill/pause, post-hoc review) | partial | AgentMint dispatches go through Hermes' `_async_delegation_watcher` for re-injection, but they don't currently register with `_active_subagents` (the registry the TUI reads). The TUI won't show them in the live tree. Use `agent.list` / `agent.run.status` against AgentMint instead. |
| Per-branch cost / token / file rollups | partial | Available via AgentMint server-side (`agent.runs`, `agent.run.status`'s `billed_usdc` field) but not surfaced into Hermes' TUI views |
| `delegation.pause` RPC (freeze new fan-out) | n/a | Hermes-level; we don't observe it. If Hermes refuses to dispatch, we never see the call. |

## Pitfalls

- **Mode 1 (Stripe-Link) and Mode 2 (Tempo) don't share state.** Funds in the credit wallet (`account:<principal>`) are not transferable to a blockchain address and vice versa. Pick one model per principal.
- **JWT is caller-wide on Stripe-Link.** One token authorises any agent.* call against any subagent the principal owns.
- **`name` is global + immutable.** First mint wins. Pick something specific (`reviewer-mesutcelik-agentmint`, not `reviewer`). Released only by `agent.delete`.
- **Ephemeral pricing is smoothed** ($0.01–$0.075 per call, same band as all-inclusive `agent.run`). For a long-running specialist that learns over many calls, persistent mode amortizes the mint cost across all calls.
- **Stripe-MPP only accepts `credits.topup`.** Trying `agent.create` over Stripe-MPP returns `400 use_bearer_after_topup`. Bootstrap with `credits.topup` first.
- **Tempo broadcast is client-side.** `tempo request` broadcasts before AgentMint's server sees the payment, so a server-side failure after `verify` still leaves the customer charged. Grep server logs for `[agentmint/refund-needed]`.
- **Wallet keys never enter Hermes context.** Wallet skills store credentials under their own config dirs; never `cat`/`read_file` them.

## Verification

```bash
# Confirm the AgentMint endpoint is reachable
curl -X POST https://api.agentmint.store/a2a \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"agent.create","params":{}}'
# → 402 with accepts[] enumerating supported rails

# Confirm the plugin entry-point is discovered after pip install:
python -c "import importlib.metadata as m; print([(e.name,e.value) for e in m.entry_points(group='hermes_agent.plugins')])"
# → [('agentmint', 'agentmint_hermes_runner.hermes_plugin')]
```

For mode canaries, see `examples/{ephemeral,persistent,plugin}.py` in the [agentmint-hermes](https://github.com/mesutcelik/agentmint-hermes) repo.
