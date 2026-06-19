---
name: agentmint-hermes
description: Mint AgentMint pay-as-you-go subagents from Hermes. Provisions a persistent sandbox (Claude Code / Codex / OpenCode harness, any model via OpenRouter) for a long-running task; subsequent `delegate_task(background=true)` calls dispatch to it, hibernate the box between calls, and bill per run. Pay via Stripe-Link (link-cli) or Tempo USDC.e.
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

## Tier 2 — `delegate_task(background=True)` dispatch

Pre-mint the subagent (any of the paths above), then wire the Python adapter into Hermes' gateway. The adapter ships at <https://github.com/mesutcelik/agentmint-hermes>.

### Install

```bash
pip install agentmint-hermes-runner
```

### Wire-up

```python
import os
from agentmint_hermes_runner import (
    AgentMintDispatcher,
    AgentMintWebhookReceiver,
    BearerAuth,        # OR: TempoAuth
)
from hermes.gateway.process_registry import completion_queue   # merged PR #40946 rail

dispatcher = AgentMintDispatcher(
    endpoint="https://api.agentmint.store/a2a",
    auth=BearerAuth(jwt=os.environ["AGENTMINT_JWT"]),       # OR: TempoAuth(account="tempo")
    webhook_url="https://my-gateway.example.com/agentmint-webhook",
)

receiver = AgentMintWebhookReceiver(
    signing_secret=os.environ["AGENTMINT_WEBHOOK_SIGNING_SECRET"],
    completion_queue=completion_queue,
)
```

### Strategy B (default in v0.3) — wrap `delegate_task` transparently

The whole wiring collapses to **three lines** plus one CLI mint. No HTTPS endpoint, no webhook secret, no HTTP route — polling against `agent.run.status` does the re-injection.

```python
# in Hermes gateway startup (e.g. ~/.hermes/gateway_init.py):
import os
from agentmint_hermes_runner import (
    AgentMintDispatcher, BearerAuth, install_delegate_task_wrapper,
)

dispatcher = AgentMintDispatcher(auth=BearerAuth(jwt=os.environ["AGENTMINT_JWT"]))
install_delegate_task_wrapper(dispatcher, default_agent_name="default-worker")
# That's it. Every delegate_task(background=True) now lands on
# AgentMint's "default-worker" subagent — its /workspace/MEMORY.md
# accumulates across every delegation, forever.
```

`install_delegate_task_wrapper` monkey-patches `tools.async_delegation.dispatch_async_delegation` (the PR #40946 hook). Sync `delegate_task` and batch `delegate_task` are untouched.

**Polling specifics:** a daemon thread per dispatch polls `agent.run.status` (Bearer-only, free) every 5 s. On terminal status it calls Hermes' `_push_completion_event` directly. Configurable via `poll_interval=...`.

**Webhook mode (opt-in):** pass `delivery="webhook"` and pre-wire `AgentMintWebhookReceiver` to an HTTP route + set `webhook_url` on the dispatcher. Use this when you already have a public HTTPS endpoint and want sub-second-latency re-injection.

## Procedure summary (recommended)

1. **`web_extract` the full AgentMint API** from `https://agentmint.store/SKILL.md` (every method, parameter, error code).
2. **Pick a wallet** from the table above based on what the user has already authenticated. If unclear, default to `link-cli` for non-developers; Tempo for users with a funded USDC.e wallet.
3. **Mint the subagent** with `agent.create { name: …, … }` over the chosen rail.
4. **Run it** with `agent.run { name: …, prompt: … }` — synchronously by default, or `{ async: true, webhook: { url, headers } }` for background dispatch.
5. **(Tier 2 only)** Install `agentmint-hermes-runner`, wire it into your gateway extension + webhook route, then use `delegate_task(background=True, …)` against the pre-minted subagent.

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
| `background=True` (PR #40946) | ✅ **`install_delegate_task_wrapper(...)` — Strategy B, polling default** | Transparent to the LLM; no webhook required |
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
- **Async webhook delivery is via Upstash QStash.** Customer endpoint must be reachable from the public internet and signature-verify `X-AgentMint-Signature` (HMAC-SHA256 over `${timestamp}.${raw_body}`).
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
