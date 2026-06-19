---
name: hermes-delegate-task
description: Route Hermes `delegate_task(background=True)` calls to a named, persistent AgentMint subagent — its `/workspace/MEMORY.md` accumulates context across every delegation, the opposite of Hermes-native delegation which spawns a fresh subagent per call. Polling-only delivery (no public HTTPS required); pay via Stripe-Link (link-cli) or Tempo USDC.e.
version: 0.2.0
author: AgentMint
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [Subagents, Delegation, Payments, MPP, Sandbox]
    related_skills: [mpp-agent, stripe-link-cli]
---

# AgentMint × Hermes

Long-lived, named, USDC-paid subagents that Hermes can `delegate_task` against. Each subagent has its own bounded sandbox (Upstash Box), its own filesystem that persists across calls (`/workspace/MEMORY.md` is the standard memory anchor), and a stable name (`reviewer-myrepo`, `support-acme`, …). Hibernates to zero between calls — billed only when running.

## When to use

- Hermes' main session needs a **specialist** (PR reviewer, compliance checker, customer-support agent, codebase oracle, etc.) that accumulates domain knowledge across days/weeks.
- A task naturally **fans out** into N independent slices and you want each one on its own sandbox.
- You want **`delegate_task(background=true)`** to dispatch the actual work somewhere with isolated credentials, not the Hermes gateway itself.
- You want to use a **specific harness × model** combination (e.g. opencode + `openrouter/fusion`, claude-code + claude-sonnet-4-6) without baking those choices into Hermes.

