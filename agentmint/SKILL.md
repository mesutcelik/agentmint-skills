---
name: agentmint
description: Pay-as-you-go AI subagents over USDC or USD. Provision a persistent Claude Code / Codex / OpenCode sandbox, then send prompts and pay-per-call. Settles via x402 (Base, Solana), MPP (Tempo), or Stripe-Link (USD card via link-cli). BEFORE PAYING, run the discovery checklist below — pick the rail the user already has authenticated locally rather than defaulting to any single MCP server or chain.
license: MIT
metadata:
  endpoint: https://api.agentmint.store/a2a
  agent_card: https://api.agentmint.store/.well-known/agent-card.json
  cli: https://www.npmjs.com/package/agentmint-cli
  version: "0.4.1"
---

# agentmint

AgentMint sells **USDC-paid (or USD-via-Stripe-Link) subagents** to other AI agents.

You pay **0.10 USDC** to provision a persistent sandbox (binding name, harness, model, optional API key, skills, init command). Each subsequent prompt costs ~0.05 USDC. State-mutation operations (update skills, cancel a run, delete the agent) cost 0.01 USDC each — the payment doubles as proof of ownership (`payer` must equal the `owner_wallet` set at create).

Blockchain customers (x402 / MPP-blockchain rails) pay each call directly from their wallet. **Stripe-Link customers** use a **caller-wide credit wallet** instead: one `credits.topup` charge funds a balance keyed to the customer's principal (`link_stripe:cus_…`); every subsequent `agent.*` call — including `agent.create` for new subagents — debits that shared balance over `Authorization: Bearer <jwt>`. One wallet per customer, used across every subagent that customer owns.

## Before paying — ask the human, then verify

**The first rule: if the human hasn't named a rail, ask which one to use.** Do not auto-detect, do not default to whichever payment MCP server happens to be wired up, do not silently pick the first signer env var you find. Auto-defaults pick the wrong rail when the user has another tool already authenticated (e.g. routing to an empty AgentCash wallet when `link-cli` has a card on file).

> **Skip the ask only if either**:
> - The human's original prompt already named the tool / rail (e.g. "use link-cli", "via agentcash", "pay on Base") — use what they specified.
> - Exactly one of the rails below is **both authenticated and funded** on this host — use it and tell the user which one you picked.

### Scan probe (run only when the human says "scan my system")

```sh
# Stripe-Link (USD via card)
which link-cli && link-cli auth status 2>&1 | head -3
link-cli payment-methods list 2>&1 | head -20

# CLI wallets — quick auth checks (see Wallet catalog below for full details)
which tempo && tempo wallet whoami 2>&1 | head -3
npx -y agentcash@latest accounts 2>&1 | head -3

# agentmint-cli + signer env vars (on-chain)
which agentmint-cli && agentmint-cli --version
ls ~/.agentmint/agents.json 2>/dev/null
env | grep -E '^(EVM|SVM|TEMPO)_PRIVATE_KEY=' \
  | sed 's/=.*$/=<set>/'   # never print the value

# AgentCash MCP wallet (only if the MCP server is installed in this session)
# Call mcp__agentcash__get_balance — non-zero means funded.
```

### Rail matrix

| Rail              | Currency | Chain(s)                                     | Detect with                                                   | Pick when                                                                 |
|-------------------|----------|----------------------------------------------|---------------------------------------------------------------|---------------------------------------------------------------------------|
| **Stripe-Link**   | USD      | n/a (Link account + saved card)              | `link-cli auth status` AND a `type: CARD` in `payment-methods list` | User has a card, no crypto wallet; one approval per spend-request         |
| **CLI wallet**    | USDC     | Base / Solana / Tempo (per wallet)           | See the **Wallet catalog** section — each entry has an auth-check command | A specific CLI is installed & has USDC for the relevant chain             |
| **agentmint-cli** | USD      | n/a (Bearer JWT from `credits topup`)        | A Stripe-Link wallet token is cached locally                                | User has already bootstrapped via `agentmint credits topup`               |
| **AgentCash MCP** | USDC     | Base / Solana / Tempo                        | `mcp__agentcash__get_balance` returns ≥ $0.50                 | The MCP server is installed AND the wallet is funded; not just installed  |
| **Raw HTTP**      | USDC/USD | any of the above                             | Custom — you're wiring x402/MPP SDKs into bespoke code        | You're building a service that pays without a CLI in the loop             |

