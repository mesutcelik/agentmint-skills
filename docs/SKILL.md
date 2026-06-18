---
name: agentmint-hermes
description: Mint AgentMint pay-as-you-go subagents from Hermes. Provisions a persistent sandbox (Claude Code / Codex / OpenCode harness, any model via OpenRouter) for a long-running task; subsequent `delegate_task(background=true)` calls dispatch to it, hibernate the box between calls, and bill per run. Pay via Stripe-Link (link-cli) or Tempo USDC.e.
version: 0.1.0
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

### Dispatch side (Hermes `delegate_tool.py` extension)

```python
# When background=True and the operator's routing logic targets AgentMint:
result = dispatcher.dispatch(
    agent_name="reviewer-myrepo",        # OR agent_id="agt_…"
    goal=goal_text,
    files=staged_files,                  # optional, materialised at /workspace/
    cleanup_paths=["/workspace/pr-42"],  # optional, rm -rf'd after the run
    async_=True,
    hermes_context={
        "session_key": session_key,
        "toolsets": current_toolsets,
        "role": "pr-reviewer",
        "model": "openrouter/fusion",
    },
)
return {"status": "dispatched", "delegation_id": result.delegation_id, "mode": "background"}
```

### Webhook side (Hermes gateway HTTP route — Flask example)

```python
@app.post("/agentmint-webhook")
def on_agentmint_webhook():
    status, body = receiver.handle(dict(request.headers), request.get_data())
    return body, status
```

Hermes' existing `_async_delegation_watcher` drains `completion_queue` when idle and re-injects results as a new turn in the originating session.

If your Hermes fork's completion-event shape diverges from the upstream merged PR #40946, supply your own `event_adapter` to `AgentMintWebhookReceiver`.

## Procedure summary (recommended)

1. **`web_extract` the full AgentMint API** from `https://agentmint.store/SKILL.md` (every method, parameter, error code).
2. **Pick a wallet** from the table above based on what the user has already authenticated. If unclear, default to `link-cli` for non-developers; Tempo for users with a funded USDC.e wallet.
3. **Mint the subagent** with `agent.create { name: …, … }` over the chosen rail.
4. **Run it** with `agent.run { name: …, prompt: … }` — synchronously by default, or `{ async: true, webhook: { url, headers } }` for background dispatch.
5. **(Tier 2 only)** Install `agentmint-hermes-runner`, wire it into your gateway extension + webhook route, then use `delegate_task(background=True, …)` against the pre-minted subagent.

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