Not the right tool when:
- The task is one-shot and Hermes can answer directly.
- You need cross-subagent shared state (each subagent's MEMORY is its own).

## Two integration tiers

### Tier 1 — Direct (no Python, no Hermes code changes)

Hermes calls AgentMint's JSON-RPC `/a2a` endpoint via `terminal` using whichever wallet skill the user has authenticated. Mint once, run many times.

### Tier 2 — `delegate_task` background dispatch

Pip-install `agentmint-hermes-runner` and wire it into Hermes' gateway. After that, `delegate_task(background=True, …)` results route through PR #40946's async-delegation rail (merged 2026-06-15). Hermes' existing `_async_delegation_watcher` re-injects the result as a new turn in the originating session.

## Wallet matrix

AgentMint speaks the same `/a2a` endpoint for both wallets — pick whichever Hermes already has authenticated.

| Wallet | When | Path |
|---|---|---|
| **Stripe-Link** (`link-cli`) | User has a card, no crypto wallet. Best for non-developers. | Bearer JWT against a caller-wide credit wallet — bootstrap once, debits per call |
| **Tempo Wallet** | User has Tempo wallet authenticated; wants spend controls + service discovery | Per-call x402/MPP, USDC.e on Tempo (`eip155:4217`) |

Fetch the underlying wallet skill via `web_extract` before invoking, so its setup steps are in context:

- `https://agentmint.store/SKILL.md` — full AgentMint API (every method, every rail)
- Hermes' built-in `stripe-link-cli` skill for `link-cli`
- Hermes' built-in `mpp-agent` skill for `tempo request`

## Tier 1 — Direct mint + run

### Path A: Stripe-Link (link-cli + credit wallet)

Bootstrap once, then every subsequent `agent.*` call is Bearer-paid against a shared credit wallet — no Stripe per-call fee.

```bash
# 1) Bootstrap the wallet (min $10) — via the stripe-link-cli skill
link-cli mpp pay https://api.agentmint.store/a2a \
  -X POST -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"credits.topup","params":{"amount_usd":10}}' \
  --spend-request-id <lsrq_…>
# → response.access_token = <jwt>   (caller-wide; works for any subagent)

# 2) Mint a subagent (Bearer-paid, 0.10 USDC equivalent debited from wallet)
curl -X POST https://api.agentmint.store/a2a \
  -H 'Authorization: Bearer <jwt>' -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"agent.create","params":{"name":"reviewer-myrepo"}}'

# 3) Run the subagent (per-call price debited from the same wallet)
curl -X POST https://api.agentmint.store/a2a \
  -H 'Authorization: Bearer <jwt>' -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"agent.run","params":{"name":"reviewer-myrepo","prompt":"…"}}'

# 4) Check the shared balance any time
curl -X POST https://api.agentmint.store/a2a \
  -H 'Authorization: Bearer <jwt>' -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"credits.balance","params":{}}'
```

Same JWT works across every subagent the user mints — one balance, N subagents.

### Path B: Tempo Wallet

```bash
tempo wallet login           # one-time, browser-based
tempo wallet whoami          # confirms address + USDC balance

tempo request -X POST \
  --json '{"jsonrpc":"2.0","id":1,"method":"agent.create","params":{"name":"reviewer-myrepo"}}' \
  https://api.agentmint.store/a2a
```

Pin to `tempo-request@0.5.2` — newer versions hit "Invalid base64 JSON header" against AgentMint's challenge. Downgrade with `tempo cli 0.0.0 downgrade tempo request cli to 0.5.2`.

## Tier 2 — `delegate_task(background=True)` dispatch (Strategy B)

`install_delegate_task_wrapper` monkey-patches `tools.async_delegation.dispatch_async_delegation` (the PR #40946 hook) so every `delegate_task(background=True, single-task)` call inside Hermes transparently routes to a named, persistent AgentMint subagent. Sync `delegate_task` and batch `delegate_task` are untouched.

Completion is delivered via **polling** against AgentMint's `agent.run.status` endpoint (Bearer-only, free). A daemon thread per dispatch polls every 5 s and pushes completions onto Hermes' `completion_queue` via `_push_completion_event`. No public HTTPS endpoint, no webhook secret, no HTTP route to register — polling is the only delivery mode.

### Step-by-step setup

**Step 1 — Bootstrap an AgentMint wallet (one-time)**

```bash
# Stripe-Link (recommended, supports polling) — min $10:
link-cli mpp pay https://api.agentmint.store/a2a \
  -X POST -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"credits.topup","params":{"amount_usd":10}}'
# → response.result.access_token = <JWT>

export AGENTMINT_JWT=<the JWT>
```

(Tempo path also works, but polling is Bearer-only — Tempo users must use webhook mode, covered in "Webhook mode" below.)

**Step 2 — Pre-mint the subagent (one-time)**

```bash
curl -X POST https://api.agentmint.store/a2a \
  -H "Authorization: Bearer $AGENTMINT_JWT" \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"agent.create","params":{
        "name":"default-worker",
        "harness":"opencode",
        "model":"openrouter/fusion"}}'
```

This is the entity that will REMEMBER across every Hermes delegation. Its `/workspace/MEMORY.md` accumulates context across every call. Cost: 0.10 USDC equivalent debited from the credit wallet.

**Step 3 — Install the Python adapter in Hermes' venv**

```bash
pip install agentmint-hermes-runner
```

Verify: `python -c "import agentmint_hermes_runner; print(agentmint_hermes_runner.__version__)"` → `0.3.0` or higher.

**Step 4 — Add three lines to your Hermes gateway startup**

Put this in your Hermes gateway entry-point (or wherever you instantiate the gateway), BEFORE any `delegate_task(background=True)` call:

```python
import os
from agentmint_hermes_runner import (
    AgentMintDispatcher, BearerAuth, install_delegate_task_wrapper,
)

dispatcher = AgentMintDispatcher(auth=BearerAuth(jwt=os.environ["AGENTMINT_JWT"]))
install_delegate_task_wrapper(dispatcher, default_agent_name="default-worker")
```

That's the entire wiring. The function returns an `uninstall()` callable if you want to undo it later (mostly useful in tests).

**Step 5 — Restart Hermes and test**

Restart the gateway so the new module loads and the patch is in effect. Then from inside a Hermes session:

```
> use delegate_task with background=true to ask: "Say hello and tell me what
  you remember from prior calls."
```

The LLM will call `delegate_task(background=True, goal="…")`. Behind the scenes:
1. Adapter calls `agent.run` on AgentMint with `async: true`
2. AgentMint returns a `run_id` (e.g. `arun_a1b2c3d4`)
3. Adapter spawns a daemon thread that polls `agent.run.status` every 5 s
4. AgentMint finishes the run (~15-60 s typically)
5. Adapter calls `_push_completion_event` → Hermes' `completion_queue`
6. Hermes' `_async_delegation_watcher` drains and re-injects the result as a new turn

**Step 6 — Verify persistence (the value proposition)**

Call `delegate_task(background=true)` twice with different goals against the same Hermes session. The second response should reference details from the first — because `/workspace/MEMORY.md` survived between dispatches. That's the differentiator from Hermes' native `delegate_task` (which always starts fresh).


## Hermes `delegate_task` coverage (v0.3)

| Hermes feature | AgentMint via this runner | Notes |
|---|---|---|
| `goal` | ✅ Concatenated under `## Goal` | `dispatcher.dispatch(goal=…)` |
| `context` | ✅ Concatenated under `## Context` | Client-side concat — no server-side `context` field |
| `toolsets=["terminal", "file"]` restrictions | ✅ Soft hints in prompt ("Do not run shell commands.", …) | Sandbox can't structurally enforce; the harness should respect the hint |
| `toolsets=["web"]` | ❌ **Unsupported** — raises `UnsupportedToolset` | No canonical web-fetch skill in the AgentMint catalog yet; tracked separately |
| `role="leaf"` / `"orchestrator"` | ✅ Soft hint in prompt | Default `"leaf"` |
| `max_iterations` | ✅ Soft hint ("Soft iteration budget: ~N actions.") | Harness-dependent enforcement |
| `tasks=[{…}, {…}]` (batch) | ✅ `dispatcher.dispatch_batch(tasks=…)` — parallel via ThreadPoolExecutor, results in input order | Each Task targets a named subagent |
| `max_concurrent_children` | ✅ `max_concurrent_children=N` param to `dispatch_batch` | Default 3 |
| `child_timeout_seconds` | ✅ `child_timeout_seconds=N` param; floor 30s; fires `agent.cancel` on expiry | Single + batch |
| Interrupt cascade | ✅ `cancel_event=threading.Event` to `dispatch_batch` — fires `agent.cancel` on all in-flight | |
| `background=True` (PR #40946) | ✅ **`install_delegate_task_wrapper(...)` — Strategy B, polling** | Transparent to the LLM; polling-only |
| Result ordering (by task index) | ✅ `dispatch_batch` returns in input order regardless of completion order | |
| `max_spawn_depth` (nested delegation) | n/a | AgentMint sandboxes aren't depth-bounded structurally |
| `/agents` TUI overlay | n/a | Pure Hermes UI feature; use `dispatcher.list()` to enumerate subagents |
| Credential inheritance | **better** | Each subagent has its own credentials (no parent key sharing) |
| "Fresh conversation per call" | **inverted** | AgentMint subagents persist `/workspace/MEMORY.md` across calls — this is the core value |

## Pitfalls

- **Mode 1 (Stripe-Link) and Mode 2 (Tempo) don't share state.** Funds in the credit wallet (`account:<principal>`) are not transferable to a blockchain address and vice versa. Pick one model per principal.
- **JWT is caller-wide on Stripe-Link.** One token authorises any agent.* call against any subagent the principal owns. If lost, re-bootstrap via `credits.topup` with no Bearer — the server rotates the canonical jti. The old token is NOT auto-revoked; revoke it explicitly via `credits.revoke_token --jti <jti>` if you know the lost jti.
- **`name` is global + immutable.** First mint wins. Pick something specific enough to avoid collisions (`reviewer-mesutcelik-agentmint`, not `reviewer`). Released only by `agent.delete`.
- **Stripe-MPP only accepts `credits.topup`.** Trying `agent.create` over Stripe-MPP returns `400 use_bearer_after_topup`. Bootstrap with `credits.topup` first.
- **Tempo broadcast is client-side.** `tempo request` broadcasts before AgentMint's server sees the payment, so a server-side failure after `verify` still leaves the customer charged. Grep server logs for `[agentmint/refund-needed]` for manual operator refund triggers.
- **Wallet keys never enter Hermes context.** Both wallet skills store credentials under their own config dirs; never `cat`/`read_file` them.

## Verification

```bash
# Confirm the AgentMint endpoint is reachable + supports your wallet
curl -X POST https://api.agentmint.store/a2a \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"agent.create","params":{}}'
# → 402 with accepts[] enumerating supported chains. Pick the one matching your wallet.
```

For Tier 2, the canary is a complete dispatch + webhook + re-injection cycle. See `examples/stripe_link.py` and `examples/tempo_wallet.py` in the agentmint-hermes repo.