The server speaks every rail at the same `/a2a` endpoint — the choice is purely client-side.

## When to use

- The user wants a sandboxed Claude Code / Codex / OpenCode subagent that can run shells, install packages, edit files, and persist state across calls.
- The user wants a workflow customized via skill files (e.g. `moltycash/payment`, `your-org/your-skill`).
- The user wants pay-as-you-go isolated compute. Pay per call from any chain, or bulk-top-up a credit wallet once via Stripe-Link / x402 and use the resulting access token for subsequent calls (no per-call signature, no monthly commitment).

## Endpoint

`POST https://api.agentmint.store/a2a` — JSON-RPC 2.0. All payment plumbing (402 challenges, x402/MPP verify, settle) is handled at this single endpoint.

Discovery: `GET https://api.agentmint.store/.well-known/agent-card.json`

## Network support

| Network     | Chain                  | Token | Decimals | Protocol | CAIP-2          |
|-------------|------------------------|-------|----------|----------|-----------------|
| Base        | EVM (8453)             | USDC  | 6        | x402     | `eip155:8453`   |
| Solana      | SVM mainnet            | USDC  | 6        | x402     | `solana:5eyk…`  |
| Tempo       | EVM (4217)             | USDC  | 6        | MPP      | `eip155:4217`   |
| Stripe-Link | Stripe Customer        | USD   | 2        | MPP      | (Link account)  |

Every 402 challenge advertises every chain whose commission wallet is configured server-side. Pick whichever your wallet supports — there is no preferred chain.

## Two payment protocols

**x402** (Base, Solana) — Client sends request → server returns `402 Payment Required` with `accepts: [...]` → client signs and resubmits with `PAYMENT-SIGNATURE` header.

**MPP** (Tempo, Stripe-Link) — Client sends request → server returns `WWW-Authenticate: Payment` → client signs and resubmits with `Authorization: Payment` header.

The server speaks both. Pick based on which chain you're paying on; the SDK clients (`@x402/evm`, `@x402/svm`, `mppx`) handle the framing.

## Workspace anchors (`/workspace/AGENTS.md`, `CLAUDE.md`, `MEMORY.md`)

Every subagent boots with three canonical files under `/workspace/` that the harness reads on every call:

| File | Created | Purpose |
|---|---|---|
| `/workspace/AGENTS.md` | by AgentMint at `agent.create`; rewritten on `agent.update --persona` | Read automatically by **Codex** and **OpenCode** harnesses. Contains: the customer's **persona**, the memory protocol, and the per-call files note. |
| `/workspace/CLAUDE.md` | symlink → `AGENTS.md` | Read automatically by the **claude-code** harness. Always sees the same content as Codex / OpenCode. |
| `/workspace/MEMORY.md` | seeded once at `agent.create` (empty stub); **never overwritten** by AgentMint after that | The subagent's long-term notebook. The persona's memory-protocol section instructs the agent to append a 1-2 sentence summary after each meaningful run and to re-read it at the start of each run. Persists across hibernate/resume until `agent.delete`. |

**For all-inclusive mode** (which routes internally through the `opencode` harness + `openrouter/fusion`), the harness reads `AGENTS.md` — same as a BYOK `opencode` mint.

The customer controls the **Persona** section via the `persona` param on `agent.create` (and `agent.update`); everything else (wallets, memory protocol, per-call files note) is fixed by AgentMint. Max persona length: 8 KB.

```json
{
  "jsonrpc": "2.0", "id": 1, "method": "agent.create",
  "params": {
    "name": "reviewer-myrepo",
    "persona": "You are a strict PR reviewer for mesutcelik/agentmint. Block changes to apps/api/src/routes/a2a.ts that lack tests. Demand conventional-commit titles."
  }
}
```

To rewrite the persona later without touching the agent's MEMORY:

```json
{ "method": "agent.update",
  "params": { "name": "reviewer-myrepo", "persona": "<new instructions>" } }
```

Pass `"persona": ""` on `agent.update` to clear back to the built-in default. MEMORY.md is never touched by `agent.update`.

## Two billing modes (chosen at agent.create — permanent)

**byok** — You configure everything: harness, model, your AI provider key. Your provider bills tokens directly. Flat **0.02 USDC** per `agent.run`.

**all-inclusive** — You configure nothing about the AI side. AgentMint picks harness + model + key. AI tokens covered. Per-call price **0.05 USDC base**, smoothed 0.01 ↔ 0.075 across recent runs based on actual token cost.

Mode is auto-detected: if you supply `api_key`, it's BYOK; otherwise all-inclusive.

## Interview order before `agent.create`

When gathering inputs from a human before provisioning, ask in this exact order — each step gates the next, so do not collect harness/model details before the human has picked a billing mode:

1. **Payment rail** — which rail to settle on (see "Before paying — ask the human, then verify" above). Skip only under the conditions listed there.
2. **Billing mode** — `byok` or `all-inclusive`. This must come **before** any harness/model question, because all-inclusive needs no harness, model, or API key — asking those up front wastes the user's time and implies BYOK as the default.
3. **Harness details** — only if the human picked `byok`:
   - `harness` (claude-code / codex / opencode)
   - `model` (any model the harness supports)
   - `api_key` (their provider key)
   - `runtime`, `size`, `init_command`, `skills` (optional)
   For `all-inclusive`, skip this step — AgentMint picks harness + model + key.
4. **Purpose / skills** — what the agent should do (e.g. which public GitHub skills to mount). Applies to both modes.
5. **Submit** — confirm the full config back to the human, then call `agent.create`.

## Methods

| Method | Cost | Auth | Purpose |
|--------|------|------|---------|
| `agent.create` | 0.10 USDC | blockchain: per-call rail handshake. Stripe-Link: Bearer (debits the caller-wide wallet — bootstrap with `credits.topup` first) | Provision a persistent named subagent; owner = payer/principal |
| `agent.run`    | 0.02 / 0.05 USDC | payer / principal = owner | Send a prompt; receive reply |
| `agent.update` | 0.01 USDC | payer / principal = owner | Update skills, init command, model |
| `agent.cancel` | 0.01 USDC | payer / principal = owner | Cancel a stuck run |
| `agent.runs`   | 0.01 USDC | payer / principal = owner | List recent runs |
| `agent.get`    | 0.01 USDC | payer / principal = owner | Read agent metadata |
| `agent.delete` | 0.01 USDC | payer / principal = owner | Destroy the subagent |
| `agent.list`   | 0.01 USDC | payer / principal = owner | Enumerate all subagents owned by the caller (`limit` default 50, max 200; `offset` for paging) |
| `credits.topup` | ≥ $10 USD | **Stripe-MPP only**. No Bearer = bootstrap (mints JWT). With Bearer = top up existing wallet | Fund the caller-wide credit wallet; response includes the (fresh) access token |
| `credits.balance` | free | `Authorization: Bearer <jwt>` | Read caller-wide balance |
| `credits.revoke_token` | free | `Authorization: Bearer <jwt>` | Revoke a specific jti for the caller |
| `credits.history` | free | `Authorization: Bearer <jwt>` | Per-event ledger: every topup, debit, refund for the caller |


Use this when you want one-shot delegated work in an isolated cloud sandbox. For a persistent specialist that remembers across calls, use `agent.create` + `agent.run` instead.

## Caller-wide credit wallet (Stripe-Link only)

The credit-wallet flow is **only available on the Stripe-Link rail**. Blockchain customers (Base / Solana / Tempo) already have on-chain balances and pay per call from those. Stripe-Link customers, with no on-chain wallet, instead get a **caller-wide credit balance** funded by Stripe-MPP top-ups — bulk pre-payment avoids Stripe's ~$0.30 + 2.9% per-call fees that would otherwise dwarf the cost of each method.

**The credit ledger is keyed by `principal` (e.g. `link_stripe:cus_…`), not by `agent_id`.** A customer with N subagents has ONE shared balance and ONE JWT that authorises any `agent.*` call against any of those subagents. Ownership is enforced by `agent.owner_principal === jwt.principal`.

**Stripe-MPP rail accepts only `credits.topup`.** Every other method over Stripe-MPP returns `400 use_bearer_after_topup` — call via `Authorization: Bearer <access_token>` instead. Blockchain rails reject `credits.*` entirely with `400 stripe_rail_required`.

Principal format on this rail: `link_stripe:cus_…` (stored as `agent.owner_principal` on every subagent and as the wallet key on Redis).

Flow:

1. **Bootstrap the wallet.** Call `credits.topup` over Stripe-MPP with **no Bearer** and `{ amount_usd }` (≥ $10). Server creates `account:<principal>`, credits the paid amount, and returns `{ principal, balance_microusdc, balance_usd, access_token, bootstrap: true }`. The JWT is bound to the principal (not to any specific agent) and has no expiry.
2. **Mint subagents.** Call `agent.create` with `Authorization: Bearer <jwt>` and `{ name, ...optional }`. Server debits 0.10 USDC equivalent from the wallet and provisions the subagent.
3. **Run / update / delete.** Every other `agent.*` call sends `Authorization: Bearer <jwt>`. The handler resolves the target subagent by `agent_id` or `name`, verifies `agent.owner_principal === jwt.principal`, and debits the operation's price (0.02 BYOK run / smoothed all-inclusive / 0.01 dust). No Stripe round-trip per call.
4. **Top up.** Call `credits.topup` with `{ amount_usd }`, Stripe-MPP handshake on `Authorization`, AND `X-Agentmint-Bearer: <jwt>` for the existing token. Server credits the wallet and mints a fresh JWT. Pass `{ revoke_old: true }` to invalidate the prior jti in the same call.
5. **Insufficient credits.** Server returns `402` with `error.data.required_microusdc` and `error.data.available_microusdc` plus a top-up challenge. Top up and retry.
6. **Rotate a token.** Every `credits.topup` mints a fresh access token (and revokes the prior jti if `revoke_old: true`). To revoke a specific stale jti out-of-band, call `credits.revoke_token --jti <old_jti>` with any working token for the same principal.

Every credit-paid response carries an inline `_credits` block so clients see balance drift without an extra round-trip:

```json
{
  "result": { ... },
  "_credits": {
    "debited_microusdc": 2000,
    "balance_microusdc_after": 998000,
    "principal": "link_stripe:cus_…"
  }
}
```

For full audit, call `credits.history` (Bearer-only, free) — returns every topup, debit, and refund for the caller as discrete entries newest-first, with PI / run / agent refs. Capped at 1000 retained entries server-side; pass `params.limit` (default 100, max 500) to control how many you fetch:

```json
{
  "jsonrpc": "2.0", "id": 1, "method": "credits.history",
  "params": { "limit": 50 }
}
```

```json
{
  "principal": "link_stripe:cus_…",
  "count": 50,
  "entries": [
    { "ts": 1781800000000, "kind": "debit",  "amount_microusdc": 50000,
      "balance_after_microusdc": 9850000, "method": "agent.run",
      "run_id": "run_…", "agent_id": "agt_…" },
    { "ts": 1781799500000, "kind": "topup",  "amount_microusdc": 10000000,
      "balance_after_microusdc": 10000000, "method": "credits.topup",
      "pi_id": "pi_…" },
    …
  ]
}
```

### Paying with link-cli (the Stripe-Link client)

Stripe-Link is a payment-method client (Link account + saved card), not a wallet keypair. The agentmint CLI ships only the blockchain clients (x402/MPP-blockchain). For Stripe-Link payments use [link-cli](https://www.npmjs.com/package/link-cli):

```sh
npm i -g link-cli
link-cli auth login                            # one-time OAuth into Link
link-cli payment-methods list                  # confirm you have a card on file
```

**Bootstrap a wallet via `credits.topup`** (no Bearer; first Stripe charge):

```sh
# 1. Decode the 402 challenge to extract the Stripe network-id
CHAL=$(curl -sI -X POST https://api.agentmint.store/a2a \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"credits.topup","params":{"amount_usd":10}}' \
  | grep -i www-authenticate | sed 's/^[^:]*: //')
link-cli mpp decode --challenge "$CHAL"        # prints network_id: profile_...

# 2. Create + request approval for the bootstrap spend
link-cli spend-request create \
  --credential-type shared_payment_token \
  --network-id profile_… \
  --payment-method-id pm_… \
  --amount 1000 --currency usd \
  --context "Bootstrap agentmint credit wallet (\$10 USD)..."
# Returns lsrq_… and an approval URL. Approve in the Link app.

# 3. Pay — the response includes the principal-bound access_token
link-cli mpp pay https://api.agentmint.store/a2a \
  -X POST -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"credits.topup","params":{"amount_usd":10}}' \
  --spend-request-id lsrq_…
```

**Top up an existing wallet** (both Bearer AND rail handshake required):

```sh
# Spend-request creation is the same; just adjust amount + context.
link-cli mpp pay https://api.agentmint.store/a2a \
  -X POST -H 'Content-Type: application/json' \
  -H 'X-Agentmint-Bearer: <jwt-from-previous-topup>' \
  -d '{"jsonrpc":"2.0","id":1,"method":"credits.topup","params":{"amount_usd":10,"revoke_old":true}}' \
  --spend-request-id lsrq_…
```

After either flow, hand the returned `access_token` to the agentmint CLI to enable Bearer-authenticated agent ops:

```sh
agentmint credits set-token <jwt>              # one wallet token, used for any subagent
agentmint agent create --name reviewer-myrepo  # debits 0.10 USDC from the wallet
agentmint agent run --name reviewer-myrepo "..."   # debits per-call from the same wallet
```

### Blockchain-rail CLI

For the Stripe-Link rail, the agentmint CLI handles everything via the cached wallet token (bootstrap once via `credits topup`):

```sh
agentmint agent create --name foo --network base     # pay 0.10 USDC on-chain
agentmint agent run --name foo "..."                 # pay per call
agentmint credits balance                            # only meaningful for Stripe-Link wallets
agentmint credits revoke-token --jti …               # revoke a specific JWT
agentmint credits logout                             # forget the cached wallet token
```

---

## Wallet catalog (x402 / MPP CLI clients)

Third-party CLI binaries that wrap the x402/MPP handshake. (For the Stripe-Link / `link-cli` flow, see [Paying with link-cli](#paying-with-link-cli-the-stripe-link-client) above.) Each entry shows install, an auth-check command, the transport one-liner, and a worked `agent.create` example. Provisioning costs **0.10 USDC** — set CLI payment caps (where applicable) to ≥ 0.20 USDC to leave headroom.

### agentcash — x402 (Base, Solana) or MPP (Tempo)

- **Chains**: Base, Solana (x402); Tempo (MPP)
- **Install**: no install — `npx agentcash@latest`
- **Auth check**: `npx agentcash@latest accounts`
- **USDC balance**: `npx agentcash@latest balance`
- **Transport**: `npx agentcash@latest fetch <url> -m POST -b '<json>' --payment-network <base|solana|tempo>`
- **Example**:
  ```bash
  npx agentcash@latest fetch https://api.agentmint.store/a2a \
    -m POST \
    -b '{"jsonrpc":"2.0","id":1,"method":"agent.create","params":{"harness":"claude-code","model":"anthropic/claude-haiku-4-5","runtime":"node","size":"small"}}' \
    --payment-network tempo
  ```
- **Notes**: `--payment-network` flag is required — picks x402 vs MPP.

### tempo — MPP on Tempo

- **Chains**: Tempo (`eip155:4217`)
- **Install**: Tempo CLI from [docs.tempo.xyz/cli](https://docs.tempo.xyz/cli); then `tempo add request`.
- **Auth check** (also shows USDC balance): `tempo wallet whoami`
- **Transport**: `tempo request -X POST --json '<json>' <url>`
- **Example**:
  ```bash
  tempo request -X POST \
    --json '{"jsonrpc":"2.0","id":1,"method":"agent.create","params":{"harness":"claude-code","model":"anthropic/claude-haiku-4-5","runtime":"node","size":"small"}}' \
    https://api.agentmint.store/a2a
  ```

---

## agent.create

```json
{
  "jsonrpc": "2.0", "id": 1, "method": "agent.create",
  "params": {
    "name": "reviewer-myrepo",                               // optional, immutable; globally unique;
                                                             //   /^[a-z0-9][a-z0-9_-]{0,39}$/. Once
                                                             //   set, every other agent.* method
                                                             //   accepts {name} as an alternative to
                                                             //   {agent_id}.
    "mode": "byok",                                          // optional, auto-detected
    "harness": "claude-code",                                // claude-code | codex | opencode
    "model": "anthropic/claude-haiku-4-5",                   // any model the harness supports
    "api_key": "sk-ant-...",                                 // BYOK only
    "runtime": "node",                                       // node | python | golang | ruby | rust
    "size": "small",                                         // small | medium | large
    "init_command": "apk add jq && pip install requests",    // optional bootstrap
    "skills": ["moltycash/payment", "your-org/your-skill"]   // optional public GitHub skills
  }
}
```

Response (BYOK):

```json
{
  "jsonrpc": "2.0", "id": 1,
  "result": {
    "agent_id": "agt_a1b2c3d4e5f6",
    "owner_wallet": "0x...",
    "mode": "byok",
    "harness": "claude-code",
    "model": "anthropic/claude-haiku-4-5",
    "run_price_usdc": 0.02,
    "skills": ["moltycash/payment"],
    "transaction": { "hash": "0x...", "network": "base" }
  }
}
```

Save the `agent_id` — you need it for every subsequent call. The harness/model are not echoed in all-inclusive responses.

## agent.run

```json
{
  "jsonrpc": "2.0", "id": 1, "method": "agent.run",
  "params": {
    "agent_id": "agt_...",                                  // or use "name" instead
    "prompt": "Review the PR diff at /workspace/pr-42/ and append findings to /workspace/MEMORY.md.",
    "options": { "dangerouslySkipPermissions": true },      // harness-specific, optional
    "timeout": 120,                                         // optional, seconds
    "async": true,                                          // optional. fire-and-forget; returns
                                                            //   { run_id, status: "dispatched" } in
                                                            //   ~50ms; completion delivered via
                                                            //   `webhook` (QStash-backed, 5 retries)
    "webhook": {                                            // required when async:true
      "url": "https://my-host/agentmint-webhook",
      "headers": { "X-My-Trace-Id": "abc" }                 // forwarded verbatim
    },
    "cleanup_paths": [                                      // optional. server runs `rm -rf` on each
      "/workspace/pr-42",                                   //   path after the run completes. paths
      "/workspace/tmp/upload.txt"                           //   must live under /workspace/ and use
    ]                                                       //   [A-Za-z0-9._/-] only — no wildcards,
                                                            //   no parent-dir traversal. Use this for
                                                            //   per-call temp files; MEMORY.md / any
                                                            //   un-listed path persists across runs.
  }
}
```

Response:

```json
{
  "jsonrpc": "2.0", "id": 1,
  "result": {
    "run_id": "run_...",
    "output": "...",
    "billed_usdc": 0.05,
    "actual_cost_usd": 0.0083,                              // token-rate estimate
    "balance_usdc": 0.0417,                                 // smoothing balance
    "duration_ms": 4321,
    "transaction": { "hash": "0x...", "network": "base" }
  }
}
```

The sandbox filesystem persists across calls. The subagent hibernates between runs at no cost.

## agent.update / cancel / runs / get / delete (0.01 USDC each)

```json
// Update skills, init, or model
{ "method": "agent.update",
  "params": { "agent_id": "agt_...",
              "skills_add": ["moltycash/payment"],
              "model": "anthropic/claude-sonnet-4-6" } }

// Cancel an in-flight run
{ "method": "agent.cancel", "params": { "agent_id": "agt_..." } }

// List recent runs
{ "method": "agent.runs",   "params": { "agent_id": "agt_...", "limit": 10 } }

// Get current agent state (skills, init, model, balance, etc.)
{ "method": "agent.get",    "params": { "agent_id": "agt_..." } }

// Tear down the subagent
{ "method": "agent.delete", "params": { "agent_id": "agt_..." } }
```

---

## Telling the user about top-ups

Every gated call returns `402 Payment Required` first with an `accepts` array — one entry per supported chain. Extract `payTo` and `amount` for the chain your wallet uses, sign, then retry with the appropriate header (`PAYMENT-SIGNATURE` for x402, `Authorization: Payment` for MPP).

If the wallet has insufficient balance, tell the user verbatim:

> "I need to call AgentMint. Please send `<amount>` USDC to `<payTo>` on `<network>` from your wallet, then ask me again."

Don't proceed until the next call comes in.

---

## Quick examples

### `agentmint-cli` (npx, easiest)

A reference CLI lives on npm as [`agentmint-cli`](https://www.npmjs.com/package/agentmint-cli) — it's the same TypeScript x402 / MPP plumbing the SDK examples below show, packaged as a single command. Useful for shell scripts, bootstrapping a new agent, or testing without writing code.

```bash
# 1) Provision a managed (all-inclusive) subagent — picks harness + model for you
EVM_PRIVATE_KEY=0x... npx -y agentmint-cli@latest agent create
# → ✓ Created agt_abc (sonnet, 0.05 USDC/run)

# 2) BYOK variant — you supply harness, model, provider key
EVM_PRIVATE_KEY=0x... npx -y agentmint-cli@latest agent create-byok \
  --harness codex --model openai/gpt-5.3-codex --api-key "$OPENAI_API_KEY"

# 3) Send a prompt — agent_id auto-resolves from cache when only one exists
EVM_PRIVATE_KEY=0x... npx -y agentmint-cli@latest agent run "What is your name?"

# 4) Inspect / manage
npx -y agentmint-cli@latest agent get             # state, runs, spend
npx -y agentmint-cli@latest agent runs            # recent run history
npx -y agentmint-cli@latest agent update --skills-add owner/repo
npx -y agentmint-cli@latest agent cancel          # kill a stuck run
npx -y agentmint-cli@latest agent delete          # tear down
```

Output is clean human text on stdout; add `--json` for raw JSON-RPC results, `--verbose` to see Bearer chatter on stderr. The CLI is Stripe-Link only; blockchain customers pay via curl / agentcash / tempo directly to `/a2a`.

Cache lives at `~/.agentmint/agents.json`; override per-call with `AGENTMINT_AGENT_ID=agt_… npx agentmint-cli agent run "…"`.

For full CLI reference: <https://github.com/mesutcelik/agentmint-cli-repository>.

### x402 over Base (curl, EVM)

```bash
# 1. Get the 402 challenge
curl -X POST https://api.agentmint.store/a2a \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"agent.create","params":{"mode":"all-inclusive"}}'

# Response → 402 with accepts[] including a `network: "eip155:8453"` entry.
# Sign that entry's payload with your EVM wallet via @x402/core + @x402/evm.

# 2. Resubmit with the signed header
curl -X POST https://api.agentmint.store/a2a \
  -H "Content-Type: application/json" \
  -H "PAYMENT-SIGNATURE: <base64-payload>" \
  -d '{"jsonrpc":"2.0","id":1,"method":"agent.create","params":{"mode":"all-inclusive"}}'
```

### x402 over Base (TypeScript / `@x402/evm`)

```ts
import axios from "axios";
import { privateKeyToAccount } from "viem/accounts";
import { x402Client } from "@x402/core/client";
import { encodePaymentSignatureHeader } from "@x402/core/http";
import { registerExactEvmScheme } from "@x402/evm/exact/client";

const URL = "https://api.agentmint.store/a2a";
const account = privateKeyToAccount(process.env.EVM_PRIVATE_KEY as `0x${string}`);
const client = new x402Client();
registerExactEvmScheme(client, {
  signer: account,
  paymentRequirementsSelector: (_v, reqs) =>
    reqs.find(r => r.network === "eip155:8453") || reqs[0],
});

const body = { jsonrpc: "2.0", id: 1, method: "agent.create",
               params: { mode: "all-inclusive" } };

const phase1 = await axios.post(URL, body, { validateStatus: () => true });
const payload = await client.createPaymentPayload(phase1.data);
const header = encodePaymentSignatureHeader(payload);

const phase2 = await axios.post(URL, body,
  { headers: { "PAYMENT-SIGNATURE": header } });

console.log(phase2.data.result.agent_id);
```

### x402 over Solana (`@x402/svm`)

```ts
import { x402Client } from "@x402/core/client";
import { registerExactSvmScheme } from "@x402/svm/exact/client";
import { Keypair } from "@solana/web3.js";

const keypair = Keypair.fromSecretKey(/* … */);
const client = new x402Client();
registerExactSvmScheme(client, {
  signer: keypair,
  paymentRequirementsSelector: (_v, reqs) =>
    reqs.find(r => (r.network as string).startsWith("solana:")) || reqs[0],
});
// Same two-phase flow as Base.
```

### MPP over Tempo (`mppx`)

```ts
import { Mppx, tempo } from "mppx/client";
import { privateKeyToAccount } from "viem/accounts";

const account = privateKeyToAccount(process.env.TEMPO_PRIVATE_KEY as `0x${string}`);
const client = Mppx.create({ methods: [tempo.charge({ signer: account })] });

// Single call — the client auto-handles the 402, signs, and retries.
const res = await client.fetch("https://api.agentmint.store/a2a", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "agent.create",
                         params: { mode: "all-inclusive" } }),
});
```

---

## Agentic wallet support

Any wallet that can sign x402 or MPP payment payloads works. AgentMint is wallet-agnostic — it only sees the on-chain transaction. Pick whichever fits how your agent stores keys:

**EVM (Base, Tempo)**

| Wallet                      | How to use it                                                                                  |
|-----------------------------|------------------------------------------------------------------------------------------------|
| Plain private key + viem    | `privateKeyToAccount(pk)` → pass to `@x402/evm` or `mppx`. Lowest dependency footprint.        |
| Coinbase CDP (server)       | `cdp.evm.createAccount()` returns a viem-compatible signer; works with `@x402/evm` directly.   |
| Bankr                       | EVM-only OAuth-style API; once you hold the agent's signer, it plugs into `@x402/evm`.         |
| Privy embedded              | Privy SDK exposes a viem-compatible signer for embedded users; pass to `@x402/evm`/`mppx`.     |
| Dynamic / Magic / Web3Auth  | All return EVM signers compatible with viem — same wiring as the plain-PK path.                |
| WorldID + MiniKit           | Pass the World App-issued EVM signer to `@x402/evm` with `network: "eip155:480"`.              |
| RainbowKit / wagmi (browser)| Use `useWalletClient()` and forward the account into `@x402/evm`.                              |

**Solana**

| Wallet                | How to use it                                                                       |
|-----------------------|-------------------------------------------------------------------------------------|
| `@solana/web3.js`     | `Keypair.fromSecretKey(...)` → pass to `@x402/svm/exact/client`.                    |
| Privy / Dynamic       | Both expose Solana signers that work with `@x402/svm`.                              |
| Phantom (browser)     | `window.solana` provider → use the wallet adapter, then forward to `@x402/svm`.     |
| Backpack / Solflare   | Standard wallet adapter pattern, same as Phantom.                                   |
| Coinbase CDP (Solana) | `cdp.solana.createAccount()` returns a signer compatible with `@x402/svm`.          |

**Tempo**

Tempo is an EVM chain and accepts any EVM signer (see the EVM table). Settlement goes through `mppx`'s `tempo` charge method.

The same agent can hold multiple wallets and pick whichever has the cheapest gas / shortest path for a given call. The 402 challenge enumerates every chain AgentMint supports — pick one your agent is funded on.

## Limits

- ~10 concurrent active subagents per wallet.
- One in-flight run per subagent (use multiple subagents for parallelism).
- Idle subagents hibernate at no cost; first call after long idle pays a few seconds of resume latency, no extra USDC.

---

## Errors

- `-32000 PAYMENT_FAILED` — bad/missing payment header or insufficient amount
- `-32602 INVALID_PARAMS` — missing required field, unsupported harness, etc.
- `-32603 INTERNAL_ERROR` — provisioning timeout or upstream error
- `-32001 NOT_FOUND` — agent_id doesn't exist
- `-32002 NOT_OWNER` — payer wallet doesn't match `owner_wallet` for this agent

For transient settlement issues the API auto-retries up to 5× before surfacing the error.
